from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class LeaseStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    MONTH_TO_MONTH = "month_to_month"


class TenantDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    first_name: str
    last_name: str
    email: EmailStr
    phone: str
    property_id: str
    unit_id: Optional[str] = None
    lease_status: LeaseStatus = LeaseStatus.ACTIVE
    lease_start_date: date
    lease_end_date: date
    monthly_rent: float
    security_deposit: float = 0.0
    security_deposit_held: float = 0.0
    pet_deposit: float = 0.0
    last_rent_increase: Optional[date] = None
    move_in_date: Optional[date] = None
    move_out_date: Optional[date] = None
    emergency_contact: Optional[Dict[str, str]] = None
    num_occupants: int = 1
    vehicles: List[Dict[str, str]] = []
    balance: float = 0.0
    portal_user_id: Optional[str] = None
    documents: List[str] = []
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
