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
function PlatformEvChips({ ids, openEvidence, label }) {
  const list = (ids || []).filter(Boolean);
  if (!list.length) return null;
  return (
    <div className="row" style={{ flexWrap: "wrap", gap: 4, alignItems: "center" }}>
      {label ? (
        <span style={{ fontSize: 9, color: "var(--z-muted)", letterSpacing: ".06em", textTransform: "uppercase" }}>{label}</span>
      ) : null}
      {list.map(eid => {
        const e = DMA.getEvidence(eid);
        return e ? (
          <button key={eid} className={`tier-chip tier-${e.tier}`}
            style={{ cursor: "pointer", border: 0 }}
            title={`${e.title || eid} · ${e.source_pretty || ""}`}
            onClick={ev => { ev.stopPropagation(); openEvidence(eid); }}>{eid}</button>
        ) : (
          <span key={eid} className="chip muted" title="cited id - not in this run's served evidence">{eid}</span>
        );
      })}
    </div>
  );
}

/* ── The evidence behind a platform, which was promoted and never shown ──
   Measured 2026-08-15 against the live BCU payload. `platform_story` serves 16
   keys per platform. The page rendered exactly two of them — `platform` and
   `story_md` — and dropped the rest on the floor:

     fit_score · fit_basis          the ranked number the whole page sorts by
     peer_synthesis · peer_coverage
     peer_deployments               25 rows, every one carrying a cited basis
     estate_reach                   what the register already reaches, and why
     readiness                      verdict, what is already true, what is not
     integration_pathway            how it lands in THIS estate
     zennify_pathway                internal only; stripped for the customer
     r_layer.confidence_basis       internal only

   That is the write-path-with-no-read-path shape at its most expensive: the
   producer ran the search, argued against itself, cited the result — and a
   reader saw a name and a paragraph. It is also the direct cause of the
   reported "blanks stated instead of sourced or inferred": the sourcing was
   there and unrendered, so an absent peer figure read as a blank rather than
   as the recorded finding it is.

   Two rules this block obeys, both owner adjudications:
     · Never an em dash for an absence (2026-08-14). A row whose value is not
       sourceable is OMITTED, not rendered as punctuation (2026-08-15).
     · What is absent from the payload is absent because redaction removed it
       (`r_layer` and `zennify_pathway` for the customer audience) or because
       the producer had nothing. Neither is announced; the block simply carries
       what exists, so a customer never learns what a customer cannot see. */
function PlatformFact({ label, children, ids, openEvidence, title }) {
  if (children === null || children === undefined || children === "") return null;
  return (
    <div style={{ marginTop: 9 }}>
      <div className="eyebrow" style={{ fontSize: 9, marginBottom: 3 }} title={title || ""}>{label}</div>
      <div style={{ fontSize: 11.5, lineHeight: 1.6, color: "var(--z-body)" }}>{children}</div>
      {ids && ids.length ? (
        <div style={{ marginTop: 4 }}>
          <PlatformEvChips ids={ids} openEvidence={openEvidence} label="cited" />
        </div>
      ) : null}
    </div>
  );
}

function PlatformDossier({ p, openEvidence }) {
  const [open, setOpen] = useState(false);
  const reach = (p && p.estate_reach) || null;
  const ready = (p && p.readiness) || null;
  const rl = (p && p.r_layer) || null;
  const peers = ((p && p.peer_deployments) || []).filter(Boolean);
  const cats = ((reach && reach.by_category) || []).filter(Boolean);

  // Every fact this platform actually carries. If the count is zero there is
  // nothing behind the story and the control is not rendered at all — a
  // disclosure toggle that opens onto nothing is its own dead end.
  const facts = [
    pfText(p && p.peer_synthesis), peers.length ? "peers" : null,
    reach && (cats.length || pfText(reach.why_this_is_established)) ? "reach" : null,
    ready && (pfText(ready.verdict) || pfText(ready.already_true)) ? "ready" : null,
    pfText(p && p.integration_pathway), pfText(p && p.zennify_pathway),
    rl && pfText(rl.confidence_basis),
  ].filter(Boolean);
  if (!facts.length) return null;

  const cover = fmtPct(pfNum(p && p.peer_coverage));
  const notReached = pfNum(reach && reach.cells_not_yet_reached);

  return (
    <div style={{ marginTop: 10, borderTop: "1px dashed var(--z-sep)", paddingTop: 8 }}>
      <button onClick={() => setOpen(o => !o)}
        style={{ background: "none", border: 0, padding: 0, cursor: "pointer", width: "100%", textAlign: "left" }}
        title={pfText(p && p.fit_basis) || ""}>
        <div className="row" style={{ gap: 6, alignItems: "center" }}>
          <span className="eyebrow" style={{ fontSize: 9.5 }}>
            Evidence behind this platform
          </span>
          <span style={{ fontSize: 10, color: "var(--z-muted)" }}>
            {facts.length} {facts.length === 1 ? "finding" : "findings"}
          </span>
          <span className="spacer" />
          <Icon name={open ? "chevron-u" : "chevron-d"} size={13} style={{ color: "var(--z-muted)" }} />
        </div>
      </button>
      {open ? (
        <div style={{ paddingTop: 2 }}>
          <PlatformFact label="Peer position" openEvidence={openEvidence}>
            {pfText(p.peer_synthesis) || (cover !== null
              ? `${cover} of the locked peer set is established on this platform area.`
              : null)}
          </PlatformFact>

          {peers.length ? (
            <div style={{ marginTop: 8 }}>
              <div className="eyebrow" style={{ fontSize: 9, marginBottom: 4 }}>
                Peer set · {peers.length}
              </div>
              {peers.map((pd, i) => {
                const name = pfText(pd.peer);
                if (!name) return null;
                // `deployed` is a tri-state and every branch is a different
                // finding: true is a citable deployment, false is a search-led
                // absence, null is "the search ran and settled nothing". The
                // basis prose says which, so the badge must never flatten the
                // three into a blank.
                const dep = pd.deployed;
                const tone = dep === true ? "b-above" : dep === false ? "b-below" : "b-muted";
                const word = dep === true ? "established"
                           : dep === false ? "not established" : "unestablished";
                const asOf = pfText(pd.as_of);
                const url = pfText(pd.source_url);
                return (
                  <div key={`${name}-${i}`} style={{ padding: "6px 0", borderTop: i ? "1px solid var(--z-sep)" : 0 }}>
                    <div className="row" style={{ gap: 6, alignItems: "baseline", flexWrap: "wrap" }}>
                      <span style={{ fontSize: 11.5, fontWeight: 600 }}>{name}</span>
                      <span className={`b ${tone}`} style={{ flexShrink: 0 }}>{word}</span>
                      {asOf ? <span style={{ fontSize: 10, color: "var(--z-muted)" }}>{fmtDate(asOf)}</span> : null}
                      {url ? (
                        <a href={url} target="_blank" rel="noreferrer"
                          style={{ fontSize: 10, color: "var(--z-mid)" }}>source</a>
                      ) : null}
                    </div>
                    {pfText(pd.basis) ? (
                      <div style={{ fontSize: 11, lineHeight: 1.55, color: "var(--z-body)", marginTop: 2 }}>
                        {pfText(pd.basis)}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : null}

          {reach ? (
            <PlatformFact label="Estate reach" openEvidence={openEvidence}
              ids={reach.e_ids} title={pfText(reach.derivation) || ""}>
              <>
                {cats.length ? (
                  <div style={{ marginBottom: 4 }}>
                    {cats.map((c, i) => {
                      const linked = pfNum(c.cells_a_register_product_is_linked_to);
                      const scored = pfNum(c.cells_this_run_scores);
                      if (linked === null || scored === null) return null;
                      return (
                        <div key={c.category_id || i} style={{ fontSize: 11 }}>
                          <span className="f-mono" style={{ color: "var(--z-muted)" }}>{pfText(c.category_id)}</span>{" "}
                          {pfText(c.category_name)} · {linked} of {scored} cells reached
                        </div>
                      );
                    })}
                  </div>
                ) : null}
                {notReached !== null ? (
                  <div style={{ marginBottom: 4, fontSize: 11, color: "var(--z-muted)" }}>
                    {notReached} cells this run scores have no register row against them.
                  </div>
                ) : null}
                {pfText(reach.why_this_is_established)}
              </>
            </PlatformFact>
          ) : null}

          {ready ? (
            <PlatformFact label={`Readiness${pfText(ready.verdict) ? ` · ${pfText(ready.verdict)}` : ""}`}
              openEvidence={openEvidence} ids={ready.e_ids}>
              <>
                {pfText(ready.already_true) ? <div>{pfText(ready.already_true)}</div> : null}
                {pfText(ready.must_be_true_first) ? (
                  <div style={{ marginTop: 4 }}>
                    <span style={{ color: "var(--z-muted)" }}>Must be true first: </span>
                    {pfText(ready.must_be_true_first)}
                  </div>
                ) : null}
                {pfText(ready.sequencing_basis) ? (
                  <div style={{ marginTop: 4 }}>
                    <span style={{ color: "var(--z-muted)" }}>Why this order: </span>
                    {pfText(ready.sequencing_basis)}
                  </div>
                ) : null}
              </>
            </PlatformFact>
          ) : null}

          <PlatformFact label="How it lands in this estate" openEvidence={openEvidence}>
            {pfText(p.integration_pathway)}
          </PlatformFact>

          {/* internal only: redaction removes this key for the customer
              audience, so its absence needs no branch here. */}
          <PlatformFact label="Assessment pathway" openEvidence={openEvidence}>
            {pfText(p.zennify_pathway)}
          </PlatformFact>

          <PlatformFact
            label={`Confidence${rl && pfText(rl.confidence) ? ` · ${pfText(rl.confidence)}` : ""}`}
            openEvidence={openEvidence}>
            {rl ? pfText(rl.confidence_basis) : null}
          </PlatformFact>
        </div>
      ) : null}
    </div>
  );
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
function ScopeDivider({ shown, total, noun, scope }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "10px 0 8px" }}>
      <span style={{ height: 1, background: "var(--z-sep)", flex: "0 0 14px" }} />
      <span style={{ fontSize: 10, color: "var(--z-muted)", lineHeight: 1.45 }}>
        {shown} of {total} {noun}{shown === 1 ? "" : "s"}
        {scope ? ` in ${scope}` : " could be placed on a platform"} · the rest of this run's below
      </span>
      <span style={{ height: 1, background: "var(--z-sep)", flex: 1 }} />
    </div>
  );
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
  return (row && row.name) || null;
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
  return { exact, family };
}

/* The area one cell is filed under, with the grain that answered.
   `basis` travels with the answer so the surface can say whether the run filed
   this exact cell or only its family. Ambiguity — two areas at either grain —
   returns nothing, because a coin toss between two areas is the invented
   mapping this index exists to avoid. */
function areaOfCell(index, cellId) {
  if (!index || !cellId) return null;
  const exact = index.exact.get(String(cellId));
  if (exact && exact.size === 1) return { area: [...exact][0], basis: "cell" };
  const fam = cellFamilyOf(cellId);
  const byFam = fam ? index.family.get(fam) : null;
  if (byFam && byFam.size === 1) return { area: [...byFam][0], basis: "family" };
  return null;
}

/* The area an opportunity tile scopes: the one its own addressable cells are
   filed under most often. Ties resolve to nothing rather than to whichever
   area Object.entries happened to order first. The vote counts come back with
   the answer so the heading can state how strong the join is. */
function areaOfTile(index, tile) {
  const cells = (tile && tile.addressable_cells) || [];
  const tally = new Map();
  let exactVotes = 0;
  for (const c of cells) {
    const hit = areaOfCell(index, c && c.subcap_id);
    if (!hit) continue;
    tally.set(hit.area, (tally.get(hit.area) || 0) + 1);
    if (hit.basis === "cell") exactVotes += 1;
  }
  if (!tally.size) return { area: null, votes: 0, of: cells.length, exact: 0 };
  const ranked = [...tally.entries()].sort((a, b) => b[1] - a[1]);
  if (ranked.length > 1 && ranked[0][1] === ranked[1][1]) {
    return { area: null, votes: 0, of: cells.length, exact: 0, tied: true };
  }
  return { area: ranked[0][0], votes: ranked[0][1], of: cells.length, exact: exactVotes };
}

/* The L3 areas this run promoted, earliest roadmap phase first. Used only to
   report what the tile row does NOT reach — an area carrying recommendations
   that no promoted tile addresses would otherwise vanish from the page. */
function platformAreasOf(recs, storyPlatforms) {
  const order = [];
  const seen = {};
  const add = (area, phase) => {
    if (!area) return;
    if (seen[area] === undefined) { seen[area] = order.length; order.push({ area, phase }); }
    else if (phase != null) {
      const cur = order[seen[area]];
      if (cur.phase == null || Number(phase) < Number(cur.phase)) cur.phase = phase;
    }
  };
  for (const r of recs || []) add(r.l3, r.phase);
  for (const p of storyPlatforms || []) {
    for (const g of p.gaps || []) add(g.l3_area, null);
  }
  return order
    .slice()
    .sort((a, b) => (pfNum(a.phase) === null ? 99 : Number(a.phase))
                  - (pfNum(b.phase) === null ? 99 : Number(b.phase)))
    .map(x => x.area);
}

/* One place where the tile axis and the area axis meet, so the three surfaces
   that need the join (the page, the ladder, the roadmap) compute it the same
   way instead of three slightly different ways. Pure: it reads the promoted
   sections through DMA and holds no state. */
function platformScopeOf(entityId) {
  const recs = (DMA.recsFor(entityId) || []);
  const story = DMA.platformStoryFor(entityId) || null;
  const opportunity = DMA.opportunityFor(entityId) || null;
  const storyPlatforms = (story && story.platforms) || [];
  const index = cellAreaIndex(recs, storyPlatforms);
  const tiles = ((opportunity && opportunity.tiles) || []).slice()
    .sort((a, b) => (pfNum(a.rank) === null ? 99 : Number(a.rank))
                  - (pfNum(b.rank) === null ? 99 : Number(b.rank)));
  const assign = new Map();     // tile key → {area, votes, of, exact}
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
    recs, story, opportunity, storyPlatforms, tiles, index, assign, platformOfArea,
    areas: platformAreasOf(recs, storyPlatforms),
    keyOf: (t, i) => pfText(t.platform) || `tile-${i + 1}`,
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
        cell, condition: cond, min,
        current: pfNum(q.current),
        verdict: q.verdict || null,
        basis: q.basis || null,
        note: q.note || null,
        recs: [],
      };
      if (!row.recs.includes(r.id)) row.recs.push(r.id);
      byKey.set(key, row);
    }
  }
  return [...byKey.values()]
    .sort((a, b) => (a.kind === b.kind ? 0 : a.kind === "cell" ? -1 : 1));
}

/* MET / NOT MET as the run states it. The verdict used to be collapsed to a
   boolean and re-labelled "PARTIAL", which is a word no payload contains — the
   run says "NOT MET". Where no verdict was stated but both figures were, the
   comparison is computed and marked as computed. */
function prereqVerdict(p) {
  if (p.verdict) return { text: String(p.verdict), met: String(p.verdict).toUpperCase() === "MET", computed: false };
  if (p.min !== null && p.current !== null) {
    const met = p.current >= p.min;
    return { text: met ? "MET" : "NOT MET", met, computed: true };
  }
  return null;
}

/* ── D4 Platform opportunity ──────────────────────────────────────── */
function ClientPlatform({ entity, run }) {
  const route = useRoute();
  // `audience` decides what an empty field is allowed to say: a customer is
  // told the assessment did not establish it, an internal reader is told it is
  // queued for enrichment. Nothing on this page may print a bare em dash.
  const { audience, setIpSurface, setIpContext, setIpOpen, openEvidence, openRec, openSubcap, pushToast } = useApp();

  const scope = platformScopeOf(entity.id);
  const { recs, story, opportunity, storyPlatforms, tiles, index, assign } = scope;
  const tileKeys = tiles.map((t, i) => scope.keyOf(t, i));

  /* A route parameter selects a tile only where the run promoted that
     platform: a stale link must not select a tile that does not exist and
     blank every panel below it. Links written against the previous build
     carry an L3 AREA rather than a platform name, so an area is accepted too
     and resolves to the tile that scopes it. */
  const routeParam = route.params.platform || null;
  const routeKey = routeParam
    ? (tileKeys.find(k => String(k).toLowerCase() === String(routeParam).toLowerCase())
       || scope.platformOfArea.get(routeParam) || null)
    : null;
  const [pickedKey, setPickedKey] = useState(routeKey);
  const selKey = tileKeys.includes(pickedKey) ? pickedKey : (tileKeys[0] || null);
  const tile = tileKeys.indexOf(selKey) >= 0 ? tiles[tileKeys.indexOf(selKey)] : null;
  const assignment = assign.get(selKey) || { area: null, votes: 0, of: 0, exact: 0 };
  const area = assignment.area;

  const [openPrereq, setOpenPrereq] = useState(null);
  const [openTile, setOpenTile] = useState(null);
  const [openStarter, setOpenStarter] = useState(null);
  const [showDiscarded, setShowDiscarded] = useState(false);
  useEffect(() => { setIpSurface("platform_story"); setIpContext({ entity, platform: selKey }); },
            [selKey, entity?.id]);

  /* Selecting a platform replaces every row beneath it, so a row left open on
     the previous platform must not stay open at the same index in the new
     list — that is how one prerequisite's detail ends up under another's. */
  const selectTile = (key) => { setPickedKey(key); setOpenPrereq(null); setOpenStarter(null); };

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

  const byPhaseThenId = (a, b) =>
    String(a.phase || "").localeCompare(String(b.phase || ""))
      || String(a.id).localeCompare(String(b.id));
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
  const inThisArea = (g) => !!area && g.l3_area === area;
  const storyRows = storyAll.filter(inThisArea);
  const storyElsewhere = storyAll.filter(g => !inThisArea(g));
  const storySeen = new Set(storyRows.map(g => String(g.subcap_id)));
  const tileCells = ((tile && tile.addressable_cells) || [])
    .filter(c => c && !storySeen.has(String(c.subcap_id)));
  const storyGapRow = (g, scoped) => ({
    key: `story:${g.subcap_id}`, from: "story", scoped,
    subcap_id: g.subcap_id, name: g.name, pillar: g.pillar,
    current: pfNum(g.current_score), peer: pfNum(g.peer_score),
    peer_note: g.peer_note || null, peer_basis: g.peer_basis || null,
    feature: g.l4_feature, path: g.catalogue_path, e_ids: g.e_ids || [],
    l3_area: g.l3_area || null,
  });
  const scopedGapRows = [
    ...storyRows.map(g => storyGapRow(g, true)),
    ...tileCells.map(c => ({
      key: `tile:${c.subcap_id}`, from: "tile", scoped: true,
      subcap_id: c.subcap_id, name: c.name, pillar: null,
      current: pfNum(c.current), peer: pfNum(c.peer),
      peer_note: null, peer_basis: null,
      feature: c.feature_that_addresses_it, path: null, e_ids: [],
      l3_area: null,
    })),
  ];
  // A cell already on this platform's own rows is not repeated below the
  // divider — the same cell twice in one table reads as two findings.
  const scopedSeen = new Set(scopedGapRows.map(g => String(g.subcap_id)));
  const otherGapRows = storyElsewhere
    .filter(g => !scopedSeen.has(String(g.subcap_id)))
    .map(g => storyGapRow(g, false));
  const gapRows = [...scopedGapRows, ...otherGapRows];
  // Only render the gap column where at least one row can state a difference.
  // Before, every row printed "−-2.5": a unary minus prepended to an already
  // negative difference, computed against a peer median that does not exist
  // for these cells.
  const anyPeer = gapRows.some(g => g.peer !== null);
  const gapCols = (anyPeer ? 7 : 6);

  const prereqRows = areaPrereqs(areaRecs);
  /* Readiness gates come from the recommendations, so a platform the scope
     reaches no recommendation for used to show an empty rail. The gates of
     every other promoted recommendation are the same run's gates; they are
     listed after this platform's, under the same divider rule. */
  const otherPrereqRows = areaPrereqs(otherRecs)
    .filter(p => !prereqRows.some(q => q.key === p.key));

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
  const allStarters = (DMA.startersFor ? (DMA.startersFor(entity.id) || []) : [])
    .slice().sort((a, b) => (pfNum(a.rank) === null ? 99 : Number(a.rank))
                          - (pfNum(b.rank) === null ? 99 : Number(b.rank)));
  const starterArea = (s) => {
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
  const discarded = ((story && story.discarded) || []).length
    ? story.discarded
    : ((opportunity && opportunity.discarded) || []);

  // Areas the tile row cannot reach. A recommendation filed under one of these
  // appears under no platform, so it is named rather than silently dropped.
  const reachable = new Set([...assign.values()].map(a => a.area).filter(Boolean));
  const orphanRecs = recs.filter(r => !r.l3 || !reachable.has(r.l3));
  const orphanAreas = [];
  for (const r of orphanRecs) if (r.l3 && !orphanAreas.includes(r.l3)) orphanAreas.push(r.l3);

  const scopeLine = area
    ? `${area} · the area this run files ${assignment.votes} of ${assignment.of} of this platform's cells under`
    : (tile
        ? "This run files none of this platform's cells under an L3 area, so nothing below is scoped to it."
        : "No platform tile promoted for this run.");

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Platform opportunity</div>
          <h1>Platform Fit Score</h1>
          <div className="sub">Which platform conversation should lead with {entity.name}?</div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" onClick={() => pushToast(`Exporting ${entity.name} roadmap as PDF…`, "success")}><Icon name="download" size={13} /> Roadmap export</button>
          <button className="btn btn-secondary" onClick={() => { setIpSurface("platform_story"); setIpContext({ entity, platform: selKey }); setIpOpen(true); }}>✦ Platform story</button>
        </div>
      </div>

      {/* ── Promoted platform fit tiles · the page's one selector ──── */}
      {tiles.length ? (
        /* alignItems start: an expanded breakdown stretches its grid row, and
           the collapsed tiles beside it grew to match, leaving a block of
           empty card. */
        <div className={tiles.length === 5 ? "g5" : "g4"} style={{ alignItems: "start", marginBottom: 16 }}>
          {tiles.map((t, i) => {
            // Keyed by the PROMOTED platform string. The vendor-alias fold this
            // replaced collapsed "Salesforce Data Cloud" and "Service Cloud
            // consolidation" onto one key and destroyed a tile.
            const key = scope.keyOf(t, i);
            const isSel = key === selKey;
            const isOpen = openTile === key;
            const a = assign.get(key) || { area: null, votes: 0, of: 0 };
            const cells = (t.addressable_cells || []).filter(Boolean);
            const composite = pfNum(t.composite);
            const tileRecs = a.area ? recs.filter(r => r.l3 === a.area).length : 0;
            /* "Top:" names the cells this platform addresses, in the
               catalogue's own words. The tile states `name: null` for every
               one of them, so the name comes from the workbook read and the id
               stands in where the run does not carry that cell. */
            const top = cells.slice(0, 3)
              .map(c => pfText(c.name) || cellNameOf(cellIndex, c.subcap_id) || pfText(c.subcap_id))
              .filter(Boolean);
            return (
              /* A click on an unselected tile scopes the page to it. A click on
                 the tile ALREADY selected has nothing left to scope, so it
                 opens that tile's own breakdown rather than doing nothing —
                 the QA sweep reads a click that changes no DOM as a dead
                 control, and on the page's most prominent card it reads that
                 way to a person too. */
              <div key={key} className="card-tile clickable"
                title={isSel
                  ? (isOpen ? "Hide the composite breakdown" : "Show the composite breakdown")
                  : `Scope this page to ${key}`}
                onClick={() => { if (isSel) setOpenTile(o => o === key ? null : key); else selectTile(key); }}
                style={{ border: isSel ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)",
                         background: isSel ? "var(--z-ice)" : "#fff" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 600, lineHeight: 1.3 }}>
                      {t.rank != null ? <span className="b b-purple" style={{ marginRight: 5 }}>#{pfText(t.rank)}</span> : null}
                      {pfText(t.platform) || "Platform not named"}
                    </div>
                    {/* The prototype's sub-line is the platform's product list.
                        This run states no product list, and the fact worth
                        carrying in its place is the area the tile scopes —
                        which is what every heading below the tiles reads. */}
                    <div style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 2, lineHeight: 1.4 }} className="txt-fit-2">
                      {a.area || "No L3 area stated for these cells"}
                    </div>
                  </div>
                  <div style={{ textAlign: "right", flexShrink: composite === null ? 1 : 0, minWidth: 0 }}>
                    {/* The numeral's display size is for a numeral. Where the
                        run states no composite the slot carries a label, not a
                        figure, so it drops to label size in the same
                        conditional that already sets its colour — at 26px the
                        words would push the platform name out of the tile.

                        `flexShrink` moves with it. A three-character numeral
                        must never shrink; a sentence must, because the customer
                        wording is the long one ("Not established in this
                        assessment", which `compact` does not shorten) and an
                        unshrinkable slot that wide collapses the platform name
                        beside it in a five-up grid. */}
                    <div style={{ fontSize: composite === null ? 11.5 : 26, fontWeight: composite === null ? 400 : 200, color: composite === null ? "var(--z-muted)" : "var(--z-teal)", lineHeight: 1.15 }}>
                      {composite === null
                        ? <EnrichmentGap what="Platform fit score" audience={audience} compact />
                        : composite.toFixed(1)}
                    </div>
                    <div className="f-mono" style={{ fontSize: 9, color: "var(--z-muted)" }}>/100 fit</div>
                  </div>
                </div>
                {/* Both counts are computed from this tile's own rows and this
                    run's own recommendations (invariant 8). The prototype's
                    "3 absent" was a literal on all five of its tiles, and the
                    gap count it sat beside was a scan of every cell below 3.0
                    in the workbook — 346 of them under "Salesforce". */}
                <div className="row" style={{ marginTop: 10, gap: 4, fontSize: 11, flexWrap: "wrap" }}>
                  <span className="b b-org">{cells.length} cell{cells.length === 1 ? "" : "s"}</span>
                  {a.area ? <span className="b b-muted">{tileRecs} rec{tileRecs === 1 ? "" : "s"}</span> : null}
                </div>
                {top.length ? (
                  <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 6, lineHeight: 1.45 }} className="txt-fit-2">
                    Top: {top.join(" · ")}
                  </div>
                ) : null}
                {/* The breakdown is a control INSIDE the selector, so its click
                    must not also re-select the tile it sits in. */}
                <div className="row" style={{ marginTop: 8, fontSize: 10, color: "var(--z-mid)" }}>
                  <span className="spacer" />
                  <button className="btn btn-tertiary btn-sm" style={{ color: "var(--z-mid)" }}
                    title={isOpen ? "Hide the composite breakdown" : "Show the composite breakdown"}
                    onClick={(ev) => { ev.stopPropagation(); setOpenTile(o => o === key ? null : key); }}>
                    {isOpen ? "Hide breakdown" : "Breakdown"}
                    <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={12} />
                  </button>
                </div>
                {isOpen ? (
                  <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--z-sep)" }}>
                    {t.relevance != null ? (
                      <div className="row" style={{ gap: 5, marginBottom: 6 }}>
                        <span className="b b-muted f-mono" title="relevance to the assessed gaps">{Number(t.relevance).toFixed(2)}</span>
                        <span style={{ fontSize: 9.5, color: "var(--z-muted)" }}>relevance</span>
                      </div>
                    ) : null}
                    {/* The stack prose belongs here, not on the tile face: at
                        four lines of grey it was the tallest thing on the row
                        and buried the score it explains. */}
                    {t.their_stack_context ? (
                      <div style={{ fontSize: 10.5, color: "var(--z-body)", marginBottom: 8, lineHeight: 1.5 }}>
                        {pfText(t.their_stack_context)}
                      </div>
                    ) : null}
                    {(t.factors || []).length ? (
                      <>
                        <div className="eyebrow" style={{ fontSize: 9, marginBottom: 5 }}>Composite factors</div>
                        {t.factors.map((f, j) => (
                          <div key={j} className="row" style={{ fontSize: 10, gap: 5, marginBottom: 3 }}>
                            <span style={{ color: "var(--z-muted)", width: 78, flexShrink: 0 }}
                              title={f.weight != null ? `weight ${f.weight}` : ""}>{String(f.name || "").replace(/_/g, " ")}</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div className="prog" style={{ height: 4 }}>
                                <div className="prog-fill" style={{ width: `${Math.max(0, Math.min(100, (pfNum(f.value) || 0) * 10))}%` }} />
                              </div>
                            </div>
                            {f.contribution != null ? (
                              <span className="f-mono" style={{ fontSize: 9, color: "var(--z-muted)", width: 34, textAlign: "right", flexShrink: 0 }}
                                title="contribution to the composite">+{Number(f.contribution).toFixed(1)}</span>
                            ) : null}
                          </div>
                        ))}
                      </>
                    ) : null}
                    {cells.length ? (
                      <>
                        <div className="eyebrow" style={{ fontSize: 9, margin: "8px 0 5px" }}>Cells it addresses</div>
                        <div style={{ display: "grid", gap: 4 }}>
                          {cells.map((c, j) => {
                            const sid = pfText(c.subcap_id);
                            return (
                              <div key={j} className="row" style={{ gap: 5, fontSize: 10, alignItems: "flex-start" }}>
                                {/* A cell id is a drill target everywhere else on
                                    the page; as a bare span these chips were the
                                    QA sweep's DEAD targets. */}
                                {sid ? (
                                  <button className="chip f-mono" style={{ fontSize: 9, flexShrink: 0 }}
                                    title={`Open ${sid} in the heatmap`}
                                    onClick={(ev) => { ev.stopPropagation(); openSubcap(sid); }}>{sid}</button>
                                ) : null}
                                {pfNum(c.current) !== null ? <MaturityChip score={pfNum(c.current)} /> : null}
                                <span style={{ flex: 1, minWidth: 0, color: "var(--z-body)", lineHeight: 1.45 }}>{pfText(c.feature_that_addresses_it) || pfText(c.name) || ""}</span>
                              </div>
                            );
                          })}
                        </div>
                      </>
                    ) : null}
                    {t.rank_rationale ? (
                      <div style={{ fontSize: 10.5, color: "var(--z-body)", marginTop: 8, lineHeight: 1.55 }}>{pfText(t.rank_rationale)}</div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="card" style={{ marginBottom: 16, fontSize: 12, color: "var(--z-muted)" }}>
          The opportunity surface did not promote for this run, so no platform fit score is available.
        </div>
      )}

      {/* Selected platform — its gap mapping and its readiness.
          Was `grid: minmax(0,1fr) 380px` — a fixed sidebar that no media query
          catches (the app.css override matches the literal "1fr 380px" only),
          so at 768px the table column was ~110px wide. Flex-wrap sidebar
          pattern instead: side by side while both fit at a readable width
          (the 999 grow gives the table nearly all the slack, so the readiness
          column holds ~300px), stacked below that. No media query needed.

          The table's basis is what decides WHEN the pair stops sitting side
          by side, and it is stated as the width the table wants rather than
          the width the card can survive: a flex line wraps once the bases
          plus the gap exceed it, so at 560 + 300 + 16 the readiness rail
          drops below the table at about 1150px of browser and the table takes
          the whole column back — the width at which a seven-column table is
          readable again. At the old 400 the pair stayed side by side down to
          ~940px with the table at 480, which is the state the reader had to
          scroll sideways out of. */}
      <div id="platform-area-detail" style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", gap: 16, marginBottom: 16 }}>
        <div className="card flush" style={{ flex: "999 1 560px", minWidth: 0, maxWidth: "100%" }}>
          <div className="card-head">
            <div style={{ minWidth: 0 }}>
              <h3>Gap-to-platform mapping · {selKey || "no platform promoted"}</h3>
              <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 2, lineHeight: 1.45 }}>{scopeLine}</div>
            </div>
            <span style={{ fontSize: 11, color: "var(--z-muted)", flexShrink: 0, textAlign: "right" }}>
              {scopedGapRows.length} mapped cell{scopedGapRows.length === 1 ? "" : "s"}
              {storyRows.length && tileCells.length ? (
                <div style={{ fontSize: 9.5 }}>{storyRows.length} from the story · {tileCells.length} from the tile</div>
              ) : null}
            </span>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {/* `tbl-reflow` (app.css) makes this table answer to the width of
                the COLUMN it sits in rather than to the viewport: full columns
                while the card is wide, the `col-drop` column gone while it is
                medium, and one card per row while it is narrow. The box no
                longer scrolls sideways in any of those states, which is what
                the previous fix — a 720px floor inside an overflow-x box —
                traded away to stop the columns collapsing. */}
            <div className="tbl-reflow">
            <table className="tbl">
              {/* nowrap on the narrow columns: at this width "PILLAR" and
                  "SCORE" broke mid-word into "PILLA / R" and "SCOR / E".
                  Pillar carries `col-drop` because it is the ONLY column whose
                  fact the row prints twice — the pillar is the first token of
                  the cell id under the name — so at a medium width the table
                  loses a column and no information. In the stacked mode it
                  returns as a labelled line, where it costs no width. */}
              <thead><tr>
                <th>Cell</th>
                <th className="col-drop" style={{ whiteSpace: "nowrap" }}>Pillar</th>
                <th style={{ whiteSpace: "nowrap" }}>Score</th>
                <th style={{ whiteSpace: "nowrap" }}>Peer</th>
                {anyPeer ? <th style={{ whiteSpace: "nowrap" }}>Gap</th> : null}
                <th>Feature / L4</th><th>Evidence</th>
              </tr></thead>
              <tbody>
                {gapRows.map(g => {
                  const wb = cellIndex.get(String(g.subcap_id)) || null;
                  const name = pfText(g.name) || (wb && wb.name) || pfText(g.subcap_id);
                  const pillar = pfText(g.pillar) || (wb && wb.pillar)
                    || (/^(P\d+)/.exec(String(g.subcap_id || "")) || [])[1] || null;
                  const cur = g.current !== null ? g.current : (wb ? pfNum(wb.score) : null);
                  const peer = g.peer !== null ? g.peer : (wb ? pfNum(wb.peerMedian) : null);
                  // Computed-or-null: a delta exists only where both figures do,
                  // and it carries its own sign — no minus is prepended.
                  const delta = (cur !== null && peer !== null) ? Math.round((cur - peer) * 100) / 100 : null;
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
                  const peerWhy = pfText(g.peer_note)
                    || (g.peer_basis ? String(g.peer_basis).replace(/_/g, " ")
                                     : (wb && wb.peer_basis ? String(wb.peer_basis).replace(/_/g, " ")
                                                            : "No peer figure is stated for this cell"));
                  /* A missing peer with a stated basis is HELD, not silent: the
                     producer ran the comparison and the figure failed. Tile
                     rows carry `peer_basis: null` by construction, so those are
                     a real gap and read as one. Guarded on `peer === null`
                     because a basis beside a PRESENT peer describes how that
                     figure was derived (category_proxy), not why one is
                     missing. */
                  const peerHeld = peer === null
                    && !!(pfText(g.peer_note) || g.peer_basis || (wb && wb.peer_basis));
                  // The first row the derived scope does not reach carries the
                  // divider; the rows under it are the same run's promoted gap
                  // rows, filed under another platform's area.
                  const first = !g.scoped && otherGapRows.length && otherGapRows[0].key === g.key;
                  return (
                    <React.Fragment key={g.key}>
                    {first ? (
                      <tr className="tbl-split"><td className="tbl-split" colSpan={gapCols}>
                        {scopedGapRows.length} of {gapRows.length} mapped cells sit in {area || "no area this page could derive"} · the rest of this run's gap rows below
                      </td></tr>
                    ) : null}
                    <tr style={{ opacity: g.scoped ? 1 : .78 }}>
                      <td data-label="Cell">
                        <div style={{ fontSize: 12, fontWeight: 500 }}>{name}</div>
                        <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{pfText(g.subcap_id)}</div>
                        {!g.scoped && g.l3_area ? (
                          <div style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 2 }}>{pfText(g.l3_area)}</div>
                        ) : null}
                      </td>
                      <td data-label="Pillar" className="col-drop">{pillar ? <span className="b b-purple">{pillar}</span> : <EnrichmentGap what="Pillar" audience={audience} compact />}</td>
                      <td data-label="Score"><MaturityChip score={cur} /></td>
                      <td data-label="Peer">{peer !== null ? <MaturityChip score={peer} /> : (
                        <EnrichmentGap what="Peer score" held={peerHeld}
                          reason={peerHeld ? peerWhy : undefined} audience={audience} compact />
                      )}</td>
                      {anyPeer ? (
                        /* The delta is arithmetic, so it carries the state of
                           its inputs: held where the peer is held, an ordinary
                           gap where a score is simply not stated. The reason
                           itself is not repeated here — it is one cell to the
                           left and belongs to the figure it explains, not to a
                           subtraction. */
                        <td data-label="Gap">{delta === null ? <EnrichmentGap what="Gap to peer" held={peerHeld} audience={audience} compact /> : (
                          <span className="f-mono" style={{ color: delta < 0 ? "var(--z-below)" : "var(--z-above)" }}>{delta > 0 ? `+${delta.toFixed(1)}` : delta.toFixed(1)}</span>
                        )}</td>
                      ) : null}
                      {/* The catalogue path is a tooltip rather than a second
                          line: at 9.5px under every feature it doubled the
                          height of every row and pushed the table past the
                          readiness column beside it. */}
                      <td data-label="Feature / L4" title={pfText(g.path) || ""}>
                        <div style={{ fontSize: 11.5, color: "var(--z-dark)" }}>
                          {pfText(g.feature) || <EnrichmentGap what="Feature / L4" audience={audience} compact />}
                        </div>
                      </td>
                      <td data-label="Evidence"><PlatformEvChips ids={eids} openEvidence={openEvidence} /></td>
                    </tr>
                    </React.Fragment>
                  );
                })}
                {gapRows.length === 0 ? (
                  <tr><td colSpan={gapCols} className="tbl-empty">
                    No platform story gap row and no addressable cell promoted in this run,
                    so there is no gap mapping to show for any platform.
                  </td></tr>
                ) : null}
              </tbody>
            </table>
            </div>
            {/* The story argues for the rows above it, so it sits under them
                rather than in a card of its own.

                It was gated on `storyRows.length` and each platform was matched
                by `g.l3_area === area` — the DERIVED area join. The page's own
                rule two hundred lines up says a derived relationship may order
                content and must never hide it, and this block broke that rule
                against itself: when the derivation produced no area, all five
                promoted platform stories and every fact behind them vanished
                from the page. Measured against the live run: five stories, five
                readiness verdicts, twenty-five cited peer rows, zero rendered.

                The reader's selection is a STATED join — the tile and the story
                both name the platform — so it leads, and the run's other
                platforms follow. Nothing is scoped away. */}
            {storyPlatforms.length ? (() => {
              const named = (p) => pfText(p && p.platform) || "";
              const isSel = (p) => !!selKey && named(p) === selKey;
              const ordered = [...storyPlatforms.filter(isSel),
                               ...storyPlatforms.filter(p => !isSel(p))];
              const block = (p, i, lead) => {
                const md = pfText(p.story_md);
                const fit = pfNum(p.fit_score);
                const rank = pfNum(p.rank);
                const name = named(p);
                // The dossier used to be gated behind `story_md`, so a platform
                // with a full evidence base and no narrative rendered nothing.
                // Either half earns the block.
                const dossier = <PlatformDossier p={p} openEvidence={openEvidence} />;
                if (!md && !p.estate_reach && !p.readiness
                    && !(p.peer_deployments || []).length) return null;
                return (
                  <div key={`${name}-${i}`} style={{ padding: "12px 18px", borderTop: "1px solid var(--z-sep)", fontSize: 12, color: "var(--z-body)", lineHeight: 1.65 }}>
                    <div className="row" style={{ gap: 6, alignItems: "baseline", marginBottom: 5, flexWrap: "wrap" }}>
                      <div className="eyebrow" style={{ fontSize: 9.5 }}>
                        {lead ? "What this platform changes" : name}
                      </div>
                      <span className="spacer" />
                      {/* The number the page ranks by was served on every
                          platform and shown on none of them, so the order was
                          asserted and never justified. `fit_basis` says where
                          it came from and rides on the tooltip. */}
                      {fit !== null ? (
                        <span className="b b-muted f-mono" style={{ flexShrink: 0 }}
                          title={pfText(p.fit_basis) || ""}>
                          {rank !== null ? `rank ${rank} · ` : ""}fit {fit.toFixed(1)}
                        </span>
                      ) : null}
                    </div>
                    {md}
                    {dossier}
                  </div>
                );
              };
              const lead = ordered[0] && isSel(ordered[0]) ? ordered[0] : null;
              const rest = lead ? ordered.slice(1) : ordered;
              return (
                <>
                  {lead ? block(lead, 0, true) : null}
                  {rest.length ? (
                    <div style={{ padding: "8px 18px 0", borderTop: "1px solid var(--z-sep)" }}>
                      <div className="eyebrow" style={{ fontSize: 9 }}>
                        {lead ? `The run's other promoted platforms · ${rest.length}`
                              : `Promoted platform stories · ${rest.length}`}
                      </div>
                    </div>
                  ) : null}
                  {rest.map((p, i) => block(p, i + 1, false))}
                </>
              );
            })() : null}
          </div>
        </div>

        <div className="card" style={{ flex: "1 1 300px", minWidth: 0, maxWidth: "100%" }}>
          <div className="row" style={{ marginBottom: 10, gap: 6 }}>
            <Icon name="shield" size={16} />
            <div style={{ fontSize: 13, fontWeight: 600, flex: 1, minWidth: 0 }} className="txt-fit-1"
              title={selKey ? `Readiness · ${selKey}` : ""}>Readiness · {selKey || "no platform"}</div>
            <span style={{ fontSize: 10, color: "var(--z-muted)", flexShrink: 0 }}>click a row to drill in</span>
          </div>
          {[...prereqRows, ...otherPrereqRows].map((p, idx) => {
            const v = prereqVerdict(p);
            const isOpen = openPrereq === idx;
            // The divider rides on the first gate the derived scope does not
            // reach, so a platform whose area matches no recommendation still
            // shows this run's gates rather than an empty rail.
            const split = idx === prereqRows.length && otherPrereqRows.length ? (
              <div key="split" style={{ padding: "8px 0 6px", borderTop: "1px solid var(--z-sep)", fontSize: 10, color: "var(--z-muted)", lineHeight: 1.5 }}>
                {prereqRows.length} of {prereqRows.length + otherPrereqRows.length} gates belong to {selKey || "this platform"} · this run's other gates below
              </div>
            ) : null;
            if (p.kind === "condition") {
              /* A text condition has no cell, no minimum and no current value,
                 so it gets its own row shape — but the SAME height as a
                 threshold row. It used to render the condition as a 317px
                 badge, its note and its recommendation chips all at once, three
                 stacked blocks per row in a 300px column. */
              return (
                <React.Fragment key={p.key}>
                {split}
                <div style={{ borderBottom: "1px solid var(--z-sep)" }}>
                  {/* The word "Condition" is an eyebrow, not a badge in the
                      row. As a badge it took 78px of a 300px column and the
                      condition itself — the only thing the row is about — was
                      clamped to "Architecture…". */}
                  <button onClick={() => setOpenPrereq(o => o === idx ? null : idx)}
                    title={pfText(p.condition) || ""}
                    style={{ width: "100%", background: "none", border: 0, cursor: "pointer", textAlign: "left", padding: "10px 0" }}>
                    <div className="row" style={{ gap: 6, marginBottom: 3 }}>
                      <span style={{ fontSize: 9, color: "var(--z-muted)", letterSpacing: ".06em", textTransform: "uppercase", flexShrink: 0 }}>Condition</span>
                      <span className="spacer" />
                      {p.basis ? <span className="b b-above" style={{ flexShrink: 0 }}>{pfText(p.basis)}</span> : null}
                      <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={13} style={{ color: "var(--z-muted)", flexShrink: 0 }} />
                    </div>
                    <div style={{ fontSize: 12, lineHeight: 1.45 }} className="txt-fit-2">{pfText(p.condition)}</div>
                  </button>
                  {isOpen ? (
                    <div style={{ padding: "0 0 12px" }}>
                      <div style={{ fontSize: 11.5, color: "var(--z-dark)", lineHeight: 1.5, marginBottom: 4 }}>{pfText(p.condition)}</div>
                      {p.note ? (
                        <div style={{ fontSize: 11, color: "var(--z-muted)", marginBottom: 5, lineHeight: 1.5 }}>{pfText(p.note)}</div>
                      ) : null}
                      <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 9, color: "var(--z-muted)", letterSpacing: ".06em", textTransform: "uppercase" }}>Required by</span>
                        {p.recs.map(rid => (
                          <button key={rid} className="chip" style={{ cursor: "pointer", border: 0 }} title={`Open ${rid}`}
                            onClick={() => openRec(rid)}>{rid}</button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
                </React.Fragment>
              );
            }
            // Cell threshold. Keyed by index so two thresholds on the same cell
            // cannot share an open state.
            const cat = p.cell ? DMA.getCategory(p.cell) : null;
            const subs = (entity.subcaps || []).filter(s => String(s.id).startsWith(`${p.cell}.`));
            const ev = (DMA.EVIDENCE || []).filter(e => (e.subcaps || []).some(sid => String(sid).startsWith(`${p.cell}.`)));
            const pct = (p.min !== null && p.current !== null && p.min > 0)
              ? Math.max(0, Math.min(100, (p.current / p.min) * 100)) : null;
            return (
              <React.Fragment key={p.key}>
              {split}
              <div style={{ borderBottom: "1px solid var(--z-sep)" }}>
                <button onClick={() => setOpenPrereq(o => o === idx ? null : idx)} style={{ width: "100%", background: "none", border: 0, cursor: "pointer", textAlign: "left", padding: "10px 0" }}>
                  {/* The prototype's row is a chip, a NAME and a verdict. The
                      name is the catalogue's own category name for the cell —
                      the row used to print the threshold here instead, which
                      left the reader with two numbers and no subject. */}
                  <div className="row" style={{ marginBottom: 4, gap: 6 }}>
                    <span className="b b-purple" style={{ flexShrink: 0 }}>{pfText(p.cell)}</span>
                    <span style={{ fontSize: 12, flex: 1, minWidth: 0 }} className="txt-fit-1">
                      {(cat && cat.name) || (p.min === null ? "Threshold not stated" : `Threshold ≥ ${p.min.toFixed(1)}`)}
                    </span>
                    {v ? (
                      <span className={`b ${v.met ? "b-above" : "b-org"}`} style={{ flexShrink: 0 }} title={v.computed ? "computed from the stated minimum and current value" : "verdict as promoted"}>{v.text}</span>
                    ) : null}
                    <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={13} style={{ color: "var(--z-muted)", flexShrink: 0 }} />
                  </div>
                  <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
                    {p.min === null ? "Min not stated" : `Min ${p.min.toFixed(1)}`} · {p.current === null ? "current not stated" : `Current ${p.current.toFixed(2)}`} · {subs.length} cells · {ev.length} evidence
                  </div>
                  {pct !== null ? (
                    <div className="prog" style={{ marginTop: 4, height: 4 }}>
                      <div className="prog-fill" style={{ width: `${pct}%`, background: v && v.met ? "var(--z-mid)" : "var(--z-org)" }} />
                    </div>
                  ) : null}
                </button>
                {isOpen ? (
                  <div style={{ padding: "2px 0 12px" }}>
                    <div className="row" style={{ gap: 4, flexWrap: "wrap", marginBottom: 6 }}>
                      <span style={{ fontSize: 9, color: "var(--z-muted)", letterSpacing: ".06em", textTransform: "uppercase" }}>Required by</span>
                      {p.recs.map(rid => (
                        <button key={rid} className="chip" style={{ cursor: "pointer", border: 0 }} title={`Open ${rid}`}
                          onClick={() => openRec(rid)}>{rid}</button>
                      ))}
                    </div>
                    {subs.length ? <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", margin: "6px 0 4px" }}>Backing cells</div> : null}
                    {subs.slice(0, 6).map(s => (
                      <div key={s.id} className="row" style={{ gap: 6, padding: "3px 0" }}>
                        {/* `fx` returns the em dash for an unscored cell and
                            stays that way on purpose (it feeds 40-odd template
                            literals a component would print as [object Object]),
                            so the guard belongs at the call site — utils.jsx
                            says so where fx is defined.

                            The badge shell goes with the numeral rather than
                            being kept around a label. `.b` is `white-space:
                            nowrap` and this rail is ~300px: the customer
                            sentence is not shortened by `compact`, so nowrap
                            would run it out of the card. Bare, it shrinks and
                            wraps, and it matches the four other gaps on this
                            page. */}
                        {s.score == null
                          ? <span style={{ flex: "0 1 auto", minWidth: 0 }}>
                              <EnrichmentGap what={`${s.id} score`} audience={audience} compact />
                            </span>
                          : <span className={`b ${DMA.helpers.maturityClass(s.score)}`} style={{ width: 30, justifyContent: "center", flexShrink: 0 }}>{fx(s.score, 1)}</span>}
                        <span style={{ fontSize: 11.5, color: "var(--z-dark)", flex: 1, minWidth: 0 }} className="txt-fit-1">{s.name}</span>
                        <span className="f-mono" style={{ fontSize: 9.5, color: "var(--z-muted)", flexShrink: 0 }}>{s.id}</span>
                      </div>
                    ))}
                    {subs.length > 6 ? (
                      <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 3 }}>+{subs.length - 6} more cells in {p.cell}</div>
                    ) : null}
                    {ev.length ? (
                      <>
                        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", margin: "8px 0 4px" }}>Evidence · click to open</div>
                        <PlatformEvChips ids={ev.slice(0, 12).map(e => e.id)} openEvidence={openEvidence} />
                      </>
                    ) : null}
                  </div>
                ) : null}
              </div>
              </React.Fragment>
            );
          })}
          {prereqRows.length + otherPrereqRows.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--z-muted)" }}>
              {recs.length
                ? "No recommendation in this run promoted a prerequisite, so no readiness gate applies."
                : "No recommendation promoted in this run, so no readiness gate applies."}
            </div>
          ) : null}
          {prereqRows.some(p => { const v = prereqVerdict(p); return v && !v.met; }) ? (
            <div className="co co-org" style={{ marginTop: 10 }}>
              <Icon name="warn" size={14} />
              <div><div className="co-title">Advisory</div><div className="co-body">
                A threshold here is not met. The unmet prerequisite is the conversation that comes first.
              </div></div>
            </div>
          ) : null}
        </div>
      </div>

      {/* Recommendation cards + Conversation starters. Two columns only while
          each keeps a readable width; below that they stack (the fixed 1fr/1fr
          pair escaped every media query and halved to ~250px at tablet). */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 340px), 1fr))", gap: 16, marginBottom: 16 }}>
        <div className="card flush">
          <div className="card-head">
            <div style={{ minWidth: 0 }}>
              <h3>Recommendations · {selKey || "no platform promoted"}</h3>
              {area ? <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 2 }}>{area}</div> : null}
            </div>
            <span style={{ fontSize: 11, color: "var(--z-muted)", flexShrink: 0 }}>{areaRecs.length} of {recs.length} promoted</span>
          </div>
          <div>
            {[...areaRecs, ...otherRecs].map(r => {
              const gate = r.validation_gate || null;
              const kpi = r.kpi || null;
              const impacts = (r.dma_impact || []).length;
              const scoped = areaRecs.indexOf(r) >= 0;
              // The divider rides on the first row the scope does not reach.
              const first = !scoped && otherRecs.length && otherRecs[0].id === r.id;
              return (
                <React.Fragment key={r.id}>
                {first ? (
                  <div style={{ padding: "8px 18px", background: "var(--z-bg)", borderTop: "1px solid var(--z-sep)", borderBottom: "1px solid var(--z-sep)", fontSize: 10, color: "var(--z-muted)", lineHeight: 1.5 }}>
                    {areaRecs.length} of {recs.length} promoted recommendations sit in {area || "no area this page could derive for this tile"} · the rest of this run's below, each still openable
                  </div>
                ) : null}
                <div className="rec-row" onClick={() => openRec(r.id)} title="Open full recommendation" style={{ padding: "12px 18px", borderBottom: "1px solid var(--z-sep)", cursor: "pointer", opacity: scoped ? 1 : .82 }}>
                  {/* wrap: the title, two badges and the chevron do not fit on
                      one line in a column that halves at tablet width, and the
                      badges were pushing the title's own box past the card. */}
                  <div className="row" style={{ marginBottom: 4, gap: 6, flexWrap: "wrap" }}>
                    <span className="chip">{r.id}</span>
                    <span style={{ fontWeight: 600, fontSize: 13, flex: "1 1 160px", minWidth: 0 }}>{pfText(r.title)}</span>
                    {r.phase != null ? <span className="b b-teal" style={{ flexShrink: 0 }}>Phase {pfText(r.phase)}</span> : null}
                    {r.effort ? <span className="b b-muted" style={{ flexShrink: 0 }} title="effort band">{pfText(r.effort)}</span> : null}
                    <Icon name="chevron-r" size={13} style={{ color: "var(--z-muted)", flexShrink: 0 }} />
                  </div>
                  {!scoped && r.l3 ? (
                    <div style={{ fontSize: 10, color: "var(--z-muted)", marginBottom: 4 }}>{pfText(r.l3)}</div>
                  ) : null}
                  {r.l4 ? <div style={{ fontSize: 11, color: "var(--z-mid)", marginBottom: 5, overflowWrap: "anywhere" }}>{pfText(r.l4)}</div> : null}
                  {r.root_cause_text ? (
                    <div style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.55, margin: "6px 0" }} className="txt-fit-3">
                      {pfText(r.root_cause_text)}
                    </div>
                  ) : null}
                  <PlatformEvChips ids={r.root_cause} openEvidence={openEvidence} label="cites" />
                  {/* auto-fit, not a hard pair: at `repeat(2, 1fr)` each slot
                      was ~110px in a column that halves at tablet width, and
                      the KPI sentence ran out of its half. */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 150px), 1fr))", gap: 8, marginTop: 8, fontSize: 11 }}>
                    {gate && gate.threshold ? (
                      <div>
                        <div className="muted" style={{ fontSize: 10 }}>Readiness gate</div>
                        <strong className="f-mono" style={{ fontSize: 11 }} title={pfText(gate.grain_note) || ""}>{pfText(gate.threshold)}</strong>
                        {gate.verdict ? <span className={`b ${String(gate.verdict).toUpperCase() === "MET" ? "b-above" : "b-org"}`} style={{ marginLeft: 5 }}>{pfText(gate.verdict)}</span> : null}
                      </div>
                    ) : null}
                    <div>
                      <div className="muted" style={{ fontSize: 10 }}>Cells it moves</div>
                      <strong>{impacts}</strong>
                    </div>
                    {kpi && kpi.metric ? (
                      /* 1/-1 rather than "span 2": with an auto-fit track count
                         the grid may only HAVE one column, and a 2-wide item in
                         a 1-wide grid adds an implicit column the row then
                         overflows into. 1/-1 is "the whole row", whatever the
                         count came out as. */
                      <div style={{ gridColumn: "1 / -1", minWidth: 0 }}>
                        <div className="muted" style={{ fontSize: 10 }}>KPI</div>
                        <strong style={{ fontWeight: 500 }}>{pfText(kpi.metric)}</strong>
                        {kpi.baseline ? (
                          <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 2, lineHeight: 1.5 }}>
                            Baseline · {pfText(kpi.baseline)}{kpi.baseline_as_of ? ` · ${kpi.baseline_as_of}` : ""}
                          </div>
                        ) : null}
                        {kpi.target ? (
                          <div style={{ fontSize: 10.5, color: "var(--z-mid)", marginTop: 2, lineHeight: 1.5 }}>Target · {pfText(kpi.target)}</div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </div>
                </React.Fragment>
              );
            })}
            {recs.length === 0 ? (
              <div className="empty"><p>No recommendation promoted in this run.</p></div>
            ) : null}
            {/* A recommendation filed under an area no tile reaches is now in
                the list above like every other one; this line still names the
                areas, because "no promoted platform addresses this" is a fact
                about the run worth stating once. */}
            {orphanAreas.length ? (
              <div style={{ padding: "10px 18px", fontSize: 11, color: "var(--z-muted)", borderTop: "1px solid var(--z-sep)", lineHeight: 1.6 }}>
                {orphanRecs.length} of the {recs.length} promoted recommendation{recs.length === 1 ? "" : "s"} sit{orphanRecs.length === 1 ? "s" : ""} in an area no promoted platform addresses — {orphanAreas.join(" · ")}.
              </div>
            ) : null}
          </div>
        </div>

        <div className="card flush">
          <div className="card-head">
            <div style={{ minWidth: 0 }}>
              <h3>Conversation starters · {starters.length}</h3>
              {/* The sub-line says which platform the list is under AND how
                  much of it this page could actually place there, because
                  those are different facts and the heading alone reads as a
                  claim that all of them are this platform's. Both numbers are
                  counted from the rows above. */}
              <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 2, lineHeight: 1.45 }}>
                {selKey || "no platform promoted"}
                {unplacedStarters
                  ? ` · ${unplacedStarters} of ${starters.length} name${unplacedStarters === 1 ? "s" : ""} no cell this run files under a platform area, so ${unplacedStarters === 1 ? "it shows" : "they show"} under every platform`
                  : ""}
              </div>
            </div>
            {/* flexShrink 0: `.btn` is nowrap, and in a space-between head it
                was being shrunk below its own label — "Copy all" spilled its
                box at 1100px. */}
            <button className="btn btn-tertiary btn-sm" style={{ flexShrink: 0 }} onClick={() => {
              const text = starters.map((s, i) => {
                const head = `#${s.rank != null ? s.rank : i + 1}`;
                return [`${head} — ${pfText(s.text) || ""}`,
                        s.followup_question ? `Follow-up: ${pfText(s.followup_question)}` : null,
                        (s.e_ids || []).length ? `Evidence: ${s.e_ids.join(", ")}` : null]
                  .filter(Boolean).join("\n");
              }).join("\n\n");
              try { navigator.clipboard.writeText(text); pushToast(`Copied ${starters.length} conversation starters`, "success"); }
              catch (e) { pushToast("Couldn't access clipboard", "warn"); }
            }}><Icon name="copy" size={12} /> Copy all</button>
          </div>
          <div style={{ padding: 14 }}>
            {starters.map((s, i) => {
              const key = s.rank != null ? `r${s.rank}` : `i${i}`;
              const isOpen = openStarter === key;
              const cites = (s.e_ids || []).filter(Boolean);
              const extras = [s.their_system_reference, s.peer_reference, s.followup_question]
                .filter(Boolean).length + (cites.length ? 1 : 0);
              /* The prototype's card carries a small grey stamp under the rank
                 — "Template-fill · evidence-cited". That stamp was a literal:
                 every card wore it whether or not the starter cited anything.
                 Same position, same weight, but each half is read off this
                 starter: what it opens on, and how many evidence ids it
                 actually carries. A starter citing nothing says so, which is
                 the one thing the prototype's version could never do. */
              const stamp = [
                s.opens_on ? `opens on ${String(s.opens_on).replace(/_/g, " ")}` : null,
                cites.length ? `${cites.length} cited` : "not cited",
              ].filter(Boolean).join(" · ");
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
              return (
                <React.Fragment key={key}>
                {first ? (
                  <ScopeDivider shown={scopedStarters.length} total={allStarters.length}
                                noun="starter" scope={area || null} />
                ) : null}
                {/* One card, one target: the whole face expands it. The "More"
                    button stays — it is what NAMES the hidden half — but a
                    reader who clicks the paragraph should not have to find a
                    10px control to see the rest of the same starter. */}
                <div style={{ padding: 10, marginBottom: 8, background: "var(--ph0-lt)", border: `1px solid ${scoped ? "var(--ph0-bd)" : "var(--z-sep)"}`, borderRadius: 8, opacity: scoped ? 1 : .84, cursor: extras ? "pointer" : "default" }}
                  title={extras && !isOpen ? "Show the rest of this starter" : ""}
                  onClick={() => { if (extras) setOpenStarter(o => o === key ? null : key); }}>
                  <div className="row" style={{ marginBottom: 6, gap: 6, flexWrap: "wrap" }}>
                    <span className="b b-purple" style={{ flexShrink: 0 }}>#{s.rank != null ? s.rank : i + 1}</span>
                    {stamp ? <span style={{ fontSize: 10, color: "var(--z-dpur)", opacity: .85 }}>{stamp}</span> : null}
                    {gapCell ? (
                      <button className="chip f-mono" style={{ fontSize: 9, flexShrink: 0 }}
                        title={`The gap this starter names — open ${gapCell} in the heatmap`}
                        onClick={(ev) => { ev.stopPropagation(); openSubcap(gapCell); }}>{gapCell}</button>
                    ) : gapId ? (
                      <span className="chip muted f-mono" style={{ fontSize: 9, flexShrink: 0, cursor: "default" }}
                        title="the gap this starter names - not a cell id this run scored, so it opens nothing">{gapId}</span>
                    ) : null}
                    <span className="spacer" />
                    <button className="btn btn-tertiary btn-sm" style={{ color: "var(--z-dpur)" }} title="Copy this starter" onClick={(ev) => {
                      ev.stopPropagation();
                      const one = [pfText(s.text), s.followup_question ? `Follow-up: ${pfText(s.followup_question)}` : null].filter(Boolean).join("\n");
                      try { navigator.clipboard.writeText(one); pushToast("Conversation starter copied", "success"); }
                      catch (e) { pushToast("Couldn't access clipboard", "warn"); }
                    }}><Icon name="copy" size={11} /></button>
                  </div>
                  {/* Collapsed, the card is the starter's opening lines at the
                      prototype's density — four lines, so several fit on one
                      screen. The system reference, the peer line, the follow-up
                      question and the citations are the rest of the SAME card,
                      one click away, rather than four stacked blocks that made
                      each starter a page of its own. */}
                  <div style={{ fontSize: 12, color: "#3B0764", lineHeight: 1.6 }}
                    className={isOpen ? "" : "txt-fit-4"} title={isOpen ? "" : (pfText(s.text) || "")}>
                    {pfText(s.text)}
                  </div>
                  {isOpen ? (
                    <>
                      {s.their_system_reference ? (
                        <div style={{ fontSize: 11, color: "var(--z-dpur)", marginTop: 6, lineHeight: 1.5 }}>
                          <span style={{ fontSize: 9, letterSpacing: ".06em", textTransform: "uppercase", opacity: .75 }}>Their system · </span>
                          {pfText(s.their_system_reference)}
                        </div>
                      ) : null}
                      {s.peer_reference ? (
                        <div style={{ fontSize: 11, color: "var(--z-dpur)", marginTop: 4, lineHeight: 1.5 }}>
                          <span style={{ fontSize: 9, letterSpacing: ".06em", textTransform: "uppercase", opacity: .75 }}>Peer · </span>
                          {pfText(s.peer_reference)}
                        </div>
                      ) : null}
                      {s.followup_question ? (
                        <div style={{ fontSize: 11.5, color: "#3B0764", marginTop: 6, lineHeight: 1.55, paddingLeft: 8, borderLeft: "2px solid var(--ph0-bd)" }}>
                          {pfText(s.followup_question)}
                        </div>
                      ) : null}
                      <div style={{ marginTop: 6 }}>
                        <PlatformEvChips ids={cites} openEvidence={openEvidence} label="cites" />
                      </div>
                    </>
                  ) : null}
                  {extras ? (
                    <div className="row" style={{ marginTop: 4 }}>
                      <span className="spacer" />
                      <button className="btn btn-tertiary btn-sm" style={{ color: "var(--z-dpur)", fontSize: 10 }}
                        onClick={(ev) => { ev.stopPropagation(); setOpenStarter(o => o === key ? null : key); }}>
                        {isOpen ? "Less" : `More · ${extras}`}
                        <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={11} />
                      </button>
                    </div>
                  ) : null}
                </div>
                </React.Fragment>
              );
            })}
            {starters.length === 0 ? (
              <div style={{ fontSize: 12, color: "var(--z-muted)" }}>
                No conversation starter promoted for this run.
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {/* ── Considered and set aside ───────────────────────────────────
          Below the primary story and closed by default. It is honest content —
          the run's own reason for not leading with a platform — but it is an
          appendix to the argument, and it used to sit between the tiles and
          the gap mapping they scope, which is where the prototype puts the
          mapping itself. */}
      {discarded.length ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <button onClick={() => setShowDiscarded(v => !v)}
            style={{ width: "100%", background: "none", border: 0, cursor: "pointer", textAlign: "left", padding: 0 }}>
            <div className="row" style={{ gap: 8 }}>
              <Icon name="filter" size={14} />
              <div style={{ fontSize: 13, fontWeight: 600 }}>Considered and set aside · {discarded.length}</div>
              <span className="spacer" />
              {/* The one panel on this page that CANNOT be scoped to a tile,
                  and it says so rather than appearing to ignore the click:
                  a discarded platform belongs to no promoted platform's area,
                  which is precisely what discarding it means. */}
              <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
                why the run did not lead with these · this list is the run's, not {selKey || "any one platform"}'s</span>
              <Icon name={showDiscarded ? "chevron-u" : "chevron-d"} size={13} style={{ color: "var(--z-muted)" }} />
            </div>
          </button>
          {showDiscarded ? (
            <div style={{ display: "grid", gap: 7, marginTop: 10 }}>
              {discarded.map((x, i) => (
                /* The name column was a fixed 210px in a no-wrap row, so on a
                   narrow viewport the reason text was squeezed to a sliver
                   beside it. The row wraps: when the reason no longer fits at a
                   readable width it drops to its own full-width line. */
                <div key={i} className="row" style={{ gap: 10, alignItems: "flex-start", fontSize: 11.5, flexWrap: "wrap" }}>
                  <span style={{ fontWeight: 500, color: "var(--z-dark)", flex: "0 0 210px", maxWidth: "100%", lineHeight: 1.45 }}>
                    {pfText(x.platform) || pfText(x.name) || "Platform not named"}
                  </span>
                  {x.relevance != null ? (
                    <span className="b b-muted f-mono" style={{ flexShrink: 0 }} title="relevance to the assessed gaps">{Number(x.relevance).toFixed(2)}</span>
                  ) : null}
                  <span style={{ color: "var(--z-muted)", flex: "1 1 240px", minWidth: 0, lineHeight: 1.5 }}>{pfText(x.reason) || pfText(x.why_not) || "No reason promoted."}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* ── Stair-step ladder ───────────────────────────────────────
          Both of these take the selection now. They were the two panels a
          tile click left untouched — measured: clicking each of the four
          tiles changed the gap table, the readiness rail, the recommendation
          list and the starter order, and left the ladder and the roadmap
          byte-identical. */}
      <StairstepCurve entity={entity} selKey={selKey} area={area} />

      {/* ── Transformation Roadmap ───────────────────────────────── */}
      <TransformationRoadmap entity={entity} selKey={selKey} area={area} />
    </div>
  );
}

/* ── Stair-step ladder ───────────────────────────────────────────────
   The ladder's rungs are ORDERED STEPS, not maturity bands. They used to be
   drawn as "M1 … M4" in band colours, which asserts that rung 4 is the
   Differentiating band — the payload says nothing of the kind, and the run's
   own composite is 2.71. Rungs are numbered and coloured from their index
   (presentation, deterministic, claiming nothing), and the position marker is
   the rung the run flags as `current_position` rather than always the first. */
const RUNG_COLORS = ["var(--z-dark2)", "var(--z-mid)", "var(--z-dpur)",
                     "var(--z-teal)", "var(--z-purple)"];

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
    if (next.length > maxChars && cur) { lines.push(cur); cur = w; }
    else cur = next;
  }
  if (cur) lines.push(cur);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  kept[maxLines - 1] = `${kept[maxLines - 1].slice(0, Math.max(0, maxChars - 1))}…`;
  return kept;
}

function StairstepCurve({ entity, selKey, area }) {
  // The default cluster key was hardcoded "P4-data", so any run whose ladder
  // does not carry that theme threw on C.label and blanked the whole lower
  // half of the platform page — the missing maturity curve and roadmap.
  const clusters = DMA.STAIRSTEP_CLUSTERS || {};
  const keys = Object.keys(clusters);
  const [cluster, setCluster] = useState(null);
  const active = (cluster && clusters[cluster]) ? cluster : keys[0];
  const C = active ? clusters[active] : null;
  if (!C || !(C.steps || []).length) {
    return (
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row" style={{ marginBottom: 8 }}>
          <Icon name="stairs" size={14} />
          <div style={{ fontSize: 13, fontWeight: 600 }}>Maturity stair-step</div>
        </div>
        <div style={{ fontSize: 12, color: "var(--z-muted)" }}>
          No stair-step ladder promoted for this run.
        </div>
      </div>
    );
  }

  const steps = C.steps;
  const n = steps.length;
  /* The platform each rung is climbed with, on the same join the tiles use:
     the rung's covered cells are filed under an L3 area by the run's own
     recommendations and story rows, and one promoted tile leads on that area.
     A rung whose cells resolve to no single area carries no platform label —
     the design's "via SF" is worth having only where the run says which. */
  const scope = platformScopeOf(entity.id);
  const viaOf = (s) => {
    const tally = new Map();
    for (const id of (s && s.subcaps) || []) {
      const hit = areaOfCell(scope.index, id);
      if (!hit) continue;
      tally.set(hit.area, (tally.get(hit.area) || 0) + 1);
    }
    if (!tally.size) return null;
    const ranked = [...tally.entries()].sort((a, b) => b[1] - a[1]);
    if (ranked.length > 1 && ranked[0][1] === ranked[1][1]) return null;
    const key = scope.platformOfArea.get(ranked[0][0]);
    return key ? { platform: key, area: ranked[0][0] } : null;
  };
  // Sized from the rung count, not a hardcoded four: a three- or five-rung
  // ladder used to be squeezed into or spill out of four columns. The rungs
  // climb to (i+1)/n of the plot height, so the last one reaches the top of
  // the frame as it does in the design — at (i+1)/(n+1) the whole staircase
  // sat in the lower two thirds with a band of empty chart above it.
  const W = 880, H = 560, padL = 60, padR = 40, padT = 40, padB = 70;
  const stepW = (W - padL - padR) / n;
  const stepY = (i) => H - padB - (i + 1) * (H - padT - padB) / n;
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
  const minesIdx = selKey ? viaCache.map((v, i) => (v && v.platform === selKey ? i : -1))
                                     .filter(i => i >= 0) : [];
  const placed = viaCache.filter(Boolean).length;

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      {/* wrap: with several cluster toggles the strip overflowed the card on
          narrow viewports instead of dropping below the title. */}
      <div className="row" style={{ marginBottom: 14, flexWrap: "wrap" }}>
        <div style={{ width: 28, height: 28, borderRadius: 7, background: "var(--z-ice)", color: "var(--z-mid)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Icon name="stairs" size={14} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            Stair-step ladder · {C.label}
            {selKey ? <span style={{ color: "var(--z-muted)", fontWeight: 400 }}> · {selKey}</span> : null}
          </div>
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
            {n} rung{n === 1 ? "" : "s"} · where {entity.name} stands today, and what each rung requires
          </div>
          {/* What the selection did to THIS card, in the run's own counts. A
              platform that climbs none of these rungs says so rather than
              leaving the reader to conclude the card ignored the click. */}
          {selKey ? (
            <div style={{ fontSize: 10.5, color: minesIdx.length ? "var(--z-mid)" : "var(--z-muted)", marginTop: 2, lineHeight: 1.45 }}>
              {minesIdx.length
                ? `${minesIdx.length} of ${n} rungs are climbed with ${selKey}${area ? ` (${area})` : ""} — marked below`
                : (placed
                    ? `No rung on this ladder is climbed with ${selKey}. ${placed} of ${n} resolve to another promoted platform, and all ${n} stay in sequence.`
                    : `This run files none of these rungs' cells under an L3 area, so no rung can be attributed to ${selKey} or to any other platform.`)}
            </div>
          ) : null}
        </div>
        {keys.length > 1 ? (
          <div className="toggle-row">
            {Object.entries(clusters).map(([k, v]) => (
              <button key={k} className={active === k ? "on" : ""} onClick={() => setCluster(k)}>{v.label}</button>
            ))}
          </div>
        ) : null}
      </div>

      {/* Was `grid: 1fr 300px` — the step list held 300px whatever the
          viewport, and the chart (an SVG that scales freely) was crushed
          beside it. Same flex-wrap sidebar pattern as the readiness column:
          side by side while both fit, stacked below. alignItems start: the
          chart box is an SVG with a fixed aspect ratio, so stretching it to
          the rail's height added a band of empty gradient under the
          staircase rather than a taller staircase. */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", gap: 18 }}>
        <div style={{ flex: "999 1 400px", minWidth: 0, maxWidth: "100%", background: "linear-gradient(180deg, var(--z-bg), #fff)", borderRadius: 10, padding: "16px 14px 12px", border: "1px solid var(--z-sep)", position: "relative", overflow: "hidden" }}>
          <img src={assetUrl("illo_curvesTR", "brand/illustrations/curves_topright.png")} alt="" style={{ position: "absolute", top: 0, right: 0, width: 320, height: "auto", opacity: .5, pointerEvents: "none" }} />

          <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block", position: "relative" }}>
            <defs>
              <marker id="arrowH" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="var(--z-purple)"/></marker>
            </defs>
            <line x1={padL} y1={H - padB + 18} x2={W - padR} y2={H - padB + 18} stroke="var(--z-purple)" strokeWidth="1.5" markerEnd="url(#arrowH)" />
            <text x={padL} y={H - padB + 38} fontSize="10" fill="var(--z-muted)">Today</text>
            <text x={W - padR - 36} y={H - padB + 38} fontSize="10" fill="var(--z-mid)" fontWeight="600">Leading</text>

            {steps.map((s, i) => {
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
              const meta = [
                (s.subcaps || []).length ? `${s.subcaps.length} cells` : null,
                s.effort ? `effort ${s.effort}` : null,
              ].filter(Boolean).join(" · ");
              /* SVG cannot clip a centred string to its box, so each line is
                 admitted only if the rung is tall enough to hold it. The
                 platform outranks the meta line: the cell count is also on the
                 card beside the chart, and "via <platform>" is the one thing
                 the rung says that nothing else on the row does. */
              const top = y + 20 + lines.length * 14;
              const viaFits = via && (top + 12 <= H - padB - 6);
              const metaFits = meta && (top + (viaFits ? 12 : 0) + 12 <= H - padB - 6);
              const clip = (t, max) => (t.length > max ? `${t.slice(0, max - 1)}…` : t);
              return (
                <g key={i} opacity={dim ? 0.42 : 1}>
                  <title>{`Step ${s.m}: ${pfText(s.label) || ""}${via ? ` · via ${via.platform} (${via.area})` : ""}`}</title>
                  <rect x={x} y={y} width={rungW} height={h} fill={color} rx="6" ry="6" />
                  {mine ? (
                    <rect x={x - 2} y={y - 2} width={rungW + 4} height={h + 2} rx="8" ry="8"
                          fill="none" stroke="var(--z-org)" strokeWidth="2" />
                  ) : null}
                  <circle cx={x + 16} cy={y - 14} r="14" fill="#fff" stroke={color} strokeWidth="2.5" />
                  <text x={x + 16} y={y - 9} fontSize="13" fontWeight="700" fill={color} textAnchor="middle">{s.m}</text>
                  {lines.map((ln, k) => (
                    <text key={k} x={x + rungW / 2} y={y + 20 + k * 14} fontSize="11" fontWeight="600" fill="#fff" textAnchor="middle">{ln}</text>
                  ))}
                  {viaFits ? (
                    <text x={x + rungW / 2} y={top + 2} fontSize="9.5" fill="rgba(255,255,255,.92)" textAnchor="middle" style={{ fontFamily: "var(--font-mono)" }}>
                      {clip(`via ${via.platform}`, monoChars)}
                    </text>
                  ) : null}
                  {metaFits ? (
                    <text x={x + rungW / 2} y={top + (viaFits ? 14 : 2)} fontSize="9" fill="rgba(255,255,255,.8)" textAnchor="middle" style={{ fontFamily: "var(--font-mono)" }}>
                      {clip(meta, monoChars)}
                    </text>
                  ) : null}
                </g>
              );
            })}

            {steps.slice(0, -1).map((s, i) => {
              const x1 = padL + (i + 1) * stepW - 8;
              const y1 = stepY(i);
              const x2 = padL + (i + 1) * stepW;
              const y2 = H - padB;
              return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--z-dpur)" strokeWidth="2" strokeDasharray="3 3" opacity="0.5" />;
            })}

            {/* Position marker — the rung the run flags, not a maturity score.
                This used to print fx(current, 1) under the word CURRENT, so a
                rung LEVEL of 1 rendered as "1.0" beside a maturity ladder and
                read as a composite score of 1.0. */}
            {currentIdx >= 0 ? (
              <g>
                <circle cx={padL + currentIdx * stepW + 16} cy={stepY(currentIdx) - 14} r="20" fill="none" stroke="var(--z-org)" strokeWidth="2" strokeDasharray="4 3" />
                {/* Both labels clear the r=20 dashed ring (its top edge is
                    stepY-34); at -40/-29 the second line sat inside it. */}
                <text x={padL + currentIdx * stepW + 16} y={stepY(currentIdx) - 53} fontSize="9.5" fill="var(--z-org)" fontWeight="700" textAnchor="middle">YOU ARE HERE</text>
                <text x={padL + currentIdx * stepW + 16} y={stepY(currentIdx) - 40} fontSize="9" fill="var(--z-muted)" textAnchor="middle">{`step ${steps[currentIdx].m} of ${n}`}</text>
              </g>
            ) : null}
          </svg>
        </div>

        {/* The right rail is the design's list of the same rungs: a badge row,
            the rung, and a line or two of what it unlocks. The note is clamped
            rather than run in full — four unclamped notes made the rail twice
            the height of the chart it annotates, which is what left the chart
            floating in a band of empty card. */}
        <div style={{ flex: "1 1 280px", minWidth: 0, maxWidth: "100%", display: "flex", flexDirection: "column", gap: 8 }}>
          {steps.map((s, i) => {
            const via = viaCache[i];
            const mine = !!(selKey && via && via.platform === selKey);
            const dim = !!(selKey && minesIdx.length && !mine);
            return (
              <div key={i} style={{ padding: "10px 12px", background: i === currentIdx ? "var(--z-ice)" : "var(--z-bg)", borderRadius: 8,
                    border: mine ? "1px solid var(--z-org)"
                      : i === currentIdx ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)",
                    opacity: dim ? 0.62 : 1 }}>
                <div className="row" style={{ marginBottom: 4, gap: 6, flexWrap: "wrap" }}>
                  <span className="b b-purple" style={{ flexShrink: 0 }}>Step {s.m}</span>
                  {i === currentIdx ? <span className="b b-teal" style={{ flexShrink: 0 }}>current</span> : null}
                  {mine ? <span className="b b-org" style={{ flexShrink: 0 }}
                            title={`This rung's cells are filed under ${via.area}, which ${selKey} leads on`}>
                            this platform</span> : null}
                  {s.effort ? <span className="b b-muted" style={{ flexShrink: 0 }} title="effort band">{pfText(s.effort)}</span> : null}
                  {(s.blocking || []).map(b => <span key={b} className="b b-org" style={{ flexShrink: 0 }} title="blocking finding">{pfText(b)}</span>)}
                </div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--z-dark)", lineHeight: 1.4 }}>{pfText(s.label)}</div>
                {via ? (
                  <div style={{ fontSize: 10, color: "var(--z-mid)", marginTop: 3 }}
                    title={`This rung's cells are filed under ${via.area}, which ${via.platform} leads on`}>
                    via {via.platform}
                  </div>
                ) : null}
                {s.note ? (
                  <div style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.55, marginTop: 4 }}
                    className="txt-fit-2" title={pfText(s.note) || ""}>{pfText(s.note)}</div>
                ) : null}
                {(s.subcaps || []).length ? (
                  <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 4 }}>{s.subcaps.length} cells covered</div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ── Transformation Roadmap (Pattern J: phase chevrons) ─────────── */
function TransformationRoadmap({ entity, selKey, area }) {
  const { openRec, pushToast } = useApp();
  const [view, setView] = useState("chevrons"); // chevrons | impact
  const roadmap = DMA.ROADMAP || [];
  const recs = DMA.RECOMMENDATIONS || [];

  if (!roadmap.length) {
    return (
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row" style={{ marginBottom: 8 }}>
          <Icon name="route" size={14} />
          <div style={{ fontSize: 13, fontWeight: 600 }}>Transformation roadmap</div>
        </div>
        <div style={{ fontSize: 12, color: "var(--z-muted)" }}>No roadmap promoted for this run.</div>
      </div>
    );
  }

  const phaseRecs = (r) => (r.recs || []).map(rid => recs.find(x => x.id === rid)).filter(Boolean);
  const impactRows = roadmap.reduce((a, r) => a + phaseRecs(r)
    .reduce((b, rec) => b + (rec.dma_impact || []).length, 0), 0);
  // The section states its sequencing basis beside `phases`, so it reaches the
  // page through the entity rather than through the phase array.
  const basis = (typeof window !== "undefined" && window.DMA_ENTITY
    && window.DMA_ENTITY.roadmapBasis) || null;

  /* Which of this roadmap's recommendations belong to the SELECTED platform.
     Same join as everything else on the page — a recommendation's `l3` against
     the L3 area the tile derives — so the roadmap answers a tile click instead
     of being the one panel that ignores it.

     Marked and counted, never filtered: a roadmap is an ORDER, and a phase
     removed from it because the reader clicked a platform is a different plan.
     `mine` per phase is how many of that phase's served recommendations this
     platform leads. */
  const isMine = (rec) => !!(area && rec && rec.l3 === area);
  const mineCount = recs.filter(isMine).length;
  const phaseMine = (r) => phaseRecs(r).filter(isMine).length;
  const roadmapMine = roadmap.reduce((a, r) => a + phaseMine(r), 0);

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      {/* wrap: title + view toggle + export exceed a narrow card; the
          controls drop below the title instead of clipping. */}
      <div className="row" style={{ marginBottom: 16, flexWrap: "wrap" }}>
        <div style={{ width: 28, height: 28, borderRadius: 7, background: "var(--z-ice)", color: "var(--z-mid)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Icon name="route" size={14} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            Transformation roadmap
            {selKey ? <span style={{ color: "var(--z-muted)", fontWeight: 400 }}> · {selKey}</span> : null}
          </div>
          {/* Was "From Assessment Report · 3-phase sequencing aligned to the
              maturity curve above" — a sentence from no payload, hardcoded to
              three phases and claiming an alignment to the ladder that nothing
              states. Counted from the promoted phases instead. */}
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
            {roadmap.length} promoted phase{roadmap.length === 1 ? "" : "s"} · {roadmap.reduce((a, r) => a + (r.recs || []).length, 0)} recommendations
          </div>
          {selKey ? (
            <div style={{ fontSize: 10.5, color: roadmapMine ? "var(--z-mid)" : "var(--z-muted)", marginTop: 2, lineHeight: 1.45 }}>
              {roadmapMine
                ? `${roadmapMine} of them sit in ${area} — the area ${selKey} leads — and are marked in their phases. The rest of the plan stays in sequence.`
                : (area
                    ? `None of this plan's recommendations sit in ${area}, so ${selKey} leads no phase of it. Every phase is still this run's.`
                    : `This run files none of ${selKey}'s cells under an L3 area, so no phase can be attributed to it.`)}
            </div>
          ) : null}
        </div>
        <div className="toggle-row">
          <button className={view === "chevrons" ? "on" : ""} onClick={() => setView("chevrons")}><Icon name="route" size={11} /> Phases</button>
          <button className={view === "impact" ? "on" : ""} onClick={() => setView("impact")}><Icon name="stairs" size={11} /> Cell impact</button>
        </div>
        <button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`Exporting ${entity.name} roadmap (${view} view)…`, "success")}><Icon name="download" size={11} /> Export</button>
      </div>

      {/* The third view ("Step curve") plotted entity.overall + 0.3 / +0.7 /
          +1.1 at 6 / 12 / 18 months against an M1–M5 axis, and its drilldown
          asserted a composite the client would reach and a "success metric"
          from `phase.metric`, a field the roadmap contract does not carry. All
          of it was invented — the projection, the horizons, the fifth band —
          so the view is gone rather than re-dressed. What the run does state
          about movement is per-cell, and that is the Cell impact view. */}
      {view === "chevrons"
        ? <ChevronView roadmap={roadmap} recs={recs} openRec={openRec} phaseRecs={phaseRecs}
                       isMine={isMine} selKey={selKey} phaseMine={phaseMine} />
        : <CellImpactView roadmap={roadmap} phaseRecs={phaseRecs} openRec={openRec}
                          impactRows={impactRows} isMine={isMine} selKey={selKey} />}

      {/* The design's rationale strip under the chevrons. `sequencing_basis`
          is the roadmap section's own answer to "why this order", stated once
          for the whole plan rather than per phase — it sat unread in the
          payload because the adapter returned only the phase array. */}
      {basis ? (
        <div className="co co-teal" style={{ marginTop: 14 }}>
          <Icon name="info" size={14} />
          <div>
            <div className="co-title">Sequencing rationale</div>
            <div className="co-body">{pfText(basis)}</div>
          </div>
        </div>
      ) : null}
    </div>
  );
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
    const span = lo === null ? null
      : (lo === hi ? `+${lo.toFixed(1)}` : `+${lo.toFixed(1)} to +${hi.toFixed(1)}`);
    move = `${impacts.length} cell${impacts.length === 1 ? "" : "s"}${span ? ` · ${span} projected` : ""}`;
  }
  return { areas, metrics, move, bases };
}

function ChevronView({ roadmap, recs, openRec, phaseRecs, isMine, selKey, phaseMine }) {
  const mineOf = isMine || (() => false);
  return (
    /* One fluid column per phase, each carrying its own chevron header AND its
       own content card. This used to be two parallel `repeat(N, 1fr)` grids —
       N hard columns whatever the viewport, so at tablet widths every phase
       was crushed to a sliver, and the two grids could not wrap without the
       chevrons drifting away from their phases. Whole phases wrap together
       instead, and only when a column would drop below a readable width. */
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 230px), 1fr))", gap: 12 }}>
      {roadmap.map((r, i) => {
      const rs = phaseRecs ? phaseRecs(r) : (r.recs || []).map(rid => recs.find(x => x.id === rid)).filter(Boolean);
      const facts = phaseFacts(rs);
      return (
        <div key={r.phase} style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{
            background: r.color,
            clipPath: i === roadmap.length - 1 ? "polygon(0 0, 100% 0, 100% 100%, 0 100%, 4% 50%)" : "polygon(0 0, 96% 0, 100% 50%, 96% 100%, 0 100%, 4% 50%)",
            color: "#fff", padding: "10px 22px",
            fontSize: 12.5, fontWeight: 600,
            display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8
          }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 10, opacity: .8, letterSpacing: ".08em", textTransform: "uppercase" }}>Phase {r.phase}</div>
              {/* label and duration are BOTH the phase's horizon in the
                  adapter, so the chevron printed the horizon twice and the
                  card below printed it a third time. Once, here. */}
              <div>{r.label}</div>
            </div>
            <div style={{ fontSize: 10, opacity: .85, textAlign: "right", flexShrink: 0 }}>
              {(r.recs || []).length} rec{(r.recs || []).length === 1 ? "" : "s"}
              {/* What this phase owes the selected platform, counted from the
                  phase's own served recommendations. */}
              {selKey && phaseMine ? (
                <div style={{ fontSize: 9.5, opacity: .9 }}
                     title={`${phaseMine(r)} of this phase's recommendations sit in the area ${selKey} leads`}>
                  {phaseMine(r)} · {selKey.length > 18 ? `${selKey.slice(0, 17)}…` : selKey}
                </div>
              ) : null}
            </div>
          </div>

          {/* flex: 1 keeps the cards in a row the same height. */}
          <div style={{ background: r.color, borderRadius: 8, padding: 14, color: "#fff", flex: 1 }}>
            {/* The design's card reads PLATFORM · TARGET MATURITY · SUCCESS
                METRIC · RECOMMENDATIONS. None of those is a field of the
                roadmap contract — a phase states its horizon, its rationale,
                its dependencies and its recommendation ids — so each slot is
                filled from the phase's own recommendations, and a slot they
                say nothing about is left out rather than headed and empty.
                "Platform areas" and not "Platform": the L3 area is what a
                recommendation names, and naming a vendor here would be this
                page's one invented mapping. */}
            {facts.areas.length ? (
              <>
                <div style={{ fontSize: 10, color: "rgba(255,255,255,.7)", letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 4 }}>Platform areas</div>
                {/* Two lines: a phase carrying four areas made this slot
                    taller than the recommendations it heads. */}
                <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 10, lineHeight: 1.4 }}
                  className="txt-fit-2" title={facts.areas.join(" · ")}>{facts.areas.join(" · ")}</div>
              </>
            ) : null}
            {facts.move ? (
              <>
                <div style={{ fontSize: 10, color: "rgba(255,255,255,.7)", letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 4 }}>Target maturity</div>
                <div style={{ fontSize: 12.5, marginBottom: 10, color: "var(--z-mint-lt)" }}
                  title={facts.bases.join("\n") || "Projected movement, from the recommendations' own stated targets"}>{facts.move}</div>
              </>
            ) : null}
            {facts.metrics.length ? (
              <>
                <div style={{ fontSize: 10, color: "rgba(255,255,255,.7)", letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 4 }}>Success metric</div>
                {/* Three, then a count. Every metric is one recommendation's
                    KPI and they are all openable on the card above; a phase
                    with four of them turned this slot into a list. */}
                <div style={{ fontSize: 12, marginBottom: 10, lineHeight: 1.5 }}>
                  {facts.metrics.slice(0, 3).map((m, k) => <div key={k} style={{ marginBottom: 2 }}>{m}</div>)}
                  {facts.metrics.length > 3 ? (
                    <div style={{ color: "rgba(255,255,255,.75)", marginTop: 2 }} title={facts.metrics.slice(3).join("\n")}>
                      +{facts.metrics.length - 3} more
                    </div>
                  ) : null}
                </div>
              </>
            ) : null}

            <div style={{ fontSize: 10, color: "rgba(255,255,255,.7)", letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 6 }}>Recommendations</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {(r.recs || []).map(rid => {
                const rec = recs.find(x => x.id === rid);
                // The selected platform's own rows keep a full-strength face;
                // the rest of the phase recedes. Every row stays clickable.
                const mine = mineOf(rec);
                const marked = !!(selKey && mine);
                return rec ? (
                  <button key={rid} onClick={(e) => { e.stopPropagation(); openRec(rid); }}
                    /* The title ellipsises to one line by design; without this
                       the rest of the sentence is unreachable by any means. */
                    title={`${rec.id} · ${pfText(rec.title) || ""}${marked ? ` · ${selKey} leads this` : ""}`}
                    style={{ padding: "6px 8px", background: marked ? "rgba(255,255,255,.30)" : "rgba(255,255,255,.14)", borderRadius: 5, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6, border: marked ? "1px solid rgba(255,255,255,.85)" : "1px solid transparent", color: "#fff", textAlign: "left", cursor: "pointer", transition: "background 120ms" }}
                    onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,.22)"}
                    onMouseLeave={e => e.currentTarget.style.background = marked ? "rgba(255,255,255,.30)" : "rgba(255,255,255,.14)"}>
                    <span style={{ fontSize: 10.5, fontWeight: 600, flexShrink: 0 }}>{rec.id}</span>
                    <span style={{ fontSize: 10.5, color: "rgba(255,255,255,.85)", flex: 1, minWidth: 0 }} className="txt-trunc">{pfText(rec.title)}</span>
                    <Icon name="arrow-r" size={11} />
                  </button>
                ) : (
                  /* A phase that names a recommendation this run did not serve
                     says so — it used to render nothing at all. */
                  <span key={rid} style={{ fontSize: 10.5, color: "rgba(255,255,255,.7)" }}>{rid} · not served in this run</span>
                );
              })}
            </div>

            {/* The phase's own reason and its predecessors, under the four
                slots the design leads with rather than above them: the
                rationale is a paragraph, and at the top of the card it pushed
                every structured fact below the fold of a 230px column. */}
            {r.rationale || (r.depends_on || []).length ? (
              <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px solid rgba(255,255,255,.2)" }}>
                {(r.depends_on || []).length ? (
                  <div style={{ fontSize: 10.5, color: "rgba(255,255,255,.8)", marginBottom: 6 }}>
                    Depends on {r.depends_on.join(" · ")}
                  </div>
                ) : null}
                {r.rationale ? (
                  <>
                    <div style={{ fontSize: 10, color: "rgba(255,255,255,.7)", letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 4 }}>Why this phase</div>
                    <div style={{ fontSize: 11.5, lineHeight: 1.5 }} className="txt-fit-3" title={pfText(r.rationale) || ""}>{pfText(r.rationale)}</div>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      );
      })}
    </div>
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
function CellImpactView({ roadmap, phaseRecs, openRec, impactRows, isMine, selKey }) {
  const mineOf = isMine || (() => false);
  if (!impactRows) {
    return (
      <div style={{ fontSize: 12, color: "var(--z-muted)" }}>
        No recommendation in this roadmap promoted a cell-impact table, so there is nothing to show per phase.
      </div>
    );
  }
  return (
    /* Fluid, like the chevron view: N hard columns crushed each phase's
       impact table at tablet widths; phases wrap when a column would drop
       below a readable width. */
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))", gap: 12 }}>
      {roadmap.map(r => {
        const rs = phaseRecs(r);
        const bases = [];
        for (const rec of rs) {
          for (const im of rec.dma_impact || []) {
            if (im.target_basis && !bases.includes(im.target_basis)) bases.push(im.target_basis);
          }
        }
        return (
          <div key={r.phase} className="card-tile" style={{ padding: 14, borderTop: `3px solid ${r.color}` }}>
            <div className="row" style={{ marginBottom: 4, gap: 6 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: r.color, letterSpacing: ".08em", textTransform: "uppercase", flexShrink: 0 }}>Phase {pfText(r.phase)}</span>
              <strong style={{ fontSize: 12.5, flex: 1, minWidth: 0 }}>{r.label}</strong>
            </div>
            <div className="eyebrow" style={{ fontSize: 9.5, margin: "8px 0 6px" }}>Cells this phase moves</div>
            {rs.map(rec => (
              <div key={rec.id} style={{ marginBottom: 10 }}>
                <button onClick={() => openRec(rec.id)}
                  title={`${rec.id} · ${pfText(rec.title) || ""}${selKey && mineOf(rec) ? ` · ${selKey} leads this` : ""}`}
                  style={{ padding: 0, background: "none", border: 0, cursor: "pointer", textAlign: "left", display: "flex", gap: 6, alignItems: "center", width: "100%" }}>
                  <strong style={{ fontSize: 10.5, color: "var(--z-dark)", flexShrink: 0 }}>{rec.id}</strong>
                  <span style={{ fontSize: 10.5, color: "var(--z-muted)", flex: 1, minWidth: 0 }} className="txt-trunc">{pfText(rec.title)}</span>
                  {/* The same mark the chevron view uses, so switching views
                      does not change which rows belong to the selection. */}
                  {selKey && mineOf(rec)
                    ? <span className="b b-org" style={{ flexShrink: 0 }}>this platform</span> : null}
                  <Icon name="arrow-r" size={11} style={{ color: "var(--z-muted)", flexShrink: 0 }} />
                </button>
                {(rec.dma_impact || []).length ? (rec.dma_impact || []).map((im, j) => {
                  const cur = pfNum(im.current), tgt = pfNum(im.target), d = pfNum(im.delta);
                  return (
                    <div key={j} className="row" style={{ padding: "5px 0", borderTop: "1px solid var(--z-sep)", gap: 6, alignItems: "flex-start" }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 11, color: "var(--z-body)", lineHeight: 1.35 }}>{pfText(im.name) || im.subcap_id}</div>
                        <div className="f-mono" style={{ fontSize: 9, color: "var(--z-muted)" }}>{pfText(im.subcap_id)}</div>
                      </div>
                      <span style={{ flexShrink: 0 }}><MaturityChip score={cur} /></span>
                      <span style={{ fontSize: 10, color: "var(--z-muted)", flexShrink: 0 }}>→</span>
                      <span style={{ flexShrink: 0 }}><MaturityChip score={tgt} /></span>
                      {d !== null ? (
                        <span className="f-mono" style={{ fontSize: 10, color: "var(--z-mid)", width: 30, textAlign: "right", flexShrink: 0 }}>{d > 0 ? `+${d.toFixed(1)}` : d.toFixed(1)}</span>
                      ) : null}
                    </div>
                  );
                }) : (
                  <div style={{ fontSize: 10.5, color: "var(--z-muted)", padding: "4px 0" }}>No cell impact promoted for this recommendation.</div>
                )}
              </div>
            ))}
            {!rs.length ? (
              <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
                {(r.recs || []).length
                  ? `This phase names ${r.recs.join(" · ")}, none of them served in this run.`
                  : "This phase names no recommendation."}
              </div>
            ) : null}
            {bases.length ? (
              <div style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--z-sep)", lineHeight: 1.5 }}>
                {bases.map((b, i) => <div key={i} style={{ marginBottom: 3 }}>{pfText(b)}</div>)}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

Object.assign(window, { ClientPlatform });
