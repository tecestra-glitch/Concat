"use client";
/**
 * Live updates: initial snapshot, SSE with cursor replay, reconnection without
 * duplicate connections, periodic snapshot fallback. Connection state is kept
 * separate from quote age (a connected stream does not make an old quote fresh).
 */
import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { API_URL, api } from "./api/client";
import type { Quote, Snapshot, Source, StreamEvent } from "./api/types";
import { useSettings } from "./settings";

export type ConnState = "connected" | "reconnecting" | "offline" | "demo";

interface LiveCtx {
  state: ConnState;
  lastEventAt: string | null;
  eventsReceived: number;
  lastHeartbeatAt: string | null;
}

const LiveContext = React.createContext<LiveCtx>({ state: "demo", lastEventAt: null, eventsReceived: 0, lastHeartbeatAt: null });

export function LiveProvider({ children }: { children: React.ReactNode }) {
  const { mode, settings } = useSettings();
  const qc = useQueryClient();
  const [connState, setState] = React.useState<ConnState>("reconnecting");
  const state: ConnState = mode === "demo" || !API_URL ? "demo" : connState;
  const [lastEventAt, setLastEventAt] = React.useState<string | null>(null);
  const [lastHeartbeatAt, setLastHeartbeatAt] = React.useState<string | null>(null);
  const [eventsReceived, setEventsReceived] = React.useState(0);
  const cursorRef = React.useRef<string | null>(null);
  const seenRef = React.useRef<Set<string>>(new Set());
  const esRef = React.useRef<EventSource | null>(null);
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = React.useRef(0);

  const applySnapshot = React.useCallback(
    (snap: Snapshot) => {
      cursorRef.current = snap.cursor;
      seenRef.current.clear();
      qc.setQueryData(["sources", "real"], snap.sources);
      qc.setQueryData(["quotes", "real", "snapshot"], snap.quotes);
      qc.setQueryData(["opportunities", "real", undefined], snap.opportunities);
      qc.invalidateQueries({ queryKey: ["quotes"] });
    },
    [qc],
  );

  const applyEvent = React.useCallback(
    (ev: StreamEvent) => {
      if (seenRef.current.has(ev.id)) return; // replay dedupe
      seenRef.current.add(ev.id);
      if (seenRef.current.size > 5000) seenRef.current = new Set([...seenRef.current].slice(-2500));
      cursorRef.current = ev.id;
      setEventsReceived((n) => n + 1);
      if (ev.type === "heartbeat") {
        setLastHeartbeatAt(ev.ts);
        return;
      }
      setLastEventAt(ev.ts);
      if (ev.type === "quote.updated") {
        const q = ev.payload as Quote;
        qc.setQueriesData<Quote[]>({ queryKey: ["quotes", "real"] }, (old) => {
          if (!old) return old;
          const idx = old.findIndex((x) => x.id === q.id || (x.source_id === q.source_id && x.branch_id === q.branch_id && x.base === q.base && x.quote === q.quote && x.modality === q.modality && x.amount_base === q.amount_base && JSON.stringify(x.context) === JSON.stringify(q.context)));
          if (idx === -1) return [...old, q];
          const next = old.slice();
          next[idx] = q;
          return next;
        });
        qc.invalidateQueries({ queryKey: ["history"] });
      } else if (ev.type === "source.health") {
        const s = ev.payload as Source;
        qc.setQueryData<Source[]>(["sources", "real"], (old) => (old ? old.map((x) => (x.id === s.id ? s : x)) : old));
      } else if (ev.type === "opportunity.updated") {
        qc.invalidateQueries({ queryKey: ["opportunities"] });
      }
    },
    [qc],
  );

  React.useEffect(() => {
    if (mode === "demo" || !API_URL) return;
    let disposed = false;

    const closeEs = () => {
      esRef.current?.close();
      esRef.current = null;
    };

    const connect = async (fresh: boolean) => {
      if (disposed || esRef.current) return; // never open duplicate connections
      try {
        if (fresh || !cursorRef.current) {
          const snap = await api.snapshot("real");
          if (disposed) return;
          applySnapshot(snap);
        }
      } catch {
        if (disposed) return;
        setState("offline");
        schedule();
        return;
      }
      const es = new EventSource(api.streamUrl(cursorRef.current));
      esRef.current = es;
      es.onopen = () => {
        attemptRef.current = 0;
        setState("connected");
      };
      es.onmessage = (m) => {
        try {
          const ev = JSON.parse(m.data) as StreamEvent;
          if (!ev.id && m.lastEventId) ev.id = m.lastEventId;
          applyEvent(ev);
        } catch {
          /* ignore malformed */
        }
      };
      es.onerror = () => {
        // Browser auto-retry would duplicate our own schedule; close and own the backoff.
        closeEs();
        if (disposed) return;
        setState("reconnecting");
        schedule();
      };
    };

    const schedule = () => {
      if (timerRef.current) return; // one pending reconnect at a time
      const delay = Math.min(30000, 1000 * 2 ** Math.min(attemptRef.current, 5));
      attemptRef.current += 1;
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        // Cursor may have expired (410) — the server rejects it; we detect via snapshot path.
        void connect(attemptRef.current > 3);
      }, delay);
    };

    void connect(true);

    // Snapshot fallback every N seconds keeps data moving even if SSE is blocked by a proxy.
    const fallback = setInterval(() => {
      if (disposed) return;
      api
        .snapshot("real")
        .then((snap) => {
          if (!esRef.current) applySnapshot(snap);
        })
        .catch(() => setState((s) => (s === "connected" ? s : "offline")));
    }, Math.max(10, settings.pollFallbackSeconds) * 1000);

    const onVisibility = () => {
      if (document.visibilityState === "visible" && !esRef.current && !timerRef.current) void connect(false);
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      disposed = true;
      closeEs();
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
      clearInterval(fallback);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [mode, settings.pollFallbackSeconds, applySnapshot, applyEvent]);

  const value = React.useMemo<LiveCtx>(() => ({ state, lastEventAt, eventsReceived, lastHeartbeatAt }), [state, lastEventAt, eventsReceived, lastHeartbeatAt]);
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLive(): LiveCtx {
  return React.useContext(LiveContext);
}
