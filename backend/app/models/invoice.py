from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from enum import Enum


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    PARTIAL = "partial"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"
    WRITE_OFF = "write_off"


class InvoiceLineItem(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float
    amount: float
    account_code: Optional[str] = None
    tax_rate: float = 0.0


class InvoiceDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    invoice_number: str
    owner_id: str
    property_id: str
    billing_period_start: date
    billing_period_end: date
    issue_date: date
    due_date: date
    line_items: List[InvoiceLineItem] = []
    subtotal: float = 0.0
    tax_amount: float = 0.0
    total_amount: float = 0.0
    amount_paid: float = 0.0
    balance_due: float = 0.0
    carried_forward_balance: float = 0.0
    late_fee: float = 0.0
    late_fee_applied_at: Optional[datetime] = None
    status: InvoiceStatus = InvoiceStatus.DRAFT
    notes: Optional[str] = None
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    journal_entry_id: Optional[str] = None
    recurring_schedule_id: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class PaymentDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    invoice_id: str
    owner_id: str
    property_id: str
    amount: float
    payment_date: date
    payment_method: str  # check, ach, wire, cash, credit_card, other
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    journal_entry_id: Optional[str] = None
    recorded_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class RecurringScheduleDB(BaseModel):
    """Drives automatic invoice generation."""
    id: Optional[str] = Field(None, alias="_id")
    owner_id: str
    property_id: str
    name: str
    frequency: str  # monthly | quarterly | annually
    day_of_month: int = 1
    start_date: date
    end_date: Optional[date] = None
    line_items: List[InvoiceLineItem] = []
    auto_send: bool = True
    late_fee_enabled: bool = True
    late_fee_days: int = 10
    late_fee_rate: float = 0.05
    late_fee_flat: Optional[float] = None
    is_active: bool = True
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
