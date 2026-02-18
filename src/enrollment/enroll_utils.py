"""
Shared enrollment utilities.

Used by both enroll_from_video.py and enroll_from_webcam.py
to prevent duplicate face enrollment under different roll numbers.
"""

import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.db_manager import check_duplicate_face

# Threshold for "same person" during enrollment
# Your data shows: max cross-person sim = 0.28, intra-person sim > 0.76
# So anything above 0.45 is almost certainly the same person
ENROLLMENT_DUPLICATE_THRESHOLD = 0.45


def verify_unique_identity(centroid, roll_no, is_re_enrollment=False):
    """
    Check that this face doesn't already exist under a DIFFERENT roll number.

    Args:
        centroid: 512-D embedding of the new enrollment
        roll_no: the roll number being enrolled
        is_re_enrollment: if True, skip the student's own existing entry

    Returns:
        (allowed: bool, message: str)

    Flow:
        Murari (780322) tries to enroll as 780350:
            → centroid matches 780322 (sim=0.95)
            → BLOCKED: "Face matches 780322 (Murari)"

        Murari (780322) re-enrolls as 780322:
            → exclude_roll=780322, skip own entry
            → No other match → ALLOWED

        New student (780350) enrolls:
            → No match above 0.45 → ALLOWED
    """
    exclude = roll_no if is_re_enrollment else None

    match = check_duplicate_face(
        embedding=centroid,
        exclude_roll=exclude,
        threshold=ENROLLMENT_DUPLICATE_THRESHOLD
    )

    if match:
        return False, (
            f"✗ BLOCKED: This face matches already-enrolled student "
            f"{match['roll_no']} ({match['name']}) "
            f"with similarity {match['similarity']:.4f}\n"
            f"    If this is the same person, use their existing roll number "
            f"({match['roll_no']}) to re-enroll."
        )

    return True, "✓ Face is unique — no duplicate found"