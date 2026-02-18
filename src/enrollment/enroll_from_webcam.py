"""
Enroll a student using laptop webcam — live capture.

Opens webcam, shows live feed with face detection overlay,
captures frames when face quality is good, and enrolls
directly into PostgreSQL.

Controls:
    SPACE  — Start/stop capture
    q/ESC  — Quit without enrolling
    e      — Finish capture and enroll

Usage:
    python -m src.enrollment.enroll_from_webcam
"""

import cv2
import os
import sys
import numpy as np
import time
import logging

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
logging.getLogger('insightface').setLevel(logging.ERROR)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.settings import (
    CAMERA_INDEX, INSIGHTFACE_MODEL, DET_SIZE, DET_THRESH, FACES_DIR
)
from core.db_manager import insert_student, get_student, get_all_embeddings
from enrollment.enroll_utils import verify_unique_identity

from insightface.app import FaceAnalysis
from insightface.utils.face_align import norm_crop

# Enrollment settings
TARGET_FACES = 25
MAX_FACES = 50
MIN_DET_SCORE = 0.65
MIN_FACE_SIZE = 80
MAX_YAW_PROXY = 0.30
MAX_ROLL_ANGLE = 25
MIN_EYE_DISTANCE = 20
DUPLICATE_COSINE_THRESH = 0.95
CAPTURE_INTERVAL_FRAMES = 5
IMAGE_QUALITY = 95


def check_quality(face, frame_shape):
    """Quality check for webcam enrollment."""
    bbox = face.bbox.astype(int)
    kps = face.kps
    score = face.det_score
    h, w = frame_shape[:2]

    if score < MIN_DET_SCORE:
        return False, "Low confidence"

    x1, y1, x2, y2 = bbox
    fw, fh = x2 - x1, y2 - y1

    if fw < MIN_FACE_SIZE or fh < MIN_FACE_SIZE:
        return False, "Too far — come closer"

    if x1 < 10 or y1 < 10 or x2 > w - 10 or y2 > h - 10:
        return False, "Face at edge"

    if kps is None:
        return False, "No landmarks"

    left_eye, right_eye, nose = kps[0], kps[1], kps[2]

    eye_dist = np.linalg.norm(right_eye - left_eye)
    if eye_dist < MIN_EYE_DISTANCE:
        return False, "Too far"

    dy = right_eye[1] - left_eye[1]
    dx = right_eye[0] - left_eye[0]
    if abs(np.degrees(np.arctan2(dy, dx))) > MAX_ROLL_ANGLE:
        return False, "Head tilted"

    eye_center_x = (left_eye[0] + right_eye[0]) / 2
    if eye_dist > 0 and abs(nose[0] - eye_center_x) / eye_dist > MAX_YAW_PROXY:
        return False, "Turn face forward"

    if face.embedding is None:
        return False, "No embedding"

    return True, "Good"


def webcam_enroll():
    """Interactive webcam enrollment."""

    print("=" * 60)
    print("  STUDENT ENROLLMENT — Webcam Capture")
    print("=" * 60)

    # Get student info
    roll_no = input("\n  Roll number: ").strip()
    if not roll_no:
        print("  ✗ Roll number required!")
        return

    # Check if re-enrollment
    is_re_enrollment = False
    existing = get_student(roll_no)
    if existing:
        print(f"  ⚠ {roll_no} ({existing['name']}) already enrolled!")
        confirm = input("  Re-enroll (overwrite)? (y/n): ").strip().lower()
        if confirm != 'y':
            print("  Cancelled.")
            return
        is_re_enrollment = True

    name = input("  Student name: ").strip()
    if not name:
        print("  ✗ Name required!")
        return

    department = input("  Department (default=Computer): ").strip() or "Computer"
    semester = input("  Semester (default=8): ").strip()
    semester = int(semester) if semester else 8

    # Init detector
    print(f"\n[INIT] Loading model...")
    detector = FaceAnalysis(
        name=INSIGHTFACE_MODEL,
        providers=['CPUExecutionProvider'],
        allowed_modules=['detection', 'recognition']
    )
    detector.prepare(ctx_id=-1, det_size=DET_SIZE, det_thresh=DET_THRESH)

    # Open webcam
    print(f"[CAM] Opening camera...")
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("[ERROR] Cannot open camera!")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print(f"\n[INSTRUCTIONS]")
    print(f"  1. Position face in the frame")
    print(f"  2. Press SPACE to start capturing")
    print(f"  3. Slowly turn head: left, right, up, down")
    print(f"  4. System captures automatically when quality is good")
    print(f"  5. Press 'e' to finish and enroll (need {TARGET_FACES}+ faces)")
    print(f"  6. Press 'q' to quit without enrolling")

    embeddings_list = []
    face_data_list = []
    capturing = False
    frame_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            frame_count += 1
            display = frame.copy()
            h, w = frame.shape[:2]

            # Detect
            faces = detector.get(frame)

            status_text = ""
            status_color = (200, 200, 200)

            if len(faces) == 0:
                status_text = "No face detected"
                status_color = (0, 0, 255)

            elif len(faces) > 1:
                status_text = "Multiple faces — only 1 person please"
                status_color = (0, 0, 255)

            elif len(faces) == 1:
                face = faces[0]
                passed, reason = check_quality(face, frame.shape)
                bbox = face.bbox.astype(int)

                if passed:
                    color = (0, 255, 0)
                    status_text = f"Quality: Good | Captured: {len(embeddings_list)}/{TARGET_FACES}"
                    status_color = (0, 255, 0)

                    # Auto-capture if capturing mode is on
                    if capturing and frame_count % CAPTURE_INTERVAL_FRAMES == 0:
                        if len(embeddings_list) < MAX_FACES:
                            aligned = norm_crop(frame, face.kps, image_size=112, mode='arcface')
                            emb = face.embedding.copy()
                            emb = emb / np.linalg.norm(emb)

                            # Check not too similar to last capture
                            is_dup = False
                            if embeddings_list:
                                last_sim = np.dot(embeddings_list[-1], emb)
                                if last_sim > DUPLICATE_COSINE_THRESH:
                                    is_dup = True

                            if not is_dup:
                                embeddings_list.append(emb)
                                face_data_list.append({
                                    'aligned_face': aligned,
                                    'det_score': float(face.det_score),
                                })

                                # Flash green briefly
                                cv2.rectangle(display, (0, 0), (w, h), (0, 255, 0), 8)
                else:
                    color = (0, 165, 255)
                    status_text = f"{reason} | Captured: {len(embeddings_list)}"
                    status_color = (0, 165, 255)

                # Draw bbox
                cv2.rectangle(display, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)

                if face.kps is not None:
                    for kp in face.kps.astype(int):
                        cv2.circle(display, tuple(kp), 3, color, -1)

            # ── UI Overlay ──
            overlay = display.copy()
            cv2.rectangle(overlay, (0, 0), (w, 90), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.6, display, 0.4, 0, display)

            cv2.putText(display, f"Enrollment: {name} ({roll_no})", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(display, status_text, (10, 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 1)

            mode_text = "CAPTURING" if capturing else "PAUSED — Press SPACE to start"
            mode_color = (0, 255, 0) if capturing else (0, 255, 255)
            cv2.putText(display, mode_text, (w - 400, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, mode_color, 2)

            # Progress bar
            progress = min(len(embeddings_list) / TARGET_FACES, 1.0)
            bar_w = 300
            cv2.rectangle(display, (10, 70), (10 + bar_w, 85), (50, 50, 50), -1)
            cv2.rectangle(display, (10, 70), (10 + int(bar_w * progress), 85), (0, 255, 0), -1)
            cv2.putText(display, f"{len(embeddings_list)}/{TARGET_FACES}", (bar_w + 20, 83),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            if len(embeddings_list) >= TARGET_FACES:
                cv2.putText(display, "Ready! Press 'e' to enroll", (10, h - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.putText(display, "[SPACE] Capture  [E] Enroll  [Q] Quit",
                        (w - 380, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

            cv2.imshow('Enrollment', display)

            # ── Keys ──
            key = cv2.waitKey(1) & 0xFF

            if key == ord(' '):
                capturing = not capturing
                state = "STARTED" if capturing else "PAUSED"
                print(f"  [CAPTURE] {state} — {len(embeddings_list)} faces so far")

            elif key == ord('e'):
                if len(embeddings_list) < 5:
                    print(f"  ⚠ Need at least 5 faces (have {len(embeddings_list)})")
                else:
                    break

            elif key == ord('q') or key == 27:
                print("  Cancelled.")
                cap.release()
                cv2.destroyAllWindows()
                return

    finally:
        cap.release()
        cv2.destroyAllWindows()

    # ── Process and enroll ──
    if len(embeddings_list) < 5:
        print(f"  ✗ Not enough faces captured ({len(embeddings_list)})")
        return

    print(f"\n  Processing {len(embeddings_list)} captured faces...")

    embeddings_array = np.array(embeddings_list)
    centroid = np.mean(embeddings_array, axis=0)
    centroid = centroid / np.linalg.norm(centroid)

    sims = embeddings_array @ centroid
    intra_mean = float(np.mean(sims))
    intra_min = float(np.min(sims))
    intra_std = float(np.std(sims))

    # ══════════════════════════════════════════════════════════
    # DUPLICATE FACE CHECK — the critical guard
    # ══════════════════════════════════════════════════════════
    print(f"\n  Checking for duplicate identity...")
    allowed, message = verify_unique_identity(centroid, roll_no, is_re_enrollment)
    print(f"  {message}")

    if not allowed:
        print(f"\n  ✗ ENROLLMENT CANCELLED — duplicate face detected!")
        print(f"    The captured face belongs to an already-enrolled student.")
        print(f"    No data was saved.")
        return
    # ══════════════════════════════════════════════════════════

    # Save crops
    face_dir = os.path.join(FACES_DIR, roll_no)
    os.makedirs(face_dir, exist_ok=True)
    det_scores = [d['det_score'] for d in face_data_list]
    best_idx = int(np.argmax(det_scores))

    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), IMAGE_QUALITY]
    for i, data in enumerate(face_data_list):
        cv2.imwrite(
            os.path.join(face_dir, f"{roll_no}_{i:04d}.jpg"),
            data['aligned_face'], encode_params
        )
    photo_path = os.path.join(face_dir, f"{roll_no}_{best_idx:04d}.jpg")

    # Insert
    insert_student(
        roll_no=roll_no, name=name, department=department, semester=semester,
        embedding=centroid, num_samples=len(embeddings_list),
        intra_sim_mean=intra_mean, intra_sim_min=intra_min,
        intra_sim_std=intra_std, photo_path=photo_path,
    )

    print(f"\n  {'═' * 55}")
    print(f"  ✓ ENROLLED: {name} ({roll_no})")
    print(f"  Faces: {len(embeddings_list)} | Intra-sim: {intra_mean:.4f}")
    quality = "✓ Good" if intra_mean > 0.7 else "⚠ Low"
    print(f"  Quality: {quality}")
    print(f"  {'═' * 55}")


if __name__ == "__main__":
    webcam_enroll()