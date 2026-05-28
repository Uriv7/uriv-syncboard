"""
uriv-syncboard / backend / app / main.py
────────────────────────────────────────
FastAPI application factory.

Startup lifecycle
  1. Create DB tables via SQLAlchemy
  2. Initialise the singleton CaptureOrchestrator
  3. Mount routers (REST + WebSocket)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ws import router as ws_router
from app.api.routes import router as rest_router
from app.core.config import settings
from app.db.session import engine
from app.db.models import Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
log = logging.getLogger("syncboard")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup; clean up on shutdown."""
    log.info("Starting SyncBoard backend …")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("Database tables ready.")
    yield
    log.info("Shutting down SyncBoard backend …")
    await engine.dispose()


# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "SyncBoard API",
    description = "Smart Whiteboard OCR — WebSocket + REST",
    version     = "1.0.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = settings.cors_origins_list,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(ws_router)
app.include_router(rest_router, prefix="/api")


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "version": "1.0.0"}
