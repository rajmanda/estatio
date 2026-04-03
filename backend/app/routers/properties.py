"""
Properties router — CRUD for properties, ownership management, units, and
property-level financial summaries.

Endpoints:
    GET    /                        → list properties (RBAC filtered)
    POST   /                        → create property (admin/manager only)
    GET    /{id}                    → get property with ownership details
    PUT    /{id}                    → update property
    DELETE /{id}                    → soft delete
    GET    /{id}/owners             → list owners with ownership %
    POST   /{id}/owners             → assign owner to property
    DELETE /{id}/owners/{owner_id}  → remove owner
    GET    /{id}/units              → list units for a property
    GET    /{id}/financials         → property-level financial summary
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.core.auth import (
    get_current_active_user,
    require_manager_or_admin,
)
from app.core.database import get_db
from app.models.property import (
    PropertyStatus,
    PropertyType,
)
from app.models.user import UserRole

log = structlog.get_logger()

router = APIRouter(prefix="/properties", tags=["properties"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class AddressSchema(BaseModel):
    street: str
    unit: Optional[str] = None
    city: str
    state: str
    zip_code: str
    country: str = "US"
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class UnitSchema(BaseModel):
    unit_id: str
    unit_number: str
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    square_feet: Optional[float] = None
    rent_amount: Optional[float] = None
    status: str = "vacant"
    current_tenant_id: Optional[str] = None


class HOAInfoSchema(BaseModel):
    hoa_name: Optional[str] = None
    hoa_contact: Optional[str] = None
    hoa_fee: Optional[float] = None
    hoa_fee_frequency: Optional[str] = "monthly"
    next_due_date: Optional[date] = None
    violations: List[Dict[str, Any]] = []


class PropertyCreateRequest(BaseModel):
    name: str
    property_type: PropertyType
    status: PropertyStatus = PropertyStatus.ACTIVE
    address: AddressSchema
    units: List[UnitSchema] = []
    year_built: Optional[int] = None
    square_feet: Optional[float] = None
    lot_size: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    purchase_price: Optional[float] = None
    purchase_date: Optional[date] = None
    current_value: Optional[float] = None
    monthly_rent: Optional[float] = None
    hoa_info: Optional[HOAInfoSchema] = None
    management_fee_rate: float = 0.10
    management_fee_type: str = "percentage"
    management_fee_flat: Optional[float] = None
    amenities: List[str] = []
    notes: Optional[str] = None


class PropertyUpdateRequest(BaseModel):
    name: Optional[str] = None
    property_type: Optional[PropertyType] = None
    status: Optional[PropertyStatus] = None
    address: Optional[AddressSchema] = None
    units: Optional[List[UnitSchema]] = None
    year_built: Optional[int] = None
    square_feet: Optional[float] = None
    lot_size: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    purchase_price: Optional[float] = None
    purchase_date: Optional[date] = None
    current_value: Optional[float] = None
    monthly_rent: Optional[float] = None
    hoa_info: Optional[HOAInfoSchema] = None
    management_fee_rate: Optional[float] = None
    management_fee_type: Optional[str] = None
    management_fee_flat: Optional[float] = None
    amenities: Optional[List[str]] = None
    notes: Optional[str] = None


class AssignOwnerRequest(BaseModel):
    owner_id: str
    ownership_percentage: float = Field(gt=0, le=100)
    billing_preference: str = "email"  # email | portal | mail
    statement_preference: str = "monthly"  # monthly | quarterly | annual
    effective_date: date
    end_date: Optional[date] = None
    is_primary_owner: bool = False
    notes: Optional[str] = None


class PropertyResponse(BaseModel):
    id: str
    name: str
    property_type: str
    status: str
    address: Dict[str, Any]
    units: List[Dict[str, Any]]
    year_built: Optional[int]
    square_feet: Optional[float]
    bedrooms: Optional[int]
    bathrooms: Optional[float]
    purchase_price: Optional[float]
    current_value: Optional[float]
    monthly_rent: Optional[float]
    management_fee_rate: float
    amenities: List[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _obj_id(raw_id: str) -> ObjectId:
    try:
        return ObjectId(raw_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid id: {raw_id}"
        )


def _serialize(doc: dict) -> dict:
    """Recursively stringify ObjectIds in a Mongo document."""
    if doc is None:
        return {}
    result = {}
    for k, v in doc.items():
        if k == "_id":
            result["id"] = str(v)
        elif isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, dict):
            result[k] = _serialize(v)
        elif isinstance(v, list):
            result[k] = [_serialize(i) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = v
    return result


async def _get_property_or_404(property_id: str, db: AsyncIOMotorDatabase) -> dict:
    doc = await db.properties.find_one(
        {"_id": _obj_id(property_id), "deleted": {"$ne": True}}
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Property not found"
        )
    return doc


async def _assert_property_access(
    property_id: str,
    current_user: dict,
    db: AsyncIOMotorDatabase,
) -> dict:
    """Fetch property and enforce owner-level row-level access."""
    prop = await _get_property_or_404(property_id, db)
    role = current_user.get("role")
    if role in (UserRole.ADMIN.value, UserRole.MANAGER.value):
        return prop
    # Owner: verify they have an ownership record
    ownership = await db.ownerships.find_one(
        {
            "owner_id": str(current_user["_id"]),
            "property_id": property_id,
        }
    )
    if not ownership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )
    return prop


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/", summary="List properties")
async def list_properties(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    property_type: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Return a paginated list of properties.
    - admin / manager: see all properties.
    - owner: see only properties they have an ownership record for.
    """
    role = current_user.get("role")
    query: Dict[str, Any] = {"deleted": {"$ne": True}}

    if status_filter:
        query["status"] = status_filter
    if property_type:
        query["property_type"] = property_type
    if city:
        query["address.city"] = {"$regex": city, "$options": "i"}
    if search:
        query["$text"] = {"$search": search}

    if role == UserRole.OWNER.value:
        # Collect property IDs from ownerships
        ownership_cursor = db.ownerships.find(
            {"owner_id": str(current_user["_id"])},
            {"property_id": 1},
        )
        property_ids = [ObjectId(o["property_id"]) async for o in ownership_cursor]
        query["_id"] = {"$in": property_ids}

    total = await db.properties.count_documents(query)
    cursor = db.properties.find(query).sort("created_at", -1).skip(skip).limit(limit)
    properties = [_serialize(p) async for p in cursor]

    return {"total": total, "skip": skip, "limit": limit, "data": properties}


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create property")
async def create_property(
    body: PropertyCreateRequest,
    current_user: dict = Depends(require_manager_or_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Create a new property record. Requires admin or manager role."""
    now = datetime.now(timezone.utc)
    doc = body.model_dump()
    doc["created_by"] = str(current_user["_id"])
    doc["created_at"] = now
    doc["updated_at"] = now
    doc["deleted"] = False
    doc["images"] = []

    # Normalise nested date objects for Mongo
    if doc.get("purchase_date"):
        doc["purchase_date"] = datetime(
            doc["purchase_date"].year,
            doc["purchase_date"].month,
            doc["purchase_date"].day,
        )
    if doc.get("hoa_info") and doc["hoa_info"].get("next_due_date"):
        nd = doc["hoa_info"]["next_due_date"]
        doc["hoa_info"]["next_due_date"] = datetime(nd.year, nd.month, nd.day)

    result = await db.properties.insert_one(doc)
    created = await db.properties.find_one({"_id": result.inserted_id})
    log.info("Property created", property_id=str(result.inserted_id))
    return _serialize(created)


@router.get("/{property_id}", summary="Get property")
async def get_property(
    property_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return a single property with its ownership details."""
    prop = await _assert_property_access(property_id, current_user, db)

    # Attach ownership details
    ownership_cursor = db.ownerships.find({"property_id": property_id})
    ownerships = [_serialize(o) async for o in ownership_cursor]

    # For each ownership, attach owner name
    enriched_ownerships = []
    for o in ownerships:
        owner = await db.users.find_one(
            {"_id": _obj_id(o["owner_id"])},
            {"full_name": 1, "email": 1, "avatar_url": 1},
        )
        o["owner"] = (
            {
                "id": str(owner["_id"]),
                "full_name": owner.get("full_name"),
                "email": owner.get("email"),
            }
            if owner
            else None
        )
        enriched_ownerships.append(o)

    result = _serialize(prop)
    result["ownerships"] = enriched_ownerships
    return result


@router.put("/{property_id}", summary="Update property")
async def update_property(
    property_id: str,
    body: PropertyUpdateRequest,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Update a property. Admin/manager can update any; owners can only update their own."""
    await _assert_property_access(property_id, current_user, db)

    role = current_user.get("role")
    if role == UserRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owners cannot modify property details. Contact your manager.",
        )

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided"
        )

    update_data["updated_at"] = datetime.now(timezone.utc)

    # Normalise nested dates
    if update_data.get("purchase_date"):
        pd = update_data["purchase_date"]
        update_data["purchase_date"] = datetime(pd.year, pd.month, pd.day)

    await db.properties.update_one(
        {"_id": _obj_id(property_id)},
        {"$set": update_data},
    )
    updated = await db.properties.find_one({"_id": _obj_id(property_id)})
    return _serialize(updated)


@router.delete(
    "/{property_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete property",
)
async def delete_property(
    property_id: str,
    current_user: dict = Depends(require_manager_or_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Soft-delete a property (sets deleted=True). Requires admin or manager."""
    await _get_property_or_404(property_id, db)
    await db.properties.update_one(
        {"_id": _obj_id(property_id)},
        {"$set": {"deleted": True, "updated_at": datetime.now(timezone.utc)}},
    )
    log.info("Property soft-deleted", property_id=property_id)


# ---------------------------------------------------------------------------
# Ownership sub-routes
# ---------------------------------------------------------------------------


@router.get("/{property_id}/owners", summary="List owners for a property")
async def list_owners(
    property_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return all owners associated with a property, with ownership percentage."""
    await _assert_property_access(property_id, current_user, db)

    ownership_cursor = db.ownerships.find({"property_id": property_id})
    result = []
    async for o in ownership_cursor:
        o_serialized = _serialize(o)
        owner = await db.users.find_one(
            {"_id": _obj_id(o["owner_id"])},
            {"full_name": 1, "email": 1, "avatar_url": 1, "phone": 1, "role": 1},
        )
        if owner:
            o_serialized["owner_details"] = {
                "id": str(owner["_id"]),
                "full_name": owner.get("full_name"),
                "email": owner.get("email"),
                "avatar_url": owner.get("avatar_url"),
                "phone": owner.get("phone"),
            }
        result.append(o_serialized)

    return {"data": result, "total": len(result)}


@router.post(
    "/{property_id}/owners",
    status_code=status.HTTP_201_CREATED,
    summary="Assign owner to property",
)
async def assign_owner(
    property_id: str,
    body: AssignOwnerRequest,
    current_user: dict = Depends(require_manager_or_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Assign an owner to a property with an ownership percentage and preferences.
    Validates that total ownership does not exceed 100%.
    """
    await _get_property_or_404(property_id, db)

    # Validate the owner exists
    owner = await db.users.find_one({"_id": _obj_id(body.owner_id)})
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found"
        )

    # Check for duplicate
    existing = await db.ownerships.find_one(
        {"owner_id": body.owner_id, "property_id": property_id}
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This owner already has an ownership record for this property.",
        )

    # Validate total ownership percentage
    agg = await db.ownerships.aggregate(
        [
            {"$match": {"property_id": property_id}},
            {"$group": {"_id": None, "total": {"$sum": "$ownership_percentage"}}},
        ]
    ).to_list(1)
    current_total = agg[0]["total"] if agg else 0.0
    if current_total + body.ownership_percentage > 100.0 + 0.001:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Adding {body.ownership_percentage}% would exceed 100% "
                f"(current total: {current_total}%)"
            ),
        )

    now = datetime.now(timezone.utc)
    ownership_doc = body.model_dump()
    ownership_doc["property_id"] = property_id
    ownership_doc["created_at"] = now

    # Normalise dates
    ownership_doc["effective_date"] = datetime(
        body.effective_date.year, body.effective_date.month, body.effective_date.day
    )
    if body.end_date:
        ownership_doc["end_date"] = datetime(
            body.end_date.year, body.end_date.month, body.end_date.day
        )

    result = await db.ownerships.insert_one(ownership_doc)
    created = await db.ownerships.find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.delete(
    "/{property_id}/owners/{owner_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove owner from property",
)
async def remove_owner(
    property_id: str,
    owner_id: str,
    current_user: dict = Depends(require_manager_or_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Remove an owner's association with a property."""
    result = await db.ownerships.delete_one(
        {"owner_id": owner_id, "property_id": property_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ownership record not found",
        )


# ---------------------------------------------------------------------------
# Units sub-route
# ---------------------------------------------------------------------------


@router.get("/{property_id}/units", summary="List units for a property")
async def list_units(
    property_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return all units embedded in the property document."""
    prop = await _assert_property_access(property_id, current_user, db)
    units = prop.get("units", [])

    # Enrich with tenant info if available
    enriched = []
    for unit in units:
        u = dict(unit)
        if u.get("current_tenant_id"):
            tenant = await db.tenants.find_one(
                {"_id": _obj_id(u["current_tenant_id"])},
                {"full_name": 1, "email": 1},
            )
            u["tenant_details"] = (
                {
                    "id": str(tenant["_id"]),
                    "full_name": tenant.get("full_name"),
                    "email": tenant.get("email"),
                }
                if tenant
                else None
            )
        enriched.append(u)

    return {"property_id": property_id, "data": enriched, "total": len(enriched)}


# ---------------------------------------------------------------------------
# Financials sub-route
# ---------------------------------------------------------------------------


@router.get("/{property_id}/financials", summary="Property-level financial summary")
async def property_financials(
    property_id: str,
    year: int = Query(None, description="Filter by year (defaults to current year)"),
    month: int = Query(None, ge=1, le=12, description="Filter by month"),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Aggregate income, expenses, and NOI for a property from journal entries.
    Returns month-level breakdown when a year is specified.
    """
    await _assert_property_access(property_id, current_user, db)

    now = datetime.now(timezone.utc)
    filter_year = year or now.year

    match_stage: Dict[str, Any] = {
        "property_id": property_id,
        "is_voided": False,
    }

    if month:
        start_dt = datetime(filter_year, month, 1)
        if month == 12:
            end_dt = datetime(filter_year + 1, 1, 1)
        else:
            end_dt = datetime(filter_year, month + 1, 1)
        match_stage["date"] = {"$gte": start_dt, "$lt": end_dt}
    else:
        match_stage["date"] = {
            "$gte": datetime(filter_year, 1, 1),
            "$lt": datetime(filter_year + 1, 1, 1),
        }

    # Aggregate journal line amounts by account type
    pipeline = [
        {"$match": match_stage},
        {"$unwind": "$lines"},
        {
            "$lookup": {
                "from": "accounts",
                "let": {"aid": {"$toObjectId": "$lines.account_id"}},
                "pipeline": [{"$match": {"$expr": {"$eq": ["$_id", "$$aid"]}}}],
                "as": "account_doc",
            }
        },
        {"$unwind": {"path": "$account_doc", "preserveNullAndEmptyArrays": True}},
        {
            "$group": {
                "_id": "$account_doc.account_type",
                "total_debit": {"$sum": "$lines.debit"},
                "total_credit": {"$sum": "$lines.credit"},
            }
        },
    ]

    agg_result = await db.journal_entries.aggregate(pipeline).to_list(None)

    totals: Dict[str, Dict[str, float]] = {}
    for row in agg_result:
        acct_type = row["_id"] or "unknown"
        totals[acct_type] = {
            "total_debit": round(row["total_debit"], 2),
            "total_credit": round(row["total_credit"], 2),
        }

    # Revenue accounts: normal balance is credit
    revenue_credit = totals.get("revenue", {}).get("total_credit", 0.0)
    revenue_debit = totals.get("revenue", {}).get("total_debit", 0.0)
    total_income = round(revenue_credit - revenue_debit, 2)

    # Expense accounts: normal balance is debit
    expense_debit = totals.get("expense", {}).get("total_debit", 0.0)
    expense_credit = totals.get("expense", {}).get("total_credit", 0.0)
    total_expenses = round(expense_debit - expense_credit, 2)

    noi = round(total_income - total_expenses, 2)

    # Pending invoices
    pending_invoices = await db.invoices.count_documents(
        {"property_id": property_id, "status": {"$in": ["pending", "overdue"]}}
    )
    open_work_orders = await db.work_orders.count_documents(
        {"property_id": property_id, "status": {"$in": ["open", "in_progress"]}}
    )

    return {
        "property_id": property_id,
        "year": filter_year,
        "month": month,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_operating_income": noi,
        "noi_margin": round((noi / total_income * 100) if total_income else 0.0, 2),
        "pending_invoices": pending_invoices,
        "open_work_orders": open_work_orders,
        "account_type_breakdown": totals,
    }
