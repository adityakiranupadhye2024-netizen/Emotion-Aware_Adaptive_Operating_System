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
        """Updates all key personal signal baselines after a 5-minute cycle evaluation."""
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
        - ContextComponent (relevance of active task)
        - PersonalizationComponent (deviation from user's learned personal baseline)
        - WorkloadComponent (cognitive demand)
        Normalized to 0.00 – 1.00.
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
        context = ctx_info.get('context', ctx_info.get('activity', 'GENERAL_WORK')).upper()
        if context in ['CODING', 'WRITING', 'STUDYING']:
            c = 0.90
        elif context in ['MEETING']:
            c = 0.70
        elif context in ['BROWSING']:
            c = 0.50
        elif context in ['GAMING', 'IDLE']:
            c = 0.30
        else:
            c = 0.45

        w = state.get('workload', {}).get('score', 0.45)

        # Personalization Component (how unusual current state is relative to personal baseline)
        p = self.personalization.compute_unusualness_component(state)

        weights = settings.as_weights
        w_e = weights.get('emotion', 0.35)
        w_c = weights.get('context', 0.20)
        w_w = weights.get('workload', 0.30)
        w_p = weights.get('personalization', 0.15)

        total_weight = w_e + w_c + w_w + w_p
        score = (w_e * e_norm + w_c * c + w_w * w + w_p * p) / max(0.01, total_weight)
        score = max(0.0, min(1.0, round(score, 3)))

        components = {
            'emotion': round(e_norm, 3),
            'context': round(c, 3),
            'workload': round(w, 3),
            'personalization': round(p, 3)
        }
        return score, components

    def decide(self, state: Dict[str, Any]) -> Decision:
        now = time.time()
        score, components = self.calculate_as(state)
        emotion = state.get('emotion', {}).get('dominant', 'Focused')
        probs = state.get('emotion', {}).get('probabilities', {})
        workload = state.get('workload', {}).get('score', 0.40)

        ctx_info = state.get('context', {})
        context = str(ctx_info.get('context', ctx_info.get('activity', 'GENERAL_WORK'))).upper()
        context_conf = float(ctx_info.get('context_confidence', ctx_info.get('confidence', 0.80)))

        inputs = state.get('inputs', {})
        cam = inputs.get('camera', {})
        ambient = cam.get('ambient_light', 0.5)
        kb = inputs.get('keyboard', {})
        backspace_rate = kb.get('avg_backspace_rate', kb.get('backspace_rate', 0.0))
        typing_rate = kb.get('avg_typing_rate', kb.get('typing_rate', 0.0))

        # Synchronize with ground truth OS state
        real_os = state.get('actual_os_state') or {}
        if 'dark_mode' in real_os and real_os['dark_mode'] is not None:
            self.dark_mode_active = bool(real_os['dark_mode'])
        if 'focus_mode_active' in real_os and real_os['focus_mode_active'] is not None:
            self.in_focus_mode = bool(real_os['focus_mode_active'])
        if 'audio_muted' in real_os and real_os['audio_muted'] is not None:
            self.audio_muted = bool(real_os['audio_muted'])
        curr_brightness = real_os.get('brightness', 0.5)
        curr_volume = real_os.get('volume', 50)

        # Personalization deviations
        devs = self.personalization.calculate_personal_deviations(state)
        workload_dev = devs['workload']['deviation']
        is_calibrating = (self.personalization.status == "CALIBRATING")

        # Configurable thresholds
        t = settings.thresholds
        sens = settings.sensitivity
        sens_multiplier = 0.85 if sens in ['ultra_responsive', 'high'] else 1.0

        th_workload_high = t.get('workload_high', 0.40) * sens_multiplier
        th_frust_high = t.get('frustration_high', 0.25) * sens_multiplier
        th_fatigue_high = t.get('fatigue_high', 0.25) * sens_multiplier
        th_backspace_high = t.get('typing_error_high', 0.08) * sens_multiplier
        th_dim = t.get('ambient_dim_threshold', 0.35)
        th_bright = t.get('ambient_bright_threshold', 0.60)

        # -------------------------------------------------------------
        # SEPARATE DECISION CONFIDENCE FROM ADAPTIVE SCORE (Feature 10)
        # -------------------------------------------------------------
        sensor_coverage = 0
        if kb.get('events', 0) > 0 or typing_rate > 0.0:
            sensor_coverage += 1
        if not inputs.get('mouse', {}).get('idle', True):
            sensor_coverage += 1
        if cam.get('active', False) and cam.get('face_detected', False):
            sensor_coverage += 1

        base_conf = 0.62 + (0.16 * context_conf) + (0.05 * sensor_coverage)
        if is_calibrating:
            base_conf = min(0.82, base_conf)
        else:
            base_conf = min(0.95, base_conf + 0.04)

        conf = round(base_conf, 2)

        # If confidence is too low for automatic adaptation:
        if conf < settings.thresholds.get('decision_score_min', 0.30):
            return Decision(
                action='NO_ACTION',
                reason='Insufficient confidence for automatic adaptation.',
                confidence=conf,
                policy='Confidence Guard',
                adaptive_score=score,
                explanation={
                    'assessment_window': '5 minutes',
                    'context': context,
                    'context_confidence': int(context_conf * 100),
                    'emotion': emotion,
                    'workload': f"{int(workload * 100)}%",
                    'adaptive_score': score,
                    'decision_confidence': int(conf * 100),
                    'action': 'NO_ACTION',
                    'why': 'Insufficient confidence for automatic adaptation.',
                    'factors': ['Decision confidence below safe threshold']
                }
            )

        # -------------------------------------------------------------
        # CONTEXT-AWARE ADAPTATION RULES (Feature 9)
        # -------------------------------------------------------------
        action = 'NO_ACTION'
        reason = 'Activity nominal. User state remained stable.'
        personal_note = None
        contributing_factors = []

        # RULE CONTEXT MODIFIER 1: MEETING
        if context == 'MEETING':
            # Safeguard meeting audio: if audio was muted, unmute it so meeting audio is audible
            if self.audio_muted:
                action = 'UNMUTE_AUDIO'
                reason = 'Active meeting detected; system audio unmuted so meeting participants can be heard clearly.'
                self.audio_muted = False
                contributing_factors.append('Meeting audio safeguard')
            elif (emotion == 'Fatigued' or probs.get('Fatigued', 0.0) > th_fatigue_high) and workload > 0.40:
                action = 'SUGGEST_BREAK'
                reason = f'Elevated fatigue during meeting session; subtle wellness chime suggested.'
                contributing_factors.append('Fatigue in active meeting')
            else:
                action = 'NO_ACTION'
                reason = 'Active meeting in progress. Intrusive desktop adaptations suppressed.'
                contributing_factors.append('Meeting context active')

        # RULE CONTEXT MODIFIER 2: GAMING
        elif context == 'GAMING':
            action = 'NO_ACTION'
            reason = 'Active gaming session detected. Adaptations suppressed to prevent interruption.'
            contributing_factors.append('Gaming context active')

        # RULE CONTEXT MODIFIER 3: IDLE
        elif context == 'IDLE':
            if self.in_focus_mode:
                action = 'DISABLE_FOCUS_MODE'
                reason = 'User is currently idle/away. Focus Mode disengaged.'
                self.in_focus_mode = False
                contributing_factors.append('Idle state observed')
            elif self.audio_muted:
                action = 'UNMUTE_AUDIO'
                reason = 'User is currently idle/away; system audio unmuted.'
                self.audio_muted = False
                contributing_factors.append('Idle audio restoration')
            elif curr_brightness < 0.45:
                action = 'RESTORE_BRIGHTNESS'
                reason = 'User idle; standard display brightness restored.'
                contributing_factors.append('Idle brightness recovery')
            else:
                action = 'NO_ACTION'
                reason = 'User currently idle. Environment stable.'

        # RULE CONTEXT MODIFIER 4: CODING / WRITING / STUDYING / GENERAL WORK
        else:
            # Trigger 1: Environmental Ambient Lighting (Dark Mode vs Light Mode)
            if ambient < th_dim and not self.dark_mode_active:
                action = 'ENABLE_DARK_MODE'
                reason = f'Low background lighting ({ambient:.2f} < {th_dim:.2f}); Dark Mode engaged automatically for eye comfort.'
                self.dark_mode_active = True
                contributing_factors.append('Low ambient lighting')

            elif ambient > th_bright and self.dark_mode_active:
                action = 'DISABLE_DARK_MODE'
                reason = f'Bright background lighting ({ambient:.2f} > {th_bright:.2f}); macOS Light appearance restored automatically.'
                self.dark_mode_active = False
                contributing_factors.append('Bright ambient lighting')

            # Trigger 2: Frustration & Auditory Sensory Relief
            elif (emotion == 'Frustrated' or probs.get('Frustrated', 0.0) > th_frust_high or backspace_rate > th_backspace_high) and not self.audio_muted:
                action = 'MUTE_AUDIO'
                reason = f'Elevated frustration ({int(probs.get("Frustrated", 0.0) * 100)}%) / typing friction; system audio muted to eliminate auditory stress.'
                self.audio_muted = True
                contributing_factors.append('Auditory stress relief for frustration')

            # Trigger 2B: High Coding Frustration & Debugging Assistance (if already muted)
            elif (emotion == 'Frustrated' or probs.get('Frustrated', 0.0) > th_frust_high or backspace_rate > th_backspace_high) and (context in ['CODING'] or typing_rate > 0.8):
                action = 'SUGGEST_DEBUG_RESOURCE'
                reason = f'Elevated friction / backspace error rate ({int(backspace_rate * 100)}%) detected while coding.'
                contributing_factors.append('High typing error rate')
                contributing_factors.append('Frustration detected in coding')

            # Trigger 3: Focus Mode Activation (Personalized Workload Elevation or High Engagement)
            elif (workload >= th_workload_high or (not is_calibrating and workload_dev >= 0.18) or emotion in ['Focused', 'Flow State'] or probs.get('Focused', 0.0) > 0.35) and (context in ['CODING', 'WRITING', 'STUDYING', 'GENERAL_WORK']) and not self.in_focus_mode:
                action = 'ENABLE_FOCUS_MODE'
                if not is_calibrating and workload_dev >= 0.18:
                    reason = f'Workload was significantly higher than your personal baseline ({devs["workload"]["current"]} vs {devs["workload"]["baseline"]}, deviation {workload_dev:+.2f}) while {context.lower()}; notification alerts silenced & focus mode engaged.'
                    personal_note = f"Personal workload deviation: {workload_dev:+.2f}"
                    contributing_factors.append('Personal baseline deviation exceeded')
                else:
                    reason = f'Elevated cognitive workload ({int(workload * 100)}%) in {context.lower()}; desktop decluttered & notification alerts silenced.'
                    contributing_factors.append('High cognitive workload')
                self.in_focus_mode = True

            # Trigger 3B: Deep Focus Audio Muting (Sustained Focus with Focus Mode already active)
            elif self.in_focus_mode and not self.audio_muted and (workload >= th_workload_high or emotion in ['Focused', 'Flow State']):
                action = 'MUTE_AUDIO'
                reason = f'Sustained deep focus & immersion ({int(probs.get("Focused", 0.0) * 100)}%); system audio muted to eliminate disruptive noises.'
                self.audio_muted = True
                contributing_factors.append('Deep focus audio muting')

            # Trigger 4: Eye Strain / Visual Fatigue / Screen Glare -> Reduce Brightness
            elif (emotion in ['Fatigued', 'Frustrated'] or workload > 0.50 or ambient < th_dim) and curr_brightness > 0.35:
                action = 'REDUCE_BRIGHTNESS'
                reason = f'Visual strain or sustained focus detected; physical display brightness dimmed by 20% to reduce glare.'
                contributing_factors.append('Glare and visual fatigue reduction')

            # Trigger 5: Fatigue / Break Recommendation
            elif (emotion == 'Fatigued' or probs.get('Fatigued', 0.0) > th_fatigue_high) and workload > 0.25:
                action = 'SUGGEST_BREAK'
                reason = f'Sustained workload ({int(workload * 100)}%) with fatigue indicators; recommended wellness pause.'
                contributing_factors.append('Elevated fatigue indicators')

            # Trigger 6: Recovery / Relaxed State -> Unmute Audio
            elif self.audio_muted and (emotion in ['Relaxed'] or (workload < 0.25 and emotion != 'Frustrated')):
                action = 'UNMUTE_AUDIO'
                reason = 'Cognitive workload eased and user in relaxed state; system audio unmuted.'
                self.audio_muted = False
                contributing_factors.append('Relaxed state audio unmute')

            # Trigger 7: Exit Focus Mode when relaxed/idle
            elif emotion in ['Relaxed'] and self.in_focus_mode and typing_rate < 0.2:
                action = 'DISABLE_FOCUS_MODE'
                reason = 'Workload eased; standard desktop notifications & audio restored.'
                self.in_focus_mode = False
                contributing_factors.append('Relaxed cognitive recovery')

            # Trigger 8: Bright Ambient Light / Recovery -> Restore Brightness
            elif (ambient > th_bright or emotion in ['Relaxed']) and curr_brightness < 0.50:
                action = 'RESTORE_BRIGHTNESS'
                reason = f'Bright environment or relaxed state; display brightness restored to standard level.'
                contributing_factors.append('Ambient lighting brightness restoration')

        # -------------------------------------------------------------
        # AUTOMATIC POLICY LEARNING (Feature 13 - LinUCB Bandit)
        # -------------------------------------------------------------
        candidate_actions = ['NO_ACTION']
        if workload > 0.3 or emotion == 'Fatigued':
            candidate_actions.append('SUGGEST_BREAK')

        # Focus Mode candidates: only when actively working, never when idle or relaxed
        if not self.in_focus_mode:
            if context not in ['IDLE', 'GAMING'] and emotion != 'Relaxed':
                candidate_actions.append('ENABLE_FOCUS_MODE')
        else:
            candidate_actions.append('DISABLE_FOCUS_MODE')

        if not self.dark_mode_active:
            candidate_actions.append('ENABLE_DARK_MODE')
        else:
            candidate_actions.append('DISABLE_DARK_MODE')

        if not self.audio_muted:
            candidate_actions.append('MUTE_AUDIO')
        else:
            candidate_actions.append('UNMUTE_AUDIO')

        if curr_brightness > 0.35:
            candidate_actions.append('REDUCE_BRIGHTNESS')
        if curr_brightness < 0.55:
            candidate_actions.append('RESTORE_BRIGHTNESS')

        if action not in candidate_actions:
            candidate_actions.append(action)

        policy_name = 'Baseline Rules'
        if self.policy_learner.total_feedback_count > 0:
            features = self.policy_learner.featurize(state, score, context)
            best_bandit_action, bandit_conf, bandit_val = self.policy_learner.predict(features, candidate_actions)

            if self.policy_learner.status in ['LEARNING', 'ADAPTIVE']:
                # If baseline rule had NO_ACTION, let learned bandit trigger preferred adaptation
                if action == 'NO_ACTION' and best_bandit_action != 'NO_ACTION' and bandit_val > 0.05:
                    action = best_bandit_action
                    conf = bandit_conf
                    policy_name = f'Learned LinUCB ({self.policy_learner.status})'
                    reason = f'Learned policy selected {action.replace("_", " ").title()} based on {self.policy_learner.total_feedback_count} feedback samples (Bandit UCB score: {bandit_val:.2f}).'
                    contributing_factors.append(f'Learned bandit recommendation ({action})')
                # If in ADAPTIVE mode and the bandit strongly favors an alternative action
                # (guarded so lighting ergonomics, acute sensory relief, and context safeguards are strictly preserved):
                elif (
                    self.policy_learner.status == 'ADAPTIVE'
                    and best_bandit_action != action
                    and bandit_val > 0.20
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

        # Check if extreme distress state
        is_extreme = emotion in ['Frustrated', 'Fatigued'] and (workload > 0.70 or backspace_rate > 0.20)

        # Record cycle observation in personal baseline
        self.personalization.record_cycle_observation(state, is_extreme=is_extreme)

        if action != 'NO_ACTION':
            self.last_action = action
            self.last_action_time[action] = now
            self.action_history.append((now, action, reason))

        # -------------------------------------------------------------
        # STRUCTURED DECISION EXPLANATION (Feature 10)
        # -------------------------------------------------------------
        explanation = {
            'assessment_window': '5 minutes',
            'context': context.title(),
            'context_confidence': int(context_conf * 100),
            'emotion': f"{emotion} ({int(probs.get(emotion, 0.5) * 100)}%)",
            'workload': f"{int(workload * 100)}%",
            'personal_baseline_workload': f"{int(devs['workload']['baseline'] * 100)}%",
            'workload_deviation': f"{workload_dev:+.2f}",
            'typing_deviation': f"{devs['typing_rate']['deviation']:+.1f} keys/s",
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

