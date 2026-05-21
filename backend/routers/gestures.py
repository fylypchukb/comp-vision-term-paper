"""
routers/gestures.py — Gesture verification endpoint and access log.

Prefix: /api

Endpoints:
  POST /gestures/verify  — called by CV module after each confirmed gesture
  GET  /access-log       — retrieve recent access log entries
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.api import AccessLogResponse, GestureVerifyRequest, GestureVerifyResponse
from services import lock_service, pin_service

router = APIRouter(prefix="/api", tags=["gestures"])


@router.post("/gestures/verify", response_model=GestureVerifyResponse)
async def verify_gesture(
    body: GestureVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive a confirmed gesture event from the CV module.

    The CV module sends this after a gesture has been held stable for 15 frames.
    The response status drives the CV module's next action:
      - "partial"  → keep accumulating the PIN sequence
      - "match"    → PIN matched; lock state was toggled
      - "fail"     → mismatch; CV module resets its sequence buffer
      - "recorded" → gesture acknowledged in recording mode

    Returns 404 if the lock_id is not found — this prevents FK constraint
    violations and gives the CV module a clear signal to check its configuration.
    """
    lock = await lock_service.get_lock(db, body.lock_id)
    if lock is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Lock {body.lock_id} not found. "
                "Check LOCK_ID in cv-module/.env matches a lock in the database."
            ),
        )

    return await pin_service.verify_gesture(
        db=db,
        lock_id=body.lock_id,
        gesture=body.gesture,
        sequence=body.sequence,
        mode=body.mode,
        timestamp=body.timestamp,
    )


@router.get("/access-log", response_model=list[AccessLogResponse])
async def get_access_log(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """
    Return recent access log entries (newest first).

    Query param `limit` controls how many rows to return (default 100).
    """
    entries = await lock_service.get_access_log(db, limit=limit)
    # Validate each ORM instance to trigger the JSON-parsing field validator
    return [AccessLogResponse.model_validate(e) for e in entries]
