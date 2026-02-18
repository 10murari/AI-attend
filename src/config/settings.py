"""
Central configuration for the Attendance System.
All paths, thresholds, and database settings in one place.
"""

import os

# ==============================================================
# PROJECT ROOT
# ==============================================================
PROJECT_ROOT = "C:/Final_Project"

# ==============================================================
# DATABASE (PostgreSQL)
# ==============================================================
DB_CONFIG = {
    "dbname": "attendance_system",
    "user": "attendance_admin",
    "password": "root",     # ← CHANGE THIS
    "host": "localhost",
    "port": 5433,
}

# ==============================================================
# ENROLLMENT DATA PATHS (from Colab extraction)
# ==============================================================
ENROLLMENT_DIR = os.path.join(PROJECT_ROOT, "dataset", "enrollment")
EMBEDDINGS_DIR = os.path.join(ENROLLMENT_DIR, "embeddings")
FACES_DIR = os.path.join(ENROLLMENT_DIR, "faces_aligned")
GALLERY_DIR = os.path.join(ENROLLMENT_DIR, "gallery")
GALLERY_PKL = os.path.join(GALLERY_DIR, "enrollment_gallery.pkl")

# ==============================================================
# FACE RECOGNITION THRESHOLDS
# ==============================================================
RECOGNITION_THRESHOLD = 0.45        # Cosine similarity — start conservative
                                     # Your max cross-person sim is 0.28
                                     # So 0.45 gives safe margin
                                     # Tune after testing

RECOGNITION_TOP_K = 3               # Return top-K matches for debugging

# ==============================================================
# ATTENDANCE RULES
# ==============================================================
DUPLICATE_WINDOW_SECONDS = 300       # Ignore re-detection within 5 min
MARK_ABSENT_ON_SESSION_END = True    # Auto-mark absent when session closes

# ==============================================================
# WEBCAM / LIVE VIDEO
# ==============================================================
CAMERA_INDEX = 0                     # 0 = default laptop webcam
PROCESS_EVERY_N_FRAMES = 3          # Skip frames for performance
DISPLAY_RESOLUTION = (1280, 720)     # Display window size

# ==============================================================
# INSIGHTFACE MODEL
# ==============================================================
INSIGHTFACE_MODEL = "buffalo_l"
DET_SIZE = (640, 640)
DET_THRESH = 0.5
MIN_DET_SCORE = 0.5                  # Slightly relaxed for live video
                                      # (vs 0.6 for enrollment)

# ==============================================================
# STUDENT METADATA (for migration)
# Your 14 enrolled students
# ==============================================================
STUDENT_METADATA = {
    "780306": {"name": "Arkrisha",   "department": "Computer", "semester": 8},
    "780309": {"name": "Chitra",     "department": "Computer", "semester": 8},
    "780312": {"name": "Dibyam",     "department": "Computer", "semester": 8},
    "780314": {"name": "Jayadev",    "department": "Computer", "semester": 8},
    "780315": {"name": "Jina",       "department": "Computer", "semester": 8},
    "780317": {"name": "Kripesh",    "department": "Computer", "semester": 8},
    "780322": {"name": "Murari",     "department": "Computer", "semester": 8},
    "780324": {"name": "Nimesh",     "department": "Computer", "semester": 8},
    "780328": {"name": "Pratik",     "department": "Computer", "semester": 8},
    "780339": {"name": "Sanjib",     "department": "Computer", "semester": 8},
    "780340": {"name": "Saurav",     "department": "Computer", "semester": 8},
    "780341": {"name": "Subekshya",  "department": "Computer", "semester": 8},
    "780343": {"name": "Sumit",      "department": "Computer", "semester": 8},
    "780349": {"name": "Kiran",      "department": "Computer", "semester": 8},
}