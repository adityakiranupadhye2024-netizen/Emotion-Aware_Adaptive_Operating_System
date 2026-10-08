import random
import time
from typing import Dict, Any, Optional

EMOTIONS = ['Focused', 'Frustrated', 'Fatigued', 'Confused', 'Relaxed', 'Flow State']


class StateBuilder:
    """
    Multimodal state calculation service.
    Fuses real behavioral telemetry from Keyboard, Mouse, Camera, and Context sensors
    into normalized evidence signals, cognitive workload, and emotion probabilities.
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
        Pure multimodal evidence calculation following Parts 5 & 6 specifications.
        """
        # 1. Cognitive Workload Calculation (Part 6)
        # Does NOT allow CPU percentage to dominate human cognitive workload.
        typing_intensity = min(1.0, typing_rate / 4.0)
        typing_act = min(1.0, max(typing_activity_ratio, 1.0 if typing_rate > 1.5 else (typing_rate / 1.5)))
        correction_load = min(1.0, backspace_rate / 0.20)
        mouse_act = min(1.0, mouse_active_ratio)
        context_switching_load = min(1.0, switch_rate / 4.0)
        session_load = min(1.0, session_minutes / 90.0)

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

        # 2. Camera Visual Evidence (Part 3)
        cam_fatigue = float(camera_metrics.get('fatigue_proxy', 0.0))
        cam_conf = float(camera_metrics.get('camera_data_confidence', 0.0))
        smile_observed = bool(camera_metrics.get('conditions', {}).get('smile_observed', False))
        dim_proxy = bool(camera_metrics.get('conditions', {}).get('dim_proxy', False))
        bright_proxy = bool(camera_metrics.get('conditions', {}).get('bright_proxy', False))
        avg_ambient = float(camera_metrics.get('average_visual_light_proxy', 0.50))

        # 3. Multimodal Modality Scores (Part 5)
        keyboard_correction_score = min(1.0, backspace_rate / 0.18)
        mouse_agitation_score = min(1.0, jitter_score / 0.30)
        switching_score = min(1.0, switch_rate / 3.5)
        instability_score = min(1.0, rhythm_cv / 0.90) if rhythm_cv > 0.0 else 0.0

        # Frustration signal: 0.40 kb_correction + 0.30 mouse_agitation + 0.15 switching + 0.15 instability
        frustration_raw = (
            0.40 * keyboard_correction_score
            + 0.30 * mouse_agitation_score
            + 0.15 * switching_score
            + 0.15 * instability_score
        )
        # Suppress frustration if completely idle
        if is_idle or (typing_rate < 0.2 and mouse_act < 0.15):
            frustration_raw *= 0.20

        # Fatigue signal: 0.35 low_typing + 0.25 prolonged_idle + 0.25 cam_fatigue + 0.15 session_duration
        low_typing_activity_score = max(0.0, 1.0 - min(1.0, typing_rate / 1.2))
        prolonged_idle_score = min(1.0, idle_seconds / 35.0)
        session_duration_score = min(1.0, session_minutes / 60.0)

        fatigue_raw = (
            0.35 * low_typing_activity_score
            + 0.25 * prolonged_idle_score
            + 0.25 * cam_fatigue
            + 0.15 * session_duration_score
        )

        # Focus signal: 0.35 typing_engagement + 0.20 mouse_engagement + 0.20 productive_context + 0.15 low_correction + 0.10 stable_interaction
        typing_engagement = min(1.0, typing_rate / 3.0)
        mouse_engagement = mouse_act
        is_productive = 1.0 if context in ['CODING', 'WRITING', 'STUDYING', 'GENERAL_WORK'] else 0.2
        low_correction_score = max(0.0, 1.0 - min(1.0, backspace_rate / 0.10))
        stable_interaction_score = max(0.0, 1.0 - mouse_agitation_score)

        focus_raw = (
            0.35 * typing_engagement
            + 0.20 * mouse_engagement
            + 0.20 * is_productive
            + 0.15 * low_correction_score
            + 0.10 * stable_interaction_score
        )
        if is_idle or context in ['IDLE', 'GAMING']:
            focus_raw *= 0.25

        # Flow State: high focus + rhythmically sustained typing + coding/writing + near-zero errors
        if is_productive > 0.5 and typing_rate >= 2.0 and backspace_rate < 0.06 and mouse_agitation_score < 0.25:
            flow_raw = 0.45 * typing_engagement + 0.35 * low_correction_score + 0.20 * stable_interaction_score
        else:
            flow_raw = 0.04

        # Relaxed signal: 0.30 low_workload + 0.25 low_agitation + 0.20 stable_context + 0.15 cam_positive + 0.10 low_switching
        relaxed_raw = (
            0.30 * max(0.0, 1.0 - workload)
            + 0.25 * max(0.0, 1.0 - mouse_agitation_score)
            + 0.20 * (1.0 if context in ['BROWSING', 'GENERAL_WORK', 'IDLE'] else 0.5)
            + 0.15 * (1.0 if smile_observed else 0.3)
            + 0.10 * max(0.0, 1.0 - switching_score)
        )

        # Confused signal: high switching with low task progress or browsing
        confused_raw = (
            0.45 * switching_score
            + 0.30 * max(0.0, 1.0 - typing_engagement)
            + 0.25 * (1.0 if context == 'BROWSING' else 0.2)
        )

        raw_scores = {
            'Focused': max(0.03, focus_raw),
            'Flow State': max(0.02, flow_raw),
            'Frustrated': max(0.02, frustration_raw),
            'Fatigued': max(0.02, fatigue_raw),
            'Confused': max(0.02, confused_raw),
            'Relaxed': max(0.03, relaxed_raw)
        }

        tot = sum(raw_scores.values())
        probs = {k: round(v / tot, 4) for k, v in raw_scores.items()}
        dominant = max(probs, key=probs.get)
        confidence = probs[dominant]

        # Multi-factor evidence metrics
        evidence_signals = {
            'keyboard_correction_score': round(keyboard_correction_score, 3),
            'mouse_agitation_score': round(mouse_agitation_score, 3),
            'camera_fatigue_score': round(cam_fatigue, 3),
            'context_switching_score': round(switching_score, 3),
            'typing_engagement_score': round(typing_engagement, 3),
            'mouse_engagement_score': round(mouse_engagement, 3),
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
            'evidence_signals': evidence_signals
        }

    def build(self, keyboard, mouse, camera, context, simulation: bool = False) -> Dict[str, Any]:
        """
        Instantaneous telemetry snapshot builder.
        """
        if simulation:
            probs = {e: 0.05 for e in EMOTIONS}
            probs['Focused'] = 0.62
            probs['Flow State'] = 0.18
            probs['Relaxed'] = 0.08
            workload = 0.55 + random.uniform(-0.06, 0.06)
            cam = {'active': False, 'status': 'CAMERA OFF', 'face_detected': False, 'confidence': 0.0, 'ambient_light': 0.50}
            kb = {'active': True, 'events': random.randint(30, 80), 'avg_inter_key_interval': 0.18, 'typing_rate': 4.5, 'backspace_rate': 0.03}
            ms = {'active': True, 'movement_distance': random.uniform(300, 800), 'jitter': 0.12, 'clicks': random.randint(5, 20), 'idle': False}
            ctx = {'active_app': 'VS Code', 'window_title': 'EAOS — main.py', 'activity': 'Coding', 'session_duration': random.randint(600, 3600), 'app_switch_rate': 1.5, 'calendar_state': 'Free', 'system_load': {'cpu': 24.5, 'memory': 58.2, 'processes': 142}}
            dominant = 'Focused'
            level = 'Moderate'
            evidence = {}
        else:
            kb = keyboard.snapshot() if keyboard else {'active': False, 'events': 0, 'typing_rate': 0.0, 'backspace_rate': 0.0, 'avg_inter_key_interval': 0.0}
            ms = mouse.snapshot() if mouse else {'active': False, 'movement_distance': 0.0, 'jitter': 0.0, 'clicks': 0, 'idle': True}
            cam = camera.snapshot() if camera else {'active': False, 'status': 'CAMERA OFF', 'face_detected': False, 'confidence': 0.0, 'ambient_light': 0.5}
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
                camera_metrics=cam_metrics,
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
                'evidence_signals': evidence
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
        Fuses true aggregated metrics from Keyboard, Mouse, Camera, and Context.
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
                'evidence_signals': evidence
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
