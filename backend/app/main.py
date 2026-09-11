"""
EAOS backend entrypoint.

Run with:
    uvicorn app.main:app --reload --port 8765

The Electron shell talks to this process over HTTP (REST, module 1+) and
WebSocket (real-time state stream, module 3+) on localhost only — this
process is never exposed beyond the local machine.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.session import init_db
from app.api.routes import users, emotion

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Local backend for the Emotion-Aware Adaptive Operating System desktop app.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


app.include_router(users.router, prefix=settings.api_prefix)
app.include_router(emotion.router, prefix=settings.api_prefix)


# --- Placeholders for upcoming modules (registered here so the route tree
# is visible from Module 1, implemented as each module lands) -------------
#
# Module 3: app.api.routes.context         -> /context/*  (active app / activity / calendar)
# Module 4: app.api.routes.decision        -> /decision/* (ASS + bandit policy + actions)
# Module 5: app.api.routes.feedback        -> /feedback/* (explicit/implicit feedback ingestion)
# Module 6: app.api.routes.os_adapter      -> /os/*       (focus mode, brightness, dark mode, notifications)
# Module 7: WebSocket /ws/state            -> real-time push of state snapshots to the dashboard
