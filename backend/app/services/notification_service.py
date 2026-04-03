"""
notification_service.py
-----------------------
Notification service for the Estatio property management platform.

Responsibilities:
  - Create in-app notifications stored in MongoDB
  - Mark notifications as read (individual and bulk)
  - Query and count unread notifications per user
  - Send email notifications via SendGrid (with graceful fallback to logging)
  - Domain-specific helpers for invoice, payment, and work-order events

MongoDB collection: notifications (NotificationDB)
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.models.notification import NotificationDB, NotificationType

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SendGrid client (lazy, optional)
# ---------------------------------------------------------------------------

_sendgrid_available = False

try:
    if settings.SENDGRID_API_KEY:
        from sendgrid import SendGridAPIClient  # type: ignore
        from sendgrid.helpers.mail import Mail  # type: ignore

        _sendgrid_available = True
        log.info("SendGrid client available")
    else:
        log.info("SENDGRID_API_KEY not set — email notifications will be logged only")
except ImportError:
    log.warning("sendgrid package not installed — email notifications will be logged only")


# ---------------------------------------------------------------------------
# Internal MongoDB helpers
# ---------------------------------------------------------------------------

def _notif_from_mongo(raw: Dict[str, Any]) -> NotificationDB:
    """Convert a raw MongoDB dict to a NotificationDB instance."""
    raw["_id"] = str(raw["_id"])
    return NotificationDB(**raw)


# ---------------------------------------------------------------------------
# Core notification CRUD
# ---------------------------------------------------------------------------

async def create_notification(
    db: AsyncIOMotorDatabase,
    user_id: str,
    type: NotificationType,
    title: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    action_url: Optional[str] = None,
    priority: str = "normal",
) -> NotificationDB:
    """
    Create and persist a new in-app notification.

    Parameters:
        db         – Motor async database handle
        user_id    – Target user ID
        type       – NotificationType enum value
        title      – Short notification title
        message    – Full notification message body
        data       – Optional arbitrary payload dict (e.g. invoice_id, amount)
        action_url – Optional deep-link URL for the notification CTA
        priority   – "low" | "normal" | "high" | "urgent"

    Returns:
        The persisted NotificationDB instance.
    """
    logger = log.bind(action="create_notification", user_id=user_id, type=type)

    notif_id = str(ObjectId())
    now = datetime.utcnow()

    notif = NotificationDB(
        _id=notif_id,
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        data=data or {},
        action_url=action_url,
        priority=priority,
        read=False,
        read_at=None,
        created_at=now,
    )

    doc_dict = notif.model_dump(by_alias=False)
    doc_dict["_id"] = ObjectId(notif_id)
    await db.notifications.insert_one(doc_dict)

    logger.info("Notification created", notification_id=notif_id, priority=priority)
    return notif


async def mark_read(
    db: AsyncIOMotorDatabase,
    notification_id: str,
    user_id: str,
) -> bool:
    """
    Mark a single notification as read.

    Verifies that the notification belongs to ``user_id`` before updating.

    Returns:
        True if updated, False if not found or already read.
    """
    now = datetime.utcnow()
    result = await db.notifications.update_one(
        {
            "_id": ObjectId(notification_id),
            "user_id": user_id,
            "read": False,
        },
        {"$set": {"read": True, "read_at": now}},
    )
    updated = result.modified_count > 0
    log.info(
        "mark_read",
        notification_id=notification_id,
        user_id=user_id,
        updated=updated,
    )
    return updated


async def mark_all_read(
    db: AsyncIOMotorDatabase,
    user_id: str,
) -> int:
    """
    Mark all unread notifications for a user as read.

    Returns:
        Number of notifications that were updated.
    """
    now = datetime.utcnow()
    result = await db.notifications.update_many(
        {"user_id": user_id, "read": False},
        {"$set": {"read": True, "read_at": now}},
    )
    count = result.modified_count
    log.info("mark_all_read", user_id=user_id, updated=count)
    return count


async def get_notifications(
    db: AsyncIOMotorDatabase,
    user_id: str,
    unread_only: bool = False,
    skip: int = 0,
    limit: int = 50,
) -> List[NotificationDB]:
    """
    Retrieve notifications for a user, most recent first.

    Parameters:
        db          – Motor async database handle
        user_id     – Target user ID
        unread_only – If True, return only unread notifications
        skip        – Pagination offset
        limit       – Maximum records to return

    Returns:
        List of NotificationDB instances.
    """
    query: Dict[str, Any] = {"user_id": user_id}
    if unread_only:
        query["read"] = False

    cursor = (
        db.notifications.find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )

    results: List[NotificationDB] = []
    async for raw in cursor:
        try:
            results.append(_notif_from_mongo(raw))
        except Exception as exc:
            log.warning("Failed to parse notification", error=str(exc))
    return results


async def get_unread_count(
    db: AsyncIOMotorDatabase,
    user_id: str,
) -> int:
    """
    Return the count of unread notifications for a user.
    """
    count = await db.notifications.count_documents(
        {"user_id": user_id, "read": False}
    )
    return count


async def delete_notification(
    db: AsyncIOMotorDatabase,
    notification_id: str,
    user_id: str,
) -> bool:
    """
    Permanently delete a notification.

    Verifies ownership before deleting.

    Returns:
        True if deleted, False if not found.
    """
    result = await db.notifications.delete_one(
        {"_id": ObjectId(notification_id), "user_id": user_id}
    )
    deleted = result.deleted_count > 0
    log.info(
        "delete_notification",
        notification_id=notification_id,
        user_id=user_id,
        deleted=deleted,
    )
    return deleted


# ---------------------------------------------------------------------------
# Email notifications
# ---------------------------------------------------------------------------

async def send_email_notification(
    to_email: str,
    subject: str,
    html_body: str,
) -> bool:
    """
    Send an HTML email notification via SendGrid.

    Falls back to structured logging when SendGrid is not configured or
    the package is not installed.

    Parameters:
        to_email  – Recipient email address
        subject   – Email subject line
        html_body – HTML email body content

    Returns:
        True on success (or simulated success in fallback mode), False on error.
    """
    if not _sendgrid_available or not settings.SENDGRID_API_KEY:
        log.info(
            "Email notification (SendGrid not configured)",
            to=to_email,
            subject=subject,
            body_length=len(html_body),
        )
        return True  # Treat as success in dev/logging mode

    try:
        from sendgrid import SendGridAPIClient  # type: ignore
        from sendgrid.helpers.mail import Mail  # type: ignore

        message = Mail(
            from_email=settings.FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=html_body,
        )

        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        # Run sync SendGrid call in executor to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, sg.send, message)

        success = response.status_code in (200, 202)
        log.info(
            "Email sent via SendGrid",
            to=to_email,
            subject=subject,
            status_code=response.status_code,
        )
        return success
    except Exception as exc:
        log.error("SendGrid email failed", to=to_email, subject=subject, error=str(exc))
        return False


# ---------------------------------------------------------------------------
# Email template helpers
# ---------------------------------------------------------------------------

def _invoice_created_html(invoice_number: str, amount: float, due_date: str) -> str:
    return f"""
<html><body>
<h2>New Invoice Created</h2>
<p>Invoice <strong>{invoice_number}</strong> has been created for
<strong>${amount:,.2f}</strong>, due on <strong>{due_date}</strong>.</p>
<p>Please log in to Estatio to review and pay your invoice.</p>
</body></html>
"""


def _payment_received_html(amount: float, invoice_number: str, payment_date: str) -> str:
    return f"""
<html><body>
<h2>Payment Received</h2>
<p>We received a payment of <strong>${amount:,.2f}</strong>
for invoice <strong>{invoice_number}</strong> on <strong>{payment_date}</strong>.</p>
<p>Thank you for your prompt payment.</p>
</body></html>
"""


def _work_order_update_html(work_order_number: str, message: str) -> str:
    return f"""
<html><body>
<h2>Work Order Update</h2>
<p>There is an update for work order <strong>{work_order_number}</strong>:</p>
<blockquote>{message}</blockquote>
<p>Please log in to Estatio to view full details.</p>
</body></html>
"""


# ---------------------------------------------------------------------------
# Domain-specific notification helpers
# ---------------------------------------------------------------------------

async def notify_invoice_created(
    db: AsyncIOMotorDatabase,
    invoice: Any,
) -> None:
    """
    Send an in-app notification (and optionally email) to the invoice owner
    when a new invoice is created.

    Parameters:
        db      – Motor async database handle
        invoice – InvoiceDB instance (or dict) with at minimum:
                  owner_id, invoice_number, total_amount, due_date
    """
    # Support both dict and model instances
    if hasattr(invoice, "model_dump"):
        inv = invoice.model_dump()
    elif isinstance(invoice, dict):
        inv = invoice
    else:
        inv = vars(invoice)

    owner_id = str(inv.get("owner_id", ""))
    invoice_number = inv.get("invoice_number", "N/A")
    total_amount = float(inv.get("total_amount", 0.0))
    due_date = str(inv.get("due_date", ""))
    property_id = str(inv.get("property_id", ""))

    await create_notification(
        db=db,
        user_id=owner_id,
        type=NotificationType.INVOICE_CREATED,
        title="New Invoice Generated",
        message=(
            f"Invoice {invoice_number} for ${total_amount:,.2f} "
            f"has been created and is due on {due_date}."
        ),
        data={
            "invoice_number": invoice_number,
            "total_amount": total_amount,
            "due_date": due_date,
            "property_id": property_id,
        },
        action_url=f"/invoices/{inv.get('id') or inv.get('_id', '')}",
        priority="normal",
    )

    # Fetch owner email if present and send email notification
    try:
        owner = await db.users.find_one({"_id": ObjectId(owner_id)})
        if owner and owner.get("email"):
            html = _invoice_created_html(invoice_number, total_amount, due_date)
            asyncio.create_task(
                send_email_notification(
                    to_email=owner["email"],
                    subject=f"Invoice {invoice_number} — ${total_amount:,.2f} due {due_date}",
                    html_body=html,
                )
            )
    except Exception as exc:
        log.warning("notify_invoice_created email step failed", error=str(exc))


async def notify_payment_received(
    db: AsyncIOMotorDatabase,
    payment: Any,
    invoice: Any,
) -> None:
    """
    Notify the invoice owner when a payment is recorded.

    Parameters:
        db      – Motor async database handle
        payment – PaymentDB instance or dict with: owner_id, amount, payment_date
        invoice – InvoiceDB instance or dict with: invoice_number, owner_id
    """
    if hasattr(payment, "model_dump"):
        pmt = payment.model_dump()
    elif isinstance(payment, dict):
        pmt = payment
    else:
        pmt = vars(payment)

    if hasattr(invoice, "model_dump"):
        inv = invoice.model_dump()
    elif isinstance(invoice, dict):
        inv = invoice
    else:
        inv = vars(invoice)

    owner_id = str(pmt.get("owner_id") or inv.get("owner_id", ""))
    amount = float(pmt.get("amount", 0.0))
    payment_date = str(pmt.get("payment_date", ""))
    invoice_number = inv.get("invoice_number", "N/A")
    property_id = str(pmt.get("property_id") or inv.get("property_id", ""))

    await create_notification(
        db=db,
        user_id=owner_id,
        type=NotificationType.PAYMENT_RECEIVED,
        title="Payment Received",
        message=(
            f"A payment of ${amount:,.2f} was received for invoice "
            f"{invoice_number} on {payment_date}."
        ),
        data={
            "amount": amount,
            "payment_date": payment_date,
            "invoice_number": invoice_number,
            "property_id": property_id,
        },
        action_url=f"/invoices/{inv.get('id') or inv.get('_id', '')}",
        priority="normal",
    )

    try:
        owner = await db.users.find_one({"_id": ObjectId(owner_id)})
        if owner and owner.get("email"):
            html = _payment_received_html(amount, invoice_number, payment_date)
            asyncio.create_task(
                send_email_notification(
                    to_email=owner["email"],
                    subject=f"Payment Confirmed — ${amount:,.2f} for {invoice_number}",
                    html_body=html,
                )
            )
    except Exception as exc:
        log.warning("notify_payment_received email step failed", error=str(exc))


async def notify_work_order_update(
    db: AsyncIOMotorDatabase,
    work_order: Any,
    message: str,
) -> None:
    """
    Notify the relevant parties when a work order status changes.

    Notifies the property owner. If the work order was reported by a tenant,
    also creates a notification for the tenant.

    Parameters:
        db         – Motor async database handle
        work_order – WorkOrderDB instance or dict
        message    – Human-readable status update message
    """
    if hasattr(work_order, "model_dump"):
        wo = work_order.model_dump()
    elif isinstance(work_order, dict):
        wo = work_order
    else:
        wo = vars(work_order)

    wo_number = wo.get("work_order_number", "N/A")
    property_id = str(wo.get("property_id", ""))
    status = wo.get("status", "")
    wo_id = str(wo.get("id") or wo.get("_id", ""))

    # Determine notification type from status
    if status == "completed":
        notif_type = NotificationType.MAINTENANCE_COMPLETED
        priority = "normal"
    elif status in ("submitted", "triaged"):
        notif_type = NotificationType.MAINTENANCE_SUBMITTED
        priority = "normal"
    else:
        notif_type = NotificationType.MAINTENANCE_UPDATED
        priority = "normal"

    if wo.get("priority") == "emergency":
        priority = "urgent"

    # Notify owner via ownership lookup
    try:
        async for ownership in db.ownerships.find({"property_id": property_id}):
            owner_id = str(ownership.get("owner_id", ""))
            if owner_id:
                await create_notification(
                    db=db,
                    user_id=owner_id,
                    type=notif_type,
                    title=f"Work Order Update — {wo_number}",
                    message=message,
                    data={
                        "work_order_number": wo_number,
                        "property_id": property_id,
                        "status": status,
                    },
                    action_url=f"/maintenance/{wo_id}",
                    priority=priority,
                )

                # Email notification for emergency or completion
                if priority in ("urgent", "high") or status == "completed":
                    try:
                        owner = await db.users.find_one({"_id": ObjectId(owner_id)})
                        if owner and owner.get("email"):
                            html = _work_order_update_html(wo_number, message)
                            asyncio.create_task(
                                send_email_notification(
                                    to_email=owner["email"],
                                    subject=f"Work Order {wo_number} — {status.replace('_', ' ').title()}",
                                    html_body=html,
                                )
                            )
                    except Exception as exc:
                        log.warning("notify_work_order_update owner email failed", error=str(exc))
    except Exception as exc:
        log.warning("notify_work_order_update ownership lookup failed", error=str(exc))

    # Also notify the tenant if reported_by_type is "tenant"
    if wo.get("reported_by_type") == "tenant" and wo.get("reported_by"):
        tenant_user_id = str(wo["reported_by"])
        try:
            await create_notification(
                db=db,
                user_id=tenant_user_id,
                type=notif_type,
                title=f"Maintenance Update — {wo_number}",
                message=message,
                data={
                    "work_order_number": wo_number,
                    "property_id": property_id,
                    "status": status,
                },
                action_url=f"/maintenance/{wo_id}",
                priority=priority,
            )
        except Exception as exc:
            log.warning("notify_work_order_update tenant notify failed", error=str(exc))
