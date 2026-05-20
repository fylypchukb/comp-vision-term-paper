"""
services/pin_service.py — PIN verification logic and gesture event orchestration.

The main entry point is `verify_gesture()`, which is called by the gestures router
for every POST /api/gestures/verify request from the CV module.

PIN comparison algorithm:
  stored  = ["OPEN_PALM", "FIST", "INDEX_UP"]   (from DB)
  incoming = ["OPEN_PALM"]                        → "partial"  (prefix match)
  incoming = ["OPEN_PALM", "FIST", "INDEX_UP"]   → "match"    (full match)
  incoming = ["OPEN_PALM", "THUMBS_UP"]           → "fail"     (wrong gesture)
  incoming = ["OPEN_PALM", "FIST", "INDEX_UP", "PEACE"] → "fail" (too long)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from schemas.api import GestureVerifyResponse
from services.lock_service import (
    create_access_log_entry,
    get_lock_state,
    get_pin,
    set_lock_state,
)
from ws_manager import manager

logger = logging.getLogger(__name__)


async def verify_gesture(
    db: AsyncSession,
    lock_id: int,
    gesture: str,
    sequence: list[str],
    mode: str,
    timestamp: datetime,
) -> GestureVerifyResponse:
    """
    Core gesture verification handler.

    Handles both 'entry' mode (PIN comparison) and 'recording' mode
    (acknowledgement + WebSocket progress event).

    Parameters
    ----------
    db       : Open async database session.
    lock_id  : ID of the lock being operated.
    gesture  : The gesture that was just confirmed by the CV module.
    sequence : Full gesture sequence accumulated so far (including `gesture`).
    mode     : 'entry' or 'recording'.
    timestamp: UTC timestamp of the gesture event.

    Returns
    -------
    GestureVerifyResponse with status: 'partial' | 'match' | 'fail' | 'recorded'.
    """
    if mode == "recording":
        return await _handle_recording(lock_id, gesture, sequence)

    return await _handle_entry(db, lock_id, gesture, sequence, timestamp)


# ---------------------------------------------------------------------------
# Recording mode
# ---------------------------------------------------------------------------

async def _handle_recording(
    lock_id: int, gesture: str, sequence: list[str]
) -> GestureVerifyResponse:
    """
    Acknowledge a gesture during PIN recording and push a WebSocket event.

    The PIN is NOT saved here — the frontend calls POST /api/locks/{id}/pin
    with the complete sequence after the user clicks "Save".
    """
    await manager.broadcast({
        "event": "pin_recording_update",
        "lock_id": lock_id,
        "gesture": gesture,
        "gesture_count": len(sequence),
        "sequence": sequence,
    })
    logger.info(
        "Recording — lock %d: gesture '%s' (%d/%d max)",
        lock_id, gesture, len(sequence), 6,
    )
    return GestureVerifyResponse(status="recorded", gesture_count=len(sequence))


# ---------------------------------------------------------------------------
# Entry mode
# ---------------------------------------------------------------------------

async def _handle_entry(
    db: AsyncSession,
    lock_id: int,
    gesture: str,
    sequence: list[str],
    timestamp: datetime,
) -> GestureVerifyResponse:
    """Compare the incoming sequence against the stored PIN and act accordingly."""
    pin_config = await get_pin(db, lock_id)

    # No PIN configured → always fail (lock is unavailable for gesture control)
    if pin_config is None:
        logger.info("Lock %d has no PIN configured — returning fail", lock_id)
        await create_access_log_entry(db, lock_id, None, timestamp, "fail", sequence)
        return GestureVerifyResponse(status="fail")

    stored: list[str] = json.loads(pin_config.sequence)
    comparison = _compare_sequences(incoming=sequence, stored=stored)

    if comparison == "match":
        return await _handle_match(db, lock_id, sequence, timestamp)

    if comparison == "partial":
        return await _handle_partial(lock_id, gesture, sequence)

    # "fail"
    return await _handle_fail(db, lock_id, gesture, sequence, timestamp)


async def _handle_match(
    db: AsyncSession,
    lock_id: int,
    sequence: list[str],
    timestamp: datetime,
) -> GestureVerifyResponse:
    """
    Full PIN match — toggle the lock state and log success.

    Toggling: locked → unlocked → locked → ...
    """
    current_state = await get_lock_state(db, lock_id)
    # Default to "locked" if no state has been recorded yet
    new_state = "unlocked" if (current_state is None or current_state.state == "locked") else "locked"

    await set_lock_state(db, lock_id, new_state, changed_by=None, changed_at=timestamp)
    await create_access_log_entry(db, lock_id, None, timestamp, "success", sequence)

    logger.info("Lock %d PIN matched — state → %s", lock_id, new_state)
    return GestureVerifyResponse(status="match", lock_state=new_state)


async def _handle_partial(
    lock_id: int, gesture: str, sequence: list[str]
) -> GestureVerifyResponse:
    """
    Sequence is a valid prefix — acknowledge and push a WebSocket progress event.
    """
    await manager.broadcast({
        "event": "gesture_event",
        "lock_id": lock_id,
        "gesture": gesture,
        "sequence": sequence,
        "status": "partial",
    })
    logger.info("Lock %d partial match: %s", lock_id, sequence)
    return GestureVerifyResponse(status="partial")


async def _handle_fail(
    db: AsyncSession,
    lock_id: int,
    gesture: str,
    sequence: list[str],
    timestamp: datetime,
) -> GestureVerifyResponse:
    """Sequence does not match — log the failed attempt and push a WebSocket event."""
    await create_access_log_entry(db, lock_id, None, timestamp, "fail", sequence)
    await manager.broadcast({
        "event": "gesture_event",
        "lock_id": lock_id,
        "gesture": gesture,
        "sequence": sequence,
        "status": "fail",
    })
    logger.info("Lock %d PIN mismatch at sequence: %s", lock_id, sequence)
    return GestureVerifyResponse(status="fail")


# ---------------------------------------------------------------------------
# Pure comparison helper (easy to unit-test)
# ---------------------------------------------------------------------------

def _compare_sequences(
    incoming: list[str], stored: list[str]
) -> str:
    """
    Compare an incoming gesture sequence against the stored PIN.

    Returns:
      "partial" — incoming is a non-empty prefix of stored
      "match"   — incoming equals stored exactly
      "fail"    — incoming diverges from stored or exceeds its length
    """
    # Sequence longer than PIN can never be correct
    if len(incoming) > len(stored):
        return "fail"
    # Check if incoming matches the beginning of stored
    if incoming == stored[: len(incoming)]:
        return "match" if len(incoming) == len(stored) else "partial"
    return "fail"
