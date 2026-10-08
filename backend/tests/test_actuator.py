"""Unit tests for MacOSActuator (Parts 12 - 16 - OS Verification & Safe Restoration)."""
import unittest
from unittest.mock import patch
from app.services.actuator import MacActuator, MacOSActuator


class TestMacOSActuator(unittest.TestCase):
    def setUp(self):
        self.actuator = MacOSActuator()
        self.actuator.eaos_owned_volume = False
        self.actuator.eaos_original_volume = None
        self.actuator.eaos_owned_brightness = False
        self.actuator.eaos_original_brightness = None

    def test_no_action_verification(self):
        """Verify NO_ACTION returns verified nominal execution without modifying OS state."""
        res = self.actuator.execute('NO_ACTION')
        self.assertTrue(res['verified'])
        self.assertTrue(res['success'])
        self.assertEqual(res['status'], 'no_action')

    @patch('app.services.actuator.run_shortcut')
    @patch.object(MacActuator, 'get_current_os_state')
    def test_command_success_is_not_state_verification(self, mock_get_state, mock_run_shortcut):
        """Verify that shortcut returncode 0 does NOT equal verification if actual OS state did not change."""
        # Shortcut command runs successfully
        mock_run_shortcut.return_value = True
        # But actual macOS state remains Dark Mode = False before AND after
        mock_get_state.side_effect = [
            {'dark_mode': False, 'volume': 60, 'audio_muted': False, 'brightness': 0.70, 'focus_mode_active': False},
            {'dark_mode': False, 'volume': 60, 'audio_muted': False, 'brightness': 0.70, 'focus_mode_active': False}
        ]

        res = self.actuator.execute('ENABLE_DARK_MODE')
        # Even though command succeeded, verified must be False because state is still False!
        self.assertFalse(res['verified'])
        self.assertFalse(res['success'])
        self.assertEqual(res['status'], 'failed_verification')

    @patch('app.services.actuator.run_shortcut')
    @patch.object(MacActuator, 'get_current_os_state')
    def test_dark_mode_verified_when_state_matches(self, mock_get_state, mock_run_shortcut):
        """Verify dark mode reports success and verified=True only when OS state actually becomes True."""
        mock_run_shortcut.return_value = True
        mock_get_state.side_effect = [
            {'dark_mode': False, 'volume': 60, 'audio_muted': False, 'brightness': 0.70, 'focus_mode_active': False},
            {'dark_mode': True, 'volume': 60, 'audio_muted': False, 'brightness': 0.70, 'focus_mode_active': False}
        ]

        res = self.actuator.execute('ENABLE_DARK_MODE')
        self.assertTrue(res['verified'])
        self.assertTrue(res['success'])
        self.assertEqual(res['status'], 'executed')

    @patch('app.services.actuator.run_shortcut')
    @patch.object(MacActuator, 'get_current_os_state')
    def test_volume_preserves_and_restores_original_value(self, mock_get_state, mock_run_shortcut):
        """Verify audio mute preserves original volume (e.g. 73) and restoration restores 73, NOT 50."""
        mock_run_shortcut.return_value = True
        # Step 1: Mute audio when user original volume is 73
        mock_get_state.side_effect = [
            {'dark_mode': False, 'volume': 73, 'audio_muted': False, 'brightness': 0.70, 'focus_mode_active': False},
            {'dark_mode': False, 'volume': 0, 'audio_muted': True, 'brightness': 0.70, 'focus_mode_active': False}
        ]

        res_mute = self.actuator.execute('MUTE_AUDIO')
        self.assertEqual(self.actuator.eaos_original_volume, 73)
        self.assertTrue(self.actuator.eaos_owned_volume)
        mock_run_shortcut.assert_called_with('Set Volume', '0')

        # Step 2: Unmute/Restore audio
        mock_get_state.side_effect = [
            {'dark_mode': False, 'volume': 0, 'audio_muted': True, 'brightness': 0.70, 'focus_mode_active': False},
            {'dark_mode': False, 'volume': 73, 'audio_muted': False, 'brightness': 0.70, 'focus_mode_active': False}
        ]

        res_unmute = self.actuator.execute('UNMUTE_AUDIO')
        # Shortcut MUST be called with '73', NEVER '50'
        mock_run_shortcut.assert_called_with('Set Volume', '73')
        self.assertEqual(res_unmute['status'], 'executed')

    @patch('app.services.actuator.run_shortcut')
    @patch.object(MacActuator, 'get_current_os_state')
    def test_brightness_relative_reduction_and_exact_restoration(self, mock_get_state, mock_run_shortcut):
        """Verify relative brightness reduction and exact restoration of original brightness, NOT fixed 0.65."""
        mock_run_shortcut.return_value = True
        # Initial brightness: 0.80
        mock_get_state.side_effect = [
            {'dark_mode': False, 'volume': 50, 'audio_muted': False, 'brightness': 0.80, 'focus_mode_active': False},
            {'dark_mode': False, 'volume': 50, 'audio_muted': False, 'brightness': 0.68, 'focus_mode_active': False}
        ]

        # Normal fatigue: 0.80 * 0.85 = 0.68
        res_reduce = self.actuator.execute('REDUCE_BRIGHTNESS')
        self.assertEqual(self.actuator.eaos_original_brightness, 0.80)
        mock_run_shortcut.assert_called_with('Set Brightness', '0.68')
        self.assertTrue(self.actuator.eaos_owned_brightness)

        # Recovery restoration: restores exact 0.80, NOT 0.65
        mock_get_state.side_effect = [
            {'dark_mode': False, 'volume': 50, 'audio_muted': False, 'brightness': 0.68, 'focus_mode_active': False},
            {'dark_mode': False, 'volume': 50, 'audio_muted': False, 'brightness': 0.80, 'focus_mode_active': False}
        ]
        res_restore = self.actuator.execute('RESTORE_BRIGHTNESS')
        mock_run_shortcut.assert_called_with('Set Brightness', '0.80')
        self.assertEqual(res_restore['status'], 'executed')


if __name__ == '__main__':
    unittest.main()
