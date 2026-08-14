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
  const v = median === null || median === undefined || median === "" ? null : Number(median);
  return {
    median: v === null || !isFinite(v) ? null : v,
    basis: basis || null
  };
}

/* The mean of the peer medians that EXIST, or null when none do. Never treats a
   missing value as zero and never divides by the full count. */
function peerMeanOf(rows) {
  const vals = (rows || []).map(r => r && r.peerMedian !== null && r.peerMedian !== undefined ? Number(r.peerMedian) : null).filter(v => v !== null && isFinite(v));
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
  const name = s.name && s.name !== s.id ? s.name : "unnamed in catalogue";
  return `${s.id} — ${name} · ${s.score != null ? fx(s.score, 1) : "no score"}`;
}
function useCellTip() {
  const [tip, setTip] = useState(null);
  // One state write on enter, one on leave. The label is computed by the
  // caller at render time, so hovering re-renders nothing but the bubble.
  const show = label => e => {
    const r = e.currentTarget.getBoundingClientRect();
    setTip({
      label,
      x: r.left + r.width / 2,
      top: r.top,
      bottom: r.bottom,
      flip: r.top < 64
    });
  };
  const hide = () => setTip(null);
  return {
    tip,
    show,
    hide
  };
}
function CellTip({
  tip
}) {
  if (!tip) return null;
  const vw = typeof window !== "undefined" && window.innerWidth || 1024;
  // Keep the bubble on-screen: clamp its centre so a cell at either edge
  // still reads in full.
  const x = Math.min(Math.max(tip.x, 132), Math.max(vw - 132, 132));
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: "fixed",
      left: x,
      top: tip.flip ? tip.bottom + 7 : tip.top - 7,
      transform: tip.flip ? "translate(-50%, 0)" : "translate(-50%, -100%)",
      maxWidth: 248,
      padding: "5px 9px",
      borderRadius: 6,
      background: "var(--z-dark)",
      color: "#fff",
      fontSize: 11,
      lineHeight: 1.45,
      textAlign: "left",
      pointerEvents: "none",
      zIndex: 120,
      boxShadow: "0 2px 10px rgba(0,0,0,.28)"
    }
  }, tip.label);
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
  const reg = typeof window !== "undefined" && window.DMA_ENTITY || null;
  return reg && reg.workbookScores || null;
}

/* The contract allows either shape for the workbook tables: an id-keyed object
   ({"P1C1": {score…}}, which is what the API sends) or a list of rows carrying
   their own id. Both become a list of rows with `id`. */
function promotedRowsOf(table, idKey) {
  if (!table) return [];
  if (Array.isArray(table)) {
    return table.map(r => ({
      ...r,
      id: r[idKey] || r.id || null
    })).filter(r => r.id);
  }
  return Object.keys(table).map(k => ({
    ...table[k],
    id: k
  }));
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
    rows[r.id] = {
      id: r.id,
      score: numOf(r.score),
      peer: numOf(r.peer_median),
      band: r.band || null,
      source_cell: r.source_cell || null,
      promoted: true
    };
  }
  const cells = Array.isArray(entity && entity.subcaps) ? entity.subcaps : [];
  for (const s of cells) {
    if (s.category && !rows[s.category]) {
      rows[s.category] = {
        id: s.category,
        score: null,
        peer: null,
        band: null,
        source_cell: null,
        promoted: false
      };
    }
  }
  return Object.keys(rows).sort().map(id => {
    const cat = DMA.getCategory(id) || null;
    const mine = cells.filter(s => s.category === id);
    return {
      ...rows[id],
      // The pillar comes from the id itself when the catalogue cannot answer —
      // deterministic, not inferred.
      pillar: cat && cat.pillar || id.slice(0, 2),
      name: cat && cat.name || null,
      inCatalogue: !!cat,
      weight: cat && cat.weight != null ? Number(cat.weight) : null,
      cells: mine,
      thin: mine.filter(s => s.thin).length,
      // Only used where the run promoted no category score; labelled as a mean
      // wherever it renders, so it is never mistaken for the workbook's figure.
      cellMean: meanOf(mine.map(s => s.score))
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
    const overview = (entity && entity.pillar_scores || {})[id];
    const overviewPeer = (entity && entity.pillar_peer_medians || {})[id];
    return {
      id,
      name: meta && meta.name || null,
      short: meta && meta.short || null,
      inCatalogue: !!meta,
      score: numOf(overview) != null ? numOf(overview) : numOf(promoted[id] && promoted[id].score),
      peer: numOf(overviewPeer) != null ? numOf(overviewPeer) : numOf(promoted[id] && promoted[id].peer_median),
      cats: mine,
      // Summed from the columns the grid actually draws, so the header count
      // cannot disagree with them again.
      cellCount: mine.reduce((a, c) => a + c.cells.length, 0),
      thin: mine.reduce((a, c) => a + c.thin, 0)
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
  const cell = typeof DMA.cellEvidenceFor === "function" ? DMA.cellEvidenceFor(subcapId) : null;
  const ids = cell && Array.isArray(cell.e_ids) ? cell.e_ids : [];
  if (ids.length) {
    return {
      basis: "promoted",
      cell,
      items: ids.map(id => {
        const e = DMA.getEvidence(id) || null;
        return e ? {
          ...e,
          resolved: true
        } : {
          id,
          resolved: false
        };
      })
    };
  }
  return {
    basis: "derived",
    cell,
    items: (DMA.EVIDENCE || []).filter(e => e.subcaps && e.subcaps.includes(subcapId)).map(e => ({
      ...e,
      resolved: true
    }))
  };
}

/* The number of evidence items behind a cell, and where the number came from.
   The row used to count `DMA.EVIDENCE` rows that list the cell, which is why
   all 43 cells of P4C1 read "5 evidence" — the link table is coarser than the
   citation lists. `grounded_on` is the promoted length (invariant 8: it is the
   length of the citation list, not a stored number to be re-derived). */
function evidenceCountOf(subcap) {
  const cell = typeof DMA.cellEvidenceFor === "function" ? DMA.cellEvidenceFor(subcap.id) : null;
  const ids = cell && Array.isArray(cell.e_ids) ? cell.e_ids : null;
  if (ids && ids.length) return {
    n: ids.length,
    basis: "cited"
  };
  if (subcap.evidence_count != null) return {
    n: subcap.evidence_count,
    basis: "linked"
  };
  return {
    n: null,
    basis: null
  };
}
function ClientHeatmap({
  entity,
  run
}) {
  const route = useRoute();
  const {
    audience,
    openEvidence,
    openInsight,
    setIpSurface,
    setIpContext,
    tweaks,
    pushToast
  } = useApp();
  // Order and default, per the build owner 2026-08-14: the STANDARD heatmap
  // opens the page, then focus areas, then the value chain. The customer
  // audience still cannot reach the standard grid (it carries every capped and
  // thin cell), so it opens on focus areas — the ternary that used to return
  // "focus" on both branches now actually branches.
  const [mode, setMode] = useState(route.params.hm || (audience === "customer" ? "focus" : "standard")); // standard | focus | value_chain
  const [zoom, setZoom] = useState(route.params.zoom || "category");
  const [pillarFocus, setPillarFocus] = useState(route.params.pillar || null);
  const [catFocus, setCatFocus] = useState(route.params.cat || null);
  const [showPeers, setShowPeers] = useState(true);
  const [showIssues, setShowIssues] = useState(false);
  const [focusArea, setFocusArea] = useState(null);
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
  useEffect(() => {
    const sid = route.params.subcap;
    if (!sid) return;
    const s = (entity.subcaps || []).find(x => x.id === sid);
    if (s) setSynthSubcap({
      kind: "subcap",
      subcap: s
    });
  }, [route.params.subcap, entity?.id]);

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
  const subcapsForFocusArea = fa => {
    if (!fa || !Array.isArray(entity.subcaps)) return [];
    const named = new Set(fa.subcaps || []);
    if (!named.size) return [];
    const exact = entity.subcaps.filter(s => named.has(s.id));
    if (exact.length) return exact;
    // Some packages name a capability (P4C1.2) where the grid holds its
    // sub-capabilities (P4C1.2.1…): widen to descendants of a named id.
    return entity.subcaps.filter(s => [...named].some(n => typeof n === "string" && s.id.startsWith(`${n}.`)));
  };
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "page-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, "Maturity heatmap"), /*#__PURE__*/React.createElement("h1", null, "Where ", entity.name, " is today"), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, entity.subcaps.length, " subcaps \xB7 ", entity.subcaps.filter(s => s.thin).length, " thin", overallLabel ? ` · overall maturity ${overallLabel.toLowerCase()}` : " · no overall score promoted")), /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast(`Exporting ${entity.name} heatmap as PDF…`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Export"))), /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 14,
      padding: "12px 16px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      flexWrap: "wrap",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".08em"
    }
  }, "View"), /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, /*#__PURE__*/React.createElement("button", {
    className: mode === "standard" ? "on" : "",
    disabled: audience === "customer",
    title: audience === "customer" ? "the full internal grid is not part of the customer view" : null,
    style: audience === "customer" ? {
      opacity: .45,
      cursor: "not-allowed"
    } : null,
    onClick: () => {
      if (audience !== "customer") setMode("standard");
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "heatmap",
    size: 11
  }), " Standard"), /*#__PURE__*/React.createElement("button", {
    className: mode === "focus" ? "on" : "",
    onClick: () => {
      setMode("focus");
      setFocusArea(null);
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "sparkle",
    size: 11
  }), " Focus areas"), /*#__PURE__*/React.createElement("button", {
    className: mode === "value_chain" ? "on" : "",
    onClick: () => setMode("value_chain")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "route",
    size: 11
  }), " Value chain"))), /*#__PURE__*/React.createElement("span", {
    style: {
      width: 1,
      height: 22,
      background: "var(--z-sep)"
    }
  }), mode === "standard" ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".08em"
    }
  }, "Zoom"), /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, ["pillar", "category", "capability", "subcap"].map(z => /*#__PURE__*/React.createElement("button", {
    key: z,
    className: zoom === z ? "on" : "",
    onClick: () => setZoom(z)
  }, z[0].toUpperCase() + z.slice(1))))) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("label", {
    className: "row",
    style: {
      fontSize: 11.5,
      cursor: "pointer"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `switch ${showPeers ? "on" : ""}`,
    onClick: () => setShowPeers(p => !p)
  }), "Peers"), /*#__PURE__*/React.createElement("label", {
    className: "row",
    style: {
      fontSize: 11.5,
      cursor: "pointer"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `switch ${showIssues ? "on" : ""}`,
    onClick: () => setShowIssues(p => !p)
  }), "Issues"), /*#__PURE__*/React.createElement(Legend, null)), (pillarFocus || catFocus) && mode === "standard" ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 10,
      fontSize: 12,
      color: "var(--z-body)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, "Drilling:"), pillarFocus ? /*#__PURE__*/React.createElement("span", {
    className: "chip purple"
  }, pillarFocus) : null, catFocus ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-r",
    size: 11
  }), /*#__PURE__*/React.createElement("span", {
    className: "chip"
  }, catFocus)) : null, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => {
      setPillarFocus(null);
      setCatFocus(null);
      setZoom("category");
    }
  }, "Reset")) : null), mode === "focus" ? /*#__PURE__*/React.createElement(FocusAreaView, {
    entity: entity,
    run: run,
    focusArea: focusArea,
    setFocusArea: setFocusArea,
    subcapsForFocusArea: subcapsForFocusArea,
    openSubcap: setSynthSubcap,
    openEvidence: openEvidence,
    openInsight: openInsight,
    audience: audience,
    showIssues: showIssues
  }) : mode === "value_chain" ? /*#__PURE__*/React.createElement(ValueChainView, {
    entity: entity,
    subcapsForFocusArea: subcapsForFocusArea,
    openSubcap: setSynthSubcap,
    openInsight: openInsight
  }) : /*#__PURE__*/React.createElement(React.Fragment, null, showIssues ? /*#__PURE__*/React.createElement(IssueRegisterBanner, {
    entity: entity,
    onSubcap: s => setSynthSubcap({
      kind: "subcap",
      subcap: s
    }),
    openEvidence: openEvidence
  }) : null, zoom === "pillar" ? /*#__PURE__*/React.createElement(PillarHeatmap, {
    entity: entity,
    pillars: pillars,
    audience: audience,
    setPillarFocus: p => {
      setPillarFocus(p);
      setZoom("category");
    }
  }) : zoom === "category" ? /*#__PURE__*/React.createElement(CategoryHeatmap, {
    entity: entity,
    pillars: pillars,
    pillarFocus: pillarFocus,
    showPeers: showPeers,
    showIssues: showIssues,
    audience: audience,
    setCatFocus: c => {
      setCatFocus(c);
      setZoom("capability");
    },
    onSynth: catId => {
      setSynthSubcap({
        kind: "category",
        catId
      });
    }
  }) : zoom === "capability" ?
  /*#__PURE__*/
  /* Its own grain. The button used to set zoom to "capability" and
     fall through to the subcap branch, so it produced DOM identical
     to "Subcap" — a control that did nothing. */
  React.createElement(CapabilityHeatmap, {
    entity: entity,
    cats: cats,
    catFocus: catFocus,
    pillarFocus: pillarFocus,
    showIssues: showIssues,
    audience: audience,
    drillCategory: c => {
      setCatFocus(c);
      setZoom("subcap");
    }
  }) : /*#__PURE__*/React.createElement(SubcapHeatmap, {
    entity: entity,
    cats: cats,
    catFocus: catFocus,
    pillarFocus: pillarFocus,
    showPeers: showPeers,
    showIssues: showIssues,
    audience: audience,
    setCatFocus: setCatFocus,
    onSynth: s => setSynthSubcap({
      kind: "subcap",
      subcap: s
    })
  })), synthSubcap ? /*#__PURE__*/React.createElement(SynthesisDrawer, {
    entity: entity,
    item: synthSubcap,
    onClose: () => setSynthSubcap(null),
    openEvidence: openEvidence,
    openInsight: openInsight,
    showIssues: showIssues,
    audience: audience
  }) : null);
}

/* ─────────────────────── FOCUS AREA VIEW ─────────────────────── */
function FocusAreaView({
  entity,
  run,
  focusArea,
  setFocusArea,
  subcapsForFocusArea,
  openSubcap,
  openEvidence,
  openInsight,
  audience
}) {
  // Hover identification for the score-only cell grid in the detail branch.
  // Called before the early return — hooks cannot be conditional.
  const cellTip = useCellTip();
  if (!focusArea) {
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 12
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "sparkle",
      size: 15,
      style: {
        color: "var(--z-dpur)"
      }
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, "Strategic priorities for ", entity.name), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, "Click any focus area to drill in")), /*#__PURE__*/React.createElement("div", {
      className: "g3"
    }, DMA.FOCUS_AREAS.map(fa => {
      const subs = subcapsForFocusArea(fa);
      // The focus area's own promoted figures first (peer_score/delta are
      // in the H1 contract and were unread), then the mean of the cells it
      // names, then nothing. No 2.5/2.8 fallbacks: a hardcoded average is
      // a claim about this client.
      // `entity_score` is the producer's own figure for this focus area
      // (H1 contract) and it is not the mean of the cells: FA-1 promotes
      // 1.95 where its 43 cells average 2.0. Read it; the mean only
      // stands in when the run states none.
      const avg = numOf(fa.entity_score) != null ? numOf(fa.entity_score) : meanOf(subs.map(s => s.score));
      const peer = fa.peer_score != null ? Number(fa.peer_score) : peerMeanOf(subs);
      const gap = fa.delta != null ? -Number(fa.delta) : deltaOf(peer, avg);
      return /*#__PURE__*/React.createElement("div", {
        key: fa.id,
        className: "fa-card",
        onClick: () => setFocusArea(fa)
      }, /*#__PURE__*/React.createElement("div", {
        className: "fa-illo",
        style: {
          height: 116,
          background: `linear-gradient(135deg, ${fa.colors[0]}, ${fa.colors[1]})`
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "icon-block"
      }, /*#__PURE__*/React.createElement(Icon, {
        name: fa.icon,
        size: 16
      })), /*#__PURE__*/React.createElement("div", {
        className: "title-block"
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 13,
          fontWeight: 700,
          lineHeight: 1.35
        },
        className: "txt-fit-2",
        title: fa.name
      }, fa.name), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10.5,
          opacity: .92
        }
      }, subs.length, " subcaps"))), /*#__PURE__*/React.createElement("div", {
        className: "fa-meta"
      }, /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          marginBottom: 8
        }
      }, avg != null ? /*#__PURE__*/React.createElement(MaturityChip, {
        score: avg
      }) : /*#__PURE__*/React.createElement("span", {
        className: "b b-muted"
      }, "no score"), peer != null ? /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 11,
          color: "var(--z-muted)"
        }
      }, "Peer ", fx(peer, 1)) :
      /*#__PURE__*/
      /* No stated median at focus-area grain is a routable
         gap, not a dash. Compact: this row already carries a
         maturity chip and a delta badge inside a three-up
         card, and the queue badge would push the delta out. */
      React.createElement("span", {
        style: {
          fontSize: 11,
          color: "var(--z-muted)"
        },
        title: "no peer median is stated at this grain in this run"
      }, /*#__PURE__*/React.createElement(EnrichmentGap, {
        what: `${fa.id} peer median`,
        audience: audience,
        compact: true
      })), gap == null ? null : gap > 0 ? /*#__PURE__*/React.createElement("span", {
        className: "b b-below",
        style: {
          marginLeft: "auto"
        }
      }, "\u2212", fx(gap, 1)) : gap < 0 ? /*#__PURE__*/React.createElement("span", {
        className: "b b-above",
        style: {
          marginLeft: "auto"
        }
      }, "+", fx(Math.abs(gap), 1)) : /*#__PURE__*/React.createElement("span", {
        className: "b b-muted",
        style: {
          marginLeft: "auto"
        }
      }, "0.0")), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 12,
          color: "var(--z-body)",
          lineHeight: 1.5
        },
        className: "txt-fit-2"
      }, fa.description)));
    })));
  }

  // Selected focus area detail
  const fa = focusArea;
  const subs = subcapsForFocusArea(fa);
  const avg = numOf(fa.entity_score) != null ? numOf(fa.entity_score) : meanOf(subs.map(s => s.score));
  const peer = fa.peer_score != null ? Number(fa.peer_score) : peerMeanOf(subs);
  // Cards this focus area's OWN cells are affected by. Matching on a 4-char
  // prefix meant "anything in the same category", so a card about a cell this
  // focus area never names was listed under it — the same fabricated linkage
  // the cell list already had fixed.
  const named = new Set(fa.subcaps || []);
  const insights = DMA.INSIGHT_CARDS.filter(ic => (ic.affects || []).some(sid => named.has(sid) || [...named].some(n => typeof n === "string" && sid.startsWith(`${n}.`))));
  // Each fragment of the source line only exists when its value does: a null
  // page printed " · p. · " and a focus area carries no financial reference at
  // all, so the label sat there with nothing after it.
  const srcBits = [fa.source && fa.source.type, fa.source && fa.source.page ? `p.${fa.source.page}` : null, fa.source && fa.source.doc].filter(Boolean);
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      padding: "22px 24px",
      background: `linear-gradient(135deg, ${fa.colors[0]}10, ${fa.colors[1]}1a)`,
      borderBottom: "1px solid var(--z-sep)",
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: assetUrl("illo_curvesTR", "brand/illustrations/curves_topright.png"),
    alt: "",
    style: {
      position: "absolute",
      right: -60,
      top: -40,
      width: 360,
      height: "auto",
      opacity: .55,
      pointerEvents: "none"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      display: "flex",
      justifyContent: "space-between",
      alignItems: "flex-start",
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0,
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => setFocusArea(null),
    className: "row",
    style: {
      fontSize: 11.5,
      color: "var(--z-mid)",
      background: "transparent",
      padding: "4px 8px 4px 0",
      border: 0,
      marginBottom: 8,
      cursor: "pointer"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-l",
    size: 12
  }), " All focus areas"), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 36,
      height: 36,
      borderRadius: 9,
      background: fa.colors[0],
      color: "#fff",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: fa.icon,
    size: 18
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 6,
      marginBottom: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, "FOCUS AREA \xB7 ", fa.id), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)"
    }
  }, subs.length, " subcaps")), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 22,
      fontWeight: 600,
      color: "var(--z-dark)",
      letterSpacing: "-.015em"
    }
  }, fa.name))), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      color: "var(--z-body)",
      lineHeight: 1.5,
      maxWidth: 640
    }
  }, fa.description)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 16,
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(ScoreRing, {
    score: avg,
    size: 88
  })))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "14px 20px",
      background: "var(--z-bg)",
      display: "flex",
      gap: 14,
      alignItems: "flex-start",
      borderBottom: "1px solid var(--z-sep)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "doc",
    size: 16,
    style: {
      color: "var(--z-dpur)",
      flexShrink: 0,
      marginTop: 2
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, "SOURCE"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      minWidth: 0,
      overflowWrap: "anywhere"
    }
  }, srcBits.length ? srcBits.join(" · ") : "the run states no source for this focus area")), fa.strategic_quote ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      color: "var(--z-dark)",
      fontStyle: "italic",
      lineHeight: 1.55
    }
  }, "\"", String(fa.strategic_quote).replace(/[“”]/g, ""), "\"") : null, fa.financial_ref ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 5
    }
  }, "Financial reference: ", fa.financial_ref) : null))), /*#__PURE__*/React.createElement(CustomizableKpiStrip, {
    fa: fa,
    entity: entity
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "280px minmax(0, 1fr)",
      gap: 14,
      marginBottom: 14,
      alignItems: "start"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      marginBottom: 8
    }
  }, "Where its cells sit, by pillar"), !fa.pillars_weight || !Object.keys(fa.pillars_weight).length ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "No cells linked to this focus area.") : Object.entries(fa.pillars_weight).map(([p, w]) => /*#__PURE__*/React.createElement("div", {
    key: p,
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      fontSize: 11,
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "chip purple",
    style: {
      minWidth: 26,
      textAlign: "center"
    }
  }, p), /*#__PURE__*/React.createElement("div", {
    className: "prog",
    style: {
      flex: 1,
      height: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "prog-fill",
    style: {
      width: `${w}%`,
      background: DMA.helpers.maturityHex(entity.pillar_scores[p])
    }
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      width: 30,
      textAlign: "right"
    }
  }, w, "%"))), /*#__PURE__*/React.createElement("div", {
    className: "sep"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      lineHeight: 1.5
    }
  }, "Share of the ", (fa.subcaps || []).length, " cells this focus area names, per pillar. Bar fill is each pillar's own promoted maturity for ", entity.name, ".")), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "heatmap",
    size: 14
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "Subcap heatmap"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, subs.length, " cells \xB7 click any cell for synthesis")), /*#__PURE__*/React.createElement("div", {
    className: "hm",
    style: {
      gridTemplateColumns: `repeat(${Math.min(subs.length, 8)}, 1fr)`,
      gap: 5
    }
  }, subs.map(s =>
  /*#__PURE__*/
  /* The cell only carries its score and an id fragment — which
     subcap it IS took a click. Identified on hover: title attr +
     the grid's shared bubble (hidden on click so it cannot linger
     over the drawer that opens). */
  React.createElement("button", {
    key: s.id,
    onClick: () => {
      cellTip.hide();
      openSubcap({
        kind: "subcap",
        subcap: s
      });
    },
    className: `hm-cell b ${DMA.helpers.maturityClass(s.score)} ${s.thin ? "thin" : ""}`,
    title: subcapTipText(s),
    onMouseEnter: cellTip.show(subcapTipText(s)),
    onMouseLeave: cellTip.hide,
    style: {
      flexDirection: "column",
      height: 56,
      fontSize: 11,
      padding: 4,
      border: 0
    }
  }, s.score == null ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      fontWeight: 600
    }
  }, /*#__PURE__*/React.createElement(EnrichmentGap, {
    what: `${s.id} score`,
    audience: audience,
    compact: true
  })) : /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      fontWeight: 700
    }
  }, fx(s.score, 1)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 8.5,
      opacity: .85,
      fontFamily: "var(--font-mono)"
    }
  }, s.id.split(".").slice(1).join("."))))), /*#__PURE__*/React.createElement(CellTip, {
    tip: cellTip.tip
  }))), /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", null, "Insight cards in this focus area"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, insights.length, " cards")), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 14
    }
  }, insights.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 12
    }
  }, "No insight cards yet") : /*#__PURE__*/React.createElement("div", {
    className: "g2"
  }, insights.map(ic => /*#__PURE__*/React.createElement("div", {
    key: ic.id,
    className: `ic ${ic.flag.toLowerCase()}`,
    onClick: () => openInsight(ic.id)
  }, /*#__PURE__*/React.createElement("div", {
    className: "ic-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "ic-id"
  }, ic.id), /*#__PURE__*/React.createElement("span", {
    className: `b ${ic.flag === "CRITICAL" ? "b-below" : ic.flag === "OPPORTUNITY" ? "b-org" : "b-teal"}`
  }, ic.flag))), /*#__PURE__*/React.createElement("div", {
    className: "ic-title"
  }, ic.title), /*#__PURE__*/React.createElement("div", {
    className: "ic-body txt-fit-2"
  }, ic.what), /*#__PURE__*/React.createElement("div", {
    className: "ic-foot"
  }, ic.platforms.map(p => /*#__PURE__*/React.createElement("span", {
    key: p,
    className: "b b-teal"
  }, DMA.getPlatform(p)?.short)))))))));
}

/* ── Customisable KPI strip ─────────────────────────────────────── */
function CustomizableKpiStrip({
  fa,
  entity
}) {
  // Each KPI gets a "source mode": "public" (inferred from public DMA) or "client" (provided / awaiting client input) or "hidden"
  const kpis = fa && Array.isArray(fa.kpis) ? fa.kpis : [];
  const [modes, setModes] = useState(() => kpis.reduce((m, k) => {
    m[k.label] = "public";
    return m;
  }, {}));
  const [editing, setEditing] = useState(null);
  const [drafts, setDrafts] = useState({});
  // The H1 contract carries no KPI baselines or targets, so this is [] for
  // every focus area of every run today. It rendered anyway: a heading, a
  // "Customise per client" badge and a six-line explainer over zero tiles —
  // chrome promising figures that do not exist. Nothing to show, nothing shown;
  // if a future contract carries kpis the strip returns on its own.
  if (!kpis.length) return null;
  const cycleMode = label => {
    setModes(m => ({
      ...m,
      [label]: m[label] === "public" ? "client" : m[label] === "client" ? "hidden" : "public"
    }));
  };
  const saveDraft = label => {
    setEditing(null);
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 14,
      padding: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "scale",
    size: 14
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "KPI baseline \xB7 target"), /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, "Customise per client"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Toggle each KPI between Public inference \xB7 Client-provided \xB7 Hidden")), /*#__PURE__*/React.createElement("div", {
    className: "g3"
  }, kpis.map(k => {
    const mode = modes[k.label];
    const isEditing = editing === k.label;
    const isHidden = mode === "hidden";
    const isClient = mode === "client";
    const meta = isClient ? {
      tag: "Client-provided",
      color: "var(--z-dpur)",
      bg: "var(--ph0-lt)",
      bd: "var(--ph0-bd)",
      icon: "user"
    } : isHidden ? {
      tag: "Not available",
      color: "var(--z-muted)",
      bg: "var(--z-lav)",
      bd: "var(--z-sep)",
      icon: "lock"
    } : {
      tag: "Public DMA inference",
      color: "var(--z-mid)",
      bg: "var(--z-ice)",
      bd: "rgba(39,187,175,.3)",
      icon: "globe"
    };
    return /*#__PURE__*/React.createElement("div", {
      key: k.label,
      className: "card-tile",
      style: {
        padding: 12,
        border: `1px solid ${meta.bd}`,
        background: meta.bg
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 6
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        textTransform: "uppercase",
        letterSpacing: ".06em",
        flex: 1
      },
      className: "txt-fit-1"
    }, k.label), /*#__PURE__*/React.createElement("button", {
      className: "icon-btn",
      style: {
        width: 22,
        height: 22,
        color: meta.color
      },
      title: `Source: ${meta.tag} · click to change`,
      onClick: () => cycleMode(k.label)
    }, /*#__PURE__*/React.createElement(Icon, {
      name: meta.icon,
      size: 11
    })), /*#__PURE__*/React.createElement("button", {
      className: "icon-btn",
      style: {
        width: 22,
        height: 22,
        color: "var(--z-muted)"
      },
      title: "Edit values",
      onClick: () => setEditing(isEditing ? null : k.label)
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "edit",
      size: 11
    }))), !isHidden && !isEditing ? /*#__PURE__*/React.createElement("div", {
      className: "row"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 16,
        fontWeight: 700,
        color: "var(--z-dark)"
      }
    }, drafts[k.label + "_current"] || k.current), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9,
        color: "var(--z-muted)"
      }
    }, "current")), /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-r",
      size: 12,
      style: {
        color: "var(--z-muted)"
      }
    }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 16,
        fontWeight: 700,
        color: meta.color
      }
    }, drafts[k.label + "_target"] || k.target), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9,
        color: "var(--z-muted)"
      }
    }, "target")), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      className: `b`,
      style: {
        background: meta.bd,
        color: meta.color,
        fontSize: 9
      }
    }, k.delta)) : isEditing ? /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        flexDirection: "column",
        gap: 6
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 6
      }
    }, /*#__PURE__*/React.createElement("input", {
      className: "inp",
      style: {
        padding: "4px 8px",
        fontSize: 11
      },
      placeholder: "Current",
      defaultValue: drafts[k.label + "_current"] || k.current,
      onChange: e => setDrafts(d => ({
        ...d,
        [k.label + "_current"]: e.target.value
      }))
    }), /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-r",
      size: 11,
      style: {
        color: "var(--z-muted)"
      }
    }), /*#__PURE__*/React.createElement("input", {
      className: "inp",
      style: {
        padding: "4px 8px",
        fontSize: 11
      },
      placeholder: "Target",
      defaultValue: drafts[k.label + "_target"] || k.target,
      onChange: e => setDrafts(d => ({
        ...d,
        [k.label + "_target"]: e.target.value
      }))
    })), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 4
      }
    }, /*#__PURE__*/React.createElement("button", {
      className: "btn btn-primary btn-sm",
      style: {
        padding: "3px 8px",
        fontSize: 10.5
      },
      onClick: () => saveDraft(k.label)
    }, "Save"), /*#__PURE__*/React.createElement("button", {
      className: "btn btn-tertiary btn-sm",
      style: {
        padding: "3px 8px",
        fontSize: 10.5
      },
      onClick: () => setEditing(null)
    }, "Cancel"))) : /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: meta.color,
        padding: "4px 0",
        display: "flex",
        alignItems: "center",
        gap: 6
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "lock",
      size: 11
    }), " Hidden - not inferable from public sources"), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        color: meta.color,
        marginTop: 5,
        fontWeight: 600
      }
    }, meta.tag.toUpperCase()));
  })), /*#__PURE__*/React.createElement("div", {
    className: "co co-teal",
    style: {
      marginTop: 10
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 13
  }), /*#__PURE__*/React.createElement("div", {
    className: "co-body"
  }, "Some KPIs can only be inferred indirectly from public sources (annual reports, hiring signals, app store reviews). Click the source icon to switch a KPI between ", /*#__PURE__*/React.createElement("strong", null, "Public DMA inference"), ", ", /*#__PURE__*/React.createElement("strong", null, "Client-provided"), " (when you receive direct data in a meeting), or ", /*#__PURE__*/React.createElement("strong", null, "Hidden"), " (when no reliable source exists). Use the edit icon to enter values directly.")));
}

/* ─────────────────────── PILLAR HEATMAP ─────────────────────── */
function PillarHeatmap({
  entity,
  pillars,
  setPillarFocus,
  audience
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "g4"
  }, (pillars || []).map(p => {
    // The promoted pillar score and the workbook's STATED pillar median.
    // A constant offset used to stand in for the median: Baxter's P1 sits
    // at 3.11 against a stated 2.9 — ABOVE its peer set — and `score +
    // 0.3` rendered that as 0.3 BELOW.
    const score = p.score,
      peer = p.peer;
    const delta = deltaOf(score, peer);
    return /*#__PURE__*/React.createElement("div", {
      key: p.id,
      className: "card-tile clickable",
      onClick: () => setPillarFocus(p.id),
      style: {
        padding: 16
      },
      title: `${p.id} — ${p.name || "unnamed in catalogue"} · ${score != null ? fx(score, 1) : "no score"} · click to drill`
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 12
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, p.id), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 14,
        fontWeight: 600
      },
      className: "txt-fit-2"
    }, p.name || "not named in the current catalogue")), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement(MaturityChip, {
      score: score,
      large: true
    })), score != null ? /*#__PURE__*/React.createElement("div", {
      className: "prog"
    }, /*#__PURE__*/React.createElement("div", {
      className: "prog-fill",
      style: {
        width: `${score / 5 * 100}%`,
        background: DMA.helpers.maturityHex(score)
      }
    })) : /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, "no pillar score promoted"), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginTop: 8,
        fontSize: 11
      }
    }, peer != null ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
      style: {
        color: "var(--z-muted)"
      }
    }, "Peer ", fx(peer, 1)), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), delta != null ? /*#__PURE__*/React.createElement("span", {
      style: {
        color: delta < 0 ? "var(--z-below)" : "var(--z-mid)",
        fontFamily: "var(--font-mono)"
      }
    }, delta >= 0 ? "▲" : "▼", " ", fx(Math.abs(delta), 1)) : null) :
    /*#__PURE__*/
    /* Compact: four tiles across, and the 11px meta row under
       the progress bar has no room for the queue badge. */
    React.createElement("span", {
      style: {
        color: "var(--z-muted)"
      },
      title: "the run states no peer median for this pillar"
    }, /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: `${p.id} peer median`,
      audience: audience,
      compact: true
    }))), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)",
        marginTop: 10
      }
    }, p.cats.length, " categories \xB7 ", p.cellCount, " subcaps \xB7 click to drill"));
  })));
}

/* ─────────────────────── CATEGORY HEATMAP ─────────────────────── */
function CategoryHeatmap({
  entity,
  pillars,
  pillarFocus,
  showPeers,
  showIssues,
  setCatFocus,
  onSynth,
  audience
}) {
  const rows = pillarFocus ? (pillars || []).filter(p => p.id === pillarFocus) : pillars || [];
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
      const row = catCaps[catId] || (catCaps[catId] = {
        linked: 0,
        capped: 0
      });
      row.linked += 1;
      if (cap != null) row.capped += 1;
    });
  });
  return /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, rows.map(p => {
    const cats = p.cats;
    return /*#__PURE__*/React.createElement("div", {
      key: p.id,
      style: {
        marginBottom: 16
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 10
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, p.id), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, p.name || "not named in the current catalogue"), /*#__PURE__*/React.createElement(MaturityChip, {
      score: p.score
    }), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, cats.length, " categories \xB7 ", p.cellCount, " subcaps")), !cats.length ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, "This run scored no cells in this pillar.") : /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: `120px repeat(${cats.length}, minmax(0, 1fr))`,
        gap: 4
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)",
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        paddingRight: 8
      }
    }, "Entity"), cats.map(c => {
      // The workbook's own category score. Where the run promotes
      // none, the mean of the cells it scored — said so in the
      // tooltip, never silently swapped for the stated figure.
      const shown = c.score != null ? c.score : c.cellMean;
      const basis = c.score != null ? `promoted category score${c.source_cell ? ` (${c.source_cell})` : ""}` : c.cellMean != null ? `mean of ${c.cells.length} scored cells — the run promoted no category score` : "no score";
      const iss = catCaps[c.id] || {
        linked: 0,
        capped: 0
      };
      const capCount = iss.capped || iss.linked;
      const tipLabel = `${c.id} — ${c.name || "unnamed in catalogue"} · ${shown != null ? fx(shown, 1) : "no score"}`;
      return /*#__PURE__*/React.createElement("button", {
        key: c.id,
        className: `hm-cell b ${DMA.helpers.maturityClass(shown)}`,
        onClick: () => {
          cellTip.hide();
          setCatFocus(c.id);
        },
        onContextMenu: e => {
          e.preventDefault();
          cellTip.hide();
          onSynth(c.id);
        },
        onMouseEnter: cellTip.show(tipLabel),
        onMouseLeave: cellTip.hide,
        style: {
          position: "relative",
          border: 0,
          padding: "8px 6px",
          minHeight: 44
        },
        title: `${c.id} · ${c.name || "not named in the current catalogue"} · ${basis}${iss.capped ? ` · ${iss.capped} subcaps capped by issues` : iss.linked ? ` · ${iss.linked} subcaps linked to issues (no cap level stated)` : ""} · click to drill`
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          display: "flex",
          flexDirection: "column",
          lineHeight: 1.2,
          gap: 2
        }
      }, shown == null ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10.5,
          fontWeight: 600
        }
      }, /*#__PURE__*/React.createElement(EnrichmentGap, {
        what: `${c.id} score`,
        audience: audience,
        compact: true
      })) : /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 13,
          fontWeight: 700
        }
      }, fx(shown, 1)), c.thin > 0 ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 8,
          fontWeight: 600
        }
      }, c.thin, " thin") : null), showIssues && capCount > 0 ? /*#__PURE__*/React.createElement("span", {
        style: {
          position: "absolute",
          top: 3,
          right: 4,
          display: "inline-flex",
          alignItems: "center",
          gap: 2,
          fontSize: 9,
          color: "var(--z-org)",
          background: "rgba(255,255,255,.85)",
          padding: "0 3px",
          borderRadius: 3
        }
      }, /*#__PURE__*/React.createElement(Icon, {
        name: iss.capped ? "lock" : "warn",
        size: 9
      }), capCount) : null);
    }), showPeers ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)",
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        paddingRight: 8
      }
    }, "Peer"), cats.map(c => {
      const pm = c.peer;
      // A null median banded as maturityClass(null) and printed 0.0,
      // so all sixteen categories read "Peer 0.0" in the lowest band
      // — a peer set that scores nothing.
      return pm == null ?
      /*#__PURE__*/
      /* Compact, and only compact: this is a fixed-height grid
         cell in a row of peer figures — the queue badge would
         burst the column. */
      React.createElement("div", {
        key: c.id,
        className: "hm-cell peer b b-muted",
        style: {
          minHeight: 30,
          padding: "4px 6px"
        },
        title: "no peer median stated for this category in this run"
      }, /*#__PURE__*/React.createElement(EnrichmentGap, {
        what: `${c.id} peer median`,
        audience: audience,
        compact: true
      })) : /*#__PURE__*/React.createElement("div", {
        key: c.id,
        className: `hm-cell peer b ${DMA.helpers.maturityClass(pm)}`,
        style: {
          minHeight: 30,
          padding: "4px 6px"
        },
        title: `${c.id} — ${c.name || "unnamed in catalogue"} · peer median ${fx(pm, 1)}`,
        onMouseEnter: cellTip.show(`${c.id} — ${c.name || "unnamed in catalogue"} · peer median ${fx(pm, 1)}`),
        onMouseLeave: cellTip.hide
      }, fx(pm, 1));
    })) : null, /*#__PURE__*/React.createElement("div", null), cats.map(c => /*#__PURE__*/React.createElement("div", {
      key: `l-${c.id}`,
      style: {
        fontSize: 9.5,
        color: "var(--z-muted)",
        textAlign: "center",
        padding: "4px 2px 0",
        lineHeight: 1.3,
        minWidth: 0
      },
      title: c.inCatalogue ? `${c.id} · ${c.name}` : `${c.id} · this run scored ${c.cells.length} cells here; the current catalogue does not list this category, so no name is available`
    }, /*#__PURE__*/React.createElement("div", {
      className: "f-mono"
    }, c.id), /*#__PURE__*/React.createElement("div", {
      className: "txt-fit-2",
      style: c.inCatalogue ? null : {
        fontStyle: "italic"
      }
    }, c.name || "unnamed in catalogue")))));
  }), /*#__PURE__*/React.createElement(CellTip, {
    tip: cellTip.tip
  }));
}

/* ─────────────────────── CAPABILITY HEATMAP ─────────────────────
   The capability grain: one row per capability (L1) with the cells beneath it.
   The run's cell grain carries `capability_id` but no capability NAME, so a row
   is labelled with its id — the alternative would be inventing one. The mean is
   computed from the cells because nothing is promoted at this grain, and every
   row says how many cells it is a mean of. */
function CapabilityHeatmap({
  entity,
  cats,
  catFocus,
  pillarFocus,
  showIssues,
  drillCategory,
  audience
}) {
  const scope = catFocus ? (cats || []).filter(c => c.id === catFocus) : pillarFocus ? (cats || []).filter(c => c.pillar === pillarFocus) : cats || [];
  if (!scope.length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "card"
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-muted)"
      }
    }, "This run scored no cells in the current selection."));
  }
  return /*#__PURE__*/React.createElement("div", null, scope.map(c => {
    const groups = [];
    const byCap = {};
    for (const s of c.cells) {
      const cap = s.capability || `${c.id} · cell carries no capability id`;
      if (!byCap[cap]) {
        byCap[cap] = {
          id: cap,
          items: []
        };
        groups.push(byCap[cap]);
      }
      byCap[cap].items.push(s);
    }
    groups.sort((a, b) => String(a.id).localeCompare(String(b.id), undefined, {
      numeric: true
    }));
    return /*#__PURE__*/React.createElement("div", {
      key: c.id,
      className: "card",
      style: {
        marginBottom: 14
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 12
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip"
    }, c.id), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, c.name || "unnamed in catalogue"), /*#__PURE__*/React.createElement(MaturityChip, {
      score: c.score != null ? c.score : c.cellMean
    }), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, groups.length, " capabilities \xB7 ", c.cells.length, " subcaps", c.weight != null ? ` · weight ${fx(c.weight * 100, 0)}%` : "")), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)",
        marginBottom: 8
      }
    }, "The run promotes no score and no name at capability grain \u2014 each row is its own cells' mean, labelled with its capability id."), /*#__PURE__*/React.createElement("div", {
      className: "g2",
      style: {
        gap: 8
      }
    }, groups.map(g => {
      const mean = meanOf(g.items.map(s => s.score));
      const thin = g.items.filter(s => s.thin).length;
      const capped = showIssues ? g.items.filter(s => DMA.issueCapsFor(s.id).length).length : 0;
      return /*#__PURE__*/React.createElement("button", {
        key: g.id,
        className: "card-tile clickable",
        style: {
          padding: 10,
          textAlign: "left"
        },
        onClick: () => drillCategory && drillCategory(c.id),
        title: `${g.id} · mean of ${g.items.length} scored cells (no capability score is promoted) · click to read the cells`
      }, /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          gap: 8
        }
      }, mean == null ? /*#__PURE__*/React.createElement("span", {
        style: {
          flex: "0 1 auto",
          minWidth: 0
        }
      }, /*#__PURE__*/React.createElement(EnrichmentGap, {
        what: `${g.id} cell scores`,
        audience: audience,
        compact: true
      })) : /*#__PURE__*/React.createElement("span", {
        className: `b ${DMA.helpers.maturityClass(mean)}`,
        style: {
          width: 34,
          justifyContent: "center",
          flexShrink: 0
        }
      }, fx(mean, 1)), /*#__PURE__*/React.createElement("span", {
        className: "f-mono txt-fit-1",
        style: {
          fontSize: 11.5,
          fontWeight: 600,
          color: "var(--z-dark)",
          minWidth: 0
        }
      }, g.id), /*#__PURE__*/React.createElement("span", {
        className: "spacer"
      }), /*#__PURE__*/React.createElement("span", {
        className: "b b-muted",
        title: "cells in this capability"
      }, g.items.length), thin ? /*#__PURE__*/React.createElement("span", {
        className: "b b-org"
      }, thin, " thin") : null, capped ? /*#__PURE__*/React.createElement("span", {
        className: "b b-org"
      }, /*#__PURE__*/React.createElement(Icon, {
        name: "lock",
        size: 9
      }), " ", capped) : null), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10,
          color: "var(--z-muted)",
          marginTop: 4
        }
      }, "mean of ", g.items.length, " cell", g.items.length === 1 ? "" : "s"));
    })));
  }));
}

/* ─────────────────────── SUBCAP HEATMAP ─────────────────────── */
function SubcapHeatmap({
  entity,
  cats: allCats,
  catFocus,
  pillarFocus,
  showPeers,
  showIssues,
  onSynth,
  setCatFocus,
  audience
}) {
  const [openClusters, setOpenClusters] = useState({});
  // Every grid that paints a cell gets the same bubble. This one and the
  // capability grid carried the `title` attribute alone, which is the
  // browser's own tooltip: it waits about a second, paints in the OS style,
  // and reads as nothing happening to anyone who moves on before it fires.
  // Same text, same instant bubble, in all four views.
  const cellTip = useCellTip();
  // The run's categories, so a category the current catalogue does not list is
  // still reachable and its cells still readable.
  const cats = catFocus ? (allCats || []).filter(c => c.id === catFocus) : pillarFocus ? (allCats || []).filter(c => c.pillar === pillarFocus) : null;

  // No category/pillar in focus → show a picker instead of dumping all 765 cells
  if (!cats || cats.length === 0) {
    const pillarIds = [];
    for (const c of allCats || []) if (!pillarIds.includes(c.pillar)) pillarIds.push(c.pillar);
    return /*#__PURE__*/React.createElement("div", {
      className: "card",
      style: {
        marginBottom: 14
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 4
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "grid",
      size: 14
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, "Select a category to view its sub-capabilities")), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-muted)",
        marginBottom: 14
      }
    }, "The subcap view drills into one category at a time so you can read the evidence behind each score. Pick a category below."), pillarIds.sort().map(pid => {
      const meta = (DMA.PILLARS || []).find(p => p.id === pid) || null;
      const pcats = (allCats || []).filter(c => c.pillar === pid);
      return /*#__PURE__*/React.createElement("div", {
        key: pid,
        style: {
          marginBottom: 12
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          marginBottom: 6,
          gap: 6
        }
      }, /*#__PURE__*/React.createElement("span", {
        className: "b b-purple"
      }, pid), /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 11.5,
          fontWeight: 600,
          color: "var(--z-dark)"
        }
      }, meta && (meta.short || meta.name) || "unnamed in catalogue")), /*#__PURE__*/React.createElement("div", {
        className: "g4",
        style: {
          gap: 8
        }
      }, pcats.map(c => {
        // The promoted category score, else the mean of its cells,
        // else nothing. A zero here read as a measured floor.
        const shown = c.score != null ? c.score : c.cellMean;
        return /*#__PURE__*/React.createElement("button", {
          key: c.id,
          className: "card-tile clickable",
          style: {
            padding: 11,
            textAlign: "left"
          },
          onClick: () => setCatFocus && setCatFocus(c.id),
          disabled: !c.cells.length
        }, /*#__PURE__*/React.createElement("div", {
          className: "row",
          style: {
            marginBottom: 6,
            gap: 5
          }
        }, /*#__PURE__*/React.createElement("span", {
          className: "chip"
        }, c.id), /*#__PURE__*/React.createElement("span", {
          className: "spacer"
        }), shown != null ? /*#__PURE__*/React.createElement("span", {
          className: `b ${DMA.helpers.maturityClass(shown)}`
        }, fx(shown, 1)) : /*#__PURE__*/React.createElement("span", {
          className: "b b-muted"
        }, /*#__PURE__*/React.createElement(EnrichmentGap, {
          what: `${c.id} score`,
          audience: audience,
          compact: true
        }))), /*#__PURE__*/React.createElement("div", {
          style: {
            fontSize: 12,
            fontWeight: 600,
            color: "var(--z-dark)"
          },
          className: "txt-fit-2"
        }, c.name || "unnamed in catalogue"), /*#__PURE__*/React.createElement("div", {
          style: {
            fontSize: 10.5,
            color: "var(--z-muted)",
            marginTop: 3
          }
        }, c.cells.length, " subcaps", c.thin ? ` · ${c.thin} thin` : ""));
      })));
    }));
  }
  return /*#__PURE__*/React.createElement("div", null, catFocus ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => setCatFocus && setCatFocus(null)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-l",
    size: 12
  }), " All categories"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Showing sub-capabilities for ", catFocus)) : null, cats.map(c => {
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
      if (!byCap[cap]) {
        byCap[cap] = {
          id: cap,
          named: !!s.capability,
          items: []
        };
        clusters.push(byCap[cap]);
      }
      byCap[cap].items.push(s);
    });
    clusters.sort((a, b) => String(a.id).localeCompare(String(b.id), undefined, {
      numeric: true
    }));
    return /*#__PURE__*/React.createElement("div", {
      key: c.id,
      className: "card",
      style: {
        marginBottom: 14
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 12
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip"
    }, c.id), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, c.name || "unnamed in catalogue"), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, subs.length, " subcaps \xB7 ", clusters.length, " capabilities", c.weight != null ? ` · weight ${fx(c.weight * 100, 0)}%` : "")), clusters.map(cl => {
      const key = `${c.id}.${cl.id}`;
      const open = openClusters[key] !== false; // default open
      const avg = meanOf(cl.items.map(s => s.score));
      const capped = showIssues ? cl.items.filter(s => DMA.issueCapsFor(s.id).length).length : 0;
      return /*#__PURE__*/React.createElement("div", {
        key: key,
        style: {
          border: "1px solid var(--z-sep)",
          borderRadius: 8,
          marginBottom: 8,
          overflow: "hidden"
        }
      }, /*#__PURE__*/React.createElement("button", {
        onClick: () => setOpenClusters(o => ({
          ...o,
          [key]: !open
        })),
        title: `${cl.id} · mean of ${cl.items.length} scored cells (no capability score or name is promoted at this grain)`,
        style: {
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "9px 12px",
          background: "var(--z-bg)",
          border: 0,
          cursor: "pointer",
          textAlign: "left"
        }
      }, avg == null ? /*#__PURE__*/React.createElement("span", {
        style: {
          flex: "0 1 auto",
          minWidth: 0
        }
      }, /*#__PURE__*/React.createElement(EnrichmentGap, {
        what: `${cl.id} cell scores`,
        audience: audience,
        compact: true
      })) : /*#__PURE__*/React.createElement("span", {
        className: `b ${DMA.helpers.maturityClass(avg)}`,
        style: {
          width: 34,
          justifyContent: "center",
          flexShrink: 0
        }
      }, fx(avg, 1)), /*#__PURE__*/React.createElement("span", {
        className: "f-mono txt-fit-1",
        style: {
          flex: 1,
          minWidth: 0,
          fontSize: 12,
          fontWeight: 600,
          color: "var(--z-dark)"
        }
      }, cl.id), /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 10,
          color: "var(--z-muted)",
          flexShrink: 0
        }
      }, cl.items.length, " cells"), capped ? /*#__PURE__*/React.createElement("span", {
        className: "b b-org"
      }, /*#__PURE__*/React.createElement(Icon, {
        name: "lock",
        size: 9
      }), " ", capped) : null, /*#__PURE__*/React.createElement(Icon, {
        name: open ? "chevron-u" : "chevron-d",
        size: 13,
        style: {
          color: "var(--z-muted)",
          flexShrink: 0
        }
      })), open ? /*#__PURE__*/React.createElement("div", {
        style: {
          display: "flex",
          flexDirection: "column",
          gap: 5,
          padding: "8px 10px"
        }
      }, cl.items.map(s => {
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
          /*#__PURE__*/
          /* The name column ellipsises to one line; the title
             carries the full identification. */
          React.createElement("button", {
            key: s.id,
            className: "subcap-row",
            onClick: () => onSynth(s),
            title: subcapTipText(s),
            onMouseEnter: cellTip.show(subcapTipText(s)),
            onMouseLeave: cellTip.hide
          }, s.score == null ? /*#__PURE__*/React.createElement("span", {
            style: {
              flex: "0 1 auto",
              minWidth: 0
            }
          }, /*#__PURE__*/React.createElement(EnrichmentGap, {
            what: `${s.id} score`,
            audience: audience,
            compact: true
          })) : /*#__PURE__*/React.createElement("span", {
            className: `b ${DMA.helpers.maturityClass(s.score)}`,
            style: {
              width: 34,
              justifyContent: "center",
              flexShrink: 0
            }
          }, fx(s.score, 1)), /*#__PURE__*/React.createElement("div", {
            style: {
              flex: 1,
              minWidth: 0
            }
          }, /*#__PURE__*/React.createElement("div", {
            className: "row",
            style: {
              gap: 6
            }
          }, /*#__PURE__*/React.createElement("span", {
            style: {
              fontSize: 12,
              fontWeight: 500,
              color: s.name && s.name !== s.id ? "var(--z-dark)" : "var(--z-muted)",
              fontStyle: s.name && s.name !== s.id ? "normal" : "italic"
            },
            className: "txt-fit-1"
          }, s.name && s.name !== s.id ? s.name : "unnamed in catalogue"), s.thin ? /*#__PURE__*/React.createElement("span", {
            className: "b b-org"
          }, "THIN") : null, caps.length ? /*#__PURE__*/React.createElement("span", {
            className: "b b-org"
          }, /*#__PURE__*/React.createElement(Icon, {
            name: "lock",
            size: 9
          }), " M", caps[0].cap) : null), /*#__PURE__*/React.createElement("div", {
            className: "f-mono txt-fit-1",
            style: {
              fontSize: 10,
              color: "var(--z-muted)",
              marginTop: 1
            },
            title: ev.basis === "cited" ? "ids the producer cited for this cell" : ev.basis === "linked" ? "evidence items the run links to this cell" : null
          }, s.id, s.confidence ? ` · ${s.confidence}` : "", ev.n != null ? ` · ${ev.n} ${ev.basis}` : " · no evidence count")), /*#__PURE__*/React.createElement("div", {
            style: {
              width: 90,
              flexShrink: 0
            }
          }, /*#__PURE__*/React.createElement("div", {
            style: {
              position: "relative",
              height: 6,
              background: "var(--z-sep)",
              borderRadius: 3
            },
            title: `Score ${fx(s.score, 1)}${s.peerMedian != null ? ` · Peer ${fx(s.peerMedian, 1)}` : " · no peer median stated"}`
          }, s.score != null ? /*#__PURE__*/React.createElement("div", {
            style: {
              width: `${s.score / 5 * 100}%`,
              height: "100%",
              background: DMA.helpers.maturityHex(s.score),
              borderRadius: 3
            }
          }) : null, s.peerMedian != null ? /*#__PURE__*/React.createElement("div", {
            style: {
              position: "absolute",
              left: `calc(${s.peerMedian / 5 * 100}% - 1px)`,
              top: -2,
              bottom: -2,
              width: 2,
              background: "var(--z-dpur)"
            }
          }) : null), gap != null ? /*#__PURE__*/React.createElement("div", {
            style: {
              fontSize: 9,
              color: gap > 0 ? "var(--z-below)" : gap < 0 ? "var(--z-mid)" : "var(--z-muted)",
              marginTop: 2,
              textAlign: "right"
            }
          }, gap > 0 ? `−${fx(gap, 1)}` : gap < 0 ? `+${fx(Math.abs(gap), 1)}` : "0.0", " vs peer") : /*#__PURE__*/React.createElement("div", {
            style: {
              fontSize: 9,
              color: "var(--z-muted)",
              marginTop: 2,
              textAlign: "right"
            }
          }, "\xA0")), /*#__PURE__*/React.createElement("div", {
            style: {
              display: "flex",
              gap: 3,
              flexShrink: 0
            }
          }, s.platforms.slice(0, 2).map(p => /*#__PURE__*/React.createElement("span", {
            key: p,
            className: "b b-teal"
          }, DMA.getPlatform(p)?.short || p))), /*#__PURE__*/React.createElement(Icon, {
            name: "chevron-r",
            size: 13,
            style: {
              color: "var(--z-muted)",
              flexShrink: 0
            }
          }))
        );
      })) : null);
    }));
  }), /*#__PURE__*/React.createElement(CellTip, {
    tip: cellTip.tip
  }));
}

/* ─────────────────────── VALUE CHAIN VIEW ─────────────────────── */
// The cells a value-chain stage actually covers. Each stage declares its own
// membership list; the view used to pick `subcaps.slice(hash(stage.id) % n, +8)`
// instead, which is why the cells under "Loan Origination" had nothing to do
// with loan origination. A stage that declares nothing renders empty and says
// so — the arrangement is a claim about the client's operating model, and an
// arbitrary slice of it is not one.
function subcapsForStage(entity, vc) {
  const named = new Set(vc && (vc.subcaps || vc.subcap_ids) || []);
  const all = Array.isArray(entity.subcaps) ? entity.subcaps : [];
  if (!named.size || !all.length) return [];
  const exact = all.filter(s => named.has(s.id));
  if (exact.length) return exact;
  return all.filter(s => [...named].some(n => typeof n === "string" && s.id.startsWith(`${n}.`)));
}
function ValueChainView({
  entity,
  subcapsForFocusArea,
  openSubcap,
  openInsight
}) {
  const [selected, setSelected] = useState(null);
  // The stage tiles' mini-cells carry a score and nothing else — hover
  // identification, same shared-bubble pattern as the other grids.
  const cellTip = useCellTip();
  const chains = DMA.VALUE_CHAINS || [];
  const state = typeof DMA.sectionStateFor === "function" ? DMA.sectionStateFor("heatmap.value_chain") : null;
  const empty = state && state.empty_state;

  /* The section is optional and Baxter's run submitted eight of nine sections
     without it. With no chains the view rendered its heading, an empty grey
     badge and "Same 765 subcaps, reorganised by business process" over an empty
     grid — a promise that the cells had been arranged by business process when
     nothing had been. The stage arrangement is a claim about this client's
     operating model, so there is nothing to derive it from; say that it did not
     promote, and name what the API said. */
  if (!chains.length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "empty"
    }, /*#__PURE__*/React.createElement("div", {
      className: "icon"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "route",
      size: 20
    })), /*#__PURE__*/React.createElement("h3", null, "The value chain section did not promote for this run"), /*#__PURE__*/React.createElement("p", null, empty ? `${String(empty.kind || "empty").replace(/_/g, " ")}${empty.reason ? ` — ${empty.reason}` : ""}.` : "The run promoted no value-chain stages."), /*#__PURE__*/React.createElement("p", {
      style: {
        marginTop: 8
      }
    }, "Which cells belong to which business process is the producer's claim about ", entity.name, "'s operating model. The cell grain alone cannot stand it up, so nothing is drawn here until the section promotes."));
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
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "route",
    size: 14
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "Value chain view"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, chains.length, " stages \xB7 ", mapped.size, " of ", entity.subcaps.length, " subcaps mapped")), /*#__PURE__*/React.createElement("div", {
    className: "g3",
    style: {
      marginBottom: 14
    }
  }, chains.map(vc => {
    // Pick subcaps representative of value chain - sample from subcaps
    const subs = subcapsForStage(entity, vc);
    const scored = subs.filter(s => s.score != null);
    const avg = scored.length ? scored.reduce((a, s) => a + s.score, 0) / scored.length : null;
    // Peer medians are absent at cell grain in every shipped package, so
    // this is null far more often than not — and averaging nulls produced
    // NaN on the tile. Computed-or-null, never a placeholder.
    const withPeer = subs.filter(s => s.peerMedian != null);
    const peer = withPeer.length ? withPeer.reduce((a, s) => a + s.peerMedian, 0) / withPeer.length : null;
    return /*#__PURE__*/React.createElement("div", {
      key: vc.id,
      className: "card-tile clickable",
      style: {
        padding: 14,
        border: selected === vc.id ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)",
        background: selected === vc.id ? "var(--z-ice)" : "#fff"
      },
      onClick: () => setSelected(vc.id === selected ? null : vc.id)
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, vc.name)), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 8
      }
    }, avg == null ? /*#__PURE__*/React.createElement("span", {
      className: "b b-muted"
    }, "No score") : /*#__PURE__*/React.createElement(MaturityChip, {
      score: avg
    }), peer == null ? null : /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, "Peer ", fx(peer, 1)), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, subs.length, " subcap", subs.length === 1 ? "" : "s")), !subs.length ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, "No cells mapped to this stage for this run.") : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: `repeat(${Math.min(subs.length, STRIP)}, 1fr)`,
        gap: 2
      }
    }, subs.slice(0, STRIP).map(s => /*#__PURE__*/React.createElement("div", {
      key: s.id,
      className: `hm-cell b ${DMA.helpers.maturityClass(s.score)}`,
      style: {
        height: 18,
        fontSize: 9,
        padding: 0,
        border: 0
      },
      title: subcapTipText(s),
      onMouseEnter: cellTip.show(subcapTipText(s)),
      onMouseLeave: cellTip.hide
    }, s.score == null ? null : fx(s.score, 1)))), subs.length > STRIP ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        marginTop: 5
      }
    }, "first ", STRIP, " cells by id \xB7 open the stage for all ", subs.length) : null));
  })), selected ? (() => {
    const vc = chains.find(x => x.id === selected);
    if (!vc) return null;
    const subs = subcapsForStage(entity, vc);
    const insights = DMA.INSIGHT_CARDS.filter(ic => ic.affects.some(sid => subs.some(s => s.id === sid)));
    return /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "1.4fr 1fr",
        gap: 14
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "card"
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 12
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "heatmap",
      size: 14
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, vc.name, " \xB7 subcaps"), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, subs.length, " cells \xB7 click to drill")), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 6
      }
    }, subs.map(s => /*#__PURE__*/React.createElement("button", {
      key: s.id,
      className: "card-tile clickable",
      style: {
        padding: 10
      },
      title: subcapTipText(s),
      onMouseEnter: cellTip.show(subcapTipText(s)),
      onMouseLeave: cellTip.hide,
      onClick: () => {
        cellTip.hide();
        openSubcap({
          kind: "subcap",
          subcap: s
        });
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 4
      }
    }, /*#__PURE__*/React.createElement(MaturityChip, {
      score: s.score
    }), /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, s.id), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), s.thin ? /*#__PURE__*/React.createElement("span", {
      className: "b b-org"
    }, "THIN") : null), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-dark)"
      },
      className: "txt-fit-2"
    }, s.name))))), /*#__PURE__*/React.createElement("div", {
      className: "card flush"
    }, /*#__PURE__*/React.createElement("div", {
      className: "card-head"
    }, /*#__PURE__*/React.createElement("h3", null, "Insight cards in this chain"), /*#__PURE__*/React.createElement("span", {
      className: "b b-muted"
    }, insights.length)), /*#__PURE__*/React.createElement("div", {
      style: {
        padding: 12
      }
    }, insights.length === 0 ? /*#__PURE__*/React.createElement("div", {
      className: "muted",
      style: {
        fontSize: 12
      }
    }, "No insight cards mapped") : insights.map(ic => /*#__PURE__*/React.createElement("button", {
      key: ic.id,
      className: "card-tile clickable",
      style: {
        marginBottom: 8,
        padding: 12,
        width: "100%",
        textAlign: "left"
      },
      onClick: () => openInsight(ic.id)
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 4
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "ic-id"
    }, ic.id), /*#__PURE__*/React.createElement("span", {
      className: `b ${ic.flag === "CRITICAL" ? "b-below" : ic.flag === "OPPORTUNITY" ? "b-org" : "b-teal"}`
    }, ic.flag)), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600
      },
      className: "txt-fit-1"
    }, ic.title))))));
  })() : null, /*#__PURE__*/React.createElement(CellTip, {
    tip: cellTip.tip
  }));
}

/* A category's citations: the union of its cells' promoted lists, in cell order.
   Falls back to the run's link table only when no cell in the category promoted
   one, and says which it used. */
function categoryCitationsOf(cells) {
  const seen = new Set();
  const items = [];
  let withLists = 0;
  for (const c of cells || []) {
    const cell = typeof DMA.cellEvidenceFor === "function" ? DMA.cellEvidenceFor(c.id) : null;
    const ids = cell && Array.isArray(cell.e_ids) ? cell.e_ids : [];
    if (ids.length) withLists += 1;
    for (const id of ids) {
      if (seen.has(id)) continue;
      seen.add(id);
      const e = DMA.getEvidence(id) || null;
      items.push(e ? {
        ...e,
        resolved: true
      } : {
        id,
        resolved: false
      });
    }
  }
  if (items.length) return {
    basis: "promoted",
    items,
    withLists
  };
  const ids = new Set((cells || []).map(c => c.id));
  return {
    basis: "derived",
    withLists: 0,
    items: (DMA.EVIDENCE || []).filter(e => e.subcaps && e.subcaps.some(sid => ids.has(sid))).map(e => ({
      ...e,
      resolved: true
    }))
  };
}

/* The score axis. It was labelled with five maturity levels, and the fifth does
   not exist: there are four bands, resolved on the raw score, strictly
   less-than. Labelled with the scale's own numbers and the band that owns each
   range. */
function BandAxis() {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      height: 15,
      fontSize: 10,
      color: "var(--z-muted)",
      fontFamily: "var(--font-mono)"
    }
  }, [1, 2, 3, 4, 5].map(t => /*#__PURE__*/React.createElement("span", {
    key: t,
    style: {
      position: "absolute",
      top: 0,
      lineHeight: "14px",
      left: `${(t - 1) / 4 * 100}%`,
      transform: t === 1 ? "none" : t === 5 ? "translateX(-100%)" : "translateX(-50%)"
    }
  }, t))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
      gap: 2,
      fontSize: 9,
      color: "var(--z-muted)",
      textAlign: "center"
    }
  }, ["Activating", "Building", "Competing", "Differentiating"].map(b => /*#__PURE__*/React.createElement("span", {
    key: b,
    className: "txt-fit-1"
  }, b))));
}

/* ─────────────────────── SYNTHESIS DRAWER ─────────────────────── */
function SynthesisDrawer({
  entity,
  item,
  onClose,
  openEvidence,
  openInsight,
  showIssues,
  audience
}) {
  const subcap = item.subcap;
  const catId = item.catId || subcap && subcap.category || null;
  const cats = useMemo(() => runCategoriesOf(entity), [entity?.id, entity?.subcaps]);
  // The RUN's category row. Reading `DMA.getCategory` alone meant a category the
  // current catalogue does not list (P1C5, 30 scored cells) resolved to nothing
  // and the drawer returned null — no synthesis at all for those cells.
  const catRow = catId ? cats.find(c => c.id === catId) || null : null;
  const category = item.catId ? catRow || null : null;
  if (!subcap && !category) return null;
  const catCells = catRow ? catRow.cells : [];

  // Linked insight cards
  const linkedIC = subcap ? DMA.INSIGHT_CARDS.filter(ic => (ic.affects || []).includes(subcap.id)) : DMA.INSIGHT_CARDS.filter(ic => (ic.affects || []).some(sid => sid.startsWith(category.id)));

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
  const score = subcap ? numOf(subcap.score) : catRow.score != null ? catRow.score : catRow.cellMean;
  const scoreBasis = subcap ? null : catRow.score != null ? `promoted category score${catRow.source_cell ? ` · ${catRow.source_cell}` : ""}` : `mean of ${catCells.length} scored cells — the run promoted no category score`;
  // The drawer's peer figure. For a category it was `score + 0.3`; for a cell it
  // was the null cell median, then formatted, then compared. Read the promoted
  // category median where there is one, and inherit it at cell grain labelled a
  // PROXY (the workbook states medians at category grain, not per cell).
  const catPeer = catRow ? catRow.peer : null;
  const peer = subcap ? subcap.peerMedian != null ? Number(subcap.peerMedian) : catPeer : catPeer;
  const peerIsProxy = !!(subcap && subcap.peerMedian == null && catPeer != null);
  // `peer - score` with a null peer is -score, which printed as "+2.5" in the
  // above-peer colour on a cell with no benchmark at all.
  const gap = deltaOf(peer, score);
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "drawer-mask",
    onClick: onClose
  }), /*#__PURE__*/React.createElement("div", {
    className: "drawer",
    style: {
      width: 480
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "drawer-head"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0,
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-teal"
  }, "SYNTHESIS"), subcap ? /*#__PURE__*/React.createElement("span", {
    className: "chip purple"
  }, subcap.id) : /*#__PURE__*/React.createElement("span", {
    className: "chip"
  }, category.id), subcap?.thin ? /*#__PURE__*/React.createElement("span", {
    className: "b b-org"
  }, "THIN") : null), /*#__PURE__*/React.createElement("div", {
    className: "title",
    style: {
      fontSize: 15
    }
  }, subcap ? subcap.name && subcap.name !== subcap.id ? subcap.name : `${subcap.id} · unnamed in catalogue` : category.name || `${category.id} · unnamed in catalogue`), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, subcap ? `Score ${fx(subcap.score, 1)}${subcap.confidence ? ` · ${subcap.confidence}` : ""}` : `${catCells.length} subcaps${category.weight != null ? ` · weight ${fx(category.weight * 100, 0)}%` : ""}`)), /*#__PURE__*/React.createElement("button", {
    className: "icon-btn",
    onClick: onClose
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "x",
    size: 16
  }))), /*#__PURE__*/React.createElement("div", {
    className: "drawer-body"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-tile",
    style: {
      marginBottom: 14,
      background: "var(--z-lav)",
      border: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "scale",
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      fontWeight: 600
    }
  }, "Peer comparison")), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      height: 36,
      background: "#fff",
      borderRadius: 6,
      overflow: "hidden",
      marginBottom: 8
    }
  }, [1, 2, 3, 4, 5].map(t => /*#__PURE__*/React.createElement("div", {
    key: t,
    style: {
      position: "absolute",
      left: `${(t - 1) / 4 * 100}%`,
      top: 0,
      bottom: 0,
      width: 1,
      background: "var(--z-sep)"
    }
  })), score != null ? /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      left: `calc(${(score - 1) / 4 * 100}% - 6px)`,
      top: 4,
      width: 12,
      height: 28,
      background: DMA.helpers.maturityHex(score),
      borderRadius: 3,
      boxShadow: "0 1px 3px rgba(0,0,0,.2)"
    },
    title: "Entity"
  }) : null, peer != null ? /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      left: `calc(${(peer - 1) / 4 * 100}% - 1px)`,
      top: 0,
      bottom: 0,
      width: 2,
      background: "var(--z-dpur)"
    },
    title: "Peer median"
  }) : null), /*#__PURE__*/React.createElement(BandAxis, null), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 10,
      fontSize: 12,
      flexWrap: "wrap",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "row",
    style: {
      gap: 5
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 10,
      height: 10,
      borderRadius: 3,
      background: DMA.helpers.maturityHex(score)
    }
  }), " Entity ", score == null
  /* The marker above already guards on a null score; this
     readout did not, so `fx` printed "Entity —" beside a
     peer branch that says "no peer median stated" in words.
     Compact: the row carries entity, peer and delta on one
     line. */ ? /*#__PURE__*/React.createElement(EnrichmentGap, {
    what: subcap ? `${subcap.id} score` : `${catId || "category"} score`,
    audience: audience,
    compact: true
  }) : /*#__PURE__*/React.createElement("strong", null, fx(score, 1))), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), peer != null ? /*#__PURE__*/React.createElement("span", {
    className: "row",
    style: {
      gap: 5
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 2,
      height: 12,
      background: "var(--z-dpur)"
    }
  }), " Peer ", /*#__PURE__*/React.createElement("strong", null, fx(peer, 1))) : /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    },
    title: "no peer median is stated at this grain in this run"
  }, "no peer median stated"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), gap != null ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: gap > 0 ? "var(--z-below)" : gap < 0 ? "var(--z-mid)" : "var(--z-muted)"
    }
  }, gap > 0 ? `−${fx(gap, 1)}` : gap < 0 ? `+${fx(Math.abs(gap), 1)}` : "0.0") : null), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      marginTop: 6,
      lineHeight: 1.45
    }
  }, scoreBasis ? `${scoreBasis}. ` : "", peer == null ? "The run states no peer median at this grain." : peerIsProxy ? `Peer figure is ${catId}'s category median, used as a proxy — the workbook states no median per cell.` : "Peer median as stated for this grain.")), caps.length > 0 ? /*#__PURE__*/React.createElement("div", {
    className: "co co-org",
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "lock",
    size: 14
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "co-title"
  }, "Capped by ", caps.length, " issue", caps.length === 1 ? "" : "s"), caps.map(c => {
    // An issue whose row did not promote has no description, and
    // `.desc.slice` on it took the drawer down.
    const desc = c.issue && (c.issue.desc || c.issue.title) || null;
    return /*#__PURE__*/React.createElement("div", {
      key: c.id,
      style: {
        fontSize: 12,
        marginTop: 4
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip",
      style: {
        marginRight: 6
      }
    }, c.id), desc ? `${desc.slice(0, 70)}${desc.length > 70 ? "…" : ""} ` : "", c.cap != null ? /*#__PURE__*/React.createElement("strong", null, "Cap M", c.cap) : /*#__PURE__*/React.createElement("span", {
      className: "muted"
    }, "cap level not stated"));
  }))) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 8,
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "evidence",
    size: 13,
    style: {
      color: "var(--z-mid)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: ".08em",
      color: "var(--z-dark)",
      textTransform: "uppercase"
    }
  }, "Source reports & evidence"), /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, linkedEv.length), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, "click an ID to open")), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      marginBottom: 6,
      lineHeight: 1.45
    }
  }, cit.basis === "promoted" ? subcap ? "The ids the producer cited for this cell (heatmap.cell_evidence)." : `The ids cited by the ${cit.withLists} cell${cit.withLists === 1 ? "" : "s"} in this category that promoted a citation list.` : `The run promoted no citation list for this ${subcap ? "cell" : "category"}; these are the evidence items the run links to ${subcap ? "it" : "its cells"}.`), linkedEv.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "co co-org",
    style: {
      marginBottom: 0
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "warn",
    size: 13
  }), /*#__PURE__*/React.createElement("div", {
    className: "co-body"
  }, "No evidence item directly cites this ", subcap ? "subcap" : "category", " in this run \u2014 the score is inferred. Treat as provisional until corroborated.")) : linkedEv.map(e => {
    // A cited id that resolves to nothing in the evidence store is
    // shown as unresolved, not dropped: a dangling citation is a
    // finding, and silently omitting it hides it.
    if (!e.resolved) {
      return /*#__PURE__*/React.createElement("div", {
        key: e.id,
        className: "card-tile",
        style: {
          width: "100%",
          padding: 11,
          marginBottom: 6
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          gap: 6
        }
      }, /*#__PURE__*/React.createElement("span", {
        className: "chip"
      }, e.id), /*#__PURE__*/React.createElement("span", {
        className: "b b-org"
      }, "UNRESOLVED")), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 11,
          color: "var(--z-muted)",
          marginTop: 4
        }
      }, "Cited for this cell but not present in this run's evidence store."));
    }
    const tier = DMA.getTier(e.tier);
    // title and source_pretty are both `source_name` for most rows, so
    // every row printed the same string twice. Show the source only
    // when it says something the title does not.
    const showSource = e.source_pretty && e.source_pretty !== e.title;
    return /*#__PURE__*/React.createElement("button", {
      key: e.id,
      className: "card-tile clickable",
      style: {
        width: "100%",
        padding: 11,
        marginBottom: 6,
        textAlign: "left"
      },
      onClick: () => openEvidence(e.id)
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 4,
        gap: 6
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: `tier-chip tier-${e.tier}`
    }, e.id), /*#__PURE__*/React.createElement("span", {
      className: "b b-muted",
      title: tier?.label
    }, [e.tier, e.claim].filter(Boolean).join(" · ")), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, e.recency)), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        fontWeight: 600,
        color: "var(--z-dark)"
      },
      className: "txt-fit-1"
    }, e.title), showSource ? /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 5,
        marginTop: 3
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "drive",
      size: 10,
      style: {
        color: "var(--z-muted)"
      }
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10.5,
        color: "var(--z-mid)",
        fontWeight: 500
      },
      className: "txt-fit-1"
    }, e.source_pretty)) : null, e.excerpt ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-body)",
        lineHeight: 1.5,
        marginTop: 6,
        paddingLeft: 8,
        borderLeft: "2px solid var(--z-sep)",
        fontStyle: "italic"
      }
    }, "\u201C", e.excerpt, "\u201D") : null);
  })), linkedIC.length > 0 ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: ".1em",
      color: "var(--z-muted)",
      textTransform: "uppercase",
      marginBottom: 8
    }
  }, "Linked insight cards \xB7 ", linkedIC.length), linkedIC.map(ic => /*#__PURE__*/React.createElement("button", {
    key: ic.id,
    className: "card-tile clickable",
    style: {
      width: "100%",
      padding: 11,
      marginBottom: 6,
      textAlign: "left"
    },
    onClick: () => openInsight(ic.id)
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "ic-id"
  }, ic.id), /*#__PURE__*/React.createElement("span", {
    className: `b ${ic.flag === "CRITICAL" ? "b-below" : ic.flag === "OPPORTUNITY" ? "b-org" : "b-teal"}`
  }, ic.flag)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      fontWeight: 600
    },
    className: "txt-fit-1"
  }, ic.title)))) : null, subcap ? (() => {
    const cell = DMA.cellEvidenceFor(subcap.id);
    const body = cell && (cell.synthesis || cell.narrative || cell.rationale);
    return /*#__PURE__*/React.createElement("div", {
      className: "card-tile",
      style: {
        marginBottom: 4,
        background: "var(--ph0-lt)",
        border: "1px solid var(--ph0-bd)",
        padding: 12
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 6,
        gap: 6
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "evidence",
      size: 13,
      style: {
        color: "var(--z-dpur)"
      }
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        fontWeight: 700,
        color: "var(--z-dpur)",
        letterSpacing: ".08em",
        textTransform: "uppercase"
      }
    }, "Cell synthesis"), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), cell && (cell.e_ids || []).length ? /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 9.5,
        color: "var(--z-dpur)",
        opacity: .85
      }
    }, cell.e_ids.length, " cited") : null), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12.5,
        color: "#3B0764",
        lineHeight: 1.6
      }
    }, body ? body : subcap.thin ? `Evidence is thin (${subcap.evidence_count} of 3). The workbook score stands and the cell carries a dashed outline; the run did not write a synthesis for it.` : "The run promoted no synthesis for this cell."), cell && cell.closure_condition ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-dpur)",
        marginTop: 6
      }
    }, "Closes on: ", cell.closure_condition) : null);
  })() : null), /*#__PURE__*/React.createElement("div", {
    className: "drawer-foot"
  }, subcap ? /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => {
      // Only what the run states. This used to copy "peer median —" for
      // every cell, which reads as a stated median of nothing.
      const bits = [subcap.score != null ? `Score ${fx(subcap.score, 1)}` : "no score stated", subcap.confidence ? `confidence ${subcap.confidence}` : null, subcap.peerMedian != null ? `peer median ${fx(subcap.peerMedian, 1)}` : peerIsProxy ? `peer median ${fx(peer, 1)} (${catId} category proxy)` : "no peer median stated"].filter(Boolean);
      const text = `${subcap.name || subcap.id} (${subcap.id})\n${bits.join(" · ")}.`;
      try {
        navigator.clipboard.writeText(text);
      } catch (e) {}
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "copy",
    size: 13
  }), " Copy synthesis") : /*#__PURE__*/React.createElement("span", null), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: onClose
  }, "Close"))));
}
function IssueRegisterBanner({
  entity,
  onSubcap,
  openEvidence
}) {
  /* Every promoted issue, with its promoted status printed. This filtered on
     `status === "OPEN"` — a value the register does not use (this run states
     ACTIVE, NEW OBLIGATION and REMEDIATED) — so the whole banner vanished while
     the cells beneath it carried issue markers, and the page contradicted
     itself. Classifying a promoted status as open or closed is a judgement the
     run has not made, so the row shows what it says. */
  const issues = DMA.ISSUES || [];
  const [open, setOpen] = useState(null);
  if (issues.length === 0) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 12,
      padding: 14,
      background: "rgba(254,151,50,.06)",
      border: "1px solid rgba(254,151,50,.28)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "warn",
    size: 14,
    style: {
      color: "var(--z-org)"
    }
  }), /*#__PURE__*/React.createElement("strong", {
    style: {
      fontSize: 13,
      color: "var(--z-dark)"
    }
  }, "Issue register \xB7 ", issues.length, " issue", issues.length === 1 ? "" : "s"), /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, "click an issue to drill in"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("a", {
    href: `#/clients/${entity.id}/context`,
    style: {
      fontSize: 11,
      color: "var(--z-mid)",
      fontWeight: 600
    }
  }, "Full register \u2192")), /*#__PURE__*/React.createElement("div", {
    className: "g2",
    style: {
      gap: 8
    }
  }, issues.map(iss => {
    const caps = Object.entries(DMA.ISSUE_CAPS[iss.id]?.caps || {});
    const capped = caps.filter(([, cap]) => cap != null).length;
    const isOpen = open === iss.id;
    // Evidence for the CAPPED cells. Matching on a 4-char prefix meant
    // "anything citing any cell in the same category", so an item that has
    // nothing to do with the issue was listed as its evidence.
    const cappedIds = new Set(caps.map(([cid]) => cid));
    const ev = DMA.EVIDENCE.filter(e => e.subcaps && e.subcaps.some(sid => cappedIds.has(sid)));
    return /*#__PURE__*/React.createElement("div", {
      key: iss.id,
      className: "card-tile",
      style: {
        padding: 0,
        background: "#fff",
        gridColumn: isOpen ? "1 / -1" : "auto",
        overflow: "hidden"
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setOpen(o => o === iss.id ? null : iss.id),
      style: {
        width: "100%",
        background: "none",
        border: 0,
        cursor: "pointer",
        textAlign: "left",
        padding: 10
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 6,
        gap: 6
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip"
    }, iss.id), iss.title || iss.type ? /*#__PURE__*/React.createElement("span", {
      className: "b b-muted txt-fit-1"
    }, iss.title || iss.type) : null, iss.severity ? /*#__PURE__*/React.createElement("span", {
      className: `b ${iss.severity === "CRITICAL" ? "b-below" : iss.severity === "MATERIAL" ? "b-org" : "b-muted"}`
    }, iss.severity) : null, /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), capped ? /*#__PURE__*/React.createElement(Icon, {
      name: "lock",
      size: 11,
      style: {
        color: "var(--z-org)"
      }
    }) : null, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, capped ? `caps ${capped}` : `${caps.length} cell${caps.length === 1 ? "" : "s"} linked`), /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-u" : "chevron-d",
      size: 13,
      style: {
        color: "var(--z-muted)"
      }
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-dark)",
        lineHeight: 1.5
      },
      className: isOpen ? "" : "txt-fit-2"
    }, iss.desc)), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        padding: "0 10px 10px"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 12,
        fontSize: 11,
        color: "var(--z-muted)",
        marginBottom: 8,
        flexWrap: "wrap"
      }
    }, iss.status ? /*#__PURE__*/React.createElement("span", null, "Status ", /*#__PURE__*/React.createElement("strong", {
      style: {
        color: "var(--z-org)"
      }
    }, iss.status)) : null, iss.cap_value != null ? /*#__PURE__*/React.createElement("span", null, "Cap ", /*#__PURE__*/React.createElement("strong", {
      style: {
        color: "var(--z-dark)"
      }
    }, "M", iss.cap_value)) : /*#__PURE__*/React.createElement("span", null, "no cap level stated"), iss.start ? /*#__PURE__*/React.createElement("span", null, "Since ", /*#__PURE__*/React.createElement("strong", {
      style: {
        color: "var(--z-dark)"
      }
    }, iss.start)) : /*#__PURE__*/React.createElement("span", null, "undated"), iss.end ? /*#__PURE__*/React.createElement("span", null, "Resolved ", iss.end) : null), caps.length ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        marginBottom: 4
      }
    }, capped ? "Capped subcaps · click to drill" : "Subcaps linked to this issue · click to drill") : null, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        flexWrap: "wrap",
        gap: 4,
        marginBottom: ev.length ? 10 : 0
      }
    }, caps.map(([sid, cap]) => {
      const subcap = entity.subcaps.find(s => s.id === sid);
      return /*#__PURE__*/React.createElement("button", {
        key: sid,
        className: "chip purple",
        onClick: () => subcap && onSubcap(subcap),
        title: `${subcap?.name || sid}${cap != null ? ` · capped at M${cap}` : " · linked; no cap level stated"}`
      }, sid, cap != null ? ` · M${cap}` : "", subcap ? ` · ${subcap.name}` : "");
    })), ev.length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        marginBottom: 4
      }
    }, "Evidence \xB7 click to open"), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        flexWrap: "wrap",
        gap: 4
      }
    }, ev.map(e => /*#__PURE__*/React.createElement("button", {
      key: e.id,
      className: `tier-chip tier-${e.tier}`,
      style: {
        cursor: "pointer",
        border: 0
      },
      title: `${e.title} · ${e.source_pretty}`,
      onClick: () => openEvidence && openEvidence(e.id)
    }, e.id)))) : null) : null);
  })));
}
function Legend() {
  return /*#__PURE__*/React.createElement("div", {
    className: "row-wrap",
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      gap: 8
    }
  }, [["b-act", "M1"], ["b-bld", "M2"], ["b-cmp", "M3"], ["b-dif", "M4+"]].map(([c, l]) => /*#__PURE__*/React.createElement("span", {
    key: c,
    className: "row",
    style: {
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `b ${c}`,
    style: {
      width: 12,
      height: 12,
      padding: 0,
      borderRadius: 3
    }
  }), l)), /*#__PURE__*/React.createElement("span", {
    className: "row",
    style: {
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 12,
      height: 12,
      border: "2px dashed var(--z-org)",
      borderRadius: 3
    }
  }), " Thin"), /*#__PURE__*/React.createElement("span", {
    className: "row",
    style: {
      gap: 4
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "lock",
    size: 10
  }), " Capped"));
}
function hashCode(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h << 5) - h + s.charCodeAt(i);
  return h;
}
window.hashCode = hashCode;
Object.assign(window, {
  ClientHeatmap
});