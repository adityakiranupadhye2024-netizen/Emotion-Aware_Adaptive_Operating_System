import React, { useEffect, useState } from 'react';
import {
  getPrivacyStatus,
  togglePrivacyPause,
  clearHistory,
  applyDataRetention,
  updatePrivacySettings,
} from '../services/api';
import { PrivacyStatus } from '../types';

export const Privacy: React.FC = () => {
  const [privacy, setPrivacy] = useState<PrivacyStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retentionPeriod, setRetentionPeriod] = useState('30d');
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  const fetchPrivacy = async () => {
    try {
      const data = await getPrivacyStatus();
      setPrivacy(data);
      if (data.retention_setting) {
        setRetentionPeriod(data.retention_setting);
      }
      setError(null);
    } catch (e: any) {
      setError(e.message || 'Failed to load privacy status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPrivacy();
    const interval = setInterval(fetchPrivacy, 5000);
    return () => clearInterval(interval);
  }, []);

  const handlePauseToggle = async () => {
    if (!privacy) return;
    try {
      const nextState = !privacy.monitoring_paused;
      await togglePrivacyPause(nextState);
      setActionMessage(nextState ? 'Monitoring paused: Sensors suspended.' : 'Monitoring resumed: Sensors active.');
      fetchPrivacy();
    } catch (e: any) {
      setError(e.message || 'Failed to toggle pause');
    }
  };

  const handleCameraToggle = async () => {
    if (!privacy) return;
    try {
      const nextState = !privacy.camera_sensing_enabled;
      await updatePrivacySettings({ camera_sensing_enabled: nextState });
      setActionMessage(nextState ? 'Camera sensing enabled.' : 'Camera sensing disabled (hardware released).');
      fetchPrivacy();
    } catch (e: any) {
      setError(e.message || 'Failed to update camera setting');
    }
  };

  const handleRetentionSave = async () => {
    try {
      await applyDataRetention(retentionPeriod);
      setActionMessage(`Retention policy (${retentionPeriod}) applied to database.`);
      fetchPrivacy();
    } catch (e: any) {
      setError(e.message || 'Failed to apply retention');
    }
  };

  const handleClearHistory = async () => {
    try {
      await clearHistory();
      setActionMessage('All historical decisions, notifications, and telemetry purged.');
      setConfirmClear(false);
      fetchPrivacy();
    } catch (e: any) {
      setError(e.message || 'Failed to clear history');
    }
  };

  if (loading && !privacy) {
    return (
      <div className="page-container">
        <h1 className="page-title">Privacy & Data Governance</h1>
        <div style={{ color: '#94a3b8' }}>Loading privacy controls...</div>
      </div>
    );
  }

  const isPaused = privacy?.monitoring_paused ?? false;
  const camState = privacy?.camera_hardware_state ?? 'OFF';

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h1 className="page-title" style={{ margin: 0 }}>Privacy & Data Governance</h1>
          <p style={{ margin: '4px 0 0 0', color: '#94a3b8', fontSize: '0.9rem' }}>
            EAOS is designed with strict on-device privacy, zero text logging, and transparent controls.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <button
            onClick={handlePauseToggle}
            className={`btn ${isPaused ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '8px 16px', fontWeight: 600 }}
          >
            {isPaused ? '▶ Resume Monitoring' : '⏸ Pause All Monitoring'}
          </button>
        </div>
      </div>

      {actionMessage && (
        <div style={{ padding: '10px 16px', marginBottom: '16px', borderRadius: '6px', background: 'rgba(56, 189, 248, 0.15)', border: '1px solid #38bdf8', color: '#38bdf8', fontSize: '0.9rem' }}>
          {actionMessage}
        </div>
      )}

      {error && (
        <div style={{ padding: '10px 16px', marginBottom: '16px', borderRadius: '6px', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid #ef4444', color: '#ef4444', fontSize: '0.9rem' }}>
          {error}
        </div>
      )}

      {/* Monitoring Pause Banner */}
      {isPaused && (
        <div style={{ padding: '16px', marginBottom: '20px', borderRadius: '8px', background: 'rgba(245, 158, 11, 0.15)', border: '1px solid #f59e0b', color: '#fbbf24' }}>
          <div style={{ fontWeight: 600, fontSize: '1rem' }}>⏸ Monitoring is Currently Paused</div>
          <div style={{ fontSize: '0.85rem', marginTop: '4px', color: '#fef3c7' }}>
            No keyboard cadence, mouse jitter, context, or camera frames are being collected or assessed.
          </div>
        </div>
      )}

      {/* Core Privacy Guarantees */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        <div className="card" style={{ padding: '16px', borderTop: '3px solid #10b981' }}>
          <div style={{ fontSize: '1.2rem', marginBottom: '8px' }}>🔒 Local Processing</div>
          <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.95rem' }}>100% On-Device Inference</div>
          <p style={{ margin: '6px 0 0 0', color: '#94a3b8', fontSize: '0.85rem' }}>
            All emotional analysis, workload scoring, and decision engine logic execute locally. No audio, video, or keystrokes leave your machine.
          </p>
        </div>

        <div className="card" style={{ padding: '16px', borderTop: '3px solid #38bdf8' }}>
          <div style={{ fontSize: '1.2rem', marginBottom: '8px' }}>⌨️ Zero Text Logging</div>
          <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.95rem' }}>Cadence Only, No Content</div>
          <p style={{ margin: '6px 0 0 0', color: '#94a3b8', fontSize: '0.85rem' }}>
            The keyboard sensor measures inter-key interval timing and backspace count. Individual key identities and typed characters are discarded.
          </p>
        </div>

        <div className="card" style={{ padding: '16px', borderTop: '3px solid #a78bfa' }}>
          <div style={{ fontSize: '1.2rem', marginBottom: '8px' }}>📷 Ephemeral Video</div>
          <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.95rem' }}>Zero Frames Saved to Disk</div>
          <p style={{ margin: '6px 0 0 0', color: '#94a3b8', fontSize: '0.85rem' }}>
            Camera frames are analyzed in-memory and immediately released. The webcam operates strictly in the 5-minute sensing window when enabled.
          </p>
        </div>

        <div className="card" style={{ padding: '16px', borderTop: '3px solid #f59e0b' }}>
          <div style={{ fontSize: '1.2rem', marginBottom: '8px' }}>🛡️ Transparent State</div>
          <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.95rem' }}>Hardware Status: {camState}</div>
          <p style={{ margin: '6px 0 0 0', color: '#94a3b8', fontSize: '0.85rem' }}>
            Operating state matches actual physical camera usage. Disabling camera sensing releases camera hardware.
          </p>
        </div>
      </div>

      {/* Camera Sensing Controls */}
      <div className="card" style={{ padding: '20px', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '1.1rem', margin: '0 0 16px 0', color: '#f8fafc' }}>
          Camera Sensing & Privacy Scheduler
        </h2>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 0', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
          <div>
            <div style={{ fontWeight: 600, color: '#f8fafc' }}>Enable Camera Facial Sensing</div>
            <div style={{ fontSize: '0.85rem', color: '#94a3b8', marginTop: '2px' }}>
              When enabled, analyzes facial expression during 5-minute assessment cycles. When disabled, emotion is inferred solely from keyboard & mouse behavior.
            </div>
          </div>
          <button
            onClick={handleCameraToggle}
            className={`btn ${privacy?.camera_sensing_enabled ? 'btn-primary' : 'btn-secondary'}`}
            style={{ minWidth: '110px' }}
          >
            {privacy?.camera_sensing_enabled ? '✓ Enabled' : 'Off'}
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginTop: '16px' }}>
          <div className="stat-card" style={{ padding: '12px', background: 'rgba(255,255,255,0.02)' }}>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>CAMERA HARDWARE STATE</div>
            <div style={{ fontWeight: 600, color: camState === 'ACTIVE' ? '#10b981' : '#94a3b8', marginTop: '4px' }}>
              ● {camState}
            </div>
          </div>
          <div className="stat-card" style={{ padding: '12px', background: 'rgba(255,255,255,0.02)' }}>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>TOTAL CAMERA ON-TIME</div>
            <div style={{ fontWeight: 600, color: '#38bdf8', marginTop: '4px' }}>
              {Math.round((privacy?.camera_stats?.camera_on_seconds ?? 0) / 60)} minutes
            </div>
          </div>
          <div className="stat-card" style={{ padding: '12px', background: 'rgba(255,255,255,0.02)' }}>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>SESSIONS RECORDED</div>
            <div style={{ fontWeight: 600, color: '#a78bfa', marginTop: '4px' }}>
              {privacy?.camera_stats?.camera_sessions_count ?? 0} cycles
            </div>
          </div>
        </div>
      </div>

      {/* Data Retention & Purge Controls */}
      <div className="card" style={{ padding: '20px', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '1.1rem', margin: '0 0 16px 0', color: '#f8fafc' }}>
          Data Retention & History Management
        </h2>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 0', borderBottom: '1px solid rgba(255,255,255,0.06)', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <div style={{ fontWeight: 600, color: '#f8fafc' }}>Automatic Data Retention Policy</div>
            <div style={{ fontSize: '0.85rem', color: '#94a3b8', marginTop: '2px' }}>
              Older assessment decisions and telemetry logs are permanently purged from the local SQLite database.
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <select
              value={retentionPeriod}
              onChange={(e) => setRetentionPeriod(e.target.value)}
              className="select-input"
              style={{ padding: '6px 12px', borderRadius: '6px', background: 'rgba(15, 23, 42, 0.8)', color: '#f8fafc', border: '1px solid rgba(255,255,255,0.15)' }}
            >
              <option value="7d">Keep for 7 Days</option>
              <option value="30d">Keep for 30 Days</option>
              <option value="90d">Keep for 90 Days</option>
              <option value="forever">Keep Forever</option>
            </select>
            <button
              onClick={handleRetentionSave}
              className="btn btn-secondary"
              style={{ padding: '6px 12px' }}
            >
              Apply Retention
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '16px', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <div style={{ fontWeight: 600, color: '#ef4444' }}>Purge Historical Decisions & Telemetry</div>
            <div style={{ fontSize: '0.85rem', color: '#94a3b8', marginTop: '2px' }}>
              Immediately deletes all past assessment logs, effectiveness comparisons, and notification histories.
            </div>
          </div>
          <div>
            {confirmClear ? (
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={handleClearHistory}
                  className="btn btn-danger"
                  style={{ padding: '6px 14px' }}
                >
                  Yes, Purge Everything
                </button>
                <button
                  onClick={() => setConfirmClear(false)}
                  className="btn btn-secondary"
                  style={{ padding: '6px 12px' }}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmClear(true)}
                className="btn btn-danger"
                style={{ padding: '6px 14px' }}
              >
                Clear Decision History
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Recent Camera Hardware Sessions */}
      {privacy?.camera_stats?.sessions && privacy.camera_stats.sessions.length > 0 && (
        <div className="card" style={{ padding: '20px' }}>
          <h2 style={{ fontSize: '1.1rem', margin: '0 0 12px 0', color: '#f8fafc' }}>
            Recent Camera Sensing Windows
          </h2>
          <table className="eaos-table" style={{ width: '100%', fontSize: '0.85rem' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left' }}>Session #</th>
                <th style={{ textAlign: 'left' }}>Start Timestamp</th>
                <th style={{ textAlign: 'left' }}>Duration</th>
                <th style={{ textAlign: 'left' }}>Hardware State</th>
              </tr>
            </thead>
            <tbody>
              {privacy.camera_stats.sessions.slice(-8).reverse().map((s) => (
                <tr key={s.id}>
                  <td style={{ color: '#94a3b8' }}>#{s.id}</td>
                  <td style={{ color: '#cbd5e1' }}>{new Date(s.start_time).toLocaleTimeString()}</td>
                  <td style={{ color: '#38bdf8' }}>{Math.round(s.duration_seconds)}s</td>
                  <td>
                    <span className="status-pill pill-positive">
                      ● {s.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
