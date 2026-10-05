# Emotion-Aware Adaptive Operating System (EAOS)

*Research Documentation & Architectural Specification*

---

## 1. Abstract

Modern operating systems treat users identically regardless of whether they are deep in flow state, battling cognitive fatigue, or experiencing intense task friction. This research introduces **EAOS (Emotion-Aware Adaptive Operating System)**, a zero-prompt, user-space desktop adaptation system that continuously infers a user's affective and cognitive state from real multimodal behavioral signals (facial affect, keyboard typing cadence, mouse dynamics, active application context, and cognitive workload) and translates those inferences into native operating system adaptations—appearance modes, notification suppression, audio muting, and contextual break suggestions—in repeating 5-minute wall-clock cycles.

The core research contribution is the **Adaptive Score (AS)** framework: a personalized, mathematically grounded fusion of multimodal emotion, task context, cognitive workload, and an online Exponentially Weighted Moving Average (**EWMA**) behavioral baseline that drives an explore-exploit **LinUCB contextual bandit** policy engine. All computer vision, inference, and state calculations execute strictly on-device in RAM without cloud dependencies, demonstrating that affective computing can be delivered with uncompromising user privacy.

---

## 2. Research Problem & Motivation

Existing desktop focus tools (such as static Do Not Disturb timers, website blockers, and night shift schedules) rely on rigid, user-authored rules. They suffer from critical limitations:

1. **Affective Blindness**: They cannot differentiate between productive silence (deep flow) and unproductive struggle (staring at a compiler error or fatigued disengagement).
2. **Homogeneous Thresholds**: Behavioral baselines vary by orders of magnitude across individuals. A typing rate of 2.0 keys/sec might represent peak flow for one user and sluggish exhaustion for another.
3. **Absence of Credit Assignment**: Static rule engines cannot learn whether an intervention actually improved the user's focus or caused additional disruption.
4. **Modality Brittleness**: Fixed heuristics fail when a sensor (such as the camera) is disabled or obscured.

EAOS addresses these challenges by formalizing user state estimation as a continuous multimodal inference problem paired with online reinforcement learning.

---

## 3. Mathematical Formulations

### 3.1 Multimodal Emotion Estimation

The emotional state vector $\mathbf{E}(t) \in \Delta^5$ represents a probability distribution across six canonical discrete affective states:

$$\mathbf{E}(t) = \left[ P(\text{Focused}), P(\text{Flow State}), P(\text{Frustrated}), P(\text{Fatigued}), P(\text{Confused}), P(\text{Relaxed}) \right]^\top$$

The raw activation scores $s_i$ are computed from behavioral and facial signals:

$$s_{\text{focus}} = 0.15 + 0.45 \cdot \min(1, \frac{v_{\text{key}}}{4}) + 0.15 \cdot \mathbb{I}_{\text{face}} + 0.10 \cdot \mathbb{I}_{\text{eyes}} + 0.20 \cdot \mathbb{I}_{\text{work}} - 0.35 \cdot \min(1, 3 \cdot r_{\text{bs}})$$

$$s_{\text{flow}} = \left( 0.45 \cdot \min(1, \frac{v_{\text{key}}}{5}) + 0.25 \cdot \max(0, 1 - 6 r_{\text{bs}}) + 0.15 \cdot \max(0, 1 - 2 j_{\text{mouse}}) + 0.15 \cdot \mathbb{I}_{\text{eyes}} \right) \cdot \mathbb{I}_{\text{work}}$$

$$s_{\text{frust}} = 0.05 + 0.60 \cdot \min(1, 4.5 r_{\text{bs}}) + 0.25 \cdot \min(1, 2.5 j_{\text{mouse}}) + 0.15 \cdot \mathbb{I}_{\text{code}} - 0.10 \cdot \mathbb{I}_{\text{smile}}$$

$$s_{\text{fatigue}} = 0.05 + 0.35 \cdot \min(1, \frac{t_{\text{session}}}{45}) + 0.30 \cdot \Phi_{\text{face}} + 0.25 \cdot \mathbb{I}_{\text{sluggish}}$$

$$s_{\text{relax}} = 0.10 + 0.35 \cdot \max(0, 1 - \frac{v_{\text{key}}}{3}) + 0.25 \cdot \max(0, 1 - 2 u_{\text{cpu}}) + 0.20 \cdot \mathbb{I}_{\text{smile}} + 0.20 \cdot \mathbb{I}_{\text{media}}$$

Where:
* $v_{\text{key}}$ = typing cadence (keystrokes per second)
* $r_{\text{bs}}$ = backspace error ratio
* $j_{\text{mouse}}$ = mouse directional jitter
* $\Phi_{\text{face}}$ = facial fatigue / eye closure index
* $\mathbb{I}_{\text{smile}}, \mathbb{I}_{\text{eyes}}, \mathbb{I}_{\text{face}}$ = indicator functions from OpenCV Haar Cascade analysis

Probabilities are normalized via softmax / partition:
$$P(\text{emotion}_i) = \frac{s_i}{\sum_k s_k}$$

---

### 3.2 Personalization Engine (Online EWMA Learning)

To adapt to each user's unique baseline, EAOS continuously updates individual distribution statistics $(\mu, \sigma^2)$ for each signal $x \in \{ \text{workload}, v_{\text{key}}, r_{\text{bs}}, j_{\text{mouse}} \}$:

$$\mu_t = \alpha x_t + (1 - \alpha)\mu_{t-1}$$
$$\sigma_t^2 = (1 - \alpha)\left( \sigma_{t-1}^2 + \alpha(x_t - \mu_{t-1})^2 \right)$$

* **Spike Dampening**: If an observation coincides with severe acute distress (high frustration or exhaustion), $\alpha$ is attenuated by 75% ($\alpha_{\text{damp}} = 0.25\alpha$) so temporary stress does not skew long-term normal baselines.
* **Normalized Deviation ($z$-score)**:
  $$z_t = \frac{x_t - \mu_{t-1}}{\sigma_{t-1}}$$

---

### 3.3 The Adaptive Score (AS)

The global Adaptive Score $\text{AS} \in [0.00, 1.00]$ is a linear combination of four normalized components:

$$\text{AS} = w_e \cdot E + w_c \cdot C + w_w \cdot W + w_p \cdot P$$

* $w_e = 0.35$: Emotion Component (affective valence and focus)
* $w_c = 0.20$: Context Component (productive utility of active application)
* $w_w = 0.30$: Workload Component (cognitive load index: typing cadence, CPU, switching)
* $w_p = 0.15$: Personalization Component (normalized deviation $z$-score from individual baseline)

Constraint: $\sum w_i = 1.00$.

---

### 3.4 Decision Policy: LinUCB Contextual Bandit

EAOS formalizes zero-prompt adaptation as a contextual bandit with disjoint linear models. For each candidate adaptation $a \in \mathcal{A}$:

$$\text{Action} = \arg\max_{a \in \mathcal{A}} \left( \hat{\theta}_a^\top \mathbf{x}_t + \beta \sqrt{\mathbf{x}_t^\top \mathbf{A}_a^{-1} \mathbf{x}_t} \right)$$

Where:
* $\mathbf{x}_t \in \mathbb{R}^d$: The context vector containing $\text{AS}$, emotion probabilities, context category one-hot, and workload deviation.
* $\mathbf{A}_a = \mathbf{D}_a^\top \mathbf{D}_a + \mathbf{I}_d$: Covariance matrix of historical context vectors for arm $a$.
* $\hat{\theta}_a = \mathbf{A}_a^{-1} \mathbf{b}_a$: Ridge regression weight estimate for arm $a$.
* $\beta \ge 0$: Exploration parameter balancing confidence interval width against expected reward.

---

## 4. On-Device Privacy Architecture

Affective computing systems often face legitimate privacy resistance. EAOS addresses this by design:

1. **Strictly In-Memory Frame Processing**: The camera feed is analyzed in RAM via OpenCV. No raw frames, video clips, or face embeddings are ever written to disk or transmitted across networks.
2. **1-Minute Sensing Cycle**: The webcam hardware is initialized only during the 1-minute input collection window and is immediately powered down and released during the 4-minute adaptation phase.
3. **No Keystroke Content Capture**: Key codes and characters are discarded immediately. The system records only timestamp deltas ($\Delta t = t_i - t_{i-1}$) and the count of backspace key events.
4. **Local Hardware Actuation**: Adaptations execute locally via macOS Shortcuts and AppleScript APIs with zero external cloud dependencies.

---

## 5. Experimental Evaluation Framework

The system provides empirical tracking to validate four primary research hypotheses:

* **H1 (Personalization Benefit)**: An individual EWMA baseline significantly reduces false-positive adaptation triggers compared to population-average thresholds.
* **H2 (Multimodal Synergy)**: Fusing keystroke cadence, mouse dynamics, and facial valence achieves higher adaptation acceptance than single-modality sensors.
* **H3 (Bandit Convergence)**: The LinUCB policy converges to user-preferred adaptations within 15–20 feedback cycles.
* **H4 (Cognitive Load Reduction)**: Automated Do Not Disturb and dark mode adaptations during elevated workload measurably reduce error backspace rates in subsequent cycles.
