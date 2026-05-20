"""
services/lock_service.py — Database operations for locks, states, modes, PINs, and logs.

All public functions are async and accept an AsyncSession as their first argument.
Write operations use `async with session.begin()` for automatic commit/rollback.
Read operations execute queries directly on the passed session.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import AccessLog, Lock, LockState, PinConfig, User
from schemas.api import LockCreate, LockUpdate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

async def get_all_users(db: AsyncSession) -> list[User]:
    """Return all users ordered by id."""
    result = await db.execute(select(User).order_by(User.id))
    return list(result.scalars().all())


async def get_user(db: AsyncSession, user_id: int) -> User | None:
    """Return a single user by id, or None if not found."""
    return await db.get(User, user_id)


async def create_user(db: AsyncSession, username: str, role: str) -> User:
    """
    Insert a new user.

    Raises IntegrityError (HTTP 409) if username already exists.
    """
    user = User(username=username, role=role)
    async with db.begin():
        db.add(user)
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    """
    Delete a user by id.

    Returns True if the row existed and was deleted, False otherwise.
    """
    user = await db.get(User, user_id)
    if user is None:
        return False
    async with db.begin():
        await db.delete(user)
    return True


# ---------------------------------------------------------------------------
# Lock CRUD
# ---------------------------------------------------------------------------

async def get_all_locks(db: AsyncSession) -> list[Lock]:
    """Return all locks ordered by id."""
    result = await db.execute(select(Lock).order_by(Lock.id))
    return list(result.scalars().all())


async def get_lock(db: AsyncSession, lock_id: int) -> Lock | None:
    """Return a single lock by id, or None if not found."""
    return await db.get(Lock, lock_id)


async def create_lock(db: AsyncSession, data: LockCreate) -> Lock:
    """Insert a new lock and return the created row."""
    lock = Lock(name=data.name, location=data.location, mode=data.mode)
    async with db.begin():
        db.add(lock)
    await db.refresh(lock)
    return lock


async def update_lock(
    db: AsyncSession, lock_id: int, data: LockUpdate
) -> Lock | None:
    """
    Partially update a lock's fields.

    Only non-None fields in `data` are applied. Returns the updated lock or
    None if the lock_id does not exist.
    """
    lock = await db.get(Lock, lock_id)
    if lock is None:
        return None
    async with db.begin():
        if data.name is not None:
            lock.name = data.name
        if data.location is not None:
            lock.location = data.location
        if data.mode is not None:
            lock.mode = data.mode
        db.add(lock)
    await db.refresh(lock)
    return lock


async def delete_lock(db: AsyncSession, lock_id: int) -> bool:
    """Delete a lock by id. Returns True on success, False if not found."""
    lock = await db.get(Lock, lock_id)
    if lock is None:
        return False
    async with db.begin():
        await db.delete(lock)
    return True


# ---------------------------------------------------------------------------
# Lock mode (entry / recording)
# ---------------------------------------------------------------------------

async def get_lock_mode(db: AsyncSession, lock_id: int) -> str | None:
    """
    Return the current mode for a lock ('entry' or 'recording').

    Returns None if the lock does not exist.
    """
    lock = await db.get(Lock, lock_id)
    return lock.mode if lock else None


async def set_lock_mode(
    db: AsyncSession, lock_id: int, mode: str
) -> Lock | None:
    """
    Update the mode column of a lock.

    Returns the updated lock or None if the lock_id does not exist.
    """
    lock = await db.get(Lock, lock_id)
    if lock is None:
        return None
    async with db.begin():
        lock.mode = mode
        db.add(lock)
    await db.refresh(lock)
    return lock


# ---------------------------------------------------------------------------
# Lock state (locked / unlocked) — append-only
# ---------------------------------------------------------------------------

async def get_lock_state(db: AsyncSession, lock_id: int) -> LockState | None:
    """
    Return the most recent state row for a lock (current state).

    The lock_states table is append-only; the current state is always the
    row with the highest `changed_at` for a given lock_id.
    """
    result = await db.execute(
        select(LockState)
        .where(LockState.lock_id == lock_id)
        .order_by(LockState.changed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def set_lock_state(
    db: AsyncSession,
    lock_id: int,
    state: str,
    changed_by: int | None,
    changed_at: datetime | None = None,
) -> LockState:
    """
    Insert a new lock_states row (append-only; never updates existing rows).

    Broadcasts a 'lock_state_changed' WebSocket event after the insert.
    `changed_at` defaults to the current UTC time if not provided.
    """
    from ws_manager import manager  # imported here to avoid circular imports

    entry = LockState(
        lock_id=lock_id,
        state=state,
        changed_by=changed_by,
        changed_at=changed_at or datetime.utcnow(),
    )
    async with db.begin():
        db.add(entry)
    await db.refresh(entry)

    # Broadcast real-time event to all WebSocket clients
    await manager.broadcast({
        "event": "lock_state_changed",
        "lock_id": lock_id,
        "state": state,
        "changed_at": entry.changed_at.isoformat(),
    })
    logger.info("Lock %d state → %s (changed_by=%s)", lock_id, state, changed_by)
    return entry


# ---------------------------------------------------------------------------
# PIN configuration
# ---------------------------------------------------------------------------

async def get_pin(db: AsyncSession, lock_id: int) -> PinConfig | None:
    """Return the active PIN config for a lock, or None if not set."""
    result = await db.execute(
        select(PinConfig).where(PinConfig.lock_id == lock_id)
    )
    return result.scalar_one_or_none()


async def save_pin(
    db: AsyncSession, lock_id: int, user_id: int, sequence: list[str]
) -> PinConfig:
    """
    Persist a new PIN for a lock.

    Deletes any existing PIN for the lock before inserting the new one so
    that only one PIN per lock is active at any time. Both operations run
    in a single transaction.
    """
    new_pin = PinConfig(
        lock_id=lock_id,
        user_id=user_id,
        sequence=json.dumps(sequence),
    )
    async with db.begin():
        # Delete old PIN (if any) within the same transaction
        await db.execute(
            delete(PinConfig).where(PinConfig.lock_id == lock_id)
        )
        db.add(new_pin)
    await db.refresh(new_pin)
    logger.info("PIN saved for lock %d: %s", lock_id, sequence)
    return new_pin


async def delete_pin(db: AsyncSession, lock_id: int) -> bool:
    """
    Remove the PIN for a lock, returning the lock to 'no PIN' state.

    Returns True if a PIN existed and was deleted, False otherwise.
    """
    result = await db.execute(
        select(PinConfig).where(PinConfig.lock_id == lock_id)
    )
    pin = result.scalar_one_or_none()
    if pin is None:
        return False
    async with db.begin():
        await db.delete(pin)
    logger.info("PIN deleted for lock %d", lock_id)
    return True


# ---------------------------------------------------------------------------
# Access log
# ---------------------------------------------------------------------------

async def get_access_log(
    db: AsyncSession, limit: int = 100
) -> list[AccessLog]:
    """Return the most recent access log entries (newest first)."""
    result = await db.execute(
        select(AccessLog)
        .order_by(AccessLog.timestamp.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_access_log_entry(
    db: AsyncSession,
    lock_id: int,
    user_id: int | None,
    timestamp: datetime,
    result: str,
    sequence: list[str],
) -> AccessLog:
    """Insert a new access log row for a verification attempt."""
    entry = AccessLog(
        lock_id=lock_id,
        user_id=user_id,
        timestamp=timestamp,
        result=result,
        gesture_sequence=json.dumps(sequence),
    )
    async with db.begin():
        db.add(entry)
    await db.refresh(entry)
    return entry
