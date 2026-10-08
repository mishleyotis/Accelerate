/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Usage tracker (production only)
   ───────────────────────────────────────────────────────────────────────
   The router lives in the hash, so page changes never reach the server.
   This module reports them to /api/usage, which only LOGS (lib/usage.js →
   log sink → BigQuery → Admin › Usage analytics). It sends:

     page_view  when a page is left or the tab is hidden: the path and the
                VISIBLE time spent on it. A hidden tab accrues nothing, and the
                visit resumed afterwards is marked `cont` — its time counts,
                it is not a second view.
     heartbeat  every 60 s while the tab is visible, so "live now" and an
                idle-but-reading session are distinguishable from a closed one.
     feature    named actions: evidence drawer, insight modal, Intelligence
                panel, client link copied.

   A session is continuous activity with less than 30 minutes between events
   (the prototype's definition). Identity is never sent: the server reads it
   from the session cookie. Local preview (no DMA_LIVE) sends nothing.
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  const noop = () => {};
  const LIVE = typeof window !== "undefined" && window.DMA_LIVE;
  if (!LIVE || !LIVE.authed) {
    Object.assign(window, { trackUsage: noop, setUsageContext: noop });
    return;
  }

  const IDLE_MS = 30 * 60 * 1000;
  const HEARTBEAT_MS = 60 * 1000;
  const MAX_DWELL_MS = 4 * 60 * 60 * 1000;
  const KEY = "dma_usage_sid";
  let ctx = { audience: "internal", acting_role: null };
  let memSid = null;

  function newSid() {
    try {
      const a = new Uint8Array(12);
      crypto.getRandomValues(a);
      return Array.from(a, b => b.toString(16).padStart(2, "0")).join("");
    } catch (e) {
      return (Date.now().toString(36) + Math.random().toString(36).slice(2, 12)).slice(0, 24);
    }
  }

  // The session id, rotated after 30 minutes without an event. sessionStorage
  // can be absent or throw (private windows); the in-memory id is the fallback.
  function sid() {
    const now = Date.now();
    try {
      const s = JSON.parse(sessionStorage.getItem(KEY) || "null");
      const id = s && s.sid && now - s.last < IDLE_MS ? s.sid : newSid();
      sessionStorage.setItem(KEY, JSON.stringify({ sid: id, last: now }));
      return id;
    } catch (e) {
      if (!memSid || now - memSid.last >= IDLE_MS) memSid = { sid: newSid(), last: now };
      memSid.last = now;
      return memSid.sid;
    }
  }

  function send(events) {
    const body = JSON.stringify({ events });
    try {
      if (navigator.sendBeacon &&
          navigator.sendBeacon("/api/usage", new Blob([body], { type: "application/json" }))) return;
    } catch (e) {}
    try {
      fetch("/api/usage", { method: "POST", body, keepalive: true, credentials: "same-origin",
                            headers: { "content-type": "application/json" } }).catch(noop);
    } catch (e) {}
  }

  const pathNow = () => {
    try { return parseHash().path || "/"; } catch (e) { return "/"; }
  };
  const visible = () => typeof document === "undefined" || document.visibilityState !== "hidden";
  const event = (type, path, extra) => Object.assign({
    type, sid: sid(), path, audience: ctx.audience, acting_role: ctx.acting_role,
    client_link: typeof isClientLink === "function" ? !!isClientLink() : false,
  }, extra);

  let cur = null;
  function start(path, cont) {
    cur = { path, enteredAt: new Date().toISOString(), visibleMs: 0,
            since: visible() ? Date.now() : null, cont: !!cont };
  }
  function flush() {
    if (!cur) return;
    if (cur.since != null) { cur.visibleMs += Date.now() - cur.since; cur.since = visible() ? Date.now() : null; }
    // A resumed visit with no visible time adds nothing; a first visit always
    // counts as a view, however short.
    if (!cur.cont || cur.visibleMs >= 1000) {
      send([event("page_view", cur.path, {
        dwell_ms: Math.min(MAX_DWELL_MS, Math.round(cur.visibleMs)),
        entered_at: cur.enteredAt, cont: cur.cont,
      })]);
    }
    cur.visibleMs = 0;
    cur.cont = true;
  }

  start(pathNow(), false);
  window.addEventListener("hashchange", () => {
    const p = pathNow();
    if (cur && p === cur.path) return;          // a query-only change
    flush();
    start(p, false);
  });
  document.addEventListener("visibilitychange", () => {
    if (!cur) return;
    if (visible()) { cur.since = Date.now(); cur.enteredAt = new Date().toISOString(); }
    else flush();
  });
  window.addEventListener("pagehide", flush);
  const beat = setInterval(() => { if (visible() && cur) send([event("heartbeat", cur.path)]); }, HEARTBEAT_MS);
  // The test harnesses run this bundle in Node, where a live interval keeps
  // the process from exiting. Browsers hand back a number and skip this.
  if (beat && typeof beat.unref === "function") beat.unref();

  // Called from the app provider whenever audience / acting-as changes.
  function setUsageContext(next) { ctx = Object.assign({}, ctx, next || {}); }
  function trackUsage(feature) { send([event("feature", cur ? cur.path : pathNow(), { feature })]); }

  Object.assign(window, { trackUsage, setUsageContext });
})();
