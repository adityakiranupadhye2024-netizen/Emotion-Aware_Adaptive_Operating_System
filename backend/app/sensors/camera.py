import time
import math
import logging
import threading
import queue
from collections import deque
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

try:
    import cv2
except Exception:
    cv2 = None

try:
    from deepface import DeepFace
except Exception as e:
    DeepFace = None

logger = logging.getLogger("eaos.camera")

FACIAL_EMOTIONS = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']


class CameraSensor:
    """
    Real-time vision and pretrained facial emotion sensor using DeepFace.
    Operates an on-device local inference pipeline:
      Camera Capture Thread / Stream
            ↓
      OpenCV Face Detection & Region Selection (Single Primary User)
            ↓
      Controlled Async Inference Worker (2–4 FPS decoupled from video stream)
            ↓
      DeepFace Emotion Analysis (actions=['emotion'], enforce_detection=False, detector_backend='opencv')
            ↓
      Normalized Probabilities [0.0 – 1.0] (sum = 1.0)
            ↓
      Temporal Exponential Moving Average (EMA) Smoothing & Consistency
            ↓
      Derived Facial Evidence Signals for EAOS Multimodal Fusion
    """

    def __init__(
        self,
        inference_interval: float = 0.35,
        ema_alpha: float = 0.25,
        stale_timeout_sec: float = 5.0,
        detector_backend: str = "opencv"
    ):
        self._lock = threading.Lock()
        self.cap = None
        self.active = False
        self.face_detected = False
        self.eyes_detected = False
        self.smile_detected = False
        self.confidence = 0.0
        self.face_confidence = 0.0
        self.ambient_light = 0.5
        self.lighting_condition = "NORMAL"
        self.fatigue_score = 0.0
        self.last_frame_time = 0.0
        self.status_text = "CAMERA OFF"

        self.preview_requested = False
        self.latest_face_box: Optional[Tuple[int, int, int, int]] = None
        self.latest_annotated_jpeg: Optional[bytes] = None
        self.last_jpeg_time = 0.0
        self.frame_history = deque(maxlen=600)

        # DeepFace & Facial Emotion Configuration
        self.inference_interval = inference_interval
        self.ema_alpha = ema_alpha
        self.stale_timeout_sec = stale_timeout_sec
        self.detector_backend = detector_backend

        # State storage for DeepFace emotion inference
        self.raw_facial_emotions: Dict[str, float] = {e: 0.0 for e in FACIAL_EMOTIONS}
        self.raw_facial_emotions['neutral'] = 1.0
        self.smoothed_facial_emotions: Dict[str, float] = dict(self.raw_facial_emotions)
        self.dominant_facial_emotion: str = "neutral"
        self.emotion_confidence: float = 0.0
        self.emotion_available: bool = False
        self.emotion_stale: bool = True
        self.last_inference_time: float = 0.0
        self.last_inference_duration_ms: float = 0.0
        self.emotion_consistency: float = 0.5
        self.total_inference_count: int = 0

        # Derived facial evidence signals
        self.facial_frustration: float = 0.0
        self.facial_fatigue: float = 0.0
        self.facial_relaxation: float = 0.0

        # Rolling history of recent DeepFace predictions for temporal smoothing and consistency
        self._emotion_history = deque(maxlen=15)

        # Legacy display label for UI backwards compatibility
        self.current_emotion_label = "Neutral"
        self.current_emotion_confidence = 0.0

        # Cascades for rapid frame annotation and eye tracking
        self._clahe = None
        self._face_alt2 = None
        self._face_default = None
        self._profile_cascade = None
        self._eye_cascade = None
        self._smile_cascade = None

        if cv2 is not None:
            try:
                self._clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
                hdir = cv2.data.haarcascades
                self._face_alt2 = cv2.CascadeClassifier(hdir + 'haarcascade_frontalface_alt2.xml')
                self._face_default = cv2.CascadeClassifier(hdir + 'haarcascade_frontalface_default.xml')
                self._profile_cascade = cv2.CascadeClassifier(hdir + 'haarcascade_profileface.xml')
                self._eye_cascade = cv2.CascadeClassifier(hdir + 'haarcascade_eye_tree_eyeglasses.xml')
                self._smile_cascade = cv2.CascadeClassifier(hdir + 'haarcascade_smile.xml')
            except Exception as e:
                logger.warning(f"Error loading OpenCV Haar Cascades: {e}")

        # Controlled Background Inference Worker
        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self._worker_running = True
        self._last_submitted_time = 0.0
        self._worker_thread = threading.Thread(target=self._inference_worker_loop, daemon=True)
        self._worker_thread.start()

    def set_current_emotion(self, emotion: str, confidence: float = 0.85):
        """Allows external services to update nominal HUD label if facial inference is inactive."""
        with self._lock:
            if not self.emotion_available or self.emotion_stale:
                self.current_emotion_label = emotion or "Neutral"
                self.current_emotion_confidence = float(confidence) if confidence is not None else 0.0

    def set_preview_requested(self, enabled: bool):
        with self._lock:
            self.preview_requested = enabled
            if enabled:
                if not self.active or self.cap is None or not self.cap.isOpened():
                    self._open_hardware()

    def _open_hardware(self) -> bool:
        if cv2 is None:
            self.active = False
            self.status_text = "CAMERA UNAVAILABLE"
            return False
        if self.cap is not None and self.cap.isOpened():
            self.active = True
            self.status_text = "CAMERA SENSING"
            return True
        try:
            self.cap = cv2.VideoCapture(0)
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.active = True
                self.status_text = "CAMERA SENSING"
                logger.info("Camera hardware opened successfully for sensing/preview.")
                return True
            else:
                self.active = False
                self.status_text = "CAMERA UNAVAILABLE"
                return False
        except Exception as e:
            logger.warning(f"Failed to open camera hardware: {e}")
            self.active = False
            self.status_text = "CAMERA ERROR"
            return False

    def open_camera(self) -> bool:
        """Opens camera hardware during scheduled sensing window or preview."""
        with self._lock:
            return self._open_hardware()

    def close_camera(self, force: bool = False):
        """Closes and releases camera hardware in a thread-safe manner."""
        with self._lock:
            if self.preview_requested and not force:
                logger.info("Camera close requested, but preview is active. Keeping camera open for preview.")
                return
            self.active = False
            self.face_detected = False
            self.eyes_detected = False
            self.smile_detected = False
            self.confidence = 0.0
            self.face_confidence = 0.0
            self.emotion_available = False
            self.emotion_stale = True
            self.status_text = "CAMERA OFF"
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
            logger.info("Camera hardware closed and released cleanly.")

    def close(self):
        self.close_camera(force=True)

    def is_active(self) -> bool:
        with self._lock:
            return self.active and (self.cap is not None) and self.cap.isOpened()

    def _select_primary_face(self, faces: List[Any], frame_shape: Tuple[int, ...]) -> Optional[Tuple[int, int, int, int]]:
        """
        EAOS is single-user. When multiple faces appear in the frame, select the primary user face:
        Prioritizes largest face area with proximity to the center of the frame.
        Prevents background people from corrupting user state.
        """
        if not faces or len(faces) == 0:
            return None
        h, w = frame_shape[:2]
        cx, cy = w / 2.0, h / 2.0

        best_face = None
        best_score = -1.0

        for face in faces:
            fx, fy, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
            area = fw * fh
            face_center_x = fx + (fw / 2.0)
            face_center_y = fy + (fh / 2.0)
            dist_to_center = math.hypot(face_center_x - cx, face_center_y - cy)
            max_dist = math.hypot(cx, cy)
            center_factor = max(0.2, 1.0 - (0.5 * (dist_to_center / max_dist)))
            score = area * center_factor
            if score > best_score:
                best_score = score
                best_face = (fx, fy, fw, fh)

        return best_face

    def _submit_frame_for_inference(self, frame: np.ndarray, primary_face: Optional[Tuple[int, int, int, int]]):
        """
        Submits a frame to the decoupled inference worker if interval has elapsed.
        Keeps queue size bounded to 1 (drops stale frames to prevent memory leaks).
        """
        now = time.time()
        if now - self._last_submitted_time < self.inference_interval:
            return

        self._last_submitted_time = now
        try:
            # Drop older frame if still in queue
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                pass

            # Submit deep copy of the frame and primary face region
            item = {
                'frame': frame.copy(),
                'primary_face': primary_face,
                'timestamp': now
            }
            self._frame_queue.put_nowait(item)
        except Exception as e:
            logger.debug(f"Frame queue submission issue: {e}")

    def _inference_worker_loop(self):
        """
        Dedicated background worker thread for DeepFace local inference.
        Decoupled from camera capture/stream so live HUD preview NEVER freezes.
        """
        while self._worker_running:
            try:
                item = self._frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not self._worker_running:
                break

            try:
                self._run_emotion_inference(item['frame'], item['primary_face'], item['timestamp'])
            except Exception as e:
                logger.error(f"Unexpected error in DeepFace inference worker: {e}", exc_info=True)
            finally:
                del item

    def _normalize_emotions(self, raw_scores: Dict[str, Any]) -> Dict[str, float]:
        """
        Normalizes DeepFace emotion outputs to proper 0.0 - 1.0 probabilities that sum to exactly 1.0.
        DeepFace returns scores as percentages (0 - 100); handles both percentage and float inputs.
        """
        floats: Dict[str, float] = {}
        for k in FACIAL_EMOTIONS:
            val = raw_scores.get(k, 0.0)
            try:
                floats[k] = max(0.0, float(val))
            except Exception:
                floats[k] = 0.0

        total = sum(floats.values())
        if total > 0.0:
            norm = {k: round(v / total, 4) for k, v in floats.items()}
        else:
            norm = {k: round(1.0 / len(FACIAL_EMOTIONS), 4) for k in FACIAL_EMOTIONS}

        # Ensure exact sum == 1.0
        diff = round(1.0 - sum(norm.values()), 4)
        norm['neutral'] = max(0.0, round(norm['neutral'] + diff, 4))
        return norm

    def _compute_consistency(self) -> float:
        """
        Calculates temporal consistency of facial emotion predictions over the rolling history.
        Stable emotion over consecutive predictions gives high consistency (~0.8 - 1.0).
        Rapid erratic oscillations reduce consistency (< 0.5) to dampen facial signal weight.
        """
        if len(self._emotion_history) < 2:
            return 0.70

        dominants = [p['dominant'] for p in self._emotion_history]
        counts: Dict[str, int] = {}
        for d in dominants:
            counts[d] = counts.get(d, 0) + 1

        mode_dominant = max(counts, key=counts.get)
        mode_ratio = counts[mode_dominant] / float(len(dominants))

        # Variance of the dominant emotion probability
        dom_probs = [p['emotions'].get(mode_dominant, 0.0) for p in self._emotion_history]
        mean_prob = sum(dom_probs) / float(len(dom_probs))
        prob_var = sum((x - mean_prob) ** 2 for x in dom_probs) / float(len(dom_probs))

        consistency = mode_ratio * (1.0 - min(0.5, 2.0 * math.sqrt(prob_var)))
        return round(max(0.05, min(1.0, consistency)), 3)

    def _run_emotion_inference(
        self,
        frame: np.ndarray,
        primary_face: Optional[Tuple[int, int, int, int]],
        capture_time: float
    ):
        """
        Executes DeepFace pretrained emotion analysis on the selected face or full frame.
        Runs entirely on-device without network calls or persistent disk writes.
        """
        t0 = time.time()
        if DeepFace is None:
            with self._lock:
                self.emotion_available = False
                self.emotion_stale = True
                self.status_text = "DEEPFACE UNAVAILABLE"
            return

        h, w = frame.shape[:2]
        crop_target = frame
        use_backend = self.detector_backend

        if primary_face is not None:
            fx, fy, fw, fh = primary_face
            # Add subtle padding around detected face bounding box
            pad_x = int(fw * 0.15)
            pad_y = int(fh * 0.15)
            x1 = max(0, fx - pad_x)
            y1 = max(0, fy - pad_y)
            x2 = min(w, fx + fw + pad_x)
            y2 = min(h, fy + fh + pad_y)

            if (x2 - x1) >= 40 and (y2 - y1) >= 40:
                crop_target = frame[y1:y2, x1:x2]
                # If we already localized the primary face, skip secondary detection for speed
                use_backend = "skip"

        try:
            analysis = DeepFace.analyze(
                img_path=crop_target,
                actions=['emotion'],
                enforce_detection=False,
                detector_backend=use_backend
            )
        except Exception as e:
            logger.debug(f"DeepFace.analyze error: {e}")
            with self._lock:
                self.emotion_available = False
                self.emotion_stale = True
            return

        duration_ms = round((time.time() - t0) * 1000, 1)

        result = analysis[0] if isinstance(analysis, list) and len(analysis) > 0 else analysis
        if not isinstance(result, dict) or 'emotion' not in result:
            with self._lock:
                self.emotion_available = False
                self.emotion_stale = True
            return

        raw_scores = result.get('emotion', {})
        norm_emotions = self._normalize_emotions(raw_scores)
        dominant = max(norm_emotions, key=norm_emotions.get)
        confidence = norm_emotions[dominant]

        # Calculate face quality confidence
        if primary_face is not None:
            _, _, fw, fh = primary_face
            size_ratio = min(1.0, max(0.1, (fw * fh) / (120.0 * 120.0)))
            face_conf = round(min(0.98, 0.60 + 0.38 * size_ratio), 3)
            face_found = True
        else:
            region = result.get('region', {})
            fw = region.get('w', 0)
            fh = region.get('h', 0)
            if fw > 30 and fh > 30:
                face_conf = 0.75
                face_found = True
            else:
                face_conf = 0.30
                face_found = False

        # Apply Exponential Moving Average (EMA) smoothing
        with self._lock:
            self.total_inference_count += 1
            self.raw_facial_emotions = norm_emotions

            if len(self._emotion_history) == 0:
                smoothed = dict(norm_emotions)
            else:
                smoothed = {}
                for k in FACIAL_EMOTIONS:
                    prev_val = self.smoothed_facial_emotions.get(k, norm_emotions[k])
                    smoothed[k] = round(self.ema_alpha * norm_emotions[k] + (1.0 - self.ema_alpha) * prev_val, 4)

            # Re-normalize smoothed distribution
            tot_s = sum(smoothed.values())
            if tot_s > 0.0:
                smoothed = {k: round(v / tot_s, 4) for k, v in smoothed.items()}
            self.smoothed_facial_emotions = smoothed

            smoothed_dominant = max(smoothed, key=smoothed.get)
            self.dominant_facial_emotion = smoothed_dominant
            self.emotion_confidence = smoothed[smoothed_dominant]
            self.face_confidence = face_conf
            self.face_detected = face_found
            self.emotion_available = face_found
            self.emotion_stale = False
            self.last_inference_time = capture_time
            self.last_inference_duration_ms = duration_ms

            # Append to rolling prediction history
            self._emotion_history.append({
                'timestamp': capture_time,
                'dominant': dominant,
                'confidence': confidence,
                'emotions': norm_emotions
            })

            # Calculate emotion consistency
            self.emotion_consistency = self._compute_consistency()

            # Calculate transparent facial evidence signals
            instability = max(0.0, 1.0 - self.emotion_consistency)
            eye_vis_ratio = 1.0 if self.eyes_detected else 0.0

            # Facial Frustration Evidence: 0.55 angry + 0.20 disgust + 0.10 surprise + 0.15 instability
            self.facial_frustration = round(
                0.55 * smoothed.get('angry', 0.0)
                + 0.20 * smoothed.get('disgust', 0.0)
                + 0.10 * smoothed.get('surprise', 0.0)
                + 0.15 * instability,
                3
            )

            # Facial Relaxation Evidence: 0.60 happy + 0.30 neutral + 0.10 stable_expression
            self.facial_relaxation = round(
                0.60 * smoothed.get('happy', 0.0)
                + 0.30 * smoothed.get('neutral', 0.0)
                + 0.10 * self.emotion_consistency,
                3
            )

            # Facial Fatigue Proxy: 0.45 sad + 0.20 low_eye_vis + 0.20 neutral + 0.15 quality_penalty
            quality_penalty = max(0.0, 1.0 - self.face_confidence)
            self.facial_fatigue = round(
                0.45 * smoothed.get('sad', 0.0)
                + 0.20 * (1.0 - eye_vis_ratio)
                + 0.20 * smoothed.get('neutral', 0.0)
                + 0.15 * quality_penalty,
                3
            )

            # Update HUD display attributes
            self.current_emotion_label = smoothed_dominant.title()
            self.current_emotion_confidence = self.emotion_confidence

        logger.info(
            f"DeepFace Emotion Inference: dominant={smoothed_dominant} ({int(self.emotion_confidence * 100)}%), "
            f"face_detected={face_found}, conf={face_conf:.2f}, consistency={self.emotion_consistency:.2f}, "
            f"duration={duration_ms}ms"
        )

    def _create_standby_frame(self, message: str = "CAMERA IN STANDBY") -> bytes:
        """Generates a HUD standby frame when hardware camera is off."""
        w, h = 640, 360
        img = np.full((h, w, 3), (15, 23, 42), dtype=np.uint8)
        for y in range(0, h, 30):
            cv2.line(img, (0, y), (w, y), (26, 38, 64), 1)
        for x in range(0, w, 30):
            cv2.line(img, (x, 0), (x, h), (26, 38, 64), 1)
        cv2.rectangle(img, (20, 20), (w - 20, h - 20), (56, 189, 248), 1)

        accent = (56, 189, 248)
        c_len = 16
        cv2.line(img, (20, 20), (20 + c_len, 20), accent, 3)
        cv2.line(img, (20, 20), (20, 20 + c_len), accent, 3)
        cv2.line(img, (w - 20, 20), (w - 20 - c_len, 20), accent, 3)
        cv2.line(img, (w - 20, 20), (w - 20, 20 + c_len), accent, 3)
        cv2.line(img, (20, h - 20), (20 + c_len, h - 20), accent, 3)
        cv2.line(img, (20, h - 20), (20, h - 20 - c_len), accent, 3)
        cv2.line(img, (w - 20, h - 20), (w - 20 - c_len, h - 20), accent, 3)
        cv2.line(img, (w - 20, h - 20), (w - 20, h - 20 - c_len), accent, 3)

        cv2.putText(img, "EAOS VISION & DEEPFACE EMOTION SYSTEM", (w // 2 - 200, h // 2 - 35),
                    cv2.FONT_HERSHEY_DUPLEX, 0.60, (248, 189, 56), 1, cv2.LINE_AA)
        cv2.putText(img, f"[ {message} ]", (w // 2 - 130, h // 2 + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (148, 163, 184), 1, cv2.LINE_AA)
        cv2.putText(img, "Active during 1-min sensing window or click 'Live Preview'",
                    (w // 2 - 200, h // 2 + 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (100, 116, 139), 1, cv2.LINE_AA)
        cv2.putText(img, "ON-DEVICE DEEPFACE INFERENCE · ZERO CLOUD UPLOAD", (w // 2 - 180, h - 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (52, 211, 153), 1, cv2.LINE_AA)

        ret, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        return buf.tobytes() if ret else b''

    def _annotate_frame(
        self,
        frame: np.ndarray,
        primary_face: Optional[Tuple[int, int, int, int]],
        eyes_found: bool,
        smiles_found: bool
    ) -> bytes:
        """
        Draws live HUD overlays: face bounding box with cyber corners, eye trackers,
        and real-time DeepFace emotion badge showing dominant facial emotion.
        """
        h, w = frame.shape[:2]

        # Emotion colors mapping (BGR)
        palette = {
            'neutral': (248, 189, 56),    # Electric Cyan
            'happy': (52, 211, 153),      # Emerald Green
            'sad': (36, 191, 251),        # Amber
            'angry': (113, 113, 248),     # Coral Red
            'disgust': (180, 80, 240),    # Magenta
            'fear': (71, 224, 253),       # Yellow
            'surprise': (255, 140, 50),   # Light Blue
        }
        color = palette.get(self.dominant_facial_emotion.lower(), (248, 189, 56))

        # 1. Top HUD Bar
        cv2.rectangle(frame, (0, 0), (w, 36), (15, 23, 42), -1)
        cv2.line(frame, (0, 36), (w, 36), (56, 189, 248), 1)
        cv2.circle(frame, (20, 18), 6, (52, 211, 153), -1)
        cv2.putText(frame, "EAOS VISION HUD", (34, 23),
                    cv2.FONT_HERSHEY_DUPLEX, 0.50, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, "ON-DEVICE DEEPFACE INFERENCE", (w - 250, 23),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (148, 163, 184), 1, cv2.LINE_AA)

        # 2. Draw Face Detection
        if primary_face is not None:
            fx, fy, fw, fh = primary_face
            self.latest_face_box = (fx, fy, fw, fh)

            c_len = max(14, int(fw * 0.18))
            thick = 2
            cv2.line(frame, (fx, fy), (fx + c_len, fy), color, thick)
            cv2.line(frame, (fx, fy), (fx, fy + c_len), color, thick)
            cv2.line(frame, (fx + fw, fy), (fx + fw - c_len, fy), color, thick)
            cv2.line(frame, (fx + fw, fy), (fx + fw, fy + c_len), color, thick)
            cv2.line(frame, (fx, fy + fh), (fx + c_len, fy + fh), color, thick)
            cv2.line(frame, (fx, fy + fh), (fx, fy + fh - c_len), color, thick)
            cv2.line(frame, (fx + fw, fy + fh), (fx + fw - c_len, fy + fh), color, thick)
            cv2.line(frame, (fx + fw, fy + fh), (fx + fw, fy + fh - c_len), color, thick)

            cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (int(color[0]), int(color[1]), int(color[2])), 1)

            if eyes_found:
                eye_y = fy + int(fh * 0.35)
                eye_x1 = fx + int(fw * 0.32)
                eye_x2 = fx + int(fw * 0.68)
                cv2.circle(frame, (eye_x1, eye_y), 4, (255, 255, 255), -1)
                cv2.circle(frame, (eye_x1, eye_y), 10, color, 1)
                cv2.circle(frame, (eye_x2, eye_y), 4, (255, 255, 255), -1)
                cv2.circle(frame, (eye_x2, eye_y), 10, color, 1)

            # Real Dynamic DeepFace Emotion Badge right above face
            if self.emotion_available and not self.emotion_stale:
                pct = int(self.emotion_confidence * 100)
                tag_text = f"FACIAL: {self.dominant_facial_emotion.upper()} ({pct}%)"
            else:
                tag_text = "FACE DETECTED"

            badge_y = fy - 12 if fy > 45 else fy + fh + 32
            badge_w = max(220, fw)

            cv2.rectangle(frame, (fx, badge_y - 24), (fx + badge_w, badge_y + 4), (15, 23, 42), -1)
            cv2.rectangle(frame, (fx, badge_y - 24), (fx + badge_w, badge_y + 4), color, 1)
            cv2.putText(frame, tag_text, (fx + 8, badge_y - 7),
                        cv2.FONT_HERSHEY_DUPLEX, 0.46, (255, 255, 255), 1, cv2.LINE_AA)

            if smiles_found:
                cv2.putText(frame, "SMILE DETECTED", (fx + 8, badge_y + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.40, (52, 211, 153), 1, cv2.LINE_AA)
        else:
            self.latest_face_box = None
            cx, cy = w // 2, h // 2
            cv2.line(frame, (cx - 20, cy), (cx + 20, cy), (100, 116, 139), 1)
            cv2.line(frame, (cx, cy - 20), (cx, cy + 20), (100, 116, 139), 1)
            cv2.putText(frame, "SEARCHING FOR FACE...", (cx - 85, cy + 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (148, 163, 184), 1, cv2.LINE_AA)

        # 4. Bottom Telemetry Bar
        cv2.rectangle(frame, (0, h - 28), (w, h), (15, 23, 42), -1)
        status_line = (
            f"FACE: {'LOCKED' if primary_face else 'STANDBY'}   "
            f"EYES: {'ENGAGED' if eyes_found else 'TRACKING'}   "
            f"LIGHT: {self.lighting_condition} ({self.ambient_light})   "
            f"CONSISTENCY: {int(self.emotion_consistency * 100)}%"
        )
        cv2.putText(frame, status_line, (14, h - 9),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (148, 163, 184), 1, cv2.LINE_AA)

        ret, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        return buf.tobytes() if ret else b''

    def get_stream_frame(self) -> bytes:
        """Returns the real-time annotated camera frame or standby frame for HTTP streaming."""
        with self._lock:
            if not self.active or self.cap is None or not self.cap.isOpened():
                return self._create_standby_frame(self.status_text)

            try:
                ok, frame = self.cap.read()
            except Exception:
                ok, frame = False, None

            if not ok or frame is None:
                return self._create_standby_frame("FRAME READ PAUSED")

            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                raw_ambient = float(np.mean(gray) / 255.0)
                self.ambient_light = round(0.75 * self.ambient_light + 0.25 * raw_ambient, 3)

                enhanced_gray = self._clahe.apply(gray) if self._clahe is not None else gray
                faces = []
                if self._face_alt2 and not self._face_alt2.empty():
                    faces = self._face_alt2.detectMultiScale(enhanced_gray, scaleFactor=1.1, minNeighbors=3, minSize=(40, 40))
                if len(faces) == 0 and self._face_default and not self._face_default.empty():
                    faces = self._face_default.detectMultiScale(enhanced_gray, scaleFactor=1.15, minNeighbors=3, minSize=(45, 45))

                primary_face = self._select_primary_face(faces, frame.shape)
                self.face_detected = (primary_face is not None)
                eyes_found = False
                smiles_found = False

                if primary_face is not None:
                    fx, fy, fw, fh = primary_face
                    face_roi = enhanced_gray[fy:fy + fh, fx:fx + fw]
                    if self._eye_cascade and not self._eye_cascade.empty():
                        upper_face = face_roi[0:int(fh * 0.65), :]
                        eyes = self._eye_cascade.detectMultiScale(upper_face, scaleFactor=1.1, minNeighbors=3, minSize=(15, 15))
                        eyes_found = len(eyes) > 0
                    if self._smile_cascade and not self._smile_cascade.empty():
                        lower_face = face_roi[int(fh * 0.5):, :]
                        smiles = self._smile_cascade.detectMultiScale(lower_face, scaleFactor=1.2, minNeighbors=5, minSize=(20, 20))
                        smiles_found = len(smiles) > 0

                # Check stale emotion timeout
                now_t = time.time()
                if primary_face is None and (now_t - self.last_inference_time > self.stale_timeout_sec):
                    self.emotion_available = False
                    self.emotion_stale = True

                # Submit frame to decoupled DeepFace worker
                self._submit_frame_for_inference(frame, primary_face)

                jpeg_bytes = self._annotate_frame(frame, primary_face, eyes_found, smiles_found)
                self.latest_annotated_jpeg = jpeg_bytes
                self.last_jpeg_time = now_t
                return jpeg_bytes
            except Exception as e:
                logger.warning(f"Error in get_stream_frame: {e}")
                return self._create_standby_frame("ANALYSIS ERROR")

    def snapshot(self) -> Dict[str, Any]:
        """Processes current frame strictly in-memory and returns full telemetry state."""
        with self._lock:
            now_t = time.time()
            if not self.active or self.cap is None or not self.cap.isOpened():
                self.frame_history.append({'timestamp': now_t, 'active': False, 'valid': False})
                return {
                    'active': False,
                    'status': self.status_text,
                    'face_detected': False,
                    'face_confidence': 0.0,
                    'eyes_detected': False,
                    'smile_detected': False,
                    'confidence': 0.0,
                    'ambient_light': round(self.ambient_light, 3),
                    'lighting_condition': self.lighting_condition,
                    'fatigue_score': round(self.fatigue_score, 2),
                    'emotion_available': False,
                    'emotion_stale': True,
                    'dominant_facial_emotion': self.dominant_facial_emotion,
                    'raw_facial_emotions': dict(self.raw_facial_emotions),
                    'smoothed_facial_emotions': dict(self.smoothed_facial_emotions),
                    'emotion_confidence': round(self.emotion_confidence, 3),
                    'emotion_consistency': round(self.emotion_consistency, 3),
                    'facial_frustration': round(self.facial_frustration, 3),
                    'facial_fatigue': round(self.facial_fatigue, 3),
                    'facial_relaxation': round(self.facial_relaxation, 3)
                }

            try:
                ok, frame = self.cap.read()
            except Exception:
                ok, frame = False, None

            if not ok or frame is None:
                self.frame_history.append({'timestamp': now_t, 'active': True, 'valid': False})
                return {
                    'active': True,
                    'status': self.status_text,
                    'face_detected': False,
                    'face_confidence': 0.0,
                    'eyes_detected': False,
                    'smile_detected': False,
                    'confidence': 0.0,
                    'ambient_light': round(self.ambient_light, 3),
                    'lighting_condition': self.lighting_condition,
                    'fatigue_score': round(self.fatigue_score, 2),
                    'emotion_available': False,
                    'emotion_stale': True,
                    'dominant_facial_emotion': self.dominant_facial_emotion,
                    'raw_facial_emotions': dict(self.raw_facial_emotions),
                    'smoothed_facial_emotions': dict(self.smoothed_facial_emotions),
                    'emotion_confidence': round(self.emotion_confidence, 3),
                    'emotion_consistency': round(self.emotion_consistency, 3),
                    'facial_frustration': round(self.facial_frustration, 3),
                    'facial_fatigue': round(self.facial_fatigue, 3),
                    'facial_relaxation': round(self.facial_relaxation, 3)
                }

            self.last_frame_time = now_t
            primary_face = None
            eyes_found = False
            smiles_found = False

            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                raw_ambient = float(np.mean(gray) / 255.0)
                self.ambient_light = round(0.75 * self.ambient_light + 0.25 * raw_ambient, 3)

                if self.ambient_light < 0.25:
                    self.lighting_condition = "DIM"
                elif self.ambient_light > 0.65:
                    self.lighting_condition = "BRIGHT"
                else:
                    self.lighting_condition = "NORMAL"

                enhanced_gray = self._clahe.apply(gray) if self._clahe is not None else gray

                faces = []
                if self._face_alt2 and not self._face_alt2.empty():
                    faces = self._face_alt2.detectMultiScale(enhanced_gray, scaleFactor=1.1, minNeighbors=3, minSize=(40, 40))
                if len(faces) == 0 and self._face_default and not self._face_default.empty():
                    faces = self._face_default.detectMultiScale(enhanced_gray, scaleFactor=1.15, minNeighbors=3, minSize=(45, 45))
                if len(faces) == 0 and self._profile_cascade and not self._profile_cascade.empty():
                    faces = self._profile_cascade.detectMultiScale(enhanced_gray, scaleFactor=1.15, minNeighbors=3, minSize=(45, 45))

                primary_face = self._select_primary_face(faces, frame.shape)
                self.face_detected = (primary_face is not None)

                if primary_face is not None:
                    fx, fy, fw, fh = primary_face
                    face_roi = enhanced_gray[fy:fy + fh, fx:fx + fw]

                    if self._eye_cascade and not self._eye_cascade.empty():
                        upper_face = face_roi[0:int(fh * 0.65), :]
                        eyes = self._eye_cascade.detectMultiScale(upper_face, scaleFactor=1.1, minNeighbors=3, minSize=(15, 15))
                        eyes_found = len(eyes) > 0

                    if self._smile_cascade and not self._smile_cascade.empty():
                        lower_face = face_roi[int(fh * 0.5):, :]
                        smiles = self._smile_cascade.detectMultiScale(lower_face, scaleFactor=1.2, minNeighbors=5, minSize=(20, 20))
                        smiles_found = len(smiles) > 0

                    self.eyes_detected = eyes_found
                    self.smile_detected = smiles_found

                    if not eyes_found:
                        self.fatigue_score = min(1.0, self.fatigue_score + 0.15)
                    else:
                        self.fatigue_score = max(0.0, self.fatigue_score - 0.10)

                    size_ratio = min(1.0, max(0.1, (fw * fh) / (120.0 * 120.0)))
                    self.confidence = min(0.98, 0.65 + 0.15 * (1 if eyes_found else 0) + 0.18 * size_ratio)
                    self.face_confidence = round(self.confidence, 3)
                else:
                    self.eyes_detected = False
                    self.smile_detected = False
                    self.confidence = 0.0
                    self.face_confidence = 0.0
                    self.fatigue_score = max(0.0, self.fatigue_score - 0.05)

                # Check stale emotion timeout
                if primary_face is None and (now_t - self.last_inference_time > self.stale_timeout_sec):
                    self.emotion_available = False
                    self.emotion_stale = True

                # Submit frame to decoupled DeepFace worker
                self._submit_frame_for_inference(frame, primary_face)

                self.frame_history.append({
                    'timestamp': now_t,
                    'active': True,
                    'valid': True,
                    'face_detected': self.face_detected,
                    'eyes_detected': self.eyes_detected,
                    'smile_detected': self.smile_detected,
                    'ambient_light': self.ambient_light,
                    'confidence': self.confidence,
                    'dominant_facial_emotion': self.dominant_facial_emotion,
                    'smoothed_facial_emotions': dict(self.smoothed_facial_emotions),
                    'emotion_confidence': self.emotion_confidence,
                    'emotion_consistency': self.emotion_consistency,
                    'emotion_available': self.emotion_available and not self.emotion_stale
                })

                self.latest_annotated_jpeg = self._annotate_frame(frame, primary_face, eyes_found, smiles_found)
                self.last_jpeg_time = now_t

            except Exception as e:
                logger.warning(f"Error during facial frame analysis: {e}")
            finally:
                del frame

            inference_age = round(now_t - self.last_inference_time, 2) if self.last_inference_time > 0 else None

            return {
                'active': True,
                'status': self.status_text,
                'face_detected': self.face_detected,
                'face_confidence': round(self.face_confidence, 2),
                'eyes_detected': self.eyes_detected,
                'smile_detected': self.smile_detected,
                'confidence': round(self.confidence, 2),
                'ambient_light': round(self.ambient_light, 3),
                'lighting_condition': self.lighting_condition,
                'fatigue_score': round(self.fatigue_score, 2),
                'emotion_available': self.emotion_available and not self.emotion_stale,
                'emotion_stale': self.emotion_stale or (not self.face_detected),
                'emotion_inference_age': inference_age,
                'dominant_facial_emotion': self.dominant_facial_emotion,
                'raw_facial_emotions': dict(self.raw_facial_emotions),
                'smoothed_facial_emotions': dict(self.smoothed_facial_emotions),
                'emotion_confidence': round(self.emotion_confidence, 3),
                'emotion_consistency': round(self.emotion_consistency, 3),
                'facial_frustration': round(self.facial_frustration, 3),
                'facial_fatigue': round(self.facial_fatigue, 3),
                'facial_relaxation': round(self.facial_relaxation, 3)
            }

    def get_window_metrics(self, window_sec: float = 60.0) -> Dict[str, Any]:
        """
        Calculates authoritative camera visual signals, DeepFace facial distributions,
        and temporal consistency across the 60-second observation window.
        """
        with self._lock:
            now = time.time()
            cutoff = now - window_sec
            recent = [f for f in self.frame_history if f['timestamp'] >= cutoff]

            total_samples = len(recent)
            if total_samples == 0:
                return {
                    'camera_active_ratio': 0.0,
                    'valid_frame_ratio': 0.0,
                    'face_presence_ratio': 0.0,
                    'eye_visibility_ratio': 0.0,
                    'smile_presence_ratio': 0.0,
                    'average_visual_light_proxy': 0.50,
                    'low_light_ratio': 0.0,
                    'no_face_ratio': 1.0,
                    'face_detection_confidence': 0.0,
                    'fatigue_proxy': 0.0,
                    'camera_data_confidence': 0.0,
                    'emotion_observation_count': 0,
                    'emotion_consistency': 0.5,
                    'facial_emotion_distribution': dict(self.smoothed_facial_emotions),
                    'dominant_facial_emotion': self.dominant_facial_emotion,
                    'facial_frustration': 0.0,
                    'facial_fatigue': 0.0,
                    'facial_relaxation': 0.0,
                    'conditions': {
                        'valid_camera_observation': False,
                        'face_present': False,
                        'strong_face_presence': False,
                        'face_mostly_absent': True,
                        'eyes_engaged': False,
                        'low_eye_visibility': False,
                        'persistent_low_eye_visibility': False,
                        'smile_observed': False,
                        'dim_proxy': False,
                        'bright_proxy': False
                    }
                }

            valid_frames = [f for f in recent if f.get('valid')]
            valid_frame_ratio = len(valid_frames) / float(total_samples)

            distinct_active_seconds = len(set(int(f['timestamp']) for f in recent if f.get('active')))
            camera_active_ratio = min(1.0, distinct_active_seconds / max(1.0, window_sec))

            face_frames = [f for f in valid_frames if f.get('face_detected')]
            face_presence_ratio = len(face_frames) / float(len(valid_frames)) if valid_frames else 0.0
            no_face_ratio = max(0.0, 1.0 - face_presence_ratio)

            eye_frames = [f for f in face_frames if f.get('eyes_detected')]
            eye_visibility_ratio = len(eye_frames) / float(len(face_frames)) if face_frames else 0.0

            smile_frames = [f for f in face_frames if f.get('smile_detected')]
            smile_presence_ratio = len(smile_frames) / float(len(face_frames)) if face_frames else 0.0

            ambients = [f.get('ambient_light', 0.5) for f in valid_frames]
            avg_light = (sum(ambients) / len(ambients)) if ambients else 0.50
            low_light_count = sum(1 for a in ambients if a < 0.25)
            low_light_ratio = low_light_count / float(len(ambients)) if ambients else 0.0

            confidences = [f.get('confidence', 0.0) for f in face_frames]
            face_conf = (sum(confidences) / len(confidences)) if confidences else 0.0

            persistent_low_eyes = (eye_visibility_ratio < 0.40 and face_presence_ratio >= 0.60)
            low_eye_visibility = (eye_visibility_ratio < 0.45 and face_presence_ratio >= 0.60)
            fatigue_proxy = round(max(0.0, min(1.0, (1.0 - eye_visibility_ratio) * 0.7 + (0.3 if persistent_low_eyes else 0.0))), 3) if face_presence_ratio >= 0.50 else 0.0

            cam_conf = round(valid_frame_ratio * (0.3 + 0.7 * face_presence_ratio), 3) if valid_frame_ratio >= 0.5 else 0.0

            # Aggregate DeepFace facial emotion probabilities across valid face frames
            face_frames_with_emotions = [f for f in face_frames if f.get('smoothed_facial_emotions')]
            emotion_obs_count = len(face_frames_with_emotions)

            if emotion_obs_count > 0:
                agg_emotions: Dict[str, float] = {}
                for k in FACIAL_EMOTIONS:
                    agg_emotions[k] = sum(f['smoothed_facial_emotions'].get(k, 0.0) for f in face_frames_with_emotions) / float(emotion_obs_count)
                tot_e = sum(agg_emotions.values())
                if tot_e > 0.0:
                    agg_emotions = {k: round(v / tot_e, 4) for k, v in agg_emotions.items()}
                window_dominant = max(agg_emotions, key=agg_emotions.get)
            else:
                agg_emotions = dict(self.smoothed_facial_emotions)
                window_dominant = self.dominant_facial_emotion

            window_consistency = self.emotion_consistency

            # Window-level evidence signals
            instability = max(0.0, 1.0 - window_consistency)
            facial_frustration = round(
                0.55 * agg_emotions.get('angry', 0.0)
                + 0.20 * agg_emotions.get('disgust', 0.0)
                + 0.10 * agg_emotions.get('surprise', 0.0)
                + 0.15 * instability,
                3
            )
            facial_relaxation = round(
                0.60 * agg_emotions.get('happy', 0.0)
                + 0.30 * agg_emotions.get('neutral', 0.0)
                + 0.10 * window_consistency,
                3
            )
            quality_penalty = max(0.0, 1.0 - face_conf)
            facial_fatigue = round(
                0.45 * agg_emotions.get('sad', 0.0)
                + 0.20 * (1.0 - eye_visibility_ratio)
                + 0.20 * agg_emotions.get('neutral', 0.0)
                + 0.15 * quality_penalty,
                3
            )

            conditions = {
                'valid_camera_observation': valid_frame_ratio >= 0.70,
                'face_present': face_presence_ratio >= 0.60,
                'strong_face_presence': face_presence_ratio >= 0.80,
                'face_mostly_absent': face_presence_ratio < 0.30,
                'eyes_engaged': (eye_visibility_ratio >= 0.65 and face_presence_ratio >= 0.50),
                'low_eye_visibility': low_eye_visibility,
                'persistent_low_eye_visibility': persistent_low_eyes,
                'smile_observed': smile_presence_ratio >= 0.40,
                'dim_proxy': avg_light < 0.25,
                'bright_proxy': avg_light > 0.65
            }

            return {
                'camera_active_ratio': round(camera_active_ratio, 3),
                'valid_frame_ratio': round(valid_frame_ratio, 3),
                'face_presence_ratio': round(face_presence_ratio, 3),
                'eye_visibility_ratio': round(eye_visibility_ratio, 3),
                'smile_presence_ratio': round(smile_presence_ratio, 3),
                'average_visual_light_proxy': round(avg_light, 3),
                'low_light_ratio': round(low_light_ratio, 3),
                'no_face_ratio': round(no_face_ratio, 3),
                'face_detection_confidence': round(face_conf, 3),
                'fatigue_proxy': fatigue_proxy,
                'camera_data_confidence': cam_conf,
                'emotion_observation_count': emotion_obs_count,
                'emotion_consistency': window_consistency,
                'facial_emotion_distribution': agg_emotions,
                'dominant_facial_emotion': window_dominant,
                'facial_frustration': facial_frustration,
                'facial_fatigue': facial_fatigue,
                'facial_relaxation': facial_relaxation,
                'conditions': conditions
            }
