"""
hand_detector.py — MediaPipe Hands wrapper.

Isolates all MediaPipe API calls so the rest of the codebase
never imports mediapipe directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np


@dataclass
class HandLandmarks:
    """
    Holds the 21 normalized landmark points for one detected hand.

    Attributes
    ----------
    points : list[tuple[float, float, float]]
        21 elements ordered by MediaPipe landmark index (0 = wrist … 20 = pinky tip).
        Each element is (x, y, z) in normalized image coordinates [0.0, 1.0].
    handedness : str
        'Left' or 'Right' as reported by MediaPipe.
    """

    points: list[tuple[float, float, float]]
    handedness: str


class HandDetector:
    """
    Wraps MediaPipe Hands for single-hand detection.

    Parameters
    ----------
    max_num_hands : int
        Maximum number of hands to detect. Kept at 1 for lock use-case.
    min_detection_confidence : float
        MediaPipe detection confidence threshold.
    min_tracking_confidence : float
        MediaPipe tracking confidence threshold.
    """

    def __init__(
        self,
        max_num_hands: int = 1,
        min_detection_confidence: float = 0.7,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self._mp_hands = mp.solutions.hands
        self._drawing_utils = mp.solutions.drawing_utils
        self._hands = self._mp_hands.Hands(
            max_num_hands=max_num_hands,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def process_frame(
        self, frame: np.ndarray
    ) -> tuple[Optional[HandLandmarks], np.ndarray]:
        """
        Run MediaPipe inference on one BGR frame.

        Parameters
        ----------
        frame : np.ndarray
            Raw BGR frame from cv2.VideoCapture.

        Returns
        -------
        landmarks : HandLandmarks or None
            None when no hand is visible.
        annotated_frame : np.ndarray
            Copy of the frame with MediaPipe skeleton drawn (for debug display).
        """
        annotated = frame.copy()

        # MediaPipe requires RGB input
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self._hands.process(rgb)

        if not results.multi_hand_landmarks:
            return None, annotated

        hand_landmarks = results.multi_hand_landmarks[0]
        handedness_label = results.multi_handedness[0].classification[0].label

        # Draw skeleton on annotated frame
        self._drawing_utils.draw_landmarks(
            annotated,
            hand_landmarks,
            self._mp_hands.HAND_CONNECTIONS,
        )

        points = [
            (lm.x, lm.y, lm.z) for lm in hand_landmarks.landmark
        ]

        return HandLandmarks(points=points, handedness=handedness_label), annotated

    def close(self) -> None:
        """Release MediaPipe resources."""
        self._hands.close()
