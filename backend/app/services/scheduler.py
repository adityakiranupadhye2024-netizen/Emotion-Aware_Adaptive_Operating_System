import time
import json
import threading
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.core.config import settings
from app.db.database import (
    insert_decision, record_cycle, update_decision_notification, record_camera_session,
    record_adaptation_effectiveness, recent_decisions, update_cycle_phase
)
from app.services.notification import notification_service
from app.decision_engine.engine import Decision

logger = logging.getLogger("eaos.scheduler")

class InputObservationWindow:
    def __init__(self, cycle_id: int, start_time: float, duration_seconds: float):
        self.cycle_id = cycle_id
        self.start_time = start_time
        self.duration_seconds = duration_seconds
        self.end_time = start_time + duration_seconds

        # Real telemetry samples collected during the input window
        self.keyboard_samples: List[Dict[str, Any]] = []
        self.mouse_samples: List[Dict[str, Any]] = []
        self.context_samples: List[Dict[str, Any]] = []
        self.camera_samples: List[Dict[str, Any]] = []
        self.workload_samples: List[float] = []
        self.app_frequencies: Dict[str, int] = {}
        self.activity_frequencies: Dict[str, int] = {}
        self.last_sampled_app: Optional[str] = None
        self.actual_app_switches: int = 0

    def add_sample(self, kb: dict, ms: dict, ctx: dict, cam: dict, workload: float):
        if kb:
            self.keyboard_samples.append({
                'typing_rate': float(kb.get('typing_rate', 0.0)),
                'backspace_rate': float(kb.get('backspace_rate', 0.0)),
                'avg_inter_key_interval': float(kb.get('avg_inter_key_interval', 0.0)),
                'typing_rhythm_cv': float(kb.get('typing_rhythm_cv', 0.0)),
                'typing_activity_ratio': float(kb.get('typing_activity_ratio', 0.5 if kb.get('typing_rate', 0) > 0 else 0.0))
            })
        if ms:
            self.mouse_samples.append({
                'movement_distance': float(ms.get('movement_distance', 0.0)),
                'jitter': float(ms.get('jitter', 0.0)),
                'click_rate': float(ms.get('click_rate', 0.0)),
                'mouse_active_ratio': float(ms.get('active_mouse_ratio', 0.5 if not ms.get('idle') else 0.0)),
                'idle': bool(ms.get('idle', False)),
                'idle_duration_seconds': float(ms.get('idle_duration_seconds', 0.0))
            })
        if ctx:
            app = str(ctx.get('active_app', 'Unknown'))
            act = str(ctx.get('activity', 'General'))
            if self.last_sampled_app is not None and app != self.last_sampled_app:
                self.actual_app_switches += 1
            self.last_sampled_app = app
            self.app_frequencies[app] = self.app_frequencies.get(app, 0) + 1
            self.activity_frequencies[act] = self.activity_frequencies.get(act, 0) + 1
            self.context_samples.append(ctx)
        if cam and cam.get('active', False):
            self.camera_samples.append({
                'face_detected': bool(cam.get('face_detected', False)),
                'face_confidence': float(cam.get('face_confidence', cam.get('confidence', 0.0))),
                'eyes_detected': bool(cam.get('eyes_detected', False)),
                'smile_detected': bool(cam.get('smile_detected', False)),
                'confidence': float(cam.get('confidence', 0.0)),
                'ambient_light': float(cam.get('ambient_light', 0.5)),
                'fatigue_score': float(cam.get('fatigue_score', 0.0)),
                'dominant_facial_emotion': str(cam.get('dominant_facial_emotion', 'neutral')),
                'smoothed_facial_emotions': dict(cam.get('smoothed_facial_emotions', {})),
                'raw_facial_emotions': dict(cam.get('raw_facial_emotions', {})),
                'emotion_confidence': float(cam.get('emotion_confidence', 0.0)),
                'emotion_consistency': float(cam.get('emotion_consistency', 0.5)),
                'facial_frustration': float(cam.get('facial_frustration', 0.0)),
                'facial_fatigue': float(cam.get('facial_fatigue', 0.0)),
                'facial_relaxation': float(cam.get('facial_relaxation', 0.0)),
                'emotion_available': bool(cam.get('emotion_available', False))
            })
        self.workload_samples.append(float(workload))

    def get_aggregated_state(self) -> Dict[str, Any]:
        n_kb = max(1, len(self.keyboard_samples))
        avg_typing = sum(s['typing_rate'] for s in self.keyboard_samples) / n_kb if self.keyboard_samples else 0.0
        avg_backspace = sum(s['backspace_rate'] for s in self.keyboard_samples) / n_kb if self.keyboard_samples else 0.0
        avg_interval = sum(s['avg_inter_key_interval'] for s in self.keyboard_samples) / n_kb if self.keyboard_samples else 0.0
        avg_cv = sum(s.get('typing_rhythm_cv', 0.0) for s in self.keyboard_samples) / n_kb if self.keyboard_samples else 0.0
        avg_act = sum(s.get('typing_activity_ratio', 0.5 if avg_typing > 0 else 0.0) for s in self.keyboard_samples) / n_kb if self.keyboard_samples else 0.0

        n_ms = max(1, len(self.mouse_samples))
        avg_jitter = sum(s['jitter'] for s in self.mouse_samples) / n_ms if self.mouse_samples else 0.0
        avg_clicks = sum(s.get('click_rate', 0.0) for s in self.mouse_samples) / n_ms if self.mouse_samples else 0.0
        active_mouse_count = sum(1 for s in self.mouse_samples if not s['idle'])
        mouse_active_ratio = active_mouse_count / n_ms if self.mouse_samples else 0.5
        last_idle_sec = self.mouse_samples[-1].get('idle_duration_seconds', 0.0) if self.mouse_samples else 0.0

        dominant_app = max(self.app_frequencies, key=self.app_frequencies.get) if self.app_frequencies else 'General'
        dominant_activity = max(self.activity_frequencies, key=self.activity_frequencies.get) if self.activity_frequencies else 'General'
        avg_ctx_conf = sum(float(c.get('confidence', 0.80)) for c in self.context_samples) / max(1, len(self.context_samples)) if self.context_samples else 0.85

        avg_workload = sum(self.workload_samples) / max(1, len(self.workload_samples)) if self.workload_samples else 0.40

        n_cam = max(1, len(self.camera_samples))
        face_detected_samples = sum(1 for s in self.camera_samples if s.get('face_detected'))
        face_presence_ratio = face_detected_samples / n_cam if self.camera_samples else 0.0
        avg_ambient = sum(s.get('ambient_light', 0.5) for s in self.camera_samples) / n_cam if self.camera_samples else 0.5
        conf_list = [s.get('face_confidence', s.get('confidence', 0.0)) for s in self.camera_samples if s.get('face_detected')]
        avg_face_conf = (sum(conf_list) / len(conf_list)) if conf_list else 0.0
        avg_fatigue = sum(s.get('fatigue_score', 0.0) for s in self.camera_samples) / n_cam if self.camera_samples else 0.0

        eye_detected_samples = sum(1 for s in self.camera_samples if s.get('eyes_detected'))
        eye_vis_ratio = eye_detected_samples / float(max(1, face_detected_samples)) if face_detected_samples > 0 else 0.0

        smile_detected_samples = sum(1 for s in self.camera_samples if s.get('smile_detected'))
        smile_ratio = smile_detected_samples / float(max(1, face_detected_samples)) if face_detected_samples > 0 else 0.0

        # DeepFace 60-second Emotion Distribution Aggregation
        valid_face_samples = [s for s in self.camera_samples if s.get('face_detected') and s.get('smoothed_facial_emotions')]
        emotion_obs_count = len(valid_face_samples)

        standard_emotions = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']
        if emotion_obs_count > 0:
            agg_facial_emotions: Dict[str, float] = {}
            for k in standard_emotions:
                agg_facial_emotions[k] = sum(s['smoothed_facial_emotions'].get(k, 0.0) for s in valid_face_samples) / float(emotion_obs_count)
            tot_e = sum(agg_facial_emotions.values())
            if tot_e > 0:
                agg_facial_emotions = {k: round(v / tot_e, 4) for k, v in agg_facial_emotions.items()}
            dominant_facial_emotion = max(agg_facial_emotions, key=agg_facial_emotions.get)
            avg_consistency = sum(s.get('emotion_consistency', 0.5) for s in valid_face_samples) / float(emotion_obs_count)
        else:
            agg_facial_emotions = {k: 0.0 for k in standard_emotions}
            agg_facial_emotions['neutral'] = 1.0
            dominant_facial_emotion = 'neutral'
            avg_consistency = 0.50

        # Derived cycle-level facial evidence signals
        instability = max(0.0, 1.0 - avg_consistency)
        facial_frustration = round(
            0.55 * agg_facial_emotions.get('angry', 0.0)
            + 0.20 * agg_facial_emotions.get('disgust', 0.0)
            + 0.10 * agg_facial_emotions.get('surprise', 0.0)
            + 0.15 * instability,
            3
        )
        facial_relaxation = round(
            0.60 * agg_facial_emotions.get('happy', 0.0)
            + 0.30 * agg_facial_emotions.get('neutral', 0.0)
            + 0.10 * avg_consistency,
            3
        )
        quality_penalty = max(0.0, 1.0 - avg_face_conf)
        facial_fatigue = round(
            0.45 * agg_facial_emotions.get('sad', 0.0)
            + 0.20 * (1.0 - eye_vis_ratio)
            + 0.20 * agg_facial_emotions.get('neutral', 0.0)
            + 0.15 * quality_penalty,
            3
        )

        had_camera = len(self.camera_samples) > 0
        cam_conditions = {
            'valid_camera_observation': had_camera and len(self.camera_samples) >= 5,
            'face_present': face_presence_ratio >= 0.60,
            'strong_face_presence': face_presence_ratio >= 0.80,
            'face_mostly_absent': face_presence_ratio < 0.30,
            'eyes_engaged': (eye_vis_ratio >= 0.65 and face_presence_ratio >= 0.50),
            'low_eye_visibility': (eye_vis_ratio < 0.45 and face_presence_ratio >= 0.60),
            'persistent_low_eye_visibility': (eye_vis_ratio < 0.40 and face_presence_ratio >= 0.60),
            'smile_observed': smile_ratio >= 0.40,
            'dim_proxy': avg_ambient < 0.25,
            'bright_proxy': avg_ambient > 0.65
        }

        return {
            'cycle_id': self.cycle_id,
            'samples_count': len(self.workload_samples),
            'camera_samples_count': len(self.camera_samples),
            'duration_seconds': self.duration_seconds,
            'keyboard': {
                'avg_typing_rate': round(avg_typing, 2),
                'avg_backspace_rate': round(avg_backspace, 3),
                'avg_inter_key_interval': round(avg_interval, 3),
                'typing_rhythm_cv': round(avg_cv, 3),
                'typing_activity_ratio': round(avg_act, 3)
            },
            'mouse': {
                'avg_jitter': round(avg_jitter, 3),
                'mouse_active_ratio': round(mouse_active_ratio, 2),
                'click_rate': round(avg_clicks, 2),
                'idle_duration_seconds': round(last_idle_sec, 1),
                'conditions': {
                    'mouse_idle': last_idle_sec >= 15.0 or mouse_active_ratio < 0.15,
                    'strong_idle': last_idle_sec >= 25.0 or mouse_active_ratio < 0.10
                }
            },
            'context': {
                'dominant_app': dominant_app,
                'dominant_activity': dominant_activity,
                'actual_app_switches': self.actual_app_switches,
                'app_switches': self.actual_app_switches,
                'context_confidence': round(avg_ctx_conf, 2)
            },
            'camera': {
                'face_presence_ratio': round(face_presence_ratio, 2),
                'eye_visibility_ratio': round(eye_vis_ratio, 2),
                'smile_presence_ratio': round(smile_ratio, 2),
                'avg_ambient_light': round(avg_ambient, 3),
                'average_visual_light_proxy': round(avg_ambient, 3),
                'avg_confidence': round(avg_face_conf, 2),
                'camera_data_confidence': round(avg_face_conf * (0.3 + 0.7 * face_presence_ratio), 2) if had_camera else 0.0,
                'fatigue_proxy': round(avg_fatigue, 2),
                'facial_emotion_distribution': agg_facial_emotions,
                'dominant_facial_emotion': dominant_facial_emotion,
                'emotion_observation_count': emotion_obs_count,
                'emotion_consistency': round(avg_consistency, 2),
                'facial_frustration': facial_frustration,
                'facial_fatigue': facial_fatigue,
                'facial_relaxation': facial_relaxation,
                'had_camera_window': had_camera,
                'conditions': cam_conditions
            },
            'workload': round(avg_workload, 3)
        }


class CycleScheduler:
    """
    Manages the strict repeating adaptive cycle (default: 2-minute total = 1-min input + 1-min adaptation):
    Phase 1: INPUT_COLLECTION (configurable, default 1 minute)
    Phase 2: ADAPTATION (configurable, default 1 minute)

    There is NEVER a period where both phases are active simultaneously.
    Aligned to wall-clock time boundaries determined by settings.get_effective_cycle_seconds().
    """
    def __init__(self, camera_sensor, state_builder, decision_engine, os_actuator):
        self.camera = camera_sensor
        self.builder = state_builder
        self.engine = decision_engine
        self.actuator = os_actuator

        self.cycle_id = 1
        self.current_window: Optional[InputObservationWindow] = None
        self.running = False
        self.paused = False
        self.pending_adaptation: Optional[Dict[str, Any]] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # State machine: 'INPUT_COLLECTION' or 'ADAPTATION'
        self.phase = "INPUT_COLLECTION"
        self.last_slot_idx: Optional[int] = None
        self.cycle_start_time = time.time()
        self.boundary_time = time.time() + float(settings.get_effective_cycle_seconds())
        self.active_cycle_row_id: Optional[int] = None

        # Frozen states for the ADAPTATION phase
        self.frozen_state: Optional[Dict[str, Any]] = None
        self.frozen_as: float = 0.50
        self.frozen_as_components: Dict[str, float] = {
            'emotion': 0.5,
            'context': 0.5,
            'workload': 0.5,
            'personalization': 0.5
        }
        self.frozen_decision: Optional[Dict[str, Any]] = None
        self.latest_decision: Optional[Dict[str, Any]] = None
        self.latest_execution: Optional[Dict[str, Any]] = None

    def _compute_wall_clock_slot(self, t: Optional[float] = None) -> Dict[str, Any]:
        """
        Calculates wall-clock cycle boundary:
        Each slot duration is block_sec (default 1 minute = 60s):
        - Even minute slots: INPUT_COLLECTION (1 minute input)
        - Odd minute slots: ADAPTATION (1 minute wait / adaptation)
        """
        now = t if t is not None else time.time()
        block_sec = float(settings.get_effective_cycle_seconds())
        slot_idx = int(now // block_sec)
        remaining = max(0.0, block_sec - (now % block_sec))
        is_input = (slot_idx % 2 == 0)

        phase = "INPUT_COLLECTION" if is_input else "ADAPTATION"
        next_phase = "ADAPTATION" if is_input else "INPUT_COLLECTION"
        boundary_time = now + remaining

        return {
            'slot_idx': slot_idx,
            'phase': phase,
            'next_phase': next_phase,
            'is_input': is_input,
            'remaining_seconds': remaining,
            'boundary_time': boundary_time,
            'block_seconds': block_sec
        }

    def set_monitoring_paused(self, paused: bool):
        with self._lock:
            self.paused = paused
            if self.paused:
                logger.info("EAOS monitoring paused by user request.")
                if self.camera:
                    self.camera.close_camera()
            else:
                logger.info("EAOS monitoring resumed by user request.")
                if self.phase == "INPUT_COLLECTION" and settings.camera_sensing_enabled and self.camera:
                    self.camera.open_camera()

    def start(self):
        with self._lock:
            if self.running:
                return
            self.running = True

            # Determine initial phase and boundary from actual wall-clock time
            slot_info = self._compute_wall_clock_slot()
            self.last_slot_idx = slot_info['slot_idx']
            self.phase = slot_info['phase']
            self.boundary_time = slot_info['boundary_time']
            self.cycle_start_time = time.time()

            logger.info(f"EAOS Wall-Clock Scheduler started. Wall clock phase: {self.phase}, Slot #{self.last_slot_idx}, remaining: {int(slot_info['remaining_seconds'])}s")

            if self.phase == "INPUT_COLLECTION":
                self.current_window = InputObservationWindow(
                    cycle_id=self.cycle_id,
                    start_time=self.cycle_start_time,
                    duration_seconds=slot_info['block_seconds']
                )
                if settings.camera_sensing_enabled and not self.paused and self.camera:
                    self.camera.open_camera()
                elif self.camera:
                    self.camera.close_camera()
            else:
                # Started during ADAPTATION window
                if self.camera:
                    self.camera.close_camera()
                # Use fallback or last decision
                past = recent_decisions(1)
                if past:
                    self.latest_decision = past[0]
                    self.frozen_decision = past[0]
                    self.frozen_as = past[0].get('adaptive_score', 0.5)
                else:
                    self.frozen_as = 0.50
                    self.frozen_decision = {
                        'action': 'NO_ACTION',
                        'reason': 'Started mid-adaptation window. Nominal settings maintained until next input window.',
                        'confidence': 0.85,
                        'policy': 'Adaptive 2-Min Cycle',
                        'adaptive_score': 0.50,
                        'status': 'executed',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                    self.latest_decision = self.frozen_decision

                self.frozen_state = self.builder.build_aggregated_cycle_state({})

            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            self.running = False
            if self.camera:
                self.camera.close_camera()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("EAOS CycleScheduler stopped cleanly.")

    def _run_loop(self):
        while self.running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"Error in scheduler tick: {e}", exc_info=True)
            time.sleep(settings.update_seconds)

    def _tick(self):
        now = time.time()
        with self._lock:
            if not self.running:
                return

            if self.paused:
                return

            slot_info = self._compute_wall_clock_slot(now)
            current_slot = slot_info['slot_idx']
            self.boundary_time = slot_info['boundary_time']

            # Enforce camera state by phase
            if self.phase == "ADAPTATION":
                # Camera assessment MUST NOT run during adaptation
                if self.camera and self.camera.is_active():
                    self.camera.close_camera()
            elif self.phase == "INPUT_COLLECTION":
                if settings.camera_sensing_enabled and self.camera and not self.camera.is_active():
                    self.camera.open_camera()
                elif not settings.camera_sensing_enabled and self.camera and self.camera.is_active():
                    self.camera.close_camera()

            # Check for wall-clock boundary crossing
            if self.last_slot_idx is not None and current_slot != self.last_slot_idx:
                slot_diff = current_slot - self.last_slot_idx
                if slot_diff == 1:
                    if self.phase == "INPUT_COLLECTION":
                        self._transition_to_adaptation()
                    else:
                        self._transition_to_input_collection()
                else:
                    # Machine slept or app was paused across multiple slots
                    logger.warning(f"Wall-clock jumped {slot_diff} slots (sleep/wake event). Resyncing phase to {slot_info['phase']}.")
                    self._resync_from_sleep(slot_info)

                self.last_slot_idx = current_slot

    def sample_telemetry(self, kb: dict, ms: dict, ctx: dict, cam: dict, workload: float):
        """
        Gathers telemetry ONLY during the INPUT_COLLECTION phase.
        Ignored during the ADAPTATION phase.
        """
        with self._lock:
            if not self.paused and self.phase == "INPUT_COLLECTION" and self.current_window:
                self.current_window.add_sample(kb, ms, ctx, cam, workload)

    def _transition_to_adaptation(self):
        """
        Exact transition: INPUT_COLLECTION -> ADAPTATION at the cycle boundary.
        1. Aggregates collected signals.
        2. Calculates state, workload, emotion, context.
        3. Applies personalization and calculates Adaptive Score (AS).
        4. Runs Decision Engine and FREEZES the decision.
        5. Closes the camera for the adaptation phase.
        6. Executes OS adaptation once.
        7. Sends single intelligent notification.
        8. Holds adaptation for the next cycle phase.
        """
        now_ts = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        input_start_iso = datetime.fromtimestamp(self.cycle_start_time, tz=timezone.utc).isoformat()
        next_boundary_iso = datetime.fromtimestamp(now_ts + float(settings.get_effective_cycle_seconds()), tz=timezone.utc).isoformat()

        logger.info(f"=== [CYCLE BOUNDARY] Finalizing Input Window for Cycle #{self.cycle_id} -> Transitioning to ADAPTATION ===")

        # 1. Aggregate signals & query verified macOS state
        window_summary = self.current_window.get_aggregated_state() if self.current_window else {}
        current_state = self.builder.build_aggregated_cycle_state(window_summary, settings.simulation)
        current_state['actual_os_state'] = self.actuator.get_current_os_state()

        # 2. Calculate AS & components
        as_score, as_components = self.engine.calculate_as(current_state)
        curr_workload = current_state.get('workload', {}).get('score', 0.5)

        # 3. Evaluate previous adaptation effectiveness (if any)
        if self.pending_adaptation is not None:
            try:
                target_did = self.pending_adaptation.get('decision_id')
                pre_as = self.pending_adaptation.get('pre_as', as_score)
                pre_wl = self.pending_adaptation.get('pre_workload', curr_workload)
                act = self.pending_adaptation.get('action', 'UNKNOWN')
                as_delta = round(as_score - pre_as, 3)
                wl_delta = round(curr_workload - pre_wl, 3)

                if as_score < pre_as - 0.05:
                    outcome = "POSITIVE"
                    reward = 1.0
                elif as_score > pre_as + 0.05:
                    outcome = "NEGATIVE"
                    reward = -0.5
                else:
                    outcome = "NEUTRAL"
                    reward = 0.1

                record_adaptation_effectiveness(
                    decision_id=target_did,
                    action=act,
                    pre_as=pre_as,
                    post_as=as_score,
                    as_delta=as_delta,
                    pre_workload=pre_wl,
                    post_workload=curr_workload,
                    workload_delta=wl_delta,
                    outcome=outcome
                )
                if hasattr(self.engine, 'policy_learner'):
                    self.engine.policy_learner.update(
                        action=act,
                        state_or_vector=self.pending_adaptation.get('state', current_state),
                        reward=reward,
                        source="EFFECTIVENESS"
                    )
            except Exception as e:
                logger.warning(f"Error evaluating adaptation effectiveness: {e}")
            finally:
                self.pending_adaptation = None

        # 4. Decide & FREEZE decision
        decision = self.engine.decide(current_state)

        self.frozen_state = current_state
        self.frozen_as = as_score
        self.frozen_as_components = as_components
        self.frozen_decision = {
            'action': decision.action,
            'reason': decision.reason,
            'confidence': decision.confidence,
            'policy': decision.policy,
            'adaptive_score': as_score,
            'personalization_summary': decision.personalization_summary,
            'timestamp': now_iso
        }

        # 5. CLOSE camera during adaptation period
        if self.camera:
            self.camera.close_camera()

        # 6. Execute OS adaptation once
        execution = {"status": "skipped", "success": True, "action": decision.action}
        if settings.automation_enabled:
            execution = self.actuator.execute(
                decision.action,
                params={
                    'adaptive_score': as_score,
                    'reason': decision.reason,
                    'cycle_id': self.cycle_id
                }
            )
        else:
            execution = {
                "status": "automation_disabled",
                "success": True,
                "action": decision.action,
                "message": "Automation disabled in Settings"
            }

        # Update actual OS state after actuation
        new_os_state = execution.get('state_after') or self.actuator.get_current_os_state(force_refresh=True)
        current_state['actual_os_state'] = new_os_state
        if self.frozen_state:
            self.frozen_state['actual_os_state'] = new_os_state

        self.latest_decision = dict(self.frozen_decision)
        self.latest_decision['status'] = execution.get('status', 'executed')
        self.latest_decision['verified'] = execution.get('verified', False)
        self.latest_decision['command_used'] = execution.get('command_used', 'NONE')
        self.latest_decision['message'] = execution.get('message', '')
        self.latest_decision['execution_details'] = execution
        self.latest_execution = execution

        # 7. Record decision in DB with verified OS execution data
        kb_summary = window_summary.get('keyboard', {})
        ms_summary = window_summary.get('mouse', {})
        cam_summary = window_summary.get('camera', {})
        typing_rate = kb_summary.get('avg_typing_rate', 0.0)
        backspace_rate = kb_summary.get('avg_backspace_rate', 0.0)
        mouse_jitter = ms_summary.get('avg_jitter', 0.0)
        camera_active = 1 if cam_summary.get('had_camera_window', False) else 0
        canonical_context = current_state.get('context', {}).get('canonical_context', current_state.get('context', {}).get('dominant_activity', 'GENERAL_WORK'))
        decision_ctx_conf = getattr(decision, 'context_confidence', 0.80)
        decision_explanation = getattr(decision, 'explanation', None)

        # Structured Cycle Boundary Log
        cycle_banner = f"""
================================================
EAOS CYCLE #{self.cycle_id}
INPUT WINDOW COMPLETE
================================================

Keyboard:
  Typing Rate: {typing_rate:.1f} keys/s | Backspace Ratio: {int(backspace_rate * 100)}% | Rhythm CV: {kb_summary.get('typing_rhythm_cv', 0.0):.2f}

Mouse:
  Agitation (Jitter): {mouse_jitter:.3f} | Active Ratio: {int(ms_summary.get('mouse_active_ratio', 0.0) * 100)}% | Clicks: {ms_summary.get('click_rate', 0.0):.1f}/s

Camera:
  Status: {'ACTIVE' if camera_active else 'OFF'} | Face Presence: {int(cam_summary.get('face_presence_ratio', 0.0) * 100)}% | Light Proxy: {cam_summary.get('average_visual_light_proxy', 0.5):.2f}

Facial:
  Dominant Expression: {cam_summary.get('dominant_facial_emotion', 'None').upper()} | Consistency: {cam_summary.get('emotion_consistency', 0.0):.2f} | Obs Count: {cam_summary.get('emotion_observation_count', 0)}

Context:
  Activity: {canonical_context} | App Switches: {window_summary.get('context', {}).get('actual_app_switches', 0)} | Confidence: {decision_ctx_conf:.2f}

Workload:
  Score: {curr_workload:.2f} ({current_state.get('workload', {}).get('level', 'MODERATE')})

Personalization:
  Status: {self.engine.personalization.status} | Total Samples: {self.engine.personalization.total_cycle_samples} | Note: {decision.personalization_summary or 'Nominal'}

Adaptive Score:
  AS: {as_score:.2f} (Emotion: {as_components.get('emotion', 0.5):.2f}, Context: {as_components.get('context', 0.5):.2f}, Workload: {as_components.get('workload', 0.5):.2f}, Personalization: {as_components.get('personalization', 0.5):.2f})

Decision:
  Action: {decision.action} | Policy: {decision.policy} | Confidence: {decision.confidence:.2f} | Reason: {decision.reason}

Actuator:
  Command: {execution.get('command_used', 'NONE')} | Status: {execution.get('status', 'executed')}

Verification:
  Verified: {execution.get('verified', False)} | Success: {execution.get('success', False)}
================================================
"""
        logger.info(cycle_banner)

        emotion_probs = json.dumps(current_state.get('emotion', {}).get('probabilities', {}))

        did = insert_decision({
            'timestamp': now_iso,
            'cycle_id': self.cycle_id,
            'emotion': current_state.get('emotion', {}).get('dominant', 'Focused'),
            'emotion_confidence': current_state.get('emotion', {}).get('confidence', 0.85),
            'workload': current_state['workload']['score'],
            'adaptive_score': as_score,
            'ass': as_score,
            'context': canonical_context,
            'context_confidence': decision_ctx_conf,
            'explanation': decision_explanation,
            'action': decision.action,
            'reason': decision.reason,
            'confidence': decision.confidence,
            'policy': decision.policy,
            'status': execution.get('status', 'executed'),
            'notification_status': 'pending',
            'typing_rate': typing_rate,
            'backspace_rate': backspace_rate,
            'mouse_jitter': mouse_jitter,
            'camera_active': camera_active,
            'emotion_probabilities': emotion_probs,
            'baseline_workload': self.engine.personalization.get_signal_mean('workload', 0.35),
            'baseline_typing': self.engine.personalization.get_signal_mean('typing_rate', 3.5),
            'baseline_jitter': self.engine.personalization.get_signal_mean('mouse_jitter', 0.12),
            'verified': 1 if execution.get('verified') else 0,
            'command_used': execution.get('command_used'),
            'state_before': execution.get('state_before'),
            'state_after': execution.get('state_after'),
            'execution_error': execution.get('error')
        })
        self.latest_decision['id'] = did
        self.frozen_decision['id'] = did

        if decision.action != 'NO_ACTION' and execution.get('status') == 'executed':
            self.pending_adaptation = {
                'decision_id': did,
                'action': decision.action,
                'pre_as': as_score,
                'pre_workload': curr_workload,
                'state': current_state
            }

        # 8. Record cycle in DB
        self.active_cycle_row_id = record_cycle({
            'cycle_number': self.cycle_id,
            'cycle_id': self.cycle_id,
            'start_time': input_start_iso,
            'end_time': next_boundary_iso,
            'input_start_time': input_start_iso,
            'input_end_time': now_iso,
            'adaptation_start_time': now_iso,
            'adaptation_end_time': next_boundary_iso,
            'phase': 'ADAPTATION',
            'camera_used': window_summary.get('camera', {}).get('had_camera_window', False),
            'samples_count': window_summary.get('samples_count', 0),
            'adaptive_score': as_score,
            'action': decision.action,
            'selected_action': decision.action,
            'reason': decision.reason,
            'status': execution.get('status', 'executed'),
            'os_action_status': execution.get('status', 'executed'),
            'emotion': current_state['emotion']['dominant'],
            'workload': current_state['workload']['score'],
            'context': canonical_context
        })

        # 9. Deliver ONE intelligent notification
        detection_summary = f"{current_state['emotion']['dominant']} · Workload {int(current_state['workload']['score'] * 100)}%"
        notif_res = notification_service.send_adaptation_notification(
            action=decision.action,
            reason=decision.reason,
            adaptive_score=as_score,
            detection_summary=detection_summary,
            camera_used=bool(camera_active),
            cycle_id=self.cycle_id,
            decision_id=did,
            context=canonical_context,
            context_confidence=decision_ctx_conf
        )
        update_decision_notification(did, notif_res.get('status', 'delivered'))

        # 10. Complete transition into ADAPTATION
        self.phase = "ADAPTATION"
        logger.info(f"Cycle #{self.cycle_id} now in ADAPTATION phase. OS Adaptation '{decision.action}' active for next adaptation window.")

    def _transition_to_input_collection(self):
        """
        Exact transition: ADAPTATION -> INPUT_COLLECTION at the cycle boundary.
        1. Finalizes the previous cycle in the DB.
        2. Increments cycle_id.
        3. Re-opens the camera according to privacy settings.
        4. Initializes a fresh InputObservationWindow.
        5. Switches phase to INPUT_COLLECTION.
        """
        now_ts = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        logger.info(f"=== [CYCLE BOUNDARY] Ending Adaptation Phase -> Starting INPUT_COLLECTION for Cycle #{self.cycle_id + 1} ===")

        if self.active_cycle_row_id:
            update_cycle_phase(self.active_cycle_row_id, phase='COMPLETED', end_time=now_iso, status='SUCCESS')

        self.cycle_id += 1
        self.cycle_start_time = now_ts
        self.phase = "INPUT_COLLECTION"

        # Camera may resume according to configured privacy policy
        if settings.camera_sensing_enabled and not self.paused and self.camera:
            self.camera.open_camera()

        self.current_window = InputObservationWindow(
            cycle_id=self.cycle_id,
            start_time=now_ts,
            duration_seconds=float(settings.get_effective_cycle_seconds())
        )
        logger.info(f"Cycle #{self.cycle_id} INPUT_COLLECTION started. Real sensor data accumulation active.")

    def _resync_from_sleep(self, slot_info: Dict[str, Any]):
        """Handles resume after machine sleep or background pause."""
        self.phase = slot_info['phase']
        now_ts = time.time()
        self.cycle_start_time = now_ts

        if self.phase == "INPUT_COLLECTION":
            self.current_window = InputObservationWindow(
                cycle_id=self.cycle_id,
                start_time=now_ts,
                duration_seconds=slot_info['block_seconds']
            )
            if settings.camera_sensing_enabled and not self.paused and self.camera:
                self.camera.open_camera()
        else:
            if self.camera:
                self.camera.close_camera()

    def get_cycle_status(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            slot_info = self._compute_wall_clock_slot(now)
            remaining = slot_info['remaining_seconds']
            block_sec = slot_info['block_seconds']
            elapsed = max(0.0, block_sec - remaining)
            next_iso = datetime.fromtimestamp(slot_info['boundary_time'], tz=timezone.utc).isoformat()
            next_local_str = datetime.fromtimestamp(slot_info['boundary_time']).strftime("%H:%M")
            next_phase_display = f"NEXT {slot_info['next_phase'].replace('_', ' ')} {next_local_str}"

            if self.paused:
                cam_status = "MONITORING PAUSED"
            elif self.phase == "ADAPTATION":
                cam_status = "CAMERA PAUSED (Adaptation Window)"
            elif not settings.camera_sensing_enabled:
                cam_status = "CAMERA OFF (Privacy Setting)"
            elif self.camera and self.camera.is_active():
                cam_status = "CAMERA ACTIVE"
            else:
                cam_status = "CAMERA READY"

            policy_status = self.engine.policy_learner.get_status() if hasattr(self.engine, 'policy_learner') else None

            # Exact status indicators per prompt specification
            if self.phase == "INPUT_COLLECTION":
                status_indicators = {
                    'keyboard': 'RECEIVING',
                    'mouse': 'RECEIVING',
                    'camera': 'CAMERA SENSING' if (self.camera and self.camera.is_active()) else 'PAUSED',
                    'context': 'UPDATING',
                    'emotion': 'UPDATING',
                    'workload': 'UPDATING',
                    'personalization': 'UPDATING',
                    'decision_engine': 'ANALYZING',
                    'os_actuator': 'READY'
                }
            else:  # ADAPTATION
                status_indicators = {
                    'keyboard': 'PAUSED',
                    'mouse': 'PAUSED',
                    'camera': 'PAUSED',
                    'context': 'PAUSED',
                    'emotion': 'FROZEN',
                    'workload': 'FROZEN',
                    'as': 'FROZEN',
                    'decision': 'FROZEN',
                    'os_actuator': 'ACTIVE'
                }

            return {
                'cycle_id': self.cycle_id,
                'phase': self.phase,
                'next_phase': slot_info['next_phase'],
                'next_phase_display': next_phase_display,
                'next_phase_time': next_local_str,
                'mode': 'DEMO' if settings.demo_mode else 'PRODUCTION',
                'cycle_duration_seconds': int(block_sec),
                'remaining_seconds': int(remaining),
                'elapsed_seconds': int(elapsed),
                'next_processing_time': next_iso,
                'input_collection_active': (self.phase == "INPUT_COLLECTION") and not self.paused,
                'adaptation_active': (self.phase == "ADAPTATION"),
                'monitoring_paused': self.paused,
                'decision_processing': False,
                'camera_active': (self.camera.is_active() if self.camera else False) and not self.paused and (self.phase == "INPUT_COLLECTION"),
                'camera_status': cam_status,
                'camera_sensing_enabled': settings.camera_sensing_enabled,
                'automation_enabled': settings.automation_enabled,
                'personalization_status': self.engine.personalization.status,
                'personalization_samples': self.engine.personalization.total_cycle_samples,
                'policy_status': policy_status,
                'pending_adaptation': self.pending_adaptation is not None,
                'latest_decision': self.latest_decision,
                'latest_execution': self.latest_execution,
                'actual_os_state': self.actuator.get_current_os_state(),
                'status_indicators': status_indicators
            }
