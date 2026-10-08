"""Unit tests for StateBuilder and Adaptive Score (AS) calculation (Parts 5, 6, 8)."""
import unittest
from app.services.state import StateBuilder
from app.decision_engine.engine import DecisionEngine


class TestStateAndAdaptiveScore(unittest.TestCase):
    def setUp(self):
        self.builder = StateBuilder()
        self.engine = DecisionEngine()

    def test_multimodal_emotion_probabilities(self):
        """Verify that emotion probabilities sum to 1.0, are non-negative, and respond to evidence."""
        calc = self.builder.compute_multimodal_state(
            typing_rate=3.5,
            backspace_rate=0.15,
            rhythm_cv=0.85,
            typing_activity_ratio=0.60,
            mouse_active_ratio=0.50,
            jitter_score=0.40,
            click_rate=12.0,
            idle_seconds=0.0,
            camera_metrics={'conditions': {'valid_camera_observation': True}, 'camera_data_confidence': 0.8},
            context='CODING',
            context_conf=0.90,
            switch_rate=1.0,
            session_minutes=30.0,
            is_idle=False
        )

        probs = calc['emotion_probabilities']
        # Must sum to 1.0 within floating point precision
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=3)
        # All probabilities must be >= 0.0
        for em, p in probs.items():
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)

        # Frustrated should be elevated due to backspace friction + mouse jitter
        self.assertGreater(probs['Frustrated'], 0.20)

    def test_behavioral_cognitive_workload(self):
        """Verify cognitive workload calculation ranges and levels."""
        # Low activity -> LOW workload (< 0.30)
        calc_low = self.builder.compute_multimodal_state(
            typing_rate=0.1,
            backspace_rate=0.0,
            rhythm_cv=0.0,
            typing_activity_ratio=0.05,
            mouse_active_ratio=0.05,
            jitter_score=0.0,
            click_rate=0.0,
            idle_seconds=20.0,
            camera_metrics={},
            context='GENERAL_WORK',
            context_conf=0.60,
            switch_rate=0.0,
            session_minutes=5.0,
            is_idle=True
        )
        self.assertLess(calc_low['workload'], 0.30)
        self.assertEqual(calc_low['workload_level'], 'LOW')

        # High activity -> HIGH or VERY HIGH workload (>= 0.60)
        calc_high = self.builder.compute_multimodal_state(
            typing_rate=4.0,
            backspace_rate=0.08,
            rhythm_cv=0.5,
            typing_activity_ratio=0.75,
            mouse_active_ratio=0.70,
            jitter_score=0.15,
            click_rate=20.0,
            idle_seconds=0.0,
            camera_metrics={},
            context='CODING',
            context_conf=0.90,
            switch_rate=2.0,
            session_minutes=45.0,
            is_idle=False
        )
        self.assertGreaterEqual(calc_high['workload'], 0.60)
        self.assertIn(calc_high['workload_level'], ['HIGH', 'VERY HIGH'])

    def test_adaptive_score_deterministic_and_normalized(self):
        """Verify AS calculation: deterministic, normalized in [0, 1], and respects weights."""
        dummy_state = {
            'emotion': {
                'dominant': 'Focused',
                'probabilities': {'Focused': 0.70, 'Flow State': 0.10, 'Frustrated': 0.05, 'Fatigued': 0.05, 'Confused': 0.05, 'Relaxed': 0.05},
                'confidence': 0.70
            },
            'context': {
                'context': 'CODING',
                'context_confidence': 0.90,
                'activity': 'CODING'
            },
            'workload': {
                'score': 0.65
            },
            'inputs': {
                'keyboard': {'typing_rate': 3.0, 'backspace_rate': 0.04},
                'mouse': {'jitter': 0.10, 'mouse_active_ratio': 0.50},
                'camera': {'ambient_light': 0.50}
            }
        }

        score1, comp1 = self.engine.calculate_as(dummy_state)
        score2, comp2 = self.engine.calculate_as(dummy_state)

        # Deterministic
        self.assertEqual(score1, score2)
        self.assertEqual(comp1, comp2)

        # In [0, 1]
        self.assertGreaterEqual(score1, 0.0)
        self.assertLessEqual(score1, 1.0)

        # Components present
        self.assertIn('emotion', comp1)
        self.assertIn('context', comp1)
        self.assertIn('workload', comp1)
        self.assertIn('personalization', comp1)


if __name__ == '__main__':
    unittest.main()
