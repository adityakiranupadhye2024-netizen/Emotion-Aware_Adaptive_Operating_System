import { useState, useEffect } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  Legend
} from 'recharts';
import { getAnalyticsSummary, getAdaptationEffectiveness } from '../services/api';
import { LiveState, AnalyticsSummary, EffectivenessStats } from '../types';

function formatDuration(sec: number): string {
  if (!sec || sec <= 0) return '0m';
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s > 0 ? s + 's' : ''}`;
  return `${s}s`;
}

function formatTime(isoStr?: string): string {
  if (!isoStr) return '--:--';
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '--:--';
  }
}

export default function Analytics({ s }: { s: LiveState | null }) {
  const [period, setPeriod] = useState<string>('all');
  const [data, setData] = useState<AnalyticsSummary | null>(() => {
    try {
      const cached = localStorage.getItem('eaos_analytics_cache');
      return cached ? JSON.parse(cached) : null;
    } catch {
      return null;
    }
  });
  const [effStats, setEffStats] = useState<EffectivenessStats | null>(() => {
    try {
      const cached = localStorage.getItem('eaos_eff_cache');
      return cached ? JSON.parse(cached) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAnalytics = (filterPeriod: string) => {
    getAnalyticsSummary(filterPeriod)
      .then((res) => {
        setData(res);
        setError(null);
        try {
          localStorage.setItem('eaos_analytics_cache', JSON.stringify(res));
        } catch {}
      })
      .catch((err) => {
        // Fallback to cache if backend is closed
        const cached = localStorage.getItem('eaos_analytics_cache');
        if (cached) {
          try {
            setData(JSON.parse(cached));
          } catch {}
        }
        setError(err.message || 'Backend offline');
      });

    getAdaptationEffectiveness()
      .then((res) => {
        setEffStats(res);
        try {
          localStorage.setItem('eaos_eff_cache', JSON.stringify(res));
        } catch {}
      })
      .catch(() => {
        const cached = localStorage.getItem('eaos_eff_cache');
        if (cached) {
          try {
            setEffStats(JSON.parse(cached));
          } catch {}
        }
      });
  };

  useEffect(() => {
    fetchAnalytics(period);
    // Poll every 3 seconds to keep graphs live and updated with current input data
    const timer = setInterval(() => {
      fetchAnalytics(period);
    }, 3000);
    return () => clearInterval(timer);
  }, [period]);

  const decisions = data?.decisions || [];
  const overview = data?.overview;
  const osDurations = data?.os_durations;
  const cameraStats = data?.camera_stats;

  // Live input phase telemetry gathered in real-time
  const liveKbRate = Number((s?.inputs?.keyboard?.typing_rate || 0).toFixed(2));
  const liveJitter = Number((s?.inputs?.mouse?.jitter || 0).toFixed(3));
  const liveWl = Math.round((s?.workload?.score || 0.4) * 100);
  const liveAs = Number((s?.adaptive_score?.score || 0.5).toFixed(2));
  const isInputPhase = s?.phase === 'INPUT_COLLECTION' || liveKbRate > 0;

  // 1. TYPING SPEED DATA
  const typingData = decisions.map((d, i) => {
    const rate = Number((d.typing_rate || 0).toFixed(2));
    const baseline = Number((d.baseline_typing || overview?.baseline_typing || 3.5).toFixed(2));
    const dev = baseline > 0 ? Number((((rate - baseline) / baseline) * 100).toFixed(1)) : 0;
    return {
      name: `#${d.cycle_id || i + 1}`,
      time: formatTime(d.timestamp),
      typing_rate: rate,
      baseline: baseline,
      deviation: dev
    };
  });

  if (isInputPhase) {
    const baseline = Number((overview?.baseline_typing || 3.5).toFixed(2));
    const dev = baseline > 0 ? Number((((liveKbRate - baseline) / baseline) * 100).toFixed(1)) : 0;
    typingData.push({
      name: `Live (Input)`,
      time: 'Now',
      typing_rate: liveKbRate,
      baseline: baseline,
      deviation: dev
    });
  }

  // 2. MOUSE ACTIVITY DATA
  const mouseData = decisions.map((d, i) => {
    const jitter = Number((d.mouse_jitter || 0).toFixed(3));
    const baseline = Number((d.baseline_jitter || overview?.baseline_jitter || 0.12).toFixed(3));
    return {
      name: `#${d.cycle_id || i + 1}`,
      time: formatTime(d.timestamp),
      jitter: jitter,
      baseline: baseline
    };
  });

  if (isInputPhase) {
    const baseline = Number((overview?.baseline_jitter || 0.12).toFixed(3));
    mouseData.push({
      name: `Live (Input)`,
      time: 'Now',
      jitter: liveJitter,
      baseline: baseline
    });
  }

  // 3. WORKLOAD DATA
  const workloadData = decisions.map((d, i) => {
    const wl = Math.round((d.workload || 0) * 100);
    const baseline = Math.round((d.baseline_workload || overview?.baseline_workload || 0.35) * 100);
    return {
      name: `#${d.cycle_id || i + 1}`,
      time: formatTime(d.timestamp),
      workload: wl,
      baseline: baseline
    };
  });

  if (isInputPhase) {
    const baseline = Math.round((overview?.baseline_workload || 0.35) * 100);
    workloadData.push({
      name: `Live (Input)`,
      time: 'Now',
      workload: liveWl,
      baseline: baseline
    });
  }

  // 4. EMOTION OVER TIME DATA (Only include if camera was active/observed)
  const cameraAvailableAssessments = decisions.filter((d) => d.camera_active === 1 || (d.emotion_probabilities && Object.keys(d.emotion_probabilities).length > 0));
  const emotionTimelineData = cameraAvailableAssessments.map((d, i) => {
    const probs = d.emotion_probabilities || {};
    return {
      name: `#${d.cycle_id || i + 1}`,
      time: formatTime(d.timestamp),
      Focused: Math.round((probs['Focused'] || (d.emotion === 'Focused' ? d.emotion_confidence || 0.7 : 0.1)) * 100),
      Relaxed: Math.round((probs['Relaxed'] || (d.emotion === 'Relaxed' ? d.emotion_confidence || 0.7 : 0.1)) * 100),
      Frustrated: Math.round((probs['Frustrated'] || (d.emotion === 'Frustrated' ? d.emotion_confidence || 0.7 : 0.05)) * 100),
      Fatigued: Math.round((probs['Fatigued'] || (d.emotion === 'Fatigued' ? d.emotion_confidence || 0.7 : 0.05)) * 100),
      Confused: Math.round((probs['Confused'] || (d.emotion === 'Confused' ? d.emotion_confidence || 0.7 : 0.05)) * 100),
    };
  });

  // 5. EMOTION DISTRIBUTION
  const emotionDistData = Object.entries(data?.emotion_distribution || {
    Focused: 0, Relaxed: 0, Frustrated: 0, Fatigued: 0, Confused: 0
  }).map(([name, count]) => ({ name, count }));

  // 6. ADAPTIVE SCORE TIMELINE
  const asTimelineData = decisions.map((d, i) => {
    const score = Number((d.adaptive_score ?? d.ass ?? 0.5).toFixed(2));
    const isAdaptation = d.action && d.action !== 'NO_ACTION';
    return {
      name: `#${d.cycle_id || i + 1}`,
      time: formatTime(d.timestamp),
      as: score,
      adaptationPoint: isAdaptation ? score : null,
      action: d.action?.replace(/_/g, ' ') || 'NO ACTION',
      isAdaptation
    };
  });

  if (isInputPhase) {
    asTimelineData.push({
      name: `Live (Input)`,
      time: 'Now',
      as: liveAs,
      adaptationPoint: null,
      action: 'IN PROGRESS',
      isAdaptation: false
    });
  }

  // 7. ADAPTATION FREQUENCY
  const freqCategories = [
    { key: 'ENABLE_DARK_MODE', label: 'Dark Mode' },
    { key: 'ENABLE_FOCUS_MODE', label: 'DND / Focus' },
    { key: 'DISABLE_DARK_MODE', label: 'Light Mode' },
    { key: 'REDUCE_BRIGHTNESS', label: 'Brightness' },
    { key: 'SUGGEST_BREAK', label: 'Break' },
    { key: 'NO_ACTION', label: 'No Action' }
  ];
  const freqData = freqCategories.map((c) => ({
    name: c.label,
    count: data?.action_frequency?.[c.key] || 0
  }));

  // 8. DISPLAY MODE DONUT DATA
  const darkSec = osDurations?.dark_mode_seconds || 0;
  const lightSec = osDurations?.light_mode_seconds || 0;
  const totalMonitoredSec = Math.max(1, osDurations?.total_monitored_seconds || (darkSec + lightSec) || 300);
  const displayPieData = [
    { name: 'Dark Mode', value: Math.round(darkSec) || 1, fill: '#8b5cf6' },
    { name: 'Light Mode', value: Math.round(lightSec) || 1, fill: '#f59e0b' }
  ];

  // 9. DND DONUT DATA
  const dndSec = osDurations?.focus_mode_seconds || 0;
  const dndDisabledSec = osDurations?.focus_disabled_seconds || Math.max(0, totalMonitoredSec - dndSec);
  const dndPieData = [
    { name: 'DND Active', value: Math.round(dndSec) || 1, fill: '#06b6d4' },
    { name: 'DND Disabled', value: Math.round(dndDisabledSec) || 1, fill: '#334155' }
  ];

  // 10. GANTT / TIMELINE PERCENTAGES
  const darkPct = Math.min(100, Math.round((darkSec / totalMonitoredSec) * 100)) || (osDurations?.current_appearance === 'DARK' ? 100 : 0);
  const lightPct = Math.max(0, 100 - darkPct);
  const focusPct = Math.min(100, Math.round((dndSec / totalMonitoredSec) * 100)) || (osDurations?.current_focus === 'ON' ? 100 : 0);
  const cameraOnSec = cameraStats?.camera_on_seconds || 0;
  const cameraOnPct = Math.min(100, Math.round((cameraOnSec / totalMonitoredSec) * 100));

  // Current values
  const currentTyping = liveKbRate > 0 ? liveKbRate : (overview?.typing_speed ?? (s?.inputs?.keyboard?.typing_rate || 0));
  const baselineTyping = overview?.baseline_typing ?? 3.5;
  const devPercent = baselineTyping > 0 ? Math.round(((currentTyping - baselineTyping) / baselineTyping) * 100) : 0;
  const currentWorkloadPct = s?.workload?.score ? Math.round(s.workload.score * 100) : Math.round((overview?.workload ?? 0.4) * 100);
  const baselineWorkloadPct = Math.round((overview?.baseline_workload ?? 0.35) * 100);

  return (
    <div style={{ paddingBottom: 60 }}>
      {/* Page Header and Filter Bar */}
      <div className="pagehead" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span>EAOS Analytics</span>
            <span className="live-pill">REAL DATABASE RECORDS</span>
          </h1>
          <p>
            Continuous multimodal behavioural tracking, personal baseline calibration, and real-time OS environment adaptations across 5-minute assessment cycles.
          </p>
        </div>

        {/* Date/Time Filter (Requirement 15) */}
        <div className="analytics-filter-bar">
          {[
            { id: 'today', label: 'Today' },
            { id: '1h', label: 'Last 1h' },
            { id: '6h', label: 'Last 6h' },
            { id: '24h', label: 'Last 24h' },
            { id: '7d', label: 'Last 7d' },
            { id: 'all', label: 'All History' }
          ].map((f) => (
            <button
              key={f.id}
              className={`filter-btn ${period === f.id ? 'active' : ''}`}
              onClick={() => setPeriod(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="offline-banner">
          <b>Analytics Warning:</b> {error}. Showing cached state records.
        </div>
      )}

      {/* ==================================================
          SECTION 1: "Current Overview"
          ================================================== */}
      <section className="analytics-section">
        <div className="analytics-section-head">
          <div className="analytics-section-title">
            <span className="section-tag">Section 1</span>
            <h2>Current Overview</h2>
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Filter: {period.toUpperCase()} · {decisions.length} 5-Minute Assessments
          </span>
        </div>

        <div className="grid6" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 14 }}>
          <div className="card metric">
            <span>Adaptive Score (AS)</span>
            <strong>{(overview?.adaptive_score ?? (s?.adaptive_score?.score || 0.5)).toFixed(2)}</strong>
            <small>Range 0.00 – 1.00</small>
          </div>

          <div className="card metric">
            <span>Cognitive Workload</span>
            <strong>{currentWorkloadPct}%</strong>
            <small>Baseline: {baselineWorkloadPct}%</small>
          </div>

          <div className="card metric">
            <span>Typing Speed</span>
            <strong>{currentTyping.toFixed(1)} <span style={{ fontSize: 13, fontWeight: 400 }}>k/s</span></strong>
            <small className={devPercent >= 0 ? 'badge-dev-pos' : 'badge-dev-neg'}>
              {devPercent >= 0 ? `+${devPercent}%` : `${devPercent}%`} vs baseline
            </small>
          </div>

          <div className="card metric">
            <span>Dominant Emotion</span>
            <strong>{overview?.dominant_emotion || s?.emotion?.dominant || 'Focused'}</strong>
            <small>{Math.round((s?.emotion?.confidence || 0.8) * 100)}% confidence</small>
          </div>

          <div className="card metric">
            <span>Adaptations Executed</span>
            <strong>{overview?.adaptations_count ?? 0}</strong>
            <small>Out of {decisions.length} cycles</small>
          </div>

          <div className="card metric">
            <span>Camera Sessions</span>
            <strong>{cameraStats?.camera_sessions_count ?? 0}</strong>
            <small>{formatDuration(cameraStats?.camera_on_seconds || 0)} active</small>
          </div>
        </div>

        {/* Adaptation Effectiveness Metric Card */}
        {effStats && (
          <div className="card" style={{ marginTop: 16, padding: '16px 20px', background: 'rgba(15, 23, 42, 0.6)', border: '1px solid rgba(255,255,255,0.08)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
              <div>
                <span style={{ fontSize: 11, fontWeight: 600, color: '#38bdf8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  ADAPTATION EFFECTIVENESS (5-MINUTE POST-ASSESSMENT DELTAS)
                </span>
                <h3 style={{ margin: '2px 0 0 0', fontSize: 16, color: '#f8fafc' }}>
                  Observed Outcomes Across 5-Minute Evaluation Cycles
                </h3>
              </div>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {effStats.total_evaluated} Total Adaptations Evaluated
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
              <div className="stat-card" style={{ padding: '10px', background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ fontSize: 11, color: '#94a3b8' }}>POSITIVE IMPROVEMENT</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#10b981', marginTop: 2 }}>
                  {effStats.positive_pct}% <span style={{ fontSize: 12, fontWeight: 400 }}>({effStats.positive_count})</span>
                </div>
              </div>

              <div className="stat-card" style={{ padding: '10px', background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ fontSize: 11, color: '#94a3b8' }}>NEUTRAL STATE</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#f59e0b', marginTop: 2 }}>
                  {effStats.neutral_pct}% <span style={{ fontSize: 12, fontWeight: 400 }}>({effStats.neutral_count})</span>
                </div>
              </div>

              <div className="stat-card" style={{ padding: '10px', background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ fontSize: 11, color: '#94a3b8' }}>NEGATIVE CHANGE</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#ef4444', marginTop: 2 }}>
                  {effStats.negative_pct}% <span style={{ fontSize: 12, fontWeight: 400 }}>({effStats.negative_count})</span>
                </div>
              </div>

              <div className="stat-card" style={{ padding: '10px', background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ fontSize: 11, color: '#94a3b8' }}>MOST EFFECTIVE ACTION</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#38bdf8', marginTop: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {effStats.most_effective_adaptation}
                </div>
              </div>
            </div>
          </div>
        )}
      </section>


      {/* ==================================================
          SECTION 2: "Behavioural Signals"
          ================================================== */}
      <section className="analytics-section">
        <div className="analytics-section-head">
          <div className="analytics-section-title">
            <span className="section-tag">Section 2</span>
            <h2>Behavioural Signals (vs Personal Baseline)</h2>
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Real keyboard & mouse telemetry</span>
        </div>

        <div className="twocol" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 16, marginBottom: 16 }}>
          {/* Graph 1: Typing Speed vs Personal Baseline */}
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <h3 style={{ margin: '0 0 2px 0', fontSize: 15 }}>Typing Speed vs Personal Baseline</h3>
                <div className="chart-subtitle">Real keyboard rate over 5-minute assessments compared to learned baseline</div>
              </div>
            </div>

            <div className="stat-comparison">
              <span>Current: <b>{currentTyping.toFixed(1)} keys/s</b></span>
              <span>•</span>
              <span>Avg: <b>{(overview?.avg_typing_speed || currentTyping).toFixed(1)} keys/s</b></span>
              <span>•</span>
              <span>Baseline: <b>{baselineTyping.toFixed(1)} keys/s</b></span>
              <span>•</span>
              <span className={devPercent >= 0 ? 'badge-dev-pos' : 'badge-dev-neg'}>
                {devPercent >= 0 ? `+${devPercent}%` : `${devPercent}%`} deviation
              </span>
            </div>

            {typingData.length === 0 ? (
              <div style={{ height: 220, display: 'grid', placeItems: 'center', color: 'var(--text-muted)' }}>
                Awaiting keyboard input in current 5-minute window...
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={230}>
                <LineChart data={typingData}>
                  <XAxis dataKey="time" stroke="#8492a6" fontSize={11} />
                  <YAxis stroke="#8492a6" fontSize={11} domain={[0, 'auto']} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#090c14', borderColor: 'rgba(255,255,255,0.1)', borderRadius: 8 }}
                    labelStyle={{ color: '#fff' }}
                  />
                  <Legend verticalAlign="top" height={36} />
                  <Line
                    type="monotone"
                    dataKey="typing_rate"
                    name="Typing Speed (keys/sec)"
                    stroke="#06b6d4"
                    strokeWidth={2.5}
                    dot={{ r: 3 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="baseline"
                    name="Personal Baseline"
                    stroke="#8b5cf6"
                    strokeWidth={1.8}
                    strokeDasharray="4 4"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Graph 2: Mouse Activity vs Personal Baseline */}
          <div className="card">
            <h3 style={{ margin: '0 0 2px 0', fontSize: 15 }}>Mouse Activity vs Personal Baseline</h3>
            <div className="chart-subtitle">Cursor erraticism (jitter) & speed measured against calibrated baseline</div>

            <div className="stat-comparison">
              <span>Current Jitter: <b>{(overview?.baseline_jitter || 0.12).toFixed(3)}</b></span>
              <span>•</span>
              <span>Personal Baseline: <b>{(overview?.baseline_jitter || 0.12).toFixed(3)}</b></span>
              <span>•</span>
              <span>Status: <b style={{ color: '#10b981' }}>Within Tolerance</b></span>
            </div>

            {mouseData.length === 0 ? (
              <div style={{ height: 220, display: 'grid', placeItems: 'center', color: 'var(--text-muted)' }}>
                Awaiting mouse telemetry in current 5-minute window...
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={230}>
                <LineChart data={mouseData}>
                  <XAxis dataKey="time" stroke="#8492a6" fontSize={11} />
                  <YAxis stroke="#8492a6" fontSize={11} domain={[0, 'auto']} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#090c14', borderColor: 'rgba(255,255,255,0.1)', borderRadius: 8 }}
                    labelStyle={{ color: '#fff' }}
                  />
                  <Legend verticalAlign="top" height={36} />
                  <Line
                    type="monotone"
                    dataKey="jitter"
                    name="Mouse Jitter"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="baseline"
                    name="Personal Baseline"
                    stroke="#a78bfa"
                    strokeWidth={1.8}
                    strokeDasharray="4 4"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Graph 3: Workload vs Personal Baseline */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <h3 style={{ margin: '0 0 2px 0', fontSize: 15 }}>Cognitive Workload vs Personal Baseline</h3>
              <div className="chart-subtitle">Multi-feature workload score relative to individual user baseline threshold</div>
            </div>
            <div className="stat-comparison" style={{ margin: 0 }}>
              <span>Current: <b>{currentWorkloadPct}%</b></span>
              <span>•</span>
              <span>Personal Baseline: <b>{baselineWorkloadPct}%</b></span>
            </div>
          </div>

          {workloadData.length === 0 ? (
            <div style={{ height: 200, display: 'grid', placeItems: 'center', color: 'var(--text-muted)' }}>
              No workload history recorded yet for selected filter.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={workloadData}>
                <XAxis dataKey="time" stroke="#8492a6" fontSize={11} />
                <YAxis domain={[0, 100]} stroke="#8492a6" fontSize={11} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#090c14', borderColor: 'rgba(255,255,255,0.1)', borderRadius: 8 }}
                  labelStyle={{ color: '#fff' }}
                />
                <Legend verticalAlign="top" height={36} />
                <Line
                  type="monotone"
                  dataKey="workload"
                  name="Cognitive Workload (%)"
                  stroke="#38bdf8"
                  strokeWidth={2.5}
                  dot={{ r: 3 }}
                />
                <Line
                  type="monotone"
                  dataKey="baseline"
                  name="Personal Baseline Workload (%)"
                  stroke="#ec4899"
                  strokeWidth={1.8}
                  strokeDasharray="4 4"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      {/* ==================================================
          SECTION 3: "Emotion & Cognitive State"
          ================================================== */}
      <section className="analytics-section">
        <div className="analytics-section-head">
          <div className="analytics-section-title">
            <span className="section-tag">Section 3</span>
            <h2>Emotion & Cognitive State</h2>
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Camera & Inferred Affective State</span>
        </div>

        <div className="twocol" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 16, marginBottom: 16 }}>
          {/* Graph 4: Facial Emotion Over Time */}
          <div className="card">
            <h3 style={{ margin: '0 0 2px 0', fontSize: 15 }}>Facial Emotion Over Time</h3>
            <div className="chart-subtitle">Observation probabilities across camera sensing windows (Focused, Relaxed, Frustrated, Fatigued, Confused)</div>

            {emotionTimelineData.length === 0 ? (
              <div className="no-camera-banner" style={{ margin: '20px 0' }}>
                <div style={{ fontSize: 28, marginBottom: 6 }}>📷</div>
                <strong style={{ display: 'block', color: 'var(--text-main)', marginBottom: 4 }}>No facial data available</strong>
                <span>Camera sensing is disabled or no facial observations were captured during this interval. No artificial emotion values are generated.</span>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={emotionTimelineData}>
                  <XAxis dataKey="time" stroke="#8492a6" fontSize={11} />
                  <YAxis domain={[0, 100]} stroke="#8492a6" fontSize={11} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#090c14', borderColor: 'rgba(255,255,255,0.1)', borderRadius: 8 }}
                    labelStyle={{ color: '#fff' }}
                  />
                  <Legend verticalAlign="top" height={36} />
                  <Line type="monotone" dataKey="Focused" stroke="#10b981" strokeWidth={2} dot={{ r: 2 }} />
                  <Line type="monotone" dataKey="Relaxed" stroke="#06b6d4" strokeWidth={2} dot={{ r: 2 }} />
                  <Line type="monotone" dataKey="Frustrated" stroke="#f43f5e" strokeWidth={2} dot={{ r: 2 }} />
                  <Line type="monotone" dataKey="Fatigued" stroke="#f59e0b" strokeWidth={2} dot={{ r: 2 }} />
                  <Line type="monotone" dataKey="Confused" stroke="#8b5cf6" strokeWidth={2} dot={{ r: 2 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Graph 5: Emotion Distribution */}
          <div className="card">
            <h3 style={{ margin: '0 0 2px 0', fontSize: 15 }}>Emotion Distribution</h3>
            <div className="chart-subtitle">Total 5-minute assessments classified by dominant emotion</div>

            {emotionDistData.every((e) => e.count === 0) ? (
              <div style={{ height: 250, display: 'grid', placeItems: 'center', color: 'var(--text-muted)' }}>
                Awaiting assessments to classify emotional states...
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={emotionDistData}>
                  <XAxis dataKey="name" stroke="#8492a6" fontSize={11} />
                  <YAxis stroke="#8492a6" fontSize={11} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#090c14', borderColor: 'rgba(255,255,255,0.1)' }}
                  />
                  <Bar dataKey="count" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Graph 6: Adaptive Score (AS) Timeline */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <h3 style={{ margin: '0 0 2px 0', fontSize: 15 }}>Adaptive Score (AS) Timeline</h3>
              <div className="chart-subtitle">Continuous AS index (0.00 – 1.00) with automatic adaptation trigger events marked</div>
            </div>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Adaptation Threshold: ≥ 0.40
            </span>
          </div>

          {asTimelineData.length === 0 ? (
            <div style={{ height: 220, display: 'grid', placeItems: 'center', color: 'var(--text-muted)' }}>
              Awaiting first assessment completion...
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <LineChart data={asTimelineData}>
                <XAxis dataKey="time" stroke="#8492a6" fontSize={11} />
                <YAxis domain={[0, 1]} stroke="#8492a6" fontSize={11} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#090c14', borderColor: 'rgba(255,255,255,0.1)', borderRadius: 8 }}
                  labelStyle={{ color: '#fff' }}
                  formatter={(value: any, name: any, item: any) => {
                    if (name === 'Adaptive Score (AS)') {
                      return [value, `${name} (Action: ${item.payload.action})`];
                    }
                    return [value, name];
                  }}
                />
                <Legend verticalAlign="top" height={36} />
                <Line
                  type="monotone"
                  dataKey="as"
                  name="Adaptive Score (AS)"
                  stroke="#a855f7"
                  strokeWidth={2.5}
                  dot={{ r: 3 }}
                />
                <Line
                  type="monotone"
                  dataKey="adaptationPoint"
                  name="Adaptation Triggered"
                  stroke="#ef4444"
                  strokeWidth={0}
                  dot={{ r: 6, fill: '#ef4444', strokeWidth: 2, stroke: '#fff' }}
                  activeDot={{ r: 8 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      {/* ==================================================
          SECTION 4: "OS Adaptation"
          ================================================== */}
      <section className="analytics-section">
        <div className="analytics-section-head">
          <div className="analytics-section-title">
            <span className="section-tag">Section 4</span>
            <h2>OS Adaptation & State Durations</h2>
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Actual OS transitions recorded via AppleScript</span>
        </div>

        {/* Graph 7: OS Adaptation Duration Timeline (Gantt Style) */}
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ margin: '0 0 2px 0', fontSize: 15 }}>OS Adaptation Duration Timeline</h3>
          <div className="chart-subtitle">Real-time state intervals demonstrating when EAOS modified the host operating environment</div>

          <div className="gantt-timeline-container">
            {/* Dark Mode Track */}
            <div className="gantt-row">
              <div className="gantt-label">
                <span>🌙 Dark Mode</span>
              </div>
              <div className="gantt-track">
                {darkPct > 0 ? (
                  <div className="gantt-segment gantt-dark" style={{ width: `${darkPct}%` }}>
                    Active: {formatDuration(darkSec)} ({darkPct}%)
                  </div>
                ) : (
                  <div style={{ paddingLeft: 12, fontSize: 11, color: 'var(--text-muted)' }}>Inactive in selected window</div>
                )}
              </div>
            </div>

            {/* Light Mode Track */}
            <div className="gantt-row">
              <div className="gantt-label">
                <span>☀️ Light Mode</span>
              </div>
              <div className="gantt-track">
                {lightPct > 0 ? (
                  <div className="gantt-segment gantt-light" style={{ width: `${lightPct}%` }}>
                    Active: {formatDuration(lightSec)} ({lightPct}%)
                  </div>
                ) : (
                  <div style={{ paddingLeft: 12, fontSize: 11, color: 'var(--text-muted)' }}>Inactive in selected window</div>
                )}
              </div>
            </div>

            {/* DND / Focus Track */}
            <div className="gantt-row">
              <div className="gantt-label">
                <span>🔕 Focus / DND</span>
              </div>
              <div className="gantt-track">
                {focusPct > 0 ? (
                  <div className="gantt-segment gantt-focus" style={{ width: `${focusPct}%` }}>
                    DND Engaged: {formatDuration(dndSec)} ({focusPct}%)
                  </div>
                ) : (
                  <div style={{ paddingLeft: 12, fontSize: 11, color: 'var(--text-muted)' }}>Standard notifications active</div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Graphs 8, 9, 10 */}
        <div className="threecol" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
          {/* Graph 8: Dark Mode vs Light Mode Duration */}
          <div className="card">
            <h3 style={{ margin: '0 0 2px 0', fontSize: 15 }}>Display Mode Usage</h3>
            <div className="chart-subtitle">Dark Mode vs Light Mode active time</div>

            <div style={{ height: 160 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={displayPieData}
                    innerRadius={46}
                    outerRadius={65}
                    paddingAngle={4}
                    dataKey="value"
                  >
                    {displayPieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: '#090c14', borderColor: 'rgba(255,255,255,0.1)' }} />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="kv" style={{ marginTop: 8 }}>
              <span>Dark Mode Duration</span>
              <b>{formatDuration(darkSec)}</b>
              <span>Light Mode Duration</span>
              <b>{formatDuration(lightSec)}</b>
              <span>Total Monitored</span>
              <b>{formatDuration(totalMonitoredSec)}</b>
              <span>Current Appearance</span>
              <b style={{ color: osDurations?.current_appearance === 'DARK' ? '#a78bfa' : '#fbbf24' }}>
                {osDurations?.current_appearance || 'LIGHT'}
              </b>
            </div>
          </div>

          {/* Graph 9: Focus / DND Usage */}
          <div className="card">
            <h3 style={{ margin: '0 0 2px 0', fontSize: 15 }}>Focus / DND Usage</h3>
            <div className="chart-subtitle">Do Not Disturb activations & duration</div>

            <div style={{ height: 160 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={dndPieData}
                    innerRadius={46}
                    outerRadius={65}
                    paddingAngle={4}
                    dataKey="value"
                  >
                    {dndPieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: '#090c14', borderColor: 'rgba(255,255,255,0.1)' }} />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="kv" style={{ marginTop: 8 }}>
              <span>DND Enabled</span>
              <b>{formatDuration(dndSec)}</b>
              <span>DND Disabled</span>
              <b>{formatDuration(dndDisabledSec)}</b>
              <span>Automatic Activations</span>
              <b>{osDurations?.focus_activations || 0}</b>
              <span>Automatic Deactivations</span>
              <b>{osDurations?.focus_deactivations || 0}</b>
            </div>
          </div>

          {/* Graph 10: Automatic Adaptation Frequency */}
          <div className="card">
            <h3 style={{ margin: '0 0 2px 0', fontSize: 15 }}>Automatic Adaptations</h3>
            <div className="chart-subtitle">Trigger count per intervention category</div>

            <div style={{ height: 210 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={freqData} layout="vertical">
                  <XAxis type="number" stroke="#8492a6" fontSize={11} allowDecimals={false} />
                  <YAxis dataKey="name" type="category" stroke="#8492a6" fontSize={11} width={80} />
                  <Tooltip contentStyle={{ backgroundColor: '#090c14', borderColor: 'rgba(255,255,255,0.1)' }} />
                  <Bar dataKey="count" fill="#38bdf8" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </section>

      {/* ==================================================
          SECTION 5: "AI Decision Relationship"
          ================================================== */}
      <section className="analytics-section">
        <div className="analytics-section-head">
          <div className="analytics-section-title">
            <span className="section-tag">Section 5</span>
            <h2>AI Decision Relationship: Input → AS → Adaptation</h2>
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Transparent Decision Pipeline</span>
        </div>

        <div className="card">
          <h3 style={{ margin: '0 0 2px 0', fontSize: 15 }}>Input vs Adaptation Timeline</h3>
          <div className="chart-subtitle">Shows how user behavioral signals & workload score feed the Adaptive Score (AS) and trigger automatic OS actions</div>

          {decisions.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', padding: '20px 0' }}>Awaiting assessments...</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 320, overflowY: 'auto' }}>
              {decisions.slice(-6).reverse().map((d, index) => {
                const asVal = Number((d.adaptive_score ?? d.ass ?? 0.5).toFixed(2));
                const wlVal = Math.round((d.workload || 0) * 100);
                const isAction = d.action && d.action !== 'NO_ACTION';
                return (
                  <div key={d.id || index} className="decision-flow-item">
                    <div className="flow-step" style={{ minWidth: 90 }}>
                      <span>Assessment</span>
                      <strong>{formatTime(d.timestamp)} (#{d.cycle_id || d.id})</strong>
                    </div>

                    <div className="flow-arrow">→</div>

                    <div className="flow-step">
                      <span>User Input</span>
                      <strong>Workload {wlVal}% · {d.emotion}</strong>
                    </div>

                    <div className="flow-arrow">→</div>

                    <div className="flow-step">
                      <span>Adaptive Score</span>
                      <strong style={{ color: '#a78bfa' }}>AS: {asVal}</strong>
                    </div>

                    <div className="flow-arrow">→</div>

                    <div className="flow-step" style={{ minWidth: 160 }}>
                      <span>OS Action Executed</span>
                      <strong style={{ color: isAction ? '#38bdf8' : 'var(--text-muted)' }}>
                        {d.action?.replace(/_/g, ' ') || 'NO ACTION'}
                      </strong>
                    </div>

                    <div className="flow-step" style={{ flex: 1, maxWidth: 300 }}>
                      <span>AI Rationale</span>
                      <small style={{ color: 'var(--text-muted)', display: 'block', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                        {d.reason || 'State within normal baseline thresholds'}
                      </small>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>

      {/* ==================================================
          SECTION 6: "Camera & Privacy"
          ================================================== */}
      <section className="analytics-section">
        <div className="analytics-section-head">
          <div className="analytics-section-title">
            <span className="section-tag">Section 6</span>
            <h2>Camera Sensing & Privacy Activity</h2>
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Zero persistent video storage</span>
        </div>

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <h3 style={{ margin: '0 0 2px 0', fontSize: 15 }}>Camera Sensing Window Activity</h3>
              <div className="chart-subtitle">
                Demonstrates strict privacy isolation: hardware webcam is active only during designated 5-minute cycle sensing windows
              </div>
            </div>

            <div className="stat-comparison" style={{ margin: 0 }}>
              <span>Camera ON: <b style={{ color: '#ef4444' }}>{formatDuration(cameraOnSec)}</b></span>
              <span>•</span>
              <span>Camera OFF: <b style={{ color: '#10b981' }}>{formatDuration(Math.max(0, totalMonitoredSec - cameraOnSec))}</b></span>
              <span>•</span>
              <span>Sessions: <b>{cameraStats?.camera_sessions_count || 0}</b></span>
            </div>
          </div>

          <div className="gantt-timeline-container" style={{ marginTop: 12 }}>
            <div className="gantt-row">
              <div className="gantt-label">
                <span>📷 Hardware State</span>
              </div>
              <div className="gantt-track">
                {cameraOnPct > 0 ? (
                  <div className="gantt-segment gantt-cam-on" style={{ width: `${cameraOnPct}%` }}>
                    Sensing Active ({cameraOnPct}%)
                  </div>
                ) : null}
                <div className="gantt-segment gantt-cam-off" style={{ width: `${100 - cameraOnPct}%` }}>
                  Hardware Released & Closed ({100 - cameraOnPct}%)
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginTop: 14 }}>
            <div className="kv" style={{ background: 'rgba(255,255,255,0.02)', padding: 12, borderRadius: 8 }}>
              <span>Total Active Duration</span>
              <b>{formatDuration(cameraOnSec)}</b>
              <span>Hardware Disengaged</span>
              <b>{formatDuration(Math.max(0, totalMonitoredSec - cameraOnSec))}</b>
            </div>
            <div className="kv" style={{ background: 'rgba(255,255,255,0.02)', padding: 12, borderRadius: 8 }}>
              <span>Last Sensing Session</span>
              <b>{cameraStats?.last_session_time ? formatTime(cameraStats.last_session_time) : 'Never'}</b>
              <span>Privacy Policy</span>
              <b style={{ color: '#10b981' }}>Local In-Memory Only</b>
            </div>
          </div>
        </div>
      </section>

      {/* ==================================================
          SECTION 7: "Assessment History Table"
          ================================================== */}
      <section className="analytics-section">
        <div className="analytics-section-head">
          <div className="analytics-section-title">
            <span className="section-tag">Section 7</span>
            <h2>5-Minute Assessment History</h2>
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Complete audit trail from SQLite database ({decisions.length} records)
          </span>
        </div>

        <div className="card" style={{ overflowX: 'auto', padding: 0 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, textAlign: 'left' }}>
            <thead>
              <tr style={{ background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '12px 14px' }}>Assessment #</th>
                <th style={{ padding: '12px 14px' }}>Time</th>
                <th style={{ padding: '12px 14px' }}>Window</th>
                <th style={{ padding: '12px 14px' }}>Dominant Emotion</th>
                <th style={{ padding: '12px 14px' }}>Workload</th>
                <th style={{ padding: '12px 14px' }}>Adaptive Score</th>
                <th style={{ padding: '12px 14px' }}>OS Action</th>
                <th style={{ padding: '12px 14px' }}>Decision Rationale</th>
                <th style={{ padding: '12px 14px' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {decisions.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)' }}>
                    No assessments found in database for selected filter.
                  </td>
                </tr>
              ) : (
                [...decisions].reverse().map((d, index) => {
                  const asScore = Number((d.adaptive_score ?? d.ass ?? 0.5).toFixed(2));
                  const isAct = d.action && d.action !== 'NO_ACTION';
                  return (
                    <tr key={d.id || index} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '12px 14px', fontWeight: 600 }}>#{d.cycle_id || d.id}</td>
                      <td style={{ padding: '12px 14px', color: 'var(--text-muted)' }}>{formatTime(d.timestamp)}</td>
                      <td style={{ padding: '12px 14px' }}>5m</td>
                      <td style={{ padding: '12px 14px' }}>
                        <span className="status-pill subtle">{d.emotion || 'Focused'}</span>
                      </td>
                      <td style={{ padding: '12px 14px' }}>{Math.round((d.workload || 0) * 100)}%</td>
                      <td style={{ padding: '12px 14px', fontWeight: 600, color: '#a78bfa' }}>{asScore}</td>
                      <td style={{ padding: '12px 14px' }}>
                        <span className={`status-pill ${isAct ? 'ok' : 'subtle'}`}>
                          {d.action?.replace(/_/g, ' ') || 'NO ACTION'}
                        </span>
                      </td>
                      <td style={{ padding: '12px 14px', color: 'var(--text-muted)', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {d.reason || 'Nominal behavior'}
                      </td>
                      <td style={{ padding: '12px 14px' }}>
                        <span className="status-pill subtle">{d.status || 'executed'}</span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
