import asyncio
import time
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, HTTPException, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.services.notification import notification_service
from app.db.database import (
    init_db,
    insert_decision,
    recent_decisions,
    get_decisions_history,
    get_decision_by_id,
    add_feedback,
    feedback_stats,
    save_setting,
    load_settings,
    recent_cycles,
    recent_notifications,
    get_decisions_by_period,
    get_os_state_durations,
    recent_os_state_events,
    get_camera_sensing_stats,
    recent_camera_sessions,
    load_signal_baselines,
    record_context_observation,
    get_context_history,
    add_feedback_for_decision,
    get_effectiveness_stats,
    get_policy_stats,
    clear_decision_history,
    cleanup_data_retention
)
from app.sensors.keyboard import KeyboardSensor
from app.sensors.mouse import MouseSensor
from app.sensors.context import ContextSensor
from app.sensors.camera import CameraSensor
from app.services.state import StateBuilder
from app.decision_engine.engine import DecisionEngine
from app.services.actuator import OSActuator
from app.services.scheduler import CycleScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("eaos.main")

app = FastAPI(title="EAOS API — Continuous Adaptive Cycle", version="2.5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Core subsystems
keyboard = KeyboardSensor()
mouse = MouseSensor()
context = ContextSensor()
camera = CameraSensor()
builder = StateBuilder()
engine = DecisionEngine()
actuator = OSActuator()
scheduler = CycleScheduler(camera, builder, engine, actuator)

last_keyboard_time = 0.0
last_mouse_time = 0.0
last_camera_time = 0.0
last_context_time = 0.0


@app.on_event("startup")
async def startup():
    logger.info("Initializing EAOS database and subsystems for continuous adaptive cycle...")
    init_db()

    # Load persistent settings
    try:
        saved = load_settings()
        if saved:
            settings.update_from_dict(saved)
            logger.info("Loaded persisted settings from database.")
    except Exception as e:
        logger.warning(f"Could not load settings from DB: {e}")

    # Start non-camera behavioral sensors
    try:
        keyboard.start()
        mouse.start()
    except Exception as e:
        logger.warning(f"Sensor startup issue: {e}")

    # Start repeating adaptive cycle scheduler
    scheduler.start()
    logger.info(f"EAOS continuous adaptive cycle active. Personalization: {engine.personalization.status}")

@app.on_event("shutdown")
def shutdown():
    logger.info("Shutting down EAOS subsystems safely...")
    scheduler.stop()
    camera.close_camera()

def get_current_telemetry_snapshot():
    global last_keyboard_time, last_mouse_time, last_camera_time, last_context_time
    now = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Build current frame of state
    state = builder.build(keyboard, mouse, camera, context, simulation=settings.simulation)

    # Track sensor activity
    kb = state['inputs']['keyboard']
    ms = state['inputs']['mouse']
    cam = state['inputs']['camera']
    ctx = state.get('context', {})

    if kb.get('events', 0) > 0 or kb.get('typing_rate', 0.0) > 0:
        last_keyboard_time = now
    if ms.get('clicks', 0) > 0 or ms.get('movement_distance', 0.0) > 0 or not ms.get('idle', True):
        last_mouse_time = now
    if cam.get('active', False) or cam.get('face_detected', False):
        last_camera_time = now
    if ctx.get('active_app') and ctx.get('active_app') != 'Unknown':
        last_context_time = now

    # Input health status calculation
    kb_sec = round(now - last_keyboard_time, 1) if last_keyboard_time > 0 else None
    ms_sec = round(now - last_mouse_time, 1) if last_mouse_time > 0 else None
    ctx_sec = round(now - last_context_time, 1) if last_context_time > 0 else None
    cam_sec = round(now - last_camera_time, 1) if last_camera_time > 0 else None

    kb_status = "ACTIVE" if (kb_sec is not None and kb_sec < 45) else ("IDLE" if kb_sec is not None and kb_sec < 180 else "STALE")
    ms_status = "ACTIVE" if (ms_sec is not None and ms_sec < 45) else ("IDLE" if ms_sec is not None and ms_sec < 180 else "STALE")
    ctx_status = "ACTIVE" if (ctx_sec is not None and ctx_sec < 30) else "STALE"

    if scheduler.paused:
        cam_status = "MONITORING PAUSED"
    elif not settings.camera_sensing_enabled:
        cam_status = "CAMERA OFF (Privacy Setting)"
    elif camera.is_active():
        cam_status = "CAMERA ACTIVE"
    else:
        cam_status = "CAMERA READY"

    # Calculate real-time Adaptive Score (AS) incorporating personalization
    as_score, as_components = engine.calculate_as(state)

    dominant_emo = state.get('emotion', {}).get('dominant', 'Focused')
    conf_emo = state.get('emotion', {}).get('confidence', 0.85)
    camera.set_current_emotion(dominant_emo, conf_emo)

    # Send periodic telemetry sample to current observation window
    scheduler.sample_telemetry(
        kb=kb,
        ms=ms,
        ctx=ctx,
        cam=cam,
        workload=state['workload']['score']
    )

    cycle_status = scheduler.get_cycle_status()

    # Personalization snapshot and live deviations
    personalization_snap = engine.personalization.snapshot()
    personal_deviations = engine.personalization.calculate_personal_deviations(state)

    # Policy status
    policy_status = engine.policy_learner.get_status() if hasattr(engine, 'policy_learner') else None

    # Latest adaptation info
    latest_decision = scheduler.latest_decision
    if not latest_decision:
        recent = recent_decisions(1)
        if recent:
            latest_decision = recent[0]
        else:
            latest_decision = {
                'action': 'NO_ACTION',
                'reason': 'Initial input window active. Monitoring signals.',
                'confidence': 0.85,
                'policy': 'Personalized Adaptive Engine',
                'adaptive_score': as_score,
                'status': 'input_collection',
                'timestamp': now_iso
            }

    # Strict state separation: During ADAPTATION, telemetry and AS are FROZEN from previous input window
    if scheduler.phase == "ADAPTATION" and scheduler.frozen_state:
        disp_state = scheduler.frozen_state
        disp_as = scheduler.frozen_as
        disp_as_components = scheduler.frozen_as_components
        disp_decision = scheduler.latest_decision or latest_decision
    else:
        disp_state = state
        disp_as = as_score
        disp_as_components = as_components
        disp_decision = latest_decision

    return {
        'timestamp': now_iso,
        'mode': 'SIMULATION' if settings.simulation else ('DEMO' if settings.demo_mode else 'LIVE'),
        'cycle': cycle_status,
        'cycle_id': cycle_status['cycle_id'],
        'phase': cycle_status['phase'],
        'next_phase': cycle_status.get('next_phase'),
        'next_phase_display': cycle_status.get('next_phase_display'),
        'next_phase_time': cycle_status.get('next_phase_time'),
        'cycle_duration_seconds': cycle_status['cycle_duration_seconds'],
        'remaining_seconds': cycle_status['remaining_seconds'],
        'next_processing_time': cycle_status['next_processing_time'],
        'input_collection_active': cycle_status['input_collection_active'],
        'adaptation_active': cycle_status.get('adaptation_active', False),
        'decision_processing': cycle_status['decision_processing'],
        'camera_active': cycle_status['camera_active'],
        'camera_status': cam_status,
        'monitoring_paused': scheduler.paused,
        'status_indicators': cycle_status.get('status_indicators', {}),
        'heartbeats': {
            'last_keyboard_sec': kb_sec,
            'last_mouse_sec': ms_sec,
            'last_context_sec': ctx_sec,
            'last_camera_sec': cam_sec,
            'keyboard_status': kb_status,
            'mouse_status': ms_status,
            'context_status': ctx_status,
            'camera_status': cam_status
        },
        'latest_action': disp_decision.get('action', 'NO_ACTION'),
        'emotion': disp_state['emotion'],
        'context': disp_state['context'],
        'workload': disp_state['workload'],
        'policy': policy_status,
        'personalization': {
            'status': engine.personalization.status,
            'enabled': settings.personalization_enabled,
            'samples': engine.personalization.total_cycle_samples,
            'calibration_cycles': settings.calibration_cycles,
            'baseline': personalization_snap['baselines'],
            'deviations': personal_deviations
        },
        'adaptive_score': {
            'score': disp_as,
            'emotion_component': disp_as_components.get('emotion', 0.5),
            'context_component': disp_as_components.get('context', 0.5),
            'workload_component': disp_as_components.get('workload', 0.5),
            'personalization_component': disp_as_components.get('personalization', 0.5),
            'weights': settings.as_weights
        },
        'ass': {
            'score': disp_as,
            'emotion_component': disp_as_components.get('emotion', 0.5),
            'context_component': disp_as_components.get('context', 0.5),
            'workload_component': disp_as_components.get('workload', 0.5),
            'personalization_component': disp_as_components.get('personalization', 0.5),
            'weights': settings.as_weights
        },
        'decision': disp_decision,
        'inputs': state['inputs'],
        'actual_os_state': actuator.get_current_os_state(),
        'system': {
            'backend': 'RUNNING',
            'decision_engine': 'RUNNING',
            'os_adapter': 'READY' if actuator.system == 'Darwin' else 'SIMULATED',
            'scheduler': 'RUNNING' if scheduler.running else 'STOPPED',
            'camera_status': cam_status,
            'monitoring_paused': scheduler.paused
        }
    }


@app.get('/')
def root():
    """Root status endpoint providing service status and links to frontend dashboard and API docs."""
    return {
        "service": "EAOS Backend API",
        "status": "online",
        "version": "1.0.0",
        "docs_url": "http://127.0.0.1:8765/docs",
        "frontend_url": "http://127.0.0.1:5173",
        "message": "EAOS API is running. Open http://127.0.0.1:5173 for the live Dashboard or /docs for API documentation."
    }


@app.get('/api/v1/os/state')
def get_os_state():
    """Ground truth endpoint querying actual macOS state (appearance, brightness, audio volume)."""
    return actuator.get_current_os_state()


@app.post('/api/v1/actions/execute')
def execute_direct_action(payload: dict):
    """
    Executes a direct operating system adaptation (Dark Mode, Light Mode, Focus/DND, Brightness).
    Used for instant user mode switching and validation testing.
    """
    action = payload.get('action')
    if not action:
        raise HTTPException(status_code=400, detail="Missing required 'action' field")
    
    action_clean = action.replace("_", " ").title()
    reason = payload.get('reason', f'Direct user adaptation triggered: {action_clean}')
    params = payload.get('params', {})
    if 'value' in payload:
        params['value'] = payload['value']
    if 'brightness' in payload:
        params['brightness'] = payload['brightness']
    if 'volume' in payload:
        params['volume'] = payload['volume']
    params['reason'] = reason
    params['cycle_id'] = scheduler.cycle_id

    # 1. Execute real OS actuator
    execution = actuator.execute(action, params)
    now_iso = datetime.now(timezone.utc).isoformat()

    # 2. Record decision in database
    did = insert_decision({
        'timestamp': now_iso,
        'cycle_id': scheduler.cycle_id,
        'emotion': 'Focused',
        'emotion_confidence': 0.95,
        'workload': 0.50,
        'adaptive_score': 0.50,
        'ass': 0.50,
        'context': 'MANUAL_OVERRIDE',
        'context_confidence': 1.0,
        'explanation': {'why': reason, 'factors': ['Direct user command']},
        'action': action,
        'reason': reason,
        'confidence': 1.0,
        'policy': 'Direct Execution',
        'status': execution.get('status', 'executed'),
        'notification_status': 'delivered',
        'typing_rate': 0.0,
        'backspace_rate': 0.0,
        'mouse_jitter': 0.0,
        'camera_active': 0,
        'emotion_probabilities': '{}',
        'baseline_workload': 0.35,
        'baseline_typing': 3.5,
        'baseline_jitter': 0.12,
        'verified': 1 if execution.get('verified') else 0,
        'command_used': execution.get('command_used'),
        'state_before': execution.get('state_before'),
        'state_after': execution.get('state_after'),
        'execution_error': execution.get('error')
    })

    # 3. Deliver notification (force=True to bypass 10s duplicate filter)
    notif = notification_service.send_adaptation_notification(
        action=action,
        reason=reason,
        adaptive_score=0.50,
        detection_summary=f"OS Action: {action_clean}",
        camera_used=False,
        cycle_id=scheduler.cycle_id,
        decision_id=did,
        force=True
    )

    # 3b. Train Contextual Bandit Policy Learner on explicit manual user preference
    if hasattr(engine, 'policy_learner'):
        manual_state = {
            'workload': {'score': 0.55},
            'adaptive_score': 0.50,
            'emotion': {'dominant': 'Focused', 'probabilities': {'Focused': 0.75}},
            'context': {'canonical_context': 'CODING'},
            'inputs': {'keyboard': {'avg_typing_rate': 3.5, 'typing_rate': 3.5}}
        }
        engine.policy_learner.update(action, manual_state, reward=1.0, source="MANUAL_ACTION")

    # 4. Synchronize scheduler latest_decision so UI reflects it immediately
    exec_status = execution.get('status', 'executed')
    is_verified = execution.get('verified', False)
    scheduler.latest_decision = {
        'action': action,
        'reason': reason,
        'confidence': 1.0,
        'policy': 'Direct Execution',
        'adaptive_score': 0.50,
        'timestamp': now_iso,
        'status': exec_status,
        'verified': is_verified,
        'command_used': execution.get('command_used', 'NONE'),
        'message': execution.get('message', ''),
        'execution_details': execution
    }

    return {
        'ok': True,
        'decision_id': did,
        'execution': execution,
        'notification': notif,
        'actual_os_state': actuator.get_current_os_state()
    }


@app.get('/api/v1/health')
def health():
    cycle = scheduler.get_cycle_status()
    os_state = actuator.get_current_os_state()
    return {
        'status': 'ok',
        'backend': 'RUNNING',
        'platform': actuator.system,
        'database': 'CONNECTED',
        'cycle_phase': cycle['phase'],
        'remaining_seconds': cycle['remaining_seconds'],
        'keyboard_sensor': 'RECEIVING' if keyboard.active else 'UNAVAILABLE',
        'mouse_sensor': 'RECEIVING' if mouse.active else 'UNAVAILABLE',
        'camera_sensor': camera.status_text,
        'personalization': engine.personalization.status,
        'scheduler': 'RUNNING' if scheduler.running else 'STOPPED',
        'decision_engine': 'RUNNING',
        'os_actuator': 'READY' if actuator.system == 'Darwin' else 'SIMULATED',
        'actual_os_state': os_state,
        'diagnostics': {
            'keyboard_listener_active': bool(keyboard.active),
            'mouse_listener_active': bool(mouse.active),
            'camera_active': bool(camera.is_active()) if hasattr(camera, 'is_active') else False,
            'camera_frame_age': round(time.time() - camera.last_frame_time, 2) if getattr(camera, 'last_frame_time', None) else None,
            'context_last_update': datetime.fromtimestamp(getattr(context, 'last_update_time', time.time()), tz=timezone.utc).isoformat(),
            'last_keyboard_event': keyboard.last_press_time,
            'last_mouse_event': mouse.last_event,
            'sample_count': len(scheduler.current_window.workload_samples) if scheduler.current_window else 0,
            'camera_sample_count': len(scheduler.current_window.camera_samples) if scheduler.current_window else 0,
            'input_window_duration': float(settings.get_effective_cycle_seconds()),
            'phase': cycle['phase'],
            'seconds_remaining': cycle['remaining_seconds'],
            'last_decision': scheduler.latest_decision,
            'last_action_execution': scheduler.latest_execution,
            'last_verification': scheduler.latest_decision.get('verified') if scheduler.latest_decision else None
        },
        'timestamp': datetime.now(timezone.utc).isoformat()
    }

@app.get('/api/v1/cycle/current')
def get_current_cycle():
    return scheduler.get_cycle_status()

@app.get('/api/v1/state/current')
def get_state():
    return get_current_telemetry_snapshot()

@app.get('/api/v1/decisions/recent')
def get_decisions():
    return recent_decisions(50)

@app.get('/api/v1/decisions/history')
def get_decisions_history_route(
    limit: int = 100,
    offset: int = 0,
    action: Optional[str] = None,
    context: Optional[str] = None,
    effectiveness: Optional[str] = None,
    search: Optional[str] = None
):
    return get_decisions_history(
        limit=limit,
        offset=offset,
        action=action,
        context=context,
        effectiveness=effectiveness,
        search=search
    )

@app.get('/api/v1/notifications/recent')
def get_recent_notifications(limit: int = 50):
    return recent_notifications(limit)

@app.get('/api/v1/notifications/preferences')
def get_notification_preferences():
    return notification_service.get_settings()

@app.post('/api/v1/notifications/preferences')
def update_notification_preferences(payload: dict):
    notification_service.update_settings(payload)
    return {'ok': True, 'preferences': notification_service.get_settings()}

@app.get('/api/v1/decisions/{decision_id}')
def get_decision(decision_id: int):
    d = get_decision_by_id(decision_id)
    if not d:
        raise HTTPException(status_code=404, detail="Decision not found")
    return d

@app.post('/api/v1/decisions/{decision_id}/feedback')
def feedback(decision_id: int, payload: dict):
    raw_fb = str(payload.get('feedback', 'KEEP')).strip().upper()
    if raw_fb in ['ACCEPTED', 'KEEP', 'LIKE']:
        fb = 'KEEP'
        reward = 1.0
    elif raw_fb in ['UNDONE', 'UNDO']:
        fb = 'UNDO'
        reward = -1.0
    elif raw_fb in ['DISMISSED', 'DISMISS', 'REJECTED']:
        fb = 'DISMISS'
        reward = -1.0
    else:
        fb = raw_fb
        reward = 0.0

    d = get_decision_by_id(decision_id)
    act = d.get('action', 'NO_ACTION') if d else 'NO_ACTION'
    as_val = d.get('adaptive_score', 0.0) if d else 0.0
    ctx_val = d.get('context', 'UNKNOWN') if d else 'UNKNOWN'

    add_feedback_for_decision(decision_id, fb, reward, action=act, adaptive_score=as_val, context=ctx_val)

    # Contextual bandit update
    if hasattr(engine, 'policy_learner') and d:
        dummy_state = {
            'workload': {'score': d.get('workload', 0.5)},
            'adaptive_score': as_val,
            'emotion': {'dominant': d.get('emotion', 'Focused')},
            'context': {'canonical_context': ctx_val},
            'inputs': {'keyboard': {'typing_rate': d.get('typing_rate', 0.0)}}
        }
        engine.policy_learner.update(act, dummy_state, reward, source="USER_FEEDBACK")

    undo_result = None
    if fb == 'UNDO' and act != 'NO_ACTION':
        undo_result = actuator.undo_action(act)
        if scheduler.latest_decision:
            scheduler.latest_decision['status'] = 'undone'
            scheduler.latest_decision['message'] = f"Action {act.replace('_', ' ').title()} was undone by user feedback."

    return {
        'ok': True,
        'decision_id': decision_id,
        'feedback': fb,
        'reward': reward,
        'action': act,
        'undo_result': undo_result
    }


@app.get('/api/v1/profile/baseline')
def get_baseline():
    return engine.personalization.snapshot()

@app.post('/api/v1/profile/reset')
def reset_baseline():
    engine.personalization.reset()
    return {
        'ok': True,
        'message': 'Personal baseline statistics reset successfully. System returned to CALIBRATING status.',
        'personalization': engine.personalization.snapshot()
    }

@app.get('/api/v1/analytics/timeline')
def analytics():
    return {
        'decisions': recent_decisions(100),
        'cycles': recent_cycles(50),
        'notifications': recent_notifications(50),
        'feedback': feedback_stats()
    }

@app.get('/api/v1/analytics/summary')
def analytics_summary(period: str = 'all'):
    decisions = get_decisions_by_period(period)
    os_durations = get_os_state_durations()
    os_events = recent_os_state_events(100)
    camera_stats = get_camera_sensing_stats()
    baselines = load_signal_baselines()

    action_frequency = {
        'ENABLE_DARK_MODE': 0,
        'DISABLE_DARK_MODE': 0,
        'ENABLE_FOCUS_MODE': 0,
        'DISABLE_FOCUS_MODE': 0,
        'SUGGEST_BREAK': 0,
        'REDUCE_BRIGHTNESS': 0,
        'NO_ACTION': 0
    }
    emotion_distribution = {
        'Focused': 0,
        'Relaxed': 0,
        'Frustrated': 0,
        'Fatigued': 0,
        'Confused': 0
    }

    total_typing = 0.0
    typing_count = 0

    for d in decisions:
        act = d.get('action', 'NO_ACTION')
        if act in action_frequency:
            action_frequency[act] += 1
        else:
            action_frequency[act] = 1

        emo = d.get('emotion', 'Focused')
        if emo in emotion_distribution:
            emotion_distribution[emo] += 1
        else:
            emotion_distribution[emo] = 1

        rate = d.get('typing_rate', 0.0)
        if rate and rate > 0:
            total_typing += rate
            typing_count += 1

    avg_typing = round(total_typing / max(1, typing_count), 2) if typing_count > 0 else 0.0
    current_typing = decisions[-1].get('typing_rate', 0.0) if decisions else 0.0
    current_workload = decisions[-1].get('workload', 0.0) if decisions else 0.0
    current_as = decisions[-1].get('adaptive_score', 0.0) if decisions else 0.0
    current_emotion = decisions[-1].get('emotion', 'Focused') if decisions else 'Focused'

    baseline_typing = baselines.get('typing_rate', {}).get('mean', 3.5)
    baseline_workload = baselines.get('workload', {}).get('mean', 0.35)
    baseline_jitter = baselines.get('mouse_jitter', {}).get('mean', 0.12)

    typing_deviation_pct = round(((current_typing - baseline_typing) / max(0.1, baseline_typing)) * 100, 1) if current_typing > 0 else 0.0

    return {
        'period': period,
        'total_assessments': len(decisions),
        'decisions': decisions,
        'os_durations': os_durations,
        'os_events': os_events,
        'camera_stats': camera_stats,
        'action_frequency': action_frequency,
        'emotion_distribution': emotion_distribution,
        'personal_baselines': baselines,
        'overview': {
            'adaptive_score': round(current_as, 2),
            'workload': round(current_workload, 2),
            'typing_speed': round(current_typing, 2),
            'avg_typing_speed': avg_typing,
            'baseline_typing': round(baseline_typing, 2),
            'typing_deviation_pct': typing_deviation_pct,
            'baseline_workload': round(baseline_workload, 2),
            'baseline_jitter': round(baseline_jitter, 3),
            'dominant_emotion': current_emotion,
            'adaptations_count': sum(v for k, v in action_frequency.items() if k != 'NO_ACTION'),
            'camera_sessions_count': camera_stats.get('camera_sessions_count', 0)
        }
    }

@app.get('/api/v1/analytics/typing-speed')
def analytics_typing(period: str = 'all'):
    decisions = get_decisions_by_period(period)
    b_mean = engine.personalization.get_signal_mean('typing_rate', 3.5)
    items = []
    for d in decisions:
        rate = d.get('typing_rate', 0.0) or 0.0
        dev = round(((rate - b_mean) / max(0.1, b_mean)) * 100, 1) if rate > 0 else 0.0
        items.append({
            'timestamp': d.get('timestamp'),
            'typing_rate': rate,
            'baseline': d.get('baseline_typing', b_mean) or b_mean,
            'backspace_rate': d.get('backspace_rate', 0.0),
            'deviation_pct': dev
        })
    return {'period': period, 'data': items, 'baseline': b_mean}

@app.get('/api/v1/analytics/emotions')
def analytics_emotions(period: str = 'all'):
    decisions = get_decisions_by_period(period)
    items = []
    for d in decisions:
        probs = d.get('emotion_probabilities', {})
        items.append({
            'timestamp': d.get('timestamp'),
            'dominant': d.get('emotion'),
            'confidence': d.get('emotion_confidence', 0.0),
            'camera_active': bool(d.get('camera_active', 0)),
            'probabilities': probs
        })
    return {'period': period, 'data': items}

@app.get('/api/v1/analytics/workload')
def analytics_workload(period: str = 'all'):
    decisions = get_decisions_by_period(period)
    b_mean = engine.personalization.get_signal_mean('workload', 0.35)
    items = [{
        'timestamp': d.get('timestamp'),
        'workload': d.get('workload', 0.0),
        'baseline': d.get('baseline_workload', b_mean) or b_mean
    } for d in decisions]
    return {'period': period, 'data': items, 'baseline': b_mean}

@app.get('/api/v1/analytics/adaptive-score')
def analytics_as(period: str = 'all'):
    decisions = get_decisions_by_period(period)
    items = [{
        'timestamp': d.get('timestamp'),
        'adaptive_score': d.get('adaptive_score', 0.0),
        'action': d.get('action'),
        'is_adaptation': d.get('action') != 'NO_ACTION'
    } for d in decisions]
    return {'period': period, 'data': items}

@app.get('/api/v1/analytics/os-adaptations')
def analytics_os_adaptations():
    return {
        'events': recent_os_state_events(100),
        'durations': get_os_state_durations()
    }

@app.get('/api/v1/analytics/display-mode')
def analytics_display_mode():
    durations = get_os_state_durations()
    return {
        'dark_mode_seconds': durations.get('dark_mode_seconds', 0.0),
        'light_mode_seconds': durations.get('light_mode_seconds', 0.0),
        'total_monitored_seconds': durations.get('total_monitored_seconds', 0.0),
        'current_appearance': durations.get('current_appearance', 'LIGHT')
    }

@app.get('/api/v1/analytics/dnd')
def analytics_dnd():
    durations = get_os_state_durations()
    return {
        'focus_mode_seconds': durations.get('focus_mode_seconds', 0.0),
        'focus_disabled_seconds': durations.get('focus_disabled_seconds', 0.0),
        'activations': durations.get('focus_activations', 0),
        'deactivations': durations.get('focus_deactivations', 0),
        'current_focus': durations.get('current_focus', 'OFF')
    }

@app.get('/api/v1/analytics/camera')
def analytics_camera():
    return get_camera_sensing_stats()

@app.get('/api/v1/camera/stream')
def camera_stream():
    """Streams live MJPEG camera feed with face tracking and real-time emotion HUD."""
    def frame_generator():
        while True:
            frame_bytes = camera.get_stream_frame()
            if frame_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.06)  # ~16 FPS
    return StreamingResponse(frame_generator(), media_type='multipart/x-mixed-replace; boundary=frame')

@app.get('/api/v1/camera/frame')
def camera_single_frame():
    """Returns a single current JPEG image frame for static previews or polling fallback."""
    frame_bytes = camera.get_stream_frame()
    return Response(content=frame_bytes, media_type='image/jpeg')

@app.post('/api/v1/camera/preview')
def set_camera_preview(payload: dict):
    """Enables or disables continuous live camera preview mode."""
    preview = bool(payload.get('preview', True))
    camera.set_preview_requested(preview)
    if preview:
        camera.open_camera()
    else:
        if scheduler.phase == "ADAPTATION":
            camera.close_camera(force=True)
    return {
        'ok': True,
        'preview_requested': camera.preview_requested,
        'camera_active': camera.is_active(),
        'status': camera.status_text
    }

@app.get('/api/v1/settings')
def get_all_settings():
    return {
        'automation_enabled': settings.automation_enabled,
        'camera_sensing_enabled': settings.camera_sensing_enabled,
        'demo_mode': settings.demo_mode,
        'cycle_duration_minutes': settings.cycle_duration_minutes,
        'demo_cycle_minutes': settings.demo_cycle_minutes,
        'personalization_enabled': settings.personalization_enabled,
        'calibration_cycles': settings.calibration_cycles,
        'personalization_alpha': settings.personalization_alpha,
        'baseline_adaptation': settings.baseline_adaptation,
        'sensitivity': settings.sensitivity,
        'thresholds': settings.thresholds,
        'as_weights': settings.as_weights,
        'simulation': settings.simulation
    }

@app.post('/api/v1/settings')
def update_all_settings(payload: dict):
    settings.update_from_dict(payload)
    for k, v in payload.items():
        try:
            save_setting(k, v)
        except Exception:
            pass
    return {'ok': True, 'settings': get_all_settings()}

@app.get('/api/v1/diagnostics')
def diagnostics():
    now = time.time()
    cycle = scheduler.get_cycle_status()
    last_assessment = recent_decisions(1)
    last_assessment_str = last_assessment[0]['timestamp'] if last_assessment else 'Awaiting first assessment'

    return {
        'health': {
            'input_collection': {'status': 'ACTIVE' if cycle['input_collection_active'] else 'PROCESSING', 'detail': f"Cycle #{cycle['cycle_id']}"},
            'backend': {'status': 'CONNECTED', 'detail': 'FastAPI port 8765'},
            'database': {'status': 'CONNECTED', 'detail': f'SQLite {settings.db_path}'},
            'camera': {'status': cycle['camera_status'], 'detail': 'Webcam streaming' if camera.is_active() else 'Hardware released'},
            'keyboard': {'status': 'RECEIVING' if keyboard.active else 'UNAVAILABLE', 'detail': f'{keyboard.total_events} keystrokes logged'},
            'mouse': {'status': 'RECEIVING' if mouse.active else 'UNAVAILABLE', 'detail': f'{mouse.total_clicks} clicks logged'},
            'context': {'status': 'DETECTED' if context.last_app else 'CHECKING', 'detail': context.last_app or 'Unknown'},
            'workload': {'status': 'UPDATING', 'detail': 'Continuous scoring'},
            'emotion': {'status': 'UPDATING', 'detail': 'Multimodal inference'},
            'adaptive_score': {'status': 'READY', 'detail': 'Personalized AS Index'},
            'personalization': {'status': engine.personalization.status, 'detail': f"{engine.personalization.total_cycle_samples} samples collected"},
            'decision_engine': {'status': 'RUNNING' if cycle['decision_processing'] else 'WAITING', 'detail': 'Adaptive Evaluator'},
            'os_actuator': {
                'status': 'READY' if actuator.system == 'Darwin' else 'SIMULATED',
                'detail': f'{actuator.system} Native (AppleScript + DisplayServices)',
                'actual_os_state': actuator.get_current_os_state()
            }
        },
        'telemetry_timestamps': {
            'last_keyboard_event': datetime.fromtimestamp(last_keyboard_time, tz=timezone.utc).isoformat() if last_keyboard_time > 0 else 'Monitoring...',
            'last_mouse_event': datetime.fromtimestamp(last_mouse_time, tz=timezone.utc).isoformat() if last_mouse_time > 0 else 'Monitoring...',
            'last_context_update': datetime.now(timezone.utc).isoformat(),
            'cycle_start': datetime.fromtimestamp(scheduler.cycle_start_time, tz=timezone.utc).isoformat(),
            'last_assessment_time': last_assessment_str,
            'next_assessment_time': cycle['next_processing_time'],
            'next_decision_seconds': cycle['remaining_seconds']
        }
    }

@app.post('/api/v1/actions/reset')
def reset_system():
    engine.reset()
    res = actuator.reset_all()
    now = datetime.now(timezone.utc).isoformat()
    record = {
        'timestamp': now,
        'cycle_id': scheduler.cycle_id,
        'emotion': 'System Reset',
        'emotion_confidence': 1.0,
        'workload': 0.0,
        'adaptive_score': 0.0,
        'ass': 0.0,
        'context': 'Manual Reset Trigger',
        'action': 'RESET_ALL',
        'reason': 'User requested full system reset to default state',
        'confidence': 1.0,
        'policy': 'System Control',
        'status': res.get('status', 'executed'),
        'notification_status': 'delivered'
    }
    did = insert_decision(record)
    return {'ok': True, 'message': 'System and adaptations reset to default.', 'decision_id': did, 'result': res}

@app.get('/api/v1/context/current')
def get_current_context():
    snap = get_current_telemetry_snapshot()
    ctx = snap.get('context', {})
    return {
        'canonical_context': ctx.get('canonical_context', 'UNKNOWN'),
        'active_app': ctx.get('active_app', 'Unknown'),
        'confidence': ctx.get('confidence', 0.8),
        'session_duration_seconds': ctx.get('session_duration', 0),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }

@app.get('/api/v1/context/history')
def get_context_history_endpoint(limit: int = 50):
    return get_context_history(limit=limit)

@app.get('/api/v1/adaptations/effectiveness')
def get_effectiveness_endpoint():
    return get_effectiveness_stats()

@app.get('/api/v1/policy/status')
def get_policy_status_endpoint():
    status = engine.policy_learner.get_status() if hasattr(engine, 'policy_learner') else {}
    stats = get_policy_stats()
    return {
        **status,
        'policy_stats': stats
    }

@app.get('/api/v1/privacy/status')
def get_privacy_status():
    camera_stats = get_camera_sensing_stats()
    if scheduler.paused:
        hw_state = "PAUSED"
    elif not settings.camera_sensing_enabled:
        hw_state = "OFF"
    elif camera.is_active():
        hw_state = "ACTIVE"
    else:
        hw_state = "BLOCKED / OFF"

    return {
        'monitoring_paused': scheduler.paused,
        'camera_sensing_enabled': settings.camera_sensing_enabled,
        'camera_hardware_state': hw_state,
        'camera_stats': camera_stats,
        'raw_frames_stored': False,
        'text_typed_stored': False,
        'keystroke_content_zero_logging': True,
        'local_processing_only': True,
        'retention_setting': getattr(settings, 'data_retention', 'forever')
    }

@app.post('/api/v1/privacy/pause')
def toggle_monitoring_pause(payload: dict):
    paused = bool(payload.get('paused', True))
    scheduler.set_monitoring_paused(paused)
    return {'ok': True, 'monitoring_paused': scheduler.paused}

@app.post('/api/v1/privacy/clear-history')
def clear_history():
    clear_decision_history()
    return {'ok': True, 'message': 'All decision history, notifications, and observation logs purged.'}

@app.post('/api/v1/privacy/retention')
def apply_retention(payload: dict):
    period = payload.get('retention_period', '30d')
    days_map = {'7d': 7, '30d': 30, '90d': 90, 'forever': 0}
    days = days_map.get(period, 30)
    if days > 0:
        cleanup_data_retention(days)
    return {'ok': True, 'retention_period': period, 'days_applied': days}

@app.post('/api/v1/privacy/settings')
def update_privacy_settings(payload: dict):
    if 'camera_sensing_enabled' in payload:
        enabled = bool(payload['camera_sensing_enabled'])
        settings.camera_sensing_enabled = enabled
        save_setting('camera_sensing_enabled', enabled)
        if not enabled and camera.is_active():
            camera.close_camera()
        elif enabled and not scheduler.paused:
            camera.open_camera()
    return {'ok': True, 'privacy': get_privacy_status()}

@app.get('/api/v1/settings/privacy')
def privacy():
    return get_privacy_status()

@app.get('/api/v1/system/status')
def get_system_status():
    snap = get_current_telemetry_snapshot()
    return {
        'system': snap.get('system', {}),
        'heartbeats': snap.get('heartbeats', {}),
        'cycle': snap.get('cycle', {}),
        'policy': snap.get('policy', {}),
        'monitoring_paused': scheduler.paused,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


@app.websocket('/ws/live-state')
async def ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            snapshot = get_current_telemetry_snapshot()
            await websocket.send_json(snapshot)
            await asyncio.sleep(settings.update_seconds)
    except Exception:
        pass
