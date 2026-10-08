"""
Comprehensive Unit Tests for EAOS DeepFace Pretrained Facial Emotion Pipeline & Multimodal Decision System.
Covers all 20 required criteria:
 1. Valid face frame
 2. No-face frame
 3. Invalid frame
 4. DeepFace inference failure
 5. Emotion probability normalization
 6. Temporal smoothing (EMA)
 7. Stale emotion timeout
 8. Camera privacy OFF
 9. Camera OFF during adaptation
10. 60-second input window
11. 60-second adaptation window
12. Multimodal frustration
13. Multimodal fatigue
14. Focus
15. Meeting safeguard
16. Gaming safeguard
17. NO_ACTION
18. Actuator verification (Command success != State verification)
19. Exact audio restoration (Never hard-coded 50)
20. Exact brightness restoration (Never fixed 0.65)
"""
import unittest
import time
from unittest.mock import patch, MagicMock
import numpy as np

from app.sensors.camera import CameraSensor
from app.services.state import StateBuilder
from app.decision_engine.engine import DecisionEngine
from app.services.actuator import MacActuator
from app.services.scheduler import CycleScheduler, InputObservationWindow
from app.core.config import settings


class TestDeepFaceIntegration(unittest.TestCase):
    def setUp(self):
        self.camera = CameraSensor()
        self.builder = StateBuilder()
        self.engine = DecisionEngine()
        self.actuator = MacActuator()

    def tearDown(self):
        self.camera.close_camera(force=True)

    # -------------------------------------------------------------------------
    # 1. Valid face frame
    # -------------------------------------------------------------------------
    @patch('app.sensors.camera.DeepFace')
    def test_01_valid_face_frame(self, mock_deepface):
        mock_deepface.analyze.return_value = [{
            'dominant_emotion': 'happy',
            'emotion': {
                'angry': 1.0, 'disgust': 0.1, 'fear': 0.2, 'happy': 85.0,
                'sad': 2.0, 'surprise': 3.0, 'neutral': 8.7
            },
            'region': {'x': 100, 'y': 100, 'w': 150, 'h': 150}
        }]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.camera._run_emotion_inference(frame, (100, 100, 150, 150), time.time())

        self.assertTrue(self.camera.face_detected)
        self.assertTrue(self.camera.emotion_available)
        self.assertFalse(self.camera.emotion_stale)
        self.assertEqual(self.camera.dominant_facial_emotion, 'happy')
        self.assertGreater(self.camera.emotion_confidence, 0.70)
        self.assertGreater(self.camera.facial_relaxation, 0.50)

    # -------------------------------------------------------------------------
    # 2. No-face frame
    # -------------------------------------------------------------------------
    def test_02_no_face_frame(self):
        # Frame with no faces
        self.camera.active = False
        snap = self.camera.snapshot()

        self.assertFalse(snap['face_detected'])
        self.assertFalse(snap['emotion_available'])
        self.assertTrue(snap['emotion_stale'])
        # Must NOT return fake "Focused 85%"
        self.assertNotEqual(snap.get('current_emotion_label'), 'Focused 85%')

    # -------------------------------------------------------------------------
    # 3. Invalid frame
    # -------------------------------------------------------------------------
    def test_03_invalid_frame(self):
        # Corrupt or empty frame simulation
        with patch.object(self.camera, 'cap') as mock_cap:
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (False, None)
            self.camera.active = True

            snap = self.camera.snapshot()
            self.assertFalse(snap['face_detected'])
            self.assertFalse(snap['emotion_available'])
            self.assertTrue(snap['emotion_stale'])

    # -------------------------------------------------------------------------
    # 4. DeepFace inference failure
    # -------------------------------------------------------------------------
    @patch('app.sensors.camera.DeepFace')
    def test_04_deepface_inference_failure(self, mock_deepface):
        mock_deepface.analyze.side_effect = RuntimeError("GPU Out of Memory or Model Error")

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Must catch error and not crash
        self.camera._run_emotion_inference(frame, (50, 50, 100, 100), time.time())

        self.assertFalse(self.camera.emotion_available)
        self.assertTrue(self.camera.emotion_stale)

    # -------------------------------------------------------------------------
    # 5. Emotion probability normalization
    # -------------------------------------------------------------------------
    def test_05_emotion_probability_normalization(self):
        raw_percentages = {
            'angry': 61.0,
            'fear': 4.0,
            'neutral': 11.0,
            'sad': 8.0,
            'disgust': 2.0,
            'happy': 3.0,
            'surprise': 11.0
        }
        normalized = self.camera._normalize_emotions(raw_percentages)

        self.assertAlmostEqual(sum(normalized.values()), 1.0, places=3)
        for k, v in normalized.items():
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)
        self.assertAlmostEqual(normalized['angry'], 0.61, delta=0.02)

    # -------------------------------------------------------------------------
    # 6. Temporal smoothing (EMA)
    # -------------------------------------------------------------------------
    @patch('app.sensors.camera.DeepFace')
    def test_06_temporal_smoothing(self, mock_deepface):
        self.camera.ema_alpha = 0.25
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Frame 1: Angry = 60%
        mock_deepface.analyze.return_value = [{'dominant_emotion': 'angry', 'emotion': {'angry': 60.0, 'neutral': 40.0}}]
        self.camera._run_emotion_inference(frame, (50, 50, 100, 100), time.time())
        p1 = self.camera.smoothed_facial_emotions['angry']

        # Frame 2: Angry = 80%
        mock_deepface.analyze.return_value = [{'dominant_emotion': 'angry', 'emotion': {'angry': 80.0, 'neutral': 20.0}}]
        self.camera._run_emotion_inference(frame, (50, 50, 100, 100), time.time())
        p2 = self.camera.smoothed_facial_emotions['angry']

        # EMA formula: 0.25 * 0.80 + 0.75 * p1
        expected = 0.25 * 0.80 + 0.75 * p1
        self.assertAlmostEqual(p2, expected, delta=0.05)
        self.assertGreater(p2, p1)

    # -------------------------------------------------------------------------
    # 7. Stale emotion timeout
    # -------------------------------------------------------------------------
    def test_07_stale_emotion_timeout(self):
        self.camera.stale_timeout_sec = 2.0
        self.camera.last_inference_time = time.time() - 3.5  # 3.5s ago (> 2s timeout)
        self.camera.emotion_available = True
        self.camera.emotion_stale = False

        # When stream or snapshot processes with no face
        snap = self.camera.snapshot()
        self.assertTrue(snap['emotion_stale'])
        self.assertFalse(snap['emotion_available'])

    # -------------------------------------------------------------------------
    # 8. Camera privacy OFF
    # -------------------------------------------------------------------------
    def test_08_camera_privacy_off(self):
        # When user disables camera sensing in settings
        with patch.object(settings, 'camera_sensing_enabled', False):
            self.camera.active = True
            # Scheduler tick closes active camera if privacy is disabled
            scheduler = CycleScheduler(self.camera, self.builder, self.engine, self.actuator)
            scheduler.running = True
            scheduler.phase = "INPUT_COLLECTION"
            scheduler._tick()

            self.assertFalse(self.camera.is_active())

    # -------------------------------------------------------------------------
    # 9. Camera OFF during adaptation
    # -------------------------------------------------------------------------
    def test_09_camera_off_during_adaptation(self):
        scheduler = CycleScheduler(self.camera, self.builder, self.engine, self.actuator)
        scheduler.running = True
        scheduler.phase = "ADAPTATION"
        self.camera.active = True

        scheduler._tick()
        self.assertFalse(self.camera.is_active())

    # -------------------------------------------------------------------------
    # 10. 60-second input window
    # -------------------------------------------------------------------------
    def test_10_60_second_input_window(self):
        scheduler = CycleScheduler(self.camera, self.builder, self.engine, self.actuator)
        slot_even = scheduler._compute_wall_clock_slot(t=120.0)  # Minute 2 (even) -> INPUT_COLLECTION

        self.assertEqual(slot_even['phase'], 'INPUT_COLLECTION')
        self.assertEqual(slot_even['block_seconds'], 60.0)
        self.assertEqual(slot_even['next_phase'], 'ADAPTATION')

    # -------------------------------------------------------------------------
    # 11. 60-second adaptation window
    # -------------------------------------------------------------------------
    def test_11_60_second_adaptation_window(self):
        scheduler = CycleScheduler(self.camera, self.builder, self.engine, self.actuator)
        slot_odd = scheduler._compute_wall_clock_slot(t=180.0)  # Minute 3 (odd) -> ADAPTATION

        self.assertEqual(slot_odd['phase'], 'ADAPTATION')
        self.assertEqual(slot_odd['block_seconds'], 60.0)
        self.assertEqual(slot_odd['next_phase'], 'INPUT_COLLECTION')

    # -------------------------------------------------------------------------
    # 12. Multimodal frustration
    # -------------------------------------------------------------------------
    def test_12_multimodal_frustration(self):
        # Backspace rate >= 0.10 + high mouse agitation + facial angry evidence
        cam_metrics = {
            'active': True,
            'camera_active_ratio': 1.0,
            'face_detection_confidence': 0.85,
            'camera_data_confidence': 0.85,
            'conditions': {'face_present': True},
            'facial_emotion_distribution': {'angry': 0.65, 'disgust': 0.10, 'neutral': 0.25},
            'facial_frustration': 0.72,
            'emotion_consistency': 0.85
        }
        res = self.builder.compute_multimodal_state(
            typing_rate=2.5,
            backspace_rate=0.18,
            rhythm_cv=0.85,
            typing_activity_ratio=0.8,
            mouse_active_ratio=0.7,
            jitter_score=0.40,
            click_rate=2.0,
            idle_seconds=0.0,
            camera_metrics=cam_metrics,
            context='CODING',
            context_conf=0.90,
            switch_rate=2.0,
            session_minutes=30.0
        )
        self.assertEqual(res['dominant_emotion'], 'Frustrated')
        self.assertGreater(res['emotion_probabilities']['Frustrated'], 0.40)
        self.assertGreater(res['evidence_signals']['frustration_signal'], 0.50)

    # -------------------------------------------------------------------------
    # 13. Multimodal fatigue
    # -------------------------------------------------------------------------
    def test_13_multimodal_fatigue(self):
        # Sluggish typing, low mouse activity, eye fatigue proxy, facial sad/neutral
        cam_metrics = {
            'active': True,
            'camera_active_ratio': 1.0,
            'face_detection_confidence': 0.80,
            'camera_data_confidence': 0.80,
            'conditions': {'face_present': True, 'persistent_low_eye_visibility': True},
            'fatigue_proxy': 0.80,
            'facial_fatigue': 0.75,
            'facial_emotion_distribution': {'sad': 0.60, 'neutral': 0.40},
            'emotion_consistency': 0.80
        }
        res = self.builder.compute_multimodal_state(
            typing_rate=0.2,
            backspace_rate=0.02,
            rhythm_cv=0.20,
            typing_activity_ratio=0.1,
            mouse_active_ratio=0.1,
            jitter_score=0.05,
            click_rate=0.1,
            idle_seconds=28.0,
            camera_metrics=cam_metrics,
            context='STUDYING',
            context_conf=0.85,
            switch_rate=0.5,
            session_minutes=75.0
        )
        self.assertEqual(res['dominant_emotion'], 'Fatigued')
        self.assertGreater(res['emotion_probabilities']['Fatigued'], 0.35)

    # -------------------------------------------------------------------------
    # 14. Focus
    # -------------------------------------------------------------------------
    def test_14_focus(self):
        # Steady typing, productive context (CODING), low errors, calm facial engagement
        cam_metrics = {
            'active': True,
            'face_detection_confidence': 0.85,
            'conditions': {'face_present': True},
            'facial_emotion_distribution': {'neutral': 0.75, 'happy': 0.20},
            'emotion_consistency': 0.85
        }
        res = self.builder.compute_multimodal_state(
            typing_rate=3.2,
            backspace_rate=0.02,
            rhythm_cv=0.15,
            typing_activity_ratio=0.85,
            mouse_active_ratio=0.6,
            jitter_score=0.08,
            click_rate=0.8,
            idle_seconds=0.0,
            camera_metrics=cam_metrics,
            context='CODING',
            context_conf=0.95,
            switch_rate=0.5,
            session_minutes=25.0
        )
        self.assertIn(res['dominant_emotion'], ['Focused', 'Flow State'])
        self.assertGreaterEqual(res['emotion_probabilities']['Focused'] + res['emotion_probabilities']['Flow State'], 0.50)

    # -------------------------------------------------------------------------
    # 15. Meeting safeguard
    # -------------------------------------------------------------------------
    def test_15_meeting_safeguard(self):
        # Even with frustration or workload during a meeting, audio must NEVER be muted
        state = {
            'context': {'canonical_context': 'MEETING', 'activity': 'MEETING', 'context_confidence': 0.95},
            'workload': {'score': 0.85},
            'emotion': {'dominant': 'Frustrated', 'probabilities': {'Frustrated': 0.70}},
            'inputs': {'keyboard': {'typing_rate': 4.0, 'backspace_rate': 0.20}, 'mouse': {'jitter': 0.45}}
        }
        dec = self.engine.decide(state)
        # Must NOT mute audio in a meeting!
        self.assertNotEqual(dec.action, 'MUTE_AUDIO')
        self.assertIn(dec.action, ['NO_ACTION', 'SUGGEST_BREAK'])

    # -------------------------------------------------------------------------
    # 16. Gaming safeguard
    # -------------------------------------------------------------------------
    def test_16_gaming_safeguard(self):
        state = {
            'context': {'canonical_context': 'GAMING', 'activity': 'GAMING', 'context_confidence': 0.95},
            'workload': {'score': 0.85},
            'emotion': {'dominant': 'Frustrated', 'probabilities': {'Frustrated': 0.70}},
            'inputs': {'keyboard': {'typing_rate': 4.0}, 'mouse': {'jitter': 0.50}}
        }
        dec = self.engine.decide(state)
        self.assertEqual(dec.action, 'NO_ACTION')
        self.assertIn('gaming', dec.reason.lower())

    # -------------------------------------------------------------------------
    # 17. NO_ACTION
    # -------------------------------------------------------------------------
    def test_17_no_action_when_nominal(self):
        state = {
            'context': {'canonical_context': 'CODING', 'activity': 'CODING', 'context_confidence': 0.85},
            'workload': {'score': 0.45},
            'emotion': {'dominant': 'Focused', 'probabilities': {'Focused': 0.40, 'Relaxed': 0.30}},
            'inputs': {'keyboard': {'typing_rate': 2.0, 'backspace_rate': 0.03}, 'mouse': {'jitter': 0.10}}
        }
        dec = self.engine.decide(state)
        self.assertEqual(dec.action, 'NO_ACTION')

    # -------------------------------------------------------------------------
    # 18. Actuator verification (Command success != State verification)
    # -------------------------------------------------------------------------
    @patch('app.services.actuator.run_shortcut')
    @patch.object(MacActuator, 'get_current_os_state')
    def test_18_actuator_verification(self, mock_get_state, mock_run_shortcut):
        mock_run_shortcut.return_value = True
        # Shortcut exited 0, but state remains Dark Mode = False!
        mock_get_state.side_effect = [
            {'dark_mode': False, 'volume': 50, 'audio_muted': False, 'brightness': 0.70, 'focus_mode_active': False},
            {'dark_mode': False, 'volume': 50, 'audio_muted': False, 'brightness': 0.70, 'focus_mode_active': False}
        ]
        res = self.actuator.execute('ENABLE_DARK_MODE')
        self.assertFalse(res['verified'])
        self.assertFalse(res['success'])
        self.assertEqual(res['status'], 'failed_verification')

    # -------------------------------------------------------------------------
    # 19. Exact audio restoration (Never hardcoded 50)
    # -------------------------------------------------------------------------
    @patch('app.services.actuator.run_shortcut')
    @patch.object(MacActuator, 'get_current_os_state')
    def test_19_exact_audio_restoration(self, mock_get_state, mock_run_shortcut):
        mock_run_shortcut.return_value = True
        # User volume is 73%
        mock_get_state.side_effect = [
            {'dark_mode': False, 'volume': 73, 'audio_muted': False, 'brightness': 0.70, 'focus_mode_active': False},
            {'dark_mode': False, 'volume': 0, 'audio_muted': True, 'brightness': 0.70, 'focus_mode_active': False}
        ]
        self.actuator.execute('MUTE_AUDIO')
        self.assertEqual(self.actuator.eaos_original_volume, 73)

        # Restore audio
        mock_get_state.side_effect = [
            {'dark_mode': False, 'volume': 0, 'audio_muted': True, 'brightness': 0.70, 'focus_mode_active': False},
            {'dark_mode': False, 'volume': 73, 'audio_muted': False, 'brightness': 0.70, 'focus_mode_active': False}
        ]
        res = self.actuator.execute('UNMUTE_AUDIO')
        # Must restore 73, NOT 50!
        mock_run_shortcut.assert_called_with('Set Volume', '73')
        self.assertTrue(res['verified'])

    # -------------------------------------------------------------------------
    # 20. Exact brightness restoration (Never fixed 0.65)
    # -------------------------------------------------------------------------
    @patch('app.services.actuator.run_shortcut')
    @patch.object(MacActuator, 'get_current_os_state')
    def test_20_exact_brightness_restoration(self, mock_get_state, mock_run_shortcut):
        mock_run_shortcut.return_value = True
        # User brightness is 0.82
        mock_get_state.side_effect = [
            {'dark_mode': False, 'volume': 50, 'audio_muted': False, 'brightness': 0.82, 'focus_mode_active': False},
            {'dark_mode': False, 'volume': 50, 'audio_muted': False, 'brightness': 0.70, 'focus_mode_active': False}
        ]
        self.actuator.execute('REDUCE_BRIGHTNESS')
        self.assertEqual(self.actuator.eaos_original_brightness, 0.82)

        # Restore brightness
        mock_get_state.side_effect = [
            {'dark_mode': False, 'volume': 50, 'audio_muted': False, 'brightness': 0.70, 'focus_mode_active': False},
            {'dark_mode': False, 'volume': 50, 'audio_muted': False, 'brightness': 0.82, 'focus_mode_active': False}
        ]
        res = self.actuator.execute('RESTORE_BRIGHTNESS')
        # Must restore 0.82, NOT fixed 0.65!
        mock_run_shortcut.assert_called_with('Set Brightness', '0.82')
        self.assertTrue(res['verified'])


if __name__ == '__main__':
    unittest.main()
