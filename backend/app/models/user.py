from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    OWNER = "owner"
    CONTRACTOR = "contractor"
    TENANT = "tenant"


class NotificationPreferences(BaseModel):
    email: bool = True
    in_app: bool = True
    maintenance_alerts: bool = True
    invoice_alerts: bool = True
    lease_alerts: bool = True
    hoa_alerts: bool = True


class UserDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    email: EmailStr
    full_name: str
    google_id: Optional[str] = None
    avatar_url: Optional[str] = None
    role: UserRole = UserRole.OWNER
    is_active: bool = True
    is_verified: bool = False
    phone: Optional[str] = None
    notification_preferences: NotificationPreferences = NotificationPreferences()
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
