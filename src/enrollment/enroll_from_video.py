"""
Enroll a student from a phone video file.

This is the laptop equivalent of extract_faces_enrollment.ipynb
but writes directly to PostgreSQL instead of .npz/.pkl files.

Usage:
    python -m src.enrollment.enroll_from_video

    Or with arguments:
    python -m src.enrollment.enroll_from_video --video path/to/video.mp4 --roll 780350 --name "New Student"
"""

import cv2
import os
import sys
import argparse
import numpy as np
import logging
import time
from collections import defaultdict

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
logging.getLogger('insightface').setLevel(logging.ERROR)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.settings import (
    INSIGHTFACE_MODEL, DET_SIZE, DET_THRESH, FACES_DIR
)
from core.db_manager import insert_student, get_student, get_all_embeddings
from enrollment.enroll_utils import verify_unique_identity

from insightface.app import FaceAnalysis

# ==============================================================
# ENROLLMENT CONFIGURATION
# ==============================================================

EXTRACT_INTERVAL_SECONDS = 0.25
MIN_FACE_SIZE = 50
MAX_FACES_PER_FRAME = 1
MIN_DET_SCORE = 0.6
MAX_YAW_PROXY = 0.35
MAX_ROLL_ANGLE = 30
MIN_EYE_DISTANCE = 15
MIN_FACE_AREA_RATIO = 0.005
EDGE_MARGIN = 10
DUPLICATE_COSINE_THRESH = 0.95
IMAGE_QUALITY = 95


# ==============================================================
# FACE QUALITY CHECK
# ==============================================================

def check_face_quality(face, frame_shape):
    """Comprehensive quality check — identical to your Colab version."""
    bbox = face.bbox.astype(int)
    kps = face.kps
    score = face.det_score
    frame_h, frame_w = frame_shape[:2]

    if score < MIN_DET_SCORE:
        return False, "low_conf"

    x1, y1, x2, y2 = bbox
    face_w, face_h = x2 - x1, y2 - y1

    if face_w < MIN_FACE_SIZE or face_h < MIN_FACE_SIZE:
        return False, "too_small"

    if (face_w * face_h) / (frame_w * frame_h) < MIN_FACE_AREA_RATIO:
        return False, "area_ratio"

    if (x1 < EDGE_MARGIN or y1 < EDGE_MARGIN or
            x2 > frame_w - EDGE_MARGIN or y2 > frame_h - EDGE_MARGIN):
        return False, "at_edge"

    if kps is None:
        return False, "no_landmarks"

    left_eye, right_eye, nose = kps[0], kps[1], kps[2]
    mouth_left, mouth_right = kps[3], kps[4]

    eye_dist = np.linalg.norm(right_eye - left_eye)
    if eye_dist < MIN_EYE_DISTANCE:
        return False, "eye_dist"

    dy = right_eye[1] - left_eye[1]
    dx = right_eye[0] - left_eye[0]
    if abs(np.degrees(np.arctan2(dy, dx))) > MAX_ROLL_ANGLE:
        return False, "roll"

    eye_center_x = (left_eye[0] + right_eye[0]) / 2
    if eye_dist > 0 and abs(nose[0] - eye_center_x) / eye_dist > MAX_YAW_PROXY:
        return False, "yaw"

    if mouth_left[1] < nose[1] or mouth_right[1] < nose[1]:
        return False, "bad_landmarks"

    if not hasattr(face, 'embedding') or face.embedding is None:
        return False, "no_embedding"

    return True, "passed"


# ==============================================================
# DUPLICATE REMOVAL
# ==============================================================

def remove_duplicates(embeddings_list, face_data_list):
    """Remove near-duplicate faces based on cosine similarity."""
    if len(embeddings_list) <= 1:
        return embeddings_list, face_data_list

    embeddings = np.array(embeddings_list)
    n = len(embeddings)
    keep_mask = np.ones(n, dtype=bool)

    for i in range(n):
        if not keep_mask[i]:
            continue
        for j in range(i + 1, n):
            if not keep_mask[j]:
                continue
            sim = np.dot(embeddings[i], embeddings[j])
            if sim > DUPLICATE_COSINE_THRESH:
                keep_mask[j] = False

    kept = np.where(keep_mask)[0]
    removed = n - len(kept)
    if removed > 0:
        print(f"    [DEDUP] Removed {removed} near-duplicates, kept {len(kept)}")

    return [embeddings_list[i] for i in kept], [face_data_list[i] for i in kept]


# ==============================================================
# MAIN ENROLLMENT FROM VIDEO
# ==============================================================

def enroll_from_video(video_path, roll_no, name, department="Computer",
                      semester=8, detector=None, save_crops=True):
    """
    Extract faces from video and enroll directly into PostgreSQL.
    """

    # Initialize detector if not provided
    if detector is None:
        print("[INIT] Loading InsightFace model...")
        detector = FaceAnalysis(
            name=INSIGHTFACE_MODEL,
            providers=['CPUExecutionProvider'],
            allowed_modules=['detection', 'recognition']
        )
        detector.prepare(ctx_id=-1, det_size=DET_SIZE, det_thresh=DET_THRESH)
        print("[INIT] ✓ Model ready (CPU)")

    # Check if re-enrollment
    is_re_enrollment = False
    existing = get_student(roll_no)
    if existing:
        print(f"\n  ⚠ Student {roll_no} ({existing['name']}) already enrolled!")
        confirm = input("  Re-enroll (overwrite)? (y/n): ").strip().lower()
        if confirm != 'y':
            print("  Cancelled.")
            return None
        is_re_enrollment = True

    # Open video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  [ERROR] Cannot open video: {video_path}")
        return None

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    frame_interval = max(1, int(fps * EXTRACT_INTERVAL_SECONDS))

    print(f"\n  {'─' * 55}")
    print(f"  Enrolling: {name} (Roll: {roll_no})")
    print(f"  Video: {os.path.basename(video_path)}")
    print(f"  Duration: {duration:.1f}s | FPS: {fps:.1f} | "
          f"Total: {total_frames} | Sample every: {frame_interval} frames")
    print(f"  {'─' * 55}")

    embeddings_list = []
    face_data_list = []
    stats = defaultdict(int)
    frame_idx = 0
    start_time = time.time()

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            stats['sampled'] += 1
            faces = detector.get(frame)

            if len(faces) == 0:
                stats['no_detection'] += 1
            elif len(faces) > MAX_FACES_PER_FRAME:
                stats['multiple_faces'] += 1
            else:
                face = faces[0]
                passed, reason = check_face_quality(face, frame.shape)

                if passed:
                    from insightface.utils.face_align import norm_crop
                    aligned = norm_crop(frame, face.kps, image_size=112, mode='arcface')

                    embedding = face.embedding.copy()
                    embedding = embedding / np.linalg.norm(embedding)

                    embeddings_list.append(embedding)
                    face_data_list.append({
                        'aligned_face': aligned,
                        'det_score': float(face.det_score),
                        'frame_idx': frame_idx,
                    })
                    stats['passed'] += 1
                else:
                    stats[reason] += 1

            # Progress
            if stats['sampled'] % 20 == 0:
                progress = (frame_idx / total_frames) * 100 if total_frames > 0 else 0
                print(f"    Progress: {progress:.0f}% | Passed: {stats['passed']}", end='\r')

        frame_idx += 1

    cap.release()
    elapsed = time.time() - start_time

    if len(embeddings_list) == 0:
        print(f"\n  ✗ No valid faces extracted! Check video quality.")
        return None

    # Deduplicate
    pre_dedup = len(embeddings_list)
    embeddings_list, face_data_list = remove_duplicates(embeddings_list, face_data_list)
    stats['duplicates_removed'] = pre_dedup - len(embeddings_list)

    # Compute centroid
    embeddings_array = np.array(embeddings_list)
    centroid = np.mean(embeddings_array, axis=0)
    centroid = centroid / np.linalg.norm(centroid)

    # Quality metrics
    sims = embeddings_array @ centroid
    intra_mean = float(np.mean(sims))
    intra_min = float(np.min(sims))
    intra_std = float(np.std(sims))

    # ══════════════════════════════════════════════════════════
    # DUPLICATE FACE CHECK — prevent same face under different roll
    # ══════════════════════════════════════════════════════════
    print(f"\n    Checking for duplicate identity...")
    allowed, message = verify_unique_identity(centroid, roll_no, is_re_enrollment)
    print(f"    {message}")

    if not allowed:
        print(f"\n  ✗ ENROLLMENT CANCELLED — duplicate face detected!")
        print(f"    The video contains a face that matches an already-enrolled student.")
        print(f"    No data was saved.")
        return None
    # ══════════════════════════════════════════════════════════

    # Save face crops
    photo_path = None
    if save_crops:
        face_dir = os.path.join(FACES_DIR, roll_no)
        os.makedirs(face_dir, exist_ok=True)

        det_scores = [d['det_score'] for d in face_data_list]
        best_idx = int(np.argmax(det_scores))

        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), IMAGE_QUALITY]
        for i, data in enumerate(face_data_list):
            filename = f"{roll_no}_{i:04d}.jpg"
            cv2.imwrite(os.path.join(face_dir, filename), data['aligned_face'], encode_params)

        photo_path = os.path.join(face_dir, f"{roll_no}_{best_idx:04d}.jpg")

    # Insert into database
    insert_student(
        roll_no=roll_no,
        name=name,
        department=department,
        semester=semester,
        embedding=centroid,
        num_samples=len(embeddings_list),
        intra_sim_mean=intra_mean,
        intra_sim_min=intra_min,
        intra_sim_std=intra_std,
        photo_path=photo_path,
    )

    # Summary
    print(f"\n  {'═' * 55}")
    print(f"  ✓ ENROLLMENT COMPLETE")
    print(f"  {'═' * 55}")
    print(f"  Student:     {name} ({roll_no})")
    print(f"  Faces used:  {len(embeddings_list)} (from {stats['sampled']} sampled)")
    print(f"  Intra-sim:   mean={intra_mean:.4f} | min={intra_min:.4f}")
    print(f"  Time:        {elapsed:.1f}s")
    print(f"  Saved to:    PostgreSQL ✓")
    if photo_path:
        print(f"  Crops:       {os.path.join(FACES_DIR, roll_no)}")

    quality = "✓ Good" if intra_mean > 0.7 else "⚠ Low" if intra_mean > 0.5 else "✗ Poor"
    print(f"  Quality:     {quality}")

    if len(embeddings_list) < 10:
        print(f"  ⚠ Only {len(embeddings_list)} faces — consider re-recording a longer video")
    print(f"  {'═' * 55}")

    return {
        'roll_no': roll_no,
        'name': name,
        'num_faces': len(embeddings_list),
        'intra_sim_mean': intra_mean,
    }


# ==============================================================
# INTERACTIVE / CLI
# ==============================================================

def interactive_enroll():
    """Interactive enrollment — prompts for video path and student info."""
    print("=" * 60)
    print("  STUDENT ENROLLMENT — From Video")
    print("=" * 60)

    video_path = input("\n  Video file path: ").strip().strip('"')
    if not os.path.exists(video_path):
        print(f"  ✗ File not found: {video_path}")
        return

    roll_no = input("  Roll number: ").strip()
    name = input("  Student name: ").strip()
    department = input("  Department (default=Computer): ").strip() or "Computer"
    semester = input("  Semester (default=8): ").strip()
    semester = int(semester) if semester else 8

    print(f"\n  Enrolling {name} ({roll_no}) from {os.path.basename(video_path)}...")
    confirm = input("  Proceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print("  Cancelled.")
        return

    enroll_from_video(video_path, roll_no, name, department, semester)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enroll student from video")
    parser.add_argument('--video', type=str, help='Path to video file')
    parser.add_argument('--roll', type=str, help='Roll number')
    parser.add_argument('--name', type=str, help='Student name')
    parser.add_argument('--dept', type=str, default='Computer')
    parser.add_argument('--sem', type=int, default=8)
    args = parser.parse_args()

    if args.video and args.roll and args.name:
        enroll_from_video(args.video, args.roll, args.name, args.dept, args.sem)
    else:
        interactive_enroll()