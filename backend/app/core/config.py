"""
Central application configuration.

All tunable parameters (sampling rates, thresholds, DB location, CORS origins)
live here so the rest of the codebase never hardcodes them. Values can be
overridden via environment variables or a local `.env` file, which keeps the
scaffold usable for both development and packaged desktop builds.
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[3]  # project root (eaos/)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="EAOS_")

    # --- General ---
    app_name: str = "Emotion-Aware Adaptive Operating System"
    environment: str = "development"  # development | production
    debug: bool = True

    # --- API / CORS ---
    api_prefix: str = "/api/v1"
    # Electron renderer runs on a local origin in dev; packaged app uses file://
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "app://.",
    ]

    # --- Database ---
    database_url: str = f"sqlite:///{BASE_DIR / 'backend' / 'data' / 'eaos.db'}"
    # Example Postgres override:
    # EAOS_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/eaos

    # --- Sensing cadence (seconds) ---
    keyboard_mouse_sample_interval: float = 1.0
    facial_frame_interval: float = 2.0
    context_poll_interval: float = 5.0
    ass_recompute_interval: float = 3.0

    # --- Privacy defaults (opt-in camera, on by default for everything else) ---
    camera_sensing_enabled_default: bool = False
    keyboard_dynamics_enabled_default: bool = True
    mouse_dynamics_enabled_default: bool = True
    app_context_enabled_default: bool = True

    # --- Decision engine ---
    bandit_algorithm: str = "thompson_sampling"  # thompson_sampling | lin_ucb
    min_seconds_between_interventions: float = 60.0


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — import this, not Settings(), across the app."""
    return Settings()
