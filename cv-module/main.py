"""
main.py — Entry point for the Gesture Smart Lock CV module.

Environment variables (loaded from .env if present):
    BACKEND_URL          : str   — FastAPI base URL (default: http://localhost:8000)
    CAMERA_INDEX         : int   — OpenCV camera index (default: 0)
    LOCK_ID              : int   — ID of the lock this instance controls (default: 1)
    DETECTION_CONFIDENCE : float — MediaPipe detection threshold (default: 0.7)
    TRACKING_CONFIDENCE  : float — MediaPipe tracking threshold (default: 0.5)
    DEBUG_DISPLAY        : bool  — Show CV preview window (default: false)
    REQUEST_TIMEOUT      : float — Seconds for backend HTTP timeout (default: 2.0)
    MODE_POLL_INTERVAL   : float — Seconds between mode-check polls (default: 2.0)
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from typing import Optional

import cv2
import requests
from dotenv import load_dotenv

from modules import GestureBuffer, GestureClassifier, HandDetector

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MAX_READ_FAILURES = 30
TARGET_FPS = 20
LOG_INTERVAL_FRAMES = 60  # Print status to console every N frames


def load_config() -> dict:
    """
    Load and validate environment configuration.

    Returns a dict of typed config values. Exits with code 1 on invalid input.
    """
    def _float(name: str, default: float) -> float:
        val = os.getenv(name, str(default))
        try:
            return float(val)
        except ValueError:
            logger.critical("Invalid float for %s: '%s'", name, val)
            sys.exit(1)

    def _int(name: str, default: int) -> int:
        val = os.getenv(name, str(default))
        try:
            return int(val)
        except ValueError:
            logger.critical("Invalid integer for %s: '%s'", name, val)
            sys.exit(1)

    def _bool(name: str, default: bool) -> bool:
        val = os.getenv(name, str(default)).lower()
        return val in ("1", "true", "yes")

    return {
        "backend_url":          os.getenv("BACKEND_URL", "http://localhost:8000"),
        "camera_index":         _int("CAMERA_INDEX", 0),
        "lock_id":              _int("LOCK_ID", 1),
        "detection_confidence": _float("DETECTION_CONFIDENCE", 0.7),
        "tracking_confidence":  _float("TRACKING_CONFIDENCE", 0.5),
        "debug_display":        _bool("DEBUG_DISPLAY", False),
        "request_timeout":      _float("REQUEST_TIMEOUT", 2.0),
        "mode_poll_interval":   _float("MODE_POLL_INTERVAL", 2.0),
    }


def build_debug_overlay(frame, ui_state: dict, fps: float) -> None:
    """
    Draw gesture label, stability counter, sequence, status, and FPS on frame in-place.
    """
    gesture = ui_state.get("current_gesture") or "---"
    stable = ui_state.get("stable_frames", 0)
    sequence = ui_state.get("sequence", [])
    status = ui_state.get("status", "")
    mode = ui_state.get("mode", "entry")

    lines = [
        f"Gesture: {gesture}  ({stable}/15)",
        f"Sequence: {' > '.join(sequence) if sequence else 'empty'}",
        f"Status: {status}   Mode: {mode}",
        f"FPS: {fps:.1f}",
    ]

    y = 30
    for line in lines:
        cv2.putText(
            frame, line, (10, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2, cv2.LINE_AA,
        )
        y += 30


def poll_mode(backend_url: str, lock_id: int, timeout: float) -> Optional[str]:
    """
    GET {backend_url}/api/locks/{lock_id}/mode.

    Returns 'entry', 'recording', or None on any error.
    """
    url = f"{backend_url.rstrip('/')}/api/locks/{lock_id}/mode"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("mode")
    except Exception:
        return None


def start_mode_poll_thread(
    backend_url: str,
    lock_id: int,
    timeout: float,
    interval: float,
    stop_event: threading.Event,
) -> dict:
    """
    Spawn a background daemon thread that polls the backend for mode changes.

    Returns a shared dict with key "mode" that the main loop reads.
    The thread never blocks the camera loop — all HTTP waits happen off the
    main thread.
    """
    result: dict = {"mode": None}

    def _worker() -> None:
        while not stop_event.wait(interval):
            mode = poll_mode(backend_url, lock_id, timeout)
            if mode:
                result["mode"] = mode

    thread = threading.Thread(target=_worker, daemon=True, name="mode-poll")
    thread.start()
    return result


def main() -> None:
    """Main camera loop."""
    config = load_config()

    cap = cv2.VideoCapture(config["camera_index"])
    if not cap.isOpened():
        logger.critical("Cannot open camera index %d", config["camera_index"])
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    detector = HandDetector(
        min_detection_confidence=config["detection_confidence"],
        min_tracking_confidence=config["tracking_confidence"],
    )
    classifier = GestureClassifier()
    buffer = GestureBuffer(
        backend_url=config["backend_url"],
        lock_id=config["lock_id"],
        request_timeout=config["request_timeout"],
    )

    # Background thread handles mode polling without blocking the camera loop
    stop_event = threading.Event()
    mode_result = start_mode_poll_thread(
        config["backend_url"],
        config["lock_id"],
        config["request_timeout"],
        config["mode_poll_interval"],
        stop_event,
    )

    shutdown_requested = False

    def _handle_signal(sig, _frame):
        nonlocal shutdown_requested
        logger.info("Signal %s received — shutting down", sig)
        shutdown_requested = True

    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        "CV module started | camera=%d  lock=%d  backend=%s  debug_display=%s",
        config["camera_index"], config["lock_id"],
        config["backend_url"], config["debug_display"],
    )

    target_frame_time = 1.0 / TARGET_FPS
    consecutive_failures = 0
    frame_count = 0
    fps_window_start = time.monotonic()
    current_fps = 0.0

    try:
        while not shutdown_requested:
            frame_start = time.monotonic()

            ret, frame = cap.read()
            if not ret:
                consecutive_failures += 1
                logger.warning("Frame read failed (%d/%d)", consecutive_failures, MAX_READ_FAILURES)
                if consecutive_failures >= MAX_READ_FAILURES:
                    logger.critical("Too many consecutive frame failures — exiting")
                    break
                continue

            consecutive_failures = 0
            frame_count += 1

            # Detect landmarks
            landmarks, annotated_frame = detector.process_frame(frame)

            # Classify gesture (None when no hand visible)
            gesture = classifier.classify(landmarks) if landmarks else None

            # Update buffer state machine
            ui_state = buffer.update(gesture)

            # Apply mode change from background poll thread
            new_mode = mode_result.get("mode")
            if new_mode and new_mode != buffer.mode:
                try:
                    buffer.set_mode(new_mode)
                    mode_result["mode"] = None  # Consume the update
                except ValueError as exc:
                    logger.warning("Invalid mode from backend: %s", exc)

            # Recalculate FPS every LOG_INTERVAL_FRAMES frames
            if frame_count % LOG_INTERVAL_FRAMES == 0:
                elapsed_window = time.monotonic() - fps_window_start
                current_fps = LOG_INTERVAL_FRAMES / elapsed_window if elapsed_window > 0 else 0.0
                fps_window_start = time.monotonic()
                logger.info(
                    "FPS: %.1f | gesture: %s | stable: %d/15 | sequence: %s | status: %s",
                    current_fps,
                    ui_state["current_gesture"] or "none",
                    ui_state["stable_frames"],
                    ui_state["sequence"] or "[]",
                    ui_state["status"],
                )

            if config["debug_display"]:
                build_debug_overlay(annotated_frame, ui_state, current_fps)
                cv2.imshow("Gesture Smart Lock", annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            # Sleep only the remaining frame budget to maintain target FPS
            elapsed = time.monotonic() - frame_start
            sleep_time = target_frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    finally:
        stop_event.set()  # Signal background thread to exit
        cap.release()
        detector.close()
        if config["debug_display"]:
            cv2.destroyAllWindows()
        logger.info("CV module stopped")


if __name__ == "__main__":
    main()
