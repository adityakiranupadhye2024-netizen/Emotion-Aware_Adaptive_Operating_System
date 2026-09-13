# EAOS — Emotion-Aware Adaptive Operating System

A cross-platform user-space adaptive desktop system that combines multimodal behavioral signals (keyboard cadence, mouse dynamics, active application context, cognitive workload, and camera/facial cues) with an individual **Personalization Engine** to autonomously evaluate an **Adaptive Score (AS)** and execute native macOS adaptations in **continuous 5-minute cycles**.

> **Note**: EAOS is an autonomous desktop adaptation layer, not a replacement OS kernel. It operates strictly in user space.

---

## 🔄 Continuous 5-Minute Adaptive Cycle Architecture

EAOS runs on a repeating **5-minute continuous cycle** based on absolute timestamps to prevent drift:

```text
00:00 ──────────────────────────────────────────────────────────────────────── 05:00
  │                                                                              │
  ▼                                                                              ▼
5-Minute Input Collection Window                                        Cycle Assessment & Actuation
• Real keyboard cadence (typing speed, error rate)                      • Finalize 5-minute input window
• Real mouse dynamics (jitter, movement, idle)                          • Compare inputs to personal baseline
• Active application & task context classification                      • Calculate Adaptive Score (AS)
• Cognitive workload estimation                                         • Decision Engine selects adaptation
• Camera / facial engagement (when privacy toggle is enabled)           • OS Actuator executes macOS action
                                                                        • Notification sent to user
                                                                        • Personal baseline updated (EWMA)
                                                                        • Timer resets to 05:00
                                                                        • Next 5-minute cycle begins
```

---

## 🧠 Personalization Engine (Individual User Learning)

EAOS learns what is normal for you over time rather than enforcing static one-size-fits-all rules:

1. **Signals Learned**:
   - Typing speed (keys/sec) & error rate
   - Mouse movement & jitter agitation
   - Workload baseline
   - Dominant emotional distribution
2. **Initial Calibration (First 5 Cycles)**:
   - Collects actual observations without aggressive adaptations.
   - Status transitions: `CALIBRATING (X/5)` → `LEARNING` → `ACTIVE`.
3. **EWMA Baseline Adaptation**:
   - Updates personal mean and variance using Exponentially Weighted Moving Averages:
     $$\mu_{\text{new}} = \alpha \cdot x + (1 - \alpha) \cdot \mu_{\text{old}}$$
   - Extreme distress (acute frustration/fatigue) is dampened so temporary spikes do not skew your long-term normal baseline.
4. **Personal Z-Scores & Deviation**:
   - Computes $z = \frac{x - \mu}{\sigma}$ to evaluate if your current state is unusually elevated relative to your individual habits.
   - The deviation feeds directly into the **Personalization Component** of the Adaptive Score.
5. **Reset Capability**:
   - You can click **🔄 Reset Personal Baseline** in Settings at any time to clear learned statistics and restart calibration.

---

## 🔒 Privacy Guarantees

1. **No Keylogging**: EAOS measures only timing cadence (inter-key intervals, backspace rates). **Typed text is never captured or stored**.
2. **Camera Privacy Controls**: The webcam is used solely for local in-memory facial engagement and ambient light detection when enabled. You can toggle "Camera Sensing Integration" off in Settings at any time, in which case the camera is **strictly closed** and EAOS operates seamlessly using non-camera behavioral signals.
3. **In-Memory Frame Processing**: Camera frames are processed strictly in RAM; **raw camera frames are never saved to disk**.

---

## 📊 Adaptive Score (AS)

The **Adaptive Score (AS)** is a normalized index between `0.00` and `1.00` composed of four weighted components:

$$\text{AS} = w_{\text{emotion}} \cdot E + w_{\text{context}} \cdot C + w_{\text{workload}} \cdot W + w_{\text{personalization}} \cdot P$$

- **Emotion Component ($E$, 35%)**: Valence and focus derived from keyboard friction, flow indicators, and facial engagement.
- **Context Component ($C$, 20%)**: Productive relevance of the frontmost application (Coding, Writing, Communications, etc.).
- **Workload Component ($W$, 30%)**: Cognitive demand index derived from typing cadence, system CPU load, and window switching.
- **Personalization Component ($P$, 15%)**: Measures the degree of deviation from your learned personal baseline.

---

## 🖥️ Automatic macOS Actions (OS Actuator)

At the end of each 5-minute cycle, the Decision Engine automatically executes one of the following adaptations:

- **Dark Mode (`ENABLE_DARK_MODE`)**: Activates macOS Dark Appearance if low ambient light or eye strain is detected.
- **Light Mode (`DISABLE_DARK_MODE`)**: Restores standard appearance when room lighting is bright.
- **Focus Mode (`ENABLE_FOCUS_MODE`)**: Mutes system notification audio and declutters non-essential background windows during elevated workload or high personal deviation.
- **Restore Focus (`DISABLE_FOCUS_MODE`)**: Restores standard alert volume when work ease returns.
- **Wellness Break Alert (`SUGGEST_BREAK`)**: Sounds an audible chime, provides speech prompt, and suggests taking a stretch break during sustained fatigue.
- **Developer Resource (`SUGGEST_DEBUG_RESOURCE`)**: Opens documentation reference when high friction/backspaces occur during coding.
- **No Action (`NO_ACTION`)**: Confirms user state is nominal and avoids unnecessary changes.

---

## 🚀 Getting Started (macOS)

### Prerequisites

- macOS 12+ (tested on Apple Silicon and Intel MacBooks)
- Python 3.10+
- Node.js 18+

### Step 1: Start Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8765
```

### Step 2: Start Frontend (Vite Dashboard)

In a new terminal window:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173` in your browser. The dashboard connects via WebSocket to the live backend and displays the real 5-minute countdown timer.

### Step 3 (Optional): Run Electron Desktop Shell

In a third terminal window:

```bash
cd electron
npm install
npm start
```

---

## 🔐 macOS Permissions

For live behavioral sensing on macOS:

1. **Accessibility**: Open **System Settings > Privacy & Security > Accessibility** and ensure your terminal app (Terminal, iTerm2, or VS Code) is enabled so active application detection and mouse tracking can function.
2. **Input Monitoring**: Open **System Settings > Privacy & Security > Input Monitoring** and allow your terminal for keyboard cadence detection.
3. **Camera**: macOS will prompt to grant Camera access to Terminal / Python when camera sensing is enabled.
