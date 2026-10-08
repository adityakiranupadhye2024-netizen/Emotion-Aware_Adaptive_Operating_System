import { useEffect, useState } from 'react';
import { getDecisions, sendDecisionFeedback } from '../services/api';
import { DecisionRecord } from '../types';
import { DecisionDetailsModal } from '../components/DecisionDetailsModal';

export default function History() {
  const [rows, setRows] = useState<DecisionRecord[]>([]);
  const [actionFilter, setActionFilter] = useState('ALL');
  const [contextFilter, setContextFilter] = useState('ALL');
  const [effectivenessFilter, setEffectivenessFilter] = useState('ALL');
  const [search, setSearch] = useState('');
  const [selectedDecision, setSelectedDecision] = useState<DecisionRecord | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const fetchHistory = () => {
    getDecisions()
      .then(setRows)
      .catch(() => setRows([]));
  };

  useEffect(() => {
    fetchHistory();
    const timer = setInterval(fetchHistory, 6000);
    return () => clearInterval(timer);
  }, []);

  const uniqueActions = Array.from(new Set(rows.map((r) => r.action))).filter(Boolean);
  const uniqueContexts = Array.from(new Set(rows.map((r) => r.context))).filter(Boolean);

  const handleQuickFeedback = async (id: number, type: 'KEEP' | 'UNDO' | 'DISMISS', e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await sendDecisionFeedback(id, type);
      setActionMessage(`Decision #${id} marked as ${type}`);
      setTimeout(() => setActionMessage(null), 3000);
      fetchHistory();
    } catch (err: any) {
      setActionMessage(`Error: ${err.message}`);
      setTimeout(() => setActionMessage(null), 3000);
    }
  };

  const filtered = rows.filter((r) => {
    if (actionFilter !== 'ALL' && r.action !== actionFilter) return false;
    if (contextFilter !== 'ALL' && r.context !== contextFilter) return false;
    if (effectivenessFilter !== 'ALL') {
      if (effectivenessFilter === 'PENDING' && r.effectiveness) return false;
      if (effectivenessFilter !== 'PENDING' && r.effectiveness !== effectivenessFilter) return false;
    }
    if (search) {
      const q = search.toLowerCase();
      const matchAction = r.action?.toLowerCase().includes(q);
      const matchReason = r.reason?.toLowerCase().includes(q);
      const matchEmotion = r.emotion?.toLowerCase().includes(q);
      const matchContext = r.context?.toLowerCase().includes(q);
      if (!matchAction && !matchReason && !matchEmotion && !matchContext) return false;
    }
    return true;
  });

  return (
    <div>
      <div className="pagehead">
        <div>
          <h1>5-Minute Decision &amp; Adaptation History</h1>
          <p>
            10-column comprehensive audit log of 5-minute cycle assessments, explainable context, confidence, and adaptation outcomes.
          </p>
        </div>
      </div>

      {actionMessage && (
        <div style={{ padding: '8px 16px', marginBottom: '12px', borderRadius: '6px', background: 'rgba(56, 189, 248, 0.15)', border: '1px solid #38bdf8', color: '#38bdf8', fontSize: '0.85rem' }}>
          ✓ {actionMessage}
        </div>
      )}

      {/* Filter Controls Bar */}
      <section className="card filter-bar" style={{ marginBottom: '16px', padding: '14px 18px' }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4, textTransform: 'uppercase' }}>
              Action:
            </label>
            <select
              className="select-filter"
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              style={{ padding: '6px 10px', borderRadius: '6px', background: 'rgba(15, 23, 42, 0.8)', color: '#f8fafc', border: '1px solid rgba(255,255,255,0.15)' }}
            >
              <option value="ALL">All Actions</option>
              {uniqueActions.map((a) => (
                <option key={a} value={a}>
                  {a === 'MUTE_AUDIO' ? 'AUDIO DECREASED' : a.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4, textTransform: 'uppercase' }}>
              Context:
            </label>
            <select
              className="select-filter"
              value={contextFilter}
              onChange={(e) => setContextFilter(e.target.value)}
              style={{ padding: '6px 10px', borderRadius: '6px', background: 'rgba(15, 23, 42, 0.8)', color: '#f8fafc', border: '1px solid rgba(255,255,255,0.15)' }}
            >
              <option value="ALL">All Contexts</option>
              {uniqueContexts.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4, textTransform: 'uppercase' }}>
              Effectiveness:
            </label>
            <select
              className="select-filter"
              value={effectivenessFilter}
              onChange={(e) => setEffectivenessFilter(e.target.value)}
              style={{ padding: '6px 10px', borderRadius: '6px', background: 'rgba(15, 23, 42, 0.8)', color: '#f8fafc', border: '1px solid rgba(255,255,255,0.15)' }}
            >
              <option value="ALL">All Outcomes</option>
              <option value="POSITIVE">Positive Improvement</option>
              <option value="NEUTRAL">Neutral State</option>
              <option value="NEGATIVE">Negative Change</option>
              <option value="PENDING">Pending Evaluation</option>
            </select>
          </div>

          <div style={{ flex: 1, minWidth: 220 }}>
            <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4, textTransform: 'uppercase' }}>
              Search Reason, Action or Context:
            </label>
            <input
              type="text"
              className="input-search"
              placeholder="Search history..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: '100%', padding: '6px 12px', borderRadius: '6px', background: 'rgba(15, 23, 42, 0.8)', color: '#f8fafc', border: '1px solid rgba(255,255,255,0.15)' }}
            />
          </div>
        </div>
      </section>

      {/* 10-Column Table of Decisions */}
      <section className="card tablewrap" style={{ overflowX: 'auto' }}>
        {filtered.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', padding: '24px 0', textAlign: 'center' }}>
            No assessment decisions match the selected criteria.
          </p>
        ) : (
          <table className="eaos-table" style={{ width: '100%', fontSize: '0.82rem', whiteSpace: 'nowrap' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                <th style={{ padding: '10px 8px', textAlign: 'left' }}>Cycle</th>
                <th style={{ padding: '10px 8px', textAlign: 'left' }}>Time</th>
                <th style={{ padding: '10px 8px', textAlign: 'left' }}>Context</th>
                <th style={{ padding: '10px 8px', textAlign: 'left' }}>Emotion</th>
                <th style={{ padding: '10px 8px', textAlign: 'left' }}>Workload</th>
                <th style={{ padding: '10px 8px', textAlign: 'left' }}>AS</th>
                <th style={{ padding: '10px 8px', textAlign: 'left' }}>Action Taken</th>
                <th style={{ padding: '10px 8px', textAlign: 'left' }}>Confidence</th>
                <th style={{ padding: '10px 8px', textAlign: 'center' }}>Feedback</th>
                <th style={{ padding: '10px 8px', textAlign: 'center' }}>Effectiveness</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setSelectedDecision(r)}
                  style={{ cursor: 'pointer', transition: 'background 0.15s ease' }}
                  className="history-row"
                  title="Click to view explainable AI rationale & breakdown"
                >
                  <td style={{ padding: '10px 8px', fontWeight: 600, color: '#f8fafc' }}>
                    #{r.cycle_id ?? 1}
                  </td>
                  <td style={{ padding: '10px 8px', color: '#94a3b8' }}>
                    {new Date(r.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </td>
                  <td style={{ padding: '10px 8px' }}>
                    <span style={{ color: '#38bdf8', fontWeight: 500 }}>
                      {r.context}
                    </span>
                    <small style={{ color: '#64748b', marginLeft: 4 }}>
                      {Math.round((r.context_confidence ?? 0.8) * 100)}%
                    </small>
                  </td>
                  <td style={{ padding: '10px 8px' }}>
                    <span style={{ color: '#cbd5e1' }}>{r.emotion}</span>
                  </td>
                  <td style={{ padding: '10px 8px', color: '#cbd5e1' }}>
                    {Math.round((r.workload ?? 0.5) * 100)}%
                  </td>
                  <td style={{ padding: '10px 8px' }}>
                    <b style={{ color: '#a78bfa' }}>
                      {(r.adaptive_score ?? r.ass ?? 0).toFixed(2)}
                    </b>
                  </td>
                  <td style={{ padding: '10px 8px' }}>
                    <b style={{ color: r.action === 'NO_ACTION' ? '#64748b' : '#38bdf8' }}>
                      {r.action === 'MUTE_AUDIO' ? 'AUDIO DECREASED' : r.action.replace(/_/g, ' ')}
                    </b>
                  </td>
                  <td style={{ padding: '10px 8px' }}>
                    <span style={{ color: '#10b981', fontWeight: 500 }}>
                      {Math.round((r.confidence ?? 0.8) * 100)}%
                    </span>
                  </td>
                  <td style={{ padding: '10px 8px', textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
                    {r.feedback ? (
                      <span className={`status-pill ${r.feedback === 'KEEP' ? 'pill-positive' : 'pill-negative'}`}>
                        {r.feedback}
                      </span>
                    ) : (
                      <div style={{ display: 'inline-flex', gap: 4 }}>
                        <button
                          onClick={(e) => handleQuickFeedback(r.id, 'KEEP', e)}
                          className="btn btn-sm btn-secondary"
                          style={{ padding: '2px 6px', fontSize: '0.7rem' }}
                          title="Reward (+1.0)"
                        >
                          ✓
                        </button>
                        <button
                          onClick={(e) => handleQuickFeedback(r.id, 'UNDO', e)}
                          className="btn btn-sm btn-secondary"
                          style={{ padding: '2px 6px', fontSize: '0.7rem', color: '#ef4444' }}
                          title="Undo & Downvote (-1.0)"
                        >
                          ↺
                        </button>
                      </div>
                    )}
                  </td>
                  <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                    {r.effectiveness ? (
                      <span className={`status-pill pill-${r.effectiveness.toLowerCase()}`}>
                        ● {r.effectiveness}
                      </span>
                    ) : (
                      <span style={{ color: '#64748b', fontSize: '0.75rem' }}>
                        {r.action === 'NO_ACTION' ? '—' : 'Cycle N+1'}
                      </span>
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
          onFeedbackUpdated={(id, fb) => {
            setActionMessage(`Decision #${id} marked as ${fb}`);
            fetchHistory();
          }}
        />
      )}
    </div>
  );
}
