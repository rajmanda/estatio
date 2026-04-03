"""
maintenance.py  (router)
------------------------
Maintenance workflow router for the Estatio property management platform.

Endpoints:
    GET    /                          → list work orders (filters: property_id, status, priority, category)
    POST   /                          → create work order
    GET    /{id}                      → get work order detail
    PUT    /{id}                      → update work order fields
    POST   /{id}/status               → update status with note
    POST   /{id}/estimates            → submit vendor estimate
    POST   /{id}/select-estimate      → select winning estimate
    POST   /{id}/approve              → approve work order
    POST   /{id}/complete             → mark completed with actual cost
    GET    /preventive/schedules      → list preventive maintenance schedules
    POST   /preventive/schedules      → create preventive schedule
    GET    /summary                   → maintenance summary stats
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import structlog
from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.core.auth import (
    get_current_active_user,
    require_manager_or_admin,
    require_owner_or_above,
)
from app.core.database import get_db
from app.models.maintenance import (
    EstimateLine,
    PreventiveMaintenanceDB,
    StatusHistoryEntry,
    VendorEstimate,
    WorkOrderCategory,
    WorkOrderDB,
    WorkOrderPriority,
    WorkOrderStatus,
)

log = structlog.get_logger()

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class WorkOrderCreateRequest(BaseModel):
    property_id: str
    unit_id: Optional[str] = None
    title: str
    description: str
    category: WorkOrderCategory
    priority: WorkOrderPriority = WorkOrderPriority.MEDIUM
    reported_by_type: str = "owner"  # tenant | owner | manager | system
    scheduled_date: Optional[date] = None
    notes: Optional[str] = None
    images: List[str] = []


class WorkOrderUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[WorkOrderCategory] = None
    priority: Optional[WorkOrderPriority] = None
    assigned_vendor_id: Optional[str] = None
    scheduled_date: Optional[date] = None
    notes: Optional[str] = None
    images: Optional[List[str]] = None
    documents: Optional[List[str]] = None


class StatusUpdateRequest(BaseModel):
    status: WorkOrderStatus
    note: Optional[str] = None


class EstimateRequest(BaseModel):
    vendor_id: str
    vendor_name: str
    labor_cost: float = 0.0
    materials_cost: float = 0.0
    total_amount: float
    estimated_duration_hours: Optional[float] = None
    notes: Optional[str] = None
    line_items: List[EstimateLine] = []
    document_id: Optional[str] = None


class SelectEstimateRequest(BaseModel):
    vendor_id: str


class ApproveRequest(BaseModel):
    approved_amount: float
    note: Optional[str] = None


class CompleteRequest(BaseModel):
    actual_cost: float
    note: Optional[str] = None
    tenant_rating: Optional[int] = Field(None, ge=1, le=5)


class PreventiveScheduleCreateRequest(BaseModel):
    property_id: str
    title: str
    description: str
    category: WorkOrderCategory
    frequency: str  # monthly | quarterly | semi-annual | annual
    month_of_year: Optional[List[int]] = None
    day_of_month: int = 1
    next_due_date: date
    estimated_cost: Optional[float] = None
    preferred_vendor_id: Optional[str] = None
    auto_create_work_order: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_work_order_or_404(
    db: AsyncIOMotorDatabase, work_order_id: str
) -> Dict[str, Any]:
    """Fetch a work order by ID, raising 404 if not found."""
    try:
        raw = await db.work_orders.find_one({"_id": ObjectId(work_order_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid work order ID"
        )
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Work order not found"
        )
    return raw


def _wo_to_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a MongoDB work order document for API response."""
    raw["id"] = str(raw.pop("_id"))
    return raw


async def _next_wo_number(db: AsyncIOMotorDatabase) -> str:
    """Generate a sequential work order number WO-{YEAR}-{SEQ:06d}."""
    year = datetime.utcnow().year
    prefix = f"WO-{year}-"
    last = await db.work_orders.find_one(
        {"work_order_number": {"$regex": f"^{prefix}"}},
        sort=[("work_order_number", -1)],
    )
    if last:
        try:
            seq = int(last["work_order_number"].split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:06d}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/summary")
async def get_maintenance_summary(
    property_id: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_active_user),
):
    """
    Return aggregate maintenance statistics.
    Optionally scoped to a specific property.
    """
    match_filter: Dict[str, Any] = {}
    if property_id:
        match_filter["property_id"] = property_id

    pipeline = [
        {"$match": match_filter},
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1},
                "total_cost": {"$sum": {"$ifNull": ["$actual_cost", 0]}},
            }
        },
    ]

    status_counts: Dict[str, int] = {}
    total_cost = 0.0
    async for row in db.work_orders.aggregate(pipeline):
        s = str(row["_id"])
        status_counts[s] = row["count"]
        total_cost += float(row.get("total_cost", 0.0))

    priority_pipeline = [
        {
            "$match": {
                **match_filter,
                "status": {"$nin": ["completed", "closed", "cancelled"]},
            }
        },
        {"$group": {"_id": "$priority", "count": {"$sum": 1}}},
    ]
    priority_counts: Dict[str, int] = {}
    async for row in db.work_orders.aggregate(priority_pipeline):
        priority_counts[str(row["_id"])] = row["count"]

    category_pipeline = [
        {"$match": match_filter},
        {
            "$group": {
                "_id": "$category",
                "count": {"$sum": 1},
                "total_cost": {"$sum": {"$ifNull": ["$actual_cost", 0]}},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    category_stats: List[Dict[str, Any]] = []
    async for row in db.work_orders.aggregate(category_pipeline):
        category_stats.append(
            {
                "category": str(row["_id"]),
                "count": row["count"],
                "total_cost": round(float(row.get("total_cost", 0.0)), 2),
            }
        )

    total_open = sum(
        v
        for k, v in status_counts.items()
        if k not in ("completed", "closed", "cancelled")
    )

    return {
        "total_open": total_open,
        "total_cost_completed": round(total_cost, 2),
        "by_status": status_counts,
        "by_priority": priority_counts,
        "by_category": category_stats,
    }


@router.get("/preventive/schedules")
async def list_preventive_schedules(
    property_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_active_user),
):
    """List preventive maintenance schedules."""
    query: Dict[str, Any] = {}
    if property_id:
        query["property_id"] = property_id
    if is_active is not None:
        query["is_active"] = is_active

    cursor = (
        db.preventive_maintenance.find(query)
        .sort("next_due_date", 1)
        .skip(skip)
        .limit(limit)
    )

    results = []
    async for raw in cursor:
        raw["id"] = str(raw.pop("_id"))
        results.append(raw)

    total = await db.preventive_maintenance.count_documents(query)
    return {"total": total, "items": results, "skip": skip, "limit": limit}


@router.post("/preventive/schedules", status_code=status.HTTP_201_CREATED)
async def create_preventive_schedule(
    body: PreventiveScheduleCreateRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_manager_or_admin),
):
    """Create a new preventive maintenance schedule."""
    schedule_id = str(ObjectId())
    now = datetime.utcnow()

    schedule = PreventiveMaintenanceDB(
        _id=schedule_id,
        property_id=body.property_id,
        title=body.title,
        description=body.description,
        category=body.category,
        frequency=body.frequency,
        month_of_year=body.month_of_year,
        day_of_month=body.day_of_month,
        next_due_date=body.next_due_date,
        estimated_cost=body.estimated_cost,
        preferred_vendor_id=body.preferred_vendor_id,
        auto_create_work_order=body.auto_create_work_order,
        is_active=True,
        created_at=now,
    )

    doc_dict = schedule.model_dump(by_alias=False)
    doc_dict["_id"] = ObjectId(schedule_id)
    await db.preventive_maintenance.insert_one(doc_dict)

    doc_dict["id"] = str(doc_dict.pop("_id"))
    log.info("Preventive schedule created", schedule_id=schedule_id)
    return doc_dict


@router.get("/")
async def list_work_orders(
    property_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    priority: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    assigned_vendor_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_active_user),
):
    """
    List work orders with optional filters.

    Filters:
        property_id, status, priority, category, assigned_vendor_id
    """
    query: Dict[str, Any] = {}
    if property_id:
        query["property_id"] = property_id
    if status_filter:
        # Support comma-separated list for multi-status filter
        statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
        query["status"] = {"$in": statuses} if len(statuses) > 1 else statuses[0]
    if priority:
        query["priority"] = priority
    if category:
        query["category"] = category
    if assigned_vendor_id:
        query["assigned_vendor_id"] = assigned_vendor_id

    cursor = db.work_orders.find(query).sort("created_at", -1).skip(skip).limit(limit)

    results = []
    async for raw in cursor:
        results.append(_wo_to_response(raw))

    total = await db.work_orders.count_documents(query)
    return {"total": total, "items": results, "skip": skip, "limit": limit}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_work_order(
    body: WorkOrderCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_active_user),
):
    """Create a new work order."""
    from app.services.notification_service import notify_work_order_update

    wo_number = await _next_wo_number(db)
    wo_id = str(ObjectId())
    now = datetime.utcnow()
    user_id = str(current_user["_id"])

    initial_history = StatusHistoryEntry(
        status=WorkOrderStatus.SUBMITTED,
        changed_at=now,
        changed_by=user_id,
        note="Work order submitted",
    )

    wo = WorkOrderDB(
        _id=wo_id,
        work_order_number=wo_number,
        property_id=body.property_id,
        unit_id=body.unit_id,
        title=body.title,
        description=body.description,
        category=body.category,
        priority=body.priority,
        status=WorkOrderStatus.SUBMITTED,
        reported_by=user_id,
        reported_by_type=body.reported_by_type,
        scheduled_date=body.scheduled_date,
        notes=body.notes,
        images=body.images,
        status_history=[initial_history],
        created_at=now,
        updated_at=now,
    )

    doc_dict = wo.model_dump(by_alias=False)
    doc_dict["_id"] = ObjectId(wo_id)
    # Serialize nested models
    doc_dict["status_history"] = [h.model_dump() for h in wo.status_history]
    await db.work_orders.insert_one(doc_dict)

    log.info("Work order created", wo_id=wo_id, wo_number=wo_number)

    # Send notification (fire-and-forget)
    background_tasks.add_task(
        notify_work_order_update,
        db,
        wo,
        f"Work order {wo_number} has been submitted.",
    )

    doc_dict["id"] = str(doc_dict.pop("_id"))
    return doc_dict


@router.get("/{work_order_id}")
async def get_work_order(
    work_order_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_active_user),
):
    """Get a single work order by ID."""
    raw = await _get_work_order_or_404(db, work_order_id)
    return _wo_to_response(raw)


@router.put("/{work_order_id}")
async def update_work_order(
    work_order_id: str,
    body: WorkOrderUpdateRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_active_user),
):
    """Update work order fields."""
    await _get_work_order_or_404(db, work_order_id)

    updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
    for field, value in body.model_dump(exclude_none=True).items():
        updates[field] = value

    await db.work_orders.update_one(
        {"_id": ObjectId(work_order_id)},
        {"$set": updates},
    )

    raw = await db.work_orders.find_one({"_id": ObjectId(work_order_id)})
    return _wo_to_response(raw)


@router.post("/{work_order_id}/status")
async def update_work_order_status(
    work_order_id: str,
    body: StatusUpdateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_active_user),
):
    """
    Update the status of a work order and append an entry to status_history.
    """
    from app.services.notification_service import notify_work_order_update

    await _get_work_order_or_404(db, work_order_id)
    user_id = str(current_user["_id"])
    now = datetime.utcnow()

    history_entry = StatusHistoryEntry(
        status=body.status,
        changed_at=now,
        changed_by=user_id,
        note=body.note,
    )

    await db.work_orders.update_one(
        {"_id": ObjectId(work_order_id)},
        {
            "$set": {"status": body.status.value, "updated_at": now},
            "$push": {"status_history": history_entry.model_dump()},
        },
    )

    log.info(
        "Work order status updated",
        wo_id=work_order_id,
        new_status=body.status,
    )

    # Re-fetch and notify
    updated_raw = await db.work_orders.find_one({"_id": ObjectId(work_order_id)})
    msg = (
        body.note or f"Status updated to {body.status.value.replace('_', ' ').title()}."
    )
    background_tasks.add_task(notify_work_order_update, db, updated_raw, msg)

    return _wo_to_response(updated_raw)


@router.post("/{work_order_id}/estimates", status_code=status.HTTP_201_CREATED)
async def submit_estimate(
    work_order_id: str,
    body: EstimateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_active_user),
):
    """
    Submit a vendor estimate for a work order.
    """
    from app.services.notification_service import notify_work_order_update

    await _get_work_order_or_404(db, work_order_id)
    now = datetime.utcnow()

    estimate = VendorEstimate(
        vendor_id=body.vendor_id,
        vendor_name=body.vendor_name,
        submitted_at=now,
        labor_cost=body.labor_cost,
        materials_cost=body.materials_cost,
        total_amount=body.total_amount,
        estimated_duration_hours=body.estimated_duration_hours,
        notes=body.notes,
        line_items=body.line_items,
        is_selected=False,
        document_id=body.document_id,
    )

    await db.work_orders.update_one(
        {"_id": ObjectId(work_order_id)},
        {
            "$push": {"estimates": estimate.model_dump()},
            "$set": {
                "status": WorkOrderStatus.ESTIMATE_RECEIVED.value,
                "updated_at": now,
            },
        },
    )

    log.info("Estimate submitted", wo_id=work_order_id, vendor_id=body.vendor_id)

    updated_raw = await db.work_orders.find_one({"_id": ObjectId(work_order_id)})
    background_tasks.add_task(
        notify_work_order_update,
        db,
        updated_raw,
        f"Estimate received from {body.vendor_name} for ${body.total_amount:,.2f}.",
    )

    return _wo_to_response(updated_raw)


@router.post("/{work_order_id}/select-estimate")
async def select_estimate(
    work_order_id: str,
    body: SelectEstimateRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_owner_or_above),
):
    """
    Select the winning vendor estimate and move to AWAITING_APPROVAL.
    """
    raw = await _get_work_order_or_404(db, work_order_id)

    estimates: List[Dict[str, Any]] = raw.get("estimates", [])
    selected: Optional[Dict[str, Any]] = None
    updated_estimates: List[Dict[str, Any]] = []

    for est in estimates:
        est["is_selected"] = est["vendor_id"] == body.vendor_id
        if est["is_selected"]:
            selected = est
        updated_estimates.append(est)

    if not selected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No estimate found for vendor_id '{body.vendor_id}'",
        )

    now = datetime.utcnow()
    history_entry = StatusHistoryEntry(
        status=WorkOrderStatus.AWAITING_APPROVAL,
        changed_at=now,
        changed_by=str(current_user["_id"]),
        note=f"Selected estimate from {selected.get('vendor_name', body.vendor_id)}",
    )

    await db.work_orders.update_one(
        {"_id": ObjectId(work_order_id)},
        {
            "$set": {
                "estimates": updated_estimates,
                "selected_estimate": selected,
                "assigned_vendor_id": body.vendor_id,
                "status": WorkOrderStatus.AWAITING_APPROVAL.value,
                "updated_at": now,
            },
            "$push": {"status_history": history_entry.model_dump()},
        },
    )

    raw = await db.work_orders.find_one({"_id": ObjectId(work_order_id)})
    return _wo_to_response(raw)


@router.post("/{work_order_id}/approve")
async def approve_work_order(
    work_order_id: str,
    body: ApproveRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_owner_or_above),
):
    """
    Approve a work order with the agreed amount and advance to APPROVED status.
    """
    raw = await _get_work_order_or_404(db, work_order_id)

    if raw.get("status") not in (
        WorkOrderStatus.AWAITING_APPROVAL.value,
        WorkOrderStatus.ESTIMATE_RECEIVED.value,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Work order is not in a state that can be approved",
        )

    user_id = str(current_user["_id"])
    now = datetime.utcnow()
    history_entry = StatusHistoryEntry(
        status=WorkOrderStatus.APPROVED,
        changed_at=now,
        changed_by=user_id,
        note=body.note or f"Approved for ${body.approved_amount:,.2f}",
    )

    await db.work_orders.update_one(
        {"_id": ObjectId(work_order_id)},
        {
            "$set": {
                "status": WorkOrderStatus.APPROVED.value,
                "approved_by": user_id,
                "approved_at": now,
                "approved_amount": body.approved_amount,
                "updated_at": now,
            },
            "$push": {"status_history": history_entry.model_dump()},
        },
    )

    log.info("Work order approved", wo_id=work_order_id, amount=body.approved_amount)
    raw = await db.work_orders.find_one({"_id": ObjectId(work_order_id)})
    return _wo_to_response(raw)


@router.post("/{work_order_id}/complete")
async def complete_work_order(
    work_order_id: str,
    body: CompleteRequest,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_manager_or_admin),
):
    """
    Mark a work order as completed with the actual cost incurred.
    """
    from app.services.notification_service import notify_work_order_update

    raw = await _get_work_order_or_404(db, work_order_id)

    user_id = str(current_user["_id"])
    now = datetime.utcnow()
    today = date.today()

    history_entry = StatusHistoryEntry(
        status=WorkOrderStatus.COMPLETED,
        changed_at=now,
        changed_by=user_id,
        note=body.note or f"Completed. Actual cost: ${body.actual_cost:,.2f}",
    )

    update_fields: Dict[str, Any] = {
        "status": WorkOrderStatus.COMPLETED.value,
        "actual_cost": body.actual_cost,
        "completed_date": today.isoformat(),
        "updated_at": now,
    }
    if body.tenant_rating is not None:
        update_fields["tenant_rating"] = body.tenant_rating

    await db.work_orders.update_one(
        {"_id": ObjectId(work_order_id)},
        {
            "$set": update_fields,
            "$push": {"status_history": history_entry.model_dump()},
        },
    )

    log.info("Work order completed", wo_id=work_order_id, actual_cost=body.actual_cost)

    updated_raw = await db.work_orders.find_one({"_id": ObjectId(work_order_id)})
    background_tasks.add_task(
        notify_work_order_update,
        db,
        updated_raw,
        f"Work order {raw.get('work_order_number', work_order_id)} has been completed. "
        f"Actual cost: ${body.actual_cost:,.2f}.",
    )

    return _wo_to_response(updated_raw)
