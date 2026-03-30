from fastapi import APIRouter, Depends, HTTPException, Query, status
from bson import ObjectId
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, EmailStr
from app.core.auth import get_current_active_user, require_manager_or_admin
from app.core.database import get_db

router = APIRouter(prefix="/vendors", tags=["Vendors"])


class VendorCreateRequest(BaseModel):
    name: str
    company_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: str
    trade_specialties: List[str] = []
    license_number: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_expiry: Optional[date] = None
    payment_terms: str = "net30"
    notes: Optional[str] = None


class VendorUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    trade_specialties: Optional[List[str]] = None
    license_number: Optional[str] = None
    license_expiry: Optional[date] = None
    insurance_expiry: Optional[date] = None
    status: Optional[str] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None


def _serialize(doc):
    if doc and "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


@router.get("/")
async def list_vendors(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
    specialty: Optional[str] = None,
    status: Optional[str] = None,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    query = {}
    if search:
        query["$text"] = {"$search": search}
    if specialty:
        query["trade_specialties"] = specialty
    if status:
        query["status"] = status

    vendors = await db.vendors.find(query).skip(skip).limit(limit).to_list(limit)
    total = await db.vendors.count_documents(query)
    return {"vendors": [_serialize(v) for v in vendors], "total": total}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_vendor(
    payload: VendorCreateRequest,
    db=Depends(get_db),
    current_user=Depends(require_manager_or_admin),
):
    doc = payload.model_dump()
    doc["status"] = "active"
    doc["total_jobs"] = 0
    doc["total_spend"] = 0.0
    doc["w9_on_file"] = False
    doc["created_at"] = datetime.utcnow()
    doc["updated_at"] = datetime.utcnow()
    result = await db.vendors.insert_one(doc)
    created = await db.vendors.find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("/{vendor_id}")
async def get_vendor(
    vendor_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    vendor = await db.vendors.find_one({"_id": ObjectId(vendor_id)})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return _serialize(vendor)


@router.put("/{vendor_id}")
async def update_vendor(
    vendor_id: str,
    payload: VendorUpdateRequest,
    db=Depends(get_db),
    current_user=Depends(require_manager_or_admin),
):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = datetime.utcnow()
    result = await db.vendors.update_one(
        {"_id": ObjectId(vendor_id)}, {"$set": updates}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    updated = await db.vendors.find_one({"_id": ObjectId(vendor_id)})
    return _serialize(updated)


@router.get("/{vendor_id}/invoices")
async def get_vendor_invoices(
    vendor_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
    current_user=Depends(require_manager_or_admin),
):
    invoices = await db.vendor_invoices.find({"vendor_id": vendor_id}).skip(skip).limit(limit).to_list(limit)
    total = await db.vendor_invoices.count_documents({"vendor_id": vendor_id})
    return {"invoices": [_serialize(i) for i in invoices], "total": total}


@router.post("/{vendor_id}/invoices", status_code=status.HTTP_201_CREATED)
async def create_vendor_invoice(
    vendor_id: str,
    payload: dict,
    db=Depends(get_db),
    current_user=Depends(require_manager_or_admin),
):
    vendor = await db.vendors.find_one({"_id": ObjectId(vendor_id)})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    payload["vendor_id"] = vendor_id
    payload["status"] = "pending"
    payload["amount_paid"] = 0.0
    payload["created_at"] = datetime.utcnow()
    result = await db.vendor_invoices.insert_one(payload)
    created = await db.vendor_invoices.find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("/{vendor_id}/work-orders")
async def get_vendor_work_orders(
    vendor_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    wos = await db.work_orders.find(
        {"assigned_vendor_id": vendor_id}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.work_orders.count_documents({"assigned_vendor_id": vendor_id})
    return {"work_orders": [_serialize(w) for w in wos], "total": total}


@router.get("/{vendor_id}/stats")
async def get_vendor_stats(
    vendor_id: str,
    db=Depends(get_db),
    current_user=Depends(require_manager_or_admin),
):
    pipeline = [
        {"$match": {"assigned_vendor_id": vendor_id}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "total_cost": {"$sum": {"$ifNull": ["$actual_cost", 0]}},
        }},
    ]
    breakdown = await db.work_orders.aggregate(pipeline).to_list(20)
    total_spend = sum(b.get("total_cost", 0) for b in breakdown)
    total_jobs = sum(b.get("count", 0) for b in breakdown)
    vendor = await db.vendors.find_one({"_id": ObjectId(vendor_id)})
    return {
        "vendor_id": vendor_id,
        "total_jobs": total_jobs,
        "total_spend": total_spend,
        "status_breakdown": breakdown,
        "rating": vendor.get("rating") if vendor else None,
    }
