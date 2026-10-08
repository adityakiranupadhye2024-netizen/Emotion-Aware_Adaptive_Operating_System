import time
import math
from collections import deque
from typing import Dict, Any, List, Optional

try:
    from pynput import mouse
except Exception:
    mouse = None


class MouseSensor:
    """
    Mouse telemetry sensor computing trajectory, straightness, click dynamics,
    and agitation/jitter scores.
    """
    def __init__(self):
        # Rolling history of (timestamp, x, y) over the last 120 seconds
        self.positions = deque(maxlen=4000)
        self.clicks_history = deque(maxlen=500)
        self.total_clicks = 0
        self.last_event = time.time()
        self.active = False
        self.listener = None

    def _move(self, x, y):
        now = time.time()
        self.positions.append((now, x, y))
        self.last_event = now

    def _click(self, x, y, button, pressed):
        if pressed:
            now = time.time()
            self.total_clicks += 1
            self.clicks_history.append(now)
            self.last_event = now

    def start(self):
        if mouse is None:
            return
        if self.active and self.listener:
            return
        try:
            self.listener = mouse.Listener(on_move=self._move, on_click=self._click)
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
        Calculates all Part 2 mouse metrics for the observation window.
        """
        now = time.time()
        cutoff = now - window_sec
        recent_pts = [p for p in self.positions if p[0] >= cutoff]
        recent_clicks = [t for t in self.clicks_history if t >= cutoff]

        click_count = len(recent_clicks)
        click_rate = click_count / (max(1.0, window_sec) / 60.0)

        # Idle time since last event
        idle_duration = now - self.last_event
        is_idle_15s = (idle_duration >= 15.0)
        is_strong_idle_25s = (idle_duration >= 25.0)

        path_length = 0.0
        reversals = 0
        dxs: List[float] = []
        dys: List[float] = []
        point_timestamps: List[float] = []

        if len(recent_pts) >= 2:
            for a, b in zip(recent_pts, recent_pts[1:]):
                d = math.hypot(b[1] - a[1], b[2] - a[2])
                path_length += d
                dxs.append(b[1] - a[1])
                dys.append(b[2] - a[2])
                point_timestamps.append(b[0])

            # Directional reversals
            for i in range(1, len(dxs)):
                if (dxs[i] * dxs[i - 1] < 0) or (dys[i] * dys[i - 1] < 0):
                    reversals += 1

            first_p = recent_pts[0]
            last_p = recent_pts[-1]
            net_displacement = math.hypot(last_p[1] - first_p[1], last_p[2] - first_p[2])
            straightness = net_displacement / max(1.0, path_length)
        else:
            net_displacement = 0.0
            straightness = 1.0

        movement_distance_per_sec = path_length / max(1.0, window_sec)
        movement_distance_per_min = movement_distance_per_sec * 60.0

        # Active mouse ratio: distinct 1-second buckets with movement or clicks
        active_seconds_set = set(int(p[0]) for p in recent_pts).union(set(int(t) for t in recent_clicks))
        active_seconds = len(active_seconds_set)
        active_mouse_ratio = min(1.0, active_seconds / max(1.0, window_sec))
        idle_ratio = max(0.0, 1.0 - active_mouse_ratio)

        # Pauses (intervals between movements > 2.0s)
        pause_count = 0
        burst_count = 0
        in_burst = False
        for i in range(1, len(point_timestamps)):
            dt = point_timestamps[i] - point_timestamps[i - 1]
            if dt > 2.0:
                pause_count += 1
                in_burst = False
            else:
                if not in_burst:
                    burst_count += 1
                    in_burst = True

        # Stable jitter / agitation score:
        # High agitation is marked by high path length with low straightness (erratic looping),
        # high directional reversal density, and rapid click rate.
        reversal_density = (reversals / max(1, len(dxs))) if dxs else 0.0
        inefficiency = max(0.0, 1.0 - straightness) if path_length > 100.0 else 0.0
        speed_factor = min(1.0, movement_distance_per_min / 1200.0)

        jitter_score = (
            0.40 * reversal_density +
            0.35 * inefficiency * speed_factor +
            0.25 * min(1.0, click_rate / 40.0)
        )
        jitter_score = round(min(1.0, max(0.0, jitter_score)), 3)

        # Mouse condition flags
        mouse_active = (movement_distance_per_min >= 100.0 or click_rate >= 3.0)
        high_click_rate = (click_rate >= 30.0)
        very_high_click_rate = (click_rate >= 60.0)
        agitated_mouse = (jitter_score >= 0.20 and movement_distance_per_min >= 500.0 and click_rate >= 5.0)
        strong_agitation = (jitter_score >= 0.35 and movement_distance_per_min >= 700.0 and click_rate >= 8.0)

        return {
            'total_movement_distance': round(path_length, 1),
            'movement_distance_per_second': round(movement_distance_per_sec, 2),
            'movement_distance_per_minute': round(movement_distance_per_min, 1),
            'click_count': click_count,
            'click_rate': round(click_rate, 2),
            'active_mouse_ratio': round(active_mouse_ratio, 3),
            'idle_ratio': round(idle_ratio, 3),
            'pause_count': pause_count,
            'movement_burst_count': burst_count,
            'jitter_score': jitter_score,
            'straightness': round(straightness, 3),
            'net_displacement': round(net_displacement, 1),
            'idle_duration_seconds': round(idle_duration, 1),
            'conditions': {
                'mouse_active': mouse_active,
                'mouse_idle': is_idle_15s,
                'strong_idle': is_strong_idle_25s,
                'high_click_rate': high_click_rate,
                'very_high_click_rate': very_high_click_rate,
                'agitated_mouse': agitated_mouse,
                'strong_agitation': strong_agitation
            }
        }

    def snapshot(self, window_sec: float = 10.0) -> Dict[str, Any]:
        """
        Backward-compatible snapshot.
        """
        metrics = self.get_window_metrics(window_sec=window_sec)
        return {
            'active': self.active,
            'movement_distance': metrics['total_movement_distance'],
            'movement_distance_per_min': metrics['movement_distance_per_minute'],
            'jitter': metrics['jitter_score'],
            'jitter_score': metrics['jitter_score'],
            'clicks': self.total_clicks,
            'recent_clicks': metrics['click_count'],
            'click_rate': metrics['click_rate'],
            'straightness': metrics['straightness'],
            'idle': metrics['conditions']['mouse_idle'],
            'strong_idle': metrics['conditions']['strong_idle'],
            'active_mouse_ratio': metrics['active_mouse_ratio'],
            'conditions': metrics['conditions']
        }
