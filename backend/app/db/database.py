import sqlite3
import json
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, List
from app.core.config import settings

DB = Path(settings.db_path)

SCHEMA = '''
CREATE TABLE IF NOT EXISTS decisions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 timestamp TEXT NOT NULL,
 cycle_id INTEGER,
 emotion TEXT,
 emotion_confidence REAL,
 workload REAL,
 adaptive_score REAL,
 ass REAL,
 context TEXT,
 action TEXT,
 reason TEXT,
 confidence REAL,
 policy TEXT,
 status TEXT,
 notification_status TEXT,
 typing_rate REAL DEFAULT 0.0,
 backspace_rate REAL DEFAULT 0.0,
 mouse_jitter REAL DEFAULT 0.0,
 camera_active INTEGER DEFAULT 0,
 emotion_probabilities TEXT,
 baseline_workload REAL DEFAULT 0.35,
 baseline_typing REAL DEFAULT 3.5,
 baseline_jitter REAL DEFAULT 0.10
);
CREATE TABLE IF NOT EXISTS hourly_cycles (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 cycle_number INTEGER,
 start_time TEXT NOT NULL,
 end_time TEXT,
 phase TEXT,
 camera_used INTEGER DEFAULT 0,
 samples_count INTEGER DEFAULT 0,
 adaptive_score REAL,
 action TEXT,
 reason TEXT,
 status TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 decision_id INTEGER,
 cycle_id INTEGER,
 timestamp TEXT NOT NULL,
 title TEXT,
 message TEXT,
 action TEXT,
 adaptive_score REAL,
 status TEXT
);
CREATE TABLE IF NOT EXISTS os_state_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 timestamp TEXT NOT NULL,
 setting TEXT NOT NULL,
 state TEXT NOT NULL,
 source TEXT NOT NULL,
 adaptive_score REAL DEFAULT 0.0,
 reason TEXT,
 cycle_id INTEGER,
 duration_seconds REAL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS camera_sessions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 start_time TEXT NOT NULL,
 end_time TEXT,
 duration_seconds REAL DEFAULT 0.0,
 status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 decision_id INTEGER,
 timestamp TEXT NOT NULL,
 feedback TEXT NOT NULL,
 reward REAL NOT NULL,
 action TEXT,
 adaptive_score REAL DEFAULT 0.0,
 context TEXT
);
CREATE TABLE IF NOT EXISTS context_observations (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 timestamp TEXT NOT NULL,
 active_app TEXT NOT NULL,
 context TEXT NOT NULL,
 confidence REAL NOT NULL,
 session_duration INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS adaptation_effectiveness (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 decision_id INTEGER NOT NULL,
 action TEXT NOT NULL,
 pre_as REAL NOT NULL,
 post_as REAL NOT NULL,
 as_delta REAL NOT NULL,
 pre_workload REAL NOT NULL,
 post_workload REAL NOT NULL,
 workload_delta REAL NOT NULL,
 outcome TEXT NOT NULL,
 timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS policy_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 timestamp TEXT NOT NULL,
 policy_name TEXT NOT NULL,
 action TEXT NOT NULL,
 reward REAL NOT NULL,
 context TEXT,
 as_score REAL DEFAULT 0.0,
 details TEXT
);
CREATE TABLE IF NOT EXISTS signal_baselines (
 signal TEXT PRIMARY KEY,
 mean REAL NOT NULL,
 variance REAL NOT NULL,
 observations INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
 key TEXT PRIMARY KEY,
 value TEXT NOT NULL
);
'''

def init_db():
    with sqlite3.connect(DB) as con:
        con.executescript(SCHEMA)
        cursor = con.cursor()
        cursor.execute("PRAGMA table_info(decisions)")
        columns = [row[1] for row in cursor.fetchall()]
        cols_to_add = {
            'adaptive_score': 'REAL',
            'cycle_id': 'INTEGER',
            'notification_status': 'TEXT',
            'typing_rate': 'REAL DEFAULT 0.0',
            'backspace_rate': 'REAL DEFAULT 0.0',
            'mouse_jitter': 'REAL DEFAULT 0.0',
            'camera_active': 'INTEGER DEFAULT 0',
            'emotion_probabilities': 'TEXT',
            'baseline_workload': 'REAL DEFAULT 0.35',
            'baseline_typing': 'REAL DEFAULT 3.5',
            'baseline_jitter': 'REAL DEFAULT 0.10',
            'context_confidence': 'REAL DEFAULT 0.80',
            'explanation_json': 'TEXT',
            'feedback': 'TEXT',
            'effectiveness': 'TEXT',
            'observed_as_change': 'REAL',
            'observed_workload_change': 'REAL',
            'pre_as': 'REAL',
            'post_as': 'REAL',
            'pre_workload': 'REAL',
            'post_workload': 'REAL',
            'verified': 'INTEGER DEFAULT 0',
            'command_used': 'TEXT',
            'state_before': 'TEXT',
            'state_after': 'TEXT',
            'execution_error': 'TEXT'
        }
        for col, col_type in cols_to_add.items():
            if col not in columns:
                try:
                    con.execute(f"ALTER TABLE decisions ADD COLUMN {col} {col_type}")
                except Exception:
                    pass

        cursor.execute("PRAGMA table_info(feedback_events)")
        fb_columns = [row[1] for row in cursor.fetchall()]
        fb_cols_to_add = {
            'action': 'TEXT',
            'adaptive_score': 'REAL DEFAULT 0.0',
            'context': 'TEXT'
        }
        for col, col_type in fb_cols_to_add.items():
            if col not in fb_columns:
                try:
                    con.execute(f"ALTER TABLE feedback_events ADD COLUMN {col} {col_type}")
                except Exception:
                    pass

        cursor.execute("PRAGMA table_info(hourly_cycles)")
        cycle_columns = [row[1] for row in cursor.fetchall()]
        cycle_cols_to_add = {
            'cycle_id': 'INTEGER',
            'input_start_time': 'TEXT',
            'input_end_time': 'TEXT',
            'adaptation_start_time': 'TEXT',
            'adaptation_end_time': 'TEXT',
            'emotion': 'TEXT',
            'workload': 'REAL',
            'context': 'TEXT',
            'selected_action': 'TEXT',
            'os_action_status': 'TEXT'
        }
        for col, col_type in cycle_cols_to_add.items():
            if col not in cycle_columns:
                try:
                    con.execute(f"ALTER TABLE hourly_cycles ADD COLUMN {col} {col_type}")
                except Exception:
                    pass


def insert_decision(d):
    adaptive_score = d.get('adaptive_score', d.get('ass', 0.0))
    probs_json = json.dumps(d.get('emotion_probabilities', {}))
    explanation_json = json.dumps(d.get('explanation', {})) if d.get('explanation') else None
    state_before_json = json.dumps(d.get('state_before', {})) if isinstance(d.get('state_before'), dict) else d.get('state_before')
    state_after_json = json.dumps(d.get('state_after', {})) if isinstance(d.get('state_after'), dict) else d.get('state_after')
    with sqlite3.connect(DB) as con:
        cur = con.execute('''INSERT INTO decisions(
            timestamp, cycle_id, emotion, emotion_confidence, workload,
            adaptive_score, ass, context, action, reason, confidence, policy, status, notification_status,
            typing_rate, backspace_rate, mouse_jitter, camera_active, emotion_probabilities,
            baseline_workload, baseline_typing, baseline_jitter,
            context_confidence, explanation_json, feedback, effectiveness,
            observed_as_change, observed_workload_change, pre_as, post_as, pre_workload, post_workload,
            verified, command_used, state_before, state_after, execution_error
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
            d['timestamp'],
            d.get('cycle_id', 1),
            d.get('emotion', 'Focused'),
            d.get('emotion_confidence', 0.5),
            d.get('workload', 0.5),
            adaptive_score,
            adaptive_score,
            d.get('context', 'GENERAL_WORK'),
            d.get('action', 'NO_ACTION'),
            d.get('reason', ''),
            d.get('confidence', 0.5),
            d.get('policy', 'Decision Engine'),
            d.get('status', 'executed'),
            d.get('notification_status', 'pending'),
            d.get('typing_rate', 0.0),
            d.get('backspace_rate', 0.0),
            d.get('mouse_jitter', 0.0),
            1 if d.get('camera_active') else 0,
            probs_json,
            d.get('baseline_workload', 0.35),
            d.get('baseline_typing', 3.5),
            d.get('baseline_jitter', 0.10),
            d.get('context_confidence', 0.80),
            explanation_json,
            d.get('feedback'),
            d.get('effectiveness'),
            d.get('observed_as_change'),
            d.get('observed_workload_change'),
            d.get('pre_as'),
            d.get('post_as'),
            d.get('pre_workload'),
            d.get('post_workload'),
            1 if d.get('verified') else 0,
            d.get('command_used'),
            state_before_json,
            state_after_json,
            d.get('execution_error')
        ))
        return cur.lastrowid

def update_decision_notification(decision_id: int, notification_status: str):
    with sqlite3.connect(DB) as con:
        con.execute("UPDATE decisions SET notification_status=? WHERE id=?", (notification_status, decision_id))

def _format_decision_dict(d: dict) -> dict:
    if d.get('adaptive_score') is None:
        d['adaptive_score'] = d.get('ass', 0.0)
    if d.get('emotion_probabilities') and isinstance(d['emotion_probabilities'], str):
        try:
            d['emotion_probabilities'] = json.loads(d['emotion_probabilities'])
        except Exception:
            d['emotion_probabilities'] = {}
    if d.get('explanation_json') and isinstance(d['explanation_json'], str):
        try:
            d['explanation'] = json.loads(d['explanation_json'])
        except Exception:
            d['explanation'] = None
    else:
        d['explanation'] = None
    if d.get('state_before') and isinstance(d['state_before'], str):
        try:
            d['state_before'] = json.loads(d['state_before'])
        except Exception:
            pass
    if d.get('state_after') and isinstance(d['state_after'], str):
        try:
            d['state_after'] = json.loads(d['state_after'])
        except Exception:
            pass
    return d

def recent_decisions(limit=50):
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute('SELECT * FROM decisions ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [_format_decision_dict(dict(r)) for r in rows]

def get_decisions_history(limit=100, offset=0, action=None, context=None, effectiveness=None, search=None):
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        query = "SELECT * FROM decisions WHERE 1=1"
        params = []
        if action and action != "ALL":
            query += " AND action = ?"
            params.append(action)
        if context and context != "ALL":
            query += " AND context = ?"
            params.append(context)
        if effectiveness and effectiveness != "ALL":
            if effectiveness == "PENDING":
                query += " AND (effectiveness IS NULL OR effectiveness = '')"
            else:
                query += " AND effectiveness = ?"
                params.append(effectiveness)
        if search:
            query += " AND (action LIKE ? OR reason LIKE ? OR emotion LIKE ? OR context LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s, s])
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = con.execute(query, tuple(params)).fetchall()
        return [_format_decision_dict(dict(r)) for r in rows]

def get_decision_by_id(decision_id: int):
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        row = con.execute('SELECT * FROM decisions WHERE id = ?', (decision_id,)).fetchone()
        if not row:
            return None
        return _format_decision_dict(dict(row))

# OS State Tracking & Transitions
def record_os_state_event(setting: str, state: str, source: str = "EAOS", adaptive_score: float = 0.0, reason: str = "", cycle_id: int = 1, duration_seconds: float = 0.0):
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB) as con:
        cur = con.execute('''INSERT INTO os_state_events(
            timestamp, setting, state, source, adaptive_score, reason, cycle_id, duration_seconds
        ) VALUES(?,?,?,?,?,?,?,?)''', (
            now, setting, state, source, adaptive_score, reason, cycle_id, duration_seconds
        ))
        return cur.lastrowid

def recent_os_state_events(limit=100):
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute('SELECT * FROM os_state_events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()]

def get_os_state_durations():
    """Calculates actual accumulated active durations for Dark Mode, Light Mode, and Focus/DND."""
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        events = [dict(r) for r in con.execute('SELECT * FROM os_state_events ORDER BY id ASC').fetchall()]

    dark_sec = 0.0
    light_sec = 0.0
    focus_sec = 0.0
    focus_activations = 0
    focus_deactivations = 0

    last_appearance_state = None
    last_appearance_time = None

    last_focus_state = None
    last_focus_time = None

    now = datetime.now(timezone.utc)

    for ev in events:
        try:
            ev_time = datetime.fromisoformat(ev['timestamp'])
        except Exception:
            continue

        setting = ev['setting']
        state = ev['state']

        if setting in ['APPEARANCE', 'DARK_MODE']:
            appearance_state = 'DARK' if state in ['DARK', 'ON'] else 'LIGHT'
            if last_appearance_state and last_appearance_time:
                dur = max(0.0, (ev_time - last_appearance_time).total_seconds())
                if last_appearance_state == 'DARK':
                    dark_sec += dur
                else:
                    light_sec += dur
            last_appearance_state = appearance_state
            last_appearance_time = ev_time

        elif setting == 'FOCUS_MODE' or setting == 'DND':
            if state == 'ON':
                focus_activations += 1
            elif state == 'OFF':
                focus_deactivations += 1

            if last_focus_state and last_focus_time:
                dur = max(0.0, (ev_time - last_focus_time).total_seconds())
                if last_focus_state == 'ON':
                    focus_sec += dur
            last_focus_state = state
            last_focus_time = ev_time

    # Tally up to current time
    if last_appearance_state and last_appearance_time:
        dur = max(0.0, (now - last_appearance_time).total_seconds())
        if last_appearance_state == 'DARK':
            dark_sec += dur
        else:
            light_sec += dur

    if last_focus_state == 'ON' and last_focus_time:
        focus_sec += max(0.0, (now - last_focus_time).total_seconds())

    total_monitored_sec = dark_sec + light_sec
    if total_monitored_sec <= 0:
        total_monitored_sec = 300.0  # Default minimum
        light_sec = 300.0

    return {
        'dark_mode_seconds': round(dark_sec, 1),
        'light_mode_seconds': round(light_sec, 1),
        'total_monitored_seconds': round(total_monitored_sec, 1),
        'focus_mode_seconds': round(focus_sec, 1),
        'focus_disabled_seconds': round(max(0.0, total_monitored_sec - focus_sec), 1),
        'focus_activations': focus_activations,
        'focus_deactivations': focus_deactivations,
        'current_appearance': last_appearance_state or 'LIGHT',
        'current_focus': last_focus_state or 'OFF'
    }

# Camera Sensing Tracking
def record_camera_session(start_time: str, end_time: str, duration_seconds: float, status: str):
    with sqlite3.connect(DB) as con:
        con.execute('''INSERT INTO camera_sessions(start_time, end_time, duration_seconds, status)
        VALUES(?,?,?,?)''', (start_time, end_time, duration_seconds, status))

def recent_camera_sessions(limit=50):
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute('SELECT * FROM camera_sessions ORDER BY id DESC LIMIT ?', (limit,)).fetchall()]

def get_camera_sensing_stats():
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute('SELECT * FROM camera_sessions ORDER BY id ASC').fetchall()]

    active_sec = sum(r['duration_seconds'] for r in rows if r['status'] == 'ACTIVE')
    count = len(rows)
    last_session = rows[-1]['start_time'] if rows else None

    return {
        'camera_on_seconds': round(active_sec, 1),
        'camera_sessions_count': count,
        'last_session_time': last_session,
        'sessions': rows[-20:]
    }

# Filtered Decisions by Date/Time Range
def get_decisions_by_period(period: str = 'all', limit=200) -> List[dict]:
    now = datetime.now(timezone.utc)
    cutoff = None
    if period == '1h':
        cutoff = now - timedelta(hours=1)
    elif period == '6h':
        cutoff = now - timedelta(hours=6)
    elif period == '24h':
        cutoff = now - timedelta(hours=24)
    elif period == 'today':
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == '7d':
        cutoff = now - timedelta(days=7)

    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        if cutoff:
            rows = con.execute('SELECT * FROM (SELECT * FROM decisions WHERE timestamp >= ? ORDER BY id DESC LIMIT ?) ORDER BY id ASC', (cutoff.isoformat(), limit)).fetchall()
        else:
            rows = con.execute('SELECT * FROM (SELECT * FROM decisions ORDER BY id DESC LIMIT ?) ORDER BY id ASC', (limit,)).fetchall()

    res = []
    for r in rows:
        d = dict(r)
        if d.get('adaptive_score') is None:
            d['adaptive_score'] = d.get('ass', 0.0)
        if d.get('emotion_probabilities') and isinstance(d['emotion_probabilities'], str):
            try:
                d['emotion_probabilities'] = json.loads(d['emotion_probabilities'])
            except Exception:
                d['emotion_probabilities'] = {}
        res.append(d)
    return res

def record_hourly_cycle(cycle_data: dict):
    with sqlite3.connect(DB) as con:
        cur = con.execute('''INSERT INTO hourly_cycles(
            cycle_number, cycle_id, start_time, end_time, input_start_time, input_end_time,
            adaptation_start_time, adaptation_end_time, phase, camera_used, samples_count,
            adaptive_score, action, selected_action, reason, status, os_action_status,
            emotion, workload, context
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
            cycle_data.get('cycle_number', cycle_data.get('cycle_id', 1)),
            cycle_data.get('cycle_id', cycle_data.get('cycle_number', 1)),
            cycle_data.get('start_time'),
            cycle_data.get('end_time'),
            cycle_data.get('input_start_time'),
            cycle_data.get('input_end_time'),
            cycle_data.get('adaptation_start_time'),
            cycle_data.get('adaptation_end_time'),
            cycle_data.get('phase', 'COMPLETED'),
            1 if cycle_data.get('camera_used') else 0,
            cycle_data.get('samples_count', 0),
            cycle_data.get('adaptive_score', 0.0),
            cycle_data.get('action', 'NO_ACTION'),
            cycle_data.get('selected_action', cycle_data.get('action', 'NO_ACTION')),
            cycle_data.get('reason', ''),
            cycle_data.get('status', 'completed'),
            cycle_data.get('os_action_status', cycle_data.get('status', 'completed')),
            cycle_data.get('emotion', 'Focused'),
            cycle_data.get('workload', 0.5),
            cycle_data.get('context', 'GENERAL_WORK')
        ))
        return cur.lastrowid

record_cycle = record_hourly_cycle

def update_cycle_phase(cycle_row_id: int, phase: str, end_time: str = None, status: str = None):
    with sqlite3.connect(DB) as con:
        if end_time and status:
            con.execute("UPDATE hourly_cycles SET phase=?, end_time=?, status=?, os_action_status=? WHERE id=?", (phase, end_time, status, status, cycle_row_id))
        elif end_time:
            con.execute("UPDATE hourly_cycles SET phase=?, end_time=? WHERE id=?", (phase, end_time, cycle_row_id))
        else:
            con.execute("UPDATE hourly_cycles SET phase=? WHERE id=?", (phase, cycle_row_id))

def recent_cycles(limit=50):
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute('SELECT * FROM hourly_cycles ORDER BY id DESC LIMIT ?', (limit,)).fetchall()]

def record_notification(notif: dict):
    with sqlite3.connect(DB) as con:
        cur = con.execute('''INSERT INTO notifications(
            decision_id, cycle_id, timestamp, title, message, action, adaptive_score, status
        ) VALUES(?,?,?,?,?,?,?,?)''', (
            notif.get('decision_id'),
            notif.get('cycle_id'),
            notif.get('timestamp'),
            notif.get('title'),
            notif.get('message'),
            notif.get('action'),
            notif.get('adaptive_score', 0.0),
            notif.get('status', 'delivered')
        ))
        return cur.lastrowid

def recent_notifications(limit=50):
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute('SELECT * FROM notifications ORDER BY id DESC LIMIT ?', (limit,)).fetchall()]

def add_feedback(decision_id, feedback, reward, timestamp):
    with sqlite3.connect(DB) as con:
        con.execute('INSERT INTO feedback_events(decision_id,timestamp,feedback,reward) VALUES(?,?,?,?)', (decision_id,timestamp,feedback,reward))

def feedback_stats():
    with sqlite3.connect(DB) as con:
        row = con.execute('SELECT COUNT(*), COALESCE(AVG(reward),0) FROM feedback_events').fetchone()
        return {'count': row[0], 'average_reward': row[1]}

def save_setting(key: str, val: any):
    with sqlite3.connect(DB) as con:
        con.execute('INSERT OR REPLACE INTO settings(key, value) VALUES(?,?)', (key, json.dumps(val)))

def load_settings():
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute('SELECT key, value FROM settings').fetchall()
        res = {}
        for r in rows:
            try:
                res[r['key']] = json.loads(r['value'])
            except Exception:
                res[r['key']] = r['value']
        return res

def save_signal_baseline(signal: str, mean: float, variance: float, observations: int):
    with sqlite3.connect(DB) as con:
        con.execute(
            'INSERT OR REPLACE INTO signal_baselines(signal, mean, variance, observations) VALUES(?,?,?,?)',
            (signal, mean, variance, observations)
        )

def load_signal_baselines() -> dict:
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute('SELECT signal, mean, variance, observations FROM signal_baselines').fetchall()
        return {r['signal']: {'mean': r['mean'], 'variance': r['variance'], 'observations': r['observations']} for r in rows}

def reset_signal_baselines():
    with sqlite3.connect(DB) as con:
        con.execute('DELETE FROM signal_baselines')

# Context Observations
def record_context_observation(active_app: str, context: str, confidence: float, session_duration: int = 0):
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB) as con:
        con.execute('''INSERT INTO context_observations(timestamp, active_app, context, confidence, session_duration)
        VALUES(?,?,?,?,?)''', (now, active_app, context, confidence, session_duration))

def get_context_history(limit: int = 50):
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute('SELECT * FROM context_observations ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [dict(r) for r in rows]

# Feedback & Effectiveness
def add_feedback_for_decision(decision_id: int, feedback_type: str, reward: float, action: str = "", adaptive_score: float = 0.0, context: str = ""):
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB) as con:
        con.execute('''INSERT INTO feedback_events(decision_id, timestamp, feedback, reward, action, adaptive_score, context)
        VALUES(?,?,?,?,?,?,?)''', (decision_id, now, feedback_type, reward, action, adaptive_score, context))
        con.execute('UPDATE decisions SET feedback = ? WHERE id = ?', (feedback_type, decision_id))

def record_adaptation_effectiveness(decision_id: int, action: str, pre_as: float, post_as: float, as_delta: float, pre_workload: float, post_workload: float, workload_delta: float, outcome: str):
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB) as con:
        con.execute('''INSERT INTO adaptation_effectiveness(
            decision_id, action, pre_as, post_as, as_delta, pre_workload, post_workload, workload_delta, outcome, timestamp
        ) VALUES(?,?,?,?,?,?,?,?,?,?)''', (
            decision_id, action, pre_as, post_as, as_delta, pre_workload, post_workload, workload_delta, outcome, now
        ))
        con.execute('''UPDATE decisions SET
            effectiveness = ?, observed_as_change = ?, observed_workload_change = ?,
            pre_as = ?, post_as = ?, pre_workload = ?, post_workload = ?
        WHERE id = ?''', (
            outcome, as_delta, workload_delta, pre_as, post_as, pre_workload, post_workload, decision_id
        ))

def get_effectiveness_stats():
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute('SELECT * FROM adaptation_effectiveness ORDER BY id DESC').fetchall()
    total = len(rows)
    if total == 0:
        return {
            'total_evaluated': 0,
            'positive_count': 0,
            'neutral_count': 0,
            'negative_count': 0,
            'positive_pct': 0.0,
            'neutral_pct': 0.0,
            'negative_pct': 0.0,
            'most_effective_adaptation': 'None observed yet',
            'least_effective_adaptation': 'None observed yet',
            'recent_events': []
        }
    pos = sum(1 for r in rows if r['outcome'] == 'POSITIVE')
    neu = sum(1 for r in rows if r['outcome'] == 'NEUTRAL')
    neg = sum(1 for r in rows if r['outcome'] == 'NEGATIVE')

    action_pos = {}
    action_total = {}
    for r in rows:
        act = r['action']
        action_total[act] = action_total.get(act, 0) + 1
        if r['outcome'] == 'POSITIVE':
            action_pos[act] = action_pos.get(act, 0) + 1

    most_eff = max(action_total.keys(), key=lambda a: action_pos.get(a, 0) / action_total[a]) if action_total else 'None'
    least_eff = min(action_total.keys(), key=lambda a: action_pos.get(a, 0) / action_total[a]) if action_total else 'None'

    return {
        'total_evaluated': total,
        'positive_count': pos,
        'neutral_count': neu,
        'negative_count': neg,
        'positive_pct': round((pos / total) * 100, 1),
        'neutral_pct': round((neu / total) * 100, 1),
        'negative_pct': round((neg / total) * 100, 1),
        'most_effective_adaptation': most_eff.replace('_', ' ').title(),
        'least_effective_adaptation': least_eff.replace('_', ' ').title(),
        'recent_events': [dict(r) for r in rows[:15]]
    }

# Policy Events & Learning
def record_policy_event(policy_name: str, action: str, reward: float, context: str = "", as_score: float = 0.0, details: str = ""):
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB) as con:
        con.execute('''INSERT INTO policy_events(timestamp, policy_name, action, reward, context, as_score, details)
        VALUES(?,?,?,?,?,?,?)''', (now, policy_name, action, reward, context, as_score, details))

def get_policy_stats():
    with sqlite3.connect(DB) as con:
        row = con.execute('SELECT COUNT(*), COALESCE(AVG(reward), 0) FROM policy_events').fetchone()
        return {'total_events': row[0], 'average_reward': round(row[1], 2)}

def get_all_policy_events():
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute('SELECT action, reward, context, as_score, details FROM policy_events ORDER BY id ASC').fetchall()
        return [dict(r) for r in rows]

# Privacy & Retention
def clear_decision_history():
    with sqlite3.connect(DB) as con:
        con.execute('DELETE FROM decisions')
        con.execute('DELETE FROM notifications')
        con.execute('DELETE FROM context_observations')
        con.execute('DELETE FROM adaptation_effectiveness')
        con.execute('DELETE FROM feedback_events')
        con.execute('DELETE FROM policy_events')

def cleanup_data_retention(retention_days: int):
    if retention_days <= 0:
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    with sqlite3.connect(DB) as con:
        con.execute('DELETE FROM decisions WHERE timestamp < ?', (cutoff,))
        con.execute('DELETE FROM notifications WHERE timestamp < ?', (cutoff,))
        con.execute('DELETE FROM context_observations WHERE timestamp < ?', (cutoff,))
        con.execute('DELETE FROM adaptation_effectiveness WHERE timestamp < ?', (cutoff,))
        con.execute('DELETE FROM feedback_events WHERE timestamp < ?', (cutoff,))
        con.execute('DELETE FROM policy_events WHERE timestamp < ?', (cutoff,))
        con.execute('DELETE FROM os_state_events WHERE timestamp < ?', (cutoff,))
        con.execute('DELETE FROM camera_sessions WHERE start_time < ?', (cutoff,))

# Automatically ensure database schema and tables exist on module import
init_db()
