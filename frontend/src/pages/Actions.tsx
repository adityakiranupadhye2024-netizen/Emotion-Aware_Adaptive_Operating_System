import { useState, useEffect } from 'react';
import { sendDecisionFeedback, getDecisions } from '../services/api';
import { LiveState, DecisionRecord } from '../types';
import { DecisionDetailsModal } from '../components/DecisionDetailsModal';
import { QuickOSControl } from '../components/QuickOSControl';

export default function Actions({ s }: { s: LiveState | null }) {
  const [history, setHistory] = useState<DecisionRecord[]>([]);
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);
  const [selectedDecision, setSelectedDecision] = useState<DecisionRecord | null>(null);

  const fetchHistory = () => {
    getDecisions()
      .then(setHistory)
      .catch(() => setHistory([]));
  };

  useEffect(() => {
    fetchHistory();
  }, [s?.decision?.id]);

  if (!s) {
    return (
      <div className="empty-state-box">
        <div className="empty-icon">⚙️</div>
        <h2>Waiting for Decision Engine Data</h2>
        <p>No active decision stream detected. Start the backend to view automatic adaptations.</p>
      </div>
    );
  }

  const decision = s.decision || {
    id: 1,
    action: 'NO_ACTION',
    reason: '5-minute observation window active. Monitoring signals.',
    confidence: 0.85,
    policy: 'Personalized 5-Minute Adaptive Engine',
    status: 'observing',
    adaptive_score: s.adaptive_score?.score ?? 0.5,
  };

  const asScore = decision.adaptive_score ?? s.adaptive_score?.score ?? 0.5;

  const handleFeedback = async (type: 'KEEP' | 'UNDO' | 'DISMISS') => {
    if (decision.id) {
      try {
        await sendDecisionFeedback(decision.id, type);
        setFeedbackMsg(
          type === 'KEEP'
            ? '✓ Feedback recorded: Keep (+1.0 reward to contextual bandit).'
            : type === 'UNDO'
            ? '↺ Action reversed at OS level and logged (-1.0 reward).'
            : '✕ Action dismissed (-1.0 reward).'
        );
        fetchHistory();
        setTimeout(() => setFeedbackMsg(null), 4000);
      } catch (err: any) {
        setFeedbackMsg(`Feedback error: ${err.message}`);
        setTimeout(() => setFeedbackMsg(null), 4000);
      }
    }
  };

  return (
    <div>
      <div className="pagehead">
        <div>
          <h1>Automatic Adaptations &amp; Policy Control</h1>
          <p>
            Zero-prompt OS adaptations executed automatically at the end of each 5-minute cycle based on real multimodal state and policy learning.
          </p>
        </div>
      </div>

      {feedbackMsg && (
        <div className="toast-msg" style={{ marginBottom: 16 }}>
          <span>✓</span>
          <span>{feedbackMsg}</span>
        </div>
      )}

      {/* Real OS Mode Switcher & Actuator Testing Controls */}
      <QuickOSControl
        osState={s.actual_os_state}
        cycle={s.cycle}
        decision={s.decision}
        emotion={s.emotion?.dominant}
        workload={s.workload?.score}
        onActionTriggered={fetchHistory}
      />

      {/* Active Autonomous Adaptation Hero */}
      <section className="card heroaction">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 10 }}>
          <div>
            <span>⚡ CURRENT AUTOMATIC ADAPTATION (CYCLE #{s.cycle?.cycle_id || 1})</span>
            <h2>{decision.action.replace(/_/g, ' ')}</h2>
          </div>
          <button
            onClick={() => {
              const rec: DecisionRecord = {
                id: decision.id || 1,
                timestamp: decision.timestamp || new Date().toISOString(),
                cycle_id: s.cycle?.cycle_id || 1,
                emotion: s.emotion.dominant,
                emotion_confidence: s.emotion.confidence,
                workload: s.workload.score,
                adaptive_score: asScore,
                context: (s.context as any)?.canonical_context || s.context.activity || 'GENERAL_WORK',
                context_confidence: (s.context as any)?.confidence || 0.8,
                action: decision.action,
                reason: decision.reason,
                confidence: decision.confidence || 0.85,
                policy: decision.policy || 'LinUCB Policy',
                status: decision.status || 'executed',
                explanation: (decision as any).explanation,
                feedback: (decision as any).feedback
              };
              setSelectedDecision(rec);
            }}
            className="btn btn-sm btn-secondary"
            style={{ background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: '1px solid rgba(56, 189, 248, 0.4)' }}
          >
            🔍 Inspect Explainable AI Rationale
          </button>
        </div>

        <p style={{ marginTop: 8 }}>{decision.reason}</p>

        {(decision as any).message && (
          <div style={{ margin: '8px 0 12px', fontSize: 13, color: '#e2e8f0', background: 'rgba(255,255,255,0.05)', padding: '6px 12px', borderRadius: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: '#38bdf8' }}>⚙️ macOS Execution:</span>
            <span>{(decision as any).message}</span>
            {(decision as any).command_used && (decision as any).command_used !== 'NONE' && (
              <code style={{ fontSize: 11, background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: 4, color: '#94a3b8' }}>{(decision as any).command_used}</code>
            )}
          </div>
        )}

        <div className="decisionmeta" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <span>
              Adaptive Score (AS): <b>{asScore.toFixed(2)}</b>
            </span>
            <span>·</span>
            <span>
              OS Verification: {
                decision.status === 'executed' && (decision as any).verified ? (
                  <b style={{ color: '#34d399' }}>✓ EXECUTED &amp; VERIFIED ON MACOS</b>
                ) : decision.status === 'already_in_desired_state' ? (
                  <b style={{ color: '#38bdf8' }}>● ALREADY IN DESIRED STATE</b>
                ) : decision.status === 'permission_required' ? (
                  <b style={{ color: '#fbbf24' }}>⚠️ PERMISSION REQUIRED</b>
                ) : decision.status === 'failed' ? (
                  <b style={{ color: '#f87171' }}>✕ FAILED — OS UNCHANGED</b>
                ) : decision.status === 'no_action' ? (
                  <b style={{ color: '#94a3b8' }}>● NO ACTION NEEDED</b>
                ) : (
                  <b style={{ color: '#34d399' }}>{(decision.status || 'READY').toUpperCase()}</b>
                )
              }
            </span>
            <span>·</span>
            <span>
              Policy: <b>{decision.policy}</b>
            </span>
            <span>·</span>
            <span>
              Confidence: <b>{Math.round((decision.confidence || 0.85) * 100)}%</b>
            </span>
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
            <button
              className="btn btn-sm btn-primary"
              onClick={() => handleFeedback('KEEP')}
              title="Confirm adaptation was helpful and reward contextual bandit (+1.0)"
            >
              ✓ Keep
            </button>
            <button
              className="btn btn-sm btn-danger"
              disabled={decision.action === 'NO_ACTION'}
              onClick={() => handleFeedback('UNDO')}
              title="Reverse OS adaptation immediately and penalize policy (-1.0)"
            >
              ↺ Undo Action
            </button>
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => handleFeedback('DISMISS')}
              title="Dismiss notification and downvote (-1.0)"
            >
              ✕ Dismiss
            </button>
          </div>
        </div>
      </section>

      {/* Decision Engine Architecture Overview */}
      <section className="card" style={{ marginTop: 20 }}>
        <h2>Zero-Prompt Adaptive Automation Pipeline</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13.5, lineHeight: 1.6, marginTop: 4, marginBottom: 18 }}>
          EAOS evaluates user stress, fatigue, typing cadence, and active context every 5 minutes. Intrusive window hiding and muting are suppressed during meetings or focus-intensive sessions.
        </p>
        <div className="kv">
          <span>Target Platform</span>
          <b>macOS (Native osascript Appearance, DND, Alerts &amp; Volume)</b>
          <span>Decision Frequency</span>
          <b>Continuous 5-Minute Assessment Window</b>
          <span>Context Safety Rules</span>
          <b style={{ color: '#38bdf8' }}>Meeting &amp; Gaming Protective Suppressions Active</b>
          <span>Policy Learner</span>
          <b style={{ color: '#10b981' }}>LinUCB Contextual Bandit with Dual Feedback &amp; Effectiveness Rewards</b>
        </div>
      </section>

      {/* Recent Adaptations Audit Log */}
      <section className="card tablewrap" style={{ marginTop: 20 }}>
        <h2>Recent 5-Minute Adaptations Audit</h2>
        {history.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', padding: '16px 0' }}>
            No adaptations recorded yet in this session.
          </p>
        ) : (
          <table className="eaos-table" style={{ width: '100%', fontSize: '0.85rem' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left' }}>Time</th>
                <th style={{ textAlign: 'left' }}>Action</th>
                <th style={{ textAlign: 'left' }}>Context</th>
                <th style={{ textAlign: 'left' }}>Adaptive Score</th>
                <th style={{ textAlign: 'left' }}>Status</th>
                <th style={{ textAlign: 'center' }}>Feedback</th>
                <th style={{ textAlign: 'center' }}>Effectiveness</th>
              </tr>
            </thead>
            <tbody>
              {history.slice(0, 12).map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setSelectedDecision(r)}
                  style={{ cursor: 'pointer' }}
                  title="Click to inspect decision breakdown"
                >
                  <td style={{ color: '#94a3b8' }}>{new Date(r.timestamp).toLocaleTimeString()}</td>
                  <td>
                    <b style={{ color: r.action === 'NO_ACTION' ? '#64748b' : '#38bdf8' }}>
                      {r.action.replace(/_/g, ' ')}
                    </b>
                  </td>
                  <td style={{ color: '#cbd5e1' }}>{r.context}</td>
                  <td>
                    <b style={{ color: '#a78bfa' }}>{(r.adaptive_score ?? r.ass ?? 0).toFixed(2)}</b>
                  </td>
                  <td>
                    <span className={`status-pill ${r.status === 'executed' ? 'pill-positive' : 'pill-neutral'}`}>
                      {r.status?.toUpperCase() || 'EXECUTED'}
                    </span>
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    {r.feedback ? (
                      <span className={`status-pill ${r.feedback === 'KEEP' ? 'pill-positive' : 'pill-negative'}`}>
                        {r.feedback}
                      </span>
                    ) : (
                      <span style={{ color: '#64748b' }}>—</span>
                    )}
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    {r.effectiveness ? (
                      <span className={`status-pill pill-${r.effectiveness.toLowerCase()}`}>
                        ● {r.effectiveness}
                      </span>
                    ) : (
                      <span style={{ color: '#64748b' }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Decision Details Modal */}
      {selectedDecision && (
        <DecisionDetailsModal
          decision={selectedDecision}
          onClose={() => setSelectedDecision(null)}
          onFeedbackUpdated={() => fetchHistory()}
        />
      )}
    </div>
  );
}
