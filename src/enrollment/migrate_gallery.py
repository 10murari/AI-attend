"""
Migrate existing enrollment data (from Colab) → PostgreSQL.

Reads:
  - gallery/*.npz          (centroid embeddings)
  - embeddings/*/metadata.json  (quality metrics)
  - settings.STUDENT_METADATA   (names, department)
  - faces_aligned/*/         (reference photos)

Writes:
  - students table in PostgreSQL
"""

import os
import sys
import json
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.settings import (
    EMBEDDINGS_DIR, GALLERY_DIR, FACES_DIR, STUDENT_METADATA
)
from core.db_manager import (
    create_tables, insert_student, get_all_students,
    get_enrolled_count, get_all_embeddings
)


def load_gallery_data(person_id):
    """Load centroid embedding from .npz gallery file."""
    npz_path = os.path.join(GALLERY_DIR, f"{person_id}_gallery.npz")
    if not os.path.exists(npz_path):
        return None, None

    data = np.load(npz_path)
    centroid = data['centroid']
    all_embeddings = data['embeddings']

    # Ensure normalized
    norm = np.linalg.norm(centroid)
    if abs(norm - 1.0) > 0.01:
        centroid = centroid / norm

    return centroid, all_embeddings


def load_metadata(person_id):
    """Load extraction metadata from JSON."""
    meta_path = os.path.join(EMBEDDINGS_DIR, person_id, f"{person_id}_metadata.json")
    if not os.path.exists(meta_path):
        return {}

    with open(meta_path) as f:
        return json.load(f)


def find_best_reference_photo(person_id, metadata):
    """
    Find the best face crop to use as reference photo.
    Pick the one with the highest detection score.
    """
    face_dir = os.path.join(FACES_DIR, person_id)
    if not os.path.exists(face_dir):
        return None

    crops = sorted([f for f in os.listdir(face_dir) if f.endswith('.jpg')])
    if not crops:
        return None

    # If we have detection scores, pick the best one
    det_scores = metadata.get('det_scores', [])
    if det_scores and len(det_scores) == len(crops):
        best_idx = int(np.argmax(det_scores))
        return os.path.join(face_dir, crops[best_idx])

    # Otherwise pick the middle one (likely most representative)
    mid_idx = len(crops) // 2
    return os.path.join(face_dir, crops[mid_idx])


def migrate():
    """Main migration: gallery data → PostgreSQL students table."""
    print("=" * 60)
    print("  MIGRATION: Gallery → PostgreSQL")
    print("=" * 60)

    # Ensure tables exist
    create_tables()

    # Get list of enrolled person IDs from gallery
    npz_files = sorted([
        f.replace('_gallery.npz', '')
        for f in os.listdir(GALLERY_DIR)
        if f.endswith('_gallery.npz')
    ])

    print(f"\n  Found {len(npz_files)} gallery files")
    print(f"  Student metadata configured for {len(STUDENT_METADATA)} students")

    # Check for missing metadata
    missing = [pid for pid in npz_files if pid not in STUDENT_METADATA]
    if missing:
        print(f"\n  ⚠ Missing metadata for: {missing}")
        print(f"    Add them to STUDENT_METADATA in settings.py")
        print(f"    Proceeding with available data...\n")

    # Migrate each student
    success = 0
    errors = 0

    print(f"\n  {'Roll':<10} {'Name':<15} {'Faces':<8} {'Intra Sim':<12} {'Status'}")
    print(f"  {'─'*10} {'─'*15} {'─'*8} {'─'*12} {'─'*10}")

    for person_id in npz_files:
        try:
            # Load embedding
            centroid, all_emb = load_gallery_data(person_id)
            if centroid is None:
                print(f"  {person_id:<10} {'—':<15} {'—':<8} {'—':<12} ✗ No gallery data")
                errors += 1
                continue

            # Load metadata
            metadata = load_metadata(person_id)

            # Get student info
            student_info = STUDENT_METADATA.get(person_id, {})
            name = student_info.get('name', f'Student_{person_id}')
            department = student_info.get('department', 'Unknown')
            semester = student_info.get('semester', None)

            # Quality metrics
            num_samples = metadata.get('num_faces', all_emb.shape[0] if all_emb is not None else 0)
            intra_mean = metadata.get('intra_similarity_mean', None)
            intra_min = metadata.get('intra_similarity_min', None)
            intra_std = metadata.get('intra_similarity_std', None)

            # Reference photo
            photo_path = find_best_reference_photo(person_id, metadata)

            # Insert into database
            insert_student(
                roll_no=person_id,
                name=name,
                department=department,
                semester=semester,
                embedding=centroid,
                num_samples=num_samples,
                intra_sim_mean=intra_mean,
                intra_sim_min=intra_min,
                intra_sim_std=intra_std,
                photo_path=photo_path,
            )

            intra_str = f"{intra_mean:.4f}" if intra_mean else "—"
            print(f"  {person_id:<10} {name:<15} {num_samples:<8} {intra_str:<12} ✓ Migrated")
            success += 1

        except Exception as e:
            print(f"  {person_id:<10} {'—':<15} {'—':<8} {'—':<12} ✗ Error: {e}")
            errors += 1

    # ── Verification ──
    print(f"\n{'─' * 60}")
    print(f"  VERIFICATION")
    print(f"{'─' * 60}")

    total = get_enrolled_count()
    print(f"  Students in DB: {total}")

    # Load back and verify embeddings
    all_db = get_all_embeddings()
    print(f"  Embeddings loadable: {len(all_db)}")

    # Quick sanity: compare DB embeddings vs original gallery
    import pickle
    from config.settings import GALLERY_PKL

    if os.path.exists(GALLERY_PKL):
        with open(GALLERY_PKL, 'rb') as f:
            original = pickle.load(f)

        print(f"\n  Embedding integrity check (DB vs original .pkl):")
        all_match = True
        for pid in original:
            if pid in all_db:
                orig_centroid = original[pid]['centroid']
                db_centroid = all_db[pid]['embedding']
                sim = float(np.dot(orig_centroid, db_centroid))
                status = "✓" if sim > 0.9999 else "⚠ MISMATCH"
                if sim < 0.9999:
                    all_match = False
                print(f"    {pid}: similarity = {sim:.6f} {status}")

        if all_match:
            print(f"\n  ✓ All embeddings match perfectly!")
        else:
            print(f"\n  ⚠ Some embeddings don't match — check serialization")

    # ── Summary ──
    print(f"\n{'=' * 60}")
    print(f"  MIGRATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Success: {success}/{len(npz_files)}")
    print(f"  Errors:  {errors}/{len(npz_files)}")
    print(f"  Total in DB: {total}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    migrate()