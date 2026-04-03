from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class NotificationType(str, Enum):
    INVOICE_CREATED = "invoice_created"
    INVOICE_DUE = "invoice_due"
    INVOICE_OVERDUE = "invoice_overdue"
    PAYMENT_RECEIVED = "payment_received"
    MAINTENANCE_SUBMITTED = "maintenance_submitted"
    MAINTENANCE_UPDATED = "maintenance_updated"
    MAINTENANCE_COMPLETED = "maintenance_completed"
    LEASE_EXPIRING = "lease_expiring"
    LEASE_EXPIRED = "lease_expired"
    HOA_DEADLINE = "hoa_deadline"
    HOA_VIOLATION = "hoa_violation"
    DOCUMENT_UPLOADED = "document_uploaded"
    VENDOR_ESTIMATE = "vendor_estimate"
    SYSTEM = "system"
    AI_INSIGHT = "ai_insight"


class NotificationDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    user_id: str
    type: NotificationType
    title: str
    message: str
    data: Optional[Dict[str, Any]] = None
    read: bool = False
    read_at: Optional[datetime] = None
    action_url: Optional[str] = None
    priority: str = "normal"  # low | normal | high | urgent
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
