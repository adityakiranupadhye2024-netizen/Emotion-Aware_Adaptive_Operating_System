"""Unit tests for MouseSensor (Part 2 - Mouse Conditions & Agitation)."""
import unittest
import time
from app.sensors.mouse import MouseSensor


class TestMouseSensor(unittest.TestCase):
    def setUp(self):
        self.sensor = MouseSensor()
        self.sensor.positions.clear()
        self.sensor.clicks_history.clear()

    def test_normal_movement(self):
        """Verify normal movement: distance >= 100 px/min triggers mouse_active."""
        now = time.time()
        base_t = now - 50.0
        # Move cursor in a straight line: 200 pixels over 20 points
        for i in range(20):
            t = base_t + i * 2.0
            x = 100.0 + (i * 10.0)
            y = 100.0
            self.sensor.positions.append((t, x, y))
        self.sensor.last_event = base_t + 38.0

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertGreaterEqual(metrics['movement_distance_per_minute'], 100.0)
        self.assertTrue(metrics['conditions']['mouse_active'])
        self.assertAlmostEqual(metrics['straightness'], 1.0, places=1)
        self.assertFalse(metrics['conditions']['agitated_mouse'])

    def test_high_clicks(self):
        """Verify high click rate (>= 30 clicks/min) and very high (>= 60 clicks/min)."""
        now = time.time()
        base_t = now - 50.0
        for i in range(35):
            t = base_t + i * 1.0
            self.sensor.clicks_history.append(t)
        self.sensor.last_event = now

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertGreaterEqual(metrics['click_rate'], 30.0)
        self.assertTrue(metrics['conditions']['high_click_rate'])
        self.assertFalse(metrics['conditions']['very_high_click_rate'])

        # Now add 30 more clicks -> total 65
        for i in range(30):
            self.sensor.clicks_history.append(base_t + 35.0 + (i * 0.4))
        metrics2 = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertGreaterEqual(metrics2['click_rate'], 60.0)
        self.assertTrue(metrics2['conditions']['very_high_click_rate'])

    def test_agitation_and_strong_agitation(self):
        """Verify jitter score and agitation conditions with erratic rapid back-and-forth movement & clicks."""
        now = time.time()
        base_t = now - 50.0
        # Back-and-forth zigzagging with high reversals and large total distance
        x = 500.0
        for i in range(80):
            t = base_t + i * 0.5
            x = 500.0 if (i % 2 == 0) else 530.0  # 30px jump every 0.5s -> 80 jumps = 2400px
            self.sensor.positions.append((t, x, 500.0))

        # Add 12 clicks
        for i in range(12):
            self.sensor.clicks_history.append(base_t + i * 3.0)
        self.sensor.last_event = now

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertGreaterEqual(metrics['movement_distance_per_minute'], 700.0)
        self.assertGreaterEqual(metrics['click_rate'], 8.0)
        self.assertGreaterEqual(metrics['jitter_score'], 0.35)
        self.assertTrue(metrics['conditions']['agitated_mouse'])
        self.assertTrue(metrics['conditions']['strong_agitation'])

    def test_idle_conditions(self):
        """Verify MOUSE IDLE (>= 15s) and STRONG IDLE (>= 25s)."""
        now = time.time()
        # Last event 26 seconds ago
        self.sensor.last_event = now - 26.0

        metrics = self.sensor.get_window_metrics(window_sec=60.0)
        self.assertTrue(metrics['conditions']['mouse_idle'])
        self.assertTrue(metrics['conditions']['strong_idle'])


if __name__ == '__main__':
    unittest.main()
