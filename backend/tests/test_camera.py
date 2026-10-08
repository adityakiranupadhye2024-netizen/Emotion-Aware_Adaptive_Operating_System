"""Unit tests for CameraSensor (Part 3 - Camera Conditions & Visual Proxies)."""
import unittest
import time
from app.sensors.camera import CameraSensor


class TestCameraSensor(unittest.TestCase):
    def setUp(self):
        self.sensor = CameraSensor()
        self.sensor.frame_history.clear()

    def test_face_present_and_eyes_engaged(self):
        """Verify conditions when face is present and eyes are actively detected."""
        now = time.time()
        for i in range(20):
            self.sensor.frame_history.append({
                'timestamp': now - (20 - i),
                'valid': True,
                'active': True,
                'face_detected': True,
                'eyes_detected': True,
                'smile_detected': False,
                'confidence': 0.90,
                'ambient_light': 0.45
            })

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertTrue(metrics['conditions']['valid_camera_observation'])
        self.assertTrue(metrics['conditions']['face_present'])
        self.assertTrue(metrics['conditions']['strong_face_presence'])
        self.assertFalse(metrics['conditions']['face_mostly_absent'])
        self.assertTrue(metrics['conditions']['eyes_engaged'])
        self.assertGreater(metrics['camera_data_confidence'], 0.70)

    def test_face_absent(self):
        """Verify conditions when face is absent for the majority of the window."""
        now = time.time()
        for i in range(20):
            self.sensor.frame_history.append({
                'timestamp': now - (20 - i),
                'valid': True,
                'active': True,
                'face_detected': False,
                'eyes_detected': False,
                'smile_detected': False,
                'confidence': 0.0,
                'ambient_light': 0.40
            })

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertTrue(metrics['conditions']['face_mostly_absent'])
        self.assertFalse(metrics['conditions']['face_present'])
        self.assertLess(metrics['camera_data_confidence'], 0.40)

    def test_low_eye_visibility_fatigue_proxy(self):
        """Verify persistent low eye visibility with face present contributes to fatigue proxy."""
        now = time.time()
        # 20 frames, all have face detected, but only 4 have eyes detected (20% eyes)
        for i in range(20):
            has_eyes = (i < 4)
            self.sensor.frame_history.append({
                'timestamp': now - (20 - i),
                'valid': True,
                'active': True,
                'face_detected': True,
                'eyes_detected': has_eyes,
                'smile_detected': False,
                'confidence': 0.85,
                'ambient_light': 0.40
            })

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertTrue(metrics['conditions']['low_eye_visibility'])
        self.assertTrue(metrics['conditions']['persistent_low_eye_visibility'])
        self.assertGreater(metrics['fatigue_proxy'], 0.50)

    def test_dim_proxy_lighting(self):
        """Verify dim lighting proxy when average ambient illumination < 0.25."""
        now = time.time()
        for i in range(20):
            self.sensor.frame_history.append({
                'timestamp': now - (20 - i),
                'valid': True,
                'active': True,
                'face_detected': True,
                'eyes_detected': True,
                'smile_detected': False,
                'confidence': 0.85,
                'ambient_light': 0.18
            })

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertTrue(metrics['conditions']['dim_proxy'])
        self.assertFalse(metrics['conditions']['bright_proxy'])

    def test_bright_proxy_lighting(self):
        """Verify bright lighting proxy when average ambient illumination > 0.65."""
        now = time.time()
        for i in range(20):
            self.sensor.frame_history.append({
                'timestamp': now - (20 - i),
                'valid': True,
                'active': True,
                'face_detected': True,
                'eyes_detected': True,
                'smile_detected': False,
                'confidence': 0.85,
                'ambient_light': 0.75
            })

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertTrue(metrics['conditions']['bright_proxy'])
        self.assertFalse(metrics['conditions']['dim_proxy'])


if __name__ == '__main__':
    unittest.main()
