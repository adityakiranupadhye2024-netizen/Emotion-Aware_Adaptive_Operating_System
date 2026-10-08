import time
import math
import logging
from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional
from app.core.config import settings
from app.db.database import save_signal_baseline, load_signal_baselines, reset_signal_baselines

logger = logging.getLogger("eaos.engine")

ACTIONS = [
    'ENABLE_FOCUS_MODE',
    'DISABLE_FOCUS_MODE',
    'SILENCE_NOTIFICATIONS',
    'PAUSE_UPDATES',
    'SUGGEST_DEBUG_RESOURCE',
    'RECOMMEND_AI_CODE_ASSISTANT',
    'REDUCE_BRIGHTNESS',
    'RESTORE_BRIGHTNESS',
    'ENABLE_DARK_MODE',
    'DISABLE_DARK_MODE',
    'MUTE_AUDIO',
    'UNMUTE_AUDIO',
    'SET_VOLUME',
    'SUGGEST_BREAK',
    'DELAY_NON_URGENT_NOTIFICATIONS',
    'NO_ACTION'
]

@dataclass
class Decision:
    action: str
    reason: str
    confidence: float
    policy: str
    adaptive_score: float = 0.0
    personalization_summary: Optional[str] = None
    explanation: Optional[Dict[str, Any]] = None
    supporting_signals: Optional[Dict[str, Any]] = None
    context_confidence: float = 0.80


class LinUCBPolicyLearner:
    """
    Contextual Bandit (LinUCB) for automatic policy learning.
    Cold Start Progression:
      < 10 feedback samples: BASELINE (Deterministic Rule-Based Policy)
      10 - 25 samples: LEARNING (Observing, shadow-scoring, and updating weights)
      >= 25 samples: ADAPTIVE (LinUCB contextual action selection bounded by safety rules)
    """
    def __init__(self, actions: list, dimension: int = 7, alpha: float = 0.25):
        self.actions = actions
        self.d = dimension
        self.alpha = alpha
        self.A = {a: [[1.0 if i == j else 0.0 for j in range(self.d)] for i in range(self.d)] for a in actions}
        self.b = {a: [0.0] * self.d for a in actions}
        self.total_feedback_count = 0
        self._load_from_db()
        if self.total_feedback_count < 10:
            self.train_actuator_models()

    def _load_from_db(self):
        try:
            from app.db.database import get_all_policy_events
            events = get_all_policy_events()
            self.total_feedback_count = len(events)
            for ev in events:
                act = ev.get('action')
                if act in self.A:
                    as_val = float(ev.get('as_score', 0.5) or 0.5)
                    ctx_str = str(ev.get('context', 'CODING') or 'CODING')
                    ctx_map = {'CODING': 1.0, 'WRITING': 0.8, 'STUDYING': 0.6, 'BROWSING': 0.4, 'MEETING': 0.2, 'GAMING': 0.0, 'IDLE': -0.5}
                    ctx_val = ctx_map.get(ctx_str, 0.5)
                    feat = [1.0, 0.5, round(as_val, 2), 0.1, round(ctx_val, 2), 0.5, 0.5]
                    rew = float(ev.get('reward', 0.0) or 0.0)
                    for i in range(self.d):
                        self.A[act][i][i] += feat[i] * feat[i]
                        self.b[act][i] += rew * feat[i]
        except Exception as e:
            logger.warning(f"Error loading policy events from db: {e}")

    def train_actuator_models(self):
        """
        Calibrates and pre-trains LinUCB weights across all actuator buttons
        grounded in human-state ergonomics, cognitive strain, and background lighting.
        """
        training_samples = [
            # Dark Mode: Dim ambient lighting (< 0.25)
            ('ENABLE_DARK_MODE', [1.0, 0.40, 0.50, 0.10, 0.8, 0.4, 0.15], 1.0),
            ('ENABLE_DARK_MODE', [1.0, 0.55, 0.60, 0.00, 1.0, 0.5, 0.08], 1.0),
            # Light Mode: Bright ambient lighting (> 0.65)
            ('DISABLE_DARK_MODE', [1.0, 0.35, 0.50, 0.20, 0.8, 0.3, 0.85], 1.0),
            ('DISABLE_DARK_MODE', [1.0, 0.25, 0.45, 0.30, 0.4, 0.2, 0.75], 1.0),
            # Focus Mode (Turn ON DND): High cognitive workload / deep focus
            ('ENABLE_FOCUS_MODE', [1.0, 0.80, 0.75, 0.40, 1.0, 0.8, 0.50], 1.0),
            ('ENABLE_FOCUS_MODE', [1.0, 0.70, 0.70, 0.35, 0.8, 0.7, 0.45], 1.0),
            # Turn OFF DND: Low workload / relaxation / recovery
            ('DISABLE_FOCUS_MODE', [1.0, 0.15, 0.35, 0.50, 0.4, 0.1, 0.50], 1.0),
            ('DISABLE_FOCUS_MODE', [1.0, 0.10, 0.30, 0.40, -0.5, 0.0, 0.50], 1.0),
            # Mute Audio: High frustration / typing friction / sensory relief
            ('MUTE_AUDIO', [1.0, 0.70, 0.40, -0.45, 1.0, 0.5, 0.50], 1.0),
            ('MUTE_AUDIO', [1.0, 0.65, 0.45, -0.35, 0.8, 0.6, 0.40], 1.0),
            # Unmute Audio: Relaxed state / media / workload eased
            ('UNMUTE_AUDIO', [1.0, 0.20, 0.45, 0.60, 0.4, 0.2, 0.50], 1.0),
            ('UNMUTE_AUDIO', [1.0, 0.15, 0.40, 0.55, 0.2, 0.1, 0.50], 1.0),
            # Reduce Brightness: Visual fatigue / glare / eye strain
            ('REDUCE_BRIGHTNESS', [1.0, 0.60, 0.45, -0.25, 0.8, 0.3, 0.20], 1.0),
            # Restore Brightness: Balanced / daytime recovery
            ('RESTORE_BRIGHTNESS', [1.0, 0.30, 0.55, 0.30, 0.8, 0.4, 0.70], 1.0),
            # Break Suggestion: Sustained fatigue
            ('SUGGEST_BREAK', [1.0, 0.55, 0.35, -0.30, 0.6, 0.2, 0.40], 1.0),
        ]

        for act, feat, rew in training_samples:
            if act in self.A:
                for i in range(self.d):
                    self.A[act][i][i] += feat[i] * feat[i]
                    self.b[act][i] += rew * feat[i]
                self.total_feedback_count += 1
        logger.info(f"Calibrated LinUCB actuator models with {len(training_samples)} trained ergonomic samples.")

    @property
    def status(self) -> str:
        if self.total_feedback_count == 0:
            return "BASELINE"
        elif self.total_feedback_count < 4:
            return "LEARNING"
        return "ADAPTIVE"

    def featurize(self, state: dict, as_score: float, context: str) -> list:
        workload = float(state.get('workload', {}).get('score', 0.4))
        probs = state.get('emotion', {}).get('probabilities', {})
        valence = float(probs.get('Focused', 0.5) - probs.get('Frustrated', 0.1) - probs.get('Fatigued', 0.1))

        ctx_map = {'CODING': 1.0, 'WRITING': 0.8, 'STUDYING': 0.6, 'BROWSING': 0.4, 'MEETING': 0.2, 'GAMING': 0.0, 'IDLE': -0.5}
        ctx_val = ctx_map.get(context, 0.3)

        kb = state.get('inputs', {}).get('keyboard', {})
        typing_rate = kb.get('avg_typing_rate', kb.get('typing_rate', 0.0))
        typing_norm = min(1.0, max(0.0, typing_rate / 6.0))

        cam = state.get('inputs', {}).get('camera', {})
        ambient = float(cam.get('ambient_light', 0.5))

        return [1.0, round(workload, 2), round(as_score, 2), round(valence, 2), round(ctx_val, 2), round(typing_norm, 2), round(ambient, 2)]

    def predict(self, feature_vector: list, candidate_actions: list) -> Tuple[str, float, float]:
        best_a = candidate_actions[0] if candidate_actions else 'NO_ACTION'
        best_val = -1e9

        for a in candidate_actions:
            if a not in self.A:
                continue
            A_diag = [self.A[a][i][i] for i in range(self.d)]
            theta = [self.b[a][i] / max(0.1, A_diag[i]) for i in range(self.d)]
            dot = sum(theta[i] * feature_vector[i] for i in range(self.d))
            variance = sum((feature_vector[i] ** 2) / max(0.1, A_diag[i]) for i in range(self.d))
            ucb = dot + self.alpha * math.sqrt(max(0.001, variance))

            if ucb > best_val:
                best_val = ucb
                best_a = a

        conf = min(0.95, max(0.65, 0.75 + 0.05 * min(4, self.total_feedback_count // 2)))
        return best_a, conf, best_val

    def update(self, action: str, state_or_vector: Any, reward: float, source: str = "FEEDBACK"):
        if action not in self.A:
            return
        if isinstance(state_or_vector, list):
            feat = state_or_vector
        elif isinstance(state_or_vector, dict):
            feat = self.featurize(
                state_or_vector,
                state_or_vector.get('adaptive_score', 0.5),
                state_or_vector.get('context', {}).get('canonical_context', 'UNKNOWN') if isinstance(state_or_vector.get('context'), dict) else str(state_or_vector.get('context', 'UNKNOWN'))
            )
        else:
            feat = [1.0, 0.5, 0.5, 0.0, 0.3, 0.5, 0.5]

        self.total_feedback_count += 1
        for i in range(self.d):
            self.A[action][i][i] += feat[i] * feat[i]
            self.b[action][i] += reward * feat[i]

        from app.db.database import record_policy_event
        try:
            ctx_str = str(state_or_vector.get('context', '')) if isinstance(state_or_vector, dict) else ''
            as_val = float(state_or_vector.get('adaptive_score', 0.0)) if isinstance(state_or_vector, dict) else 0.0
            record_policy_event(
                policy_name="LinUCB",
                action=action,
                reward=reward,
                context=ctx_str,
                as_score=as_val,
                details=f"Source: {source}, Sample #{self.total_feedback_count}"
            )
        except Exception:
            pass

    def snapshot(self) -> Dict[str, Any]:
        return {
            'status': self.status,
            'total_feedback_count': self.total_feedback_count,
            'algorithm': 'LinUCB Contextual Bandit',
            'supported_actions': self.actions
        }

    def get_status(self) -> Dict[str, Any]:
        return self.snapshot()


class PersonalizationEngine:
    """
    Maintains and updates personal baselines using Exponentially Weighted Moving Averages (EWMA)
    and computes personal z-score deviations to estimate how unusual current behavior is.
    """
    def __init__(self):
        # signal_name -> [mean, variance, observations]
        self.baselines: Dict[str, list] = {}
        self.total_cycle_samples: int = 0
        self._load_from_db()

    def _load_from_db(self):
        try:
            saved = load_signal_baselines()
            if saved:
                for sig, data in saved.items():
                    self.baselines[sig] = [data['mean'], data['variance'], data['observations']]
                self.total_cycle_samples = max(d['observations'] for d in saved.values()) if saved else 0
                logger.info(f"Loaded {len(self.baselines)} signal baselines from SQLite.")
        except Exception as e:
            logger.warning(f"Failed loading baselines: {e}")

    def reset(self):
        self.baselines.clear()
        self.total_cycle_samples = 0
        try:
            reset_signal_baselines()
            logger.info("Personal baseline statistics reset successfully.")
        except Exception as e:
            logger.error(f"Error resetting signal baselines: {e}")

    @property
    def status(self) -> str:
        if not settings.personalization_enabled:
            return "DISABLED"
        if self.total_cycle_samples < settings.calibration_cycles:
            return "CALIBRATING"
        if self.total_cycle_samples < (settings.calibration_cycles * 3):
            return "LEARNING"
        return "ACTIVE"

    def get_signal_mean(self, signal: str, default: float) -> float:
        if signal in self.baselines and self.baselines[signal][2] > 0:
            return float(self.baselines[signal][0])
        return default

    def get_signal_variance(self, signal: str, default: float = 0.05) -> float:
        if signal in self.baselines and self.baselines[signal][2] > 0:
            return max(0.001, float(self.baselines[signal][1]))
        return default

    def update_signal(self, signal: str, value: float, is_extreme: bool = False):
        """Updates personal baseline using EWMA. Dampens learning rate during extreme distress."""
        if not settings.personalization_enabled:
            return

        alpha = settings.personalization_alpha
        # If the user is currently in acute frustration or fatigue, do not allow it to quickly shift normal
        if is_extreme:
            alpha = alpha * 0.20

        if signal not in self.baselines:
            # First observation
            self.baselines[signal] = [float(value), 0.04, 1]
        else:
            mean, var, n = self.baselines[signal]
            new_mean = mean + alpha * (value - mean)
            new_var = (1 - alpha) * (var + alpha * ((value - mean) ** 2))
            self.baselines[signal] = [new_mean, max(0.001, new_var), n + 1]

        # Save to database
        try:
            b = self.baselines[signal]
            save_signal_baseline(signal, b[0], b[1], b[2])
        except Exception:
            pass

    def record_cycle_observation(self, state: Dict[str, Any], is_extreme: bool = False):
        """Updates all key personal signal baselines after a cycle evaluation."""
        if not settings.personalization_enabled:
            return

        self.total_cycle_samples += 1

        workload = state.get('workload', {}).get('score', 0.40)
        kb = state.get('inputs', {}).get('keyboard', {})
        ms = state.get('inputs', {}).get('mouse', {})
        probs = state.get('emotion', {}).get('probabilities', {})

        self.update_signal('workload', workload, is_extreme)

        typing_rate = kb.get('avg_typing_rate', kb.get('typing_rate', 0.0))
        backspace_rate = kb.get('avg_backspace_rate', kb.get('backspace_rate', 0.0))
        if typing_rate > 0.1:
            self.update_signal('typing_rate', typing_rate, is_extreme)
        self.update_signal('backspace_rate', backspace_rate, is_extreme)

        jitter = ms.get('avg_jitter', ms.get('jitter', 0.0))
        mouse_active = 0.0 if ms.get('idle', False) else 1.0
        self.update_signal('mouse_jitter', jitter, is_extreme)
        self.update_signal('mouse_activity', mouse_active, is_extreme)

        self.update_signal('focus', probs.get('Focused', 0.3), is_extreme)
        self.update_signal('frustration', probs.get('Frustrated', 0.05), is_extreme)
        self.update_signal('fatigue', probs.get('Fatigued', 0.05), is_extreme)

    def calculate_personal_deviations(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Compares current state against learned personal baseline."""
        workload = state.get('workload', {}).get('score', 0.40)
        kb = state.get('inputs', {}).get('keyboard', {})
        ms = state.get('inputs', {}).get('mouse', {})

        typing_rate = kb.get('avg_typing_rate', kb.get('typing_rate', 0.0))
        jitter = ms.get('avg_jitter', ms.get('jitter', 0.0))

        base_workload = self.get_signal_mean('workload', 0.35)
        base_typing = self.get_signal_mean('typing_rate', 3.0)
        base_jitter = self.get_signal_mean('mouse_jitter', 0.10)

        workload_dev = workload - base_workload
        typing_dev = typing_rate - base_typing
        jitter_dev = jitter - base_jitter

        # Z-Scores
        var_w = self.get_signal_variance('workload', 0.04)
        z_workload = workload_dev / math.sqrt(var_w)

        var_t = self.get_signal_variance('typing_rate', 0.8)
        z_typing = typing_dev / math.sqrt(var_t)

        var_j = self.get_signal_variance('mouse_jitter', 0.02)
        z_jitter = jitter_dev / math.sqrt(var_j)

        return {
            'workload': {
                'current': round(workload, 2),
                'baseline': round(base_workload, 2),
                'deviation': round(workload_dev, 2),
                'z_score': round(z_workload, 2)
            },
            'typing_rate': {
                'current': round(typing_rate, 1),
                'baseline': round(base_typing, 1),
                'deviation': round(typing_dev, 1),
                'z_score': round(z_typing, 2)
            },
            'mouse_jitter': {
                'current': round(jitter, 3),
                'baseline': round(base_jitter, 3),
                'deviation': round(jitter_dev, 3),
                'z_score': round(z_jitter, 2)
            }
        }

    def compute_unusualness_component(self, state: Dict[str, Any]) -> float:
        """
        Calculates the PersonalizationComponent of Adaptive Score (AS).
        Evaluates how far current inputs deviate from the user's personal baseline.
        Normalized to 0.00 – 1.00.
        """
        if not settings.personalization_enabled or self.total_cycle_samples < 2:
            return 0.50

        devs = self.calculate_personal_deviations(state)
        z_w = max(0.0, devs['workload']['z_score'])
        z_j = max(0.0, devs['mouse_jitter']['z_score'])
        # Negative typing z-score indicates sluggishness/fatigue
        z_t_neg = max(0.0, -devs['typing_rate']['z_score'])

        # Sigmoid-like normalization into 0.0 - 1.0 range
        composite_z = 0.5 * z_w + 0.3 * z_j + 0.2 * z_t_neg
        unusualness = 1.0 / (1.0 + math.exp(-0.8 * (composite_z - 1.0)))
        return max(0.05, min(0.95, round(unusualness, 3)))

    def snapshot(self) -> Dict[str, Any]:
        return {
            'status': self.status,
            'enabled': settings.personalization_enabled,
            'samples': self.total_cycle_samples,
            'calibration_cycles': settings.calibration_cycles,
            'alpha': settings.personalization_alpha,
            'adaptation_speed': settings.baseline_adaptation,
            'baselines': {
                k: {
                    'mean': round(v[0], 3),
                    'variance': round(v[1], 3),
                    'std': round(math.sqrt(v[1]), 3),
                    'observations': v[2]
                } for k, v in self.baselines.items()
            }
        }

# Maintain backward compatibility alias
Personalization = PersonalizationEngine

class DecisionEngine:
    def __init__(self):
        self.personalization = PersonalizationEngine()
        self.policy_learner = LinUCBPolicyLearner(ACTIONS)
        self.last_action = 'NO_ACTION'
        self.last_action_time: Dict[str, float] = {}
        self.action_history = []
        self.use_bandit = False

        # OS State Persistence to prevent flapping / duplicate actions
        self.in_focus_mode = False
        self.dark_mode_active = False
        self.audio_muted = False

    def reset(self):
        self.last_action = 'NO_ACTION'
        self.last_action_time.clear()
        self.action_history.clear()
        self.in_focus_mode = False
        self.dark_mode_active = False
        self.audio_muted = False

    def calculate_as(self, state: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
        """
        Calculates the Adaptive Score (AS) combining:
        - EmotionComponent (valence and focus)
        - ContextComponent (relevance of active task * context confidence)
        - PersonalizationComponent (deviation from user's learned personal baseline)
        - WorkloadComponent (cognitive demand)
        Normalized to 0.00 – 1.00.
        Formula:
          AS = 0.35 * Emotion + 0.20 * Context + 0.30 * Workload + 0.15 * Personalization
        """
        probs = state.get('emotion', {}).get('probabilities', {})
        e = (
            probs.get('Focused', 0.0)
            + 0.6 * probs.get('Flow State', 0.0)
            - 0.4 * probs.get('Frustrated', 0.0)
            - 0.3 * probs.get('Fatigued', 0.0)
        )
        e_norm = max(0.0, min(1.0, 0.5 + e * 0.5))

        ctx_info = state.get('context', {})
        context = str(ctx_info.get('context', ctx_info.get('activity', 'GENERAL_WORK'))).upper()
        ctx_conf = float(ctx_info.get('confidence', ctx_info.get('context_confidence', 0.85)))

        if context in ['CODING', 'WRITING', 'STUDYING']:
            base_c = 0.90
        elif context in ['MEETING']:
            base_c = 0.70
        elif context in ['BROWSING']:
            base_c = 0.50
        elif context in ['GAMING', 'IDLE']:
            base_c = 0.30
        else:
            base_c = 0.45

        c_eff = max(0.0, min(1.0, base_c * ctx_conf))
        w = float(state.get('workload', {}).get('score', 0.45))
        p = float(self.personalization.compute_unusualness_component(state))

        weights = settings.as_weights
        w_e = float(weights.get('emotion', 0.35))
        w_c = float(weights.get('context', 0.20))
        w_w = float(weights.get('workload', 0.30))
        w_p = float(weights.get('personalization', 0.15))

        total_weight = w_e + w_c + w_w + w_p
        score = (w_e * e_norm + w_c * c_eff + w_w * w + w_p * p) / max(0.01, total_weight)
        score = max(0.0, min(1.0, round(score, 3)))

        components = {
            'emotion': round(e_norm, 3),
            'context': round(c_eff, 3),
            'workload': round(w, 3),
            'personalization': round(p, 3)
        }
        return score, components

    def decide(self, state: Dict[str, Any]) -> Decision:
        now = time.time()
        score, components = self.calculate_as(state)
        emotion = state.get('emotion', {}).get('dominant', 'Focused')
        probs = state.get('emotion', {}).get('probabilities', {})
        evidence = state.get('emotion', {}).get('evidence_signals', {})
        workload = float(state.get('workload', {}).get('score', 0.40))

        ctx_info = state.get('context', {})
        context = str(ctx_info.get('context', ctx_info.get('activity', 'GENERAL_WORK'))).upper()
        context_conf = float(ctx_info.get('context_confidence', ctx_info.get('confidence', 0.80)))

        inputs = state.get('inputs', {})
        cam = inputs.get('camera', {})
        kb = inputs.get('keyboard', {})
        ms = inputs.get('mouse', {})

        typing_rate = float(kb.get('typing_rate', 0.0))
        backspace_rate = float(kb.get('backspace_rate', 0.0))
        typing_activity_ratio = float(kb.get('typing_activity_ratio', 0.5 if typing_rate > 0 else 0.0))
        mouse_active_ratio = float(ms.get('mouse_active_ratio', 0.5 if not ms.get('idle') else 0.0))
        mouse_agitation = float(evidence.get('mouse_agitation_score', ms.get('jitter', 0.0)))

        frustration_signal = float(evidence.get('frustration_signal', probs.get('Frustrated', 0.0)))
        fatigue_signal = float(evidence.get('fatigue_signal', probs.get('Fatigued', 0.0)))
        focus_signal = float(evidence.get('focus_signal', probs.get('Focused', 0.0)))
        relaxed_signal = float(evidence.get('relaxed_signal', probs.get('Relaxed', 0.0)))

        cam_conditions = cam.get('conditions', {})
        ambient = float(cam.get('ambient_light', 0.50))
        dim_proxy = bool(cam_conditions.get('dim_proxy', ambient < 0.25))
        bright_proxy = bool(cam_conditions.get('bright_proxy', ambient > 0.65))
        cam_valid = bool(cam_conditions.get('valid_camera_observation', cam.get('confidence', 0.0) >= 0.5))

        # Synchronize with ground truth OS state
        real_os = state.get('actual_os_state') or {}
        if 'dark_mode' in real_os and real_os['dark_mode'] is not None:
            self.dark_mode_active = bool(real_os['dark_mode'])
        if 'focus_mode_active' in real_os and real_os['focus_mode_active'] is not None:
            self.in_focus_mode = bool(real_os['focus_mode_active'])
        if 'audio_muted' in real_os and real_os['audio_muted'] is not None:
            self.audio_muted = bool(real_os['audio_muted'])
        curr_brightness = float(real_os.get('brightness', 0.50))
        curr_volume = int(real_os.get('volume', 50))

        # Personalization deviations
        devs = self.personalization.calculate_personal_deviations(state)
        workload_dev = float(devs['workload']['deviation'])
        workload_z = float(devs['workload']['z_score'])
        is_calibrating = (self.personalization.status == "CALIBRATING")

        # Decision confidence
        sensor_coverage = 0
        if kb.get('active', False) and (typing_rate > 0.0 or kb.get('events', 0) > 0):
            sensor_coverage += 1
        if ms.get('active', False) and not ms.get('idle', True):
            sensor_coverage += 1
        if cam_valid:
            sensor_coverage += 1

        base_conf = 0.65 + (0.15 * context_conf) + (0.06 * sensor_coverage)
        if is_calibrating:
            base_conf = min(0.85, base_conf)
        else:
            base_conf = min(0.96, base_conf + 0.04)
        conf = round(base_conf, 2)

        # Confidence Guard: if overall confidence is too low, fail closed to NO_ACTION
        if conf < settings.thresholds.get('decision_score_min', 0.30):
            return Decision(
                action='NO_ACTION',
                reason='Insufficient sensor confidence for automatic adaptation.',
                confidence=conf,
                policy='Confidence Guard',
                adaptive_score=score,
                explanation={
                    'assessment_window': f"{int(settings.get_effective_cycle_seconds() / 60)} minute" if settings.get_effective_cycle_seconds() == 60 else f"{settings.get_effective_cycle_seconds() / 60:.1f} minutes",
                    'context': context,
                    'context_confidence': int(context_conf * 100),
                    'emotion': emotion,
                    'workload': f"{int(workload * 100)}%",
                    'adaptive_score': score,
                    'decision_confidence': int(conf * 100),
                    'action': 'NO_ACTION',
                    'why': 'Insufficient sensor confidence for automatic adaptation.',
                    'factors': ['Confidence below safety threshold']
                }
            )

        # ---------------------------------------------------------------------
        # DETERMINISTIC SAFETY & DECISION HIERARCHY (Parts 9, 10, 18)
        # ---------------------------------------------------------------------
        action = 'NO_ACTION'
        reason = 'Activity nominal. User state remained stable within comfort thresholds.'
        personal_note = None
        contributing_factors = []

        # 1. PRIORITY 1: MEETING SAFETY (Never mute meeting audio, suppress intrusive changes)
        if context == 'MEETING':
            if self.audio_muted:
                action = 'UNMUTE_AUDIO'
                reason = 'Active meeting detected; system audio unmuted so call audio remains audible.'
                self.audio_muted = False
                contributing_factors.append('Meeting audio safeguard')
            elif fatigue_signal >= 0.60:
                action = 'SUGGEST_BREAK'
                reason = f'Elevated fatigue ({int(fatigue_signal * 100)}%) during meeting; break reminder suggested.'
                contributing_factors.append('Fatigue during meeting')
            else:
                action = 'NO_ACTION'
                reason = 'Active meeting in progress. Intrusive desktop adaptations suppressed.'
                contributing_factors.append('Meeting safety guard active')

        # 2. PRIORITY 2: GAMING SAFETY (Suppress intrusive interruptions)
        elif context == 'GAMING':
            action = 'NO_ACTION'
            reason = 'Active gaming session detected. Adaptations suppressed to prevent interruption.'
            contributing_factors.append('Gaming context active')

        # 3. PRIORITY 3: IDLE / USER AWAY (Part 9, Action 2 & Part 28 Scenario G)
        elif context == 'IDLE' or (typing_activity_ratio < 0.10 and mouse_active_ratio < 0.10 and ms.get('idle', False)):
            if self.in_focus_mode:
                action = 'DISABLE_FOCUS_MODE'
                reason = 'User is away or idle. Native Focus Mode disengaged.'
                self.in_focus_mode = False
                contributing_factors.append('Idle state observed')
            elif self.audio_muted:
                action = 'UNMUTE_AUDIO'
                reason = 'User is idle; standard system audio unmuted.'
                self.audio_muted = False
                contributing_factors.append('Idle audio restoration')
            elif curr_brightness < 0.45:
                action = 'RESTORE_BRIGHTNESS'
                reason = 'User is idle; standard display brightness restored.'
                contributing_factors.append('Idle brightness recovery')
            else:
                action = 'NO_ACTION'
                reason = 'User currently idle. System state nominal.'
                contributing_factors.append('Idle state nominal')

        # 4. ACTIVE WORK CONTEXTS (CODING, WRITING, STUDYING, GENERAL_WORK)
        else:
            # Step A: STRONG FRUSTRATION -> MUTE_AUDIO (Part 9, Action 3)
            # Requires multi-modal agreement (kb correction + mouse agitation) or severe frustration signal
            is_frustrated = (
                (frustration_signal >= 0.60 and (backspace_rate >= 0.10 or mouse_agitation >= 0.35))
                or (frustration_signal >= 0.75)
            )
            if is_frustrated and not self.audio_muted:
                action = 'MUTE_AUDIO'
                reason = (
                    f"Elevated typing correction ({int(backspace_rate * 100)}%) and cursor agitation "
                    f"during {context.lower()} session indicated sustained frustration. Audio was muted to minimize distraction."
                )
                self.audio_muted = True
                contributing_factors.append(f"Typing correction {int(backspace_rate * 100)}%")
                contributing_factors.append(f"Mouse agitation {mouse_agitation:.2f}")

            # Step B: STRONG FATIGUE / VISUAL STRAIN -> REDUCE_BRIGHTNESS (Part 9, Action 7)
            elif (fatigue_signal >= 0.55 or (fatigue_signal >= 0.45 and cam_conditions.get('persistent_low_eye_visibility', False))) and curr_brightness > 0.45:
                action = 'REDUCE_BRIGHTNESS'
                reason = f'Elevated visual fatigue ({int(fatigue_signal * 100)}%) detected; display brightness reduced to relieve eye strain.'
                contributing_factors.append('Visual fatigue indicators')
                contributing_factors.append(f'Current brightness {int(curr_brightness * 100)}% > 45%')

            # Step C: HIGH WORKLOAD / DEEP FOCUS -> ENABLE_FOCUS_MODE (Part 9, Action 1)
            # Must satisfy: workload >= 0.60 OR workload z-score >= +1.5 OR focus_signal >= 0.65 with productive context
            # AND typing or mouse activity >= 0.35 AND context_conf >= 0.60 AND Focus is OFF
            elif (
                (workload >= 0.60 or workload_z >= 1.5 or (focus_signal >= 0.65 and context in ['CODING', 'WRITING', 'STUDYING']))
                and (typing_activity_ratio >= 0.35 or mouse_active_ratio >= 0.35)
                and context_conf >= 0.60
                and not self.in_focus_mode
            ):
                action = 'ENABLE_FOCUS_MODE'
                if workload_z >= 1.5 and not is_calibrating:
                    reason = f'Workload was significantly higher than personal baseline (z={workload_z:+.1f}) while {context.lower()}; Focus Mode engaged.'
                    personal_note = f"Personal workload deviation: {workload_dev:+.2f}"
                    contributing_factors.append('Personal baseline deviation exceeded')
                else:
                    reason = f'Elevated cognitive workload ({int(workload * 100)}%) in {context.lower()}; desktop notifications silenced & Focus Mode engaged.'
                    contributing_factors.append('High cognitive workload')
                self.in_focus_mode = True

            # Step D: VISUAL ENVIRONMENT LIGHTING (Part 9, Actions 5 & 6)
            # ENABLE_DARK_MODE: camera valid AND dim proxy persistently < 0.25 AND productive context AND (fatigue >= 0.35 OR workload >= 0.40) AND not already dark
            elif cam_valid and dim_proxy and (fatigue_signal >= 0.35 or workload >= 0.40) and not self.dark_mode_active:
                action = 'ENABLE_DARK_MODE'
                reason = f'Low ambient illumination proxy ({ambient:.2f} < 0.25) during focused work; macOS Dark Mode engaged for eye comfort.'
                self.dark_mode_active = True
                contributing_factors.append('Low ambient illumination')

            # DISABLE_DARK_MODE: camera valid AND bright proxy persistently > 0.65 AND user actively working AND fatigue not elevated AND already dark
            elif cam_valid and bright_proxy and (typing_activity_ratio >= 0.20 or mouse_active_ratio >= 0.20) and fatigue_signal < 0.30 and self.dark_mode_active:
                action = 'DISABLE_DARK_MODE'
                reason = f'Bright ambient illumination proxy ({ambient:.2f} > 0.65); macOS Light appearance restored.'
                self.dark_mode_active = False
                contributing_factors.append('Bright ambient illumination')

            # Step E: RECOVERY / RESTORATION (Part 9, Actions 2, 4, 8)
            elif self.audio_muted and (relaxed_signal >= 0.60 or workload < 0.30 or frustration_signal < 0.25):
                action = 'UNMUTE_AUDIO'
                reason = 'Cognitive workload eased and frustration subsided; system audio restored to original user volume.'
                self.audio_muted = False
                contributing_factors.append('Frustration recovery')

            elif self.in_focus_mode and (relaxed_signal >= 0.60 or workload < 0.30) and typing_rate < 0.30:
                action = 'DISABLE_FOCUS_MODE'
                reason = 'Workload eased and user entered relaxed recovery; native Focus Mode disengaged.'
                self.in_focus_mode = False
                contributing_factors.append('Focus recovery')

            elif curr_brightness < 0.50 and (relaxed_signal >= 0.60 or bright_proxy) and fatigue_signal < 0.25:
                action = 'RESTORE_BRIGHTNESS'
                reason = 'Visual strain cleared and ambient environment bright; original display brightness restored.'
                contributing_factors.append('Brightness recovery')

        # ---------------------------------------------------------------------
        # AUTOMATIC POLICY LEARNING WITH STRICT SAFETY GUARDS (Part 19 - LinUCB)
        # ---------------------------------------------------------------------
        candidate_actions = ['NO_ACTION']

        if context == 'GAMING':
            # Priority safety: Zero intrusive adaptations during gaming
            candidate_actions = ['NO_ACTION']
        elif context == 'MEETING':
            # Priority safety: Never mute or dim during meeting
            candidate_actions = ['NO_ACTION']
            if self.audio_muted:
                candidate_actions.append('UNMUTE_AUDIO')
        elif context == 'IDLE':
            # Only restorations allowed during idle
            candidate_actions = ['NO_ACTION']
            if self.in_focus_mode:
                candidate_actions.append('DISABLE_FOCUS_MODE')
            if self.audio_muted:
                candidate_actions.append('UNMUTE_AUDIO')
            if curr_brightness < 0.45:
                candidate_actions.append('RESTORE_BRIGHTNESS')
        else:
            # Active work contexts: strictly safe legal actions
            # Focus Mode candidates: only when actively working
            if not self.in_focus_mode:
                if context in ['CODING', 'WRITING', 'STUDYING', 'GENERAL_WORK'] and not (typing_activity_ratio < 0.15 and mouse_active_ratio < 0.15):
                    candidate_actions.append('ENABLE_FOCUS_MODE')
            else:
                candidate_actions.append('DISABLE_FOCUS_MODE')

            # Dark Mode candidates: only when camera data is valid
            if cam_valid:
                if not self.dark_mode_active:
                    candidate_actions.append('ENABLE_DARK_MODE')
                else:
                    candidate_actions.append('DISABLE_DARK_MODE')

            # Audio candidates: only if frustration is elevated
            if not self.audio_muted:
                if frustration_signal >= 0.50:
                    candidate_actions.append('MUTE_AUDIO')
            else:
                candidate_actions.append('UNMUTE_AUDIO')

            # Brightness candidates: only if fatigue is elevated
            if fatigue_signal >= 0.45 and curr_brightness > 0.45:
                candidate_actions.append('REDUCE_BRIGHTNESS')
            if curr_brightness < 0.50 and fatigue_signal < 0.30:
                candidate_actions.append('RESTORE_BRIGHTNESS')

        if action not in candidate_actions:
            candidate_actions.append(action)

        policy_name = 'Baseline Rules'
        if self.policy_learner.total_feedback_count > 0 and context not in ['MEETING', 'GAMING']:
            features = self.policy_learner.featurize(state, score, context)
            best_bandit_action, bandit_conf, bandit_val = self.policy_learner.predict(features, candidate_actions)

            if self.policy_learner.status in ['LEARNING', 'ADAPTIVE']:
                if action == 'NO_ACTION' and best_bandit_action != 'NO_ACTION' and bandit_val > 0.10:
                    action = best_bandit_action
                    conf = bandit_conf
                    policy_name = f'Learned LinUCB ({self.policy_learner.status})'
                    reason = f'Learned policy selected {action.replace("_", " ").title()} based on {self.policy_learner.total_feedback_count} feedback samples (Bandit UCB score: {bandit_val:.2f}).'
                    contributing_factors.append(f'Learned bandit recommendation ({action})')
                elif (
                    self.policy_learner.status == 'ADAPTIVE'
                    and best_bandit_action != action
                    and bandit_val > 0.25
                    and action not in ['ENABLE_DARK_MODE', 'DISABLE_DARK_MODE', 'MUTE_AUDIO', 'UNMUTE_AUDIO']
                    and context not in ['MEETING', 'IDLE', 'GAMING']
                ):
                    old_action = action
                    action = best_bandit_action
                    conf = bandit_conf
                    policy_name = 'Learned LinUCB (Active Override)'
                    reason = f'Learned policy prioritized {action.replace("_", " ").title()} over {old_action.replace("_", " ").title()} based on user satisfaction history (Bandit UCB: {bandit_val:.2f}).'
                    contributing_factors.append(f'Learned override of {old_action}')
                else:
                    policy_name = f'Baseline Rules ({self.policy_learner.status} Active)'

        # Check for extreme distress state before updating personalization baselines
        is_extreme = emotion in ['Frustrated', 'Fatigued'] and (workload > 0.70 or backspace_rate > 0.20)
        self.personalization.record_cycle_observation(state, is_extreme=is_extreme)

        if action != 'NO_ACTION':
            self.last_action = action
            self.last_action_time[action] = now
            self.action_history.append((now, action, reason))

        # ---------------------------------------------------------------------
        # STRUCTURED DECISION EXPLANATION (Part 22)
        # ---------------------------------------------------------------------
        explanation = {
            'assessment_window': f"{int(settings.get_effective_cycle_seconds() / 60)} minute" if settings.get_effective_cycle_seconds() == 60 else f"{settings.get_effective_cycle_seconds() / 60:.1f} minutes",
            'context': context.title(),
            'context_confidence': int(context_conf * 100),
            'emotion': f"{emotion} ({int(probs.get(emotion, 0.5) * 100)}%)",
            'workload': f"{int(workload * 100)}%",
            'personal_baseline_workload': f"{int(devs['workload']['baseline'] * 100)}%",
            'workload_deviation': f"{workload_dev:+.2f}",
            'typing_rate': f"{typing_rate:.1f} keys/s",
            'backspace_ratio': f"{int(backspace_rate * 100)}%",
            'mouse_agitation': round(mouse_agitation, 2),
            'adaptive_score': score,
            'decision_confidence': int(conf * 100),
            'selected_action': action.replace('_', ' ').title(),
            'why': reason,
            'policy': policy_name,
            'policy_status': self.policy_learner.status,
            'factors': contributing_factors or ['Nominal behavioural pattern']
        }

        supporting_signals = {
            'context': context,
            'context_confidence': context_conf,
            'workload': workload,
            'baseline_workload': devs['workload']['baseline'],
            'workload_deviation': workload_dev,
            'typing_rate': typing_rate,
            'typing_deviation': devs['typing_rate']['deviation'],
            'dominant_emotion': emotion,
            'emotion_confidence': probs.get(emotion, 0.5),
            'adaptive_score': score,
            'decision_confidence': conf
        }

        return Decision(
            action=action,
            reason=reason,
            confidence=conf,
            policy=policy_name,
            adaptive_score=score,
            personalization_summary=personal_note,
            explanation=explanation,
            supporting_signals=supporting_signals,
            context_confidence=context_conf
        )

