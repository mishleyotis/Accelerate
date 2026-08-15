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
   every route). Absent prints an em dash.

   2026-08-14, the no-em-dash pass: this one SURVIVES, deliberately. fx returns
   a STRING and ~90 call lines across 7 modules depend on that (grep `fx(` under
   apps/web/proto; the count moves as the sweep lands, so re-derive it rather
   than trust this number). Roughly half interpolate it into a template literal
   — Peer ${fx(peer,1)} · M${fx(ceiling,1)} · the lo-hi range pair · money()'s
   ${fx(v)}${unit} — where a returned React element prints "[object Object]",
   and returning any longer word ("Not stated") glues into "Mnot stated" and
   "$Not stated". Neither the type nor the string can change from in here.

   The truthiness trap, for whoever takes the follow-up: grep `fx(…) || "-"`.
   Those sites look like they fall back to a hyphen; they do not. "—" is TRUTHY,
   so the `||` never fires and they render the em dash. A "fix" that returns ""
   would flip them all on and swap one dead end for another.

   The real fix is per-caller, not here: each site that renders a bare score
   guards on null and renders <EnrichmentGap> itself, and fx is left to format
   numbers it was actually given. Until that lands, the return below is the one
   dead end still reaching the screen from this file, and Gate C
   (scripts/gate_c_no_render_dead_ends.py) flags it. It is deliberately NOT in
   that gate's ALLOWED list: this is real debt, not a legitimate literal, and
   allowlisting it would hide the very thing the gate exists to surface. */
function fx(v, digits) {
  const n = Number(v);
  return (v === null || v === undefined || v === "" || !isFinite(n))
    ? "—" : n.toFixed(digits === undefined ? 1 : digits);
}

/* Prose that renders as a sentence, starting like one.

   The producer writes some fields as sentence fragments and some as
   sentences, and a fragment dropped into a paragraph slot renders as
   "with plans to increase our member base…" — a lowercase opening under a
   heading. The real fix is upstream (the connector refuses it now), but a
   promoted run already in the database still has to read correctly, so the
   render boundary raises the first letter too.

   What it must NOT do is "correct" a name. A first word that carries an
   uppercase letter anywhere after its first character is deliberate —
   nCino, iPhone, eBay — and is left exactly as written, as is anything
   starting with a URL, an identifier or a digit. */
/* Em and en dashes become hyphens in promoted prose.

   The producer writes them because they read well in a document. On these
   surfaces they are a liability: the em dash is the one punctuation mark
   that survives every copy-paste into a CRM note, an email or a deck and
   marks the text as machine-written, and at small sizes it is hard to tell
   from a minus sign beside a score. A hyphen carries the same clause break
   and none of that.

   Spaced dashes collapse to a spaced hyphen; an unspaced dash between two
   words keeps its spacing rather than gluing them together. A MINUS sign in
   a figure is not a dash and is not touched — this only ever runs over
   prose, never over a number. */
function dashes(s) {
  return String(s)
    .replace(/\s+[—–]\s+/g, " - ")
    .replace(/([^\s])[—–]([^\s])/g, "$1-$2")
    .replace(/[—–]/g, "-");
}

function sentence(s) {
  if (typeof s !== "string") return s;
  // Each branch below decides only about CAPITALISATION, so each returns the
  // dash-normalised text. Returning the original here was the bug that would
  // have left every already-capitalised sentence — which is most of them —
  // with its em dashes intact.
  const t = dashes(s).trimStart();
  if (!t) return s;
  const first = t.split(/\s/)[0];
  // A URL is left exactly as written: its hyphens are part of the address.
  if (/^(https?:|www\.)/i.test(first)) return s;
  if (/[A-Z]/.test(first.slice(1))) return t;      // nCino, iOS, eBay
  if (!/^[a-z]/.test(t)) return t;                 // digits, quotes, already capital
  return t[0].toUpperCase() + t.slice(1);
}

/* Renderable text from a payload value that may not be a string.

   React throws on an object child and there is no error boundary above these
   cards, so one wrapped value takes the page down. Several contract fields
   are objects with the prose inside them — `strategic_alignment` is
   `{score, statement}` — and a card that reads the field directly renders
   either the statement or a crash, depending on the run. This unwraps by the
   naming keys the contract actually uses, joins a list, and returns null for
   anything it cannot render, so the caller shows its absent state instead.
   Sentence-cased on the way out for the same reason `sentence` exists. */
function asText(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "string") return v ? sentence(v) : null;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(asText).filter(Boolean).join(" · ") || null;
  if (typeof v === "object") {
    for (const k of ["statement", "text", "label", "name", "title", "value"]) {
      const t = asText(v[k]);
      if (t) return t;
    }
    return null;
  }
  return String(v);
}

/* The bounds a producer stated for a measure, read from their own words.

   Producers write a scale the way the source writes it, which is at least
   four notations: "NPS -100..100", "0-100 % of employees agreeing",
   "1-5 stars", "0 to 10". A reader that understands only one of them does
   not fail loudly — it returns null, the bar draws nothing, and the card
   shows a number beside an empty track as though the measure had no scale.
   That is what happened to every row whose scale was not written with "..":
   Great Place To Work at 88 and the App Store at 4.9 both rendered blank
   while NPS, alone in using "..", drew a bar.

   Both bounds matter, not just the top. NPS runs from -100, so 79.8 is
   nine tenths of the way up its range and dividing by the maximum alone
   understates it. Returns {min, max} or null — null is still the honest
   answer for a scale nobody stated, and the caller draws no bar. */
function scaleBounds(scale) {
  const s = String(scale || "").trim();
  if (!s) return null;
  const num2 = (a, b) => {
    const lo = Number(a), hi = Number(b);
    return isFinite(lo) && isFinite(hi) && hi > lo ? { min: lo, max: hi } : null;
  };
  // "a..b" first: it is the only notation that can carry a negative low
  // bound without the hyphen being ambiguous.
  let m = s.match(/(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)/);
  if (m) return num2(m[1], m[2]);
  // "a to b", "a-b", "a–b". A leading minus is honoured; an interior one
  // is the separator.
  m = s.match(/(-?\d+(?:\.\d+)?)\s*(?:to|[-–—])\s*(-?\d+(?:\.\d+)?)/i);
  if (m) return num2(m[1], m[2]);
  // A bare percentage or star rating states its bounds by convention.
  if (/%/.test(s)) return { min: 0, max: 100 };
  m = s.match(/(\d+(?:\.\d+)?)\s*stars?/i);
  if (m) return num2(1, m[1]);
  return null;
}

/* Where a value sits within its own stated scale, 0..1, or null when the
   scale is not stated. Never assumes bounds: an unstated scale draws no
   bar rather than a bar against invented bounds. */
function scaleFraction(value, scale) {
  const b = scaleBounds(scale);
  const v = Number(value);
  if (!b || !isFinite(v)) return null;
  return Math.max(0, Math.min(1, (v - b.min) / (b.max - b.min)));
}

/* ── Render boundaries ────────────────────────────────────────────────
   React unmounts the WHOLE tree when a render throws and nothing catches
   it. This app had exactly one error boundary and it lived in
   pages-live-client.jsx, a module the router never renders — so a single
   malformed list item (a string where the contract says object, a null
   where a card reads a field off it) took the entire application down to a
   literally empty <body>. No message, no chrome, no way back but a reload
   onto the same payload.

   The unit of failure has to be the CARD. One boundary around the app only
   moves the blank page up a level: the reader still loses every surface
   because one field on one card was the wrong shape. So each card and each
   section gets its own, and a card that cannot render says so in its own
   frame while its neighbours render normally.

   What the notice may say is limited on purpose. It names the section, it
   states that THIS PAGE could not render it, and it stops. It never blames
   the reader, never guesses at the data, and never prints a plausible
   substitute — a card that fabricates on failure is worse than a blank one.
   The thrown message is shown verbatim as small mono text because that is
   the one fact we actually have, and an analyst reading it can tell an
   engineer which field is wrong.

   Trips are also recorded on window.__DMA_RENDER_FAILURES. A boundary that
   silently swallowed crashes would hide from the QA sweep exactly the class
   of defect the sweep exists to find; automation reads the list. */
class RenderBoundary extends React.Component {
  constructor(props) { super(props); this.state = { failed: null }; }
  static getDerivedStateFromError(err) { return { failed: err }; }
  componentDidCatch(err, info) {
    const rec = { name: this.props.name || "unnamed",
                  message: (err && err.message) || String(err),
                  stack: (info && info.componentStack) || null,
                  at: new Date().toISOString() };
    if (typeof window !== "undefined") {
      window.__DMA_RENDER_FAILURES = window.__DMA_RENDER_FAILURES || [];
      window.__DMA_RENDER_FAILURES.push(rec);
    }
    if (typeof console !== "undefined" && console.error) {
      console.error(`render failed in ${rec.name}:`, err);
    }
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return this.props.fallback(this.state.failed);
  }
}

/* The error's own words, small and mono. Never the only thing shown. */
function boundaryDetail(err) {
  const msg = (err && err.message) || String(err || "");
  if (!msg) return null;
  return (
    <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)",
                                     marginTop: 6, wordBreak: "break-word" }}>
      {msg}
    </div>
  );
}

/* One card. The page keeps its shape; this frame keeps the card's. */
function CardBoundary({ name, children }) {
  return (
    <RenderBoundary name={name} fallback={(err) => (
      <div className="card flush" data-render-failed={name || "card"}>
        <div className="card-head">
          <div className="row"><Icon name="warn" size={14} /><h3>{name || "This card"}</h3></div>
          <span className="b b-org">Could not render</span>
        </div>
        <div className="card-body">
          <div style={{ fontSize: 11.5, color: "var(--z-muted)", lineHeight: 1.55 }}>
            This page could not render {name ? `the ${name} card` : "this card"} from
            the run's payload. Nothing was changed in the run, and the rest of the
            page is unaffected.
          </div>
          {boundaryDetail(err)}
        </div>
      </div>
    )}>{children}</RenderBoundary>
  );
}

/* One row/tile inside a card — an insight card, a list item. Same rules,
   card-tile sized, so one bad item costs one item and not the list. */
function ItemBoundary({ name, children }) {
  return (
    <RenderBoundary name={name} fallback={(err) => (
      <div className="card-tile" data-render-failed={name || "item"}
           style={{ borderStyle: "dashed" }}>
        <div className="row" style={{ marginBottom: 6 }}>
          <span className="b b-org">Could not render</span>
          <span className="spacer" />
          <span className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{name || ""}</span>
        </div>
        <div style={{ fontSize: 11.5, color: "var(--z-muted)", lineHeight: 1.5 }}>
          This item could not be rendered from the run's payload. The others in
          this list are unaffected.
        </div>
        {boundaryDetail(err)}
      </div>
    )}>{children}</RenderBoundary>
  );
}

/* One whole page, as the last stop before the blank body. Only reached when
   the fault is above every card — in the page's own frame or in the merge
   that feeds it — so it offers the two ways out a reader actually has. */
function PageBoundary({ name, children }) {
  return (
    <RenderBoundary name={name} fallback={(err) => (
      <div className="empty" data-render-failed={name || "page"}>
        <div className="icon"><Icon name="warn" size={20} /></div>
        <h3>This page could not be rendered</h3>
        <p>
          The {name ? `${name} ` : ""}surface holds a value this page cannot draw.
          The run is unchanged and the other dashboards still open from the tabs
          above.
        </p>
        {boundaryDetail(err)}
      </div>
    )}>{children}</RenderBoundary>
  );
}

/* ── The empty state the API already sent ─────────────────────────────
   A section with nothing in it is not a blank card. The envelope carries a
   `empty_state` — kind, reason, what was searched, what would close it — and
   a surface that renders a void instead is throwing away the one answer the
   run gave. Worse is the fabricated zero-assertion: "no critical role gaps"
   printed off an EMPTY roster asserts a check nobody ran.

   Three cases, all stated plainly:
     no section state   the section did not promote at all
     empty_state        the producer's own account of the absence
     state, no reason   it promoted and carries nothing, which is all we know */
/* Whether the enrichment a surface DEPENDS on actually reached it.

   Renders nothing when the surface is not enrichment-dependent, and nothing
   when it is and is healthy — a badge on every card is noise, and the reader
   only needs telling when what they are looking at is short of what it should
   be. `enrichment_status` is computed at read from
   packages/shared/enrichment_register.json; see dma_api/computed.py.

   The line the build owner asked for on 2026-08-14: a twelve-row technology
   register and a fifty-one-row one rendered identically, and the short one
   read as the client's whole estate. */
function EnrichmentFlag({ s, what }) {
  if (!s || !s.required) return null;
  const thin = !!s.thin;
  const notRun = !s.ran;
  if (!thin && !notRun) return null;
  return (
    <div className="row" data-enrichment={what || "surface"}
         style={{ gap: 6, marginTop: 6, flexWrap: "wrap", alignItems: "baseline" }}>
      <span className="b b-org" style={{ whiteSpace: "nowrap" }}>
        {notRun ? "Scan did not run" : `Thin ${what || "surface"}`}
      </span>
      <span style={{ fontSize: 11, color: "var(--z-muted)", lineHeight: 1.5 }}>
        {s.thin_reason
          || `no served row records that ${(s.sources || []).join(" or ")} reached this surface`}
        {s.count != null && s.thin_below
          ? ` (${s.count} of ${s.thin_below} expected)` : ""}
        {s.closes_with ? ` · closes with ${s.closes_with}` : ""}
      </span>
    </div>
  );
}

/* ── The em dash, replaced ────────────────────────────────────────────
   Build owner, 2026-08-14: "Never place an em dash. There should always be a
   way to send a signal to the MCP to give us an enrichment of the empty field."

   An em dash is a dead end. It looks identical whether the producer searched
   and found nothing, held a figure that failed the identity gate, or was never
   asked for the field at all — and those are three different facts, only one of
   which is a finding. Worse, it is terminal: a reader who sees one has no route
   to getting it filled.

   So every empty spot renders this instead, and it says which of the three it
   is. The connector computes the same set from the promoted payload against the
   contract (`list_enrichment_gaps`), so a gap a reader sees here is already on
   the producer's worklist — the signal is derived, not clicked, and therefore
   cannot be forgotten.

   AUDIENCE. Internal names the gap and says it is queued. Customer gets the
   plain statement and no queue language: the queue is our workflow, not theirs,
   and the leadership panel's own comment settles the shape — an affordance that
   promises an action the reader cannot take is worse than the absence. */
function EnrichmentGap({ what, reason, held, audience, compact }) {
  /* OWNER ADJUDICATION 2026-08-14, superseding the three-state vocabulary
     below: "It should not state queued for enrichment or held. It should
     enrich and clarify real time and give the real data."

     So this renders NOTHING. A value that cannot be established is not
     announced to the reader in our workflow's language; the field is enriched
     and shown, or it does not appear.

     WHY THIS IS NOT A RETURN TO THE ORIGINAL DEFECT. Hiding an absent field is
     what kept the missing website invisible for five days — but only because
     nothing else was counting. Now three things are, none of them on the page:
     `list_enrichment_gaps(run_id)` computes the empty set from the staged
     payload and hands it to the producer as a worklist,
     `audit_promoted_client.py` fails on a field null across 100% of its rows,
     and CG-18 refuses a submission missing a must-present member outright. The
     reader stops seeing our bookkeeping; the system does not stop keeping it.

     Kept rather than deleted so the call sites stay self-documenting about
     WHICH field is absent, and so the policy lives in one place if it is ever
     revisited. A caller that can drop its whole row should do that instead —
     see FirmographicsPanel, which builds a filtered row list. */
  return null;

  /* eslint-disable no-unreachable */
  /* DEFAULT-DENY on the audience, deliberately inverted from the usual
     `=== "customer"` test used elsewhere in this file.

     `audience` is "internal" or "customer" and this component is rendered from
     ~50 sites across ten modules, several of which had to have the prop
     THREADED to them. A site that misses it would, under the usual test, show a
     CUSTOMER the internal wording — "queued for enrichment" is our workflow
     language and it names a backlog the client is not party to. Under this
     test, the same mistake shows an internal reader the plainer sentence: less
     informative, and harmless.

     Invariant 5's shape, applied one layer out: the unmarked case is the
     protected one. */
  const isCust = audience !== "internal";
  // A held field is the one honest absence: the producer ran the ladder, the
  // figure failed, and the reason is the finding. It is not a gap to queue.
  if (held) {
    return (
      <span className="enrich-gap" data-gap="held" title={reason || undefined}
            style={{ color: "var(--z-muted)", fontStyle: "italic" }}>
        {isCust ? "Not established" : "Held"}
        {!isCust && reason ? ` · ${reason}` : ""}
      </span>
    );
  }
  if (isCust) {
    return (
      <span className="enrich-gap" data-gap="absent"
            style={{ color: "var(--z-muted)", fontStyle: "italic" }}>
        Not established in this assessment
      </span>
    );
  }
  return (
    <span className="enrich-gap" data-gap="queued"
          title={what ? `${what} is empty on the promoted run and is in the connector's enrichment worklist` : undefined}
          style={{ display: "inline-flex", alignItems: "baseline", gap: 6,
                   flexWrap: "wrap" }}>
      <span style={{ color: "var(--z-muted)", fontStyle: "italic" }}>
        Not stated
      </span>
      {compact ? null : (
        <span className="b b-org" style={{ whiteSpace: "nowrap" }}>
          queued for enrichment
        </span>
      )}
    </span>
  );
}

/* A finding reference, however the payload happens to carry it.
   CG-21 now refuses a serialised object at submit, so new runs cannot
   reintroduce this — but a run promoted BEFORE that gate existed carried
   `blocking_findings` as JSON-encoded strings, and the ladder printed
   '{"f_id": "F-1", "e_ids": [...]}' into a chip. The serving path stores
   what it was given, so the repair has to hold on this side too for any
   payload already in the database.

   Order matters: the id if there is one, then any single string field, and
   only then the raw value — a chip that says something wrong is worse than
   one that says the id it could establish. */
function findingChipId(f) {
  if (f == null) return "";
  let v = f;
  if (typeof v === "string") {
    const s = v.trim();
    if (s.startsWith("{") || s.startsWith("[")) {
      try { v = JSON.parse(s); } catch (e) { return s; }
    } else {
      return s;
    }
  }
  if (Array.isArray(v)) return v.map(findingChipId).filter(Boolean).join(", ");
  if (typeof v === "object") {
    const id = v.f_id || v.finding_id || v.id || v.rec_id;
    if (id) return String(id);
    const first = Object.values(v).find((x) => typeof x === "string" && x.trim());
    return first ? String(first) : "Finding";
  }
  return String(v);
}

function SectionEmpty({ section, absent, empty }) {
  const state = (typeof DMA !== "undefined" && typeof DMA.sectionStateFor === "function")
    ? DMA.sectionStateFor(section) : null;
  const es = (state && state.empty_state) || null;
  const kind = es && es.kind ? String(es.kind).replace(/_/g, " ") : null;
  const searched = (es && Array.isArray(es.sources_searched)) ? es.sources_searched : [];
  const line = { fontSize: 11.5, color: "var(--z-muted)", lineHeight: 1.55 };
  return (
    <div data-empty-section={section}>
      <div style={line}>
        {!state ? (absent || "This section did not promote for this run.")
                : es ? `${kind ? `${kind}. ` : ""}${es.reason || empty || "The section promoted with nothing in it."}`
                     : (empty || "The section promoted with nothing in it.")}
      </div>
      {es && es.closure_condition ? (
        <div style={{ ...line, marginTop: 6 }}>
          <strong style={{ color: "var(--z-body)" }}>Closes when · </strong>{es.closure_condition}
        </div>
      ) : null}
      {searched.length ? (
        <details style={{ marginTop: 6 }}>
          <summary style={{ fontSize: 11, color: "var(--z-mid)", cursor: "pointer" }}>
            {searched.length} source{searched.length === 1 ? "" : "s"} searched
          </summary>
          <ul style={{ margin: "6px 0 0 16px", padding: 0 }}>
            {searched.map((s, i) => (
              <li key={i} style={{ ...line, marginBottom: 3 }}>{asText(s)}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

/* The same account, at the foot of a card that DID render rows. A section can
   carry data and a declared absence at once; this renders only the absence,
   and renders nothing at all when the section declared none. */
function SectionEmptyFoot({ section, title }) {
  const state = (typeof DMA !== "undefined" && typeof DMA.sectionStateFor === "function")
    ? DMA.sectionStateFor(section) : null;
  if (!state || !state.empty_state) return null;
  return (
    <div style={{ marginTop: 12, borderTop: "1px solid var(--z-sep)", paddingTop: 8 }}>
      <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase",
                    letterSpacing: ".06em", marginBottom: 4 }}>
        {title || "Not established"}
      </div>
      <SectionEmpty section={section} />
    </div>
  );
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
    // An unknown name renders NOTHING. The fallback used to be a filled
    // circle, which is indistinguishable from a deliberate bullet: a single
    // mistyped name put a stray dot in front of a card heading and nothing in
    // the code said so. Absent beats a mark nobody asked for.
    default:          return null;
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
    // `short` is the sidebar footer's compact name (chrome.jsx, .sb-foot-name).
    // Nothing enriches a logged-out session, so this is a plain statement of
    // fact, not an EnrichmentGap: there is no field for the producer to fill.
    return { name: "Not signed in", short: "Not signed in", first: "there",
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
function useLiveEntity(displayId, audience, runId, actingRole) {
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
      // The acting-as role travels with every read so the SERVER decides what
      // the previewed role may see. It can only narrow the session's granted
      // role (lib/identity.effectiveRole), so this is a request, not a grant.
      if (actingRole) q.set("role", actingRole);
      if (runId) q.set("run", runId);
      for (const k of Object.keys(extra || {})) q.set(k, extra[k]);
      return q.toString();
    };
    const get = (path) => fetch(path)
      .then(r => r.json().then(body => ({ ok: r.ok, status: r.status, body })))
      // A page an audience may not see (403) or that has nothing promoted is
      // a legitimate answer, not a failure: it becomes an absent section.
      .catch(() => ({ ok: false, status: 0, body: null }));

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
      // A 403 is the server exercising default-deny, not a fault: the API
      // withholds a whole dashboard from the customer audience, and an AE has
      // no route to D5. The reason it sends is what the locked state prints,
      // so the tab renders "withheld, and why" instead of a white page.
      const withheld = {};
      pages.forEach((p, i) => {
        if (results[i].ok) { byPage[p] = results[i].body; return; }
        if (results[i].status === 403) {
          withheld[p] = (results[i].body && results[i].body.detail)
            || "this dashboard is not available to your role or audience";
        }
      });
      const evidence = results[pages.length].ok ? results[pages.length].body : null;
      const subcaps = results[pages.length + 1].ok
        ? (results[pages.length + 1].body.subcaps || []) : [];

      if (!Object.keys(byPage).length) {
        setState({ status: "error", code: "no_promoted_pages", withheld });
        return;
      }
      // The adapter runs INSIDE a promise, so anything it throws — a section
      // whose list arrived as a number, so `.map` is not a function — became an
      // unhandled rejection and the state stayed "loading" for ever: the page
      // sat on its spinner with no error, no timeout and nothing in the UI to
      // say why. A read that cannot be adapted is a failed read, and it says so.
      let built;
      try {
        built = window.buildLiveEntity(displayId, byPage, { evidence, subcaps });
      } catch (err) {
        if (typeof console !== "undefined" && console.error) {
          console.error("buildLiveEntity failed", err);
        }
        window.DMA_ENTITY = null;
        setState({ status: "error", code: "payload_unreadable", withheld,
                   detail: (err && err.message) || String(err) });
        return;
      }
      window.DMA_ENTITY = built;
      setState({ status: "ready", entity: built, withheld,
                 run: built.run, audience: audience || "internal" });
      // Producer-authored answers are a run-scoped grain read, and nothing on
      // first paint needs them: the panel answers from the promoted prose it
      // already holds, with no request at all. So this is fetched BESIDE the
      // render rather than before it — it cannot add a millisecond to the
      // page, and when the connector starts writing them they simply become
      // the preferred answer on the next open.
      get(`/api/entity/${id}/answers?${qs()}`).then((r) => {
        if (cancelled || !r.ok || window.DMA_ENTITY !== built) return;
        const rows = window.adaptAnswers(r.body);
        if (rows.length) built.answers = rows;
      });
    });
    return () => { cancelled = true; };
  }, [LIVE, displayId, audience, runId, actingRole]);

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
/* Assets, honouring the unit the payload states.
   The firmographics contract states magnitude in a `unit` field — Baxter's is
   `{value: "6.5", unit: "USD billions"}` — so the bare number is 6.5, not
   6_500_000_000. Formatting it by size alone printed "$6.5", which reads as six
   dollars fifty for a $6.5bn balance sheet. The unit is now applied first. */
function fmtAssets(n, unit) {
  // null and 0 used to share one branch, so a STATED zero printed exactly
  // like an unstated figure. A zero on a balance-sheet field is almost
  // certainly a producer error — but that is the identity gate's call, not a
  // formatter's; the formatter's only job is to never make two different
  // facts look the same. Callers guard null and render the gap themselves.
  if (n == null || n === "" || !isFinite(Number(n))) return null;
  if (Number(n) === 0) return "$0";
  const u = String(unit || "").toLowerCase();
  const mult = /billion|\bbn\b/.test(u) ? 1e9
             : /million|\bmm?\b/.test(u) ? 1e6
             : /thousand|\bk\b/.test(u) ? 1e3 : 1;
  const v = Number(n) * mult;
  if (v >= 1e9) return `$${(v/1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v/1e6).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
}
/* A null percentage used to print "0%" — the one formatter in this file that
   answered "nobody measured this" with a MEASUREMENT. Invariant 9: derived
   values are computed or null, never a default that looks like data. Returns
   null so the caller renders its gap; every current call site already guards,
   and the next one that does not will now show nothing rather than a lie. */
function fmtPct(n) {
  return (n == null || n === "" || !isFinite(Number(n)))
    ? null : `${(Number(n)*100).toFixed(0)}%`;
}
/* ── Entity search: ONE rule, three call sites ───────────────────────
   The acceptance doc's DIR-02 and SRCH-10 both require the directory and the
   global search to match on "name and display ID". Neither did. The global
   popover matched name+domain, the directory matched name+domain, and the
   prospecting picker matched name alone — three controls, three answers to the
   same question, and the identifier a reader actually holds (it is in the URL,
   in every alert row and on the printed scorecard) matched in none of them.

   Adjudicated 2026-08-15 in favour of the doc: a directory that cannot find an
   entity by its own identifier is a real gap, and the fix is additive. The rule
   lives here rather than at the call sites because "held in two places, drifts"
   is exactly what produced the three-way disagreement above.

   `display_id` arrives as both `id` and `slug` from /v1/directory; both are
   read so a shape change on either side cannot silently narrow the match. */
function entityMatches(e, q) {
  const ql = String(q == null ? "" : q).toLowerCase().trim();
  if (!ql) return true;
  return [e && e.name, e && e.domain, e && e.id, e && e.slug]
    .some(v => v != null && String(v).toLowerCase().includes(ql));
}
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
    slow:     { title: "Slow connection",               body: "The network is sluggish - we're still working on it.",      detail: "Falling back to cached responses where possible" },
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
  RenderBoundary, CardBoundary, ItemBoundary, PageBoundary,
  SectionEmpty, SectionEmptyFoot, EnrichmentFlag, EnrichmentGap, findingChipId,
  LoadingScreen, SectionLoader, ConnectionWatcher,
  parseHash, buildHash, navigate, useRoute,
  fmtDate, fmtAssets, fmtPct, relTime, FreshnessDot, fx, entityMatches,
  assetUrl, sessionUser, grantedRole, signOutSession,
  useLivePage, useLiveEntity, liveSection, liveSectionState,
});
