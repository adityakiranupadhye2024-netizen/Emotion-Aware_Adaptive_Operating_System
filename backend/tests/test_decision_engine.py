"""Unit tests for DecisionEngine (Parts 9, 18, 19 - Decision Conditions & Safety)."""
import unittest
from app.decision_engine.engine import DecisionEngine


class TestDecisionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DecisionEngine()

    def test_frustration_triggers_audio_reduction(self):
        """Verify high frustration (keyboard correction + mouse agitation) triggers audio reduction/mute."""
        state = {
            'emotion': {
                'dominant': 'Frustrated',
                'probabilities': {'Frustrated': 0.65, 'Focused': 0.15, 'Fatigued': 0.10, 'Relaxed': 0.10},
                'confidence': 0.65,
                'evidence_signals': {
                    'frustration_signal': 0.68,
                    'mouse_agitation_score': 0.38,
                    'keyboard_correction_score': 0.70
                }
            },
            'context': {
                'context': 'CODING',
                'activity': 'CODING',
                'context_confidence': 0.90
            },
            'workload': {'score': 0.65},
            'inputs': {
                'keyboard': {'typing_rate': 3.5, 'backspace_rate': 0.16, 'typing_activity_ratio': 0.60, 'active': True},
                'mouse': {'jitter': 0.40, 'mouse_active_ratio': 0.60, 'click_rate': 12.0, 'idle': False, 'active': True},
                'camera': {'conditions': {'valid_camera_observation': True}, 'confidence': 0.8}
            },
            'actual_os_state': {'audio_muted': False, 'volume': 70}
        }

        decision = self.engine.decide(state)
        self.assertIn(decision.action, ['MUTE_AUDIO', 'REDUCE_AUDIO'])
        self.assertIn('frustration', decision.reason.lower())

    def test_meeting_safety_never_mutes_audio(self):
        """Verify that meeting context NEVER allows MUTE_AUDIO or volume reduction, even with frustration."""
        state = {
            'emotion': {
                'dominant': 'Frustrated',
                'probabilities': {'Frustrated': 0.80, 'Focused': 0.10, 'Fatigued': 0.05, 'Relaxed': 0.05},
                'confidence': 0.80,
                'evidence_signals': {
                    'frustration_signal': 0.85,
                    'mouse_agitation_score': 0.50
                }
            },
            'context': {
                'context': 'MEETING',
                'activity': 'MEETING',
                'context_confidence': 0.95
            },
            'workload': {'score': 0.75},
            'inputs': {
                'keyboard': {'typing_rate': 2.0, 'backspace_rate': 0.20, 'typing_activity_ratio': 0.50, 'active': True},
                'mouse': {'jitter': 0.45, 'mouse_active_ratio': 0.50, 'click_rate': 10.0, 'idle': False, 'active': True},
                'camera': {'conditions': {'valid_camera_observation': True}, 'confidence': 0.85}
            },
            'actual_os_state': {'audio_muted': False, 'volume': 75}
        }

        decision = self.engine.decide(state)
        self.assertNotEqual(decision.action, 'MUTE_AUDIO')
        self.assertNotEqual(decision.action, 'REDUCE_AUDIO')

    def test_gaming_safety_no_intrusive_action(self):
        """Verify gaming context suppresses intrusive focus/audio actions."""
        state = {
            'emotion': {
                'dominant': 'Focused',
                'probabilities': {'Focused': 0.70, 'Relaxed': 0.10, 'Frustrated': 0.10, 'Fatigued': 0.10},
                'confidence': 0.70,
                'evidence_signals': {'focus_signal': 0.75}
            },
            'context': {
                'context': 'GAMING',
                'activity': 'GAMING',
                'context_confidence': 0.92
            },
            'workload': {'score': 0.80},
            'inputs': {
                'keyboard': {'typing_rate': 4.0, 'backspace_rate': 0.02, 'typing_activity_ratio': 0.70, 'active': True},
                'mouse': {'jitter': 0.10, 'mouse_active_ratio': 0.80, 'click_rate': 40.0, 'idle': False, 'active': True},
                'camera': {'conditions': {'valid_camera_observation': False}}
            },
            'actual_os_state': {'focus_mode_active': False}
        }

        decision = self.engine.decide(state)
        self.assertEqual(decision.action, 'NO_ACTION')

    def test_deep_focus_triggers_focus_mode(self):
        """Verify high workload + productive context + focus evidence triggers ENABLE_FOCUS_MODE."""
        state = {
            'emotion': {
                'dominant': 'Focused',
                'probabilities': {'Focused': 0.75, 'Flow State': 0.15, 'Relaxed': 0.05, 'Frustrated': 0.05},
                'confidence': 0.75,
                'evidence_signals': {'focus_signal': 0.78}
            },
            'context': {
                'context': 'CODING',
                'activity': 'CODING',
                'context_confidence': 0.92
            },
            'workload': {'score': 0.68},
            'inputs': {
                'keyboard': {'typing_rate': 3.2, 'backspace_rate': 0.03, 'typing_activity_ratio': 0.55, 'active': True},
                'mouse': {'jitter': 0.08, 'mouse_active_ratio': 0.45, 'click_rate': 5.0, 'idle': False, 'active': True},
                'camera': {'conditions': {'valid_camera_observation': True}, 'confidence': 0.85}
            },
            'actual_os_state': {'focus_mode_active': False}
        }

        decision = self.engine.decide(state)
        self.assertEqual(decision.action, 'ENABLE_FOCUS_MODE')

    def test_fatigue_triggers_brightness_reduction(self):
        """Verify persistent fatigue triggers REDUCE_BRIGHTNESS."""
        state = {
            'emotion': {
                'dominant': 'Fatigued',
                'probabilities': {'Fatigued': 0.65, 'Relaxed': 0.15, 'Focused': 0.10, 'Frustrated': 0.10},
                'confidence': 0.65,
                'evidence_signals': {'fatigue_signal': 0.62}
            },
            'context': {
                'context': 'STUDYING',
                'activity': 'STUDYING',
                'context_confidence': 0.88
            },
            'workload': {'score': 0.45},
            'inputs': {
                'keyboard': {'typing_rate': 0.8, 'backspace_rate': 0.05, 'typing_activity_ratio': 0.25, 'active': True},
                'mouse': {'jitter': 0.05, 'mouse_active_ratio': 0.25, 'click_rate': 2.0, 'idle': False, 'active': True},
                'camera': {
                    'conditions': {
                        'valid_camera_observation': True,
                        'face_present': True,
                        'low_eye_visibility': True
                    },
                    'confidence': 0.80,
                    'fatigue_proxy': 0.65
                }
            },
            'actual_os_state': {'brightness': 0.80}
        }

        decision = self.engine.decide(state)
        self.assertEqual(decision.action, 'REDUCE_BRIGHTNESS')

    def test_dim_environment_triggers_dark_mode(self):
        """Verify valid camera + dim illumination proxy (< 0.25) triggers ENABLE_DARK_MODE."""
        state = {
            'emotion': {
                'dominant': 'Focused',
                'probabilities': {'Focused': 0.60, 'Relaxed': 0.20, 'Fatigued': 0.10, 'Frustrated': 0.10},
                'confidence': 0.60,
                'evidence_signals': {'fatigue_signal': 0.40}
            },
            'context': {
                'context': 'CODING',
                'activity': 'CODING',
                'context_confidence': 0.90
            },
            'workload': {'score': 0.50},
            'inputs': {
                'keyboard': {'typing_rate': 2.0, 'backspace_rate': 0.04, 'typing_activity_ratio': 0.45, 'active': True},
                'mouse': {'jitter': 0.08, 'mouse_active_ratio': 0.40, 'click_rate': 4.0, 'idle': False, 'active': True},
                'camera': {
                    'ambient_light': 0.18,
                    'confidence': 0.85,
                    'conditions': {
                        'valid_camera_observation': True,
                        'dim_proxy': True,
                        'bright_proxy': False
                    }
                }
            },
            'actual_os_state': {'dark_mode': False}
        }

        decision = self.engine.decide(state)
        self.assertEqual(decision.action, 'ENABLE_DARK_MODE')


if __name__ == '__main__':
    unittest.main()
