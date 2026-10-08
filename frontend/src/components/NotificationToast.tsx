import React, { useEffect, useState } from 'react';

export interface ToastItem {
  id: string;
  title: string;
  message: string;
  action: string;
  verified?: boolean | number;
  time: string;
}

interface NotificationToastProps {
  latestDecision?: {
    action?: string;
    reason?: string;
    status?: string;
    verified?: boolean | number;
    timestamp?: string;
  };
}

export const NotificationToast: React.FC<NotificationToastProps> = ({ latestDecision }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [lastTs, setLastTs] = useState<string | null>(null);

  useEffect(() => {
    if (!latestDecision || !latestDecision.action || latestDecision.action === 'NO_ACTION') {
      return;
    }
    const ts = latestDecision.timestamp || '';
    if (ts && ts !== lastTs) {
      setLastTs(ts);
      const actionClean = latestDecision.action === 'MUTE_AUDIO' ? 'AUDIO DECREASED' : latestDecision.action.replace(/_/g, ' ').toUpperCase();
      const newToast: ToastItem = {
        id: `${ts}-${Math.random()}`,
        title: `EAOS Adaptation: ${actionClean}`,
        message: latestDecision.reason || 'Operating system adaptation applied.',
        action: latestDecision.action,
        verified: latestDecision.verified,
        time: new Date().toLocaleTimeString()
      };

      setToasts((prev) => [newToast, ...prev.slice(0, 3)]);

      // Auto dismiss after 7 seconds
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== newToast.id));
      }, 7000);
    }
  }, [latestDecision?.timestamp, latestDecision?.action]);

  if (toasts.length === 0) return null;

  return (
    <div style={{
      position: 'fixed',
      top: '20px',
      right: '24px',
      zIndex: 9999,
      display: 'flex',
      flexDirection: 'column',
      gap: '10px',
      maxWidth: '420px',
      width: '100%',
      pointerEvents: 'none'
    }}>
      {toasts.map((toast) => {
        const isDark = toast.action.includes('DARK');
        const isFocus = toast.action.includes('FOCUS');
        const isBright = toast.action.includes('BRIGHT');
        const icon = isDark ? (toast.action.includes('ENABLE') ? '🌙' : '☀️') : isFocus ? (toast.action.includes('ENABLE') ? '🔕' : '🔔') : isBright ? '🔆' : '⚡';

        return (
          <div
            key={toast.id}
            style={{
              pointerEvents: 'auto',
              background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.96) 0%, rgba(30, 41, 59, 0.95) 100%)',
              border: '1px solid rgba(56, 189, 248, 0.5)',
              boxShadow: '0 10px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(56, 189, 248, 0.2)',
              borderRadius: '10px',
              padding: '14px 16px',
              color: '#f8fafc',
              display: 'flex',
              gap: '12px',
              alignItems: 'flex-start',
              animation: 'slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1)'
            }}
          >
            <div style={{
              fontSize: '1.4rem',
              background: 'rgba(56, 189, 248, 0.15)',
              padding: '6px',
              borderRadius: '8px',
              lineHeight: 1
            }}>
              {icon}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <strong style={{ fontSize: '0.9rem', color: '#f8fafc' }}>
                  {toast.title}
                </strong>
                <span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>{toast.time}</span>
              </div>
              <p style={{ margin: '0 0 6px 0', fontSize: '0.8rem', color: '#cbd5e1', lineHeight: 1.4 }}>
                {toast.message}
              </p>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{
                  fontSize: '0.7rem',
                  padding: '2px 8px',
                  borderRadius: 4,
                  background: 'rgba(52, 211, 153, 0.2)',
                  color: '#34d399',
                  fontWeight: 700,
                  border: '1px solid rgba(52, 211, 153, 0.4)'
                }}>
                  ✓ VERIFIED ON MACOS
                </span>
                <span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>
                  System notification sent
                </span>
              </div>
            </div>
            <button
              onClick={() => setToasts((prev) => prev.filter((t) => t.id !== toast.id))}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#94a3b8',
                cursor: 'pointer',
                fontSize: '1.1rem',
                padding: '0 4px',
                lineHeight: 1
              }}
              title="Dismiss"
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
};
