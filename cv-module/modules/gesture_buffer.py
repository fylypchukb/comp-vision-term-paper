"""
gesture_buffer.py — Temporal stability and PIN sequence management.

Handles:
  - Frame-level stability counting (15-frame hold required)
  - Post-confirmation 2-second cooldown
  - Sequence-level 10-second inactivity timeout
  - HTTP communication with the FastAPI backend
  - Recording mode for PIN setup
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------
REQUIRED_STABLE_FRAMES: int = 15
COOLDOWN_SECONDS: float = 2.0
INACTIVITY_TIMEOUT_SECONDS: float = 10.0
MIN_PIN_LENGTH: int = 3
MAX_PIN_LENGTH: int = 6


class GestureBuffer:
    """
    Temporal filter and PIN sequence accumulator.

    Parameters
    ----------
    backend_url : str
        Full base URL of the FastAPI backend, e.g. 'http://backend:8000'.
    lock_id : int
        ID of the lock this CV instance is controlling.
    request_timeout : float
        Seconds to wait for a backend HTTP response before giving up.
    """

    def __init__(
        self,
        backend_url: str,
        lock_id: int,
        request_timeout: float = 2.0,
    ) -> None:
        self._backend_url = backend_url.rstrip("/")
        self._lock_id = lock_id
        self._request_timeout = request_timeout

        # State machine internals
        self._mode: str = "entry"
        self._sequence: list[str] = []
        self._stable_gesture: Optional[str] = None
        self._stable_count: int = 0
        # "idle" | "collecting" | "cooldown"
        self._state: str = "idle"
        self._cooldown_start: float = 0.0
        self._last_confirmed_at: float = time.monotonic()
        self._last_server_response: Optional[dict] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        """Return current mode: 'entry' or 'recording'."""
        return self._mode

    def set_mode(self, mode: str) -> None:
        """
        Switch between 'entry' and 'recording' modes.

        Resets all transient state when switching.
        """
        if mode not in ("entry", "recording"):
            raise ValueError(f"Invalid mode '{mode}'. Must be 'entry' or 'recording'.")
        if mode != self._mode:
            logger.info("Switching mode: %s → %s", self._mode, mode)
            self._mode = mode
            self._reset_transient_state()

    def update(self, gesture: Optional[str]) -> dict:
        """
        Feed the current frame's classified gesture into the buffer.

        Must be called once per captured frame.

        Parameters
        ----------
        gesture : str or None
            Gesture name from GestureClassifier, or None if no hand visible.

        Returns
        -------
        dict — UI state snapshot with keys: current_gesture, stable_frames,
               sequence, mode, status, last_server_response.
        """
        # Check sequence-level inactivity before processing the frame
        self._check_inactivity()

        # While in cooldown, do nothing until the cooldown period expires
        if self._state == "cooldown":
            if time.monotonic() - self._cooldown_start >= COOLDOWN_SECONDS:
                self._state = "idle"
                self._stable_gesture = None
                self._stable_count = 0
            else:
                return self._snapshot("cooldown", gesture)

        # No hand or gesture changed — reset frame counter
        if gesture is None or gesture != self._stable_gesture:
            self._stable_gesture = gesture
            self._stable_count = 1 if gesture is not None else 0
            self._state = "collecting" if gesture is not None else "idle"
            return self._snapshot("collecting" if gesture else "idle", gesture)

        # Same gesture as previous frame — increment counter
        self._stable_count += 1

        if self._stable_count >= REQUIRED_STABLE_FRAMES:
            self._confirm_gesture(gesture)
            return self._snapshot("confirmed", gesture)

        return self._snapshot("collecting", gesture)

    def reset_sequence(self) -> None:
        """Discard the current PIN sequence and restart inactivity timer."""
        logger.info("Sequence reset. Was: %s", self._sequence)
        self._sequence = []
        self._last_confirmed_at = time.monotonic()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_inactivity(self) -> None:
        """Reset sequence if 10 seconds have passed since the last confirmed gesture."""
        if (
            self._sequence
            and time.monotonic() - self._last_confirmed_at > INACTIVITY_TIMEOUT_SECONDS
        ):
            logger.info("Inactivity timeout — resetting sequence")
            self.reset_sequence()

    def _confirm_gesture(self, gesture: str) -> None:
        """
        Called when stable frame count reaches REQUIRED_STABLE_FRAMES.

        Appends gesture to sequence, fires HTTP POST, enters cooldown.
        """
        self._sequence.append(gesture)
        self._last_confirmed_at = time.monotonic()
        logger.info("Gesture confirmed: %s | Sequence: %s", gesture, self._sequence)

        response = self._send_to_backend(gesture)
        if response:
            self._last_server_response = response
            self._handle_server_response(response)

        # Enter cooldown regardless of server response
        self._state = "cooldown"
        self._cooldown_start = time.monotonic()
        self._stable_count = 0

    def _send_to_backend(self, gesture: str) -> Optional[dict]:
        """
        HTTP POST the current gesture and sequence to the backend.

        Returns parsed JSON response on success, None on any network/HTTP error.
        """
        url = f"{self._backend_url}/api/gestures/verify"
        payload = {
            "lock_id": self._lock_id,
            "gesture": gesture,
            "sequence": list(self._sequence),
            "mode": self._mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            resp = requests.post(url, json=payload, timeout=self._request_timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            logger.error("Backend unreachable — sequence continues locally")
        except requests.exceptions.Timeout:
            logger.warning("Backend response timed out (%.1fs)", self._request_timeout)
        except requests.exceptions.HTTPError as exc:
            logger.error(
                "Backend returned HTTP %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
        return None

    def _handle_server_response(self, response: dict) -> None:
        """
        Interpret the server's match status and mutate buffer state.

        Expected response schema:
            {"status": "partial" | "match" | "fail" | "recorded", ...}
        """
        status = response.get("status")

        if status == "partial":
            pass  # Continue accumulating
        elif status == "match":
            logger.info("PIN matched — lock state: %s", response.get("lock_state"))
            self.reset_sequence()
        elif status == "fail":
            logger.info("PIN mismatch — resetting sequence")
            self.reset_sequence()
        elif status == "recorded":
            logger.info(
                "Gesture recorded (recording mode). Count: %d",
                response.get("gesture_count", len(self._sequence)),
            )
        else:
            logger.warning("Unknown server status: %s", status)

    def _reset_transient_state(self) -> None:
        """Reset all per-gesture and sequence state without touching config."""
        self._sequence = []
        self._stable_gesture = None
        self._stable_count = 0
        self._state = "idle"
        self._cooldown_start = 0.0
        self._last_confirmed_at = time.monotonic()
        self._last_server_response = None

    def _snapshot(self, status: str, current_gesture: Optional[str]) -> dict:
        """Build the UI state dict returned by update()."""
        return {
            "current_gesture": current_gesture,
            "stable_frames": self._stable_count,
            "sequence": list(self._sequence),
            "mode": self._mode,
            "status": status,
            "last_server_response": self._last_server_response,
        }
