"""
Multi-frame liveness confirmation.

A single frame that passes the anti-spoof check is not enough to mark
attendance: on the video test set, 40% of replay/print attacks passed
at least one frame at the production threshold, because attack scores
flicker across frames. What separates attacks almost perfectly is the
*average* score over many frames (best attack mean 0.75 vs real means
mostly >= 0.85).

So each detected face is tracked across frames by bounding-box overlap,
and every model score — passing or spoofy — is accumulated into the
track's rolling window. Attendance is marked only when, on a frame that
itself passes the per-frame threshold:

    - the face's track has >= LIVENESS_CONFIRM_MIN_FRAMES observations
    - the window mean is >= LIVENESS_CONFIRM_MEAN_SCORE

Tracking must be by location, not identity: spoof-verdict frames never
reach recognition (no identity), yet their low scores are exactly the
evidence that keeps an attack's mean down.

Replaying the evaluation videos through this policy (window 20,
min 3 frames, mean 0.80): 0/55 attacks marked vs 49/55 real videos
auto-confirmed — the remainder are borderline-quality captures that the
teacher can mark manually.

State is in-process (fine for the threaded single-worker deployment);
a restart merely restarts pending confirmations, never grants a pass.
"""

import threading
import time
from collections import deque

from django.conf import settings

_IOU_MATCH = 0.3


def _iou(box_a, box_b):
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0.0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


class _Track:
    __slots__ = ('bbox', 'scores', 'last_ts')

    def __init__(self, bbox, window, now):
        self.bbox = list(bbox)
        self.scores = deque(maxlen=window)
        self.last_ts = now


class LivenessConfirmationTracker:
    """Thread-safe per-session face tracker with rolling score windows."""

    def __init__(self):
        self._tracks = {}    # session_id -> list[_Track]
        self._lock = threading.Lock()

    @staticmethod
    def min_frames():
        return max(1, int(getattr(settings, 'LIVENESS_CONFIRM_MIN_FRAMES', 3)))

    @staticmethod
    def mean_threshold():
        return float(getattr(settings, 'LIVENESS_CONFIRM_MEAN_SCORE', 0.80))

    @staticmethod
    def _window():
        return max(1, int(getattr(settings, 'LIVENESS_CONFIRM_WINDOW', 20)))

    @staticmethod
    def _max_gap():
        return float(getattr(settings, 'LIVENESS_TRACK_MAX_GAP_SECONDS', 6.0))

    def observe(self, session_id, bbox, score):
        """
        Feed one scored face observation (any verdict) into its track.

        Returns (confirmed, n_observations, window_mean). `confirmed`
        only says the track's history is trustworthy — the caller still
        gates on the current frame's own verdict and recognition match.
        """
        now = time.monotonic()
        max_gap = self._max_gap()

        with self._lock:
            tracks = self._tracks.get(session_id, [])
            # A face absent longer than max_gap is a new presentation:
            # drop the track so nobody inherits another's history.
            tracks = [t for t in tracks if now - t.last_ts <= max_gap]

            best, best_iou = None, _IOU_MATCH
            for track in tracks:
                overlap = _iou(track.bbox, bbox)
                if overlap >= best_iou:
                    best, best_iou = track, overlap

            if best is None:
                best = _Track(bbox, self._window(), now)
                tracks.append(best)

            best.bbox = list(bbox)
            best.last_ts = now
            best.scores.append(float(score))
            self._tracks[session_id] = tracks

            n = len(best.scores)
            mean = sum(best.scores) / n
            confirmed = n >= self.min_frames() and mean >= self.mean_threshold()
            return confirmed, n, round(mean, 4)


liveness_gate = LivenessConfirmationTracker()
