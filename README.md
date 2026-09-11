# Emotion-Aware Adaptive Operating System (EAOS)

*A cross-platform, AI-driven desktop assistant that senses a user's cognitive-emotional state and adapts the computing environment in real time.*

---

## Overview

Modern operating systems are emotionally blind: they treat a user deep in flow state and a user in a state of frustration identically. **EAOS** continuously infers a user's affective and cognitive state from multimodal behavioral signals (facial expression, keyboard/mouse dynamics, application context) and translates that inference into intelligent OS-level adaptations — such as focus mode, notification suppression, brightness/theme adjustments, and contextual assistance.

### Key Highlights

- **Multimodal State Estimation**: Real-time fusion of facial affect, typing cadence, and mouse movement dynamics.
- **Adaptive State Score (ASS)**: A learned, personalized mathematical framework combining Emotion $E(t)$, Context $C(t)$, Workload $W(t)$, and Historical baseline $H(t)$.
- **Contextual Decision Engine**: Replaces brittle static rules with an intelligent policy engine that selects adaptations and learns from explicit and implicit feedback.
- **Privacy-First & On-Device**: Local inference and on-device processing to ensure user telemetry stays private.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     ELECTRON DESKTOP SHELL                       │
│  ┌───────────────┐  ┌────────────────┐  ┌─────────────────────┐ │
│  │ React Dashboard│  │ Native OS Hooks│  │ Background Sensors  │ │
│  │ (TS + Tailwind)│  │ (focus/bright- │  │ (camera, keyboard,  │ │
│  │                │  │  ness/notif.)  │  │  mouse, active-win) │ │
│  └───────┬────────┘  └────────┬───────┘  └──────────┬──────────┘ │
└──────────┼────────────────────┼─────────────────────┼────────────┘
           │ REST / WebSocket    │                     │ local stream
           ▼                    ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                     PYTHON BACKEND (FastAPI)                     │
│                                                                 │
│  ┌────────────────┐   ┌───────────────────┐   ┌────────────────┐│
│  │ Emotion         │   │ Context            │   │ Personalization││
│  │ Recognition AI  │──▶│ Understanding AI   │──▶│ Engine (per-   ││
│  │ (CV + keystroke │   │ (active app, cal-  │   │ user baseline) ││
│  │  + mouse models)│   │  endar, activity)  │   │                ││
│  └────────┬────────┘   └─────────┬─────────┘   └────────┬───────┘│
│           │                      │                       │       │
│           └──────────┬───────────┴───────────┬───────────┘       │
│                       ▼                       ▼                  │
│              ┌──────────────────────────────────────┐            │
│              │   Adaptive State Score (ASS) Fusion   │            │
│              └────────────────────┬─────────────────┘            │
│                                    ▼                             │
│              ┌──────────────────────────────────────┐            │
│              │  Decision Engine (Contextual Bandit)  │            │
│              └────────────────────┬─────────────────┘            │
│                                    ▼                             │
│              ┌──────────────────────────────────────┐            │
│              │  Action Executor → OS Adapter Layer   │            │
│              └────────────────────┬─────────────────┘            │
│                                    │                             │
│              ┌─────────────────────────────────────┐             │
│              │  Feedback Store + Continuous Learner  │◀───────────┘
│              └─────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```text
eaos/
├── backend/
│   ├── app/
│   │   ├── ai/                 # Multimodal inference (face, keystroke, mouse, fusion)
│   │   ├── api/                # FastAPI endpoints & WebSocket handlers
│   │   ├── core/               # Configuration and core utilities
│   │   ├── db/                 # Database models and session management
│   │   ├── models/             # Pydantic and ORM schemas
│   │   ├── services/           # Business logic & decision orchestration
│   │   └── main.py             # FastAPI entrypoint
│   ├── scripts/                # Utility scripts (e.g., model downloader)
│   └── requirements.txt        # Python dependencies
├── docs/
│   └── RESEARCH_DOCUMENTATION.md # In-depth research & theoretical documentation
├── frontend/                   # UI Dashboard & Desktop Client
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)

### Backend Setup

1. **Navigate to the backend folder**:
   ```bash
   cd backend
   ```

2. **Activate the virtual environment**:
   ```bash
   source ../venv/bin/activate  # Or create a new one: python -m venv venv
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Download AI models**:
   ```bash
   python scripts/download_models.py
   ```

5. **Run the backend server**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

---

## Documentation

For a detailed breakdown of the research methodology, theoretical equations, Adaptive State Score (ASS) framework, and experimental setup, refer to [RESEARCH_DOCUMENTATION.md](docs/RESEARCH_DOCUMENTATION.md).
