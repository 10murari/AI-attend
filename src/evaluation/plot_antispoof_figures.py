"""Generate report figures (confusion matrix, PR curve, ROC curve) from the
anti-spoof evaluation results in antispoof_results/.

Two evaluation levels:
  frame — every scored frame is a sample (the raw model's performance)
  video — each video scored by its mean liveness over 20 frames (the
          temporally-aggregated pipeline)

Spoof is the positive class: score = 1 - liveness score, so higher means
"more likely spoof". A sample is predicted spoof when its liveness score
falls below the production threshold (0.85).

Usage:
    .venv/bin/python src/evaluation/plot_antispoof_figures.py
"""

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

RESULTS_DIR = Path(__file__).resolve().parents[2] / "antispoof_results"
FIGURES_DIR = RESULTS_DIR / "figures"
THRESHOLD = 0.85

BLUE = "#3987e5"
BLUE_DARK = "#1c5cab"
BLUE_LIGHT = "#cde2fb"
INK = "#1f2937"
INK_MUTED = "#6b7280"
GRID = "#e5e7eb"


def load_samples(filename: str, score_col: str):
    y_true, y_score = [], []  # 1 = spoof (positive class), score = spoofness
    with open(RESULTS_DIR / filename) as f:
        for row in csv.DictReader(f):
            if not row[score_col]:
                continue
            y_true.append(1 if row["label"] == "attack" else 0)
            y_score.append(1.0 - float(row[score_col]))
    return np.array(y_true), np.array(y_score)


def roc_points(y_true, y_score):
    order = np.argsort(-y_score)
    y = y_true[order]
    tps = np.cumsum(y)
    fps = np.cumsum(1 - y)
    tpr = np.concatenate([[0], tps / y_true.sum()])
    fpr = np.concatenate([[0], fps / (len(y_true) - y_true.sum())])
    auc = np.trapezoid(tpr, fpr)
    return fpr, tpr, auc


def pr_points(y_true, y_score):
    order = np.argsort(-y_score)
    y = y_true[order]
    tps = np.cumsum(y)
    precision = tps / np.arange(1, len(y) + 1)
    recall = tps / y_true.sum()
    # Average precision: sum of precision at each new true positive
    ap = float(np.sum(precision[y == 1]) / y_true.sum())
    return recall, precision, ap


def style_axes(ax):
    ax.set_facecolor("white")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_MUTED, labelsize=10)
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)


def plot_confusion_matrix(y_true, y_score, prefix: str, title: str):
    pred_spoof = y_score > (1 - THRESHOLD)  # liveness < 0.85
    # rows = true (real, spoof), cols = predicted (real, spoof)
    cm = np.zeros((2, 2), dtype=int)
    for t, p in zip(y_true, pred_spoof.astype(int)):
        cm[t, p] += 1

    fig, ax = plt.subplots(figsize=(5.2, 4.4), dpi=200)
    ax.imshow(cm, cmap=plt.matplotlib.colors.LinearSegmentedColormap.from_list(
        "seq_blue", ["#f5f9fe", BLUE_LIGHT, BLUE, BLUE_DARK]), vmin=0)
    for i in range(2):
        for j in range(2):
            frac = cm[i, j] / cm.max()
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                    fontsize=20, fontweight="bold",
                    color="white" if frac > 0.55 else INK)
    ax.set_xticks([0, 1], ["Real", "Spoof"], fontsize=11, color=INK)
    ax.set_yticks([0, 1], ["Real", "Spoof"], fontsize=11, color=INK)
    ax.set_xlabel("Predicted label", fontsize=11, color=INK)
    ax.set_ylabel("True label", fontsize=11, color=INK)
    ax.set_title(f"{title} (threshold = {THRESHOLD})",
                 fontsize=12, color=INK, pad=12)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / f"{prefix}confusion_matrix.png",
                bbox_inches="tight")
    plt.close(fig)
    return cm


def plot_pr_curve(y_true, y_score, prefix: str):
    recall, precision, ap = pr_points(y_true, y_score)
    fig, ax = plt.subplots(figsize=(5.6, 4.4), dpi=200)
    style_axes(ax)
    ax.plot(recall, precision, color=BLUE, linewidth=2)
    ax.fill_between(recall, precision, color=BLUE, alpha=0.08)
    ax.axhline(y_true.mean(), color=INK_MUTED, linewidth=1.2, linestyle="--")
    ax.text(0.02, y_true.mean() - 0.03, "no-skill baseline",
            fontsize=9, color=INK_MUTED, va="top")
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Recall (spoofs caught)", fontsize=11, color=INK)
    ax.set_ylabel("Precision (flagged = actual spoof)", fontsize=11, color=INK)
    ax.set_title(f"Precision-Recall Curve (AP = {ap:.3f})",
                 fontsize=12, color=INK, pad=12)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / f"{prefix}pr_curve.png", bbox_inches="tight")
    plt.close(fig)
    return ap


def plot_roc_curve(y_true, y_score, prefix: str):
    fpr, tpr, auc = roc_points(y_true, y_score)
    fig, ax = plt.subplots(figsize=(5.6, 4.4), dpi=200)
    style_axes(ax)
    ax.plot([0, 1], [0, 1], color=INK_MUTED, linewidth=1.2, linestyle="--")
    ax.text(0.62, 0.56, "random guess", fontsize=9, color=INK_MUTED,
            rotation=38, rotation_mode="anchor")
    ax.plot(fpr, tpr, color=BLUE, linewidth=2)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("False Positive Rate", fontsize=11, color=INK)
    ax.set_ylabel("True Positive Rate", fontsize=11, color=INK)
    ax.set_title(f"ROC Curve (AUC = {auc:.3f})", fontsize=12, color=INK, pad=12)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / f"{prefix}roc_curve.png", bbox_inches="tight")
    plt.close(fig)
    return auc


def run_level(name: str, prefix: str, y_true, y_score, cm_title: str):
    cm = plot_confusion_matrix(y_true, y_score, prefix, cm_title)
    ap = plot_pr_curve(y_true, y_score, prefix)
    auc = plot_roc_curve(y_true, y_score, prefix)
    print(f"\n{name}: {len(y_true)} samples "
          f"({int(y_true.sum())} spoof, {int((1 - y_true).sum())} real)")
    print("confusion matrix [rows=true real/spoof, cols=pred real/spoof]:")
    print(cm)
    print(f"AP  = {ap:.4f}")
    print(f"AUC = {auc:.4f}")


def main():
    FIGURES_DIR.mkdir(exist_ok=True)
    run_level("FRAME-LEVEL", "frame_",
              *load_samples("frames.csv", "score"),
              cm_title="Anti-Spoof Confusion Matrix, per frame")
    run_level("VIDEO-LEVEL", "video_",
              *load_samples("videos.csv", "mean_score"),
              cm_title="Anti-Spoof Confusion Matrix, per video")
    print(f"\nfigures written to {FIGURES_DIR}")


if __name__ == "__main__":
    main()
