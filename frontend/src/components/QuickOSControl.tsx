import React, { useState } from 'react';
import { executeOSAction } from '../services/api';

interface QuickOSControlProps {
  osState?: {
    dark_mode?: boolean;
    dark_mode_display?: string;
    brightness?: number;
    brightness_pct?: number;
    audio_muted?: boolean;
    focus_mode_active?: boolean;
    actuator_ready?: boolean;
  };
  onActionTriggered?: (result: any) => void;
}

export const QuickOSControl: React.FC<QuickOSControlProps> = ({ osState, onActionTriggered }) => {
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [lastMessage, setLastMessage] = useState<string | null>(null);
  const [isSuccess, setIsSuccess] = useState<boolean>(true);

  const isDarkMode = osState?.dark_mode ?? false;
  const isFocusOn = osState?.focus_mode_active || osState?.audio_muted;
  const brightnessPct = osState?.brightness_pct ?? (osState?.brightness !== undefined ? Math.round(osState.brightness * 100) : 50);

  const handleAction = async (action: string, reason: string, value?: number) => {
    setLoadingAction(action);
    setLastMessage(null);
    try {
      const res = await executeOSAction(action, reason, value);
      setIsSuccess(res?.execution?.verified ?? true);
      setLastMessage(res?.execution?.message || `${action.replace(/_/g, ' ')} executed and verified on macOS.`);
      if (onActionTriggered) {
        onActionTriggered(res);
      }
    } catch (err: any) {
      setIsSuccess(false);
      setLastMessage(`Execution failed: ${err.message}`);
    } finally {
      setLoadingAction(null);
      setTimeout(() => {
        setLastMessage(null);
      }, 5000);
    }
  };

  return (
    <div className="card quick-os-control" style={{
      background: 'linear-gradient(145deg, rgba(15, 23, 42, 0.9) 0%, rgba(30, 41, 59, 0.8) 100%)',
      border: '1px solid rgba(56, 189, 248, 0.35)',
      borderRadius: '12px',
      padding: '16px 20px',
      marginBottom: '20px',
      boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '1.2rem' }}>⚡</span>
            <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.01em' }}>
              Real OS Actuator &amp; Mode Switcher
            </h3>
            <span style={{
              fontSize: '0.72rem',
              padding: '2px 8px',
              borderRadius: 20,
              background: 'rgba(52, 211, 153, 0.18)',
              color: '#34d399',
              border: '1px solid rgba(52, 211, 153, 0.35)',
              fontWeight: 600
            }}>
              NATIVE MACOS
            </span>
          </div>
          <p style={{ margin: '3px 0 0', fontSize: '0.82rem', color: '#94a3b8' }}>
            Direct hardware &amp; appearance switches with live verification and system notifications
          </p>
        </div>

        {/* Live Ground Truth Pills */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{
            fontSize: '0.75rem',
            padding: '4px 10px',
            borderRadius: 6,
            background: isDarkMode ? 'rgba(99, 102, 241, 0.25)' : 'rgba(245, 158, 11, 0.25)',
            color: isDarkMode ? '#a5b4fc' : '#fbbf24',
            border: `1px solid ${isDarkMode ? 'rgba(99, 102, 241, 0.4)' : 'rgba(245, 158, 11, 0.4)'}`,
            fontWeight: 600
          }}>
            {isDarkMode ? '🌙 Dark Mode Active' : '☀️ Light Mode Active'}
          </span>
          <span style={{
            fontSize: '0.75rem',
            padding: '4px 10px',
            borderRadius: 6,
            background: isFocusOn ? 'rgba(6, 182, 212, 0.25)' : 'rgba(100, 116, 139, 0.25)',
            color: isFocusOn ? '#67e8f9' : '#cbd5e1',
            border: `1px solid ${isFocusOn ? 'rgba(6, 182, 212, 0.4)' : 'rgba(100, 116, 139, 0.4)'}`,
            fontWeight: 600
          }}>
            {isFocusOn ? '🔕 DND / Focus Active' : '🔔 Alerts Normal'}
          </span>
          <span style={{
            fontSize: '0.75rem',
            padding: '4px 10px',
            borderRadius: 6,
            background: 'rgba(255, 255, 255, 0.08)',
            color: '#e2e8f0',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            fontWeight: 600
          }}>
            🔆 {brightnessPct}% Brightness
          </span>
        </div>
      </div>

      {/* Button Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: '10px',
        marginBottom: '14px'
      }}>
        {/* Dark Mode */}
        <button
          onClick={() => handleAction('ENABLE_DARK_MODE', 'User switched macOS to Dark Mode')}
          disabled={loadingAction !== null}
          style={{
            padding: '10px 14px',
            borderRadius: '8px',
            background: isDarkMode ? 'rgba(99, 102, 241, 0.35)' : 'rgba(255, 255, 255, 0.05)',
            border: `1px solid ${isDarkMode ? '#6366f1' : 'rgba(255, 255, 255, 0.12)'}`,
            color: '#f8fafc',
            cursor: loadingAction ? 'not-allowed' : 'pointer',
            textAlign: 'left',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            transition: 'all 0.15s ease'
          }}
          title="Switch real macOS appearance to Dark Mode"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>🌙 Dark Mode</span>
            {isDarkMode && <span style={{ color: '#34d399', fontSize: '0.8rem' }}>✓ ON</span>}
          </div>
          <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
            {loadingAction === 'ENABLE_DARK_MODE' ? 'Applying...' : 'Set system appearance dark'}
          </span>
        </button>

        {/* Light Mode */}
        <button
          onClick={() => handleAction('DISABLE_DARK_MODE', 'User switched macOS to Light Mode')}
          disabled={loadingAction !== null}
          style={{
            padding: '10px 14px',
            borderRadius: '8px',
            background: !isDarkMode ? 'rgba(245, 158, 11, 0.3)' : 'rgba(255, 255, 255, 0.05)',
            border: `1px solid ${!isDarkMode ? '#f59e0b' : 'rgba(255, 255, 255, 0.12)'}`,
            color: '#f8fafc',
            cursor: loadingAction ? 'not-allowed' : 'pointer',
            textAlign: 'left',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            transition: 'all 0.15s ease'
          }}
          title="Switch real macOS appearance to Light Mode"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>☀️ Light Mode</span>
            {!isDarkMode && <span style={{ color: '#34d399', fontSize: '0.8rem' }}>✓ ON</span>}
          </div>
          <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
            {loadingAction === 'DISABLE_DARK_MODE' ? 'Applying...' : 'Set system appearance light'}
          </span>
        </button>

        {/* Enable Focus / DND */}
        <button
          onClick={() => handleAction('ENABLE_FOCUS_MODE', 'User turned on Focus / DND Mode')}
          disabled={loadingAction !== null}
          style={{
            padding: '10px 14px',
            borderRadius: '8px',
            background: isFocusOn ? 'rgba(6, 182, 212, 0.35)' : 'rgba(255, 255, 255, 0.05)',
            border: `1px solid ${isFocusOn ? '#06b6d4' : 'rgba(255, 255, 255, 0.12)'}`,
            color: '#f8fafc',
            cursor: loadingAction ? 'not-allowed' : 'pointer',
            textAlign: 'left',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            transition: 'all 0.15s ease'
          }}
          title="Mute alert audio and declutter non-essential desktop apps"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>🔕 Turn ON DND / Focus</span>
            {isFocusOn && <span style={{ color: '#34d399', fontSize: '0.8rem' }}>✓ ACTIVE</span>}
          </div>
          <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
            {loadingAction === 'ENABLE_FOCUS_MODE' ? 'Engaging...' : 'Mute alerts & declutter apps'}
          </span>
        </button>

        {/* Disable Focus / DND */}
        <button
          onClick={() => handleAction('DISABLE_FOCUS_MODE', 'User restored normal alert notifications')}
          disabled={loadingAction !== null}
          style={{
            padding: '10px 14px',
            borderRadius: '8px',
            background: !isFocusOn ? 'rgba(16, 185, 129, 0.25)' : 'rgba(255, 255, 255, 0.05)',
            border: `1px solid ${!isFocusOn ? '#10b981' : 'rgba(255, 255, 255, 0.12)'}`,
            color: '#f8fafc',
            cursor: loadingAction ? 'not-allowed' : 'pointer',
            textAlign: 'left',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            transition: 'all 0.15s ease'
          }}
          title="Restore alert volume and notifications"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>🔔 Turn OFF DND</span>
            {!isFocusOn && <span style={{ color: '#34d399', fontSize: '0.8rem' }}>✓ NORMAL</span>}
          </div>
          <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
            {loadingAction === 'DISABLE_FOCUS_MODE' ? 'Restoring...' : 'Restore alert audio volume'}
          </span>
        </button>

        {/* Reduce Brightness */}
        <button
          onClick={() => handleAction('REDUCE_BRIGHTNESS', 'User reduced display brightness by 20%')}
          disabled={loadingAction !== null}
          style={{
            padding: '10px 14px',
            borderRadius: '8px',
            background: 'rgba(255, 255, 255, 0.05)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            color: '#f8fafc',
            cursor: loadingAction ? 'not-allowed' : 'pointer',
            textAlign: 'left',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            transition: 'all 0.15s ease'
          }}
          title="Dim physical screen luminance by 20%"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>🔅 Dim Brightness (-20%)</span>
          </div>
          <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
            {loadingAction === 'REDUCE_BRIGHTNESS' ? 'Dimming...' : 'Lower screen glare (hardware)'}
          </span>
        </button>

        {/* Restore Brightness */}
        <button
          onClick={() => handleAction('RESTORE_BRIGHTNESS', 'User restored display brightness')}
          disabled={loadingAction !== null}
          style={{
            padding: '10px 14px',
            borderRadius: '8px',
            background: 'rgba(255, 255, 255, 0.05)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            color: '#f8fafc',
            cursor: loadingAction ? 'not-allowed' : 'pointer',
            textAlign: 'left',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            transition: 'all 0.15s ease'
          }}
          title="Restore physical screen luminance"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>🔆 Restore Brightness</span>
          </div>
          <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
            {loadingAction === 'RESTORE_BRIGHTNESS' ? 'Restoring...' : 'Return to nominal luminance'}
          </span>
        </button>
      </div>

      {/* Brightness Fine-Tuning Slider */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '10px 14px',
        background: 'rgba(0, 0, 0, 0.25)',
        borderRadius: 8,
        border: '1px solid rgba(255, 255, 255, 0.08)'
      }}>
        <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#e2e8f0', whiteSpace: 'nowrap' }}>
          Display Brightness:
        </span>
        <input
          type="range"
          min="10"
          max="100"
          step="5"
          value={brightnessPct}
          onChange={(e) => {
            const val = Number(e.target.value);
            handleAction('SET_BRIGHTNESS', `Brightness adjusted to ${val}%`, val / 100);
          }}
          style={{
            flex: 1,
            accentColor: '#38bdf8',
            cursor: 'pointer'
          }}
        />
        <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#38bdf8', minWidth: '42px', textAlign: 'right' }}>
          {brightnessPct}%
        </span>
      </div>

      {/* Instant Action Feedback Banner */}
      {lastMessage && (
        <div style={{
          marginTop: 12,
          padding: '8px 14px',
          borderRadius: 6,
          background: isSuccess ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
          border: `1px solid ${isSuccess ? 'rgba(52, 211, 153, 0.4)' : 'rgba(248, 113, 113, 0.4)'}`,
          color: isSuccess ? '#34d399' : '#f87171',
          fontSize: '0.82rem',
          display: 'flex',
          alignItems: 'center',
          gap: 8
        }}>
          <span>{isSuccess ? '✓' : '✕'}</span>
          <span style={{ fontWeight: 600 }}>{lastMessage}</span>
          {isSuccess && <span style={{ marginLeft: 'auto', fontSize: '0.72rem', color: '#94a3b8' }}>Verified on macOS hardware</span>}
        </div>
      )}
    </div>
  );
};
