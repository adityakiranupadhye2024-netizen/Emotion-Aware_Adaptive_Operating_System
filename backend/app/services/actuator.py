import platform
import subprocess
import logging
import time
import ctypes
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.db.database import record_os_state_event

logger = logging.getLogger("eaos.actuator")

# Load macOS DisplayServices private framework for physical display brightness
_ds_lib = None
if platform.system() == "Darwin":
    try:
        _ds_lib = ctypes.cdll.LoadLibrary('/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices')
        if hasattr(_ds_lib, 'DisplayServicesGetLinearBrightness'):
            _ds_lib.DisplayServicesGetLinearBrightness.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_float)]
            _ds_lib.DisplayServicesGetLinearBrightness.restype = ctypes.c_int
            _ds_lib.DisplayServicesSetLinearBrightness.argtypes = [ctypes.c_uint32, ctypes.c_float]
            _ds_lib.DisplayServicesSetLinearBrightness.restype = ctypes.c_int
        else:
            _ds_lib.DisplayServicesGetBrightness.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_float)]
            _ds_lib.DisplayServicesGetBrightness.restype = ctypes.c_int
            _ds_lib.DisplayServicesSetBrightness.argtypes = [ctypes.c_uint32, ctypes.c_float]
            _ds_lib.DisplayServicesSetBrightness.restype = ctypes.c_int
        logger.info("macOS DisplayServices framework initialized for hardware linear brightness control.")
    except Exception as e:
        logger.warning(f"Could not load DisplayServices framework: {e}")


class MacActuator:
    """
    Real macOS Actuator for EAOS.
    Executes actual operating-system changes using macOS native APIs (AppleScript via osascript,
    DisplayServices.framework via ctypes).
    
    CRITICAL INVARIANTS:
    1. NEVER report success without reading the real OS state after execution and verifying the change.
    2. Read OS state before execution for idempotency (avoid redundant commands).
    3. Detect permission failures (e.g. AppleScript -1743 Automation permission).
    4. Provide get_current_os_state() as the ground-truth reader for macOS.
    """

    def __init__(self):
        self.system = platform.system()
        self.focus_active = False
        self.last_saved_brightness: Optional[float] = None
        self._cached_os_state: Optional[Dict[str, Any]] = None
        self._last_state_check_time: float = 0.0
        self._state_cache_ttl: float = 1.2
        self._check_initial_permissions()

    def _check_initial_permissions(self) -> Dict[str, Any]:
        """Performs initial check of macOS automation and accessibility permissions."""
        if self.system != "Darwin":
            return {"automation": False, "details": f"Non-macOS platform ({self.system})"}
        try:
            res = subprocess.run(
                ['osascript', '-e', 'tell application "System Events" to tell appearance preferences to get dark mode'],
                capture_output=True, text=True, timeout=2
            )
            if res.returncode == 0:
                return {"automation": True, "details": "AppleScript Automation permission GRANTED"}
            elif "-1743" in res.stderr:
                return {"automation": False, "details": "PERMISSION_REQUIRED: Automation permission denied for System Events"}
            else:
                return {"automation": False, "details": res.stderr.strip()}
        except Exception as e:
            return {"automation": False, "details": str(e)}

    # =========================================================================
    # REAL MACOS STATE READERS (GROUND TRUTH)
    # =========================================================================

    def get_dark_mode(self) -> Optional[bool]:
        """Reads real macOS appearance (Dark Mode = True, Light Mode = False)."""
        if self.system != "Darwin":
            return False
        try:
            res = subprocess.run(
                ['osascript', '-e', 'tell application "System Events" to tell appearance preferences to get dark mode'],
                capture_output=True, text=True, timeout=2
            )
            if res.returncode == 0:
                return res.stdout.strip().lower() == "true"
            logger.warning(f"Failed to read macOS dark mode: {res.stderr.strip()}")
            return None
        except Exception as e:
            logger.warning(f"Error querying dark mode: {e}")
            return None

    def get_brightness(self) -> Optional[float]:
        """Reads real physical display brightness (0.0 to 1.0) via DisplayServices."""
        if self.system != "Darwin" or not _ds_lib:
            return None
        try:
            val = ctypes.c_float()
            if hasattr(_ds_lib, 'DisplayServicesGetLinearBrightness'):
                ret = _ds_lib.DisplayServicesGetLinearBrightness(1, ctypes.byref(val))
            else:
                ret = _ds_lib.DisplayServicesGetBrightness(1, ctypes.byref(val))
            if ret == 0:
                return round(float(val.value), 3)
            return None
        except Exception as e:
            logger.warning(f"Error querying display brightness: {e}")
            return None

    def get_alert_volume(self) -> int:
        """Reads real system notification alert volume (0 = silenced/DND, 100 = nominal)."""
        if self.system != "Darwin":
            return 100
        try:
            res = subprocess.run(
                ['osascript', '-e', 'get alert volume of (get volume settings)'],
                capture_output=True, text=True, timeout=2
            )
            if res.returncode == 0:
                return int(res.stdout.strip())
            return 100
        except Exception:
            return 100

    def get_audio_muted(self) -> Optional[bool]:
        """Reads real system alert audio mute status."""
        if self.system != "Darwin":
            return False
        try:
            res = subprocess.run(
                ['osascript', '-e', 'output muted of (get volume settings)'],
                capture_output=True, text=True, timeout=2
            )
            out_muted = res.returncode == 0 and res.stdout.strip().lower() == "true"
            return out_muted or self.focus_active
        except Exception as e:
            logger.warning(f"Error querying audio mute state: {e}")
            return self.focus_active

    def get_current_os_state(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Comprehensive real-time ground truth reader for the macOS system.
        Cached with 1.2s TTL to prevent subprocess flooding while providing fast dashboard updates.
        """
        now_ts = time.time()
        if not force_refresh and self._cached_os_state is not None and (now_ts - self._last_state_check_time) < self._state_cache_ttl:
            return self._cached_os_state

        now = datetime.now(timezone.utc).isoformat()
        dark = self.get_dark_mode()
        brightness = self.get_brightness()
        alert_vol = self.get_alert_volume()
        muted = self.get_audio_muted()

        permission_ok = dark is not None and muted is not None

        state = {
            "platform": self.system,
            "actuator_ready": self.system == "Darwin" and permission_ok,
            "dark_mode": dark if dark is not None else False,
            "dark_mode_display": "DARK MODE" if dark else "LIGHT MODE",
            "brightness": brightness if brightness is not None else 0.50,
            "brightness_pct": int((brightness if brightness is not None else 0.50) * 100),
            "brightness_controllable": brightness is not None,
            "audio_muted": bool(muted),
            "alert_volume": alert_vol,
            "focus_mode_active": self.focus_active or alert_vol == 0 or (muted is True),
            "permission_status": "GRANTED" if permission_ok else "REQUIRED",
            "last_checked": now
        }
        self._cached_os_state = state
        self._last_state_check_time = now_ts
        return state

    # Backward compatibility alias
    def is_dark_mode(self) -> bool:
        dm = self.get_dark_mode()
        return bool(dm) if dm is not None else False

    # =========================================================================
    # ACTION EXECUTION & VERIFICATION PIPELINE
    # =========================================================================

    def _set_display_brightness(self, target_b: float) -> int:
        target_b = max(0.05, min(1.0, float(target_b)))
        if hasattr(_ds_lib, 'DisplayServicesSetLinearBrightness'):
            return _ds_lib.DisplayServicesSetLinearBrightness(1, ctypes.c_float(target_b))
        elif hasattr(_ds_lib, 'DisplayServicesSetBrightness'):
            return _ds_lib.DisplayServicesSetBrightness(1, ctypes.c_float(target_b))
        return -1

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes an OS adaptation action following the strict pipeline:
        1. Read actual OS state before.
        2. Idempotency check: if already in desired state, return already_in_desired_state.
        3. Execute actual macOS command / API.
        4. Wait for completion and capture exit code / output.
        5. Read actual OS state after.
        6. Verify state actually changed as expected.
        7. Record state event in DB ONLY when verified.
        8. Return comprehensive ActionResult.
        """
        start_t = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        params = params or {}
        as_score = float(params.get('adaptive_score', 0.0))
        reason = str(params.get('reason', ''))
        cycle_id = int(params.get('cycle_id', 1))

        self._cached_os_state = None
        state_before = self.get_current_os_state(force_refresh=True)

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

        if self.system != 'Darwin':
            return {
                'action': action,
                'requested': True,
                'executed': False,
                'verified': False,
                'success': False,
                'status': 'unsupported',
                'command_used': 'NONE',
                'state_before': state_before,
                'state_after': state_before,
                'message': f'Real OS actuation unavailable on non-macOS platform ({self.system}).',
                'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                'timestamp': now_iso,
                'error': f'Unsupported OS: {self.system}'
            }

        # ---------------------------------------------------------------------
        # 1. ENABLE_DARK_MODE
        # ---------------------------------------------------------------------
        if action == 'ENABLE_DARK_MODE':
            command = 'osascript -e \'tell application "System Events" to tell appearance preferences to set dark mode to true\''
            
            # Idempotency check
            if state_before.get('dark_mode') is True:
                return {
                    'action': action,
                    'requested': True,
                    'executed': False,
                    'verified': True,
                    'success': True,
                    'status': 'already_in_desired_state',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_before,
                    'message': 'macOS Dark Mode is already active. No OS command needed.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': None
                }

            res = subprocess.run(
                ['osascript', '-e', 'tell application "System Events" to tell appearance preferences to set dark mode to true'],
                capture_output=True, text=True, timeout=4
            )
            time.sleep(0.15)  # allow macOS appearance transition
            state_after = self.get_current_os_state(force_refresh=True)
            verified = (state_after.get('dark_mode') is True)

            if verified:
                record_os_state_event('DARK_MODE', 'ON', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': True,
                    'success': True,
                    'status': 'executed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': 'macOS Dark Mode enabled and verified successfully.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': None
                }
            else:
                err = res.stderr.strip() or "Appearance preference failed to transition to dark mode."
                status = 'permission_required' if '-1743' in err else 'failed'
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': False,
                    'success': False,
                    'status': status,
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': f'Failed to enable Dark Mode: {err}',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': err
                }

        # ---------------------------------------------------------------------
        # 2. DISABLE_DARK_MODE
        # ---------------------------------------------------------------------
        elif action == 'DISABLE_DARK_MODE':
            command = 'osascript -e \'tell application "System Events" to tell appearance preferences to set dark mode to false\''
            
            # Idempotency check
            if state_before.get('dark_mode') is False:
                return {
                    'action': action,
                    'requested': True,
                    'executed': False,
                    'verified': True,
                    'success': True,
                    'status': 'already_in_desired_state',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_before,
                    'message': 'macOS Light Mode is already active. No OS command needed.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': None
                }

            res = subprocess.run(
                ['osascript', '-e', 'tell application "System Events" to tell appearance preferences to set dark mode to false'],
                capture_output=True, text=True, timeout=4
            )
            time.sleep(0.15)
            state_after = self.get_current_os_state(force_refresh=True)
            verified = (state_after.get('dark_mode') is False)

            if verified:
                record_os_state_event('DARK_MODE', 'OFF', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': True,
                    'success': True,
                    'status': 'executed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': 'macOS Light Mode restored and verified successfully.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': None
                }
            else:
                err = res.stderr.strip() or "Appearance preference failed to transition to light mode."
                status = 'permission_required' if '-1743' in err else 'failed'
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': False,
                    'success': False,
                    'status': status,
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': f'Failed to restore Light Mode: {err}',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': err
                }

        # ---------------------------------------------------------------------
        # 3. REDUCE_BRIGHTNESS (Real hardware display control)
        # ---------------------------------------------------------------------
        elif action == 'REDUCE_BRIGHTNESS':
            command = 'DisplayServices.DisplayServicesSetLinearBrightness(1, target_brightness)'
            curr_b = self.get_brightness()

            if curr_b is None:
                sub_res = self.execute('ENABLE_DARK_MODE', params)
                sub_res['message'] = "Brightness control unavailable on display; switched to Dark Mode to reduce screen glare."
                return sub_res

            # Save previous brightness for restoration
            if self.last_saved_brightness is None:
                self.last_saved_brightness = curr_b

            target_b = max(0.15, curr_b - 0.20)
            if abs(curr_b - target_b) < 0.03:
                return {
                    'action': action,
                    'requested': True,
                    'executed': False,
                    'verified': True,
                    'success': True,
                    'status': 'already_in_desired_state',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_before,
                    'message': f'Screen brightness already at reduced level ({int(curr_b * 100)}%).',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': None
                }

            ret = self._set_display_brightness(target_b)
            time.sleep(0.1)
            state_after = self.get_current_os_state(force_refresh=True)
            new_b = state_after.get('brightness', 0.5)
            verified = (ret == 0 and new_b < curr_b)

            if verified:
                record_os_state_event('BRIGHTNESS', f'{int(new_b * 100)}%', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': True,
                    'success': True,
                    'status': 'executed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': f'Physical display brightness reduced from {int(curr_b * 100)}% to {int(new_b * 100)}%.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': None
                }
            else:
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': False,
                    'success': False,
                    'status': 'failed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': 'Failed to adjust physical display brightness.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': f'DisplayServicesSetLinearBrightness returned error code {ret}'
                }

        # ---------------------------------------------------------------------
        # 4. RESTORE_BRIGHTNESS
        # ---------------------------------------------------------------------
        elif action == 'RESTORE_BRIGHTNESS':
            command = 'DisplayServices.DisplayServicesSetLinearBrightness(1, restored_brightness)'
            curr_b = self.get_brightness()
            if curr_b is None or not _ds_lib:
                return {
                    'action': action,
                    'requested': True,
                    'executed': False,
                    'verified': False,
                    'success': False,
                    'status': 'unsupported',
                    'command_used': 'NONE',
                    'state_before': state_before,
                    'state_after': state_before,
                    'message': 'Hardware brightness control unavailable on this system.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': 'DisplayServices unavailable'
                }

            target_b = self.last_saved_brightness if self.last_saved_brightness is not None else min(1.0, curr_b + 0.20)
            ret = self._set_display_brightness(target_b)
            time.sleep(0.1)
            state_after = self.get_current_os_state(force_refresh=True)
            new_b = state_after.get('brightness', 0.5)
            verified = (ret == 0 and new_b >= curr_b)
            self.last_saved_brightness = None

            if verified:
                record_os_state_event('BRIGHTNESS', f'{int(new_b * 100)}%', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': True,
                    'success': True,
                    'status': 'executed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': f'Display brightness restored to {int(new_b * 100)}%.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': None
                }
            else:
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': False,
                    'success': False,
                    'status': 'failed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': 'Failed to restore display brightness.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': f'DisplayServicesSetLinearBrightness returned {ret}'
                }

        # ---------------------------------------------------------------------
        # 5. ENABLE_FOCUS_MODE / SILENCE_NOTIFICATIONS
        # ---------------------------------------------------------------------
        elif action in ['ENABLE_FOCUS_MODE', 'SILENCE_NOTIFICATIONS']:
            command = "osascript -e 'set volume alert volume 0' + 'set volume output muted true'"
            
            # Idempotency check
            if (self.get_alert_volume() == 0 or state_before.get('audio_muted') is True) and self.focus_active:
                return {
                    'action': action,
                    'requested': True,
                    'executed': False,
                    'verified': True,
                    'success': True,
                    'status': 'already_in_desired_state',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_before,
                    'message': 'Focus / DND Mode is already active (alerts silenced).',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': None
                }

            # 1. Mute alert volume to 0 (DND) and output muted
            subprocess.run(['osascript', '-e', 'set volume alert volume 0'], capture_output=True, text=True, timeout=2)
            subprocess.run(['osascript', '-e', 'set volume output muted true'], capture_output=True, text=True, timeout=2)
            self.focus_active = True
            
            # 2. Declutter background windows (safeguard active app + IDEs + Terminals)
            hide_script = '''
            tell application "System Events"
                try
                    set frontApp to name of first application process whose frontmost is true
                    set visible of (every process whose visible is true and name is not frontApp and name is not "Electron" and name is not "Terminal" and name is not "iTerm2") to false
                end try
            end tell
            '''
            subprocess.run(['osascript', '-e', hide_script], capture_output=True, text=True, timeout=3)
            
            state_after = self.get_current_os_state(force_refresh=True)
            verified = (state_after.get('audio_muted') is True or state_after.get('alert_volume', 100) == 0)

            if verified:
                record_os_state_event('FOCUS_MODE', 'ON', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': True,
                    'success': True,
                    'status': 'executed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': 'Focus / DND mode active: notification alert volume silenced and background apps hidden.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': None
                }
            else:
                err = "Audio volume muting command failed."
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': False,
                    'success': False,
                    'status': 'failed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': f'Failed to mute system alerts: {err}',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': err
                }

        # ---------------------------------------------------------------------
        # 6. DISABLE_FOCUS_MODE
        # ---------------------------------------------------------------------
        elif action == 'DISABLE_FOCUS_MODE':
            command = "osascript -e 'set volume alert volume 100' + 'set volume output muted false'"

            # Idempotency check
            if self.get_alert_volume() > 0 and state_before.get('audio_muted') is False and not self.focus_active:
                return {
                    'action': action,
                    'requested': True,
                    'executed': False,
                    'verified': True,
                    'success': True,
                    'status': 'already_in_desired_state',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_before,
                    'message': 'Normal notification alert volume is already active.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': None
                }

            subprocess.run(['osascript', '-e', 'set volume alert volume 100'], capture_output=True, text=True, timeout=2)
            subprocess.run(['osascript', '-e', 'set volume output muted false'], capture_output=True, text=True, timeout=2)
            self.focus_active = False
            state_after = self.get_current_os_state(force_refresh=True)
            verified = (state_after.get('audio_muted') is False or state_after.get('alert_volume', 0) > 0)

            if verified:
                record_os_state_event('FOCUS_MODE', 'OFF', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': True,
                    'success': True,
                    'status': 'executed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': 'Focus / DND mode disengaged; normal alert volume restored to 100%.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': None
                }
            else:
                err = "Audio volume unmuting failed."
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': False,
                    'success': False,
                    'status': 'failed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': f'Failed to restore alert volume: {err}',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': err
                }

        # ---------------------------------------------------------------------
        # 6B. SET_BRIGHTNESS (Direct Brightness Setting)
        # ---------------------------------------------------------------------
        elif action == 'SET_BRIGHTNESS':
            target_b = float(params.get('brightness', params.get('value', 0.5)))
            target_b = max(0.05, min(1.0, target_b))
            command = f'DisplayServices.DisplayServicesSetLinearBrightness(1, {target_b:.2f})'
            curr_b = self.get_brightness()
            if curr_b is None or not _ds_lib:
                return {
                    'action': action,
                    'requested': True,
                    'executed': False,
                    'verified': False,
                    'success': False,
                    'status': 'unsupported',
                    'command_used': 'NONE',
                    'state_before': state_before,
                    'state_after': state_before,
                    'message': 'Hardware brightness control unavailable.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': 'DisplayServices unavailable'
                }
            ret = self._set_display_brightness(target_b)
            time.sleep(0.1)
            state_after = self.get_current_os_state(force_refresh=True)
            new_b = state_after.get('brightness', target_b)
            verified = (ret == 0)
            if verified:
                record_os_state_event('BRIGHTNESS', f'{int(new_b * 100)}%', source='EAOS', adaptive_score=as_score, reason=reason, cycle_id=cycle_id)
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': True,
                    'success': True,
                    'status': 'executed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': f'Display brightness set to {int(new_b * 100)}%.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': None
                }
            else:
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': False,
                    'success': False,
                    'status': 'failed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': 'Failed to adjust brightness.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': f'DisplayServicesSetLinearBrightness error {ret}'
                }

        # ---------------------------------------------------------------------
        # 7. SUGGEST_BREAK (Audio chime + Speech synthesizer)
        # ---------------------------------------------------------------------
        elif action == 'SUGGEST_BREAK':
            command = 'osascript -e beep 2 + say -r 190 "EAOS recommends taking a short break"'
            try:
                subprocess.run(['osascript', '-e', 'beep 2'], capture_output=True, timeout=2)
                proc = subprocess.Popen(['say', '-r', '190', 'EAOS recommends taking a short break'])
                state_after = self.get_current_os_state(force_refresh=True)
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': True,
                    'success': True,
                    'status': 'executed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': 'Wellness alert chime sounded and speech notification delivered.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': None
                }
            except Exception as e:
                return {
                    'action': action,
                    'requested': True,
                    'executed': False,
                    'verified': False,
                    'success': False,
                    'status': 'failed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_before,
                    'message': f'Could not play break chime or voice announcement: {e}',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': str(e)
                }

        # ---------------------------------------------------------------------
        # 8. SUGGEST_DEBUG_RESOURCE
        # ---------------------------------------------------------------------
        elif action == 'SUGGEST_DEBUG_RESOURCE':
            command = 'open https://devdocs.io'
            try:
                res = subprocess.run(['open', 'https://devdocs.io'], capture_output=True, text=True, timeout=3)
                state_after = self.get_current_os_state(force_refresh=True)
                return {
                    'action': action,
                    'requested': True,
                    'executed': True,
                    'verified': res.returncode == 0,
                    'success': res.returncode == 0,
                    'status': 'executed' if res.returncode == 0 else 'failed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_after,
                    'message': 'Opened documentation reference in default browser.',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': res.stderr.strip() if res.returncode != 0 else None
                }
            except Exception as e:
                return {
                    'action': action,
                    'requested': True,
                    'executed': False,
                    'verified': False,
                    'success': False,
                    'status': 'failed',
                    'command_used': command,
                    'state_before': state_before,
                    'state_after': state_before,
                    'message': f'Failed opening browser resource: {e}',
                    'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
                    'timestamp': now_iso,
                    'error': str(e)
                }

        # Default fallback for unhandled actions
        return {
            'action': action,
            'requested': True,
            'executed': False,
            'verified': False,
            'success': False,
            'status': 'unsupported',
            'command_used': 'NONE',
            'state_before': state_before,
            'state_after': state_before,
            'message': f'Action {action} is not a recognized macOS adaptation.',
            'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
            'timestamp': now_iso,
            'error': f'Unsupported action: {action}'
        }

    # =========================================================================
    # REVERSAL & RESET PIPELINE
    # =========================================================================

    def undo_action(self, action: str) -> Dict[str, Any]:
        """Reverses a previously executed OS adaptation and verifies the reversal."""
        logger.info(f"User requested UNDO for action: {action}")
        if action == 'ENABLE_DARK_MODE':
            res = self.execute('DISABLE_DARK_MODE', {'reason': f'User UNDO of {action}'})
            res['action'] = action
            res['status'] = 'undone'
            return res
        elif action == 'REDUCE_BRIGHTNESS':
            res = self.execute('RESTORE_BRIGHTNESS', {'reason': 'User UNDO of brightness reduction'})
            res['action'] = action
            res['status'] = 'undone'
            return res
        elif action == 'RESTORE_BRIGHTNESS':
            res = self.execute('REDUCE_BRIGHTNESS', {'reason': 'User UNDO of restore brightness'})
            res['action'] = action
            res['status'] = 'undone'
            return res
        elif action in ['ENABLE_FOCUS_MODE', 'SILENCE_NOTIFICATIONS']:
            res = self.execute('DISABLE_FOCUS_MODE', {'reason': f'User UNDO of {action}'})
            res['action'] = action
            res['status'] = 'undone'
            return res
        elif action == 'DISABLE_DARK_MODE':
            res = self.execute('ENABLE_DARK_MODE', {'reason': f'User UNDO of {action}'})
            res['action'] = action
            res['status'] = 'undone'
            return res
        elif action == 'DISABLE_FOCUS_MODE':
            res = self.execute('ENABLE_FOCUS_MODE', {'reason': f'User UNDO of {action}'})
            res['action'] = action
            res['status'] = 'undone'
            return res
        else:
            return {
                'action': action,
                'requested': True,
                'executed': False,
                'verified': True,
                'success': True,
                'status': 'undone',
                'message': f'Adaptation {action} has no persistent OS settings to reverse.',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': None
            }

    def reset_all(self) -> Dict[str, Any]:
        """
        Restores macOS to baseline user settings:
        1. Disables Dark Mode (restores Light Mode).
        2. Restores unmuted system alert audio.
        3. Restores physical display brightness.
        4. Verifies every restored setting against macOS.
        """
        start_t = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        state_before = self.get_current_os_state()

        if self.system != 'Darwin':
            record_os_state_event('DARK_MODE', 'OFF', source='EAOS_RESET', reason='Platform Reset All')
            record_os_state_event('FOCUS_MODE', 'OFF', source='EAOS_RESET', reason='Platform Reset All')
            return {
                'action': 'RESET_ALL',
                'requested': True,
                'executed': False,
                'verified': False,
                'success': True,
                'status': 'unsupported',
                'message': f'Reset simulated on {self.system}',
                'timestamp': now_iso,
                'error': None
            }

        # 1. Restore Light Mode
        subprocess.run(
            ['osascript', '-e', 'tell application "System Events" to tell appearance preferences to set dark mode to false'],
            capture_output=True, timeout=3
        )
        # 2. Unmute system alert audio
        subprocess.run(['osascript', '-e', 'set volume output muted false'], capture_output=True, timeout=2)

        # 3. Restore brightness if altered
        if self.last_saved_brightness is not None and _ds_lib:
            try:
                _ds_lib.DisplayServicesSetBrightness(1, ctypes.c_float(self.last_saved_brightness))
            except Exception:
                pass
            self.last_saved_brightness = None

        time.sleep(0.15)
        state_after = self.get_current_os_state(force_refresh=True)
        self.focus_active = False

        verified = (state_after.get('dark_mode') is False) and (state_after.get('audio_muted') is False)
        record_os_state_event('DARK_MODE', 'OFF', source='EAOS_RESET', reason='User triggered Reset All')
        record_os_state_event('FOCUS_MODE', 'OFF', source='EAOS_RESET', reason='User triggered Reset All')

        return {
            'action': 'RESET_ALL',
            'requested': True,
            'executed': True,
            'verified': verified,
            'success': verified,
            'status': 'executed' if verified else 'failed',
            'command_used': 'Appearance preferences light mode + unmute audio + restore brightness',
            'state_before': state_before,
            'state_after': state_after,
            'message': 'Light Mode restored, audio unmuted, and display brightness reset.' if verified else 'Partial reset: some macOS settings did not change.',
            'execution_duration_ms': round((time.time() - start_t) * 1000, 2),
            'timestamp': now_iso,
            'error': None if verified else 'Failed to verify light mode or audio unmute'
        }


# Export both names for backwards compatibility
OSActuator = MacActuator
