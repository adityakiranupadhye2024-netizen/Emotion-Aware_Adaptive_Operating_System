import time, math
from collections import deque
try:
    from pynput import mouse
except Exception:
    mouse = None

class MouseSensor:
    def __init__(self):
        self.positions = deque(maxlen=200)       # (timestamp, x, y)
        self.clicks_history = deque(maxlen=100)  # timestamps
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

    def snapshot(self, window_sec: float = 10.0):
        now = time.time()
        recent_pts = [p for p in self.positions if now - p[0] <= window_sec]
        distance = 0.0
        jitter = 0.0

        if len(recent_pts) >= 2:
            dxs = []
            dys = []
            for a, b in zip(recent_pts, recent_pts[1:]):
                d = math.hypot(b[1] - a[1], b[2] - a[2])
                distance += d
                dxs.append(b[1] - a[1])
                dys.append(b[2] - a[2])

            # Directional reversals metric (frequent sharp back-and-forth = agitation/frustration)
            reversals = 0
            for i in range(1, len(dxs)):
                if (dxs[i] * dxs[i-1] < 0) or (dys[i] * dys[i-1] < 0):
                    reversals += 1
            jitter = reversals / max(1, len(dxs))

        recent_clicks = sum(1 for t in self.clicks_history if now - t <= window_sec)
        idle = (now - self.last_event > 6.0)

        return {
            'active': self.active,
            'movement_distance': round(distance, 1),
            'jitter': round(jitter, 3),
            'clicks': self.total_clicks,
            'recent_clicks': recent_clicks,
            'idle': idle
        }

