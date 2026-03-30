from fastapi import APIRouter, Depends, HTTPException, Query, status
from bson import ObjectId
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from app.core.auth import get_current_active_user, require_manager_or_admin
from app.core.database import get_db

router = APIRouter(prefix="/tenants", tags=["Tenants"])


def _serialize(doc):
    if doc and "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


class TenantCreateRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str
    property_id: str
    unit_id: Optional[str] = None
    lease_start_date: str
    lease_end_date: str
    monthly_rent: float
    security_deposit: float = 0.0


@router.get("/")
async def list_tenants(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    property_id: Optional[str] = None,
    status: Optional[str] = None,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    query = {}
    if property_id:
        query["property_id"] = property_id
    if status:
        query["lease_status"] = status

    role = current_user.get("role")
    if role == "owner":
        user_id = str(current_user["_id"])
        ownerships = await db.ownerships.find({"owner_id": user_id}).to_list(200)
        prop_ids = [o["property_id"] for o in ownerships]
        query["property_id"] = {"$in": prop_ids}

    tenants = await db.tenants.find(query).skip(skip).limit(limit).to_list(limit)
    total = await db.tenants.count_documents(query)
    return {"tenants": [_serialize(t) for t in tenants], "total": total}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreateRequest,
    db=Depends(get_db),
    current_user=Depends(require_manager_or_admin),
):
    doc = payload.model_dump()
    doc["lease_status"] = "active"
    doc["balance"] = 0.0
    doc["created_at"] = datetime.utcnow()
    doc["updated_at"] = datetime.utcnow()
    result = await db.tenants.insert_one(doc)
    created = await db.tenants.find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    tenant = await db.tenants.find_one({"_id": ObjectId(tenant_id)})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _serialize(tenant)


@router.get("/{tenant_id}/ledger")
async def get_tenant_ledger(
    tenant_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    tenant = await db.tenants.find_one({"_id": ObjectId(tenant_id)})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    entries = await db.journal_entries.find(
        {"reference_id": tenant_id}
    ).sort("date", -1).to_list(200)
    return {"tenant_id": tenant_id, "ledger": [_serialize(e) for e in entries]}
