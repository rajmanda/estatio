import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.services.ai_service import answer_query, generate_insight, predict_maintenance
from app.services.document_service import get_document

log = structlog.get_logger()
router = APIRouter(prefix="/ai", tags=["AI"])


class QueryRequest(BaseModel):
    query: str


@router.post("/query")
async def natural_language_query(
    payload: QueryRequest,
    background_tasks: __import__("fastapi").BackgroundTasks,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    if not payload.query or len(payload.query.strip()) < 3:
        raise HTTPException(status_code=400, detail="Query too short")
    user_id = str(current_user["_id"])
    result = await answer_query(db, user_id, payload.query)
    return result


@router.get("/insights/{property_id}")
async def property_insights(
    property_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    prop = await db.properties.find_one(
        {"_id": __import__("bson").ObjectId(property_id)}
    )
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    insights = await generate_insight(db, property_id)
    return insights


@router.get("/predict/{property_id}")
async def maintenance_predictions(
    property_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    prop = await db.properties.find_one(
        {"_id": __import__("bson").ObjectId(property_id)}
    )
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    predictions = await predict_maintenance(db, property_id)
    return predictions


@router.post("/documents/{doc_id}/classify")
async def reclassify_document(
    doc_id: str,
    background_tasks: __import__("fastapi").BackgroundTasks,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):

    from app.services.document_service import process_document_ai

    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    background_tasks.add_task(process_document_ai, db, doc_id)
    return {"status": "classification_started", "document_id": doc_id}
