"""
invoice_service.py
------------------
Invoice and billing engine for the Estatio property management platform.

Responsibilities:
  - Create invoices with auto-generated invoice numbers
  - Carry-forward outstanding balances from prior invoices
  - Send invoices and trigger notifications
  - Apply payments and create corresponding journal entries
  - Apply late fees after the grace period
  - Generate recurring invoices from RecurringSchedule documents
  - Void invoices with reversing journal entries

MongoDB collections used:
  invoices              – InvoiceDB
  payments              – PaymentDB
  recurring_schedules   – RecurringScheduleDB
  accounts              – AccountDB (for journal line lookups)
  notifications         – NotificationDB
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.invoice import InvoiceStatus
from app.services.accounting_service import create_journal_entry

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return str(ObjectId())


def _round2(value: float) -> float:
    return round(value, 2)


async def _next_invoice_number(db: AsyncIOMotorDatabase) -> str:
    """Generate INV-{YEAR}-{SEQUENCE:05d}."""
    year = datetime.utcnow().year
    prefix = f"INV-{year}-"
    last = await db.invoices.find_one(
        {"invoice_number": {"$regex": f"^{prefix}"}},
        sort=[("invoice_number", -1)],
    )
    if last:
        try:
            seq = int(last["invoice_number"].split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:05d}"


async def _get_account_by_code(
    db: AsyncIOMotorDatabase, code: str
) -> Optional[Dict[str, Any]]:
    """Look up an account document by its chart-of-accounts code."""
    return await db.accounts.find_one({"code": code})


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
    """Persist an in-app notification document."""
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
# Create invoice
# ---------------------------------------------------------------------------

async def create_invoice(
    db: AsyncIOMotorDatabase,
    invoice_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a new invoice.

    ``invoice_data`` keys:
        owner_id                – str (required)
        property_id             – str (required)
        billing_period_start    – date | ISO str (required)
        billing_period_end      – date | ISO str (required)
        issue_date              – date | ISO str (defaults to today)
        due_date                – date | ISO str (required)
        line_items              – list of:
                                    { description, quantity, unit_price,
                                      amount, account_code?, tax_rate? }
        notes                   – str (optional)
        created_by              – str (user_id, required)
        recurring_schedule_id   – str (optional)

    Behaviour:
      - Auto-generates invoice_number (INV-{YEAR}-{SEQ:05d})
      - Sums subtotal, tax, and total from line_items
      - Carries forward the outstanding balance of the most-recent open invoice
        for the same owner + property
      - Creates an Accounts-Receivable journal entry
      - Returns the persisted invoice document
    """
    logger = log.bind(
        action="create_invoice",
        owner_id=invoice_data.get("owner_id"),
        property_id=invoice_data.get("property_id"),
    )
    logger.info("Creating invoice")

    owner_id = invoice_data["owner_id"]
    property_id = invoice_data["property_id"]
    created_by = invoice_data.get("created_by", "system")
    now = datetime.utcnow()

    # Normalise dates
    def _to_date(val: Any) -> date:
        if isinstance(val, date):
            return val
        return date.fromisoformat(str(val))

    billing_start = _to_date(invoice_data["billing_period_start"])
    billing_end = _to_date(invoice_data["billing_period_end"])
    issue_date = _to_date(invoice_data.get("issue_date", date.today()))
    due_date = _to_date(invoice_data["due_date"])

    # Calculate totals from line items
    line_items = invoice_data.get("line_items", [])
    subtotal = 0.0
    tax_amount = 0.0
    normalised_lines: List[Dict[str, Any]] = []

    for item in line_items:
        qty = float(item.get("quantity", 1.0))
        unit_price = float(item.get("unit_price", 0.0))
        amount = _round2(float(item.get("amount", qty * unit_price)))
        tax_rate = float(item.get("tax_rate", 0.0))
        item_tax = _round2(amount * tax_rate)
        subtotal += amount
        tax_amount += item_tax
        normalised_lines.append(
            {
                "description": item.get("description", ""),
                "quantity": qty,
                "unit_price": unit_price,
                "amount": amount,
                "account_code": item.get("account_code"),
                "tax_rate": tax_rate,
            }
        )

    subtotal = _round2(subtotal)
    tax_amount = _round2(tax_amount)
    total_amount = _round2(subtotal + tax_amount)

    # Carry-forward: find the most-recent open invoice for this owner + property
    carried_forward_balance = 0.0
    prior_invoice = await db.invoices.find_one(
        {
            "owner_id": owner_id,
            "property_id": property_id,
            "status": {"$in": [
                InvoiceStatus.SENT.value,
                InvoiceStatus.VIEWED.value,
                InvoiceStatus.PARTIAL.value,
                InvoiceStatus.OVERDUE.value,
            ]},
        },
        sort=[("created_at", -1)],
    )
    if prior_invoice:
        carried_forward_balance = _round2(
            float(prior_invoice.get("balance_due", 0.0))
        )

    balance_due = _round2(total_amount + carried_forward_balance)
    invoice_number = await _next_invoice_number(db)
    invoice_id = _new_id()

    doc: Dict[str, Any] = {
        "_id": invoice_id,
        "invoice_number": invoice_number,
        "owner_id": owner_id,
        "property_id": property_id,
        "billing_period_start": billing_start.isoformat(),
        "billing_period_end": billing_end.isoformat(),
        "issue_date": issue_date.isoformat(),
        "due_date": due_date.isoformat(),
        "line_items": normalised_lines,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "total_amount": total_amount,
        "amount_paid": 0.0,
        "balance_due": balance_due,
        "carried_forward_balance": carried_forward_balance,
        "late_fee": 0.0,
        "late_fee_applied_at": None,
        "status": InvoiceStatus.DRAFT.value,
        "notes": invoice_data.get("notes"),
        "sent_at": None,
        "viewed_at": None,
        "paid_at": None,
        "journal_entry_id": None,
        "recurring_schedule_id": invoice_data.get("recurring_schedule_id"),
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }

    await db.invoices.insert_one(doc)

    # Create Accounts Receivable journal entry
    # DR: Accounts Receivable  CR: Rental Income (or appropriate revenue account)
    ar_account = await _get_account_by_code(db, "1100")
    revenue_account = await _get_account_by_code(db, "4000")

    if ar_account and revenue_account and total_amount > 0:
        je_lines: List[Dict[str, Any]] = [
            {
                "account_id": str(ar_account["_id"]),
                "account_code": ar_account["code"],
                "account_name": ar_account["name"],
                "debit": total_amount,
                "credit": 0.0,
                "description": f"Invoice {invoice_number}",
                "property_id": property_id,
            },
            {
                "account_id": str(revenue_account["_id"]),
                "account_code": revenue_account["code"],
                "account_name": revenue_account["name"],
                "debit": 0.0,
                "credit": total_amount,
                "description": f"Invoice {invoice_number}",
                "property_id": property_id,
            },
        ]
        try:
            je = await create_journal_entry(
                db,
                {
                    "date": issue_date,
                    "description": f"Invoice {invoice_number} – {property_id}",
                    "entry_type": "invoice",
                    "lines": je_lines,
                    "reference_id": invoice_id,
                    "reference_type": "invoice",
                    "property_id": property_id,
                    "created_by": created_by,
                },
            )
            await db.invoices.update_one(
                {"_id": invoice_id},
                {"$set": {"journal_entry_id": je["_id"], "updated_at": datetime.utcnow()}},
            )
            doc["journal_entry_id"] = je["_id"]
        except Exception as exc:
            logger.error("Failed to create journal entry for invoice", error=str(exc))

    logger.info(
        "Invoice created",
        invoice_id=invoice_id,
        invoice_number=invoice_number,
        total_amount=total_amount,
        carried_forward=carried_forward_balance,
    )
    return doc


# ---------------------------------------------------------------------------
# Send invoice
# ---------------------------------------------------------------------------

async def send_invoice(
    db: AsyncIOMotorDatabase,
    invoice_id: str,
) -> Dict[str, Any]:
    """
    Mark an invoice as sent and trigger an in-app notification to the owner.

    The invoice status must be DRAFT to transition to SENT.
    Raises ValueError if the invoice is not found or already sent/paid/void.
    """
    logger = log.bind(action="send_invoice", invoice_id=invoice_id)

    invoice = await db.invoices.find_one({"_id": invoice_id})
    if not invoice:
        raise ValueError(f"Invoice {invoice_id} not found")

    current_status = invoice.get("status", "")
    if current_status not in (InvoiceStatus.DRAFT.value,):
        raise ValueError(
            f"Cannot send invoice in status '{current_status}'. "
            "Only DRAFT invoices can be sent."
        )

    now = datetime.utcnow()
    await db.invoices.update_one(
        {"_id": invoice_id},
        {
            "$set": {
                "status": InvoiceStatus.SENT.value,
                "sent_at": now,
                "updated_at": now,
            }
        },
    )

    # Trigger notification to the owner
    await _send_notification(
        db,
        user_id=invoice["owner_id"],
        notif_type="invoice_created",
        title=f"Invoice {invoice['invoice_number']} Sent",
        message=(
            f"Your invoice {invoice['invoice_number']} for "
            f"${invoice.get('total_amount', 0):.2f} is due on "
            f"{invoice.get('due_date', 'N/A')}."
        ),
        data={
            "invoice_id": invoice_id,
            "invoice_number": invoice["invoice_number"],
            "total_amount": invoice.get("total_amount", 0),
            "due_date": str(invoice.get("due_date", "")),
        },
        action_url=f"/invoices/{invoice_id}",
        priority="normal",
    )

    logger.info(
        "Invoice sent",
        invoice_number=invoice["invoice_number"],
        owner_id=invoice["owner_id"],
    )

    invoice["status"] = InvoiceStatus.SENT.value
    invoice["sent_at"] = now
    return invoice


# ---------------------------------------------------------------------------
# Apply payment
# ---------------------------------------------------------------------------

async def apply_payment(
    db: AsyncIOMotorDatabase,
    invoice_id: str,
    payment_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Record a payment against an invoice.

    ``payment_data`` keys:
        amount          – float (required)
        payment_date    – date | ISO str (defaults to today)
        payment_method  – str (check | ach | wire | cash | credit_card | other)
        reference_number– str (optional)
        recorded_by     – str (user_id, required)
        notes           – str (optional)

    Effects:
      - Creates a PaymentDB document
      - Reduces balance_due on the invoice
      - Creates a cash-receipt journal entry (DR Cash, CR AR)
      - Marks invoice PAID if balance_due reaches zero
      - Sends a payment-received notification to the owner
    """
    logger = log.bind(action="apply_payment", invoice_id=invoice_id)

    invoice = await db.invoices.find_one({"_id": invoice_id})
    if not invoice:
        raise ValueError(f"Invoice {invoice_id} not found")

    if invoice.get("status") in (InvoiceStatus.VOID.value, InvoiceStatus.WRITE_OFF.value):
        raise ValueError(
            f"Cannot apply payment to a {invoice['status']} invoice."
        )

    def _to_date(val: Any) -> date:
        if isinstance(val, date):
            return val
        return date.fromisoformat(str(val))

    payment_amount = _round2(float(payment_data["amount"]))
    payment_date = _to_date(payment_data.get("payment_date", date.today()))
    recorded_by = payment_data.get("recorded_by", "system")

    current_balance = _round2(float(invoice.get("balance_due", 0.0)))
    new_balance = _round2(current_balance - payment_amount)
    new_amount_paid = _round2(float(invoice.get("amount_paid", 0.0)) + payment_amount)

    # Determine new status
    now = datetime.utcnow()
    if new_balance <= 0.0:
        new_status = InvoiceStatus.PAID.value
        paid_at = now
    elif new_amount_paid > 0:
        new_status = InvoiceStatus.PARTIAL.value
        paid_at = None
    else:
        new_status = invoice.get("status", InvoiceStatus.SENT.value)
        paid_at = None

    # Persist payment record
    payment_id = _new_id()
    payment_doc: Dict[str, Any] = {
        "_id": payment_id,
        "invoice_id": invoice_id,
        "owner_id": invoice["owner_id"],
        "property_id": invoice["property_id"],
        "amount": payment_amount,
        "payment_date": payment_date.isoformat(),
        "payment_method": payment_data.get("payment_method", "other"),
        "reference_number": payment_data.get("reference_number"),
        "notes": payment_data.get("notes"),
        "journal_entry_id": None,
        "recorded_by": recorded_by,
        "created_at": now,
    }
    await db.payments.insert_one(payment_doc)

    # Update invoice
    update_fields: Dict[str, Any] = {
        "balance_due": max(new_balance, 0.0),
        "amount_paid": new_amount_paid,
        "status": new_status,
        "updated_at": now,
    }
    if paid_at:
        update_fields["paid_at"] = paid_at

    await db.invoices.update_one({"_id": invoice_id}, {"$set": update_fields})

    # Create cash receipt journal entry: DR Cash, CR Accounts Receivable
    cash_account = await _get_account_by_code(db, "1010")
    ar_account = await _get_account_by_code(db, "1100")

    if cash_account and ar_account:
        je_lines: List[Dict[str, Any]] = [
            {
                "account_id": str(cash_account["_id"]),
                "account_code": cash_account["code"],
                "account_name": cash_account["name"],
                "debit": payment_amount,
                "credit": 0.0,
                "description": f"Payment for {invoice['invoice_number']}",
                "property_id": invoice["property_id"],
            },
            {
                "account_id": str(ar_account["_id"]),
                "account_code": ar_account["code"],
                "account_name": ar_account["name"],
                "debit": 0.0,
                "credit": payment_amount,
                "description": f"Payment for {invoice['invoice_number']}",
                "property_id": invoice["property_id"],
            },
        ]
        try:
            je = await create_journal_entry(
                db,
                {
                    "date": payment_date,
                    "description": (
                        f"Payment received – {invoice['invoice_number']} "
                        f"(${payment_amount:.2f})"
                    ),
                    "entry_type": "payment",
                    "lines": je_lines,
                    "reference_id": payment_id,
                    "reference_type": "payment",
                    "property_id": invoice["property_id"],
                    "created_by": recorded_by,
                },
            )
            await db.payments.update_one(
                {"_id": payment_id},
                {"$set": {"journal_entry_id": je["_id"]}},
            )
        except Exception as exc:
            logger.error("Failed to create journal entry for payment", error=str(exc))

    # Notification
    await _send_notification(
        db,
        user_id=invoice["owner_id"],
        notif_type="payment_received",
        title="Payment Received",
        message=(
            f"A payment of ${payment_amount:.2f} has been applied to invoice "
            f"{invoice['invoice_number']}. "
            f"Remaining balance: ${max(new_balance, 0.0):.2f}."
        ),
        data={
            "invoice_id": invoice_id,
            "payment_id": payment_id,
            "amount": payment_amount,
            "balance_due": max(new_balance, 0.0),
        },
        action_url=f"/invoices/{invoice_id}",
        priority="normal",
    )

    logger.info(
        "Payment applied",
        payment_id=payment_id,
        amount=payment_amount,
        new_balance=max(new_balance, 0.0),
        new_status=new_status,
    )

    payment_doc["journal_entry_id"] = payment_doc.get("journal_entry_id")
    return {
        "payment": payment_doc,
        "invoice": {
            "invoice_id": invoice_id,
            "invoice_number": invoice["invoice_number"],
            "amount_paid": new_amount_paid,
            "balance_due": max(new_balance, 0.0),
            "status": new_status,
        },
    }


# ---------------------------------------------------------------------------
# Apply late fee
# ---------------------------------------------------------------------------

async def apply_late_fee(
    db: AsyncIOMotorDatabase,
    invoice_id: str,
) -> Dict[str, Any]:
    """
    Apply a late fee to the invoice if it is past due_date + grace period.

    The grace period and rate are sourced from the linked RecurringSchedule
    (if any). Defaults: 10-day grace period, 5% of balance_due.

    A late fee can only be applied once per invoice.
    Returns the updated invoice document.
    """
    logger = log.bind(action="apply_late_fee", invoice_id=invoice_id)

    invoice = await db.invoices.find_one({"_id": invoice_id})
    if not invoice:
        raise ValueError(f"Invoice {invoice_id} not found")

    if invoice.get("late_fee_applied_at"):
        logger.info("Late fee already applied, skipping")
        return invoice

    status = invoice.get("status", "")
    if status in (InvoiceStatus.PAID.value, InvoiceStatus.VOID.value, InvoiceStatus.WRITE_OFF.value):
        return invoice

    # Determine grace period and rate from linked schedule
    grace_days = 10
    late_fee_rate = 0.05
    late_fee_flat: Optional[float] = None

    schedule_id = invoice.get("recurring_schedule_id")
    if schedule_id:
        sched = await db.recurring_schedules.find_one({"_id": schedule_id})
        if sched:
            grace_days = int(sched.get("late_fee_days", grace_days))
            late_fee_rate = float(sched.get("late_fee_rate", late_fee_rate))
            late_fee_flat = sched.get("late_fee_flat")

    due_date = date.fromisoformat(str(invoice.get("due_date", date.today())))
    deadline = due_date + timedelta(days=grace_days)

    if date.today() <= deadline:
        logger.info(
            "Late fee not yet applicable",
            due_date=str(due_date),
            deadline=str(deadline),
        )
        return invoice

    balance_due = _round2(float(invoice.get("balance_due", 0.0)))
    if balance_due <= 0:
        return invoice

    if late_fee_flat is not None:
        late_fee = _round2(float(late_fee_flat))
    else:
        late_fee = _round2(balance_due * late_fee_rate)

    if late_fee <= 0:
        return invoice

    new_balance_due = _round2(balance_due + late_fee)
    now = datetime.utcnow()

    await db.invoices.update_one(
        {"_id": invoice_id},
        {
            "$set": {
                "late_fee": late_fee,
                "late_fee_applied_at": now,
                "balance_due": new_balance_due,
                "status": InvoiceStatus.OVERDUE.value,
                "updated_at": now,
            }
        },
    )

    # Journal entry: DR AR, CR Late Fee Income
    ar_account = await _get_account_by_code(db, "1100")
    late_fee_account = await _get_account_by_code(db, "4200")

    if ar_account and late_fee_account:
        try:
            await create_journal_entry(
                db,
                {
                    "date": date.today(),
                    "description": (
                        f"Late fee – {invoice['invoice_number']} (${late_fee:.2f})"
                    ),
                    "entry_type": "adjustment",
                    "lines": [
                        {
                            "account_id": str(ar_account["_id"]),
                            "account_code": ar_account["code"],
                            "account_name": ar_account["name"],
                            "debit": late_fee,
                            "credit": 0.0,
                            "description": f"Late fee – {invoice['invoice_number']}",
                            "property_id": invoice.get("property_id"),
                        },
                        {
                            "account_id": str(late_fee_account["_id"]),
                            "account_code": late_fee_account["code"],
                            "account_name": late_fee_account["name"],
                            "debit": 0.0,
                            "credit": late_fee,
                            "description": f"Late fee – {invoice['invoice_number']}",
                            "property_id": invoice.get("property_id"),
                        },
                    ],
                    "reference_id": invoice_id,
                    "reference_type": "invoice",
                    "property_id": invoice.get("property_id"),
                    "created_by": "system",
                },
            )
        except Exception as exc:
            logger.error("Failed to create late-fee journal entry", error=str(exc))

    # Notify owner
    await _send_notification(
        db,
        user_id=invoice["owner_id"],
        notif_type="invoice_overdue",
        title=f"Late Fee Applied – {invoice['invoice_number']}",
        message=(
            f"A late fee of ${late_fee:.2f} has been added to invoice "
            f"{invoice['invoice_number']}. New balance: ${new_balance_due:.2f}."
        ),
        data={
            "invoice_id": invoice_id,
            "late_fee": late_fee,
            "balance_due": new_balance_due,
        },
        action_url=f"/invoices/{invoice_id}",
        priority="high",
    )

    logger.info(
        "Late fee applied",
        invoice_number=invoice["invoice_number"],
        late_fee=late_fee,
        new_balance_due=new_balance_due,
    )

    invoice["late_fee"] = late_fee
    invoice["balance_due"] = new_balance_due
    invoice["status"] = InvoiceStatus.OVERDUE.value
    return invoice


# ---------------------------------------------------------------------------
# Generate recurring invoices
# ---------------------------------------------------------------------------

async def generate_recurring_invoices(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Scan all active RecurringSchedule documents and generate invoices that are
    now due.

    A schedule's ``next_run_at`` is compared against today's date. When due:
      1. An invoice is created for the schedule's owner + property.
      2. ``last_run_at`` and ``next_run_at`` are rolled forward.
      3. If ``auto_send`` is True, the invoice is automatically sent.

    Returns a summary: { "generated": int, "errors": list }
    """
    logger = log.bind(action="generate_recurring_invoices")
    logger.info("Running recurring invoice generation")

    today = date.today()
    generated = 0
    errors: List[Dict[str, Any]] = []

    async for sched in db.recurring_schedules.find(
        {
            "is_active": True,
            "next_run_at": {"$lte": today.isoformat()},
        }
    ):
        sched_id = str(sched["_id"])
        owner_id = sched.get("owner_id", "")
        property_id = sched.get("property_id", "")

        try:
            # Build due_date based on frequency
            frequency = sched.get("frequency", "monthly")
            issue_date = today
            if frequency == "monthly":
                # due date = first of next month
                if today.month == 12:
                    due_date = date(today.year + 1, 1, sched.get("day_of_month", 1))
                    next_run = date(today.year + 1, 1, sched.get("day_of_month", 1))
                else:
                    due_date = date(today.year, today.month + 1, sched.get("day_of_month", 1))
                    next_run = due_date
            elif frequency == "quarterly":
                # Add 3 months
                month = today.month + 3
                year = today.year + (month - 1) // 12
                month = ((month - 1) % 12) + 1
                due_date = date(year, month, sched.get("day_of_month", 1))
                next_run = due_date
            elif frequency == "annually":
                due_date = date(today.year + 1, today.month, sched.get("day_of_month", 1))
                next_run = due_date
            else:
                due_date = today + timedelta(days=30)
                next_run = due_date

            # Check schedule end date
            end_date = sched.get("end_date")
            if end_date and date.fromisoformat(str(end_date)) < today:
                await db.recurring_schedules.update_one(
                    {"_id": sched["_id"]}, {"$set": {"is_active": False}}
                )
                continue

            billing_start = today.replace(day=1)
            # billing_end = last day of current month
            if today.month == 12:
                billing_end = date(today.year + 1, 1, 1) - timedelta(days=1)
            else:
                billing_end = date(today.year, today.month + 1, 1) - timedelta(days=1)

            invoice = await create_invoice(
                db,
                {
                    "owner_id": owner_id,
                    "property_id": property_id,
                    "billing_period_start": billing_start,
                    "billing_period_end": billing_end,
                    "issue_date": issue_date,
                    "due_date": due_date,
                    "line_items": sched.get("line_items", []),
                    "created_by": "system",
                    "recurring_schedule_id": sched_id,
                },
            )

            # Roll forward schedule
            await db.recurring_schedules.update_one(
                {"_id": sched["_id"]},
                {
                    "$set": {
                        "last_run_at": datetime.utcnow(),
                        "next_run_at": next_run.isoformat(),
                    }
                },
            )

            if sched.get("auto_send", True):
                await send_invoice(db, invoice["_id"])

            generated += 1
            logger.info(
                "Recurring invoice generated",
                invoice_number=invoice.get("invoice_number"),
                owner_id=owner_id,
                property_id=property_id,
            )

        except Exception as exc:
            logger.error(
                "Error generating recurring invoice",
                schedule_id=sched_id,
                owner_id=owner_id,
                property_id=property_id,
                error=str(exc),
            )
            errors.append({"schedule_id": sched_id, "error": str(exc)})

    logger.info("Recurring invoice generation complete", generated=generated, errors=len(errors))
    return {"generated": generated, "errors": errors}


# ---------------------------------------------------------------------------
# Owner balance
# ---------------------------------------------------------------------------

async def get_owner_balance(
    db: AsyncIOMotorDatabase,
    owner_id: str,
) -> Dict[str, Any]:
    """
    Return the sum of all outstanding invoice balances for an owner.

    Returns:
        {
            "owner_id": ...,
            "total_outstanding": ...,
            "by_status": {
                "sent": ...,
                "partial": ...,
                "overdue": ...,
            },
            "invoice_count": ...,
        }
    """
    logger = log.bind(action="get_owner_balance", owner_id=owner_id)
    logger.info("Calculating owner balance")

    pipeline = [
        {
            "$match": {
                "owner_id": owner_id,
                "status": {
                    "$in": [
                        InvoiceStatus.SENT.value,
                        InvoiceStatus.VIEWED.value,
                        InvoiceStatus.PARTIAL.value,
                        InvoiceStatus.OVERDUE.value,
                    ]
                },
            }
        },
        {
            "$group": {
                "_id": "$status",
                "total_balance": {"$sum": "$balance_due"},
                "count": {"$sum": 1},
            }
        },
    ]

    by_status: Dict[str, float] = {}
    invoice_count = 0
    async for row in db.invoices.aggregate(pipeline):
        by_status[row["_id"]] = _round2(row["total_balance"])
        invoice_count += row["count"]

    total_outstanding = _round2(sum(by_status.values()))

    return {
        "owner_id": owner_id,
        "total_outstanding": total_outstanding,
        "by_status": by_status,
        "invoice_count": invoice_count,
    }


# ---------------------------------------------------------------------------
# Void invoice
# ---------------------------------------------------------------------------

async def void_invoice(
    db: AsyncIOMotorDatabase,
    invoice_id: str,
    reason: str,
) -> Dict[str, Any]:
    """
    Void an invoice and create a reversing journal entry.

    An invoice can be voided from any non-void status.
    All journal amounts are reversed (DR ↔ CR swapped).

    Returns the updated invoice document.
    """
    logger = log.bind(action="void_invoice", invoice_id=invoice_id)

    invoice = await db.invoices.find_one({"_id": invoice_id})
    if not invoice:
        raise ValueError(f"Invoice {invoice_id} not found")

    if invoice.get("status") == InvoiceStatus.VOID.value:
        raise ValueError(f"Invoice {invoice_id} is already voided.")

    now = datetime.utcnow()
    total_amount = _round2(float(invoice.get("total_amount", 0.0)))

    # Reverse the original AR entry: DR Revenue Income, CR AR
    ar_account = await _get_account_by_code(db, "1100")
    revenue_account = await _get_account_by_code(db, "4000")

    if ar_account and revenue_account and total_amount > 0:
        try:
            await create_journal_entry(
                db,
                {
                    "date": date.today(),
                    "description": (
                        f"VOID – {invoice['invoice_number']}: {reason}"
                    ),
                    "entry_type": "adjustment",
                    "lines": [
                        {
                            "account_id": str(revenue_account["_id"]),
                            "account_code": revenue_account["code"],
                            "account_name": revenue_account["name"],
                            "debit": total_amount,
                            "credit": 0.0,
                            "description": f"Reversal – {invoice['invoice_number']}",
                            "property_id": invoice.get("property_id"),
                        },
                        {
                            "account_id": str(ar_account["_id"]),
                            "account_code": ar_account["code"],
                            "account_name": ar_account["name"],
                            "debit": 0.0,
                            "credit": total_amount,
                            "description": f"Reversal – {invoice['invoice_number']}",
                            "property_id": invoice.get("property_id"),
                        },
                    ],
                    "reference_id": invoice_id,
                    "reference_type": "invoice_void",
                    "property_id": invoice.get("property_id"),
                    "created_by": "system",
                },
            )
        except Exception as exc:
            logger.error("Failed to create reversing journal entry", error=str(exc))

    await db.invoices.update_one(
        {"_id": invoice_id},
        {
            "$set": {
                "status": InvoiceStatus.VOID.value,
                "balance_due": 0.0,
                "void_reason": reason,
                "updated_at": now,
            }
        },
    )

    logger.info(
        "Invoice voided",
        invoice_number=invoice.get("invoice_number"),
        reason=reason,
    )

    invoice["status"] = InvoiceStatus.VOID.value
    invoice["balance_due"] = 0.0
    invoice["void_reason"] = reason
    return invoice
