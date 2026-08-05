/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Drawer/Modal components - Evidence drawer, Insight modal,
   Intelligence panel, simple toast helpers
   ═══════════════════════════════════════════════════════════════════════ */

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
            <div className="sub">{items.length} evidence item{items.length === 1 ? "" : "s"}{subcap ? ` · score ${subcap.score} · ${subcap.confidence}` : ""}</div>
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
                  {subcap.peerMedian != null ? ` · peer median ${fx(subcap.peerMedian, 1)}` : " · no peer figure available"}
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
                  <p>{subcap && subcap.thin
                        ? "The cell is flagged thin: it keeps its workbook score and a dashed outline, and its closure condition names what would settle it."
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
                          ? "no publication date could be resolved, so the recency ladder cannot rank this item — its claim class is unaffected"
                          : (it.published_date || "")}>
                    {it.recency}
                  </span>
                  {role !== "AE" && audience !== "customer" ? <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--z-muted)" }}>ERS <strong style={{ color: "var(--z-mid)" }}>{it.ers}</strong></span> : null}
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)", marginBottom: 5 }}>{it.title}</div>
                <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55, fontStyle: "italic", padding: "8px 10px", background: tier?.bg || "var(--z-bg)", borderLeft: `3px solid ${tier?.color || "var(--z-teal)"}`, borderRadius: 3 }}>"{it.excerpt}"</div>
                <div style={{ marginTop: 6, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <a href={`https://${it.source}`} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: "var(--z-mid)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}>
                    <Icon name="external" size={11} /> {it.source_pretty || it.source}
                  </a>
                  {it.subcaps && it.subcaps.length > 0 ? (
                    <span style={{ fontSize: 10, color: "var(--z-muted)", display: "inline-flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
                      <span>· supports:</span>
                      {it.subcaps.slice(0, 3).map(sid => <button key={sid} className="chip" onClick={() => openSubcap(sid)}>{sid}</button>)}
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
        <div className="drawer-foot">
          <button className="btn btn-tertiary" onClick={() => {
            const lines = filtered.map(it => `${it.id} · ${it.tier} · ${it.title} — "${it.excerpt}" (${it.source_pretty || it.source})`).join("\n");
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
  const { insightModal, closeInsight, openEvidence, openSubcap, openRec, audience, pushToast } = useApp();
  const [tab, setTab] = useState("detail");
  const [note, setNote] = useState("");
  const [annStatus, setAnnStatus] = useState("ACTIONED");

  useEffect(() => { if (insightModal) setTab("detail"); }, [insightModal]);
  if (!insightModal) return null;
  const ic = DMA.getInsight(insightModal);
  if (!ic) return null;
  const rec = ic.rec ? DMA.getRecommendation(ic.rec) : null;
  const platform = ic.platforms[0] ? DMA.getPlatform(ic.platforms[0]) : null;

  return (
    <div className="modal-mask" onClick={closeInsight}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 820 }}>
        <div className="modal-head">
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6 }}>
              <span className={`b ${ic.flag === "CRITICAL" ? "b-below" : ic.flag === "OPPORTUNITY" ? "b-org" : "b-teal"}`}>{ic.flag}</span>
              <span className="b b-purple">{ic.pillar}</span>
              <span className="chip">{ic.id}</span>
              {platform ? <span className="b b-teal">{platform.name}</span> : null}
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Confidence · {ic.confidence}</span>
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
                  {(ic.r_layer.probes_run || []).length ? (
                    <div className="row" style={{ gap: 5, flexWrap: "wrap", marginTop: 4 }}>
                      <span style={{ fontSize: 9.5, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>Probes</span>
                      {ic.r_layer.probes_run.map((x, i) => <span key={i} className="chip" title={x}>{String(x).slice(0, 34)}</span>)}
                    </div>
                  ) : null}
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
              {rec && audience !== "customer" ? (
                <div className="co co-teal" style={{ marginTop: 12, cursor: "pointer" }} onClick={() => { closeInsight(); openRec(rec.id); }}>
                  <Icon name="platform" size={14} />
                  <div style={{ flex: 1 }}>
                    <div className="co-title">Linked recommendation · click for impact</div>
                    <div className="co-body"><strong>{rec.id}</strong> - {rec.title}. {DMA.getPlatform(rec.platform).name} · {rec.feature} · {rec.phase}.</div>
                  </div>
                  <Icon name="arrow-r" size={14} style={{ color: "var(--z-mid)" }} />
                </div>
              ) : null}
            </div>
          ) : tab === "evidence" ? (
            <div>
              {ic.evidence.map(eid => {
                const e = DMA.getEvidence(eid);
                if (!e) return null;
                return (
                  <div key={eid} style={{ padding: "12px 0", borderBottom: "1px solid var(--z-sep)" }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                      <span className="chip">{e.id}</span>
                      <span className="b b-muted">{e.tier}</span>
                      <span className="b b-purple">{e.claim}</span>
                      <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--z-muted)" }}>{e.recency} · ERS {e.ers}</span>
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{e.title}</div>
                    <div style={{ fontStyle: "italic", padding: "6px 10px", background: "var(--z-bg)", borderLeft: "2px solid var(--z-teal)", fontSize: 12, color: "var(--z-body)" }}>"{e.excerpt}"</div>
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
            <div style={{ fontSize: 12, color: "var(--z-body)" }}>
              <p style={{ marginBottom: 10 }}><strong>Subcapabilities affected:</strong></p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
                {ic.affects.map(sid => <span key={sid} className="chip purple">{sid}</span>)}
              </div>
              <p style={{ marginBottom: 10 }}><strong>Implicated platforms:</strong></p>
              <div style={{ display: "flex", gap: 6 }}>{ic.platforms.map(p => <span key={p} className="b b-teal">{DMA.getPlatform(p)?.name}</span>)}</div>
            </div>
          )}
        </div>
        <div className="modal-foot">
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-tertiary" onClick={() => {
              const text = `${ic.id} · ${ic.flag} · ${ic.pillar}\n${ic.title}\n\nWHAT: ${ic.what}\n\nWHY: ${ic.why}\n\nSO WHAT: ${ic.so_what}`;
              try { navigator.clipboard.writeText(text); pushToast("Insight card copied to clipboard", "success"); }
              catch (e) { pushToast("Couldn't access clipboard", "warn"); }
            }}><Icon name="copy" size={13} /> Copy card</button>
            <button className="btn btn-tertiary" onClick={() => pushToast(`Exporting ${ic.id} as PDF…`, "success")}><Icon name="download" size={13} /> Export</button>
          </div>
          <button className="btn btn-primary" onClick={closeInsight}>Close</button>
        </div>
      </div>
    </div>
  );
}

function Block({ title, body, evIds, onEv, accent }) {
  // Render body and inject tier-colored E-ID chips for any tokens like [E-047]
  const parts = [];
  let last = 0;
  const re = /\[?E-\d+\]?/g;
  let m;
  while ((m = re.exec(body)) !== null) {
    if (m.index > last) parts.push(body.slice(last, m.index));
    parts.push({ chip: m[0].replace(/[\[\]]/g, "") });
    last = m.index + m[0].length;
  }
  if (last < body.length) parts.push(body.slice(last));

  const renderChip = (id) => {
    const ev = DMA.getEvidence(id);
    const tier = ev?.tier || "T1";
    return <button key={id} className={`tier-chip tier-${tier}`} style={{ marginLeft: 4, cursor: "pointer" }} onClick={() => onEv && onEv(id)} title={ev?.title}>{id}<span style={{ fontWeight: 400, opacity: .65, marginLeft: 4 }}>·{tier}</span></button>;
  };

  return (
    <div style={{ marginBottom: 14, borderLeft: accent ? "3px solid var(--z-teal)" : "3px solid var(--z-sep)", paddingLeft: 14 }}>
      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".12em", color: accent ? "var(--z-mid)" : "var(--z-muted)", textTransform: "uppercase", marginBottom: 6 }}>{title}</div>
      <div style={{ fontSize: 13.5, color: "var(--z-dark)", lineHeight: 1.65 }}>
        {parts.map((p, i) => typeof p === "string" ? <span key={i}>{p}</span> : renderChip(p.chip))}
        {evIds && evIds.length ? <span style={{ marginLeft: 6 }}>{evIds.map(eid => renderChip(eid))}</span> : null}
      </div>
    </div>
  );
}

/* ── Intelligence Panel ─────────────────────────────────────────── */
function IntelligencePanel() {
  const { ipOpen, setIpOpen, ipSurface, ipContext, authed, pushToast, openEvidence } = useApp();
  const [text, setText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [chat, setChat] = useState([]);          // [{role: 'user'|'ai', text}]
  const [chatInput, setChatInput] = useState("");
  const [chatStreaming, setChatStreaming] = useState(false);
  const messages = useMemo(() => surfaceMessages(ipSurface, ipContext), [ipSurface, ipContext]);
  const bodyRef = useRef(null);

  // Reset on surface change
  useEffect(() => {
    if (!ipOpen) return;
    setText("");
    setStreaming(true);
    setChat([]);
    let i = 0;
    const id = setInterval(() => {
      i += 4;
      setText(messages.body.slice(0, i));
      if (i >= messages.body.length) { clearInterval(id); setStreaming(false); }
    }, 16);
    return () => clearInterval(id);
  }, [ipOpen, messages]);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [chat, chatStreaming]);

  const STARTERS = useMemo(() => starterQuestions(ipSurface, ipContext), [ipSurface, ipContext]);

  // Never show before sign-in (rule of hooks: gate AFTER all hook calls)
  if (!authed) return null;

  const ask = (question) => {
    // In LIVE nothing answers: the serving path runs no model (invariant 1),
    // and the prototype's canned reply is another institution's story.
    if (IP_LIVE()) return;
    const q = (question || chatInput).trim();
    if (!q) return;
    setChat(c => [...c, { role: "user", text: q }, { role: "ai", text: "" }]);
    setChatInput("");
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
        <div style={{ fontSize: 13, lineHeight: 1.65 }}>
          {text}{streaming ? <span className="ip-cursor" /> : null}
        </div>
        {!streaming && ipSurface === "why_now" ? <WhyNowSignals ctx={ipContext} openEvidence={openEvidence} pushToast={pushToast} /> : null}
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
                setText(messages.body.slice(0, i));
                if (i >= messages.body.length) { clearInterval(id); setStreaming(false); }
              }, 16);
            }}><Icon name="refresh" size={12} /> Replay</button>
            {IP_LIVE() ? null : (
              <button className="btn btn-tertiary btn-sm" onClick={() => pushToast("Routed to Gemini Pro — deeper analysis takes ~8s", "success")}>Deeper · Pro</button>
            )}
          </div>
        ) : null}

        {/* Chat */}
        {chat.length > 0 ? (
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed var(--ph0-bd)" }}>
            {chat.map((m, i) => (
              <div key={i} className={`ip-message ${m.role}`}>{m.text}{m.role === "ai" && chatStreaming && i === chat.length - 1 ? <span className="ip-cursor" /> : null}</div>
            ))}
          </div>
        ) : null}
      </div>

      {/* Starters. In LIVE these are the producer's promoted talking points and
          are read-only — clicking one would ask a question nothing can answer. */}
      {!chatStreaming && STARTERS.length ? (
        <div className="ip-chat">
          <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase", marginBottom: 6 }}>
            {IP_LIVE() ? "Conversation starters · promoted"
                       : (chat.length === 0 ? "Try a question" : "Follow-ups")}
          </div>
          {STARTERS.map((s, i) => (
            IP_LIVE()
              ? <div key={i} className="ip-starter" style={{ cursor: "default" }}>{s}</div>
              : <button key={i} className="ip-starter" onClick={() => ask(s)}>{s}</button>
          ))}
        </div>
      ) : null}

      {/* Chat input — prototype only. There is no request-time model to ask. */}
      {IP_LIVE() ? null : (
        <div className="ip-input">
          <input placeholder="Ask anything about this entity…"
                 value={chatInput}
                 onChange={e => setChatInput(e.target.value)}
                 onKeyDown={e => e.key === "Enter" && ask()} />
          <button className="btn btn-primary btn-sm" onClick={() => ask()} disabled={!chatInput.trim() || chatStreaming}>
            <Icon name="arrow-r" size={12} />
          </button>
        </div>
      )}
    </aside>
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
  const CAT = {
    core_migration: { icon: "refresh", color: "var(--z-teal)" },
    leadership:     { icon: "users",   color: "var(--z-dpur)" },
    hiring:         { icon: "users",   color: "var(--z-mid)" },
    regulatory:     { icon: "lock",    color: "var(--z-org)" },
    market:         { icon: "stack",   color: "var(--z-mid)" },
  };
  const STR = { STRONG: "b-teal", LEADING: "b-purple", SUPPORTING: "b-muted" };
  return (
    <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed var(--ph0-bd)" }} data-source="evidence_index.json (trigger) + timeline_events.csv">
      <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase", marginBottom: 8 }}>
        Trigger signals · click to drill in
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {signals.map(s => {
          const isOpen = open === s.id;
          const cat = CAT[s.category] || CAT.market;
          return (
            <div key={s.id} className="wn-signal" style={{ border: "1px solid var(--ph0-bd)", borderRadius: 8, overflow: "hidden", background: "rgba(255,255,255,.04)" }}>
              <button onClick={() => setOpen(o => o === s.id ? null : s.id)}
                style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, padding: "9px 10px", background: "none", border: 0, cursor: "pointer", textAlign: "left" }}>
                <span style={{ width: 22, height: 22, borderRadius: 6, background: cat.color, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><Icon name={cat.icon} size={12} /></span>
                <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 600, color: "#fff" }} className="txt-fit-1">{s.label}</span>
                <span className={`b ${STR[s.strength] || "b-muted"}`}>{s.strength}</span>
                <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={13} style={{ color: "rgba(255,255,255,.6)", flexShrink: 0 }} />
              </button>
              {isOpen ? (
                <div style={{ padding: "0 10px 10px", fontSize: 12, lineHeight: 1.6, color: "rgba(255,255,255,.85)" }}>
                  {/* confidence + claim + metric */}
                  <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap", marginBottom: 8 }}>
                    {s.confidence ? <span className="b" style={{ background: "rgba(255,255,255,.12)", color: "#fff" }}>{s.confidence} confidence</span> : null}
                    {s.claim ? <span className="b" style={{ background: "rgba(255,255,255,.12)", color: "rgba(255,255,255,.85)" }}>{s.claim}</span> : null}
                  </div>
                  {s.metric ? (
                    <div style={{ background: "rgba(255,255,255,.06)", border: "1px solid rgba(255,255,255,.1)", borderRadius: 6, padding: "6px 9px", marginBottom: 8, fontSize: 11.5, color: "#fff", fontFamily: "var(--font-mono, monospace)" }}>{s.metric}</div>
                  ) : null}
                  <div style={{ marginBottom: 8 }}>{s.detail}</div>
                  {s.peer_context ? (
                    <div style={{ marginBottom: 8 }}>
                      <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em", color: "rgba(255,255,255,.5)", textTransform: "uppercase" }}>Peer context · </span>
                      <span style={{ fontSize: 11.5 }}>{s.peer_context}</span>
                    </div>
                  ) : null}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "rgba(255,255,255,.65)", marginBottom: 8 }}>
                    <Icon name="timeline" size={11} /><span className="f-mono">{s.timeline.date}</span> · {s.timeline.event}
                  </div>
                  {s.play ? (
                    <div style={{ background: "rgba(39,187,175,.14)", borderLeft: "2px solid var(--z-teal)", borderRadius: 4, padding: "7px 9px", fontSize: 11.5, color: "#DFF6F2", marginBottom: 6 }}>
                      <strong style={{ color: "var(--z-teal)" }}>Play · </strong>{s.play}
                    </div>
                  ) : null}
                  <div style={{ background: "rgba(39,187,175,.14)", borderLeft: "2px solid var(--z-teal)", borderRadius: 4, padding: "7px 9px", fontSize: 11.5, color: "#DFF6F2", marginBottom: 6 }}>
                    <strong style={{ color: "var(--z-teal)" }}>So what · </strong>{s.impact}
                  </div>
                  {s.risk ? (
                    <div style={{ background: "rgba(254,151,50,.14)", borderLeft: "2px solid var(--z-org)", borderRadius: 4, padding: "7px 9px", fontSize: 11.5, color: "#FEDFC0", marginBottom: 8 }}>
                      <strong style={{ color: "#FEC07A" }}>Risk if ignored · </strong>{s.risk}
                    </div>
                  ) : null}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 10, color: "rgba(255,255,255,.5)", textTransform: "uppercase", letterSpacing: ".08em" }}>Evidence</span>
                    {s.evidence && s.evidence.length ? s.evidence.map(eid => {
                      const e = DMA.getEvidence(eid);
                      return (
                        <button key={eid} className={`tier-chip tier-${e?.tier || "T3"}`} style={{ cursor: "pointer", border: 0 }}
                          title={e ? `${e.title} · ${e.source_pretty}` : eid}
                          onClick={() => { openEvidence(eid); }}>{eid}</button>
                      );
                    }) : <span style={{ fontSize: 11, color: "rgba(255,255,255,.45)" }}>Inferred — confirm in discovery</span>}
                    <span style={{ flex: 1 }} />
                    <span className="b" style={{ background: (CAT[s.category] || CAT.market).color, color: "#fff" }}>{s.window}</span>
                  </div>
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
   surface's own synthesis and the producer's conversation starters — and the
   free-text box, the regenerate button and the canned answers are absent.
   Anything the run did not promote is stated as absent, never filled in. */
const IP_LIVE = () => typeof window !== "undefined" && !!window.DMA_LIVE;

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
  const absent = (what) =>
    `${what} did not promote for this run. Nothing is shown rather than filled in — ` +
    `the panel reads promoted synthesis only and this application runs no model at request time.`;

  if (surface === "why_now") {
    const wn = id ? DMA.whyNowFor(id) : null;
    const body = (wn && (wn.synthesis || wn.narrative)) || null;
    return {
      title: "Why now", sub: (wn && wn.window) || "Trigger signals",
      cache_age: "promoted",
      body: body || (wn && wn.signals && wn.signals.length
        ? `${wn.signals.length} trigger signal${wn.signals.length === 1 ? "" : "s"} promoted for ${ent}. ` +
          `Expand a signal below for its claim, evidence and play.`
        : absent("The why-now synthesis")),
    };
  }
  if (surface === "subcap_narrative") {
    const sc = ctx?.subcap || {};
    const cell = (DMA.cellEvidenceFor(sc.id) || null);
    return {
      title: "Cell synthesis", sub: sc.id || "Heatmap selection",
      cache_age: "promoted",
      body: (cell && (cell.synthesis || cell.narrative)) || absent(`A synthesis for ${sc.id || "this cell"}`),
    };
  }
  if (surface === "platform_story") {
    const ps = DMA.platformStoryFor(id);
    return {
      title: "Platform story", sub: (ps && ps.platform) || ctx?.platform || "Promoted narrative",
      cache_age: "promoted",
      body: (ps && (ps.narrative || ps.story || ps.synthesis)) || absent("The platform story"),
    };
  }
  if (surface === "focus_area") {
    const fa = ctx?.focusArea || {};
    return {
      title: "Focus area synthesis", sub: fa.name || "Strategic priority",
      cache_age: "promoted",
      body: fa.synthesis || fa.rationale || fa.quote || absent("A synthesis for this focus area"),
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
  const plat = DMA.getPlatform(r.platform);
  const impact = DMA.ROADMAP_IMPACTS[r.id];
  const linkedSubcaps = DMA.INSIGHT_CARDS.filter(c => c.rec === r.id).flatMap(c => c.affects);

  return (
    <div className="modal-mask" onClick={closeRec}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 820 }}>
        <div className="modal-head">
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
              <span className="chip">{r.id}</span>
              <span className="b b-teal">{plat?.name} · {r.feature}</span>
              <span className="b b-purple">{r.phase}</span>
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Effort {r.outcomes.effort} · {r.outcomes.time}</span>
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
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {[
                    { n: "1", k: "Trigger", v: <>Surfaced by {r.root_cause.length} evidence item{r.root_cause.length === 1 ? "" : "s"} ({r.root_cause.map((eid, i) => <span key={eid}><button className="chip" style={{ marginRight: 3 }} onClick={() => openEvidence(eid)}>{eid}</button></span>)}) showing a capability gap the client cannot close with current tooling.</> },
                    { n: "2", k: "Mechanism", v: <>{plat?.name}'s <strong>{r.feature}</strong> directly addresses the root cause. It is the lowest-friction path to the target maturity because the platform footprint is already {plat ? "present or adjacent" : "in scope"}.</> },
                    { n: "3", k: "Sequencing", v: <>Scheduled in <strong>{r.phase}</strong>{impact ? ` (phase ${impact.phase})` : ""}. {impact && impact.dependencies && impact.dependencies.length ? <>Depends on {impact.dependencies.map(d => <span key={d} className="chip" style={{ marginRight: 3 }}>{d}</span>)} landing first.</> : "No prerequisites — this can land first and unblock later phases."}</> },
                    { n: "4", k: "Expected outcome", v: <><strong>{r.outcomes.metric}</strong> · {r.outcomes.time} · {r.outcomes.effort} effort</> },
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
              <div className="g3" style={{ marginBottom: 14 }}>
                {Object.entries(impact?.customer_impact || {}).map(([k, v]) => (
                  <div key={k} className="card-tile" style={{ background: "var(--z-ice)", padding: 14 }}>
                    <div style={{ fontSize: 10, color: "var(--z-mid)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 4 }}>{k.replace(/_/g, " ")}</div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: "var(--z-dark)" }}>{v}</div>
                  </div>
                ))}
              </div>

              {/* Before / after pillar uplift */}
              <div className="card" style={{ marginBottom: 14, padding: 14 }}>
                <div className="row" style={{ marginBottom: 12 }}>
                  <Icon name="heatmap" size={14} />
                  <div style={{ fontWeight: 600, fontSize: 13 }}>Projected pillar uplift</div>
                </div>
                {impact && Object.entries(impact.after).map(([p, after]) => {
                  const before = impact.before[p];
                  return (
                    <div key={p} className="pbar" style={{ pointerEvents: "none" }}>
                      <div className="pbar-name">{p} · {DMA.PILLARS.find(x => x.id === p)?.short}</div>
                      <div className="pbar-track" style={{ position: "relative" }}>
                        <div className="pbar-fill" style={{ width: `${before / 5 * 100}%`, background: DMA.helpers.maturityHex(before), opacity: .45 }} />
                        <div style={{ position: "absolute", left: 0, top: 0, height: "100%", width: `${after / 5 * 100}%`, background: DMA.helpers.maturityHex(after), borderRadius: 4, transition: "width 1.2s var(--ease)" }} />
                      </div>
                      <div className="pbar-score">{fx(after, 1)}</div>
                      <div className="pbar-delta" style={{ color: "var(--z-mid)" }}>+{fx((after - before), 1)}</div>
                    </div>
                  );
                })}
              </div>

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
              <p style={{ fontSize: 12, color: "var(--z-muted)", marginBottom: 12 }}>The root cause is grounded in the following evidence. Click any chip to open the full source.</p>
              {r.root_cause.map(eid => {
                const e = DMA.getEvidence(eid);
                if (!e) return null;
                const tier = DMA.getTier(e.tier);
                return (
                  <div key={eid} style={{ padding: "12px 0", borderBottom: "1px solid var(--z-sep)" }}>
                    <div className="row" style={{ marginBottom: 6 }}>
                      <button className="chip" onClick={() => openEvidence(eid)}>{e.id}</button>
                      <span className={`tier-chip tier-${e.tier}`}>{e.tier} · {tier?.label}</span>
                      <span className="b b-purple">{e.claim}</span>
                      <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--z-muted)" }}>{e.recency} · ERS {e.ers}</span>
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 5 }}>{e.title}</div>
                    <div style={{ fontStyle: "italic", padding: "6px 10px", background: tier?.bg || "var(--z-bg)", borderLeft: `3px solid ${tier?.color}`, fontSize: 12, color: "var(--z-body)" }}>"{e.excerpt}"</div>
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
              const summary = `${r.id} · ${r.title}\n${plat?.name} · ${r.feature} · ${r.phase}\nEffort ${r.outcomes.effort} · ${r.outcomes.time}`;
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

function DependencyMap({ rec }) {
  const impact = DMA.ROADMAP_IMPACTS[rec.id];
  const deps = (impact?.dependencies || []).map(id => DMA.getRecommendation(id)).filter(Boolean);
  const followups = Object.values(DMA.ROADMAP_IMPACTS).map(x => ({ ...x, _id: Object.keys(DMA.ROADMAP_IMPACTS).find(k => DMA.ROADMAP_IMPACTS[k] === x) })).filter(x => x.dependencies.includes(rec.id));
  return (
    <div>
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="b b-muted">PHASE {impact?.phase || "-"}</span>
        <span style={{ fontSize: 12 }}>Sequencing position in the transformation roadmap</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, alignItems: "stretch" }}>
        {/* Predecessors */}
        <div className="card" style={{ padding: 12 }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>Prerequisites</div>
          {deps.length === 0 ? <div className="muted" style={{ fontSize: 12 }}>No prerequisites · can land first</div> : deps.map(d => (
            <div key={d.id} style={{ padding: "8px 10px", background: "var(--z-ice)", borderRadius: 6, marginBottom: 6 }}>
              <div style={{ fontSize: 12, fontWeight: 600 }}>{d.id}</div>
              <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{d.title}</div>
            </div>
          ))}
        </div>

        {/* Current */}
        <div className="card" style={{ padding: 12, background: "var(--z-lav)", border: "2px solid var(--z-teal)" }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-mid)", textTransform: "uppercase", marginBottom: 8 }}>This initiative</div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dark)" }}>{rec.id}</div>
          <div style={{ fontSize: 11, color: "var(--z-body)", marginTop: 4 }}>{rec.title}</div>
          <div className="sep" />
          <div style={{ fontSize: 11 }}>Phase {impact?.phase} · {rec.outcomes.time}</div>
        </div>

        {/* Followups */}
        <div className="card" style={{ padding: 12 }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>Unlocks</div>
          {followups.length === 0 ? <div className="muted" style={{ fontSize: 12 }}>No downstream initiatives</div> : followups.map(d => {
            const r = DMA.getRecommendation(d._id);
            if (!r) return null;
            return (
              <div key={d._id} style={{ padding: "8px 10px", background: "var(--ph0-lt)", borderRadius: 6, marginBottom: 6 }}>
                <div style={{ fontSize: 12, fontWeight: 600 }}>{r.id}</div>
                <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{r.title}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
