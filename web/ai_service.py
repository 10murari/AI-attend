"""
AI Service — Bridges InsightFace pipeline to Django.

Loads the model ONCE and provides detect/embed/recognize functions.
Used by both enrollment and attendance views.
"""

import os
import sys
import numpy as np
import threading
import logging

logger = logging.getLogger(__name__)

# Add the src directory to path so we can import existing modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


class AIService:
    """
    Thread-safe singleton for InsightFace model.
    Loads once, reused across all requests.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.app = None
        self._model_lock = threading.Lock()
        logger.info("AIService created (not loaded yet — lazy init)")

    def _ensure_loaded(self):
        """Lazy-load the InsightFace model on first use."""
        if self.app is not None:
            return

        with self._model_lock:
            if self.app is not None:
                return

            logger.info("Loading InsightFace model...")
            try:
                import insightface
                from insightface.app import FaceAnalysis

                self.app = FaceAnalysis(
                    name='buffalo_l',
                    providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
                )
                self.app.prepare(ctx_id=0, det_size=(640, 640), det_thresh=0.5)
                logger.info("InsightFace model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load InsightFace: {e}")
                raise

    def detect_faces(self, frame):
        """
        Detect faces in a BGR frame.

        Args:
            frame: numpy array (H, W, 3) BGR

        Returns:
            list of insightface Face objects
        """
        self._ensure_loaded()
        return self.app.get(frame)

    def get_embedding(self, face):
        """
        Get 512-D normalized embedding from a detected face.

        Args:
            face: insightface Face object

        Returns:
            numpy array (512,) float32, L2-normalized
        """
        emb = face.embedding.astype(np.float32)
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb

    def compute_centroid(self, embeddings):
        """
        Compute centroid from multiple embeddings.

        Args:
            embeddings: list of numpy arrays (512,)

        Returns:
            dict with centroid, quality metrics
        """
        if not embeddings:
            return None

        embs = np.array(embeddings, dtype=np.float32)

        # Compute centroid
        centroid = embs.mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm

        # Compute quality metrics (intra-person similarity)
        similarities = []
        for emb in embs:
            sim = float(np.dot(emb, centroid))
            similarities.append(sim)

        return {
            'centroid': centroid,
            'num_samples': len(embeddings),
            'intra_sim_mean': float(np.mean(similarities)),
            'intra_sim_min': float(np.min(similarities)),
            'intra_sim_std': float(np.std(similarities)),
        }

    def recognize(self, embedding, gallery, threshold=0.45):
        """
        Match an embedding against the gallery.

        Args:
            embedding: numpy array (512,) float32, normalized
            gallery: dict {user_id: {'embedding': np.array, 'roll_no': str, 'name': str}}
            threshold: minimum cosine similarity for match

        Returns:
            None if no match, otherwise:
            {'user_id': int, 'roll_no': str, 'name': str, 'similarity': float}
        """
        if not gallery:
            return None

        best_match = None
        best_sim = -1

        for user_id, data in gallery.items():
            sim = float(np.dot(embedding, data['embedding']))
            if sim > best_sim:
                best_sim = sim
                best_match = {
                    'user_id': user_id,
                    'roll_no': data['roll_no'],
                    'name': data['name'],
                    'similarity': round(sim, 4),
                }

        if best_match and best_match['similarity'] >= threshold:
            return best_match

        return None

    def load_gallery(self):
        """
        Load all active face embeddings from DB as gallery.

        Returns:
            dict {user_id: {'embedding': np.array, 'roll_no': str, 'name': str}}
        """
        from enrollment.models import FaceEmbedding
        gallery = {}

        for fe in FaceEmbedding.objects.filter(is_active=True).select_related('user'):
            emb = fe.get_embedding()
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm

            gallery[fe.user_id] = {
                'embedding': emb,
                'roll_no': fe.user.roll_no,
                'name': fe.user.full_name,
            }

        return gallery


# Global singleton
ai_service = AIService()