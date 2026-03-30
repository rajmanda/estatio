"""
Owners router — owner profile management, portfolio aggregation, and
per-owner reporting endpoints.

Endpoints:
    GET  /                      → list all owners (admin/manager)
    GET  /{id}                  → owner profile
    GET  /{id}/portfolio        → all properties for this owner with summaries
    GET  /{id}/statements       → owner statement list
    GET  /{id}/invoices         → owner invoices
    GET  /{id}/payments         → payment history
    GET  /{id}/maintenance      → maintenance summary across all properties
    GET  /{id}/dashboard        → portfolio-level dashboard (KPIs, alerts)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.auth import (
    get_current_active_user,
    require_manager_or_admin,
)
from app.core.database import get_db
from app.models.user import UserRole

log = structlog.get_logger()

router = APIRouter(prefix="/owners", tags=["owners"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _obj_id(raw_id: str) -> ObjectId:
    try:
        return ObjectId(raw_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid id: {raw_id}",
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


async def _resolve_owner(
    owner_id: str,
    current_user: dict,
    db: AsyncIOMotorDatabase,
) -> dict:
    """
    Return the owner document, enforcing that:
    - Admins and managers can access any owner.
    - An owner can only access their own profile.
    """
    role = current_user.get("role")
    caller_id = str(current_user["_id"])

    if role not in (UserRole.ADMIN.value, UserRole.MANAGER.value):
        if caller_id != owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    owner = await db.users.find_one({"_id": _obj_id(owner_id), "is_active": True})
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    return owner


async def _owner_property_ids(owner_id: str, db: AsyncIOMotorDatabase) -> List[ObjectId]:
    """Return a list of ObjectIds for properties owned by this owner."""
    cursor = db.ownerships.find({"owner_id": owner_id}, {"property_id": 1})
    return [_obj_id(o["property_id"]) async for o in cursor]


async def _financial_summary_for_property(
    property_id_str: str,
    db: AsyncIOMotorDatabase,
    year: Optional[int] = None,
) -> Dict[str, float]:
    """
    Compute income / expenses / NOI for a single property from journal entries.
    """
    now = datetime.now(timezone.utc)
    filter_year = year or now.year

    match: Dict[str, Any] = {
        "property_id": property_id_str,
        "is_voided": False,
        "date": {
            "$gte": datetime(filter_year, 1, 1),
            "$lt": datetime(filter_year + 1, 1, 1),
        },
    }

    pipeline = [
        {"$match": match},
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
            "total_debit": row["total_debit"],
            "total_credit": row["total_credit"],
        }

    revenue = totals.get("revenue", {})
    income = round(revenue.get("total_credit", 0) - revenue.get("total_debit", 0), 2)
    expense_row = totals.get("expense", {})
    expenses = round(expense_row.get("total_debit", 0) - expense_row.get("total_credit", 0), 2)
    noi = round(income - expenses, 2)

    return {"income": income, "expenses": expenses, "noi": noi}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/", summary="List all owners")
async def list_owners(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    current_user: dict = Depends(require_manager_or_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return paginated list of all owner-role users. Admin/manager only."""
    query: Dict[str, Any] = {"role": UserRole.OWNER.value, "is_active": True}
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]

    total = await db.users.count_documents(query)
    cursor = db.users.find(query, {"google_id": 0}).skip(skip).limit(limit)
    owners = [_serialize(u) async for u in cursor]

    return {"total": total, "skip": skip, "limit": limit, "data": owners}


@router.get("/{owner_id}", summary="Get owner profile")
async def get_owner(
    owner_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return the owner's profile. Owners can only view their own profile."""
    owner = await _resolve_owner(owner_id, current_user, db)
    result = _serialize(owner)
    result.pop("google_id", None)

    # Attach ownership count
    ownership_count = await db.ownerships.count_documents({"owner_id": owner_id})
    result["property_count"] = ownership_count
    return result


@router.get("/{owner_id}/portfolio", summary="Owner's full property portfolio")
async def owner_portfolio(
    owner_id: str,
    year: Optional[int] = Query(None, description="Financial year (defaults to current year)"),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Return every property the owner has a stake in, with financial summaries
    (income, expenses, NOI) and ownership percentage.
    """
    await _resolve_owner(owner_id, current_user, db)

    ownership_cursor = db.ownerships.find({"owner_id": owner_id})
    portfolio = []

    async for ownership in ownership_cursor:
        prop_id_str = ownership["property_id"]
        try:
            prop = await db.properties.find_one({"_id": _obj_id(prop_id_str)})
        except Exception:
            continue
        if not prop:
            continue

        financials = await _financial_summary_for_property(prop_id_str, db, year)
        ownership_pct = ownership.get("ownership_percentage", 100.0)

        # Scale financials by ownership percentage
        owner_share = {
            "income": round(financials["income"] * ownership_pct / 100, 2),
            "expenses": round(financials["expenses"] * ownership_pct / 100, 2),
            "noi": round(financials["noi"] * ownership_pct / 100, 2),
        }

        entry = _serialize(prop)
        entry["ownership_percentage"] = ownership_pct
        entry["billing_preference"] = ownership.get("billing_preference")
        entry["statement_preference"] = ownership.get("statement_preference")
        entry["effective_date"] = ownership.get("effective_date")
        entry["financials"] = financials
        entry["owner_share_financials"] = owner_share

        # Unit summary
        units = prop.get("units", [])
        occupied = sum(1 for u in units if u.get("status") == "occupied")
        entry["unit_summary"] = {
            "total": len(units),
            "occupied": occupied,
            "vacant": len(units) - occupied,
            "occupancy_rate": round(occupied / len(units) * 100, 1) if units else 0.0,
        }

        portfolio.append(entry)

    # Aggregate totals
    total_income = round(sum(p["owner_share_financials"]["income"] for p in portfolio), 2)
    total_expenses = round(sum(p["owner_share_financials"]["expenses"] for p in portfolio), 2)
    total_noi = round(sum(p["owner_share_financials"]["noi"] for p in portfolio), 2)

    return {
        "owner_id": owner_id,
        "year": year or datetime.now(timezone.utc).year,
        "property_count": len(portfolio),
        "aggregate_financials": {
            "income": total_income,
            "expenses": total_expenses,
            "noi": total_noi,
        },
        "properties": portfolio,
    }


@router.get("/{owner_id}/statements", summary="Owner statements list")
async def owner_statements(
    owner_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    year: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return paginated list of owner statements."""
    await _resolve_owner(owner_id, current_user, db)

    query: Dict[str, Any] = {"owner_id": owner_id}
    if year:
        query["year"] = year

    total = await db.owner_statements.count_documents(query)
    cursor = db.owner_statements.find(query).sort("period_end", -1).skip(skip).limit(limit)
    statements = [_serialize(s) async for s in cursor]

    return {"owner_id": owner_id, "total": total, "skip": skip, "limit": limit, "data": statements}


@router.get("/{owner_id}/invoices", summary="Owner invoices")
async def owner_invoices(
    owner_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    invoice_status: Optional[str] = Query(None, alias="status"),
    property_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return paginated list of invoices for an owner."""
    await _resolve_owner(owner_id, current_user, db)

    query: Dict[str, Any] = {"owner_id": owner_id}
    if invoice_status:
        query["status"] = invoice_status
    if property_id:
        query["property_id"] = property_id

    total = await db.invoices.count_documents(query)
    cursor = db.invoices.find(query).sort("due_date", -1).skip(skip).limit(limit)
    invoices = [_serialize(i) async for i in cursor]

    return {"owner_id": owner_id, "total": total, "skip": skip, "limit": limit, "data": invoices}


@router.get("/{owner_id}/payments", summary="Owner payment history")
async def owner_payments(
    owner_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    property_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return paginated payment history for an owner."""
    await _resolve_owner(owner_id, current_user, db)

    query: Dict[str, Any] = {"owner_id": owner_id}
    if property_id:
        query["property_id"] = property_id

    date_filter: Dict[str, Any] = {}
    if date_from:
        try:
            date_filter["$gte"] = datetime.fromisoformat(date_from)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_from format. Use YYYY-MM-DD.")
    if date_to:
        try:
            date_filter["$lte"] = datetime.fromisoformat(date_to)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_to format. Use YYYY-MM-DD.")
    if date_filter:
        query["payment_date"] = date_filter

    total = await db.payments.count_documents(query)
    cursor = db.payments.find(query).sort("payment_date", -1).skip(skip).limit(limit)
    payments = [_serialize(p) async for p in cursor]

    # Aggregate total paid
    agg = await db.payments.aggregate([
        {"$match": query},
        {"$group": {"_id": None, "total_paid": {"$sum": "$amount"}}},
    ]).to_list(1)
    total_paid = round(agg[0]["total_paid"], 2) if agg else 0.0

    return {
        "owner_id": owner_id,
        "total": total,
        "total_paid": total_paid,
        "skip": skip,
        "limit": limit,
        "data": payments,
    }


@router.get("/{owner_id}/maintenance", summary="Maintenance summary across all owner properties")
async def owner_maintenance(
    owner_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    work_order_status: Optional[str] = Query(None, alias="status"),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return work orders across all properties owned by this owner."""
    await _resolve_owner(owner_id, current_user, db)

    property_ids_obj = await _owner_property_ids(owner_id, db)
    if not property_ids_obj:
        return {
            "owner_id": owner_id,
            "summary": {"total": 0, "open": 0, "in_progress": 0, "completed": 0},
            "data": [],
        }

    property_ids_str = [str(pid) for pid in property_ids_obj]
    query: Dict[str, Any] = {"property_id": {"$in": property_ids_str}}
    if work_order_status:
        query["status"] = work_order_status

    total = await db.work_orders.count_documents(query)
    cursor = db.work_orders.find(query).sort("created_at", -1).skip(skip).limit(limit)
    work_orders = [_serialize(wo) async for wo in cursor]

    # Status counts
    status_pipeline = [
        {"$match": {"property_id": {"$in": property_ids_str}}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    status_counts_raw = await db.work_orders.aggregate(status_pipeline).to_list(None)
    status_counts = {row["_id"]: row["count"] for row in status_counts_raw}

    return {
        "owner_id": owner_id,
        "total": total,
        "summary": {
            "total": sum(status_counts.values()),
            "open": status_counts.get("open", 0),
            "in_progress": status_counts.get("in_progress", 0),
            "completed": status_counts.get("completed", 0),
            "cancelled": status_counts.get("cancelled", 0),
        },
        "skip": skip,
        "limit": limit,
        "data": work_orders,
    }


@router.get("/{owner_id}/dashboard", summary="Owner portfolio dashboard")
async def owner_dashboard(
    owner_id: str,
    year: Optional[int] = Query(None, description="Financial year for aggregations"),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Return a comprehensive portfolio-level dashboard for the owner including:
    - KPIs: total income, expenses, NOI, occupancy rate
    - Pending invoices count and total amount due
    - Open work orders
    - Recent activity (invoices, payments, work orders)
    - Per-property quick stats
    """
    owner = await _resolve_owner(owner_id, current_user, db)
    filter_year = year or datetime.now(timezone.utc).year

    # ------------------------------------------------------------------
    # Portfolio financials (from journal entries, owner-share adjusted)
    # ------------------------------------------------------------------
    ownership_docs = await db.ownerships.find({"owner_id": owner_id}).to_list(None)
    property_ids_str = [o["property_id"] for o in ownership_docs]

    portfolio_income = 0.0
    portfolio_expenses = 0.0
    total_units = 0
    occupied_units = 0
    property_quick_stats = []

    for ownership in ownership_docs:
        prop_id_str = ownership["property_id"]
        try:
            prop = await db.properties.find_one({"_id": _obj_id(prop_id_str)})
        except Exception:
            continue
        if not prop:
            continue

        financials = await _financial_summary_for_property(prop_id_str, db, filter_year)
        pct = ownership.get("ownership_percentage", 100.0)

        owner_income = round(financials["income"] * pct / 100, 2)
        owner_expenses = round(financials["expenses"] * pct / 100, 2)
        portfolio_income += owner_income
        portfolio_expenses += owner_expenses

        units = prop.get("units", [])
        occ = sum(1 for u in units if u.get("status") == "occupied")
        total_units += len(units)
        occupied_units += occ

        property_quick_stats.append({
            "property_id": prop_id_str,
            "name": prop.get("name"),
            "status": prop.get("status"),
            "ownership_percentage": pct,
            "income": owner_income,
            "expenses": owner_expenses,
            "noi": round(owner_income - owner_expenses, 2),
            "unit_count": len(units),
            "occupancy_rate": round(occ / len(units) * 100, 1) if units else 0.0,
        })

    portfolio_noi = round(portfolio_income - portfolio_expenses, 2)
    overall_occupancy = round(occupied_units / total_units * 100, 1) if total_units else 0.0

    # ------------------------------------------------------------------
    # Invoices
    # ------------------------------------------------------------------
    pending_invoices_pipeline = [
        {"$match": {"owner_id": owner_id, "status": {"$in": ["pending", "overdue"]}}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}, "total": {"$sum": "$amount_due"}}},
    ]
    inv_agg = await db.invoices.aggregate(pending_invoices_pipeline).to_list(None)
    pending_count = sum(r["count"] for r in inv_agg)
    pending_amount = round(sum(r["total"] for r in inv_agg), 2)

    # ------------------------------------------------------------------
    # Work orders
    # ------------------------------------------------------------------
    open_work_orders = await db.work_orders.count_documents(
        {
            "property_id": {"$in": property_ids_str},
            "status": {"$in": ["open", "in_progress"]},
        }
    )
    urgent_work_orders = await db.work_orders.count_documents(
        {
            "property_id": {"$in": property_ids_str},
            "status": {"$in": ["open", "in_progress"]},
            "priority": {"$in": ["urgent", "emergency"]},
        }
    )

    # ------------------------------------------------------------------
    # Recent activity (last 5 items per category)
    # ------------------------------------------------------------------
    recent_invoices_cursor = (
        db.invoices.find({"owner_id": owner_id})
        .sort("created_at", -1)
        .limit(5)
    )
    recent_invoices = [_serialize(i) async for i in recent_invoices_cursor]

    recent_payments_cursor = (
        db.payments.find({"owner_id": owner_id})
        .sort("payment_date", -1)
        .limit(5)
    )
    recent_payments = [_serialize(p) async for p in recent_payments_cursor]

    recent_work_orders_cursor = (
        db.work_orders.find({"property_id": {"$in": property_ids_str}})
        .sort("created_at", -1)
        .limit(5)
    )
    recent_work_orders = [_serialize(wo) async for wo in recent_work_orders_cursor]

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------
    alerts = []
    if urgent_work_orders:
        alerts.append({
            "type": "urgent_maintenance",
            "severity": "high",
            "message": f"{urgent_work_orders} urgent/emergency work order(s) require attention.",
        })
    if pending_count:
        alerts.append({
            "type": "pending_invoices",
            "severity": "medium",
            "message": f"{pending_count} invoice(s) pending payment totalling ${pending_amount:,.2f}.",
        })

    return {
        "owner_id": owner_id,
        "owner_name": owner.get("full_name"),
        "year": filter_year,
        "kpis": {
            "total_income": round(portfolio_income, 2),
            "total_expenses": round(portfolio_expenses, 2),
            "net_operating_income": portfolio_noi,
            "noi_margin": round((portfolio_noi / portfolio_income * 100) if portfolio_income else 0.0, 2),
            "overall_occupancy_rate": overall_occupancy,
            "total_units": total_units,
            "occupied_units": occupied_units,
            "property_count": len(ownership_docs),
        },
        "invoices": {
            "pending_count": pending_count,
            "pending_amount": pending_amount,
        },
        "work_orders": {
            "open": open_work_orders,
            "urgent": urgent_work_orders,
        },
        "alerts": alerts,
        "property_quick_stats": property_quick_stats,
        "recent_activity": {
            "invoices": recent_invoices,
            "payments": recent_payments,
            "work_orders": recent_work_orders,
        },
    }
