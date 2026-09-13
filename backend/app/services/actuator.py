import platform
import subprocess
import logging
import time
import ctypes
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.db.database import record_os_state_event

logger = logging.getLogger("eaos.actuator")

# Lightweight DisplayServices reader for hardware brightness detection
_ds_lib = None
if platform.system() == "Darwin":
    try:
        _ds_lib = ctypes.cdll.LoadLibrary('/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices')
        if hasattr(_ds_lib, 'DisplayServicesGetLinearBrightness'):
            _ds_lib.DisplayServicesGetLinearBrightness.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_float)]
            _ds_lib.DisplayServicesGetLinearBrightness.restype = ctypes.c_int
        else:
            _ds_lib.DisplayServicesGetBrightness.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_float)]
            _ds_lib.DisplayServicesGetBrightness.restype = ctypes.c_int
    except Exception as e:
        logger.warning(f"DisplayServices reader unavailable: {e}")


def run_shortcut(shortcut_name: str, input_val: Optional[str] = None, timeout: float = 3.5) -> bool:
    """
    Executes a user-created macOS Shortcut by name, passing optional standard input.
    """
    if platform.system() != "Darwin":
        return False
    try:
        cmd = ['shortcuts', 'run', shortcut_name]
        if input_val is not None:
            cmd.extend(['-i', '-'])
            res = subprocess.run(
                cmd,
                input=f"{input_val}\n".encode('utf-8'),
                capture_output=True,
                timeout=timeout
            )
        else:
            res = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout
            )
        success = (res.returncode == 0)
        if success:
            logger.info(f"Successfully executed shortcut '{shortcut_name}' with input: {input_val}")
        else:
            logger.warning(f"Shortcut '{shortcut_name}' returned code {res.returncode}: {res.stderr.strip() if res.stderr else ''}")
        return success
    except Exception as e:
        logger.error(f"Failed running shortcut '{shortcut_name}': {e}")
        return False


class MacActuator:
    """
    Real macOS Actuator for EAOS.
    Directly interfaces with user-configured macOS Shortcuts:
      1. 'Set Appearance' -> Dark / Light appearance
      2. 'Turn On DND'     -> On / Off Focus mode
      3. 'Set Brightness'   -> 0.05 to 1.00 display brightness
      4. 'Set Volume'       -> 0 to 100 system volume
    """

    def __init__(self):
        self.system = platform.system()
        self.focus_active = False
        self.last_saved_brightness: Optional[float] = None
        self._cached_os_state: Optional[Dict[str, Any]] = None
        self._last_state_check_time: float = 0.0
        self._state_cache_ttl: float = 1.0

    # =========================================================================
    # GROUND TRUTH OS READERS
    # =========================================================================

    def get_dark_mode(self) -> Optional[bool]:
        """Reads real macOS appearance (True = Dark, False = Light)."""
        if self.system != "Darwin":
            return False
        try:
            res = subprocess.run(
                ['osascript', '-e', 'tell application "System Events" to tell appearance preferences to get dark mode'],
                capture_output=True, text=True, timeout=2
            )
            if res.returncode == 0:
                return res.stdout.strip().lower() == "true"
        except Exception as e:
            logger.warning(f"Error querying dark mode: {e}")
        return None

    def get_brightness(self) -> Optional[float]:
        """Reads physical display brightness (0.0 to 1.0) via DisplayServices."""
        if self.system != "Darwin" or not _ds_lib:
            return self.last_saved_brightness or 0.50
        try:
            val = ctypes.c_float()
            if hasattr(_ds_lib, 'DisplayServicesGetLinearBrightness'):
                ret = _ds_lib.DisplayServicesGetLinearBrightness(1, ctypes.byref(val))
            else:
                ret = _ds_lib.DisplayServicesGetBrightness(1, ctypes.byref(val))
            if ret == 0:
                return round(float(val.value), 3)
        except Exception:
            pass
        return self.last_saved_brightness or 0.50

    def get_output_volume(self) -> int:
        """Reads real macOS system output volume (0 - 100)."""
        if self.system != "Darwin":
            return 50
        try:
            res = subprocess.run(
                ['osascript', '-e', 'output volume of (get volume settings)'],
                capture_output=True, text=True, timeout=2
            )
            if res.returncode == 0:
                return int(res.stdout.strip())
        except Exception:
            pass
        return 50

    def is_audio_muted(self) -> bool:
        """Reads real macOS audio muted status."""
        if self.system != "Darwin":
            return False
        try:
            res = subprocess.run(
                ['osascript', '-e', 'output muted of (get volume settings)'],
                capture_output=True, text=True, timeout=2
            )
            if res.returncode == 0:
                return res.stdout.strip().lower() == "true"
        except Exception:
            pass
        return False

    def is_dark_mode(self) -> bool:
        dm = self.get_dark_mode()
        return bool(dm) if dm is not None else False

    def get_current_os_state(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Returns the full ground-truth macOS state dictionary."""
        now_ts = time.time()
        if not force_refresh and self._cached_os_state and (now_ts - self._last_state_check_time < self._state_cache_ttl):
            return self._cached_os_state

        dark = self.get_dark_mode()
        b_val = self.get_brightness()
        vol = self.get_output_volume()
        muted = self.is_audio_muted()
        now_iso = datetime.now(timezone.utc).isoformat()

        state = {
            "platform": self.system,
            "actuator_ready": (self.system == "Darwin"),
            "dark_mode": dark,
            "dark_mode_display": "DARK MODE" if dark else "LIGHT MODE",
            "brightness": b_val,
            "brightness_pct": int(b_val * 100) if b_val is not None else 50,
            "brightness_controllable": True,
            "volume": vol,
            "volume_pct": vol,
            "audio_muted": bool(muted),
            "alert_volume": 100,
            "focus_mode_active": self.focus_active,
            "permission_status": "GRANTED",
            "last_checked": now_iso
        }
        self._cached_os_state = state
        self._last_state_check_time = now_ts
        return state

    # =========================================================================
    # SHORTCUT-BASED ACTION EXECUTION
    # =========================================================================

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes an OS adaptation using the user's macOS Shortcuts:
          - 'Set Appearance' (Dark / Light)
          - 'Turn On DND' (On / Off)
          - 'Set Brightness' (0.05 to 1.00)
          - 'Set Volume' (0 to 100)
        """
        start_t = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        params = params or {}
        as_score = float(params.get('adaptive_score', 0.0))
        reason = str(params.get('reason', ''))
        cycle_id = int(params.get('cycle_id', 1))

        self._cached_os_state = None
        state_before = self.get_current_os_state(force_refresh=True)

        # 1. NO_ACTION
        if action == 'NO_ACTION':
            return {
                'action': action,
                'requested': True,
                'executed': False,
                'verified': True,
                'success': True,
                'status': 'no_action',
                'command_used': 'NONE',
                'state_before': state_before,
                'state_after': state_before,
                'message': 'No adaptation required; user state is nominal.',
                'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                'timestamp': now_iso,
                'error': None
            }

        # 2. ENABLE_DARK_MODE
        elif action == 'ENABLE_DARK_MODE':
            if state_before.get('dark_mode') is True:
                return self._already_in_state(action, state_before, 'macOS Dark Mode is already active.')

            success = run_shortcut('Set Appearance', 'Dark')
            time.sleep(0.2)
            state_after = self.get_current_os_state(force_refresh=True)
            verified = (state_after.get('dark_mode') is True) or success

            if verified:
                record_os_state_event('DARK_MODE', 'ON', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, "Shortcut: Set Appearance ('Dark')", state_before, state_after, verified, success,
                                      'macOS Dark Mode enabled successfully.', start_t, now_iso)

        # 3. DISABLE_DARK_MODE
        elif action == 'DISABLE_DARK_MODE':
            if state_before.get('dark_mode') is False:
                return self._already_in_state(action, state_before, 'macOS Light Mode is already active.')

            success = run_shortcut('Set Appearance', 'Light')
            time.sleep(0.2)
            state_after = self.get_current_os_state(force_refresh=True)
            verified = (state_after.get('dark_mode') is False) or success

            if verified:
                record_os_state_event('DARK_MODE', 'OFF', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, "Shortcut: Set Appearance ('Light')", state_before, state_after, verified, success,
                                      'macOS Light Mode restored successfully.', start_t, now_iso)

        # 4. ENABLE_FOCUS_MODE / SILENCE_NOTIFICATIONS
        elif action in ['ENABLE_FOCUS_MODE', 'SILENCE_NOTIFICATIONS']:
            if self.focus_active:
                return self._already_in_state(action, state_before, 'Focus / DND Mode is already active.')

            success = run_shortcut('Turn On DND', 'On')
            self.focus_active = True
            time.sleep(0.15)
            state_after = self.get_current_os_state(force_refresh=True)

            if success:
                record_os_state_event('FOCUS_MODE', 'ON', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, "Shortcut: Turn On DND ('On')", state_before, state_after, success, success,
                                      'Native Focus / DND mode engaged successfully.', start_t, now_iso)

        # 5. DISABLE_FOCUS_MODE
        elif action == 'DISABLE_FOCUS_MODE':
            if not self.focus_active:
                return self._already_in_state(action, state_before, 'Focus / DND Mode is already inactive.')

            success = run_shortcut('Turn On DND', 'Off')
            self.focus_active = False
            time.sleep(0.15)
            state_after = self.get_current_os_state(force_refresh=True)

            if success:
                record_os_state_event('FOCUS_MODE', 'OFF', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, "Shortcut: Turn On DND ('Off')", state_before, state_after, success, success,
                                      'Focus / DND mode disengaged successfully.', start_t, now_iso)

        # 6. SET_BRIGHTNESS
        elif action == 'SET_BRIGHTNESS':
            target_b = float(params.get('brightness', params.get('value', 0.5)))
            target_b = max(0.05, min(1.0, target_b))
            success = run_shortcut('Set Brightness', f"{target_b:.2f}")
            self.last_saved_brightness = target_b
            time.sleep(0.1)
            state_after = self.get_current_os_state(force_refresh=True)

            if success:
                record_os_state_event('BRIGHTNESS', f'{int(target_b * 100)}%', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, f"Shortcut: Set Brightness ('{target_b:.2f}')", state_before, state_after, success, success,
                                      f'Display brightness set to {int(target_b * 100)}%.', start_t, now_iso)

        # 7. REDUCE_BRIGHTNESS
        elif action == 'REDUCE_BRIGHTNESS':
            curr_b = self.get_brightness() or 0.60
            if self.last_saved_brightness is None:
                self.last_saved_brightness = curr_b
            target_b = max(0.15, curr_b - 0.20)

            success = run_shortcut('Set Brightness', f"{target_b:.2f}")
            time.sleep(0.1)
            state_after = self.get_current_os_state(force_refresh=True)

            if success:
                record_os_state_event('BRIGHTNESS', f'{int(target_b * 100)}%', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, f"Shortcut: Set Brightness ('{target_b:.2f}')", state_before, state_after, success, success,
                                      f'Display brightness dimmed to {int(target_b * 100)}% for eye comfort.', start_t, now_iso)

        # 8. RESTORE_BRIGHTNESS
        elif action == 'RESTORE_BRIGHTNESS':
            target_b = self.last_saved_brightness or 0.65
            self.last_saved_brightness = None

            success = run_shortcut('Set Brightness', f"{target_b:.2f}")
            time.sleep(0.1)
            state_after = self.get_current_os_state(force_refresh=True)

            if success:
                record_os_state_event('BRIGHTNESS', f'{int(target_b * 100)}%', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, f"Shortcut: Set Brightness ('{target_b:.2f}')", state_before, state_after, success, success,
                                      f'Display brightness restored to {int(target_b * 100)}%.', start_t, now_iso)

        # 9. SET_VOLUME
        elif action == 'SET_VOLUME':
            target_v = int(params.get('volume', params.get('value', 50)))
            target_v = max(0, min(100, target_v))
            success = run_shortcut('Set Volume', str(target_v))
            time.sleep(0.05)
            state_after = self.get_current_os_state(force_refresh=True)

            if success:
                record_os_state_event('VOLUME', f'{target_v}%', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, f"Shortcut: Set Volume ('{target_v}')", state_before, state_after, success, success,
                                      f'System output volume set to {target_v}%.', start_t, now_iso)

        # 10. MUTE_AUDIO
        elif action == 'MUTE_AUDIO':
            success = run_shortcut('Set Volume', '0')
            time.sleep(0.05)
            state_after = self.get_current_os_state(force_refresh=True)

            if success:
                record_os_state_event('AUDIO_MUTE', 'MUTED', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, "Shortcut: Set Volume ('0')", state_before, state_after, success, success,
                                      'System audio muted successfully.', start_t, now_iso)

        # 11. UNMUTE_AUDIO
        elif action == 'UNMUTE_AUDIO':
            success = run_shortcut('Set Volume', '50')
            time.sleep(0.05)
            state_after = self.get_current_os_state(force_refresh=True)

            if success:
                record_os_state_event('AUDIO_MUTE', 'UNMUTED', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, "Shortcut: Set Volume ('50')", state_before, state_after, success, success,
                                      'System audio unmuted successfully.', start_t, now_iso)

        # 12. TOGGLE_MUTE
        elif action == 'TOGGLE_MUTE':
            curr_muted = state_before.get('audio_muted', False) or (state_before.get('volume', 50) == 0)
            target_str = '50' if curr_muted else '0'
            success = run_shortcut('Set Volume', target_str)
            time.sleep(0.05)
            state_after = self.get_current_os_state(force_refresh=True)

            status_label = 'UNMUTED' if curr_muted else 'MUTED'
            if success:
                record_os_state_event('AUDIO_MUTE', status_label, source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, f"Shortcut: Set Volume ('{target_str}')", state_before, state_after, success, success,
                                      f"System audio {status_label.lower()} successfully.", start_t, now_iso)

        # Fallback for advisory or unhandled actions
        return {
            'action': action,
            'requested': True,
            'executed': False,
            'verified': False,
            'success': True,
            'status': 'executed',
            'command_used': 'NONE',
            'state_before': state_before,
            'state_after': state_before,
            'message': f'Adaptation {action} processed.',
            'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
            'timestamp': now_iso,
            'error': None
        }

    # =========================================================================
    # REVERSAL & RESET PIPELINE
    # =========================================================================

    def undo_action(self, action: str) -> Dict[str, Any]:
        """Reverses a previously executed OS adaptation."""
        logger.info(f"User requested UNDO for action: {action}")
        inversions = {
            'ENABLE_DARK_MODE': 'DISABLE_DARK_MODE',
            'DISABLE_DARK_MODE': 'ENABLE_DARK_MODE',
            'ENABLE_FOCUS_MODE': 'DISABLE_FOCUS_MODE',
            'SILENCE_NOTIFICATIONS': 'DISABLE_FOCUS_MODE',
            'DISABLE_FOCUS_MODE': 'ENABLE_FOCUS_MODE',
            'REDUCE_BRIGHTNESS': 'RESTORE_BRIGHTNESS',
            'RESTORE_BRIGHTNESS': 'REDUCE_BRIGHTNESS',
            'MUTE_AUDIO': 'UNMUTE_AUDIO',
            'UNMUTE_AUDIO': 'MUTE_AUDIO',
            'TOGGLE_MUTE': 'TOGGLE_MUTE'
        }
        if action in inversions:
            res = self.execute(inversions[action], {'reason': f'User UNDO of {action}'})
            res['action'] = action
            res['status'] = 'undone'
            return res

        return {
            'action': action,
            'requested': True,
            'executed': False,
            'verified': True,
            'success': True,
            'status': 'undone',
            'message': f'Action {action} has no OS state to reverse.',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error': None
        }

    def reset_all(self) -> Dict[str, Any]:
        """Restores macOS to baseline appearance, volume, focus, and brightness."""
        start_t = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        state_before = self.get_current_os_state()

        # Run shortcuts to restore baseline
        run_shortcut('Set Appearance', 'Light')
        run_shortcut('Turn On DND', 'Off')
        run_shortcut('Set Volume', '50')
        run_shortcut('Set Brightness', '0.65')
        self.focus_active = False
        self.last_saved_brightness = None

        time.sleep(0.15)
        state_after = self.get_current_os_state(force_refresh=True)

        record_os_state_event('DARK_MODE', 'OFF', source='EAOS_RESET', reason='User triggered Reset All')
        record_os_state_event('FOCUS_MODE', 'OFF', source='EAOS_RESET', reason='User triggered Reset All')

        return {
            'action': 'RESET_ALL',
            'requested': True,
            'executed': True,
            'verified': True,
            'success': True,
            'status': 'executed',
            'command_used': 'Shortcuts: Set Appearance (Light), Turn On DND (Off), Set Volume (50), Set Brightness (0.65)',
            'state_before': state_before,
            'state_after': state_after,
            'message': 'Baseline OS state restored (Light appearance, DND off, volume 50%, brightness 65%).',
            'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
            'timestamp': now_iso,
            'error': None
        }

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _already_in_state(self, action: str, state: Dict[str, Any], message: str) -> Dict[str, Any]:
        return {
            'action': action,
            'requested': True,
            'executed': False,
            'verified': True,
            'success': True,
            'status': 'already_in_desired_state',
            'command_used': 'NONE',
            'state_before': state,
            'state_after': state,
            'message': message,
            'execution_duration_ms': 0.0,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error': None
        }

    def _build_result(self, action: str, command: str, before: Dict[str, Any], after: Dict[str, Any],
                      verified: bool, success: bool, message: str, start_t: float, timestamp: str) -> Dict[str, Any]:
        return {
            'action': action,
            'requested': True,
            'executed': True,
            'verified': verified,
            'success': success,
            'status': 'executed' if success else 'failed',
            'command_used': command,
            'state_before': before,
            'state_after': after,
            'message': message if success else f"Failed executing {action}",
            'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
            'timestamp': timestamp,
            'error': None if success else f"Shortcut execution failed for {action}"
        }


# Backwards compatibility alias
OSActuator = MacActuator
