from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class VendorStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PREFERRED = "preferred"


class VendorDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    name: str
    company_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: str
    address: Optional[Dict[str, str]] = None
    trade_specialties: List[str] = []
    license_number: Optional[str] = None
    license_expiry: Optional[date] = None
    insurance_provider: Optional[str] = None
    insurance_policy_number: Optional[str] = None
    insurance_expiry: Optional[date] = None
    w9_on_file: bool = False
    w9_document_id: Optional[str] = None
    status: VendorStatus = VendorStatus.ACTIVE
    rating: Optional[float] = None
    total_jobs: int = 0
    total_spend: float = 0.0
    bank_name: Optional[str] = None
    bank_routing: Optional[str] = None
    bank_account: Optional[str] = None
    payment_terms: str = "net30"
    notes: Optional[str] = None
    portal_user_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class VendorInvoiceDB(BaseModel):
    """AP: Invoice FROM a vendor for work done."""

    id: Optional[str] = Field(None, alias="_id")
    vendor_id: str
    work_order_id: Optional[str] = None
    property_id: str
    invoice_number: str
    invoice_date: date
    due_date: date
    amount: float
    amount_paid: float = 0.0
    status: str = "pending"  # pending | approved | paid | disputed
    line_items: List[Dict[str, Any]] = []
    document_id: Optional[str] = None
    journal_entry_id: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
