"""Unit tests for CycleScheduler (Part 11 - Two-Minute Cycle Architecture)."""
import unittest
from unittest.mock import MagicMock, patch
from app.services.scheduler import CycleScheduler, InputObservationWindow
from app.core.config import settings


class TestCycleScheduler(unittest.TestCase):
    def setUp(self):
        self.mock_camera = MagicMock()
        self.mock_builder = MagicMock()
        self.mock_engine = MagicMock()
        self.mock_actuator = MagicMock()

        self.scheduler = CycleScheduler(
            camera_sensor=self.mock_camera,
            state_builder=self.mock_builder,
            decision_engine=self.mock_engine,
            os_actuator=self.mock_actuator
        )

    def test_wall_clock_two_minute_cycle_slots(self):
        """Verify 60s INPUT_COLLECTION + 60s ADAPTATION = 120s continuous 2-minute cycle."""
        block_sec = float(settings.get_effective_cycle_seconds())
        self.assertEqual(block_sec, 60.0)

        # Slot at t = 120.0 (even minute slot: 2.0 min)
        slot_even = self.scheduler._compute_wall_clock_slot(t=120.0)
        self.assertEqual(slot_even['phase'], 'INPUT_COLLECTION')
        self.assertEqual(slot_even['block_seconds'], 60.0)
        self.assertAlmostEqual(slot_even['remaining_seconds'], 60.0, places=1)

        # Slot at t = 180.0 (odd minute slot: 3.0 min)
        slot_odd = self.scheduler._compute_wall_clock_slot(t=180.0)
        self.assertEqual(slot_odd['phase'], 'ADAPTATION')
        self.assertEqual(slot_odd['block_seconds'], 60.0)
        self.assertAlmostEqual(slot_odd['remaining_seconds'], 60.0, places=1)

        # Total 2-slot cycle = 120s
        self.assertEqual(slot_even['block_seconds'] + slot_odd['block_seconds'], 120.0)

    @patch('app.services.scheduler.update_decision_notification')
    @patch('app.services.scheduler.notification_service')
    @patch('app.services.scheduler.record_cycle')
    @patch('app.services.scheduler.insert_decision')
    def test_transition_to_adaptation_closes_camera_and_makes_one_decision(self, mock_ins_dec, mock_rec_cyc, mock_notif, mock_upd_notif):
        """Verify camera is closed upon entering ADAPTATION, exactly one decision made, and state is frozen."""
        self.scheduler.phase = 'INPUT_COLLECTION'
        self.scheduler.current_window = InputObservationWindow(cycle_id=1, start_time=0.0, duration_seconds=60.0)

        mock_ins_dec.return_value = 101
        mock_rec_cyc.return_value = 201
        mock_notif.send_adaptation_notification.return_value = {'status': 'delivered'}

        # Setup mock return values
        self.mock_builder.build_aggregated_cycle_state.return_value = {
            'emotion': {'dominant': 'Frustrated', 'probabilities': {'Frustrated': 0.70}, 'confidence': 0.70, 'evidence_signals': {}},
            'context': {'active_app': 'Code', 'dominant_activity': 'CODING', 'context_confidence': 0.90},
            'workload': {'score': 0.65, 'level': 'High'},
            'inputs': {'camera': {}, 'keyboard': {}, 'mouse': {}, 'active_app': 'Code'}
        }
        self.mock_engine.calculate_as.return_value = (0.72, {'emotion': 0.7, 'context': 0.2, 'workload': 0.6, 'personalization': 0.5})
        self.mock_engine.decide.return_value = MagicMock(
            action='MUTE_AUDIO',
            reason='Elevated typing correction indicated frustration.',
            confidence=0.88,
            policy='Baseline Rules',
            adaptive_score=0.72,
            explanation={'action': 'MUTE_AUDIO'},
            supporting_signals={},
            context_confidence=0.90,
            personalization_summary=None
        )
        self.mock_actuator.execute.return_value = {
            'action': 'MUTE_AUDIO',
            'verified': True,
            'success': True,
            'status': 'executed',
            'state_before': {'volume': 70},
            'state_after': {'volume': 0}
        }
        self.mock_actuator.get_current_os_state.return_value = {'volume': 70}

        self.scheduler._transition_to_adaptation()

        # 1. Camera MUST be closed during ADAPTATION
        self.mock_camera.close_camera.assert_called()

        # 2. Decision engine decide() called exactly once
        self.assertEqual(self.mock_engine.decide.call_count, 1)

        # 3. Actuator execute() called exactly once with the selected action
        self.assertEqual(self.mock_actuator.execute.call_count, 1)
        self.assertEqual(self.mock_actuator.execute.call_args[0][0], 'MUTE_AUDIO')

        # 4. State is frozen throughout ADAPTATION phase
        self.assertEqual(self.scheduler.phase, 'ADAPTATION')
        self.assertIsNotNone(self.scheduler.frozen_decision)
        self.assertEqual(self.scheduler.frozen_decision['action'], 'MUTE_AUDIO')

    @patch('app.services.scheduler.update_cycle_phase')
    def test_transition_to_input_collection_reopens_camera(self, mock_update_phase):
        """Verify camera is reopened and fresh observation window created on transition to INPUT_COLLECTION."""
        self.scheduler.phase = 'ADAPTATION'

        self.scheduler._transition_to_input_collection()

        self.assertEqual(self.scheduler.phase, 'INPUT_COLLECTION')
        self.mock_camera.open_camera.assert_called()
        self.assertIsNotNone(self.scheduler.current_window)


if __name__ == '__main__':
    unittest.main()
