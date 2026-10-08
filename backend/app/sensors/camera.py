import time
import logging
import threading
from collections import deque
from typing import Dict, Any, List, Optional
import numpy as np

try:
    import cv2
except Exception:
    cv2 = None

logger = logging.getLogger("eaos.camera")


class CameraSensor:
    def __init__(self):
        self._lock = threading.Lock()
        self.cap = None
        self.active = False
        self.face_detected = False
        self.eyes_detected = False
        self.smile_detected = False
        self.confidence = 0.0
        self.ambient_light = 0.5
        self.lighting_condition = "NORMAL"
        self.fatigue_score = 0.0
        self.last_frame_time = 0
        self.status_text = "CAMERA OFF"

        self.preview_requested = False
        self.current_emotion_label = "Focused"
        self.current_emotion_confidence = 0.85
        self.latest_face_box = None
        self.latest_annotated_jpeg = None
        self.last_jpeg_time = 0.0
        self.frame_history = deque(maxlen=600)

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

    def set_current_emotion(self, emotion: str, confidence: float = 0.85):
        self.current_emotion_label = emotion or "Focused"
        self.current_emotion_confidence = float(confidence) if confidence is not None else 0.85

    def set_preview_requested(self, enabled: bool):
        with self._lock:
            self.preview_requested = enabled
            if enabled:
                if not self.active or self.cap is None or not self.cap.isOpened():
                    self._open_hardware()
            else:
                pass

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
                logger.info("Camera activated for sensing/preview.")
                return True
            else:
                self.active = False
                self.status_text = "CAMERA UNAVAILABLE"
                return False
        except Exception as e:
            logger.warning(f"Failed to open camera: {e}")
            self.active = False
            self.status_text = "CAMERA ERROR"
            return False

    def open_camera(self) -> bool:
        """Explicitly opens camera for the scheduled sensing window or preview."""
        with self._lock:
            return self._open_hardware()

    def close_camera(self, force: bool = False):
        """Immediately closes and releases the camera hardware in a thread-safe manner."""
        with self._lock:
            if self.preview_requested and not force:
                logger.info("Camera close requested, but preview is active. Keeping camera open for preview.")
                return
            self.active = False
            self.face_detected = False
            self.eyes_detected = False
            self.smile_detected = False
            self.confidence = 0.0
            self.status_text = "CAMERA OFF"
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
            logger.info("Camera closed and released.")

    def close(self):
        self.close_camera(force=True)

    def is_active(self) -> bool:
        with self._lock:
            return self.active and (self.cap is not None) and self.cap.isOpened()

    def _create_standby_frame(self, message: str = "CAMERA IN STANDBY") -> bytes:
        """Generates a high-tech HUD standby frame when hardware camera is off."""
        w, h = 640, 360
        img = np.full((h, w, 3), (15, 23, 42), dtype=np.uint8)  # #0f172a slate
        # Subtle grid lines
        for y in range(0, h, 30):
            cv2.line(img, (0, y), (w, y), (26, 38, 64), 1)
        for x in range(0, w, 30):
            cv2.line(img, (x, 0), (x, h), (26, 38, 64), 1)
        # Inner cyber border
        cv2.rectangle(img, (20, 20), (w - 20, h - 20), (56, 189, 248), 1)
        # Corner accents
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

        # Center HUD Text
        cv2.putText(img, "EAOS VISION & EMOTION SYSTEM", (w // 2 - 170, h // 2 - 35),
                    cv2.FONT_HERSHEY_DUPLEX, 0.65, (248, 189, 56), 1, cv2.LINE_AA)
        cv2.putText(img, f"[ {message} ]", (w // 2 - 130, h // 2 + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (148, 163, 184), 1, cv2.LINE_AA)
        cv2.putText(img, "Active during 1-min sensing window or click 'Live Preview'",
                    (w // 2 - 200, h // 2 + 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (100, 116, 139), 1, cv2.LINE_AA)
        cv2.putText(img, "ON-DEVICE PRIVACY · ZERO CLOUD UPLOAD", (w // 2 - 150, h - 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (52, 211, 153), 1, cv2.LINE_AA)

        ret, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        return buf.tobytes() if ret else b''

    def _annotate_frame(self, frame, faces, eyes_found, smiles_found) -> bytes:
        """Draws HUD overlays: face bounding box with cyber corners, eye trackers, and live emotion badge."""
        h, w = frame.shape[:2]

        # Emotion colors mapping (BGR)
        palette = {
            'Focused': (248, 189, 56),     # Electric Cyan
            'Flow State': (247, 85, 168),  # Magenta/Purple
            'Relaxed': (52, 211, 153),     # Emerald Green
            'Fatigued': (36, 191, 251),    # Amber
            'Frustrated': (113, 113, 248), # Coral Red
            'Confused': (71, 224, 253),    # Yellow
        }
        color = palette.get(self.current_emotion_label, (248, 189, 56))

        # 1. Top HUD Bar
        cv2.rectangle(frame, (0, 0), (w, 36), (15, 23, 42), -1)
        cv2.line(frame, (0, 36), (w, 36), (56, 189, 248), 1)
        cv2.circle(frame, (20, 18), 6, (52, 211, 153), -1)  # Live indicator green dot
        cv2.putText(frame, "EAOS VISION HUD", (34, 23),
                    cv2.FONT_HERSHEY_DUPLEX, 0.50, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, "ON-DEVICE LOCAL INFERENCE", (w - 230, 23),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (148, 163, 184), 1, cv2.LINE_AA)

        # 2. Draw Face Detection
        if len(faces) > 0:
            fx, fy, fw, fh = faces[0]
            self.latest_face_box = (fx, fy, fw, fh)

            # Sleek Cyber Corner Brackets around face
            c_len = max(14, int(fw * 0.18))
            thick = 2
            # Top-left corner
            cv2.line(frame, (fx, fy), (fx + c_len, fy), color, thick)
            cv2.line(frame, (fx, fy), (fx, fy + c_len), color, thick)
            # Top-right corner
            cv2.line(frame, (fx + fw, fy), (fx + fw - c_len, fy), color, thick)
            cv2.line(frame, (fx + fw, fy), (fx + fw, fy + c_len), color, thick)
            # Bottom-left corner
            cv2.line(frame, (fx, fy + fh), (fx + c_len, fy + fh), color, thick)
            cv2.line(frame, (fx, fy + fh), (fx, fy + fh - c_len), color, thick)
            # Bottom-right corner
            cv2.line(frame, (fx + fw, fy + fh), (fx + fw - c_len, fy + fh), color, thick)
            cv2.line(frame, (fx + fw, fy + fh), (fx + fw, fy + fh - c_len), color, thick)

            # Subtle bounding box outline
            cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (color[0], color[1], color[2]), 1)

            # Eye tracking circles
            if eyes_found:
                eye_y = fy + int(fh * 0.35)
                eye_x1 = fx + int(fw * 0.32)
                eye_x2 = fx + int(fw * 0.68)
                cv2.circle(frame, (eye_x1, eye_y), 4, (255, 255, 255), -1)
                cv2.circle(frame, (eye_x1, eye_y), 10, color, 1)
                cv2.circle(frame, (eye_x2, eye_y), 4, (255, 255, 255), -1)
                cv2.circle(frame, (eye_x2, eye_y), 10, color, 1)

            # 3. Dynamic Emotion Badge right above face
            pct = int(self.current_emotion_confidence * 100)
            tag_text = f"EMOTION: {self.current_emotion_label.upper()} ({pct}%)"
            badge_y = fy - 12 if fy > 45 else fy + fh + 32
            badge_w = max(210, fw)

            # Badge background
            cv2.rectangle(frame, (fx, badge_y - 24), (fx + badge_w, badge_y + 4), (15, 23, 42), -1)
            cv2.rectangle(frame, (fx, badge_y - 24), (fx + badge_w, badge_y + 4), color, 1)
            cv2.putText(frame, tag_text, (fx + 8, badge_y - 7),
                        cv2.FONT_HERSHEY_DUPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

            if smiles_found:
                cv2.putText(frame, "SMILE DETECTED", (fx + 8, badge_y + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.40, (52, 211, 153), 1, cv2.LINE_AA)
        else:
            self.latest_face_box = None
            # Searching crosshair reticle in center
            cx, cy = w // 2, h // 2
            cv2.line(frame, (cx - 20, cy), (cx + 20, cy), (100, 116, 139), 1)
            cv2.line(frame, (cx, cy - 20), (cx, cy + 20), (100, 116, 139), 1)
            cv2.putText(frame, "SEARCHING FOR FACE...", (cx - 85, cy + 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (148, 163, 184), 1, cv2.LINE_AA)

        # 4. Bottom Telemetry Bar
        cv2.rectangle(frame, (0, h - 28), (w, h), (15, 23, 42), -1)
        status_line = f"FACE: {'LOCKED' if len(faces) > 0 else 'STANDBY'}   EYES: {'ENGAGED' if eyes_found else 'TRACKING'}   LIGHT: {self.lighting_condition} ({self.ambient_light})"
        cv2.putText(frame, status_line, (14, h - 9),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (148, 163, 184), 1, cv2.LINE_AA)

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

                self.face_detected = len(faces) > 0
                eyes_found = False
                smiles_found = False

                if self.face_detected:
                    fx, fy, fw, fh = faces[0]
                    face_roi = enhanced_gray[fy:fy + fh, fx:fx + fw]
                    if self._eye_cascade and not self._eye_cascade.empty():
                        upper_face = face_roi[0:int(fh * 0.65), :]
                        eyes = self._eye_cascade.detectMultiScale(upper_face, scaleFactor=1.1, minNeighbors=3, minSize=(15, 15))
                        eyes_found = len(eyes) > 0
                    if self._smile_cascade and not self._smile_cascade.empty():
                        lower_face = face_roi[int(fh * 0.5):, :]
                        smiles = self._smile_cascade.detectMultiScale(lower_face, scaleFactor=1.2, minNeighbors=5, minSize=(20, 20))
                        smiles_found = len(smiles) > 0

                jpeg_bytes = self._annotate_frame(frame, faces, eyes_found, smiles_found)
                self.latest_annotated_jpeg = jpeg_bytes
                self.last_jpeg_time = time.time()
                return jpeg_bytes
            except Exception as e:
                logger.warning(f"Error in get_stream_frame: {e}")
                return self._create_standby_frame("ANALYSIS ERROR")

    def snapshot(self):
        """Processes current frame strictly in-memory and updates telemetry state."""
        with self._lock:
            now_t = time.time()
            if not self.active or self.cap is None or not self.cap.isOpened():
                self.frame_history.append({'timestamp': now_t, 'active': False, 'valid': False})
                return {
                    'active': False,
                    'status': self.status_text,
                    'face_detected': False,
                    'eyes_detected': False,
                    'smile_detected': False,
                    'confidence': 0.0,
                    'ambient_light': round(self.ambient_light, 3),
                    'lighting_condition': self.lighting_condition,
                    'fatigue_score': round(self.fatigue_score, 2)
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
                    'eyes_detected': False,
                    'smile_detected': False,
                    'confidence': 0.0,
                    'ambient_light': round(self.ambient_light, 3),
                    'lighting_condition': self.lighting_condition,
                    'fatigue_score': round(self.fatigue_score, 2)
                }

            self.last_frame_time = now_t
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

                self.face_detected = len(faces) > 0
                eyes_found = False
                smiles_found = False

                if self.face_detected:
                    fx, fy, fw, fh = faces[0]
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

                    self.confidence = min(0.98, 0.72 + 0.12 * (1 if eyes_found else 0) + 0.08 * min(2, len(faces)))
                else:
                    self.eyes_detected = False
                    self.smile_detected = False
                    self.confidence = 0.0
                    self.fatigue_score = max(0.0, self.fatigue_score - 0.05)

                self.frame_history.append({
                    'timestamp': now_t,
                    'active': True,
                    'valid': True,
                    'face_detected': self.face_detected,
                    'eyes_detected': self.eyes_detected,
                    'smile_detected': self.smile_detected,
                    'ambient_light': self.ambient_light,
                    'confidence': self.confidence
                })

                # Store annotated frame for live feed caching
                self.latest_annotated_jpeg = self._annotate_frame(frame, faces, eyes_found, smiles_found)
                self.last_jpeg_time = time.time()

            except Exception as e:
                logger.warning(f"Error during facial frame analysis: {e}")
            finally:
                del frame

            return {
                'active': True,
                'status': self.status_text,
                'face_detected': self.face_detected,
                'eyes_detected': self.eyes_detected,
                'smile_detected': self.smile_detected,
                'confidence': round(self.confidence, 2),
                'ambient_light': round(self.ambient_light, 3),
                'lighting_condition': self.lighting_condition,
                'fatigue_score': round(self.fatigue_score, 2)
            }

    def get_window_metrics(self, window_sec: float = 60.0) -> Dict[str, Any]:
        """
        Calculates all Part 3 camera visual signals and conditions across the observation window.
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
                'conditions': conditions
            }

