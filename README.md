# EAOS — Emotion-Aware Adaptive Operating System

[![macOS](https://img.shields.io/badge/Platform-macOS%2012%2B-blue.svg)](https://apple.com/macos)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/Frontend-React%2018%20%2B%20TypeScript%20%2B%20Vite-61DAFB.svg?logo=react&logoColor=black)](https://react.dev)
[![OpenCV](https://img.shields.io/badge/Vision-OpenCV%204.12-5C3EE8.svg?logo=opencv&logoColor=white)](https://opencv.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A cross-platform, user-space adaptive desktop system that combines real multimodal behavioral signals (keyboard cadence, mouse dynamics, active application context, cognitive workload, and on-device facial cues) with an individual **Personalization Engine** to autonomously evaluate an **Adaptive Score (AS)** and execute native macOS adaptations in **continuous 2-minute wall-clock cycles** (1-minute input collection + 1-minute adaptation).

> **Note**: EAOS is an autonomous desktop adaptation layer operating strictly in user space—not a replacement OS kernel. It interfaces directly with native macOS Shortcuts and AppleScript APIs with zero cloud dependencies.

---

## 🌟 Key Features

* **👁️ Real-Time AI Vision & Facial Emotion HUD**: Local in-memory face tracking via OpenCV Haar Cascades with sleek cyber corner brackets, eye engagement tracking, smile detection, and dynamic in-frame emotion badges.
* **🔄 Synchronized 2-Minute Wall-Clock Cycle**: Continuous repeating cycle with a **1-minute input collection window** followed by a **1-minute adaptation window** (120 seconds total), preventing clock drift.
* **⚡ Native macOS Shortcut Actuation**: Direct zero-latency hardware and appearance actuation via macOS Shortcuts (`Set Appearance`, `Turn On DND`, `Set Volume`, `Set Brightness`).
* **🧠 Individual Personalization Engine**: Online EWMA learning that calibrates to your personal typing cadence, error tolerance, and mouse dynamics rather than static thresholds.
* **📊 Explainable AI Decision Engine**: LinUCB contextual bandit algorithm paired with rule-based verification, computing an Adaptive Score ($AS \in [0, 1]$) with transparent rationales.
* **🔒 Strict On-Device Privacy Architecture**: Zero keylogging (only inter-key timing and error rates are captured), RAM-only frame processing (never written to disk), and automatic hardware release during adaptation phases.
* **🎛️ Dual-Mode Live Dashboard**: Futuristic React + Vite dark-mode dashboard with real-time WebSocket telemetry, Gantt state timelines, quick manual actuator overrides, and dual-mode camera streaming (OpenCV stream or browser webcam).

---

## 🔄 Continuous 2-Minute Adaptive Cycle Architecture

EAOS aligns its observation and actuation phases with continuous wall-clock boundaries (60 seconds per slot, alternating between input collection and adaptation):

```text
00:00 ───────────────────────────── 01:00 ──────────────────────────────────────── 02:00
  │                                   │                                              │
  ▼                                   ▼                                              ▼
[INPUT COLLECTION (1 MINUTE)]       [BOUNDARY FINALIZATION]                [ADAPTATION (1 MINUTE)]
• Webcam opens (sensing window)     • Finalize 1-min aggregated signals    • Webcam closed & released (privacy)
• Keystroke dynamics & cadence      • Compare inputs against EWMA baseline • OS adaptation remains active
• Mouse velocity, jitter, idle      • Calculate Adaptive Score (AS)        • Behavioral sensors monitor ease
• Frontmost app & task context      • LinUCB / Decision Engine picks arm   • System prepares for next cycle
• Cognitive workload estimation     • Native macOS Shortcut executed       • Telemetry & durations recorded
• In-memory facial valence & smile  • User notification dispatched         • Countdown resets for next cycle
```

---

## 👁️ AI Vision & Facial Emotion Tracking Box

EAOS features an interactive on-device vision stream accessible from both the **Overview** and **AI State** dashboard tabs:

* **In-Frame Face Bounding Box**: Cybernetic corner brackets lock onto detected faces with sub-millisecond latency.
* **Dynamic In-Camera Emotion Badge**: Real-time classified emotion (`FOCUSED`, `FLOW STATE`, `RELAXED`, `FATIGUED`, `FRUSTRATED`, `CONFUSED`) is rendered directly over the face with confidence percentages and tailored color themes.
* **Eye & Expression Indicators**: Real-time crosshairs track eye engagement and smile detection.
* **Cyber Scanline & Standby HUD**: When the camera is closed during the 1-minute adaptation phase to preserve privacy, a synthetic cyberpunk HUD standby screen is rendered so the video stream never drops or errors.
* **Dual Streaming Support**:
  1. **Backend OpenCV Stream**: Native MJPEG video stream from `/api/v1/camera/stream` at ~16 FPS.
  2. **Direct Browser Cam**: High-resolution browser WebCam capture via `navigator.mediaDevices.getUserMedia`.
* **On-Demand Preview**: Click **`▶ Live Cam Preview`** at any time to stream continuously regardless of cycle phase.

---

## 🖥️ macOS Shortcuts Actuator (Hardware Bridge)

EAOS leverages macOS Shortcuts for reliable, native control without brittle UI scripting:

| Adaptation Action | System Command Executed | macOS Effect |
| :--- | :--- | :--- |
| `ENABLE_DARK_MODE` | `shortcuts run "Set Appearance" <<< "Dark"` | Switches macOS system appearance to Dark Mode |
| `DISABLE_DARK_MODE` | `shortcuts run "Set Appearance" <<< "Light"` | Restores macOS system appearance to Light Mode |
| `ENABLE_FOCUS_MODE` | `shortcuts run "Turn On DND" <<< "On"` | Engages Do Not Disturb / Focus Mode |
| `DISABLE_FOCUS_MODE` | `shortcuts run "Turn On DND" <<< "Off"` | Disengages Focus Mode and restores notifications |
| `SET_BRIGHTNESS` | `shortcuts run "Set Brightness" <<< "<val>"` | Sets display brightness via DisplayServices |
| `SET_VOLUME` | `shortcuts run "Set Volume" <<< "<val>"` | Sets output volume level (0 to 100) |
| `TOGGLE_MUTE` | `shortcuts run "Set Volume" <<< "0"` | Mutes audio during high stress or un-mutes |
| `RESET_ALL` | Runs all 4 baseline shortcuts sequentially | Restores Light Mode, DND Off, Volume 50%, Brightness 65% |

---

## 🧠 Personalization Engine (Individual User Learning)

EAOS learns what is normal for you over time rather than enforcing static one-size-fits-all rules:

1. **Signals Learned**:
   - Typing speed (keys/sec) & error rate
   - Mouse movement velocity & directional jitter
   - Cognitive workload baseline
   - Dominant emotional distribution
2. **Initial Calibration (First 5 Cycles = 10 Minutes)**:
   - Collects actual observations without aggressive adaptations.
   - Status transitions: `CALIBRATING (X/5)` → `LEARNING` → `ACTIVE`.
3. **EWMA Baseline Adaptation**:
   - Updates personal mean and variance using Exponentially Weighted Moving Averages:
     $$\mu_{\text{new}} = \alpha \cdot x + (1 - \alpha) \cdot \mu_{\text{old}}$$
   - Extreme distress (acute frustration/fatigue) is dampened so temporary spikes do not skew your long-term normal baseline.
4. **Personal Z-Scores & Deviation**:
   - Computes $z = \frac{x - \mu}{\sigma}$ to evaluate if your current state is unusually elevated relative to your individual habits.
5. **Reset Capability**:
   - You can click **🔄 Reset Adaptations** in the dashboard header or **Reset Baseline** in Settings at any time.

---

## 📊 Adaptive Score (AS) Formulation

The **Adaptive Score (AS)** is a normalized index between `0.00` and `1.00` composed of four weighted components:

$$\text{AS} = w_{\text{emotion}} \cdot E + w_{\text{context}} \cdot C + w_{\text{workload}} \cdot W + w_{\text{personalization}} \cdot P$$

* **Emotion Component ($E$, 35%)**: Valence and focus derived from keyboard cadence, error backspaces, and facial engagement.
* **Context Component ($C$, 20%)**: Task category of the frontmost application (Coding, Writing, Browsing, Communication).
* **Workload Component ($W$, 30%)**: Cognitive demand index derived from typing cadence, CPU load, and window switching frequency.
* **Personalization Component ($P$, 15%)**: Measures the degree of deviation from your learned personal baseline ($z$-scores).

---

## 🔒 Privacy Guarantees

1. **No Keylogging**: EAOS measures only timing cadence (inter-key intervals, backspace rates). **Typed characters and text are never captured, logged, or transmitted**.
2. **Scheduled Camera Window**: The webcam is activated solely during the 1-minute input sensing window, then **immediately released** for the 1-minute adaptation phase.
3. **In-Memory Frame Processing**: Camera frames are processed strictly in RAM; **raw camera frames are never saved to disk**.
4. **Full Offline Execution**: All machine learning, computer vision, and state evaluation occur 100% locally on your machine with zero telemetry sent to external servers.

---

## 🚀 Getting Started

### Prerequisites

* macOS 12+ (tested on Apple Silicon M-series and Intel MacBooks)
* Python 3.10+
* Node.js 18+

### Step 1: Clone and Configure Shortcuts

Ensure the 4 native macOS Shortcuts exist in your Shortcuts app:
1. `Set Appearance` (Accepts Text: `Dark` or `Light`)
2. `Turn On DND` (Accepts Text: `On` or `Off`)
3. `Set Volume` (Accepts Text/Number: `0` to `100`)
4. `Set Brightness` (Accepts Text/Number: `0.05` to `1.00`)

*(See [docs/SETUP_MACOS.md](docs/SETUP_MACOS.md) for full shortcut creation steps)*

### Step 2: Start Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8765 --host 127.0.0.1
```

### Step 3: Start Frontend (Vite + React)

In a second terminal window:

```bash
cd frontend
npm install
npm run dev
```

Open **`http://127.0.0.1:5173`** in your browser to access the live dashboard.

---

## 📂 Project Structure

```text
eaos-full-project/
├── backend/
│   ├── app/
│   │   ├── core/               # Configuration and environment settings
│   │   ├── db/                 # SQLite schema, migrations, and CRUD operations
│   │   ├── decision_engine/    # LinUCB bandit policy, Adaptive Score, and rules
│   │   ├── sensors/            # Multimodal sensors: Keyboard, Mouse, Context, Camera
│   │   ├── services/           # Actuator (Shortcuts), Scheduler, StateBuilder, Notification
│   │   └── main.py             # FastAPI REST endpoints and WebSocket server
│   └── requirements.txt        # Python dependencies (OpenCV, FastAPI, uvicorn, pynput)
├── frontend/
│   ├── src/
│   │   ├── components/         # CameraBox, QuickOSControl, Cards, Modal
│   │   ├── pages/              # Overview, AI State, Analytics, Actions, History, Privacy, Settings
│   │   ├── services/           # REST and WebSocket client
│   │   └── styles.css          # Design system, glassmorphism, animations
│   ├── package.json            # Vite, React, Lucide, Recharts dependencies
│   └── vite.config.ts
├── docs/
│   ├── ARCHITECTURE.md         # Deep-dive architecture and component pipeline
│   ├── RESEARCH_DOCUMENTATION.md# Research paper, mathematical formulations, and metrics
│   └── SETUP_MACOS.md          # Comprehensive macOS setup and permissions guide
└── README.md                   # Project overview and quickstart guide
```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
