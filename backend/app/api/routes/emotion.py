"""
/emotion endpoints — Module 2's surface area.

Accepts batches of keystroke/mouse events (and, optionally, a base64 JPEG
frame if the user has camera sensing enabled) and returns the fused E(t)
vector plus per-modality breakdowns for transparency in the dashboard's
"AI confidence score" panel.

A process-lifetime FusionEngine instance is kept per server process so the
EMA temporal smoothing (see fusion.py) persists across requests within a
session — this is acceptable for a single-user desktop app; a multi-user
deployment would key this dict by user_id (already stubbed below).
"""

from __future__ import annotations

import base64
from typing import Dict, List, Optional

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.ai.base import EmotionEstimate
from app.ai.facial_emotion import FacialEmotionEstimator
from app.ai.fusion import EmotionFusionEngine
from app.ai.keystroke_dynamics import KeyEvent, KeystrokeBaseline, KeystrokeDynamicsEstimator
from app.ai.mouse_dynamics import MouseBaseline, MouseDynamicsEstimator, MouseEvent

router = APIRouter(prefix="/emotion", tags=["emotion"])

_facial_estimator = FacialEmotionEstimator()
_keystroke_estimator = KeystrokeDynamicsEstimator()
_mouse_estimator = MouseDynamicsEstimator()
_fusion_engines: Dict[str, EmotionFusionEngine] = {}


def _get_fusion_engine(user_id: str) -> EmotionFusionEngine:
    if user_id not in _fusion_engines:
        _fusion_engines[user_id] = EmotionFusionEngine()
    return _fusion_engines[user_id]


class KeyEventIn(BaseModel):
    timestamp: float
    is_backspace: bool = False
    is_navigation: bool = False


class MouseEventIn(BaseModel):
    x: float
    y: float
    timestamp: float
    is_click: bool = False


class EmotionAnalyzeRequest(BaseModel):
    user_id: str = "default"
    key_events: List[KeyEventIn] = Field(default_factory=list)
    mouse_events: List[MouseEventIn] = Field(default_factory=list)
    frame_base64: Optional[str] = None  # JPEG/PNG bytes, base64-encoded; omitted if camera sensing is off


class ModalityBreakdown(BaseModel):
    modality: str
    confidence: float
    vector: Dict[str, float]
    details: Dict[str, object]


class EmotionAnalyzeResponse(BaseModel):
    fused_vector: Dict[str, float]
    overall_confidence: float
    modalities_used: List[str]
    per_modality: List[ModalityBreakdown]


@router.post("/analyze", response_model=EmotionAnalyzeResponse)
def analyze_emotion(payload: EmotionAnalyzeRequest):
    estimates: List[EmotionEstimate] = []

    key_events = [KeyEvent(timestamp=k.timestamp, is_backspace=k.is_backspace, is_navigation=k.is_navigation)
                  for k in payload.key_events]
    estimates.append(_keystroke_estimator.estimate(key_events, KeystrokeBaseline()))

    mouse_events = [MouseEvent(x=m.x, y=m.y, timestamp=m.timestamp, is_click=m.is_click)
                    for m in payload.mouse_events]
    estimates.append(_mouse_estimator.estimate(mouse_events, MouseBaseline()))

    if payload.frame_base64:
        try:
            frame = _decode_frame(payload.frame_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not decode frame_base64: {exc}")
        estimates.append(_facial_estimator.estimate(frame))

    engine = _get_fusion_engine(payload.user_id)
    result = engine.fuse(estimates)

    return EmotionAnalyzeResponse(
        fused_vector=result.vector,
        overall_confidence=result.overall_confidence,
        modalities_used=result.modalities_used,
        per_modality=[
            ModalityBreakdown(
                modality=e.modality,
                confidence=e.confidence,
                vector=e.vector,
                details=e.details,
            )
            for e in estimates
        ],
    )


@router.post("/reset/{user_id}", summary="Reset temporal smoothing state (e.g. on session start)")
def reset_session(user_id: str):
    _get_fusion_engine(user_id).reset()
    return {"status": "reset", "user_id": user_id}


def _decode_frame(frame_base64: str) -> "np.ndarray":
    import cv2

    if "," in frame_base64:  # tolerate data: URLs from the browser/Electron layer
        frame_base64 = frame_base64.split(",", 1)[1]
    raw = base64.b64decode(frame_base64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("cv2.imdecode returned None — not a valid image")
    return frame
