/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Backend loader
   ═══════════════════════════════════════════════════════════════════════

   Runs AFTER data.js exposes window.DMA (with empty collections) but
   before the React tree renders (the 600 ms boot delay in app-root.jsx
   gives us a window to populate). Fetches top-level lists from the
   real backend and mutates window.DMA.* arrays IN PLACE — pages read
   window.DMA at render time, so by the time the boot screen closes,
   the data is there.

   Top-level wiring (this loader):
     ENTITIES      ← GET /api/v1/entities
     ACTIVE_RUNS   ← GET /api/v1/dashboard (active_runs[])
     ALERTS        ← GET /api/v1/alerts
     CURRENT_USER  ← GET /api/v1/auth/me

   Per-entity wiring (deferred — handled lazily when a client page opens):
     INSIGHT_CARDS, EVIDENCE, RECOMMENDATIONS, TECH_STACK, QA_GATES,
     ISSUES, TIMELINE_EVENTS, FOCUS_AREAS, LEADERSHIP, etc.

   Failure modes:
     - 401 (no session)         → leave collections empty; LoginPage path
     - 5xx / network            → leave empty; user gets empty states
     - JSON parse error         → leave empty; logged to console
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  if (!window.DMA) {
    console.warn("[backend-loader] window.DMA not set — data.js must load first");
    return;
  }

  const FETCH_OPTS = { credentials: "include", headers: { Accept: "application/json" } };

  // Per-request timeout (ms). Without this, a backend hang (DB lock,
  // missing migration causing slow error path, network blip) causes
  // the admin pages to spin forever instead of surfacing a clear
  // error. 30s is generous — most admin queries are < 1s; this only
  // trips when something is genuinely wrong.
  const FETCH_TIMEOUT_MS = 30_000;
  function _withTimeout(opts = {}) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), FETCH_TIMEOUT_MS);
    return {
      opts: { ...opts, signal: ctl.signal },
      cancel: () => clearTimeout(timer),
    };
  }

  // Backend error state. Pages can subscribe via a polling MutationObserver
  // OR by reading window.DMA_LOAD_STATE.errors directly. The chrome
  // BackendErrorBanner reads this object and renders when errors.length
  // > 0. Each entry is {path, status, message, ts}; cleared on success.
  if (!window.DMA_LOAD_STATE) {
    window.DMA_LOAD_STATE = {
      boot: "pending",   // "pending" | "ok" | "error"
      errors: [],        // array of {path, status, message, ts}
      loadedAt: null,
    };
  }
  // 2026-05-29 QA audit P1: admin-endpoint 5xx errors were pushed into
  // the SAME global window.DMA_LOAD_STATE.errors queue read by the
  // app-wide BackendErrorBanner. AEs landing on any non-admin page saw
  // "Backend data failed to load... 500 /api/v1/admin/import-audit/by-
  // entity" even though the admin page already renders that error
  // locally. Fix: `scope` ∈ {"global","admin"}; BackendErrorBanner only
  // shows "global". Boot/core failures stay global; admin/diagnostic
  // failures stay scoped to their page.
  function _pushError(path, status, message, scope) {
    scope = scope || "global";
    const ts = Date.now();
    // 2026-05-28 audit fix (F-305): polling endpoints (admin
    // diagnostics every 10s, jobs every 3s) can produce dozens of
    // identical error rows when the backend stays down. Dedup by
    // (path, status, message) -- if an identical error already exists
    // in the queue, bump its `count` + `lastTs` instead of appending.
    // The bounded queue still caps at 20 entries; the diagnostic
    // signal (`count` field) shows the operator the error is
    // recurring, not stale.
    const last = window.DMA_LOAD_STATE.errors.find(
      e => e.path === path && e.status === status && e.message === message,
    );
    if (last) {
      last.count = (last.count || 1) + 1;
      last.lastTs = ts;
    } else {
      window.DMA_LOAD_STATE.errors.push({
        path, status, message, ts, count: 1, lastTs: ts, scope,
      });
      // Keep last 20 unique entries — bounded queue.
      if (window.DMA_LOAD_STATE.errors.length > 20) {
        window.DMA_LOAD_STATE.errors.shift();
      }
    }
    // Notify any listeners (BackendErrorBanner uses this).
    window.dispatchEvent(new CustomEvent("dma:load-error", {
      detail: { path, status, message, ts, scope, deduped: !!last },
    }));
  }
  function _clearErrorsFor(path) {
    if (!window.DMA_LOAD_STATE.errors.length) return;
    window.DMA_LOAD_STATE.errors = window.DMA_LOAD_STATE.errors.filter(
      e => e.path !== path,
    );
  }

  /* 2026-05-28 audit fix (Probe 8): every entity-scoped backend call
     now carries the current audience (`internal` or `customer`) as a
     `?view=` query param. The backend already strips internal fields
     when view=customer (see app/routers/{insights,heatmap,...} +
     services/audience_strip.py); without the param the strip never
     fires and the "Customer view" toggle in the chrome was a UI-only
     lie.

     Self-healing contract:
       - If `window.DMA?.tweaks?.audience` is "customer" → append
         `?view=customer` (or `&view=customer` if path already has `?`).
       - Otherwise → leave the URL alone (backend defaults to
         view=internal).
       - Path that already contains `view=` is left untouched (caller
         knows best). */
  function _withAudience(path) {
    if (typeof path !== "string") return path;
    if (/[?&]view=/.test(path)) return path;
    const audience = window.DMA?.tweaks?.audience;
    if (audience !== "customer") return path;
    return path + (path.includes("?") ? "&" : "?") + "view=customer";
  }

  async function fetchJSON(path) {
    path = _withAudience(path);
    // _withTimeout wraps with AbortController so boot fetches can't hang
    // indefinitely (was: `fetch(path, FETCH_OPTS)` directly, no timeout —
    // a single hung core endpoint could hold the whole boot at the
    // boot-screen forever; 2026-05-29 QA audit P1).
    const t = _withTimeout(FETCH_OPTS);
    try {
      const r = await fetch(path, t.opts);
      t.cancel();
      if (!r.ok) {
        if (r.status !== 401) {
          console.warn(`[backend-loader] ${path} → ${r.status} ${r.statusText}`);
          // 5xx errors are operator-actionable — surface them on the
          // BackendErrorBanner. 4xx (except 401) are usually user-input
          // and shown per-form.
          if (r.status >= 500) {
            _pushError(path, r.status, r.statusText || "Server error");
          }
        }
        return null;
      }
      _clearErrorsFor(path);
      return await r.json();
    } catch (e) {
      t.cancel();
      const msg = String(e && e.message || e);
      console.warn(`[backend-loader] ${path} → ${msg}`);
      // Network / timeout / parse failures — operator banner.
      _pushError(path, 0, msg);
      return null;
    }
  }

  /* Mutate an existing window.DMA.X array in place so any reference
     held by the page modules stays valid. */
  function replaceArray(target, source) {
    if (!Array.isArray(target) || !Array.isArray(source)) return;
    target.length = 0;
    for (const item of source) target.push(item);
  }

  /* Backend entity shape:
       { id, display_id, name, subvertical, status, run, scqa, ... }
     Standalone entity shape (what pages expect):
       { id, slug, name, subvertical_label, overall_score, pillar_scores,
         subcaps[], firmographics, assigned_to, run: { request_id, status,
         completed_at, confidence } }
     Minimal adapter so the Directory + Dashboard tiles render real names. */
  function adaptEntity(e) {
    if (!e) return null;
    // 2026-05-28 audit fix: expanded the surface to forward
    // in_progress / hq / assets / assessment_date / oss / tech_stack /
    // runs[]. Several pages (D6 Health, Directory mini-card, the
    // PDF export header) read these fields directly; previously they
    // saw `undefined` because the adapter dropped them.
    return {
      id: e.display_id || e.id,
      slug: e.display_id || e.id,
      name: e.name,
      subvertical: e.subvertical,
      subvertical_label: window.DMA.SUBVERTICAL_LABEL?.[e.subvertical] || e.subvertical || "—",
      overall_score: e.run?.overall_score ?? null,
      pillar_scores: e.run?.pillar_scores || [],
      subcaps: e.subcaps || [],
      firmographics: e.firmographics || null,
      assigned_to: e.assigned_to || null,
      // Forward fields the previous adapter dropped:
      in_progress: e.in_progress ?? (e.run?.status?.toUpperCase() === "IN_PROGRESS"),
      hq: e.hq || e.firmographics?.hq || null,
      assets: e.assets ?? e.firmographics?.assets ?? null,
      assessment_date: e.assessment_date || e.run?.completed_at || null,
      oss: e.oss || e.open_source_signals || null,
      tech_stack: e.tech_stack || [],
      runs: Array.isArray(e.runs) ? e.runs : (e.run ? [e.run] : []),
      run: e.run ? {
        request_id: e.run.request_id,
        status: e.run.status?.toLowerCase() || "—",
        completed_at: e.run.completed_at,
        confidence: e.run.confidence,
        data_source: e.run.data_source,
      } : null,
      _raw_backend: e,   // keep the original for any downstream code that wants it
    };
  }

  async function load() {
    const [me, entResp, dashResp, alertResp] = await Promise.all([
      fetchJSON("/api/v1/auth/me"),
      fetchJSON("/api/v1/entities?owner=all"),
      fetchJSON("/api/v1/dashboard?scope=all"),
      fetchJSON("/api/v1/alerts"),
    ]);

    if (me) {
      window.DMA.CURRENT_USER = me;
    }

    if (entResp && Array.isArray(entResp.items)) {
      replaceArray(window.DMA.ENTITIES, entResp.items.map(adaptEntity).filter(Boolean));
      console.info(`[backend-loader] loaded ${window.DMA.ENTITIES.length} entities`);
    }

    if (dashResp && Array.isArray(dashResp.active_runs)) {
      replaceArray(window.DMA.ACTIVE_RUNS, dashResp.active_runs);
      console.info(`[backend-loader] loaded ${window.DMA.ACTIVE_RUNS.length} active runs`);
    }

    if (alertResp && Array.isArray(alertResp.items)) {
      replaceArray(window.DMA.ALERTS, alertResp.items);
      console.info(`[backend-loader] loaded ${window.DMA.ALERTS.length} alerts`);
    }

    /* 2026-05-28 audit fix: flip the boot state after the parallel load
       completes so pages gated on DMA_LOAD_STATE.boot=='ok' can render.
       'error' if any 5xx surfaced during the load (errors[] non-empty);
       'ok' otherwise. Operator-facing BackendErrorBanner already keys
       off errors[]; this flag is for page-level boot gates that don't
       want to render until the initial fetch has actually finished. */
    window.DMA_LOAD_STATE.loadedAt = Date.now();
    window.DMA_LOAD_STATE.boot =
      window.DMA_LOAD_STATE.errors.length > 0 ? "error" : "ok";

    /* Force any currently-mounted page to re-render with the now-populated
       collections. The standalone's hash router re-runs its route handler
       on hashchange, so pages re-read window.DMA on every navigation.
       This synthetic hashchange triggers an immediate refresh without
       changing the URL. */
    window.dispatchEvent(new Event("hashchange"));

    /* Custom event for any custom listeners that want to react to data
       ready (e.g., dashboard tile counters, sidebar badges). Both event
       names dispatch — `DMA:ready` is the original; `dma:data-loaded`
       is the lower-cased canonical name the audit standardised on so
       it composes with the other dma:* events (dma:load-error etc.). */
    const detail = {
      entities: window.DMA.ENTITIES.length,
      active_runs: window.DMA.ACTIVE_RUNS.length,
      alerts: window.DMA.ALERTS.length,
      boot: window.DMA_LOAD_STATE.boot,
      loadedAt: window.DMA_LOAD_STATE.loadedAt,
    };
    window.dispatchEvent(new CustomEvent("DMA:ready", { detail }));
    window.dispatchEvent(new CustomEvent("dma:data-loaded", { detail }));
  }

  /* Kick off the load immediately. The boot screen (app-root.jsx) shows
     for 600 ms; our fetches typically complete in ≤200 ms on warm
     containers, so the React tree sees populated data on first render. */
  load();

  /* ─── Per-page admin loaders ──────────────────────────────────────
     Each admin sub-page calls these lazily on mount via useEffect.
     They return raw backend JSON so admin pages can render loading /
     error / empty states without translating shapes here. Wired to the
     six endpoints exposed by backend/app/routers/admin.py:
       GET  /api/v1/admin/users
       PATCH /api/v1/admin/users/:id/role
       GET  /api/v1/admin/imports/audit       (Import Audit page)
       GET  /api/v1/admin/build-qa            (Build QA gates)
       GET  /api/v1/admin/catalogue           (Catalogue queue + versions)
       GET  /api/v1/admin/assignments         (AE assignment queue)
     Each returns { ok, data, error } so admin pages can pattern-match. */
  async function adminGet(path) {
    path = _withAudience(path);
    const t = _withTimeout(FETCH_OPTS);
    try {
      const r = await fetch(path, t.opts);
      if (!r.ok) {
        const text = await r.text().catch(() => "");
        // 2026-05-29 QA audit P1: tag admin errors with scope="admin" so
        // BackendErrorBanner (filter scope==="global") doesn't surface
        // an admin-page-only failure as an app-wide banner. The admin
        // page renders the local error via the returned {ok:false,error}
        // shape and is the operator-visible source of truth.
        if (r.status >= 500) {
          _pushError(path, r.status, r.statusText || "Server error", "admin");
        }
        return { ok: false, data: null, error: `${r.status} ${r.statusText}${text ? " · " + text.slice(0, 200) : ""}` };
      }
      _clearErrorsFor(path);
      return { ok: true, data: await r.json(), error: null };
    } catch (e) {
      // AbortError surfaces as a generic AbortError DOMException — make
      // it actionable for the operator. The backend hang is almost
      // always a missing migration OR an exhausted DB pool — point
      // at the troubleshooting doc.
      const isTimeout = e && (e.name === "AbortError" || /aborted/i.test(String(e)));
      const msg = isTimeout
        ? `Request timed out after ${FETCH_TIMEOUT_MS/1000}s. Backend may be unreachable OR DB query is hanging. Check Cloud Run logs + DEPLOYMENT.md §T17 / §8.`
        : String(e);
      _pushError(path, 0, msg, "admin");
      return { ok: false, data: null, error: msg };
    } finally {
      t.cancel();
    }
  }
  async function adminPatch(path, body) {
    path = _withAudience(path);
    const t = _withTimeout({
      ...FETCH_OPTS,
      method: "PATCH",
      headers: { ...FETCH_OPTS.headers, "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    try {
      const r = await fetch(path, t.opts);
      if (!r.ok) {
        const text = await r.text().catch(() => "");
        if (r.status >= 500) {
          _pushError(path, r.status, r.statusText || "Server error");
        }
        return { ok: false, data: null, error: `${r.status} ${r.statusText}${text ? " · " + text.slice(0, 200) : ""}` };
      }
      _clearErrorsFor(path);
      return { ok: true, data: await r.json(), error: null };
    } catch (e) {
      const isTimeout = e && (e.name === "AbortError" || /aborted/i.test(String(e)));
      const msg = isTimeout
        ? `PATCH timed out after ${FETCH_TIMEOUT_MS/1000}s — backend unreachable.`
        : String(e);
      _pushError(path, 0, msg);
      return { ok: false, data: null, error: msg };
    } finally {
      t.cancel();
    }
  }
  /* ─── Generic POST wrapper ──────────────────────────────────────
     Mirrors adminPatch but with a configurable method (POST | DELETE).
     Used by the job-trigger surface where the URL contains a colon
     verb (e.g. /jobs/drive_crawler:execute). */
  async function adminPost(path, body) {
    path = _withAudience(path);
    const t = _withTimeout({
      ...FETCH_OPTS,
      method: "POST",
      headers: { ...FETCH_OPTS.headers, "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    try {
      const r = await fetch(path, t.opts);
      if (!r.ok) {
        const text = await r.text().catch(() => "");
        if (r.status >= 500) {
          _pushError(path, r.status, r.statusText || "Server error");
        }
        return { ok: false, data: null, error: `${r.status} ${r.statusText}${text ? " · " + text.slice(0, 200) : ""}` };
      }
      _clearErrorsFor(path);
      return { ok: true, data: await r.json(), error: null };
    } catch (e) {
      const isTimeout = e && (e.name === "AbortError" || /aborted/i.test(String(e)));
      const msg = isTimeout
        ? `POST timed out after ${FETCH_TIMEOUT_MS/1000}s — backend unreachable.`
        : String(e);
      _pushError(path, 0, msg);
      return { ok: false, data: null, error: msg };
    } finally {
      t.cancel();
    }
  }
  window.DMA.admin = {
    listUsers:        () => adminGet("/api/v1/admin/users"),
    updateUserRole:   (id, role) => adminPatch(`/api/v1/admin/users/${encodeURIComponent(id)}/role`, { role }),
    listImportAudit:  () => adminGet("/api/v1/admin/imports/audit"),
    listBuildQa:      () => adminGet("/api/v1/admin/build-qa"),
    listCatalogue:    () => adminGet("/api/v1/admin/catalogue"),
    listAssignments:  () => adminGet("/api/v1/admin/assignments"),
    // New AI-layer admin surfaces (Deliverable #7)
    vertexBudget:     () => adminGet("/api/v1/admin/vertex-budget"),
    pendingReview:    () => adminGet("/api/v1/admin/pending-review"),

    /* ─── job_executions (Defect 2 — admin home triggers) ─────────
       executeJob('drive_crawler', { mode: 'full' }) returns
         { ok, data: { id, status: 'running', started_at, … }, error }
       getJobExecution(id) returns the polling target.
       Frontend polls every 3s until status != 'running'. */
    listJobs:         () => adminGet("/api/v1/admin/jobs"),
    executeJob:       (name, body) =>
      adminPost(`/api/v1/admin/jobs/${encodeURIComponent(name)}:execute`, body || {}),
    listJobExecutions: (opts = {}) => {
      const q = new URLSearchParams();
      if (opts.job_name) q.set("job_name", opts.job_name);
      if (opts.entity_id) q.set("entity_id", opts.entity_id);
      if (opts.limit) q.set("limit", String(opts.limit));
      const qs = q.toString();
      return adminGet(`/api/v1/admin/jobs/executions${qs ? "?" + qs : ""}`);
    },
    getJobExecution: (id) =>
      adminGet(`/api/v1/admin/jobs/executions/${encodeURIComponent(id)}`),

    /* ─── import audit drilldowns (Defect 3 + 4) ─────────────────
       summary returns the 5 tile counts; byEntity returns one row
       per entity ever ingested; entityDetail returns the per-client
       runs+jobs timeline for the drilldown drawer. */
    importAuditSummary: () => adminGet("/api/v1/admin/import-audit/summary"),
    importAuditByEntity: () => adminGet("/api/v1/admin/import-audit/by-entity"),
    importAuditEntityDetail: (entityId) =>
      adminGet(`/api/v1/admin/import-audit/entities/${encodeURIComponent(entityId)}`),
    retryImportFile: (fileId) =>
      adminPost(`/api/v1/admin/imports/files/${encodeURIComponent(fileId)}:retry`, {}),

    /* ─── Operations panel (audit Wave 3) ───────────────────────
       diagnostics()     → GET /admin/diagnostics — 5-category health
                            check (orphan runs, stuck jobs, catalogue
                            stubs, missing fixtures, retry candidates)
       traceIngest()     → GET /admin/trace/ingest — proves the full
                            ingest → DB → API → UI render chain on one
                            request_id (per-step status + counts)
       abortJob(id)      → POST /jobs/executions/{id}:abort — flips a
                            running row to status='cancelled' so the
                            admin pill unsticks even if the Cloud Run
                            container never completed
       repairCatalogueStubs() → POST /repair:catalogue-stubs — idempotent
                            insert of v7.0 + v5.5 placeholder rows when
                            the catalogue table is empty (else a fresh
                            DB blocks every /heatmap call)
       repairCloseStuckJobs() → POST /repair:close-stuck-jobs — marks
                            rows older than 30 minutes with status=running
                            as failed (operator escape hatch when the
                            pre-dispatch auto-close hasn't caught up).
       The Vite-tree OperationsPanel.tsx was the reference impl; this
       port lifts the same endpoints into the production frontend. */
    diagnostics:      () => adminGet("/api/v1/admin/diagnostics"),
    traceIngest:      () => adminGet("/api/v1/admin/trace/ingest"),
    abortJob:         (id) =>
      adminPost(`/api/v1/admin/jobs/executions/${encodeURIComponent(id)}:abort`, {}),
    repairCatalogueStubs: () =>
      adminPost("/api/v1/admin/repair:catalogue-stubs", { versions: ["v7.0", "v5.5"] }),
    repairCloseStuckJobs: () =>
      adminPost("/api/v1/admin/repair:close-stuck-jobs", {}),
    /* Backfill convenience wrappers — the underlying call is
       executeJob('historical_backfill', { mode, args }) but the two
       canonical operator paths (first-deploy "run everything" + the
       "retry only failed" round-trip) deserve named entrypoints so
       the AdminPage button handlers stay self-documenting. */
    runFullBackfill: () =>
      adminPost("/api/v1/admin/jobs/historical_backfill:execute",
        { mode: "full", args: {} }),
    runRetryFailedBackfill: () =>
      adminPost("/api/v1/admin/jobs/historical_backfill:execute",
        { mode: "retry", args: { extra_args: ["--retry-failed-only"] } }),
  };

  /* ─── Chat persistence + feedback ─────────────────────────────────
     Chat sessions list / detail / delete + per-message feedback POST.
     Returns { ok, data, error } like adminGet/Patch so caller pages
     can render loading/empty/error states uniformly.
     State transitions:
       - session belongs to another user → 403 (handled as not-found)
       - DELETE soft-deletes; subsequent reads return 404
       - feedback with rating=-1 + better_answer is the explicit
         adversarial-learning signal */
  window.DMA.chat = {
    listSessions:   (entityId, limit = 20) => adminGet(
      `/api/v1/chat/sessions?limit=${limit}${entityId ? `&entity_id=${encodeURIComponent(entityId)}` : ""}`
    ),
    getSession:     (id) => adminGet(`/api/v1/chat/sessions/${encodeURIComponent(id)}`),
    deleteSession:  async (id) => {
      try {
        const r = await fetch(`/api/v1/chat/sessions/${encodeURIComponent(id)}`, {
          method: "DELETE", credentials: "include",
        });
        return r.ok ? { ok: true } : { ok: false, error: r.statusText };
      } catch (e) { return { ok: false, error: String(e) }; }
    },
    postFeedback:   (messageId, payload) => adminPatch(
      `/api/v1/chat/messages/${encodeURIComponent(messageId)}/feedback`, payload,
    ),
  };

  /* ─── Session resumption for IntelligencePanel ────────────────────
     The panel persists a per-entity session_id in localStorage so the
     next /answer turn appends to the same chat_sessions row.
     State branches:
       - no entity context        → key=`dma:chat:global`
       - entity_id present        → key=`dma:chat:{entityId}`
       - session_id rejected (403) → caller clears localStorage and
                                     retries without session_id */
  window.DMA.chatSession = {
    keyFor(entityId) { return entityId ? `dma:chat:${entityId}` : "dma:chat:global"; },
    get(entityId) {
      try { return window.localStorage.getItem(this.keyFor(entityId)) || null; }
      catch { return null; }
    },
    set(entityId, sessionId) {
      try { window.localStorage.setItem(this.keyFor(entityId), sessionId); }
      catch { /* private mode */ }
    },
    clear(entityId) {
      try { window.localStorage.removeItem(this.keyFor(entityId)); }
      catch { /* ignore */ }
    },
  };

  /* ─── Intelligence panel: streamed answer (Vertex / Gemini) ────────
     POSTs to /api/v1/rag/answer (the backend's grounded-answer endpoint)
     with pageContext + a style hint. Returns an async generator yielding
     { token, citations, done } so the IntelligencePanel can render
     tokens incrementally with a cursor. Falls back gracefully:
       - 404            → caller renders local welcomeAnswer/answerFor
       - 5xx / network  → caller shows "Sources: pending backend integration"
     The backend may not yet honour {response_style, max_paragraphs,
     require_citations} — we send them anyway so the shape is ready. */
  async function* streamAnswer({ question, pageContext, style, sessionId }) {
    // Streaming path first — IntelligencePanel renders tokens with a
    // cursor. The previous implementation POSTed to /answer (the JSON
    // endpoint) so the panel never received incremental tokens; this
    // fix routes to /answer/stream first and falls back to /answer
    // only on 404/415 (older backends without the stream variant).
    const streamUrl = "/api/v1/rag/answer/stream";
    const jsonUrl   = "/api/v1/rag/answer";
    // Resume the entity's prior session if the caller didn't pass one.
    const entityId = pageContext?.entity_id || null;
    const sid = sessionId || window.DMA?.chatSession?.get(entityId) || null;
    const payload = {
      question,
      page_context: pageContext || null,
      response_style: style?.response_style || "concise",
      max_paragraphs: style?.max_paragraphs || 3,
      require_citations: style?.require_citations !== false,
      session_id: sid,
    };
    let res;
    try {
      res = await fetch(streamUrl, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify(payload),
      });
    } catch (e) {
      yield { error: String(e), done: true };
      return;
    }
    // Fall back to non-streaming /answer when the stream variant isn't
    // wired on this backend (404) or it rejects our SSE Accept (415).
    if (res.status === 404 || res.status === 415) {
      try {
        res = await fetch(jsonUrl, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(payload),
        });
      } catch (e) {
        yield { error: String(e), done: true };
        return;
      }
    }
    if (!res.ok) {
      yield { error: `${res.status} ${res.statusText}`, status: res.status, done: true };
      return;
    }
    const ct = (res.headers.get("Content-Type") || "").toLowerCase();
    // SSE path (text/event-stream)
    if (ct.includes("text/event-stream") && res.body && res.body.getReader) {
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        // SSE frames separated by \n\n; each line is `data: <json>` or
        // `event: <name>`. We only care about data lines for now.
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const frame = buf.slice(0, idx).trim();
          buf = buf.slice(idx + 2);
          for (const line of frame.split("\n")) {
            const m = line.match(/^data:\s?(.*)$/);
            if (!m) continue;
            const raw = m[1];
            if (raw === "[DONE]") { yield { done: true }; return; }
            try {
              const obj = JSON.parse(raw);
              // Backend SSE token event emits `data: {"text":"..."}` —
              // accept `text`, `token`, AND `delta` (alias hardiness)
              // so a server-side rename doesn't break the chat panel.
              // Prior parser only accepted token/delta, so every chunk
              // yielded an empty string and the panel fell through to
              // the local scripted answer fallback even when Vertex
              // streamed real grounded content.
              yield { token: obj.text || obj.token || obj.delta || "", citations: obj.citations, ...obj };
            } catch (e) {
              // raw text frame
              if (raw) yield { token: raw };
            }
          }
        }
      }
      yield { done: true };
      return;
    }
    // Non-streaming JSON fallback
    let body;
    try { body = await res.json(); }
    catch (e) { yield { error: "invalid JSON", done: true }; return; }
    // Backend returns `answer_markdown` in the v1 schema; older shapes
    // used `answer`. Accept both.
    const answerText = body?.answer_markdown ?? body?.answer ?? null;
    if (body && typeof answerText === "string") {
      // Persist the session_id so follow-up turns resume this thread.
      if (body.session_id && window.DMA?.chatSession) {
        window.DMA.chatSession.set(entityId, body.session_id);
      }
      yield {
        token: answerText,
        citations: body.citations || body.cited_evidence_ids || null,
        session_id: body.session_id || null,
        message_id: body.message_id || null,
        fallback_used: body.fallback_used,
        validators_passed: body.validators_passed,
        // Staleness metadata per the 3-year evidence mandate — UI
        // surfaces "Most evidence is dated" banner when stale_pct
        // exceeds the backend threshold.
        bundle_stale_pct: body.bundle_stale_pct,
        stale_disclaimer: body.stale_disclaimer,
        done: true,
      };
      return;
    }
    yield { error: "unexpected response shape", done: true };
  }
  window.DMA.intelligence = { streamAnswer };

  /* ─── Entity-scoped AI-layer fetchers ──────────────────────────────
     Loaded lazily by per-page components (D3 archetype chip, D6
     Patterns tab, runs history timeline, heatmap enrichment pills).
     Pure GET wrappers around the v1 endpoints. */
  /* ─── Evidence: per-row "Seen in N runs" chip (Promise 5 / commit 8331bd2)
     The React app has SeenInRunsChip; the standalone needs the same API
     reachable. State branches:
       - 404                   → row never indexed in evidence_run_links
       - n_runs <= 1           → "First seen" muted chip; no popover
       - n_runs >= 2           → "Seen in N runs" + popover listing each run
     Accepts both UUID form and short E-ID (the router disambiguates). */
  window.DMA.evidence = {
    runHistory: (evidenceId) => adminGet(
      `/api/v1/evidence/${encodeURIComponent(evidenceId)}/run-history`
    ),
  };

  /* ─── Cross-pillar stories on D5 Context (Promise 10 / commit b30f9bf)
     One row per cross-pillar story whose origin_subcap_id intersects the
     entity's scored subcaps. Filter chips are origin pillar P1..P4. */
  window.DMA.crossPillar = {
    storiesForEntity: (entityId, opts = {}) => {
      const q = new URLSearchParams();
      // Backend expects `pillar`; frontend may pass `origin_pillar` or `pillar`.
      const p = opts.pillar || opts.origin_pillar;
      if (p) q.set("pillar", p);
      const qs = q.toString();
      return adminGet(
        `/api/v1/entities/${encodeURIComponent(entityId)}/cross-pillar-stories${qs ? "?" + qs : ""}`
      );
    },
  };

  /* ─── Manual assessment payload upload (JSON, bot-replay)
     ERROR HISTORY L1: 'Upload payload manually' button on /admin/import
     was rendered but had no onClick; operators reported 'button doesn't
     work' on 2026-05-24. Wired here as POST JSON to
     /api/v1/ingest/assessment so analysts can re-ingest a single
     AppPayloadV1 envelope when the bot loop fails.

     IMPORTANT — endpoint separation (ADR 0012):
       * uploadAssessment(file)  → JSON AppPayloadV1 → /ingest/assessment
                                   (bot-replay path; can also be driven
                                    by admin session cookie)
       * uploadPackage(file)     → ZIP DMA package    → /ingest/package
                                   (the canonical re-ingest path the
                                    audit identified as the missing
                                    UI control)

     The two routes are NOT interchangeable. A ZIP posted to
     /ingest/assessment is rejected with 422 because the route is a
     pydantic JSON validator.

     State branches:
       no_file_picked   → ok:false, error="No file selected"
       not_json         → ok:false, error="File must be .json"
       backend_400      → ok:false, error includes server validation msg
       backend_413      → nginx fix N6 raised body limit to 100MB
       backend_ok       → ok:true, data={run_id, request_id} */
  window.DMA.admin.uploadAssessment = async (file) => {
    if (!file) return { ok: false, error: "No file selected" };
    if (!/\.json$/i.test(file.name)) {
      return { ok: false, error: "File must be a .json payload (use uploadPackage for a .zip)" };
    }
    let parsed;
    try {
      parsed = JSON.parse(await file.text());
    } catch (e) {
      return { ok: false, error: `Not valid JSON: ${String(e).slice(0, 120)}` };
    }
    const t = _withTimeout({
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsed),
    });
    try {
      const r = await fetch("/api/v1/ingest/assessment", t.opts);
      if (!r.ok) {
        const text = await r.text().catch(() => "");
        return { ok: false, error: `${r.status} ${r.statusText}${text ? " · " + text.slice(0, 240) : ""}` };
      }
      return { ok: true, data: await r.json() };
    } catch (e) {
      const isTimeout = e && (e.name === "AbortError" || /aborted/i.test(String(e)));
      return { ok: false, error: isTimeout ? "Upload timed out" : String(e) };
    } finally { t.cancel(); }
  };

  /* ─── Manual DMA package upload (ZIP, complete package re-ingest)
     2026-05-28 audit fix: this is the canonical "drag the complete
     package zip onto the dropzone" path that the audit identified as
     missing from the standalone admin UI. POSTs multipart/form-data
     to /api/v1/ingest/package, which extracts the zip, skips deck
     entries (05_narrative_deck/*), parses the rest, persists, and
     returns IngestPackageAck with subcap/evidence/issue counts +
     parser_warnings (including any skipped decks).

     Allowed file extensions: .zip
     Backend per-entry cap: 50 MB after deck skip; cumulative 200 MB.
     Backend transport cap (compressed): 100 MB.

     State branches:
       no_file_picked      → ok:false, error="No file selected"
       not_zip             → ok:false, error="File must be .zip"
       backend_413         → ok:false, error="upload exceeds 100 MB"
       backend_400_zipslip → ok:false, error="zip slip detected"
       backend_ok          → ok:true, data={run_id, request_id, …, warnings} */
  window.DMA.admin.uploadPackage = async (file) => {
    if (!file) return { ok: false, error: "No file selected" };
    if (!/\.zip$/i.test(file.name)) {
      return { ok: false, error: "File must be a .zip DMA package (use uploadAssessment for .json)" };
    }
    const fd = new FormData();
    fd.append("file", file, file.name);
    // Long-haul timeout: real packages can take 30-60s to ingest end-
    // to-end. The default FETCH_TIMEOUT_MS (30s) is too tight; bump.
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 180_000); // 3 minutes
    try {
      const r = await fetch("/api/v1/ingest/package", {
        method: "POST",
        credentials: "include",
        body: fd,
        signal: ctl.signal,
      });
      if (!r.ok) {
        const text = await r.text().catch(() => "");
        return { ok: false, error: `${r.status} ${r.statusText}${text ? " · " + text.slice(0, 240) : ""}` };
      }
      return { ok: true, data: await r.json() };
    } catch (e) {
      const isTimeout = e && (e.name === "AbortError" || /aborted/i.test(String(e)));
      return { ok: false, error: isTimeout ? "Package upload timed out (180s)" : String(e) };
    } finally { clearTimeout(timer); }
  };

  /* ─── Catalogue upload (Promise 11)
     POST a workbook ZIP to /api/v1/admin/catalogue:upload. Server
     versions it as v7.N+1 atomically (rejects if same hash). */
  window.DMA.admin.uploadCatalogue = async (file, version) => {
    if (!file) return { ok: false, error: "No file selected" };
    const fd = new FormData();
    fd.append("workbook", file);
    if (version) fd.append("version", version);
    const t = _withTimeout({ method: "POST", credentials: "include", body: fd });
    try {
      const r = await fetch("/api/v1/admin/catalogue:upload", t.opts);
      if (!r.ok) {
        const text = await r.text().catch(() => "");
        return { ok: false, error: `${r.status} ${r.statusText}${text ? " · " + text.slice(0, 200) : ""}` };
      }
      return { ok: true, data: await r.json() };
    } catch (e) {
      const isTimeout = e && (e.name === "AbortError" || /aborted/i.test(String(e)));
      return { ok: false, error: isTimeout ? "Upload timed out" : String(e) };
    } finally { t.cancel(); }
  };

  window.DMA.archetype = {
    /* Closest archetype for one entity. State branches:
       - 404           → entity unknown
       - insufficient_data:true  → render "Archetype: insufficient cohort (N<3)"
       - closest set   → render chip with label + sample_count */
    forEntity: (displayId) => adminGet(
      `/api/v1/entities/${encodeURIComponent(displayId)}/archetype`
    ),
  };

  window.DMA.entities = {
    /* Run-history chain for the version-timeline UI on D5/D6 Runs.
       State branches:
       - 404 → entity missing
       - items=[] → empty timeline
       - parent_chain walked newest→oldest by request_id */
    runHistory: (displayId) => adminGet(
      `/api/v1/entities/${encodeURIComponent(displayId)}/run-history`
    ),
    heatmap: (displayId, opts = {}) => {
      const q = new URLSearchParams();
      if (opts.zoom) q.set("zoom", opts.zoom);
      if (opts.hm) q.set("hm", opts.hm);
      if (opts.peer) q.set("peer", "true");
      if (opts.issues) q.set("issues", "true");
      const qs = q.toString();
      return adminGet(
        `/api/v1/entities/${encodeURIComponent(displayId)}/heatmap${qs ? "?" + qs : ""}`
      );
    },
  };

  window.DMA.patterns = {
    /* D6 Health "Patterns" tab data source — peer_archetypes rows
       filtered by subvertical + catalogue version. */
    list: (subvertical, catalogueVersion) => {
      const q = new URLSearchParams();
      if (subvertical) q.set("subvertical", subvertical);
      if (catalogueVersion) q.set("catalogue_version", catalogueVersion);
      const qs = q.toString();
      return adminGet(`/api/v1/archetypes${qs ? "?" + qs : ""}`);
    },
  };
})();
