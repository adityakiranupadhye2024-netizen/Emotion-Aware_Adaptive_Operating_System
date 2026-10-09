import React, { Component, ErrorInfo, ReactNode, useState } from 'react';
import Sidebar from './components/Sidebar';
import Overview from './pages/Overview';
import AIState from './pages/AIState';
import Analytics from './pages/Analytics';
import Actions from './pages/Actions';
import History from './pages/History';
import Settings from './pages/Settings';
import Diagnostics from './pages/Diagnostics';
import { Privacy } from './pages/Privacy';
import { useEAOS } from './store/useEAOS';
import { resetSystem } from './services/api';
import { NotificationToast } from './components/NotificationToast';
import './styles.css';

class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; error: string | null }> {
  state = { hasError: false, error: null };
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('EAOS UI Render Error:', error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="empty-state-box" style={{ margin: '30px auto', maxWidth: 650 }}>
          <div className="empty-icon">⚠️</div>
          <h2>Interface Recovered</h2>
          <p style={{ color: '#ef4444' }}>{this.state.error}</p>
          <p>The system intercepted a render error and prevented a blank screen.</p>
          <button className="btn btn-primary" onClick={() => this.setState({ hasError: false, error: null })}>
            Reload View
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const [page, setPage] = useState('Overview');
  const [resetMsg, setResetMsg] = useState<string | null>(null);
  const [isResetting, setIsResetting] = useState(false);
  const { state, online } = useEAOS();

  const handleReset = async () => {
    setIsResetting(true);
    try {
      const res = await resetSystem();
      setResetMsg(res.message || 'System & macOS adaptations reset to default.');
      setTimeout(() => setResetMsg(null), 4500);
    } catch (err: any) {
      setResetMsg(`Reset error: ${err.message}`);
      setTimeout(() => setResetMsg(null), 4000);
    } finally {
      setIsResetting(false);
    }
  };

  const Page =
    page === 'Overview'
      ? Overview
      : page === 'AI State'
      ? AIState
      : page === 'Analytics'
      ? Analytics
      : page === 'Actions'
      ? Actions
      : page === 'History'
      ? History
      : page === 'Privacy'
      ? Privacy
      : page === 'Settings'
      ? Settings
      : Diagnostics;


  const isAutomationOn = state?.cycle?.automation_enabled ?? true;
  const isFocusOn = !!state?.actual_os_state?.focus_mode_active;

  React.useEffect(() => {
    document.body.classList.remove('light-theme');
  }, []);

  return (
    <div className="app">
      <Sidebar page={page} setPage={setPage} />
      <main>
        <header>
          <div className="header-left">
            <b>EAOS</b>
            <span>Emotion-Aware Adaptive Operating System</span>
          </div>

          <div className="header-actions">
            <div className={online && isAutomationOn ? 'auto-pill' : 'auto-pill off'}>
              <i />
              <span>{online ? (isAutomationOn ? '● EAOS ACTIVE' : '● AUTOMATION PAUSED') : '● EAOS STANDBY'}</span>
            </div>

            <button
              className="reset-btn"
              disabled={isResetting || !online}
              onClick={handleReset}
              title="Restore macOS Light Mode, unmute sound, and reset adaptive state"
            >
              🔄 {isResetting ? 'Resetting...' : 'Reset Adaptations'}
            </button>

            <div className={online ? 'connection live' : 'connection offline'}>
              <i /> {online ? (state?.mode === 'DEMO' ? 'DEMO MODE' : 'LIVE SYSTEM') : 'BACKEND OFFLINE'}
            </div>
          </div>
        </header>

        <div className="content">
          <NotificationToast latestDecision={state?.decision} />
          {isFocusOn && (
            <div className="dnd-active-banner">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: '1.25rem' }}>🔕</span>
                <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>
                  DO NOT DISTURB ACTIVE · All system alerts & notifications silenced
                </span>
              </div>
              <span style={{ fontSize: '0.75rem', background: 'rgba(6, 182, 212, 0.25)', padding: '3px 8px', borderRadius: 4, fontWeight: 700 }}>
                DND MODE ENGAGED
              </span>
            </div>
          )}
          {resetMsg && (
            <div className="toast-msg">
              <span>✓</span>
              <span>{resetMsg}</span>
            </div>
          )}
          {state?.monitoring_paused && (
            <div style={{ padding: '10px 16px', marginBottom: '14px', borderRadius: '8px', background: 'rgba(245, 158, 11, 0.2)', border: '1px solid #f59e0b', color: '#fbbf24', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <strong>⏸ Monitoring is Paused:</strong> Telemetry collection and adaptive assessment are currently suspended.
              </div>
              <button
                onClick={() => setPage('Privacy')}
                className="btn btn-sm btn-secondary"
                style={{ padding: '4px 10px', fontSize: '0.8rem' }}
              >
                Privacy Settings →
              </button>
            </div>
          )}
          {!online && (
            <div className="offline-banner">
              <strong>⚠️ BACKEND OFFLINE</strong>
              <span>Cannot connect to FastAPI server at <code>http://127.0.0.1:8765</code>. Start the backend with <code>uvicorn app.main:app --port 8765</code>.</span>
            </div>
          )}

          <ErrorBoundary>
            <Page s={state} online={online} />
          </ErrorBoundary>
        </div>
      </main>
    </div>
  );
}
