import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.core.database import close_db, connect_db
from app.routers import (
    accounting,
    ai,
    auth,
    documents,
    maintenance,
    notifications,
    owners,
    properties,
    tenants,
    vendors,
)
from app.services.accounting_service import seed_chart_of_accounts

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Estatio API", env=settings.APP_ENV)
    await connect_db()
    from app.core.database import get_db

    db = get_db()
    await seed_chart_of_accounts(db)
    log.info("Estatio API ready")
    yield
    await close_db()
    log.info("Estatio API shutdown")


app = FastAPI(
    title="Estatio Property Management API",
    description="AI-native property management platform — production SaaS",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics ─────────────────────────────────────────────────────────
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# ── Request logging middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    log.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
    )
    return response


# ── Global exception handler ───────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again."},
    )


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "version": "1.0.0", "app": settings.APP_NAME}


# ── Routers ────────────────────────────────────────────────────────────────────
PREFIX = settings.API_V1_PREFIX

app.include_router(auth.router, prefix=PREFIX)
app.include_router(properties.router, prefix=PREFIX)
app.include_router(owners.router, prefix=PREFIX)
app.include_router(accounting.router, prefix=PREFIX)
app.include_router(maintenance.router, prefix=PREFIX)
app.include_router(vendors.router, prefix=PREFIX)
app.include_router(documents.router, prefix=PREFIX)
app.include_router(notifications.router, prefix=PREFIX)
app.include_router(ai.router, prefix=PREFIX)
app.include_router(tenants.router, prefix=PREFIX)
