from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class WorkOrderPriority(str, Enum):
    EMERGENCY = "emergency"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class WorkOrderStatus(str, Enum):
    SUBMITTED = "submitted"
    TRIAGED = "triaged"
    ESTIMATE_REQUESTED = "estimate_requested"
    ESTIMATE_RECEIVED = "estimate_received"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    INVOICED = "invoiced"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class WorkOrderCategory(str, Enum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    HVAC = "hvac"
    ROOFING = "roofing"
    APPLIANCE = "appliance"
    LANDSCAPING = "landscaping"
    PEST_CONTROL = "pest_control"
    CLEANING = "cleaning"
    FLOORING = "flooring"
    PAINTING = "painting"
    GENERAL = "general"
    EMERGENCY = "emergency"
    PREVENTIVE = "preventive"


class EstimateLine(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float
    amount: float


class VendorEstimate(BaseModel):
    vendor_id: str
    vendor_name: str
    submitted_at: datetime
    labor_cost: float = 0.0
    materials_cost: float = 0.0
    total_amount: float
    estimated_duration_hours: Optional[float] = None
    notes: Optional[str] = None
    line_items: List[EstimateLine] = []
    is_selected: bool = False
    document_id: Optional[str] = None


class StatusHistoryEntry(BaseModel):
    status: WorkOrderStatus
    changed_at: datetime = Field(default_factory=datetime.utcnow)
    changed_by: str
    note: Optional[str] = None


class WorkOrderDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    work_order_number: str
    property_id: str
    unit_id: Optional[str] = None
    title: str
    description: str
    category: WorkOrderCategory
    priority: WorkOrderPriority = WorkOrderPriority.MEDIUM
    status: WorkOrderStatus = WorkOrderStatus.SUBMITTED
    reported_by: str
    reported_by_type: str = "tenant"  # tenant | owner | manager | system
    assigned_vendor_id: Optional[str] = None
    estimates: List[VendorEstimate] = []
    selected_estimate: Optional[VendorEstimate] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    approved_amount: Optional[float] = None
    scheduled_date: Optional[date] = None
    completed_date: Optional[date] = None
    actual_cost: Optional[float] = None
    journal_entry_id: Optional[str] = None
    images: List[str] = []
    documents: List[str] = []
    status_history: List[StatusHistoryEntry] = []
    notes: Optional[str] = None
    tenant_rating: Optional[int] = None
    is_recurring: bool = False
    preventive_schedule_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class PreventiveMaintenanceDB(BaseModel):
    """Scheduled preventive maintenance tasks."""

    id: Optional[str] = Field(None, alias="_id")
    property_id: str
    title: str
    description: str
    category: WorkOrderCategory
    frequency: str  # monthly | quarterly | semi-annual | annual
    month_of_year: Optional[List[int]] = None
    day_of_month: int = 1
    next_due_date: date
    last_completed_date: Optional[date] = None
    estimated_cost: Optional[float] = None
    preferred_vendor_id: Optional[str] = None
    auto_create_work_order: bool = True
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
