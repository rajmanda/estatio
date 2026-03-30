from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from bson import ObjectId
from typing import Optional
from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.services.document_service import (
    upload_document, list_documents, get_document,
    get_signed_url, delete_document, process_document_ai
)
import asyncio

router = APIRouter(prefix="/documents", tags=["Documents"])


def _serialize(doc):
    if doc and "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    category: str = Form("other"),
    property_id: Optional[str] = Form(None),
    owner_id: Optional[str] = Form(None),
    vendor_id: Optional[str] = Form(None),
    work_order_id: Optional[str] = Form(None),
    invoice_id: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    metadata = {
        "category": category,
        "property_id": property_id,
        "owner_id": owner_id,
        "vendor_id": vendor_id,
        "work_order_id": work_order_id,
        "invoice_id": invoice_id,
        "description": description,
        "tags": [t.strip() for t in tags.split(",")] if tags else [],
    }
    doc = await upload_document(db, file, metadata, str(current_user["_id"]))
    return _serialize(doc.model_dump(by_alias=True))


@router.get("/")
async def list_docs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    property_id: Optional[str] = None,
    owner_id: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    filters = {}
    if property_id:
        filters["property_id"] = property_id
    if owner_id:
        filters["owner_id"] = owner_id
    if category:
        filters["category"] = category
    if search:
        filters["$text"] = {"$search": search}

    role = current_user.get("role")
    if role == "owner":
        user_id = str(current_user["_id"])
        ownerships = await db.ownerships.find({"owner_id": user_id}).to_list(200)
        prop_ids = [o["property_id"] for o in ownerships]
        filters["$or"] = [
            {"owner_id": user_id},
            {"property_id": {"$in": prop_ids}},
        ]

    docs = await db.documents.find(filters).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.documents.count_documents(filters)
    return {"documents": [_serialize(d) for d in docs], "total": total}


@router.get("/{doc_id}")
async def get_doc(
    doc_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return _serialize(doc.model_dump(by_alias=True))


@router.get("/{doc_id}/download")
async def download_doc(
    doc_id: str,
    expiry_minutes: int = Query(60, ge=5, le=1440),
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    signed_url = await get_signed_url(doc.gcs_path, expiry_minutes)
    return {"signed_url": signed_url, "expires_in_minutes": expiry_minutes}


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doc(
    doc_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    deleted = await delete_document(db, doc_id, str(current_user["_id"]))
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")


@router.post("/{doc_id}/reprocess")
async def reprocess_doc(
    doc_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    asyncio.create_task(process_document_ai(db, doc_id))
    return {"status": "reprocessing_started", "document_id": doc_id}
