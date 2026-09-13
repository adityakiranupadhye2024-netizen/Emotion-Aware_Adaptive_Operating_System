import threading, time
from collections import deque
try:
    from pynput import keyboard
except Exception:
    keyboard = None

class KeyboardSensor:
    def __init__(self):
        self.events_history = deque(maxlen=300) # (timestamp, is_backspace)
        self.intervals = deque(maxlen=60)        # intervals between consecutive keystrokes (seconds)
        self.last_press_time = None
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

        if self.last_press_time is not None:
            dt = now - self.last_press_time
            if dt < 4.0:  # ignore long idle pauses
                self.intervals.append(dt)
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

    def snapshot(self, window_sec: float = 10.0):
        now = time.time()
        recent = [ev for ev in self.events_history if now - ev[0] <= window_sec]
        recent_count = len(recent)
        recent_backspaces = sum(1 for ev in recent if ev[1])

        typing_rate = recent_count / max(1.0, window_sec)
        backspace_rate = (recent_backspaces / recent_count) if recent_count > 0 else 0.0

        vals = list(self.intervals)
        avg_interval = (sum(vals) / len(vals)) if vals else 0.0

        return {
            'active': self.active,
            'events': self.total_events,
            'recent_events': recent_count,
            'avg_inter_key_interval': round(avg_interval, 3),
            'typing_rate': round(typing_rate, 2),
            'backspace_rate': round(backspace_rate, 3)
        }

