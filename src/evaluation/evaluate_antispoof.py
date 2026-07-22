"""
Anti-spoofing evaluation on a video test set.

Runs the EXACT production liveness pipeline (InsightFace detection +
MiniFASNet ensemble via ai_service.check_liveness) over a dataset of
real and attack videos, then reports standard PAD metrics:

    frame-level and video-level —
    Accuracy, Precision, Recall, F1,
    APCER (attacks accepted), BPCER (real rejected), ACER,
    FAR / FRR / HTER, ROC AUC, EER (+ EER threshold),
    best-ACER threshold from a full threshold sweep.

Dataset layout (videos may be nested in subfolders):

    <real-dir>/**/*.mp4      genuine (bona fide) presentations
    <attack-dir>/**/*.mp4    presentation attacks (print / replay / mask)

Usage:
    .venv/bin/python src/evaluation/evaluate_antispoof.py \
        --real-dir  /path/to/real_videos \
        --attack-dir /path/to/attack_videos \
        [--frames-per-video 20] [--threshold 0.85] \
        [--out-dir data/eval/antispoof_results]

Outputs (in --out-dir):
    frames.csv     one row per sampled frame (video, label, score, verdict)
    videos.csv     one row per video (aggregated mean score, decision)
    summary.json   all computed metrics
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Django bootstrap so ai_service (and its settings) load exactly as in prod
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = PROJECT_ROOT / "web"
sys.path.insert(0, str(WEB_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "attendance_project.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from ai_service import ai_service  # noqa: E402

import cv2  # noqa: E402

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def find_videos(directory: Path) -> list:
    videos = sorted(
        p for p in directory.rglob("*")
        if p.suffix.lower() in VIDEO_EXTENSIONS and not p.name.startswith(".")
    )
    return videos


def sample_frame_indices(total_frames: int, n_samples: int) -> list:
    """Evenly spaced frame indices across the whole video."""
    if total_frames <= 0:
        return []
    n = min(n_samples, total_frames)
    return sorted(set(np.linspace(0, total_frames - 1, n, dtype=int).tolist()))


def largest_face(faces):
    def area(f):
        x1, y1, x2, y2 = f.bbox
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    return max(faces, key=area) if faces else None


def evaluate_video(path: Path, label: str, frames_per_video: int) -> list:
    """Return a list of per-frame result dicts for one video."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        print(f"  !! cannot open {path.name}")
        return []

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    indices = sample_frame_indices(total, frames_per_video)
    rows = []

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue

        faces = ai_service.detect_faces(frame)
        face = largest_face(faces)
        if face is None:
            rows.append({
                "video": str(path), "label": label, "frame": idx,
                "verdict": "no_face", "score": None, "bbox": None,
            })
            continue

        verdict, score = ai_service.check_liveness(frame, face)
        rows.append({
            "video": str(path), "label": label, "frame": idx,
            "verdict": verdict,
            # too_small/error scores are 0.0 placeholders, not model output
            "score": score if verdict in ("real", "spoof") else None,
            "bbox": [round(float(v), 2) for v in face.bbox[:4]],
        })

    cap.release()
    return rows


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def binary_metrics(y_true: np.ndarray, y_score: np.ndarray, threshold: float) -> dict:
    """y_true: 1 = real (bona fide), 0 = attack. Predict real if score >= t."""
    y_pred = (y_score >= threshold).astype(int)

    tp = int(np.sum((y_true == 1) & (y_pred == 1)))  # real accepted
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))  # attack rejected
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))  # attack ACCEPTED  (bad)
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))  # real REJECTED

    n_real = tp + fn
    n_attack = tn + fp

    apcer = fp / n_attack if n_attack else 0.0   # = FAR
    bpcer = fn / n_real if n_real else 0.0       # = FRR

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / n_real if n_real else 0.0

    return {
        "threshold": round(threshold, 4),
        "n_real": n_real,
        "n_attack": n_attack,
        "tp_real_accepted": tp,
        "tn_attack_rejected": tn,
        "fp_attack_accepted": fp,
        "fn_real_rejected": fn,
        "accuracy": round((tp + tn) / len(y_true), 4) if len(y_true) else 0.0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4)
              if (precision + recall) else 0.0,
        "apcer_far": round(apcer, 4),
        "bpcer_frr": round(bpcer, 4),
        "acer_hter": round((apcer + bpcer) / 2, 4),
    }


def roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """AUC via the Mann-Whitney U statistic (rank-based, handles ties)."""
    pos = y_score[y_true == 1]
    neg = y_score[y_true == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]))
    ranks = np.empty(len(order), dtype=float)
    ranks[order] = np.arange(1, len(order) + 1)
    # average ranks for ties
    combined = np.concatenate([pos, neg])
    for value in np.unique(combined):
        mask = combined == value
        ranks[mask] = ranks[mask].mean()
    r_pos = ranks[: len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def threshold_sweep(y_true: np.ndarray, y_score: np.ndarray) -> dict:
    """Find EER and the threshold minimising ACER."""
    candidates = np.unique(np.concatenate([y_score, [0.0, 1.0]]))
    best_eer, eer_t, smallest_gap = 1.0, 0.5, float("inf")
    best_acer, acer_t = 1.0, 0.5

    for t in candidates:
        m = binary_metrics(y_true, y_score, float(t))
        far, frr = m["apcer_far"], m["bpcer_frr"]
        gap = abs(far - frr)
        if gap < smallest_gap:  # EER: where FAR and FRR cross
            smallest_gap = gap
            best_eer, eer_t = (far + frr) / 2, float(t)
        if m["acer_hter"] < best_acer:
            best_acer, acer_t = m["acer_hter"], float(t)

    return {
        "eer": round(best_eer, 4),
        "eer_threshold": round(eer_t, 4),
        "min_acer": round(best_acer, 4),
        "min_acer_threshold": round(acer_t, 4),
    }


def simulate_production_policy(frame_rows: list, frame_threshold: float) -> dict:
    """
    Replay each video's frames, in order, through the REAL production
    marking rule: attendance/liveness_gate.py (rolling window mean) plus
    the per-frame verdict gate. Assumes the worst case for attacks —
    that recognition would match an enrolled student on every frame.
    """
    from attendance.liveness_gate import LivenessConfirmationTracker

    by_video = {}
    for r in frame_rows:
        by_video.setdefault((r["video"], r["label"]), []).append(r)

    results = {"real": {"marked": 0, "total": 0, "frames_to_mark": []},
               "attack": {"marked": 0, "total": 0, "frames_to_mark": []}}

    for (_video, label), rows in by_video.items():
        gate = LivenessConfirmationTracker()
        results[label]["total"] += 1
        for i, r in enumerate(sorted(rows, key=lambda x: x["frame"]), 1):
            if r["score"] is None:
                continue
            confirmed, _, _ = gate.observe(0, r["bbox"], r["score"])
            if confirmed and r["score"] >= frame_threshold:
                results[label]["marked"] += 1
                results[label]["frames_to_mark"].append(i)
                break

    for label in results:
        marks = results[label].pop("frames_to_mark")
        results[label]["marked_rate"] = round(
            results[label]["marked"] / results[label]["total"], 4
        ) if results[label]["total"] else 0.0
        results[label]["median_frames_to_mark"] = (
            float(np.median(marks)) if marks else None
        )
    return results


def aggregate_videos(frame_rows: list) -> list:
    """Mean model score per video; verdict counts for context."""
    by_video = {}
    for r in frame_rows:
        by_video.setdefault(r["video"], []).append(r)

    videos = []
    for video, rows in by_video.items():
        scores = [r["score"] for r in rows if r["score"] is not None]
        counts = {}
        for r in rows:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        videos.append({
            "video": video,
            "label": rows[0]["label"],
            "frames_sampled": len(rows),
            "frames_scored": len(scores),
            "mean_score": round(float(np.mean(scores)), 4) if scores else None,
            "median_score": round(float(np.median(scores)), 4) if scores else None,
            "verdict_counts": counts,
        })
    return videos


def level_report(name: str, y_true: np.ndarray, y_score: np.ndarray,
                 threshold: float) -> dict:
    report = {
        "operating_point": binary_metrics(y_true, y_score, threshold),
        "roc_auc": round(roc_auc(y_true, y_score), 4),
        **threshold_sweep(y_true, y_score),
    }
    op = report["operating_point"]
    print(f"\n=== {name} metrics (threshold = {threshold}) ===")
    print(f"  real: {op['n_real']}   attack: {op['n_attack']}")
    print(f"  accuracy   {op['accuracy']:.4f}    f1        {op['f1']:.4f}")
    print(f"  precision  {op['precision']:.4f}    recall    {op['recall']:.4f}")
    print(f"  APCER/FAR  {op['apcer_far']:.4f}    (attacks wrongly ACCEPTED)")
    print(f"  BPCER/FRR  {op['bpcer_frr']:.4f}    (real users wrongly REJECTED)")
    print(f"  ACER/HTER  {op['acer_hter']:.4f}")
    print(f"  ROC AUC    {report['roc_auc']:.4f}")
    print(f"  EER        {report['eer']:.4f}  at threshold {report['eer_threshold']}")
    print(f"  min ACER   {report['min_acer']:.4f}  at threshold {report['min_acer_threshold']}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-dir", required=True, type=Path,
                        help="Directory of genuine (bona fide) videos")
    parser.add_argument("--attack-dir", required=True, type=Path,
                        help="Directory of attack (spoof) videos")
    parser.add_argument("--frames-per-video", type=int, default=20,
                        help="Evenly sampled frames per video (default 20)")
    parser.add_argument("--threshold", type=float,
                        default=float(getattr(settings, "LIVENESS_THRESHOLD", 0.85)),
                        help="Operating threshold (default: production setting)")
    parser.add_argument("--out-dir", type=Path,
                        default=PROJECT_ROOT / "data" / "eval" / "antispoof_results")
    args = parser.parse_args()

    for d in (args.real_dir, args.attack_dir):
        if not d.is_dir():
            sys.exit(f"error: not a directory: {d}")

    real_videos = find_videos(args.real_dir)
    attack_videos = find_videos(args.attack_dir)
    if not real_videos or not attack_videos:
        sys.exit(f"error: found {len(real_videos)} real / "
                 f"{len(attack_videos)} attack videos — need both.")

    print(f"Found {len(real_videos)} real and {len(attack_videos)} attack videos.")
    print(f"Sampling {args.frames_per_video} frames per video; "
          f"operating threshold = {args.threshold}\n")

    frame_rows = []
    started = time.time()
    todo = [(v, "real") for v in real_videos] + [(v, "attack") for v in attack_videos]
    for i, (video, label) in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {label:6s} {video.name}")
        frame_rows.extend(evaluate_video(video, label, args.frames_per_video))
    elapsed = time.time() - started

    video_rows = aggregate_videos(frame_rows)

    # ------------------------------------------------------------------
    # Metric computation (scores exist only for 'real'/'spoof' verdicts)
    # ------------------------------------------------------------------
    scored = [r for r in frame_rows if r["score"] is not None]
    f_true = np.array([1 if r["label"] == "real" else 0 for r in scored])
    f_score = np.array([r["score"] for r in scored], dtype=float)

    scored_videos = [v for v in video_rows if v["mean_score"] is not None]
    v_true = np.array([1 if v["label"] == "real" else 0 for v in scored_videos])
    v_score = np.array([v["mean_score"] for v in scored_videos], dtype=float)

    unverifiable = {}
    for label in ("real", "attack"):
        rows = [r for r in frame_rows if r["label"] == label]
        bad = [r for r in rows if r["score"] is None]
        unverifiable[label] = {
            "frames": len(bad),
            "of_total": len(rows),
            "rate": round(len(bad) / len(rows), 4) if rows else 0.0,
            "reasons": {v: sum(1 for r in bad if r["verdict"] == v)
                        for v in set(r["verdict"] for r in bad)},
        }

    policy = simulate_production_policy(frame_rows, args.threshold)

    summary = {
        "dataset": {
            "real_dir": str(args.real_dir),
            "attack_dir": str(args.attack_dir),
            "real_videos": len(real_videos),
            "attack_videos": len(attack_videos),
            "frames_per_video": args.frames_per_video,
            "frames_total": len(frame_rows),
            "frames_scored": len(scored),
            "elapsed_seconds": round(elapsed, 1),
        },
        "unverifiable_frames": unverifiable,
        "frame_level": level_report("FRAME-LEVEL", f_true, f_score, args.threshold),
        "video_level": level_report("VIDEO-LEVEL", v_true, v_score, args.threshold),
        "production_policy": policy,
    }

    print("\n=== PRODUCTION MARKING POLICY (liveness_gate: window mean "
          f">= {getattr(settings, 'LIVENESS_CONFIRM_MEAN_SCORE', 0.80)}, "
          f"min {getattr(settings, 'LIVENESS_CONFIRM_MIN_FRAMES', 3)} frames, "
          f"+ per-frame gate) ===")
    for label in ("real", "attack"):
        p = policy[label]
        note = "auto-marked" if label == "real" else "WRONGLY MARKED"
        median = (f", median {p['median_frames_to_mark']:.0f} frames to mark"
                  if p["median_frames_to_mark"] else "")
        print(f"  {label:6s}: {p['marked']}/{p['total']} {note} "
              f"({p['marked_rate']:.1%}{median})")

    print("\nUnverifiable frames (no_face / too_small / error — never marked "
          "in production):")
    for label, info in unverifiable.items():
        print(f"  {label:6s}: {info['frames']}/{info['of_total']} "
              f"({info['rate']:.1%})  {info['reasons']}")

    # ------------------------------------------------------------------
    # Persist results
    # ------------------------------------------------------------------
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with open(args.out_dir / "frames.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["video", "label", "frame",
                                               "verdict", "score", "bbox"])
        writer.writeheader()
        for r in frame_rows:
            row = dict(r)
            row["bbox"] = json.dumps(row["bbox"]) if row["bbox"] else ""
            writer.writerow(row)

    with open(args.out_dir / "videos.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["video", "label", "frames_sampled",
                                               "frames_scored", "mean_score",
                                               "median_score", "verdict_counts"])
        writer.writeheader()
        for v in video_rows:
            row = dict(v)
            row["verdict_counts"] = json.dumps(row["verdict_counts"])
            writer.writerow(row)

    with open(args.out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nResults written to {args.out_dir}/ "
          f"(frames.csv, videos.csv, summary.json)")


if __name__ == "__main__":
    main()
