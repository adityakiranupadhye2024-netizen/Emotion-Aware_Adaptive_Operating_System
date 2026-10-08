"""Unit tests for KeyboardSensor (Part 1 - Keyboard Conditions & Privacy)."""
import unittest
import time
from app.sensors.keyboard import KeyboardSensor


class DummyKey:
    def __init__(self, char=None, name=None):
        self.char = char
        self.name = name


class TestKeyboardSensor(unittest.TestCase):
    def setUp(self):
        self.sensor = KeyboardSensor()
        self.sensor.events_history.clear()

    def test_privacy_no_keylogging(self):
        """Verify that typed characters or text are NEVER recorded or stored."""
        k_a = DummyKey(char='secret_character_x')
        self.sensor._press(k_a)

        # Inspect sensor internal state: only (timestamp, is_backspace) tuples must exist
        self.assertEqual(len(self.sensor.events_history), 1)
        ts, is_bs = self.sensor.events_history[0]
        self.assertIsInstance(ts, float)
        self.assertFalse(is_bs)

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertNotIn('secret_character_x', str(metrics))
        self.assertNotIn('text', metrics)
        self.assertNotIn('chars', metrics)

    def test_normal_typing(self):
        """Verify NORMAL ACTIVE TYPING conditions: typing_rate >= 1.0 kps, activity_ratio >= 0.35."""
        base_t = time.time() - 50.0
        # 80 keystrokes across 25 seconds in a 60s window: rate = 80/60 = 1.33 kps, activity = 25/60 = 0.417
        for i in range(80):
            t = base_t + (i * 0.31)
            self.sensor.events_history.append((t, False))

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertGreaterEqual(metrics['typing_rate_kps'], 1.0)
        self.assertGreaterEqual(metrics['typing_activity_ratio'], 0.35)
        self.assertTrue(metrics['conditions']['normal_active'])

    def test_high_typing_intensity(self):
        """Verify HIGH TYPING INTENSITY: typing_rate >= 3.0 kps and activity >= 0.50."""
        base_t = time.time() - 50.0
        # 200 keystrokes across 35 distinct seconds: rate = 200/60 = 3.33 kps, activity = 35/60 = 0.583
        for i in range(200):
            t = base_t + (i * 0.17)
            self.sensor.events_history.append((t, False))

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertGreaterEqual(metrics['typing_rate_kps'], 3.0)
        self.assertGreaterEqual(metrics['typing_activity_ratio'], 0.50)
        self.assertTrue(metrics['conditions']['high_intensity'])

    def test_high_backspace_ratio_friction(self):
        """Verify HIGH CORRECTION conditions: backspace_ratio >= 0.10 and >= 0.18."""
        base_t = time.time() - 40.0
        for i in range(50):
            t = base_t + i * 0.5
            is_backspace = (i < 10)  # 10 backspaces out of 50 = 20%
            self.sensor.events_history.append((t, is_backspace))

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertAlmostEqual(metrics['backspace_ratio'], 0.20, places=2)
        self.assertTrue(metrics['conditions']['high_friction'])
        self.assertTrue(metrics['conditions']['strong_friction'])

    def test_slow_hesitant_typing(self):
        """Verify SLOW / HESITANT TYPING: rate <= 0.60 kps and activity >= 0.25."""
        base_t = time.time() - 50.0
        # 20 keystrokes spread over 20 distinct seconds: rate = 20/60 = 0.33 kps, activity = 20/60 = 0.33
        for i in range(20):
            t = base_t + (i * 2.0)
            self.sensor.events_history.append((t, False))

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertLessEqual(metrics['typing_rate_kps'], 0.60)
        self.assertGreaterEqual(metrics['typing_activity_ratio'], 0.25)
        self.assertTrue(metrics['conditions']['slow_hesitant'])

    def test_near_idle(self):
        """Verify NEAR-IDLE condition: typing_rate < 0.20 kps and activity < 0.15."""
        # Only 2 keystrokes in 60s: rate = 2/60 = 0.03 kps, activity = 2/60 = 0.03
        base_t = time.time() - 30.0
        self.sensor.events_history.append((base_t, False))
        self.sensor.events_history.append((base_t + 1.0, False))

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertTrue(metrics['conditions']['near_idle'])


if __name__ == '__main__':
    unittest.main()
