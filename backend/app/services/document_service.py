"""
document_service.py
-------------------
GCS document service for the Estatio property management platform.

Responsibilities:
  - Upload documents to Google Cloud Storage with structured paths
  - Store document metadata in MongoDB
  - Fire-and-forget AI classification via background tasks
  - Generate signed URLs for secure temporary access
  - Soft-delete documents in MongoDB with optional GCS removal
  - List and retrieve document records

GCS bucket path pattern:
  {bucket}/{env}/{category}/{property_id}/{YYYY-MM-DD}/{uuid}_{filename}

MongoDB collection: documents (DocumentDB)
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from functools import partial
from typing import Any, Dict, List, Optional

import structlog
from bson import ObjectId
from fastapi import UploadFile
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.models.document import DocumentCategory, DocumentDB

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# GCS client — initialised lazily, wrapped for async via run_in_executor
# ---------------------------------------------------------------------------

_gcs_client = None
_GCS_AVAILABLE = False


def _get_gcs_client():
    """Return a cached google.cloud.storage.Client instance."""
    global _gcs_client, _GCS_AVAILABLE
    if _gcs_client is None:
        try:
            from google.cloud import storage  # type: ignore

            _gcs_client = storage.Client(project=settings.GCS_PROJECT_ID)
            _GCS_AVAILABLE = True
            log.info("GCS client initialised", project=settings.GCS_PROJECT_ID)
        except Exception as exc:
            log.warning("GCS client unavailable", error=str(exc))
            _GCS_AVAILABLE = False
    return _gcs_client


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

# Mapping from DocumentCategory to GCS sub-folder
_CATEGORY_FOLDER_MAP: Dict[str, str] = {
    DocumentCategory.LEASE: "leases",
    DocumentCategory.INVOICE: "invoices",
    DocumentCategory.RECEIPT: "invoices",
    DocumentCategory.MAINTENANCE: "maintenance",
    DocumentCategory.VENDOR_CONTRACT: "maintenance",
    DocumentCategory.INSPECTION: "maintenance",
    DocumentCategory.PHOTO: "photos",
    DocumentCategory.TAX: "tax",
    DocumentCategory.INSURANCE: "insurance",
    DocumentCategory.HOA: "other",
    DocumentCategory.LEGAL: "other",
    DocumentCategory.FINANCIAL: "other",
    DocumentCategory.PERMIT: "other",
    DocumentCategory.OTHER: "other",
}


def _build_gcs_path(
    category: DocumentCategory,
    property_id: Optional[str],
    filename: str,
    file_uuid: str,
) -> str:
    """
    Build a structured GCS object path.

    Pattern: {env}/{folder}/{property_id_or_shared}/{date}/{uuid}_{filename}
    """
    env = settings.APP_ENV  # "production", "development", "staging", etc.
    folder = _CATEGORY_FOLDER_MAP.get(category, "other")
    scope = property_id if property_id else "shared"
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    safe_filename = filename.replace(" ", "_")
    return f"{env}/{folder}/{scope}/{date_str}/{file_uuid}_{safe_filename}"


# ---------------------------------------------------------------------------
# GCS sync helpers (run inside executor)
# ---------------------------------------------------------------------------

def _sync_upload_blob(
    bucket_name: str,
    gcs_path: str,
    data: bytes,
    content_type: str,
) -> None:
    """Upload bytes to GCS (sync — must be called via run_in_executor)."""

    client = _get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    blob.upload_from_string(data, content_type=content_type)
    log.info("GCS upload complete", path=gcs_path, size=len(data))


def _sync_generate_signed_url(
    bucket_name: str,
    gcs_path: str,
    expiry_minutes: int,
) -> str:
    """Generate a V4 signed URL (sync — must be called via run_in_executor)."""

    client = _get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expiry_minutes),
        method="GET",
    )
    return url


def _sync_delete_blob(bucket_name: str, gcs_path: str) -> bool:
    """Delete a GCS object (sync — must be called via run_in_executor)."""
    try:

        client = _get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_path)
        blob.delete()
        log.info("GCS object deleted", path=gcs_path)
        return True
    except Exception as exc:
        log.warning("GCS delete failed", path=gcs_path, error=str(exc))
        return False


def _sync_download_blob(bucket_name: str, gcs_path: str) -> bytes:
    """Download a GCS object as bytes (sync — must be called via run_in_executor)."""

    client = _get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    return blob.download_as_bytes()


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------

async def _async_upload_blob(
    bucket_name: str,
    gcs_path: str,
    data: bytes,
    content_type: str,
) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        partial(_sync_upload_blob, bucket_name, gcs_path, data, content_type),
    )


async def _async_generate_signed_url(
    bucket_name: str,
    gcs_path: str,
    expiry_minutes: int,
) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(_sync_generate_signed_url, bucket_name, gcs_path, expiry_minutes),
    )


async def _async_delete_blob(bucket_name: str, gcs_path: str) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(_sync_delete_blob, bucket_name, gcs_path),
    )


async def _async_download_blob(bucket_name: str, gcs_path: str) -> bytes:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(_sync_download_blob, bucket_name, gcs_path),
    )


# ---------------------------------------------------------------------------
# Internal MongoDB helpers
# ---------------------------------------------------------------------------

def _doc_from_mongo(raw: Dict[str, Any]) -> DocumentDB:
    """Convert a raw MongoDB document dict to a DocumentDB instance."""
    raw["_id"] = str(raw["_id"])
    return DocumentDB(**raw)


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

async def upload_document(
    db: AsyncIOMotorDatabase,
    file: UploadFile,
    metadata: Dict[str, Any],
    user_id: str,
) -> DocumentDB:
    """
    Upload a file to GCS and store its metadata in MongoDB.

    Parameters:
        db        – Motor async database handle
        file      – FastAPI UploadFile object
        metadata  – dict with optional keys:
                      category, property_id, owner_id, tenant_id, vendor_id,
                      work_order_id, invoice_id, name, description, tags,
                      is_public, accessible_by
        user_id   – ID of the user performing the upload

    Returns:
        DocumentDB instance with the persisted document record.
    """
    logger = log.bind(action="upload_document", user_id=user_id)
    logger.info("Starting document upload", filename=file.filename)

    # Read file bytes
    file_bytes = await file.read()
    file_size = len(file_bytes)

    # Resolve category
    raw_category = metadata.get("category", DocumentCategory.OTHER)
    try:
        category = DocumentCategory(raw_category)
    except ValueError:
        category = DocumentCategory.OTHER

    # Build GCS path
    file_uuid = str(uuid.uuid4())
    original_filename = file.filename or "unknown"
    property_id = metadata.get("property_id")
    gcs_path = _build_gcs_path(category, property_id, original_filename, file_uuid)
    bucket_name = settings.GCS_BUCKET_NAME
    content_type = file.content_type or "application/octet-stream"

    # Upload to GCS (graceful fallback when GCS is unavailable)
    _get_gcs_client()
    if _GCS_AVAILABLE:
        try:
            await _async_upload_blob(bucket_name, gcs_path, file_bytes, content_type)
        except Exception as exc:
            logger.error("GCS upload failed", error=str(exc))
            raise RuntimeError(f"File upload failed: {exc}") from exc
    else:
        logger.warning("GCS unavailable — metadata stored without actual file upload")

    # Build DocumentDB record
    doc_id = str(ObjectId())
    now = datetime.utcnow()
    doc = DocumentDB(
        _id=doc_id,
        name=metadata.get("name") or original_filename,
        original_filename=original_filename,
        gcs_path=gcs_path,
        gcs_bucket=bucket_name,
        content_type=content_type,
        size_bytes=file_size,
        category=category,
        property_id=property_id,
        owner_id=metadata.get("owner_id"),
        tenant_id=metadata.get("tenant_id"),
        vendor_id=metadata.get("vendor_id"),
        work_order_id=metadata.get("work_order_id"),
        invoice_id=metadata.get("invoice_id"),
        tags=metadata.get("tags", []),
        description=metadata.get("description"),
        is_public=metadata.get("is_public", False),
        accessible_by=metadata.get("accessible_by", []),
        uploaded_by=user_id,
        ai_processed=False,
        created_at=now,
        updated_at=now,
    )

    # Persist to MongoDB
    doc_dict = doc.model_dump(by_alias=False)
    doc_dict["_id"] = ObjectId(doc_id)
    await db.documents.insert_one(doc_dict)
    logger.info("Document metadata saved to MongoDB", document_id=doc_id)

    # Fire-and-forget AI classification
    asyncio.create_task(
        _fire_and_forget_ai(db, doc_id, file_bytes, original_filename)
    )

    return doc


async def _fire_and_forget_ai(
    db: AsyncIOMotorDatabase,
    document_id: str,
    file_bytes: bytes,
    filename: str,
) -> None:
    """
    Fire-and-forget wrapper for AI classification.
    Errors are caught and logged without propagation.
    """
    try:
        await _classify_and_update(db, document_id, file_bytes, filename)
    except Exception as exc:
        log.warning(
            "Background AI classification error",
            document_id=document_id,
            error=str(exc),
        )


async def _classify_and_update(
    db: AsyncIOMotorDatabase,
    document_id: str,
    file_bytes: bytes,
    filename: str,
) -> None:
    """
    Run AI classification and update the document record in MongoDB.
    """
    from app.services import ai_service  # local import to avoid circular deps

    logger = log.bind(action="classify_document", document_id=document_id)
    logger.info("Running AI classification")

    try:
        result = await ai_service.classify_document(file_bytes, filename)
        now = datetime.utcnow()
        await db.documents.update_one(
            {"_id": ObjectId(document_id)},
            {
                "$set": {
                    "ai_summary": result.get("summary"),
                    "ai_extracted_data": result.get("extracted_data"),
                    "ai_classification_confidence": result.get("confidence"),
                    "category": result.get("category", DocumentCategory.OTHER),
                    "tags": result.get("tags", []),
                    "ai_processed": True,
                    "ai_processed_at": now,
                    "updated_at": now,
                }
            },
        )
        logger.info(
            "AI classification complete",
            category=result.get("category"),
            confidence=result.get("confidence"),
        )
    except Exception as exc:
        logger.error("AI classification failed", error=str(exc))
        await db.documents.update_one(
            {"_id": ObjectId(document_id)},
            {"$set": {"ai_processed": False, "updated_at": datetime.utcnow()}},
        )


async def get_signed_url(gcs_path: str, expiry_minutes: int = 60) -> str:
    """
    Generate a signed URL for temporary, secure file access.

    Parameters:
        gcs_path       – GCS object path (relative to bucket)
        expiry_minutes – How long the URL remains valid (default 60 min)

    Returns:
        A signed URL string, or a placeholder if GCS is unavailable.
    """
    _get_gcs_client()
    if not _GCS_AVAILABLE:
        log.warning("GCS unavailable — returning placeholder URL", gcs_path=gcs_path)
        return f"https://storage.googleapis.com/{settings.GCS_BUCKET_NAME}/{gcs_path}"

    try:
        url = await _async_generate_signed_url(
            settings.GCS_BUCKET_NAME, gcs_path, expiry_minutes
        )
        log.info("Signed URL generated", gcs_path=gcs_path, expiry_minutes=expiry_minutes)
        return url
    except Exception as exc:
        log.error("Failed to generate signed URL", gcs_path=gcs_path, error=str(exc))
        raise RuntimeError(f"Could not generate signed URL: {exc}") from exc


async def delete_document(
    db: AsyncIOMotorDatabase,
    document_id: str,
    user_id: str,
    hard_delete_gcs: bool = False,
) -> bool:
    """
    Soft-delete a document record in MongoDB.

    Optionally removes the object from GCS (hard_delete_gcs=True).

    Parameters:
        db                – Motor async database handle
        document_id       – MongoDB _id of the document
        user_id           – ID of the user requesting deletion
        hard_delete_gcs   – If True, also delete the GCS object

    Returns:
        True if the document was found and deleted, False otherwise.
    """
    logger = log.bind(action="delete_document", document_id=document_id, user_id=user_id)

    raw = await db.documents.find_one({"_id": ObjectId(document_id)})
    if not raw:
        logger.warning("Document not found for deletion")
        return False

    now = datetime.utcnow()
    result = await db.documents.update_one(
        {"_id": ObjectId(document_id)},
        {
            "$set": {
                "is_deleted": True,
                "deleted_by": user_id,
                "deleted_at": now,
                "updated_at": now,
            }
        },
    )

    if result.modified_count == 0:
        logger.warning("Document delete update matched nothing")
        return False

    logger.info("Document soft-deleted from MongoDB")

    if hard_delete_gcs:
        gcs_path = raw.get("gcs_path", "")
        if gcs_path:
            _get_gcs_client()
            if _GCS_AVAILABLE:
                asyncio.create_task(
                    _async_delete_blob(settings.GCS_BUCKET_NAME, gcs_path)
                )

    return True


async def list_documents(
    db: AsyncIOMotorDatabase,
    filters: Dict[str, Any],
    skip: int = 0,
    limit: int = 50,
) -> List[DocumentDB]:
    """
    List documents matching the given filters.

    Parameters:
        db      – Motor async database handle
        filters – MongoDB filter dict (e.g. {"property_id": "...", "category": "lease"})
        skip    – Number of records to skip (pagination offset)
        limit   – Maximum number of records to return

    Returns:
        List of DocumentDB instances (excludes soft-deleted documents).
    """
    # Always exclude soft-deleted documents
    query = {**filters, "is_deleted": {"$ne": True}}

    cursor = db.documents.find(query).sort("created_at", -1).skip(skip).limit(limit)
    results: List[DocumentDB] = []
    async for raw in cursor:
        try:
            results.append(_doc_from_mongo(raw))
        except Exception as exc:
            log.warning("Failed to parse document", error=str(exc))
    return results


async def get_document(
    db: AsyncIOMotorDatabase,
    document_id: str,
) -> Optional[DocumentDB]:
    """
    Retrieve a single document by its MongoDB _id.

    Parameters:
        db          – Motor async database handle
        document_id – MongoDB _id string

    Returns:
        DocumentDB instance, or None if not found / soft-deleted.
    """
    try:
        raw = await db.documents.find_one(
            {"_id": ObjectId(document_id), "is_deleted": {"$ne": True}}
        )
    except Exception as exc:
        log.warning("get_document query error", document_id=document_id, error=str(exc))
        return None

    if not raw:
        return None
    return _doc_from_mongo(raw)


async def process_document_ai(
    db: AsyncIOMotorDatabase,
    document_id: str,
) -> None:
    """
    Background task: fetch the document from GCS, run AI classification,
    and update the MongoDB record with the results.

    This function is safe to call directly (e.g. from a Celery worker or
    FastAPI background task) and will not raise on classification errors.

    Parameters:
        db          – Motor async database handle
        document_id – MongoDB _id of the document to process
    """
    logger = log.bind(action="process_document_ai", document_id=document_id)
    logger.info("Starting document AI reprocessing")

    raw = await db.documents.find_one({"_id": ObjectId(document_id)})
    if not raw:
        logger.warning("Document not found for AI processing")
        return

    gcs_path: str = raw.get("gcs_path", "")
    filename: str = raw.get("original_filename", "unknown")

    _get_gcs_client()
    file_bytes = b""
    if _GCS_AVAILABLE and gcs_path:
        try:
            file_bytes = await _async_download_blob(settings.GCS_BUCKET_NAME, gcs_path)
            logger.info("Document fetched from GCS", size=len(file_bytes))
        except Exception as exc:
            logger.warning("Failed to fetch document from GCS", error=str(exc))
            # Continue with empty bytes — classify_document will use filename heuristics
    else:
        logger.warning("GCS unavailable or no gcs_path — classifying by filename only")

    await _classify_and_update(db, document_id, file_bytes, filename)
    logger.info("Document AI reprocessing complete")
