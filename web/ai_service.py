"""
AI Service — Bridges InsightFace pipeline to Django.

Loads the model ONCE and provides detect/embed/recognize functions.
Used by both enrollment and attendance views.

Anti-spoofing uses MiniVision MiniFASNet models located at:
    web/antispoof/resources/anti_spoof_models/
"""

import os
import sys
import numpy as np
import threading

import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# web/ directory (where this file lives)
WEB_DIR = os.path.dirname(os.path.abspath(__file__))

# Antispoof package lives inside web/
ANTISPOOF_DIR = os.path.join(WEB_DIR, 'antispoof')
SPOOF_MODEL_DIR = os.path.join(ANTISPOOF_DIR, 'resources', 'anti_spoof_models')

# Liveness threshold — overridable from settings.py
LIVENESS_THRESHOLD = getattr(settings, 'LIVENESS_THRESHOLD', 0.85)


class AIService:
    """
    Thread-safe singleton for InsightFace + anti-spoofing models.
    Loads once on first use, reused across all requests.
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
        self.app = None                 # InsightFace FaceAnalysis
        self._spoof_predictor = None    # AntiSpoofPredict  (None = not installed)
        self._spoof_cropper = None      # CropImage
        self._model_lock = threading.Lock()
        self._gallery_cache = None
        logger.info("AIService created (not loaded yet — lazy init)")

    # ------------------------------------------------------------------
    # Internal loaders
    # ------------------------------------------------------------------

    def _ensure_loaded(self):
        """Lazy-load both models on first use."""
        if self.app is not None:
            return

        with self._model_lock:
            if self.app is not None:
                return
            self._load_insightface()
            self._load_antispoofing()

    def _load_insightface(self):
        """Load InsightFace buffalo_l (unchanged from original)."""
        logger.info("Loading InsightFace model...")
        try:
            from insightface.app import FaceAnalysis
            self.app = FaceAnalysis(
                name=getattr(settings, 'INSIGHTFACE_MODEL', 'buffalo_l'),
                providers=['CUDAExecutionProvider', 'CPUExecutionProvider'],
            )
            self.app.prepare(
                ctx_id=0,
                det_size=getattr(settings, 'DET_SIZE', (640, 640)),
                det_thresh=getattr(settings, 'DET_THRESH', 0.5),
            )
            logger.info("InsightFace model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load InsightFace: {e}")
            raise

    def _load_antispoofing(self):
        if not os.path.isdir(SPOOF_MODEL_DIR):
            logger.warning(
                f"Anti-spoofing model dir not found: {SPOOF_MODEL_DIR}. "
                "Running WITHOUT liveness detection."
            )
            return
        try:
            # Add antispoof dir to sys.path so relative imports inside
            # anti_spoof_predict.py resolve correctly as absolute imports
            if WEB_DIR not in sys.path:
                sys.path.insert(0, WEB_DIR)

            from antispoof.anti_spoof_predict import AntiSpoofPredict
            from antispoof.generate_patches import CropImage
            self._spoof_predictor = AntiSpoofPredict(device_id=0)
            self._spoof_cropper = CropImage()
            logger.info(f"Anti-spoofing models loaded from {SPOOF_MODEL_DIR}")
        except ImportError as e:
            logger.warning(f"Anti-spoofing import failed ({e}).")
        except Exception as e:
            logger.warning(f"Anti-spoofing setup error: {e}. Continuing without liveness check.")

    # ------------------------------------------------------------------
    # Public API (existing methods — unchanged)
    # ------------------------------------------------------------------

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

        centroid = embs.mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm

        similarities = [float(np.dot(emb, centroid)) for emb in embs]

        return {
            'centroid': centroid,
            'num_samples': len(embeddings),
            'intra_sim_mean': float(np.mean(similarities)),
            'intra_sim_min': float(np.min(similarities)),
            'intra_sim_std': float(np.std(similarities)),
        }

    def recognize(self, embedding, gallery, threshold=None):
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

        if threshold is None:
            threshold = getattr(settings, 'RECOGNITION_THRESHOLD', 0.45)

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
        Load all active face embeddings from DB as gallery (cached).

        Returns:
            dict {user_id: {'embedding': np.array, 'roll_no': str, 'name': str}}
        """
        if self._gallery_cache is not None:
            return self._gallery_cache
            
        return self.refresh_gallery()

    def refresh_gallery(self):
        """
        Force a refresh of the gallery cache from the database.
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

        self._gallery_cache = gallery
        return gallery

    # ------------------------------------------------------------------
    # NEW: Anti-spoofing
    # ------------------------------------------------------------------

    def check_liveness(self, frame, face) -> tuple:
        """
        Determine whether a detected face is a live person or a spoof
        (printed photo, phone screen, mask).

        Uses MiniVision MiniFASNetV1 + MiniFASNetV2 in ensemble:
        both models vote; their softmax outputs are summed and the
        real-face probability is normalised to [0, 1].

        Args:
            frame : numpy array (H, W, 3) BGR — the full webcam frame
            face  : insightface Face object returned by detect_faces()

        Returns:
            (is_real: bool, liveness_score: float)

            is_real        — True if the face passes the liveness threshold
            liveness_score — real-face probability in [0, 1]; always present
                             so the caller can log or surface it in the UI

        Fail-open contract:
            If the anti-spoofing model was not installed, returns (True, 1.0)
            so the existing recognition pipeline is unaffected.
        """
        self._ensure_loaded()

        if not getattr(settings, 'ANTI_SPOOF_ENABLED', True):
            return True, 1.0

        # Model not installed — fail open
        if self._spoof_predictor is None:
            return True, 1.0

        try:
            from antispoof.utility import parse_model_name
            anti_spoof_input_size = int(getattr(settings, 'ANTI_SPOOF_INPUT_SIZE', 128))
            min_face_size = int(
                getattr(
                    settings,
                    'ANTI_SPOOF_MIN_FACE_SIZE',
                    max(64, int(anti_spoof_input_size * 0.75)),
                )
            )

            # InsightFace bbox is [x1, y1, x2, y2] (floats).
            # MiniFASNet CropImage expects [x, y, w, h] (ints).
            x1, y1, x2, y2 = face.bbox.astype(int)
            face_w = x2 - x1
            face_h = y2 - y1

            if face_w <= 0 or face_h <= 0:
                logger.debug("Liveness rejected invalid face bbox: %s", [x1, y1, x2, y2])
                return False, 0.0

            if min(face_w, face_h) < min_face_size:
                logger.debug(
                    "Liveness skipped small face crop: bbox=%s size=%sx%s min=%s",
                    [x1, y1, x2, y2],
                    face_w,
                    face_h,
                    min_face_size,
                )
                return True, 0.0

            bbox_xywh = [x1, y1, face_w, face_h]

            # Accumulate softmax outputs across both bundled models.
            # Shape: (1, 3) — classes are [spoof_type_A, real, spoof_type_B]
            # (index 1 = real face in the MiniVision label convention)
            import numpy as np
            prediction = np.zeros((1, 3), dtype=np.float32)

            for model_filename in os.listdir(SPOOF_MODEL_DIR):
                if not model_filename.endswith('.pth'):
                    continue

                h_input, w_input, _model_type, scale = parse_model_name(model_filename)

                crop_params = {
                    "org_img": frame,
                    "bbox": bbox_xywh,
                    "scale": scale,
                    "out_w": w_input,
                    "out_h": h_input,
                    "crop": scale is not None,   # org_ models skip cropping
                }
                cropped = self._spoof_cropper.crop(**crop_params)

                model_path = os.path.join(SPOOF_MODEL_DIR, model_filename)
                prediction += self._spoof_predictor.predict(cropped, model_path)

            # label 1 = real face; sum over both models then normalise
            real_score = float(prediction[0, 1])
            total_score = float(prediction.sum())
            liveness_score = real_score / total_score if total_score > 0 else 0.0

            threshold = float(getattr(settings, 'LIVENESS_THRESHOLD', LIVENESS_THRESHOLD))
            is_real = liveness_score >= threshold
            logger.debug(
                f"Liveness: {'REAL' if is_real else 'SPOOF'} "
                f"(score={liveness_score:.3f}, threshold={threshold})"
            )
            return is_real, round(liveness_score, 4)

        except Exception as e:
            # Never crash the attendance flow due to antispoofing error
            logger.warning(f"Liveness check error (failing open): {e}")
            return True, 1.0


# Global singleton
ai_service = AIService()
