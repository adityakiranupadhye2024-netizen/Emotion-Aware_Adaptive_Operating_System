import React from 'react';
import { DecisionRecord } from '../types';
import { sendDecisionFeedback } from '../services/api';

interface DecisionDetailsModalProps {
  decision: DecisionRecord | null;
  onClose: () => void;
  onFeedbackUpdated?: (id: number, feedback: string) => void;
}

export const DecisionDetailsModal: React.FC<DecisionDetailsModalProps> = ({
  decision,
  onClose,
  onFeedbackUpdated,
}) => {
  if (!decision) return null;

  const [submitting, setSubmitting] = React.useState(false);
  const [currentFeedback, setCurrentFeedback] = React.useState<string | undefined>(decision.feedback);

  const handleFeedback = async (type: 'KEEP' | 'UNDO' | 'DISMISS') => {
    try {
      setSubmitting(true);
      await sendDecisionFeedback(decision.id, type);
      setCurrentFeedback(type);
      if (onFeedbackUpdated) {
        onFeedbackUpdated(decision.id, type);
      }
    } catch (e) {
      console.error('Failed to submit feedback:', e);
    } finally {
      setSubmitting(false);
    }
  };

  const explanation = decision.explanation;
  const factors = explanation?.contributing_factors || [];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '680px', width: '90%', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid var(--border-color, rgba(255,255,255,0.1))', paddingBottom: '12px' }}>
          <div>
            <div style={{ fontSize: '0.8rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Cycle #{decision.cycle_id || 1} Assessment · Decision #{decision.id}
            </div>
            <h2 style={{ margin: '4px 0 0 0', fontSize: '1.3rem', color: '#f8fafc' }}>
              Explainable AI Decision Details
            </h2>
          </div>
          <button
            onClick={onClose}
            className="btn btn-secondary"
            style={{ padding: '4px 10px', fontSize: '0.9rem' }}
          >
            ✕
          </button>
        </div>

        {/* Action & Status Overview */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px', marginTop: '16px' }}>
          <div className="stat-card" style={{ padding: '10px', background: 'rgba(255,255,255,0.03)' }}>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>ADAPTATION ACTION</div>
            <div style={{ fontWeight: 600, color: '#38bdf8', marginTop: '4px' }}>
              {decision.action.replace(/_/g, ' ')}
            </div>
          </div>
          <div className="stat-card" style={{ padding: '10px', background: 'rgba(255,255,255,0.03)' }}>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>ADAPTIVE SCORE (AS)</div>
            <div style={{ fontWeight: 600, color: '#a78bfa', marginTop: '4px' }}>
              {(decision.adaptive_score ?? 0).toFixed(2)} / 1.00
            </div>
          </div>
          <div className="stat-card" style={{ padding: '10px', background: 'rgba(255,255,255,0.03)' }}>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>DECISION CONFIDENCE</div>
            <div style={{ fontWeight: 600, color: '#10b981', marginTop: '4px' }}>
              {Math.round((decision.confidence ?? 0.8) * 100)}%
            </div>
          </div>
          <div className="stat-card" style={{ padding: '10px', background: 'rgba(255,255,255,0.03)' }}>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>CONTEXT</div>
            <div style={{ fontWeight: 600, color: '#f59e0b', marginTop: '4px' }}>
              {decision.context} ({Math.round((decision.context_confidence ?? 0.8) * 100)}%)
            </div>
          </div>
        </div>

        {/* Plain English Explanation */}
        <div style={{ marginTop: '16px', background: 'rgba(15, 23, 42, 0.6)', padding: '14px', borderRadius: '8px', borderLeft: '4px solid #38bdf8' }}>
          <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#38bdf8', marginBottom: '4px' }}>
            PLAIN-ENGLISH RATIONALE ("WHY?")
          </div>
          <p style={{ margin: 0, color: '#e2e8f0', fontSize: '0.95rem', lineHeight: '1.45' }}>
            {explanation?.summary || decision.reason}
          </p>
          {explanation?.context_modifier_applied && (
            <div style={{ marginTop: '8px', fontSize: '0.85rem', color: '#cbd5e1' }}>
              <strong>Context Rule Applied:</strong> {explanation.context_modifier_applied}
            </div>
          )}
        </div>

        {/* Contributing Signals Breakdown */}
        <div style={{ marginTop: '16px' }}>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#94a3b8', marginBottom: '8px' }}>
            CONTRIBUTING SIGNALS & IMPACT
          </div>
          {factors.length > 0 ? (
            <table className="eaos-table" style={{ width: '100%', fontSize: '0.85rem' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left' }}>Signal</th>
                  <th style={{ textAlign: 'left' }}>Observed Value</th>
                  <th style={{ textAlign: 'left' }}>Effect on Decision</th>
                </tr>
              </thead>
              <tbody>
                {factors.map((f, idx) => (
                  <tr key={idx}>
                    <td style={{ fontWeight: 500, color: '#f8fafc' }}>{f.factor}</td>
                    <td style={{ color: '#94a3b8' }}>{f.weight_or_value}</td>
                    <td style={{ color: f.impact.toLowerCase().includes('high') ? '#f59e0b' : '#38bdf8' }}>
                      {f.impact}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ fontSize: '0.85rem', color: '#94a3b8', fontStyle: 'italic' }}>
              Dominant emotion: {decision.emotion} · Workload: {Math.round(decision.workload * 100)}% · Policy: {decision.policy}
            </div>
          )}
        </div>

        {/* Effectiveness Section (if evaluated) */}
        {decision.effectiveness && (
          <div style={{ marginTop: '16px', padding: '12px', borderRadius: '8px', background: 'rgba(30, 41, 59, 0.5)', border: '1px solid rgba(255,255,255,0.08)' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#94a3b8', marginBottom: '6px' }}>
              ADAPTATION EFFECTIVENESS (5-MINUTE POST-ASSESSMENT)
            </div>
            <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
              <span className={`status-pill pill-${decision.effectiveness.toLowerCase()}`}>
                ● {decision.effectiveness}
              </span>
              <span style={{ fontSize: '0.85rem', color: '#cbd5e1' }}>
                Adaptive Score: {decision.pre_as?.toFixed(2)} → {decision.post_as?.toFixed(2)} ({decision.observed_as_change && decision.observed_as_change > 0 ? '+' : ''}{decision.observed_as_change?.toFixed(2)})
              </span>
              <span style={{ fontSize: '0.85rem', color: '#cbd5e1' }}>
                Workload: {Math.round((decision.pre_workload ?? 0) * 100)}% → {Math.round((decision.post_workload ?? 0) * 100)}%
              </span>
            </div>
          </div>
        )}

        {/* User Feedback Controls */}
        <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border-color, rgba(255,255,255,0.1))', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>USER FEEDBACK</div>
            <div style={{ fontSize: '0.85rem', color: currentFeedback ? '#38bdf8' : '#64748b', fontWeight: 500 }}>
              {currentFeedback ? `Marked as ${currentFeedback}` : 'No feedback recorded yet'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => handleFeedback('KEEP')}
              disabled={submitting || currentFeedback === 'KEEP'}
              className="btn btn-sm btn-primary"
              style={{ background: currentFeedback === 'KEEP' ? '#059669' : undefined }}
              title="Reward policy learner (+1.0) and keep adaptation"
            >
              ✓ Keep
            </button>
            <button
              onClick={() => handleFeedback('UNDO')}
              disabled={submitting || currentFeedback === 'UNDO' || decision.action === 'NO_ACTION'}
              className="btn btn-sm btn-danger"
              style={{ background: currentFeedback === 'UNDO' ? '#dc2626' : undefined }}
              title="Reverse OS adaptation immediately and update policy (-1.0)"
            >
              ↺ Undo
            </button>
            <button
              onClick={() => handleFeedback('DISMISS')}
              disabled={submitting || currentFeedback === 'DISMISS'}
              className="btn btn-sm btn-secondary"
              style={{ opacity: currentFeedback === 'DISMISS' ? 0.6 : 1 }}
              title="Dismiss notification and downvote (-1.0)"
            >
              ✕ Dismiss
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
