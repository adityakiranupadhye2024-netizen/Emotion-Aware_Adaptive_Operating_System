# EAOS System Architecture

This document provides a technical overview of the **Emotion-Aware Adaptive Operating System (EAOS)**, including its multimodal sensor architecture, AI vision pipeline, wall-clock cycle scheduler, decision engine, native OS actuator, and persistence layer.

---

## 1. High-Level System Architecture

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               FRONTEND (REACT + VITE + TS)                             │
│                                                                                        │
│  ┌───────────────────────┐  ┌─────────────────────────┐  ┌──────────────────────────┐  │
│  │   AI Vision Cam Box   │  │   Real OS Actuator &    │  │     Live Telemetry &     │  │
│  │  (In-Frame Emotion)   │  │      Mode Switcher      │  │      Gantt Timeline      │  │
│  └───────────▲───────────┘  └────────────▲────────────┘  └────────────▲─────────────┘  │
└──────────────┼───────────────────────────┼────────────────────────────┼────────────────┘
               │ MJPEG /api/v1/camera/stream│ POST /api/v1/actions/execute │ WebSocket /ws/live-state
               ▼                           ▼                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              FASTAPI BACKEND CORE (PORT 8765)                          │
│                                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │                       WALL-CLOCK CYCLE SCHEDULER (5-MIN BOUNDARIES)              │  │
│  │                                                                                  │  │
│  │   [00:00 - 01:00] INPUT COLLECTION WINDOW    [01:00 - 05:00] ADAPTATION WINDOW   │  │
│  │   • Camera open & sensing                   • Camera closed & released (privacy) │  │
│  │   • Real sensor accumulation                • OS adaptation active on macOS      │  │
│  └───────────────────────────▲──────────────────────────────────────▲───────────────┘  │
│                              │                                      │                  │
│       ┌──────────────────────┴───────┐              ┌───────────────┴──────────────┐   │
│       │      MULTIMODAL SENSORS      │              │      OS ACTUATOR ENGINE      │   │
│       │                              │              │                              │   │
│       │ • Keyboard (Cadence/Errors)  │              │ • macOS Shortcuts Bridge     │   │
│       │ • Mouse (Jitter/Velocity)    │              │   - 'Set Appearance'         │   │
│       │ • Context (Frontmost App)    │              │   - 'Turn On DND'            │   │
│       │ • Workload (Cognitive Index) │              │   - 'Set Brightness'         │   │
│       │ • Camera (OpenCV Vision HUD) │              │   - 'Set Volume'             │   │
│       └──────────────┬───────────────┘              │ • AppleScript & CTypes       │   │
│                      │                              └───────────────▲──────────────┘   │
│                      ▼                                              │                  │
│       ┌──────────────────────────────┐              ┌───────────────┴──────────────┐   │
│       │    PERSONALIZATION ENGINE    │              │   DECISION ENGINE & POLICY   │   │
│       │                              │              │                              │   │
│       │ • EWMA Baseline Learning     │─────────────▶│ • Adaptive Score (AS) Fusion │   │
│       │ • Normalized Z-Score Devs    │              │ • LinUCB Contextual Bandit   │   │
│       │ • Distress Spike Dampening   │              │ • Explainable AI Rationale   │   │
│       └──────────────────────────────┘              └──────────────────────────────┘   │
│                                                                                        │
│       ┌─────────────────────────────────────────────────────────────────────────────┐  │
│       │                         SQLITE PERSISTENCE LAYER                            │  │
│       │  cycles · decisions · os_state_events · camera_sessions · baselines         │  │
│       └─────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Multimodal Sensor Subsystems

EAOS captures human-computer interaction (HCI) telemetry entirely in user space:

### A. Keyboard Cadence Sensor ([`keyboard.py`](file:///Users/adityaupadhye/Desktop/eaos-full-project/backend/app/sensors/keyboard.py))
* **Cadence Tracking**: Captures inter-key interval distributions, typing speed (keys per second), and cadence regularity.
* **Error Rate**: Computes the backspace ratio $\frac{N_{\text{backspace}}}{N_{\text{total}}}$ to detect cognitive hesitation, frustration, or task friction.
* **Strict Privacy**: Key character values are **discarded instantly**. The system only observes timestamp deltas.

### B. Mouse Dynamics Sensor ([`mouse.py`](file:///Users/adityaupadhye/Desktop/eaos-full-project/backend/app/sensors/mouse.py))
* **Velocity & Acceleration**: Measures pixel distance traversed over time.
* **Agitation / Jitter**: Computes high-frequency directional vector reversals (sudden sharp direction changes indicating user restlessness or cognitive overload).
* **Idleness**: Detects inactivity periods to prevent false fatigue triggers when the user is away.

### C. Active Application & Context Sensor ([`context.py`](file:///Users/adityaupadhye/Desktop/eaos-full-project/backend/app/sensors/context.py))
* Uses macOS AppleScript (`System Events`) to query the frontmost process name.
* Maps active applications to canonical task profiles:
  * **`Coding`**: VS Code, Xcode, Terminal, PyCharm, Sublime
  * **`Writing / Studying`**: Obsidian, Notion, Pages, Word, Notes
  * **`Browsing`**: Safari, Chrome, Arc, Brave, Firefox
  * **`Communication`**: Slack, Teams, Discord, Mail, Messages
  * **`Media / Entertainment`**: Spotify, YouTube, VLC, Music
  * **`Idle`**: Finder / System idle

### D. AI Vision & Facial Emotion Sensor ([`camera.py`](file:///Users/adityaupadhye/Desktop/eaos-full-project/backend/app/sensors/camera.py))
* **Multi-Stage Detection Pipeline**:
  1. Contrast Limited Adaptive Histogram Equalization (**CLAHE**) normalizes uneven lighting.
  2. Multi-cascade detection using `haarcascade_frontalface_alt2.xml`, `haarcascade_frontalface_default.xml`, and `haarcascade_profileface.xml`.
  3. Feature verification: `haarcascade_eye_tree_eyeglasses.xml` for eye engagement and `haarcascade_smile.xml` for facial valence.
* **Real-Time HUD Annotation**:
  * Draws bounding box corner brackets on detected faces.
  * Overlays eye tracking crosshairs and smile detection flags.
  * Injects the dynamic emotion badge (`FOCUSED`, `FLOW STATE`, `RELAXED`, `FATIGUED`, `FRUSTRATED`, `CONFUSED`) directly into the frame.
* **In-Memory Streaming**:
  * Encodes annotated frames to JPEG in RAM.
  * Served via HTTP multipart stream `/api/v1/camera/stream` at ~16 FPS.
  * Generates an animated standby HUD when the camera is powered down for privacy.

---

## 3. Continuous 5-Minute Wall-Clock Cycle

EAOS eliminates timing drift by binding cycle boundaries directly to absolute Unix epoch time (`time.time() // 300`):

```text
 00:00                     01:00                                            05:00
┌─────────────────────────┬──────────────────────────────────────────────────────┐
│  INPUT COLLECTION (1m)  │                ADAPTATION PHASE (4m)                 │
│  • Camera open          │  • Camera closed & released                          │
│  • Multimodal sensing   │  • OS adaptation remains active on macOS             │
│  • Buffer accumulation  │  • Continuous behavioral monitoring                  │
└─────────────────────────┴──────────────────────────────────────────────────────┘
                          ▲
                          │ Boundary Evaluation:
                          │ 1. Finalize telemetry window
                          │ 2. Evaluate Adaptive Score (AS)
                          │ 3. Execute macOS Shortcut
                          │ 4. Update EWMA Personal Baseline
```

---

## 4. Personalization Engine (Online EWMA Learning)

Instead of hardcoded thresholds, EAOS personalizes state evaluation for each user:

1. **EWMA Statistics**:
   Tracks moving mean $\mu_t$ and variance $\sigma^2_t$ for workload, typing rate, backspace rate, and mouse jitter:
   $$\mu_t = \alpha x_t + (1 - \alpha)\mu_{t-1}$$
   $$\sigma^2_t = (1 - \alpha)(\sigma^2_{t-1} + \alpha(x_t - \mu_{t-1})^2)$$
2. **Distress Dampening**:
   Observations flagged with acute distress (severe frustration or exhaustion) use a reduced $\alpha$ to prevent temporary anomalies from corrupting the baseline.
3. **Normalized Z-Scores**:
   $$z = \frac{x - \mu}{\sigma}$$
   Used to detect when a user's current behavior significantly deviates from their individual historical habits.

---

## 5. Decision Engine & LinUCB Contextual Bandit

The Decision Engine selects the optimal OS adaptation using an upper confidence bound contextual bandit algorithm:

$$\text{Action} = \arg\max_{a} \left( \hat{\theta}_a^\top x_t + \beta \sqrt{x_t^\top A_a^{-1} x_t} \right)$$

* **Context Vector $x_t$**: Encodes emotion probabilities, context task embedding, cognitive workload, and personalization deviation.
* **Candidate Arms**:
  1. `ENABLE_DARK_MODE`
  2. `DISABLE_DARK_MODE`
  3. `ENABLE_FOCUS_MODE`
  4. `DISABLE_FOCUS_MODE`
  5. `SET_BRIGHTNESS`
  6. `SET_VOLUME`
  7. `TOGGLE_MUTE`
  8. `SUGGEST_BREAK`
  9. `NO_ACTION`

---

## 6. Native macOS Actuator Architecture

The actuator directly interfaces with user-configured macOS Shortcuts using standard input pipes:

```python
def run_shortcut(shortcut_name: str, input_val: Optional[str] = None) -> bool:
    cmd = ['shortcuts', 'run', shortcut_name]
    res = subprocess.run(cmd, input=input_val, text=True, capture_output=True, timeout=3.5)
    return res.returncode == 0
```

* **Live Hardware Verification**:
  * Appearance verified via AppleScript:
    ```applescript
    tell application "System Events" to tell appearance preferences to get dark mode
    ```
  * Display brightness verified via macOS `DisplayServices.framework` ctypes bindings.
  * Audio volume verified via AppleScript:
    ```applescript
    output volume of (get volume settings)
    ```

---

## 7. Database Persistence Schema (SQLite)

EAOS uses an asynchronous-compatible SQLite database (`eaos.db`) with the following core tables:

1. **`decisions`**: Stores cycle assessments, chosen action, confidence, policy name, and user feedback.
2. **`cycles`**: Stores cycle boundary telemetry, phase timings, sensor sample counts, and window aggregates.
3. **`os_state_events`**: Precise transition log for Dark Mode and Focus Mode to calculate exact hardware durations.
4. **`camera_sessions`**: Records camera hardware open/close events for privacy auditing.
5. **`context_history`**: Periodic frontmost application and task category observations.
6. **`signal_baselines`**: Persisted EWMA mean, variance, sample counts, and last updated timestamps.
7. **`settings`**: Key-value store for user configurations (automation toggle, cycle duration, camera enabled).
