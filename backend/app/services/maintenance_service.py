"""
maintenance_service.py
----------------------
Maintenance workflow engine for the Estatio property management platform.

Responsibilities:
  - Create and track work orders with full status-lifecycle management
  - Request and select vendor estimates
  - Approve and complete work orders with expense journal entries
  - Run preventive-maintenance schedules to auto-create work orders
  - Provide aggregate maintenance statistics per property / owner

MongoDB collections used:
  work_orders                 - WorkOrderDB
  preventive_maintenance      - PreventiveMaintenanceDB
  vendors                     - VendorDB
  notifications               - NotificationDB
  ownerships                  - OwnershipDB (to resolve property → owner)
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.maintenance import (
    WorkOrderCategory,
    WorkOrderPriority,
    WorkOrderStatus,
)
from app.services.accounting_service import create_journal_entry

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _new_id() -> str:
    return str(ObjectId())


def _round2(value: float) -> float:
    return round(value, 2)


async def _next_work_order_number(db: AsyncIOMotorDatabase) -> str:
    """Generate WO-{YEAR}-{SEQUENCE:06d}."""
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


async def _get_property_owner_ids(
    db: AsyncIOMotorDatabase, property_id: str
) -> List[str]:
    """Return all owner user_ids linked to a property via ownerships."""
    owner_ids: List[str] = []
    async for ownership in db.ownerships.find({"property_id": property_id}):
        owner_ids.append(ownership["owner_id"])
    return owner_ids


async def _send_notification(
    db: AsyncIOMotorDatabase,
    user_id: str,
    notif_type: str,
    title: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    action_url: Optional[str] = None,
    priority: str = "normal",
) -> None:
    doc: Dict[str, Any] = {
        "_id": _new_id(),
        "user_id": user_id,
        "type": notif_type,
        "title": title,
        "message": message,
        "data": data or {},
        "read": False,
        "read_at": None,
        "action_url": action_url,
        "priority": priority,
        "created_at": datetime.utcnow(),
    }
    await db.notifications.insert_one(doc)
    log.debug("Notification sent", user_id=user_id, type=notif_type)


# ---------------------------------------------------------------------------
# Status transition map
# ---------------------------------------------------------------------------

# Each status maps to a set of statuses it may legally advance to.
_ALLOWED_TRANSITIONS: Dict[WorkOrderStatus, List[WorkOrderStatus]] = {
    WorkOrderStatus.SUBMITTED: [
        WorkOrderStatus.TRIAGED,
        WorkOrderStatus.CANCELLED,
    ],
    WorkOrderStatus.TRIAGED: [
        WorkOrderStatus.ESTIMATE_REQUESTED,
        WorkOrderStatus.APPROVED,  # manager can skip estimates
        WorkOrderStatus.CANCELLED,
    ],
    WorkOrderStatus.ESTIMATE_REQUESTED: [
        WorkOrderStatus.ESTIMATE_RECEIVED,
        WorkOrderStatus.CANCELLED,
    ],
    WorkOrderStatus.ESTIMATE_RECEIVED: [
        WorkOrderStatus.AWAITING_APPROVAL,
        WorkOrderStatus.ESTIMATE_REQUESTED,  # re-request
        WorkOrderStatus.CANCELLED,
    ],
    WorkOrderStatus.AWAITING_APPROVAL: [
        WorkOrderStatus.APPROVED,
        WorkOrderStatus.ESTIMATE_REQUESTED,  # send back for re-estimate
        WorkOrderStatus.CANCELLED,
    ],
    WorkOrderStatus.APPROVED: [
        WorkOrderStatus.SCHEDULED,
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.CANCELLED,
    ],
    WorkOrderStatus.SCHEDULED: [
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.CANCELLED,
    ],
    WorkOrderStatus.IN_PROGRESS: [
        WorkOrderStatus.COMPLETED,
        WorkOrderStatus.CANCELLED,
    ],
    WorkOrderStatus.COMPLETED: [
        WorkOrderStatus.INVOICED,
        WorkOrderStatus.CLOSED,
    ],
    WorkOrderStatus.INVOICED: [
        WorkOrderStatus.CLOSED,
    ],
    WorkOrderStatus.CLOSED: [],
    WorkOrderStatus.CANCELLED: [],
}


# ---------------------------------------------------------------------------
# Create work order
# ---------------------------------------------------------------------------


async def create_work_order(
    db: AsyncIOMotorDatabase,
    wo_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a new work order.

    ``wo_data`` keys:
        property_id     - str (required)
        title           - str (required)
        description     - str (required)
        category        - WorkOrderCategory value (required)
        priority        - WorkOrderPriority value (default: MEDIUM)
        reported_by     - str user_id (required)
        reported_by_type- str (tenant | owner | manager | system)
        unit_id         - str (optional)
        images          - list of str GCS paths (optional)
        notes           - str (optional)
        is_recurring    - bool (optional)
        preventive_schedule_id - str (optional)

    Effects:
      - Auto-generates work_order_number (WO-{YEAR}-{SEQ:06d})
      - Creates the work order document with status SUBMITTED
      - Sends notifications to all property owners
    """
    logger = log.bind(
        action="create_work_order",
        property_id=wo_data.get("property_id"),
    )
    logger.info("Creating work order")

    wo_number = await _next_work_order_number(db)
    wo_id = _new_id()
    now = datetime.utcnow()

    priority_str = wo_data.get("priority", WorkOrderPriority.MEDIUM.value)
    category_str = wo_data.get("category", WorkOrderCategory.GENERAL.value)
    property_id = wo_data["property_id"]
    reported_by = wo_data.get("reported_by", "system")

    initial_history_entry = {
        "status": WorkOrderStatus.SUBMITTED.value,
        "changed_at": now,
        "changed_by": reported_by,
        "note": "Work order submitted",
    }

    doc: Dict[str, Any] = {
        "_id": wo_id,
        "work_order_number": wo_number,
        "property_id": property_id,
        "unit_id": wo_data.get("unit_id"),
        "title": wo_data["title"],
        "description": wo_data["description"],
        "category": category_str,
        "priority": priority_str,
        "status": WorkOrderStatus.SUBMITTED.value,
        "reported_by": reported_by,
        "reported_by_type": wo_data.get("reported_by_type", "tenant"),
        "assigned_vendor_id": None,
        "estimates": [],
        "selected_estimate": None,
        "approved_by": None,
        "approved_at": None,
        "approved_amount": None,
        "scheduled_date": None,
        "completed_date": None,
        "actual_cost": None,
        "journal_entry_id": None,
        "images": wo_data.get("images", []),
        "documents": [],
        "status_history": [initial_history_entry],
        "notes": wo_data.get("notes"),
        "tenant_rating": None,
        "is_recurring": wo_data.get("is_recurring", False),
        "preventive_schedule_id": wo_data.get("preventive_schedule_id"),
        "created_at": now,
        "updated_at": now,
    }

    await db.work_orders.insert_one(doc)

    # Notify property owners
    owner_ids = await _get_property_owner_ids(db, property_id)
    notification_tasks = [
        _send_notification(
            db,
            user_id=owner_id,
            notif_type="maintenance_submitted",
            title=f"New Work Order: {wo_data['title']}",
            message=(
                f"A new {priority_str} priority maintenance request "
                f"({wo_number}) has been submitted for your property."
            ),
            data={
                "work_order_id": wo_id,
                "work_order_number": wo_number,
                "category": category_str,
                "priority": priority_str,
            },
            action_url=f"/maintenance/{wo_id}",
            priority="high"
            if priority_str == WorkOrderPriority.EMERGENCY.value
            else "normal",
        )
        for owner_id in owner_ids
    ]
    if notification_tasks:
        await asyncio.gather(*notification_tasks, return_exceptions=True)

    logger.info(
        "Work order created",
        wo_id=wo_id,
        wo_number=wo_number,
        priority=priority_str,
    )
    return doc


# ---------------------------------------------------------------------------
# Update work order status
# ---------------------------------------------------------------------------


async def update_work_order_status(
    db: AsyncIOMotorDatabase,
    wo_id: str,
    new_status: WorkOrderStatus,
    user_id: str,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Advance a work order to a new status, enforcing valid transitions.

    Records the transition in status_history and notifies property owners.

    Raises ValueError for invalid work order IDs or disallowed transitions.
    """
    logger = log.bind(
        action="update_work_order_status",
        wo_id=wo_id,
        new_status=new_status.value,
    )

    wo = await db.work_orders.find_one({"_id": wo_id})
    if not wo:
        raise ValueError(f"Work order {wo_id} not found")

    current = WorkOrderStatus(wo["status"])
    allowed = _ALLOWED_TRANSITIONS.get(current, [])
    if new_status not in allowed:
        raise ValueError(
            f"Cannot transition work order from '{current.value}' to '{new_status.value}'. "
            f"Allowed transitions: {[s.value for s in allowed]}"
        )

    now = datetime.utcnow()
    history_entry: Dict[str, Any] = {
        "status": new_status.value,
        "changed_at": now,
        "changed_by": user_id,
        "note": note,
    }

    update: Dict[str, Any] = {
        "$set": {
            "status": new_status.value,
            "updated_at": now,
        },
        "$push": {"status_history": history_entry},
    }

    await db.work_orders.update_one({"_id": wo_id}, update)

    # Notify owners of meaningful state changes
    notify_statuses = {
        WorkOrderStatus.TRIAGED,
        WorkOrderStatus.APPROVED,
        WorkOrderStatus.SCHEDULED,
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.COMPLETED,
        WorkOrderStatus.CANCELLED,
    }
    if new_status in notify_statuses:
        owner_ids = await _get_property_owner_ids(db, wo["property_id"])
        tasks = [
            _send_notification(
                db,
                user_id=oid,
                notif_type="maintenance_updated",
                title=f"Work Order {wo['work_order_number']} - {new_status.value.replace('_', ' ').title()}",
                message=(
                    f"Work order {wo['work_order_number']} ({wo['title']}) "
                    f"has been updated to {new_status.value.replace('_', ' ')}."
                    + (f" Note: {note}" if note else "")
                ),
                data={
                    "work_order_id": wo_id,
                    "work_order_number": wo["work_order_number"],
                    "new_status": new_status.value,
                },
                action_url=f"/maintenance/{wo_id}",
            )
            for oid in owner_ids
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(
        "Work order status updated",
        wo_number=wo["work_order_number"],
        from_status=current.value,
        to_status=new_status.value,
    )

    wo["status"] = new_status.value
    wo["updated_at"] = now
    return wo


# ---------------------------------------------------------------------------
# Request estimates
# ---------------------------------------------------------------------------


async def request_estimates(
    db: AsyncIOMotorDatabase,
    wo_id: str,
    vendor_ids: List[str],
) -> Dict[str, Any]:
    """
    Send estimate requests to a list of vendors.

    For each vendor:
      - Looks up the vendor document to obtain name and email.
      - Creates an in-app notification for the vendor's portal user (if any).
      - Adds a stub VendorEstimate placeholder to the work order's estimates list.

    Advances status to ESTIMATE_REQUESTED.

    Returns the updated work order.
    """
    logger = log.bind(action="request_estimates", wo_id=wo_id)

    wo = await db.work_orders.find_one({"_id": wo_id})
    if not wo:
        raise ValueError(f"Work order {wo_id} not found")

    now = datetime.utcnow()
    stub_estimates: List[Dict[str, Any]] = list(wo.get("estimates", []))
    existing_vendor_ids = {e["vendor_id"] for e in stub_estimates}

    tasks: List[Any] = []
    for vendor_id in vendor_ids:
        if vendor_id in existing_vendor_ids:
            continue

        vendor = await db.vendors.find_one({"_id": vendor_id})
        if not vendor:
            logger.warning("Vendor not found, skipping", vendor_id=vendor_id)
            continue

        vendor_name = vendor.get("name", vendor_id)
        stub: Dict[str, Any] = {
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "submitted_at": now,
            "labor_cost": 0.0,
            "materials_cost": 0.0,
            "total_amount": 0.0,
            "estimated_duration_hours": None,
            "notes": None,
            "line_items": [],
            "is_selected": False,
            "document_id": None,
        }
        stub_estimates.append(stub)
        existing_vendor_ids.add(vendor_id)

        # Notify vendor portal user if they have one
        portal_user_id = vendor.get("portal_user_id")
        if portal_user_id:
            tasks.append(
                _send_notification(
                    db,
                    user_id=portal_user_id,
                    notif_type="vendor_estimate",
                    title=f"Estimate Request - {wo['work_order_number']}",
                    message=(
                        f"You have been asked to submit an estimate for work order "
                        f"{wo['work_order_number']}: {wo['title']}."
                    ),
                    data={
                        "work_order_id": wo_id,
                        "work_order_number": wo["work_order_number"],
                        "vendor_id": vendor_id,
                    },
                    action_url=f"/vendor/estimates/{wo_id}",
                    priority="normal",
                )
            )

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    # Advance to ESTIMATE_REQUESTED
    new_status = WorkOrderStatus.ESTIMATE_REQUESTED
    history_entry = {
        "status": new_status.value,
        "changed_at": now,
        "changed_by": "system",
        "note": f"Estimate requests sent to {len(vendor_ids)} vendor(s)",
    }

    await db.work_orders.update_one(
        {"_id": wo_id},
        {
            "$set": {
                "estimates": stub_estimates,
                "status": new_status.value,
                "updated_at": now,
            },
            "$push": {"status_history": history_entry},
        },
    )

    logger.info(
        "Estimates requested",
        wo_number=wo["work_order_number"],
        vendor_count=len(vendor_ids),
    )

    wo["estimates"] = stub_estimates
    wo["status"] = new_status.value
    return wo


# ---------------------------------------------------------------------------
# Select estimate
# ---------------------------------------------------------------------------


async def select_estimate(
    db: AsyncIOMotorDatabase,
    wo_id: str,
    vendor_id: str,
) -> Dict[str, Any]:
    """
    Mark a vendor's estimate as selected and advance status to AWAITING_APPROVAL.

    Raises ValueError if no estimate from that vendor exists on the work order.
    """
    logger = log.bind(action="select_estimate", wo_id=wo_id, vendor_id=vendor_id)

    wo = await db.work_orders.find_one({"_id": wo_id})
    if not wo:
        raise ValueError(f"Work order {wo_id} not found")

    estimates: List[Dict[str, Any]] = wo.get("estimates", [])
    selected: Optional[Dict[str, Any]] = None

    for est in estimates:
        if est["vendor_id"] == vendor_id:
            est["is_selected"] = True
            selected = est
        else:
            est["is_selected"] = False

    if selected is None:
        raise ValueError(
            f"No estimate from vendor {vendor_id} found on work order {wo_id}"
        )

    now = datetime.utcnow()
    history_entry = {
        "status": WorkOrderStatus.AWAITING_APPROVAL.value,
        "changed_at": now,
        "changed_by": "system",
        "note": f"Estimate selected from vendor {selected.get('vendor_name', vendor_id)} "
        f"(${selected.get('total_amount', 0):.2f})",
    }

    await db.work_orders.update_one(
        {"_id": wo_id},
        {
            "$set": {
                "estimates": estimates,
                "selected_estimate": selected,
                "assigned_vendor_id": vendor_id,
                "status": WorkOrderStatus.AWAITING_APPROVAL.value,
                "updated_at": now,
            },
            "$push": {"status_history": history_entry},
        },
    )

    # Notify property owners to review and approve
    owner_ids = await _get_property_owner_ids(db, wo["property_id"])
    tasks = [
        _send_notification(
            db,
            user_id=oid,
            notif_type="maintenance_updated",
            title=f"Approval Required - {wo['work_order_number']}",
            message=(
                f"An estimate of ${selected.get('total_amount', 0):.2f} from "
                f"{selected.get('vendor_name', 'a vendor')} is awaiting your approval "
                f"for work order {wo['work_order_number']}."
            ),
            data={
                "work_order_id": wo_id,
                "vendor_id": vendor_id,
                "amount": selected.get("total_amount", 0),
            },
            action_url=f"/maintenance/{wo_id}",
            priority="high",
        )
        for oid in owner_ids
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(
        "Estimate selected",
        wo_number=wo["work_order_number"],
        vendor_id=vendor_id,
        amount=selected.get("total_amount", 0),
    )

    wo["estimates"] = estimates
    wo["selected_estimate"] = selected
    wo["status"] = WorkOrderStatus.AWAITING_APPROVAL.value
    return wo


# ---------------------------------------------------------------------------
# Approve work order
# ---------------------------------------------------------------------------


async def approve_work_order(
    db: AsyncIOMotorDatabase,
    wo_id: str,
    approver_id: str,
    approved_amount: float,
) -> Dict[str, Any]:
    """
    Record owner approval of a work order and advance status to APPROVED.

    ``approved_amount`` is the dollar ceiling approved for this work.
    """
    logger = log.bind(action="approve_work_order", wo_id=wo_id, approver_id=approver_id)

    wo = await db.work_orders.find_one({"_id": wo_id})
    if not wo:
        raise ValueError(f"Work order {wo_id} not found")

    current = WorkOrderStatus(wo["status"])
    if WorkOrderStatus.APPROVED not in _ALLOWED_TRANSITIONS.get(current, []):
        raise ValueError(f"Cannot approve work order in status '{current.value}'.")

    now = datetime.utcnow()
    approved_amount = _round2(float(approved_amount))
    history_entry = {
        "status": WorkOrderStatus.APPROVED.value,
        "changed_at": now,
        "changed_by": approver_id,
        "note": f"Approved up to ${approved_amount:.2f}",
    }

    await db.work_orders.update_one(
        {"_id": wo_id},
        {
            "$set": {
                "status": WorkOrderStatus.APPROVED.value,
                "approved_by": approver_id,
                "approved_at": now,
                "approved_amount": approved_amount,
                "updated_at": now,
            },
            "$push": {"status_history": history_entry},
        },
    )

    # Notify assigned vendor if they have a portal account
    vendor_id = wo.get("assigned_vendor_id")
    if vendor_id:
        vendor = await db.vendors.find_one({"_id": vendor_id})
        if vendor and vendor.get("portal_user_id"):
            await _send_notification(
                db,
                user_id=vendor["portal_user_id"],
                notif_type="maintenance_updated",
                title=f"Work Order Approved - {wo['work_order_number']}",
                message=(
                    f"Work order {wo['work_order_number']} ({wo['title']}) has been "
                    f"approved for up to ${approved_amount:.2f}. You may now schedule the work."
                ),
                data={
                    "work_order_id": wo_id,
                    "approved_amount": approved_amount,
                },
                action_url=f"/vendor/work-orders/{wo_id}",
                priority="high",
            )

    logger.info(
        "Work order approved",
        wo_number=wo["work_order_number"],
        approver_id=approver_id,
        approved_amount=approved_amount,
    )

    wo["status"] = WorkOrderStatus.APPROVED.value
    wo["approved_by"] = approver_id
    wo["approved_at"] = now
    wo["approved_amount"] = approved_amount
    return wo


# ---------------------------------------------------------------------------
# Complete work order
# ---------------------------------------------------------------------------


async def complete_work_order(
    db: AsyncIOMotorDatabase,
    wo_id: str,
    actual_cost: float,
) -> Dict[str, Any]:
    """
    Mark a work order as COMPLETED and create an expense journal entry.

    ``actual_cost`` is the final invoiced cost from the vendor.

    Journal entry:
      DR Maintenance Expense (5000)  CR Accounts Payable (2000)
    """
    logger = log.bind(action="complete_work_order", wo_id=wo_id)

    wo = await db.work_orders.find_one({"_id": wo_id})
    if not wo:
        raise ValueError(f"Work order {wo_id} not found")

    current = WorkOrderStatus(wo["status"])
    if WorkOrderStatus.COMPLETED not in _ALLOWED_TRANSITIONS.get(current, []):
        raise ValueError(f"Cannot complete work order in status '{current.value}'.")

    actual_cost = _round2(float(actual_cost))
    now = datetime.utcnow()
    completed_date = date.today()

    history_entry = {
        "status": WorkOrderStatus.COMPLETED.value,
        "changed_at": now,
        "changed_by": "system",
        "note": f"Completed. Actual cost: ${actual_cost:.2f}",
    }

    await db.work_orders.update_one(
        {"_id": wo_id},
        {
            "$set": {
                "status": WorkOrderStatus.COMPLETED.value,
                "completed_date": completed_date.isoformat(),
                "actual_cost": actual_cost,
                "updated_at": now,
            },
            "$push": {"status_history": history_entry},
        },
    )

    # Create expense journal entry
    maintenance_account = await db.accounts.find_one({"code": "5000"})
    ap_account = await db.accounts.find_one({"code": "2000"})

    if maintenance_account and ap_account and actual_cost > 0:
        # Use a more specific sub-account if the category maps to one
        category = wo.get("category", "")
        category_code_map: Dict[str, str] = {
            WorkOrderCategory.HVAC.value: "5010",
            WorkOrderCategory.PLUMBING.value: "5020",
            WorkOrderCategory.ELECTRICAL.value: "5030",
            WorkOrderCategory.APPLIANCE.value: "5040",
            WorkOrderCategory.LANDSCAPING.value: "5050",
        }
        expense_code = category_code_map.get(category, "5000")
        expense_account = (
            await db.accounts.find_one({"code": expense_code}) or maintenance_account
        )

        try:
            je = await create_journal_entry(
                db,
                {
                    "date": completed_date,
                    "description": (
                        f"Maintenance expense - {wo['work_order_number']} - {wo['title']}"
                    ),
                    "entry_type": "expense",
                    "lines": [
                        {
                            "account_id": str(expense_account["_id"]),
                            "account_code": expense_account["code"],
                            "account_name": expense_account["name"],
                            "debit": actual_cost,
                            "credit": 0.0,
                            "description": wo["title"],
                            "property_id": wo["property_id"],
                        },
                        {
                            "account_id": str(ap_account["_id"]),
                            "account_code": ap_account["code"],
                            "account_name": ap_account["name"],
                            "debit": 0.0,
                            "credit": actual_cost,
                            "description": wo["title"],
                            "property_id": wo["property_id"],
                        },
                    ],
                    "reference_id": wo_id,
                    "reference_type": "work_order",
                    "property_id": wo["property_id"],
                    "created_by": "system",
                },
            )
            await db.work_orders.update_one(
                {"_id": wo_id},
                {"$set": {"journal_entry_id": je["_id"]}},
            )
        except Exception as exc:
            logger.error("Failed to create expense journal entry", error=str(exc))

    # Notify property owners
    owner_ids = await _get_property_owner_ids(db, wo["property_id"])
    tasks = [
        _send_notification(
            db,
            user_id=oid,
            notif_type="maintenance_completed",
            title=f"Work Order Completed - {wo['work_order_number']}",
            message=(
                f"Work order {wo['work_order_number']} ({wo['title']}) has been completed. "
                f"Final cost: ${actual_cost:.2f}."
            ),
            data={
                "work_order_id": wo_id,
                "actual_cost": actual_cost,
            },
            action_url=f"/maintenance/{wo_id}",
            priority="normal",
        )
        for oid in owner_ids
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(
        "Work order completed",
        wo_number=wo["work_order_number"],
        actual_cost=actual_cost,
    )

    wo["status"] = WorkOrderStatus.COMPLETED.value
    wo["completed_date"] = completed_date.isoformat()
    wo["actual_cost"] = actual_cost
    return wo


# ---------------------------------------------------------------------------
# Run preventive maintenance
# ---------------------------------------------------------------------------


async def run_preventive_maintenance(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Scan all active PreventiveMaintenance schedules and create work orders for
    items whose next_due_date is on or before today.

    After creating the work order, rolls ``next_due_date`` forward based on
    the schedule's frequency.

    Returns: { "created": int, "errors": list }
    """
    logger = log.bind(action="run_preventive_maintenance")
    logger.info("Running preventive maintenance check")

    today = date.today()
    created = 0
    errors: List[Dict[str, Any]] = []

    async for pm in db.preventive_maintenance.find(
        {
            "is_active": True,
            "auto_create_work_order": True,
            "next_due_date": {"$lte": today.isoformat()},
        }
    ):
        pm_id = str(pm["_id"])
        try:
            wo_data: Dict[str, Any] = {
                "property_id": pm["property_id"],
                "title": pm["title"],
                "description": pm.get("description", ""),
                "category": pm.get("category", WorkOrderCategory.PREVENTIVE.value),
                "priority": WorkOrderPriority.MEDIUM.value,
                "reported_by": "system",
                "reported_by_type": "system",
                "is_recurring": True,
                "preventive_schedule_id": pm_id,
                "notes": (
                    f"Auto-generated from preventive maintenance schedule "
                    f"(ID: {pm_id}). Estimated cost: "
                    f"${pm.get('estimated_cost', 0):.2f}"
                ),
            }

            # Assign preferred vendor if specified
            if pm.get("preferred_vendor_id"):
                wo_data["assigned_vendor_id"] = pm["preferred_vendor_id"]

            await create_work_order(db, wo_data)

            # Roll forward next_due_date
            current_due = date.fromisoformat(str(pm["next_due_date"]))
            frequency = pm.get("frequency", "monthly")
            if frequency == "monthly":
                # Next month, same day
                month = current_due.month + 1
                year = current_due.year + (month - 1) // 12
                month = ((month - 1) % 12) + 1
                try:
                    next_due = date(
                        year, month, pm.get("day_of_month", current_due.day)
                    )
                except ValueError:
                    # Handle months with fewer days
                    import calendar

                    max_day = calendar.monthrange(year, month)[1]
                    next_due = date(
                        year,
                        month,
                        min(pm.get("day_of_month", current_due.day), max_day),
                    )
            elif frequency == "quarterly":
                month = current_due.month + 3
                year = current_due.year + (month - 1) // 12
                month = ((month - 1) % 12) + 1
                try:
                    next_due = date(
                        year, month, pm.get("day_of_month", current_due.day)
                    )
                except ValueError:
                    import calendar

                    max_day = calendar.monthrange(year, month)[1]
                    next_due = date(
                        year,
                        month,
                        min(pm.get("day_of_month", current_due.day), max_day),
                    )
            elif frequency == "semi-annual":
                month = current_due.month + 6
                year = current_due.year + (month - 1) // 12
                month = ((month - 1) % 12) + 1
                try:
                    next_due = date(
                        year, month, pm.get("day_of_month", current_due.day)
                    )
                except ValueError:
                    import calendar

                    max_day = calendar.monthrange(year, month)[1]
                    next_due = date(
                        year,
                        month,
                        min(pm.get("day_of_month", current_due.day), max_day),
                    )
            elif frequency == "annual":
                next_due = date(
                    current_due.year + 1, current_due.month, current_due.day
                )
            else:
                next_due = current_due + timedelta(days=30)

            await db.preventive_maintenance.update_one(
                {"_id": pm["_id"]},
                {
                    "$set": {
                        "last_completed_date": today.isoformat(),
                        "next_due_date": next_due.isoformat(),
                    }
                },
            )

            created += 1
            logger.info(
                "Preventive maintenance WO created",
                pm_id=pm_id,
                property_id=pm["property_id"],
                next_due=str(next_due),
            )

        except Exception as exc:
            logger.error(
                "Error creating preventive maintenance work order",
                pm_id=pm_id,
                error=str(exc),
            )
            errors.append({"pm_id": pm_id, "error": str(exc)})

    logger.info(
        "Preventive maintenance run complete", created=created, errors=len(errors)
    )
    return {"created": created, "errors": errors}


# ---------------------------------------------------------------------------
# Get maintenance summary
# ---------------------------------------------------------------------------


async def get_maintenance_summary(
    db: AsyncIOMotorDatabase,
    property_id: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return aggregate maintenance statistics.

    If ``owner_id`` is supplied, all properties owned by that owner are included.
    If ``property_id`` is supplied, the summary is scoped to that property.
    Both can be combined.

    Returns:
        {
            "filter": {...},
            "total_work_orders": int,
            "by_status": { status: count },
            "by_category": { category: count },
            "by_priority": { priority: count },
            "total_cost_actual": float,
            "total_cost_approved": float,
            "open_count": int,
            "avg_resolution_days": float | None,
        }
    """
    logger = log.bind(
        action="get_maintenance_summary",
        property_id=property_id,
        owner_id=owner_id,
    )
    logger.info("Generating maintenance summary")

    match: Dict[str, Any] = {}

    if property_id:
        match["property_id"] = property_id
    elif owner_id:
        # Resolve property IDs for this owner
        prop_ids: List[str] = []
        async for ownership in db.ownerships.find({"owner_id": owner_id}):
            prop_ids.append(ownership["property_id"])
        if prop_ids:
            match["property_id"] = {"$in": prop_ids}
        else:
            return {
                "filter": {"property_id": property_id, "owner_id": owner_id},
                "total_work_orders": 0,
                "by_status": {},
                "by_category": {},
                "by_priority": {},
                "total_cost_actual": 0.0,
                "total_cost_approved": 0.0,
                "open_count": 0,
                "avg_resolution_days": None,
            }

    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": None,
                "total": {"$sum": 1},
                "total_cost_actual": {"$sum": {"$ifNull": ["$actual_cost", 0]}},
                "total_cost_approved": {"$sum": {"$ifNull": ["$approved_amount", 0]}},
            }
        },
    ]

    by_status: Dict[str, int] = {}
    by_category: Dict[str, int] = {}
    by_priority: Dict[str, int] = {}
    total_work_orders = 0
    total_cost_actual = 0.0
    total_cost_approved = 0.0

    # Aggregates in parallel
    async def _group_by(field: str) -> Dict[str, int]:
        result: Dict[str, int] = {}
        pipe = [
            {"$match": match},
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        ]
        async for row in db.work_orders.aggregate(pipe):
            if row["_id"] is not None:
                result[row["_id"]] = row["count"]
        return result

    results = await asyncio.gather(
        db.work_orders.aggregate(pipeline).to_list(1),
        _group_by("status"),
        _group_by("category"),
        _group_by("priority"),
    )

    totals_list, by_status, by_category, by_priority = results

    if totals_list:
        row = totals_list[0]
        total_work_orders = row.get("total", 0)
        total_cost_actual = _round2(row.get("total_cost_actual", 0.0))
        total_cost_approved = _round2(row.get("total_cost_approved", 0.0))

    open_statuses = [
        WorkOrderStatus.SUBMITTED.value,
        WorkOrderStatus.TRIAGED.value,
        WorkOrderStatus.ESTIMATE_REQUESTED.value,
        WorkOrderStatus.ESTIMATE_RECEIVED.value,
        WorkOrderStatus.AWAITING_APPROVAL.value,
        WorkOrderStatus.APPROVED.value,
        WorkOrderStatus.SCHEDULED.value,
        WorkOrderStatus.IN_PROGRESS.value,
    ]
    open_count = sum(by_status.get(s, 0) for s in open_statuses)

    # Average resolution days (SUBMITTED → COMPLETED)
    avg_resolution_days: Optional[float] = None
    completed_wo = await db.work_orders.find(
        {
            **match,
            "status": WorkOrderStatus.COMPLETED.value,
            "completed_date": {"$exists": True},
        },
        {"created_at": 1, "completed_date": 1},
    ).to_list(200)

    if completed_wo:
        deltas: List[float] = []
        for wo in completed_wo:
            try:
                created = wo["created_at"]
                completed = date.fromisoformat(str(wo["completed_date"]))
                if isinstance(created, datetime):
                    created_date = created.date()
                else:
                    created_date = created
                deltas.append((completed - created_date).days)
            except Exception:
                continue
        if deltas:
            avg_resolution_days = _round2(sum(deltas) / len(deltas))

    return {
        "filter": {"property_id": property_id, "owner_id": owner_id},
        "total_work_orders": total_work_orders,
        "by_status": by_status,
        "by_category": by_category,
        "by_priority": by_priority,
        "total_cost_actual": total_cost_actual,
        "total_cost_approved": total_cost_approved,
        "open_count": open_count,
        "avg_resolution_days": avg_resolution_days,
    }
