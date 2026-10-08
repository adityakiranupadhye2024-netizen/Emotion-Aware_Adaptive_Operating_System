"""Unit tests for ContextSensor (Part 4 - Context Conditions & App Transitions)."""
import unittest
import time
from unittest.mock import patch
from app.sensors.context import ContextSensor


class TestContextSensor(unittest.TestCase):
    def setUp(self):
        self.sensor = ContextSensor()
        self.sensor.last_app = None
        self.sensor.actual_app_switches = 0
        self.sensor.app_switch_history.clear()

    def test_context_classification(self):
        """Verify canonical context classifications for different active applications."""
        # 1. Coding
        ctx, conf = self.sensor.classify('Visual Studio Code', kb_rate=1.5, mouse_clicks=5, mouse_idle=False)
        self.assertEqual(ctx, 'CODING')
        self.assertGreaterEqual(conf, 0.85)

        # 2. Meeting
        ctx, conf = self.sensor.classify('Zoom Meeting', kb_rate=0.0, mouse_clicks=0, mouse_idle=True)
        self.assertEqual(ctx, 'MEETING')
        self.assertGreaterEqual(conf, 0.90)

        # 3. Writing
        ctx, conf = self.sensor.classify('Microsoft Word', kb_rate=1.0, mouse_clicks=2, mouse_idle=False)
        self.assertEqual(ctx, 'WRITING')
        self.assertGreaterEqual(conf, 0.80)

        # 4. Studying
        ctx, conf = self.sensor.classify('Adobe Acrobat Reader', kb_rate=0.0, mouse_clicks=1, mouse_idle=False)
        self.assertEqual(ctx, 'STUDYING')
        self.assertGreaterEqual(conf, 0.85)

        # 5. Browsing
        ctx, conf = self.sensor.classify('Google Chrome', kb_rate=0.2, mouse_clicks=3, mouse_idle=False)
        self.assertEqual(ctx, 'BROWSING')
        self.assertGreaterEqual(conf, 0.80)

        # 6. Gaming
        ctx, conf = self.sensor.classify('Steam Client', kb_rate=2.0, mouse_clicks=20, mouse_idle=False)
        self.assertEqual(ctx, 'GAMING')
        self.assertGreaterEqual(conf, 0.90)

    def test_idle_context(self):
        """Verify IDLE context when both keyboard and mouse are inactive >= 15s / 25s."""
        # 15s inactivity
        ctx, conf = self.sensor.classify('Code', kb_rate=0.0, mouse_clicks=0, mouse_idle=True,
                                         kb_idle_seconds=16.0, mouse_idle_seconds=16.0)
        self.assertEqual(ctx, 'IDLE')
        self.assertGreaterEqual(conf, 0.85)

        # 25s strong inactivity
        ctx, conf = self.sensor.classify('Code', kb_rate=0.0, mouse_clicks=0, mouse_idle=True,
                                         kb_idle_seconds=26.0, mouse_idle_seconds=26.0)
        self.assertEqual(ctx, 'IDLE')
        self.assertEqual(conf, 0.95)

    @patch.object(ContextSensor, 'active_app')
    def test_actual_app_transitions_not_sample_counts(self, mock_active_app):
        """Verify actual app transitions count when app changes, and do NOT inflate on repeated samples."""
        # Consecutive samples of the same app
        mock_active_app.return_value = 'Code'
        snap1 = self.sensor.snapshot()
        snap2 = self.sensor.snapshot()
        snap3 = self.sensor.snapshot()
        self.assertEqual(self.sensor.actual_app_switches, 0)

        # Switch to Chrome
        mock_active_app.return_value = 'Google Chrome'
        snap4 = self.sensor.snapshot()
        self.assertEqual(self.sensor.actual_app_switches, 1)

        # Remain in Chrome for 5 samples
        for _ in range(5):
            self.sensor.snapshot()
        self.assertEqual(self.sensor.actual_app_switches, 1)

        # Switch to Terminal
        mock_active_app.return_value = 'iTerm'
        snap5 = self.sensor.snapshot()
        self.assertEqual(self.sensor.actual_app_switches, 2)


if __name__ == '__main__':
    unittest.main()
