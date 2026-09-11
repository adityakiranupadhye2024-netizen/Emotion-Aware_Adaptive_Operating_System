"""
User and per-user personalization baseline (H(t) in the ASS formula).

A single-user desktop install still gets a `User` row — this keeps the
schema identical if multi-profile support is ever added, and gives the
Personalization Engine a stable place to store learned baselines.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Float, JSON, ForeignKey
from sqlalchemy.orm import relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    display_name = Column(String, nullable=False, default="Default User")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Privacy toggles (mirrors core/config.py defaults, but overridable per-user)
    camera_sensing_enabled = Column(String, default="false")  # "true"/"false" for simple JSON-free storage
    keyboard_dynamics_enabled = Column(String, default="true")
    mouse_dynamics_enabled = Column(String, default="true")
    app_context_enabled = Column(String, default="true")

    baseline = relationship("UserBaseline", back_populates="user", uselist=False)


class UserBaseline(Base):
    """
    Learned behavioral baseline — the H(t) component of the Adaptive State
    Score. Updated incrementally (running mean/variance) by the
    Personalization Engine as new sensor data arrives.
    """

    __tablename__ = "user_baselines"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    # Running statistics for behavioral signals (mean/variance updated online)
    typing_speed_mean = Column(Float, default=0.0)
    typing_speed_var = Column(Float, default=0.0)
    keystroke_interval_mean = Column(Float, default=0.0)
    keystroke_interval_var = Column(Float, default=0.0)
    mouse_velocity_mean = Column(Float, default=0.0)
    mouse_velocity_var = Column(Float, default=0.0)
    app_switch_rate_mean = Column(Float, default=0.0)
    app_switch_rate_var = Column(Float, default=0.0)
    typical_break_interval_minutes = Column(Float, default=45.0)

    sample_count = Column(Float, default=0.0)  # number of observations folded in
    last_updated = Column(DateTime, default=datetime.utcnow)

    # Free-form extension slot for additional learned parameters without migrations
    extra = Column(JSON, default=dict)

    user = relationship("User", back_populates="baseline")
