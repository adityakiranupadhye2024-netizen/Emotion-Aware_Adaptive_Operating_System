import os
import platform
import subprocess
import time
import logging
from typing import Tuple, Dict, Any, List, Optional
import psutil
from app.db.database import record_context_observation

logger = logging.getLogger("eaos.context")

# Canonical EAOS Contexts:
# CODING, STUDYING, WRITING, MEETING, BROWSING, GAMING, IDLE, GENERAL_WORK, UNKNOWN

class ContextSensor:
    def __init__(self):
        self.session_start = time.time()
        self.last_app: Optional[str] = None
        self.last_context = "UNKNOWN"
        self.last_confidence = 0.50
        self.context_start_time = time.time()
        self.actual_app_switches = 0
        self.app_switch_history: List[float] = []  # Timestamps of actual app transitions
        self.last_db_record_time = 0.0
        self.last_update_time = time.time()

    def active_app(self) -> str:
        system = platform.system()
        if system == 'Darwin':
            try:
                script = 'tell application "System Events" to get name of first application process whose frontmost is true'
                res = subprocess.check_output(['osascript', '-e', script], text=True, timeout=1).strip()
                return res or 'Unknown'
            except Exception:
                return 'Unknown'
        return 'Unknown'

    def classify_with_behaviour(
        self,
        app: str,
        kb_rate: float = 0.0,
        mouse_clicks: int = 0,
        mouse_idle: bool = False,
        idle_seconds: float = 0.0,
        kb_idle_seconds: float = 0.0,
        mouse_idle_seconds: float = 0.0
    ) -> Tuple[str, float]:
        """
        Combines frontmost application with behavioral telemetry (typing rate, mouse interaction, idleness)
        to assign a canonical EAOS context and a truthful confidence level (0.00 – 1.00).
        """
        if not app or app.lower() in ['unknown', '']:
            return ('UNKNOWN', 0.35)

        effective_kb_idle = max(idle_seconds, kb_idle_seconds)
        effective_mouse_idle = max(idle_seconds, mouse_idle_seconds)

        # IDLE Conditions:
        # STRONG IDLE: keyboard inactivity >= 25 s AND mouse inactivity >= 25 s
        if effective_kb_idle >= 25.0 and (effective_mouse_idle >= 25.0 or mouse_idle):
            return ('IDLE', 0.95)
        # IDLE: keyboard inactivity >= 15 s AND mouse inactivity >= 15 s
        if effective_kb_idle >= 15.0 and (effective_mouse_idle >= 15.0 or mouse_idle):
            return ('IDLE', 0.88)

        s = app.lower()

        # 1. MEETING (takes precedence for safety)
        if any(x in s for x in ['zoom', 'teams', 'meet', 'webex', 'facetime', 'skype', 'discord', 'slack']):
            return ('MEETING', 0.92)

        # 2. GAMING
        if any(x in s for x in ['steam', 'epic', 'game', 'minecraft', 'roblox', 'unity', 'unreal']):
            return ('GAMING', 0.90)

        # 3. CODING
        if any(x in s for x in ['code', 'cursor', 'pycharm', 'intellij', 'xcode', 'clion', 'webstorm', 'terminal', 'iterm', 'vim', 'nvim', 'sublime', 'goland']):
            if kb_rate > 0.4:
                return ('CODING', 0.93)
            elif not mouse_idle:
                return ('CODING', 0.86)
            return ('CODING', 0.80)

        # 4. WRITING
        if any(x in s for x in ['word', 'pages', 'notion', 'docs', 'obsidian', 'notes', 'scrivener', 'typora', 'writer']):
            if kb_rate > 0.5:
                return ('WRITING', 0.90)
            return ('WRITING', 0.80)

        # 5. STUDYING
        if any(x in s for x in ['acrobat', 'reader', 'preview', 'pdf', 'kindle', 'books', 'scholar', 'anki']):
            return ('STUDYING', 0.86)

        # 6. BROWSING
        if any(x in s for x in ['chrome', 'safari', 'firefox', 'edge', 'arc', 'brave', 'opera']):
            if kb_rate > 1.2:
                # Heavy typing in browser (e.g. online doc or editor)
                return ('WRITING', 0.75)
            return ('BROWSING', 0.84)

        # 7. GENERAL WORK fallback
        return ('GENERAL_WORK', 0.60)

    classify = classify_with_behaviour

    def system_metrics(self) -> Dict[str, Any]:
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            pids = len(psutil.pids())
            return {'cpu': round(cpu, 1), 'memory': round(mem, 1), 'processes': pids}
        except Exception:
            return {'cpu': 10.0, 'memory': 50.0, 'processes': 100}

    def snapshot(
        self,
        kb_rate: float = 0.0,
        mouse_clicks: int = 0,
        mouse_idle: bool = False,
        idle_seconds: float = 0.0,
        kb_idle_seconds: float = 0.0,
        mouse_idle_seconds: float = 0.0
    ) -> Dict[str, Any]:
        now = time.time()
        self.last_update_time = now
        app = self.active_app()

        # Count actual app transitions: if app_previous != app_current
        if self.last_app is not None and app != self.last_app:
            self.actual_app_switches += 1
            self.app_switch_history.append(now)

        # Retain switches in last 60 seconds for 1-minute rate calculation
        self.app_switch_history = [t for t in self.app_switch_history if now - t <= 60.0]
        switches_in_last_min = len(self.app_switch_history)
        app_switch_rate = float(switches_in_last_min)  # switches per minute

        # Switching condition levels:
        # LOW: < 1 switch/min, MODERATE: 1-2, HIGH: 2-4, VERY HIGH: > 4
        switch_level = 'LOW'
        if app_switch_rate > 4.0:
            switch_level = 'VERY_HIGH'
        elif app_switch_rate >= 2.0:
            switch_level = 'HIGH'
        elif app_switch_rate >= 1.0:
            switch_level = 'MODERATE'

        context, conf = self.classify_with_behaviour(
            app=app,
            kb_rate=kb_rate,
            mouse_clicks=mouse_clicks,
            mouse_idle=mouse_idle,
            idle_seconds=idle_seconds,
            kb_idle_seconds=kb_idle_seconds,
            mouse_idle_seconds=mouse_idle_seconds
        )

        if context != self.last_context:
            self.last_context = context
            self.context_start_time = now

        context_session_minutes = max(1, int((now - self.context_start_time) / 60.0))
        total_session_seconds = max(1, int(now - self.session_start))

        # Log observation to database periodically or when app changes
        if (now - self.last_db_record_time >= 60.0) or (app != self.last_app):
            try:
                record_context_observation(app, context, conf, context_session_minutes)
                self.last_db_record_time = now
            except Exception as e:
                logger.warning(f"Failed to record context observation: {e}")

        self.last_app = app
        self.last_confidence = conf
        metrics = self.system_metrics()

        return {
            'active_app': app,
            'window_title': app,
            'activity': context,
            'context': context,
            'confidence': round(conf, 2),
            'context_confidence': round(conf, 2),
            'session_duration': total_session_seconds,
            'context_duration_minutes': context_session_minutes,
            'app_switch_count': self.actual_app_switches,
            'app_switch_rate': round(app_switch_rate, 2),
            'app_switch_level': switch_level,
            'calendar_state': 'In Meeting' if context == 'MEETING' else 'Free',
            'system_load': metrics
        }
