"""
Keystroke Dynamics Estimator.

Consumes a short window of raw key events (key, timestamp, is_backspace)
and estimates emotional/cognitive state from typing *rhythm* rather than
content — no keylogging of what was typed, only timing and error-correction
behavior, which is enough signal and keeps this privacy-respecting by
construction.

Signals used:
  - typing speed (chars/sec)
  - inter-keystroke interval variability (burstiness)
  - backspace/correction rate
  - long-pause frequency (thinking/stuck pauses)

All raw thresholds are compared against the user's personal baseline
(UserBaseline row) rather than fixed population constants, which is what
makes this personalized rather than a rule table.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev
from typing import List, Optional

from app.ai.base import EmotionEstimator, EmotionEstimate, normalize


@dataclass
class KeyEvent:
    timestamp: float          # seconds, monotonic clock
    is_backspace: bool = False
    is_navigation: bool = False  # arrow keys, etc. — excluded from "typing speed" but counted for restlessness


@dataclass
class KeystrokeBaseline:
    """Subset of UserBaseline relevant to this modality (decoupled from the
    ORM model so this file has no DB dependency and is trivially unit-testable)."""

    typing_speed_mean: float = 4.0        # keys/sec, reasonable population default
    typing_speed_var: float = 2.0
    keystroke_interval_mean: float = 0.20  # seconds between keys
    keystroke_interval_var: float = 0.05


LONG_PAUSE_THRESHOLD_SECONDS = 2.5
MIN_EVENTS_FOR_ESTIMATE = 6


class KeystrokeDynamicsEstimator(EmotionEstimator):
    modality_name = "keyboard"

    def estimate(
        self,
        events: List[KeyEvent],
        baseline: Optional[KeystrokeBaseline] = None,
    ) -> EmotionEstimate:
        baseline = baseline or KeystrokeBaseline()

        if len(events) < MIN_EVENTS_FOR_ESTIMATE:
            return self._insufficient_data_estimate(
                f"only {len(events)} key events, need >= {MIN_EVENTS_FOR_ESTIMATE}"
            )

        events = sorted(events, key=lambda e: e.timestamp)
        intervals = [b.timestamp - a.timestamp for a, b in zip(events, events[1:])]
        intervals = [i for i in intervals if i >= 0]

        if not intervals:
            return self._insufficient_data_estimate("no valid positive intervals")

        mean_interval = mean(intervals)
        interval_std = pstdev(intervals) if len(intervals) > 1 else 0.0
        typing_speed = 1.0 / mean_interval if mean_interval > 0 else 0.0

        backspace_rate = sum(1 for e in events if e.is_backspace) / len(events)
        long_pauses = sum(1 for i in intervals if i > LONG_PAUSE_THRESHOLD_SECONDS)
        long_pause_rate = long_pauses / len(intervals)

        # Z-scores relative to this user's personal baseline
        speed_z = _safe_z(typing_speed, baseline.typing_speed_mean, baseline.typing_speed_var)
        interval_var_z = _safe_z(interval_std, baseline.keystroke_interval_var, baseline.keystroke_interval_var or 0.05)

        scores = {
            # Fast, steady typing close to or above baseline, low backspace rate -> focused/flow
            "flow": max(0.0, speed_z) * (1 - backspace_rate) * (1 - long_pause_rate),
            "focused": max(0.0, 1 - abs(speed_z)) * (1 - backspace_rate),
            # High backspace rate + erratic intervals -> frustration
            "frustrated": backspace_rate * 3.0 + max(0.0, interval_var_z) * 0.5,
            # Frequent long pauses without high backspace -> confusion (thinking, stuck)
            "confused": long_pause_rate * 2.0 * (1 - backspace_rate),
            # Typing noticeably slower than baseline with rising pause rate -> fatigue
            "fatigued": max(0.0, -speed_z) * 0.8 + long_pause_rate * 0.5,
            # Slow but calm, low backspace, low variance -> relaxed
            "relaxed": max(0.0, -speed_z * 0.3) * (1 - backspace_rate) * (1 - long_pause_rate) * 0.5,
        }

        vector = normalize(scores)

        # Confidence grows with sample size, saturating around ~40 events
        confidence = min(1.0, len(events) / 40.0)

        return EmotionEstimate(
            vector=vector,
            confidence=confidence,
            modality=self.modality_name,
            details={
                "typing_speed_keys_per_sec": round(typing_speed, 3),
                "interval_std": round(interval_std, 3),
                "backspace_rate": round(backspace_rate, 3),
                "long_pause_rate": round(long_pause_rate, 3),
                "n_events": len(events),
            },
        )


def _safe_z(value: float, mean_: float, var_: float) -> float:
    std = var_ ** 0.5 if var_ > 0 else 1e-6
    return (value - mean_) / std
