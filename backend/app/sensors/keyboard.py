import time
import math
from collections import deque
from typing import Dict, Any, List, Optional

try:
    from pynput import keyboard
except Exception:
    keyboard = None


class KeyboardSensor:
    """
    Privacy-preserving behavioral keyboard sensor.
    DO NOT store actual typed text.
    DO NOT perform keylogging.
    Only collects timing and event metadata.
    """
    def __init__(self):
        # Rolling history of (timestamp, is_backspace) over the last 120 seconds
        self.events_history = deque(maxlen=2000)
        self.last_press_time: Optional[float] = None
        self.total_events = 0
        self.total_backspaces = 0
        self.active = False
        self.listener = None

    def _press(self, key):
        now = time.time()
        is_backspace = False
        try:
            if key == keyboard.Key.backspace or getattr(key, 'name', None) == 'backspace':
                is_backspace = True
        except Exception:
            pass

        self.last_press_time = now
        self.total_events += 1
        if is_backspace:
            self.total_backspaces += 1

        self.events_history.append((now, is_backspace))

    def start(self):
        if keyboard is None:
            return
        if self.active and self.listener:
            return
        try:
            self.listener = keyboard.Listener(on_press=self._press)
            self.listener.daemon = True
            self.listener.start()
            self.active = True
        except Exception:
            self.active = False

    def stop(self):
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
            self.listener = None
        self.active = False

    def get_window_metrics(self, window_sec: float = 60.0) -> Dict[str, Any]:
        """
        Calculates all Part 1 keyboard metrics for the given observation window.
        """
        now = time.time()
        cutoff = now - window_sec
        recent = [ev for ev in self.events_history if ev[0] >= cutoff]

        total_keydowns = len(recent)
        backspace_count = sum(1 for ev in recent if ev[1])
        backspace_ratio = (backspace_count / max(1, total_keydowns)) if total_keydowns > 0 else 0.0

        # Inter-key intervals within this observation window
        ikis: List[float] = []
        timestamps = [ev[0] for ev in recent]
        for i in range(1, len(timestamps)):
            dt = timestamps[i] - timestamps[i - 1]
            if 0.001 <= dt <= 4.0:  # Valid inter-key interval
                ikis.append(dt)

        if ikis:
            ikis_sorted = sorted(ikis)
            n_ikis = len(ikis_sorted)
            median_iki = ikis_sorted[n_ikis // 2] if n_ikis % 2 != 0 else (ikis_sorted[n_ikis // 2 - 1] + ikis_sorted[n_ikis // 2]) / 2.0
            mean_iki = sum(ikis) / n_ikis
            variance = sum((x - mean_iki) ** 2 for x in ikis) / n_ikis
            iki_std = math.sqrt(variance)
            rhythm_cv = (iki_std / mean_iki) if mean_iki > 0.0 else 0.0
        else:
            median_iki = 0.0
            mean_iki = 0.0
            iki_std = 0.0
            rhythm_cv = 0.0

        # Active typing seconds: distinct 1-second buckets with >= 1 keystroke
        distinct_seconds = set(int(t) for t in timestamps)
        active_typing_seconds = len(distinct_seconds)
        typing_activity_ratio = min(1.0, active_typing_seconds / max(1.0, window_sec))

        # Typing rate: key-down events / active observation seconds
        typing_rate_kps = total_keydowns / max(1.0, float(window_sec))
        typing_rate_kpm = typing_rate_kps * 60.0

        # Longest pause within the observation window
        longest_pause = 0.0
        if len(timestamps) >= 2:
            longest_pause = max((timestamps[i] - timestamps[i - 1]) for i in range(1, len(timestamps)))
        elif len(timestamps) == 1:
            longest_pause = min(window_sec, max(0.0, now - timestamps[0]))
        else:
            longest_pause = window_sec

        # Burst count: sequences with IKI < 2.0s
        burst_count = 0
        in_burst = False
        for i in range(1, len(timestamps)):
            dt = timestamps[i] - timestamps[i - 1]
            if dt < 2.0:
                if not in_burst:
                    burst_count += 1
                    in_burst = True
            else:
                in_burst = False

        # Condition flags
        normal_active = (typing_rate_kps >= 1.0 and typing_activity_ratio >= 0.35)
        high_intensity = (typing_rate_kps >= 3.0 and typing_activity_ratio >= 0.50)
        very_high_intensity = (typing_rate_kps >= 4.5 and typing_activity_ratio >= 0.60)
        high_friction = (backspace_ratio >= 0.10)
        strong_friction = (backspace_ratio >= 0.18)
        extreme_friction = (backspace_ratio >= 0.25)
        slow_hesitant = (typing_rate_kps <= 0.60 and typing_activity_ratio >= 0.25)
        near_idle = (typing_rate_kps < 0.20 and typing_activity_ratio < 0.15)
        unstable_rhythm = (median_iki < 0.18 and rhythm_cv > 0.80 and total_keydowns >= 10)
        hesitation = (median_iki > 0.55 and typing_activity_ratio >= 0.20)

        return {
            'total_keydowns': total_keydowns,
            'typing_rate_kps': round(typing_rate_kps, 2),
            'typing_rate_kpm': round(typing_rate_kpm, 1),
            'backspace_count': backspace_count,
            'backspace_ratio': round(backspace_ratio, 3),
            'median_inter_key_interval': round(median_iki, 3),
            'mean_inter_key_interval': round(mean_iki, 3),
            'inter_key_interval_std': round(iki_std, 3),
            'typing_rhythm_cv': round(rhythm_cv, 3),
            'active_typing_seconds': active_typing_seconds,
            'typing_activity_ratio': round(typing_activity_ratio, 3),
            'longest_typing_pause': round(longest_pause, 2),
            'burst_count': burst_count,
            'conditions': {
                'normal_active': normal_active,
                'high_intensity': high_intensity,
                'very_high_intensity': very_high_intensity,
                'high_friction': high_friction,
                'strong_friction': strong_friction,
                'extreme_friction': extreme_friction,
                'slow_hesitant': slow_hesitant,
                'near_idle': near_idle,
                'unstable_rhythm': unstable_rhythm,
                'hesitation': hesitation
            }
        }

    def snapshot(self, window_sec: float = 10.0) -> Dict[str, Any]:
        """
        Backward-compatible snapshot containing both classic fields and window metrics.
        """
        metrics = self.get_window_metrics(window_sec=window_sec)
        return {
            'active': self.active,
            'events': self.total_events,
            'recent_events': metrics['total_keydowns'],
            'avg_inter_key_interval': metrics['mean_inter_key_interval'],
            'median_inter_key_interval': metrics['median_inter_key_interval'],
            'typing_rate': metrics['typing_rate_kps'],
            'typing_rate_kpm': metrics['typing_rate_kpm'],
            'backspace_rate': metrics['backspace_ratio'],
            'backspace_count': metrics['backspace_count'],
            'active_typing_seconds': metrics['active_typing_seconds'],
            'typing_activity_ratio': metrics['typing_activity_ratio'],
            'typing_rhythm_cv': metrics['typing_rhythm_cv'],
            'longest_typing_pause': metrics['longest_typing_pause'],
            'burst_count': metrics['burst_count'],
            'conditions': metrics['conditions']
        }
