"""
Actions (adaptations) chosen and executed by the Decision Engine.

Each row is one "arm pull" of the contextual bandit: which action was
chosen, in what state, and (filled in later by feedback.py) how well it
was received. This is the training signal for the policy.
"""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column, String, DateTime, Float, JSON, ForeignKey

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ActionType(str, Enum):
    ENABLE_FOCUS_MODE = "enable_focus_mode"
    SILENCE_NOTIFICATIONS = "silence_notifications"
    PAUSE_UPDATES = "pause_updates"
    SUGGEST_BREAK = "suggest_break"
    ENABLE_DARK_MODE = "enable_dark_mode"
    REDUCE_BRIGHTNESS = "reduce_brightness"
    SUGGEST_DEBUG_RESOURCES = "suggest_debug_resources"
    RECOMMEND_AI_ASSISTANCE = "recommend_ai_assistance"
    DELAY_NOTIFICATIONS = "delay_notifications"
    NO_ACTION = "no_action"


class ActionLog(Base):
    __tablename__ = "action_log"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)
    state_snapshot_id = Column(String, ForeignKey("state_snapshots.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    action_type = Column(String, nullable=False)  # value of ActionType
    # Snapshot of the bandit's decision context, for offline policy analysis
    policy_context = Column(JSON, default=dict)
    chosen_probability = Column(Float, default=0.0)  # policy's own confidence/propensity
    was_auto_executed = Column(String, default="true")  # "true" = auto, "false" = suggested only

    # Denormalized outcome fields, updated once feedback arrives (see feedback.py)
    reward = Column(Float, nullable=True)
