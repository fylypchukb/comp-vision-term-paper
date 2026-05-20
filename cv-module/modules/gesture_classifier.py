"""
gesture_classifier.py — Rule-based gesture recognition.

All classification is purely geometric: no ML model is loaded.
Landmark coordinates come from MediaPipe and are already normalized
to [0, 1] relative to the image dimensions.
"""

from __future__ import annotations

import math
from typing import Optional

from .hand_detector import HandLandmarks

# ---------------------------------------------------------------------------
# Landmark index constants — MediaPipe hand topology
# ---------------------------------------------------------------------------
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_PIP, RING_DIP, RING_TIP = 13, 14, 15, 16
PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP = 17, 18, 19, 20

# Normalized-coordinate distance threshold for the OK circle gesture
OK_DISTANCE_THRESHOLD: float = 0.05


class GestureClassifier:
    """
    Classifies a detected hand into one of 12 named gestures.

    The classifier is stateless — it operates on a single frame's
    landmark snapshot with no temporal information.
    """

    # Checked top-to-bottom; first match wins.
    # OK must precede OPEN_PALM because OK has three extended fingers that
    # would satisfy the OPEN_PALM rule without the circle-distance gate.
    GESTURE_PRIORITY: list[str] = [
        "OK",
        "OPEN_PALM",
        "FIST",
        "INDEX_UP",
        "PEACE",
        "THREE",
        "FOUR",
        "THUMBS_UP",
        "THUMBS_DOWN",
        "PINKY_UP",
        "ROCK",
        "CALL_ME",
    ]

    def classify(self, landmarks: HandLandmarks) -> Optional[str]:
        """
        Return the gesture name matching the given landmarks, or None.

        Parameters
        ----------
        landmarks : HandLandmarks
            21 normalized landmark points plus handedness string.

        Returns
        -------
        str or None
            One of the 12 gesture codes, or None if no rule matches.
        """
        pts = landmarks.points
        handedness = landmarks.handedness
        states = self._finger_states(pts, handedness)

        dispatch = {
            "OK":          lambda: self._check_ok(states, pts),
            "OPEN_PALM":   lambda: self._check_open_palm(states),
            "FIST":        lambda: self._check_fist(states),
            "INDEX_UP":    lambda: self._check_index_up(states),
            "PEACE":       lambda: self._check_peace(states),
            "THREE":       lambda: self._check_three(states),
            "FOUR":        lambda: self._check_four(states),
            "THUMBS_UP":   lambda: self._check_thumbs_up(states, pts),
            "THUMBS_DOWN": lambda: self._check_thumbs_down(states, pts),
            "PINKY_UP":    lambda: self._check_pinky_up(states),
            "ROCK":        lambda: self._check_rock(states),
            "CALL_ME":     lambda: self._check_call_me(states),
        }

        for name in self.GESTURE_PRIORITY:
            if dispatch[name]():
                return name

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _finger_states(
        self, pts: list[tuple[float, float, float]], handedness: str
    ) -> dict[str, bool]:
        """
        Compute extended (True) / curled (False) for each finger.

        Index, Middle, Ring, Pinky use Y-axis comparison (lower y = higher on
        screen). Thumb uses X-axis; direction is mirrored for left hands.
        """
        index_ext  = pts[INDEX_TIP][1]  < pts[INDEX_PIP][1]
        middle_ext = pts[MIDDLE_TIP][1] < pts[MIDDLE_PIP][1]
        ring_ext   = pts[RING_TIP][1]   < pts[RING_PIP][1]
        pinky_ext  = pts[PINKY_TIP][1]  < pts[PINKY_PIP][1]

        # Thumb moves along the X axis; direction depends on hand side
        if handedness == "Right":
            thumb_ext = pts[THUMB_TIP][0] < pts[THUMB_IP][0]
        else:
            thumb_ext = pts[THUMB_TIP][0] > pts[THUMB_IP][0]

        return {
            "thumb":  thumb_ext,
            "index":  index_ext,
            "middle": middle_ext,
            "ring":   ring_ext,
            "pinky":  pinky_ext,
        }

    def _is_pointing_up(self, pts: list[tuple[float, float, float]]) -> bool:
        """Return True when hand is oriented upright (middle MCP above wrist)."""
        return pts[MIDDLE_MCP][1] < pts[WRIST][1]

    def _thumb_tip_below_mcp(self, pts: list[tuple[float, float, float]]) -> bool:
        """Return True when thumb TIP is below thumb MCP — used for THUMBS_DOWN."""
        return pts[THUMB_TIP][1] > pts[THUMB_MCP][1]

    def _ok_circle_closed(self, pts: list[tuple[float, float, float]]) -> bool:
        """Return True when index tip and thumb tip are close enough to form the OK circle."""
        dx = pts[INDEX_TIP][0] - pts[THUMB_TIP][0]
        dy = pts[INDEX_TIP][1] - pts[THUMB_TIP][1]
        return math.hypot(dx, dy) < OK_DISTANCE_THRESHOLD

    # ------------------------------------------------------------------
    # Per-gesture checks
    # ------------------------------------------------------------------

    def _check_ok(self, states: dict, pts: list) -> bool:
        return (
            self._ok_circle_closed(pts)
            and states["middle"]
            and states["ring"]
            and states["pinky"]
        )

    def _check_open_palm(self, states: dict) -> bool:
        return all(states.values())

    def _check_fist(self, states: dict) -> bool:
        return not any(states.values())

    def _check_index_up(self, states: dict) -> bool:
        return (
            states["index"]
            and not states["middle"]
            and not states["ring"]
            and not states["pinky"]
            and not states["thumb"]
        )

    def _check_peace(self, states: dict) -> bool:
        return (
            states["index"]
            and states["middle"]
            and not states["ring"]
            and not states["pinky"]
            and not states["thumb"]
        )

    def _check_three(self, states: dict) -> bool:
        return (
            states["index"]
            and states["middle"]
            and states["ring"]
            and not states["pinky"]
            and not states["thumb"]
        )

    def _check_four(self, states: dict) -> bool:
        return (
            states["index"]
            and states["middle"]
            and states["ring"]
            and states["pinky"]
            and not states["thumb"]
        )

    def _check_thumbs_up(self, states: dict, pts: list) -> bool:
        return (
            states["thumb"]
            and not states["index"]
            and not states["middle"]
            and not states["ring"]
            and not states["pinky"]
            and self._is_pointing_up(pts)
        )

    def _check_thumbs_down(self, states: dict, pts: list) -> bool:
        return (
            states["thumb"]
            and not states["index"]
            and not states["middle"]
            and not states["ring"]
            and not states["pinky"]
            and self._thumb_tip_below_mcp(pts)
        )

    def _check_pinky_up(self, states: dict) -> bool:
        return (
            states["pinky"]
            and not states["index"]
            and not states["middle"]
            and not states["ring"]
            and not states["thumb"]
        )

    def _check_rock(self, states: dict) -> bool:
        return (
            states["index"]
            and states["pinky"]
            and not states["middle"]
            and not states["ring"]
            and not states["thumb"]
        )

    def _check_call_me(self, states: dict) -> bool:
        return (
            states["thumb"]
            and states["pinky"]
            and not states["index"]
            and not states["middle"]
            and not states["ring"]
        )
