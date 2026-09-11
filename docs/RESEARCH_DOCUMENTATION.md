# Emotion-Aware Adaptive Operating System (EAOS)

*A cross-platform, AI-driven desktop assistant that senses a user's cognitive-emotional state and adapts the computing environment in real time.*

---

## 1. Abstract

Modern operating systems are emotionally blind: they treat a user deep in flow state and a user in a state of frustration identically. This project introduces EAOS, a desktop-layer system that continuously infers a user's affective and cognitive state from multimodal behavioral signals (facial expression, keyboard/mouse dynamics, application context) and translates that inference into OS-level adaptations — focus mode, notification suppression, brightness/theme adjustment, and contextual assistance. The core contribution is not emotion detection itself, but the **Adaptive State Score (ASS)** framework: a learned, personalized fusion of emotion, context, workload, and historical behavior that drives a contextual-bandit/RL policy engine, replacing brittle if-this-then-that automation with a system that improves from feedback over time.

## 2. Problem Statement

Existing "focus assistants" (e.g., static Do Not Disturb schedules, simple app-based focus modes) rely on fixed, user-authored rules. They cannot:
- Distinguish *why* a user is quiet (deep focus vs. fatigue vs. boredom)
- Adapt thresholds per-user (behavioral baselines vary enormously)
- Improve automatically from being wrong
- Fuse multiple weak signals (typing cadence, app-switch frequency, facial affect) into one actionable estimate

There is no widely available system that treats emotional/cognitive state as a first-class, continuously-estimated input to OS behavior.

## 3. Objectives

1. Build a multimodal pipeline that estimates cognitive-emotional state in near real time on-device.
2. Represent "current context" (app, calendar, activity type) as structured, queryable state.
3. Design a decision engine that maps (emotion, context, workload, history) → adaptation, using a learned policy rather than static rules.
4. Personalize per-user via an online-learning baseline model.
5. Close the loop with explicit and implicit feedback to improve the policy over time.
6. Ship this as a real, runnable cross-platform desktop app (Electron + FastAPI), not a proof-of-concept notebook.

## 4. System Architecture (high level)

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
│                                                                    │
│  ┌────────────────┐   ┌───────────────────┐   ┌────────────────┐ │
│  │ Emotion         │   │ Context            │   │ Personalization│ │
│  │ Recognition AI  │──▶│ Understanding AI   │──▶│ Engine (per-   │ │
│  │ (CV + keystroke │   │ (active app, cal-  │   │ user baseline) │ │
│  │  + mouse models)│   │  endar, activity)  │   │                │ │
│  └────────┬────────┘   └─────────┬─────────┘   └────────┬───────┘ │
│           │                      │                       │        │
│           └──────────┬───────────┴───────────┬───────────┘        │
│                       ▼                       ▼                    │
│              ┌──────────────────────────────────────┐             │
│              │   Adaptive State Score (ASS) Fusion   │             │
│              └────────────────────┬─────────────────┘             │
│                                    ▼                                │
│              ┌──────────────────────────────────────┐             │
│              │  Decision Engine (Contextual Bandit / │             │
│              │  RL Policy) → chooses adaptation      │             │
│              └────────────────────┬─────────────────┘             │
│                                    ▼                                │
│              ┌──────────────────────────────────────┐             │
│              │  Action Executor → OS Adapter Layer   │             │
│              └────────────────────┬─────────────────┘             │
│                                    │                                │
│              ┌─────────────────────────────────────┐              │
│              │  Feedback Store + Continuous Learner  │◀────────────┘ (user feedback)
│              └─────────────────────────────────────┘
│                                                                     │
│              SQLite/PostgreSQL persistence layer                   │
└─────────────────────────────────────────────────────────────────┘
```

## 5. Core Research Contribution: The Adaptive State Score (ASS)

Rather than mapping raw emotion labels directly to actions (brittle, non-personalized), EAOS computes a continuous, personalized score:

```
ASS(t) = f( E(t), C(t), W(t), H(t); θ_user )
```

- **E(t)** — Emotion vector at time t (softmax over Focused, Frustrated, Fatigued, Confused, Relaxed, Flow), fused from facial + behavioral modalities with per-modality confidence weighting.
- **C(t)** — Context vector (active app category, calendar state, time-of-day, activity type embedding).
- **W(t)** — Workload estimate (task switching rate, deadline proximity, error/exception rate in IDE, meeting density).
- **H(t)** — Historical behavior baseline (this user's typical typing cadence, typical break frequency, typical error tolerance) learned online.
- **θ_user** — Per-user personalization parameters, updated via the Personalization Engine.

The Decision Engine treats ASS (plus the raw component vectors) as the *state* in a contextual bandit: each candidate adaptation (silence notifications, suggest break, enable dark mode, recommend debugging help, do nothing) is an *arm*, and the *reward* is derived from explicit feedback (👍/👎 on a suggestion) and implicit feedback (did the user immediately undo the action; did productivity signals improve afterward).

**Why this beats rule-based automation:**
1. **Personalization** — a fixed rule ("if idle 5 min → suggest break") ignores that some users' natural flow state includes stillness; ASS is calibrated per-user via H(t).
2. **Credit assignment over time** — bandit/RL reward shaping lets the system learn *which* interventions actually help *this* user, not a population average.
3. **Graceful degradation** — when a modality is unavailable (e.g., camera off), the fusion function reweights remaining signals rather than failing outright, which a rule table cannot do cleanly.
4. **Continuous improvement** — the policy updates from feedback without manual rule editing.

## 6. Methodology (summary)

1. **Signal acquisition** — sample keyboard/mouse events, active window/process, and (opt-in) webcam frames at low frequency.
2. **Per-modality inference** — CNN/MediaPipe facial affect model; hand-crafted + learned features over keystroke/mouse dynamics; app-usage embedding.
3. **Fusion** — confidence-weighted combination into E(t); combine with C(t), W(t), H(t) into ASS.
4. **Policy decision** — contextual bandit (LinUCB / Thompson Sampling to start; upgradable to a full RL agent) selects an action.
5. **Execution** — OS Adapter Layer performs the action per-platform.
6. **Feedback capture** — explicit UI feedback + implicit signal (was the action reverted / did state improve) stored and used to update the bandit and H(t).

## 7. Research Questions

- RQ1: Does a personalized ASS fusion outperform a population-level fixed-threshold model at predicting when an intervention will be accepted?
- RQ2: How many feedback samples are needed before the per-user bandit outperforms a cold-start rule baseline?
- RQ3: What is the accuracy/latency/privacy trade-off of doing all inference on-device vs. partially in the cloud?
- RQ4: Does explicit self-reported state correlate with the multimodal-inferred state, and where do they diverge?

## 8. Future Scope

- Voice-emotion modality (Whisper + prosody features) as an optional third input.
- Federated/on-device-only training to avoid ever transmitting behavioral data.
- Team/organization-level analytics (aggregated, privacy-preserving) for workplace well-being research.
- Full RL agent (e.g., PPO over a simulated user-response environment) once enough real interaction data exists to bootstrap a simulator.

## 9. Data & Privacy Note

All raw sensor data (camera frames, keystroke timings) is processed locally and only derived, aggregated features are persisted. Camera-based sensing is strictly opt-in and can be disabled without losing keyboard/mouse/context-based functionality. This is enforced structurally in the architecture (Section 4) via the Privacy Controls settings module (Module 6, upcoming).

---

*Diagrams (Use Case, Sequence, Class, DB Schema, Flowchart) will be added as Mermaid sources alongside the corresponding code module — e.g., the DB schema diagram ships with Module 1's database layer below.*
