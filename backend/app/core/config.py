import os
from dataclasses import dataclass, field
from typing import Dict, Any

# Centralized lowered demonstration thresholds for easy triggering
DEFAULT_THRESHOLDS: Dict[str, float] = {
    "workload_high": 0.45,
    "workload_medium": 0.25,
    "frustration_high": 0.30,
    "fatigue_high": 0.35,
    "mouse_jitter_high": 0.10,
    "typing_error_high": 0.06,
    "emotion_confidence_min": 0.20,
    "decision_score_min": 0.25,
    "cooldown_seconds": 5.0,
    "ambient_dim_threshold": 0.40,
    "ambient_bright_threshold": 0.60,
    "focus_mode_workload_min": 0.46,
}

DEFAULT_AS_WEIGHTS: Dict[str, float] = {
    "emotion": 0.35,
    "context": 0.20,
    "workload": 0.30,
    "personalization": 0.15,
}

@dataclass
class Settings:
    host: str = os.getenv("EAOS_HOST", "127.0.0.1")
    port: int = int(os.getenv("EAOS_PORT", "8765"))
    simulation: bool = os.getenv("EAOS_SIMULATION", "false").lower() == "true"
    db_path: str = os.getenv("EAOS_DB", "eaos.db")
    update_seconds: float = float(os.getenv("EAOS_UPDATE_SECONDS", "1.0"))

    # Adaptive Cycle Configuration (1 minute input collection, 1 minute adaptation wait = 60s each)
    cycle_duration_minutes: float = float(os.getenv("EAOS_CYCLE_MINUTES", "1.0"))

    # Demo Mode Configuration (Optional shorter cycle for rapid demonstration, e.g. 1 minute)
    demo_mode: bool = os.getenv("EAOS_DEMO_MODE", "false").lower() == "true"
    demo_cycle_minutes: float = float(os.getenv("EAOS_DEMO_CYCLE_MINUTES", "1.0"))

    # Privacy & Automation Switches
    camera_sensing_enabled: bool = os.getenv("EAOS_CAMERA_ENABLED", "true").lower() == "true"
    automation_enabled: bool = os.getenv("EAOS_AUTOMATION_ENABLED", "true").lower() == "true"

    # Personalization System Configuration
    personalization_enabled: bool = os.getenv("EAOS_PERSONALIZATION_ENABLED", "true").lower() == "true"
    calibration_cycles: int = int(os.getenv("EAOS_CALIBRATION_CYCLES", "5"))
    personalization_alpha: float = float(os.getenv("EAOS_PERSONALIZATION_ALPHA", "0.10"))
    baseline_adaptation: str = os.getenv("EAOS_BASELINE_ADAPTATION", "Normal")  # Slow, Normal, Fast

    # Sensitivity: 'ultra_responsive', 'high', 'normal', 'low'
    sensitivity: str = os.getenv("EAOS_SENSITIVITY", "ultra_responsive")

    # Thresholds and Weights
    thresholds: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))
    as_weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_AS_WEIGHTS))

    def get_effective_cycle_minutes(self) -> float:
        if self.demo_mode:
            return self.demo_cycle_minutes
        return self.cycle_duration_minutes

    def get_effective_cycle_seconds(self) -> float:
        return self.get_effective_cycle_minutes() * 60.0

    def update_from_dict(self, d: Dict[str, Any]):
        if "demo_mode" in d:
            self.demo_mode = bool(d["demo_mode"])
        if "cycle_duration_minutes" in d:
            self.cycle_duration_minutes = float(d["cycle_duration_minutes"])
        if "demo_cycle_minutes" in d:
            self.demo_cycle_minutes = float(d["demo_cycle_minutes"])
        if "camera_sensing_enabled" in d:
            self.camera_sensing_enabled = bool(d["camera_sensing_enabled"])
        if "automation_enabled" in d:
            self.automation_enabled = bool(d["automation_enabled"])
        if "personalization_enabled" in d:
            self.personalization_enabled = bool(d["personalization_enabled"])
        if "calibration_cycles" in d:
            self.calibration_cycles = int(d["calibration_cycles"])
        if "personalization_alpha" in d:
            self.personalization_alpha = float(d["personalization_alpha"])
        if "baseline_adaptation" in d:
            self.baseline_adaptation = str(d["baseline_adaptation"])
            if self.baseline_adaptation == "Slow":
                self.personalization_alpha = 0.05
            elif self.baseline_adaptation == "Fast":
                self.personalization_alpha = 0.20
            else:
                self.personalization_alpha = 0.10
        if "sensitivity" in d:
            self.sensitivity = str(d["sensitivity"])
        if "thresholds" in d and isinstance(d["thresholds"], dict):
            self.thresholds.update(d["thresholds"])
        if "as_weights" in d and isinstance(d["as_weights"], dict):
            self.as_weights.update(d["as_weights"])

settings = Settings()
