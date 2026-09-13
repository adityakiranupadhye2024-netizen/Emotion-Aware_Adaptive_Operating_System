import time
import logging
import threading
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

    def open_camera(self) -> bool:
        """Explicitly opens camera for the scheduled sensing window only."""
        with self._lock:
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
                    self.active = True
                    self.status_text = "CAMERA SENSING"
                    logger.info("Camera activated for sensing window.")
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

    def close_camera(self):
        """Immediately closes and releases the camera hardware in a thread-safe manner."""
        with self._lock:
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
        self.close_camera()

    def is_active(self) -> bool:
        with self._lock:
            return self.active and (self.cap is not None) and self.cap.isOpened()

    def snapshot(self):
        """Processes current frame strictly in-memory. Discards raw frame immediately."""
        with self._lock:
            if not self.active or self.cap is None or not self.cap.isOpened():
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

            self.last_frame_time = time.time()
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                # Compute raw ambient light (normalized 0.0 to 1.0)
                raw_ambient = float(np.mean(gray) / 255.0)
                # Smooth ambient light level with EMA
                self.ambient_light = round(0.75 * self.ambient_light + 0.25 * raw_ambient, 3)

                if self.ambient_light < 0.25:
                    self.lighting_condition = "DIM"
                elif self.ambient_light > 0.65:
                    self.lighting_condition = "BRIGHT"
                else:
                    self.lighting_condition = "NORMAL"

                # Apply Contrast Limited Adaptive Histogram Equalization (CLAHE) for dim/harsh light robustness
                enhanced_gray = self._clahe.apply(gray) if self._clahe is not None else gray

                # Multi-stage face detection
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

                    # Eye detection inside upper half of face
                    if self._eye_cascade and not self._eye_cascade.empty():
                        upper_face = face_roi[0:int(fh * 0.65), :]
                        eyes = self._eye_cascade.detectMultiScale(upper_face, scaleFactor=1.1, minNeighbors=3, minSize=(15, 15))
                        eyes_found = len(eyes) > 0

                    # Smile detection in lower half of face
                    if self._smile_cascade and not self._smile_cascade.empty():
                        lower_face = face_roi[int(fh * 0.5):, :]
                        smiles = self._smile_cascade.detectMultiScale(lower_face, scaleFactor=1.2, minNeighbors=5, minSize=(20, 20))
                        smiles_found = len(smiles) > 0

                    self.eyes_detected = eyes_found
                    self.smile_detected = smiles_found

                    # Compute fatigue: face present but eyes consistently closed/missing
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
