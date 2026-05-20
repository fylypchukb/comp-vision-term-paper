"""
routers/locks.py — REST endpoints for lock management.

Prefix: /api/locks

Endpoints:
  GET    /                     — list all locks
  POST   /                     — create a lock
  GET    /{lock_id}            — get a single lock
  PUT    /{lock_id}            — update lock fields
  DELETE /{lock_id}            — delete a lock
  GET    /{lock_id}/state      — get current lock state
  PUT    /{lock_id}/state      — manually change lock state
  GET    /{lock_id}/mode       — get CV mode (polled by CV module every 2 s)
  POST   /{lock_id}/mode       — set CV mode (called by frontend)
  GET    /{lock_id}/pin        — get current PIN config
  POST   /{lock_id}/pin        — save a new PIN (called after recording session)
  DELETE /{lock_id}/pin        — reset / delete PIN
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.api import (
    LockCreate,
    LockModeResponse,
    LockModeSet,
    LockResponse,
    LockStateResponse,
    LockStateUpdate,
    LockUpdate,
    PinConfigResponse,
    PinSave,
)
from services import lock_service

router = APIRouter(prefix="/api/locks", tags=["locks"])


# ---------------------------------------------------------------------------
# Lock CRUD
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[LockResponse])
async def list_locks(db: AsyncSession = Depends(get_db)):
    """Return all locks."""
    return await lock_service.get_all_locks(db)


@router.post("/", response_model=LockResponse, status_code=201)
async def create_lock(data: LockCreate, db: AsyncSession = Depends(get_db)):
    """Create a new lock."""
    return await lock_service.create_lock(db, data)


@router.get("/{lock_id}", response_model=LockResponse)
async def get_lock(lock_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single lock by ID."""
    lock = await lock_service.get_lock(db, lock_id)
    if lock is None:
        raise HTTPException(status_code=404, detail="Lock not found")
    return lock


@router.put("/{lock_id}", response_model=LockResponse)
async def update_lock(
    lock_id: int, data: LockUpdate, db: AsyncSession = Depends(get_db)
):
    """Update lock fields (partial update — only non-null fields are applied)."""
    lock = await lock_service.update_lock(db, lock_id, data)
    if lock is None:
        raise HTTPException(status_code=404, detail="Lock not found")
    return lock


@router.delete("/{lock_id}", status_code=204)
async def delete_lock(lock_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a lock and all its associated records."""
    deleted = await lock_service.delete_lock(db, lock_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Lock not found")


# ---------------------------------------------------------------------------
# Lock state
# ---------------------------------------------------------------------------

@router.get("/{lock_id}/state", response_model=LockStateResponse)
async def get_lock_state(lock_id: int, db: AsyncSession = Depends(get_db)):
    """Return the current lock state (latest entry in lock_states table)."""
    # Verify the lock exists first
    lock = await lock_service.get_lock(db, lock_id)
    if lock is None:
        raise HTTPException(status_code=404, detail="Lock not found")

    state = await lock_service.get_lock_state(db, lock_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No state recorded for this lock yet")
    return state


@router.put("/{lock_id}/state", response_model=LockStateResponse)
async def set_lock_state(
    lock_id: int, data: LockStateUpdate, db: AsyncSession = Depends(get_db)
):
    """Manually change the lock state (e.g. from the dashboard)."""
    lock = await lock_service.get_lock(db, lock_id)
    if lock is None:
        raise HTTPException(status_code=404, detail="Lock not found")
    return await lock_service.set_lock_state(db, lock_id, data.state, data.changed_by)


# ---------------------------------------------------------------------------
# Lock mode (entry / recording) — used by CV module and frontend
# ---------------------------------------------------------------------------

@router.get("/{lock_id}/mode", response_model=LockModeResponse)
async def get_lock_mode(lock_id: int, db: AsyncSession = Depends(get_db)):
    """
    Return the current CV mode for a lock.

    Called by the CV module every MODE_POLL_INTERVAL seconds to detect
    when the frontend has switched to recording mode.
    """
    mode = await lock_service.get_lock_mode(db, lock_id)
    if mode is None:
        raise HTTPException(status_code=404, detail="Lock not found")
    return LockModeResponse(mode=mode)


@router.post("/{lock_id}/mode", response_model=LockModeResponse)
async def set_lock_mode(
    lock_id: int, data: LockModeSet, db: AsyncSession = Depends(get_db)
):
    """
    Switch the CV mode for a lock (called by the frontend dashboard).

    The CV module picks up the change on its next poll.
    """
    lock = await lock_service.set_lock_mode(db, lock_id, data.mode)
    if lock is None:
        raise HTTPException(status_code=404, detail="Lock not found")
    return LockModeResponse(mode=lock.mode)


# ---------------------------------------------------------------------------
# PIN configuration
# ---------------------------------------------------------------------------

@router.get("/{lock_id}/pin", response_model=PinConfigResponse)
async def get_pin(lock_id: int, db: AsyncSession = Depends(get_db)):
    """Return the current PIN config for a lock."""
    pin = await lock_service.get_pin(db, lock_id)
    if pin is None:
        raise HTTPException(
            status_code=404, detail="No PIN configured for this lock"
        )
    return PinConfigResponse.model_validate(pin)


@router.post("/{lock_id}/pin", response_model=PinConfigResponse, status_code=201)
async def save_pin(
    lock_id: int, data: PinSave, db: AsyncSession = Depends(get_db)
):
    """
    Save (or replace) the PIN for a lock.

    Called by the frontend after a recording session when the user clicks "Save".
    Replaces any existing PIN in a single transaction.
    """
    lock = await lock_service.get_lock(db, lock_id)
    if lock is None:
        raise HTTPException(status_code=404, detail="Lock not found")

    # Ensure the referenced user exists
    user = await lock_service.get_user(db, data.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    pin = await lock_service.save_pin(db, lock_id, data.user_id, data.sequence)
    return PinConfigResponse.model_validate(pin)


@router.delete("/{lock_id}/pin", status_code=204)
async def delete_pin(lock_id: int, db: AsyncSession = Depends(get_db)):
    """
    Reset the PIN for a lock.

    After deletion the lock enters 'no PIN' state — unavailable for gesture control
    until a new PIN is configured.
    """
    deleted = await lock_service.delete_pin(db, lock_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail="No PIN configured for this lock"
        )
