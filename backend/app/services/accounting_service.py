"""
accounting_service.py
---------------------
Double-entry accounting engine for the Estatio property management platform.

Responsibilities:
  - Create and validate journal entries (debit == credit)
  - Maintain materialized ledger balances per account per period
  - Produce financial reports: trial balance, income statement, balance sheet,
    cash-flow statement, and per-owner statements
  - Seed the standard Chart of Accounts for property management

MongoDB collections used:
  accounts          – Chart of Accounts (AccountDB)
  journal_entries   – Double-entry journal entries (JournalEntryDB)
  ledger_balances   – Materialized period balances (LedgerBalanceDB)
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import structlog
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.accounting import (
    AccountSubtype,
    AccountType,
    JournalLine,
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return str(ObjectId())


def _round2(value: float) -> float:
    """Round a monetary value to 2 decimal places."""
    return round(value, 2)


async def _next_entry_number(db: AsyncIOMotorDatabase) -> str:
    """Generate a sequential journal entry number: JE-{YEAR}-{SEQ:06d}."""
    year = datetime.utcnow().year
    prefix = f"JE-{year}-"
    last = await db.journal_entries.find_one(
        {"entry_number": {"$regex": f"^{prefix}"}},
        sort=[("entry_number", -1)],
    )
    if last:
        try:
            seq = int(last["entry_number"].split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:06d}"


def _account_normal_balance(account_type: AccountType) -> str:
    """Assets and expenses have a debit normal balance; others credit."""
    if account_type in (AccountType.ASSET, AccountType.EXPENSE):
        return "debit"
    return "credit"


# ---------------------------------------------------------------------------
# Chart of Accounts seed
# ---------------------------------------------------------------------------

# Standard property-management CoA entries:
# (code, name, account_type, subtype, parent_code, description)
_STANDARD_COA: List[Tuple[str, str, AccountType, AccountSubtype, Optional[str], str]] = [
    # ── Assets ──────────────────────────────────────────────────────────────
    ("1000", "Cash and Cash Equivalents", AccountType.ASSET, AccountSubtype.CASH, None,
     "Primary operating cash accounts"),
    ("1010", "Operating Checking", AccountType.ASSET, AccountSubtype.BANK, "1000",
     "Main bank checking account"),
    ("1020", "Security Deposit Trust Account", AccountType.ASSET, AccountSubtype.BANK, "1000",
     "Tenant security deposit escrow"),
    ("1100", "Accounts Receivable", AccountType.ASSET, AccountSubtype.ACCOUNTS_RECEIVABLE, None,
     "Amounts owed by owners / tenants"),
    ("1200", "Prepaid Expenses", AccountType.ASSET, AccountSubtype.PREPAID, None,
     "Insurance and other prepaid costs"),
    ("1500", "Fixed Assets", AccountType.ASSET, AccountSubtype.FIXED_ASSET, None,
     "Long-lived property assets"),
    # ── Liabilities ─────────────────────────────────────────────────────────
    ("2000", "Accounts Payable", AccountType.LIABILITY, AccountSubtype.ACCOUNTS_PAYABLE, None,
     "Amounts owed to vendors"),
    ("2100", "Accrued Liabilities", AccountType.LIABILITY, AccountSubtype.ACCRUED_LIABILITY, None,
     "Accrued but unpaid expenses"),
    ("2200", "Security Deposits Held", AccountType.LIABILITY, AccountSubtype.SECURITY_DEPOSIT, None,
     "Tenant security deposits payable"),
    ("2300", "Owner Distributions Payable", AccountType.LIABILITY, AccountSubtype.ACCRUED_LIABILITY, None,
     "Net proceeds payable to owners"),
    # ── Equity ──────────────────────────────────────────────────────────────
    ("3000", "Owner Equity", AccountType.EQUITY, AccountSubtype.OWNER_EQUITY, None,
     "Accumulated owner equity"),
    ("3100", "Retained Earnings", AccountType.EQUITY, AccountSubtype.RETAINED_EARNINGS, None,
     "Accumulated retained earnings"),
    # ── Revenue ─────────────────────────────────────────────────────────────
    ("4000", "Rental Income", AccountType.REVENUE, AccountSubtype.RENT_INCOME, None,
     "Gross rental revenue"),
    ("4100", "Management Fee Income", AccountType.REVENUE, AccountSubtype.MANAGEMENT_FEE, None,
     "Property management fees collected"),
    ("4200", "Late Fee Income", AccountType.REVENUE, AccountSubtype.LATE_FEE, None,
     "Late payment fees charged to owners"),
    ("4300", "Other Income", AccountType.REVENUE, AccountSubtype.OTHER_INCOME, None,
     "Miscellaneous income"),
    # ── Expenses ────────────────────────────────────────────────────────────
    ("5000", "Maintenance and Repairs", AccountType.EXPENSE, AccountSubtype.MAINTENANCE, None,
     "Repairs, maintenance, and work orders"),
    ("5010", "HVAC", AccountType.EXPENSE, AccountSubtype.MAINTENANCE, "5000",
     "Heating, ventilation, and air conditioning"),
    ("5020", "Plumbing", AccountType.EXPENSE, AccountSubtype.MAINTENANCE, "5000",
     "Plumbing repairs"),
    ("5030", "Electrical", AccountType.EXPENSE, AccountSubtype.MAINTENANCE, "5000",
     "Electrical work"),
    ("5040", "Appliances", AccountType.EXPENSE, AccountSubtype.MAINTENANCE, "5000",
     "Appliance repairs and replacements"),
    ("5050", "Landscaping", AccountType.EXPENSE, AccountSubtype.MAINTENANCE, "5000",
     "Grounds and landscaping"),
    ("5100", "Utilities", AccountType.EXPENSE, AccountSubtype.UTILITIES, None,
     "Water, gas, electric, trash"),
    ("5200", "Insurance", AccountType.EXPENSE, AccountSubtype.INSURANCE, None,
     "Property and liability insurance"),
    ("5300", "HOA Fees", AccountType.EXPENSE, AccountSubtype.HOA, None,
     "Homeowners association dues"),
    ("5400", "Mortgage / Loan Interest", AccountType.EXPENSE, AccountSubtype.MORTGAGE, None,
     "Interest portion of mortgage payments"),
    ("5500", "Property Taxes", AccountType.EXPENSE, AccountSubtype.TAX, None,
     "Annual property taxes"),
    ("5600", "Management Fees Paid", AccountType.EXPENSE, AccountSubtype.MANAGEMENT_EXPENSE, None,
     "Fees paid to property manager (owner's view)"),
    ("5700", "Contractor Expenses", AccountType.EXPENSE, AccountSubtype.CONTRACTOR, None,
     "1099 contractor payments"),
    ("5800", "Advertising and Marketing", AccountType.EXPENSE, AccountSubtype.ADVERTISING, None,
     "Listing fees, marketing, photography"),
    ("5900", "Other Expenses", AccountType.EXPENSE, AccountSubtype.OTHER_EXPENSE, None,
     "Miscellaneous property expenses"),
]


async def seed_chart_of_accounts(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Create the standard property-management Chart of Accounts if not present.

    Idempotent: existing accounts (matched by code) are left unchanged.
    Returns a summary dict with counts of created and skipped accounts.
    """
    logger = log.bind(action="seed_chart_of_accounts")
    logger.info("Starting CoA seed")

    # Build a lookup of existing codes to avoid duplicates.
    existing_cursor = db.accounts.find({}, {"code": 1})
    existing_codes: set[str] = set()
    async for doc in existing_cursor:
        existing_codes.add(doc["code"])

    # First pass: insert all parent accounts (parent_code == None).
    code_to_id: Dict[str, str] = {}
    created = 0
    skipped = 0

    # Fetch IDs for already-existing codes.
    if existing_codes:
        async for doc in db.accounts.find({"code": {"$in": list(existing_codes)}}):
            code_to_id[doc["code"]] = str(doc["_id"])

    for code, name, acc_type, subtype, parent_code, description in _STANDARD_COA:
        if code in existing_codes:
            skipped += 1
            continue

        parent_id: Optional[str] = None
        if parent_code:
            parent_id = code_to_id.get(parent_code)

        account_id = _new_id()
        doc: Dict[str, Any] = {
            "_id": account_id,
            "code": code,
            "name": name,
            "account_type": acc_type.value,
            "subtype": subtype.value,
            "parent_id": parent_id,
            "property_id": None,
            "description": description,
            "is_active": True,
            "is_system": True,
            "normal_balance": _account_normal_balance(acc_type),
            "created_at": datetime.utcnow(),
        }
        await db.accounts.insert_one(doc)
        code_to_id[code] = account_id
        created += 1

    logger.info("CoA seed complete", created=created, skipped=skipped)
    return {"created": created, "skipped": skipped, "total": created + skipped}


# ---------------------------------------------------------------------------
# Journal entry creation
# ---------------------------------------------------------------------------

async def create_journal_entry(
    db: AsyncIOMotorDatabase,
    entry_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a balanced double-entry journal entry and update ledger balances.

    ``entry_data`` keys (all required unless noted):
        date          – ISO date string or date object
        description   – str
        entry_type    – str (rent | invoice | payment | expense | adjustment | opening)
        lines         – list of dicts with keys:
                          account_id, account_code, account_name,
                          debit (float, default 0), credit (float, default 0),
                          description (optional), property_id (optional)
        created_by    – str (user_id)
        reference_id  – str (optional)
        reference_type– str (optional)
        property_id   – str (optional)

    Raises:
        ValueError – if debits != credits (within $0.01 tolerance)
    """
    logger = log.bind(action="create_journal_entry", entry_type=entry_data.get("entry_type"))

    # Normalise date
    raw_date = entry_data.get("date", date.today())
    if isinstance(raw_date, str):
        raw_date = date.fromisoformat(raw_date)
    entry_date: date = raw_date

    # Build and validate lines
    lines: List[JournalLine] = []
    for raw_line in entry_data.get("lines", []):
        line = JournalLine(
            account_id=raw_line["account_id"],
            account_code=raw_line.get("account_code", ""),
            account_name=raw_line.get("account_name", ""),
            debit=_round2(float(raw_line.get("debit", 0.0))),
            credit=_round2(float(raw_line.get("credit", 0.0))),
            description=raw_line.get("description"),
            property_id=raw_line.get("property_id"),
        )
        lines.append(line)

    total_debit = _round2(sum(ln.debit for ln in lines))
    total_credit = _round2(sum(ln.credit for ln in lines))

    if abs(total_debit - total_credit) >= 0.01:
        raise ValueError(
            f"Journal entry is not balanced: debits={total_debit}, credits={total_credit}"
        )

    entry_number = await _next_entry_number(db)
    entry_id = _new_id()
    now = datetime.utcnow()

    doc: Dict[str, Any] = {
        "_id": entry_id,
        "entry_number": entry_number,
        "date": datetime.combine(entry_date, datetime.min.time()),
        "description": entry_data["description"],
        "entry_type": entry_data.get("entry_type", "adjustment"),
        "lines": [ln.model_dump() for ln in lines],
        "reference_id": entry_data.get("reference_id"),
        "reference_type": entry_data.get("reference_type"),
        "property_id": entry_data.get("property_id"),
        "is_voided": False,
        "void_reason": None,
        "created_by": entry_data.get("created_by", "system"),
        "approved_by": entry_data.get("approved_by"),
        "created_at": now,
        "updated_at": now,
    }

    await db.journal_entries.insert_one(doc)
    logger.info(
        "Journal entry created",
        entry_id=entry_id,
        entry_number=entry_number,
        total_debit=total_debit,
    )

    # Update materialised ledger balances for each line concurrently.
    update_tasks = [
        update_ledger_balance(
            db,
            account_id=ln.account_id,
            year=entry_date.year,
            month=entry_date.month,
            debit=ln.debit,
            credit=ln.credit,
            property_id=ln.property_id,
        )
        for ln in lines
    ]
    await asyncio.gather(*update_tasks)

    return doc


# ---------------------------------------------------------------------------
# Ledger balance maintenance
# ---------------------------------------------------------------------------

async def update_ledger_balance(
    db: AsyncIOMotorDatabase,
    account_id: str,
    year: int,
    month: int,
    debit: float,
    credit: float,
    property_id: Optional[str] = None,
) -> None:
    """
    Upsert the LedgerBalance materialised document for a given account / period.

    The closing_balance is computed as:
        opening_balance + total_debits – total_credits
    (i.e., it follows the debit-normal convention; callers convert as needed).
    """
    filter_doc: Dict[str, Any] = {
        "account_id": account_id,
        "period_year": year,
        "period_month": month,
    }
    if property_id:
        filter_doc["property_id"] = property_id
    else:
        filter_doc["property_id"] = None

    # Fetch the account's code so the ledger record is self-describing.
    account_doc = await db.accounts.find_one({"_id": account_id}, {"code": 1})
    account_code = account_doc["code"] if account_doc else ""

    update_doc: Dict[str, Any] = {
        "$inc": {
            "total_debits": _round2(debit),
            "total_credits": _round2(credit),
        },
        "$set": {
            "account_code": account_code,
            "updated_at": datetime.utcnow(),
        },
        "$setOnInsert": {
            "_id": _new_id(),
            "account_id": account_id,
            "property_id": property_id,
            "period_year": year,
            "period_month": month,
            "opening_balance": 0.0,
        },
    }

    await db.ledger_balances.update_one(filter_doc, update_doc, upsert=True)

    # Re-compute closing balance from the persisted totals.
    lb = await db.ledger_balances.find_one(filter_doc)
    if lb:
        closing = _round2(
            lb.get("opening_balance", 0.0)
            + lb.get("total_debits", 0.0)
            - lb.get("total_credits", 0.0)
        )
        await db.ledger_balances.update_one(
            filter_doc, {"$set": {"closing_balance": closing}}
        )

    log.debug(
        "Ledger balance updated",
        account_id=account_id,
        year=year,
        month=month,
        debit=debit,
        credit=credit,
    )


# ---------------------------------------------------------------------------
# Trial balance
# ---------------------------------------------------------------------------

async def get_trial_balance(
    db: AsyncIOMotorDatabase,
    property_id: Optional[str] = None,
    as_of_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Return all accounts with their cumulative debit and credit totals.

    If ``as_of_date`` is supplied, only journal entries on or before that date
    are included; otherwise all entries are used.

    Returns:
        {
            "as_of_date": ...,
            "property_id": ...,
            "accounts": [
                {
                    "account_id": ...,
                    "account_code": ...,
                    "account_name": ...,
                    "account_type": ...,
                    "normal_balance": ...,
                    "total_debits": ...,
                    "total_credits": ...,
                    "net_balance": ...,   # debits – credits (debit-normal)
                }
            ],
            "total_debits": ...,
            "total_credits": ...,
            "is_balanced": ...,
        }
    """
    logger = log.bind(action="get_trial_balance", as_of_date=str(as_of_date))
    logger.info("Building trial balance")

    # Match clause for journal entries
    match: Dict[str, Any] = {"is_voided": False}
    if as_of_date:
        match["date"] = {"$lte": datetime.combine(as_of_date, datetime.max.time())}
    if property_id:
        match["property_id"] = property_id

    pipeline = [
        {"$match": match},
        {"$unwind": "$lines"},
    ]
    if property_id:
        pipeline.append({"$match": {"lines.property_id": property_id}})

    pipeline += [
        {
            "$group": {
                "_id": "$lines.account_id",
                "account_code": {"$first": "$lines.account_code"},
                "account_name": {"$first": "$lines.account_name"},
                "total_debits": {"$sum": "$lines.debit"},
                "total_credits": {"$sum": "$lines.credit"},
            }
        },
        {"$sort": {"account_code": 1}},
    ]

    rows = []
    async for row in db.journal_entries.aggregate(pipeline):
        account_doc = await db.accounts.find_one({"_id": row["_id"]})
        acc_type = account_doc["account_type"] if account_doc else "unknown"
        normal_balance = account_doc["normal_balance"] if account_doc else "debit"
        td = _round2(row["total_debits"])
        tc = _round2(row["total_credits"])
        rows.append(
            {
                "account_id": row["_id"],
                "account_code": row.get("account_code", ""),
                "account_name": row.get("account_name", ""),
                "account_type": acc_type,
                "normal_balance": normal_balance,
                "total_debits": td,
                "total_credits": tc,
                "net_balance": _round2(td - tc),
            }
        )

    grand_debit = _round2(sum(r["total_debits"] for r in rows))
    grand_credit = _round2(sum(r["total_credits"] for r in rows))
    is_balanced = abs(grand_debit - grand_credit) < 0.01

    return {
        "as_of_date": str(as_of_date or date.today()),
        "property_id": property_id,
        "accounts": rows,
        "total_debits": grand_debit,
        "total_credits": grand_credit,
        "is_balanced": is_balanced,
    }


# ---------------------------------------------------------------------------
# Income statement  (P&L)
# ---------------------------------------------------------------------------

async def get_income_statement(
    db: AsyncIOMotorDatabase,
    start_date: date,
    end_date: date,
    property_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return revenue and expense totals for the given period.

    Returns:
        {
            "period": {"start": ..., "end": ...},
            "property_id": ...,
            "revenue": {"total": ..., "by_account": [...]},
            "expenses": {"total": ..., "by_account": [...]},
            "net_income": ...,
            "net_income_margin_pct": ...,
        }
    """
    logger = log.bind(
        action="get_income_statement",
        start_date=str(start_date),
        end_date=str(end_date),
    )
    logger.info("Building income statement")

    # Retrieve all revenue/expense accounts.
    rev_exp_accounts: Dict[str, Dict[str, Any]] = {}
    async for acc in db.accounts.find(
        {"account_type": {"$in": [AccountType.REVENUE.value, AccountType.EXPENSE.value]}}
    ):
        rev_exp_accounts[str(acc["_id"])] = acc

    match: Dict[str, Any] = {
        "is_voided": False,
        "date": {
            "$gte": datetime.combine(start_date, datetime.min.time()),
            "$lte": datetime.combine(end_date, datetime.max.time()),
        },
    }
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
                "total_debits": {"$sum": "$lines.debit"},
                "total_credits": {"$sum": "$lines.credit"},
            }
        },
    ]

    revenue_rows: List[Dict[str, Any]] = []
    expense_rows: List[Dict[str, Any]] = []

    async for row in db.journal_entries.aggregate(pipeline):
        acc_id = row["_id"]
        acc = rev_exp_accounts.get(acc_id)
        if not acc:
            continue

        td = _round2(row["total_debits"])
        tc = _round2(row["total_credits"])
        # Revenue: credit-normal → net = credits – debits
        # Expense: debit-normal → net = debits – credits
        if acc["account_type"] == AccountType.REVENUE.value:
            net = _round2(tc - td)
            revenue_rows.append(
                {
                    "account_id": acc_id,
                    "account_code": row.get("account_code", acc.get("code", "")),
                    "account_name": row.get("account_name", acc.get("name", "")),
                    "amount": net,
                }
            )
        elif acc["account_type"] == AccountType.EXPENSE.value:
            net = _round2(td - tc)
            expense_rows.append(
                {
                    "account_id": acc_id,
                    "account_code": row.get("account_code", acc.get("code", "")),
                    "account_name": row.get("account_name", acc.get("name", "")),
                    "amount": net,
                }
            )

    revenue_rows.sort(key=lambda r: r["account_code"])
    expense_rows.sort(key=lambda r: r["account_code"])

    total_revenue = _round2(sum(r["amount"] for r in revenue_rows))
    total_expenses = _round2(sum(r["amount"] for r in expense_rows))
    net_income = _round2(total_revenue - total_expenses)
    margin = _round2((net_income / total_revenue * 100) if total_revenue else 0.0)

    return {
        "period": {"start": str(start_date), "end": str(end_date)},
        "property_id": property_id,
        "revenue": {"total": total_revenue, "by_account": revenue_rows},
        "expenses": {"total": total_expenses, "by_account": expense_rows},
        "net_income": net_income,
        "net_income_margin_pct": margin,
    }


# ---------------------------------------------------------------------------
# Balance sheet
# ---------------------------------------------------------------------------

async def get_balance_sheet(
    db: AsyncIOMotorDatabase,
    as_of_date: date,
    property_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return assets, liabilities, and equity as of ``as_of_date``.

    Returns:
        {
            "as_of_date": ...,
            "property_id": ...,
            "assets": {"total": ..., "by_account": [...]},
            "liabilities": {"total": ..., "by_account": [...]},
            "equity": {"total": ..., "by_account": [...]},
            "is_balanced": ...,       # assets == liabilities + equity
        }
    """
    logger = log.bind(action="get_balance_sheet", as_of_date=str(as_of_date))
    logger.info("Building balance sheet")

    match: Dict[str, Any] = {
        "is_voided": False,
        "date": {"$lte": datetime.combine(as_of_date, datetime.max.time())},
    }
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
                "total_debits": {"$sum": "$lines.debit"},
                "total_credits": {"$sum": "$lines.credit"},
            }
        },
        {"$sort": {"account_code": 1}},
    ]

    assets: List[Dict[str, Any]] = []
    liabilities: List[Dict[str, Any]] = []
    equity: List[Dict[str, Any]] = []

    async for row in db.journal_entries.aggregate(pipeline):
        acc_id = row["_id"]
        acc = await db.accounts.find_one({"_id": acc_id})
        if not acc:
            continue

        td = _round2(row["total_debits"])
        tc = _round2(row["total_credits"])
        acc_type = acc["account_type"]

        entry = {
            "account_id": acc_id,
            "account_code": row.get("account_code", acc.get("code", "")),
            "account_name": row.get("account_name", acc.get("name", "")),
        }

        if acc_type == AccountType.ASSET.value:
            entry["balance"] = _round2(td - tc)  # debit-normal
            assets.append(entry)
        elif acc_type == AccountType.LIABILITY.value:
            entry["balance"] = _round2(tc - td)  # credit-normal
            liabilities.append(entry)
        elif acc_type == AccountType.EQUITY.value:
            entry["balance"] = _round2(tc - td)  # credit-normal
            equity.append(entry)
        # Revenue and expense flows affect retained earnings but are excluded from
        # the balance sheet view directly — they close into equity at period end.

    total_assets = _round2(sum(r["balance"] for r in assets))
    total_liabilities = _round2(sum(r["balance"] for r in liabilities))
    total_equity = _round2(sum(r["balance"] for r in equity))
    is_balanced = abs(total_assets - (total_liabilities + total_equity)) < 0.01

    return {
        "as_of_date": str(as_of_date),
        "property_id": property_id,
        "assets": {"total": total_assets, "by_account": assets},
        "liabilities": {"total": total_liabilities, "by_account": liabilities},
        "equity": {"total": total_equity, "by_account": equity},
        "total_liabilities_and_equity": _round2(total_liabilities + total_equity),
        "is_balanced": is_balanced,
    }


# ---------------------------------------------------------------------------
# Cash-flow statement
# ---------------------------------------------------------------------------

async def get_cash_flow(
    db: AsyncIOMotorDatabase,
    start_date: date,
    end_date: date,
    property_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Simplified cash-flow statement using the direct method.

    Cash accounts are identified by AccountSubtype.CASH and AccountSubtype.BANK.
    Inflows  = credits to cash accounts (money received)
    Outflows = debits to cash accounts  (money paid)

    Returns:
        {
            "period": {...},
            "operating": {"inflows": ..., "outflows": ..., "net": ..., "lines": [...]},
            "net_change_in_cash": ...,
        }
    """
    logger = log.bind(
        action="get_cash_flow",
        start_date=str(start_date),
        end_date=str(end_date),
    )
    logger.info("Building cash-flow statement")

    # Identify cash/bank account IDs
    cash_account_ids: List[str] = []
    async for acc in db.accounts.find(
        {"subtype": {"$in": [AccountSubtype.CASH.value, AccountSubtype.BANK.value]}}
    ):
        cash_account_ids.append(str(acc["_id"]))

    if not cash_account_ids:
        return {
            "period": {"start": str(start_date), "end": str(end_date)},
            "property_id": property_id,
            "operating": {"inflows": 0.0, "outflows": 0.0, "net": 0.0, "lines": []},
            "net_change_in_cash": 0.0,
        }

    match: Dict[str, Any] = {
        "is_voided": False,
        "date": {
            "$gte": datetime.combine(start_date, datetime.min.time()),
            "$lte": datetime.combine(end_date, datetime.max.time()),
        },
        "lines.account_id": {"$in": cash_account_ids},
    }
    if property_id:
        match["property_id"] = property_id

    pipeline = [
        {"$match": match},
        {"$unwind": "$lines"},
        {"$match": {"lines.account_id": {"$in": cash_account_ids}}},
        {
            "$group": {
                "_id": {
                    "account_id": "$lines.account_id",
                    "account_code": "$lines.account_code",
                    "account_name": "$lines.account_name",
                    "entry_type": "$entry_type",
                },
                "total_debits": {"$sum": "$lines.debit"},
                "total_credits": {"$sum": "$lines.credit"},
            }
        },
    ]

    lines: List[Dict[str, Any]] = []
    async for row in db.journal_entries.aggregate(pipeline):
        td = _round2(row["total_debits"])
        tc = _round2(row["total_credits"])
        lines.append(
            {
                "account_id": row["_id"]["account_id"],
                "account_code": row["_id"].get("account_code", ""),
                "account_name": row["_id"].get("account_name", ""),
                "entry_type": row["_id"].get("entry_type", ""),
                "inflow": tc,   # credits to cash = money coming in
                "outflow": td,  # debits to cash = money going out
                "net": _round2(tc - td),
            }
        )

    total_inflows = _round2(sum(ln["inflow"] for ln in lines))
    total_outflows = _round2(sum(ln["outflow"] for ln in lines))
    net_change = _round2(total_inflows - total_outflows)

    return {
        "period": {"start": str(start_date), "end": str(end_date)},
        "property_id": property_id,
        "operating": {
            "inflows": total_inflows,
            "outflows": total_outflows,
            "net": net_change,
            "lines": lines,
        },
        "net_change_in_cash": net_change,
    }


# ---------------------------------------------------------------------------
# Owner statement
# ---------------------------------------------------------------------------

async def get_owner_statement(
    db: AsyncIOMotorDatabase,
    owner_id: str,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    """
    Return all financial transactions across every property owned by ``owner_id``
    for the given period.

    Pulls invoices, payments, and work-order expenses linked to the owner's
    properties.

    Returns:
        {
            "owner_id": ...,
            "period": {...},
            "properties": [
                {
                    "property_id": ...,
                    "property_name": ...,
                    "invoices": [...],
                    "payments": [...],
                    "expenses": [...],
                    "summary": {
                        "total_invoiced": ...,
                        "total_paid": ...,
                        "total_expenses": ...,
                        "net": ...,
                    },
                }
            ],
            "totals": {
                "total_invoiced": ...,
                "total_paid": ...,
                "total_expenses": ...,
                "net": ...,
            },
        }
    """
    logger = log.bind(
        action="get_owner_statement",
        owner_id=owner_id,
        start_date=str(start_date),
        end_date=str(end_date),
    )
    logger.info("Building owner statement")

    # Find all properties this owner has access to.
    property_ids: List[str] = []
    async for ownership in db.ownerships.find({"owner_id": owner_id}):
        property_ids.append(ownership["property_id"])

    if not property_ids:
        return {
            "owner_id": owner_id,
            "period": {"start": str(start_date), "end": str(end_date)},
            "properties": [],
            "totals": {
                "total_invoiced": 0.0,
                "total_paid": 0.0,
                "total_expenses": 0.0,
                "net": 0.0,
            },
        }

    # Date filter for invoice / payment queries.
    date_gte = datetime.combine(start_date, datetime.min.time())
    date_lte = datetime.combine(end_date, datetime.max.time())

    property_summaries: List[Dict[str, Any]] = []
    grand_invoiced = 0.0
    grand_paid = 0.0
    grand_expenses = 0.0

    for prop_id in property_ids:
        prop_doc = await db.properties.find_one({"_id": prop_id})
        prop_name = prop_doc["name"] if prop_doc else prop_id

        # Invoices in period for this property
        invoice_docs: List[Dict[str, Any]] = []
        prop_invoiced = 0.0
        async for inv in db.invoices.find(
            {
                "property_id": prop_id,
                "owner_id": owner_id,
                "created_at": {"$gte": date_gte, "$lte": date_lte},
            }
        ):
            amt = _round2(inv.get("total_amount", 0.0))
            prop_invoiced += amt
            invoice_docs.append(
                {
                    "invoice_id": str(inv["_id"]),
                    "invoice_number": inv.get("invoice_number", ""),
                    "issue_date": str(inv.get("issue_date", "")),
                    "due_date": str(inv.get("due_date", "")),
                    "total_amount": amt,
                    "balance_due": _round2(inv.get("balance_due", 0.0)),
                    "status": inv.get("status", ""),
                }
            )

        # Payments in period
        payment_docs: List[Dict[str, Any]] = []
        prop_paid = 0.0
        async for pmt in db.payments.find(
            {
                "property_id": prop_id,
                "owner_id": owner_id,
                "created_at": {"$gte": date_gte, "$lte": date_lte},
            }
        ):
            amt = _round2(pmt.get("amount", 0.0))
            prop_paid += amt
            payment_docs.append(
                {
                    "payment_id": str(pmt["_id"]),
                    "invoice_id": pmt.get("invoice_id", ""),
                    "payment_date": str(pmt.get("payment_date", "")),
                    "amount": amt,
                    "payment_method": pmt.get("payment_method", ""),
                    "reference_number": pmt.get("reference_number"),
                }
            )

        # Expenses (completed work orders) in period
        expense_docs: List[Dict[str, Any]] = []
        prop_expenses = 0.0
        async for wo in db.work_orders.find(
            {
                "property_id": prop_id,
                "status": "completed",
                "completed_date": {
                    "$gte": start_date.isoformat(),
                    "$lte": end_date.isoformat(),
                },
            }
        ):
            cost = _round2(wo.get("actual_cost") or 0.0)
            prop_expenses += cost
            expense_docs.append(
                {
                    "work_order_id": str(wo["_id"]),
                    "work_order_number": wo.get("work_order_number", ""),
                    "title": wo.get("title", ""),
                    "category": wo.get("category", ""),
                    "completed_date": str(wo.get("completed_date", "")),
                    "actual_cost": cost,
                }
            )

        prop_invoiced = _round2(prop_invoiced)
        prop_paid = _round2(prop_paid)
        prop_expenses = _round2(prop_expenses)
        prop_net = _round2(prop_paid - prop_expenses)

        property_summaries.append(
            {
                "property_id": prop_id,
                "property_name": prop_name,
                "invoices": invoice_docs,
                "payments": payment_docs,
                "expenses": expense_docs,
                "summary": {
                    "total_invoiced": prop_invoiced,
                    "total_paid": prop_paid,
                    "total_expenses": prop_expenses,
                    "net": prop_net,
                },
            }
        )

        grand_invoiced += prop_invoiced
        grand_paid += prop_paid
        grand_expenses += prop_expenses

    grand_invoiced = _round2(grand_invoiced)
    grand_paid = _round2(grand_paid)
    grand_expenses = _round2(grand_expenses)

    return {
        "owner_id": owner_id,
        "period": {"start": str(start_date), "end": str(end_date)},
        "properties": property_summaries,
        "totals": {
            "total_invoiced": grand_invoiced,
            "total_paid": grand_paid,
            "total_expenses": grand_expenses,
            "net": _round2(grand_paid - grand_expenses),
        },
    }
