from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PropertyType(str, Enum):
    SINGLE_FAMILY = "single_family"
    MULTI_FAMILY = "multi_family"
    COMMERCIAL = "commercial"
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    LAND = "land"


class PropertyStatus(str, Enum):
    ACTIVE = "active"
    VACANT = "vacant"
    UNDER_MAINTENANCE = "under_maintenance"
    LISTED = "listed"
    INACTIVE = "inactive"


class Address(BaseModel):
    street: str
    unit: Optional[str] = None
    city: str
    state: str
    zip_code: str
    country: str = "US"
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class Unit(BaseModel):
    unit_id: str
    unit_number: str
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    square_feet: Optional[float] = None
    rent_amount: Optional[float] = None
    status: str = "vacant"
    current_tenant_id: Optional[str] = None


class HOAInfo(BaseModel):
    hoa_name: Optional[str] = None
    hoa_contact: Optional[str] = None
    hoa_fee: Optional[float] = None
    hoa_fee_frequency: Optional[str] = "monthly"
    next_due_date: Optional[date] = None
    violations: List[Dict[str, Any]] = []


class PropertyDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    name: str
    property_type: PropertyType
    status: PropertyStatus = PropertyStatus.ACTIVE
    address: Address
    units: List[Unit] = []
    year_built: Optional[int] = None
    square_feet: Optional[float] = None
    lot_size: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    purchase_price: Optional[float] = None
    purchase_date: Optional[date] = None
    current_value: Optional[float] = None
    monthly_rent: Optional[float] = None
    hoa_info: Optional[HOAInfo] = None
    management_fee_rate: float = 0.10
    management_fee_type: str = "percentage"
    management_fee_flat: Optional[float] = None
    insurance_info: Optional[Dict[str, Any]] = None
    mortgage_info: Optional[Dict[str, Any]] = None
    amenities: List[str] = []
    images: List[str] = []
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class OwnershipDB(BaseModel):
    """Many-to-many join: owner ↔ property with metadata."""

    id: Optional[str] = Field(None, alias="_id")
    owner_id: str
    property_id: str
    ownership_percentage: float = 100.0
    billing_preference: str = "email"  # email | portal | mail
    statement_preference: str = "monthly"  # monthly | quarterly | annual
    effective_date: date
    end_date: Optional[date] = None
    is_primary_owner: bool = False
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
