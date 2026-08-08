/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Drawer/Modal components - Evidence drawer, Insight modal,
   Intelligence panel, simple toast helpers

   Everything in this file is mounted GLOBALLY (App renders the drawer, the two
   modals and the panel as siblings of the router), so a TypeError in any of
   them unmounts the whole tree and blanks the application — not just the
   surface that opened it. Three shapes were reaching these components from the
   promoted payload that the fixture never had:

     · a field the fixture nested (`r.outcomes.effort`) where the run states it
       flat (`effort_band` → `r.effort`);
     · a field the run states as an OBJECT (`validation_gate`, `kpi_triple`)
       where the fixture stated a string — React throws #31 on an object child
       and there is no error boundary above these components;
     · a vendor id (`r.platform`, `ic.platforms[0]`) looked up in the static
       five-vendor catalogue, which knows nothing about the client and returns
       undefined for every promoted value.

   So nothing from the payload reaches JSX in this file without passing through
   `dwText`, and no lookup into the fixture catalogue decides what a promoted
   object is called.
   ═══════════════════════════════════════════════════════════════════════ */

/* Renderable text from any payload value. An object is summarised from its own
   naming keys and an unusable value becomes null, so the caller renders its
   absent state instead of crashing or printing JSON at a reader. */
function dwText(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "string") return v || null;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(dwText).filter(Boolean).join(" · ") || null;
  if (typeof v === "object") {
    for (const k of ["statement", "text", "label", "name", "title", "clause",
                     "condition", "metric", "value"]) {
      const t = dwText(v[k]);
      if (t) return t;
    }
    return null;
  }
  return String(v);
}

function dwNum(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return isFinite(n) ? n : null;
}

/* Score → band → hex through the ONE resolver (DMA.helpers). Null score yields
   null, never a band: `maturityClass(null)` is not a band and a grey chip that
   reads "Activating" is a claim the run never made. */
function dwBand(score) {
  const n = dwNum(score);
  if (n === null) return null;
  return {
    score: n,
    label: DMA.helpers.maturityLabel(n),
    hex: DMA.helpers.maturityHex(n),
  };
}

/* ── Evidence drawer ─────────────────────────────────────────────── */
function EvidenceDrawer() {
  const { evidenceDrawer, closeEvidence, role, audience, openSubcap, pushToast } = useApp();
  const [tierFilter, setTierFilter] = useState("ALL");
  if (!evidenceDrawer) return null;
  const ev = DMA.getEvidence(evidenceDrawer.evidenceId);
  const subcap = evidenceDrawer.subcap;
  const ic = evidenceDrawer.insight && DMA.getInsight(evidenceDrawer.insight);

  const LIVE = typeof window !== "undefined" && !!window.DMA_LIVE;

  // Pull evidence items
  let items = [];
  // Distinguishes "this cell has none" from "the id a card cited does not
  // resolve" — the drawer used to render both as the tier-filter empty state,
  // so a dead citation looked like a filter mistake.
  let unresolved = null;
  if (ev) items = [ev];
  else if (ic) items = (ic.evidence || []).map(id => DMA.getEvidence(id)).filter(Boolean);
  else if (subcap) {
    items = DMA.EVIDENCE.filter(e => e.subcaps && e.subcaps.includes(subcap.id));
    // Padding with unrelated items presented evidence that does not support
    // this cell as though it did. Fixture mode keeps it (it is the design
    // reference for a populated drawer); LIVE never fabricates support.
    if (items.length === 0 && !LIVE) {
      items = DMA.EVIDENCE.slice(0, Math.max(1, Math.min(subcap.evidence_count || 1, 4)));
    }
  } else if (evidenceDrawer.evidenceId) {
    unresolved = evidenceDrawer.evidenceId;
  }

  // Tier filter
  const filtered = tierFilter === "ALL" ? items : items.filter(it => it.tier === tierFilter);

  // Tier distribution for filter
  const dist = {};
  items.forEach(it => { dist[it.tier] = (dist[it.tier] || 0) + 1; });

  return (
    <>
      <div className="drawer-mask" onClick={closeEvidence} />
      <div className="drawer">
        <div className="drawer-head">
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4, flexWrap: "wrap" }}>
              <span className="b b-teal">EVIDENCE</span>
              {subcap ? <span className="chip purple">{subcap.id}</span> : null}
              {ev ? <span className={`tier-chip tier-${ev.tier}`}>{ev.tier}</span> : null}
            </div>
            <div className="title" style={{ fontSize: 14 }}>{subcap ? subcap.name : ic ? ic.title : ev ? ev.title : "Evidence"}</div>
            {/* An unscored cell used to print "score null · undefined" here. */}
            <div className="sub">{items.length} evidence item{items.length === 1 ? "" : "s"}{subcap
              ? ` · score ${dwNum(subcap.score) === null ? "not scored" : fx(subcap.score, 1)}${
                  subcap.confidence ? ` · ${subcap.confidence}` : ""}`
              : ""}</div>
          </div>
          <button className="icon-btn close" onClick={closeEvidence} aria-label="Close"><Icon name="x" size={16} /></button>
        </div>

        <div className="drawer-body">
          {subcap && role !== "AE" && audience !== "customer" ? (
            <div className="co co-teal" style={{ marginBottom: 12 }}>
              <Icon name="info" size={14} />
              <div>
                <div className="co-title">Rationale</div>
                {/* The ceiling is a fact about this cell's evidence, so it is
                    read, never asserted: the old copy claimed "T2 with
                    consistent FACT-class claims" for every cell in the run. */}
                <div className="co-body">
                  Score {fx(subcap.score, 1)}
                  {subcap.peerMedian != null ? ` · peer median ${fx(subcap.peerMedian, 1)}` : ""}
                  {subcap.peer_basis === "category_proxy" ? " (peer proxy · category median)" : ""}.
                  {" "}
                  {subcap.thin
                    ? `Evidence is below the threshold of 3 — flagged as thin${subcap.closure_condition ? `. Closes on: ${subcap.closure_condition}` : "."}`
                    : (items.length
                        ? `Grounded on ${items.length} item${items.length === 1 ? "" : "s"}${
                            (() => {
                              const tiers = [...new Set(items.map(i => i.tier).filter(Boolean))].sort();
                              return tiers.length ? ` · ${tiers.join(", ")}` : "";
                            })()}.`
                        : "No evidence linked at this grain.")}
                </div>
              </div>
            </div>
          ) : null}

          {/* Tier filter */}
          {items.length > 1 ? (
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 12 }}>
              <button className={`btn btn-tertiary btn-sm ${tierFilter === "ALL" ? "" : ""}`} style={{ background: tierFilter === "ALL" ? "var(--z-dark)" : "transparent", color: tierFilter === "ALL" ? "#fff" : "var(--z-body)" }} onClick={() => setTierFilter("ALL")}>All · {items.length}</button>
              {Object.entries(dist).sort().map(([t, n]) => (
                <button key={t} className={`tier-chip tier-${t}`} style={{ opacity: tierFilter === "ALL" || tierFilter === t ? 1 : 0.45, cursor: "pointer" }} onClick={() => setTierFilter(t === tierFilter ? "ALL" : t)}>
                  {t} · {n}
                </button>
              ))}
            </div>
          ) : null}

          {/* Evidence items */}
          {filtered.length === 0 ? (
            <div className="empty">
              <div className="icon"><Icon name="evidence" size={20} /></div>
              {unresolved ? (
                <>
                  <h3>{unresolved} is not in this run's evidence store</h3>
                  <p>The card cites an id this entity and run do not carry. Evidence
                     reads are entity-scoped and fail closed, so nothing is shown.
                     Report it — a citation that does not resolve is a producer defect.</p>
                </>
              ) : items.length === 0 ? (
                <>
                  <h3>No evidence linked{subcap ? ` to ${subcap.id}` : ""}</h3>
                  {/* The old copy said the closure condition "names what would
                      settle it". The served cell row carries no closure_condition
                      field, so that sentence pointed at something the reader
                      could never find. */}
                  <p>{subcap && subcap.thin
                        ? "The cell is flagged thin: it keeps its workbook score and renders with a dashed outline. The run states no closure condition for it."
                        : "Nothing is linked at this grain in the promoted run."}</p>
                </>
              ) : (
                <>
                  <h3>No evidence in this tier</h3>
                  <p>Try another tier or clear the filter.</p>
                </>
              )}
            </div>
          ) : filtered.map(it => {
            const tier = DMA.getTier(it.tier);
            return (
              <div key={it.id} style={{ borderBottom: "1px solid var(--z-sep)", padding: "12px 0" }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
                  <span className="chip">{it.id}</span>
                  <span className={`tier-chip tier-${it.tier}`} title={tier?.desc}>{it.tier} · {tier?.label}</span>
                  {it.claim ? <span className="b b-purple">{it.claim}</span> : null}
                  <span style={{ fontSize: 10, color: "var(--z-muted)" }}
                        title={it.recency_band === "UNVERIFIED"
                          ? "no publication date could be resolved, so the recency ladder cannot rank this item - its claim class is unaffected"
                          : (it.published_date || "")}>
                    {it.recency}
                  </span>
                  {/* ERS is computed server-side and may be unset on an item
                      the store never scored. It used to render as "ERS" with an
                      empty bold value, which reads as a score of nothing. */}
                  {role !== "AE" && audience !== "customer" ? (
                    <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--z-muted)" }}>
                      ERS <strong style={{ color: dwNum(it.ers) === null ? "var(--z-muted)" : "var(--z-mid)" }}>
                        {dwNum(it.ers) === null ? "not scored" : it.ers}</strong>
                    </span>
                  ) : null}
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)", marginBottom: 5 }}>{it.title}</div>
                {/* 27 of this run's 120 served items carry no excerpt. Printing
                    `"{it.excerpt}"` rendered an empty pair of quote marks in an
                    italic quote block — a verbatim citation of nothing. The
                    excerpt is the whole point of the drawer, so its absence is
                    stated as an absence. */}
                {dwText(it.excerpt) ? (
                  <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55, fontStyle: "italic", padding: "8px 10px", background: tier?.bg || "var(--z-bg)", borderLeft: `3px solid ${tier?.color || "var(--z-teal)"}`, borderRadius: 3 }}>"{dwText(it.excerpt)}"</div>
                ) : (
                  <div style={{ fontSize: 11.5, color: "var(--z-muted)", lineHeight: 1.5, padding: "8px 10px", background: "var(--z-bg)", borderLeft: "3px dashed var(--z-sep)", borderRadius: 3 }}>
                    No verbatim excerpt is served for this item — the source is
                    linked below, but nothing here quotes it.
                  </div>
                )}
                <div style={{ marginTop: 6, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  {it.source ? (
                    <a href={`https://${it.source}`} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: "var(--z-mid)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}>
                      <Icon name="external" size={11} /> {it.source_pretty || it.source}
                    </a>
                  ) : (
                    <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{it.source_pretty || "no source url served"}</span>
                  )}
                  {/* The traceable cell links (`linked_subcap_ids`, scoped to
                      this run). Showing the first three silently dropped the
                      rest, so an item supporting nine cells looked like it
                      supported three; the remainder is now counted. */}
                  {it.subcaps && it.subcaps.length > 0 ? (
                    <span style={{ fontSize: 10, color: "var(--z-muted)", display: "inline-flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
                      <span>· supports:</span>
                      {it.subcaps.slice(0, 4).map(sid => <button key={sid} className="chip" onClick={() => openSubcap(sid)}>{sid}</button>)}
                      {it.subcaps.length > 4 ? (
                        <span title={it.subcaps.join(" · ")}>+{it.subcaps.length - 4} more</span>
                      ) : null}
                    </span>
                  ) : (
                    <span style={{ fontSize: 10, color: "var(--z-muted)" }}>· no cell links served for this item</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        <div className="drawer-foot">
          <button className="btn btn-tertiary" onClick={() => {
            // An item with no excerpt copies as the citation without a quote,
            // never as an empty pair of quote marks pasted into a deck.
            const lines = filtered.map(it => [
              `${it.id} · ${it.tier} · ${it.title}`,
              dwText(it.excerpt) ? `— "${dwText(it.excerpt)}"` : "— no excerpt served",
              `(${it.source_pretty || it.source || "no source url"})`,
            ].join(" ")).join("\n");
            try { navigator.clipboard.writeText(lines); pushToast(`Copied ${filtered.length} citation${filtered.length === 1 ? "" : "s"}`, "success"); }
            catch (e) { pushToast("Couldn't access clipboard", "warn"); }
          }}><Icon name="copy" size={13} /> Copy citation</button>
          <button className="btn btn-secondary" onClick={closeEvidence}>Close</button>
        </div>
      </div>
    </>
  );
}

/* ── Insight card modal ──────────────────────────────────────────── */
function InsightModal() {
  const { insightModal, closeInsight, openEvidence, openSubcap, openRec, audience, pushToast, route } = useApp();
  const [tab, setTab] = useState("detail");
  const [note, setNote] = useState("");
  const [annStatus, setAnnStatus] = useState("ACTIONED");
  // Accept/Reject verdicts, keyed by card id so a decision survives closing and
  // reopening the modal within the session. The server's answer is what is
  // stored — the chip states what was RECORDED, not what was clicked.
  const [decisions, setDecisions] = useState({});
  const [deciding, setDeciding] = useState(false);

  useEffect(() => { if (insightModal) setTab("detail"); }, [insightModal]);
  if (!insightModal) return null;
  const ic = DMA.getInsight(insightModal);
  if (!ic) return null;
  const rec = ic.rec ? DMA.getRecommendation(ic.rec) : null;
  const decided = decisions[ic.id] || null;

  /* Accept / Reject → the annotation write path. Annotations and alert actions
     are the ONLY writes this app's API accepts, both behind an Idempotency-Key
     (invariant 2) — this is that write, from the reviewer's seat, through the
     same `/api/entity/…` BFF the reads use (utils.jsx). The route is another
     workstream's to build, so until it deploys a 404/501 is an EXPECTED state:
     it gets said in a toast, never left as an unhandled rejection. */
  const entityId = ((route && route.path || "").match(/^\/clients\/([^/]+)/) || [])[1] || null;
  const decide = (action) => {
    if (!entityId) {
      pushToast("No entity in the route - the decision has nowhere to be recorded", "warn");
      return;
    }
    setDeciding(true);
    fetch(`/api/entity/${encodeURIComponent(entityId)}/insights/${encodeURIComponent(ic.id)}/annotation`, {
      method: "POST",
      headers: { "content-type": "application/json",
                 "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ action }),
    })
      .then(r => {
        if (r.status === 404 || r.status === 501) {
          pushToast("Annotation write path is not deployed yet", "warn");
          return null;
        }
        if (!r.ok) {
          pushToast(`Annotation write failed (${r.status})`, "warn");
          return null;
        }
        // An empty or non-JSON 2xx body still means the write landed.
        return r.json().catch(() => ({}));
      })
      .then(body => {
        if (!body) return;
        const said = String(body.action || body.status || action).toUpperCase();
        const verdict = said.indexOf("REJECT") === 0 ? "REJECTED" : "ACCEPTED";
        setDecisions(d => ({ ...d, [ic.id]: verdict }));
        pushToast(`${ic.id} ${verdict.toLowerCase()} — recorded`, "success");
      })
      .catch(() => pushToast("Annotation write failed - the API was unreachable", "warn"))
      .finally(() => setDeciding(false));
  };
  // The card's own platform chip, rendered as the run states it. Resolving it
  // through DMA.getPlatform read the static five-vendor catalogue — which knows
  // nothing about this client — and returned undefined for every promoted
  // value, so the badge was blank whenever a chip WAS present.
  const platformChip = dwText((ic.platforms || [])[0]);

  return (
    <div className="modal-mask" onClick={closeInsight}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 820 }}>
        <div className="modal-head">
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6 }}>
              <span className={`b ${ic.flag === "CRITICAL" ? "b-below" : ic.flag === "OPPORTUNITY" ? "b-org" : "b-teal"}`}>{ic.flag}</span>
              {ic.pillar ? <span className="b b-purple">{ic.pillar}</span> : null}
              <span className="chip">{ic.id}</span>
              {platformChip ? <span className="b b-teal">{platformChip}</span> : null}
              {ic.claim ? <span className="b b-muted">{ic.claim}</span> : null}
              {decided ? <span className={`b ${decided === "ACCEPTED" ? "b-teal" : "b-below"}`}>{decided}</span> : null}
              {ic.confidence ? <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Confidence · {ic.confidence}</span> : null}
            </div>
            <div style={{ fontSize: 17, fontWeight: 600, color: "var(--z-dark)", letterSpacing: "-.005em" }}>{ic.title}</div>
          </div>
          <button className="icon-btn" onClick={closeInsight}><Icon name="x" size={18} /></button>
        </div>

        <div style={{ display: "flex", padding: "0 22px", borderBottom: "1px solid var(--z-sep)" }}>
          {["detail","evidence","annotations","linked"].map(t => (
            <button key={t} className={`client-tab`} style={{ background: "transparent", color: tab === t ? "var(--z-teal)" : "var(--z-muted)", borderBottom: tab === t ? "2px solid var(--z-teal)" : "2px solid transparent" }} onClick={() => setTab(t)}>
              {t[0].toUpperCase() + t.slice(1)}{t === "annotations" && ic.annotation ? " · 1" : ""}
            </button>
          ))}
        </div>

        <div className="modal-body">
          {tab === "detail" ? (
            <div>
              {/* WHAT / WHY / SO WHAT were the only three fields this modal read.
                  The producer promotes eleven per card, and the other six were
                  adapted onto the object and displayed by nothing — the
                  severity rationale, the alternative explanation, the
                  validation question, the claim class and the whole R-Layer
                  (hypothesis, counter-argument, domain test, probes, verdict).
                  That is the shallow reading: the reasoning was written,
                  promoted, stored, served, and never shown. */}
              <Block title="WHAT" body={ic.what} evIds={ic.evidence} onEv={openEvidence} />
              <Block title="WHY" body={ic.why} />
              <Block title="SO WHAT" body={ic.so_what} accent />

              {ic.severity_rationale ? (
                <Block title={`SEVERITY · ${ic.severity || "—"}`} body={ic.severity_rationale} />
              ) : null}

              {/* The counter-case, stated by the producer. A ranked claim that
                  never shows its alternative reads as an assertion. */}
              {ic.alternative && audience !== "customer" ? (
                <div style={{ background: "var(--z-bg)", border: "1px solid var(--z-sep)", borderRadius: 8, padding: "12px 14px", marginTop: 14 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", marginBottom: 6, textTransform: "uppercase" }}>
                    Alternative explanation
                  </div>
                  <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.6 }}>{ic.alternative}</div>
                </div>
              ) : null}

              {/* What would settle it. This is the question an AE takes into the
                  room, and it was invisible. */}
              {ic.validation_question ? (
                <div className="co co-teal" style={{ marginTop: 12 }}>
                  <Icon name="info" size={14} />
                  <div style={{ flex: 1 }}>
                    <div className="co-title">Ask in discovery</div>
                    <div className="co-body">{ic.validation_question}</div>
                  </div>
                </div>
              ) : null}

              {/* The R-Layer. Internal only: it is the producer's reasoning
                  trace, not client-facing prose. */}
              {ic.r_layer && audience !== "customer" ? (
                <div style={{ background: "var(--ph0-lt)", border: "1px solid var(--ph0-bd)", borderRadius: 8, padding: "12px 14px", marginTop: 14 }}>
                  <div className="row" style={{ marginBottom: 8 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase" }}>
                      Reasoning trace
                    </span>
                    <span className="spacer" />
                    {ic.r_layer.verdict ? <span className="b b-purple">{ic.r_layer.verdict}</span> : null}
                    {ic.r_layer.confidence ? <span className="b b-muted">{ic.r_layer.confidence}</span> : null}
                  </div>
                  {[["Hypothesis", ic.r_layer.hypothesis],
                    ["Counter-evidence", ic.r_layer.counter],
                    ["Domain test", ic.r_layer.domain_test]].map(([k, v]) => v ? (
                    <div key={k} style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 2 }}>{k}</div>
                      <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.55 }}>{v}</div>
                    </div>
                  ) : null)}
                  {/* `probes_run` is deliberately NOT rendered. The probes are
                      the producer's own audit trail — which checks it ran —
                      not client content, and as chips they read as sentences
                      chopped mid-word. The prose that IS for the reader
                      (alternative explanation, validation question) renders
                      above. */}
                </div>
              ) : null}

              {(ic.affects || []).length ? (
                <div style={{ background: "var(--z-lav)", borderRadius: 8, padding: "12px 14px", marginTop: 14 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", marginBottom: 8, textTransform: "uppercase" }}>Affects · {ic.affects.length} capabilit{ic.affects.length === 1 ? "y" : "ies"}</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {ic.affects.map(sid => (
                      <button key={sid} className="chip purple" onClick={() => openSubcap(sid)}>{sid}</button>
                    ))}
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: 11.5, color: "var(--z-muted)", marginTop: 14 }}>
                  This card names no capability cell, so it cannot be traced back
                  to the assessment grid.
                </div>
              )}
              {/* PAGE-KILLER, fixed: this read `DMA.getPlatform(rec.platform).name`.
                  A promoted recommendation states no `platform` id at all (it
                  states `l3_area` and `l4_feature`), so the lookup returned
                  undefined and `.name` threw — unmounting the whole app the
                  moment an insight card with a linked recommendation opened.
                  `rec.feature` was the fixture's key for the same reason. */}
              {rec && audience !== "customer" ? (
                <div className="co co-teal" style={{ marginTop: 12, cursor: "pointer" }} onClick={() => { closeInsight(); openRec(rec.id); }}>
                  <Icon name="platform" size={14} />
                  <div style={{ flex: 1 }}>
                    <div className="co-title">Linked recommendation · click for impact</div>
                    <div className="co-body">
                      <strong>{rec.id}</strong> - {dwText(rec.title)}
                      {[dwText(rec.l3), dwText(rec.l4), rec.phase ? `phase ${rec.phase}` : null]
                        .filter(Boolean).map(t => <span key={t}> · {t}</span>)}
                    </div>
                  </div>
                  <Icon name="arrow-r" size={14} style={{ color: "var(--z-mid)" }} />
                </div>
              ) : null}
            </div>
          ) : tab === "evidence" ? (
            <div>
              {(ic.evidence || []).length === 0 ? (
                <div className="empty">
                  <div className="icon"><Icon name="evidence" size={20} /></div>
                  <h3>This card cites no evidence</h3>
                  <p>`supporting_e_ids` is empty on the promoted card, so there is
                     nothing to open. A ranked claim with no citation is a producer
                     defect worth reporting.</p>
                </div>
              ) : null}
              {(ic.evidence || []).map(eid => {
                const e = DMA.getEvidence(eid);
                // Fail closed and SAY so (invariant 4). Returning null for an
                // unresolved id hid a dead citation completely: a card citing
                // five ids of which two do not resolve rendered three, and the
                // tab looked complete.
                if (!e) return (
                  <div key={eid} style={{ padding: "12px 0", borderBottom: "1px solid var(--z-sep)" }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <span className="chip muted">{eid}</span>
                      <span style={{ fontSize: 11.5, color: "var(--z-muted)" }}>
                        cited id — not in this run's served evidence
                      </span>
                    </div>
                  </div>
                );
                return (
                  <div key={eid} style={{ padding: "12px 0", borderBottom: "1px solid var(--z-sep)" }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
                      <button className="chip" onClick={() => openEvidence(eid)}>{e.id}</button>
                      <span className={`tier-chip tier-${e.tier}`}>{e.tier}</span>
                      {e.claim ? <span className="b b-purple">{e.claim}</span> : null}
                      <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--z-muted)" }}>
                        {e.recency}{dwNum(e.ers) === null ? "" : ` · ERS ${e.ers}`}</span>
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{e.title}</div>
                    {dwText(e.excerpt) ? (
                      <div style={{ fontStyle: "italic", padding: "6px 10px", background: "var(--z-bg)", borderLeft: "2px solid var(--z-teal)", fontSize: 12, color: "var(--z-body)" }}>"{dwText(e.excerpt)}"</div>
                    ) : (
                      <div style={{ padding: "6px 10px", background: "var(--z-bg)", borderLeft: "2px dashed var(--z-sep)", fontSize: 11.5, color: "var(--z-muted)" }}>
                        no verbatim excerpt served for this item
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : tab === "annotations" ? (
            <div>
              {ic.annotation ? (
                <div style={{ background: "var(--z-lav)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6, fontSize: 12 }}>
                    <div className="sb-avatar" style={{ width: 22, height: 22, fontSize: 9 }}>{sessionUser().initials}</div>
                    <strong>{ic.annotation.author}</strong>
                    <span className="b b-teal">{ic.annotation.role}</span>
                    <span className="b b-above">{ic.annotation.status}</span>
                    <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--z-muted)" }}>{ic.annotation.when}</span>
                  </div>
                  <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.55 }}>{ic.annotation.body}</div>
                </div>
              ) : <div className="muted" style={{ marginBottom: 12, fontSize: 12 }}>No annotations yet.</div>}

              <div className="field-group">
                <label className="inp-label">Add a note</label>
                <textarea className="inp" rows={4} placeholder="Discussed with Delivery Lead before the call…" value={note} onChange={e => setNote(e.target.value)} />
                <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center" }}>
                  <select className="inp" style={{ maxWidth: 180 }} value={annStatus} onChange={e => setAnnStatus(e.target.value)}>
                    <option>ACTIONED</option><option>PENDING</option><option>SUPERSEDED</option>
                  </select>
                  <input className="inp" style={{ maxWidth: 220 }} placeholder="Salesforce opp ID (optional)" />
                  <span className="spacer" />
                  <button className="btn btn-primary btn-sm" onClick={() => { setNote(""); }}><Icon name="check" size={12} /> Save note</button>
                </div>
              </div>
            </div>
          ) : (
            /* The Linked tab used to print two headings and, in a promoted run,
               nothing under either: the cell chips were dead spans and the
               platform row resolved every chip through the static vendor
               catalogue (`DMA.getPlatform(p)?.name` → undefined). Each row now
               either navigates somewhere or names the field that is unset — on
               this run `platform_chips` and `linked_rec_id` are null on all
               eight cards, and the tab says exactly that rather than showing an
               empty box. */
            <div style={{ fontSize: 12, color: "var(--z-body)" }}>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>
                Capability cells · {(ic.affects || []).length}
              </div>
              {(ic.affects || []).length ? (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 16 }}>
                  {ic.affects.map(sid => (
                    <button key={sid} className="chip purple" onClick={() => { closeInsight(); openSubcap(sid); }}>{sid}</button>
                  ))}
                </div>
              ) : (
                <p style={{ color: "var(--z-muted)", marginBottom: 16 }}>
                  Neither `affects` nor `linked_subcap_id` is set on this card, so
                  it cannot be traced to the assessment grid.
                </p>
              )}

              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>
                Platforms
              </div>
              {(ic.platforms || []).length ? (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
                  {ic.platforms.map(p => <span key={p} className="b b-teal">{dwText(p)}</span>)}
                </div>
              ) : (
                <p style={{ color: "var(--z-muted)", marginBottom: 16 }}>
                  `platform_chips` is unset on this card and it names no
                  recommendation to inherit one from, so no platform is implicated
                  by the run.
                </p>
              )}

              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>
                Recommendation
              </div>
              {rec ? (
                <button className="btn btn-tertiary btn-sm" onClick={() => { closeInsight(); openRec(rec.id); }}>
                  {rec.id} · {dwText(rec.title)}
                </button>
              ) : (
                <p style={{ color: "var(--z-muted)", marginBottom: 16 }}>
                  `linked_rec_id` is unset, so this card is not joined to a
                  recommendation in this run.
                </p>
              )}

              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", margin: "16px 0 8px" }}>
                Evidence · {(ic.evidence || []).length}
              </div>
              {(ic.evidence || []).length ? (
                <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                  {ic.evidence.map(eid => {
                    const e = DMA.getEvidence(eid);
                    return e ? (
                      <button key={eid} className={`tier-chip tier-${e.tier}`} style={{ cursor: "pointer", border: 0 }}
                        title={`${e.title || eid} · ${e.source_pretty || ""}`}
                        onClick={() => openEvidence(eid)}>{eid}</button>
                    ) : (
                      <span key={eid} className="chip muted" title="cited id - not in this run's served evidence">{eid}</span>
                    );
                  })}
                </div>
              ) : (
                <p style={{ color: "var(--z-muted)" }}>This card cites no evidence ids.</p>
              )}
            </div>
          )}
        </div>
        <div className="modal-foot">
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-tertiary" onClick={() => {
              // "null" and "undefined" used to be pasted into a deck whenever a
              // field was absent; an absent field is now simply not copied.
              const text = [
                [ic.id, ic.flag, ic.pillar].filter(Boolean).join(" · "),
                dwText(ic.title),
                dwText(ic.what) ? `\nWHAT: ${dwText(ic.what)}` : null,
                dwText(ic.why) ? `\nWHY: ${dwText(ic.why)}` : null,
                dwText(ic.so_what) ? `\nSO WHAT: ${dwText(ic.so_what)}` : null,
              ].filter(Boolean).join("\n");
              try { navigator.clipboard.writeText(text); pushToast("Insight card copied to clipboard", "success"); }
              catch (e) { pushToast("Couldn't access clipboard", "warn"); }
            }}><Icon name="copy" size={13} /> Copy card</button>
            <button className="btn btn-tertiary" onClick={() => pushToast(`Exporting ${ic.id} as PDF…`, "success")}><Icon name="download" size={13} /> Export</button>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button className="btn btn-secondary" disabled={deciding} onClick={() => decide("ACCEPT")}><Icon name="check" size={13} /> Accept</button>
            <button className="btn btn-secondary" disabled={deciding} onClick={() => decide("REJECT")}><Icon name="x" size={13} /> Reject</button>
            <button className="btn btn-primary" onClick={closeInsight}>Close</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Block({ title, body, evIds, onEv, accent }) {
  // PAGE-KILLER, fixed: `body` went straight into `re.exec(body)` and
  // `body.length`. A card whose promoted field is null (the contract requires
  // what/why/so-what, but nothing in the serving path enforces it) threw on
  // `null.length` and blanked the application. An absent field now says so.
  const text = dwText(body);

  // Inject tier-coloured chips for inline citation tokens. The old pattern
  // (`E-` + digits) matched none of this run's ids — they are E-BCU-066,
  // E-CC-004 — so a citation written into the prose stayed plain text.
  const parts = [];
  let last = 0;
  const src = text || "";
  const re = /\[?\bE-[A-Z0-9]+(?:-[A-Z0-9]+)*\b\]?/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    if (m.index > last) parts.push(src.slice(last, m.index));
    parts.push({ chip: m[0].replace(/[\[\]]/g, "") });
    last = m.index + m[0].length;
  }
  if (last < src.length) parts.push(src.slice(last));

  // Fail closed on evidence (invariant 4): an id that does not resolve in this
  // run is not clickable and not dressed as a tier. It used to render as a T1
  // chip that opened an empty drawer, which reads as evidence that exists.
  const renderChip = (id) => {
    const ev = DMA.getEvidence(id);
    if (!ev) return (
      <span key={id} className="chip muted" style={{ marginLeft: 4 }}
            title="cited id - not in this run's served evidence">{id}</span>
    );
    return <button key={id} className={`tier-chip tier-${ev.tier}`} style={{ marginLeft: 4, cursor: "pointer" }} onClick={() => onEv && onEv(id)} title={ev.title}>{id}<span style={{ fontWeight: 400, opacity: .65, marginLeft: 4 }}>·{ev.tier}</span></button>;
  };

  return (
    <div style={{ marginBottom: 14, borderLeft: accent ? "3px solid var(--z-teal)" : "3px solid var(--z-sep)", paddingLeft: 14 }}>
      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".12em", color: accent ? "var(--z-mid)" : "var(--z-muted)", textTransform: "uppercase", marginBottom: 6 }}>{title}</div>
      <div style={{ fontSize: 13.5, color: text ? "var(--z-dark)" : "var(--z-muted)", lineHeight: 1.65 }}>
        {text ? parts.map((p, i) => typeof p === "string" ? <span key={i}>{p}</span> : renderChip(p.chip))
              : <span>the run states no text for this field</span>}
        {evIds && evIds.length ? <span style={{ marginLeft: 6 }}>{evIds.map(eid => renderChip(eid))}</span> : null}
      </div>
    </div>
  );
}

/* One citation chip. Fail closed (invariant 4): an id that does not resolve
   in this run is shown and NOT clickable — it used to render as a T1 chip
   that opened an empty drawer, which reads as evidence that exists. */
function IpCite({ id, onEv }) {
  const ev = DMA.getEvidence(id);
  if (!ev) return <span className="chip muted" style={{ fontSize: 9 }}
                        title="cited id - not in this run's served evidence">{id}</span>;
  return (
    <button className={`tier-chip tier-${ev.tier}`}
            style={{ cursor: "pointer", border: 0, fontSize: 9 }}
            title={`${ev.title || id} · ${ev.source_pretty || ""}`}
            onClick={() => onEv && onEv(id)}>{id}</button>
  );
}

/* One part of an answer: the promoted sentence, then where it is from and
   what grounds it. Each part is its own block on purpose — see the answer
   path's opening note on why parts are never joined.

   Citations render at most six chips and then a count. The section-level
   case is labelled differently from the item-level one: a paragraph that
   inherits its section's list is grounded by that section, not by fifty-nine
   items of its own, and saying so is the difference between a citation and a
   decoration. */
const IP_CHIP_LIMIT = 6;
function IpPart({ part, onEv }) {
  const text = dwText(part && part.text);
  if (!text) return null;
  const ids = Array.isArray(part.e_ids) ? part.e_ids : [];
  const where = ipWhere(part.json_path);
  return (
    <div style={{ marginBottom: 10, borderLeft: "2px solid var(--z-sep)", paddingLeft: 10 }}>
      <div style={{ fontSize: 12.5, lineHeight: 1.6, color: "var(--z-dark)", whiteSpace: "pre-wrap" }}>{text}</div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center", marginTop: 5 }}>
        {where ? (
          <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--z-muted)" }}>
            {where}
          </span>
        ) : null}
        {ids.length ? (
          <span style={{ fontSize: 9, color: "var(--z-muted)" }}>
            {part.cite_scope === "section" ? "· section cites" : "·"}
          </span>
        ) : null}
        {ids.slice(0, IP_CHIP_LIMIT).map(id => <IpCite key={id} id={id} onEv={onEv} />)}
        {ids.length > IP_CHIP_LIMIT ? (
          <span style={{ fontSize: 9, color: "var(--z-muted)" }}>+{ids.length - IP_CHIP_LIMIT} more</span>
        ) : null}
        {!ids.length ? (
          <span style={{ fontSize: 9, color: "var(--z-muted)" }}>· the run cites nothing for this field</span>
        ) : null}
      </div>
    </div>
  );
}

/* The three shapes an answer can take, rendered so they cannot be mistaken
   for each other: prose the run promoted, quotations the run states, or an
   absence with the next step named. */
function IpAnswer({ res, onEv }) {
  if (!res) return null;
  if (res.kind === "none") {
    return (
      <div className="ip-message ai" style={{ display: "block" }}>
        <div style={{ marginBottom: 8 }}>
          This run states nothing that answers that. It is not a gap in the
          panel - nothing was promoted for it, and the alternative to saying
          so is making something up.
        </div>
        <button className="btn btn-tertiary btn-sm" disabled
                title={"Not built: queueing a question writes an annotation with a "
                       + "`question` anchor kind, and widening this app's writes past "
                       + "its two exceptions has not been adjudicated."}>
          <Icon name="calendar" size={12} /> Queue for the next synthesis run
        </button>
        <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 5 }}>
          Unavailable - the queue needs a question anchor on annotations,
          which is not adjudicated.
        </div>
      </div>
    );
  }
  const parts = Array.isArray(res.parts) ? res.parts : [];
  return (
    <div className="ip-message ai" style={{ display: "block" }}>
      <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--z-dpur)", marginBottom: 7 }}>
        {res.kind === "passages"
          ? `${res.frame} · ${parts.length} verbatim`
          : (res.provenance === "promoted"
              ? "Promoted answer" : `Promoted prose · ${parts.length}`)}
      </div>
      {parts.map((p, i) => <IpPart key={p.json_path || i} part={p} onEv={onEv} />)}
      {res.kind === "passages" ? (
        <div style={{ fontSize: 10, color: "var(--z-muted)" }}>
          Ranked from this run's own text. Nothing above was written for the
          question - it is what the run already says, quoted.
        </div>
      ) : null}
    </div>
  );
}

/* ── Intelligence Panel ─────────────────────────────────────────── */
function IntelligencePanel() {
  const { ipOpen, setIpOpen, ipSurface, ipContext, authed, pushToast, openEvidence, openSubcap } = useApp();
  const [text, setText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [chat, setChat] = useState([]);          // [{role: 'user'|'ai', text}]
  const [chatInput, setChatInput] = useState("");
  const [chatStreaming, setChatStreaming] = useState(false);
  const messages = useMemo(() => surfaceMessages(ipSurface, ipContext), [ipSurface, ipContext]);
  const bodyRef = useRef(null);
  // The typewriter slices this, so a surface that returned no body at all would
  // throw on `null.slice` and unmount the application from a globally mounted
  // panel. Coerced once, here.
  const bodyText = String((messages && messages.body) || "");

  // Reset on surface change
  useEffect(() => {
    if (!ipOpen) return;
    setText("");
    setStreaming(true);
    setChat([]);
    let i = 0;
    const id = setInterval(() => {
      i += 4;
      setText(bodyText.slice(0, i));
      if (i >= bodyText.length) { clearInterval(id); setStreaming(false); }
    }, 16);
    return () => clearInterval(id);
  }, [ipOpen, messages]);

  // Follow the conversation only when there IS one. This fired on the initial
  // empty chat too, so opening the panel jumped straight to the bottom of the
  // body — the reader landed on the last line of the synthesis with the whole
  // story scrolled off above it.
  useEffect(() => {
    if (chat.length && bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [chat, chatStreaming]);

  const STARTERS = useMemo(() => starterQuestions(ipSurface, ipContext), [ipSurface, ipContext]);
  /* The questions this run can answer on this surface, resolved against the
     payload already in the browser. Recomputed when the surface or the
     selection changes, and cheap: the corpus walk behind it is memoised on
     the entity object, so this is a path match over an array. */
  const ANSWERABLE = useMemo(
    () => (IP_LIVE() ? ipAnswerable(ipSurface, ipContext) : []),
    [ipSurface, ipContext, chat.length]);

  // Never show before sign-in (rule of hooks: gate AFTER all hook calls)
  if (!authed) return null;

  const ask = (question) => {
    const q = String(question || chatInput || "").trim();
    if (!q) return;
    setChatInput("");
    if (IP_LIVE()) {
      /* Instant, and no request. The run's own prose is already in this
         browser from the six page fetches, so a starter question is a path
         match and a free-text question is a rank over ~1,200 paragraphs —
         both single-digit milliseconds. Nothing is streamed because there is
         nothing to wait for: a typewriter on text that is already resolved
         is a costume for latency that does not exist. */
      setChat(c => [...c, { role: "user", text: q },
                    { role: "ai", answer: ipResolve(q, ipSurface, ipContext) }]);
      return;
    }
    setChat(c => [...c, { role: "user", text: q }, { role: "ai", text: "" }]);
    setChatStreaming(true);
    const answer = answerFor(q, ipSurface, ipContext);
    let i = 0;
    const id = setInterval(() => {
      i += 3;
      setChat(c => {
        const next = [...c];
        next[next.length - 1] = { role: "ai", text: answer.slice(0, i) };
        return next;
      });
      if (i >= answer.length) { clearInterval(id); setChatStreaming(false); }
    }, 14);
  };

  if (!ipOpen) {
    return (
      <button className="ip-tab" onClick={() => setIpOpen(true)} title="Open Intelligence">
        ✦ INTELLIGENCE
      </button>
    );
  }

  return (
    <aside className="ip">
      <div className="ip-head">
        <div className="ai">✦</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="title txt-fit-1">{messages.title}</div>
          <div className="sub txt-fit-1">{messages.sub}</div>
        </div>
        <button className="icon-btn" onClick={() => setIpOpen(false)}><Icon name="x" size={14} /></button>
      </div>
      <div ref={bodyRef} className="ip-body">
        {/* pre-wrap: every surface body separates its paragraphs with "\n\n",
            which HTML collapses to a single space — the fixture's three-paragraph
            meeting prep and the promoted multi-platform story both rendered as
            one unbroken wall of text. */}
        <div style={{ fontSize: 13, lineHeight: 1.65, whiteSpace: "pre-wrap" }}>
          {text}{streaming ? <span className="ip-cursor" /> : null}
        </div>
        {!streaming && ipSurface === "why_now" ? <WhyNowSignals ctx={ipContext} openEvidence={openEvidence} pushToast={pushToast} /> : null}
        {!streaming && messages.detail && messages.detail.kind === "platform_story"
          ? <PlatformStoryDetail data={messages.detail} openEvidence={openEvidence} openSubcap={openSubcap} />
          : null}
        {!streaming ? (
          <div style={{ marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button className="btn btn-tertiary btn-sm" onClick={() => {
              try { navigator.clipboard.writeText(text); pushToast("Copied response", "success"); }
              catch (e) { pushToast("Couldn't access clipboard", "warn"); }
            }}><Icon name="copy" size={12} /> Copy</button>
            <button className="btn btn-tertiary btn-sm" onClick={() => {
              setText(""); setStreaming(true);
              let i = 0;
              const id = setInterval(() => {
                i += 4;
                setText(bodyText.slice(0, i));
                if (i >= bodyText.length) { clearInterval(id); setStreaming(false); }
              }, 16);
            }}><Icon name="refresh" size={12} /> Replay</button>
            {IP_LIVE() ? null : (
              <button className="btn btn-tertiary btn-sm" onClick={() => pushToast("Routed to Gemini Pro - deeper analysis takes ~8s", "success")}>Deeper · Pro</button>
            )}
          </div>
        ) : null}

        {/* Chat. An AI turn is either the prototype's streamed string or, in
            LIVE, a resolved answer object — prose the run promoted, or its
            own passages quoted, or a stated absence. The two shapes are
            rendered by different components on purpose: a quotation must not
            be able to arrive looking like an authored reply. */}
        {chat.length > 0 ? (
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed var(--ph0-bd)" }}>
            {chat.map((m, i) => (
              m.answer
                ? <IpAnswer key={i} res={m.answer} onEv={openEvidence} />
                : <div key={i} className={`ip-message ${m.role}`}>{m.text}{m.role === "ai" && chatStreaming && i === chat.length - 1 ? <span className="ip-cursor" /> : null}</div>
            ))}
          </div>
        ) : null}
      </div>

      {/* Two lists in LIVE, and they are different things.

          ANSWERABLE are QUESTIONS this run can answer — every one is
          resolved before it is offered, so a click always lands on promoted
          prose. A question shown and then met with "nothing promoted" is the
          same broken control in a politer voice.

          STARTERS are the producer's promoted TALKING POINTS: what an AE
          says to the client, not what the AE asks the app. They stay
          read-only, because they are not questions and nothing answers them.

          maxHeight: the promoted starters are 60–90-word paragraphs, five of
          them. `.ip-chat` has no bound, so it took most of the panel and
          squeezed the body — the synthesis this panel exists to show was two
          visible lines under 700px of starters. It scrolls on its own now. */}
      {!chatStreaming && (ANSWERABLE.length || STARTERS.length) ? (
        <div className="ip-chat" style={IP_LIVE() ? { maxHeight: "38vh", overflowY: "auto" } : null}>
          {IP_LIVE() && ANSWERABLE.length ? (
            <>
              <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase", marginBottom: 6 }}>
                Answered by this run · {ANSWERABLE.length}
              </div>
              {ANSWERABLE.map(a => (
                <button key={a.q_id} className="ip-starter" onClick={() => ask(a.question)}>
                  {a.question}
                </button>
              ))}
            </>
          ) : null}
          {STARTERS.length ? (
            <div style={{ marginTop: IP_LIVE() && ANSWERABLE.length ? 10 : 0 }}>
              <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase", marginBottom: 6 }}>
                {IP_LIVE() ? `Conversation starters · promoted · ${STARTERS.length}`
                           : (chat.length === 0 ? "Try a question" : "Follow-ups")}
              </div>
              {STARTERS.map((s, i) => (
                IP_LIVE()
                  ? <div key={i} className="ip-starter" style={{ cursor: "default" }}>{s}</div>
                  : <button key={i} className="ip-starter" onClick={() => ask(s)}>{s}</button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* The question box works in LIVE now. It runs no model: a question
          that is not in the answered set is met with the run's own passages,
          ranked and quoted, or with an honest "the run states nothing about
          that". The placeholder says which, so the reader knows what they
          are getting before they type. */}
      <div className="ip-input">
        <input placeholder={IP_LIVE()
                 ? "Ask about this run - answers are quoted from it, never written"
                 : "Ask anything about this entity…"}
               value={chatInput}
               onChange={e => setChatInput(e.target.value)}
               onKeyDown={e => e.key === "Enter" && ask()} />
        <button className="btn btn-primary btn-sm" onClick={() => ask()} disabled={!chatInput.trim() || chatStreaming}>
          <Icon name="arrow-r" size={12} />
        </button>
      </div>
    </aside>
  );
}

/* The promoted platform story's structure, under its prose.

   Each gap row states its cell, the cell's measured score, the peer basis (or
   the note explaining why no peer figure exists at this grain), the L4 feature,
   the catalogue path and its evidence ids. Flattening that into a sentence loses
   the traceability, which is the only reason a reader trusts the story — so the
   rows render as rows, the cell chips open the cell, and the evidence chips open
   the drawer. An id that does not resolve in this run is shown and NOT clickable
   (invariant 4, fail closed).

   No colour is taken from the payload: the score's band and hex come from the
   one resolver via dwBand, and the band word is printed beside the score so the
   colour is never the only carrier of meaning. */
function PlatformStoryDetail({ data, openEvidence, openSubcap }) {
  const [openGaps, setOpenGaps] = useState(true);
  const [openOut, setOpenOut] = useState(false);
  const platforms = data.platforms || [];
  const discarded = data.discarded || [];
  const gapTotal = platforms.reduce((n, p) => n + ((p.gaps || []).length), 0);

  const evChip = (eid) => {
    const e = DMA.getEvidence(eid);
    return e ? (
      <button key={eid} className={`tier-chip tier-${e.tier}`} style={{ cursor: "pointer", border: 0, fontSize: 9 }}
        title={`${e.title || eid} · ${e.source_pretty || ""}`}
        onClick={() => openEvidence(eid)}>{eid}</button>
    ) : (
      <span key={eid} className="chip muted" style={{ fontSize: 9 }}
            title="cited id - not in this run's served evidence">{eid}</span>
    );
  };

  return (
    <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed var(--ph0-bd)" }}>
      {gapTotal ? (
        <>
          <button onClick={() => setOpenGaps(o => !o)}
            style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", background: "none", border: 0, padding: 0, cursor: "pointer", marginBottom: 8 }}>
            <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase" }}>
              Gaps this closes · {gapTotal}
            </span>
            <span className="spacer" />
            <Icon name={openGaps ? "chevron-u" : "chevron-d"} size={13} style={{ color: "var(--z-dpur)" }} />
          </button>
          {openGaps ? platforms.map((p, pi) => (
            <div key={pi} style={{ marginBottom: 10 }}>
              {(p.gaps || []).map((g, gi) => {
                const band = dwBand(g.current_score);
                const peer = dwNum(g.peer_score);
                return (
                  <div key={g.subcap_id || gi} className="card-tile" style={{ padding: "8px 10px", marginBottom: 6 }}>
                    <div className="row" style={{ gap: 5, flexWrap: "wrap", alignItems: "center" }}>
                      {g.subcap_id ? (
                        <button className="chip purple" style={{ fontSize: 9.5 }}
                          onClick={() => openSubcap && openSubcap(g.subcap_id)}>{g.subcap_id}</button>
                      ) : null}
                      {dwText(g.pillar) ? <span className="b b-muted">{dwText(g.pillar)}</span> : null}
                      <span style={{ fontSize: 11.5, fontWeight: 600, color: "var(--z-dark)", flex: 1, minWidth: 0, wordBreak: "break-word" }}>
                        {dwText(g.name) || "cell not named"}
                      </span>
                      {band ? (
                        <span className="row" style={{ gap: 4, flexShrink: 0 }}>
                          <span style={{ width: 8, height: 8, borderRadius: 2, background: band.hex, display: "inline-block" }} />
                          <span className="f-mono" style={{ fontSize: 10.5, color: "var(--z-body)" }}>{fx(band.score, 1)}</span>
                          <span style={{ fontSize: 9.5, color: "var(--z-muted)" }}>{band.label}</span>
                        </span>
                      ) : <span style={{ fontSize: 9.5, color: "var(--z-muted)" }}>not scored</span>}
                    </div>
                    <div className="row" style={{ gap: 5, marginTop: 4, flexWrap: "wrap" }}>
                      {peer !== null ? (
                        <span style={{ fontSize: 9.5, color: "var(--z-muted)" }}>peer {fx(peer, 1)}</span>
                      ) : dwText(g.peer_basis) ? (
                        // The basis, with the run's own note as the tooltip. A
                        // missing peer figure is never rendered as a zero or as a
                        // delta computed against nothing.
                        <span className="b b-muted" title={dwText(g.peer_note) || ""}>
                          peer · {dwText(g.peer_basis).replace(/_/g, " ")}
                        </span>
                      ) : null}
                      {dwText(g.l4_feature) ? (
                        <span style={{ fontSize: 9.5, color: "var(--z-mid)" }}>L4 · {dwText(g.l4_feature)}</span>
                      ) : null}
                    </div>
                    {/* The catalogue path ends in the L4 feature and the cell
                        name, so it is shown once, small, and wrapped — it is the
                        row's provenance, not its headline. */}
                    {dwText(g.catalogue_path) ? (
                      <div style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 3, lineHeight: 1.4, wordBreak: "break-word" }}>
                        {dwText(g.catalogue_path)}
                      </div>
                    ) : null}
                    {dwText(g.gap) ? (
                      <div style={{ fontSize: 11, color: "var(--z-body)", marginTop: 4, lineHeight: 1.5 }}>{dwText(g.gap)}</div>
                    ) : null}
                    {(g.e_ids || []).length ? (
                      <div className="row" style={{ gap: 4, marginTop: 5, flexWrap: "wrap" }}>{g.e_ids.map(evChip)}</div>
                    ) : (
                      <div style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 5 }}>no evidence cited for this row</div>
                    )}
                  </div>
                );
              })}
            </div>
          )) : null}
        </>
      ) : null}

      {discarded.length ? (
        <>
          <button onClick={() => setOpenOut(o => !o)}
            style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", background: "none", border: 0, padding: 0, cursor: "pointer", margin: "6px 0 8px" }}>
            <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase" }}>
              Considered and set aside · {discarded.length}
            </span>
            <span className="spacer" />
            <Icon name={openOut ? "chevron-u" : "chevron-d"} size={13} style={{ color: "var(--z-dpur)" }} />
          </button>
          {openOut ? discarded.map((x, i) => {
            const rel = dwNum(x.relevance);
            return (
              <div key={i} style={{ marginBottom: 8 }}>
                <div className="row" style={{ gap: 5, alignItems: "baseline", flexWrap: "wrap" }}>
                  <span style={{ fontSize: 11.5, fontWeight: 600, color: "var(--z-dark)", wordBreak: "break-word" }}>
                    {dwText(x.platform) || dwText(x.name) || "platform not named"}
                  </span>
                  {rel === null ? null : (
                    <span className="b b-muted f-mono" title="relevance to the assessed gaps">{rel.toFixed(2)}</span>
                  )}
                </div>
                {dwText(x.reason) ? (
                  <div style={{ fontSize: 10.5, color: "var(--z-muted)", lineHeight: 1.5, marginTop: 2 }}>{dwText(x.reason)}</div>
                ) : null}
              </div>
            );
          }) : null}
        </>
      ) : null}
    </div>
  );
}

function WhyNowSignals({ ctx, openEvidence, pushToast }) {
  const [open, setOpen] = useState(null);
  // No fixture fallback: with no entity in context this panel has nothing to
  // say, and defaulting to fce-001 put the flagship's triggers under whichever
  // client was open.
  const entId = ctx?.entity?.id;
  const wn = entId ? DMA.whyNowFor(entId) : null;
  const signals = Array.isArray(wn) ? wn : ((wn && wn.signals) || []);
  if (!signals.length) return null;
  /* Icon and colour per signal CATEGORY. The keys were the fixture's
     (core_migration, hiring, market); the contract's `kind` vocabulary is
     M&A · LEADERSHIP · REGULATORY · TECHNOLOGY, so every promoted signal missed
     the map and fell back to the "market" pairing. Matched case-insensitively
     against both vocabularies now. The colour is presentation derived from the
     category, not a claim about the client. */
  const CAT = {
    "m&a":            { icon: "stack",   color: "var(--z-dpur)" },
    leadership:       { icon: "users",   color: "var(--z-dpur)" },
    regulatory:       { icon: "lock",    color: "var(--z-org)" },
    technology:       { icon: "platform", color: "var(--z-teal)" },
    core_migration:   { icon: "refresh", color: "var(--z-teal)" },
    hiring:           { icon: "users",   color: "var(--z-mid)" },
    market:           { icon: "stack",   color: "var(--z-mid)" },
  };
  const catOf = (c) => CAT[String(c == null ? "" : c).trim().toLowerCase()]
    || { icon: "sparkle", color: "var(--z-mid)" };
  const STR = { STRONG: "b-teal", LEADING: "b-purple", SUPPORTING: "b-muted" };
  return (
    <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed var(--ph0-bd)" }} data-source="evidence_index.json (trigger) + timeline_events.csv">
      <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase", marginBottom: 8 }}>
        Trigger signals · click to drill in
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {/* Every text colour here was white or white-with-alpha over
            `rgba(255,255,255,.04)` — and `.ip` is a WHITE panel, so the signal
            title, the detail, the metric and the dates were painted white on
            white and read as an empty expanding row. The panel's own tokens are
            used instead. */}
        {signals.map((s, si) => {
          const key = s.id || `WN-${si}`;
          const isOpen = open === key;
          const cat = catOf(s.category);
          const strength = dwText(s.strength);
          return (
            <div key={key} className="wn-signal" style={{ border: "1px solid var(--ph0-bd)", borderRadius: 8, overflow: "hidden", background: "rgba(255,255,255,.6)" }}>
              <button onClick={() => setOpen(o => o === key ? null : key)}
                style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, padding: "9px 10px", background: "none", border: 0, cursor: "pointer", textAlign: "left" }}>
                <span style={{ width: 22, height: 22, borderRadius: 6, background: cat.color, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><Icon name={cat.icon} size={12} /></span>
                <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 600, color: "var(--z-dark)" }} className="txt-fit-1">{dwText(s.label) || key}</span>
                {/* An empty badge used to render for every promoted signal:
                    `strength` is not in the why-now contract, so the pill was a
                    coloured box with no word in it. */}
                {strength ? <span className={`b ${STR[strength.toUpperCase()] || "b-muted"}`}>{strength}</span> : null}
                {dwText(s.category) ? <span className="b b-muted">{dwText(s.category)}</span> : null}
                <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={13} style={{ color: "var(--z-dpur)", flexShrink: 0 }} />
              </button>
              {isOpen ? (
                <div style={{ padding: "0 10px 10px", fontSize: 12, lineHeight: 1.6, color: "var(--z-body)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap", marginBottom: 8 }}>
                    {s.confidence ? <span className="b b-teal">{s.confidence} confidence</span> : null}
                    {s.claim ? <span className="b b-purple">{s.claim}</span> : null}
                  </div>
                  {dwText(s.metric) ? (
                    <div className="f-mono" style={{ background: "var(--z-bg)", border: "1px solid var(--z-sep)", borderRadius: 6, padding: "6px 9px", marginBottom: 8, fontSize: 11.5, color: "var(--z-dark)" }}>{dwText(s.metric)}</div>
                  ) : null}
                  {dwText(s.detail) ? <div style={{ marginBottom: 8 }}>{dwText(s.detail)}</div> : null}
                  {dwText(s.peer_context) ? (
                    <div style={{ marginBottom: 8 }}>
                      <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase" }}>Peer context · </span>
                      <span style={{ fontSize: 11.5 }}>{dwText(s.peer_context)}</span>
                    </div>
                  ) : null}
                  {/* PAGE-KILLER, fixed: `s.timeline.date`. The adapter sets
                      `timeline` to null for a signal with no `dated_on`, so an
                      undated signal threw the moment it was expanded and took the
                      whole application with it. An undated signal now says so —
                      never "current", per invariant 9. */}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--z-muted)", marginBottom: 8 }}>
                    <Icon name="timeline" size={11} />
                    {s.timeline && dwText(s.timeline.date)
                      ? <><span className="f-mono">{dwText(s.timeline.date)}</span>
                          {dwText(s.timeline.event) ? <span>· {dwText(s.timeline.event)}</span> : null}</>
                      : <span>undated — no dated source on this signal</span>}
                  </div>
                  {dwText(s.play) ? (
                    <div style={{ background: "var(--z-ice)", borderLeft: "2px solid var(--z-teal)", borderRadius: 4, padding: "7px 9px", fontSize: 11.5, color: "var(--z-dark)", marginBottom: 6 }}>
                      <strong style={{ color: "var(--z-mid)" }}>Sequence · </strong>{dwText(s.play)}
                    </div>
                  ) : null}
                  {/* `impact` is not a why-now field; this block rendered "So what
                      ·" with nothing after it on every signal. The contract's
                      cost-of-acting-now IS promoted and was read by nothing. */}
                  {dwText(s.impact) ? (
                    <div style={{ background: "var(--z-ice)", borderLeft: "2px solid var(--z-teal)", borderRadius: 4, padding: "7px 9px", fontSize: 11.5, color: "var(--z-dark)", marginBottom: 6 }}>
                      <strong style={{ color: "var(--z-mid)" }}>So what · </strong>{dwText(s.impact)}
                    </div>
                  ) : null}
                  {dwText(s.cost_now) ? (
                    <div style={{ background: "var(--z-lav)", borderLeft: "2px solid var(--z-dpur)", borderRadius: 4, padding: "7px 9px", fontSize: 11.5, color: "var(--z-dark)", marginBottom: 6 }}>
                      <strong style={{ color: "var(--z-dpur)" }}>Cost of acting now · </strong>{dwText(s.cost_now)}
                    </div>
                  ) : null}
                  {dwText(s.risk) ? (
                    <div style={{ background: "rgba(254,151,50,.14)", borderLeft: "2px solid var(--z-org)", borderRadius: 4, padding: "7px 9px", fontSize: 11.5, color: "var(--z-dark)", marginBottom: 8 }}>
                      <strong style={{ color: "var(--z-org)" }}>Risk if ignored · </strong>{dwText(s.risk)}
                    </div>
                  ) : null}
                  {(s.subcaps || []).length ? (
                    <div className="row" style={{ gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
                      <span style={{ fontSize: 9.5, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>Cells</span>
                      {s.subcaps.map(sid => <span key={sid} className="chip purple">{sid}</span>)}
                    </div>
                  ) : null}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>Evidence</span>
                    {s.evidence && s.evidence.length ? s.evidence.map(eid => {
                      const e = DMA.getEvidence(eid);
                      // Fail closed: an id that does not resolve is not dressed as
                      // a T3 citation and does not open an empty drawer.
                      return e ? (
                        <button key={eid} className={`tier-chip tier-${e.tier}`} style={{ cursor: "pointer", border: 0 }}
                          title={`${e.title} · ${e.source_pretty || ""}`}
                          onClick={() => { openEvidence(eid); }}>{eid}</button>
                      ) : (
                        <span key={eid} className="chip muted" title="cited id - not in this run's served evidence">{eid}</span>
                      );
                    }) : <span style={{ fontSize: 11, color: "var(--z-muted)" }}>this signal cites none</span>}
                    <span style={{ flex: 1 }} />
                  </div>
                  {/* The window is a SENTENCE in the contract ("the opening runs
                      from announcement to…"), not a chip. It was rendered as a
                      coloured badge, which truncated it to an unreadable strip. */}
                  {dwText(s.window) ? (
                    <div style={{ fontSize: 11, color: "var(--z-body)", marginTop: 8, lineHeight: 1.5 }}>
                      <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase" }}>Window · </span>
                      {dwText(s.window)}
                    </div>
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

/* ── Intelligence Panel content ─────────────────────────────────────
   The panel is a prototype-mode simulation of a chat assistant: canned
   starters, canned answers, canned surface bodies. In LIVE it cannot be any
   of that, for two separate reasons:

     · the app performs NO inference at request time (invariant 1), so there
       is no one to answer a typed question, and
     · the canned prose names the fixture bank's platforms, peers and
       evidence ids, which is fabricated content about a real institution.
       It is globally mounted, so it leaked onto all eight pages.

   In LIVE the panel therefore shows only what the run promoted — the
   surface's own synthesis, the producer's conversation starters, and the
   grounded answer path below. Anything the run did not promote is stated as
   absent, never filled in. */
const IP_LIVE = () => typeof window !== "undefined" && !!window.DMA_LIVE;

/* ═══ The grounded answer path ══════════════════════════════════════════
   `ask()` used to open with `if (IP_LIVE()) return;`. For a real client the
   question box therefore accepted input and did nothing — the one control in
   the application that lied about being a control.

   The reason it did nothing was correct and is unchanged: the serving path
   runs no model, because no prose may be invented while a client is looking
   at the page. But that rule forbids WRITING a sentence, not FINDING one. So
   the panel now does the two things that invent nothing:

     LOOKUP     the questions an AE asks are knowable in advance — this file
                has enumerated them per surface since the prototype. Each is
                resolved to prose the run already promoted, with the citations
                that prose already carries.
     RETRIEVAL  anything else is answered by ranking the run's own passages
                and showing the best of them VERBATIM, under a frame that says
                that is what they are.

   Both run against `window.DMA_ENTITY` — the payload the six page fetches
   already put in this browser — so an answer costs no request and no wait.
   That is the whole point: an AE mid-call cannot spend three hours on a
   synthesis round trip, and cannot spend eight seconds either.

   Nothing here shortens, joins, paraphrases or fills. An answer is a list of
   PARTS, each keeping the field it came from and its own citations, rendered
   as separate blocks — because two promoted paragraphs shown one after
   another are two quotations, and the same two concatenated are a sentence
   nobody wrote.

   The rules below (what counts as a passage, how a passage is ranked) are
   the same rules `apps/api/dma_api/answers.py` applies server-side, so the
   answer does not change with which tier served it. `apps/api/tests/
   test_answers.py` asserts the two copies of the QUESTION registry agree;
   the thresholds are stated in both files and named identically. */

const IP_PROSE_MIN_CHARS = 40;
const IP_PROSE_MIN_WORDS = 6;

// Key names that never hold prose whatever their length.
const IP_SKIP_KEY = /(^|_)(id|ids|at|on|url|uri|slug|hex|colou?r|version|path|date|kind|type|code|status|band|tier|class|label)$/;

// The producer's own working record — the reasoning behind a ranked claim,
// the search trail behind an absence. Load-bearing for audit, and not what
// anybody asked; unfiltered it outnumbers the prose that is.
const IP_SKIP_SEGMENTS = new Set(["r_layer", "probes_run", "sources_searched",
                                  "queries_run", "empty_state", "internal_only",
                                  "redacted_paths", "annotation"]);

const IP_CITE_KEYS = ["e_ids", "supporting_e_ids", "evidence_ids", "evidence"];

// What a passage is ABOUT, when the object says so. `id` is last and matters:
// the live adapter renames `fa_id`/`ic_id`/`rec_id` to `id`, so without it a
// focus-area question could not be scoped to the focus area that is open.
const IP_ANCHOR_KEYS = [["subcap_id", "subcap"], ["cell_id", "subcap"],
                        ["ic_id", "insight"], ["rec_id", "recommendation"],
                        ["fa_id", "focus_area"], ["ts_id", "techstack"],
                        ["e_id", "evidence"], ["wn_id", "why_now"],
                        ["id", "item"]];

const IP_E_ID = /^E-[A-Za-z0-9][A-Za-z0-9-]*$/;

function ipIsProse(v) {
  if (typeof v !== "string") return false;
  const t = v.trim();
  return t.length >= IP_PROSE_MIN_CHARS && t.split(/\s+/).length >= IP_PROSE_MIN_WORDS;
}

/* An object's own citations, or the ones it inherits, and WHICH of the two.
   The distinction is not pedantry: a section-level `e_ids` can carry every
   dated item in the run, and a paragraph that inherits fifty-nine chips is
   claiming a grounding it does not have. The reader is told the difference. */
function ipCitations(node, inherited) {
  for (const key of IP_CITE_KEYS) {
    const found = node[key];
    if (Array.isArray(found) && found.length
        && found.every(x => typeof x === "string" && IP_E_ID.test(x))) {
      return [found.slice(), "item"];
    }
  }
  return inherited;
}

function ipAnchor(node, inherited) {
  for (const [key, kind] of IP_ANCHOR_KEYS) {
    const v = node[key];
    if (typeof v === "string" && v) return [kind, v];
  }
  return inherited;
}

/* Every prose string in the adapted entity, with the path it lives at, the
   citations of the row it came from and what it is about.

   Generic rather than a curated field list: a curated list goes stale the
   moment a section gains a field, and the sections this reads are adapted by
   a module this file does not own. A property of the string cannot go stale. */
function ipWalkPassages(root) {
  const out = [];
  const seen = new Set();
  const walk = (node, path, cites, anchor) => {
    if (node === null || node === undefined) return;
    if (Array.isArray(node)) {
      for (let i = 0; i < node.length; i++) walk(node[i], `${path}[${i}]`, cites, anchor);
      return;
    }
    if (typeof node === "object") {
      // Cycles are not expected in a JSON payload, but DMA_ENTITY is a live
      // object graph and this walker is mounted globally: one cycle would
      // hang the whole application, not just the panel.
      if (seen.has(node)) return;
      seen.add(node);
      const nextCites = ipCitations(node, cites);
      const nextAnchor = ipAnchor(node, anchor);
      for (const key of Object.keys(node)) {
        if (IP_SKIP_SEGMENTS.has(key)) continue;
        walk(node[key], path ? `${path}.${key}` : key, nextCites, nextAnchor);
      }
      return;
    }
    if (!ipIsProse(node)) return;
    const leaf = path.split(".").pop().split("[")[0];
    if (IP_SKIP_KEY.test(leaf)) return;
    const [ids, scope] = cites;
    const [anchorKind, anchorId] = anchor || [null, null];
    out.push({
      json_path: path, text: node.trim(),
      e_ids: (ids || []).slice(), cite_scope: (ids && ids.length) ? scope : null,
      anchor_kind: anchorKind, anchor_id: anchorId,
    });
  };
  walk(root, "", [[], "section"], null);
  return out;
}

/* The corpus, memoised on the ENTITY OBJECT, not on its id: useLiveEntity
   replaces window.DMA_ENTITY when the client, run or audience changes, and a
   cache keyed on the id would answer the new run from the old one's prose. */
let IP_CORPUS = { src: null, list: [] };
function ipPassages() {
  const ent = (typeof window !== "undefined" && window.DMA_ENTITY) || null;
  if (!ent) return [];
  if (IP_CORPUS.src !== ent) IP_CORPUS = { src: ent, list: ipWalkPassages(ent) };
  return IP_CORPUS.list;
}

/* ── Ranking ────────────────────────────────────────────────────────────
   Coverage: the share of the question's content terms a passage contains,
   both sides stemmed so "closes" answers "close". Ties break on the
   passage's own density, then on payload order. Nothing here changes between
   two identical queries, and nothing here is learned. */
const IP_STOPWORDS = new Set(("a an and are as at be been but by can could did do does doing "
  + "for from get give had has have how in into is it its me my not of on or our should so "
  + "tell than that the their them then there these they this to us was we were what when "
  + "where which who whom why will with would you your show about many much most any all "
  + "more less need want").split(" "));

function ipStem(w) {
  const rules = [["ies", "y"], ["ing", ""], ["ed", ""], ["es", ""], ["s", ""]];
  for (const [suffix, replacement] of rules) {
    if (w.endsWith(suffix) && w.length - suffix.length >= 4) {
      return w.slice(0, w.length - suffix.length) + replacement;
    }
  }
  return w;
}

function ipWords(s) { return String(s || "").toLowerCase().match(/[a-z0-9][a-z0-9'’-]*/g) || []; }

function ipTerms(q) {
  const out = [], seen = new Set();
  for (const w of ipWords(q)) {
    if (w.length < 3 || IP_STOPWORDS.has(w)) continue;
    const s = ipStem(w);
    if (seen.has(s)) continue;
    seen.add(s);
    out.push(s);
  }
  return out;
}

function ipPassageTerms(p) {
  if (!p._terms) {
    const set = new Set();
    for (const w of ipWords(p.text)) {
      if (w.length < 3 || IP_STOPWORDS.has(w)) continue;
      set.add(ipStem(w));
    }
    p._terms = set;
  }
  return p._terms;
}

// Coverage alone is not enough on a short question: two content words, one
// matched, is 0.5 — and "what is their dividend policy" would come back with
// every passage that says "policy". A passage must clear the share AND carry
// two of the question's terms wherever the question has two to give.
const IP_MATCH_FLOOR = 0.6;
const IP_MIN_TERMS_MATCHED = 2;

function ipRank(question, passages, limit) {
  const terms = ipTerms(question);
  if (!terms.length) return [];
  const need = Math.min(IP_MIN_TERMS_MATCHED, terms.length);
  const scored = [];
  for (let i = 0; i < passages.length; i++) {
    const p = passages[i];
    const words = ipPassageTerms(p);
    if (!words.size) continue;
    let hit = 0;
    for (const t of terms) if (words.has(t)) hit++;
    if (hit < need) continue;
    const score = hit / terms.length;
    if (score < IP_MATCH_FLOOR) continue;
    scored.push({ score, density: hit / words.size, i, p });
  }
  scored.sort((a, b) => (b.score - a.score) || (b.density - a.density) || (a.i - b.i));
  return scored.slice(0, limit || 5).map(s => ({
    ...s.p, score: Math.round(s.score * 10000) / 10000,
  }));
}

/* ── The anticipated questions ──────────────────────────────────────────
   The canonical list is `QUESTIONS` in apps/api/dma_api/answers.py; this is
   the panel's copy, and a test fails if the two ask different things. The
   `paths` differ deliberately and cannot be shared: the API resolves against
   the raw promoted sections, the panel against the adapted entity, and the
   adapter renames fields on the way through (`verbatim_quote` becomes
   `strategic_quote`, `why_this_sequence` becomes `play`). Where the adapter
   DROPS a field the API can read — `why_now.synthesis` is the one that bites
   — the panel names the next-best promoted field rather than going silent.

   `scope` narrows an answer to what the reader has open. "What does the run
   state about this cell?" answered with a different cell's synthesis is not a
   weaker answer, it is a wrong one, so a scoped question that resolves to
   nothing for the open cell is an absence. */
const IP_QUESTIONS = [
  { q_id: "Q-ENT-01", surface: "entity", rank: 1,
    question: "What is the 30-second version of this assessment?",
    paths: ["exec_summary.situation", "exec_summary.complication",
            "exec_summary.answer"] },
  { q_id: "Q-ENT-02", surface: "entity", rank: 2,
    question: "What does the run say the overall posture is, and on what basis?",
    paths: ["framing", "posture_basis", "narrative_thread"] },
  { q_id: "Q-ENT-03", surface: "entity", rank: 3,
    question: "What does this cost if nothing changes?",
    paths: ["exec_summary.cost_of_delay", "recommendations[].cost_of_inaction"] },
  { q_id: "Q-ENT-04", surface: "entity", rank: 4,
    question: "What are the top findings this run stands behind?",
    paths: ["findings.findings[].body", "findings.findings[].strategic_alignment"] },
  { q_id: "Q-ENT-05", surface: "entity", rank: 5,
    question: "Where is the largest opportunity, and why there?",
    paths: ["opportunity.tiles[].rank_rationale",
            "opportunity.tiles[].their_stack_context",
            "insightCards[].so_what"] },

  { q_id: "Q-WN-01", surface: "why_now", rank: 1,
    question: "What changed recently, and what closes the window?",
    paths: ["whyNow[].detail"] },
  { q_id: "Q-WN-02", surface: "why_now", rank: 2,
    question: "Why does the sequence have to start now?",
    paths: ["whyNow[].play", "whyNow[].risk"] },
  { q_id: "Q-WN-03", surface: "why_now", rank: 3,
    question: "What happens to this account without intervention?",
    paths: ["exec_summary.cost_of_delay", "roadmapBasis"] },

  { q_id: "Q-PS-01", surface: "platform_story", rank: 1,
    question: "What is the case for this platform?",
    paths: ["platformStory.platforms[].story_md"] },
  { q_id: "Q-PS-02", surface: "platform_story", rank: 2,
    question: "What gaps does it close, and against which peers?",
    paths: ["platformStory.platforms[].gaps[].peer_note",
            "recommendations[].root_cause_text"] },
  { q_id: "Q-PS-03", surface: "platform_story", rank: 3,
    question: "What has to be true before this lands?",
    paths: ["recommendations[].prerequisites[].condition",
            "recommendations[].sequencing_reason"] },

  { q_id: "Q-FA-01", surface: "focus_area", rank: 1,
    question: "Why is this a focus area?",
    scope: "focus_area",
    paths: ["focusAreas[].strategic_quote", "focusAreas[].description"] },
  { q_id: "Q-FA-02", surface: "focus_area", rank: 2,
    question: "Which capabilities sit under it, and what is holding them down?",
    paths: ["uncertainty.*.limiting_absence", "uncertainty.*.rationale"] },

  { q_id: "Q-SC-01", surface: "subcap_narrative", rank: 1,
    question: "What does the run state about this cell?",
    scope: "subcap",
    paths: ["cellEvidence[].synthesis"] },
  { q_id: "Q-SC-02", surface: "subcap_narrative", rank: 2,
    question: "What pulled this score down?",
    paths: ["uncertainty.*.limiting_absence", "alerts[].justification"] },
];

/* A declared path to a matcher over real walked paths. `[]` stands for any
   list index, `*` for any object-map key (the ceilings map is keyed by
   category id). Anchored at both ends: a prefix match would let
   `recommendations[].root_cause_text` also collect a nested field of the
   same name three levels down. */
const IP_PATH_RE = {};
function ipPathMatcher(path) {
  if (!IP_PATH_RE[path]) {
    // Built character by character rather than by chained replaces. A
    // two-pass escape needs a sentinel to hold the wildcard's place, and a
    // sentinel in a source file is a promise that the sentinel can never
    // occur in the input - which is a promise about future inputs nobody
    // can keep.
    let body = "";
    for (let i = 0; i < path.length; i++) {
      const ch = path[i];
      if (ch === "*") { body += "[^.\\[\\]]+"; continue; }
      if (ch === "[" && path[i + 1] === "]") { body += "\\[\\d+\\]"; i += 1; continue; }
      body += /[A-Za-z0-9_]/.test(ch) ? ch : `\\${ch}`;
    }
    IP_PATH_RE[path] = new RegExp(`^${body}$`);
  }
  return IP_PATH_RE[path];
}

function ipScopeId(scope, ctx) {
  if (scope === "subcap") return dwText(ctx?.subcap?.id);
  if (scope === "focus_area") return dwText(ctx?.focusArea?.id);
  return null;
}

/* One question, resolved to ordered parts of promoted prose. Returns null
   when the run promoted nothing that answers it — the caller says so rather
   than filling the space. */
const IP_MAX_PARTS = 3;
function ipResolveQuestion(qDef, ctx) {
  const corpus = ipPassages();
  if (!corpus.length) return null;
  const scopeId = qDef.scope ? ipScopeId(qDef.scope, ctx) : null;
  // A scoped question with nothing open is unscoped; a scoped question WITH
  // something open answers only about that thing.
  const inScope = (p) => !qDef.scope || !scopeId || p.anchor_id === scopeId;
  const parts = [];
  const seen = new Set();
  for (const path of qDef.paths) {
    const re = ipPathMatcher(path);
    for (const p of corpus) {
      if (!re.test(p.json_path) || !inScope(p) || seen.has(p.text)) continue;
      seen.add(p.text);
      parts.push(p);
      if (parts.length >= IP_MAX_PARTS) return parts;
    }
  }
  return parts.length ? parts : null;
}

/* The producer's own answers, once the connector writes them and the live
   adapter carries them through (see the report — `answers:` is one line in
   buildLiveEntity). Absent today, and absent reads as "fall back to
   selection" rather than as an error. */
function ipPromotedAnswers(surface) {
  const ent = (typeof window !== "undefined" && window.DMA_ENTITY) || null;
  const rows = (ent && Array.isArray(ent.answers)) ? ent.answers : [];
  return rows.filter(a => a && (!surface || a.surface === surface));
}

/* Which questions this run can actually answer on this surface. A starter
   the panel cannot answer is not shown — a question offered and then met
   with "nothing promoted" is the same broken control in a politer voice. */
function ipAnswerable(surface, ctx) {
  const key = IP_QUESTIONS.some(q => q.surface === surface) ? surface : "entity";
  const promoted = ipPromotedAnswers(key);
  const out = [];
  for (const a of promoted) {
    if (dwText(a.answer_md)) {
      out.push({ q_id: a.q_id || a.question, question: dwText(a.question),
                 provenance: "promoted",
                 parts: [{ text: dwText(a.answer_md), json_path: a.source_path || null,
                           e_ids: Array.isArray(a.e_ids) ? a.e_ids : [],
                           cite_scope: "item" }] });
    }
  }
  const answered = new Set(out.map(a => a.q_id));
  for (const q of IP_QUESTIONS) {
    if (q.surface !== key || answered.has(q.q_id)) continue;
    const parts = ipResolveQuestion(q, ctx);
    if (parts) out.push({ q_id: q.q_id, question: q.question,
                          provenance: "selected", parts });
  }
  return out;
}

/* One asked question → one of three shapes, deliberately different so the
   panel cannot render one as another. */
function ipResolve(question, surface, ctx) {
  const asked = String(question || "").trim().toLowerCase();
  for (const a of ipAnswerable(surface, ctx)) {
    if (dwText(a.question) && a.question.trim().toLowerCase() === asked) {
      return { kind: "answer", question, ...a };
    }
  }
  const hits = ipRank(question, ipPassages(), 4);
  if (hits.length) {
    return { kind: "passages", question,
             frame: "Here is what this run states about that", parts: hits };
  }
  return { kind: "none", question };
}

/* Where a passage lives, said the way a reader would say it. The path is the
   adapter's key, which is an implementation detail; the caption is not. */
const IP_WHERE = {
  exec_summary: "Executive summary", framing: "Overall scores",
  posture_basis: "Overall scores", narrative_thread: "Page narrative",
  findings: "Top findings", opportunity: "Opportunity",
  insightCards: "Insight cards", whyNow: "Why-now signals",
  platformStory: "Platform story", recommendations: "Recommendations",
  focusAreas: "Focus areas", uncertainty: "Category ceilings",
  cellEvidence: "Cell evidence", alerts: "Thin-evidence alerts",
  roadmapBasis: "Roadmap sequencing", techStack: "Technology register",
  timeline: "Timeline", issues: "Issue register", evidence: "Evidence store",
  stairstep: "Maturity ladder", landscape: "Landscape",
  regulatory: "Regulatory standing", acquisitions: "Acquisitions",
  starters: "Conversation starters", scores: "Scores",
  leadership: "Leadership", thoughtLeadership: "Thought leadership",
  valueChain: "Value chain", contextSentiment: "Context sentiment",
};
function ipWhere(path) {
  if (!path) return null;
  const segs = String(path).split(".");
  const head = segs[0].split("[")[0];
  const label = IP_WHERE[head]
    || head.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/_/g, " ").toLowerCase()
           .replace(/^./, c => c.toUpperCase());
  const leaf = segs.length > 1
    ? segs[segs.length - 1].split("[")[0].replace(/_/g, " ")
    : null;
  return leaf && leaf !== head ? `${label} · ${leaf}` : label;
}

function liveStarters(ctx) {
  const id = ctx?.entity?.id;
  if (!id) return [];
  // The producer's D4 conversation starters: talking points, not questions
  // this app could answer. Rendered read-only in LIVE.
  return (DMA.startersFor(id) || [])
    .map(s => (typeof s === "string" ? s : (s && (s.question || s.text || s.starter))))
    .filter(Boolean);
}

function liveSurfaceMessages(surface, ctx) {
  const ent = ctx?.entity?.name || "this entity";
  const id = ctx?.entity?.id;
  /* An absence, said once.

     This used to add two clauses of architecture to every empty panel —
     that nothing is filled in, that the panel reads promoted synthesis
     only, that the application runs no model at request time. All true,
     none of it the reader's problem, and repeated on every surface it fires
     on. Why the panel is empty is a property of the run; how this product
     is built is not an answer to it. */
  const absent = (what) => `${what} did not promote for this run.`;

  if (surface === "why_now") {
    // `DMA.whyNowFor` returns the ADAPTED ARRAY of signals, not the section, so
    // `wn.signals` was always undefined and the panel reported that the why-now
    // synthesis "did not promote" over four promoted trigger signals. The
    // section's own `narrative_thread` is dropped by the adapter and is
    // unreachable from here (see ADAPTER CHANGES in the report), so the body
    // states what the signals ARE rather than inventing a thread.
    const wn = id ? DMA.whyNowFor(id) : null;
    const signals = Array.isArray(wn) ? wn : ((wn && wn.signals) || []);
    // Wired for the adapter change requested in the report: when
    // `whyNowMetaFor` exists it carries the section's own narrative_thread.
    // Until it lands this is undefined and the body falls through to the
    // signals, which is the honest reading of what is reachable today.
    const meta = (typeof DMA.whyNowMetaFor === "function" && id)
      ? DMA.whyNowMetaFor(id) : null;
    const authored = dwText(meta && (meta.narrative_thread || meta.synthesis))
      || (!Array.isArray(wn) && wn ? dwText(wn.synthesis || wn.narrative) : null);
    return {
      title: "Why now",
      sub: signals.length
        ? `${signals.length} trigger signal${signals.length === 1 ? "" : "s"}`
        : "Trigger signals",
      cache_age: "promoted",
      body: authored || (signals.length
        ? `${signals.length} trigger signal${signals.length === 1 ? "" : "s"} promoted for ${ent}` +
          `${signals.map(s => dwText(s.category)).filter(Boolean).length
              ? ` — ${[...new Set(signals.map(s => dwText(s.category)).filter(Boolean))].join(" · ")}` : ""}. ` +
          `The run promotes no separate why-now narrative; expand a signal below for its ` +
          `claim, its dated evidence and the sequence the producer argues for.`
        : absent("The why-now synthesis")),
    };
  }
  if (surface === "subcap_narrative") {
    // `cell_evidence` states `synthesis` (null on 59 of this run's 69 cells) plus
    // the citation list and the server-computed `grounded_on`. When there is no
    // synthesis the panel says which cell, and what the run DOES hold for it,
    // instead of a flat "did not promote".
    const sc = ctx?.subcap || {};
    const cell = (DMA.cellEvidenceFor(sc.id) || null);
    const synth = dwText(cell && cell.synthesis);
    const cited = (cell && cell.e_ids) || [];
    const grounded = dwNum(cell && cell.grounded_on);
    return {
      title: "Cell synthesis", sub: sc.id || "Heatmap selection",
      cache_age: "promoted",
      body: synth || (cell
        ? `No cell synthesis promoted for ${sc.id || "this cell"}. The run grounds it on ` +
          `${grounded === null ? cited.length : grounded} evidence item` +
          `${(grounded === null ? cited.length : grounded) === 1 ? "" : "s"}` +
          `${cited.length ? ` (${cited.slice(0, 6).join(", ")}${cited.length > 6 ? ", …" : ""})` : ""} — ` +
          `open the cell's evidence drawer for the excerpts.`
        : absent(`A synthesis for ${sc.id || "this cell"}`)),
    };
  }
  if (surface === "platform_story") {
    /* The promoted platform story: `platforms[]`, each with a ~130-word
       `story_md` and its own gap rows, plus `discarded[]`.

       This read `ps.narrative || ps.story || ps.synthesis` — three keys the
       contract does not carry — so the panel declared that the story "did not
       promote" while the payload held all of it. The subtitle read
       `ps.platform`, also absent, and fell through to the context value.

       A promoted platform is NOT named: the contract gives it no name field, and
       the opportunity tiles that do carry a vendor name carry no L3 area, so the
       two cannot be joined without guessing. The story is therefore filed — here
       and on the page — under the L3 area its OWN GAP ROWS name, and that area
       is what the subtitle states. */
    const ps = DMA.platformStoryFor(id);
    const plats = ((ps && ps.platforms) || []).filter(p => p && typeof p === "object");
    const discarded = ((ps && ps.discarded) || []).filter(p => p && typeof p === "object");
    const area = dwText(ctx?.platform);
    const areasOf = (p) => [...new Set((p.gaps || []).map(g => dwText(g.l3_area)).filter(Boolean))];
    const named = [...new Set(plats.flatMap(areasOf))];
    const scoped = area ? plats.filter(p => areasOf(p).includes(area)) : [];
    const use = scoped.length ? scoped : plats;
    const stories = use.map(p => dwText(p.story_md)).filter(Boolean);
    /* The body is the STORY. Nothing else.

       It used to open with a paragraph of the app's own plumbing — "No
       promoted platform story names MuleSoft Anypoint Platform. The run
       files its story under Integration & API Management, shown below." —
       followed, when prose was missing, by a sentence counting the gap rows
       and set-aside platforms and pointing out that they are below. An AE
       opens this panel to read an argument they can take into a room. How
       the payload files its sections is not that argument, and the counts
       narrate structure the reader can already see rendered beneath.

       Where the story is filed remains visible, because it is genuinely
       useful — it is the SUBTITLE, one line, where a caption belongs. */
    const body = stories.join("\n\n");
    return {
      title: "Platform story",
      // The subtitle names an area the STORY names, not whatever the caller put
      // in context — a vendor alias there ("SF") would otherwise be printed as
      // the subject of a story that never mentions a vendor.
      sub: (area && (scoped.length || !named.length))
        ? area
        : (named.join(" · ") || area || "Promoted narrative"),
      cache_age: "promoted",
      body: body || absent("The platform story"),
      // Rendered structurally under the prose: gap rows carry a cell id, a score,
      // a peer basis, a catalogue path and evidence ids, none of which survives
      // being flattened into a sentence.
      detail: (use.length || discarded.length)
        ? { kind: "platform_story", platforms: use, discarded, area }
        : null,
    };
  }
  if (surface === "focus_area") {
    /* A focus area has no `synthesis`, `rationale` or `quote` field — the three
       keys this read — so the panel always said a synthesis did not promote. The
       H1 contract states a verbatim quote, a currency note and the entity/peer
       scores with a PROMOTED delta, and that is what the area actually says. */
    const fa = ctx?.focusArea || {};
    const band = dwBand(fa.entity_score);
    const peer = dwNum(fa.peer_score);
    const delta = dwNum(fa.delta);
    const parts = [
      dwText(fa.strategic_quote),
      dwText(fa.description),
      band ? `Composite ${fx(band.score, 2)} · ${band.label}` +
             (peer === null ? "" : ` · peer ${fx(peer, 2)}`) +
             (delta === null ? "" : ` · delta ${delta > 0 ? "+" : ""}${fx(delta, 2)} as promoted`) +
             (dwText(fa.currency_status) ? ` · ${dwText(fa.currency_status).replace(/_/g, " ").toLowerCase()}` : "")
           : null,
      (fa.subcaps || []).length
        ? `${fa.subcaps.length} capability cell${fa.subcaps.length === 1 ? "" : "s"} sit under this area.`
        : null,
    ].filter(Boolean);
    return {
      title: "Focus area", sub: dwText(fa.name) || "Strategic priority",
      cache_age: "promoted",
      body: parts.length
        ? `The run promotes no separate narrative for a focus area. What it does state:\n\n${parts.join("\n\n")}`
        : absent("A synthesis for this focus area"),
    };
  }
  return {
    title: "Intelligence", sub: "Promoted synthesis",
    cache_age: "promoted",
    body: "Select a cell, platform or focus area to read the synthesis the run " +
          "promoted for it. Nothing here is generated on demand.",
  };
}

function starterQuestions(surface, ctx) {
  if (IP_LIVE()) return liveStarters(ctx);
  const ent = ctx?.entity?.name || "this entity";
  switch (surface) {
    case "why_now":
      return [
        "What's the single most timely platform conversation?",
        "Which evidence is strongest for the integration window?",
        `Where will ${ent} be in 9 months without intervention?`,
      ];
    case "subcap_narrative":
      return [
        "What pulled this score down?",
        "Which platforms would close the gap fastest?",
        "Show me peer benchmarks for this subcap.",
      ];
    case "platform_story":
      return [
        "What are the readiness gaps blocking this platform?",
        "Which insight cards link to this platform?",
        "Give me a 30-second pitch I can use in the next meeting.",
      ];
    case "focus_area":
      return [
        "Which subcaps move the most if we close this focus area?",
        "What's the customer impact, not the technical impact?",
        "Show me peers that closed this focus area in the last 18 months.",
      ];
    default:
      return [
        "Summarise this entity in 30 seconds.",
        "What is the most-asked question on a first call here?",
        "What's our differentiation against the incumbent?",
      ];
  }
}

function answerFor(q, surface, ctx) {
  const ent = ctx?.entity?.name || "this entity";
  const ql = q.toLowerCase();
  if (ql.includes("9 month") || ql.includes("intervention")) {
    return `Without intervention, ${ent} layers a customer-experience program (Marketing Cloud, Twilio) on top of an unresolved data fragmentation problem. P4C1 stays at 2.1, P2 scores plateau under 3.0, and the next data foundation decision (which is the highest-leverage one) is made under pressure during the nCino go-live freeze. Recommendation: open the Data Cloud conversation in the next 60 days.`;
  }
  if (ql.includes("subcap") || ql.includes("gap")) {
    return `The biggest movers in this focus area are P4C1.3.1 (Unified profile), P4C1.2.1 (Master data) and P2C3.1.1 (Onboarding flow). Closing all three lifts the focus-area composite from 2.1 to 3.4, which moves ${ent} from M2 to M3 in the Data Foundation pillar.`;
  }
  if (ql.includes("peer") || ql.includes("benchmark")) {
    return `Synovus and First Citizens both closed similar gaps in the last 18 months. Synovus deployed Data Cloud in Q3 2025 - closed onboarding gap from 2.0 to 3.3 within nine months. First Citizens deployed nCino Workflow Engine in Q1 2025 - loan cycle 11d → 4d.`;
  }
  if (ql.includes("pitch") || ql.includes("meeting") || ql.includes("30 sec")) {
    return `“You're mid-migration to nCino, you've just made two C-suite hires, and you have five Data Cloud Architect openings - but no Data Cloud. The next six months are the window to put the substrate underneath, not on top of, the new core. Salesforce Data Cloud plus Databricks delivers the unified customer profile that every channel investment from here will rely on.”`;
  }
  if (ql.includes("strongest") || ql.includes("evidence")) {
    return `T1 evidence (annual report + 10-K) confirms the migration is in flight, with explicit acknowledgement of data complexity across three production cores. T2 (Q1 earnings call) confirms the Data Cloud evaluation is real but not committed. T7 (5 Data Cloud Architect openings) is the leading signal - Zennify has seen platform commitments follow this hiring pattern within 90–120 days.`;
  }
  return `Based on the current run, ${ent} is in the foundation window - the right next conversation is data substrate, not the next channel. The integration window opens with the nCino go-live and closes when a point CDP commitment is made (typically 6 months after the first Data Cloud Architect role posts). Evidence: E-047, E-089, E-112.`;
}

function surfaceMessages(surface, ctx) {
  if (IP_LIVE()) return liveSurfaceMessages(surface, ctx);
  const ent = ctx?.entity?.name || "this entity";
  switch (surface) {
    case "why_now":
      return {
        title: "Why now",
        sub: "Triggers in the last 24 months",
        cache_age: "instant",
        body: `${ent} is mid-migration from a legacy core to nCino, with target completion Q2 2026. The P4 score reflects fragmentation across three production systems, not absence of investment.\n\nTwo new C-suite hires (CTO from Wells Fargo in April; CDO in May) create a 6–9 month policy window. Five Data Cloud Architect openings posted in Q1 are a leading signal that the team is preparing for a customer-data platform decision - without yet committing to a vendor.\n\nThe right conversation today: position Salesforce Data Cloud + Databricks Lakehouse as the substrate, before a point-solution (Snowflake-only, or vendor-bundled) creates the next decade of fragmentation.`,
      };
    case "subcap_narrative":
      return {
        title: "Subcap narrative",
        sub: ctx?.subcap?.id || "Heatmap selection",
        cache_age: "200ms",
        body: `${ctx?.subcap?.name || "This subcap"} scores ${fx(ctx?.subcap?.score, 1) || "-"}. Peer median is ${fx(ctx?.subcap?.peerMedian, 1) || "-"}.\n\nEvidence is ${ctx?.subcap?.thin ? "thin - only " + (ctx?.subcap?.evidence_count || 0) + " items below the threshold of 3" : "consistent across multiple T1–T3 sources"}.\n\nClosing the gap to peer requires investment in the named platform candidates. The exact path differs by subvertical pillar weight.`,
      };
    case "platform_story":
      return {
        title: "Platform story",
        sub: ctx?.platform || "Highest fit",
        cache_age: "cached at ingest",
        body: `Salesforce has the strongest commercial case for ${ent}. Composite Fit Score is 82/100. The platform addresses 34 subcap gaps where confidence is high and the technology footprint is confirmed-absent.\n\nLead with Data Cloud as the foundation conversation, sequence Agentforce after the P2C2 ≥ 2.0 prerequisite is met, and use Marketing Cloud + Twilio Engage to land a customer-experience story on top.\n\nThe meeting opens with the CDO hire signal; the meeting closes with the integration window before nCino go-live.`,
      };
    case "focus_area":
      return {
        title: "Focus area synthesis",
        sub: ctx?.focusArea?.name || "Strategic priority",
        cache_age: "synthesized",
        body: `${ctx?.focusArea?.name || "This focus area"} is one of ${ent}'s declared strategic priorities - the supporting quote is verbatim from the Client Profile Research Report.\n\nThe current composite maturity is below peer median; closing it requires investment across multiple subcaps that share an underlying constraint. The constraint is the same one surfaced in the related insight cards and platform fit scores.`,
      };
    default:
      return {
        title: "Intelligence",
        sub: "Gemini Flash",
        cache_age: "instant",
        body: `Select a subcap, platform, focus area, or insight card to see contextual analysis here. The panel is additive - every page works without it.`,
      };
  }
}

Object.assign(window, { EvidenceDrawer, InsightModal, IntelligencePanel, RecommendationModal, NewRunModal });

/* ── New Run modal ──────────────────────────────────────────────── */
function NewRunModal() {
  const { newRunOpen, closeNewRun, pushToast } = useApp();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({ name: "", website: "", subvertical: "REGIONAL_BANK", notes: "", files: [], passToDmaBot: true });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => { if (newRunOpen) { setStep(1); setForm({ name: "", website: "", subvertical: "REGIONAL_BANK", notes: "", files: [], passToDmaBot: true }); } }, [newRunOpen]);

  if (!newRunOpen) return null;

  const valid1 = form.name.trim().length > 1 && form.website.trim().length > 3;
  const onFile = (e) => {
    const fs = Array.from(e.target.files || []);
    setForm(f => ({ ...f, files: [...f.files, ...fs.map(file => ({ name: file.name, size: file.size }))] }));
  };
  const removeFile = (i) => setForm(f => ({ ...f, files: f.files.filter((_, x) => x !== i) }));

  const submit = () => {
    setSubmitting(true);
    setTimeout(() => {
      setSubmitting(false);
      pushToast(`Payload passed to DMA bot for ${form.name} - first batch in ~3 min`, "success");
      closeNewRun();
    }, 1200);
  };

  return (
    <div className="modal-mask" onClick={closeNewRun}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 640 }}>
        <div className="modal-head">
          <div style={{ flex: 1 }}>
            <div className="eyebrow" style={{ marginBottom: 4 }}>Trigger new assessment</div>
            <div style={{ fontSize: 17, fontWeight: 600, color: "var(--z-dark)" }}>{step === 1 ? "Entity details" : step === 2 ? "Context & files" : "Confirm"}</div>
          </div>
          <div className="row" style={{ gap: 6, marginRight: 8 }}>
            {[1,2,3].map(n => (
              <div key={n} style={{ width: 22, height: 22, borderRadius: 11, fontSize: 11, fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", background: step >= n ? "var(--z-teal)" : "var(--z-sep)", color: step >= n ? "#fff" : "var(--z-muted)" }}>{n}</div>
            ))}
          </div>
          <button className="icon-btn" onClick={closeNewRun}><Icon name="x" size={18} /></button>
        </div>
        <div className="modal-body">
          {step === 1 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="field-group">
                <label className="inp-label">Client name <span style={{ color: "var(--z-below)" }}>*</span></label>
                <input className="inp" placeholder="e.g. Provident Bank" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
              </div>
              <div className="field-group">
                <label className="inp-label">Website <span style={{ color: "var(--z-below)" }}>*</span></label>
                <input className="inp" placeholder="https://provident.com" value={form.website} onChange={e => setForm(f => ({ ...f, website: e.target.value }))} />
                <div className="inp-help">Used as the primary entity match for Explorium technographic sync.</div>
              </div>
              <div className="field-group">
                <label className="inp-label">Subvertical</label>
                <select className="inp" value={form.subvertical} onChange={e => setForm(f => ({ ...f, subvertical: e.target.value }))}>
                  {Object.entries(DMA.SUBVERTICAL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
            </div>
          ) : step === 2 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="field-group">
                <label className="inp-label">Additional context (optional)</label>
                <textarea className="inp" rows={5} placeholder="Anything the DMA bot should know - recent news, pending discovery items, prior conversations..." value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} style={{ resize: "vertical" }} />
              </div>
              <div className="field-group">
                <label className="inp-label">Supporting files (optional)</label>
                <label style={{ display: "block", padding: "20px 14px", border: "2px dashed var(--z-sep)", borderRadius: 8, textAlign: "center", cursor: "pointer", background: "var(--z-bg)" }}>
                  <Icon name="download" size={18} />
                  <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--z-dark)", marginTop: 6 }}>Drop files or click to browse</div>
                  <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 3 }}>10-K · annual reports · prior assessment artifacts · max 50MB each</div>
                  <input type="file" multiple onChange={onFile} style={{ display: "none" }} />
                </label>
                {form.files.length > 0 ? (
                  <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
                    {form.files.map((file, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: "var(--z-lav)", borderRadius: 6 }}>
                        <Icon name="doc" size={13} />
                        <span style={{ fontSize: 12, flex: 1, minWidth: 0 }} className="txt-trunc">{file.name}</span>
                        <span style={{ fontSize: 10, color: "var(--z-muted)" }}>{fx((file.size / 1024), 0)} KB</span>
                        <button className="icon-btn" style={{ width: 22, height: 22 }} onClick={() => removeFile(i)}><Icon name="x" size={11} /></button>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
              <label className="row" style={{ fontSize: 12, padding: "10px 12px", background: "var(--z-ice)", borderRadius: 6, cursor: "pointer" }}>
                <span className={`switch ${form.passToDmaBot ? "on" : ""}`} onClick={() => setForm(f => ({ ...f, passToDmaBot: !f.passToDmaBot }))} />
                <span>Pass payload to DMA bot site for ingestion</span>
              </label>
            </div>
          ) : (
            <div>
              <div className="card-tile" style={{ padding: 14, marginBottom: 12, background: "var(--z-ice)" }}>
                <div className="row" style={{ marginBottom: 8 }}>
                  <Icon name="check" size={15} style={{ color: "var(--z-mid)" }} />
                  <strong style={{ fontSize: 13 }}>Ready to submit</strong>
                </div>
                <Row k="Client name" v={form.name} />
                <Row k="Website"     v={form.website} />
                <Row k="Subvertical" v={DMA.SUBVERTICAL_LABEL[form.subvertical]} />
                <Row k="Files"       v={form.files.length === 0 ? "-" : `${form.files.length} attached`} />
                <Row k="Pass to DMA bot" v={form.passToDmaBot ? "Yes" : "No (manual queue)"} />
                {form.notes ? <><div className="sep" /><div style={{ fontSize: 11, color: "var(--z-muted)", marginBottom: 4 }}>Notes</div><div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.5 }}>{form.notes}</div></> : null}
              </div>
              <div style={{ fontSize: 12, color: "var(--z-muted)", lineHeight: 1.55 }}>
                On submit, the payload is sent to the DMA bot site. The bot will: (1) crawl public sources, (2) classify evidence into tiers, (3) score each subcap, (4) generate insight cards, (5) post results back to this app. First batch is typically available within 3 minutes.
              </div>
            </div>
          )}
        </div>
        <div className="modal-foot">
          {step > 1 ? <button className="btn btn-tertiary" onClick={() => setStep(s => s - 1)}><Icon name="chevron-l" size={12} /> Back</button> : <span />}
          {step < 3 ? (
            <button className="btn btn-primary" disabled={step === 1 && !valid1} onClick={() => setStep(s => s + 1)}>Continue <Icon name="arrow-r" size={12} /></button>
          ) : (
            <button className="btn btn-primary" disabled={submitting} onClick={submit}>{submitting ? "Submitting…" : <><Icon name="play" size={12} /> Start assessment</>}</button>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 12 }}>
      <span style={{ color: "var(--z-muted)" }}>{k}</span>
      <span style={{ color: "var(--z-dark)", fontWeight: 500 }}>{v}</span>
    </div>
  );
}

/* ── Recommendation modal ───────────────────────────────────────── */
function RecommendationModal() {
  const { recModal, closeRec, openEvidence, openSubcap, audience, pushToast } = useApp();
  const [view, setView] = useState("rationale"); // rationale | impact | evidence | dependencies
  const [note, setNote] = useState("");
  useEffect(() => { if (recModal) setView("rationale"); }, [recModal]);
  useEffect(() => { if (recModal) { try { setNote(localStorage.getItem("dma_rec_note_" + recModal) || ""); } catch (e) { setNote(""); } } }, [recModal]);
  const saveNote = (v) => { setNote(v); try { localStorage.setItem("dma_rec_note_" + recModal, v); } catch (e) {} };
  if (!recModal) return null;
  const r = DMA.getRecommendation(recModal);
  if (!r) return null;
  // `r.platform` is a fixture-only key: a promoted recommendation states
  // `l3_area` and `l4_feature`, never a vendor id, so this lookup into the
  // static five-vendor catalogue was undefined on every live row. The heading
  // now prints the run's own L3 area and L4 feature.
  const plat = DMA.getPlatform(r.platform);
  const area = dwText(r.l3) || (plat && plat.name) || null;
  const feature = dwText(r.l4) || dwText(r.feature) || null;
  const impact = DMA.ROADMAP_IMPACTS[r.id];
  // The promoted per-cell impact table (`dma_impact`): current, target, delta
  // and the basis for the target. This is the run's own uplift statement, which
  // is why the DMA-impact tab no longer depends on ROADMAP_IMPACTS — a fixture
  // map that is empty in LIVE, leaving three headings over three empty boxes.
  const dmaImpact = (r.dma_impact || []).filter(x => x && typeof x === "object");
  const linkedSubcaps = DMA.INSIGHT_CARDS.filter(c => c.rec === r.id).flatMap(c => c.affects || []);

  return (
    <div className="modal-mask" onClick={closeRec}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 820 }}>
        <div className="modal-head">
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
              <span className="chip">{r.id}</span>
              {area ? <span className="b b-teal">{area}</span> : null}
              {feature ? <span className="b b-muted">{feature}</span> : null}
              {r.phase ? <span className="b b-purple">Phase {r.phase}</span> : null}
              {r.claim ? <span className="b b-muted">{r.claim}</span> : null}
              {/* `outcomes` is a fixture-only nested object. A promoted recommendation
                   states `effort_band` and `kpi_triple`, which the adapter maps to
                   r.effort and r.kpi — so reading r.outcomes.effort threw a
                   TypeError and blanked the entire app on any rec click. */}
              {/* `horizon` is the adapter's alias for `phase` on a promoted row,
                  so printing both rendered "Phase 1 … · 1". It is only shown
                  when it actually says something the phase badge does not. */}
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                {r.effort ? `Effort ${r.effort}` : (r.outcomes ? `Effort ${r.outcomes.effort} · ${r.outcomes.time}` : "effort not stated")}
                {dwText(r.horizon) && dwText(r.horizon) !== String(r.phase) ? ` · ${dwText(r.horizon)}` : ""}
              </span>
            </div>
            <div style={{ fontSize: 17, fontWeight: 600, color: "var(--z-dark)" }}>{r.title}</div>
          </div>
          <button className="icon-btn" onClick={closeRec}><Icon name="x" size={18} /></button>
        </div>

        <div style={{ display: "flex", padding: "0 22px", borderBottom: "1px solid var(--z-sep)" }}>
          {[
            ["rationale", "Rationale & notes"],
            ["impact", "DMA impact"],
            ["evidence", "Root cause evidence"],
            ["dependencies", "Sequencing"],
          ].map(([k, l]) => (
            <button key={k} className="client-tab" style={{ background: "transparent", color: view === k ? "var(--z-teal)" : "var(--z-muted)", borderBottom: view === k ? "2px solid var(--z-teal)" : "2px solid transparent" }} onClick={() => setView(k)}>
              {l}
            </button>
          ))}
        </div>

        <div className="modal-body">
          {view === "rationale" ? (
            <div>
              {/* Synthesized logic behind the recommendation */}
              <div className="card" style={{ padding: 14, marginBottom: 14 }}>
                <div className="row" style={{ marginBottom: 12 }}>
                  <Icon name="sparkle" size={14} style={{ color: "var(--z-dpur)" }} />
                  <div style={{ fontWeight: 600, fontSize: 13 }}>Why this recommendation</div>
                </div>
                {/* The producer's own reasoning, in place of four templated
                    sentences. Every one of these fields is promoted per
                    recommendation and none was read: root_cause,
                    cost_of_inaction, sequencing_reason, kpi_triple,
                    validation_gate and the whole r_layer. The template asserted
                    things no source states — "the lowest-friction path", "the
                    platform footprint is already present or adjacent", "no
                    prerequisites, this can land first" — identically for every
                    recommendation. That is the "no reasoning engaged" reading. */}
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {[
                    { n: "1", k: "Root cause", v: dwText(r.root_cause_text)
                        ? <>{dwText(r.root_cause_text)}{(r.root_cause || []).length ? <> {r.root_cause.map(eid => (
                            <button key={eid} className="chip" style={{ marginRight: 3 }} onClick={() => openEvidence(eid)}>{eid}</button>
                          ))}</> : null}</>
                        : (r.root_cause || []).length
                          ? <>Cited by {r.root_cause.length} evidence item{r.root_cause.length === 1 ? "" : "s"}: {r.root_cause.map(eid => (
                              <button key={eid} className="chip" style={{ marginRight: 3 }} onClick={() => openEvidence(eid)}>{eid}</button>
                            ))}</>
                          : <span style={{ color: "var(--z-muted)" }}>the run states no root cause for this recommendation</span> },
                    { n: "2", k: "Cost of inaction", v: dwText(r.cost_of_inaction)
                        || <span style={{ color: "var(--z-muted)" }}>not stated</span> },
                    { n: "3", k: "Sequencing", v: dwText(r.sequencing_reason)
                        ? <>{dwText(r.sequencing_reason)}{r.phase ? <> <span className="b b-muted">Phase {r.phase}</span></> : null}</>
                        : (r.phase
                            ? <>Scheduled in <strong>{r.phase}</strong>. The run states no sequencing reason.</>
                            : <span style={{ color: "var(--z-muted)" }}>not sequenced</span>) },
                    /* `kpi_triple` is an OBJECT — metric, baseline, target and
                       the date the baseline was read. It was collapsed to
                       `r.kpi.metric` with a JSON.stringify fallback, so the
                       baseline and the target (the two halves that make a KPI
                       measurable) never appeared. */
                    { n: "4", k: "Expected outcome", v: r.kpi
                      ? (typeof r.kpi === "string"
                          ? <><strong>{r.kpi}</strong>{r.effort ? <> · {r.effort} effort</> : null}</>
                          : <>
                              <strong>{dwText(r.kpi.metric) || "metric not stated"}</strong>
                              {r.effort ? <> · {r.effort} effort</> : null}
                              {dwText(r.kpi.baseline) ? (
                                <div style={{ marginTop: 3 }}>Baseline · {dwText(r.kpi.baseline)}
                                  {dwText(r.kpi.baseline_as_of) ? <span className="f-mono" style={{ color: "var(--z-muted)" }}> ({dwText(r.kpi.baseline_as_of)})</span> : null}
                                </div>) : null}
                              {dwText(r.kpi.target) ? (
                                <div style={{ marginTop: 2 }}>Target · {dwText(r.kpi.target)}</div>) : null}
                            </>)
                      : r.outcomes
                        ? <><strong>{r.outcomes.metric}</strong> · {r.outcomes.time} · {r.outcomes.effort} effort</>
                        : <span style={{ color: "var(--z-muted)" }}>the run states no KPI for this recommendation</span> },
                    /* PAGE-KILLER, fixed: `v: r.validation_gate` put the raw
                       object into JSX. A promoted gate is
                       {threshold, verdict, current_value, cell, grain_note,
                       backing_cells[]} — React throws #31 on an object child and
                       there is no error boundary above this modal, so every
                       recommendation click blanked the entire application. */
                    { n: "5", k: "Validation gate", v: r.validation_gate
                        ? (typeof r.validation_gate === "string"
                            ? r.validation_gate
                            : <ValidationGate gate={r.validation_gate} openSubcap={openSubcap} closeRec={closeRec} />)
                        : <span style={{ color: "var(--z-muted)" }}>not stated</span> },
                  ].map(row => (
                    <div key={row.n} style={{ display: "flex", gap: 10 }}>
                      <div style={{ width: 22, height: 22, borderRadius: 6, background: "var(--z-lav)", color: "var(--z-dpur)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, flexShrink: 0 }}>{row.n}</div>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 2 }}>{row.k}</div>
                        <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6 }}>{row.v}</div>
                      </div>
                    </div>
                  ))}
                </div>
                {/* The reasoning trace, internal only. */}
                {r.r_layer && audience !== "customer" ? (
                  <div style={{ background: "var(--ph0-lt)", border: "1px solid var(--ph0-bd)", borderRadius: 8, padding: "12px 14px", marginTop: 14 }}>
                    <div className="row" style={{ marginBottom: 8 }}>
                      <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase" }}>Reasoning trace</span>
                      <span className="spacer" />
                      {r.r_layer.verdict ? <span className="b b-purple">{r.r_layer.verdict}</span> : null}
                    </div>
                    {[["Hypothesis", r.r_layer.hypothesis],
                      ["Counter-evidence", r.r_layer.counter],
                      ["Domain test", r.r_layer.domain_test]].map(([k, v]) => v ? (
                      <div key={k} style={{ marginBottom: 8 }}>
                        <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 2 }}>{k}</div>
                        <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.55 }}>{v}</div>
                      </div>
                    ) : null)}
                  </div>
                ) : null}
              </div>

              {/* AE notes — persisted, flagged for future synthesis */}
              <div className="card" style={{ padding: 14 }}>
                <div className="row" style={{ marginBottom: 8 }}>
                  <Icon name="edit" size={14} style={{ color: "var(--z-mid)" }} />
                  <div style={{ fontWeight: 600, fontSize: 13 }}>AE notes</div>
                  <span className="spacer" />
                  {note ? <span className="b b-teal">saved locally</span> : null}
                </div>
                <textarea value={note} onChange={e => saveNote(e.target.value)} placeholder="Add client-specific framing, objections to handle, or discovery follow-ups for this recommendation…"
                  style={{ width: "100%", minHeight: 96, resize: "vertical", padding: 10, border: "1px solid var(--z-sep)", borderRadius: 8, fontSize: 12.5, fontFamily: "var(--font-sans)", lineHeight: 1.55, color: "var(--z-dark)", boxSizing: "border-box" }} />
                <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 6, display: "flex", gap: 6, alignItems: "flex-start" }}>
                  <Icon name="sparkle" size={11} style={{ color: "var(--z-dpur)", flexShrink: 0, marginTop: 1 }} />
                  <span>These notes may be synthesized into future runs to make recommendations dynamic and responsive.</span>
                </div>
              </div>
            </div>
          ) : view === "impact" ? (
            <>
              {/* The promoted per-cell impact table. Each row states the cell,
                  its CURRENT score, the projected TARGET, the delta and the
                  basis for that target — and the basis says in the run's own
                  words that the target is a projection, not a measurement, which
                  is why it is printed beside the bar rather than dropped.
                  Nothing here is recomputed: the delta renders as promoted. */}
              {dmaImpact.length ? (
                <div className="card" style={{ marginBottom: 14, padding: 14 }}>
                  <div className="row" style={{ marginBottom: 4 }}>
                    <Icon name="heatmap" size={14} />
                    <div style={{ fontWeight: 600, fontSize: 13 }}>Projected cell uplift · {dmaImpact.length}</div>
                    <span className="spacer" />
                    <span className="b b-org">projection</span>
                  </div>
                  <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginBottom: 12 }}>
                    current score is measured; the target is the run's projection
                  </div>
                  {dmaImpact.map((x, i) => {
                    const cur = dwNum(x.current), tgt = dwNum(x.target), d = dwNum(x.delta);
                    const curBand = dwBand(cur), tgtBand = dwBand(tgt);
                    return (
                      <div key={x.subcap_id || i} style={{ marginBottom: 12 }}>
                        <div className="row" style={{ gap: 6, marginBottom: 4, flexWrap: "wrap" }}>
                          {x.subcap_id ? (
                            <button className="chip purple" onClick={() => { closeRec(); openSubcap(x.subcap_id); }}>{x.subcap_id}</button>
                          ) : null}
                          <span style={{ fontSize: 12.5, fontWeight: 600, flex: 1, minWidth: 0 }}>{dwText(x.name) || "cell not named"}</span>
                          <span className="f-mono" style={{ fontSize: 11.5, color: "var(--z-body)" }}>
                            {cur === null ? "—" : fx(cur, 1)} → {tgt === null ? "—" : fx(tgt, 1)}
                          </span>
                          {d === null ? null : (
                            <span className="b b-teal">{d > 0 ? "+" : ""}{fx(d, 1)}</span>
                          )}
                        </div>
                        {/* Two bars on one track: the measured score solid, the
                            projected target as a dashed outline, so the reader
                            cannot mistake the projection for a score. */}
                        <div className="pbar-track" style={{ position: "relative", height: 8 }}>
                          {tgt === null ? null : (
                            <div style={{ position: "absolute", left: 0, top: 0, height: "100%", width: `${Math.min(100, tgt / 5 * 100)}%`, border: `1px dashed ${tgtBand ? tgtBand.hex : "var(--z-sep)"}`, borderRadius: 4, boxSizing: "border-box" }} />
                          )}
                          {cur === null ? null : (
                            <div style={{ position: "absolute", left: 0, top: 0, height: "100%", width: `${Math.min(100, cur / 5 * 100)}%`, background: curBand.hex, borderRadius: 4 }} />
                          )}
                        </div>
                        <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 4, lineHeight: 1.45 }}>
                          {curBand ? <>{curBand.label} today{tgtBand && tgtBand.label !== curBand.label ? <> → {tgtBand.label}</> : null} · </> : null}
                          {dwText(x.target_basis) || "no basis stated for the target"}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: "var(--z-muted)", marginBottom: 14 }}>
                  This recommendation states no `dma_impact` rows, so no cell
                  uplift is claimed for it.
                </div>
              )}

              {/* The fixture's customer-impact tiles and pillar bars. Both read
                  DMA.ROADMAP_IMPACTS, which is empty in LIVE by design (it
                  carries fixture-shaped uplift figures), so they render only
                  where that map actually has this recommendation. */}
              {impact && impact.customer_impact ? (
                <div className="g3" style={{ marginBottom: 14 }}>
                  {Object.entries(impact.customer_impact).map(([k, v]) => (
                    <div key={k} className="card-tile" style={{ background: "var(--z-ice)", padding: 14 }}>
                      <div style={{ fontSize: 10, color: "var(--z-mid)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 4 }}>{k.replace(/_/g, " ")}</div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: "var(--z-dark)" }}>{dwText(v)}</div>
                    </div>
                  ))}
                </div>
              ) : null}

              {impact && impact.after && impact.before ? (
                <div className="card" style={{ marginBottom: 14, padding: 14 }}>
                  <div className="row" style={{ marginBottom: 12 }}>
                    <Icon name="heatmap" size={14} />
                    <div style={{ fontWeight: 600, fontSize: 13 }}>Projected pillar uplift</div>
                  </div>
                  {Object.entries(impact.after).map(([p, after]) => {
                    const before = dwNum(impact.before[p]);
                    const a = dwNum(after);
                    return (
                      <div key={p} className="pbar" style={{ pointerEvents: "none" }}>
                        <div className="pbar-name">{p} · {DMA.PILLARS.find(x => x.id === p)?.short}</div>
                        <div className="pbar-track" style={{ position: "relative" }}>
                          {before === null ? null : <div className="pbar-fill" style={{ width: `${before / 5 * 100}%`, background: DMA.helpers.maturityHex(before), opacity: .45 }} />}
                          {a === null ? null : <div style={{ position: "absolute", left: 0, top: 0, height: "100%", width: `${a / 5 * 100}%`, background: DMA.helpers.maturityHex(a), borderRadius: 4, transition: "width 1.2s var(--ease)" }} />}
                        </div>
                        <div className="pbar-score">{a === null ? "—" : fx(a, 1)}</div>
                        {/* A delta needs both endpoints; one missing is null, not zero. */}
                        <div className="pbar-delta" style={{ color: "var(--z-mid)" }}>
                          {a === null || before === null ? "—" : `${a - before > 0 ? "+" : ""}${fx(a - before, 1)}`}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : null}

              {/* Affected subcaps */}
              {linkedSubcaps.length > 0 ? (
                <div className="card" style={{ padding: 14 }}>
                  <div className="row" style={{ marginBottom: 10 }}>
                    <Icon name="heatmap" size={14} />
                    <div style={{ fontWeight: 600, fontSize: 13 }}>Subcaps affected · {linkedSubcaps.length}</div>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {linkedSubcaps.map(sid => <button key={sid} className="chip purple" onClick={() => { closeRec(); openSubcap(sid); }}>{sid}</button>)}
                  </div>
                </div>
              ) : null}
            </>
          ) : view === "evidence" ? (
            <div>
              {/* The paragraph used to promise evidence and then render nothing
                  when `evidence_ids` was empty, and an id that does not resolve
                  was skipped silently — so a dead citation looked like it had
                  never been made (invariant 4 is fail-closed AND visible). */}
              {(r.root_cause || []).length === 0 ? (
                <div className="empty">
                  <div className="icon"><Icon name="evidence" size={20} /></div>
                  <h3>This recommendation cites no evidence</h3>
                  <p>`evidence_ids` is empty on the promoted row, so the root cause
                     stated on the Rationale tab is not traceable to a source in
                     this run.</p>
                </div>
              ) : (
                <p style={{ fontSize: 12, color: "var(--z-muted)", marginBottom: 12 }}>The root cause is grounded in the following evidence. Click any chip to open the full source.</p>
              )}
              {(r.root_cause || []).map(eid => {
                const e = DMA.getEvidence(eid);
                if (!e) return (
                  <div key={eid} className="row" style={{ padding: "10px 0", borderBottom: "1px solid var(--z-sep)", gap: 8 }}>
                    <span className="chip muted">{eid}</span>
                    <span style={{ fontSize: 11.5, color: "var(--z-muted)" }}>cited id — not in this run's served evidence</span>
                  </div>
                );
                const tier = DMA.getTier(e.tier);
                return (
                  <div key={eid} style={{ padding: "12px 0", borderBottom: "1px solid var(--z-sep)" }}>
                    <div className="row" style={{ marginBottom: 6, flexWrap: "wrap" }}>
                      <button className="chip" onClick={() => openEvidence(eid)}>{e.id}</button>
                      <span className={`tier-chip tier-${e.tier}`}>{e.tier} · {tier?.label}</span>
                      {e.claim ? <span className="b b-purple">{e.claim}</span> : null}
                      <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--z-muted)" }}>
                        {e.recency}{dwNum(e.ers) === null ? "" : ` · ERS ${e.ers}`}</span>
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 5 }}>{e.title}</div>
                    {dwText(e.excerpt) ? (
                      <div style={{ fontStyle: "italic", padding: "6px 10px", background: tier?.bg || "var(--z-bg)", borderLeft: `3px solid ${tier?.color || "var(--z-teal)"}`, fontSize: 12, color: "var(--z-body)" }}>"{dwText(e.excerpt)}"</div>
                    ) : (
                      <div style={{ padding: "6px 10px", background: "var(--z-bg)", borderLeft: "3px dashed var(--z-sep)", fontSize: 11.5, color: "var(--z-muted)" }}>
                        no verbatim excerpt served for this item
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <DependencyMap rec={r} />
          )}
        </div>
        <div className="modal-foot">
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>Linked from insight cards · {DMA.INSIGHT_CARDS.filter(c => c.rec === r.id).map(c => c.id).join(", ") || "-"}</div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-tertiary" onClick={() => {
              const summary = [
                `${r.id} · ${dwText(r.title) || ""}`,
                [area, feature, r.phase ? `phase ${r.phase}` : null].filter(Boolean).join(" · "),
                `Effort ${r.effort || (r.outcomes && r.outcomes.effort) || "not stated"}`,
              ].filter(Boolean).join("\n");
              try { navigator.clipboard.writeText(summary); pushToast("Recommendation summary copied", "success"); }
              catch (e) { pushToast("Couldn't access clipboard", "warn"); }
            }}><Icon name="copy" size={13} /> Copy summary</button>
            <button className="btn btn-primary" onClick={closeRec}>Close</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* A promoted validation gate: the threshold, the verdict, the current value and
   the cells backing it. Rendered as fields because it IS an object — printing it
   raw threw React #31 and took the application down (see the caller). */
function ValidationGate({ gate, openSubcap, closeRec }) {
  const verdict = dwText(gate.verdict);
  const cur = dwNum(gate.current_value);
  const cells = (gate.backing_cells || []).filter(c => c && typeof c === "object");
  return (
    <div>
      <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 4 }}>
        {dwText(gate.threshold) ? (
          <span className="f-mono" style={{ fontSize: 12 }}>{dwText(gate.threshold)}</span>) : null}
        {verdict ? (
          <span className={`b ${verdict.toUpperCase() === "MET" ? "b-above" : "b-below"}`}>{verdict}</span>) : null}
        {cur === null ? null : (
          <span style={{ fontSize: 11.5, color: "var(--z-muted)" }}>current {fx(cur, 2)}</span>)}
        {dwText(gate.cell) ? <span className="chip">{dwText(gate.cell)}</span> : null}
      </div>
      {dwText(gate.grain_note) ? (
        <div style={{ fontSize: 11, color: "var(--z-muted)", lineHeight: 1.5, marginBottom: 4 }}>
          {dwText(gate.grain_note)}
        </div>) : null}
      {cells.length ? (
        <div className="row" style={{ gap: 5, flexWrap: "wrap" }}>
          <span style={{ fontSize: 9.5, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>Backing cells</span>
          {cells.map((c, i) => {
            const b = dwBand(c.score);
            return (
              <button key={c.subcap_id || i} className="chip"
                onClick={() => c.subcap_id && (closeRec(), openSubcap(c.subcap_id))}
                title={[dwText(c.name), b ? `${fx(b.score, 1)} · ${b.label}` : null].filter(Boolean).join(" · ")}>
                {c.subcap_id || dwText(c.name)}{b ? ` ${fx(b.score, 1)}` : ""}
              </button>
            );
          })}
        </div>) : null}
    </div>
  );
}

/* Sequencing, from the recommendation's OWN promoted fields.

   This read DMA.ROADMAP_IMPACTS — a fixture map that is empty in LIVE by design
   — for all three columns. So every promoted recommendation rendered "PHASE -",
   "No prerequisites · can land first" and "No downstream initiatives", which is
   not an empty state but three false claims: REC-001 states two prerequisites,
   REC-003 names it as a predecessor, and the phase is on the row.

   Predecessors are the row's own `dependencies` (rec ids). "Unlocks" is COMPUTED
   by asking which other promoted recommendations name this one in theirs —
   invariant 8, one source of truth, so the two columns cannot disagree. */
function DependencyMap({ rec }) {
  const impact = DMA.ROADMAP_IMPACTS[rec.id];
  const all = DMA.RECOMMENDATIONS || [];
  const depIds = (rec.dependencies || []).length ? rec.dependencies
                                                 : (impact?.dependencies || []);
  const deps = depIds.map(id => DMA.getRecommendation(id) || { id, title: null }).filter(Boolean);
  const followups = all.filter(x => (x.dependencies || []).includes(rec.id));
  const prereqs = (rec.prerequisites || []).filter(q => q && typeof q === "object");
  const phase = rec.phase != null ? rec.phase : (impact?.phase != null ? impact.phase : null);

  return (
    <div>
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="b b-muted">{phase == null ? "PHASE NOT STATED" : `PHASE ${phase}`}</span>
        <span style={{ fontSize: 12 }}>Sequencing position in the transformation roadmap</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, alignItems: "stretch" }}>
        {/* Predecessors — recommendations this one waits on */}
        <div className="card" style={{ padding: 12 }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>Waits on</div>
          {deps.length === 0 ? (
            <div className="muted" style={{ fontSize: 12 }}>The run names no predecessor recommendation</div>
          ) : deps.map(d => (
            <div key={d.id} style={{ padding: "8px 10px", background: "var(--z-ice)", borderRadius: 6, marginBottom: 6 }}>
              <div style={{ fontSize: 12, fontWeight: 600 }}>{d.id}</div>
              <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{dwText(d.title) || "not in this run's recommendations"}</div>
            </div>
          ))}
        </div>

        {/* Current */}
        <div className="card" style={{ padding: 12, background: "var(--z-lav)", border: "2px solid var(--z-teal)" }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-mid)", textTransform: "uppercase", marginBottom: 8 }}>This initiative</div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dark)" }}>{rec.id}</div>
          <div style={{ fontSize: 11, color: "var(--z-body)", marginTop: 4 }}>{dwText(rec.title)}</div>
          <div className="sep" />
          <div style={{ fontSize: 11 }}>
            {phase == null ? "Phase not stated" : `Phase ${phase}`}
            {dwText(rec.horizon) && dwText(rec.horizon) !== String(phase) ? ` · ${dwText(rec.horizon)}` : ""}
            {rec.effort ? ` · effort ${rec.effort}` : ""}
          </div>
        </div>

        {/* Followups — computed from the other rows' dependencies */}
        <div className="card" style={{ padding: 12 }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>Unlocks</div>
          {followups.length === 0 ? (
            <div className="muted" style={{ fontSize: 12 }}>No other recommendation names this one as a predecessor</div>
          ) : followups.map(d => (
            <div key={d.id} style={{ padding: "8px 10px", background: "var(--ph0-lt)", borderRadius: 6, marginBottom: 6 }}>
              <div style={{ fontSize: 12, fontWeight: 600 }}>{d.id}</div>
              <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{dwText(d.title)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Readiness conditions — the row's own prerequisites. These are not
          recommendations, so they belong beside the three columns rather than
          inside them: a cell threshold with its verdict, or a named condition
          with the basis the producer recorded for it. */}
      {prereqs.length ? (
        <div className="card" style={{ padding: 12, marginTop: 12 }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>
            Readiness · {prereqs.length} condition{prereqs.length === 1 ? "" : "s"}
          </div>
          {prereqs.map((q, i) => {
            const min = dwNum(q.minimum), cur = dwNum(q.current);
            const verdict = dwText(q.verdict);
            return (
              <div key={i} className="row" style={{ gap: 8, padding: "6px 0", borderTop: i ? "1px solid var(--z-sep)" : 0, flexWrap: "wrap" }}>
                {q.cell ? <span className="chip purple">{q.cell}</span> : null}
                <span style={{ fontSize: 12, flex: 1, minWidth: 0 }}>
                  {q.cell
                    ? <span className="f-mono">{q.cell} ≥ {min === null ? "—" : fx(min, 1)}{cur === null ? "" : ` · currently ${fx(cur, 2)}`}</span>
                    : dwText(q.condition)}
                </span>
                {dwText(q.basis) ? <span className="b b-muted">{dwText(q.basis)}</span> : null}
                {verdict ? (
                  <span className={`b ${verdict.toUpperCase() === "MET" ? "b-above" : "b-below"}`}>{verdict}</span>
                ) : null}
              </div>
            );
          })}
          {prereqs.some(q => dwText(q.note)) ? (
            <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 8, lineHeight: 1.5 }}>
              {prereqs.map(q => dwText(q.note)).filter(Boolean).join(" · ")}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
