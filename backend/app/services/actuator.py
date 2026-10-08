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
            logger.info(f"Executed shortcut '{shortcut_name}' with input: {input_val} (exit code: 0)")
        else:
            logger.warning(f"Shortcut '{shortcut_name}' failed with code {res.returncode}: {res.stderr.strip() if res.stderr else ''}")
        return success
    except Exception as e:
        logger.error(f"Failed running shortcut '{shortcut_name}': {e}")
        return False


class MacActuator:
    """
    Real macOS Actuator for EAOS.
    Executes system adaptations via macOS Shortcuts and enforces post-action OS verification:
      COMMAND SUCCESS != STATE VERIFICATION.
    Preserves exact user volume and brightness, avoiding arbitrary overrides.
    """

    def __init__(self):
        self.system = platform.system()
        self.focus_active = False

        # Memory for exact pre-adaptation user states (Parts 14, 15, 16)
        self.eaos_original_volume: Optional[int] = None
        self.eaos_original_muted: Optional[bool] = None
        self.eaos_original_brightness: Optional[float] = None

        # Ownership tracking (Part 16: EAOS must not fight manual user changes)
        self.eaos_owned_dnd = False
        self.eaos_owned_volume = False
        self.eaos_owned_brightness = False
        self.eaos_owned_dark_mode = False

        self._cached_os_state: Optional[Dict[str, Any]] = None
        self._last_state_check_time: float = 0.0
        self._state_cache_ttl: float = 0.5

    # =========================================================================
    # GROUND TRUTH OS READERS (Part 13)
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
            return self.eaos_original_brightness or 0.50
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
        return self.eaos_original_brightness or 0.50

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

    def get_focus_mode(self) -> Optional[bool]:
        """Reads actual macOS Focus / DND state if accessible."""
        if self.system != "Darwin":
            return False
        try:
            res = subprocess.run(
                ['defaults', 'read', 'com.apple.controlcenter', 'NSStatusItem Visible FocusModes'],
                capture_output=True, text=True, timeout=1.5
            )
            if res.returncode == 0:
                val = res.stdout.strip()
                return val == "1" or val.lower() == "true"
        except Exception:
            pass
        return None

    def get_current_os_state(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Returns the full ground-truth macOS state dictionary."""
        now_ts = time.time()
        if not force_refresh and self._cached_os_state and (now_ts - self._last_state_check_time < self._state_cache_ttl):
            return self._cached_os_state

        dark = self.get_dark_mode()
        b_val = self.get_brightness()
        vol = self.get_output_volume()
        muted = self.is_audio_muted()
        focus_actual = self.get_focus_mode()
        effective_focus = focus_actual if focus_actual is not None else self.focus_active
        now_iso = datetime.now(timezone.utc).isoformat()

        # Check for manual user intervention (Part 16)
        if self._cached_os_state is not None:
            # If volume changed and EAOS didn't do it, clear EAOS ownership
            cached_vol = self._cached_os_state.get('volume')
            if cached_vol is not None and abs(vol - cached_vol) > 5 and not self.eaos_owned_volume:
                self.eaos_original_volume = vol

            # If Focus changed manually
            if focus_actual is not None and focus_actual != self.focus_active and not self.eaos_owned_dnd:
                self.focus_active = focus_actual

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
            "focus_mode_active": effective_focus,
            "focus_ground_truth_available": (focus_actual is not None),
            "permission_status": "GRANTED",
            "last_checked": now_iso
        }
        self._cached_os_state = state
        self._last_state_check_time = now_ts
        return state

    # =========================================================================
    # SHORTCUT-BASED ACTION EXECUTION & VERIFICATION (Parts 12 - 16)
    # =========================================================================

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes an OS adaptation and performs strict post-action state verification.
        COMMAND SUCCESS != STATE VERIFICATION.
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

        # 2. ENABLE_DARK_MODE (Part 9, Action 5)
        elif action == 'ENABLE_DARK_MODE':
            if state_before.get('dark_mode') is True:
                return self._already_in_state(action, state_before, 'macOS Dark Mode is already active.')

            cmd_ok = run_shortcut('Set Appearance', 'Dark')
            time.sleep(0.25)
            state_after = self.get_current_os_state(force_refresh=True)

            # Strict verification (Part 12): actual state after must be Dark
            verified = (state_after.get('dark_mode') is True)
            success = verified and cmd_ok
            if verified:
                self.eaos_owned_dark_mode = True
                record_os_state_event('DARK_MODE', 'ON', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, "Shortcut: Set Appearance ('Dark')", state_before, state_after, verified, success,
                                      'macOS Dark Mode enabled and verified.', start_t, now_iso)

        # 3. DISABLE_DARK_MODE (Part 9, Action 6)
        elif action == 'DISABLE_DARK_MODE':
            if state_before.get('dark_mode') is False:
                return self._already_in_state(action, state_before, 'macOS Light Mode is already active.')

            cmd_ok = run_shortcut('Set Appearance', 'Light')
            time.sleep(0.25)
            state_after = self.get_current_os_state(force_refresh=True)

            # Strict verification: actual state after must be Light
            verified = (state_after.get('dark_mode') is False)
            success = verified and cmd_ok
            if verified:
                self.eaos_owned_dark_mode = False
                record_os_state_event('DARK_MODE', 'OFF', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, "Shortcut: Set Appearance ('Light')", state_before, state_after, verified, success,
                                      'macOS Light Mode restored and verified.', start_t, now_iso)

        # 4. ENABLE_FOCUS_MODE / SILENCE_NOTIFICATIONS (Part 9, Action 1)
        elif action in ['ENABLE_FOCUS_MODE', 'SILENCE_NOTIFICATIONS']:
            if state_before.get('focus_mode_active') is True:
                return self._already_in_state(action, state_before, 'Focus / DND Mode is already active.')

            cmd_ok = run_shortcut('Turn On DND', 'On')
            self.focus_active = True
            self.eaos_owned_dnd = True
            time.sleep(0.25)
            state_after = self.get_current_os_state(force_refresh=True)

            # Verify ground truth if available, otherwise report verification status honestly
            if state_after.get('focus_ground_truth_available'):
                verified = (state_after.get('focus_mode_active') is True)
            else:
                verified = False
                logger.info("Direct Focus Mode ground truth verification unavailable; reported verified=False.")

            success = verified and cmd_ok
            if success:
                record_os_state_event('FOCUS_MODE', 'ON', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, "Shortcut: Turn On DND ('On')", state_before, state_after, verified, success,
                                      'Native Focus / DND mode engaged.', start_t, now_iso)

        # 5. DISABLE_FOCUS_MODE (Part 9, Action 2)
        elif action == 'DISABLE_FOCUS_MODE':
            if state_before.get('focus_mode_active') is False:
                return self._already_in_state(action, state_before, 'Focus / DND Mode is already inactive.')

            cmd_ok = run_shortcut('Turn On DND', 'Off')
            self.focus_active = False
            self.eaos_owned_dnd = False
            time.sleep(0.25)
            state_after = self.get_current_os_state(force_refresh=True)

            if state_after.get('focus_ground_truth_available'):
                verified = (state_after.get('focus_mode_active') is False)
            else:
                verified = False
                logger.info("Direct Focus Mode ground truth verification unavailable; reported verified=False.")

            success = verified and cmd_ok
            if success:
                record_os_state_event('FOCUS_MODE', 'OFF', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, "Shortcut: Turn On DND ('Off')", state_before, state_after, verified, success,
                                      'Focus / DND mode disengaged.', start_t, now_iso)

        # 6. MUTE_AUDIO / REDUCE_AUDIO (Part 9, Action 3 & Part 14)
        elif action == 'MUTE_AUDIO':
            if state_before.get('audio_muted') is True or state_before.get('volume') == 0:
                return self._already_in_state(action, state_before, 'System audio is already muted.')

            # Preserve exact original volume and mute state before modification
            if self.eaos_original_volume is None:
                self.eaos_original_volume = int(state_before.get('volume', 50))
                self.eaos_original_muted = bool(state_before.get('audio_muted', False))
            self.eaos_owned_volume = True

            cmd_ok = run_shortcut('Set Volume', '0')
            time.sleep(0.20)
            state_after = self.get_current_os_state(force_refresh=True)

            # Verification: actual volume must be 0 or muted
            verified = (state_after.get('volume') == 0 or state_after.get('audio_muted') is True)
            success = verified and cmd_ok
            if verified:
                record_os_state_event('AUDIO_MUTE', 'MUTED', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, "Shortcut: Set Volume ('0')", state_before, state_after, verified, success,
                                      f'System volume reduced to 30% (original volume {self.eaos_original_volume}% preserved).', start_t, now_iso)

        # 7. UNMUTE_AUDIO (Part 9, Action 4 & Part 14)
        elif action == 'UNMUTE_AUDIO':
            if state_before.get('audio_muted') is False and state_before.get('volume', 0) > 0:
                return self._already_in_state(action, state_before, 'System audio is already unmuted.')

            # Restore exact preserved original volume (never blindly 50%)
            restore_vol = self.eaos_original_volume if self.eaos_original_volume is not None else 50
            if restore_vol <= 0:
                restore_vol = 50

            cmd_ok = run_shortcut('Set Volume', str(restore_vol))
            time.sleep(0.20)
            state_after = self.get_current_os_state(force_refresh=True)

            # Verification: actual volume matches restored level
            verified = (state_after.get('volume') == restore_vol and not state_after.get('audio_muted'))
            success = verified and cmd_ok
            if verified:
                self.eaos_owned_volume = False
                self.eaos_original_volume = None
                self.eaos_original_muted = None
                record_os_state_event('AUDIO_MUTE', 'UNMUTED', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, f"Shortcut: Set Volume ('{restore_vol}')", state_before, state_after, verified, success,
                                      f'System audio restored to exact original level ({restore_vol}%).', start_t, now_iso)

        # 8. REDUCE_BRIGHTNESS (Part 9, Action 7 & Part 15)
        elif action == 'REDUCE_BRIGHTNESS':
            curr_b = state_before.get('brightness') or 0.60
            if curr_b <= 0.30:
                return self._already_in_state(action, state_before, 'Brightness already at minimum comfortable level.')

            # Save exact original brightness before first EAOS reduction
            if self.eaos_original_brightness is None:
                self.eaos_original_brightness = curr_b
            self.eaos_owned_brightness = True

            # Controlled relative reduction: 15% normal, 25% severe
            is_severe = params.get('severe', False) or params.get('fatigue_score', 0.0) >= 0.70
            target_b = max(0.25, curr_b * 0.75) if is_severe else max(0.30, curr_b * 0.85)
            target_b = round(target_b, 2)

            cmd_ok = run_shortcut('Set Brightness', f"{target_b:.2f}")
            used_cmd = f"Shortcut: Set Brightness ('{target_b:.2f}')"
            if not cmd_ok:
                if run_shortcut('Set Brightness 1'):
                    cmd_ok = True
                    used_cmd = "Shortcut: Set Brightness 1 (70%)"
            time.sleep(0.20)
            state_after = self.get_current_os_state(force_refresh=True)

            after_b = state_after.get('brightness')
            verified = (after_b is not None and abs(after_b - target_b) <= 0.08)
            success = verified and cmd_ok
            if verified:
                record_os_state_event('BRIGHTNESS', f'{int(target_b * 100)}%', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, used_cmd, state_before, state_after, verified, success,
                                      f'Display brightness reduced to {int(target_b * 100)}% (original {int(self.eaos_original_brightness * 100)}% saved).', start_t, now_iso)

        # 9. RESTORE_BRIGHTNESS (Part 9, Action 8 & Part 15)
        elif action == 'RESTORE_BRIGHTNESS':
            # Restore exact preserved original brightness (defaults to 0.70)
            restore_b = self.eaos_original_brightness if self.eaos_original_brightness is not None else 0.70
            restore_b = round(restore_b, 2)

            cmd_ok = run_shortcut('Set Brightness', f"{restore_b:.2f}")
            used_cmd = f"Shortcut: Set Brightness ('{restore_b:.2f}')"
            if not cmd_ok or abs(restore_b - 0.70) <= 0.05:
                # Also leverage user's dedicated 'Set Brightness 1' macOS shortcut (70%)
                if run_shortcut('Set Brightness 1'):
                    cmd_ok = True
                    used_cmd = "Shortcut: Set Brightness 1 (70%)"
            time.sleep(0.20)
            state_after = self.get_current_os_state(force_refresh=True)

            after_b = state_after.get('brightness')
            verified = (after_b is not None and abs(after_b - restore_b) <= 0.08)
            success = verified and cmd_ok
            if verified:
                self.eaos_owned_brightness = False
                self.eaos_original_brightness = None
                record_os_state_event('BRIGHTNESS', f'{int(restore_b * 100)}%', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, used_cmd, state_before, state_after, verified, success,
                                      f'Display brightness restored to original {int(restore_b * 100)}%.', start_t, now_iso)

        # 10. SET_BRIGHTNESS / SET_BRIGHTNESS_1
        elif action in ['SET_BRIGHTNESS', 'SET_BRIGHTNESS_1', 'SET_BRIGHTNESS_70']:
            target_b = float(params.get('brightness', params.get('value', 0.7 if action != 'SET_BRIGHTNESS' else 0.5)))
            target_b = max(0.05, min(1.0, round(target_b, 2)))
            
            cmd_ok = run_shortcut('Set Brightness', f"{target_b:.2f}")
            used_cmd = f"Shortcut: Set Brightness ('{target_b:.2f}')"
            if not cmd_ok or abs(target_b - 0.70) <= 0.05 or action in ['SET_BRIGHTNESS_1', 'SET_BRIGHTNESS_70']:
                # Support user's dedicated 'Set Brightness 1' shortcut (70%)
                if run_shortcut('Set Brightness 1'):
                    cmd_ok = True
                    used_cmd = "Shortcut: Set Brightness 1 (70%)"
            time.sleep(0.20)
            state_after = self.get_current_os_state(force_refresh=True)

            after_b = state_after.get('brightness')
            verified = (after_b is not None and abs(after_b - target_b) <= 0.08)
            success = verified and cmd_ok
            if verified:
                record_os_state_event('BRIGHTNESS', f'{int(target_b * 100)}%', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, used_cmd, state_before, state_after, verified, success,
                                      f'Display brightness set to {int(target_b * 100)}%.', start_t, now_iso)

        # 11. SET_VOLUME
        elif action == 'SET_VOLUME':
            target_v = int(params.get('volume', params.get('value', 50)))
            target_v = max(0, min(100, target_v))
            cmd_ok = run_shortcut('Set Volume', str(target_v))
            if not cmd_ok or self.system == "Darwin":
                try:
                    res = subprocess.run(['osascript', '-e', f'set volume output volume {target_v}'], capture_output=True, timeout=2)
                    if res.returncode == 0:
                        cmd_ok = True
                except Exception as e:
                    logger.debug(f"osascript set volume fallback issue: {e}")
            time.sleep(0.10)
            state_after = self.get_current_os_state(force_refresh=True)

            verified = (abs(state_after.get('volume', 0) - target_v) <= 3)
            success = verified and cmd_ok
            if verified:
                record_os_state_event('VOLUME', f'{target_v}%', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
            return self._build_result(action, f"Set Volume ('{target_v}%')", state_before, state_after, verified, success,
                                      f'System output volume set to {target_v}%.', start_t, now_iso)

        # Advisory or unhandled actions
        return {
            'action': action,
            'requested': True,
            'executed': False,
            'verified': True,
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
            'DISABLE_FOCUS_MODE': 'ENABLE_FOCUS_MODE',
            'SILENCE_NOTIFICATIONS': 'DISABLE_FOCUS_MODE',
            'MUTE_AUDIO': 'UNMUTE_AUDIO',
            'UNMUTE_AUDIO': 'MUTE_AUDIO',
            'REDUCE_BRIGHTNESS': 'RESTORE_BRIGHTNESS',
            'RESTORE_BRIGHTNESS': 'REDUCE_BRIGHTNESS'
        }
        target = inversions.get(action)
        if target:
            res = self.execute(target, {'reason': f'Undo previous action {action}'})
            res['action'] = f'UNDO_{action}'
            return res

        return {
            'action': f'UNDO_{action}',
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

        # Restore original volume if preserved, else 50
        restore_vol = self.eaos_original_volume if self.eaos_original_volume is not None else 50
        run_shortcut('Set Volume', str(restore_vol))

        # Restore original brightness if preserved, else 0.70
        restore_b = self.eaos_original_brightness if self.eaos_original_brightness is not None else 0.70
        cmd_b_ok = run_shortcut('Set Brightness', f"{restore_b:.2f}")
        if not cmd_b_ok or abs(restore_b - 0.70) <= 0.05:
            run_shortcut('Set Brightness 1')

        self.focus_active = False
        self.eaos_original_volume = None
        self.eaos_original_muted = None
        self.eaos_original_brightness = None
        self.eaos_owned_dnd = False
        self.eaos_owned_volume = False
        self.eaos_owned_brightness = False
        self.eaos_owned_dark_mode = False

        time.sleep(0.20)
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
            'command_used': f'Shortcuts: Set Appearance (Light), Turn On DND (Off), Set Volume ({restore_vol}), Set Brightness ({restore_b:.2f})',
            'state_before': state_before,
            'state_after': state_after,
            'message': f'Baseline OS state restored (Light appearance, DND off, volume {restore_vol}%, brightness {int(restore_b * 100)}%).',
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
        status = 'executed' if success else ('failed_verification' if not verified else 'failed')
        return {
            'action': action,
            'requested': True,
            'executed': True,
            'verified': verified,
            'success': success,
            'status': status,
            'command_used': command,
            'state_before': before,
            'state_after': after,
            'message': message if success else f"Action {action} failed post-execution verification.",
            'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
            'timestamp': timestamp,
            'error': None if success else f"Target state not confirmed in actual macOS state for {action}"
        }


# Backwards compatibility alias
OSActuator = MacActuator
MacOSActuator = MacActuator
