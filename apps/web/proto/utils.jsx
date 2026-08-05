/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Shared utilities, SVG icons, layout primitives
   ═══════════════════════════════════════════════════════════════════════ */
const { useState, useEffect, useRef, useMemo, useCallback, createContext, useContext } = React;

/* ── App context ─────────────────────────────────────────────────────
   Holds: current route, role, audience mode, toasts, intelligence panel
*/
const AppCtx = createContext(null);
const useApp = () => useContext(AppCtx);

/* ── Portal ──────────────────────────────────────────────────────────
   Renders children at document.body so overlays (popovers, drawers,
   modals) escape any ancestor stacking context (e.g. the sticky topbar
   at z-index:50) and honour their own z-index globally. */
function Portal({ children }) {
  return ReactDOM.createPortal(children, document.body);
}

/* ── Hash router ─────────────────────────────────────────────────── */
function parseHash() {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [path, qs] = raw.split("?");
  const params = {};
  if (qs) qs.split("&").forEach(kv => {
    const [k, v] = kv.split("=");
    if (k) params[decodeURIComponent(k)] = v == null ? true : decodeURIComponent(v.replace(/\+/g," "));
  });
  return { path, params };
}
function buildHash(path, params) {
  const keys = params ? Object.keys(params).filter(k => params[k] != null && params[k] !== false) : [];
  const qs = keys.length ? "?" + keys.map(k => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`).join("&") : "";
  return `#${path}${qs}`;
}
function navigate(path, params) {
  window.location.hash = buildHash(path, params || {}).slice(1);
}
function useRoute() {
  const [route, setRoute] = useState(parseHash());
  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return route;
}

/* ── fx ───────────────────────────────────────────────────────────────
   Fixed-decimal display for a value that may legitimately be absent. The
   fixture always had a number; a promoted payload may not — a peer median
   nobody stated, a delta with nothing to compare against, a score on an
   unscored cell. Rendering 0.0 there asserts a measurement, and crashing on
   null loses the whole page (React unmounts the tree, so ONE null blanked
   every route). Absent prints an em dash. */
function fx(v, digits) {
  const n = Number(v);
  return (v === null || v === undefined || v === "" || !isFinite(n))
    ? "—" : n.toFixed(digits === undefined ? 1 : digits);
}

/* ── Icons ───────────────────────────────────────────────────────── */
function Icon({ name, size = 16, ...rest }) {
  const s = size;
  const props = { width: s, height: s, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round", ...rest };
  switch (name) {
    case "home":      return <svg {...props}><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/></svg>;
    case "grid":      return <svg {...props}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>;
    case "bell":      return <svg {...props}><path d="M6 8a6 6 0 1 1 12 0c0 6 3 7 3 7H3s3-1 3-7"/><path d="M10 21a2 2 0 0 0 4 0"/></svg>;
    case "search":    return <svg {...props}><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>;
    case "user":      return <svg {...props}><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/></svg>;
    case "settings":  return <svg {...props}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 0 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>;
    case "drive":     return <svg {...props}><path d="M6 4l-4 8 4 8h12l4-8-4-8H6z"/><path d="M6 4l8 16"/><path d="M18 4l-8 16"/><path d="M2 12h20"/></svg>;
    case "x":         return <svg {...props}><path d="M6 6l12 12M18 6L6 18"/></svg>;
    case "check":     return <svg {...props}><path d="M5 12l5 5L20 7"/></svg>;
    case "chevron-r": return <svg {...props}><path d="M9 6l6 6-6 6"/></svg>;
    case "chevron-l": return <svg {...props}><path d="M15 6l-6 6 6 6"/></svg>;
    case "chevron-d": return <svg {...props}><path d="M6 9l6 6 6-6"/></svg>;
    case "chevron-u": return <svg {...props}><path d="M6 15l6-6 6 6"/></svg>;
    case "arrow-r":   return <svg {...props}><path d="M5 12h14M13 6l6 6-6 6"/></svg>;
    case "arrow-up":  return <svg {...props}><path d="M12 19V5M6 11l6-6 6 6"/></svg>;
    case "arrow-dn":  return <svg {...props}><path d="M12 5v14M6 13l6 6 6-6"/></svg>;
    case "lock":      return <svg {...props}><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>;
    case "external":  return <svg {...props}><path d="M14 4h6v6"/><path d="M20 4L10 14"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>;
    case "filter":    return <svg {...props}><path d="M3 5h18l-7 8v7l-4-2v-5L3 5z"/></svg>;
    case "plus":      return <svg {...props}><path d="M12 5v14M5 12h14"/></svg>;
    case "minus":     return <svg {...props}><path d="M5 12h14"/></svg>;
    case "edit":      return <svg {...props}><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>;
    case "download":  return <svg {...props}><path d="M12 3v12"/><path d="M6 11l6 6 6-6"/><path d="M3 21h18"/></svg>;
    case "copy":      return <svg {...props}><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>;
    case "warn":      return <svg {...props}><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><circle cx="12" cy="17" r=".5"/></svg>;
    case "info":      return <svg {...props}><circle cx="12" cy="12" r="9"/><path d="M12 8v.5"/><path d="M12 12v4"/></svg>;
    case "evidence":  return <svg {...props}><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 13h8M8 17h5"/></svg>;
    case "ai":        return <svg {...props}><path d="M12 2l1.6 4.4L18 8l-4.4 1.6L12 14l-1.6-4.4L6 8l4.4-1.6L12 2z"/><path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8L19 14z"/></svg>;
    case "menu":      return <svg {...props}><path d="M3 6h18M3 12h18M3 18h18"/></svg>;
    case "logout":    return <svg {...props}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>;
    case "platform":  return <svg {...props}><path d="M3 12l9-9 9 9-9 9z"/><path d="M3 12l9 4 9-4"/></svg>;
    case "heatmap":   return <svg {...props}><rect x="3" y="3" width="6" height="6" rx="1"/><rect x="11" y="3" width="6" height="6" rx="1"/><rect x="3" y="11" width="6" height="6" rx="1"/><rect x="11" y="11" width="6" height="6" rx="1"/><rect x="19" y="3" width="2" height="6" rx="1"/><rect x="19" y="11" width="2" height="6" rx="1"/><rect x="3" y="19" width="6" height="2" rx="1"/><rect x="11" y="19" width="6" height="2" rx="1"/></svg>;
    case "insight":   return <svg {...props}><path d="M12 2a7 7 0 0 0-4 12.7V17a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-2.3A7 7 0 0 0 12 2z"/><path d="M9 22h6"/></svg>;
    case "timeline":  return <svg {...props}><path d="M3 6h18M3 12h18M3 18h18"/><circle cx="7" cy="6" r="1.4" fill="currentColor" stroke="none"/><circle cx="13" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="9" cy="18" r="1.4" fill="currentColor" stroke="none"/></svg>;
    case "shield":    return <svg {...props}><path d="M12 2l9 4v6c0 5-3.5 9-9 10-5.5-1-9-5-9-10V6l9-4z"/></svg>;
    case "stack":     return <svg {...props}><path d="M12 2l10 5-10 5L2 7l10-5z"/><path d="M2 12l10 5 10-5"/><path d="M2 17l10 5 10-5"/></svg>;
    case "drilldown": return <svg {...props}><path d="M3 3h18v18H3z"/><path d="M9 9h6v6H9z"/></svg>;
    case "users":     return <svg {...props}><circle cx="9" cy="8" r="3"/><path d="M3 21c0-3 3-5 6-5s6 2 6 5"/><circle cx="17" cy="6" r="2"/><path d="M16 11h.5c2.5 0 4.5 2 4.5 5"/></svg>;
    case "envelope":  return <svg {...props}><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>;
    case "money":     return <svg {...props}><rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M7 12h.01M17 12h.01"/></svg>;
    case "refresh":   return <svg {...props}><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></svg>;
    case "scale":     return <svg {...props}><path d="M3 6h18"/><path d="M16 6l3 7a3 3 0 0 1-6 0l3-7zM8 6l3 7a3 3 0 0 1-6 0l3-7z"/><path d="M12 6v15M9 21h6"/></svg>;
    case "sparkle":   return <svg {...props}><path d="M12 3l1.8 4.6L18 9l-4.2 1.4L12 15l-1.8-4.6L6 9l4.2-1.4L12 3z"/><path d="M19 14l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8.8-2zM5 16l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6.6-1.4z"/></svg>;
    case "calendar":  return <svg {...props}><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/></svg>;
    case "linkedin":  return <svg {...props}><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 11v6M8 7v.01M12 17v-4a2 2 0 1 1 4 0v4M12 17v-6"/></svg>;
    case "phone":     return <svg {...props}><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/></svg>;
    case "doc":       return <svg {...props}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6M9 9h2"/></svg>;
    case "route":     return <svg {...props}><circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/><path d="M8 19h6a4 4 0 0 0 0-8H10a4 4 0 0 1 0-8h6"/></svg>;
    case "building":  return <svg {...props}><rect x="4" y="2" width="16" height="20" rx="1"/><path d="M9 22v-4h6v4M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/></svg>;
    case "stairs":    return <svg {...props}><path d="M3 19h4v-4h4v-4h4v-4h4V3"/></svg>;
    case "play":      return <svg {...props}><polygon points="6 4 20 12 6 20 6 4"/></svg>;
    case "globe":     return <svg {...props}><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>;
    case "share":     return <svg {...props}><circle cx="6" cy="12" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><path d="M8 11l8-4M8 13l8 4"/></svg>;
    case "switch":    return <svg {...props}><path d="M7 8h14l-3-3M17 16H3l3 3"/></svg>;
    case "lightbulb": return <svg {...props}><path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10.5c1 .9 1.5 2.2 1.5 3.5h5c0-1.3.5-2.6 1.5-3.5A6 6 0 0 0 12 3z"/></svg>;
    default:          return <svg {...props}><circle cx="12" cy="12" r="6"/></svg>;
  }
}

/* ── Asset resolver (resolves to bundled blob URL or falls back to path) ─ */
function assetUrl(id, fallback) {
  return (typeof window !== "undefined" && window.__resources && window.__resources[id]) || fallback;
}

/* ── Session identity (production divergence, data-flow only) ────────
   The signed-in user comes from the server-verified session in
   DMA_LIVE; the prototype's fixed persona remains only as the
   local-preview fallback. Every rendered name/avatar derives from
   here — nothing hardcodes a person. */
function sessionUser() {
  const live = (typeof window !== "undefined" && window.DMA_LIVE) || null;
  if (!live) {
    // Local prototype preview only (template.html) — never rendered in
    // production, where DMA_LIVE always exists.
    return { name: "Mishley Otiende", short: "Mishley O.", first: "Mishley",
             initials: "MO", email: "mishley@zennify.com" };
  }
  const email = live.email;
  if (!email) {
    // Live but unauthenticated: nothing to show but the sign-in gate.
    return { name: "Not signed in", short: "—", first: "there",
             initials: "?", email: "" };
  }
  // Server-verified display name (lib/identity.js); the client never
  // invents one when the server provided it.
  const name = live.name ||
    email.split("@")[0].split(/[._-]+/).filter(Boolean)
      .map(w => w[0].toUpperCase() + w.slice(1)).join(" ") || email;
  const parts = name.split(/\s+/).filter(Boolean);
  const first = parts[0] || email;
  return {
    name,
    short: parts.length > 1 ? `${parts[0]} ${parts[1][0]}.` : first,
    first,
    initials: (parts.length > 1 ? parts[0][0] + parts[1][0]
                                : (parts[0] || email).slice(0, 2)).toUpperCase(),
    email,
  };
}

/* ── Live serving-tier reads (production only) ────────────────────────
   A client-scoped page's content comes from the promoted serving tables
   through the API, never from this prototype's fixtures. Three states,
   all of which the pages must render honestly:
     loading  the request is in flight
     ready    sections is an object; a section may still be absent, which
              means it did not promote — that is a state, not a blank
     error    with the API's own code (entity_not_found, audience_forbidden,
              run_superseded …) so the surface can say what happened. */
function useLivePage(displayId, page, audience, runId) {
  const LIVE = typeof window !== "undefined" && !!window.DMA_LIVE;
  const [state, setState] = useState(
    LIVE ? { status: "loading" } : { status: "mock" });
  useEffect(() => {
    if (!LIVE || !displayId || !page) return;
    let cancelled = false;
    setState({ status: "loading" });
    const qs = new URLSearchParams({ audience: audience || "internal" });
    if (runId) qs.set("run", runId);
    fetch(`/api/entity/${encodeURIComponent(displayId)}/${page}?${qs}`)
      .then(r => r.json().then(body => ({ ok: r.ok, status: r.status, body })))
      .then(({ ok, body }) => {
        if (cancelled) return;
        setState(ok ? { status: "ready", sections: body.sections || {},
                        entity: body.entity, run: body.run,
                        audience: body.audience }
                    : { status: "error", code: body.error || "unknown",
                        detail: body.detail || null });
      })
      .catch(() => { if (!cancelled) setState({ status: "error", code: "unreachable" }); });
    return () => { cancelled = true; };
  }, [LIVE, displayId, page, audience, runId]);
  return state;
}

/* ── useLiveEntity ───────────────────────────────────────────────────
   Loads everything one client's surfaces need and installs it as
   window.DMA_ENTITY, so the PROTOTYPE'S OWN components render it: all six
   promoted pages plus the two grain reads (the evidence store, read per id,
   and the run's cell grain). Six-plus-two requests once per
   entity+run+audience, and ETag/304 makes a revisit free.

   It clears window.DMA_ENTITY before it fetches. That single line is the
   cross-client guarantee: the list accessors (DMA.EVIDENCE, INSIGHT_CARDS,
   getEvidence …) take no entity argument, because the evidence drawer only
   knows an e_id — so during a route change they must answer with nothing
   rather than the previously viewed client's rows. tests/adapter.test.js
   asserts the line is still here. */
function useLiveEntity(displayId, audience, runId) {
  const LIVE = typeof window !== "undefined" && !!window.DMA_LIVE;
  const [state, setState] = useState(LIVE ? { status: "loading" } : { status: "mock" });

  // The registry is cleared when the IDENTITY changes, not on every effect
  // run. The effect re-runs whenever audience or run changes too, and clearing
  // then left a window in which DMA.* answered with nothing while the page was
  // still mounted — the cards rendered, then emptied. Cross-client bleed is
  // what the clear is for, so it fires exactly when the client changes.
  const loadedFor = useRef(null);
  useEffect(() => {
    if (!LIVE) return;
    const key = `${displayId || ""}`;
    if (typeof window !== "undefined" && loadedFor.current !== key) {
      window.DMA_ENTITY = null;
    }
    loadedFor.current = key;
    if (!displayId) { setState({ status: "idle" }); return; }
    let cancelled = false;
    setState({ status: "loading" });

    const qs = (extra) => {
      const q = new URLSearchParams({ audience: audience || "internal" });
      if (runId) q.set("run", runId);
      for (const k of Object.keys(extra || {})) q.set(k, extra[k]);
      return q.toString();
    };
    const get = (path) => fetch(path)
      .then(r => r.json().then(body => ({ ok: r.ok, body })))
      // A page an audience may not see (403) or that has nothing promoted is
      // a legitimate answer, not a failure: it becomes an absent section.
      .catch(() => ({ ok: false, body: null }));

    const id = encodeURIComponent(displayId);
    const pages = ["overview", "heatmap", "insights", "platform", "context",
                   "techstack"];
    Promise.all([
      ...pages.map(p => get(`/api/entity/${id}/${p}?${qs()}`)),
      get(`/api/entity/${id}/evidence?${qs()}`),
      get(`/api/entity/${id}/subcaps?${qs()}`),
    ]).then((results) => {
      if (cancelled) return;
      const byPage = {};
      pages.forEach((p, i) => { if (results[i].ok) byPage[p] = results[i].body; });
      const evidence = results[pages.length].ok ? results[pages.length].body : null;
      const subcaps = results[pages.length + 1].ok
        ? (results[pages.length + 1].body.subcaps || []) : [];

      if (!Object.keys(byPage).length) {
        setState({ status: "error", code: "no_promoted_pages" });
        return;
      }
      const built = window.buildLiveEntity(displayId, byPage,
                                           { evidence, subcaps });
      window.DMA_ENTITY = built;
      setState({ status: "ready", entity: built,
                 run: built.run, audience: audience || "internal" });
    });
    return () => { cancelled = true; };
  }, [LIVE, displayId, audience, runId]);

  return state;
}

/* The promoted data for one section, or null. `null` never means "render
   the prototype's example content" — in production there is nothing else
   to show, and a fixture rendered under a real client's name is the
   fabrication this function exists to prevent. */
function liveSection(live, name) {
  if (!live || live.status !== "ready") return null;
  const s = live.sections && live.sections[name];
  return s && s.data ? s.data : null;
}

function liveSectionState(live, name) {
  if (!live || live.status !== "ready") return null;
  return (live.sections && live.sections[name]) || null;
}

/* End the app session server-side (cookie cleared), then land on the
   sign-in page. With IAP in front, the Google session itself persists —
   "Continue with Google" re-enters without a password prompt. */
function signOutSession() {
  const done = () => window.location.assign("/login");
  if (typeof window !== "undefined" && window.DMA_LIVE) {
    fetch("/api/signout", { method: "POST" }).then(done, done);
  } else {
    done();
  }
}

/* The role the SERVER granted this session (allowlist). "Acting as" may
   preview a lesser view but never exceed the grant. Local preview
   (no DMA_LIVE) keeps the prototype's free switching. */
function grantedRole() {
  const live = (typeof window !== "undefined" && window.DMA_LIVE) || null;
  // AE is what everyone outside the ADMIN/ANALYST allowlists gets — the
  // default view, granted server-side. Local preview keeps free switching.
  return live ? (live.role || "AE") : "ADMIN";
}

/* ── Brand mark ──────────────────────────────────────────────────── */
function BrandMark({ size = 28 }) {
  return (
    <img src={assetUrl("brand_iconTeal", "brand/icon_teal.png")} width={size} height={size} alt="Zennify"
         style={{ borderRadius: Math.round(size * 0.22), display: "block", flexShrink: 0, objectFit: "cover" }} />
  );
}

function ZennifyWordmark({ height = 22, color = "dark" }) {
  const src = color === "dark" ? assetUrl("brand_fullDark", "brand/full_dark.png") : assetUrl("brand_fullLight", "brand/full_light.png");
  return (
    <img src={src} height={height} alt="Zennify"
         style={{ height, width: "auto", display: "block" }} />
  );
}

/* ── Pillar badge ────────────────────────────────────────────────── */
function PillarBadge({ pillar }) {
  const p = DMA.PILLARS.find(x => x.id === pillar);
  return <span className="b b-purple">{pillar}</span>;
}

/* ── Maturity cell helper (small inline) ─────────────────────────── */
function MaturityChip({ score, large }) {
  if (score == null) return <span className="chip muted">-</span>;
  const cls = DMA.helpers.maturityClass(score);
  return (
    <span className={`b ${cls}`} style={large ? { padding: "5px 9px", fontSize: 13 } : null}>
      {score.toFixed(1)}
    </span>
  );
}

/* ── Toast manager ───────────────────────────────────────────────── */
function ToastStack({ toasts, remove }) {
  return (
    <div className="toast-stack">
      {toasts.map(t => (
        <div key={t.id} className={`toast ${t.kind || ""}`} role="status">
          <Icon name={t.kind === "warn" ? "warn" : t.kind === "error" ? "warn" : "check"} size={16} />
          <span style={{ flex: 1 }}>{t.text}</span>
          <button onClick={() => remove(t.id)} aria-label="Dismiss" className="icon-btn" style={{ width: 24, height: 24, color: "rgba(255,255,255,.7)" }}>
            <Icon name="x" size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}

/* ── Format helpers ──────────────────────────────────────────────── */
function fmtDate(s) {
  if (!s) return "-";
  const d = new Date(s);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
function fmtAssets(n) {
  if (n == null || n === 0) return "-";
  if (n >= 1e9) return `$${(n/1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n/1e6).toFixed(0)}M`;
  return `$${n.toLocaleString()}`;
}
function fmtPct(n) { return `${(n*100).toFixed(0)}%`; }
function relTime(s) {
  if (!s) return "-";
  const months = Math.round((new Date() - new Date(s)) / (1000*60*60*24*30.4));
  if (months < 1) return "just now";
  if (months < 12) return `${months} mo ago`;
  return `${Math.round(months/12*10)/10} yr ago`;
}

/* ── Freshness dot ───────────────────────────────────────────────── */
function FreshnessDot({ date, withLabel }) {
  if (!date) return null;
  const f = DMA.helpers.freshnessOf(date);
  const color = f.tone === "ok" ? "var(--z-mid)" : f.tone === "warn" ? "var(--z-org)" : "var(--z-below)";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 8, height: 8, borderRadius: 4, background: color, display: "inline-block" }} />
      {withLabel ? <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{f.label} · {f.months} mo</span> : null}
    </span>
  );
}

/* ── Loading screens ─────────────────────────────────────────────── */
function LoadingScreen({ variant, title, body, detail, dark }) {
  // variants: "boot" | "section" | "offline" | "stale" | "default"
  const presets = {
    boot:     { title: "Loading DMA Insights…",       body: "Stitching together the assessment workspace.",             detail: "Hydrating data layer · checking cached runs" },
    section:  { title: "Loading…",                     body: "Pulling the latest data for this view.",                    detail: "Hot cache · usually < 500ms" },
    offline:  { title: "You're offline",                body: "We've lost the connection. Reconnect to keep working.",     detail: "Cached views remain available · no live updates" },
    slow:     { title: "Slow connection",               body: "The network is sluggish — we're still working on it.",      detail: "Falling back to cached responses where possible" },
    unreachable: { title: "Service temporarily unreachable", body: "The DMA Insights service isn't responding. We'll retry automatically.", detail: "Last attempt failed · next retry in 12 s" },
    stale:    { title: "Sign-in is taking longer than usual", body: "Google OAuth is responding slowly. We're still waiting.", detail: "Retry pending" },
    auth:     { title: "Signing you in…",               body: "Verifying your Zennify account and loading your role.",     detail: "OAuth callback received · upserting session" },
    default:  { title: "Loading…",                      body: "Just a moment.",                                              detail: "" },
  };
  const p = presets[variant] || presets.default;
  return (
    <div className={`loader-page ${dark ? "full-dark" : ""}`}>
      <div className="loader-card">
        <div className={`loader-glyph ${dark ? "dark" : ""}`}>
          <div className="ring" />
          <div className="ring-2" />
          <div className="core">
            <img src={assetUrl("brand_iconTeal", "brand/icon_teal.png")} width="36" height="36" alt="" style={{ borderRadius: 8, display: "block" }} />
          </div>
        </div>
        <div>
          <div className="loader-title">{title || p.title}</div>
          <div className="loader-body" style={{ marginTop: 6 }}>{body || p.body}</div>
        </div>
        <div className="loader-progress" />
        <div className="loader-detail">{detail || p.detail}</div>
      </div>
    </div>
  );
}

/* ── Inline section loader (for tab/route transitions) ─────────── */
function SectionLoader({ label, sub }) {
  return (
    <div className="loader-section">
      <div className="loader-glyph">
        <div className="ring" />
        <div className="ring-2" />
        <div className="core">
          <img src={assetUrl("brand_iconTeal", "brand/icon_teal.png")} width="34" height="34" alt="" style={{ borderRadius: 7 }} />
        </div>
      </div>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--z-dark)" }}>{label || "Loading…"}</div>
        <div style={{ fontSize: 11.5, color: "var(--z-muted)", marginTop: 4 }}>{sub || "Pulling fresh data"}</div>
      </div>
      <div className="loader-progress" />
    </div>
  );
}

/* ── Connection / latency watcher ────────────────────────────────── */
function ConnectionWatcher() {
  const [state, setState] = useState("ok"); // ok | slow | offline | unreachable
  const [retryIn, setRetryIn] = useState(null);

  useEffect(() => {
    const onOffline = () => setState("offline");
    const onOnline  = () => setState("ok");
    window.addEventListener("offline", onOffline);
    window.addEventListener("online",  onOnline);
    if (typeof navigator !== "undefined" && navigator.onLine === false) setState("offline");
    // Watch effective connection type for "slow" condition
    const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (c) {
      const onChange = () => {
        const et = c.effectiveType;
        if (state === "offline") return;
        if (et === "slow-2g" || et === "2g") setState("slow");
        else if (state === "slow") setState("ok");
      };
      c.addEventListener && c.addEventListener("change", onChange);
      onChange();
      return () => {
        window.removeEventListener("offline", onOffline);
        window.removeEventListener("online",  onOnline);
        c.removeEventListener && c.removeEventListener("change", onChange);
      };
    }
    return () => {
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("online",  onOnline);
    };
  }, []);

  // Simulated retry countdown if offline
  useEffect(() => {
    if (state !== "offline" && state !== "unreachable") { setRetryIn(null); return; }
    setRetryIn(12);
    const id = setInterval(() => setRetryIn(r => r == null ? null : (r <= 1 ? 12 : r - 1)), 1000);
    return () => clearInterval(id);
  }, [state]);

  if (state === "ok") return null;
  if (state === "offline") {
    return (
      <div className="offline-banner">
        <Icon name="warn" size={14} />
        <span><strong>You're offline.</strong> Cached views still work — live updates paused. Reconnecting{retryIn != null ? ` in ${retryIn}s` : ""}…</span>
      </div>
    );
  }
  if (state === "slow") {
    return (
      <div className="offline-banner warn">
        <Icon name="info" size={14} />
        <span><strong>Slow connection.</strong> Some views may take a few extra seconds to load.</span>
      </div>
    );
  }
  if (state === "unreachable") {
    return (
      <div className="offline-banner">
        <Icon name="warn" size={14} />
        <span><strong>Service temporarily unreachable.</strong> Retrying{retryIn != null ? ` in ${retryIn}s` : "…"}</span>
      </div>
    );
  }
  return null;
}

/* ── Export to window ────────────────────────────────────────────── */
Object.assign(window, {
  useState, useEffect, useRef, useMemo, useCallback, createContext, useContext,
  AppCtx, useApp,
  Icon, BrandMark, ZennifyWordmark, PillarBadge, MaturityChip, ToastStack,
  LoadingScreen, SectionLoader, ConnectionWatcher,
  parseHash, buildHash, navigate, useRoute,
  fmtDate, fmtAssets, fmtPct, relTime, FreshnessDot, fx,
  assetUrl, sessionUser, grantedRole, signOutSession,
  useLivePage, useLiveEntity, liveSection, liveSectionState,
});
