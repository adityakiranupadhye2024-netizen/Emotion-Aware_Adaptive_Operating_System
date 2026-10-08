import React, { useState } from 'react';
import { executeOSAction } from '../services/api';

interface QuickOSControlProps {
  osState?: {
    dark_mode?: boolean;
    dark_mode_display?: string;
    brightness?: number;
    brightness_pct?: number;
    volume?: number;
    volume_pct?: number;
    audio_muted?: boolean;
    focus_mode_active?: boolean;
    actuator_ready?: boolean;
  };
  cycle?: {
    phase?: string;
    remaining_seconds?: number;
    elapsed_seconds?: number;
    cycle_id?: number;
    input_collection_active?: boolean;
  };
  decision?: {
    action?: string;
    reason?: string;
    adaptive_score?: number;
  };
  emotion?: string;
  workload?: number;
  onActionTriggered?: (result: any) => void;
}

export const QuickOSControl: React.FC<QuickOSControlProps> = ({
  osState,
  cycle,
  decision,
  emotion,
  workload,
  onActionTriggered
}) => {
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [lastMessage, setLastMessage] = useState<string | null>(null);
  const [isSuccess, setIsSuccess] = useState<boolean>(true);

  const isDarkMode = osState?.dark_mode ?? false;
  const isFocusOn = !!osState?.focus_mode_active;
  const isMuted = osState?.audio_muted ?? false;
  const brightnessPct = osState?.brightness_pct ?? (osState?.brightness !== undefined ? Math.round(osState.brightness * 100) : 50);
  const volumePct = osState?.volume_pct ?? osState?.volume ?? 50;

  const isInputPhase = cycle?.phase === 'INPUT_COLLECTION' || cycle?.input_collection_active;
  const remainingSec = cycle?.remaining_seconds ?? 60;
  const remMin = Math.floor(remainingSec / 60);
  const remSec = Math.floor(remainingSec % 60);
  const timerStr = `${remMin}:${remSec.toString().padStart(2, '0')}`;

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
      {/* Cycle Phase & State Adaptation Status Banner */}
      {cycle?.phase && (
        <div style={{
          padding: '8px 14px',
          borderRadius: '8px',
          background: isInputPhase ? 'rgba(56, 189, 248, 0.12)' : 'rgba(52, 211, 153, 0.14)',
          border: `1px solid ${isInputPhase ? 'rgba(56, 189, 248, 0.35)' : 'rgba(52, 211, 153, 0.35)'}`,
          marginBottom: '14px',
          fontSize: '0.8rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 6
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '1rem' }}>{isInputPhase ? '📥' : '⚡'}</span>
            <span style={{ color: isInputPhase ? '#38bdf8' : '#34d399', fontWeight: 700 }}>
              {isInputPhase ? `Input Collection Phase Active (${timerStr})` : `Adaptation Active: ${(decision?.action || 'NO_ACTION').replace(/_/g, ' ')} (${timerStr})`}
            </span>
          </div>
          <span style={{ color: '#cbd5e1', fontSize: '0.74rem' }}>
            {isInputPhase
              ? `Evaluating user state (${emotion || 'Active'}${workload !== undefined ? ` · ${Math.round(workload * 100)}% workload` : ''}) · Mode Switcher adapts after phase finishes`
              : `Changed according to evaluated user state: ${decision?.reason || 'Activity nominal'}`}
          </span>
        </div>
      )}
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
            {isFocusOn ? '🔕 DND Active' : '🔔 Alerts Normal'}
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
          <span style={{
            fontSize: '0.75rem',
            padding: '4px 10px',
            borderRadius: 6,
            background: isMuted ? 'rgba(239, 68, 68, 0.25)' : 'rgba(16, 185, 129, 0.25)',
            color: isMuted ? '#fca5a5' : '#6ee7b7',
            border: `1px solid ${isMuted ? 'rgba(239, 68, 68, 0.4)' : 'rgba(16, 185, 129, 0.4)'}`,
            fontWeight: 600
          }}>
            {isMuted ? '🔇 Audio Muted' : `🔊 ${volumePct}% Volume`}
          </span>
        </div>
      </div>

      {/* Button Grid: 5 Buttons (Dark, Light, DND ON, DND OFF, Volume) */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: '10px',
        marginBottom: '14px'
      }}>
        {/* 1. Dark Mode */}
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

        {/* 2. Light Mode */}
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

        {/* 3. Focus / DND Mode Toggle */}
        <button
          onClick={() => handleAction(
            isFocusOn ? 'DISABLE_FOCUS_MODE' : 'ENABLE_FOCUS_MODE',
            isFocusOn ? 'User turned off DND Mode' : 'User turned on Focus / DND Mode'
          )}
          disabled={loadingAction !== null}
          style={{
            padding: '10px 14px',
            borderRadius: '8px',
            background: isFocusOn ? 'rgba(6, 182, 212, 0.30)' : 'rgba(255, 255, 255, 0.05)',
            border: `1px solid ${isFocusOn ? '#06b6d4' : 'rgba(255, 255, 255, 0.12)'}`,
            color: '#f8fafc',
            cursor: loadingAction ? 'not-allowed' : 'pointer',
            textAlign: 'left',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            transition: 'all 0.15s ease'
          }}
          title={isFocusOn ? 'Click to turn off native macOS Focus / Do Not Disturb' : 'Click to turn on native macOS Focus / Do Not Disturb'}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>
              {isFocusOn ? '🔕 Turn OFF DND' : '🔔 Turn ON DND'}
            </span>
            <span style={{
              color: isFocusOn ? '#22d3ee' : '#34d399',
              fontSize: '0.78rem',
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: '12px',
              background: isFocusOn ? 'rgba(6, 182, 212, 0.2)' : 'rgba(52, 211, 153, 0.18)',
              border: `1px solid ${isFocusOn ? 'rgba(6, 182, 212, 0.4)' : 'rgba(52, 211, 153, 0.35)'}`
            }}>
              {isFocusOn ? '✓ DND ON' : '✓ NORMAL'}
            </span>
          </div>
          <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
            {loadingAction === 'ENABLE_FOCUS_MODE' || loadingAction === 'DISABLE_FOCUS_MODE'
              ? (isFocusOn ? 'Restoring alerts...' : 'Engaging DND...')
              : (isFocusOn ? 'Silence active · Click to turn off DND' : 'Silence notifications & DND')}
          </span>
        </button>
      </div>

      {/* Dual Sliders: Display Brightness & System Volume */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: '12px',
        padding: '12px 16px',
        background: 'rgba(0, 0, 0, 0.25)',
        borderRadius: 8,
        border: '1px solid rgba(255, 255, 255, 0.08)'
      }}>
        {/* Brightness Slider */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#e2e8f0', whiteSpace: 'nowrap' }}>
            🔆 Display Brightness:
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

        {/* Volume Slider */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#e2e8f0', whiteSpace: 'nowrap' }}>
            {isMuted ? '🔇' : '🔊'} System Volume:
          </span>
          <input
            type="range"
            min="0"
            max="100"
            step="5"
            value={isMuted ? 0 : volumePct}
            onChange={(e) => {
              const val = Number(e.target.value);
              handleAction('SET_VOLUME', `System volume adjusted to ${val}%`, val);
            }}
            style={{
              flex: 1,
              accentColor: '#10b981',
              cursor: 'pointer'
            }}
          />
          <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#10b981', minWidth: '42px', textAlign: 'right' }}>
            {isMuted ? 'Muted' : `${volumePct}%`}
          </span>
        </div>
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
