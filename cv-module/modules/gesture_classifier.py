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

# How far (in normalized Y units) the thumb tip must be above/below thumb MCP
# before it counts as "pointing up" or "pointing down".
# A plain fist has the thumb roughly level with the MCP, so it falls below this
# threshold and is not confused with THUMBS_UP / THUMBS_DOWN.
THUMB_VERTICAL_THRESHOLD: float = 0.04

# Minimum X-axis distance (normalized) between MIDDLE_TIP and RING_TIP that
# confirms the Vulcan split.
VULCAN_SPREAD_THRESHOLD: float = 0.08

# Maximum X-axis distance (normalized) allowed between the fingers WITHIN each
# pair (index+middle, ring+pinky).  Keeps the two pairs visibly "connected" and
# prevents a casually spread FOUR from triggering Vulcan.
VULCAN_PAIR_THRESHOLD: float = 0.05

# How far (normalized Y units) the thumb tip must sit ABOVE the middle-finger
# MCP (knuckle) to confirm the raised-thumb "finger gun" pose.
# Using MIDDLE_MCP as the reference (not THUMB_MCP) avoids the false-positive
# on INDEX_UP: a resting thumb lives at or below knuckle level, while a
# gun-pose thumb is clearly above it.
FINGER_GUN_THUMB_THRESHOLD: float = 0.05


class GestureClassifier:
    """
    Classifies a detected hand into one of 12 named gestures.

    The classifier is stateless — it operates on a single frame's
    landmark snapshot with no temporal information.
    """

    # Checked top-to-bottom; first match wins.
    # OK must precede OPEN_PALM because OK has three extended fingers that
    # would satisfy the OPEN_PALM rule without the circle-distance gate.
    #
    # THUMBS_UP and THUMBS_DOWN are intentionally excluded:
    #  - THUMBS_UP is indistinguishable from FIST with simple Y/X axis checks
    #    (the thumb MCP sits near the wrist, so even a curled thumb tip is
    #    often well above it).
    #  - THUMBS_DOWN requires inverted-hand detection; an inverted hand flips
    #    all four Y-axis finger checks, making curled fingers read as extended
    #    and triggering OPEN_PALM.
    GESTURE_PRIORITY: list[str] = [
        "OK",
        "VULCAN",      # before OPEN_PALM: Vulcan with thumb out = all-states-True,
                       #   only the spread gate distinguishes it from open palm.
        "OPEN_PALM",
        "FIST",
        "FINGER_GUN",  # before INDEX_UP: finger-gun thumb points up so X-axis
                       #   states["thumb"] = False, making it look like INDEX_UP.
        "INDEX_UP",
        "PEACE",
        "THREE",
        "FOUR",        # after VULCAN — same 4 fingers, no spread
        "PINKY_UP",
        "ROCK",
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
            "OK":         lambda: self._check_ok(states, pts),
            "VULCAN":     lambda: self._check_vulcan(states, pts),
            "OPEN_PALM":  lambda: self._check_open_palm(states),
            "FIST":       lambda: self._check_fist(states),
            "FINGER_GUN": lambda: self._check_finger_gun(states, pts),
            "INDEX_UP":   lambda: self._check_index_up(states),
            "PEACE":      lambda: self._check_peace(states),
            "THREE":      lambda: self._check_three(states),
            "FOUR":       lambda: self._check_four(states),
            "PINKY_UP":   lambda: self._check_pinky_up(states),
            "ROCK":       lambda: self._check_rock(states),
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
        """Return True when thumb TIP is clearly below thumb MCP — used for THUMBS_DOWN.

        Uses THUMB_VERTICAL_THRESHOLD so a resting/fist thumb (roughly level
        with the MCP) does not trigger this check.
        """
        return pts[THUMB_TIP][1] - pts[THUMB_MCP][1] > THUMB_VERTICAL_THRESHOLD

    def _thumb_points_up(self, pts: list[tuple[float, float, float]]) -> bool:
        """Return True when thumb TIP is clearly above thumb MCP — used for THUMBS_UP.

        Uses THUMB_VERTICAL_THRESHOLD so a resting/fist thumb does not
        trigger this check.  The Y-axis comparison is required because the
        existing X-axis check in _finger_states returns False when the thumb
        points straight up, which otherwise causes FIST to fire instead.
        """
        return pts[THUMB_MCP][1] - pts[THUMB_TIP][1] > THUMB_VERTICAL_THRESHOLD

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
        # Thumb is intentionally ignored: in a real fist the thumb rests in
        # many different positions (tucked over fingers, pointing sideways,
        # etc.) and the X-axis check is unreliable for it.  The four main
        # fingers being curled is sufficient to identify a fist.
        return (
            not states["index"]
            and not states["middle"]
            and not states["ring"]
            and not states["pinky"]
        )

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
        # Use Y-axis check (_thumb_points_up) instead of the X-axis
        # states["thumb"]: the X-axis check returns False when the thumb
        # points straight up, which was previously causing FIST to fire.
        return (
            self._thumb_points_up(pts)
            and not states["index"]
            and not states["middle"]
            and not states["ring"]
            and not states["pinky"]
            and self._is_pointing_up(pts)
        )

    def _check_thumbs_down(self, states: dict, pts: list) -> bool:
        # Same reasoning: drop the unreliable X-axis states["thumb"] check
        # and rely purely on Y-axis geometry.  Also require that the hand
        # is NOT in the upright orientation so an upright fist with the
        # thumb slightly below MCP doesn't trigger this.
        return (
            not states["index"]
            and not states["middle"]
            and not states["ring"]
            and not states["pinky"]
            and self._thumb_tip_below_mcp(pts)
            and not self._is_pointing_up(pts)
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

    def _check_vulcan(self, states: dict, pts: list) -> bool:
        # All four fingers extended with the split SPECIFICALLY between the
        # middle and ring fingertips (Star Trek salute).
        # Thumb state is intentionally ignored so the gesture works whether the
        # thumb is tucked or extended (both are natural poses for this sign).
        # Checked before OPEN_PALM so a Vulcan with thumb out doesn't collapse
        # into plain open-palm.
        if not (states["index"] and states["middle"]
                and states["ring"] and states["pinky"]):
            return False

        middle_ring  = abs(pts[MIDDLE_TIP][0] - pts[RING_TIP][0])
        index_middle = abs(pts[INDEX_TIP][0]  - pts[MIDDLE_TIP][0])
        ring_pinky   = abs(pts[RING_TIP][0]   - pts[PINKY_TIP][0])

        # Three conditions must all hold:
        #  1. The middle↔ring split is large enough to be intentional.
        #  2. Index and middle are visibly touching/close (one pair).
        #  3. Ring and pinky are visibly touching/close (the other pair).
        return (
            middle_ring  > VULCAN_SPREAD_THRESHOLD
            and index_middle < VULCAN_PAIR_THRESHOLD
            and ring_pinky   < VULCAN_PAIR_THRESHOLD
        )

    def _check_finger_gun(self, states: dict, pts: list) -> bool:
        # Index (Y-axis) extended, middle/ring/pinky curled, thumb raised above
        # the knuckle line.
        #
        # Reference point: MIDDLE_MCP (the middle-finger knuckle at the top of
        # the closed fist).  A resting thumb in INDEX_UP sits at or below that
        # line; a raised gun-pose thumb sits clearly above it.
        # This avoids the false-positive from _thumb_points_up, which used
        # THUMB_MCP (near the wrist) and fired on any non-downward thumb.
        thumb_above_knuckle = (
            pts[MIDDLE_MCP][1] - pts[THUMB_TIP][1] > FINGER_GUN_THUMB_THRESHOLD
        )
        return (
            thumb_above_knuckle
            and states["index"]
            and not states["middle"]
            and not states["ring"]
            and not states["pinky"]
        )
