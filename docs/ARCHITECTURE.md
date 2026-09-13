# EAOS Architecture — 5-Minute Continuous Adaptive Cycle & Personalization

## Continuous 5-Minute Adaptive Pipeline

```text
       ┌────────────────────────────────────────────────────────┐
       │             EAOS START (Application Start)             │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │        CONTINUOUS 5-MINUTE ADAPTIVE CYCLE LOOP         │
       │         (Absolute Timestamp Drift Prevention)          │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │ MINUTES 0–5: REAL INPUT COLLECTION                     │
       │ • Keyboard Behavioral Cadence (Timing & Errors)        │
       │ • Mouse Dynamics, Speed & Directional Jitter           │
       │ • Active Application & Activity Classification         │
       │ • System Load & Continuous Cognitive Workload          │
       │ • Camera Facial Cues (When privacy toggle enabled)     │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │ AT EXACTLY 05:00: CYCLE ASSESSMENT                     │
       │ 1. Stop / Finalize Input Window                        │
       │ 2. Compare Inputs to Personal Baseline (EWMA/Z-Scores) │
       │ 3. Estimate Multimodal State & Personal Deviations     │
       │ 4. Calculate Adaptive Score (AS)                       │
       │ 5. Decision Engine Evaluates Adaptation Need           │
       │ 6. OS Actuator Applies Native macOS Action             │
       │ 7. Native User Notification Sent                       │
       │ 8. Update Learned Personal Baseline                    │
       │ 9. Reset Countdown Timer to 05:00                      │
       │ 10. Immediately Begin Next 5-Minute Input Window       │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
                         REPEAT CONTINUOUSLY
```

## Personalization Engine Details

1. **EWMA Baseline Learning**:
   Maintains individual statistical distributions (mean $\mu$, variance $\sigma^2$) for workload, typing rate, backspace rate, and mouse jitter.
   $$\mu_{t} = \alpha x_t + (1 - \alpha) \mu_{t-1}$$
   $$\sigma^2_{t} = (1 - \alpha)(\sigma^2_{t-1} + \alpha(x_t - \mu_{t-1})^2)$$
2. **Distress Dampening**:
   Observations marked by acute frustration or fatigue use an attenuated $\alpha$ so temporary distress does not distort the user's permanent normal baseline.
3. **Calibration Period**:
   The first 5 cycles run in `CALIBRATING` mode to establish initial baselines before aggressive personalization takes effect.
4. **Adaptive Score Integration**:
   $$\text{AS} = w_e \cdot E + w_c \cdot C + w_w \cdot W + w_p \cdot P$$
   Where $P$ measures the aggregate normalized deviation ($z$-scores) from the user's learned baseline.

## Analytics & OS State Duration Tracking

1. **Continuous Real Telemetry Auditing**:
   All 5-minute assessment cycles store raw behavioural metrics directly to SQLite:
   - Real typing speed (keys/sec), backspace rate, and personal baseline snapshot.
   - Mouse jitter score and baseline comparison.
   - Cognitive workload score (0–100%) vs personalized workload baseline.
   - Camera sensing activity flag and facial emotion probability distribution.
   - Adaptive Score (AS) calculation and triggered OS adaptation action.

2. **Accurate OS State Duration Tracking (`os_state_events`)**:
   Instead of estimating durations from periodic decision timestamps, EAOS logs exact OS transitions upon actuation:
   - `DARK_MODE` state transitions (`ON` / `OFF`)
   - `FOCUS_MODE` / DND state transitions (`ON` / `OFF`)
   Active durations are accumulated by computing the exact delta between timestamp transitions, providing true environmental state durations.

3. **Privacy & Hardware Sensing Activity (`camera_sessions`)**:
   Tracks camera hardware activation periods. When camera sensing is disabled or no facial observations are captured, the emotion graphs strictly reflect `No facial data available`, ensuring no artificial or synthetic values are generated.

