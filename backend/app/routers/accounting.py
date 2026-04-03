"""
Accounting router — double-entry bookkeeping, chart of accounts, journal
entries, and financial report generation.

Endpoints:
    GET    /accounts                            → chart of accounts
    POST   /accounts                            → create account
    GET    /accounts/{id}                       → single account
    POST   /journal-entries                     → create journal entry
    GET    /journal-entries                     → list with filters
    GET    /journal-entries/{id}                → single entry
    POST   /journal-entries/{id}/void           → void entry
    GET    /reports/trial-balance               → trial balance
    GET    /reports/income-statement            → P&L for date range
    GET    /reports/balance-sheet               → balance sheet
    GET    /reports/cash-flow                   → cash flow summary
    GET    /reports/owner-statement/{owner_id}  → owner statement
"""

from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional

import structlog
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field, model_validator

from app.core.auth import (
    get_current_active_user,
    require_manager_or_admin,
)
from app.core.database import get_db
from app.models.accounting import AccountType, AccountSubtype
from app.models.user import UserRole

log = structlog.get_logger()

router = APIRouter(prefix="/accounting", tags=["accounting"])

# ---------------------------------------------------------------------------
# Inline Pydantic schemas
# ---------------------------------------------------------------------------

class AccountCreateRequest(BaseModel):
    code: str
    name: str
    account_type: AccountType
    subtype: AccountSubtype
    parent_id: Optional[str] = None
    property_id: Optional[str] = None
    description: Optional[str] = None
    normal_balance: str = "debit"  # "debit" or "credit"

    @model_validator(mode="after")
    def set_normal_balance_default(self):
        """Revenue and liability accounts normally carry a credit balance."""
        if self.account_type in (AccountType.REVENUE, AccountType.LIABILITY, AccountType.EQUITY):
            self.normal_balance = "credit"
        else:
            self.normal_balance = "debit"
        return self


class AccountResponse(BaseModel):
    id: str
    code: str
    name: str
    account_type: str
    subtype: str
    parent_id: Optional[str]
    property_id: Optional[str]
    description: Optional[str]
    is_active: bool
    is_system: bool
    normal_balance: str
    created_at: datetime


class JournalLineRequest(BaseModel):
    account_id: str
    debit: float = Field(default=0.0, ge=0)
    credit: float = Field(default=0.0, ge=0)
    description: Optional[str] = None
    property_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_line(self):
        if self.debit == 0.0 and self.credit == 0.0:
            raise ValueError("Each journal line must have a non-zero debit or credit.")
        if self.debit > 0 and self.credit > 0:
            raise ValueError("A journal line cannot have both debit and credit amounts.")
        return self


class JournalEntryCreateRequest(BaseModel):
    date: date
    description: str
    entry_type: str  # rent, invoice, payment, expense, adjustment, opening
    lines: List[JournalLineRequest] = Field(min_length=2)
    reference_id: Optional[str] = None
    reference_type: Optional[str] = None
    property_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_balanced(self):
        total_debit = round(sum(line.debit for line in self.lines), 2)
        total_credit = round(sum(line.credit for line in self.lines), 2)
        if abs(total_debit - total_credit) > 0.01:
            raise ValueError(
                f"Journal entry is not balanced: debits={total_debit}, credits={total_credit}"
            )
        return self


class VoidEntryRequest(BaseModel):
    void_reason: str


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


def _parse_date(date_str: str, field_name: str) -> datetime:
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format. Use ISO 8601 (YYYY-MM-DD).",
        )


async def _next_entry_number(db: AsyncIOMotorDatabase) -> str:
    """Generate a sequential journal entry number like JE-000042."""
    result = await db.journal_entries.count_documents({})
    return f"JE-{result + 1:06d}"


async def _get_account_or_404(account_id: str, db: AsyncIOMotorDatabase) -> dict:
    account = await db.accounts.find_one({"_id": _obj_id(account_id), "is_active": True})
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found",
        )
    return account


async def _enrich_journal_lines(
    lines: List[Dict[str, Any]], db: AsyncIOMotorDatabase
) -> List[Dict[str, Any]]:
    """Attach account_code and account_name to each journal line dict."""
    enriched = []
    for line in lines:
        account_id = line.get("account_id")
        if account_id:
            try:
                account = await db.accounts.find_one({"_id": _obj_id(account_id)})
            except Exception:
                account = None
            if account:
                line["account_code"] = account.get("code", "")
                line["account_name"] = account.get("name", "")
        enriched.append(line)
    return enriched


# ---------------------------------------------------------------------------
# Chart of Accounts
# ---------------------------------------------------------------------------

@router.get("/accounts", summary="Chart of accounts")
async def list_accounts(
    account_type: Optional[str] = Query(None),
    property_id: Optional[str] = Query(None),
    active_only: bool = Query(True),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return the full chart of accounts, optionally filtered by type or property."""
    query: Dict[str, Any] = {}
    if active_only:
        query["is_active"] = True
    if account_type:
        query["account_type"] = account_type
    if property_id:
        query["$or"] = [{"property_id": property_id}, {"property_id": None}]

    cursor = db.accounts.find(query).sort("code", 1)
    accounts = [_serialize(a) async for a in cursor]
    return {"total": len(accounts), "data": accounts}


@router.post("/accounts", status_code=status.HTTP_201_CREATED, summary="Create account")
async def create_account(
    body: AccountCreateRequest,
    current_user: dict = Depends(require_manager_or_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Create a new account in the chart of accounts."""
    # Ensure code is unique
    existing = await db.accounts.find_one({"code": body.code})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Account code '{body.code}' already exists.",
        )

    if body.parent_id:
        await _get_account_or_404(body.parent_id, db)

    now = datetime.now(timezone.utc)
    doc = body.model_dump()
    doc["is_active"] = True
    doc["is_system"] = False
    doc["created_at"] = now

    result = await db.accounts.insert_one(doc)
    created = await db.accounts.find_one({"_id": result.inserted_id})
    log.info("Account created", code=body.code, name=body.name)
    return _serialize(created)


@router.get("/accounts/{account_id}", summary="Get single account")
async def get_account(
    account_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return a single account by ID."""
    account = await _get_account_or_404(account_id, db)
    return _serialize(account)


# ---------------------------------------------------------------------------
# Journal Entries
# ---------------------------------------------------------------------------

@router.post("/journal-entries", status_code=status.HTTP_201_CREATED, summary="Create journal entry")
async def create_journal_entry(
    body: JournalEntryCreateRequest,
    current_user: dict = Depends(require_manager_or_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Create a double-entry journal entry.  The sum of debits must equal the
    sum of credits — this is validated in the request model.
    """
    # Validate all account IDs exist
    enriched_lines = []
    for line in body.lines:
        account = await _get_account_or_404(line.account_id, db)
        enriched_lines.append({
            "account_id": line.account_id,
            "account_code": account["code"],
            "account_name": account["name"],
            "debit": line.debit,
            "credit": line.credit,
            "description": line.description,
            "property_id": line.property_id or body.property_id,
        })

    now = datetime.now(timezone.utc)
    entry_number = await _next_entry_number(db)

    entry_doc = {
        "entry_number": entry_number,
        "date": datetime(body.date.year, body.date.month, body.date.day),
        "description": body.description,
        "entry_type": body.entry_type,
        "lines": enriched_lines,
        "reference_id": body.reference_id,
        "reference_type": body.reference_type,
        "property_id": body.property_id,
        "is_voided": False,
        "void_reason": None,
        "created_by": str(current_user["_id"]),
        "approved_by": None,
        "created_at": now,
        "updated_at": now,
    }

    result = await db.journal_entries.insert_one(entry_doc)
    created = await db.journal_entries.find_one({"_id": result.inserted_id})
    log.info("Journal entry created", entry_number=entry_number)
    return _serialize(created)


@router.get("/journal-entries", summary="List journal entries")
async def list_journal_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    property_id: Optional[str] = Query(None),
    entry_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    include_voided: bool = Query(False),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return a paginated, filtered list of journal entries."""
    query: Dict[str, Any] = {}

    if not include_voided:
        query["is_voided"] = False
    if property_id:
        query["property_id"] = property_id
    if entry_type:
        query["entry_type"] = entry_type

    date_filter: Dict[str, Any] = {}
    if date_from:
        date_filter["$gte"] = _parse_date(date_from, "date_from")
    if date_to:
        date_filter["$lte"] = _parse_date(date_to, "date_to")
    if date_filter:
        query["date"] = date_filter

    total = await db.journal_entries.count_documents(query)
    cursor = db.journal_entries.find(query).sort("date", -1).skip(skip).limit(limit)
    entries = [_serialize(e) async for e in cursor]

    return {"total": total, "skip": skip, "limit": limit, "data": entries}


@router.get("/journal-entries/{entry_id}", summary="Get single journal entry")
async def get_journal_entry(
    entry_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return a single journal entry by ID."""
    entry = await db.journal_entries.find_one({"_id": _obj_id(entry_id)})
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal entry not found")
    return _serialize(entry)


@router.post("/journal-entries/{entry_id}/void", summary="Void a journal entry")
async def void_journal_entry(
    entry_id: str,
    body: VoidEntryRequest,
    current_user: dict = Depends(require_manager_or_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Void an existing journal entry.  Creates a reversing entry with all debits
    and credits swapped, then marks the original as voided.
    """
    original = await db.journal_entries.find_one({"_id": _obj_id(entry_id)})
    if not original:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal entry not found")
    if original.get("is_voided"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Journal entry is already voided.",
        )

    now = datetime.now(timezone.utc)

    # Mark original as voided
    await db.journal_entries.update_one(
        {"_id": _obj_id(entry_id)},
        {
            "$set": {
                "is_voided": True,
                "void_reason": body.void_reason,
                "updated_at": now,
            }
        },
    )

    # Create reversing entry (swap debits/credits)
    reversing_lines = []
    for line in original.get("lines", []):
        reversing_lines.append({
            "account_id": line["account_id"],
            "account_code": line.get("account_code", ""),
            "account_name": line.get("account_name", ""),
            "debit": line.get("credit", 0.0),
            "credit": line.get("debit", 0.0),
            "description": f"VOID: {line.get('description', '')}",
            "property_id": line.get("property_id"),
        })

    entry_number = await _next_entry_number(db)
    reversing_doc = {
        "entry_number": entry_number,
        "date": now,
        "description": f"VOID of {original['entry_number']}: {body.void_reason}",
        "entry_type": "void",
        "lines": reversing_lines,
        "reference_id": str(original["_id"]),
        "reference_type": "void",
        "property_id": original.get("property_id"),
        "is_voided": False,
        "void_reason": None,
        "created_by": str(current_user["_id"]),
        "approved_by": None,
        "created_at": now,
        "updated_at": now,
    }

    await db.journal_entries.insert_one(reversing_doc)
    updated_original = await db.journal_entries.find_one({"_id": _obj_id(entry_id)})
    log.info("Journal entry voided", entry_id=entry_id, reason=body.void_reason)
    return _serialize(updated_original)


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

async def _account_balances(
    db: AsyncIOMotorDatabase,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    property_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Aggregate debit/credit totals per account from journal entry lines.
    Returns a list of dicts with account metadata and net balance.
    """
    match: Dict[str, Any] = {"is_voided": False}
    if date_from or date_to:
        date_filter: Dict[str, Any] = {}
        if date_from:
            date_filter["$gte"] = date_from
        if date_to:
            date_filter["$lte"] = date_to
        match["date"] = date_filter
    if property_id:
        match["property_id"] = property_id

    pipeline = [
        {"$match": match},
        {"$unwind": "$lines"},
        {
            "$group": {
                "_id": "$lines.account_id",
                "account_code": {"$first": "$lines.account_code"},
                "account_name": {"$first": "$lines.account_name"},
                "total_debit": {"$sum": "$lines.debit"},
                "total_credit": {"$sum": "$lines.credit"},
            }
        },
        {
            "$lookup": {
                "from": "accounts",
                "let": {"aid": {"$toObjectId": "$_id"}},
                "pipeline": [{"$match": {"$expr": {"$eq": ["$_id", "$$aid"]}}}],
                "as": "account_doc",
            }
        },
        {"$unwind": {"path": "$account_doc", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "account_id": "$_id",
                "account_code": 1,
                "account_name": 1,
                "account_type": "$account_doc.account_type",
                "subtype": "$account_doc.subtype",
                "normal_balance": "$account_doc.normal_balance",
                "total_debit": 1,
                "total_credit": 1,
            }
        },
        {"$sort": {"account_code": 1}},
    ]

    return await db.journal_entries.aggregate(pipeline).to_list(None)


def _compute_balance(row: Dict[str, Any]) -> float:
    """
    Compute the net balance for an account row.
    Normal debit accounts: balance = debit - credit
    Normal credit accounts: balance = credit - debit
    """
    normal = row.get("normal_balance", "debit")
    debit = row.get("total_debit", 0.0)
    credit = row.get("total_credit", 0.0)
    if normal == "credit":
        return round(credit - debit, 2)
    return round(debit - credit, 2)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@router.get("/reports/trial-balance", summary="Trial balance report")
async def trial_balance(
    date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    property_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_manager_or_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Compute and return the trial balance showing total debits and credits
    per account.  Validates that total debits equal total credits.
    """
    dt_from = _parse_date(date_from, "date_from") if date_from else None
    dt_to = _parse_date(date_to, "date_to") if date_to else None

    rows = await _account_balances(db, dt_from, dt_to, property_id)

    total_debit = round(sum(r["total_debit"] for r in rows), 2)
    total_credit = round(sum(r["total_credit"] for r in rows), 2)
    is_balanced = abs(total_debit - total_credit) < 0.01

    accounts_list = []
    for row in rows:
        accounts_list.append({
            "account_id": str(row["account_id"]),
            "account_code": row.get("account_code", ""),
            "account_name": row.get("account_name", ""),
            "account_type": row.get("account_type"),
            "subtype": row.get("subtype"),
            "total_debit": round(row["total_debit"], 2),
            "total_credit": round(row["total_credit"], 2),
            "balance": _compute_balance(row),
        })

    return {
        "title": "Trial Balance",
        "date_from": date_from,
        "date_to": date_to,
        "property_id": property_id,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "is_balanced": is_balanced,
        "accounts": accounts_list,
    }


@router.get("/reports/income-statement", summary="Income statement (P&L)")
async def income_statement(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
    property_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Profit & Loss statement for a date range.
    Optionally scoped to a single property.
    Owners can only view P&Ls for their own properties.
    """
    # RBAC check for owners
    role = current_user.get("role")
    if role == UserRole.OWNER.value and property_id:
        ownership = await db.ownerships.find_one(
            {"owner_id": str(current_user["_id"]), "property_id": property_id}
        )
        if not ownership:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    dt_from = _parse_date(date_from, "date_from")
    dt_to = _parse_date(date_to, "date_to")

    rows = await _account_balances(db, dt_from, dt_to, property_id)

    revenue_accounts = [r for r in rows if r.get("account_type") == "revenue"]
    expense_accounts = [r for r in rows if r.get("account_type") == "expense"]

    def _section(accounts: List[Dict]) -> Dict[str, Any]:
        items = []
        total = 0.0
        for r in sorted(accounts, key=lambda x: x.get("account_code", "")):
            balance = _compute_balance(r)
            total += balance
            items.append({
                "account_id": str(r["account_id"]),
                "account_code": r.get("account_code", ""),
                "account_name": r.get("account_name", ""),
                "subtype": r.get("subtype"),
                "amount": balance,
            })
        return {"items": items, "total": round(total, 2)}

    revenue_section = _section(revenue_accounts)
    expense_section = _section(expense_accounts)
    net_income = round(revenue_section["total"] - expense_section["total"], 2)

    return {
        "title": "Income Statement",
        "date_from": date_from,
        "date_to": date_to,
        "property_id": property_id,
        "revenue": revenue_section,
        "expenses": expense_section,
        "net_income": net_income,
        "net_income_margin": round(
            (net_income / revenue_section["total"] * 100)
            if revenue_section["total"]
            else 0.0,
            2,
        ),
    }


@router.get("/reports/balance-sheet", summary="Balance sheet")
async def balance_sheet(
    as_of_date: str = Query(..., description="As-of date YYYY-MM-DD"),
    property_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_manager_or_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Return the balance sheet (Assets = Liabilities + Equity) as of a specific
    date.  All journal entries up to and including the as_of_date are included.
    """
    dt_to = _parse_date(as_of_date, "as_of_date")

    rows = await _account_balances(db, date_from=None, date_to=dt_to, property_id=property_id)

    def _section(acct_type: str) -> Dict[str, Any]:
        items = []
        total = 0.0
        for r in sorted(
            [r for r in rows if r.get("account_type") == acct_type],
            key=lambda x: x.get("account_code", ""),
        ):
            balance = _compute_balance(r)
            total += balance
            items.append({
                "account_id": str(r["account_id"]),
                "account_code": r.get("account_code", ""),
                "account_name": r.get("account_name", ""),
                "subtype": r.get("subtype"),
                "balance": balance,
            })
        return {"items": items, "total": round(total, 2)}

    assets = _section("asset")
    liabilities = _section("liability")
    equity = _section("equity")

    # Retain net income in equity
    revenue_rows = [r for r in rows if r.get("account_type") == "revenue"]
    expense_rows = [r for r in rows if r.get("account_type") == "expense"]
    retained = round(
        sum(_compute_balance(r) for r in revenue_rows)
        - sum(_compute_balance(r) for r in expense_rows),
        2,
    )

    total_equity = round(equity["total"] + retained, 2)
    total_liabilities_equity = round(liabilities["total"] + total_equity, 2)
    is_balanced = abs(assets["total"] - total_liabilities_equity) < 0.01

    return {
        "title": "Balance Sheet",
        "as_of_date": as_of_date,
        "property_id": property_id,
        "assets": assets,
        "liabilities": liabilities,
        "equity": {
            "items": equity["items"],
            "retained_earnings": retained,
            "total": total_equity,
        },
        "total_liabilities_and_equity": total_liabilities_equity,
        "is_balanced": is_balanced,
    }


@router.get("/reports/cash-flow", summary="Cash flow summary")
async def cash_flow(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
    property_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_manager_or_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Simplified cash flow summary derived from journal entries involving cash
    and bank accounts.  Groups movements into operating, investing, and
    financing activities based on account subtype.
    """
    dt_from = _parse_date(date_from, "date_from")
    dt_to = _parse_date(date_to, "date_to")

    match: Dict[str, Any] = {
        "is_voided": False,
        "date": {"$gte": dt_from, "$lte": dt_to},
    }
    if property_id:
        match["property_id"] = property_id

    # Get all journal lines for cash/bank accounts
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
            "$match": {
                "account_doc.subtype": {"$in": ["cash", "bank"]},
            }
        },
        {
            "$group": {
                "_id": "$entry_type",
                "inflow": {"$sum": "$lines.debit"},
                "outflow": {"$sum": "$lines.credit"},
            }
        },
    ]

    agg = await db.journal_entries.aggregate(pipeline).to_list(None)

    # Map entry types to cash flow categories
    operating_types = {"rent", "invoice", "payment", "expense", "adjustment"}
    investing_types = {"asset_purchase", "asset_sale", "capex"}
    financing_types = {"loan", "owner_draw", "owner_contribution"}

    operating_inflow = operating_outflow = 0.0
    investing_inflow = investing_outflow = 0.0
    financing_inflow = financing_outflow = 0.0
    other_inflow = other_outflow = 0.0

    for row in agg:
        entry_type = row["_id"] or "other"
        inflow = round(row["inflow"], 2)
        outflow = round(row["outflow"], 2)
        if entry_type in operating_types:
            operating_inflow += inflow
            operating_outflow += outflow
        elif entry_type in investing_types:
            investing_inflow += inflow
            investing_outflow += outflow
        elif entry_type in financing_types:
            financing_inflow += inflow
            financing_outflow += outflow
        else:
            other_inflow += inflow
            other_outflow += outflow

    operating_net = round(operating_inflow - operating_outflow, 2)
    investing_net = round(investing_inflow - investing_outflow, 2)
    financing_net = round(financing_inflow - financing_outflow, 2)
    other_net = round(other_inflow - other_outflow, 2)
    net_change = round(operating_net + investing_net + financing_net + other_net, 2)

    return {
        "title": "Cash Flow Summary",
        "date_from": date_from,
        "date_to": date_to,
        "property_id": property_id,
        "operating": {
            "inflow": round(operating_inflow, 2),
            "outflow": round(operating_outflow, 2),
            "net": operating_net,
        },
        "investing": {
            "inflow": round(investing_inflow, 2),
            "outflow": round(investing_outflow, 2),
            "net": investing_net,
        },
        "financing": {
            "inflow": round(financing_inflow, 2),
            "outflow": round(financing_outflow, 2),
            "net": financing_net,
        },
        "other": {
            "inflow": round(other_inflow, 2),
            "outflow": round(other_outflow, 2),
            "net": other_net,
        },
        "net_cash_change": net_change,
    }


@router.get("/reports/owner-statement/{owner_id}", summary="Owner financial statement")
async def owner_statement(
    owner_id: str,
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
    property_id: Optional[str] = Query(None, description="Scope to a single property"),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Generate a complete owner statement for a date range.  Includes per-property
    income, management fees, expenses, and distributions.  Owners can only
    retrieve their own statement; admin/managers can retrieve any.
    """
    role = current_user.get("role")
    caller_id = str(current_user["_id"])

    if role not in (UserRole.ADMIN.value, UserRole.MANAGER.value):
        if caller_id != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    owner = await db.users.find_one({"_id": _obj_id(owner_id)})
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    dt_from = _parse_date(date_from, "date_from")
    dt_to = _parse_date(date_to, "date_to")

    # Collect all ownership records for this owner (optionally filtered by property)
    ownership_query: Dict[str, Any] = {"owner_id": owner_id}
    if property_id:
        ownership_query["property_id"] = property_id

    ownerships = await db.ownerships.find(ownership_query).to_list(None)

    property_statements = []
    total_income = 0.0
    total_management_fee = 0.0
    total_expenses = 0.0
    total_distributions = 0.0

    for ownership in ownerships:
        prop_id_str = ownership["property_id"]
        try:
            prop = await db.properties.find_one({"_id": _obj_id(prop_id_str)})
        except Exception:
            continue
        if not prop:
            continue

        pct = ownership.get("ownership_percentage", 100.0)

        rows = await _account_balances(db, dt_from, dt_to, prop_id_str)

        def _type_total(acct_type: str) -> float:
            return round(
                sum(_compute_balance(r) for r in rows if r.get("account_type") == acct_type),
                2,
            )

        prop_income = _type_total("revenue")
        prop_expenses = _type_total("expense")

        # Management fee subtotal (from expense lines with management_fee subtype)
        mgmt_fee = round(
            sum(
                _compute_balance(r)
                for r in rows
                if r.get("account_type") == "expense" and r.get("subtype") == "management_fee"
            ),
            2,
        )

        # Income net of management fee, scaled by ownership %
        owner_income = round(prop_income * pct / 100, 2)
        owner_expenses = round(prop_expenses * pct / 100, 2)
        owner_mgmt_fee = round(mgmt_fee * pct / 100, 2)
        owner_noi = round(owner_income - owner_expenses, 2)

        # Paid invoices (distributions) in period
        payments_pipeline = [
            {
                "$match": {
                    "owner_id": owner_id,
                    "property_id": prop_id_str,
                    "payment_date": {"$gte": dt_from, "$lte": dt_to},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
        payments_agg = await db.payments.aggregate(payments_pipeline).to_list(1)
        distributions = round(payments_agg[0]["total"] * pct / 100, 2) if payments_agg else 0.0

        total_income += owner_income
        total_management_fee += owner_mgmt_fee
        total_expenses += owner_expenses
        total_distributions += distributions

        # Line-level detail
        line_items = []
        for r in sorted(rows, key=lambda x: (x.get("account_type", ""), x.get("account_code", ""))):
            balance = _compute_balance(r)
            if balance == 0.0:
                continue
            line_items.append({
                "account_code": r.get("account_code", ""),
                "account_name": r.get("account_name", ""),
                "account_type": r.get("account_type"),
                "subtype": r.get("subtype"),
                "amount": round(balance * pct / 100, 2),
            })

        property_statements.append({
            "property_id": prop_id_str,
            "property_name": prop.get("name"),
            "ownership_percentage": pct,
            "gross_income": owner_income,
            "management_fee": owner_mgmt_fee,
            "total_expenses": owner_expenses,
            "net_operating_income": owner_noi,
            "distributions": distributions,
            "line_items": line_items,
        })

    return {
        "title": "Owner Statement",
        "owner_id": owner_id,
        "owner_name": owner.get("full_name"),
        "owner_email": owner.get("email"),
        "date_from": date_from,
        "date_to": date_to,
        "summary": {
            "total_gross_income": round(total_income, 2),
            "total_management_fee": round(total_management_fee, 2),
            "total_expenses": round(total_expenses, 2),
            "total_net_income": round(total_income - total_expenses, 2),
            "total_distributions": round(total_distributions, 2),
            "balance_due": round(total_income - total_expenses - total_distributions, 2),
        },
        "properties": property_statements,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
