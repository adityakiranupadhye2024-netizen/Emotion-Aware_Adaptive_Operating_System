import { LiveState } from '../types';
import { CameraBox } from '../components/CameraBox';

function formatTimer(seconds: number): string {
  if (isNaN(seconds) || seconds < 0) return '00:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

export default function AIState({ s }: { s: LiveState | null }) {
  if (!s) {
    return (
      <div className="empty-state-box">
        <div className="empty-icon">🧠</div>
        <h2>Waiting for Live AI State</h2>
        <p>Telemetry stream disconnected. Please verify the backend is running.</p>
      </div>
    );
  }

  const cycle = s.cycle || {
    remaining_seconds: 60,
    cycle_duration_seconds: 60,
    phase: 'INPUT_COLLECTION'
  };

  const asScore = s.adaptive_score?.score ?? s.ass?.score ?? 0.5;
  const asComponents = s.adaptive_score ?? s.ass ?? {
    emotion_component: 0.5,
    context_component: 0.5,
    workload_component: 0.5,
    personalization_component: 0.5,
    weights: { emotion: 0.35, context: 0.20, workload: 0.30, personalization: 0.15 }
  };

  const weights = asComponents.weights || {
    emotion: 0.35,
    context: 0.20,
    workload: 0.30,
    personalization: 0.15
  };

  const probabilities = s.emotion.probabilities || {
    Focused: 0.5,
    'Flow State': 0.1,
    Frustrated: 0.1,
    Fatigued: 0.1,
    Confused: 0.1,
    Relaxed: 0.1
  };

  const personalization = s.personalization || {
    status: 'CALIBRATING',
    samples: 0,
    calibration_cycles: 5,
    baseline: {},
    deviations: {}
  };

  const baselines = personalization.baseline || {};
  const devs = personalization.deviations || {};

  const normalWorkload = baselines.workload?.mean ?? 0.35;
  const normalTyping = baselines.typing_rate?.mean ?? 3.5;
  const normalJitter = baselines.mouse_jitter?.mean ?? 0.10;

  const currentWorkloadDev = devs.workload?.deviation ?? (s.workload.score - normalWorkload);
  const currentTypingDev = devs.typing_rate?.deviation ?? (s.inputs.keyboard.typing_rate - normalTyping);
  const currentJitterDev = devs.mouse_jitter?.deviation ?? ((s.inputs.mouse.jitter || 0) - normalJitter);

  return (
    <div>
      <div className="pagehead">
        <div>
          <h1>Multimodal AI State &amp; Personalization</h1>
          <p>Real-time fusion of behavioural signals, cognitive workload, and personal baseline deviation.</p>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <div className="timer-badge" style={{ background: 'rgba(56, 189, 248, 0.12)', border: '1px solid rgba(56, 189, 248, 0.3)', padding: '6px 14px', borderRadius: 99, color: '#38bdf8', fontSize: 13, fontWeight: 600 }}>
            ⏱ NEXT ASSESSMENT: {formatTimer(cycle.remaining_seconds)}
          </div>
        </div>
      </div>

      {/* Real-time AI Vision & Facial Emotion Cam Box */}
      <CameraBox
        emotion={s?.emotion}
        cameraState={s?.inputs?.camera}
        cycle={s?.cycle}
      />

      {/* Personalization Section */}
      <section className="card" style={{ marginBottom: 20, borderColor: 'rgba(139, 92, 246, 0.35)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div>
            <span className="section-eyebrow">INDIVIDUAL USER LEARNING</span>
            <h2>Personal Baseline &amp; Deviation</h2>
          </div>
          <div style={{ textAlign: 'right' }}>
            <span className={`status-pill ${personalization.status === 'ACTIVE' ? 'ok' : 'subtle'}`} style={{ fontSize: 12, padding: '4px 10px' }}>
              ● STATUS: {personalization.status}
            </span>
            <small style={{ display: 'block', color: 'var(--text-muted)', marginTop: 4 }}>
              Baseline Samples: <b>{personalization.samples}</b> {personalization.status === 'CALIBRATING' ? `(Target: ${personalization.calibration_cycles})` : 'cycles'}
            </small>
          </div>
        </div>

        <p style={{ color: 'var(--text-muted)', fontSize: 13, lineHeight: 1.6, marginTop: 0, marginBottom: 16 }}>
          EAOS continuously learns your normal typing cadence, workload, and mouse dynamics over time using Exponentially Weighted Moving Averages (EWMA). The Decision Engine evaluates whether your current state is unusually elevated relative to your individual baseline.
        </p>

        <div className="twocol">
          <div className="card" style={{ background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,255,255,0.06)' }}>
            <h3 style={{ fontSize: 14, margin: '0 0 10px', color: '#93c5fd' }}>Learned Personal Baseline (Normal)</h3>
            <div className="kv">
              <span>Normal Workload:</span>
              <b>{normalWorkload.toFixed(2)}</b>
              <span>Normal Typing Cadence:</span>
              <b>{normalTyping.toFixed(1)} keys/sec</b>
              <span>Normal Mouse Jitter:</span>
              <b>{normalJitter.toFixed(3)}</b>
            </div>
          </div>

          <div className="card" style={{ background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,255,255,0.06)' }}>
            <h3 style={{ fontSize: 14, margin: '0 0 10px', color: '#38bdf8' }}>Current 5-Minute Deviation</h3>
            <div className="kv">
              <span>Workload Deviation:</span>
              <b style={{ color: currentWorkloadDev > 0.15 ? '#f87171' : (currentWorkloadDev < -0.1 ? '#34d399' : '#fff') }}>
                {currentWorkloadDev >= 0 ? `+${currentWorkloadDev.toFixed(2)}` : currentWorkloadDev.toFixed(2)}
              </b>
              <span>Typing Deviation:</span>
              <b>{currentTypingDev >= 0 ? `+${currentTypingDev.toFixed(1)}` : currentTypingDev.toFixed(1)} keys/s</b>
              <span>Mouse Jitter Deviation:</span>
              <b>{currentJitterDev >= 0 ? `+${currentJitterDev.toFixed(3)}` : currentJitterDev.toFixed(3)}</b>
            </div>
          </div>
        </div>
      </section>

      <div className="twocol">
        {/* Emotion Distribution */}
        <section className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h2>Multimodal Emotion Distribution</h2>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Dominant: <b style={{ color: '#38bdf8' }}>{s.emotion.dominant}</b> ({Math.round(s.emotion.confidence * 100)}%)
            </span>
          </div>
          {Object.entries(probabilities).map(([emotionName, val]) => (
            <div className="barrow" key={emotionName}>
              <span>{emotionName}</span>
              <div className="bar">
                <i style={{ width: `${Math.min(100, Math.max(0, Number(val) * 100))}%` }} />
              </div>
              <b>{(Number(val) * 100).toFixed(0)}%</b>
            </div>
          ))}
        </section>

        {/* Adaptive Score Breakdown */}
        <section className="card">
          <h2>Adaptive Score (AS) Breakdown</h2>
          <div className="bigscore">
            {asScore.toFixed(2)}
            <small> / 1.00</small>
          </div>
          <div className="kv">
            <span>Emotion Component ({Math.round((weights.emotion || 0.35) * 100)}%)</span>
            <b>{asComponents.emotion_component.toFixed(2)}</b>
            <span>Cognitive Workload ({Math.round((weights.workload || 0.30) * 100)}%)</span>
            <b>{asComponents.workload_component.toFixed(2)}</b>
            <span>Context Alignment ({Math.round((weights.context || 0.20) * 100)}%)</span>
            <b>{asComponents.context_component.toFixed(2)}</b>
            <span>Personalization Deviation ({Math.round((weights.personalization || 0.15) * 100)}%)</span>
            <b>{asComponents.personalization_component.toFixed(2)}</b>
          </div>
        </section>
      </div>

      <div className="twocol">
        {/* Behavioral Telemetry */}
        <section className="card">
          <h2>Observed Behavioral Telemetry</h2>
          <div className="kv">
            <span>Typing Speed (Cadence)</span>
            <b>{s.inputs.keyboard.typing_rate.toFixed(2)} keys/sec</b>
            <span>Inter-Key Interval</span>
            <b>{s.inputs.keyboard.avg_inter_key_interval.toFixed(3)} s</b>
            <span>Backspace Correction Rate</span>
            <b>{(s.inputs.keyboard.backspace_rate * 100).toFixed(1)}%</b>
            <span>Mouse Jitter / Reversals</span>
            <b>{((s.inputs.mouse.jitter || 0) * 100).toFixed(1)}%</b>
            <span>Mouse Clicks</span>
            <b>{s.inputs.mouse.clicks} total</b>
            <span>Mouse State</span>
            <b>{s.inputs.mouse.idle ? 'Idle' : 'Active Movement'}</b>
          </div>
        </section>

        {/* Cognitive Workload & Context */}
        <section className="card">
          <h2>Cognitive Workload &amp; Context</h2>
          <div className="bigscore">
            {(s.workload.score * 100).toFixed(0)}
            <small> / 100</small>
          </div>
          <p style={{ marginTop: 2, marginBottom: 14, color: 'var(--text-muted)', fontSize: 13 }}>
            Assessed Level: <strong style={{ color: '#fff' }}>{s.workload.level}</strong>
          </p>
          <div className="kv">
            <span>Active Frontmost App</span>
            <b>{s.context?.active_app || 'System'}</b>
            <span>Activity Category</span>
            <b>{s.context?.activity || 'GENERAL_WORK'}</b>
            <span>Session Duration</span>
            <b>{Math.floor((s.context?.session_duration || 0) / 60)} min</b>
            <span>Window Switch Rate</span>
            <b>{(Number((s.context as any)?.app_switch_rate || 0)).toFixed(1)} / min</b>
            <span>Assessment Cycle</span>
            <b>#{cycle.cycle_id || 1} (1-minute cycle)</b>
          </div>
        </section>
      </div>
    </div>
  );
}
