"""
evaluate.py - Metrics calculator, plot generator, and performance benchmark.

Reads eval_data.csv produced by collect_dataset.py and outputs:
  • Console: classification report + hand detection rate
  • output/confusion_matrix.png   - row-normalised 11×11 heatmap
  • output/f1_per_class.png       - horizontal bar chart (sorted by F1)
  • output/performance.png        - latency over 200 frames + histogram

Usage
-----
    python cv-module/tools/evaluate.py [--csv eval_data.csv] [--camera 0] [--frames 200]
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import cv2
import numpy as np

# ── Fix imports ───────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.hand_detector import HandDetector          # noqa: E402
from modules.gesture_classifier import GestureClassifier  # noqa: E402

import pandas as pd                                        # noqa: E402
import matplotlib.pyplot as plt                            # noqa: E402
import matplotlib.patches as mpatches                      # noqa: E402
import seaborn as sns                                      # noqa: E402
from sklearn.metrics import (                              # noqa: E402
    classification_report,
    confusion_matrix,
    accuracy_score,
    f1_score,
)

# ── Constants ─────────────────────────────────────────────────────────────────
GESTURE_ORDER: list[str] = [
    "OK", "VULCAN", "OPEN_PALM", "FIST", "FINGER_GUN",
    "INDEX_UP", "PEACE", "THREE", "FOUR", "PINKY_UP", "ROCK",
]

_HERE = os.path.dirname(os.path.abspath(__file__))
_OUTPUT_DIR = os.path.join(_HERE, "output")

plt.style.use("seaborn-v0_8-whitegrid")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_output() -> None:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)


# ── Section A: Console metrics ────────────────────────────────────────────────

def print_metrics(df: pd.DataFrame) -> None:
    # Only rows where a hand was detected count toward classification accuracy
    detected = df[df["hand_detected"] == True]  # noqa: E712

    if detected.empty:
        print("[WARN] No frames with a detected hand in the dataset.")
        return

    y_true = detected["true_label"].tolist()
    y_pred = detected["predicted_label"].fillna("NONE").tolist()

    print("\n" + "=" * 62)
    print("  GESTURE CLASSIFIER - EVALUATION REPORT")
    print("=" * 62)
    print(classification_report(y_true, y_pred, labels=GESTURE_ORDER, zero_division=0))

    acc = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, labels=GESTURE_ORDER, average="macro", zero_division=0)
    weighted_f1 = f1_score(y_true, y_pred, labels=GESTURE_ORDER, average="weighted", zero_division=0)

    print(f"  Overall Accuracy   : {acc:.4f}")
    print(f"  Macro F1-score     : {macro_f1:.4f}")
    print(f"  Weighted F1-score  : {weighted_f1:.4f}")

    total_frames = len(df)
    detected_frames = int(df["hand_detected"].sum())
    det_rate = detected_frames / total_frames * 100 if total_frames else 0.0
    print(f"\n  Hand Detection Rate: {detected_frames}/{total_frames} frames ({det_rate:.1f}%)")
    print("=" * 62 + "\n")


# ── Section B: Confusion matrix ───────────────────────────────────────────────

def plot_confusion_matrix(df: pd.DataFrame) -> None:
    _ensure_output()

    detected = df[df["hand_detected"] == True]  # noqa: E712
    if detected.empty:
        print("[WARN] Skipping confusion matrix - no detected-hand rows.")
        return

    y_true = detected["true_label"].tolist()
    y_pred = detected["predicted_label"].fillna("NONE").tolist()

    cm = confusion_matrix(y_true, y_pred, labels=GESTURE_ORDER)
    # Row-normalise: each row / row sum (avoid div-by-zero)
    row_sums = cm.sum(axis=1, keepdims=True)
    cm_norm = np.where(row_sums == 0, 0.0, cm / row_sums.astype(float))

    n_samples = len(y_true)
    fig, ax = plt.subplots(figsize=(12, 10))
    sns.heatmap(
        cm_norm * 100,
        annot=True,
        fmt=".1f",
        cmap="Blues",
        xticklabels=GESTURE_ORDER,
        yticklabels=GESTURE_ORDER,
        linewidths=0.5,
        linecolor="lightgrey",
        ax=ax,
        vmin=0,
        vmax=100,
        cbar_kws={"label": "% of true class"},
    )
    ax.set_xlabel("Predicted Label", fontsize=12, labelpad=10)
    ax.set_ylabel("True Label", fontsize=12, labelpad=10)
    ax.set_title(
        f"Gesture Classifier - Confusion Matrix ({n_samples} samples)",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()

    out_path = os.path.join(_OUTPUT_DIR, "confusion_matrix.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[✓] Confusion matrix saved → {out_path}")


# ── Section C: Per-class F1 bar chart ────────────────────────────────────────

def plot_f1_per_class(df: pd.DataFrame) -> None:
    _ensure_output()

    detected = df[df["hand_detected"] == True]  # noqa: E712
    if detected.empty:
        print("[WARN] Skipping F1 chart - no detected-hand rows.")
        return

    y_true = detected["true_label"].tolist()
    y_pred = detected["predicted_label"].fillna("NONE").tolist()

    f1_scores = f1_score(
        y_true, y_pred,
        labels=GESTURE_ORDER,
        average=None,
        zero_division=0,
    )
    f1_dict = dict(zip(GESTURE_ORDER, f1_scores))

    # Sort descending by F1
    sorted_labels = sorted(f1_dict, key=f1_dict.get, reverse=True)
    sorted_scores = [f1_dict[l] for l in sorted_labels]

    # Color coding
    colors = []
    for s in sorted_scores:
        if s >= 0.90:
            colors.append("#2ecc71")   # green
        elif s >= 0.75:
            colors.append("#f1c40f")   # yellow
        else:
            colors.append("#e74c3c")   # red

    fig, ax = plt.subplots(figsize=(10, 7))
    bars = ax.barh(sorted_labels, sorted_scores, color=colors, edgecolor="white", height=0.65)

    # Annotate each bar with the value
    for bar, score in zip(bars, sorted_scores):
        ax.text(
            min(score + 0.015, 0.98),
            bar.get_y() + bar.get_height() / 2,
            f"{score:.3f}",
            va="center",
            ha="left",
            fontsize=10,
            fontweight="bold",
        )

    ax.set_xlim(0.0, 1.05)
    ax.set_xticks([i / 10 for i in range(11)])
    ax.set_xlabel("F1-score", fontsize=12)
    ax.set_title(
        "Per-class F1-score - Gesture Classifier",
        fontsize=14,
        fontweight="bold",
        pad=10,
    )
    ax.set_suptitle = None  # n/a here; use subtitle via text
    fig.text(
        0.5, 0.01,
        "Rule-based classifier - no training curves applicable",
        ha="center",
        fontsize=9,
        color="grey",
        style="italic",
    )

    # Legend patches
    legend_patches = [
        mpatches.Patch(color="#2ecc71", label="F1 ≥ 0.90"),
        mpatches.Patch(color="#f1c40f", label="F1 ≥ 0.75"),
        mpatches.Patch(color="#e74c3c", label="F1 < 0.75"),
    ]
    ax.legend(handles=legend_patches, loc="lower right", framealpha=0.9)

    ax.invert_yaxis()  # Highest F1 at the top
    plt.tight_layout(rect=[0, 0.04, 1, 1])

    out_path = os.path.join(_OUTPUT_DIR, "f1_per_class.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[✓] F1 per-class chart saved → {out_path}")


# ── Section D: FPS / latency benchmark ───────────────────────────────────────

def benchmark_performance(camera_index: int, n_frames: int) -> None:
    _ensure_output()

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"[WARN] Cannot open camera {camera_index}. Skipping performance benchmark.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    detector = HandDetector()
    classifier = GestureClassifier()

    # Warm-up: 10 frames to stabilise mediapipe
    for _ in range(10):
        ret, frame = cap.read()
        if ret:
            detector.process_frame(frame)

    latencies_ms: list[float] = []
    print(f"[…] Benchmarking {n_frames} frames …")

    for i in range(n_frames):
        ret, frame = cap.read()
        if not ret:
            continue

        t0 = time.perf_counter()
        landmarks, _ = detector.process_frame(frame)
        if landmarks:
            classifier.classify(landmarks)
        t1 = time.perf_counter()

        latencies_ms.append((t1 - t0) * 1000.0)

    cap.release()
    detector.close()

    if not latencies_ms:
        print("[WARN] No frames captured for benchmark.")
        return

    arr = np.array(latencies_ms)
    mean_ms   = float(np.mean(arr))
    p95_ms    = float(np.percentile(arr, 95))
    p99_ms    = float(np.percentile(arr, 99))
    min_ms    = float(np.min(arr))
    max_ms    = float(np.max(arr))
    mean_fps  = 1000.0 / mean_ms if mean_ms > 0 else 0.0

    print("\n" + "=" * 46)
    print("  PIPELINE PERFORMANCE BENCHMARK")
    print("=" * 46)
    print(f"  Frames measured : {len(arr)}")
    print(f"  Mean FPS        : {mean_fps:.1f}")
    print(f"  Mean latency    : {mean_ms:.2f} ms")
    print(f"  p95 latency     : {p95_ms:.2f} ms")
    print(f"  p99 latency     : {p99_ms:.2f} ms")
    print(f"  Min latency     : {min_ms:.2f} ms")
    print(f"  Max latency     : {max_ms:.2f} ms")
    print("=" * 46 + "\n")

    # ── Plot ─────────────────────────────────────────────────────────────────
    fig, (ax_line, ax_hist) = plt.subplots(2, 1, figsize=(12, 8))

    # Top: latency over time
    x = np.arange(1, len(arr) + 1)
    ax_line.plot(x, arr, linewidth=0.8, color="#3498db", alpha=0.8, label="Frame latency")
    ax_line.axhline(mean_ms, color="#e74c3c", linestyle="--", linewidth=1.5,
                    label=f"Mean = {mean_ms:.1f} ms")
    ax_line.axhline(p95_ms, color="#f39c12", linestyle="--", linewidth=1.5,
                    label=f"p95 = {p95_ms:.1f} ms")
    ax_line.axhline(p99_ms, color="#9b59b6", linestyle="--", linewidth=1.5,
                    label=f"p99 = {p99_ms:.1f} ms")
    ax_line.set_xlabel("Frame index", fontsize=11)
    ax_line.set_ylabel("Latency (ms)", fontsize=11)
    ax_line.set_title(
        f"Pipeline Latency over {len(arr)} Frames  |  Mean FPS: {mean_fps:.1f}",
        fontsize=13,
        fontweight="bold",
    )
    ax_line.legend(fontsize=9)
    ax_line.set_xlim(1, len(arr))

    # Bottom: histogram
    ax_hist.hist(arr, bins=20, color="#3498db", edgecolor="white", alpha=0.85)
    ax_hist.axvline(mean_ms, color="#e74c3c", linestyle="--", linewidth=1.5,
                    label=f"Mean = {mean_ms:.1f} ms")
    ax_hist.axvline(p95_ms, color="#f39c12", linestyle="--", linewidth=1.5,
                    label=f"p95 = {p95_ms:.1f} ms")
    ax_hist.axvline(p99_ms, color="#9b59b6", linestyle="--", linewidth=1.5,
                    label=f"p99 = {p99_ms:.1f} ms")
    ax_hist.set_xlabel("Latency (ms)", fontsize=11)
    ax_hist.set_ylabel("Frame count", fontsize=11)
    ax_hist.set_title("Frame Time Distribution", fontsize=13, fontweight="bold")
    ax_hist.legend(fontsize=9)

    plt.tight_layout()
    out_path = os.path.join(_OUTPUT_DIR, "performance.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[✓] Performance plot saved → {out_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    here = os.path.dirname(os.path.abspath(__file__))
    default_csv = os.path.join(here, "eval_data.csv")

    p = argparse.ArgumentParser(
        description="Generate classification metrics and plots from eval_data.csv.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--csv", default=default_csv, help="Path to eval_data.csv.")
    p.add_argument("--camera", type=int, default=0, help="OpenCV camera index for benchmark.")
    p.add_argument(
        "--frames", type=int, default=200,
        help="Number of frames to capture for the performance benchmark.",
    )
    p.add_argument(
        "--skip-benchmark", action="store_true",
        help="Skip the live-camera performance benchmark.",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    if not os.path.exists(args.csv):
        sys.exit(
            f"[ERROR] CSV not found: {args.csv}\n"
            "Run collect_dataset.py first."
        )

    df = pd.read_csv(args.csv)

    # Normalise the hand_detected column - CSV stores Python True/False strings
    df["hand_detected"] = df["hand_detected"].map(
        lambda v: str(v).strip().lower() in ("true", "1", "yes")
    )

    print_metrics(df)
    plot_confusion_matrix(df)
    plot_f1_per_class(df)

    if not args.skip_benchmark:
        benchmark_performance(args.camera, args.frames)


if __name__ == "__main__":
    main()
