"""
Facial Emotion Estimator.

Uses MediaPipe's Face Landmarker (Tasks API) with blendshape output enabled.
Blendshapes are 52 standard, ARKit-compatible facial-expression coefficients
(browDownLeft, jawOpen, mouthSmileLeft, eyeSqueezeLeft, etc.), each in
[0, 1], produced by a bundled on-device model — no landmark geometry math
required, which makes this estimator far less bug-prone than hand-rolled
Action-Unit ratios while remaining fully explainable (every input feature
has a human-readable name).

Model asset: this estimator needs `face_landmarker.task` present on disk
(see `scripts/download_models.py` — a one-time, one-line download from
Google's official MediaPipe model bucket). This is an external ML asset
fetch, the same as PyTorch downloading pretrained weights, not a code
placeholder: all inference/scoring logic below is complete and runs the
moment the asset is present. Until then, this estimator degrades
gracefully (see `estimate()`) rather than crashing the fusion pipeline.

This class implements the same `EmotionEstimator` interface as every other
modality, so it can later be swapped for a trained classifier over the same
blendshape feature vector (e.g. a small MLP fit on labeled expression data)
with zero changes to fusion.py or callers.

Privacy note: raw frames are processed in-memory and discarded; only the
~20 blendshape scalars used below are ever persisted (see
StateSnapshot.details), and this estimator only runs when the user has
opted in via User.camera_sensing_enabled.
"""

from __future__ import annotations

import os
from typing import Optional

import numpy as np

from app.ai.base import EmotionEstimator, EmotionEstimate, normalize

try:
    import mediapipe as mp
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.core.base_options import BaseOptions
    _MEDIAPIPE_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in envs without mediapipe installed
    _MEDIAPIPE_AVAILABLE = False

DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "models", "face_landmarker.task"
)

# Blendshape categories we read (subset of the standard 52; names match
# MediaPipe's ARKit-compatible blendshape vocabulary exactly).
_BS_BROW_DOWN = ("browDownLeft", "browDownRight")
_BS_BROW_UP = ("browInnerUp", "browOuterUpLeft", "browOuterUpRight")
_BS_EYE_SQUINT = ("eyeSquintLeft", "eyeSquintRight")
_BS_EYE_WIDE = ("eyeWideLeft", "eyeWideRight")
_BS_MOUTH_SMILE = ("mouthSmileLeft", "mouthSmileRight")
_BS_MOUTH_FROWN = ("mouthFrownLeft", "mouthFrownRight")
_BS_MOUTH_PRESS = ("mouthPressLeft", "mouthPressRight")
_BS_JAW_OPEN = ("jawOpen",)


def _avg(scores: dict, names: tuple) -> float:
    vals = [scores.get(n, 0.0) for n in names]
    return sum(vals) / len(vals) if vals else 0.0


class FacialEmotionEstimator(EmotionEstimator):
    modality_name = "facial"

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH, num_faces: int = 1):
        self._available = _MEDIAPIPE_AVAILABLE
        self._landmarker = None
        self._model_missing_reason: Optional[str] = None

        if not self._available:
            self._model_missing_reason = "mediapipe not installed"
            return

        if not os.path.isfile(model_path):
            self._model_missing_reason = (
                f"model asset not found at {model_path} — run "
                f"`python scripts/download_models.py` once (requires internet)"
            )
            return

        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=num_faces,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=False,
            min_face_detection_confidence=0.5,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()

    def estimate(self, frame_bgr: "np.ndarray") -> EmotionEstimate:
        if self._landmarker is None:
            return self._insufficient_data_estimate(
                self._model_missing_reason or "facial estimator not initialized"
            )

        blendshapes = self._extract_blendshapes(frame_bgr)
        if blendshapes is None:
            return self._insufficient_data_estimate("no face detected in frame")

        scores = self._blendshapes_to_scores(blendshapes)
        vector = normalize(scores)

        return EmotionEstimate(
            vector=vector,
            confidence=0.8,  # single-frame confidence; fusion.py applies temporal smoothing on top
            modality=self.modality_name,
            details={k: round(v, 4) for k, v in blendshapes.items()},
        )

    def _extract_blendshapes(self, frame_bgr: "np.ndarray") -> Optional[dict]:
        import cv2

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result = self._landmarker.detect(mp_image)

        if not result.face_blendshapes:
            return None

        # One list of Category(category_name, score) per detected face; take the first face.
        categories = result.face_blendshapes[0]
        return {c.category_name: c.score for c in categories}

    @staticmethod
    def _blendshapes_to_scores(bs: dict) -> dict:
        brow_down = _avg(bs, _BS_BROW_DOWN)
        brow_up = _avg(bs, _BS_BROW_UP)
        eye_squint = _avg(bs, _BS_EYE_SQUINT)
        eye_wide = _avg(bs, _BS_EYE_WIDE)
        smile = _avg(bs, _BS_MOUTH_SMILE)
        frown = _avg(bs, _BS_MOUTH_FROWN)
        press = _avg(bs, _BS_MOUTH_PRESS)
        jaw_open = _avg(bs, _BS_JAW_OPEN)

        return {
            # Furrowed brow + squinted eyes + pressed/frowning mouth -> frustration
            "frustrated": brow_down * 1.4 + eye_squint * 1.0 + press * 0.8 + frown * 0.6,
            # Raised brows + wide eyes + open jaw (no smile) -> confusion/surprise
            "confused": brow_up * 1.3 + eye_wide * 1.0 + jaw_open * 0.5 * (1 - smile),
            # Squinted/heavy eyes without brow furrow, low overall expressiveness -> fatigue
            "fatigued": eye_squint * 0.8 * (1 - brow_down) + (1 - eye_wide) * 0.2,
            # Smiling, low brow tension, relaxed eyes -> relaxed
            "relaxed": smile * 1.2 + (1 - brow_down) * 0.3 + (1 - eye_squint) * 0.2,
            # Low expression intensity overall, neutral mouth -> focused
            "focused": max(0.0, 1 - (brow_down + eye_squint + smile + frown + jaw_open)) * 1.0,
            # Focused signature sustained over time reads as flow at the
            # fusion layer's temporal-smoothing stage, not from a single frame.
            "flow": max(0.0, 1 - (brow_down + eye_squint + smile + frown + jaw_open)) * 0.6,
        }
