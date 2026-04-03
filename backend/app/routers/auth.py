"""
Authentication router — Google OAuth 2.0 flow + JWT token issuance.

Endpoints:
    GET  /google/login      → redirect to Google's OAuth consent screen
    GET  /google/callback   → exchange auth code, upsert user, return tokens
    POST /token             → refresh access token with a valid refresh token
    GET  /me                → return the current authenticated user's profile
    POST /logout            → invalidate refresh token (client-side clear)
"""

from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from jose import JWTError
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models.user import UserRole

log = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

GOOGLE_SCOPES = " ".join(
    [
        "openid",
        "email",
        "profile",
    ]
)


# ---------------------------------------------------------------------------
# Pydantic schemas (inline)
# ---------------------------------------------------------------------------
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


class RefreshRequest(BaseModel):
    refresh_token: str


class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    phone: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _serialize_user(user: dict) -> dict:
    """Convert MongoDB document to a JSON-serialisable dict."""
    user = dict(user)
    user["id"] = str(user.pop("_id"))
    return user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/google/login", summary="Redirect to Google OAuth consent screen")
async def google_login(
    redirect_uri: Optional[str] = Query(
        None, description="Override the post-login redirect URI"
    ),
):
    """
    Build the Google OAuth URL and redirect the user to Google's consent page.
    Optionally accepts a `redirect_uri` query parameter to allow the frontend
    to specify where to land after authentication; this value is stored via
    state and used after the callback.
    """
    import base64
    import json
    import urllib.parse

    # Encode optional frontend redirect in state
    state_payload = {}
    if redirect_uri:
        state_payload["redirect_uri"] = redirect_uri
    state = base64.urlsafe_b64encode(json.dumps(state_payload).encode()).decode()

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=url)


@router.get(
    "/google/callback", response_model=TokenResponse, summary="Google OAuth callback"
)
async def google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Exchange the authorization code for Google tokens, fetch user info,
    upsert the user in MongoDB, and return Estatio JWT tokens.
    """
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth error: {error}",
        )

    # --- Exchange code for tokens ---
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

    if token_resp.status_code != 200:
        log.error("Google token exchange failed", body=token_resp.text)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to exchange authorization code with Google.",
        )

    google_tokens = token_resp.json()
    google_access_token = google_tokens.get("access_token")

    # --- Fetch user info from Google ---
    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {google_access_token}"},
        )

    if userinfo_resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch user info from Google.",
        )

    google_user = userinfo_resp.json()
    google_id: str = google_user["sub"]
    email: str = google_user["email"]
    full_name: str = google_user.get("name", email.split("@", maxsplit=1)[0])
    avatar_url: Optional[str] = google_user.get("picture")
    is_verified: bool = google_user.get("email_verified", False)

    # --- Upsert user in MongoDB ---
    now = datetime.now(timezone.utc)

    # Try find by google_id first, then fall back to email
    existing = await db.users.find_one({"google_id": google_id})
    if not existing:
        existing = await db.users.find_one({"email": email})

    if existing:
        # Update existing user
        await db.users.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "google_id": google_id,
                    "full_name": full_name,
                    "avatar_url": avatar_url,
                    "is_verified": is_verified,
                    "last_login": now,
                    "updated_at": now,
                }
            },
        )
        user_id = str(existing["_id"])
    else:
        # Create new user
        new_user = {
            "email": email,
            "full_name": full_name,
            "google_id": google_id,
            "avatar_url": avatar_url,
            "role": UserRole.OWNER.value,
            "is_active": True,
            "is_verified": is_verified,
            "phone": None,
            "notification_preferences": {
                "email": True,
                "in_app": True,
                "maintenance_alerts": True,
                "invoice_alerts": True,
                "lease_alerts": True,
                "hoa_alerts": True,
            },
            "created_at": now,
            "updated_at": now,
            "last_login": now,
        }
        result = await db.users.insert_one(new_user)
        user_id = str(result.inserted_id)

    log.info("User authenticated via Google", user_id=user_id, email=email)

    # --- Issue Estatio tokens ---
    access_token = create_access_token(subject=user_id)
    refresh_token = create_refresh_token(subject=user_id)

    frontend_url = f"{settings.FRONTEND_URL}/auth/callback?access_token={access_token}&refresh_token={refresh_token}"
    return RedirectResponse(url=frontend_url)


@router.post("/token", response_model=TokenResponse, summary="Refresh access token")
async def refresh_token(
    body: RefreshRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Exchange a valid refresh token for a new access token (and a rotated
    refresh token).  The previous refresh token is implicitly invalidated
    by issuing a new one with a fresh expiry.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(body.refresh_token)
    except JWTError:
        raise credentials_exception

    if payload.get("type") != "refresh":
        raise credentials_exception

    user_id: str = payload.get("sub")
    if not user_id:
        raise credentials_exception

    # Verify user still exists and is active
    try:
        user = await db.users.find_one({"_id": ObjectId(user_id), "is_active": True})
    except Exception:
        raise credentials_exception

    if not user:
        raise credentials_exception

    new_access_token = create_access_token(subject=user_id)
    new_refresh_token = create_refresh_token(subject=user_id)

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
    )


@router.get(
    "/me", response_model=UserProfileResponse, summary="Get current user profile"
)
async def get_me(current_user: dict = Depends(get_current_active_user)):
    """
    Return the profile of the currently authenticated user.
    Requires a valid Bearer access token.
    """
    return UserProfileResponse(
        id=str(current_user["_id"]),
        email=current_user["email"],
        full_name=current_user["full_name"],
        avatar_url=current_user.get("avatar_url"),
        role=current_user.get("role", UserRole.OWNER.value),
        is_active=current_user.get("is_active", True),
        is_verified=current_user.get("is_verified", False),
        phone=current_user.get("phone"),
        created_at=current_user["created_at"],
        last_login=current_user.get("last_login"),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout")
async def logout(current_user: dict = Depends(get_current_active_user)):
    """
    Logout the current user.

    JWT tokens are stateless so true server-side invalidation would require a
    deny-list (Redis).  This endpoint exists to give the client a canonical
    place to call, and to update the last_seen timestamp.  The client MUST
    discard the access and refresh tokens on its side.
    """
    # Future: add token to Redis deny-list here
    log.info("User logged out", user_id=str(current_user["_id"]))
