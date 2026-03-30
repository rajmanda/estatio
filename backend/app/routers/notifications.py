from fastapi import APIRouter, Depends, HTTPException, Query, status
from bson import ObjectId
from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.services.notification_service import (
    get_notifications, get_unread_count, mark_read,
    mark_all_read, delete_notification
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/")
async def list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    user_id = str(current_user["_id"])
    notifications = await get_notifications(db, user_id, unread_only, skip, limit)
    count = await get_unread_count(db, user_id)
    return {"notifications": notifications, "unread_count": count}


@router.get("/unread-count")
async def unread_count(
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    count = await get_unread_count(db, str(current_user["_id"]))
    return {"unread_count": count}


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    success = await mark_read(db, notification_id, str(current_user["_id"]))
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "read"}


@router.post("/read-all")
async def mark_all_notifications_read(
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    count = await mark_all_read(db, str(current_user["_id"]))
    return {"marked_read": count}


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notif(
    notification_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    deleted = await delete_notification(db, notification_id, str(current_user["_id"]))
    if not deleted:
        raise HTTPException(status_code=404, detail="Notification not found")
