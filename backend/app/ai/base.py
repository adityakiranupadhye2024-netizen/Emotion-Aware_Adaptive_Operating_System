"""
Shared types for the Emotion Recognition AI module.

Every modality (facial, keystroke, mouse) implements the same
`EmotionEstimator` interface and returns an `EmotionEstimate`. This is what
lets the Fusion Engine (fusion.py) combine an arbitrary subset of available
modalities — including exactly one, if the user has opted out of the
others — without special-casing each combination.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict


class EmotionLabel(str, Enum):
    FOCUSED = "focused"
    FRUSTRATED = "frustrated"
    FATIGUED = "fatigued"
    CONFUSED = "confused"
    RELAXED = "relaxed"
    FLOW = "flow"


ALL_LABELS = [e.value for e in EmotionLabel]


def uniform_vector(value: float = 1.0 / len(ALL_LABELS)) -> Dict[str, float]:
    return {label: value for label in ALL_LABELS}


def normalize(vector: Dict[str, float]) -> Dict[str, float]:
    """Renormalize a raw score dict into a proper probability distribution
    over ALL_LABELS. Missing labels default to 0; negative scores are
    clipped to 0 before normalizing (these are probabilities, not logits)."""
    clipped = {label: max(0.0, vector.get(label, 0.0)) for label in ALL_LABELS}
    total = sum(clipped.values())
    if total <= 1e-9:
        return uniform_vector()
    return {label: score / total for label, score in clipped.items()}


@dataclass
class EmotionEstimate:
    """Output of a single modality's inference."""

    vector: Dict[str, float]              # probability distribution over ALL_LABELS
    confidence: float                     # 0..1, this modality's self-reported reliability
    modality: str                         # "facial" | "keyboard" | "mouse"
    details: Dict[str, object] = field(default_factory=dict)  # raw features, for debugging/analytics

    def __post_init__(self):
        self.vector = normalize(self.vector)
        self.confidence = min(1.0, max(0.0, self.confidence))


class EmotionEstimator(ABC):
    """Common interface every modality-specific estimator implements."""

    modality_name: str

    @abstractmethod
    def estimate(self, *args, **kwargs) -> EmotionEstimate:
        """Produce an EmotionEstimate from this modality's raw input.
        Must return a low-confidence uniform estimate rather than raising
        when the input is insufficient (e.g. no face detected), so the
        fusion engine can down-weight it cleanly instead of special-casing
        exceptions per modality."""
        raise NotImplementedError

    def _insufficient_data_estimate(self, reason: str) -> EmotionEstimate:
        return EmotionEstimate(
            vector=uniform_vector(),
            confidence=0.0,
            modality=self.modality_name,
            details={"reason": reason},
        )
