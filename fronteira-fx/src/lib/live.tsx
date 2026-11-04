"use client";
/**
 * Live updates (plan F6): initial snapshot, SSE with cursor replay, reconnection without duplicate
 * connections, and periodic snapshot polling only as a fallback while the stream is down.
 * Connection state is kept separate from quote age (a connected stream does not make an old quote fresh).
 * React state changes only inside event callbacks and promise handlers, never in the effect body.
 */
import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "./api/client";
import { type ParsedStreamEvent, QuoteSchema } from "./api/schemas";
import type { AlertEvent } from "./api/watch";
import { alertToasts } from "./alert-toasts";
import { applyQuoteUpdate, applySnapshot, applySourceHealthEvent, parseStreamFrame, shouldResetCursor } from "./live-cache";
import { useSettings } from "./settings";
import { probeStreamOff } from "./stream-probe";

/**
 * `scheduled`: atualização por consulta periódica, sem stream aberto. Vale quando o servidor fecha a conexão
 * depois de abrir e quando a API desligou o stream (404 na Vercel): o site passa a consultar o snapshot a cada
 * `pollFallbackSeconds`. Não é erro: o selo diz "Ao vivo · atualiza a cada 30 s". `reconnecting` só vale para
 * falha real sem abrir; `connecting` é só a primeira tentativa, antes de qualquer resposta.
 */
export type ConnState = "connecting" | "connected" | "scheduled" | "reconnecting" | "offline" | "demo";

interface LiveCtx {
  state: ConnState;
  lastEventAt: string | null;
  eventsReceived: number;
  lastHeartbeatAt: string | null;
}

const LiveContext = React.createContext<LiveCtx>({ state: "demo", lastEventAt: null, eventsReceived: 0, lastHeartbeatAt: null });

function isAlertEvent(p: unknown): p is AlertEvent {
  if (typeof p !== "object" || p === null) return false;
  const o = p as Record<string, unknown>;
  return typeof o.id === "string" && typeof o.rule_id === "string" && typeof o.message === "string" && typeof o.ts === "string";
}

export function LiveProvider({ children }: { children: React.ReactNode }) {
  const { mode, settings } = useSettings();
  const qc = useQueryClient();
  const [connState, setState] = React.useState<ConnState>("connecting"); // primeira tentativa: ainda não falhou
  const state: ConnState = mode === "demo" ? "demo" : connState;
  const [lastEventAt, setLastEventAt] = React.useState<string | null>(null);
  const [lastHeartbeatAt, setLastHeartbeatAt] = React.useState<string | null>(null);
  const [eventsReceived, setEventsReceived] = React.useState(0);
  const cursorRef = React.useRef<string | null>(null);
  const seenRef = React.useRef<Set<string>>(new Set());
  const esRef = React.useRef<EventSource | null>(null);
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = React.useRef(0);
  const openedRef = React.useRef(false); // a conexão atual chegou a abrir (onopen)
  const streamOffRef = React.useRef(false); // a API respondeu 404 no stream: só consulta periódica

  React.useEffect(() => {
    if (mode === "demo") return;
    let disposed = false;
    streamOffRef.current = false;

    const closeEs = () => {
      esRef.current?.close();
      esRef.current = null;
    };

    const takeSnapshot = async () => {
      const snap = await api.snapshot(mode);
      if (disposed) return;
      applySnapshot(qc, mode, snap);
      cursorRef.current = snap.cursor;
      seenRef.current.clear();
    };

    const dispatch = (ev: ParsedStreamEvent) => {
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
      switch (ev.type) {
        case "quote.updated": {
          const parsed = QuoteSchema.safeParse(ev.payload);
          if (parsed.success) applyQuoteUpdate(qc, mode, parsed.data);
          break;
        }
        case "source.health":
          applySourceHealthEvent(qc, mode, ev.payload);
          break;
        case "opportunity.updated":
          void qc.invalidateQueries({ queryKey: ["opportunities", mode] });
          void qc.invalidateQueries({ queryKey: ["cycles", mode] });
          break;
        case "source.change":
          void qc.invalidateQueries({ queryKey: ["watch"] });
          break;
        case "market.news":
        case "market.volatility_alert":
          // módulo market: só a leitura da tela Economia é recarregada (referência, nunca cotação executável)
          void qc.invalidateQueries({ queryKey: ["market", mode] });
          break;
        case "alert.fired":
          void qc.invalidateQueries({ queryKey: ["alerts"] });
          if (isAlertEvent(ev.payload) && (!ev.payload.data_mode || ev.payload.data_mode === mode)) alertToasts.push(ev.payload);
          break;
      }
    };

    const connect = async (fresh: boolean) => {
      if (disposed || esRef.current) return; // never open duplicate connections
      try {
        if (fresh || !cursorRef.current || streamOffRef.current) await takeSnapshot();
        if (disposed) return;
      } catch {
        if (disposed) return;
        setState("offline");
        if (!streamOffRef.current) schedule();
        return;
      }
      if (streamOffRef.current) {
        setState("scheduled"); // sem stream nesta API: o intervalo abaixo consulta o snapshot
        return;
      }
      const url = api.streamUrl(mode, cursorRef.current);
      const es = new EventSource(url);
      esRef.current = es;
      es.onopen = () => {
        attemptRef.current = 0;
        openedRef.current = true;
        setState("connected");
      };
      es.onmessage = (m: MessageEvent<string>) => {
        const ev = parseStreamFrame(m.data, m.lastEventId);
        if (ev) dispatch(ev);
      };
      es.onerror = () => {
        // A closed source means the server refused the request (e.g. 410 Gone: cursor expired):
        // forget the cursor so the next attempt starts from a fresh snapshot.
        if (shouldResetCursor(es.readyState)) cursorRef.current = null;
        // Browser auto-retry would duplicate our own schedule; close and own the backoff.
        closeEs();
        if (disposed) return;
        // Caiu depois de abrir: fechamento programado do servidor, não erro. Sem abrir: falha real.
        const wasOpen = openedRef.current;
        openedRef.current = false;
        if (wasOpen) {
          setState("scheduled");
          schedule();
          return;
        }
        // Nem abriu: pergunta à API se o stream foi desligado (404) antes de entrar no recuo de reconexão.
        void probeStreamOff(url).then((off) => {
          if (disposed) return;
          if (off) {
            streamOffRef.current = true;
            setState("scheduled");
            return;
          }
          setState("reconnecting");
          schedule();
        });
      };
    };

    const schedule = () => {
      if (timerRef.current) return; // one pending reconnect at a time
      const delay = Math.min(30000, 1000 * 2 ** Math.min(attemptRef.current, 5));
      attemptRef.current += 1;
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        void connect(attemptRef.current > 3);
      }, delay);
    };

    void connect(true);

    // Polling is only a fallback: while the stream is open the snapshot is skipped.
    const fallback = setInterval(() => {
      if (disposed || esRef.current) return;
      takeSnapshot()
        .then(() => {
          if (!disposed && streamOffRef.current) setState("scheduled"); // volta de "offline" quando a API responde
        })
        .catch(() => {
          if (!disposed) setState((s) => (s === "connected" ? s : "offline"));
        });
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
  }, [mode, settings.pollFallbackSeconds, qc]);

  const value = React.useMemo<LiveCtx>(() => ({ state, lastEventAt, eventsReceived, lastHeartbeatAt }), [state, lastEventAt, eventsReceived, lastHeartbeatAt]);
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLive(): LiveCtx {
  return React.useContext(LiveContext);
}
