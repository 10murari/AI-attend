import cv2
import numpy as np
import time
import threading
from src.core.anti_spoofing.anti_spoof_predict import AntiSpoofPredict, Detection


# ================= CONFIGURATION ==================
MODEL_PATHS = [
    'src/core/anti_spoofing/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth',
    # Add more compatible models here for stronger ensemble
]

SKIP_FRAMES          = 3      # run inference every Nth frame
N                    = 20     # vote buffer length (increased for stability)
K                    = 14     # votes needed for LIVE (K/N = ~70% — stricter)
low_threshold        = 0.70   # SPOOFED → LIVE (lowered: harder to get LIVE vote)
high_threshold       = 0.96   # LIVE → SPOOFED (hysteresis; raised for stability)
min_face_size        = 70
max_face_size_ratio  = 0.6
FACE_PAD_RATIO       = 0.2
TARGET_FACE_SIZE     = (80, 80)
ID_TRACK_TIMEOUT     = 2.0
ID_MATCH_DIST        = 80

# Quality gate
MIN_LAPLACIAN_VAR    = 30
MIN_BRIGHTNESS       = 40
MAX_BRIGHTNESS       = 220

# FFT screen artifact detection
SCREEN_SCORE_THRESHOLD = 3.5   # above = likely screen; calibrated from data
FFT_PENALTY            = 0.15   # multiply live_prob by this when screen detected (harsh penalty)

# LBP micro-texture
LBP_ENTROPY_THRESHOLD  = 5.7    # below = low texture = suspicious
LBP_PENALTY            = 0.3    # multiply live_prob by this when low texture detected (harsher)

# Optical flow motion analysis
MOTION_WINDOW          = 15     # frames to track
MOTION_VAR_THRESHOLD   = 0.0002 # below = suspiciously uniform motion
MOTION_PENALTY         = 0.25   # multiply live_prob by this (much harsher penalty)

# Debug: print per-frame scores to terminal
DEBUG_SCORES           = True
# ===================================================


# ──────────────────────────────────────────────────
#  Signal 1: Face alignment + quality gate
# ──────────────────────────────────────────────────
def align_face(frame, bbox, pad_ratio=FACE_PAD_RATIO, target_size=TARGET_FACE_SIZE):
    """Pad around the bbox and resize to model input size."""
    x, y, w, h = bbox
    pad = int(max(w, h) * pad_ratio)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(frame.shape[1], x + w + pad)
    y2 = min(frame.shape[0], y + h + pad)
    face = frame[y1:y2, x1:x2]
    if face.size == 0:
        return None
    return cv2.resize(face, target_size)


def is_good_quality(face_roi):
    """Return True only if the crop is sharp and well-lit."""
    if face_roi is None or face_roi.size == 0:
        return False
    gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
    if cv2.Laplacian(gray, cv2.CV_64F).var() < MIN_LAPLACIAN_VAR:
        return False
    mean = np.mean(gray)
    return MIN_BRIGHTNESS <= mean <= MAX_BRIGHTNESS


# ──────────────────────────────────────────────────
#  Signal 2: FFT — screen pixel-grid artifacts
# ──────────────────────────────────────────────────
def detect_screen_artifacts(face_roi):
    """
    Screens have periodic high-frequency patterns in the Fourier domain.
    Real faces do not.
    Returns a screen score — high (>6) = likely screen replay attack.
    """
    gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (128, 128)).astype(np.float32)

    dft       = np.fft.fft2(gray)
    dft_shift = np.fft.fftshift(dft)
    magnitude = np.log(np.abs(dft_shift) + 1)
    magnitude = (magnitude - magnitude.min()) / (magnitude.max() - magnitude.min() + 1e-6)

    h, w   = magnitude.shape
    cx, cy = w // 2, h // 2

    # Mask out DC component
    dc_mask = np.ones_like(magnitude)
    cv2.circle(dc_mask, (cx, cy), 15, 0, -1)
    high_freq = magnitude * dc_mask

    # Mid-high frequency ring — screens show spikes here
    ring_mask = np.zeros_like(magnitude)
    cv2.circle(ring_mask, (cx, cy), 50, 1, -1)
    cv2.circle(ring_mask, (cx, cy), 15, 0, -1)
    ring_energy = high_freq * ring_mask

    valid = ring_energy[ring_energy > 0]
    if valid.size == 0:
        return 0.0

    screen_score = ring_energy.max() / (valid.mean() + 1e-6)
    return float(screen_score)


def detect_screen_artifacts_highres(frame, bbox, fft_size=128, crop_size=192, pad_ratio=0.35):
    """
    Extract a higher-resolution crop from the original frame (not the 80x80 aligned image)
    and compute a more sensitive FFT-based screen score. This helps detect mobile
    replays where the low-res aligned crop loses grid artifacts.

    Returns a z-score-like spike metric: (max - mean) / (std + eps)
    """
    x, y, w, h = bbox
    pad = int(max(w, h) * pad_ratio)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(frame.shape[1], x + w + pad)
    y2 = min(frame.shape[0], y + h + pad)

    crop = frame[y1:y2, x1:x2]
    if crop is None or crop.size == 0:
        return 0.0

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (crop_size, crop_size)).astype(np.float32)

    dft = np.fft.fft2(gray)
    dft_shift = np.fft.fftshift(dft)
    magnitude = np.log(np.abs(dft_shift) + 1)
    magnitude = (magnitude - magnitude.min()) / (magnitude.max() - magnitude.min() + 1e-6)

    h, w = magnitude.shape
    cx, cy = w // 2, h // 2

    # remove DC
    dc_mask = np.ones_like(magnitude)
    cv2.circle(dc_mask, (cx, cy), 8, 0, -1)
    high_freq = magnitude * dc_mask

    # ring region (relative to size)
    outer_r = int(min(cx, cy) * 0.6)
    inner_r = int(min(cx, cy) * 0.12)
    ring_mask = np.zeros_like(magnitude)
    cv2.circle(ring_mask, (cx, cy), outer_r, 1, -1)
    cv2.circle(ring_mask, (cx, cy), inner_r, 0, -1)
    ring_energy = high_freq * ring_mask

    valid = ring_energy[ring_energy > 0]
    if valid.size == 0:
        return 0.0

    # use a spike metric that's sensitive to isolated peaks
    peak = float(ring_energy.max())
    mean = float(valid.mean())
    std  = float(valid.std())
    score = (peak - mean) / (std + 1e-6)

    # small scale correction to keep scores comparable with older code
    return float(score)

# ──────────────────────────────────────────────────
#  Signal 3: LBP — micro-texture entropy
# ──────────────────────────────────────────────────

def lbp_texture_score(face_roi):
    """
    Real skin has rich micro-texture -> high LBP entropy (~6.5-7.5).
    Screens/prints are more uniform -> lower entropy (~4.5-6.0).
    Uses a fast vectorised numpy LBP.
    """
    gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (64, 64)).astype(np.int16)

    # 8 clockwise neighbors starting top-left
    offsets = [(-1, -1), (-1, 0), (-1, 1),
               ( 0,  1),
               ( 1,  1), ( 1,  0), ( 1, -1),
               ( 0, -1)]

    center  = gray[1:-1, 1:-1]
    lbp_arr = np.zeros_like(center, dtype=np.uint8)

    for bit, (dr, dc) in enumerate(offsets):
        r0 = 1 + dr
        c0 = 1 + dc
        nb = gray[r0:r0 + center.shape[0], c0:c0 + center.shape[1]]
        lbp_arr |= ((nb >= center).astype(np.uint8) << bit)

    hist, _ = np.histogram(lbp_arr.ravel(), bins=256, range=(0, 256))
    hist     = hist / (hist.sum() + 1e-6)
    entropy  = -np.sum(hist * np.log2(hist + 1e-10))
    return float(entropy)


# ──────────────────────────────────────────────────
#  Signal 4: Optical flow — motion consistency
# ──────────────────────────────────────────────────
class MotionAnalyzer:
    """
    Real faces: irregular micro-movements (breathing, eye saccades, head drift).
    Video replay: motion is smooth, periodic, or near-zero between loops.
    Tracks optical flow variance over a rolling window.
    """
    def __init__(self, window=MOTION_WINDOW):
        self.prev_gray    = None
        self.flow_history = []
        self.window       = window

    def update(self, face_roi):
        gray = cv2.cvtColor(cv2.resize(face_roi, (64, 64)), cv2.COLOR_BGR2GRAY)

        if self.prev_gray is None or self.prev_gray.shape != gray.shape:
            self.prev_gray = gray
            return None

        flow = cv2.calcOpticalFlowFarneback(
            self.prev_gray, gray, None,
            pyr_scale=0.5, levels=2, winsize=8,
            iterations=2, poly_n=5, poly_sigma=1.1, flags=0,
        )
        self.prev_gray = gray

        mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
        self.flow_history.append(float(np.mean(mag)))
        if len(self.flow_history) > self.window:
            self.flow_history.pop(0)

        return float(np.var(self.flow_history)) if len(self.flow_history) >= self.window else None

    def is_suspicious(self):
        if len(self.flow_history) < self.window:
            return False
        return float(np.var(self.flow_history)) < MOTION_VAR_THRESHOLD

    def reset(self):
        self.prev_gray    = None
        self.flow_history = []


# ──────────────────────────────────────────────────
#  Face tracker
# ──────────────────────────────────────────────────
class FaceTracker:
    def __init__(self):
        self.face_data = {}
        self.next_id   = 0

    def get_face_id(self, bbox, frame_shape, now):
        x, y, w, h = bbox
        cx      = x + w / 2
        cy      = y + h / 2
        w_ratio = w / frame_shape[1]
        if w_ratio > max_face_size_ratio:
            return None

        best_match = None
        min_dist   = 99999
        for fid, data in self.face_data.items():
            px, py, pw, ph = data["bbox"]
            dist = ((cx - (px + pw / 2)) ** 2 + (cy - (py + ph / 2)) ** 2) ** 0.5
            if dist < ID_MATCH_DIST and dist < min_dist:
                min_dist   = dist
                best_match = fid
        return best_match

    def add_face(self, bbox, frame_shape, now):
        fid = self.next_id
        self.next_id += 1
        self.face_data[fid] = {
            "bbox":         bbox,
            "last_time":    now,
            "recent_probs": [],
            "live_buffer":  [],
        }
        return fid

    def update_face(self, fid, bbox, now):
        self.face_data[fid]["bbox"]      = bbox
        self.face_data[fid]["last_time"] = now

    def remove_old_faces(self, now):
        old = [fid for fid, d in self.face_data.items()
               if now - d["last_time"] > ID_TRACK_TIMEOUT]
        for fid in old:
            del self.face_data[fid]

    def get_active_face_id(self, frame_shape):
        return max(
            self.face_data,
            key=lambda fid: self.face_data[fid]["bbox"][2] * self.face_data[fid]["bbox"][3],
            default=None,
        )

    def buffer_live_prob(self, fid, live_prob):
        data = self.face_data[fid]

        data["recent_probs"].append(live_prob)
        if len(data["recent_probs"]) > N:
            data["recent_probs"].pop(0)

        smoothed      = float(np.mean(data["recent_probs"]))
        current_state = self.get_state(fid)                   # read BEFORE updating buffer
        threshold     = high_threshold if current_state == "LIVE" else low_threshold

        data["live_buffer"].append(smoothed > threshold)
        if len(data["live_buffer"]) > N:
            data["live_buffer"].pop(0)

    def get_state(self, fid):
        if fid not in self.face_data:
            return "SPOOFED"
        return "LIVE" if sum(self.face_data[fid]["live_buffer"]) >= K else "SPOOFED"


# ──────────────────────────────────────────────────
#  Background inference worker
# ──────────────────────────────────────────────────
class InferenceWorker:
    def __init__(self, predictor, tracker):
        self.predictor       = predictor
        self.tracker         = tracker
        self.motion_analyzer = MotionAnalyzer()
        self._lock           = threading.Lock()
        self._result         = {"state": "SPOOFED", "bbox": None}

    def submit(self, frame_copy, bbox, face_id):
        t = threading.Thread(
            target=self._run,
            args=(frame_copy, bbox, face_id),
            daemon=True,
        )
        t.start()

    def _run(self, frame, bbox, face_id):
        aligned = align_face(frame, bbox)
        if aligned is None or not is_good_quality(aligned):
            return

        # ── 1. Neural net ensemble ──────────────────────────
        live_probs = []
        for model_path in MODEL_PATHS:
            try:
                result = self.predictor.predict(aligned, model_path)
                live_probs.append(float(result[0][1]))
            except Exception as e:
                print(f"[Model error] {e}")

        if not live_probs:
            return

        live_prob = float(np.mean(live_probs))

        # ── 2. FFT screen artifact penalty (use high-res crop) ──
        screen_score = detect_screen_artifacts_highres(frame, bbox)
        fft_flag     = screen_score > SCREEN_SCORE_THRESHOLD
        if fft_flag:
            live_prob *= FFT_PENALTY

        # ── 3. LBP micro-texture penalty ────────────────────
        entropy  = lbp_texture_score(aligned)
        lbp_flag = entropy < LBP_ENTROPY_THRESHOLD
        if lbp_flag:
            live_prob *= LBP_PENALTY

        # ── 4. Optical flow motion penalty ──────────────────
        motion_var  = self.motion_analyzer.update(aligned)
        motion_flag = self.motion_analyzer.is_suspicious()
        if motion_flag:
            live_prob *= MOTION_PENALTY

        # ── 5. Compound: 2+ signals agree = force spoof ─────
        flags = sum([fft_flag, lbp_flag, motion_flag])
        if flags >= 2:
            live_prob = min(live_prob, 0.05)

        if DEBUG_SCORES:
            mv = motion_var if motion_var is not None else 0.0
            print(
                f"  live={live_prob:.3f}  "
                f"fft={screen_score:.2f}{'⚠' if fft_flag else ' '}  "
                f"lbp={entropy:.2f}{'⚠' if lbp_flag else ' '}  "
                f"mvar={mv:.5f}{'⚠' if motion_flag else ' '}  "
                f"flags={flags}"
            )

        if face_id in self.tracker.face_data:
            self.tracker.buffer_live_prob(face_id, live_prob)
            state = self.tracker.get_state(face_id)
            with self._lock:
                self._result = {
                    "state": state,
                    "bbox":  self.tracker.face_data[face_id]["bbox"],
                }

    def get_latest(self):
        with self._lock:
            return dict(self._result)


# ──────────────────────────────────────────────────
#  Main loop
# ──────────────────────────────────────────────────
def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Cannot open webcam")
        return

    detector  = Detection()
    predictor = AntiSpoofPredict(device_id=0)
    tracker   = FaceTracker()
    worker    = InferenceWorker(predictor, tracker)

    print("=" * 56)
    print("  Anti-Spoofing — Video Replay Hardened")
    print("=" * 56)
    print(f"  Models         : {len(MODEL_PATHS)}")
    print(f"  Buffer         : N={N}, K={K} ({K}/{N} = {K/N*100:.0f}% must be LIVE)")
    print(f"  Thresholds     : lo={low_threshold}  hi={high_threshold}")
    print(f"  FFT threshold  : score > {SCREEN_SCORE_THRESHOLD} → penalty x{FFT_PENALTY}")
    print(f"  LBP threshold  : entropy < {LBP_ENTROPY_THRESHOLD} → penalty x{LBP_PENALTY}")
    print(f"  Motion thresh  : var < {MOTION_VAR_THRESHOLD} → penalty x{MOTION_PENALTY}")
    print(f"  2+ flags fired → live_prob clamped to 0.05")
    print("  Keys: q=quit  d=toggle debug HUD")
    print("=" * 56 + "\n")

    frame_count    = 0
    show_debug_hud = True

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to read from webcam")
            break

        frame = cv2.flip(frame, 1)
        frame_count += 1
        now = time.time()

        tracker.remove_old_faces(now)

        # ── Every Nth frame: detect + submit async inference ──
        if frame_count % SKIP_FRAMES == 0:
            try:
                bbox = detector.get_bbox(frame)
                if len(bbox) > 0:
                    x, y, w, h = bbox
                    x = max(0, x)
                    y = max(0, y)
                    w = min(w, frame.shape[1] - x)
                    h = min(h, frame.shape[0] - y)

                    if w >= min_face_size and h >= min_face_size:
                        face_id = tracker.get_face_id((x, y, w, h), frame.shape, now)
                        if face_id is None:
                            face_id = tracker.add_face((x, y, w, h), frame.shape, now)
                            worker.motion_analyzer.reset()  # reset flow for new face
                        tracker.update_face(face_id, (x, y, w, h), now)
                        worker.submit(frame.copy(), (x, y, w, h), face_id)

            except Exception as e:
                print(f"[Detection error] {e}")

        # ── Draw latest async result ───────────────────────
        result = worker.get_latest()
        state  = result["state"]
        bbox   = result["bbox"]

        if bbox is not None:
            x, y, w, h = bbox
            color = (0, 220, 0) if state == "LIVE" else (0, 0, 220)

            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 3)
            cv2.putText(frame, state, (x, y - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 2)

        # ── Debug HUD ─────────────────────────────────────
        if show_debug_hud:
            hud = [
                f"N={N} K={K} skip={SKIP_FRAMES}",
                f"FFT>{SCREEN_SCORE_THRESHOLD}  LBP<{LBP_ENTROPY_THRESHOLD}  MVAR<{MOTION_VAR_THRESHOLD}",
            ]
            for i, line in enumerate(hud):
                cv2.putText(frame, line, (10, 22 + i * 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.48, (180, 180, 180), 1)

        cv2.imshow("Anti-Spoofing — Video Replay Hardened", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('d'):
            show_debug_hud = not show_debug_hud

    cap.release()
    cv2.destroyAllWindows()
    print("Webcam closed.")


if __name__ == "__main__":
    main()