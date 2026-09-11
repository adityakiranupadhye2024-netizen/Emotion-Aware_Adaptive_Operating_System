"""
Time-series state snapshots.

Each row is one "tick" of the sensing pipeline: the fused emotion vector,
context vector, workload estimate, and the resulting Adaptive State Score.
This table is what powers the real-time dashboard graph and the daily
analytics timeline.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Float, JSON, Index

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class StateSnapshot(Base):
    __tablename__ = "state_snapshots"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # E(t): emotion probability vector, e.g.
    # {"focused":0.62,"frustrated":0.05,"fatigued":0.10,"confused":0.03,"relaxed":0.12,"flow":0.08}
    emotion_vector = Column(JSON, nullable=False)
    emotion_confidence = Column(Float, default=0.0)  # aggregate confidence across modalities
    modalities_used = Column(JSON, default=list)  # e.g. ["facial","keyboard","mouse"]

    # C(t): context
    active_app = Column(String, nullable=True)
    activity_type = Column(String, nullable=True)  # coding | meeting | writing | studying | gaming | other
    context_vector = Column(JSON, default=dict)

    # W(t): workload estimate
    workload_score = Column(Float, default=0.0)  # 0..1
    error_rate = Column(Float, default=0.0)  # e.g. compile/exception frequency

    # Fused output
    adaptive_state_score = Column(Float, nullable=False)  # ASS(t)

    __table_args__ = (
        Index("ix_state_user_time", "user_id", "timestamp"),
    )
