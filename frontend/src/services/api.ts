const BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8765';

export async function getHealth() {
  const r = await fetch(`${BASE}/api/v1/health`);
  if (!r.ok) throw new Error('Backend offline');
  return r.json();
}

export async function getState() {
  const r = await fetch(`${BASE}/api/v1/state/current`);
  if (!r.ok) throw new Error('Backend offline');
  return r.json();
}

export async function getOSState() {
  const r = await fetch(`${BASE}/api/v1/os/state`);
  if (!r.ok) throw new Error('Failed to query real OS state');
  return r.json();
}

export async function getCurrentCycle() {
  const r = await fetch(`${BASE}/api/v1/cycle/current`);
  if (!r.ok) throw new Error('Backend offline');
  return r.json();
}

export async function getDecisions() {
  const r = await fetch(`${BASE}/api/v1/decisions/recent`);
  if (!r.ok) throw new Error('Backend offline');
  return r.json();
}

export async function getDecisionById(id: number) {
  const r = await fetch(`${BASE}/api/v1/decisions/${id}`);
  if (!r.ok) throw new Error(`Decision ${id} not found`);
  return r.json();
}

export async function sendFeedback(id: number, feedback: string) {
  const r = await fetch(`${BASE}/api/v1/decisions/${id}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ feedback }),
  });
  if (!r.ok) throw new Error('Failed to record feedback');
  return r.json();
}

export const sendDecisionFeedback = sendFeedback;


export async function getAnalytics() {
  const r = await fetch(`${BASE}/api/v1/analytics/timeline`);
  if (!r.ok) throw new Error('Backend offline');
  return r.json();
}

export async function getAnalyticsSummary(period: string = 'all') {
  const r = await fetch(`${BASE}/api/v1/analytics/summary?period=${encodeURIComponent(period)}`);
  if (!r.ok) throw new Error('Failed to fetch analytics summary');
  return r.json();
}

export async function getTypingSpeedAnalytics(period: string = 'all') {
  const r = await fetch(`${BASE}/api/v1/analytics/typing-speed?period=${encodeURIComponent(period)}`);
  if (!r.ok) throw new Error('Failed to fetch typing analytics');
  return r.json();
}

export async function getEmotionAnalytics(period: string = 'all') {
  const r = await fetch(`${BASE}/api/v1/analytics/emotions?period=${encodeURIComponent(period)}`);
  if (!r.ok) throw new Error('Failed to fetch emotion analytics');
  return r.json();
}

export async function getWorkloadAnalytics(period: string = 'all') {
  const r = await fetch(`${BASE}/api/v1/analytics/workload?period=${encodeURIComponent(period)}`);
  if (!r.ok) throw new Error('Failed to fetch workload analytics');
  return r.json();
}

export async function getAdaptiveScoreAnalytics(period: string = 'all') {
  const r = await fetch(`${BASE}/api/v1/analytics/adaptive-score?period=${encodeURIComponent(period)}`);
  if (!r.ok) throw new Error('Failed to fetch AS analytics');
  return r.json();
}

export async function getDisplayModeAnalytics() {
  const r = await fetch(`${BASE}/api/v1/analytics/display-mode`);
  if (!r.ok) throw new Error('Failed to fetch display mode analytics');
  return r.json();
}

export async function getDNDAnalytics() {
  const r = await fetch(`${BASE}/api/v1/analytics/dnd`);
  if (!r.ok) throw new Error('Failed to fetch DND analytics');
  return r.json();
}

export async function getCameraAnalytics() {
  const r = await fetch(`${BASE}/api/v1/analytics/camera`);
  if (!r.ok) throw new Error('Failed to fetch camera analytics');
  return r.json();
}

export async function getSettings() {
  const r = await fetch(`${BASE}/api/v1/settings`);
  if (!r.ok) throw new Error('Backend offline');
  return r.json();
}

export async function saveSettings(settings: Record<string, any>) {
  const r = await fetch(`${BASE}/api/v1/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  if (!r.ok) throw new Error('Failed to update settings');
  return r.json();
}

export async function getDiagnostics() {
  const r = await fetch(`${BASE}/api/v1/diagnostics`);
  if (!r.ok) throw new Error('Backend offline');
  return r.json();
}

export async function resetPersonalBaseline() {
  const r = await fetch(`${BASE}/api/v1/profile/reset`, { method: 'POST' });
  if (!r.ok) throw new Error('Failed to reset personal baseline');
  return r.json();
}

export async function resetSystem() {
  const r = await fetch(`${BASE}/api/v1/actions/reset`, { method: 'POST' });
  if (!r.ok) throw new Error('Failed to reset system');
  return r.json();
}

export async function getCurrentContext() {
  const r = await fetch(`${BASE}/api/v1/context/current`);
  if (!r.ok) throw new Error('Failed to fetch current context');
  return r.json();
}

export async function getContextHistory(limit: number = 50) {
  const r = await fetch(`${BASE}/api/v1/context/history?limit=${limit}`);
  if (!r.ok) throw new Error('Failed to fetch context history');
  return r.json();
}

export async function getAdaptationEffectiveness() {
  const r = await fetch(`${BASE}/api/v1/adaptations/effectiveness`);
  if (!r.ok) throw new Error('Failed to fetch effectiveness statistics');
  return r.json();
}

export async function getPolicyStatus() {
  const r = await fetch(`${BASE}/api/v1/policy/status`);
  if (!r.ok) throw new Error('Failed to fetch policy status');
  return r.json();
}

export async function getPrivacyStatus() {
  const r = await fetch(`${BASE}/api/v1/privacy/status`);
  if (!r.ok) throw new Error('Failed to fetch privacy status');
  return r.json();
}

export async function togglePrivacyPause(paused: boolean) {
  const r = await fetch(`${BASE}/api/v1/privacy/pause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paused }),
  });
  if (!r.ok) throw new Error('Failed to toggle monitoring pause');
  return r.json();
}

export async function clearHistory() {
  const r = await fetch(`${BASE}/api/v1/privacy/clear-history`, {
    method: 'POST'
  });
  if (!r.ok) throw new Error('Failed to purge history');
  return r.json();
}

export async function applyDataRetention(retention_period: string) {
  const r = await fetch(`${BASE}/api/v1/privacy/retention`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ retention_period }),
  });
  if (!r.ok) throw new Error('Failed to apply data retention');
  return r.json();
}

export async function updatePrivacySettings(payload: any) {
  const r = await fetch(`${BASE}/api/v1/privacy/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error('Failed to update privacy settings');
  return r.json();
}

export async function getSystemStatus() {
  const r = await fetch(`${BASE}/api/v1/system/status`);
  if (!r.ok) throw new Error('Failed to fetch system status');
  return r.json();
}

export async function executeOSAction(action: string, reason?: string, value?: number) {
  const r = await fetch(`${BASE}/api/v1/actions/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, reason, value }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: 'Action execution failed' }));
    throw new Error(err.detail || 'Action execution failed');
  }
  return r.json();
}


export function connectLive(onData: (d: any) => void, onStatus: (ok: boolean) => void) {
  const wsUrl = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8765/ws/live-state';
  let ws: WebSocket | null = null;
  let timer: any = null;
  let isClosed = false;

  function connect() {
    if (isClosed) return;
    try {
      if (ws) {
        try { ws.close(); } catch {}
      }
      ws = new WebSocket(wsUrl);
      ws.onopen = () => {
        onStatus(true);
      };
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          onData(data);
          onStatus(true);
        } catch (err) {
          console.error("WS parse error", err);
        }
      };
      ws.onclose = () => {
        onStatus(false);
        if (!isClosed) {
          clearTimeout(timer);
          timer = setTimeout(connect, 600);
        }
      };
      ws.onerror = () => {
        onStatus(false);
        ws?.close();
      };
    } catch {
      onStatus(false);
      if (!isClosed) {
        clearTimeout(timer);
        timer = setTimeout(connect, 600);
      }
    }
  }

  const handleVisibilityOrFocus = () => {
    if (document.visibilityState === 'visible' && (!ws || ws.readyState !== WebSocket.OPEN)) {
      clearTimeout(timer);
      connect();
    }
  };

  window.addEventListener('focus', handleVisibilityOrFocus);
  window.addEventListener('online', handleVisibilityOrFocus);
  document.addEventListener('visibilitychange', handleVisibilityOrFocus);

  connect();

  return {
    close: () => {
      isClosed = true;
      clearTimeout(timer);
      window.removeEventListener('focus', handleVisibilityOrFocus);
      window.removeEventListener('online', handleVisibilityOrFocus);
      document.removeEventListener('visibilitychange', handleVisibilityOrFocus);
      if (ws) ws.close();
    }
  };
}
