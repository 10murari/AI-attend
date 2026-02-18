"""
Live Attendance Marking System.

Opens laptop webcam, detects faces in real-time, recognizes them
against enrolled gallery, and logs attendance.

Controls:
    q / ESC     — Stop session and end attendance
    p           — Pause/resume recognition
    s           — Show current stats
    r           — Reload gallery (if new students enrolled)

Usage:
    python -m src.attendance.mark_attendance
"""

import cv2
import numpy as np
import time
import sys
import os
import logging

# Suppress noisy logs
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
logging.getLogger('insightface').setLevel(logging.ERROR)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.settings import (
    CAMERA_INDEX, PROCESS_EVERY_N_FRAMES, DISPLAY_RESOLUTION,
    INSIGHTFACE_MODEL, DET_SIZE, DET_THRESH, MIN_DET_SCORE
)
from core.face_recognizer import FaceRecognizer
from attendance.attendance_logger import AttendanceLogger

from insightface.app import FaceAnalysis


def init_face_detector():
    """Initialize InsightFace for detection + embedding."""
    print("[INIT] Loading InsightFace model...")
    app = FaceAnalysis(
        name=INSIGHTFACE_MODEL,
        providers=['CPUExecutionProvider'],     # CPU for laptop
        allowed_modules=['detection', 'recognition']
    )
    app.prepare(ctx_id=-1, det_size=DET_SIZE, det_thresh=DET_THRESH)
    print(f"[INIT] ✓ Model ready (CPU) | Det: {DET_SIZE} | Thresh: {DET_THRESH}")
    return app


def draw_overlay(frame, face, result, is_marked):
    """
    Draw bounding box, name, and confidence on frame.

    Green  = recognized & marked present
    Yellow = recognized but already marked (duplicate)
    Red    = unknown person
    """
    bbox = face.bbox.astype(int)
    x1, y1, x2, y2 = bbox

    roll = result['roll_no']
    name = result['name']
    conf = result['confidence']

    if roll == 'UNKNOWN':
        color = (0, 0, 255)       # Red
        label = f"UNKNOWN ({conf:.2f})"
    elif is_marked == 'DUPLICATE':
        color = (0, 255, 255)     # Yellow
        label = f"{name} [{roll}] (marked)"
    else:
        color = (0, 255, 0)       # Green
        label = f"{name} [{roll}] {conf:.2f}"

    # Bounding box
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    # Label background
    label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), (x1 + label_size[0], y1), color, -1)

    # Label text
    cv2.putText(frame, label, (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    # Landmarks (small dots)
    if face.kps is not None:
        for kp in face.kps.astype(int):
            cv2.circle(frame, tuple(kp), 2, color, -1)

    return frame


def draw_stats_panel(frame, stats, session_name, fps, paused):
    """Draw stats overlay at the top of the frame."""
    h, w = frame.shape[:2]

    # Semi-transparent background
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 80), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    # Session info
    cv2.putText(frame, f"Session: {session_name}", (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    # Stats
    present = stats.get('present', 0)
    total = stats.get('total', 0)
    rate = stats.get('rate', 0)
    remaining = stats.get('remaining', 0)

    cv2.putText(frame, f"Present: {present}/{total} ({rate}%)", (10, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    cv2.putText(frame, f"Remaining: {remaining}", (300, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    # FPS and controls
    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    status_text = "PAUSED" if paused else "RECORDING"
    status_color = (0, 0, 255) if paused else (0, 255, 0)
    cv2.putText(frame, status_text, (w - 150, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 2)

    # Controls hint
    cv2.putText(frame, "[Q]uit  [P]ause  [S]tats", (w - 250, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

    return frame


def run_attendance():
    """Main attendance marking loop."""

    print("=" * 60)
    print("  LIVE ATTENDANCE SYSTEM")
    print("=" * 60)

    # ── Get session info from user ──
    print("\n  Enter session details:")
    session_name = input("  Session name (e.g., CSE301_Lecture_1): ").strip()
    if not session_name:
        session_name = f"Session_{time.strftime('%Y%m%d_%H%M')}"

    subject = input("  Subject (optional, press Enter to skip): ").strip() or None
    teacher = input("  Teacher (optional, press Enter to skip): ").strip() or None

    # ── Initialize components ──
    detector = init_face_detector()

    recognizer = FaceRecognizer()
    recognizer.load_gallery()
    if not recognizer.loaded:
        print("[ERROR] No gallery loaded. Run migration first!")
        return

    logger = AttendanceLogger()
    session_id = logger.start_session(session_name, subject=subject, teacher=teacher)

    # ── Open webcam ──
    print(f"\n[CAM] Opening camera {CAMERA_INDEX}...")
    cap = cv2.VideoCapture(CAMERA_INDEX)

    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera {CAMERA_INDEX}")
        print("  Try: change CAMERA_INDEX in settings.py")
        return

    # Set resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, DISPLAY_RESOLUTION[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, DISPLAY_RESOLUTION[1])

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[CAM] ✓ Camera opened: {actual_w}x{actual_h}")
    print(f"\n[SYSTEM] ✓ Attendance system running!")
    print(f"[SYSTEM]   Press 'q' or ESC to end session\n")

    # ── Main loop ──
    frame_count = 0
    paused = False
    fps = 0
    fps_start = time.time()
    fps_frame_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[CAM] Frame read failed — retrying...")
                time.sleep(0.1)
                continue

            frame_count += 1
            display_frame = frame.copy()

            # FPS calculation
            fps_frame_count += 1
            elapsed = time.time() - fps_start
            if elapsed >= 1.0:
                fps = fps_frame_count / elapsed
                fps_frame_count = 0
                fps_start = time.time()

            # ── Process frame (if not paused and on interval) ──
            if not paused and frame_count % PROCESS_EVERY_N_FRAMES == 0:
                faces = detector.get(frame)

                for face in faces:
                    # Skip low-confidence detections
                    if face.det_score < MIN_DET_SCORE:
                        continue

                    # Skip if no embedding (shouldn't happen but safety)
                    if face.embedding is None:
                        continue

                    # Normalize embedding
                    embedding = face.embedding.copy()
                    norm = np.linalg.norm(embedding)
                    if norm > 0:
                        embedding = embedding / norm

                    # Recognize
                    result = recognizer.identify(embedding)

                    # Log attendance if recognized
                    mark_status = None
                    if result['roll_no'] != 'UNKNOWN':
                        mark_status = logger.mark(
                            session_id,
                            result['roll_no'],
                            result['name'],
                            result['confidence']
                        )

                    # Draw on frame
                    display_frame = draw_overlay(display_frame, face, result, mark_status)

            # ── Draw stats panel ──
            stats = logger.get_live_stats(session_id)
            display_frame = draw_stats_panel(
                display_frame, stats, session_name, fps, paused
            )

            # ── Show frame ──
            cv2.imshow('Attendance System', display_frame)

            # ── Handle keypresses ──
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q') or key == 27:    # q or ESC
                print("\n[SYSTEM] Ending session...")
                break

            elif key == ord('p'):
                paused = not paused
                state = "PAUSED" if paused else "RESUMED"
                print(f"[SYSTEM] {state}")

            elif key == ord('s'):
                stats = logger.get_live_stats(session_id)
                print(f"\n[STATS] Present: {stats['present']}/{stats['total']} "
                      f"({stats['rate']}%) | Remaining: {stats['remaining']}")

            elif key == ord('r'):
                print("[SYSTEM] Reloading gallery...")
                recognizer.load_gallery()

    except KeyboardInterrupt:
        print("\n[SYSTEM] Interrupted — ending session...")

    finally:
        # ── Cleanup ──
        cap.release()
        cv2.destroyAllWindows()

        # ── End session (mark absent + export) ──
        summary = logger.end(session_id, export_csv=True)

        print(f"\n[SYSTEM] ✓ Session complete!")


# ==============================================================
# MAIN
# ==============================================================

if __name__ == "__main__":
    run_attendance()