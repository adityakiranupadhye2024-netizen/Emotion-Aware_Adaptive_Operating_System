import { useEffect, useState, useRef } from 'react';
import { connectLive, getState } from '../services/api';
import { LiveState } from '../types';

export function useEAOS() {
  const [state, setState] = useState<LiveState | null>(() => {
    try {
      const saved = localStorage.getItem('eaos_last_state');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [online, setOnline] = useState(false);
  const onlineRef = useRef(false);
  onlineRef.current = online;

  useEffect(() => {
    let wsHandle: any = null;
    let pollTimer: any = null;
    let localTickTimer: any = null;

    const fetchStateImmediate = async () => {
      try {
        const d = await getState();
        setState(d);
        setOnline(true);
        try {
          localStorage.setItem('eaos_last_state', JSON.stringify(d));
        } catch {}
      } catch {
        if (!onlineRef.current) {
          setOnline(false);
        }
      }
    };

    // 1. Initial immediate fetch
    fetchStateImmediate();

    // 2. Fast HTTP polling fallback (every 500ms when offline for instant reconnection)
    pollTimer = setInterval(() => {
      if (!onlineRef.current) {
        fetchStateImmediate();
      }
    }, 500);

    // 3. WebSocket Real-time live stream
    wsHandle = connectLive(
      (d) => {
        setState(d);
        setOnline(true);
        try {
          localStorage.setItem('eaos_last_state', JSON.stringify(d));
        } catch {}
      },
      (isOk) => {
        setOnline(isOk);
      }
    );

    // 4. Smooth 1Hz wall-clock countdown timer tick
    localTickTimer = setInterval(() => {
      setState((prev) => {
        if (!prev || !prev.cycle) return prev;
        const c = prev.cycle;
        const total = c.cycle_duration_seconds || 60;

        let newRemaining: number;
        if (c.next_processing_time) {
          const targetMs = new Date(c.next_processing_time).getTime();
          const diffSec = Math.max(0, Math.round((targetMs - Date.now()) / 1000));
          newRemaining = diffSec;
          if (diffSec === 0) {
            // Reached phase boundary: fetch new phase state immediately
            fetchStateImmediate();
          }
        } else {
          const currentRemaining = c.remaining_seconds ?? 60;
          newRemaining = Math.max(0, currentRemaining - 1);
        }

        const newElapsed = Math.min(total, Math.max(0, total - newRemaining));

        if (newRemaining === c.remaining_seconds && newElapsed === c.elapsed_seconds) {
          return prev;
        }

        return {
          ...prev,
          cycle: {
            ...c,
            remaining_seconds: newRemaining,
            elapsed_seconds: newElapsed
          }
        };
      });
    }, 1000);

    return () => {
      clearInterval(pollTimer);
      clearInterval(localTickTimer);
      wsHandle?.close();
    };
  }, []);

  return { state, online };
}
