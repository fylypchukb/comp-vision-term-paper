"""
main.py — FastAPI application entry point for the Gesture Smart Lock backend.

Responsibilities:
  - Create the FastAPI application with a lifespan handler (startup / shutdown)
  - Register CORS middleware for the React frontend
  - Mount all routers (locks, users, gestures)
  - Expose the WebSocket endpoint at /ws
  - Register a global error handler for SQLAlchemy database errors

WebSocket event format (broadcast to all connected clients):
  {"event": "lock_state_changed",  "lock_id": 1, "state": "unlocked", "changed_at": "ISO8601"}
  {"event": "gesture_event",        "lock_id": 1, "gesture": "FIST", "sequence": [...], "status": "partial"}
  {"event": "pin_recording_update", "lock_id": 1, "gesture": "THUMBS_UP", "gesture_count": 2}
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from database import engine, init_db
from routers import gestures, locks, users
from ws_manager import manager

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application lifespan (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once on startup and once on shutdown.

    Startup : create all database tables (retries if SQL Server is still initializing)
    Shutdown: dispose the connection pool gracefully
    """
    logger.info("Backend starting — initialising database tables…")
    await init_db()
    logger.info("Database ready — server accepting requests")

    yield  # Application runs here

    logger.info("Backend shutting down — disposing connection pool")
    await engine.dispose()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Gesture Smart Lock API",
    description="REST API + WebSocket backend for the Gesture Smart Lock system.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the React/Vite dev server (and any configured production origin)
_cors_origin = os.getenv("CORS_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_cors_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(locks.router)
app.include_router(users.router)
app.include_router(gestures.router)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    Persistent WebSocket connection for real-time dashboard updates.

    The frontend is a receive-only consumer — it does not send messages back.
    We keep the connection alive with a receive loop; disconnects are handled
    gracefully by catching WebSocketDisconnect.
    """
    await manager.connect(ws)
    try:
        while True:
            # Block until the client sends something (or disconnects).
            # The frontend never sends messages, so this only exits on disconnect.
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Global error handlers
# ---------------------------------------------------------------------------

@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    """
    Catch unhandled SQLAlchemy errors and return a 503 response.

    This prevents raw database exceptions from leaking to the client.
    """
    logger.error("Unhandled database error on %s %s: %s", request.method, request.url, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "A database error occurred. Please try again."},
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health_check():
    """Simple liveness probe used by Docker Compose / load balancers."""
    return {"status": "ok"}
