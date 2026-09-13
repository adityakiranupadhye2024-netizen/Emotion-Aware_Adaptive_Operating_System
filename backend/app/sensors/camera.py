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
        self.confidence = 0.0
        self.ambient_light = 0.5
        self.detector = None
        self.last_frame_time = 0
        self.status_text = "CAMERA OFF"
        self._cascade_path = None

        if cv2 is not None:
            try:
                self._cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            except Exception:
                self._cascade_path = None

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
                    if self._cascade_path and self.detector is None:
                        self.detector = cv2.CascadeClassifier(self._cascade_path)
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
            self.confidence = 0.0
            self.status_text = "CAMERA OFF"
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
            logger.info("Camera closed and released.")

    # Alias for shutdown
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
                    'confidence': 0.0,
                    'ambient_light': self.ambient_light
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
                    'confidence': 0.0,
                    'ambient_light': self.ambient_light
                }

            self.last_frame_time = time.time()
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                # Ambient light level normalized (0.0 = total darkness, 1.0 = bright)
                self.ambient_light = float(np.mean(gray) / 255.0)

                # In-memory face detection
                if self.detector is not None:
                    faces = self.detector.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(60, 60))
                    self.face_detected = len(faces) > 0
                    self.confidence = min(0.98, 0.65 + 0.15 * len(faces)) if self.face_detected else 0.0
                else:
                    self.face_detected = False
                    self.confidence = 0.0
            except Exception:
                pass
            finally:
                # Explicitly clear reference to raw frame
                del frame

            return {
                'active': True,
                'status': self.status_text,
                'face_detected': self.face_detected,
            'confidence': round(self.confidence, 2),
            'ambient_light': round(self.ambient_light, 3)
        }
