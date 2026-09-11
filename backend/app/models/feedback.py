"""
Feedback (explicit + implicit) used to compute reward for the Decision Engine.

Explicit: user taps 👍/👎 on a recommendation card in the dashboard.
Implicit: the action was reverted within N seconds, or a workload/error-rate
improvement was observed in the following state snapshots.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Float, ForeignKey, Boolean

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(String, primary_key=True, default=_uuid)
    action_id = Column(String, ForeignKey("action_log.id"), nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Explicit signal
    explicit_rating = Column(Float, nullable=True)  # +1 (helpful), -1 (not helpful), null if none given

    # Implicit signals
    was_reverted = Column(Boolean, default=False)
    seconds_until_reverted = Column(Float, nullable=True)
    post_action_workload_delta = Column(Float, nullable=True)  # negative = workload improved

    # Final computed reward fed back into the bandit (combination of the above)
    computed_reward = Column(Float, nullable=True)
