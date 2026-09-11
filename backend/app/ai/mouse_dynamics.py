"""
Mouse Dynamics Estimator.

Consumes a short window of raw mouse events (x, y, timestamp, click) and
estimates emotional/cognitive state from movement patterns: velocity,
jitter (micro-corrections), idle time, and click rate.

Rapid, erratic, high-jitter movement with a high click rate tends to
correlate with frustration; long idle stretches with occasional slow
movement correlate with fatigue or deep reading/thinking (context
disambiguates which, at the fusion/decision layer).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from math import hypot
from statistics import mean, pstdev
from typing import List, Optional

from app.ai.base import EmotionEstimator, EmotionEstimate, normalize


@dataclass
class MouseEvent:
    x: float
    y: float
    timestamp: float
    is_click: bool = False


@dataclass
class MouseBaseline:
    velocity_mean: float = 250.0   # px/sec, population default
    velocity_var: float = 150.0 ** 2


IDLE_GAP_THRESHOLD_SECONDS = 3.0
MIN_EVENTS_FOR_ESTIMATE = 5


class MouseDynamicsEstimator(EmotionEstimator):
    modality_name = "mouse"

    def estimate(
        self,
        events: List[MouseEvent],
        baseline: Optional[MouseBaseline] = None,
    ) -> EmotionEstimate:
        baseline = baseline or MouseBaseline()

        if len(events) < MIN_EVENTS_FOR_ESTIMATE:
            return self._insufficient_data_estimate(
                f"only {len(events)} mouse events, need >= {MIN_EVENTS_FOR_ESTIMATE}"
            )

        events = sorted(events, key=lambda e: e.timestamp)

        velocities: List[float] = []
        direction_changes = 0
        prev_angle = None
        idle_seconds = 0.0

        for a, b in zip(events, events[1:]):
            dt = b.timestamp - a.timestamp
            if dt <= 0:
                continue
            dist = hypot(b.x - a.x, b.y - a.y)
            velocities.append(dist / dt)

            if dt > IDLE_GAP_THRESHOLD_SECONDS:
                idle_seconds += dt

            if dist > 1e-3:
                angle = math.atan2(b.y - a.y, b.x - a.x)
                if prev_angle is not None:
                    delta = abs(angle - prev_angle)
                    if delta > 1.2:  # ~70 degrees: a sharp direction reversal / jitter
                        direction_changes += 1
                prev_angle = angle

        if not velocities:
            return self._insufficient_data_estimate("no measurable movement between events")

        mean_velocity = mean(velocities)
        velocity_std = pstdev(velocities) if len(velocities) > 1 else 0.0
        click_rate = sum(1 for e in events if e.is_click) / len(events)
        jitter_rate = direction_changes / max(1, len(velocities))
        total_duration = events[-1].timestamp - events[0].timestamp
        idle_fraction = (idle_seconds / total_duration) if total_duration > 0 else 0.0

        velocity_z = _safe_z(mean_velocity, baseline.velocity_mean, baseline.velocity_var)

        scores = {
            "frustrated": jitter_rate * 2.0 + click_rate * 1.5 + max(0.0, velocity_z) * 0.3,
            "focused": max(0.0, 1 - jitter_rate * 1.5) * (1 - idle_fraction) * 0.8,
            "flow": max(0.0, 1 - jitter_rate) * max(0.0, min(1.0, 1 - abs(velocity_z) * 0.3)),
            "fatigued": idle_fraction * 1.2 + max(0.0, -velocity_z) * 0.3,
            "relaxed": (1 - jitter_rate) * max(0.0, -velocity_z * 0.2) * 0.6,
            "confused": jitter_rate * 1.0 * (1 - click_rate),
        }

        vector = normalize(scores)
        confidence = min(1.0, len(events) / 30.0)

        return EmotionEstimate(
            vector=vector,
            confidence=confidence,
            modality=self.modality_name,
            details={
                "mean_velocity_px_per_sec": round(mean_velocity, 2),
                "velocity_std": round(velocity_std, 2),
                "click_rate": round(click_rate, 3),
                "jitter_rate": round(jitter_rate, 3),
                "idle_fraction": round(idle_fraction, 3),
                "n_events": len(events),
            },
        )


def _safe_z(value: float, mean_: float, var_: float) -> float:
    std = var_ ** 0.5 if var_ > 0 else 1e-6
    return (value - mean_) / std
