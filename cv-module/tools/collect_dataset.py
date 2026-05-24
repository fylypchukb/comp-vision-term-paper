"""
collect_dataset.py - Interactive webcam-based evaluation dataset collector.

Cycles through all 11 gestures and captures N frames per gesture while the
user holds SPACE. Results are saved to eval_data.csv for later analysis with
evaluate.py.

Usage
-----
    python cv-module/tools/collect_dataset.py [--samples 30] [--camera 0] [--output eval_data.csv]

Keys
----
    SPACE  - hold to capture frames for the current gesture
    N      - skip to next gesture
    Q      - quit early
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime

COUNTDOWN_SECONDS: int = 3   # pause between gestures; set to 0 to disable

import cv2

# ── Fix imports so this runs from any working directory ──────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.hand_detector import HandDetector          # noqa: E402
from modules.gesture_classifier import GestureClassifier  # noqa: E402

# ── Constants ────────────────────────────────────────────────────────────────
GESTURE_ORDER: list[str] = [
    "OK", "VULCAN", "OPEN_PALM", "FIST", "FINGER_GUN",
    "INDEX_UP", "PEACE", "THREE", "FOUR", "PINKY_UP", "ROCK",
]

_FONT = cv2.FONT_HERSHEY_SIMPLEX


# ── Helpers ───────────────────────────────────────────────────────────────────

def _put_text(
    frame,
    text: str,
    y: int,
    scale: float = 0.75,
    color=(255, 255, 255),
    thickness: int = 2,
) -> None:
    cv2.putText(frame, text, (10, y), _FONT, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(frame, text, (10, y), _FONT, scale, color, thickness, cv2.LINE_AA)


def _draw_countdown(cap, next_label: str, seconds: int) -> bool:
    """
    Show a live countdown overlay between gestures.

    Displays the webcam feed with a large countdown number and the name of the
    NEXT gesture so the user has time to reposition their hand.
    All key presses are ignored during the countdown - SPACE cannot bleed
    into the next gesture's capture window.

    Returns False if Q was pressed (caller should quit), True otherwise.
    """
    if seconds <= 0:
        return True

    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        ret, frame = cap.read()
        if not ret:
            continue
        frame = cv2.flip(frame, 1)

        h, w = frame.shape[:2]

        # Dark overlay
        dark = frame.copy()
        cv2.rectangle(dark, (0, 0), (w, h), (10, 10, 10), -1)
        cv2.addWeighted(dark, 0.55, frame, 0.45, 0, frame)

        # Big countdown number
        count_str = str(int(remaining) + 1)
        (tw, th), _ = cv2.getTextSize(count_str, _FONT, 5.0, 8)
        cv2.putText(
            frame, count_str,
            (w // 2 - tw // 2, h // 2 + th // 2),
            _FONT, 5.0, (50, 50, 50), 14, cv2.LINE_AA,
        )
        cv2.putText(
            frame, count_str,
            (w // 2 - tw // 2, h // 2 + th // 2),
            _FONT, 5.0, (255, 200, 50), 8, cv2.LINE_AA,
        )

        # "Next gesture" label
        msg = f"Next: {next_label}"
        (mw, _), _ = cv2.getTextSize(msg, _FONT, 1.1, 2)
        cv2.putText(frame, msg, (w // 2 - mw // 2 + 2, h // 2 + th + 50 + 2),
                    _FONT, 1.1, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, msg, (w // 2 - mw // 2, h // 2 + th + 50),
                    _FONT, 1.1, (255, 255, 255), 2, cv2.LINE_AA)

        # "Get ready" sub-label
        sub = "Get ready - all keys disabled"
        (sw, _), _ = cv2.getTextSize(sub, _FONT, 0.6, 1)
        cv2.putText(frame, sub, (w // 2 - sw // 2, h - 20),
                    _FONT, 0.6, (160, 160, 160), 1, cv2.LINE_AA)

        cv2.imshow("Dataset Collector", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            return False   # propagate quit upward

    return True


def _draw_overlay(
    frame,
    label: str,
    gesture_idx: int,
    total: int,
    captured: int,
    target: int,
    capturing: bool,
) -> None:
    """Draw the HUD on top of the frame (modifies in-place)."""
    h, w = frame.shape[:2]

    # Semi-transparent top bar
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 110), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    prompt = f"Show gesture: {label}  ({gesture_idx}/{total})"
    _put_text(frame, prompt, 35, scale=0.85, color=(255, 220, 50))

    keys_hint = "Hold SPACE to capture | N - skip | Q - quit"
    _put_text(frame, keys_hint, 65, scale=0.6, color=(200, 200, 200))

    status_color = (0, 230, 80) if capturing else (160, 160, 160)
    status_text = f"Captured: {captured}/{target}" + (" - CAPTURING" if capturing else "")
    _put_text(frame, status_text, 95, scale=0.65, color=status_color)


# ── Main collector ────────────────────────────────────────────────────────────

def collect(
    samples_per_gesture: int,
    camera_index: int,
    output_path: str,
    countdown: int = COUNTDOWN_SECONDS,
) -> None:
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        sys.exit(f"[ERROR] Cannot open camera index {camera_index}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    detector = HandDetector()
    classifier = GestureClassifier()

    # Prepare CSV
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    csv_file = open(output_path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(
        csv_file,
        fieldnames=["true_label", "predicted_label", "hand_detected", "timestamp"],
    )
    writer.writeheader()

    total_gestures = len(GESTURE_ORDER)
    per_gesture_results: dict[str, list[bool]] = {}

    print("\n=== Gesture Evaluation Dataset Collector ===")
    print(f"Gestures : {', '.join(GESTURE_ORDER)}")
    print(f"Samples  : {samples_per_gesture} per gesture")
    print(f"Output   : {output_path}\n")

    try:
        for g_idx, gesture_label in enumerate(GESTURE_ORDER, start=1):
            captured = 0
            correct_count = 0
            results_this_gesture: list[bool] = []

            print(f"[{g_idx}/{total_gestures}] Ready for: {gesture_label}")
            print("  Hold SPACE to start capturing, N to skip, Q to quit …")

            while captured < samples_per_gesture:
                ret, frame = cap.read()
                if not ret:
                    continue

                frame = cv2.flip(frame, 1)  # Mirror so it feels natural
                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):
                    print("\n[INFO] Quit requested - saving partial data.")
                    cap.release()
                    detector.close()
                    csv_file.close()
                    cv2.destroyAllWindows()
                    _print_summary(per_gesture_results)
                    return

                if key == ord("n"):
                    print(f"  Skipped {gesture_label}.")
                    break

                capturing = key == ord(" ")

                if capturing:
                    landmarks, _ = detector.process_frame(frame)
                    hand_detected = landmarks is not None
                    predicted = classifier.classify(landmarks) if landmarks else None

                    writer.writerow(
                        {
                            "true_label": gesture_label,
                            "predicted_label": predicted if predicted else "",
                            "hand_detected": hand_detected,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                    csv_file.flush()

                    captured += 1
                    is_correct = predicted == gesture_label
                    if is_correct:
                        correct_count += 1
                    results_this_gesture.append(is_correct)

                _draw_overlay(
                    frame,
                    gesture_label,
                    g_idx,
                    total_gestures,
                    captured,
                    samples_per_gesture,
                    capturing,
                )
                cv2.imshow("Dataset Collector", frame)

            per_gesture_results[gesture_label] = results_this_gesture

            if results_this_gesture:
                acc = correct_count / len(results_this_gesture) * 100
                print(
                    f"  Done - {len(results_this_gesture)} samples | "
                    f"Accuracy: {correct_count}/{len(results_this_gesture)} ({acc:.1f}%)"
                )
            print()

            # Countdown before the next gesture so the user has time to
            # reposition their hand - all keys are disabled during this window
            # so a still-held SPACE cannot bleed into the next capture.
            is_last = g_idx == total_gestures
            if not is_last:
                next_label = GESTURE_ORDER[g_idx]   # g_idx is 1-based, so this is the next item
                if not _draw_countdown(cap, next_label, countdown):
                    print("\n[INFO] Quit during countdown - saving partial data.")
                    break

    finally:
        cap.release()
        detector.close()
        csv_file.close()
        cv2.destroyAllWindows()

    _print_summary(per_gesture_results)
    print(f"\nDataset saved → {output_path}")


def _print_summary(results: dict[str, list[bool]]) -> None:
    print("\n" + "=" * 52)
    print(f"{'Gesture':<15} {'Samples':>7} {'Correct':>8} {'Accuracy':>9}")
    print("-" * 52)
    total_samples = total_correct = 0
    for label, bools in results.items():
        n = len(bools)
        c = sum(bools)
        acc = c / n * 100 if n else 0.0
        total_samples += n
        total_correct += c
        print(f"{label:<15} {n:>7} {c:>8} {acc:>8.1f}%")
    print("-" * 52)
    overall = total_correct / total_samples * 100 if total_samples else 0.0
    print(f"{'TOTAL':<15} {total_samples:>7} {total_correct:>8} {overall:>8.1f}%")
    print("=" * 52)


# ── CLI entry point ───────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    here = os.path.dirname(os.path.abspath(__file__))
    default_output = os.path.join(here, "eval_data.csv")

    parser = argparse.ArgumentParser(
        description="Collect gesture evaluation dataset from webcam.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--samples", type=int, default=30,
        help="Number of frames to capture per gesture while SPACE is held.",
    )
    parser.add_argument(
        "--camera", type=int, default=0,
        help="OpenCV camera index.",
    )
    parser.add_argument(
        "--output", type=str, default=default_output,
        help="Path to the output CSV file.",
    )
    parser.add_argument(
        "--countdown", type=int, default=COUNTDOWN_SECONDS,
        help="Seconds to pause between gestures (0 to disable).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    collect(
        samples_per_gesture=args.samples,
        camera_index=args.camera,
        output_path=args.output,
        countdown=args.countdown,
    )
