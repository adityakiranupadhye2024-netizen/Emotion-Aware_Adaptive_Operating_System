import os, platform, subprocess, time
import logging
import psutil
from typing import Tuple, Dict, Any
from app.db.database import record_context_observation

logger = logging.getLogger("eaos.context")

# Canonical EAOS Contexts
# CODING, STUDYING, WRITING, MEETING, BROWSING, GAMING, IDLE, GENERAL_WORK, UNKNOWN

class ContextSensor:
    def __init__(self):
        self.session_start = time.time()
        self.last_app = None
        self.last_context = "UNKNOWN"
        self.last_confidence = 0.50
        self.context_start_time = time.time()
        self.switches = 0
        self.window_switches_recent = []
        self.last_db_record_time = 0.0

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
        idle_seconds: float = 0.0
    ) -> Tuple[str, float]:
        """
        Combines frontmost application with behavioral telemetry (typing rate, mouse interaction, idleness)
        to assign a canonical EAOS context and a truthful confidence level (0.00 – 1.00).
        """
        if not app or app.lower() in ['unknown', '']:
            return ('UNKNOWN', 0.35)

        # If user has had no interaction for >45s, classify as IDLE
        if idle_seconds > 45.0 and mouse_idle:
            return ('IDLE', 0.90)

        s = app.lower()

        # 1. CODING
        if any(x in s for x in ['code', 'cursor', 'pycharm', 'intellij', 'terminal', 'iterm', 'xcode', 'sublime', 'vim', 'nvim', 'clion', 'webstorm', 'goland']):
            if kb_rate > 0.4:
                return ('CODING', 0.92)
            elif not mouse_idle:
                return ('CODING', 0.85)
            return ('CODING', 0.78)

        # 2. MEETING
        if any(x in s for x in ['zoom', 'teams', 'meet', 'webex', 'slack', 'facetime', 'skype', 'discord']):
            return ('MEETING', 0.88)

        # 3. WRITING
        if any(x in s for x in ['word', 'pages', 'notion', 'docs', 'writer', 'obsidian', 'notes', 'scrivener', 'typora']):
            if kb_rate > 0.5:
                return ('WRITING', 0.90)
            return ('WRITING', 0.78)

        # 4. STUDYING
        if any(x in s for x in ['acrobat', 'reader', 'preview', 'pdf', 'kindle', 'books', 'scholar', 'anki']):
            return ('STUDYING', 0.85)

        # 5. BROWSING
        if any(x in s for x in ['chrome', 'safari', 'firefox', 'edge', 'arc', 'brave', 'opera']):
            if kb_rate > 1.2:
                # Heavy typing in browser (e.g. online editor or web docs)
                return ('WRITING', 0.72)
            return ('BROWSING', 0.82)

        # 6. GAMING
        if any(x in s for x in ['steam', 'epic', 'game', 'minecraft', 'roblox', 'unity', 'unreal']):
            return ('GAMING', 0.90)

        # 7. GENERAL WORK fallback
        return ('GENERAL_WORK', 0.60)

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
        idle_seconds: float = 0.0
    ) -> Dict[str, Any]:
        now = time.time()
        app = self.active_app()

        if self.last_app and app != self.last_app:
            self.switches += 1
            self.window_switches_recent.append(now)

        # Retain switches in last 5 minutes
        self.window_switches_recent = [t for t in self.window_switches_recent if now - t <= 300]
        recent_switch_rate = len(self.window_switches_recent) / 5.0

        context, conf = self.classify_with_behaviour(
            app=app,
            kb_rate=kb_rate,
            mouse_clicks=mouse_clicks,
            mouse_idle=mouse_idle,
            idle_seconds=idle_seconds
        )

        if context != self.last_context:
            self.last_context = context
            self.context_start_time = now

        context_session_minutes = max(1, int((now - self.context_start_time) / 60.0))
        total_session_seconds = max(1, int(now - self.session_start))

        # Log observation to database periodically (every 60 seconds) or when app changes
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
            'app_switch_rate': round(recent_switch_rate, 2),
            'calendar_state': 'In Meeting' if context == 'MEETING' else 'Free',
            'system_load': metrics
        }

