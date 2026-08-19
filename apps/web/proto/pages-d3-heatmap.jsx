/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · D3 Maturity Heatmap (refactored)
   Multiple view modes · synthesis drawer · working overlays
   ═══════════════════════════════════════════════════════════════════════ */

/* ── Peer figures: read, never derived ──────────────────────────────────
   Every peer number on this page was manufactured, in four different ways, and
   all four rendered as a benchmark an AE would quote:

     · pillar zoom     `const peer = score + 0.3` — a constant offset
     · category zoom   mean of `s.peerMedian` where every value is null, and
                       `a + null` is `a`, so 16 categories read "Peer 0.0"
     · subcap rows     `gap = s.peerMedian - s.score` → `null - 1.5` = -1.5,
                       printed as "+1.5 vs peer" in the ABOVE-peer colour on
                       every row, with the peer tick pinned at 0%
     · focus areas     the same null mean, plus hardcoded 2.5/2.8 fallbacks

   Peer medians genuinely do NOT exist at cell grain in this corpus — 0 of 765
   rows carry one. They exist at CATEGORY and PILLAR grain, which the run
   promotes and which were sitting unread. So: read the stated median at the
   grain that has one, inherit the category median at subcap grain and label it
   a proxy, and where nothing is stated render nothing — no tick, no delta, no
   "at peer" badge. A missing benchmark is not a benchmark of zero.

   `peerOf` returns {median, basis} where median may be null. Callers must
   branch on null rather than formatting it. */
function peerOf(median, basis) {
  const v = (median === null || median === undefined || median === "") ? null : Number(median);
  return { median: (v === null || !isFinite(v)) ? null : v, basis: basis || null };
}

/* The mean of the peer medians that EXIST, or null when none do. Never treats a
   missing value as zero and never divides by the full count. */
function peerMeanOf(rows) {
  const vals = (rows || [])
    .map(r => (r && r.peerMedian !== null && r.peerMedian !== undefined) ? Number(r.peerMedian) : null)
    .filter(v => v !== null && isFinite(v));
  if (!vals.length) return null;
  return vals.reduce((a, v) => a + v, 0) / vals.length;
}

/* A delta only exists when both sides do. */
function deltaOf(score, peer) {
  if (score == null || peer == null) return null;
  const d = Number(score) - Number(peer);
  return isFinite(d) ? d : null;
}

function numOf(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return isFinite(n) ? n : null;
}

/* The mean of the values that exist, or null. Never divides by the full count
   and never returns 0 for "nothing measured". */
function meanOf(values) {
  const vals = (values || []).map(numOf).filter(v => v !== null);
  if (!vals.length) return null;
  return vals.reduce((a, v) => a + v, 0) / vals.length;
}

/* ── Hover identification for heatmap cells ──────────────────────────────
   A score-only cell said what it was only after a click. Every cell that
   renders an individual subcap — and the category/pillar aggregates — now
   identifies itself on hover, twice over: a `title` attribute (works
   everywhere, but the native tooltip takes a second to appear) and one
   styled bubble per grid. The bubble is a single fixed-position div rendered
   once at grid level — never one per cell — fed by enter/leave only (no
   mousemove handlers, so hovering cannot cause a re-render storm) and
   positioned from the hovered cell's boundingClientRect. */
function subcapTipText(s) {
  const name = (s.name && s.name !== s.id) ? s.name : "unnamed in catalogue";
  return `${s.id} — ${name} · ${s.score != null ? fx(s.score, 1) : "no score"}`;
}

function useCellTip() {
  const [tip, setTip] = useState(null);
  // One state write on enter, one on leave. The label is computed by the
  // caller at render time, so hovering re-renders nothing but the bubble.
  const show = (label) => (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    setTip({ label, x: r.left + r.width / 2, top: r.top, bottom: r.bottom,
             flip: r.top < 64 });
  };
  const hide = () => setTip(null);
  return { tip, show, hide };
}

function CellTip({ tip }) {
  if (!tip) return null;
  const vw = (typeof window !== "undefined" && window.innerWidth) || 1024;
  // Keep the bubble on-screen: clamp its centre so a cell at either edge
  // still reads in full.
  const x = Math.min(Math.max(tip.x, 132), Math.max(vw - 132, 132));
  return (
    <div style={{
      position: "fixed", left: x,
      top: tip.flip ? tip.bottom + 7 : tip.top - 7,
      transform: tip.flip ? "translate(-50%, 0)" : "translate(-50%, -100%)",
      maxWidth: 248, padding: "5px 9px", borderRadius: 6,
      background: "var(--z-dark)", color: "#fff",
      fontSize: 11, lineHeight: 1.45, textAlign: "left",
      pointerEvents: "none", zIndex: 120,
      boxShadow: "0 2px 10px rgba(0,0,0,.28)",
    }}>{tip.label}</div>
  );
}

/* ── The run's own workbook table ────────────────────────────────────────
   `heatmap.workbook_scores` is the run's promoted pillar and category grain.
   app-root merges a WHITELIST of live fields onto the directory row and
   `workbookScores` is not on it, so `entity.workbookScores` is undefined here
   and every read of it silently fell back: sixteen categories read "Peer —"
   while the run states a median for all seventeen. Read the merged field
   first — when app-root starts carrying it this branch stops being used — and
   otherwise the registry the loader installs, which is the same object. */
function workbookScoresOf(entity) {
  if (entity && entity.workbookScores) return entity.workbookScores;
  const reg = (typeof window !== "undefined" && window.DMA_ENTITY) || null;
  return (reg && reg.workbookScores) || null;
}

/* ── Is a section's empty state a REASON, or the serving tier's stub? ────
   `SectionEmpty` renders whatever `empty_state` the section carries, and two
   sections on this run carry the SERVING TIER's stub rather than the
   producer's account:

     {kind: "section_not_promoted", reason: "no serving row for this run",
      sources_searched: []}

   That is what `pages.py` writes when `assemble` returns None, and `assemble`
   returns None whenever the writer persisted zero rows — which is exactly
   what a section with an EMPTY COLLECTION does. So *promoted with nothing in
   it* and *never promoted* are indistinguishable downstream, and the reason
   the producer wrote for `workbook_scores` (and for `cohort_patterns`) is
   discarded at promote. The durable fix is an envelope-only serving row; on
   this side of the wire, a reader must not be handed the plumbing sentence
   "no serving row for this run" where a reason belongs.

   Returns `stub: true` when the state carries nothing a reader could act on,
   and the caller then renders its own honest sentence. When the serving tier
   starts carrying the producer's state through, `stub` goes false on its own
   and the producer's words render with no further change at the call site. */
function sectionReason(key) {
  const state = (typeof DMA !== "undefined" && typeof DMA.sectionStateFor === "function")
    ? DMA.sectionStateFor(key) : null;
  const es = (state && state.empty_state) || null;
  const reason = (es && typeof es.reason === "string") ? es.reason.trim() : "";
  const stub = !es
    || (!es.closure_condition
        && !((es.sources_searched || []).length)
        && (!reason || /^no serving row for this run\.?$/i.test(reason)));
  return { state, es, stub };
}

/* The contract allows either shape for the workbook tables: an id-keyed object
   ({"P1C1": {score…}}, which is what the API sends) or a list of rows carrying
   their own id. Both become a list of rows with `id`. */
function promotedRowsOf(table, idKey) {
  if (!table) return [];
  if (Array.isArray(table)) {
    return table.map(r => ({ ...r, id: r[idKey] || r.id || null }))
                .filter(r => r.id);
  }
  return Object.keys(table).map(k => ({ ...table[k], id: k }));
}

/* ── Category rows: the RUN's categories, not the catalogue's ────────────
   The grid iterated `DMA.CATEGORIES` — the current v7.0 catalogue, sixteen
   entries — so this run's seventeenth, P1C5, rendered nowhere: 30 scored cells
   and a promoted category score of 2.03 were invisible, the P1 header counted
   194 cells above four columns covering 164, and the pillar read 3.4 (a mean
   of four category means) against its promoted 3.11 one zoom away. P1C5 is the
   ESG category v7.0 removed, so a run pinned to the seventeen-category shape
   legitimately scores cells the catalogue cannot name.

   Rows are therefore the union of what the run PROMOTED and what it SCORED,
   sorted by id (PxCy sorts naturally). A category the catalogue cannot name
   still appears, labelled with its id and marked as unnamed — never dropped,
   and never given a name from anywhere. */
function runCategoriesOf(entity) {
  const ws = workbookScoresOf(entity);
  const rows = {};
  for (const r of promotedRowsOf(ws && ws.categories, "category_id")) {
    rows[r.id] = { id: r.id, score: numOf(r.score), peer: numOf(r.peer_median),
                   band: r.band || null, source_cell: r.source_cell || null,
                   promoted: true };
  }
  const cells = Array.isArray(entity && entity.subcaps) ? entity.subcaps : [];
  for (const s of cells) {
    if (s.category && !rows[s.category]) {
      rows[s.category] = { id: s.category, score: null, peer: null, band: null,
                           source_cell: null, promoted: false };
    }
  }
  return Object.keys(rows).sort().map(id => {
    const cat = DMA.getCategory(id) || null;
    const mine = cells.filter(s => s.category === id);
    return {
      ...rows[id],
      // The pillar comes from the id itself when the catalogue cannot answer —
      // deterministic, not inferred.
      pillar: (cat && cat.pillar) || id.slice(0, 2),
      name: (cat && cat.name) || null,
      inCatalogue: !!cat,
      weight: cat && cat.weight != null ? Number(cat.weight) : null,
      cells: mine,
      thin: mine.filter(s => s.thin).length,
      // Only used where the run promoted no category score; labelled as a mean
      // wherever it renders, so it is never mistaken for the workbook's figure.
      cellMean: meanOf(mine.map(s => s.score)),
    };
  });
}

/* Pillar rows, in the same spirit: the promoted pillar score is the pillar's
   score. A mean of category means is a different number (P1: 3.4 vs 3.11) and
   the page showed both. */
function runPillarsOf(entity) {
  const cats = runCategoriesOf(entity);
  const ws = workbookScoresOf(entity);
  const promoted = {};
  for (const r of promotedRowsOf(ws && ws.pillars, "pillar_id")) promoted[r.id] = r;
  const ids = [];
  for (const p of DMA.PILLARS || []) if (!ids.includes(p.id)) ids.push(p.id);
  for (const c of cats) if (!ids.includes(c.pillar)) ids.push(c.pillar);
  for (const id of Object.keys(promoted)) if (!ids.includes(id)) ids.push(id);
  return ids.sort().map(id => {
    const meta = (DMA.PILLARS || []).find(p => p.id === id) || null;
    const mine = cats.filter(c => c.pillar === id);
    const overview = ((entity && entity.pillar_scores) || {})[id];
    const overviewPeer = ((entity && entity.pillar_peer_medians) || {})[id];
    return {
      id,
      name: (meta && meta.name) || null,
      short: (meta && meta.short) || null,
      inCatalogue: !!meta,
      score: numOf(overview) != null ? numOf(overview)
                                     : numOf(promoted[id] && promoted[id].score),
      peer: numOf(overviewPeer) != null ? numOf(overviewPeer)
                                       : numOf(promoted[id] && promoted[id].peer_median),
      cats: mine,
      // Summed from the columns the grid actually draws, so the header count
      // cannot disagree with them again.
      cellCount: mine.reduce((a, c) => a + c.cells.length, 0),
      thin: mine.reduce((a, c) => a + c.thin, 0),
    };
  });
}

/* ── A cell's citations: the list the producer promoted ──────────────────
   The drawer reverse-derived its evidence list from `DMA.EVIDENCE[].subcaps`
   — the run-scoped link table — and that disagreed with the cell's own
   promoted citation list on 65 of 69 cells: P4C1.1.1 promoted four ids and the
   drawer showed five, including a core-banking item the producer never cited
   for that cell, while P1C1.1.1 lost one it did. `heatmap.cell_evidence` is
   what the producer wrote and what the evidence gate checked, so it is what
   renders. The reverse derivation stays as the fallback for the ~90% of cells
   that promoted no list, and the caller says which of the two it is showing.

   An id that resolves to nothing in the evidence store is shown as an
   unresolved id rather than dropped — fail-closed evidence means a dangling
   citation is visible, not silently absent. */
function cellCitationsOf(subcapId) {
  const cell = (typeof DMA.cellEvidenceFor === "function")
    ? DMA.cellEvidenceFor(subcapId) : null;
  const ids = (cell && Array.isArray(cell.e_ids)) ? cell.e_ids : [];
  if (ids.length) {
    return {
      basis: "promoted",
      cell,
      items: ids.map(id => {
        const e = DMA.getEvidence(id) || null;
        return e ? { ...e, resolved: true } : { id, resolved: false };
      }),
    };
  }
  return {
    basis: "derived",
    cell,
    items: (DMA.EVIDENCE || [])
      .filter(e => e.subcaps && e.subcaps.includes(subcapId))
      .map(e => ({ ...e, resolved: true }))
      .sort(bySpecificity),
  };
}

/* THE MOST CELL-SPECIFIC ITEM FIRST, and it is not a nicety.
 *
 * Reported 2026-08-19: "evidence is so generic and not subcap specific". It
 * was. The derived list is the assessment's OWN link table, and the package
 * links a document to every cell it touches — one congressional testimony on
 * this run is linked to 21 cells, a vendor case study to 38. In hash order the
 * reader met the broadest item first: a cell about a written digital strategy
 * opened onto testimony about a $10 billion regulatory threshold.
 *
 * Specificity is ranked from what the payload already carries, in this order,
 * every term of it deterministic:
 *
 *   1 · can it be quoted at all. An item with no verbatim span is a reference,
 *       not a citation (invariant 4), and belongs below every item that is.
 *   2 · how many cells it supports. An item linked to 38 cells is by
 *       construction not about any one of them; an item linked to this cell
 *       alone is about this cell.
 *   3 · its tier, strongest first.
 *   4 · its id, so the order is stable between two identical runs.
 *
 * No model is consulted here and none could be: this is the serving path
 * (invariant 1). The embedding that WOULD score relevance runs in the worker's
 * linker and in V4 at submit, where it belongs. */
function bySpecificity(a, b) {
  // Through the shared reader, not a hand-rolled typeof: `asText` is the one
  // place that decides what counts as text, and the absence-safety gate reads
  // this file line by line — a local guard that is correct still teaches the
  // next author to write one that is not.
  const quotable = (x) => (x && asText(x.excerpt)) ? 0 : 1;
  const breadth = (x) => ((x && x.subcaps) || []).length || 999;
  const tier = (x) => String((x && x.tier) || "T9");
  return quotable(a) - quotable(b)
      || breadth(a) - breadth(b)
      || tier(a).localeCompare(tier(b))
      || String(a.id || "").localeCompare(String(b.id || ""));
}

/* The number of evidence items behind a cell, and where the number came from.
   The row used to count `DMA.EVIDENCE` rows that list the cell, which is why
   all 43 cells of P4C1 read "5 evidence" — the link table is coarser than the
   citation lists. `grounded_on` is the promoted length (invariant 8: it is the
   length of the citation list, not a stored number to be re-derived). */
function evidenceCountOf(subcap) {
  const cell = (typeof DMA.cellEvidenceFor === "function")
    ? DMA.cellEvidenceFor(subcap.id) : null;
  const ids = (cell && Array.isArray(cell.e_ids)) ? cell.e_ids : null;
  if (ids && ids.length) return { n: ids.length, basis: "cited" };
  if (subcap.evidence_count != null) return { n: subcap.evidence_count, basis: "linked" };
  return { n: null, basis: null };
}

function ClientHeatmap({ entity, run }) {
  const route = useRoute();
  const { audience, openEvidence, openInsight, setIpSurface, setIpContext, tweaks, pushToast } = useApp();
  // Order and default, per the build owner 2026-08-14: the STANDARD heatmap
  // opens the page, then focus areas, then the value chain. The customer
  // audience still cannot reach the standard grid (it carries every capped and
  // thin cell), so it opens on focus areas — the ternary that used to return
  // "focus" on both branches now actually branches.
  const [mode, setMode]               = useState(route.params.hm || (audience === "customer" ? "focus" : "standard"));  // standard | focus | value_chain
  const [zoom, setZoom]               = useState(route.params.zoom || "category");
  const [pillarFocus, setPillarFocus] = useState(route.params.pillar || null);
  const [catFocus, setCatFocus]       = useState(route.params.cat || null);
  const [showPeers, setShowPeers]     = useState(true);
  const [showIssues, setShowIssues]   = useState(false);
  const [focusArea, setFocusArea]     = useState(null);
  const [synthSubcap, setSynthSubcap] = useState(null);

  // In customer mode, lock to focus / value_chain views only. `mode` belongs in
  // the deps: with `[audience]` alone the effect had already run by the time
  // "Standard" was clicked, so the internal grid rendered for the customer
  // audience. The button is also disabled below — the lock should not depend on
  // an effect winning a race.
  useEffect(() => {
    if (audience === "customer" && mode === "standard") setMode("focus");
  }, [audience, mode]);

  // `?subcap=` is how every other page opens a cell here: `openSubcap` in
  // app-root navigates to this tab with the id as a param. Nothing consumed
  // it, so a cell chip clicked anywhere else landed on the heatmap's default
  // view and the cell it named never opened. Consume it — the drawer opens on
  // the named cell when this run scored it, and an unknown id changes nothing.
  /* The CELL GRAIN is a second fetch, and it lands after the entity does.
     With `[route.params.subcap, entity?.id]` alone this effect ran once, at
     mount, against an `entity.subcaps` that was still empty — found nothing,
     and never ran again, because the id it depends on had not changed. So
     `?subcap=` was consumed by a page that could not yet answer it and every
     cross-page cell chip still landed on the default view. The arrival of the
     705 cells is the event this effect is waiting for, so it is in the deps.
     The count is stable once loaded, and the lookup is a no-op when the id
     names no cell this run scored, so there is no loop to fall into. */
  useEffect(() => {
    const sid = route.params.subcap;
    if (!sid) return;
    const s = (entity.subcaps || []).find(x => x.id === sid);
    if (s) setSynthSubcap({ kind: "subcap", subcap: s });
  }, [route.params.subcap, entity?.id, (entity && entity.subcaps || []).length]);

  // The run's own category and pillar rows — promoted score, promoted peer
  // median, the cells it scored — including any category the current catalogue
  // does not list.
  const cats = useMemo(() => runCategoriesOf(entity), [entity?.id, entity?.subcaps]);
  const pillars = useMemo(() => runPillarsOf(entity), [entity?.id, entity?.subcaps]);
  const overallLabel = DMA.helpers.maturityLabel(entity.overall);

  // The cells a focus area names — the ones it actually names. Matching on a
  // 4-char prefix returned every cell in the CATEGORY (so a 7-cell focus area
  // showed dozens), and returned nothing at all when an id did not start with
  // a PxCy prefix, which collapsed the grid to `repeat(0, 1fr)` and rendered a
  // blank card. Exact first, prefix only as a documented fallback.
  const subcapsForFocusArea = (fa) => {
    if (!fa || !Array.isArray(entity.subcaps)) return [];
    const named = new Set(fa.subcaps || []);
    if (!named.size) return [];
    const exact = entity.subcaps.filter(s => named.has(s.id));
    if (exact.length) return exact;
    // Some packages name a capability (P4C1.2) where the grid holds its
    // sub-capabilities (P4C1.2.1…): widen to descendants of a named id.
    return entity.subcaps.filter(s =>
      [...named].some(n => typeof n === "string" && s.id.startsWith(`${n}.`)));
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Maturity heatmap</div>
          <h1>Where {entity.name} is today</h1>
          {/* maturityLabel returns null for a null composite, and .toLowerCase()
              on it took the whole page down. No composite, no band word. */}
          <div className="sub">{entity.subcaps.length} subcaps · {entity.subcaps.filter(s => s.thin).length} thin{overallLabel ? ` · overall maturity ${overallLabel.toLowerCase()}` : " · no overall score promoted"}</div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" onClick={() => pushToast(`Exporting ${entity.name} heatmap as PDF…`, "success")}><Icon name="download" size={13} /> Export</button>
        </div>
      </div>

      {/* Mode switcher + overlays */}
      <div className="card" style={{ marginBottom: 14, padding: "12px 16px" }}>
        <div className="row" style={{ flexWrap: "wrap", gap: 12 }}>
          <div className="row" style={{ gap: 6 }}>
            <span style={{ fontSize: 11, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>View</span>
            <div className="toggle-row">
              {/* Standard · Focus areas · Value chain, in that order. The
                  internal grid carries every cell, capped or thin, and is not
                  part of the customer view — disabled rather than switched
                  back a moment later. */}
              <button className={mode === "standard" ? "on" : ""}
                disabled={audience === "customer"}
                title={audience === "customer" ? "the full internal grid is not part of the customer view" : null}
                style={audience === "customer" ? { opacity: .45, cursor: "not-allowed" } : null}
                onClick={() => { if (audience !== "customer") setMode("standard"); }}><Icon name="heatmap" size={11} /> Standard</button>
              <button className={mode === "focus" ? "on" : ""} onClick={() => { setMode("focus"); setFocusArea(null); }}><Icon name="sparkle" size={11} /> Focus areas</button>
              <button className={mode === "value_chain" ? "on" : ""} onClick={() => setMode("value_chain")}><Icon name="route" size={11} /> Value chain</button>
            </div>
          </div>
          <span style={{ width: 1, height: 22, background: "var(--z-sep)" }} />
          {mode === "standard" ? (
            <div className="row" style={{ gap: 6 }}>
              <span style={{ fontSize: 11, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>Zoom</span>
              <div className="toggle-row">
                {["pillar","category","capability","subcap"].map(z => (
                  <button key={z} className={zoom === z ? "on" : ""} onClick={() => setZoom(z)}>{z[0].toUpperCase() + z.slice(1)}</button>
                ))}
              </div>
            </div>
          ) : null}
          <span className="spacer" />
          <label className="row" style={{ fontSize: 11.5, cursor: "pointer" }}>
            <span className={`switch ${showPeers ? "on" : ""}`} onClick={() => setShowPeers(p => !p)} />
            Peers
          </label>
          <label className="row" style={{ fontSize: 11.5, cursor: "pointer" }}>
            <span className={`switch ${showIssues ? "on" : ""}`} onClick={() => setShowIssues(p => !p)} />
            Issues
          </label>
          <Legend />
        </div>

        {(pillarFocus || catFocus) && mode === "standard" ? (
          <div className="row" style={{ marginTop: 10, fontSize: 12, color: "var(--z-body)" }}>
            <span className="muted">Drilling:</span>
            {pillarFocus ? <span className="chip purple">{pillarFocus}</span> : null}
            {catFocus ? <><Icon name="chevron-r" size={11} /><span className="chip">{catFocus}</span></> : null}
            <button className="btn btn-tertiary btn-sm" onClick={() => { setPillarFocus(null); setCatFocus(null); setZoom("category"); }}>Reset</button>
          </div>
        ) : null}
      </div>

      {/* CONTENT BY MODE */}
      {mode === "focus" ? (
        <FocusAreaView entity={entity} run={run}
          focusArea={focusArea}
          setFocusArea={setFocusArea}
          subcapsForFocusArea={subcapsForFocusArea}
          openSubcap={setSynthSubcap}
          openEvidence={openEvidence} openInsight={openInsight}
          audience={audience}
          showIssues={showIssues} />
      ) : mode === "value_chain" ? (
        <ValueChainView entity={entity} subcapsForFocusArea={subcapsForFocusArea} openSubcap={setSynthSubcap} openInsight={openInsight} />
      ) : (
        <>
          {showIssues ? <IssueRegisterBanner entity={entity} onSubcap={(s) => setSynthSubcap({ kind: "subcap", subcap: s })} openEvidence={openEvidence} /> : null}
          {zoom === "pillar" ? (
            <PillarHeatmap entity={entity} pillars={pillars} audience={audience} setPillarFocus={(p) => { setPillarFocus(p); setZoom("category"); }} />
          ) : zoom === "category" ? (
            <CategoryHeatmap entity={entity} pillars={pillars} pillarFocus={pillarFocus} showPeers={showPeers} showIssues={showIssues}
              audience={audience}
              setCatFocus={(c) => { setCatFocus(c); setZoom("capability"); }}
              onSynth={(catId) => { setSynthSubcap({ kind: "category", catId }); }} />
          ) : zoom === "capability" ? (
            /* Its own grain. The button used to set zoom to "capability" and
               fall through to the subcap branch, so it produced DOM identical
               to "Subcap" — a control that did nothing. */
            <CapabilityHeatmap entity={entity} cats={cats} catFocus={catFocus} pillarFocus={pillarFocus} showIssues={showIssues}
              audience={audience}
              drillCategory={(c) => { setCatFocus(c); setZoom("subcap"); }} />
          ) : (
            <SubcapHeatmap entity={entity} cats={cats} catFocus={catFocus} pillarFocus={pillarFocus} showPeers={showPeers} showIssues={showIssues}
              audience={audience}
              setCatFocus={setCatFocus}
              onSynth={(s) => setSynthSubcap({ kind: "subcap", subcap: s })} />
          )}
        </>
      )}

      {/* Synthesis Drawer (subcap or category level) */}
      {synthSubcap ? (
        <SynthesisDrawer entity={entity} item={synthSubcap}
          onClose={() => setSynthSubcap(null)}
          openEvidence={openEvidence}
          openInsight={openInsight}
          showIssues={showIssues}
          audience={audience}
        />
      ) : null}
    </div>
  );
}

/* ─────────────────────── FOCUS AREA VIEW ─────────────────────── */
function FocusAreaView({ entity, run, focusArea, setFocusArea, subcapsForFocusArea, openSubcap, openEvidence, openInsight, audience }) {
  // Hover identification for the score-only cell grid in the detail branch.
  // Called before the early return — hooks cannot be conditional.
  const cellTip = useCellTip();
  if (!focusArea) {
    return (
      <div>
        <div className="row" style={{ marginBottom: 12 }}>
          <Icon name="sparkle" size={15} style={{ color: "var(--z-dpur)" }} />
          <div style={{ fontSize: 13, fontWeight: 600 }}>Strategic priorities for {entity.name}</div>
          
          <span className="spacer" />
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Click any focus area to drill in</span>
        </div>
        <div className="g3">
          {DMA.FOCUS_AREAS.map(fa => {
            const subs = subcapsForFocusArea(fa);
            // The focus area's own promoted figures first (peer_score/delta are
            // in the H1 contract and were unread), then the mean of the cells it
            // names, then nothing. No 2.5/2.8 fallbacks: a hardcoded average is
            // a claim about this client.
            // `entity_score` is the producer's own figure for this focus area
            // (H1 contract) and it is not the mean of the cells: FA-1 promotes
            // 1.95 where its 43 cells average 2.0. Read it; the mean only
            // stands in when the run states none.
            const avg = numOf(fa.entity_score) != null ? numOf(fa.entity_score)
                                                       : meanOf(subs.map(s => s.score));
            const peer = fa.peer_score != null ? Number(fa.peer_score) : peerMeanOf(subs);
            const gap = fa.delta != null ? -Number(fa.delta) : deltaOf(peer, avg);
            return (
              <div key={fa.id} className="fa-card" onClick={() => setFocusArea(fa)}>
                {/* The prototype's 88px illo was sized for the fixture's
                    two-word focus-area names. A promoted name is a full
                    sentence, so the title grew upward from the bottom and ran
                    UNDER the icon block — the first words of every card were
                    unreadable. Taller box, name clamped to two lines with the
                    full text on hover. */}
                <div className="fa-illo" style={{ height: 116, background: `linear-gradient(135deg, ${fa.colors[0]}, ${fa.colors[1]})` }}>
                  <div className="icon-block"><Icon name={fa.icon} size={16} /></div>
                  <div className="title-block">
                    <div style={{ fontSize: 13, fontWeight: 700, lineHeight: 1.35 }} className="txt-fit-2" title={fa.name}>{fa.name}</div>
                    <div style={{ fontSize: 10.5, opacity: .92 }}>{subs.length} subcaps</div>
                  </div>
                </div>
                <div className="fa-meta">
                  <div className="row" style={{ marginBottom: 8 }}>
                    {avg != null ? <MaturityChip score={avg} /> : <span className="b b-muted">no score</span>}
                    {peer != null ? (
                      <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Peer {fx(peer, 1)}</span>
                    ) : (
                      /* No stated median at focus-area grain is a routable
                         gap, not a dash. Compact: this row already carries a
                         maturity chip and a delta badge inside a three-up
                         card, and the queue badge would push the delta out. */
                      <span style={{ fontSize: 11, color: "var(--z-muted)" }} title="no peer median is stated at this grain in this run">
                        <EnrichmentGap what={`${fa.id} peer median`} audience={audience} compact />
                      </span>
                    )}
                    {/* "at peer" is a CLAIM, and it was printed for every card
                        whose gap was null (i.e. all of them) and for every card
                        the client leads — where it also understates. The signed
                        difference between two stated figures says it without
                        asserting anything. */}
                    {gap == null ? null
                      : gap > 0 ? <span className="b b-below" style={{ marginLeft: "auto" }}>−{fx(gap, 1)}</span>
                      : gap < 0 ? <span className="b b-above" style={{ marginLeft: "auto" }}>+{fx(Math.abs(gap), 1)}</span>
                      : <span className="b b-muted" style={{ marginLeft: "auto" }}>0.0</span>}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.5 }} className="txt-fit-2">{fa.description}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Selected focus area detail
  const fa = focusArea;
  const subs = subcapsForFocusArea(fa);
  const avg = numOf(fa.entity_score) != null ? numOf(fa.entity_score)
                                             : meanOf(subs.map(s => s.score));
  const peer = fa.peer_score != null ? Number(fa.peer_score) : peerMeanOf(subs);
  // Cards this focus area's OWN cells are affected by. Matching on a 4-char
  // prefix meant "anything in the same category", so a card about a cell this
  // focus area never names was listed under it — the same fabricated linkage
  // the cell list already had fixed.
  const named = new Set(fa.subcaps || []);
  const insights = DMA.INSIGHT_CARDS.filter(ic => (ic.affects || []).some(sid =>
    named.has(sid) || [...named].some(n => typeof n === "string" && sid.startsWith(`${n}.`))));
  // Each fragment of the source line only exists when its value does: a null
  // page printed " · p. · " and a focus area carries no financial reference at
  // all, so the label sat there with nothing after it.
  const srcBits = [fa.source && fa.source.type,
                   (fa.source && fa.source.page) ? `p.${fa.source.page}` : null,
                   fa.source && fa.source.doc].filter(Boolean);

  return (
    <div>
      <div className="card flush" style={{ marginBottom: 14 }}>
        <div style={{ position: "relative", padding: "22px 24px", background: `linear-gradient(135deg, ${fa.colors[0]}10, ${fa.colors[1]}1a)`, borderBottom: "1px solid var(--z-sep)", overflow: "hidden" }}>
          <img src={assetUrl("illo_curvesTR", "brand/illustrations/curves_topright.png")} alt="" style={{ position: "absolute", right: -60, top: -40, width: 360, height: "auto", opacity: .55, pointerEvents: "none" }} />
          <div style={{ position: "relative", display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 14 }}>
            <div style={{ minWidth: 0, flex: 1 }}>
              <button onClick={() => setFocusArea(null)} className="row" style={{ fontSize: 11.5, color: "var(--z-mid)", background: "transparent", padding: "4px 8px 4px 0", border: 0, marginBottom: 8, cursor: "pointer" }}>
                <Icon name="chevron-l" size={12} /> All focus areas
              </button>
              <div className="row" style={{ marginBottom: 8 }}>
                <div style={{ width: 36, height: 36, borderRadius: 9, background: fa.colors[0], color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <Icon name={fa.icon} size={18} />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div className="row" style={{ gap: 6, marginBottom: 2 }}>
                    <span className="b b-purple">FOCUS AREA · {fa.id}</span>
                    <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>{subs.length} subcaps</span>
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 600, color: "var(--z-dark)", letterSpacing: "-.015em" }}>{fa.name}</div>
                </div>
              </div>
              <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.5, maxWidth: 640 }}>{fa.description}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 16, flexShrink: 0 }}>
              <ScoreRing score={avg} size={88} />
            </div>
          </div>
        </div>

        {/* Source citation */}
        <div style={{ padding: "14px 20px", background: "var(--z-bg)", display: "flex", gap: 14, alignItems: "flex-start", borderBottom: "1px solid var(--z-sep)" }}>
          <Icon name="doc" size={16} style={{ color: "var(--z-dpur)", flexShrink: 0, marginTop: 2 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="b b-purple">SOURCE</span>
              <span style={{ fontSize: 11, color: "var(--z-muted)", minWidth: 0, overflowWrap: "anywhere" }}>
                {srcBits.length ? srcBits.join(" · ") : "the run states no source for this focus area"}
              </span>
            </div>
            {/* A focus area with no verbatim quote used to throw on .replace and
                take the page with it. */}
            {fa.strategic_quote ? (
              <div style={{ fontSize: 12.5, color: "var(--z-dark)", fontStyle: "italic", lineHeight: 1.55 }}>"{String(fa.strategic_quote).replace(/[“”]/g, "")}"</div>
            ) : null}
            {fa.financial_ref ? (
              <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 5 }}>Financial reference: {fa.financial_ref}</div>
            ) : null}
          </div>
        </div>
      </div>

      {/* KPI strip with public-vs-private indicators + customization */}
      <CustomizableKpiStrip fa={fa} entity={entity} />

      {/* Composite + subcap grid. `alignItems: start` so the pillar-share card
          is the height of its own content: stretched to the cell grid's height
          it was mostly empty card. */}
      <div style={{ display: "grid", gridTemplateColumns: "280px minmax(0, 1fr)", gap: 14, marginBottom: 14, alignItems: "start" }}>
        <div className="card">
          <div style={{ fontSize: 11, color: "var(--z-muted)", marginBottom: 8 }}>Where its cells sit, by pillar</div>
          {!fa.pillars_weight || !Object.keys(fa.pillars_weight).length ? (
            <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
              No cells linked to this focus area.
            </div>
          ) : Object.entries(fa.pillars_weight).map(([p, w]) => (
            <div key={p} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, marginBottom: 6 }}>
              <span className="chip purple" style={{ minWidth: 26, textAlign: "center" }}>{p}</span>
              <div className="prog" style={{ flex: 1, height: 6 }}><div className="prog-fill" style={{ width: `${w}%`, background: DMA.helpers.maturityHex(entity.pillar_scores[p]) }} /></div>
              <span style={{ fontSize: 11, color: "var(--z-muted)", width: 30, textAlign: "right" }}>{w}%</span>
            </div>
          ))}
          <div className="sep" />
          {/* These are SHARES of the cell list beside them (the adapter counts
              involved_subcap_ids per pillar), not weights in a composite —
              calling them weights implied the focus area score was a weighted
              roll-up of pillars, which nothing in the run says. */}
          <div style={{ fontSize: 10.5, color: "var(--z-muted)", lineHeight: 1.5 }}>Share of the {(fa.subcaps || []).length} cells this focus area names, per pillar. Bar fill is each pillar's own promoted maturity for {entity.name}.</div>
        </div>

        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="heatmap" size={14} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>Subcap heatmap</div>
            <span className="spacer" />
            <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{subs.length} cells · click any cell for synthesis</span>
          </div>
          <div className="hm" style={{ gridTemplateColumns: `repeat(${Math.min(subs.length, 8)}, 1fr)`, gap: 5 }}>
            {subs.map(s => (
              /* The cell only carries its score and an id fragment — which
                 subcap it IS took a click. Identified on hover: title attr +
                 the grid's shared bubble (hidden on click so it cannot linger
                 over the drawer that opens). */
              <button key={s.id} onClick={() => { cellTip.hide(); openSubcap({ kind: "subcap", subcap: s }); }}
                className={`hm-cell b ${DMA.helpers.maturityClass(s.score)} ${s.thin ? "thin" : ""}`}
                title={subcapTipText(s)}
                onMouseEnter={cellTip.show(subcapTipText(s))}
                onMouseLeave={cellTip.hide}
                style={{ flexDirection: "column", height: 56, fontSize: 11, padding: 4, border: 0 }}>
                {/* `fx` returns the em dash for a null and keeps doing so on
                    purpose (utils.jsx: 40-odd template literals need it to be
                    a string), so an unscored cell has to be guarded HERE. The
                    phrase takes the numeral's line at 10px rather than 14: the
                    grid is up to eight columns and `.b` is nowrap. */}
                {s.score == null
                  ? <div style={{ fontSize: 10, fontWeight: 600 }}><EnrichmentGap what={`${s.id} score`} audience={audience} compact /></div>
                  : <div style={{ fontSize: 14, fontWeight: 700 }}>{fx(s.score, 1)}</div>}
                <div style={{ fontSize: 8.5, opacity: .85, fontFamily: "var(--font-mono)" }}>{s.id.split(".").slice(1).join(".")}</div>
              </button>
            ))}
          </div>
          <CellTip tip={cellTip.tip} />
        </div>
      </div>

      {/* Linked insight cards */}
      <div className="card flush">
        <div className="card-head">
          <h3>Insight cards in this focus area</h3>
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{insights.length} cards</span>
        </div>
        <div style={{ padding: 14 }}>
          {insights.length === 0 ? (
            <div className="muted" style={{ fontSize: 12 }}>No insight cards yet</div>
          ) : (
            <div className="g2">
              {insights.map(ic => (
                <div key={ic.id} className={`ic ${ic.flag.toLowerCase()}`} onClick={() => openInsight(ic.id)}>
                  <div className="ic-head">
                    <div className="row">
                      <span className="ic-id">{ic.id}</span>
                      <span className={`b ${ic.flag === "CRITICAL" ? "b-below" : ic.flag === "OPPORTUNITY" ? "b-org" : "b-teal"}`}>{ic.flag}</span>
                    </div>
                  </div>
                  <div className="ic-title">{ic.title}</div>
                  <div className="ic-body txt-fit-2">{ic.what}</div>
                  <div className="ic-foot">
                    {ic.platforms.map(p => <span key={p} className="b b-teal">{DMA.getPlatform(p)?.short}</span>)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Customisable KPI strip ─────────────────────────────────────── */
function CustomizableKpiStrip({ fa, entity }) {
  // Each KPI gets a "source mode": "public" (inferred from public DMA) or "client" (provided / awaiting client input) or "hidden"
  const kpis = (fa && Array.isArray(fa.kpis)) ? fa.kpis : [];
  const [modes, setModes] = useState(() => kpis.reduce((m, k) => { m[k.label] = "public"; return m; }, {}));
  const [editing, setEditing] = useState(null);
  const [drafts, setDrafts] = useState({});
  // The H1 contract carries no KPI baselines or targets, so this is [] for
  // every focus area of every run today. It rendered anyway: a heading, a
  // "Customise per client" badge and a six-line explainer over zero tiles —
  // chrome promising figures that do not exist. Nothing to show, nothing shown;
  // if a future contract carries kpis the strip returns on its own.
  if (!kpis.length) return null;

  const cycleMode = (label) => {
    setModes(m => ({ ...m, [label]: m[label] === "public" ? "client" : m[label] === "client" ? "hidden" : "public" }));
  };
  const saveDraft = (label) => {
    setEditing(null);
  };

  return (
    <div className="card" style={{ marginBottom: 14, padding: 14 }}>
      <div className="row" style={{ marginBottom: 12 }}>
        <Icon name="scale" size={14} />
        <div style={{ fontSize: 13, fontWeight: 600 }}>KPI baseline · target</div>
        <span className="b b-muted">Customise per client</span>
        <span className="spacer" />
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Toggle each KPI between Public inference · Client-provided · Hidden</span>
      </div>
      <div className="g3">
        {kpis.map(k => {
          const mode = modes[k.label];
          const isEditing = editing === k.label;
          const isHidden = mode === "hidden";
          const isClient = mode === "client";
          const meta = isClient
            ? { tag: "Client-provided", color: "var(--z-dpur)", bg: "var(--ph0-lt)", bd: "var(--ph0-bd)", icon: "user" }
            : isHidden
              ? { tag: "Not available", color: "var(--z-muted)", bg: "var(--z-lav)", bd: "var(--z-sep)", icon: "lock" }
              : { tag: "Public DMA inference", color: "var(--z-mid)", bg: "var(--z-ice)", bd: "rgba(39,187,175,.3)", icon: "globe" };
          return (
            <div key={k.label} className="card-tile" style={{ padding: 12, border: `1px solid ${meta.bd}`, background: meta.bg }}>
              <div className="row" style={{ marginBottom: 6 }}>
                <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".06em", flex: 1 }} className="txt-fit-1">{k.label}</div>
                <button className="icon-btn" style={{ width: 22, height: 22, color: meta.color }} title={`Source: ${meta.tag} · click to change`} onClick={() => cycleMode(k.label)}>
                  <Icon name={meta.icon} size={11} />
                </button>
                <button className="icon-btn" style={{ width: 22, height: 22, color: "var(--z-muted)" }} title="Edit values" onClick={() => setEditing(isEditing ? null : k.label)}>
                  <Icon name="edit" size={11} />
                </button>
              </div>
              {!isHidden && !isEditing ? (
                <div className="row">
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: "var(--z-dark)" }}>{drafts[k.label + "_current"] || k.current}</div>
                    <div style={{ fontSize: 9, color: "var(--z-muted)" }}>current</div>
                  </div>
                  <Icon name="arrow-r" size={12} style={{ color: "var(--z-muted)" }} />
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: meta.color }}>{drafts[k.label + "_target"] || k.target}</div>
                    <div style={{ fontSize: 9, color: "var(--z-muted)" }}>target</div>
                  </div>
                  <span className="spacer" />
                  <span className={`b`} style={{ background: meta.bd, color: meta.color, fontSize: 9 }}>{k.delta}</span>
                </div>
              ) : isEditing ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div className="row" style={{ gap: 6 }}>
                    <input className="inp" style={{ padding: "4px 8px", fontSize: 11 }} placeholder="Current" defaultValue={drafts[k.label + "_current"] || k.current} onChange={e => setDrafts(d => ({ ...d, [k.label + "_current"]: e.target.value }))} />
                    <Icon name="arrow-r" size={11} style={{ color: "var(--z-muted)" }} />
                    <input className="inp" style={{ padding: "4px 8px", fontSize: 11 }} placeholder="Target" defaultValue={drafts[k.label + "_target"] || k.target} onChange={e => setDrafts(d => ({ ...d, [k.label + "_target"]: e.target.value }))} />
                  </div>
                  <div className="row" style={{ gap: 4 }}>
                    <button className="btn btn-primary btn-sm" style={{ padding: "3px 8px", fontSize: 10.5 }} onClick={() => saveDraft(k.label)}>Save</button>
                    <button className="btn btn-tertiary btn-sm" style={{ padding: "3px 8px", fontSize: 10.5 }} onClick={() => setEditing(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: 11.5, color: meta.color, padding: "4px 0", display: "flex", alignItems: "center", gap: 6 }}>
                  <Icon name="lock" size={11} /> Hidden - not inferable from public sources
                </div>
              )}
              <div style={{ fontSize: 9.5, color: meta.color, marginTop: 5, fontWeight: 600 }}>{meta.tag.toUpperCase()}</div>
            </div>
          );
        })}
      </div>
      <div className="co co-teal" style={{ marginTop: 10 }}>
        <Icon name="info" size={13} />
        <div className="co-body">
          Some KPIs can only be inferred indirectly from public sources (annual reports, hiring signals, app store reviews). Click the source icon to switch a KPI between <strong>Public DMA inference</strong>, <strong>Client-provided</strong> (when you receive direct data in a meeting), or <strong>Hidden</strong> (when no reliable source exists). Use the edit icon to enter values directly.
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────── PILLAR HEATMAP ─────────────────────── */
function PillarHeatmap({ entity, pillars, setPillarFocus, audience }) {
  // Does any tile carry a figure? Four that do not is not four separate
  // absences; it is one section that promoted nothing at this grain, and the
  // reader is owed that once rather than four times or not at all.
  const anyScore = (pillars || []).some(p => p.score != null);
  return (
    <div className="card">
      <div className="g4">
        {(pillars || []).map(p => {
          // The promoted pillar score and the workbook's STATED pillar median.
          // A constant offset used to stand in for the median: Baxter's P1 sits
          // at 3.11 against a stated 2.9 — ABOVE its peer set — and `score +
          // 0.3` rendered that as 0.3 BELOW.
          const score = p.score, peer = p.peer;
          const delta = deltaOf(score, peer);
          return (
            <div key={p.id} className="card-tile clickable" onClick={() => setPillarFocus(p.id)} style={{ padding: 16 }}
              title={`${p.id} — ${p.name || "unnamed in catalogue"} · ${score != null ? fx(score, 1) : "no score"} · click to drill`}>
              <div className="row" style={{ marginBottom: 12 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{p.id}</div>
                  <div style={{ fontSize: 14, fontWeight: 600 }} className="txt-fit-2">{p.name || "not named in the current catalogue"}</div>
                </div>
                <span className="spacer" />
                <MaturityChip score={score} large />
              </div>
              {/* A null score drew a zero-width bar in the "nothing measured"
                  grey, which reads as a measured floor. No score, no bar. */}
              {score != null ? (
                <div className="prog"><div className="prog-fill" style={{ width: `${score / 5 * 100}%`, background: DMA.helpers.maturityHex(score) }} /></div>
              ) : (
                /* The tile says the figure is absent; the card foot says WHY,
                   once, in the producer's own words. Four tiles each repeating
                   "no pillar score promoted" and no reason anywhere was a
                   dead end four times over. */
                <div style={{ fontSize: 11, color: "var(--z-muted)" }}>no figure at pillar grain</div>
              )}
              <div className="row" style={{ marginTop: 8, fontSize: 11 }}>
                {peer != null ? (
                  <>
                    <span style={{ color: "var(--z-muted)" }}>Peer {fx(peer, 1)}</span>
                    <span className="spacer" />
                    {delta != null ? (
                      <span style={{ color: delta < 0 ? "var(--z-below)" : "var(--z-mid)", fontFamily: "var(--font-mono)" }}>{delta >= 0 ? "▲" : "▼"} {fx(Math.abs(delta), 1)}</span>
                    ) : null}
                  </>
                ) : (
                  /* Compact: four tiles across, and the 11px meta row under
                     the progress bar has no room for the queue badge. */
                  <span style={{ color: "var(--z-muted)" }} title="the run states no peer median for this pillar">
                    <EnrichmentGap what={`${p.id} peer median`} audience={audience} compact />
                  </span>
                )}
              </div>
              {/* Counted from the run's own categories, so a pillar carrying a
                  category the catalogue dropped (P1C5 here) says five, and the
                  grid one click away draws five columns. */}
              <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 10 }}>{p.cats.length} categories · {p.cellCount} subcaps · click to drill</div>
            </div>
          );
        })}
      </div>
      {/* ── Why the four tiles carry no figure ────────────────────────────
          The pillar grain is `heatmap.workbook_scores`, and on a run where
          that section serves nothing the zoom rendered four bare chips and
          four repetitions of "no pillar score promoted" — no reason, no
          closure condition, no ladder, nothing a reader could act on. The
          section states its own empty state and it renders here.

          Deliberately NOT a derived mean. The category zoom one click away
          derives one and this zoom does not, which is a real inconsistency
          (H-06) and an adjudication about what the grid is allowed to
          publish — not something to settle by quietly starting to publish a
          pillar figure the run does not state. */}
      {!anyScore ? (() => {
        const { stub } = sectionReason("heatmap.workbook_scores");
        return (
        <div style={{ marginTop: 12, borderTop: "1px solid var(--z-sep)", paddingTop: 10 }}>
          <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase",
                        letterSpacing: ".06em", marginBottom: 4 }}>
            Pillar grain
          </div>
          {stub ? (
            <div style={{ fontSize: 11.5, color: "var(--z-muted)", lineHeight: 1.55 }}>
              This run serves no workbook table at pillar grain, so the four
              tiles above carry their cell counts and no pillar figure. The
              scores the run does state are at cell grain — one zoom in, and
              in every cell drawer.
            </div>
          ) : <SectionEmpty section="heatmap.workbook_scores" />}
        </div>
        );
      })() : null}
    </div>
  );
}

/* ─────────────────────── CATEGORY HEATMAP ─────────────────────── */
function CategoryHeatmap({ entity, pillars, pillarFocus, showPeers, showIssues, setCatFocus, onSynth, audience }) {
  const rows = pillarFocus ? (pillars || []).filter(p => p.id === pillarFocus) : (pillars || []);
  // The aggregate cells are score-only too; same hover identification as the
  // subcap grids — one bubble for the whole grid.
  const cellTip = useCellTip();
  /* Category → cells the issue register touches. Two counts, because they are
     two different claims: a LINKED cell is one an issue names, a CAPPED cell is
     one the register puts a maturity ceiling on. The badge counted links and
     called them caps behind a padlock, while the cell view showed no cap at all
     (issueCapsFor only returns a stated level) — the same grid contradicting
     itself one zoom apart. */
  const catCaps = {};
  Object.values(DMA.ISSUE_CAPS).forEach(info => {
    Object.entries(info.caps || {}).forEach(([sid, cap]) => {
      const catId = sid.slice(0, 4);
      const row = catCaps[catId] || (catCaps[catId] = { linked: 0, capped: 0 });
      row.linked += 1;
      if (cap != null) row.capped += 1;
    });
  });
  return (
    <div className="card">
      {rows.map(p => {
        const cats = p.cats;
        return (
          <div key={p.id} style={{ marginBottom: 16 }}>
            <div className="row" style={{ marginBottom: 10 }}>
              <span className="b b-purple">{p.id}</span>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{p.name || "not named in the current catalogue"}</span>
              {/* The PROMOTED pillar score. This was the mean of the category
                  means — 3.4 for P1 where the run promotes 3.11 — so one page
                  carried two numbers for the same pillar. */}
              <MaturityChip score={p.score} />
              <span className="spacer" />
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{cats.length} categories · {p.cellCount} subcaps</span>
            </div>
            {!cats.length ? (
              <div style={{ fontSize: 11, color: "var(--z-muted)" }}>This run scored no cells in this pillar.</div>
            ) : (
            <div style={{ display: "grid", gridTemplateColumns: `120px repeat(${cats.length}, minmax(0, 1fr))`, gap: 4 }}>
              <div style={{ fontSize: 11, color: "var(--z-muted)", display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 8 }}>Entity</div>
              {cats.map(c => {
                // The workbook's own category score. Where the run promotes
                // none, the mean of the cells it scored — said so in the
                // tooltip, never silently swapped for the stated figure.
                const shown = c.score != null ? c.score : c.cellMean;
                const basis = c.score != null
                  ? `promoted category score${c.source_cell ? ` (${c.source_cell})` : ""}`
                  : (c.cellMean != null ? `mean of ${c.cells.length} scored cells — the run promoted no category score`
                                        : "no score");
                const iss = catCaps[c.id] || { linked: 0, capped: 0 };
                const capCount = iss.capped || iss.linked;
                const tipLabel = `${c.id} — ${c.name || "unnamed in catalogue"} · ${shown != null ? fx(shown, 1) : "no score"}`;
                return (
                  <button key={c.id} className={`hm-cell b ${DMA.helpers.maturityClass(shown)}`}
                    onClick={() => { cellTip.hide(); setCatFocus(c.id); }}
                    onContextMenu={(e) => { e.preventDefault(); cellTip.hide(); onSynth(c.id); }}
                    onMouseEnter={cellTip.show(tipLabel)}
                    onMouseLeave={cellTip.hide}
                    style={{ position: "relative", border: 0, padding: "8px 6px", minHeight: 44 }}
                    title={`${c.id} · ${c.name || "not named in the current catalogue"} · ${basis}${
                      iss.capped ? ` · ${iss.capped} subcaps capped by issues`
                        : iss.linked ? ` · ${iss.linked} subcaps linked to issues (no cap level stated)` : ""} · click to drill`}>
                    <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2, gap: 2 }}>
                      {/* Same value as the subcap-view picker's badge
                          (`score`, else the cells' mean), so it says the same
                          thing when there is neither: `fx` would print an em
                          dash. 10.5px so the phrase sits on the numeral's
                          line in a column of this grid. */}
                      {shown == null
                        ? <div style={{ fontSize: 10.5, fontWeight: 600 }}><EnrichmentGap what={`${c.id} score`} audience={audience} compact /></div>
                        : <div style={{ fontSize: 13, fontWeight: 700 }}>{fx(shown, 1)}</div>}
                      {c.thin > 0 ? <div style={{ fontSize: 8, fontWeight: 600 }}>{c.thin} thin</div> : null}
                    </div>
                    {showIssues && capCount > 0 ? (
                      <span style={{ position: "absolute", top: 3, right: 4, display: "inline-flex", alignItems: "center", gap: 2, fontSize: 9, color: "var(--z-org)", background: "rgba(255,255,255,.85)", padding: "0 3px", borderRadius: 3 }}>
                        <Icon name={iss.capped ? "lock" : "warn"} size={9} />
                        {capCount}
                      </span>
                    ) : null}
                  </button>
                );
              })}

              {showPeers ? <>
                <div style={{ fontSize: 11, color: "var(--z-muted)", display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 8 }}>Peer</div>
                {cats.map(c => {
                  const pm = c.peer;
                  // A null median banded as maturityClass(null) and printed 0.0,
                  // so all sixteen categories read "Peer 0.0" in the lowest band
                  // — a peer set that scores nothing.
                  return pm == null ? (
                    /* Compact, and only compact: this is a fixed-height grid
                       cell in a row of peer figures — the queue badge would
                       burst the column. */
                    <div key={c.id} className="hm-cell peer b b-muted" style={{ minHeight: 30, padding: "4px 6px" }}
                         title="no peer median stated for this category in this run">
                      <EnrichmentGap what={`${c.id} peer median`} audience={audience} compact />
                    </div>
                  ) : (
                    <div key={c.id} className={`hm-cell peer b ${DMA.helpers.maturityClass(pm)}`} style={{ minHeight: 30, padding: "4px 6px" }}
                         title={`${c.id} — ${c.name || "unnamed in catalogue"} · peer median ${fx(pm, 1)}`}
                         onMouseEnter={cellTip.show(`${c.id} — ${c.name || "unnamed in catalogue"} · peer median ${fx(pm, 1)}`)}
                         onMouseLeave={cellTip.hide}>
                      {fx(pm, 1)}
                    </div>
                  );
                })}
              </> : null}

              <div></div>
              {cats.map(c => (
                <div key={`l-${c.id}`} style={{ fontSize: 9.5, color: "var(--z-muted)", textAlign: "center", padding: "4px 2px 0", lineHeight: 1.3, minWidth: 0 }}
                     title={c.inCatalogue ? `${c.id} · ${c.name}`
                       : `${c.id} · this run scored ${c.cells.length} cells here; the current catalogue does not list this category, so no name is available`}>
                  <div className="f-mono">{c.id}</div>
                  {/* A category the catalogue cannot name is labelled with its
                      id and marked unnamed. Inventing a name for it would be
                      inventing data; dropping it hid 30 promoted cells. */}
                  <div className="txt-fit-2" style={c.inCatalogue ? null : { fontStyle: "italic" }}>{c.name || "unnamed in catalogue"}</div>
                </div>
              ))}
            </div>
            )}
          </div>
        );
      })}
      <CellTip tip={cellTip.tip} />
    </div>
  );
}

/* ─────────────────────── CAPABILITY HEATMAP ─────────────────────
   The capability grain: one row per capability (L1) with the cells beneath it.
   The run's cell grain carries `capability_id` but no capability NAME, so a row
   is labelled with its id — the alternative would be inventing one. The mean is
   computed from the cells because nothing is promoted at this grain, and every
   row says how many cells it is a mean of. */
function CapabilityHeatmap({ entity, cats, catFocus, pillarFocus, showIssues, drillCategory, audience }) {
  const scope = catFocus ? (cats || []).filter(c => c.id === catFocus)
    : pillarFocus ? (cats || []).filter(c => c.pillar === pillarFocus)
    : (cats || []);
  if (!scope.length) {
    return (
      <div className="card"><div style={{ fontSize: 12, color: "var(--z-muted)" }}>
        This run scored no cells in the current selection.
      </div></div>
    );
  }
  return (
    <div>
      {scope.map(c => {
        const groups = [];
        const byCap = {};
        for (const s of c.cells) {
          const cap = s.capability || `${c.id} · cell carries no capability id`;
          if (!byCap[cap]) { byCap[cap] = { id: cap, items: [] }; groups.push(byCap[cap]); }
          byCap[cap].items.push(s);
        }
        groups.sort((a, b) => String(a.id).localeCompare(String(b.id), undefined, { numeric: true }));
        return (
          <div key={c.id} className="card" style={{ marginBottom: 14 }}>
            <div className="row" style={{ marginBottom: 12 }}>
              <span className="chip">{c.id}</span>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{c.name || "unnamed in catalogue"}</span>
              <MaturityChip score={c.score != null ? c.score : c.cellMean} />
              <span className="spacer" />
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                {groups.length} capabilities · {c.cells.length} subcaps
                {c.weight != null ? ` · weight ${fx(c.weight * 100, 0)}%` : ""}
              </span>
            </div>
            {/* Said once for the card rather than on every row: nothing is
                promoted at this grain, so every figure below is a mean of the
                cells named beside it. */}
            <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginBottom: 8 }}>
              The run promotes no score and no name at capability grain — each row is its own cells' mean, labelled with its capability id.
            </div>
            <div className="g2" style={{ gap: 8 }}>
              {groups.map(g => {
                const mean = meanOf(g.items.map(s => s.score));
                const thin = g.items.filter(s => s.thin).length;
                const capped = showIssues ? g.items.filter(s => DMA.issueCapsFor(s.id).length).length : 0;
                return (
                  <button key={g.id} className="card-tile clickable" style={{ padding: 10, textAlign: "left" }}
                    onClick={() => drillCategory && drillCategory(c.id)}
                    title={`${g.id} · mean of ${g.items.length} scored cells (no capability score is promoted) · click to read the cells`}>
                    <div className="row" style={{ gap: 8 }}>
                      {/* No capability score is promoted at this grain, so a
                          null mean means not one cell in the group is scored —
                          and `fx` printed an em dash for it. The badge shell
                          goes with the numeral: `.b` is nowrap on a 34px fixed
                          box, so a phrase left inside it would overrun the id
                          beside it. Bare and shrinkable instead. */}
                      {mean == null
                        ? <span style={{ flex: "0 1 auto", minWidth: 0 }}><EnrichmentGap what={`${g.id} cell scores`} audience={audience} compact /></span>
                        : <span className={`b ${DMA.helpers.maturityClass(mean)}`} style={{ width: 34, justifyContent: "center", flexShrink: 0 }}>{fx(mean, 1)}</span>}
                      <span className="f-mono txt-fit-1" style={{ fontSize: 11.5, fontWeight: 600, color: "var(--z-dark)", minWidth: 0 }}>{g.id}</span>
                      <span className="spacer" />
                      <span className="b b-muted" title="cells in this capability">{g.items.length}</span>
                      {thin ? <span className="b b-org">{thin} thin</span> : null}
                      {capped ? <span className="b b-org"><Icon name="lock" size={9} /> {capped}</span> : null}
                    </div>
                    <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 4 }}>mean of {g.items.length} cell{g.items.length === 1 ? "" : "s"}</div>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ─────────────────────── SUBCAP HEATMAP ─────────────────────── */
function SubcapHeatmap({ entity, cats: allCats, catFocus, pillarFocus, showPeers, showIssues, onSynth, setCatFocus, audience }) {
  const [openClusters, setOpenClusters] = useState({});
  // Every grid that paints a cell gets the same bubble. This one and the
  // capability grid carried the `title` attribute alone, which is the
  // browser's own tooltip: it waits about a second, paints in the OS style,
  // and reads as nothing happening to anyone who moves on before it fires.
  // Same text, same instant bubble, in all four views.
  const cellTip = useCellTip();
  // The run's categories, so a category the current catalogue does not list is
  // still reachable and its cells still readable.
  const cats = catFocus ? (allCats || []).filter(c => c.id === catFocus) :
               pillarFocus ? (allCats || []).filter(c => c.pillar === pillarFocus) :
               null;

  // No category/pillar in focus → show a picker instead of dumping all 765 cells
  if (!cats || cats.length === 0) {
    const pillarIds = [];
    for (const c of allCats || []) if (!pillarIds.includes(c.pillar)) pillarIds.push(c.pillar);
    return (
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="row" style={{ marginBottom: 4 }}>
          <Icon name="grid" size={14} />
          <div style={{ fontSize: 13, fontWeight: 600 }}>Select a category to view its sub-capabilities</div>
        </div>
        <div style={{ fontSize: 11.5, color: "var(--z-muted)", marginBottom: 14 }}>The subcap view drills into one category at a time so you can read the evidence behind each score. Pick a category below.</div>
        {pillarIds.sort().map(pid => {
          const meta = (DMA.PILLARS || []).find(p => p.id === pid) || null;
          const pcats = (allCats || []).filter(c => c.pillar === pid);
          return (
            <div key={pid} style={{ marginBottom: 12 }}>
              <div className="row" style={{ marginBottom: 6, gap: 6 }}>
                <span className="b b-purple">{pid}</span>
                <span style={{ fontSize: 11.5, fontWeight: 600, color: "var(--z-dark)" }}>{(meta && (meta.short || meta.name)) || "unnamed in catalogue"}</span>
              </div>
              <div className="g4" style={{ gap: 8 }}>
                {pcats.map(c => {
                  // The promoted category score, else the mean of its cells,
                  // else nothing. A zero here read as a measured floor.
                  const shown = c.score != null ? c.score : c.cellMean;
                  return (
                    <button key={c.id} className="card-tile clickable" style={{ padding: 11, textAlign: "left" }} onClick={() => setCatFocus && setCatFocus(c.id)} disabled={!c.cells.length}>
                      <div className="row" style={{ marginBottom: 6, gap: 5 }}>
                        <span className="chip">{c.id}</span>
                        <span className="spacer" />
                        {/* Neither a promoted category score nor a mean of
                            scored cells: the score is absent, not zero. The
                            badge shell stays so the picker tiles keep their
                            row rhythm; compact inside it. */}
                        {shown != null ? <span className={`b ${DMA.helpers.maturityClass(shown)}`}>{fx(shown, 1)}</span>
                          : <span className="b b-muted"><EnrichmentGap what={`${c.id} score`} audience={audience} compact /></span>}
                      </div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--z-dark)" }} className="txt-fit-2">{c.name || "unnamed in catalogue"}</div>
                      <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 3 }}>{c.cells.length} subcaps{c.thin ? ` · ${c.thin} thin` : ""}</div>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div>
      {catFocus ? (
        <div className="row" style={{ marginBottom: 10 }}>
          <button className="btn btn-tertiary btn-sm" onClick={() => setCatFocus && setCatFocus(null)}><Icon name="chevron-l" size={12} /> All categories</button>
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Showing sub-capabilities for {catFocus}</span>
        </div>
      ) : null}
      {cats.map(c => {
        const subs = c.cells;
        // Capability clusters, grouped on the cell grain's own `capability`
        // (capability_id). This grouped on `l1`/`l1name` — keys the live cell
        // grain has never carried — so every cell in a category fell into one
        // undefined bucket: all 43 P4C1 cells under a heading reading "P4C1."
        // and "1 capabilities". The run carries no capability NAME, so a
        // cluster is labelled with its id rather than an invented title.
        const clusters = [];
        const byCap = {};
        subs.forEach(s => {
          const cap = s.capability || `${c.id}·no capability id`;
          if (!byCap[cap]) { byCap[cap] = { id: cap, named: !!s.capability, items: [] }; clusters.push(byCap[cap]); }
          byCap[cap].items.push(s);
        });
        clusters.sort((a, b) => String(a.id).localeCompare(String(b.id), undefined, { numeric: true }));
        return (
          <div key={c.id} className="card" style={{ marginBottom: 14 }}>
            <div className="row" style={{ marginBottom: 12 }}>
              <span className="chip">{c.id}</span>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{c.name || "unnamed in catalogue"}</span>
              <span className="spacer" />
              {/* The catalogue states no category weights in this version, and
                  `null * 100` printed "weight 0%" — a weight of zero is a claim
                  the catalogue never made. */}
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{subs.length} subcaps · {clusters.length} capabilities{c.weight != null ? ` · weight ${fx(c.weight * 100, 0)}%` : ""}</span>
            </div>
            {clusters.map(cl => {
              const key = `${c.id}.${cl.id}`;
              const open = openClusters[key] !== false; // default open
              const avg = meanOf(cl.items.map(s => s.score));
              const capped = showIssues ? cl.items.filter(s => DMA.issueCapsFor(s.id).length).length : 0;
              return (
                <div key={key} style={{ border: "1px solid var(--z-sep)", borderRadius: 8, marginBottom: 8, overflow: "hidden" }}>
                  <button onClick={() => setOpenClusters(o => ({ ...o, [key]: !open }))}
                    title={`${cl.id} · mean of ${cl.items.length} scored cells (no capability score or name is promoted at this grain)`}
                    style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, padding: "9px 12px", background: "var(--z-bg)", border: 0, cursor: "pointer", textAlign: "left" }}>
                    {/* Same as the capability grid: nothing is promoted at
                        this grain, so a null mean is a cluster with no scored
                        cell in it, and `fx` printed an em dash. Out of the
                        34px nowrap badge for the same reason. */}
                    {avg == null
                      ? <span style={{ flex: "0 1 auto", minWidth: 0 }}><EnrichmentGap what={`${cl.id} cell scores`} audience={audience} compact /></span>
                      : <span className={`b ${DMA.helpers.maturityClass(avg)}`} style={{ width: 34, justifyContent: "center", flexShrink: 0 }}>{fx(avg, 1)}</span>}
                    <span className="f-mono txt-fit-1" style={{ flex: 1, minWidth: 0, fontSize: 12, fontWeight: 600, color: "var(--z-dark)" }}>{cl.id}</span>
                    <span style={{ fontSize: 10, color: "var(--z-muted)", flexShrink: 0 }}>{cl.items.length} cells</span>
                    {capped ? <span className="b b-org"><Icon name="lock" size={9} /> {capped}</span> : null}
                    <Icon name={open ? "chevron-u" : "chevron-d"} size={13} style={{ color: "var(--z-muted)", flexShrink: 0 }} />
                  </button>
                  {open ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 5, padding: "8px 10px" }}>
                      {cl.items.map(s => {
                        const caps = showIssues ? DMA.issueCapsFor(s.id) : [];
                        // null - score is -score, which printed as "+score vs
                        // peer" in the above-peer colour on every row.
                        const gap = deltaOf(s.peerMedian, s.score);
                        // The cell's own citation count where it promoted a
                        // list, else the run's link count for the cell. Counting
                        // evidence rows that mention the cell is a coarser
                        // number: it made all 43 P4C1 cells read "5 evidence".
                        const ev = evidenceCountOf(s);
                        return (
                          /* The name column ellipsises to one line; the title
                             carries the full identification. */
                          <button key={s.id} className="subcap-row" onClick={() => onSynth(s)} title={subcapTipText(s)}
                                  onMouseEnter={cellTip.show(subcapTipText(s))} onMouseLeave={cellTip.hide}>
                            {/* An unscored cell printed an em dash in the
                                score badge while the row beneath it said
                                "no evidence count" in words. Same treatment as
                                the platform page's backing-cell rail: the
                                nowrap 34px badge goes with the numeral. */}
                            {s.score == null
                              ? <span style={{ flex: "0 1 auto", minWidth: 0 }}><EnrichmentGap what={`${s.id} score`} audience={audience} compact /></span>
                              : <span className={`b ${DMA.helpers.maturityClass(s.score)}`} style={{ width: 34, justifyContent: "center", flexShrink: 0 }}>{fx(s.score, 1)}</span>}
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div className="row" style={{ gap: 6 }}>
                                {/* The adapter falls back to the id when the
                                    catalogue has no name for a cell (every
                                    P1C5 cell, the category v7.0 dropped), so
                                    the row printed the id twice and looked
                                    like a name. Said once, as an absence. */}
                                <span style={{ fontSize: 12, fontWeight: 500, color: s.name && s.name !== s.id ? "var(--z-dark)" : "var(--z-muted)", fontStyle: s.name && s.name !== s.id ? "normal" : "italic" }} className="txt-fit-1">
                                  {s.name && s.name !== s.id ? s.name : "unnamed in catalogue"}
                                </span>
                                {s.thin ? <span className="b b-org">THIN</span> : null}
                                {caps.length ? <span className="b b-org"><Icon name="lock" size={9} /> M{caps[0].cap}</span> : null}
                              </div>
                              <div className="f-mono txt-fit-1" style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 1 }}
                                   title={ev.basis === "cited" ? "ids the producer cited for this cell"
                                     : ev.basis === "linked" ? "evidence items the run links to this cell" : null}>
                                {s.id}{s.confidence ? ` · ${s.confidence}` : ""}{ev.n != null ? ` · ${ev.n} ${ev.basis}` : " · no evidence count"}
                              </div>
                            </div>
                            <div style={{ width: 90, flexShrink: 0 }}>
                              <div style={{ position: "relative", height: 6, background: "var(--z-sep)", borderRadius: 3 }}
                                   title={`${s.score != null ? `Score ${fx(s.score, 1)}` : "no score stated"}${s.peerMedian != null ? ` · Peer ${fx(s.peerMedian, 1)}` : " · no peer median stated"}`}>
                                {/* An unscored cell gets no fill rather than a
                                    zero-width bar that reads as a floor. */}
                                {s.score != null ? (
                                  <div style={{ width: `${s.score / 5 * 100}%`, height: "100%", background: DMA.helpers.maturityHex(s.score), borderRadius: 3 }} />
                                ) : null}
                                {/* The tick is a peer POSITION. With a null median it
                                    was drawn at 0%, which reads as a peer set scoring
                                    nothing. No median, no tick. */}
                                {s.peerMedian != null ? (
                                  <div style={{ position: "absolute", left: `calc(${s.peerMedian / 5 * 100}% - 1px)`, top: -2, bottom: -2, width: 2, background: "var(--z-dpur)" }} />
                                ) : null}
                              </div>
                              {gap != null ? (
                                <div style={{ fontSize: 9, color: gap > 0 ? "var(--z-below)" : gap < 0 ? "var(--z-mid)" : "var(--z-muted)", marginTop: 2, textAlign: "right" }}>{gap > 0 ? `−${fx(gap, 1)}` : gap < 0 ? `+${fx(Math.abs(gap), 1)}` : "0.0"} vs peer</div>
                              ) : (
                                <div style={{ fontSize: 9, color: "var(--z-muted)", marginTop: 2, textAlign: "right" }}>&nbsp;</div>
                              )}
                            </div>
                            <div style={{ display: "flex", gap: 3, flexShrink: 0 }}>
                              {s.platforms.slice(0, 2).map(p => <span key={p} className="b b-teal">{DMA.getPlatform(p)?.short || p}</span>)}
                            </div>
                            <Icon name="chevron-r" size={13} style={{ color: "var(--z-muted)", flexShrink: 0 }} />
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        );
      })}
      <CellTip tip={cellTip.tip} />
    </div>
  );
}

/* ─────────────────────── VALUE CHAIN VIEW ─────────────────────── */
// The cells a value-chain stage actually covers. Each stage declares its own
// membership list; the view used to pick `subcaps.slice(hash(stage.id) % n, +8)`
// instead, which is why the cells under "Loan Origination" had nothing to do
// with loan origination. A stage that declares nothing renders empty and says
// so — the arrangement is a claim about the client's operating model, and an
// arbitrary slice of it is not one.
function subcapsForStage(entity, vc) {
  const named = new Set((vc && (vc.subcaps || vc.subcap_ids)) || []);
  const all = Array.isArray(entity.subcaps) ? entity.subcaps : [];
  if (!named.size || !all.length) return [];
  const exact = all.filter((s) => named.has(s.id));
  if (exact.length) return exact;
  return all.filter((s) =>
    [...named].some((n) => typeof n === "string" && s.id.startsWith(`${n}.`)));
}


function ValueChainView({ entity, subcapsForFocusArea, openSubcap, openInsight }) {
  const [selected, setSelected] = useState(null);
  // The stage tiles' mini-cells carry a score and nothing else — hover
  // identification, same shared-bubble pattern as the other grids.
  const cellTip = useCellTip();
  const chains = DMA.VALUE_CHAINS || [];
  const state = (typeof DMA.sectionStateFor === "function")
    ? DMA.sectionStateFor("heatmap.value_chain") : null;
  const empty = state && state.empty_state;

  /* The section is optional and Baxter's run submitted eight of nine sections
     without it. With no chains the view rendered its heading, an empty grey
     badge and "Same 765 subcaps, reorganised by business process" over an empty
     grid — a promise that the cells had been arranged by business process when
     nothing had been. The stage arrangement is a claim about this client's
     operating model, so there is nothing to derive it from; say that it did not
     promote, and name what the API said. */
  if (!chains.length) {
    return (
      <div className="empty">
        <div className="icon"><Icon name="route" size={20} /></div>
        <h3>The value chain section did not promote for this run</h3>
        <p>
          {empty
            ? `${String(empty.kind || "empty").replace(/_/g, " ")}${empty.reason ? ` — ${empty.reason}` : ""}.`
            : "The run promoted no value-chain stages."}
        </p>
        <p style={{ marginTop: 8 }}>
          Which cells belong to which business process is the producer's claim
          about {entity.name}'s operating model. The cell grain alone cannot
          stand it up, so nothing is drawn here until the section promotes.
        </p>
      </div>
    );
  }

  const mapped = new Set();
  for (const vc of chains) for (const s of subcapsForStage(entity, vc)) mapped.add(s.id);

  /* The whole arrangement, in its stated order. This used to draw the five
     stages with the deepest scored coverage and print a line admitting to
     twenty-five more, because the catalogue derived one stage per workbook
     label — 48 for a credit union, of which the API served 30. That was the
     right patch for the wrong layer: which processes an institution runs is
     catalogue knowledge, and 0024 moved it there (eight per sub-vertical,
     each folding the labels that name the same process). With the catalogue
     holding an arrangement a reader can follow, the renderer's job is to draw
     it — reordering by "depth" would break the sequence, which is the one
     thing a value chain has that a grid does not. */

  // How many mini-cells a stage tile's strip can hold and stay legible.
  const STRIP = 12;

  return (
    <div>
      <div className="row" style={{ marginBottom: 12 }}>
        <Icon name="route" size={14} />
        <div style={{ fontSize: 13, fontWeight: 600 }}>Value chain view</div>
        <span className="spacer" />
        {/* Counted, not asserted: only the cells the stages actually name are
            arranged by process. */}
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{chains.length} stages · {mapped.size} of {entity.subcaps.length} subcaps mapped</span>
      </div>
      <div className="g3" style={{ marginBottom: 14 }}>
        {chains.map(vc => {
          // Pick subcaps representative of value chain - sample from subcaps
          const subs = subcapsForStage(entity, vc);
          const scored = subs.filter(s => s.score != null);
          const avg = scored.length
            ? scored.reduce((a, s) => a + s.score, 0) / scored.length : null;
          // Peer medians are absent at cell grain in every shipped package, so
          // this is null far more often than not — and averaging nulls produced
          // NaN on the tile. Computed-or-null, never a placeholder.
          const withPeer = subs.filter(s => s.peerMedian != null);
          const peer = withPeer.length
            ? withPeer.reduce((a, s) => a + s.peerMedian, 0) / withPeer.length : null;
          return (
            <div key={vc.id} className="card-tile clickable" style={{ padding: 14, border: selected === vc.id ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)", background: selected === vc.id ? "var(--z-ice)" : "#fff" }}
              onClick={() => setSelected(vc.id === selected ? null : vc.id)}>
              {/* The stage's name, and only its name. The catalogue's stage
                  code (VC-CU-07 and its siblings) is an internal join key —
                  it identifies nothing a reader of this page can look up, and
                  a code beside every heading reads as jargon. It stays the
                  React key, where it belongs. */}
              <div className="row" style={{ marginBottom: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{vc.name}</span>
              </div>
              <div className="row" style={{ marginBottom: 8 }}>
                {avg == null ? <span className="b b-muted">No score</span>
                             : <MaturityChip score={avg} />}
                {peer == null ? null
                  : <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Peer {fx(peer, 1)}</span>}
                <span className="spacer" />
                <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                  {subs.length} subcap{subs.length === 1 ? "" : "s"}
                </span>
              </div>
              {!subs.length ? (
                <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
                  No cells mapped to this stage for this run.
                </div>
              ) : (
                <>
                  <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(subs.length, STRIP)}, 1fr)`, gap: 2 }}>
                    {subs.slice(0, STRIP).map(s => (
                      <div key={s.id} className={`hm-cell b ${DMA.helpers.maturityClass(s.score)}`} style={{ height: 18, fontSize: 9, padding: 0, border: 0 }}
                        title={subcapTipText(s)}
                        onMouseEnter={cellTip.show(subcapTipText(s))}
                        onMouseLeave={cellTip.hide}>
                        {/* 18px tall and up to twelve to a row: no wording
                            fits in this swatch, and `fx` painted an em dash
                            into it. The swatch already carries the "nothing
                            measured" band colour and names itself on hover
                            ("… · no score"), which is the idiom this file
                            uses for every other unscored mark (no bar, no
                            tick). Deliberately NOT an EnrichmentGap: the
                            enrichment route for these cells is the grid they
                            come from, and a phrase here would burst the
                            strip. */}
                        {s.score == null ? null : fx(s.score, 1)}
                      </div>
                    ))}
                  </div>
                  {/* A stage of 373 cells cannot draw 373 swatches in a tile,
                      and a strip of twelve beside the figure "373 subcaps"
                      reads as if those twelve WERE the stage. Say which twelve.
                      The tile's score above is the mean of every scored cell in
                      the stage, not of the strip — the strip is an opening, and
                      the panel below holds all of them. */}
                  {subs.length > STRIP ? (
                    <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 5 }}>
                      first {STRIP} cells by id · open the stage for all {subs.length}
                    </div>
                  ) : null}
                </>
              )}
            </div>
          );
        })}
      </div>

      {selected ? (() => {
        const vc = chains.find(x => x.id === selected);
        if (!vc) return null;
        const subs = subcapsForStage(entity, vc);
        const insights = DMA.INSIGHT_CARDS.filter(ic => ic.affects.some(sid => subs.some(s => s.id === sid)));
        return (
          <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 14 }}>
            <div className="card">
              <div className="row" style={{ marginBottom: 12 }}>
                <Icon name="heatmap" size={14} />
                <div style={{ fontSize: 13, fontWeight: 600 }}>{vc.name} · subcaps</div>
                <span className="spacer" />
                <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{subs.length} cells · click to drill</span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                {subs.map(s => (
                  <button key={s.id} className="card-tile clickable" style={{ padding: 10 }} title={subcapTipText(s)}
                    onMouseEnter={cellTip.show(subcapTipText(s))} onMouseLeave={cellTip.hide}
                    onClick={() => { cellTip.hide(); openSubcap({ kind: "subcap", subcap: s }); }}>
                    <div className="row" style={{ marginBottom: 4 }}>
                      <MaturityChip score={s.score} />
                      <span className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{s.id}</span>
                      <span className="spacer" />
                      {s.thin ? <span className="b b-org">THIN</span> : null}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--z-dark)" }} className="txt-fit-2">{s.name}</div>
                  </button>
                ))}
              </div>
            </div>
            <div className="card flush">
              <div className="card-head">
                <h3>Insight cards in this chain</h3>
                <span className="b b-muted">{insights.length}</span>
              </div>
              <div style={{ padding: 12 }}>
                {insights.length === 0 ? <div className="muted" style={{ fontSize: 12 }}>No insight cards mapped</div> : insights.map(ic => (
                  <button key={ic.id} className="card-tile clickable" style={{ marginBottom: 8, padding: 12, width: "100%", textAlign: "left" }} onClick={() => openInsight(ic.id)}>
                    <div className="row" style={{ marginBottom: 4 }}>
                      <span className="ic-id">{ic.id}</span>
                      <span className={`b ${ic.flag === "CRITICAL" ? "b-below" : ic.flag === "OPPORTUNITY" ? "b-org" : "b-teal"}`}>{ic.flag}</span>
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 600 }} className="txt-fit-1">{ic.title}</div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        );
      })() : null}
      <CellTip tip={cellTip.tip} />
    </div>
  );
}

/* A category's citations: the union of its cells' promoted lists, in cell order.
   Falls back to the run's link table only when no cell in the category promoted
   one, and says which it used. */
function categoryCitationsOf(cells) {
  const seen = new Set();
  const items = [];
  let withLists = 0;
  for (const c of cells || []) {
    const cell = (typeof DMA.cellEvidenceFor === "function") ? DMA.cellEvidenceFor(c.id) : null;
    const ids = (cell && Array.isArray(cell.e_ids)) ? cell.e_ids : [];
    if (ids.length) withLists += 1;
    for (const id of ids) {
      if (seen.has(id)) continue;
      seen.add(id);
      const e = DMA.getEvidence(id) || null;
      items.push(e ? { ...e, resolved: true } : { id, resolved: false });
    }
  }
  if (items.length) return { basis: "promoted", items, withLists };
  const ids = new Set((cells || []).map(c => c.id));
  return {
    basis: "derived",
    withLists: 0,
    items: (DMA.EVIDENCE || [])
      .filter(e => e.subcaps && e.subcaps.some(sid => ids.has(sid)))
      .map(e => ({ ...e, resolved: true })),
  };
}

/* The score axis. It was labelled with five maturity levels, and the fifth does
   not exist: there are four bands, resolved on the raw score, strictly
   less-than. Labelled with the scale's own numbers and the band that owns each
   range. */
function BandAxis() {
  return (
    <>
      {/* The tick row is sized to its own line box: an absolutely positioned
          span in a shorter box hangs below it and lands on the band words. */}
      <div style={{ position: "relative", height: 15, fontSize: 10, color: "var(--z-muted)", fontFamily: "var(--font-mono)" }}>
        {[1, 2, 3, 4, 5].map(t => (
          <span key={t} style={{ position: "absolute", top: 0, lineHeight: "14px", left: `${(t - 1) / 4 * 100}%`,
            transform: t === 1 ? "none" : t === 5 ? "translateX(-100%)" : "translateX(-50%)" }}>{t}</span>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 2, fontSize: 9, color: "var(--z-muted)", textAlign: "center" }}>
        {["Activating", "Building", "Competing", "Differentiating"].map(b => (
          <span key={b} className="txt-fit-1">{b}</span>
        ))}
      </div>
    </>
  );
}

/* ─────────────────────── SYNTHESIS DRAWER ─────────────────────── */
function SynthesisDrawer({ entity, item, onClose, openEvidence, openInsight, showIssues, audience }) {
  const subcap = item.subcap;
  const catId = item.catId || (subcap && subcap.category) || null;
  const cats = useMemo(() => runCategoriesOf(entity), [entity?.id, entity?.subcaps]);
  // The RUN's category row. Reading `DMA.getCategory` alone meant a category the
  // current catalogue does not list (P1C5, 30 scored cells) resolved to nothing
  // and the drawer returned null — no synthesis at all for those cells.
  const catRow = catId ? (cats.find(c => c.id === catId) || null) : null;
  const category = item.catId ? (catRow || null) : null;
  if (!subcap && !category) return null;
  const catCells = catRow ? catRow.cells : [];

  // Linked insight cards
  const linkedIC = subcap ? DMA.INSIGHT_CARDS.filter(ic => (ic.affects || []).includes(subcap.id)) :
                            DMA.INSIGHT_CARDS.filter(ic => (ic.affects || []).some(sid => sid.startsWith(category.id)));

  /* The cell's OWN promoted citation list, which is what the producer wrote and
     what the evidence gate checked. This used to reverse-derive from
     `DMA.EVIDENCE[].subcaps` and disagreed with the promoted list on 65 of 69
     cells — P4C1.1.1 promoted four ids and the drawer showed five, including a
     core-banking item never cited for that cell; P1C1.1.1 lost one it did cite.
     The reverse derivation remains the fallback for cells that promoted no
     list, and the header says which of the two is on screen. */
  const cit = subcap ? cellCitationsOf(subcap.id) : categoryCitationsOf(catCells);
  const linkedEv = cit.items;

  // Issue caps (subcap only)
  const caps = subcap ? DMA.issueCapsFor(subcap.id) : [];

  // Peer comparison (for a category, the promoted category figures)
  const score = subcap ? numOf(subcap.score)
    : (catRow.score != null ? catRow.score : catRow.cellMean);
  const scoreBasis = subcap ? null
    : (catRow.score != null
        ? `promoted category score${catRow.source_cell ? ` · ${catRow.source_cell}` : ""}`
        : `mean of ${catCells.length} scored cells — the run promoted no category score`);
  // The drawer's peer figure. For a category it was `score + 0.3`; for a cell it
  // was the null cell median, then formatted, then compared. Read the promoted
  // category median where there is one, and inherit it at cell grain labelled a
  // PROXY (the workbook states medians at category grain, not per cell).
  const catPeer = catRow ? catRow.peer : null;
  const peer = subcap
    ? (subcap.peerMedian != null ? Number(subcap.peerMedian) : catPeer)
    : catPeer;
  const peerIsProxy = !!(subcap && subcap.peerMedian == null && catPeer != null);
  // `peer - score` with a null peer is -score, which printed as "+2.5" in the
  // above-peer colour on a cell with no benchmark at all.
  const gap = deltaOf(peer, score);

  return (
    <>
      <div className="drawer-mask" onClick={onClose} />
      <div className="drawer" style={{ width: 480 }}>
        <div className="drawer-head">
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="b b-teal">SYNTHESIS</span>
              {subcap ? <span className="chip purple">{subcap.id}</span> : <span className="chip">{category.id}</span>}
              {subcap?.thin ? <span className="b b-org">THIN</span> : null}
            </div>
            <div className="title" style={{ fontSize: 15 }}>{subcap
              ? (subcap.name && subcap.name !== subcap.id ? subcap.name : `${subcap.id} · unnamed in catalogue`)
              : (category.name || `${category.id} · unnamed in catalogue`)}</div>
            <div className="sub">{subcap
              ? `${subcap.score != null ? `Score ${fx(subcap.score, 1)}` : "no score stated"}${subcap.confidence ? ` · ${subcap.confidence}` : ""}`
              : `${catCells.length} subcaps${category.weight != null ? ` · weight ${fx(category.weight * 100, 0)}%` : ""}`}</div>
          </div>
          <button className="icon-btn" onClick={onClose}><Icon name="x" size={16} /></button>
        </div>
        <div className="drawer-body">

          {/* Peer comparison viz */}
          <div className="card-tile" style={{ marginBottom: 14, background: "var(--z-lav)", border: 0 }}>
            <div className="row" style={{ marginBottom: 10 }}>
              <Icon name="scale" size={13} />
              <span style={{ fontSize: 12, fontWeight: 600 }}>Peer comparison</span>
            </div>
            <div style={{ position: "relative", height: 36, background: "#fff", borderRadius: 6, overflow: "hidden", marginBottom: 8 }}>
              {/* Scale 1-5 with markers */}
              {[1,2,3,4,5].map(t => (
                <div key={t} style={{ position: "absolute", left: `${(t-1)/4 * 100}%`, top: 0, bottom: 0, width: 1, background: "var(--z-sep)" }} />
              ))}
              {/* Both markers are POSITIONS on the scale. With a null value the
                  arithmetic yields NaN, and a NaN% offset lands the marker at 0 —
                  a score, or a peer set, of nothing. */}
              {score != null ? (
                <div style={{ position: "absolute", left: `calc(${(score - 1) / 4 * 100}% - 6px)`, top: 4, width: 12, height: 28, background: DMA.helpers.maturityHex(score), borderRadius: 3, boxShadow: "0 1px 3px rgba(0,0,0,.2)" }} title="Entity" />
              ) : null}
              {peer != null ? (
                <div style={{ position: "absolute", left: `calc(${(peer - 1) / 4 * 100}% - 1px)`, top: 0, bottom: 0, width: 2, background: "var(--z-dpur)" }} title="Peer median" />
              ) : null}
            </div>
            <BandAxis />
            <div className="row" style={{ marginTop: 10, fontSize: 12, flexWrap: "wrap", gap: 8 }}>
              <span className="row" style={{ gap: 5 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: DMA.helpers.maturityHex(score) }} /> Entity {score == null
                  /* The marker above already guards on a null score; this
                     readout did not, so `fx` printed "Entity —" beside a
                     peer branch that says "no peer median stated" in words.
                     Compact: the row carries entity, peer and delta on one
                     line. */
                  ? <EnrichmentGap what={subcap ? `${subcap.id} score` : `${catId || "category"} score`} audience={audience} compact />
                  : <strong>{fx(score, 1)}</strong>}
              </span>
              <span className="spacer" />
              {peer != null ? (
                <span className="row" style={{ gap: 5 }}><span style={{ width: 2, height: 12, background: "var(--z-dpur)" }} /> Peer <strong>{fx(peer, 1)}</strong></span>
              ) : (
                <span style={{ fontSize: 11, color: "var(--z-muted)" }} title="no peer median is stated at this grain in this run">no peer median stated</span>
              )}
              <span className="spacer" />
              {gap != null ? (
                <span style={{ fontSize: 11, color: gap > 0 ? "var(--z-below)" : gap < 0 ? "var(--z-mid)" : "var(--z-muted)" }}>
                  {gap > 0 ? `−${fx(gap, 1)}` : gap < 0 ? `+${fx(Math.abs(gap), 1)}` : "0.0"}
                </span>
              ) : null}
            </div>
            <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 6, lineHeight: 1.45 }}>
              {scoreBasis ? `${scoreBasis}. ` : ""}
              {peer == null ? "The run states no peer median at this grain."
                : peerIsProxy ? `Peer figure is ${catId}'s category median, used as a proxy — the workbook states no median per cell.`
                : "Peer median as stated for this grain."}
            </div>
          </div>

          {/* Caps from issues */}
          {caps.length > 0 ? (
            <div className="co co-org" style={{ marginBottom: 14 }}>
              <Icon name="lock" size={14} />
              <div style={{ flex: 1 }}>
                <div className="co-title">Capped by {caps.length} issue{caps.length === 1 ? "" : "s"}</div>
                {caps.map(c => {
                  // An issue whose row did not promote has no description, and
                  // `.desc.slice` on it took the drawer down.
                  const desc = (c.issue && (c.issue.desc || c.issue.title)) || null;
                  return (
                    <div key={c.id} style={{ fontSize: 12, marginTop: 4 }}>
                      <span className="chip" style={{ marginRight: 6 }}>{c.id}</span>
                      {desc ? `${desc.slice(0, 70)}${desc.length > 70 ? "…" : ""} ` : ""}
                      {c.cap != null ? <strong>Cap M{c.cap}</strong> : <span className="muted">cap level not stated</span>}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          {/* Source reports & evidence — shown BEFORE any AI enrichment */}
          <div style={{ marginBottom: 14 }}>
            <div className="row" style={{ marginBottom: 8, gap: 6 }}>
              <Icon name="evidence" size={13} style={{ color: "var(--z-mid)" }} />
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-dark)", textTransform: "uppercase" }}>Source reports &amp; evidence</span>
              <span className="b b-muted">{linkedEv.length}</span>
              <span className="spacer" />
              <span style={{ fontSize: 10, color: "var(--z-muted)" }}>click an ID to open</span>
            </div>
            {/* Which list is on screen, stated rather than implied. */}
            <div style={{ fontSize: 10, color: "var(--z-muted)", marginBottom: 6, lineHeight: 1.45 }}>
              {cit.basis === "promoted"
                ? (subcap
                    ? "The ids the producer cited for this cell (heatmap.cell_evidence)."
                    : `The ids cited by the ${cit.withLists} cell${cit.withLists === 1 ? "" : "s"} in this category that promoted a citation list.`)
                : `The run promoted no citation list for this ${subcap ? "cell" : "category"}; these are the evidence items the run links to ${subcap ? "it" : "its cells"}.`}
            </div>
            {linkedEv.length === 0 ? (() => {
              /* ── The copy has to match the record ─────────────────────────
                 This box read "No evidence item directly cites this subcap in
                 this run — the score is inferred. Treat as provisional until
                 corroborated." on 456 of the 705 cell drawers. On 456 of those
                 456 the cell's own `provenance` is `declared`: a RECORDED
                 ABSENCE that names the artefact which would settle the cell,
                 lists the rungs the run searched for it and states the
                 condition that would close it. A worked absence is the
                 opposite of an inference. Telling a client the score was
                 inferred where the run did the search and found nothing
                 citable both understates the work and misdescribes the record
                 — and it is the one sentence a reader would quote back.

                 Only 24 cells on this run are genuinely `inherited`, and that
                 is where "inferred · provisional" belongs. Where the producer
                 wrote a provenance SENTENCE rather than one of the two tokens,
                 that sentence renders as written: it is their own account of
                 how the cell came by its reading, and no paraphrase of it here
                 could be more accurate.

                 The ladder renders with it. The section's own empty_state
                 promises the reader "the cell, the artefact that would settle
                 it, and the ladder that was run"; the first two arrived and
                 the third did not. */
              const cell = cit.cell || null;
              const prov = (cell && typeof cell.provenance === "string") ? cell.provenance.trim() : "";
              const token = prov.toLowerCase();
              const declared = token === "declared";
              const inherited = token === "inherited";
              const what = subcap ? "cell" : "category";
              const searched = (cell && Array.isArray(cell.sources_searched)) ? cell.sources_searched : [];
              return (
                <div className={`co ${inherited ? "co-org" : "co-purple"}`} style={{ marginBottom: 0 }}>
                  <Icon name={inherited ? "warn" : "search"} size={13} className="co-icon" />
                  <div className="co-body">
                    <div>
                      {declared
                        ? `No evidence item in this run carries a quotable span at this ${what}'s own grain. The absence is recorded rather than assumed — the run names the artefact that would settle it, and the searches it ran for that artefact are below.`
                        : inherited
                          ? `No evidence item directly cites this ${what} in this run. The reading is carried across from a neighbouring ${what} and is labelled an inference — treat it as provisional until corroborated.`
                          : prov
                            ? prov
                            : `No evidence item directly cites this ${what} in this run, and the run states no provenance for the reading.`}
                    </div>
                    {cell && cell.reach_note ? (
                      <div style={{ marginTop: 6, opacity: .88 }}>{cell.reach_note}</div>
                    ) : null}
                    {searched.length ? (
                      <details style={{ marginTop: 6 }}>
                        <summary style={{ cursor: "pointer", color: "var(--z-dpur)", fontWeight: 600 }}>
                          {searched.length} source{searched.length === 1 ? "" : "s"} searched for it
                        </summary>
                        <ul style={{ margin: "6px 0 0 16px", padding: 0 }}>
                          {searched.map((s, i) => (
                            <li key={i} style={{ marginBottom: 4, lineHeight: 1.5 }}>{asText(s)}</li>
                          ))}
                        </ul>
                      </details>
                    ) : null}
                  </div>
                </div>
              );
            })() : linkedEv.map(e => {
              // A cited id that resolves to nothing in the evidence store is
              // shown as unresolved, not dropped: a dangling citation is a
              // finding, and silently omitting it hides it.
              if (!e.resolved) {
                return (
                  <div key={e.id} className="card-tile" style={{ width: "100%", padding: 11, marginBottom: 6 }}>
                    <div className="row" style={{ gap: 6 }}>
                      <span className="chip">{e.id}</span>
                      <span className="b b-org">UNRESOLVED</span>
                    </div>
                    <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 4 }}>Cited for this cell but not present in this run's evidence store.</div>
                  </div>
                );
              }
              const tier = DMA.getTier(e.tier);
              // title and source_pretty are both `source_name` for most rows,
              // so printing both repeats the string. When they agree, the LINK
              // carries the url instead — which is the one thing on this row
              // the title cannot say.
              const showSource = e.source_pretty && e.source_pretty !== e.title;
              const linkText = showSource ? e.source_pretty : (e.source || e.source_pretty);
              return (
                <div key={e.id} style={{ marginBottom: 6 }}>
                  <button className="card-tile clickable" style={{ width: "100%", padding: 11, textAlign: "left" }} onClick={() => openEvidence(e.id)}>
                    <div className="row" style={{ marginBottom: 4, gap: 6 }}>
                      <span className={`tier-chip tier-${e.tier}`}>{e.id}</span>
                      <span className="b b-muted" title={tier?.label}>{[e.tier, e.claim].filter(Boolean).join(" · ")}</span>
                      <span className="spacer" />
                      <span style={{ fontSize: 10, color: "var(--z-muted)" }}>{e.recency}</span>
                    </div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--z-dark)" }} className="txt-fit-1">{e.title}</div>
                    {/* An item with no verbatim span is a citation of nothing.
                        It renders as a stated absence rather than as blank
                        space, the same way the evidence drawer does — a reader
                        who cannot tell "no quote" from "no excerpt field" has
                        no way to ask for the right thing. */}
                    {e.excerpt
                      ? <div style={{ fontSize: 11, color: "var(--z-body)", lineHeight: 1.5, marginTop: 6, paddingLeft: 8, borderLeft: "2px solid var(--z-sep)", fontStyle: "italic" }}>“{e.excerpt}”</div>
                      : <div style={{ fontSize: 10.5, color: "var(--z-muted)", lineHeight: 1.45, marginTop: 6, paddingLeft: 8, borderLeft: "2px dashed var(--z-sep)" }}>No verbatim excerpt is served for this item.</div>}
                  </button>
                  {/* THE SOURCE URL, and it is outside the button on purpose:
                      an anchor nested in a button is invalid markup that
                      browsers flatten, so the row could never have carried a
                      working link while it was one element. Every evidence row
                      on this page was reported as having no url; the url was in
                      the store and in the projection the whole time, and only
                      the evidence DRAWER rendered it. */}
                  <div className="row" style={{ gap: 5, marginTop: 3, paddingLeft: 11 }}>
                    <Icon name={e.source ? "external" : "drive"} size={10} style={{ color: "var(--z-muted)" }} />
                    {/* HOW BROADLY THIS ITEM IS LINKED, stated on the row. An
                        item the assessment attached to 21 cells is not about
                        this one, and a reader who cannot see that reads it as
                        though it were. The list is ordered so the narrowest
                        citable item is first; this says what the order means. */}
                    {(e.subcaps || []).length > 3 ? (
                      <span style={{ fontSize: 9.5, color: "var(--z-muted)", whiteSpace: "nowrap" }}
                            title={`This source is linked to ${e.subcaps.length} cells in this run`}>
                        {e.subcaps.length} cells ·
                      </span>
                    ) : null}
                    {e.source ? (
                      <a href={`https://${e.source}`} target="_blank" rel="noreferrer"
                         style={{ fontSize: 10.5, color: "var(--z-mid)", fontWeight: 500, textDecoration: "none" }}
                         className="txt-fit-1" title={`https://${e.source}`}>{linkText}</a>
                    ) : (
                      <span style={{ fontSize: 10.5, color: "var(--z-muted)" }} className="txt-fit-1">
                        {showSource ? `${e.source_pretty} — no source url served` : "no source url served"}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Linked insight cards */}
          {linkedIC.length > 0 ? (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>Linked insight cards · {linkedIC.length}</div>
              {linkedIC.map(ic => (
                <button key={ic.id} className="card-tile clickable" style={{ width: "100%", padding: 11, marginBottom: 6, textAlign: "left" }} onClick={() => openInsight(ic.id)}>
                  <div className="row" style={{ marginBottom: 4 }}>
                    <span className="ic-id">{ic.id}</span>
                    <span className={`b ${ic.flag === "CRITICAL" ? "b-below" : ic.flag === "OPPORTUNITY" ? "b-org" : "b-teal"}`}>{ic.flag}</span>
                  </div>
                  <div style={{ fontSize: 12.5, fontWeight: 600 }} className="txt-fit-1">{ic.title}</div>
                </button>
              ))}
            </div>
          ) : null}

          {/* The CELL's promoted synthesis.
              This card was labelled "AI SYNTHESIS · on the N items above" and
              printed one of three client-side template strings chosen by the
              gap — including "At or above peer median. No platform investment
              needed for this subcap specifically" on every cell whose peer
              figure was null, i.e. all 765. The app runs no model and writes no
              prose (invariant 1); what belongs here is what the producer wrote
              for this cell, or an honest absence. */}
          {subcap ? (() => {
            const cell = DMA.cellEvidenceFor(subcap.id);
            const body = cell && (cell.synthesis || cell.narrative || cell.rationale);
            return (
              <div className="card-tile" style={{ marginBottom: 4, background: "var(--ph0-lt)", border: "1px solid var(--ph0-bd)", padding: 12 }}>
                <div className="row" style={{ marginBottom: 6, gap: 6 }}>
                  <Icon name="evidence" size={13} style={{ color: "var(--z-dpur)" }} />
                  <span style={{ fontSize: 11, fontWeight: 700, color: "var(--z-dpur)", letterSpacing: ".08em", textTransform: "uppercase" }}>Cell synthesis</span>
                  <span className="spacer" />
                  {cell && (cell.e_ids || []).length ? (
                    <span style={{ fontSize: 9.5, color: "var(--z-dpur)", opacity: .85 }}>{cell.e_ids.length} cited</span>
                  ) : null}
                </div>
                <div style={{ fontSize: 12.5, color: "#3B0764", lineHeight: 1.6 }}>
                  {body ? body
                    : subcap.thin
                      ? `Evidence is thin (${subcap.evidence_count} of 3). The workbook score stands and the cell carries a dashed outline; the run did not write a synthesis for it.`
                      : "The run promoted no synthesis for this cell."}
                </div>
                {cell && (cell.closure_condition) ? (
                  <div style={{ fontSize: 11, color: "var(--z-dpur)", marginTop: 6 }}>
                    Closes on: {cell.closure_condition}
                  </div>
                ) : null}
              </div>
            );
          })() : null}
        </div>
        <div className="drawer-foot">
          {subcap ? <button className="btn btn-tertiary" onClick={() => {
            // Only what the run states. This used to copy "peer median —" for
            // every cell, which reads as a stated median of nothing.
            const bits = [
              subcap.score != null ? `Score ${fx(subcap.score, 1)}` : "no score stated",
              subcap.confidence ? `confidence ${subcap.confidence}` : null,
              subcap.peerMedian != null ? `peer median ${fx(subcap.peerMedian, 1)}`
                : (peerIsProxy ? `peer median ${fx(peer, 1)} (${catId} category proxy)` : "no peer median stated"),
            ].filter(Boolean);
            const text = `${subcap.name || subcap.id} (${subcap.id})\n${bits.join(" · ")}.`;
            try { navigator.clipboard.writeText(text); } catch (e) {}
          }}><Icon name="copy" size={13} /> Copy synthesis</button> : <span />}
          <button className="btn btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </>
  );
}

function IssueRegisterBanner({ entity, onSubcap, openEvidence }) {
  /* Every promoted issue, with its promoted status printed. This filtered on
     `status === "OPEN"` — a value the register does not use (this run states
     ACTIVE, NEW OBLIGATION and REMEDIATED) — so the whole banner vanished while
     the cells beneath it carried issue markers, and the page contradicted
     itself. Classifying a promoted status as open or closed is a judgement the
     run has not made, so the row shows what it says. */
  const issues = DMA.ISSUES || [];
  const [open, setOpen] = useState(null);
  if (issues.length === 0) return null;
  return (
    <div className="card" style={{ marginBottom: 12, padding: 14, background: "rgba(254,151,50,.06)", border: "1px solid rgba(254,151,50,.28)" }}>
      <div className="row" style={{ marginBottom: 10 }}>
        <Icon name="warn" size={14} style={{ color: "var(--z-org)" }} />
        <strong style={{ fontSize: 13, color: "var(--z-dark)" }}>Issue register · {issues.length} issue{issues.length === 1 ? "" : "s"}</strong>
        <span className="b b-muted">click an issue to drill in</span>
        <span className="spacer" />
        <a href={`#/clients/${entity.id}/context`} style={{ fontSize: 11, color: "var(--z-mid)", fontWeight: 600 }}>Full register →</a>
      </div>
      <div className="g2" style={{ gap: 8 }}>
        {issues.map(iss => {
          const caps = Object.entries(DMA.ISSUE_CAPS[iss.id]?.caps || {});
          const capped = caps.filter(([, cap]) => cap != null).length;
          const isOpen = open === iss.id;
          // Evidence for the CAPPED cells. Matching on a 4-char prefix meant
          // "anything citing any cell in the same category", so an item that has
          // nothing to do with the issue was listed as its evidence.
          const cappedIds = new Set(caps.map(([cid]) => cid));
          const ev = DMA.EVIDENCE.filter(e => e.subcaps && e.subcaps.some(sid => cappedIds.has(sid)));
          return (
            <div key={iss.id} className="card-tile" style={{ padding: 0, background: "#fff", gridColumn: isOpen ? "1 / -1" : "auto", overflow: "hidden" }}>
              <button onClick={() => setOpen(o => o === iss.id ? null : iss.id)} style={{ width: "100%", background: "none", border: 0, cursor: "pointer", textAlign: "left", padding: 10 }}>
                <div className="row" style={{ marginBottom: 6, gap: 6 }}>
                  <span className="chip">{iss.id}</span>
                  {iss.title || iss.type ? <span className="b b-muted txt-fit-1">{iss.title || iss.type}</span> : null}
                  {iss.severity ? <span className={`b ${iss.severity === "CRITICAL" ? "b-below" : iss.severity === "MATERIAL" ? "b-org" : "b-muted"}`}>{iss.severity}</span> : null}
                  <span className="spacer" />
                  {/* "caps N" claimed a maturity ceiling for every linked cell.
                      The register links cells; it states a cap level only
                      sometimes, and for this run never. Lock and the word cap
                      appear only where a level is stated. */}
                  {capped ? <Icon name="lock" size={11} style={{ color: "var(--z-org)" }} /> : null}
                  <span style={{ fontSize: 10, color: "var(--z-muted)" }}>
                    {capped ? `caps ${capped}` : `${caps.length} cell${caps.length === 1 ? "" : "s"} linked`}
                  </span>
                  <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={13} style={{ color: "var(--z-muted)" }} />
                </div>
                <div style={{ fontSize: 12, color: "var(--z-dark)", lineHeight: 1.5 }} className={isOpen ? "" : "txt-fit-2"}>{iss.desc}</div>
              </button>
              {isOpen ? (
                <div style={{ padding: "0 10px 10px" }}>
                  {/* Each fact only when the register states it: "Cap M" with a
                      null level printed "Cap Mundefined", and an undated issue
                      printed "Since null". */}
                  <div className="row" style={{ gap: 12, fontSize: 11, color: "var(--z-muted)", marginBottom: 8, flexWrap: "wrap" }}>
                    {iss.status ? <span>Status <strong style={{ color: "var(--z-org)" }}>{iss.status}</strong></span> : null}
                    {iss.cap_value != null ? <span>Cap <strong style={{ color: "var(--z-dark)" }}>M{iss.cap_value}</strong></span> : <span>no cap level stated</span>}
                    {iss.start ? <span>Since <strong style={{ color: "var(--z-dark)" }}>{iss.start}</strong></span> : <span>undated</span>}
                    {iss.end ? <span>Resolved {iss.end}</span> : null}
                  </div>
                  {caps.length ? (
                    <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 4 }}>
                      {capped ? "Capped subcaps · click to drill" : "Subcaps linked to this issue · click to drill"}
                    </div>
                  ) : null}
                  <div className="row" style={{ flexWrap: "wrap", gap: 4, marginBottom: ev.length ? 10 : 0 }}>
                    {caps.map(([sid, cap]) => {
                      const subcap = entity.subcaps.find(s => s.id === sid);
                      return (
                        <button key={sid} className="chip purple" onClick={() => subcap && onSubcap(subcap)}
                          title={`${subcap?.name || sid}${cap != null ? ` · capped at M${cap}` : " · linked; no cap level stated"}`}>
                          {sid}{cap != null ? ` · M${cap}` : ""}{subcap ? ` · ${subcap.name}` : ""}
                        </button>
                      );
                    })}
                  </div>
                  {ev.length ? (
                    <>
                      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 4 }}>Evidence · click to open</div>
                      <div className="row" style={{ flexWrap: "wrap", gap: 4 }}>
                        {ev.map(e => <button key={e.id} className={`tier-chip tier-${e.tier}`} style={{ cursor: "pointer", border: 0 }} title={`${e.title} · ${e.source_pretty}`} onClick={() => openEvidence && openEvidence(e.id)}>{e.id}</button>)}
                      </div>
                    </>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="row-wrap" style={{ fontSize: 10.5, color: "var(--z-muted)", gap: 8 }}>
      {[["b-act","M1"],["b-bld","M2"],["b-cmp","M3"],["b-dif","M4+"]].map(([c, l]) => (
        <span key={c} className="row" style={{ gap: 4 }}><span className={`b ${c}`} style={{ width: 12, height: 12, padding: 0, borderRadius: 3 }}></span>{l}</span>
      ))}
      <span className="row" style={{ gap: 4 }}><span style={{ width: 12, height: 12, border: "2px dashed var(--z-org)", borderRadius: 3 }}></span> Thin</span>
      <span className="row" style={{ gap: 4 }}><Icon name="lock" size={10} /> Capped</span>
    </div>
  );
}

function hashCode(s) { let h = 0; for (let i = 0; i < s.length; i++) h = ((h << 5) - h) + s.charCodeAt(i); return h; }
window.hashCode = hashCode;

Object.assign(window, { ClientHeatmap, sectionReason });
