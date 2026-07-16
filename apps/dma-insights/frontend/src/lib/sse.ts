/**
 * SSE client — wraps `EventSource` with auto-reconnect (1s backoff capped at
 * 30s) and typed event parsing via `eventsource-parser` when we receive
 * non-default named events from the backend.
 *
 * Server-sent named events are dispatched to same-named handlers. The
 * backend SSE layer (app/routers/sse.py) emits these control events in
 * addition to the per-surface payload events (`token`/`done`/`fallback`/…):
 *   - `reconnect`   — the server is closing the stream deliberately
 *                     (MAX_STREAM_SECONDS age cap); we auto-reconnect.
 *   - `error`       — server-side failure (e.g. `redis_unavailable`);
 *                     the stream closes and we auto-reconnect.
 *   - `stream_idle` — the channel has been silent ~30s; informational.
 *
 * Reserved SYNTHETIC handler names (invoked by this wrapper, never sent
 * by the server — the `__` prefix guarantees no collision):
 *   - `__reconnecting` — the connection dropped (network error, non-ok
 *                        status, or server-side close) and a retry is
 *                        scheduled. Wire this to a "Reconnecting…" note.
 *   - `__connected`    — a connection (re)opened successfully.
 */
import { createParser, EventSourceMessage } from "eventsource-parser";

export interface SseHandlerMap {
  [eventName: string]: (data: string) => void;
}

export interface SseSubscription {
  close: () => void;
  isOpen: () => boolean;
}

export function subscribeSSE(url: string, handlers: SseHandlerMap): SseSubscription {
  let closed = false;
  let reconnectDelay = 1000;
  let abortCtrl: AbortController | null = null;

  const connect = async () => {
    if (closed) return;
    abortCtrl = new AbortController();
    try {
      const res = await fetch(url, {
        credentials: "include",
        headers: { Accept: "text/event-stream" },
        signal: abortCtrl.signal,
      });
      // 2026-06-06 QA-M7: SSE used to retry on EVERY non-ok status
      // indefinitely. A 401 mid-stream meant the AE's session had
      // expired, but the SSE client would happily keep reconnecting
      // every 1s -> 30s for the lifetime of the page, never surfacing
      // the auth-expired event the rest of the app uses to prompt
      // re-login. Now: dispatch the same `dma:auth-expired` CustomEvent
      // and STOP reconnecting (closed=true). The chrome's listener
      // surfaces the re-login dialog; reconnect resumes on the next
      // page-mount after re-auth.
      if (res.status === 401) {
        closed = true;
        try {
          window.dispatchEvent(new CustomEvent("dma:auth-expired"));
        } catch {
          /* best-effort */
        }
        return;
      }
      if (!res.ok || !res.body) throw new Error(`SSE bad status ${res.status}`);
      reconnectDelay = 1000;
      try {
        handlers.__connected?.("");
      } catch {
        /* handler errors never kill the stream */
      }

      const parser = createParser({
        onEvent(ev: EventSourceMessage) {
          const handler = handlers[ev.event ?? "message"];
          if (handler) handler(ev.data);
        },
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        parser.feed(decoder.decode(value, { stream: true }));
      }
    } catch (err) {
      if (closed) return;
      console.warn("[sse] disconnected, reconnecting", err);
    }
    if (!closed) {
      // Covers both an errored connection AND a server-side close (the
      // backend's `reconnect` max-age event or `error` event end the
      // stream cleanly — the read loop breaks and we land here too).
      try {
        handlers.__reconnecting?.("");
      } catch {
        /* best-effort */
      }
      const delay = Math.min(reconnectDelay, 30000);
      reconnectDelay = Math.min(delay * 2, 30000);
      setTimeout(connect, delay);
    }
  };

  void connect();

  return {
    close() {
      closed = true;
      abortCtrl?.abort();
    },
    isOpen() {
      return !closed;
    },
  };
}
