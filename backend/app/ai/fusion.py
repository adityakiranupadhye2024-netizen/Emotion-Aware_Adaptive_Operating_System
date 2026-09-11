"""
Emotion Fusion Engine.

Combines an arbitrary subset of per-modality EmotionEstimates into a single
E(t) — the emotion component of the Adaptive State Score. Modalities are
weighted by their own reported confidence AND a fixed per-modality prior
weight (facial signal, when available, is generally more diagnostic than
mouse jitter alone), then temporally smoothed with an exponential moving
average so a single noisy frame can't whiplash the estimate.

This is the piece of Module 1's architecture diagram between "Emotion
Recognition AI" and "Adaptive State Score Fusion" — it produces exactly the
E(t) vector the ASS formula in the research docs consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.ai.base import ALL_LABELS, EmotionEstimate, normalize

# Per-modality prior weight (before confidence weighting). Reflects that,
# all else equal, facial affect is more directly diagnostic of emotion than
# behavioral proxies — but this is a prior, not a hard rule: a highly
# confident keyboard/mouse estimate can still dominate a low-confidence
# facial read (e.g. poor lighting, face partially out of frame).
MODALITY_PRIOR_WEIGHTS = {
    "facial": 1.5,
    "keyboard": 1.0,
    "mouse": 0.8,
}

DEFAULT_EMA_ALPHA = 0.35  # weight given to the new observation vs. running history


@dataclass
class FusionResult:
    vector: Dict[str, float]
    overall_confidence: float
    modalities_used: List[str]
    per_modality: Dict[str, Dict[str, float]] = field(default_factory=dict)


class EmotionFusionEngine:
    def __init__(self, ema_alpha: float = DEFAULT_EMA_ALPHA):
        self.ema_alpha = ema_alpha
        self._smoothed_vector: Optional[Dict[str, float]] = None

    def reset(self) -> None:
        """Call when starting a new session / switching users, so history
        from a different context doesn't leak into the new EMA."""
        self._smoothed_vector = None

    def fuse(self, estimates: List[EmotionEstimate]) -> FusionResult:
        usable = [e for e in estimates if e.confidence > 0.0]

        if not usable:
            # No usable signal this tick: hold the previous smoothed estimate
            # if we have one, otherwise fall back to a uniform/neutral read.
            fallback = self._smoothed_vector or {label: 1.0 / len(ALL_LABELS) for label in ALL_LABELS}
            return FusionResult(vector=fallback, overall_confidence=0.0, modalities_used=[])

        combined = {label: 0.0 for label in ALL_LABELS}
        total_weight = 0.0
        per_modality: Dict[str, Dict[str, float]] = {}

        for est in usable:
            prior = MODALITY_PRIOR_WEIGHTS.get(est.modality, 1.0)
            weight = prior * est.confidence
            total_weight += weight
            per_modality[est.modality] = {"confidence": est.confidence, "weight": weight}
            for label in ALL_LABELS:
                combined[label] += est.vector.get(label, 0.0) * weight

        if total_weight > 0:
            combined = {label: v / total_weight for label, v in combined.items()}
        raw_fused = normalize(combined)

        # Temporal smoothing (EMA) so a single noisy tick doesn't cause a
        # visible jump on the dashboard graph or trigger an unwarranted action.
        if self._smoothed_vector is None:
            smoothed = raw_fused
        else:
            smoothed = {
                label: self.ema_alpha * raw_fused[label] + (1 - self.ema_alpha) * self._smoothed_vector[label]
                for label in ALL_LABELS
            }
            smoothed = normalize(smoothed)
        self._smoothed_vector = smoothed

        # Overall confidence: weighted average of modality confidences,
        # scaled down when few modalities are contributing (fewer independent
        # signals = less reliable fused estimate even if each is confident).
        avg_confidence = sum(e.confidence for e in usable) / len(usable)
        coverage_factor = min(1.0, len(usable) / 3.0)  # saturates once all 3 modalities present
        overall_confidence = round(avg_confidence * (0.6 + 0.4 * coverage_factor), 4)

        return FusionResult(
            vector=smoothed,
            overall_confidence=overall_confidence,
            modalities_used=[e.modality for e in usable],
            per_modality=per_modality,
        )
