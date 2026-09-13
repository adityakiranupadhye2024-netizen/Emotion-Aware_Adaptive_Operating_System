import time
import platform
import subprocess
import logging
from datetime import datetime, timezone
from app.core.config import settings
from app.db.database import record_notification

logger = logging.getLogger("eaos.notification")

class NotificationService:
    def __init__(self):
        self.system = platform.system()
        self.last_notified_action = None
        self.last_notified_time = 0.0

        # Notification Preferences (Feature 19)
        self.notify_os_changes = True
        self.notify_important_states = True
        self.notify_all_assessments = False

    def get_settings(self) -> dict:
        return {
            'notify_os_changes': self.notify_os_changes,
            'notify_important_states': self.notify_important_states,
            'notify_all_assessments': self.notify_all_assessments
        }

    def update_settings(self, prefs: dict):
        if 'notify_os_changes' in prefs:
            self.notify_os_changes = bool(prefs['notify_os_changes'])
        if 'notify_important_states' in prefs:
            self.notify_important_states = bool(prefs['notify_important_states'])
        if 'notify_all_assessments' in prefs:
            self.notify_all_assessments = bool(prefs['notify_all_assessments'])

    def send_adaptation_notification(
        self,
        action: str,
        reason: str,
        adaptive_score: float,
        detection_summary: str,
        camera_used: bool,
        cycle_id: int = 1,
        decision_id: int = None,
        context: str = "General",
        context_confidence: float = 0.80,
        force: bool = False,
        **kwargs
    ) -> dict:
        now_ts = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        action_clean = action.replace("_", " ").title()

        # Duplicate Prevention: 10s window (or never when forced)
        is_duplicate = (not force and action == self.last_notified_action and (now_ts - self.last_notified_time < 10) and action != "NO_ACTION")
        if is_duplicate:
            logger.info(f"Duplicate notification suppressed for {action}.")
            return {
                "decision_id": decision_id,
                "cycle_id": cycle_id,
                "timestamp": now_iso,
                "title": f"EAOS {action_clean}",
                "message": reason,
                "action": action,
                "adaptive_score": adaptive_score,
                "status": "suppressed_duplicate"
            }

        # Filtering according to configured triggers
        should_display_popup = False
        if action != "NO_ACTION":
            if self.notify_os_changes:
                should_display_popup = True
        else:
            if self.notify_all_assessments:
                should_display_popup = True

        if action == "NO_ACTION":
            title = "EAOS Assessment Complete"
            subtitle = f"5-Min Assessment #{cycle_id} · Context: {context}"
            message = (
                f"Adaptive Score: {adaptive_score:.2f} (Stable)\n"
                f"Context: {context}\n"
                f"Reason: {reason}\n"
                f"Next assessment in 05:00"
            )
        else:
            title = "EAOS Adaptation"
            subtitle = f"Action: {action_clean} · AS: {adaptive_score:.2f}"
            message = (
                f"Context: {context}\n"
                f"Action: {action_clean} applied\n"
                f"Reason: {reason}\n"
                f"Next assessment in 05:00"
            )

        delivery_status = "delivered" if should_display_popup else "suppressed_by_rule"

        if should_display_popup and self.system == "Darwin":
            try:
                clean_title = title.replace('"', '\\"')
                clean_sub = subtitle.replace('"', '\\"')
                clean_msg = message.replace('"', '\\"')
                sound_name = "Ping" if action != "NO_ACTION" else "default"
                script = f'display notification "{clean_msg}" with title "{clean_title}" subtitle "{clean_sub}" sound name "{sound_name}"'
                subprocess.run(["osascript", "-e", script], check=False, timeout=3)
                self.last_notified_action = action
                self.last_notified_time = now_ts
            except Exception as e:
                logger.warning(f"Failed to display macOS notification: {e}")
                delivery_status = f"failed: {e}"
        else:
            if should_display_popup:
                logger.info(f"[{self.system}] {title} - {subtitle}: {message}")
                self.last_notified_action = action
                self.last_notified_time = now_ts

        notif_record = {
            "decision_id": decision_id,
            "cycle_id": cycle_id,
            "timestamp": now_iso,
            "title": title,
            "message": message,
            "action": action,
            "adaptive_score": adaptive_score,
            "status": delivery_status
        }
        try:
            record_notification(notif_record)
        except Exception as e:
            logger.error(f"Failed to store notification in DB: {e}")

        return notif_record

notification_service = NotificationService()
