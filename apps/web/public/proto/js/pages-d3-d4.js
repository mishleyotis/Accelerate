/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Client page — D4 Platform opportunity
   (heatmap moved to pages-d3-heatmap.jsx)

   THE TILE IS THIS PAGE'S ONE SELECTOR, as it is in the design prototype.
   Every heading below reads "· <the platform you clicked>" and every panel
   under it — gap mapping, readiness, recommendations, starters — is that
   platform's own content.

   Reaching that takes one join, because the run states the platform and the
   recommendation at different grains. An opportunity tile names a PLATFORM and
   the cells it addresses. A recommendation names an L3 PLATFORM AREA and the
   cells it moves. A platform story gap row names an L3 area per cell. Nothing
   anywhere names a platform beside an area, and `platform_story.platforms[]`
   carries no platform name at all.

   So the join runs through the cells, and only through pairings the run itself
   states: every (cell → area) pair named by a recommendation's `dma_impact` or
   a story gap row is indexed, and a tile takes the area its own addressable
   cells are filed under. An exact cell match answers first; where the run
   states an area only for the cell's family (P4C3.4.5 against a stated
   P4C3.4.1) the family answers ONLY if the whole family is filed under one
   area, because a family split across two areas names nothing. A tile whose
   cells resolve to no area scopes nothing, and the page says so rather than
   showing another platform's recommendations under its name. The area is
   printed under every heading it scopes, so a reader can see the join instead
   of trusting it.

   The build before this one made the two grains two independent controls — a
   tile row that expanded a breakdown, and below it a separate "PLATFORM AREA"
   tab strip that scoped everything else. A tile click and the whole page
   beneath it were on different axes, which reads as a dead control on the
   page's most prominent row of cards.
   ═══════════════════════════════════════════════════════════════════════ */

function pfNum(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return isFinite(n) ? n : null;
}

/* Renderable text from a payload value.
   React throws on an object child (#31) and there is no error boundary, so one
   such value blanks the entire application — that is exactly how the
   recommendation drawer takes the page down today (it renders the
   `validation_gate` object raw). Nothing from the payload reaches JSX in this
   file without passing through here: an object is summarised from its own
   naming keys, never printed as JSON, and an unusable value becomes null so the
   surrounding code renders its absent state.

   It also raises the opening letter (`sentence`). Several promoted fields on
   this page are written as fragments — "with plans to increase our member
   base…" — and land under a heading where they read as sentences, so the
   page showed lowercase openings throughout. The connector refuses these at
   submit now, but a run already in the database still has to read properly.
   `sentence` leaves a deliberate lowercase name (nCino) alone. */
function pfText(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "string") return v ? sentence(v) : null;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(pfText).filter(Boolean).join(" · ") || null;
  if (typeof v === "object") {
    for (const k of ["statement", "text", "label", "name", "title", "value"]) {
      const t = pfText(v[k]);
      if (t) return t;
    }
    return null;
  }
  return String(v);
}

/* Evidence chips for a promoted id list.
   Fail-closed on evidence (invariant 4): an id that does not resolve in the
   run's served evidence renders as an unresolved token and is NOT clickable —
   a chip that opens an empty drawer reads as evidence that exists. */
function PlatformEvChips({
  ids,
  openEvidence,
  label
}) {
  const list = (ids || []).filter(Boolean);
  if (!list.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      flexWrap: "wrap",
      gap: 4,
      alignItems: "center"
    }
  }, label ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      color: "var(--z-muted)",
      letterSpacing: ".06em",
      textTransform: "uppercase"
    }
  }, label) : null, list.map(eid => {
    const e = DMA.getEvidence(eid);
    return e ? /*#__PURE__*/React.createElement("button", {
      key: eid,
      className: `tier-chip tier-${e.tier}`,
      style: {
        cursor: "pointer",
        border: 0
      },
      title: `${e.title || eid} · ${e.source_pretty || ""}`,
      onClick: ev => {
        ev.stopPropagation();
        openEvidence(eid);
      }
    }, eid) : /*#__PURE__*/React.createElement("span", {
      key: eid,
      className: "chip muted",
      title: "cited id - not in this run's served evidence"
    }, eid);
  }));
}

/* ── The scope rule this page now obeys everywhere ───────────────────
   A DERIVED relationship may ORDER content. It must never HIDE it.

   The platform → L3 area mapping under every heading on this page is derived:
   no producer states it, it is read off which cells a tile's own gaps happen
   to name. That is good enough to decide what a reader sees FIRST. It is not
   good enough to decide that promoted, cited content does not exist — and
   that is precisely what four sections were doing. "Conversation starters ·
   0 — 5 promoted across the other areas" was the visible one, reported twice
   by the reader; recommendations, the readiness rail and half the gap table
   failed the same way on any tile whose derived area matched nothing.

   So every scoped section splits its promoted rows in two: the ones the scope
   reaches, first; then this divider, saying in the run's own counts what the
   rest are; then the rest. A section whose payload is non-empty never renders
   a zero. */
function ScopeDivider({
  shown,
  total,
  noun,
  scope
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      margin: "10px 0 8px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      height: 1,
      background: "var(--z-sep)",
      flex: "0 0 14px"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      lineHeight: 1.45
    }
  }, shown, " of ", total, " ", noun, shown === 1 ? "" : "s", scope ? ` in ${scope}` : " could be placed on a platform", " \xB7 the rest of this run's below"), /*#__PURE__*/React.createElement("span", {
    style: {
      height: 1,
      background: "var(--z-sep)",
      flex: 1
    }
  }));
}

/* The cell family a cell id belongs to — P4C3.4.5 → P4C3. Parsing the id is
   not an inference: the catalogue's ids are built this way, and a string that
   is not one yields null rather than a guessed prefix. */
function cellFamilyOf(id) {
  const m = /^(P\d+C\d+)/.exec(String(id || ""));
  return m ? m[1] : null;
}

/* The catalogue's own name for a cell, from the workbook read.
   The opportunity tiles state `name: null` for every addressable cell they
   carry, so a tile that printed only what it states would list five bare ids.
   The workbook row is the run's own scored cell, not an invented label, and a
   cell the run did not score yields null so the caller falls back to the id. */
function cellNameOf(index, id) {
  const row = index && index.get ? index.get(String(id)) : null;
  return row && row.name || null;
}

/* Every (cell → L3 area) pairing THE RUN STATES, indexed at two grains.
   A recommendation files each cell of its `dma_impact` under its own
   `l3_area`; a platform story gap row files its own cell under its `l3_area`.
   Both are statements, so both are indexed; nothing else is.

   The family index exists because the grains do not line up: a tile addresses
   P4C3.4.5 while the recommendations and the story name P4C3.1.1, P4C3.1.2,
   P4C3.2.1, P4C3.4.1 and P4C3.4.3. Reading only exact ids, no tile on this run
   would resolve to any area and the page would scope nothing. A family answer
   is weaker than an exact one, so it is used only where the family carries ONE
   area — a family split across two areas answers nothing at all. */
function cellAreaIndex(recs, storyPlatforms) {
  const exact = new Map();
  const family = new Map();
  const add = (cell, area) => {
    if (!cell || !area) return;
    const id = String(cell);
    if (!exact.has(id)) exact.set(id, new Set());
    exact.get(id).add(area);
    const fam = cellFamilyOf(id);
    if (!fam) return;
    if (!family.has(fam)) family.set(fam, new Set());
    family.get(fam).add(area);
  };
  for (const r of recs || []) {
    for (const im of r.dma_impact || []) add(im && im.subcap_id, r.l3);
  }
  for (const p of storyPlatforms || []) {
    for (const g of p.gaps || []) add(g && g.subcap_id, g && g.l3_area);
  }
  return {
    exact,
    family
  };
}

/* The area one cell is filed under, with the grain that answered.
   `basis` travels with the answer so the surface can say whether the run filed
   this exact cell or only its family. Ambiguity — two areas at either grain —
   returns nothing, because a coin toss between two areas is the invented
   mapping this index exists to avoid. */
function areaOfCell(index, cellId) {
  if (!index || !cellId) return null;
  const exact = index.exact.get(String(cellId));
  if (exact && exact.size === 1) return {
    area: [...exact][0],
    basis: "cell"
  };
  const fam = cellFamilyOf(cellId);
  const byFam = fam ? index.family.get(fam) : null;
  if (byFam && byFam.size === 1) return {
    area: [...byFam][0],
    basis: "family"
  };
  return null;
}

/* The area an opportunity tile scopes: the one its own addressable cells are
   filed under most often. Ties resolve to nothing rather than to whichever
   area Object.entries happened to order first. The vote counts come back with
   the answer so the heading can state how strong the join is. */
function areaOfTile(index, tile) {
  const cells = tile && tile.addressable_cells || [];
  const tally = new Map();
  let exactVotes = 0;
  for (const c of cells) {
    const hit = areaOfCell(index, c && c.subcap_id);
    if (!hit) continue;
    tally.set(hit.area, (tally.get(hit.area) || 0) + 1);
    if (hit.basis === "cell") exactVotes += 1;
  }
  if (!tally.size) return {
    area: null,
    votes: 0,
    of: cells.length,
    exact: 0
  };
  const ranked = [...tally.entries()].sort((a, b) => b[1] - a[1]);
  if (ranked.length > 1 && ranked[0][1] === ranked[1][1]) {
    return {
      area: null,
      votes: 0,
      of: cells.length,
      exact: 0,
      tied: true
    };
  }
  return {
    area: ranked[0][0],
    votes: ranked[0][1],
    of: cells.length,
    exact: exactVotes
  };
}

/* The L3 areas this run promoted, earliest roadmap phase first. Used only to
   report what the tile row does NOT reach — an area carrying recommendations
   that no promoted tile addresses would otherwise vanish from the page. */
function platformAreasOf(recs, storyPlatforms) {
  const order = [];
  const seen = {};
  const add = (area, phase) => {
    if (!area) return;
    if (seen[area] === undefined) {
      seen[area] = order.length;
      order.push({
        area,
        phase
      });
    } else if (phase != null) {
      const cur = order[seen[area]];
      if (cur.phase == null || Number(phase) < Number(cur.phase)) cur.phase = phase;
    }
  };
  for (const r of recs || []) add(r.l3, r.phase);
  for (const p of storyPlatforms || []) {
    for (const g of p.gaps || []) add(g.l3_area, null);
  }
  return order.slice().sort((a, b) => (pfNum(a.phase) === null ? 99 : Number(a.phase)) - (pfNum(b.phase) === null ? 99 : Number(b.phase))).map(x => x.area);
}

/* One place where the tile axis and the area axis meet, so the three surfaces
   that need the join (the page, the ladder, the roadmap) compute it the same
   way instead of three slightly different ways. Pure: it reads the promoted
   sections through DMA and holds no state. */
function platformScopeOf(entityId) {
  const recs = DMA.recsFor(entityId) || [];
  const story = DMA.platformStoryFor(entityId) || null;
  const opportunity = DMA.opportunityFor(entityId) || null;
  const storyPlatforms = story && story.platforms || [];
  const index = cellAreaIndex(recs, storyPlatforms);
  const tiles = (opportunity && opportunity.tiles || []).slice().sort((a, b) => (pfNum(a.rank) === null ? 99 : Number(a.rank)) - (pfNum(b.rank) === null ? 99 : Number(b.rank)));
  const assign = new Map(); // tile key → {area, votes, of, exact}
  const platformOfArea = new Map();
  tiles.forEach((t, i) => {
    const key = pfText(t.platform) || `tile-${i + 1}`;
    const a = areaOfTile(index, t);
    assign.set(key, a);
    // First tile to claim an area owns it: the tiles arrive ranked, so the
    // higher-ranked platform is the one a rung or a phase names.
    if (a.area && !platformOfArea.has(a.area)) platformOfArea.set(a.area, key);
  });
  return {
    recs,
    story,
    opportunity,
    storyPlatforms,
    tiles,
    index,
    assign,
    platformOfArea,
    areas: platformAreasOf(recs, storyPlatforms),
    keyOf: (t, i) => pfText(t.platform) || `tile-${i + 1}`
  };
}

/* One readiness row per DISTINCT prerequisite across the selected area's
   recommendations, carrying which of them require it.

   Two things were wrong before. Every prerequisite of every recommendation was
   listed regardless of area (sixteen rows under one platform heading), and the
   list was keyed by `q.cell || q.condition` — so the five recommendations that
   each require P4C3 produced five rows with the same React key and one shared
   open state: clicking any of them expanded all five.

   A cell threshold and a text condition are different shapes, so they are kept
   apart here rather than flattened into one row that renders the same string
   twice. P4C3 ≥ 2.0 and P4C3 ≥ 2.5 are DIFFERENT prerequisites with different
   verdicts, so the key carries the minimum — deduping on the cell alone would
   silently drop the stricter of the two. */
function areaPrereqs(recs) {
  const byKey = new Map();
  for (const r of recs || []) {
    for (const q of r.prerequisites || []) {
      if (!q || typeof q !== "object") continue;
      const cell = q.cell || null;
      const cond = q.condition || null;
      if (!cell && !cond) continue;
      const min = pfNum(q.minimum);
      const key = cell ? `cell:${cell}:${min === null ? "" : min}` : `cond:${cond}`;
      const row = byKey.get(key) || {
        key,
        kind: cell ? "cell" : "condition",
        cell,
        condition: cond,
        min,
        current: pfNum(q.current),
        verdict: q.verdict || null,
        basis: q.basis || null,
        note: q.note || null,
        recs: []
      };
      if (!row.recs.includes(r.id)) row.recs.push(r.id);
      byKey.set(key, row);
    }
  }
  return [...byKey.values()].sort((a, b) => a.kind === b.kind ? 0 : a.kind === "cell" ? -1 : 1);
}

/* MET / NOT MET as the run states it. The verdict used to be collapsed to a
   boolean and re-labelled "PARTIAL", which is a word no payload contains — the
   run says "NOT MET". Where no verdict was stated but both figures were, the
   comparison is computed and marked as computed. */
function prereqVerdict(p) {
  if (p.verdict) return {
    text: String(p.verdict),
    met: String(p.verdict).toUpperCase() === "MET",
    computed: false
  };
  if (p.min !== null && p.current !== null) {
    const met = p.current >= p.min;
    return {
      text: met ? "MET" : "NOT MET",
      met,
      computed: true
    };
  }
  return null;
}

/* ── D4 Platform opportunity ──────────────────────────────────────── */
function ClientPlatform({
  entity,
  run
}) {
  const route = useRoute();
  // `audience` decides what an empty field is allowed to say: a customer is
  // told the assessment did not establish it, an internal reader is told it is
  // queued for enrichment. Nothing on this page may print a bare em dash.
  const {
    audience,
    setIpSurface,
    setIpContext,
    setIpOpen,
    openEvidence,
    openRec,
    openSubcap,
    pushToast
  } = useApp();
  const scope = platformScopeOf(entity.id);
  const {
    recs,
    story,
    opportunity,
    storyPlatforms,
    tiles,
    index,
    assign
  } = scope;
  const tileKeys = tiles.map((t, i) => scope.keyOf(t, i));

  /* A route parameter selects a tile only where the run promoted that
     platform: a stale link must not select a tile that does not exist and
     blank every panel below it. Links written against the previous build
     carry an L3 AREA rather than a platform name, so an area is accepted too
     and resolves to the tile that scopes it. */
  const routeParam = route.params.platform || null;
  const routeKey = routeParam ? tileKeys.find(k => String(k).toLowerCase() === String(routeParam).toLowerCase()) || scope.platformOfArea.get(routeParam) || null : null;
  const [pickedKey, setPickedKey] = useState(routeKey);
  const selKey = tileKeys.includes(pickedKey) ? pickedKey : tileKeys[0] || null;
  const tile = tileKeys.indexOf(selKey) >= 0 ? tiles[tileKeys.indexOf(selKey)] : null;
  const assignment = assign.get(selKey) || {
    area: null,
    votes: 0,
    of: 0,
    exact: 0
  };
  const area = assignment.area;
  const [openPrereq, setOpenPrereq] = useState(null);
  const [openTile, setOpenTile] = useState(null);
  const [openStarter, setOpenStarter] = useState(null);
  const [showDiscarded, setShowDiscarded] = useState(false);
  useEffect(() => {
    setIpSurface("platform_story");
    setIpContext({
      entity,
      platform: selKey
    });
  }, [selKey, entity?.id]);

  /* Selecting a platform replaces every row beneath it, so a row left open on
     the previous platform must not stay open at the same index in the new
     list — that is how one prerequisite's detail ends up under another's. */
  const selectTile = key => {
    setPickedKey(key);
    setOpenPrereq(null);
    setOpenStarter(null);
  };

  // The workbook read, indexed once. It answers for the catalogue's own cell
  // name and pillar where a promoted row states neither — the tile's
  // addressable cells carry `name: null` on every run seen so far.
  const cellIndex = new Map((entity.subcaps || []).map(s => [String(s.id), s]));
  const evidenceByCell = new Map();
  for (const e of DMA.EVIDENCE || []) {
    for (const sid of e.subcaps || []) {
      const k = String(sid);
      if (!evidenceByCell.has(k)) evidenceByCell.set(k, []);
      evidenceByCell.get(k).push(e.id);
    }
  }
  const byPhaseThenId = (a, b) => String(a.phase || "").localeCompare(String(b.phase || "")) || String(a.id).localeCompare(String(b.id));
  const areaRecs = recs.filter(r => area && r.l3 === area).sort(byPhaseThenId);
  // Everything else the run promoted, in the same order. It is NOT dropped:
  // see the scope note below.
  const otherRecs = recs.filter(r => !(area && r.l3 === area)).sort(byPhaseThenId);

  /* The gap-to-platform mapping for the selected tile, from the two places the
     run states one. The platform story's rows are richest — they carry the
     cell's name, its pillar, the L4 feature, the catalogue path, a peer basis
     and the evidence — so they lead; the tile's own addressable cells follow,
     minus any the story already listed.
      The tile's cells are this platform's because the tile SAYS so. The story
     rows are this platform's because their L3 area matches the area this page
     DERIVED for the tile — so the second group is scoped on an inference and
     is ordered by it, never hidden by it (see the scope note below). */
  const storyAll = [];
  for (const p of storyPlatforms) for (const g of p.gaps || []) if (g) storyAll.push(g);
  const inThisArea = g => !!area && g.l3_area === area;
  const storyRows = storyAll.filter(inThisArea);
  const storyElsewhere = storyAll.filter(g => !inThisArea(g));
  const storySeen = new Set(storyRows.map(g => String(g.subcap_id)));
  const tileCells = (tile && tile.addressable_cells || []).filter(c => c && !storySeen.has(String(c.subcap_id)));
  const storyGapRow = (g, scoped) => ({
    key: `story:${g.subcap_id}`,
    from: "story",
    scoped,
    subcap_id: g.subcap_id,
    name: g.name,
    pillar: g.pillar,
    current: pfNum(g.current_score),
    peer: pfNum(g.peer_score),
    peer_note: g.peer_note || null,
    peer_basis: g.peer_basis || null,
    feature: g.l4_feature,
    path: g.catalogue_path,
    e_ids: g.e_ids || [],
    l3_area: g.l3_area || null
  });
  const scopedGapRows = [...storyRows.map(g => storyGapRow(g, true)), ...tileCells.map(c => ({
    key: `tile:${c.subcap_id}`,
    from: "tile",
    scoped: true,
    subcap_id: c.subcap_id,
    name: c.name,
    pillar: null,
    current: pfNum(c.current),
    peer: pfNum(c.peer),
    peer_note: null,
    peer_basis: null,
    feature: c.feature_that_addresses_it,
    path: null,
    e_ids: [],
    l3_area: null
  }))];
  // A cell already on this platform's own rows is not repeated below the
  // divider — the same cell twice in one table reads as two findings.
  const scopedSeen = new Set(scopedGapRows.map(g => String(g.subcap_id)));
  const otherGapRows = storyElsewhere.filter(g => !scopedSeen.has(String(g.subcap_id))).map(g => storyGapRow(g, false));
  const gapRows = [...scopedGapRows, ...otherGapRows];
  // Only render the gap column where at least one row can state a difference.
  // Before, every row printed "−-2.5": a unary minus prepended to an already
  // negative difference, computed against a peer median that does not exist
  // for these cells.
  const anyPeer = gapRows.some(g => g.peer !== null);
  const gapCols = anyPeer ? 7 : 6;
  const prereqRows = areaPrereqs(areaRecs);
  /* Readiness gates come from the recommendations, so a platform the scope
     reaches no recommendation for used to show an empty rail. The gates of
     every other promoted recommendation are the same run's gates; they are
     listed after this platform's, under the same divider rule. */
  const otherPrereqRows = areaPrereqs(otherRecs).filter(p => !prereqRows.some(q => q.key === p.key));

  /* Conversation starters carry a named gap cell, and where that cell is one
     the run files under an L3 area, the starter belongs to a platform on the
     same evidence everything else on this page does.
      Where it is NOT — and on this run it never is — the starter is scoped to
     nothing and shows under every platform, exactly as one naming no cell
     does, because it makes no platform-specific claim this page can honour.
     That distinction is the whole defect the card showed: this run states
     `named_gap_subcap_id` as "Technology Architecture & Integration.1.2" —
     a category NAME with a numeric tail, not a catalogue id of the P4C3.4.5
     shape that `areaOfCell` indexes and that every other cell reference in
     the run uses. The old predicate asked only whether the value was truthy,
     so all five starters failed the area comparison on all four tiles and
     the card read "Conversation starters · 0" everywhere, with the "promoted
     across the other areas" note pointing at areas that do not exist. A
     starter this page cannot place must be shown, not hidden: an unplaceable
     one is still the producer's promoted talking point.
      The name is left as the run wrote it rather than mapped onto a category —
     "Technology Architecture & Integration" is not any catalogue category's
     name ("Tech Architecture" is), so a match would be a guess, and this app
     does not guess about identity. */
  const allStarters = (DMA.startersFor ? DMA.startersFor(entity.id) || [] : []).slice().sort((a, b) => (pfNum(a.rank) === null ? 99 : Number(a.rank)) - (pfNum(b.rank) === null ? 99 : Number(b.rank)));
  const starterArea = s => {
    const hit = areaOfCell(index, s && s.named_gap_subcap_id);
    return hit ? hit.area : null;
  };
  // In scope: this platform's area, or no area at all. Out of scope: filed
  // under another platform's area — ordered after, never dropped.
  const scopedStarters = allStarters.filter(s => {
    const a = starterArea(s);
    return a === null || a === area;
  });
  const otherStarters = allStarters.filter(s => scopedStarters.indexOf(s) < 0);
  const starters = [...scopedStarters, ...otherStarters];
  // Counted, not asserted: how many of what is showing this page could place
  // on THIS platform, so the card can say which part of the list a reader is
  // looking at instead of implying every one of them is this platform's.
  const placedStarters = scopedStarters.filter(s => starterArea(s) === area && area).length;
  const unplacedStarters = scopedStarters.length - placedStarters;

  // "Why not X" — the platform page's own discarded list where it promoted
  // one, otherwise the overview's. Never both merged: the two sections word
  // the same decision differently and a merge would show one platform twice
  // with conflicting reasons.
  const discarded = (story && story.discarded || []).length ? story.discarded : opportunity && opportunity.discarded || [];

  // Areas the tile row cannot reach. A recommendation filed under one of these
  // appears under no platform, so it is named rather than silently dropped.
  const reachable = new Set([...assign.values()].map(a => a.area).filter(Boolean));
  const orphanRecs = recs.filter(r => !r.l3 || !reachable.has(r.l3));
  const orphanAreas = [];
  for (const r of orphanRecs) if (r.l3 && !orphanAreas.includes(r.l3)) orphanAreas.push(r.l3);
  const scopeLine = area ? `${area} · the area this run files ${assignment.votes} of ${assignment.of} of this platform's cells under` : tile ? "This run files none of this platform's cells under an L3 area, so nothing below is scoped to it." : "No platform tile promoted for this run.";
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "page-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, "Platform opportunity"), /*#__PURE__*/React.createElement("h1", null, "Platform Fit Score"), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, "Which platform conversation should lead with ", entity.name, "?")), /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast(`Exporting ${entity.name} roadmap as PDF…`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Roadmap export"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: () => {
      setIpSurface("platform_story");
      setIpContext({
        entity,
        platform: selKey
      });
      setIpOpen(true);
    }
  }, "\u2726 Platform story"))), tiles.length ?
  /*#__PURE__*/
  /* alignItems start: an expanded breakdown stretches its grid row, and
     the collapsed tiles beside it grew to match, leaving a block of
     empty card. */
  React.createElement("div", {
    className: tiles.length === 5 ? "g5" : "g4",
    style: {
      alignItems: "start",
      marginBottom: 16
    }
  }, tiles.map((t, i) => {
    // Keyed by the PROMOTED platform string. The vendor-alias fold this
    // replaced collapsed "Salesforce Data Cloud" and "Service Cloud
    // consolidation" onto one key and destroyed a tile.
    const key = scope.keyOf(t, i);
    const isSel = key === selKey;
    const isOpen = openTile === key;
    const a = assign.get(key) || {
      area: null,
      votes: 0,
      of: 0
    };
    const cells = (t.addressable_cells || []).filter(Boolean);
    const composite = pfNum(t.composite);
    const tileRecs = a.area ? recs.filter(r => r.l3 === a.area).length : 0;
    /* "Top:" names the cells this platform addresses, in the
       catalogue's own words. The tile states `name: null` for every
       one of them, so the name comes from the workbook read and the id
       stands in where the run does not carry that cell. */
    const top = cells.slice(0, 3).map(c => pfText(c.name) || cellNameOf(cellIndex, c.subcap_id) || pfText(c.subcap_id)).filter(Boolean);
    return (
      /*#__PURE__*/
      /* A click on an unselected tile scopes the page to it. A click on
         the tile ALREADY selected has nothing left to scope, so it
         opens that tile's own breakdown rather than doing nothing —
         the QA sweep reads a click that changes no DOM as a dead
         control, and on the page's most prominent card it reads that
         way to a person too. */
      React.createElement("div", {
        key: key,
        className: "card-tile clickable",
        title: isSel ? isOpen ? "Hide the composite breakdown" : "Show the composite breakdown" : `Scope this page to ${key}`,
        onClick: () => {
          if (isSel) setOpenTile(o => o === key ? null : key);else selectTile(key);
        },
        style: {
          border: isSel ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)",
          background: isSel ? "var(--z-ice)" : "#fff"
        }
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 8
        }
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          minWidth: 0
        }
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 12.5,
          fontWeight: 600,
          lineHeight: 1.3
        }
      }, t.rank != null ? /*#__PURE__*/React.createElement("span", {
        className: "b b-purple",
        style: {
          marginRight: 5
        }
      }, "#", pfText(t.rank)) : null, pfText(t.platform) || "Platform not named"), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 9.5,
          color: "var(--z-muted)",
          marginTop: 2,
          lineHeight: 1.4
        },
        className: "txt-fit-2"
      }, a.area || "No L3 area stated for these cells")), /*#__PURE__*/React.createElement("div", {
        style: {
          textAlign: "right",
          flexShrink: composite === null ? 1 : 0,
          minWidth: 0
        }
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: composite === null ? 11.5 : 26,
          fontWeight: composite === null ? 400 : 200,
          color: composite === null ? "var(--z-muted)" : "var(--z-teal)",
          lineHeight: 1.15
        }
      }, composite === null ? /*#__PURE__*/React.createElement(EnrichmentGap, {
        what: "Platform fit score",
        audience: audience,
        compact: true
      }) : composite.toFixed(1)), /*#__PURE__*/React.createElement("div", {
        className: "f-mono",
        style: {
          fontSize: 9,
          color: "var(--z-muted)"
        }
      }, "/100 fit"))), /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          marginTop: 10,
          gap: 4,
          fontSize: 11,
          flexWrap: "wrap"
        }
      }, /*#__PURE__*/React.createElement("span", {
        className: "b b-org"
      }, cells.length, " cell", cells.length === 1 ? "" : "s"), a.area ? /*#__PURE__*/React.createElement("span", {
        className: "b b-muted"
      }, tileRecs, " rec", tileRecs === 1 ? "" : "s") : null), top.length ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10,
          color: "var(--z-muted)",
          marginTop: 6,
          lineHeight: 1.45
        },
        className: "txt-fit-2"
      }, "Top: ", top.join(" · ")) : null, /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          marginTop: 8,
          fontSize: 10,
          color: "var(--z-mid)"
        }
      }, /*#__PURE__*/React.createElement("span", {
        className: "spacer"
      }), /*#__PURE__*/React.createElement("button", {
        className: "btn btn-tertiary btn-sm",
        style: {
          color: "var(--z-mid)"
        },
        title: isOpen ? "Hide the composite breakdown" : "Show the composite breakdown",
        onClick: ev => {
          ev.stopPropagation();
          setOpenTile(o => o === key ? null : key);
        }
      }, isOpen ? "Hide breakdown" : "Breakdown", /*#__PURE__*/React.createElement(Icon, {
        name: isOpen ? "chevron-u" : "chevron-d",
        size: 12
      }))), isOpen ? /*#__PURE__*/React.createElement("div", {
        style: {
          marginTop: 8,
          paddingTop: 8,
          borderTop: "1px solid var(--z-sep)"
        }
      }, t.relevance != null ? /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          gap: 5,
          marginBottom: 6
        }
      }, /*#__PURE__*/React.createElement("span", {
        className: "b b-muted f-mono",
        title: "relevance to the assessed gaps"
      }, Number(t.relevance).toFixed(2)), /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 9.5,
          color: "var(--z-muted)"
        }
      }, "relevance")) : null, t.their_stack_context ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10.5,
          color: "var(--z-body)",
          marginBottom: 8,
          lineHeight: 1.5
        }
      }, pfText(t.their_stack_context)) : null, (t.factors || []).length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
        className: "eyebrow",
        style: {
          fontSize: 9,
          marginBottom: 5
        }
      }, "Composite factors"), t.factors.map((f, j) => /*#__PURE__*/React.createElement("div", {
        key: j,
        className: "row",
        style: {
          fontSize: 10,
          gap: 5,
          marginBottom: 3
        }
      }, /*#__PURE__*/React.createElement("span", {
        style: {
          color: "var(--z-muted)",
          width: 78,
          flexShrink: 0
        },
        title: f.weight != null ? `weight ${f.weight}` : ""
      }, String(f.name || "").replace(/_/g, " ")), /*#__PURE__*/React.createElement("div", {
        style: {
          flex: 1,
          minWidth: 0
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "prog",
        style: {
          height: 4
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "prog-fill",
        style: {
          width: `${Math.max(0, Math.min(100, (pfNum(f.value) || 0) * 10))}%`
        }
      }))), f.contribution != null ? /*#__PURE__*/React.createElement("span", {
        className: "f-mono",
        style: {
          fontSize: 9,
          color: "var(--z-muted)",
          width: 34,
          textAlign: "right",
          flexShrink: 0
        },
        title: "contribution to the composite"
      }, "+", Number(f.contribution).toFixed(1)) : null))) : null, cells.length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
        className: "eyebrow",
        style: {
          fontSize: 9,
          margin: "8px 0 5px"
        }
      }, "Cells it addresses"), /*#__PURE__*/React.createElement("div", {
        style: {
          display: "grid",
          gap: 4
        }
      }, cells.map((c, j) => {
        const sid = pfText(c.subcap_id);
        return /*#__PURE__*/React.createElement("div", {
          key: j,
          className: "row",
          style: {
            gap: 5,
            fontSize: 10,
            alignItems: "flex-start"
          }
        }, sid ? /*#__PURE__*/React.createElement("button", {
          className: "chip f-mono",
          style: {
            fontSize: 9,
            flexShrink: 0
          },
          title: `Open ${sid} in the heatmap`,
          onClick: ev => {
            ev.stopPropagation();
            openSubcap(sid);
          }
        }, sid) : null, pfNum(c.current) !== null ? /*#__PURE__*/React.createElement(MaturityChip, {
          score: pfNum(c.current)
        }) : null, /*#__PURE__*/React.createElement("span", {
          style: {
            flex: 1,
            minWidth: 0,
            color: "var(--z-body)",
            lineHeight: 1.45
          }
        }, pfText(c.feature_that_addresses_it) || pfText(c.name) || ""));
      }))) : null, t.rank_rationale ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10.5,
          color: "var(--z-body)",
          marginTop: 8,
          lineHeight: 1.55
        }
      }, pfText(t.rank_rationale)) : null) : null)
    );
  })) : /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16,
      fontSize: 12,
      color: "var(--z-muted)"
    }
  }, "The opportunity surface did not promote for this run, so no platform fit score is available."), /*#__PURE__*/React.createElement("div", {
    id: "platform-area-detail",
    style: {
      display: "flex",
      flexWrap: "wrap",
      alignItems: "flex-start",
      gap: 16,
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    style: {
      flex: "999 1 560px",
      minWidth: 0,
      maxWidth: "100%"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("h3", null, "Gap-to-platform mapping \xB7 ", selKey || "no platform promoted"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 2,
      lineHeight: 1.45
    }
  }, scopeLine)), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      flexShrink: 0,
      textAlign: "right"
    }
  }, scopedGapRows.length, " mapped cell", scopedGapRows.length === 1 ? "" : "s", storyRows.length && tileCells.length ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 9.5
    }
  }, storyRows.length, " from the story \xB7 ", tileCells.length, " from the tile") : null)), /*#__PURE__*/React.createElement("div", {
    className: "card-body",
    style: {
      padding: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "tbl-reflow"
  }, /*#__PURE__*/React.createElement("table", {
    className: "tbl"
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Cell"), /*#__PURE__*/React.createElement("th", {
    className: "col-drop",
    style: {
      whiteSpace: "nowrap"
    }
  }, "Pillar"), /*#__PURE__*/React.createElement("th", {
    style: {
      whiteSpace: "nowrap"
    }
  }, "Score"), /*#__PURE__*/React.createElement("th", {
    style: {
      whiteSpace: "nowrap"
    }
  }, "Peer"), anyPeer ? /*#__PURE__*/React.createElement("th", {
    style: {
      whiteSpace: "nowrap"
    }
  }, "Gap") : null, /*#__PURE__*/React.createElement("th", null, "Feature / L4"), /*#__PURE__*/React.createElement("th", null, "Evidence"))), /*#__PURE__*/React.createElement("tbody", null, gapRows.map(g => {
    const wb = cellIndex.get(String(g.subcap_id)) || null;
    const name = pfText(g.name) || wb && wb.name || pfText(g.subcap_id);
    const pillar = pfText(g.pillar) || wb && wb.pillar || (/^(P\d+)/.exec(String(g.subcap_id || "")) || [])[1] || null;
    const cur = g.current !== null ? g.current : wb ? pfNum(wb.score) : null;
    const peer = g.peer !== null ? g.peer : wb ? pfNum(wb.peerMedian) : null;
    // Computed-or-null: a delta exists only where both figures do,
    // and it carries its own sign — no minus is prepended.
    const delta = cur !== null && peer !== null ? Math.round((cur - peer) * 100) / 100 : null;
    /* A story row cites its own ids. A tile row cites none, so
       the column falls back to the evidence this run links to
       that cell — two of them, which is what the story rows
       carry, so the rows stay one line tall either way. */
    const eids = g.e_ids.length ? g.e_ids : (evidenceByCell.get(String(g.subcap_id)) || []).slice(0, 2);
    /* Every peer figure on this run is absent with a stated
       reason, so the column carries that reason rather than a
       chip reading "cannot estimate" on all five rows, which
       reads as a verdict on the platform rather than on the peer
       set. */
    const peerWhy = pfText(g.peer_note) || (g.peer_basis ? String(g.peer_basis).replace(/_/g, " ") : wb && wb.peer_basis ? String(wb.peer_basis).replace(/_/g, " ") : "No peer figure is stated for this cell");
    /* A missing peer with a stated basis is HELD, not silent: the
       producer ran the comparison and the figure failed. Tile
       rows carry `peer_basis: null` by construction, so those are
       a real gap and read as one. Guarded on `peer === null`
       because a basis beside a PRESENT peer describes how that
       figure was derived (category_proxy), not why one is
       missing. */
    const peerHeld = peer === null && !!(pfText(g.peer_note) || g.peer_basis || wb && wb.peer_basis);
    // The first row the derived scope does not reach carries the
    // divider; the rows under it are the same run's promoted gap
    // rows, filed under another platform's area.
    const first = !g.scoped && otherGapRows.length && otherGapRows[0].key === g.key;
    return /*#__PURE__*/React.createElement(React.Fragment, {
      key: g.key
    }, first ? /*#__PURE__*/React.createElement("tr", {
      className: "tbl-split"
    }, /*#__PURE__*/React.createElement("td", {
      className: "tbl-split",
      colSpan: gapCols
    }, scopedGapRows.length, " of ", gapRows.length, " mapped cells sit in ", area || "no area this page could derive", " \xB7 the rest of this run's gap rows below")) : null, /*#__PURE__*/React.createElement("tr", {
      style: {
        opacity: g.scoped ? 1 : .78
      }
    }, /*#__PURE__*/React.createElement("td", {
      "data-label": "Cell"
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        fontWeight: 500
      }
    }, name), /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, pfText(g.subcap_id)), !g.scoped && g.l3_area ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        color: "var(--z-muted)",
        marginTop: 2
      }
    }, pfText(g.l3_area)) : null), /*#__PURE__*/React.createElement("td", {
      "data-label": "Pillar",
      className: "col-drop"
    }, pillar ? /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, pillar) : /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: "Pillar",
      audience: audience,
      compact: true
    })), /*#__PURE__*/React.createElement("td", {
      "data-label": "Score"
    }, /*#__PURE__*/React.createElement(MaturityChip, {
      score: cur
    })), /*#__PURE__*/React.createElement("td", {
      "data-label": "Peer"
    }, peer !== null ? /*#__PURE__*/React.createElement(MaturityChip, {
      score: peer
    }) : /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: "Peer score",
      held: peerHeld,
      reason: peerHeld ? peerWhy : undefined,
      audience: audience,
      compact: true
    })), anyPeer ?
    /*#__PURE__*/
    /* The delta is arithmetic, so it carries the state of
       its inputs: held where the peer is held, an ordinary
       gap where a score is simply not stated. The reason
       itself is not repeated here — it is one cell to the
       left and belongs to the figure it explains, not to a
       subtraction. */
    React.createElement("td", {
      "data-label": "Gap"
    }, delta === null ? /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: "Gap to peer",
      held: peerHeld,
      audience: audience,
      compact: true
    }) : /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        color: delta < 0 ? "var(--z-below)" : "var(--z-above)"
      }
    }, delta > 0 ? `+${delta.toFixed(1)}` : delta.toFixed(1))) : null, /*#__PURE__*/React.createElement("td", {
      "data-label": "Feature / L4",
      title: pfText(g.path) || ""
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-dark)"
      }
    }, pfText(g.feature) || /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: "Feature / L4",
      audience: audience,
      compact: true
    }))), /*#__PURE__*/React.createElement("td", {
      "data-label": "Evidence"
    }, /*#__PURE__*/React.createElement(PlatformEvChips, {
      ids: eids,
      openEvidence: openEvidence
    }))));
  }), gapRows.length === 0 ? /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", {
    colSpan: gapCols,
    className: "tbl-empty"
  }, "No platform story gap row and no addressable cell promoted in this run, so there is no gap mapping to show for any platform.")) : null))), storyRows.length ? storyPlatforms.map((p, i) => (p.gaps || []).some(g => g && g.l3_area === area) && pfText(p.story_md) ? /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      padding: "12px 18px",
      borderTop: "1px solid var(--z-sep)",
      fontSize: 12,
      color: "var(--z-body)",
      lineHeight: 1.65
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      fontSize: 9.5,
      marginBottom: 5
    }
  }, "What this platform changes"), pfText(p.story_md)) : null) : null)), /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      flex: "1 1 300px",
      minWidth: 0,
      maxWidth: "100%"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10,
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "shield",
    size: 16
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      flex: 1,
      minWidth: 0
    },
    className: "txt-fit-1",
    title: selKey ? `Readiness · ${selKey}` : ""
  }, "Readiness \xB7 ", selKey || "no platform"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      flexShrink: 0
    }
  }, "click a row to drill in")), [...prereqRows, ...otherPrereqRows].map((p, idx) => {
    const v = prereqVerdict(p);
    const isOpen = openPrereq === idx;
    // The divider rides on the first gate the derived scope does not
    // reach, so a platform whose area matches no recommendation still
    // shows this run's gates rather than an empty rail.
    const split = idx === prereqRows.length && otherPrereqRows.length ? /*#__PURE__*/React.createElement("div", {
      key: "split",
      style: {
        padding: "8px 0 6px",
        borderTop: "1px solid var(--z-sep)",
        fontSize: 10,
        color: "var(--z-muted)",
        lineHeight: 1.5
      }
    }, prereqRows.length, " of ", prereqRows.length + otherPrereqRows.length, " gates belong to ", selKey || "this platform", " \xB7 this run's other gates below") : null;
    if (p.kind === "condition") {
      /* A text condition has no cell, no minimum and no current value,
         so it gets its own row shape — but the SAME height as a
         threshold row. It used to render the condition as a 317px
         badge, its note and its recommendation chips all at once, three
         stacked blocks per row in a 300px column. */
      return /*#__PURE__*/React.createElement(React.Fragment, {
        key: p.key
      }, split, /*#__PURE__*/React.createElement("div", {
        style: {
          borderBottom: "1px solid var(--z-sep)"
        }
      }, /*#__PURE__*/React.createElement("button", {
        onClick: () => setOpenPrereq(o => o === idx ? null : idx),
        title: pfText(p.condition) || "",
        style: {
          width: "100%",
          background: "none",
          border: 0,
          cursor: "pointer",
          textAlign: "left",
          padding: "10px 0"
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          gap: 6,
          marginBottom: 3
        }
      }, /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 9,
          color: "var(--z-muted)",
          letterSpacing: ".06em",
          textTransform: "uppercase",
          flexShrink: 0
        }
      }, "Condition"), /*#__PURE__*/React.createElement("span", {
        className: "spacer"
      }), p.basis ? /*#__PURE__*/React.createElement("span", {
        className: "b b-above",
        style: {
          flexShrink: 0
        }
      }, pfText(p.basis)) : null, /*#__PURE__*/React.createElement(Icon, {
        name: isOpen ? "chevron-u" : "chevron-d",
        size: 13,
        style: {
          color: "var(--z-muted)",
          flexShrink: 0
        }
      })), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 12,
          lineHeight: 1.45
        },
        className: "txt-fit-2"
      }, pfText(p.condition))), isOpen ? /*#__PURE__*/React.createElement("div", {
        style: {
          padding: "0 0 12px"
        }
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 11.5,
          color: "var(--z-dark)",
          lineHeight: 1.5,
          marginBottom: 4
        }
      }, pfText(p.condition)), p.note ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 11,
          color: "var(--z-muted)",
          marginBottom: 5,
          lineHeight: 1.5
        }
      }, pfText(p.note)) : null, /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          gap: 4,
          flexWrap: "wrap"
        }
      }, /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 9,
          color: "var(--z-muted)",
          letterSpacing: ".06em",
          textTransform: "uppercase"
        }
      }, "Required by"), p.recs.map(rid => /*#__PURE__*/React.createElement("button", {
        key: rid,
        className: "chip",
        style: {
          cursor: "pointer",
          border: 0
        },
        title: `Open ${rid}`,
        onClick: () => openRec(rid)
      }, rid)))) : null));
    }
    // Cell threshold. Keyed by index so two thresholds on the same cell
    // cannot share an open state.
    const cat = p.cell ? DMA.getCategory(p.cell) : null;
    const subs = (entity.subcaps || []).filter(s => String(s.id).startsWith(`${p.cell}.`));
    const ev = (DMA.EVIDENCE || []).filter(e => (e.subcaps || []).some(sid => String(sid).startsWith(`${p.cell}.`)));
    const pct = p.min !== null && p.current !== null && p.min > 0 ? Math.max(0, Math.min(100, p.current / p.min * 100)) : null;
    return /*#__PURE__*/React.createElement(React.Fragment, {
      key: p.key
    }, split, /*#__PURE__*/React.createElement("div", {
      style: {
        borderBottom: "1px solid var(--z-sep)"
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setOpenPrereq(o => o === idx ? null : idx),
      style: {
        width: "100%",
        background: "none",
        border: 0,
        cursor: "pointer",
        textAlign: "left",
        padding: "10px 0"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 4,
        gap: 6
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "b b-purple",
      style: {
        flexShrink: 0
      }
    }, pfText(p.cell)), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 12,
        flex: 1,
        minWidth: 0
      },
      className: "txt-fit-1"
    }, cat && cat.name || (p.min === null ? "Threshold not stated" : `Threshold ≥ ${p.min.toFixed(1)}`)), v ? /*#__PURE__*/React.createElement("span", {
      className: `b ${v.met ? "b-above" : "b-org"}`,
      style: {
        flexShrink: 0
      },
      title: v.computed ? "computed from the stated minimum and current value" : "verdict as promoted"
    }, v.text) : null, /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-u" : "chevron-d",
      size: 13,
      style: {
        color: "var(--z-muted)",
        flexShrink: 0
      }
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, p.min === null ? "Min not stated" : `Min ${p.min.toFixed(1)}`, " \xB7 ", p.current === null ? "current not stated" : `Current ${p.current.toFixed(2)}`, " \xB7 ", subs.length, " cells \xB7 ", ev.length, " evidence"), pct !== null ? /*#__PURE__*/React.createElement("div", {
      className: "prog",
      style: {
        marginTop: 4,
        height: 4
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "prog-fill",
      style: {
        width: `${pct}%`,
        background: v && v.met ? "var(--z-mid)" : "var(--z-org)"
      }
    })) : null), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        padding: "2px 0 12px"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 4,
        flexWrap: "wrap",
        marginBottom: 6
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 9,
        color: "var(--z-muted)",
        letterSpacing: ".06em",
        textTransform: "uppercase"
      }
    }, "Required by"), p.recs.map(rid => /*#__PURE__*/React.createElement("button", {
      key: rid,
      className: "chip",
      style: {
        cursor: "pointer",
        border: 0
      },
      title: `Open ${rid}`,
      onClick: () => openRec(rid)
    }, rid))), subs.length ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        margin: "6px 0 4px"
      }
    }, "Backing cells") : null, subs.slice(0, 6).map(s => /*#__PURE__*/React.createElement("div", {
      key: s.id,
      className: "row",
      style: {
        gap: 6,
        padding: "3px 0"
      }
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
        width: 30,
        justifyContent: "center",
        flexShrink: 0
      }
    }, fx(s.score, 1)), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11.5,
        color: "var(--z-dark)",
        flex: 1,
        minWidth: 0
      },
      className: "txt-fit-1"
    }, s.name), /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        fontSize: 9.5,
        color: "var(--z-muted)",
        flexShrink: 0
      }
    }, s.id))), subs.length > 6 ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        marginTop: 3
      }
    }, "+", subs.length - 6, " more cells in ", p.cell) : null, ev.length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        margin: "8px 0 4px"
      }
    }, "Evidence \xB7 click to open"), /*#__PURE__*/React.createElement(PlatformEvChips, {
      ids: ev.slice(0, 12).map(e => e.id),
      openEvidence: openEvidence
    })) : null) : null));
  }), prereqRows.length + otherPrereqRows.length === 0 ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-muted)"
    }
  }, recs.length ? "No recommendation in this run promoted a prerequisite, so no readiness gate applies." : "No recommendation promoted in this run, so no readiness gate applies.") : null, prereqRows.some(p => {
    const v = prereqVerdict(p);
    return v && !v.met;
  }) ? /*#__PURE__*/React.createElement("div", {
    className: "co co-org",
    style: {
      marginTop: 10
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "warn",
    size: 14
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "co-title"
  }, "Advisory"), /*#__PURE__*/React.createElement("div", {
    className: "co-body"
  }, "A threshold here is not met. The unmet prerequisite is the conversation that comes first."))) : null)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 340px), 1fr))",
      gap: 16,
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("h3", null, "Recommendations \xB7 ", selKey || "no platform promoted"), area ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 2
    }
  }, area) : null), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      flexShrink: 0
    }
  }, areaRecs.length, " of ", recs.length, " promoted")), /*#__PURE__*/React.createElement("div", null, [...areaRecs, ...otherRecs].map(r => {
    const gate = r.validation_gate || null;
    const kpi = r.kpi || null;
    const impacts = (r.dma_impact || []).length;
    const scoped = areaRecs.indexOf(r) >= 0;
    // The divider rides on the first row the scope does not reach.
    const first = !scoped && otherRecs.length && otherRecs[0].id === r.id;
    return /*#__PURE__*/React.createElement(React.Fragment, {
      key: r.id
    }, first ? /*#__PURE__*/React.createElement("div", {
      style: {
        padding: "8px 18px",
        background: "var(--z-bg)",
        borderTop: "1px solid var(--z-sep)",
        borderBottom: "1px solid var(--z-sep)",
        fontSize: 10,
        color: "var(--z-muted)",
        lineHeight: 1.5
      }
    }, areaRecs.length, " of ", recs.length, " promoted recommendations sit in ", area || "no area this page could derive for this tile", " \xB7 the rest of this run's below, each still openable") : null, /*#__PURE__*/React.createElement("div", {
      className: "rec-row",
      onClick: () => openRec(r.id),
      title: "Open full recommendation",
      style: {
        padding: "12px 18px",
        borderBottom: "1px solid var(--z-sep)",
        cursor: "pointer",
        opacity: scoped ? 1 : .82
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 4,
        gap: 6,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip"
    }, r.id), /*#__PURE__*/React.createElement("span", {
      style: {
        fontWeight: 600,
        fontSize: 13,
        flex: "1 1 160px",
        minWidth: 0
      }
    }, pfText(r.title)), r.phase != null ? /*#__PURE__*/React.createElement("span", {
      className: "b b-teal",
      style: {
        flexShrink: 0
      }
    }, "Phase ", pfText(r.phase)) : null, r.effort ? /*#__PURE__*/React.createElement("span", {
      className: "b b-muted",
      style: {
        flexShrink: 0
      },
      title: "effort band"
    }, pfText(r.effort)) : null, /*#__PURE__*/React.createElement(Icon, {
      name: "chevron-r",
      size: 13,
      style: {
        color: "var(--z-muted)",
        flexShrink: 0
      }
    })), !scoped && r.l3 ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        marginBottom: 4
      }
    }, pfText(r.l3)) : null, r.l4 ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-mid)",
        marginBottom: 5,
        overflowWrap: "anywhere"
      }
    }, pfText(r.l4)) : null, r.root_cause_text ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        lineHeight: 1.55,
        margin: "6px 0"
      },
      className: "txt-fit-3"
    }, pfText(r.root_cause_text)) : null, /*#__PURE__*/React.createElement(PlatformEvChips, {
      ids: r.root_cause,
      openEvidence: openEvidence,
      label: "cites"
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 150px), 1fr))",
        gap: 8,
        marginTop: 8,
        fontSize: 11
      }
    }, gate && gate.threshold ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "muted",
      style: {
        fontSize: 10
      }
    }, "Readiness gate"), /*#__PURE__*/React.createElement("strong", {
      className: "f-mono",
      style: {
        fontSize: 11
      },
      title: pfText(gate.grain_note) || ""
    }, pfText(gate.threshold)), gate.verdict ? /*#__PURE__*/React.createElement("span", {
      className: `b ${String(gate.verdict).toUpperCase() === "MET" ? "b-above" : "b-org"}`,
      style: {
        marginLeft: 5
      }
    }, pfText(gate.verdict)) : null) : null, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "muted",
      style: {
        fontSize: 10
      }
    }, "Cells it moves"), /*#__PURE__*/React.createElement("strong", null, impacts)), kpi && kpi.metric ?
    /*#__PURE__*/
    /* 1/-1 rather than "span 2": with an auto-fit track count
       the grid may only HAVE one column, and a 2-wide item in
       a 1-wide grid adds an implicit column the row then
       overflows into. 1/-1 is "the whole row", whatever the
       count came out as. */
    React.createElement("div", {
      style: {
        gridColumn: "1 / -1",
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "muted",
      style: {
        fontSize: 10
      }
    }, "KPI"), /*#__PURE__*/React.createElement("strong", {
      style: {
        fontWeight: 500
      }
    }, pfText(kpi.metric)), kpi.baseline ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)",
        marginTop: 2,
        lineHeight: 1.5
      }
    }, "Baseline \xB7 ", pfText(kpi.baseline), kpi.baseline_as_of ? ` · ${kpi.baseline_as_of}` : "") : null, kpi.target ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-mid)",
        marginTop: 2,
        lineHeight: 1.5
      }
    }, "Target \xB7 ", pfText(kpi.target)) : null) : null)));
  }), recs.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, /*#__PURE__*/React.createElement("p", null, "No recommendation promoted in this run.")) : null, orphanAreas.length ? /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "10px 18px",
      fontSize: 11,
      color: "var(--z-muted)",
      borderTop: "1px solid var(--z-sep)",
      lineHeight: 1.6
    }
  }, orphanRecs.length, " of the ", recs.length, " promoted recommendation", recs.length === 1 ? "" : "s", " sit", orphanRecs.length === 1 ? "s" : "", " in an area no promoted platform addresses \u2014 ", orphanAreas.join(" · "), ".") : null)), /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("h3", null, "Conversation starters \xB7 ", starters.length), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 2,
      lineHeight: 1.45
    }
  }, selKey || "no platform promoted", unplacedStarters ? ` · ${unplacedStarters} of ${starters.length} name${unplacedStarters === 1 ? "s" : ""} no cell this run files under a platform area, so ${unplacedStarters === 1 ? "it shows" : "they show"} under every platform` : "")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    style: {
      flexShrink: 0
    },
    onClick: () => {
      const text = starters.map((s, i) => {
        const head = `#${s.rank != null ? s.rank : i + 1}`;
        return [`${head} — ${pfText(s.text) || ""}`, s.followup_question ? `Follow-up: ${pfText(s.followup_question)}` : null, (s.e_ids || []).length ? `Evidence: ${s.e_ids.join(", ")}` : null].filter(Boolean).join("\n");
      }).join("\n\n");
      try {
        navigator.clipboard.writeText(text);
        pushToast(`Copied ${starters.length} conversation starters`, "success");
      } catch (e) {
        pushToast("Couldn't access clipboard", "warn");
      }
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "copy",
    size: 12
  }), " Copy all")), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 14
    }
  }, starters.map((s, i) => {
    const key = s.rank != null ? `r${s.rank}` : `i${i}`;
    const isOpen = openStarter === key;
    const cites = (s.e_ids || []).filter(Boolean);
    const extras = [s.their_system_reference, s.peer_reference, s.followup_question].filter(Boolean).length + (cites.length ? 1 : 0);
    /* The prototype's card carries a small grey stamp under the rank
       — "Template-fill · evidence-cited". That stamp was a literal:
       every card wore it whether or not the starter cited anything.
       Same position, same weight, but each half is read off this
       starter: what it opens on, and how many evidence ids it
       actually carries. A starter citing nothing says so, which is
       the one thing the prototype's version could never do. */
    const stamp = [s.opens_on ? `opens on ${String(s.opens_on).replace(/_/g, " ")}` : null, cites.length ? `${cites.length} cited` : "not cited"].filter(Boolean).join(" · ");
    /* The named gap is a drill target only where it resolves to a
       cell this run scored. This run states it as a category name
       with a numeric tail, which opens nothing — and a chip that
       opens an empty heatmap reads as a cell that exists, the same
       fail-closed rule the evidence chips follow. */
    const gapId = pfText(s.named_gap_subcap_id);
    const gapCell = gapId && cellIndex.has(String(gapId)) ? gapId : null;
    // The divider rides on the first starter the scope does not
    // reach — one filed under ANOTHER platform's area. It is still
    // rendered, still copyable, still citing what it cites.
    const scoped = scopedStarters.indexOf(s) >= 0;
    const first = !scoped && otherStarters.length && otherStarters[0] === s;
    return /*#__PURE__*/React.createElement(React.Fragment, {
      key: key
    }, first ? /*#__PURE__*/React.createElement(ScopeDivider, {
      shown: scopedStarters.length,
      total: allStarters.length,
      noun: "starter",
      scope: area || null
    }) : null, /*#__PURE__*/React.createElement("div", {
      style: {
        padding: 10,
        marginBottom: 8,
        background: "var(--ph0-lt)",
        border: `1px solid ${scoped ? "var(--ph0-bd)" : "var(--z-sep)"}`,
        borderRadius: 8,
        opacity: scoped ? 1 : .84,
        cursor: extras ? "pointer" : "default"
      },
      title: extras && !isOpen ? "Show the rest of this starter" : "",
      onClick: () => {
        if (extras) setOpenStarter(o => o === key ? null : key);
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 6,
        gap: 6,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "b b-purple",
      style: {
        flexShrink: 0
      }
    }, "#", s.rank != null ? s.rank : i + 1), stamp ? /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-dpur)",
        opacity: .85
      }
    }, stamp) : null, gapCell ? /*#__PURE__*/React.createElement("button", {
      className: "chip f-mono",
      style: {
        fontSize: 9,
        flexShrink: 0
      },
      title: `The gap this starter names — open ${gapCell} in the heatmap`,
      onClick: ev => {
        ev.stopPropagation();
        openSubcap(gapCell);
      }
    }, gapCell) : gapId ? /*#__PURE__*/React.createElement("span", {
      className: "chip muted f-mono",
      style: {
        fontSize: 9,
        flexShrink: 0,
        cursor: "default"
      },
      title: "the gap this starter names - not a cell id this run scored, so it opens nothing"
    }, gapId) : null, /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("button", {
      className: "btn btn-tertiary btn-sm",
      style: {
        color: "var(--z-dpur)"
      },
      title: "Copy this starter",
      onClick: ev => {
        ev.stopPropagation();
        const one = [pfText(s.text), s.followup_question ? `Follow-up: ${pfText(s.followup_question)}` : null].filter(Boolean).join("\n");
        try {
          navigator.clipboard.writeText(one);
          pushToast("Conversation starter copied", "success");
        } catch (e) {
          pushToast("Couldn't access clipboard", "warn");
        }
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "copy",
      size: 11
    }))), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "#3B0764",
        lineHeight: 1.6
      },
      className: isOpen ? "" : "txt-fit-4",
      title: isOpen ? "" : pfText(s.text) || ""
    }, pfText(s.text)), isOpen ? /*#__PURE__*/React.createElement(React.Fragment, null, s.their_system_reference ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-dpur)",
        marginTop: 6,
        lineHeight: 1.5
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 9,
        letterSpacing: ".06em",
        textTransform: "uppercase",
        opacity: .75
      }
    }, "Their system \xB7 "), pfText(s.their_system_reference)) : null, s.peer_reference ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-dpur)",
        marginTop: 4,
        lineHeight: 1.5
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 9,
        letterSpacing: ".06em",
        textTransform: "uppercase",
        opacity: .75
      }
    }, "Peer \xB7 "), pfText(s.peer_reference)) : null, s.followup_question ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "#3B0764",
        marginTop: 6,
        lineHeight: 1.55,
        paddingLeft: 8,
        borderLeft: "2px solid var(--ph0-bd)"
      }
    }, pfText(s.followup_question)) : null, /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 6
      }
    }, /*#__PURE__*/React.createElement(PlatformEvChips, {
      ids: cites,
      openEvidence: openEvidence,
      label: "cites"
    }))) : null, extras ? /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginTop: 4
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("button", {
      className: "btn btn-tertiary btn-sm",
      style: {
        color: "var(--z-dpur)",
        fontSize: 10
      },
      onClick: ev => {
        ev.stopPropagation();
        setOpenStarter(o => o === key ? null : key);
      }
    }, isOpen ? "Less" : `More · ${extras}`, /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-u" : "chevron-d",
      size: 11
    }))) : null));
  }), starters.length === 0 ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-muted)"
    }
  }, "No conversation starter promoted for this run.") : null))), discarded.length ? /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => setShowDiscarded(v => !v),
    style: {
      width: "100%",
      background: "none",
      border: 0,
      cursor: "pointer",
      textAlign: "left",
      padding: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "filter",
    size: 14
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "Considered and set aside \xB7 ", discarded.length), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)"
    }
  }, "why the run did not lead with these \xB7 this list is the run's, not ", selKey || "any one platform", "'s"), /*#__PURE__*/React.createElement(Icon, {
    name: showDiscarded ? "chevron-u" : "chevron-d",
    size: 13,
    style: {
      color: "var(--z-muted)"
    }
  }))), showDiscarded ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 7,
      marginTop: 10
    }
  }, discarded.map((x, i) =>
  /*#__PURE__*/
  /* The name column was a fixed 210px in a no-wrap row, so on a
     narrow viewport the reason text was squeezed to a sliver
     beside it. The row wraps: when the reason no longer fits at a
     readable width it drops to its own full-width line. */
  React.createElement("div", {
    key: i,
    className: "row",
    style: {
      gap: 10,
      alignItems: "flex-start",
      fontSize: 11.5,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 500,
      color: "var(--z-dark)",
      flex: "0 0 210px",
      maxWidth: "100%",
      lineHeight: 1.45
    }
  }, pfText(x.platform) || pfText(x.name) || "Platform not named"), x.relevance != null ? /*#__PURE__*/React.createElement("span", {
    className: "b b-muted f-mono",
    style: {
      flexShrink: 0
    },
    title: "relevance to the assessed gaps"
  }, Number(x.relevance).toFixed(2)) : null, /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-muted)",
      flex: "1 1 240px",
      minWidth: 0,
      lineHeight: 1.5
    }
  }, pfText(x.reason) || pfText(x.why_not) || "No reason promoted.")))) : null) : null, /*#__PURE__*/React.createElement(StairstepCurve, {
    entity: entity,
    selKey: selKey,
    area: area
  }), /*#__PURE__*/React.createElement(TransformationRoadmap, {
    entity: entity,
    selKey: selKey,
    area: area
  }));
}

/* ── Stair-step ladder ───────────────────────────────────────────────
   The ladder's rungs are ORDERED STEPS, not maturity bands. They used to be
   drawn as "M1 … M4" in band colours, which asserts that rung 4 is the
   Differentiating band — the payload says nothing of the kind, and the run's
   own composite is 2.71. Rungs are numbered and coloured from their index
   (presentation, deterministic, claiming nothing), and the position marker is
   the rung the run flags as `current_position` rather than always the first. */
const RUNG_COLORS = ["var(--z-dark2)", "var(--z-mid)", "var(--z-dpur)", "var(--z-teal)", "var(--z-purple)"];

/* SVG text does not wrap, and the promoted rung labels are sentences: at one
   line each they ran straight through the neighbouring rungs. Wrapped on word
   boundaries to the rectangle's own width, capped at two lines with the full
   label kept in a <title>. */
function wrapSvgLabel(text, maxChars, maxLines) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (next.length > maxChars && cur) {
      lines.push(cur);
      cur = w;
    } else cur = next;
  }
  if (cur) lines.push(cur);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  kept[maxLines - 1] = `${kept[maxLines - 1].slice(0, Math.max(0, maxChars - 1))}…`;
  return kept;
}
function StairstepCurve({
  entity,
  selKey,
  area
}) {
  // The default cluster key was hardcoded "P4-data", so any run whose ladder
  // does not carry that theme threw on C.label and blanked the whole lower
  // half of the platform page — the missing maturity curve and roadmap.
  const clusters = DMA.STAIRSTEP_CLUSTERS || {};
  const keys = Object.keys(clusters);
  const [cluster, setCluster] = useState(null);
  const active = cluster && clusters[cluster] ? cluster : keys[0];
  const C = active ? clusters[active] : null;
  if (!C || !(C.steps || []).length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "card",
      style: {
        marginBottom: 16
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "stairs",
      size: 14
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, "Maturity stair-step")), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-muted)"
      }
    }, "No stair-step ladder promoted for this run."));
  }
  const steps = C.steps;
  const n = steps.length;
  /* The platform each rung is climbed with, on the same join the tiles use:
     the rung's covered cells are filed under an L3 area by the run's own
     recommendations and story rows, and one promoted tile leads on that area.
     A rung whose cells resolve to no single area carries no platform label —
     the design's "via SF" is worth having only where the run says which. */
  const scope = platformScopeOf(entity.id);
  const viaOf = s => {
    const tally = new Map();
    for (const id of s && s.subcaps || []) {
      const hit = areaOfCell(scope.index, id);
      if (!hit) continue;
      tally.set(hit.area, (tally.get(hit.area) || 0) + 1);
    }
    if (!tally.size) return null;
    const ranked = [...tally.entries()].sort((a, b) => b[1] - a[1]);
    if (ranked.length > 1 && ranked[0][1] === ranked[1][1]) return null;
    const key = scope.platformOfArea.get(ranked[0][0]);
    return key ? {
      platform: key,
      area: ranked[0][0]
    } : null;
  };
  // Sized from the rung count, not a hardcoded four: a three- or five-rung
  // ladder used to be squeezed into or spill out of four columns. The rungs
  // climb to (i+1)/n of the plot height, so the last one reaches the top of
  // the frame as it does in the design — at (i+1)/(n+1) the whole staircase
  // sat in the lower two thirds with a band of empty chart above it.
  const W = 880,
    H = 560,
    padL = 60,
    padR = 40,
    padT = 40,
    padB = 70;
  const stepW = (W - padL - padR) / n;
  const stepY = i => H - padB - (i + 1) * (H - padT - padB) / n;
  const rungW = stepW - 8;
  const charsPerLine = Math.max(10, Math.floor(rungW / 5.9));
  const monoChars = Math.max(8, Math.floor(rungW / 5.7));
  // The rung the run marks as the current position (1-based level).
  const currentIdx = steps.findIndex(s => Number(s.m) === Number(C.current));

  /* Which rungs the SELECTED platform climbs. Every panel above this one
     changes when a tile is clicked and this card did not, which is the whole
     of "not all surfaces are enriched for each platform": the ladder already
     computed `via` per rung and then ignored the selection.
      Marked, never filtered. The rung join is DERIVED (see the scope note at
     the top of this file), and a ladder that dropped the rungs another
     platform leads would break the one thing a staircase means — that the
     rungs are in order and there are no gaps in it. So this platform's rungs
     are marked and counted, and the rest stay where they are. */
  const viaCache = steps.map(viaOf);
  const minesIdx = selKey ? viaCache.map((v, i) => v && v.platform === selKey ? i : -1).filter(i => i >= 0) : [];
  const placed = viaCache.filter(Boolean).length;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 14,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 28,
      height: 28,
      borderRadius: 7,
      background: "var(--z-ice)",
      color: "var(--z-mid)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "stairs",
    size: 14
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "Stair-step ladder \xB7 ", C.label, selKey ? /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-muted)",
      fontWeight: 400
    }
  }, " \xB7 ", selKey) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, n, " rung", n === 1 ? "" : "s", " \xB7 where ", entity.name, " stands today, and what each rung requires"), selKey ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: minesIdx.length ? "var(--z-mid)" : "var(--z-muted)",
      marginTop: 2,
      lineHeight: 1.45
    }
  }, minesIdx.length ? `${minesIdx.length} of ${n} rungs are climbed with ${selKey}${area ? ` (${area})` : ""} — marked below` : placed ? `No rung on this ladder is climbed with ${selKey}. ${placed} of ${n} resolve to another promoted platform, and all ${n} stay in sequence.` : `This run files none of these rungs' cells under an L3 area, so no rung can be attributed to ${selKey} or to any other platform.`) : null), keys.length > 1 ? /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, Object.entries(clusters).map(([k, v]) => /*#__PURE__*/React.createElement("button", {
    key: k,
    className: active === k ? "on" : "",
    onClick: () => setCluster(k)
  }, v.label))) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      alignItems: "flex-start",
      gap: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: "999 1 400px",
      minWidth: 0,
      maxWidth: "100%",
      background: "linear-gradient(180deg, var(--z-bg), #fff)",
      borderRadius: 10,
      padding: "16px 14px 12px",
      border: "1px solid var(--z-sep)",
      position: "relative",
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: assetUrl("illo_curvesTR", "brand/illustrations/curves_topright.png"),
    alt: "",
    style: {
      position: "absolute",
      top: 0,
      right: 0,
      width: 320,
      height: "auto",
      opacity: .5,
      pointerEvents: "none"
    }
  }), /*#__PURE__*/React.createElement("svg", {
    width: "100%",
    viewBox: `0 0 ${W} ${H}`,
    style: {
      display: "block",
      position: "relative"
    }
  }, /*#__PURE__*/React.createElement("defs", null, /*#__PURE__*/React.createElement("marker", {
    id: "arrowH",
    viewBox: "0 0 10 10",
    refX: "9",
    refY: "5",
    markerWidth: "8",
    markerHeight: "8",
    orient: "auto"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M0 0 L10 5 L0 10 z",
    fill: "var(--z-purple)"
  }))), /*#__PURE__*/React.createElement("line", {
    x1: padL,
    y1: H - padB + 18,
    x2: W - padR,
    y2: H - padB + 18,
    stroke: "var(--z-purple)",
    strokeWidth: "1.5",
    markerEnd: "url(#arrowH)"
  }), /*#__PURE__*/React.createElement("text", {
    x: padL,
    y: H - padB + 38,
    fontSize: "10",
    fill: "var(--z-muted)"
  }, "Today"), /*#__PURE__*/React.createElement("text", {
    x: W - padR - 36,
    y: H - padB + 38,
    fontSize: "10",
    fill: "var(--z-mid)",
    fontWeight: "600"
  }, "Leading"), steps.map((s, i) => {
    const x = padL + i * stepW;
    const y = stepY(i);
    const h = H - padB - y;
    const color = RUNG_COLORS[i % RUNG_COLORS.length];
    const lines = wrapSvgLabel(pfText(s.label), charsPerLine, 2);
    const via = viaCache[i];
    // This platform's rungs keep full weight; the others recede.
    // Nothing is removed — a staircase with a rung missing is a
    // different claim about the sequence.
    const mine = !!(selKey && via && via.platform === selKey);
    const dim = !!(selKey && minesIdx.length && !mine);
    // Cell count and effort only. The blocking findings are chips in
    // the list beside the chart: inside the rung they ran past both
    // edges of the rectangle, because a centred SVG string cannot be
    // clipped to its box.
    const meta = [(s.subcaps || []).length ? `${s.subcaps.length} cells` : null, s.effort ? `effort ${s.effort}` : null].filter(Boolean).join(" · ");
    /* SVG cannot clip a centred string to its box, so each line is
       admitted only if the rung is tall enough to hold it. The
       platform outranks the meta line: the cell count is also on the
       card beside the chart, and "via <platform>" is the one thing
       the rung says that nothing else on the row does. */
    const top = y + 20 + lines.length * 14;
    const viaFits = via && top + 12 <= H - padB - 6;
    const metaFits = meta && top + (viaFits ? 12 : 0) + 12 <= H - padB - 6;
    const clip = (t, max) => t.length > max ? `${t.slice(0, max - 1)}…` : t;
    return /*#__PURE__*/React.createElement("g", {
      key: i,
      opacity: dim ? 0.42 : 1
    }, /*#__PURE__*/React.createElement("title", null, `Step ${s.m}: ${pfText(s.label) || ""}${via ? ` · via ${via.platform} (${via.area})` : ""}`), /*#__PURE__*/React.createElement("rect", {
      x: x,
      y: y,
      width: rungW,
      height: h,
      fill: color,
      rx: "6",
      ry: "6"
    }), mine ? /*#__PURE__*/React.createElement("rect", {
      x: x - 2,
      y: y - 2,
      width: rungW + 4,
      height: h + 2,
      rx: "8",
      ry: "8",
      fill: "none",
      stroke: "var(--z-org)",
      strokeWidth: "2"
    }) : null, /*#__PURE__*/React.createElement("circle", {
      cx: x + 16,
      cy: y - 14,
      r: "14",
      fill: "#fff",
      stroke: color,
      strokeWidth: "2.5"
    }), /*#__PURE__*/React.createElement("text", {
      x: x + 16,
      y: y - 9,
      fontSize: "13",
      fontWeight: "700",
      fill: color,
      textAnchor: "middle"
    }, s.m), lines.map((ln, k) => /*#__PURE__*/React.createElement("text", {
      key: k,
      x: x + rungW / 2,
      y: y + 20 + k * 14,
      fontSize: "11",
      fontWeight: "600",
      fill: "#fff",
      textAnchor: "middle"
    }, ln)), viaFits ? /*#__PURE__*/React.createElement("text", {
      x: x + rungW / 2,
      y: top + 2,
      fontSize: "9.5",
      fill: "rgba(255,255,255,.92)",
      textAnchor: "middle",
      style: {
        fontFamily: "var(--font-mono)"
      }
    }, clip(`via ${via.platform}`, monoChars)) : null, metaFits ? /*#__PURE__*/React.createElement("text", {
      x: x + rungW / 2,
      y: top + (viaFits ? 14 : 2),
      fontSize: "9",
      fill: "rgba(255,255,255,.8)",
      textAnchor: "middle",
      style: {
        fontFamily: "var(--font-mono)"
      }
    }, clip(meta, monoChars)) : null);
  }), steps.slice(0, -1).map((s, i) => {
    const x1 = padL + (i + 1) * stepW - 8;
    const y1 = stepY(i);
    const x2 = padL + (i + 1) * stepW;
    const y2 = H - padB;
    return /*#__PURE__*/React.createElement("line", {
      key: i,
      x1: x1,
      y1: y1,
      x2: x2,
      y2: y2,
      stroke: "var(--z-dpur)",
      strokeWidth: "2",
      strokeDasharray: "3 3",
      opacity: "0.5"
    });
  }), currentIdx >= 0 ? /*#__PURE__*/React.createElement("g", null, /*#__PURE__*/React.createElement("circle", {
    cx: padL + currentIdx * stepW + 16,
    cy: stepY(currentIdx) - 14,
    r: "20",
    fill: "none",
    stroke: "var(--z-org)",
    strokeWidth: "2",
    strokeDasharray: "4 3"
  }), /*#__PURE__*/React.createElement("text", {
    x: padL + currentIdx * stepW + 16,
    y: stepY(currentIdx) - 53,
    fontSize: "9.5",
    fill: "var(--z-org)",
    fontWeight: "700",
    textAnchor: "middle"
  }, "YOU ARE HERE"), /*#__PURE__*/React.createElement("text", {
    x: padL + currentIdx * stepW + 16,
    y: stepY(currentIdx) - 40,
    fontSize: "9",
    fill: "var(--z-muted)",
    textAnchor: "middle"
  }, `step ${steps[currentIdx].m} of ${n}`)) : null)), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: "1 1 280px",
      minWidth: 0,
      maxWidth: "100%",
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, steps.map((s, i) => {
    const via = viaCache[i];
    const mine = !!(selKey && via && via.platform === selKey);
    const dim = !!(selKey && minesIdx.length && !mine);
    return /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        padding: "10px 12px",
        background: i === currentIdx ? "var(--z-ice)" : "var(--z-bg)",
        borderRadius: 8,
        border: mine ? "1px solid var(--z-org)" : i === currentIdx ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)",
        opacity: dim ? 0.62 : 1
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 4,
        gap: 6,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "b b-purple",
      style: {
        flexShrink: 0
      }
    }, "Step ", s.m), i === currentIdx ? /*#__PURE__*/React.createElement("span", {
      className: "b b-teal",
      style: {
        flexShrink: 0
      }
    }, "current") : null, mine ? /*#__PURE__*/React.createElement("span", {
      className: "b b-org",
      style: {
        flexShrink: 0
      },
      title: `This rung's cells are filed under ${via.area}, which ${selKey} leads on`
    }, "this platform") : null, s.effort ? /*#__PURE__*/React.createElement("span", {
      className: "b b-muted",
      style: {
        flexShrink: 0
      },
      title: "effort band"
    }, pfText(s.effort)) : null, (s.blocking || []).map(b => /*#__PURE__*/React.createElement("span", {
      key: b,
      className: "b b-org",
      style: {
        flexShrink: 0
      },
      title: "blocking finding"
    }, pfText(b)))), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        fontWeight: 600,
        color: "var(--z-dark)",
        lineHeight: 1.4
      }
    }, pfText(s.label)), via ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-mid)",
        marginTop: 3
      },
      title: `This rung's cells are filed under ${via.area}, which ${via.platform} leads on`
    }, "via ", via.platform) : null, s.note ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        lineHeight: 1.55,
        marginTop: 4
      },
      className: "txt-fit-2",
      title: pfText(s.note) || ""
    }, pfText(s.note)) : null, (s.subcaps || []).length ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        marginTop: 4
      }
    }, s.subcaps.length, " cells covered") : null);
  }))));
}

/* ── Transformation Roadmap (Pattern J: phase chevrons) ─────────── */
function TransformationRoadmap({
  entity,
  selKey,
  area
}) {
  const {
    openRec,
    pushToast
  } = useApp();
  const [view, setView] = useState("chevrons"); // chevrons | impact
  const roadmap = DMA.ROADMAP || [];
  const recs = DMA.RECOMMENDATIONS || [];
  if (!roadmap.length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "card",
      style: {
        marginBottom: 16
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "route",
      size: 14
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, "Transformation roadmap")), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-muted)"
      }
    }, "No roadmap promoted for this run."));
  }
  const phaseRecs = r => (r.recs || []).map(rid => recs.find(x => x.id === rid)).filter(Boolean);
  const impactRows = roadmap.reduce((a, r) => a + phaseRecs(r).reduce((b, rec) => b + (rec.dma_impact || []).length, 0), 0);
  // The section states its sequencing basis beside `phases`, so it reaches the
  // page through the entity rather than through the phase array.
  const basis = typeof window !== "undefined" && window.DMA_ENTITY && window.DMA_ENTITY.roadmapBasis || null;

  /* Which of this roadmap's recommendations belong to the SELECTED platform.
     Same join as everything else on the page — a recommendation's `l3` against
     the L3 area the tile derives — so the roadmap answers a tile click instead
     of being the one panel that ignores it.
      Marked and counted, never filtered: a roadmap is an ORDER, and a phase
     removed from it because the reader clicked a platform is a different plan.
     `mine` per phase is how many of that phase's served recommendations this
     platform leads. */
  const isMine = rec => !!(area && rec && rec.l3 === area);
  const mineCount = recs.filter(isMine).length;
  const phaseMine = r => phaseRecs(r).filter(isMine).length;
  const roadmapMine = roadmap.reduce((a, r) => a + phaseMine(r), 0);
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 16,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 28,
      height: 28,
      borderRadius: 7,
      background: "var(--z-ice)",
      color: "var(--z-mid)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "route",
    size: 14
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "Transformation roadmap", selKey ? /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-muted)",
      fontWeight: 400
    }
  }, " \xB7 ", selKey) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, roadmap.length, " promoted phase", roadmap.length === 1 ? "" : "s", " \xB7 ", roadmap.reduce((a, r) => a + (r.recs || []).length, 0), " recommendations"), selKey ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: roadmapMine ? "var(--z-mid)" : "var(--z-muted)",
      marginTop: 2,
      lineHeight: 1.45
    }
  }, roadmapMine ? `${roadmapMine} of them sit in ${area} — the area ${selKey} leads — and are marked in their phases. The rest of the plan stays in sequence.` : area ? `None of this plan's recommendations sit in ${area}, so ${selKey} leads no phase of it. Every phase is still this run's.` : `This run files none of ${selKey}'s cells under an L3 area, so no phase can be attributed to it.`) : null), /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, /*#__PURE__*/React.createElement("button", {
    className: view === "chevrons" ? "on" : "",
    onClick: () => setView("chevrons")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "route",
    size: 11
  }), " Phases"), /*#__PURE__*/React.createElement("button", {
    className: view === "impact" ? "on" : "",
    onClick: () => setView("impact")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "stairs",
    size: 11
  }), " Cell impact")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => pushToast(`Exporting ${entity.name} roadmap (${view} view)…`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 11
  }), " Export")), view === "chevrons" ? /*#__PURE__*/React.createElement(ChevronView, {
    roadmap: roadmap,
    recs: recs,
    openRec: openRec,
    phaseRecs: phaseRecs,
    isMine: isMine,
    selKey: selKey,
    phaseMine: phaseMine
  }) : /*#__PURE__*/React.createElement(CellImpactView, {
    roadmap: roadmap,
    phaseRecs: phaseRecs,
    openRec: openRec,
    impactRows: impactRows,
    isMine: isMine,
    selKey: selKey
  }), basis ? /*#__PURE__*/React.createElement("div", {
    className: "co co-teal",
    style: {
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 14
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "co-title"
  }, "Sequencing rationale"), /*#__PURE__*/React.createElement("div", {
    className: "co-body"
  }, pfText(basis)))) : null);
}

/* Per phase, the facts the design's card carries — each computed from what the
   phase's own recommendations state, and each omitted where they state
   nothing. The roadmap contract itself has no platform, target or metric
   field: those belong to the recommendations a phase contains, which is why
   reading them off the phase produced three empty labels under three
   headings. */
function phaseFacts(rs) {
  const areas = [];
  const metrics = [];
  const impacts = [];
  for (const rec of rs || []) {
    if (rec.l3 && !areas.includes(rec.l3)) areas.push(rec.l3);
    const m = rec.kpi && rec.kpi.metric ? pfText(rec.kpi.metric) : null;
    if (m && !metrics.includes(m)) metrics.push(m);
    for (const im of rec.dma_impact || []) impacts.push(im);
  }
  const deltas = impacts.map(im => pfNum(im.delta)).filter(d => d !== null);
  const bases = [];
  for (const im of impacts) {
    if (im.target_basis && !bases.includes(im.target_basis)) bases.push(im.target_basis);
  }
  // Computed-or-null: the movement line exists only where cells state one.
  let move = null;
  if (impacts.length) {
    const lo = deltas.length ? Math.min(...deltas) : null;
    const hi = deltas.length ? Math.max(...deltas) : null;
    const span = lo === null ? null : lo === hi ? `+${lo.toFixed(1)}` : `+${lo.toFixed(1)} to +${hi.toFixed(1)}`;
    move = `${impacts.length} cell${impacts.length === 1 ? "" : "s"}${span ? ` · ${span} projected` : ""}`;
  }
  return {
    areas,
    metrics,
    move,
    bases
  };
}
function ChevronView({
  roadmap,
  recs,
  openRec,
  phaseRecs,
  isMine,
  selKey,
  phaseMine
}) {
  const mineOf = isMine || (() => false);
  return (
    /*#__PURE__*/
    /* One fluid column per phase, each carrying its own chevron header AND its
       own content card. This used to be two parallel `repeat(N, 1fr)` grids —
       N hard columns whatever the viewport, so at tablet widths every phase
       was crushed to a sliver, and the two grids could not wrap without the
       chevrons drifting away from their phases. Whole phases wrap together
       instead, and only when a column would drop below a readable width. */
    React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 230px), 1fr))",
        gap: 12
      }
    }, roadmap.map((r, i) => {
      const rs = phaseRecs ? phaseRecs(r) : (r.recs || []).map(rid => recs.find(x => x.id === rid)).filter(Boolean);
      const facts = phaseFacts(rs);
      return /*#__PURE__*/React.createElement("div", {
        key: r.phase,
        style: {
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          gap: 12
        }
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          background: r.color,
          clipPath: i === roadmap.length - 1 ? "polygon(0 0, 100% 0, 100% 100%, 0 100%, 4% 50%)" : "polygon(0 0, 96% 0, 100% 50%, 96% 100%, 0 100%, 4% 50%)",
          color: "#fff",
          padding: "10px 22px",
          fontSize: 12.5,
          fontWeight: 600,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 8
        }
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          minWidth: 0
        }
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10,
          opacity: .8,
          letterSpacing: ".08em",
          textTransform: "uppercase"
        }
      }, "Phase ", r.phase), /*#__PURE__*/React.createElement("div", null, r.label)), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10,
          opacity: .85,
          textAlign: "right",
          flexShrink: 0
        }
      }, (r.recs || []).length, " rec", (r.recs || []).length === 1 ? "" : "s", selKey && phaseMine ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 9.5,
          opacity: .9
        },
        title: `${phaseMine(r)} of this phase's recommendations sit in the area ${selKey} leads`
      }, phaseMine(r), " \xB7 ", selKey.length > 18 ? `${selKey.slice(0, 17)}…` : selKey) : null)), /*#__PURE__*/React.createElement("div", {
        style: {
          background: r.color,
          borderRadius: 8,
          padding: 14,
          color: "#fff",
          flex: 1
        }
      }, facts.areas.length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10,
          color: "rgba(255,255,255,.7)",
          letterSpacing: ".06em",
          textTransform: "uppercase",
          marginBottom: 4
        }
      }, "Platform areas"), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 12.5,
          fontWeight: 600,
          marginBottom: 10,
          lineHeight: 1.4
        },
        className: "txt-fit-2",
        title: facts.areas.join(" · ")
      }, facts.areas.join(" · "))) : null, facts.move ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10,
          color: "rgba(255,255,255,.7)",
          letterSpacing: ".06em",
          textTransform: "uppercase",
          marginBottom: 4
        }
      }, "Target maturity"), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 12.5,
          marginBottom: 10,
          color: "var(--z-mint-lt)"
        },
        title: facts.bases.join("\n") || "Projected movement, from the recommendations' own stated targets"
      }, facts.move)) : null, facts.metrics.length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10,
          color: "rgba(255,255,255,.7)",
          letterSpacing: ".06em",
          textTransform: "uppercase",
          marginBottom: 4
        }
      }, "Success metric"), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 12,
          marginBottom: 10,
          lineHeight: 1.5
        }
      }, facts.metrics.slice(0, 3).map((m, k) => /*#__PURE__*/React.createElement("div", {
        key: k,
        style: {
          marginBottom: 2
        }
      }, m)), facts.metrics.length > 3 ? /*#__PURE__*/React.createElement("div", {
        style: {
          color: "rgba(255,255,255,.75)",
          marginTop: 2
        },
        title: facts.metrics.slice(3).join("\n")
      }, "+", facts.metrics.length - 3, " more") : null)) : null, /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10,
          color: "rgba(255,255,255,.7)",
          letterSpacing: ".06em",
          textTransform: "uppercase",
          marginBottom: 6
        }
      }, "Recommendations"), /*#__PURE__*/React.createElement("div", {
        style: {
          display: "flex",
          flexDirection: "column",
          gap: 4
        }
      }, (r.recs || []).map(rid => {
        const rec = recs.find(x => x.id === rid);
        // The selected platform's own rows keep a full-strength face;
        // the rest of the phase recedes. Every row stays clickable.
        const mine = mineOf(rec);
        const marked = !!(selKey && mine);
        return rec ? /*#__PURE__*/React.createElement("button", {
          key: rid,
          onClick: e => {
            e.stopPropagation();
            openRec(rid);
          }
          /* The title ellipsises to one line by design; without this
             the rest of the sentence is unreachable by any means. */,
          title: `${rec.id} · ${pfText(rec.title) || ""}${marked ? ` · ${selKey} leads this` : ""}`,
          style: {
            padding: "6px 8px",
            background: marked ? "rgba(255,255,255,.30)" : "rgba(255,255,255,.14)",
            borderRadius: 5,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 6,
            border: marked ? "1px solid rgba(255,255,255,.85)" : "1px solid transparent",
            color: "#fff",
            textAlign: "left",
            cursor: "pointer",
            transition: "background 120ms"
          },
          onMouseEnter: e => e.currentTarget.style.background = "rgba(255,255,255,.22)",
          onMouseLeave: e => e.currentTarget.style.background = marked ? "rgba(255,255,255,.30)" : "rgba(255,255,255,.14)"
        }, /*#__PURE__*/React.createElement("span", {
          style: {
            fontSize: 10.5,
            fontWeight: 600,
            flexShrink: 0
          }
        }, rec.id), /*#__PURE__*/React.createElement("span", {
          style: {
            fontSize: 10.5,
            color: "rgba(255,255,255,.85)",
            flex: 1,
            minWidth: 0
          },
          className: "txt-trunc"
        }, pfText(rec.title)), /*#__PURE__*/React.createElement(Icon, {
          name: "arrow-r",
          size: 11
        })) :
        /*#__PURE__*/
        /* A phase that names a recommendation this run did not serve
           says so — it used to render nothing at all. */
        React.createElement("span", {
          key: rid,
          style: {
            fontSize: 10.5,
            color: "rgba(255,255,255,.7)"
          }
        }, rid, " \xB7 not served in this run");
      })), r.rationale || (r.depends_on || []).length ? /*#__PURE__*/React.createElement("div", {
        style: {
          marginTop: 12,
          paddingTop: 10,
          borderTop: "1px solid rgba(255,255,255,.2)"
        }
      }, (r.depends_on || []).length ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10.5,
          color: "rgba(255,255,255,.8)",
          marginBottom: 6
        }
      }, "Depends on ", r.depends_on.join(" · ")) : null, r.rationale ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10,
          color: "rgba(255,255,255,.7)",
          letterSpacing: ".06em",
          textTransform: "uppercase",
          marginBottom: 4
        }
      }, "Why this phase"), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 11.5,
          lineHeight: 1.5
        },
        className: "txt-fit-3",
        title: pfText(r.rationale) || ""
      }, pfText(r.rationale))) : null) : null));
    }))
  );
}

/* Per-phase cell movement, from `recommendations[].dma_impact`.
   This replaces the "Customer impact" view, which read DMA.ROADMAP_IMPACTS —
   an accessor pointing at the key `roadmapImpacts`, which nothing in the live
   payload sets and no promoted section carries. It rendered three phase
   headers with zero rows. `dma_impact` is what the run does state about
   movement: per cell, its current score, the projected target and the delta —
   with `target_basis` stating in the producer's own words that the target is a
   projection, which is printed rather than paraphrased. */
function CellImpactView({
  roadmap,
  phaseRecs,
  openRec,
  impactRows,
  isMine,
  selKey
}) {
  const mineOf = isMine || (() => false);
  if (!impactRows) {
    return /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-muted)"
      }
    }, "No recommendation in this roadmap promoted a cell-impact table, so there is nothing to show per phase.");
  }
  return (
    /*#__PURE__*/
    /* Fluid, like the chevron view: N hard columns crushed each phase's
       impact table at tablet widths; phases wrap when a column would drop
       below a readable width. */
    React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))",
        gap: 12
      }
    }, roadmap.map(r => {
      const rs = phaseRecs(r);
      const bases = [];
      for (const rec of rs) {
        for (const im of rec.dma_impact || []) {
          if (im.target_basis && !bases.includes(im.target_basis)) bases.push(im.target_basis);
        }
      }
      return /*#__PURE__*/React.createElement("div", {
        key: r.phase,
        className: "card-tile",
        style: {
          padding: 14,
          borderTop: `3px solid ${r.color}`
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          marginBottom: 4,
          gap: 6
        }
      }, /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 10,
          fontWeight: 700,
          color: r.color,
          letterSpacing: ".08em",
          textTransform: "uppercase",
          flexShrink: 0
        }
      }, "Phase ", pfText(r.phase)), /*#__PURE__*/React.createElement("strong", {
        style: {
          fontSize: 12.5,
          flex: 1,
          minWidth: 0
        }
      }, r.label)), /*#__PURE__*/React.createElement("div", {
        className: "eyebrow",
        style: {
          fontSize: 9.5,
          margin: "8px 0 6px"
        }
      }, "Cells this phase moves"), rs.map(rec => /*#__PURE__*/React.createElement("div", {
        key: rec.id,
        style: {
          marginBottom: 10
        }
      }, /*#__PURE__*/React.createElement("button", {
        onClick: () => openRec(rec.id),
        title: `${rec.id} · ${pfText(rec.title) || ""}${selKey && mineOf(rec) ? ` · ${selKey} leads this` : ""}`,
        style: {
          padding: 0,
          background: "none",
          border: 0,
          cursor: "pointer",
          textAlign: "left",
          display: "flex",
          gap: 6,
          alignItems: "center",
          width: "100%"
        }
      }, /*#__PURE__*/React.createElement("strong", {
        style: {
          fontSize: 10.5,
          color: "var(--z-dark)",
          flexShrink: 0
        }
      }, rec.id), /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 10.5,
          color: "var(--z-muted)",
          flex: 1,
          minWidth: 0
        },
        className: "txt-trunc"
      }, pfText(rec.title)), selKey && mineOf(rec) ? /*#__PURE__*/React.createElement("span", {
        className: "b b-org",
        style: {
          flexShrink: 0
        }
      }, "this platform") : null, /*#__PURE__*/React.createElement(Icon, {
        name: "arrow-r",
        size: 11,
        style: {
          color: "var(--z-muted)",
          flexShrink: 0
        }
      })), (rec.dma_impact || []).length ? (rec.dma_impact || []).map((im, j) => {
        const cur = pfNum(im.current),
          tgt = pfNum(im.target),
          d = pfNum(im.delta);
        return /*#__PURE__*/React.createElement("div", {
          key: j,
          className: "row",
          style: {
            padding: "5px 0",
            borderTop: "1px solid var(--z-sep)",
            gap: 6,
            alignItems: "flex-start"
          }
        }, /*#__PURE__*/React.createElement("div", {
          style: {
            flex: 1,
            minWidth: 0
          }
        }, /*#__PURE__*/React.createElement("div", {
          style: {
            fontSize: 11,
            color: "var(--z-body)",
            lineHeight: 1.35
          }
        }, pfText(im.name) || im.subcap_id), /*#__PURE__*/React.createElement("div", {
          className: "f-mono",
          style: {
            fontSize: 9,
            color: "var(--z-muted)"
          }
        }, pfText(im.subcap_id))), /*#__PURE__*/React.createElement("span", {
          style: {
            flexShrink: 0
          }
        }, /*#__PURE__*/React.createElement(MaturityChip, {
          score: cur
        })), /*#__PURE__*/React.createElement("span", {
          style: {
            fontSize: 10,
            color: "var(--z-muted)",
            flexShrink: 0
          }
        }, "\u2192"), /*#__PURE__*/React.createElement("span", {
          style: {
            flexShrink: 0
          }
        }, /*#__PURE__*/React.createElement(MaturityChip, {
          score: tgt
        })), d !== null ? /*#__PURE__*/React.createElement("span", {
          className: "f-mono",
          style: {
            fontSize: 10,
            color: "var(--z-mid)",
            width: 30,
            textAlign: "right",
            flexShrink: 0
          }
        }, d > 0 ? `+${d.toFixed(1)}` : d.toFixed(1)) : null);
      }) : /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10.5,
          color: "var(--z-muted)",
          padding: "4px 0"
        }
      }, "No cell impact promoted for this recommendation."))), !rs.length ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 11,
          color: "var(--z-muted)"
        }
      }, (r.recs || []).length ? `This phase names ${r.recs.join(" · ")}, none of them served in this run.` : "This phase names no recommendation.") : null, bases.length ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 9.5,
          color: "var(--z-muted)",
          marginTop: 8,
          paddingTop: 8,
          borderTop: "1px solid var(--z-sep)",
          lineHeight: 1.5
        }
      }, bases.map((b, i) => /*#__PURE__*/React.createElement("div", {
        key: i,
        style: {
          marginBottom: 3
        }
      }, pfText(b)))) : null);
    }))
  );
}
Object.assign(window, {
  ClientPlatform
});