import json
import os
from typing import List, Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Estatio"
    APP_ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    DEBUG: bool = False

    # MongoDB
    MONGODB_URL: str
    MONGODB_DB: str = "estatio"

    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str = ""

    # GCS
    GCS_BUCKET_NAME: str = "estatio-documents"
    GCS_PROJECT_ID: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    # AI
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    AI_PROVIDER: str = "gemini"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Stripe
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    # Email
    SENDGRID_API_KEY: Optional[str] = None
    FROM_EMAIL: str = "noreply@estatio.app"

    # CORS
    FRONTEND_URL: str = "http://localhost:3000"
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError, ValueError):
                return [v]
        return v

    @model_validator(mode="after")
    def derive_redirect_uri(self):
        """Auto-derive GOOGLE_REDIRECT_URI on Cloud Run when not explicitly set."""
        if not self.GOOGLE_REDIRECT_URI:
            # Cloud Run always sets K_SERVICE and K_REVISION env vars.
            k_service = os.environ.get("K_SERVICE")
            gcp_region = os.environ.get("CLOUD_RUN_REGION", "us-central1")
            gcp_project = os.environ.get("GCS_PROJECT_ID", "")
            if k_service:
                # Build the deterministic Cloud Run URL.
                self.GOOGLE_REDIRECT_URI = (
                    f"https://{k_service}-{gcp_project}.{gcp_region}.run.app"
                    f"/api/v1/auth/google/callback"
                )
            else:
                # Local development fallback.
                self.GOOGLE_REDIRECT_URI = (
                    "http://localhost:8000/api/v1/auth/google/callback"
                )
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
