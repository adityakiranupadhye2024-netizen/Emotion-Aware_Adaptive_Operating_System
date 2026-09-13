import random
import time
from typing import Dict, Any

EMOTIONS = ['Focused', 'Frustrated', 'Fatigued', 'Confused', 'Relaxed', 'Flow State']

class StateBuilder:
    def build(self, keyboard, mouse, camera, context, simulation: bool = False) -> Dict[str, Any]:
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
        else:
            kb = keyboard.snapshot() if keyboard else {'active': False, 'events': 0, 'typing_rate': 0.0, 'backspace_rate': 0.0, 'avg_inter_key_interval': 0.0}
            ms = mouse.snapshot() if mouse else {'active': False, 'movement_distance': 0.0, 'jitter': 0.0, 'clicks': 0, 'idle': True}
            cam = camera.snapshot() if camera else {'active': False, 'status': 'CAMERA OFF', 'face_detected': False, 'confidence': 0.0, 'ambient_light': 0.5}
            ctx = context.snapshot() if context else {'active_app': 'Unknown', 'window_title': 'Unknown', 'activity': 'General', 'session_duration': 0, 'app_switch_rate': 0.0, 'calendar_state': 'Free', 'system_load': {'cpu': 10.0, 'memory': 50.0, 'processes': 100}}

            typing = kb.get('typing_rate', 0.0)          # keys / sec
            backspace = kb.get('backspace_rate', 0.0)    # 0.0 to 1.0
            jitter = ms.get('jitter', 0.0)               # 0.0 to 1.0
            mouse_active = not ms.get('idle', True)
            face = cam.get('face_detected', False)
            eyes = cam.get('eyes_detected', False)
            smile = cam.get('smile_detected', False)
            fatigue_face = cam.get('fatigue_score', 0.0)
            ambient = cam.get('ambient_light', 0.5)
            activity = ctx.get('activity', 'General')
            switch_rate = ctx.get('app_switch_rate', 0.0)
            session_min = ctx.get('session_duration', 0) / 60.0
            cpu_pct = ctx.get('system_load', {}).get('cpu', 15.0) / 100.0

            # Dynamic multimodal emotion features
            is_coding = activity == 'Coding'
            is_work = activity in ['Coding', 'Writing/Studying']

            # Focused: productive activity, active typing or steady mouse, face and eyes engaged, low backspace
            focus_raw = 0.15 + 0.45 * min(1.0, typing / 4.0) + (0.15 if face else 0.0) + (0.10 if eyes else 0.0) + (0.20 if is_work else 0.0) - (0.35 * min(1.0, backspace * 3.0))

            # Flow State: rhythmic sustained typing, high focus, minimal errors, coding, calm expression
            flow_raw = (0.45 * min(1.0, typing / 5.0) + 0.25 * max(0.0, 1.0 - backspace * 6.0) + 0.15 * max(0.0, 1.0 - jitter * 2.0) + (0.15 if eyes else 0.0)) if (is_work and typing > 2.0) else 0.04

            # Frustrated: high backspaces, mouse jitter, frequent rapid window shifts, high error corrections
            frust_raw = 0.05 + 0.60 * min(1.0, backspace * 4.5) + 0.25 * min(1.0, jitter * 2.5) + (0.15 if is_coding and backspace > 0.15 else 0.0) - (0.10 if smile else 0.0)

            # Fatigued: facial fatigue cues (drowsiness/eyes not visible), long session, sluggish inputs, low activity
            fatigue_raw = 0.05 + 0.35 * min(1.0, session_min / 45.0) + (0.30 * fatigue_face if face else 0.0) + (0.25 if not mouse_active and typing < 0.3 else 0.05) + (0.15 if (cam.get('active') and not face) else 0.0)

            # Confused: high switching rate without productive typing, searching/browsing
            confused_raw = 0.05 + 0.50 * min(1.0, switch_rate / 4.0) + (0.20 if activity == 'Browsing' and typing < 0.5 else 0.05)

            # Relaxed: smile detected, low system load, browsing or media, gentle inputs
            relaxed_raw = 0.10 + 0.35 * max(0.0, 1.0 - typing / 3.0) + 0.25 * max(0.0, 1.0 - cpu_pct * 2.0) + (0.20 if smile else 0.0) + (0.20 if activity in ['Media/Entertainment', 'Browsing'] else 0.0)

            raw_scores = {
                'Focused': max(0.02, focus_raw),
                'Flow State': max(0.02, flow_raw),
                'Frustrated': max(0.02, frust_raw),
                'Fatigued': max(0.02, fatigue_raw),
                'Confused': max(0.02, confused_raw),
                'Relaxed': max(0.02, relaxed_raw)
            }

            tot = sum(raw_scores.values())
            probs = {k: round(v / tot, 4) for k, v in raw_scores.items()}

            # Dynamic workload score (0.0 to 1.0)
            workload = (
                0.25 * min(1.0, typing / 5.0)
                + 0.25 * min(1.0, cpu_pct * 2.0)
                + 0.20 * min(1.0, switch_rate / 4.0)
                + 0.15 * min(1.0, session_min / 60.0)
                + 0.15 * (1.0 if mouse_active else 0.2)
            )
            workload = max(0.05, min(0.99, round(workload, 3)))

        dominant = max(probs, key=probs.get)
        level = 'High' if workload >= 0.65 else 'Moderate' if workload >= 0.35 else 'Low'

        return {
            'timestamp': time.time(),
            'emotion': {
                'dominant': dominant,
                'probabilities': probs,
                'confidence': round(probs[dominant], 3)
            },
            'context': ctx,
            'workload': {
                'score': workload,
                'level': level,
                'components': {'typing': 0.25, 'cpu': 0.25, 'switching': 0.20, 'session': 0.15, 'activity': 0.15}
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
        Fuses the non-camera behavioral context from the previous 50 minutes with
        the facial & emotional cues from the 10-minute camera sensing window.
        """
        if simulation or not window_summary:
            return self.build(None, None, None, None, simulation=True)

        kb = window_summary.get('keyboard', {})
        ms = window_summary.get('mouse', {})
        ctx = window_summary.get('context', {})
        cam = window_summary.get('camera', {})
        workload = window_summary.get('workload', 0.40)

        typing = kb.get('avg_typing_rate', 0.0)
        backspace = kb.get('avg_backspace_rate', 0.0)
        jitter = ms.get('avg_jitter', 0.0)
        dominant_activity = ctx.get('dominant_activity', 'General')
        face_presence = cam.get('face_presence_ratio', 0.0)
        ambient_light = cam.get('avg_ambient_light', 0.5)

        is_coding = dominant_activity == 'Coding'
        is_work = dominant_activity in ['Coding', 'Writing/Studying']

        # Emotion calculation using accumulated cycle data
        focus_raw = 0.20 + 0.40 * min(1.0, typing / 3.0) + (0.20 if is_work else 0.0) + (0.15 if face_presence > 0.4 else 0.0) - (0.30 * min(1.0, backspace * 3.0))
        flow_raw = (0.50 * min(1.0, typing / 4.0) + 0.30 * max(0.0, 1.0 - backspace * 5.0)) if (is_work and typing > 1.5) else 0.05
        frust_raw = 0.05 + 0.60 * min(1.0, backspace * 4.0) + 0.25 * min(1.0, jitter * 2.5) + (0.20 if is_coding and backspace > 0.10 else 0.0)
        fatigue_raw = 0.10 + 0.40 * (1.0 if face_presence < 0.2 and cam.get('had_camera_window') else 0.1) + 0.30 * (1.0 - min(1.0, typing / 2.0))
        confused_raw = 0.05 + 0.35 * min(1.0, ctx.get('app_switches', 0) / 20.0)
        relaxed_raw = 0.10 + 0.40 * max(0.0, 1.0 - typing / 2.0) + (0.25 if dominant_activity in ['Media/Entertainment', 'Browsing'] else 0.0)

        raw_scores = {
            'Focused': max(0.02, focus_raw),
            'Flow State': max(0.02, flow_raw),
            'Frustrated': max(0.02, frust_raw),
            'Fatigued': max(0.02, fatigue_raw),
            'Confused': max(0.02, confused_raw),
            'Relaxed': max(0.02, relaxed_raw)
        }
        tot = sum(raw_scores.values())
        probs = {k: round(v / tot, 4) for k, v in raw_scores.items()}
        dominant = max(probs, key=probs.get)
        level = 'High' if workload >= 0.65 else 'Moderate' if workload >= 0.35 else 'Low'

        return {
            'timestamp': time.time(),
            'cycle_id': window_summary.get('cycle_id', 1),
            'emotion': {
                'dominant': dominant,
                'probabilities': probs,
                'confidence': round(probs[dominant], 3)
            },
            'context': {
                'active_app': ctx.get('dominant_app', 'General'),
                'dominant_activity': dominant_activity,
                'activity': dominant_activity,
                'session_duration': int(window_summary.get('samples_count', 0) * 2),
                'app_switches': ctx.get('app_switches', 0),
                'app_switch_rate': round(float(ctx.get('app_switches', 0)) / max(1.0, float(window_summary.get('samples_count', 1)) * 2.0 / 60.0), 1),
                'system_load': {'cpu': 18, 'memory': 48}
            },
            'workload': {
                'score': workload,
                'level': level,
                'components': {'keyboard': 0.35, 'context': 0.35, 'fatigue': 0.30}
            },
            'inputs': {
                'camera': {
                    'active': False,
                    'status': 'CAMERA OFF',
                    'face_detected': face_presence > 0.3,
                    'ambient_light': ambient_light,
                    'confidence': cam.get('avg_confidence', 0.0)
                },
                'keyboard': {
                    'active': True,
                    'typing_rate': typing,
                    'backspace_rate': backspace,
                    'avg_inter_key_interval': kb.get('avg_inter_key_interval', 0.0)
                },
                'mouse': {
                    'active': True,
                    'jitter': jitter,
                    'idle': ms.get('mouse_active_ratio', 0.5) < 0.2
                },
                'active_app': ctx.get('dominant_app', 'General')
            }
        }
