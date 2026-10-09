import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("eaos.state")

EMOTIONS = ['Focused', 'Frustrated', 'Fatigued', 'Confused', 'Relaxed', 'Flow State']
FACIAL_EXPRESSIONS = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']


class StateBuilder:
    """
    Multimodal state calculation service.
    Fuses real behavioral telemetry from Keyboard, Mouse, Context, and DeepFace Camera sensors
    into normalized evidence signals, cognitive workload, and EAOS emotion probabilities.
    """

    def compute_multimodal_state(
        self,
        typing_rate: float,
        backspace_rate: float,
        rhythm_cv: float,
        typing_activity_ratio: float,
        mouse_active_ratio: float,
        jitter_score: float,
        click_rate: float,
        idle_seconds: float,
        camera_metrics: Dict[str, Any],
        context: str,
        context_conf: float,
        switch_rate: float,
        session_minutes: float,
        is_idle: bool = False
    ) -> Dict[str, Any]:
        """
        Authoritative multimodal evidence calculation.
        DeepFace provides facial expression evidence; final EAOS state requires multimodal fusion.
        """
        # 1. Cognitive Workload Calculation (Human behavioral workload, not just CPU)
        typing_intensity = min(1.0, max(0.0, typing_rate / 4.0))
        typing_act = min(1.0, max(0.0, max(typing_activity_ratio, 1.0 if typing_rate > 1.5 else (typing_rate / 1.5))))
        correction_load = min(1.0, max(0.0, backspace_rate / 0.20))
        mouse_act = min(1.0, max(0.0, mouse_active_ratio))
        context_switching_load = min(1.0, max(0.0, switch_rate / 4.0))
        session_load = min(1.0, max(0.0, session_minutes / 90.0))

        workload = (
            0.35 * typing_intensity
            + 0.20 * typing_act
            + 0.15 * correction_load
            + 0.10 * mouse_act
            + 0.10 * context_switching_load
            + 0.10 * session_load
        )
        workload = max(0.05, min(0.99, round(workload, 3)))
        workload_level = (
            'VERY_HIGH' if workload >= 0.80
            else 'HIGH' if workload >= 0.60
            else 'MODERATE' if workload >= 0.30
            else 'LOW'
        )

        # 2. Camera & DeepFace Facial Evidence Extraction
        cam_conf = float(camera_metrics.get('camera_data_confidence', 0.0))
        face_conf = float(camera_metrics.get('face_detection_confidence', camera_metrics.get('face_confidence', 0.0)))
        face_present = bool(
            camera_metrics.get('conditions', {}).get('face_present', False)
            or camera_metrics.get('face_detected', False)
        )
        cam_active = bool(camera_metrics.get('active', False) or camera_metrics.get('camera_active_ratio', 0.0) > 0.0)

        # Facial emotion distribution from DeepFace
        facial_dist = camera_metrics.get('facial_emotion_distribution') or camera_metrics.get('smoothed_facial_emotions') or {}
        facial_consistency = float(camera_metrics.get('emotion_consistency', 0.50))
        facial_frust_signal = float(camera_metrics.get('facial_frustration', 0.0))
        facial_fatigue_signal = float(camera_metrics.get('facial_fatigue', camera_metrics.get('fatigue_proxy', 0.0)))
        facial_relax_signal = float(camera_metrics.get('facial_relaxation', 0.0))

        has_valid_face = face_present and cam_active and (face_conf > 0.25 or cam_conf > 0.25)

        # 3. Behavioral Telemetry Normalization
        keyboard_correction_score = min(1.0, backspace_rate / 0.18)
        mouse_agitation_score = min(1.0, jitter_score / 0.30)
        switching_score = min(1.0, switch_rate / 3.5)
        instability_score = min(1.0, rhythm_cv / 0.90) if rhythm_cv > 0.0 else 0.0

        # Frustration Score Fusion
        # Facial angry + disgust + instability + keyboard correction + mouse agitation
        if has_valid_face:
            frustration_raw = (
                0.35 * facial_frust_signal
                + 0.35 * keyboard_correction_score
                + 0.20 * mouse_agitation_score
                + 0.10 * switching_score
            )
        else:
            # Re-weight gracefully when camera or face is unavailable
            frustration_raw = (
                0.50 * keyboard_correction_score
                + 0.35 * mouse_agitation_score
                + 0.15 * switching_score
            )

        # Safeguard: Strong frustration requires backspace_rate >= 0.10 AND at least one corroborating indicator
        angry_disgust_evidence = (
            facial_dist.get('angry', 0.0) >= 0.20
            or facial_dist.get('disgust', 0.0) >= 0.15
        )
        corroborated_frustration = (
            mouse_agitation_score >= 0.30
            or switching_score >= 0.40
            or (has_valid_face and angry_disgust_evidence)
            or instability_score >= 0.40
        )
        if backspace_rate < 0.10 and not (mouse_agitation_score >= 0.50 or (has_valid_face and angry_disgust_evidence)):
            frustration_raw *= 0.40
        elif not corroborated_frustration and frustration_raw > 0.35:
            # Backspaces alone must NOT classify strong frustration
            frustration_raw *= 0.50

        if is_idle or (typing_rate < 0.2 and mouse_act < 0.15):
            frustration_raw *= 0.20

        # Fatigue Score Fusion
        # Typing error & correction factor: frequent backspacing directly reflects cognitive fatigue / accuracy slip
        keyboard_fatigue_factor = min(1.0, backspace_rate / 0.12)
        low_typing_activity_score = max(0.0, 1.0 - min(1.0, typing_rate / 1.2))
        prolonged_idle_score = min(1.0, idle_seconds / 35.0)
        session_duration_score = min(1.0, session_minutes / 60.0)

        if has_valid_face:
            fatigue_raw = (
                0.25 * facial_fatigue_signal
                + 0.20 * low_typing_activity_score
                + 0.15 * max(0.0, 1.0 - mouse_act)
                + 0.10 * prolonged_idle_score
                + 0.10 * session_duration_score
                + 0.20 * keyboard_fatigue_factor
            )
        else:
            fatigue_raw = (
                0.30 * low_typing_activity_score
                + 0.20 * max(0.0, 1.0 - mouse_act)
                + 0.15 * prolonged_idle_score
                + 0.15 * session_duration_score
                + 0.20 * keyboard_fatigue_factor
            )

        # High backspace usage: repeated corrections and keystroke slips indicate cognitive fatigue
        if backspace_rate >= 0.08 and not (has_valid_face and angry_disgust_evidence and mouse_agitation_score >= 0.35):
            correction_fatigue_boost = min(0.60, (backspace_rate - 0.06) * 5.0)
            fatigue_raw = max(fatigue_raw, 0.55 + correction_fatigue_boost)

        # Focus Score Fusion
        # Typing engagement: normalized up to 2.5 keys/sec
        typing_engagement = min(1.0, typing_rate / 2.5)
        # When typing, interaction engagement is dominated by the keyboard
        interaction_engagement = max(typing_engagement, mouse_act)

        # Active typing in any application (browser, editor, terminal, notes) is productive engagement
        if context in ['CODING', 'WRITING', 'STUDYING', 'GENERAL_WORK']:
            is_productive = 1.0
        elif typing_rate >= 1.2 or typing_act >= 0.25:
            is_productive = 0.90
        elif context == 'BROWSING':
            is_productive = 0.65
        else:
            is_productive = 0.35

        low_correction_score = max(0.0, 1.0 - min(1.0, backspace_rate / 0.12))
        stable_interaction_score = max(0.0, 1.0 - mouse_agitation_score)

        # Facial focus support: consistent, calm/attentive facial expression
        if has_valid_face:
            calm_face = facial_dist.get('neutral', 0.0) * 0.6 + facial_dist.get('happy', 0.0) * 0.4
            facial_focus_support = min(1.0, calm_face * (0.5 + 0.5 * facial_consistency))
            focus_raw = (
                0.35 * interaction_engagement
                + 0.25 * is_productive
                + 0.20 * low_correction_score
                + 0.20 * facial_focus_support
            )
        else:
            focus_raw = (
                0.45 * interaction_engagement
                + 0.30 * is_productive
                + 0.25 * low_correction_score
            )

        # Frequent backspacing indicates loss of focus / mental fatigue
        if backspace_rate >= 0.08:
            focus_raw *= max(0.20, 1.0 - min(0.75, (backspace_rate - 0.06) * 6.0))

        if is_idle or context in ['IDLE', 'GAMING']:
            focus_raw *= 0.25

        # Flow State Fusion: High sustained rhythm + low error rate + stable interaction
        is_flow_candidate = (
            typing_rate >= 1.5
            and backspace_rate < 0.08
            and mouse_agitation_score < 0.30
            and frustration_raw < 0.30
            and focus_raw >= 0.45
        )
        if is_flow_candidate:
            flow_intensity = min(1.0, (typing_rate - 1.0) / 2.0)
            flow_raw = (
                0.40 * typing_engagement
                + 0.30 * low_correction_score
                + 0.20 * stable_interaction_score
                + 0.10 * flow_intensity
            )
            # When typing fast (>= 2.2 keys/s) with clean rhythm (low backspaces), Flow State takes precedence!
            if typing_rate >= 2.2 and backspace_rate < 0.05:
                flow_raw = max(flow_raw, focus_raw + 0.06)
        else:
            flow_raw = 0.03

        # Relaxation Score Fusion
        if has_valid_face:
            relaxed_raw = (
                0.30 * facial_relax_signal
                + 0.25 * max(0.0, 1.0 - workload)
                + 0.20 * max(0.0, 1.0 - mouse_agitation_score)
                + 0.15 * (1.0 if context in ['BROWSING', 'GENERAL_WORK', 'IDLE'] else 0.5)
                + 0.10 * max(0.0, 1.0 - switching_score)
            )
        else:
            relaxed_raw = (
                0.35 * max(0.0, 1.0 - workload)
                + 0.25 * max(0.0, 1.0 - mouse_agitation_score)
                + 0.25 * (1.0 if context in ['BROWSING', 'GENERAL_WORK', 'IDLE'] else 0.5)
                + 0.15 * max(0.0, 1.0 - switching_score)
            )

        # Active typing strongly suppresses relaxation (fast input is not passive relaxation)
        if typing_rate >= 0.8:
            typing_suppression = min(0.85, (typing_rate - 0.5) / 1.8)
            relaxed_raw *= max(0.12, 1.0 - typing_suppression)

        # Confused Score Fusion: High app switching with erratic / unstable behavior
        confused_raw = (
            0.45 * (switching_score if switching_score > 0.35 else 0.0)
            + 0.25 * mouse_agitation_score
            + 0.15 * max(0.0, 1.0 - context_conf)
            + 0.15 * (0.5 if context == 'BROWSING' and switching_score > 0.4 else 0.0)
        )

        raw_scores = {
            'Focused': max(0.03, focus_raw),
            'Flow State': max(0.02, flow_raw),
            'Frustrated': max(0.02, frustration_raw),
            'Fatigued': max(0.02, fatigue_raw),
            'Confused': max(0.02, confused_raw),
            'Relaxed': max(0.03, relaxed_raw)
        }

        # Calibrated probability scaling (power factor p=2.0) to give clear, accurate emotion confidence
        scaled_scores = {k: max(0.0001, v ** 2.0) for k, v in raw_scores.items()}
        tot = sum(scaled_scores.values())
        probs = {k: round(v / tot, 4) for k, v in scaled_scores.items()}
        # Handle exact rounding sum
        diff = round(1.0 - sum(probs.values()), 4)
        top_k = max(probs, key=probs.get)
        probs[top_k] = round(probs[top_k] + diff, 4)

        dominant = max(probs, key=probs.get)
        confidence = probs[dominant]

        evidence_signals = {
            'keyboard_correction_score': round(keyboard_correction_score, 3),
            'mouse_agitation_score': round(mouse_agitation_score, 3),
            'camera_fatigue_score': round(facial_fatigue_signal, 3),
            'facial_frustration': round(facial_frust_signal, 3),
            'facial_fatigue': round(facial_fatigue_signal, 3),
            'facial_relaxation': round(facial_relax_signal, 3),
            'emotion_consistency': round(facial_consistency, 3),
            'context_switching_score': round(switching_score, 3),
            'typing_engagement_score': round(typing_engagement, 3),
            'mouse_engagement_score': round(mouse_act, 3),
            'frustration_signal': round(frustration_raw, 3),
            'fatigue_signal': round(fatigue_raw, 3),
            'focus_signal': round(focus_raw, 3),
            'relaxed_signal': round(relaxed_raw, 3),
            'camera_confidence': round(cam_conf, 3),
            'context_confidence': round(context_conf, 3)
        }

        return {
            'workload': workload,
            'workload_level': workload_level,
            'dominant_emotion': dominant,
            'emotion_probabilities': probs,
            'emotion_confidence': round(confidence, 3),
            'evidence_signals': evidence_signals,
            'facial_evidence': {
                'available': has_valid_face,
                'distribution': facial_dist,
                'consistency': facial_consistency
            }
        }

    def build(self, keyboard, mouse, camera, context, simulation: bool = False) -> Dict[str, Any]:
        """
        Instantaneous telemetry snapshot builder.
        In LIVE mode, strictly consumes verified sensor telemetry with NO hardcoded fake values.
        """
        if simulation:
            probs = {e: 0.05 for e in EMOTIONS}
            probs['Focused'] = 0.62
            probs['Flow State'] = 0.18
            probs['Relaxed'] = 0.08
            workload = 0.55
            cam = {
                'active': False, 'status': 'CAMERA OFF', 'face_detected': False, 'confidence': 0.0,
                'ambient_light': 0.50, 'dominant_facial_emotion': 'neutral',
                'raw_facial_emotions': {'neutral': 1.0}, 'smoothed_facial_emotions': {'neutral': 1.0},
                'emotion_available': False, 'emotion_stale': True
            }
            kb = {'active': True, 'events': 50, 'avg_inter_key_interval': 0.18, 'typing_rate': 4.5, 'backspace_rate': 0.03}
            ms = {'active': True, 'movement_distance': 450.0, 'jitter': 0.12, 'clicks': 10, 'idle': False}
            ctx = {'active_app': 'VS Code', 'window_title': 'EAOS — main.py', 'activity': 'Coding', 'session_duration': 1200, 'app_switch_rate': 1.5, 'calendar_state': 'Free', 'system_load': {'cpu': 24.5, 'memory': 58.2, 'processes': 142}}
            dominant = 'Focused'
            level = 'MODERATE'
            evidence = {}
        else:
            kb = keyboard.snapshot() if keyboard else {'active': False, 'events': 0, 'typing_rate': 0.0, 'backspace_rate': 0.0, 'avg_inter_key_interval': 0.0}
            ms = mouse.snapshot() if mouse else {'active': False, 'movement_distance': 0.0, 'jitter': 0.0, 'clicks': 0, 'idle': True}
            cam = camera.snapshot() if camera else {
                'active': False, 'status': 'CAMERA OFF', 'face_detected': False, 'confidence': 0.0,
                'ambient_light': 0.5, 'dominant_facial_emotion': 'neutral',
                'raw_facial_emotions': {'neutral': 1.0}, 'smoothed_facial_emotions': {'neutral': 1.0},
                'emotion_available': False, 'emotion_stale': True
            }
            cam_metrics = camera.get_window_metrics() if (camera and hasattr(camera, 'get_window_metrics')) else {}
            ctx = context.snapshot(
                kb_rate=kb.get('typing_rate', 0.0),
                mouse_clicks=ms.get('recent_clicks', 0),
                mouse_idle=ms.get('idle', True),
                idle_seconds=ms.get('idle_duration_seconds', 0.0) if hasattr(mouse, 'get_window_metrics') else 0.0
            ) if context else {'active_app': 'Unknown', 'window_title': 'Unknown', 'activity': 'General', 'session_duration': 0, 'app_switch_rate': 0.0, 'calendar_state': 'Free', 'system_load': {'cpu': 10.0, 'memory': 50.0, 'processes': 100}}

            typing = float(kb.get('typing_rate', 0.0))
            backspace = float(kb.get('backspace_rate', 0.0))
            rhythm_cv = float(kb.get('typing_rhythm_cv', 0.0))
            typing_act = float(kb.get('typing_activity_ratio', 0.5 if typing > 0 else 0.0))
            mouse_act = float(ms.get('active_mouse_ratio', 0.5 if not ms.get('idle') else 0.0))
            jitter = float(ms.get('jitter', 0.0))
            click_rate = float(ms.get('click_rate', 0.0))
            idle_sec = float(ms.get('idle_duration_seconds', 0.0)) if hasattr(mouse, 'get_window_metrics') else (15.0 if ms.get('idle') else 0.0)
            context_name = str(ctx.get('activity', 'General')).upper()
            if context_name == 'GENERAL':
                context_name = 'GENERAL_WORK'
            context_conf = float(ctx.get('confidence', 0.80))
            switch_rate = float(ctx.get('app_switch_rate', 0.0))
            session_min = float(ctx.get('session_duration', 0)) / 60.0

            calc = self.compute_multimodal_state(
                typing_rate=typing,
                backspace_rate=backspace,
                rhythm_cv=rhythm_cv,
                typing_activity_ratio=typing_act,
                mouse_active_ratio=mouse_act,
                jitter_score=jitter,
                click_rate=click_rate,
                idle_seconds=idle_sec,
                camera_metrics=cam_metrics or cam,
                context=context_name,
                context_conf=context_conf,
                switch_rate=switch_rate,
                session_minutes=session_min,
                is_idle=(context_name == 'IDLE' or ms.get('idle', False))
            )
            probs = calc['emotion_probabilities']
            dominant = calc['dominant_emotion']
            workload = calc['workload']
            level = calc['workload_level']
            evidence = calc['evidence_signals']

        return {
            'timestamp': time.time(),
            'emotion': {
                'dominant': dominant,
                'probabilities': probs,
                'confidence': round(probs[dominant], 3),
                'evidence_signals': evidence,
                'facial': {
                    'detected': cam.get('face_detected', False),
                    'dominant': cam.get('dominant_facial_emotion', 'neutral'),
                    'confidence': cam.get('emotion_confidence', 0.0),
                    'consistency': cam.get('emotion_consistency', 0.5),
                    'raw_emotions': cam.get('raw_facial_emotions', {}),
                    'smoothed_emotions': cam.get('smoothed_facial_emotions', {}),
                    'available': cam.get('emotion_available', False),
                    'stale': cam.get('emotion_stale', True),
                    'inference_age': cam.get('emotion_inference_age')
                }
            },
            'context': ctx,
            'workload': {
                'score': workload,
                'level': level,
                'components': {'typing': 0.35, 'activity': 0.20, 'correction': 0.15, 'mouse': 0.10, 'switching': 0.10, 'session': 0.10}
            },
            'inputs': {
                'camera': cam,
                'keyboard': kb,
                'mouse': ms,
                'active_app': ctx.get('active_app', 'Unknown')
            }
        }

    def build_aggregated_cycle_state(self, window_summary: Dict[str, Any], simulation: bool = False) -> Dict[str, Any]:
        """
        Calculates the authoritative multimodal state at the 60-second observation boundary.
        Fuses true aggregated metrics from Keyboard, Mouse, DeepFace Camera, and Context.
        """
        if simulation or not window_summary:
            return self.build(None, None, None, None, simulation=True)

        kb = window_summary.get('keyboard', {})
        ms = window_summary.get('mouse', {})
        ctx = window_summary.get('context', {})
        cam = window_summary.get('camera', {})

        typing = float(kb.get('avg_typing_rate', 0.0))
        backspace = float(kb.get('avg_backspace_rate', 0.0))
        rhythm_cv = float(kb.get('typing_rhythm_cv', 0.0))
        typing_act = float(kb.get('typing_activity_ratio', 0.5 if typing > 0 else 0.0))
        mouse_act = float(ms.get('mouse_active_ratio', 0.5))
        jitter = float(ms.get('avg_jitter', 0.0))
        click_rate = float(ms.get('click_rate', 0.0))
        idle_sec = float(ms.get('idle_duration_seconds', 0.0))

        dominant_app = ctx.get('dominant_app', 'General')
        dominant_activity = str(ctx.get('dominant_activity', 'General')).upper()
        if dominant_activity == 'GENERAL':
            dominant_activity = 'GENERAL_WORK'
        context_conf = float(ctx.get('context_confidence', 0.85))
        actual_app_switches = int(ctx.get('actual_app_switches', ctx.get('app_switches', 0)))
        obs_duration_min = max(0.5, float(window_summary.get('duration_seconds', 60.0)) / 60.0)
        app_switch_rate = actual_app_switches / obs_duration_min
        session_min = float(window_summary.get('session_duration', 60.0)) / 60.0

        calc = self.compute_multimodal_state(
            typing_rate=typing,
            backspace_rate=backspace,
            rhythm_cv=rhythm_cv,
            typing_activity_ratio=typing_act,
            mouse_active_ratio=mouse_act,
            jitter_score=jitter,
            click_rate=click_rate,
            idle_seconds=idle_sec,
            camera_metrics=cam,
            context=dominant_activity,
            context_conf=context_conf,
            switch_rate=app_switch_rate,
            session_minutes=session_min,
            is_idle=(dominant_activity == 'IDLE')
        )

        probs = calc['emotion_probabilities']
        dominant = calc['dominant_emotion']
        workload = calc['workload']
        level = calc['workload_level']
        evidence = calc['evidence_signals']

        return {
            'timestamp': time.time(),
            'cycle_id': window_summary.get('cycle_id', 1),
            'emotion': {
                'dominant': dominant,
                'probabilities': probs,
                'confidence': round(probs[dominant], 3),
                'evidence_signals': evidence,
                'facial': {
                    'distribution': cam.get('facial_emotion_distribution', {}),
                    'dominant': cam.get('dominant_facial_emotion', 'neutral'),
                    'consistency': cam.get('emotion_consistency', 0.50),
                    'observation_count': cam.get('emotion_observation_count', 0),
                    'had_camera_window': cam.get('had_camera_window', False)
                }
            },
            'context': {
                'active_app': dominant_app,
                'dominant_activity': dominant_activity,
                'activity': dominant_activity,
                'session_duration': int(window_summary.get('session_duration', 60)),
                'app_switches': actual_app_switches,
                'app_switch_rate': round(app_switch_rate, 2),
                'confidence': context_conf,
                'context_confidence': context_conf,
                'system_load': ctx.get('system_load', {'cpu': 15.0, 'memory': 48.0})
            },
            'workload': {
                'score': workload,
                'level': level,
                'components': {'typing': 0.35, 'activity': 0.20, 'correction': 0.15, 'mouse': 0.10, 'switching': 0.10, 'session': 0.10}
            },
            'inputs': {
                'camera': {
                    'active': False,
                    'status': 'CAMERA OFF (Adaptation Window)',
                    'face_detected': cam.get('conditions', {}).get('face_present', False),
                    'ambient_light': cam.get('average_visual_light_proxy', 0.50),
                    'confidence': cam.get('camera_data_confidence', 0.0),
                    'fatigue_proxy': cam.get('fatigue_proxy', 0.0),
                    'facial_emotion_distribution': cam.get('facial_emotion_distribution', {}),
                    'dominant_facial_emotion': cam.get('dominant_facial_emotion', 'neutral'),
                    'emotion_consistency': cam.get('emotion_consistency', 0.50),
                    'conditions': cam.get('conditions', {})
                },
                'keyboard': {
                    'active': True,
                    'typing_rate': typing,
                    'backspace_rate': backspace,
                    'typing_rhythm_cv': rhythm_cv,
                    'typing_activity_ratio': typing_act,
                    'avg_inter_key_interval': kb.get('avg_inter_key_interval', 0.0)
                },
                'mouse': {
                    'active': True,
                    'jitter': jitter,
                    'mouse_active_ratio': mouse_act,
                    'click_rate': click_rate,
                    'idle': dominant_activity == 'IDLE' or ms.get('conditions', {}).get('mouse_idle', False)
                },
                'active_app': dominant_app
            }
        }
