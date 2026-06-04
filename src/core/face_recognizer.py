"""
Face Recognition Engine.

Loads enrolled embeddings from PostgreSQL, matches unknown faces
against the gallery using cosine similarity.

Usage:
    recognizer = FaceRecognizer()
    recognizer.load_gallery()
    result = recognizer.identify(embedding)
    # result = {'roll_no': '780322', 'name': 'Murari', 'confidence': 0.82}
    # or       {'roll_no': 'UNKNOWN', 'name': 'UNKNOWN', 'confidence': 0.0}
"""

import numpy as np
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.settings import RECOGNITION_THRESHOLD, RECOGNITION_TOP_K
from core.db_manager import get_all_embeddings, get_enrolled_count


class FaceRecognizer:
    """
    Cosine-similarity based face recognizer.

    Loads all enrolled centroids into a single numpy matrix for
    fast batch comparison (matrix multiply instead of loop).
    """

    def __init__(self, threshold=None):
        self.threshold = threshold or RECOGNITION_THRESHOLD
        self.gallery_matrix = None    # (N, 512) numpy array
        self.roll_numbers = []        # ordered list matching matrix rows
        self.names = {}               # roll_no → name mapping
        self.loaded = False
        self.load_time = None

    def load_gallery(self):
        """
        Load all enrolled embeddings from PostgreSQL into memory.
        Call this once at startup (or when gallery changes).
        """
        start = time.time()

        data = get_all_embeddings()

        if not data:
            print("[RECOGNIZER] ⚠ No enrolled students found in database!")
            self.loaded = False
            return

        self.roll_numbers = sorted(data.keys())
        self.names = {r: data[r]['name'] for r in self.roll_numbers}

        # Build (N, 512) matrix — each row is a centroid
        embeddings = [data[r]['embedding'] for r in self.roll_numbers]
        self.gallery_matrix = np.array(embeddings, dtype=np.float32)

        # Ensure all normalized (should already be, but safety)
        norms = np.linalg.norm(self.gallery_matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        self.gallery_matrix = self.gallery_matrix / norms

        self.loaded = True
        self.load_time = time.time() - start

        print(f"[RECOGNIZER] ✓ Gallery loaded: {len(self.roll_numbers)} students "
              f"in {self.load_time*1000:.1f}ms")
        print(f"[RECOGNIZER]   Threshold: {self.threshold}")

    def identify(self, embedding):
        """
        Identify a face by comparing its embedding against all enrolled students.

        Args:
            embedding: 512-D numpy array (L2-normalized)

        Returns:
            dict with keys:
                roll_no:    str (e.g., '780322' or 'UNKNOWN')
                name:       str (e.g., 'Murari' or 'UNKNOWN')
                confidence: float (cosine similarity, 0.0–1.0)
                top_k:      list of top-K matches for debugging
        """
        if not self.loaded or self.gallery_matrix is None:
            return self._unknown_result("gallery_not_loaded")

        # Normalize input
        embedding = embedding.astype(np.float32)
        norm = np.linalg.norm(embedding)
        if norm == 0:
            return self._unknown_result("zero_embedding")
        embedding = embedding / norm

        # Cosine similarity: dot product of normalized vectors
        # (N,512) @ (512,) → (N,) — one multiply, all students compared
        similarities = self.gallery_matrix @ embedding

        # Top-K matches
        top_k_indices = np.argsort(similarities)[::-1][:RECOGNITION_TOP_K]
        top_k = [
            {
                'roll_no': self.roll_numbers[i],
                'name': self.names[self.roll_numbers[i]],
                'confidence': round(float(similarities[i]), 4),
            }
            for i in top_k_indices
        ]

        # Best match
        best_idx = top_k_indices[0]
        best_sim = float(similarities[best_idx])

        if best_sim >= self.threshold:
            return {
                'roll_no': self.roll_numbers[best_idx],
                'name': self.names[self.roll_numbers[best_idx]],
                'confidence': round(best_sim, 4),
                'top_k': top_k,
            }
        else:
            return {
                'roll_no': 'UNKNOWN',
                'name': 'UNKNOWN',
                'confidence': round(best_sim, 4),
                'top_k': top_k,
            }

    def _unknown_result(self, reason="below_threshold"):
        return {
            'roll_no': 'UNKNOWN',
            'name': 'UNKNOWN',
            'confidence': 0.0,
            'top_k': [],
            'reason': reason,
        }

    def get_stats(self):
        """Return gallery statistics."""
        return {
            'loaded': self.loaded,
            'num_students': len(self.roll_numbers),
            'threshold': self.threshold,
            'load_time_ms': round(self.load_time * 1000, 1) if self.load_time else None,
        }


# ==============================================================
# STANDALONE TEST
# ==============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  FACE RECOGNIZER — Gallery Test")
    print("=" * 60)

    recognizer = FaceRecognizer()
    recognizer.load_gallery()

    if not recognizer.loaded:
        print("Cannot test — no gallery loaded")
        sys.exit(1)

    # Self-test: each enrolled student should match themselves
    print(f"\n  Self-recognition test (each student vs own centroid):")
    print(f"  {'Roll':<10} {'Name':<15} {'Self-Sim':<12} {'Status'}")
    print(f"  {'─'*10} {'─'*15} {'─'*12} {'─'*10}")

    all_pass = True
    for i, roll in enumerate(recognizer.roll_numbers):
        own_embedding = recognizer.gallery_matrix[i]
        result = recognizer.identify(own_embedding)
        matched = result['roll_no'] == roll
        status = "✓ MATCH" if matched else f"✗ Got {result['roll_no']}"
        if not matched:
            all_pass = False
        print(f"  {roll:<10} {recognizer.names[roll]:<15} "
              f"{result['confidence']:<12.4f} {status}")

    # Cross-test: make sure no student matches another
    print(f"\n  Cross-recognition check (no false matches):")
    false_matches = 0
    for i, roll_i in enumerate(recognizer.roll_numbers):
        for j, roll_j in enumerate(recognizer.roll_numbers):
            if i == j:
                continue
            emb_j = recognizer.gallery_matrix[j]
            result = recognizer.identify(emb_j)
            if result['roll_no'] != roll_j:
                print(f"  ⚠ {roll_j}'s embedding matched as {result['roll_no']} "
                      f"(conf={result['confidence']:.4f})")
                false_matches += 1

    if false_matches == 0:
        print(f"  ✓ No false matches — all {len(recognizer.roll_numbers)} students "
              f"correctly distinguished")

    print(f"\n{'=' * 60}")
    if all_pass and false_matches == 0:
        print(f"  ✓ ALL TESTS PASSED — Recognizer is ready!")
    else:
        print(f"  ⚠ Issues detected — review threshold ({recognizer.threshold})")
    print(f"{'=' * 60}")