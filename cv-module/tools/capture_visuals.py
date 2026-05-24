"""
capture_visuals.py - Landmark overlay screenshot tool for the academic report.

Cycles through all 11 gestures, lets the user capture one screenshot per gesture,
draws the MediaPipe landmark skeleton, overlays true/detected labels, saves
individual PNGs, and assembles an 11-gesture + 1-blank 4×3 grid montage.

Usage
-----
    python cv-module/tools/capture_visuals.py [--camera 0]

Keys
----
    SPACE  - capture current frame and move to next gesture
    N      - skip (save blank cell for this gesture)
    Q      - quit early (remaining gestures get blank cells)

Output
------
    cv-module/tools/output/gesture_<LABEL>.png    (one per gesture)
    cv-module/tools/output/gesture_montage.png    (4×3 grid)
"""

from __future__ import annotations

import argparse
import os
import sys

import cv2
import mediapipe as mp
import numpy as np

# ── Fix imports ───────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.hand_detector import HandDetector          # noqa: E402
from modules.gesture_classifier import GestureClassifier  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────────
GESTURE_ORDER: list[str] = [
    "OK", "VULCAN", "OPEN_PALM", "FIST", "FINGER_GUN",
    "INDEX_UP", "PEACE", "THREE", "FOUR", "PINKY_UP", "ROCK",
]

CELL_W, CELL_H = 320, 240          # montage cell size
MONTAGE_COLS, MONTAGE_ROWS = 4, 3  # 12 cells total (11 gestures + 1 blank)

_HERE = os.path.dirname(os.path.abspath(__file__))
_OUTPUT_DIR = os.path.join(_HERE, "output")

_FONT = cv2.FONT_HERSHEY_SIMPLEX
_mp_hands = mp.solutions.hands
_mp_drawing = mp.solutions.drawing_utils
_mp_drawing_styles = mp.solutions.drawing_styles


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_output() -> None:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)


def _put_text_outlined(
    img,
    text: str,
    pos: tuple[int, int],
    scale: float,
    color: tuple[int, int, int],
    thickness: int = 2,
) -> None:
    cv2.putText(img, text, pos, _FONT, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(img, text, pos, _FONT, scale, color, thickness, cv2.LINE_AA)


def _blank_cell() -> np.ndarray:
    """Return a dark-grey CELL_H × CELL_W blank image."""
    cell = np.full((CELL_H, CELL_W, 3), 40, dtype=np.uint8)
    _put_text_outlined(cell, "(blank)", (80, CELL_H // 2), 0.7, (120, 120, 120))
    return cell


def _draw_hud(frame, true_label: str, predicted: str | None) -> np.ndarray:
    """
    Overlay true/detected labels in the top-left corner.

    Returns a copy of the frame with the HUD drawn.
    """
    out = frame.copy()
    h = out.shape[0]

    # Background bar
    overlay = out.copy()
    cv2.rectangle(overlay, (0, 0), (280, 70), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.55, out, 0.45, 0, out)

    _put_text_outlined(out, f"True: {true_label}", (8, 28), 0.75, (255, 255, 255))

    if predicted is None:
        det_text = "Detected: (no hand)"
        det_color = (0, 60, 200)
    elif predicted == true_label:
        det_text = f"Detected: {predicted}"
        det_color = (30, 200, 30)
    else:
        det_text = f"Detected: {predicted}"
        det_color = (30, 30, 200)

    _put_text_outlined(out, det_text, (8, 58), 0.75, det_color)
    return out


def _draw_landmarks_on_frame(frame: np.ndarray) -> tuple[np.ndarray, object]:
    """
    Run a fresh MediaPipe inference on frame and draw landmarks.

    Returns (annotated_frame, results) where results is the raw MP output.
    """
    with _mp_hands.Hands(
        static_image_mode=True,
        max_num_hands=1,
        min_detection_confidence=0.5,
    ) as hands:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)

    annotated = frame.copy()
    if results.multi_hand_landmarks:
        for hand_lm in results.multi_hand_landmarks:
            _mp_drawing.draw_landmarks(
                annotated,
                hand_lm,
                _mp_hands.HAND_CONNECTIONS,
                _mp_drawing_styles.get_default_hand_landmarks_style(),
                _mp_drawing_styles.get_default_hand_connections_style(),
            )
    return annotated, results


def _make_cell_with_caption(img: np.ndarray, label: str) -> np.ndarray:
    """
    Resize img to CELL_W × CELL_H, then add a caption bar at the bottom.
    Total height = CELL_H + 24 px caption.
    """
    CAPTION_H = 24
    resized = cv2.resize(img, (CELL_W, CELL_H))
    caption_bar = np.full((CAPTION_H, CELL_W, 3), 30, dtype=np.uint8)
    cv2.putText(
        caption_bar, label,
        (CELL_W // 2 - len(label) * 5, 16),
        _FONT, 0.5, (220, 220, 220), 1, cv2.LINE_AA,
    )
    return np.vstack([resized, caption_bar])


def _build_montage(cells: list[np.ndarray]) -> np.ndarray:
    """
    Assemble a 4-column × 3-row montage from cells (each CELL_W × (CELL_H+24)).
    Pads with blank cells up to MONTAGE_COLS * MONTAGE_ROWS.
    """
    CAPTION_H = 24
    blank = _make_cell_with_caption(_blank_cell(), "")
    while len(cells) < MONTAGE_COLS * MONTAGE_ROWS:
        cells.append(blank)

    rows = []
    for r in range(MONTAGE_ROWS):
        row_cells = cells[r * MONTAGE_COLS : (r + 1) * MONTAGE_COLS]
        rows.append(np.hstack(row_cells))
    return np.vstack(rows)


# ── Main capture loop ─────────────────────────────────────────────────────────

def capture_visuals(camera_index: int) -> None:
    _ensure_output()

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        sys.exit(f"[ERROR] Cannot open camera index {camera_index}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    detector = HandDetector()
    classifier = GestureClassifier()

    montage_cells: list[np.ndarray] = []
    total = len(GESTURE_ORDER)

    print("\n=== Gesture Visual Capture Tool ===")
    print(f"Output → {_OUTPUT_DIR}\n")

    quit_early = False

    try:
        for g_idx, gesture_label in enumerate(GESTURE_ORDER, start=1):
            if quit_early:
                montage_cells.append(
                    _make_cell_with_caption(_blank_cell(), gesture_label)
                )
                continue

            print(f"[{g_idx}/{total}] Gesture: {gesture_label}")
            print("  SPACE - capture | N - skip | Q - quit")

            captured_frame: np.ndarray | None = None

            while True:
                ret, frame = cap.read()
                if not ret:
                    continue

                frame = cv2.flip(frame, 1)
                key = cv2.waitKey(1) & 0xFF

                # Live preview with running inference
                landmarks, annotated = detector.process_frame(frame)
                predicted = classifier.classify(landmarks) if landmarks else None
                preview = _draw_hud(annotated, gesture_label, predicted)

                # HUD prompt line
                cv2.putText(
                    preview,
                    f"SPACE=capture  N=skip  Q=quit  [{g_idx}/{total}]",
                    (8, preview.shape[0] - 10),
                    _FONT, 0.55, (200, 200, 200), 1, cv2.LINE_AA,
                )
                cv2.imshow("Capture Visuals", preview)

                if key == ord("q"):
                    quit_early = True
                    break

                if key == ord("n"):
                    print(f"  Skipped {gesture_label}.")
                    captured_frame = None
                    break

                if key == ord(" "):
                    captured_frame = frame.copy()
                    break

            if quit_early:
                montage_cells.append(
                    _make_cell_with_caption(_blank_cell(), gesture_label)
                )
                continue

            if captured_frame is None:
                # Skipped - blank cell
                montage_cells.append(
                    _make_cell_with_caption(_blank_cell(), gesture_label)
                )
                continue

            # Re-run full pipeline on captured frame with static_image_mode for cleaner
            # landmark drawing, then overlay HUD
            annotated_cap, _ = _draw_landmarks_on_frame(captured_frame)
            landmarks2, _ = detector.process_frame(captured_frame)
            predicted2 = classifier.classify(landmarks2) if landmarks2 else None
            final_frame = _draw_hud(annotated_cap, gesture_label, predicted2)

            # Save individual PNG
            out_path = os.path.join(_OUTPUT_DIR, f"gesture_{gesture_label}.png")
            cv2.imwrite(out_path, final_frame)
            print(f"  Saved → {out_path}  (detected: {predicted2})")

            montage_cells.append(
                _make_cell_with_caption(final_frame, gesture_label)
            )

    finally:
        cap.release()
        detector.close()
        cv2.destroyAllWindows()

    # Build and save montage
    montage = _build_montage(montage_cells)
    montage_path = os.path.join(_OUTPUT_DIR, "gesture_montage.png")
    cv2.imwrite(montage_path, montage)
    print(f"\n[✓] Montage saved → {montage_path}")
    print("Done.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Capture annotated gesture screenshots for the academic report.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--camera", type=int, default=0, help="OpenCV camera index.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    capture_visuals(camera_index=args.camera)
