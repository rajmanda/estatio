from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DocumentCategory(str, Enum):
    LEASE = "lease"
    INVOICE = "invoice"
    RECEIPT = "receipt"
    INSURANCE = "insurance"
    INSPECTION = "inspection"
    PERMIT = "permit"
    HOA = "hoa"
    MAINTENANCE = "maintenance"
    LEGAL = "legal"
    TAX = "tax"
    FINANCIAL = "financial"
    VENDOR_CONTRACT = "vendor_contract"
    PHOTO = "photo"
    OTHER = "other"


class DocumentDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    name: str
    original_filename: str
    gcs_path: str
    gcs_bucket: str
    content_type: str
    size_bytes: int
    category: DocumentCategory
    property_id: Optional[str] = None
    owner_id: Optional[str] = None
    tenant_id: Optional[str] = None
    vendor_id: Optional[str] = None
    work_order_id: Optional[str] = None
    invoice_id: Optional[str] = None
    tags: List[str] = []
    description: Optional[str] = None
    # AI-generated fields
    ai_summary: Optional[str] = None
    ai_extracted_data: Optional[Dict[str, Any]] = None
    ai_classification_confidence: Optional[float] = None
    ai_processed: bool = False
    ai_processed_at: Optional[datetime] = None
    # Access control
    is_public: bool = False
    accessible_by: List[str] = []  # user_ids
    signed_url_expiry: Optional[datetime] = None
    uploaded_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
