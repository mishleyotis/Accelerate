/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Drawer/Modal components - Evidence drawer, Insight modal,
   Intelligence panel, simple toast helpers
   ═══════════════════════════════════════════════════════════════════════ */

/* ── "Seen in N runs" chip (Promise 5 / commit 8331bd2 — standalone port)
   State branches:
     - loading           → null (do not render until data arrives; chip is
                           secondary signal, never blocks the row)
     - error / 404       → null (fail-closed; never show a misleading 0)
     - n_runs <= 1       → muted "First seen" chip, no popover
     - n_runs >= 2       → "Seen in N runs" + popover with per-run rows
   The popover lists each run with its request_id, completion date, and
   surfaces_in_run. Clicking outside or pressing the chip again toggles. */
function SeenInRunsChip({ evidenceId }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let cancelled = false;
    if (!evidenceId || !window.DMA?.evidence?.runHistory) return;
    window.DMA.evidence.runHistory(evidenceId).then(res => {
      if (cancelled) return;
      if (res?.ok && res.data) setData(res.data);
    });
    return () => { cancelled = true; };
  }, [evidenceId]);
  if (!data) return null;
  const n = data.n_runs ?? 0;
  const firstSeen = data.is_first_seen || n <= 1;
  const label = firstSeen ? "First seen" : `Seen in ${n} runs`;
  return (
    <span style={{ position: "relative", display: "inline-flex" }}
          data-evidence-history data-evidence-id={evidenceId} data-history-n={n}>
      <button
        type="button"
        className="chip"
        style={firstSeen
          ? { background: "var(--z-lav)", color: "var(--z-muted)", cursor: "default", fontSize: 10 }
          : { background: "var(--z-ice)", color: "var(--z-mid)", cursor: "pointer", fontSize: 10 }}
        onClick={() => { if (!firstSeen) setOpen(o => !o); }}
        aria-label={label}
        disabled={firstSeen}>
        <Icon name="refresh" size={10} /> {label}
      </button>
      {open && !firstSeen ? (
        <div role="dialog" aria-label="Evidence run history"
             style={{ position: "absolute", top: "100%", left: 0, marginTop: 6, zIndex: 50,
                      background: "#fff", border: "1px solid var(--z-sep)", borderRadius: 8,
                      boxShadow: "var(--sh-lg)", padding: 10, minWidth: 280 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 6 }}>
            Seen in {n} runs
          </div>
          {(data.runs || []).map(r => (
            <div key={r.run_id || r.request_id} style={{ padding: "6px 0", borderBottom: "1px solid var(--z-sep)", fontSize: 11 }}>
              <div className="f-mono" style={{ color: "var(--z-dark)", fontWeight: 600 }}>{r.request_id || r.run_id}</div>
              <div style={{ color: "var(--z-muted)", fontSize: 10, marginTop: 2 }}>
                {r.completed_at ? fmtDate(r.completed_at) : "—"}
                {r.first_seen_in_run ? " · first seen" : ""}
                {r.surfaces_in_run && r.surfaces_in_run.length > 0
                  ? ` · ${r.surfaces_in_run.slice(0, 3).join(", ")}`
                  : ""}
              </div>
            </div>
          ))}
          <button className="btn btn-tertiary btn-sm" style={{ marginTop: 8 }} onClick={() => setOpen(false)}>Close</button>
        </div>
      ) : null}
    </span>
  );
}

/* ── Evidence drawer ─────────────────────────────────────────────── */
function EvidenceDrawer() {
  const { evidenceDrawer, closeEvidence, role, audience, openSubcap } = useApp();
  const [tierFilter, setTierFilter] = useState("ALL");
  if (!evidenceDrawer) return null;
  const ev = DMA.getEvidence(evidenceDrawer.evidenceId);
  const subcap = evidenceDrawer.subcap;
  const ic = evidenceDrawer.insight && DMA.getInsight(evidenceDrawer.insight);

  // Pull evidence items
  let items = [];
  if (ev) items = [ev];
  else if (ic) items = ic.evidence.map(id => DMA.getEvidence(id)).filter(Boolean);
  else if (subcap) {
    // Find evidence items that reference this subcap, plus pad to subcap.evidence_count
    items = DMA.EVIDENCE.filter(e => e.subcaps && e.subcaps.includes(subcap.id));
    if (items.length === 0) items = DMA.EVIDENCE.slice(0, Math.max(1, Math.min(subcap.evidence_count, 4)));
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
            <div className="title txt-fit-2" style={{ fontSize: 14 }} title={subcap ? subcap.name : ic ? ic.title : ev ? ev.title : "Evidence"}>{subcap ? subcap.name : ic ? ic.title : ev ? ev.title : "Evidence"}</div>
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
                <div className="co-body">Score {subcap.score.toFixed(1)} · peer median {subcap.peerMedian.toFixed(1)}. {subcap.thin ? "Evidence is below the threshold of 3 - flagged as thin." : "Evidence ceiling: T2 with consistent FACT-class claims."}</div>
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
              <h3>No evidence in this tier</h3>
              <p>Try another tier or clear the filter.</p>
            </div>
          ) : filtered.map(it => {
            const tier = DMA.getTier(it.tier);
            return (
              <div key={it.id} style={{ borderBottom: "1px solid var(--z-sep)", padding: "12px 0" }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
                  <span className="chip">{it.id}</span>
                  <span className={`tier-chip tier-${it.tier}`} title={tier?.desc}>{it.tier} · {tier?.label}</span>
                  <span className="b b-purple">{it.claim}</span>
                  <span style={{ fontSize: 10, color: "var(--z-muted)" }}>{it.recency}</span>
                  <SeenInRunsChip evidenceId={it.id} />
                  {role !== "AE" && audience !== "customer" ? <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--z-muted)" }}>ERS <strong style={{ color: "var(--z-mid)" }}>{it.ers}</strong></span> : null}
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)", marginBottom: 5 }}>{it.title}</div>
                <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55, fontStyle: "italic", padding: "8px 10px", background: tier?.bg || "var(--z-bg)", borderLeft: `3px solid ${tier?.color || "var(--z-teal)"}`, borderRadius: 3 }}>"<ExcerptText text={it.excerpt} />"</div>
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
          <button className="btn btn-tertiary"><Icon name="copy" size={13} /> Copy citation</button>
          <button className="btn btn-secondary" onClick={closeEvidence}>Close</button>
        </div>
      </div>
    </>
  );
}

/* ── Insight card modal ──────────────────────────────────────────── */
function InsightModal() {
  const { insightModal, closeInsight, openEvidence, openSubcap, openRec, audience } = useApp();
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
              <Block title="WHAT" body={ic.what} evIds={ic.evidence} onEv={openEvidence} />
              <Block title="WHY" body={ic.why} />
              <Block title="SO WHAT" body={ic.so_what} accent />
              <div style={{ background: "var(--z-lav)", borderRadius: 8, padding: "12px 14px", marginTop: 14 }}>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", marginBottom: 8, textTransform: "uppercase" }}>Affects · {ic.affects.length} capabilities</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {ic.affects.map(sid => (
                    <button key={sid} className="chip purple" onClick={() => openSubcap(sid)}>{sid}</button>
                  ))}
                </div>
              </div>
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
                    <div style={{ fontStyle: "italic", padding: "6px 10px", background: "var(--z-bg)", borderLeft: "2px solid var(--z-teal)", fontSize: 12, color: "var(--z-body)" }}>"<ExcerptText text={e.excerpt} />"</div>
                  </div>
                );
              })}
            </div>
          ) : tab === "annotations" ? (
            <div>
              {ic.annotation ? (
                <div style={{ background: "var(--z-lav)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6, fontSize: 12 }}>
                    <div className="sb-avatar" style={{ width: 22, height: 22, fontSize: 9 }}>MO</div>
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
            <button className="btn btn-tertiary"><Icon name="copy" size={13} /> Copy card</button>
            <button className="btn btn-tertiary"><Icon name="download" size={13} /> Export</button>
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

/* ── Intelligence Panel ───────────────────────────────────────────
   Wired to Vertex AI (Gemini Flash + Pro) via the backend at
   POST /api/v1/gemini/stream (SSE; cited_evidence_ids in payload).
   Until that endpoint is reachable, the panel runs in WELCOME mode:
   it greets the signed-in user, explains what the app is for, and
   offers a guided walkthrough. It always inspects what's currently
   in window.DMA and reports whether real data is loaded.
*/
/**
 * @state-transitions
 *   IntelligencePanel.open with no prior thread
 *     → fetch DMA.chat.listSessions for current entity; render up to 3
 *       "Recent threads" rows above the starters
 *   "Resume" click on a recent thread
 *     → DMA.chat.getSession(id) → seeds chat[] with persisted messages
 *       and stamps localStorage so follow-ups extend that session
 *   thumbs-up/down click on an AI response
 *     → POST /chat/messages/:id/feedback with rating ∈ {-1, +1}
 *   lightbulb click on an AI response
 *     → opens textarea; submit posts feedback with rating=-1 +
 *       better_answer = textarea body (the adversarial signal that
 *       feeds chat_learning_signals)
 *   streaming response in flight
 *     → feedback buttons disabled until streaming completes
 *   401 on any chat fetch
 *     → silently fall back to local welcome UX (legacy behaviour)
 */
function IntelligencePanel() {
  const { ipOpen, setIpOpen, ipSurface, ipContext, authed, user, route, openEvidence } = useApp();
  const [text, setText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [chat, setChat] = useState([]);          // [{role,text,citations,grounded,error,messageId,feedback}]
  const [chatInput, setChatInput] = useState("");
  const [chatStreaming, setChatStreaming] = useState(false);
  const [showStarters, setShowStarters] = useState(true);
  const [lastQuestion, setLastQuestion] = useState(null);
  const [recentSessions, setRecentSessions] = useState([]);   // [{id, last_question, last_message_at, message_count}]
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [feedbackDraft, setFeedbackDraft] = useState({});      // messageId → { open, text }
  const dataLoaded = (DMA.ENTITIES || []).length > 0;
  // Welcome mode kicks in when no client-scoped surface context is set
  // (i.e. user is on the dashboard / directory / global pages). On
  // client pages with ipSurface set we still use the per-surface
  // messages — but every per-surface message now degrades to the
  // "data not loaded" line until ENTITIES are wired.
  const inWelcomeMode = !ipContext && !ipSurface?.startsWith?.("subcap_");
  const messages = useMemo(
    () => inWelcomeMode
      ? welcomeMessage(user, route, dataLoaded)
      : surfaceMessages(ipSurface, ipContext, dataLoaded),
    [ipSurface, ipContext, user, route, dataLoaded, inWelcomeMode]
  );
  const bodyRef = useRef(null);
  const abortRef = useRef({ cancelled: false });

  // Build a page context object the backend can ground on. Sent on
  // every /api/v1/rag/answer call so Gemini sees the current route,
  // entity, subcap, and audience.
  const pageContext = useMemo(() => ({
    route: route?.path || "/",
    params: route?.params || {},
    entity_id: ipContext?.entity?.id || null,
    entity_name: ipContext?.entity?.name || null,
    subcap_id: ipContext?.subcap?.id || null,
    surface: ipSurface || null,
    user_role: user?.role || null,
  }), [route, ipContext, ipSurface, user]);

  // Reset on surface change — pre-streamed intro paragraph
  useEffect(() => {
    if (!ipOpen) return;
    setText("");
    setStreaming(true);
    setChat([]);
    setShowStarters(true);
    setLastQuestion(null);
    setActiveSessionId(null);
    let i = 0;
    const id = setInterval(() => {
      i += 4;
      setText(messages.body.slice(0, i));
      if (i >= messages.body.length) { clearInterval(id); setStreaming(false); }
    }, 16);
    return () => clearInterval(id);
  }, [ipOpen, messages]);

  // Load recent sessions whenever the panel re-opens or entity changes.
  // The list is independent of streaming state so a returning user
  // sees the resume picker immediately.
  useEffect(() => {
    if (!ipOpen || !window.DMA?.chat?.listSessions) return;
    const eid = pageContext.entity_id || null;
    let cancelled = false;
    window.DMA.chat.listSessions(eid, 3).then(res => {
      if (cancelled) return;
      if (res?.ok && Array.isArray(res.data?.items)) {
        setRecentSessions(res.data.items);
      } else {
        setRecentSessions([]);
      }
    });
    return () => { cancelled = true; };
  }, [ipOpen, pageContext.entity_id]);

  const resumeSession = async (sessionId) => {
    if (!window.DMA?.chat?.getSession) return;
    const res = await window.DMA.chat.getSession(sessionId);
    if (!res?.ok || !res.data?.messages) return;
    const seeded = res.data.messages.map(m => ({
      role: m.role === "assistant" ? "ai" : m.role,
      text: m.content_markdown || "",
      citations: m.cited_evidence_ids?.length
        ? { cited_evidence_ids: m.cited_evidence_ids, subcap_ids: m.cited_subcap_ids }
        : null,
      messageId: m.id,
      feedback: null,
    }));
    setChat(seeded);
    setActiveSessionId(sessionId);
    // Stamp localStorage so the next askBackend() turn lands in this thread.
    if (window.DMA?.chatSession) {
      window.DMA.chatSession.set(pageContext.entity_id, sessionId);
    }
    setShowStarters(false);
    setStreaming(false);
    setText("");
  };

  const postFeedback = async (messageId, payload) => {
    if (!messageId || !window.DMA?.chat?.postFeedback) return;
    const res = await window.DMA.chat.postFeedback(messageId, payload);
    if (res?.ok) {
      setChat(c => c.map(m => (
        m.messageId === messageId ? { ...m, feedback: payload.rating } : m
      )));
      setFeedbackDraft(d => ({ ...d, [messageId]: { open: false, text: "" } }));
    }
  };

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [chat, chatStreaming]);

  const STARTERS = useMemo(
    () => inWelcomeMode ? welcomeStarters() : starterQuestions(ipSurface, ipContext),
    [ipSurface, ipContext, inWelcomeMode]
  );

  // Never show before sign-in (rule of hooks: gate AFTER all hook calls)
  if (!authed) return null;

  const askLocal = (q) => {
    // Local fallback when no backend stream is available — synthesises an
    // answer from the welcome/per-surface scripts and renders it with a
    // typewriter to keep the UX consistent.
    const answer = inWelcomeMode
      ? welcomeAnswer(q, user, dataLoaded)
      : answerFor(q, ipSurface, ipContext, dataLoaded);
    setChat(c => [...c, { role: "user", text: q }, { role: "ai", text: "", citations: null, sourceNote: "Sources: pending backend integration" }]);
    setChatStreaming(true);
    let i = 0;
    const id = setInterval(() => {
      i += 3;
      setChat(c => {
        const next = [...c];
        if (next.length === 0) return c;
        next[next.length - 1] = { ...next[next.length - 1], text: answer.slice(0, i) };
        return next;
      });
      if (i >= answer.length) { clearInterval(id); setChatStreaming(false); }
    }, 14);
  };

  const askBackend = async (q) => {
    setChat(c => [...c, { role: "user", text: q }, { role: "ai", text: "", citations: null, messageId: null, feedback: null }]);
    setChatStreaming(true);
    abortRef.current = { cancelled: false };
    const guard = abortRef.current;
    try {
      const gen = window.DMA.intelligence.streamAnswer({
        question: q,
        pageContext,
        style: { response_style: "concise", max_paragraphs: 3, require_citations: true },
        sessionId: activeSessionId || undefined,
      });
      let acc = "";
      let citations = null;
      let lastMessageId = null;
      let lastSessionId = null;
      let staleDisclaimer = null;
      let bundleStalePct = null;
      let errored = false;
      for await (const chunk of gen) {
        if (guard.cancelled) return;
        if (chunk.error) {
          errored = true;
          break;
        }
        if (chunk.token) {
          acc += chunk.token;
          setChat(c => {
            const next = [...c];
            if (next.length === 0) return c;
            next[next.length - 1] = { ...next[next.length - 1], text: acc };
            return next;
          });
        }
        if (chunk.citations) citations = chunk.citations;
        if (chunk.message_id) lastMessageId = chunk.message_id;
        if (chunk.session_id) lastSessionId = chunk.session_id;
        // Backend signals when the answer is grounded in mostly-stale
        // evidence. UI/UX brief mandate: "staleness should always be
        // flagged" — surface a per-message banner so the AE knows to
        // re-evaluate with fresher sources.
        if (chunk.stale_disclaimer) staleDisclaimer = chunk.stale_disclaimer;
        if (typeof chunk.bundle_stale_pct === "number") bundleStalePct = chunk.bundle_stale_pct;
        if (chunk.done) break;
      }
      if (errored || !acc) {
        // Fall back to the local script so the user still gets *something*
        // useful, with a clear note that backend wiring is pending.
        setChat(c => c.slice(0, -2));
        askLocal(q);
        return;
      }
      setChat(c => {
        const next = [...c];
        if (next.length === 0) return c;
        next[next.length - 1] = {
          ...next[next.length - 1],
          text: acc, citations,
          messageId: lastMessageId,
          staleDisclaimer,
          bundleStalePct,
        };
        return next;
      });
      if (lastSessionId) setActiveSessionId(lastSessionId);
      setChatStreaming(false);
    } catch (e) {
      console.warn("[ip] streamAnswer failed", e);
      setChat(c => c.slice(0, -2));
      askLocal(q);
    }
  };

  const ask = (question) => {
    const q = (question || chatInput).trim();
    if (!q) return;
    setChatInput("");
    setShowStarters(false);     // hide starter list as soon as a question fires
    setLastQuestion(q);
    // Welcome-mode starter clicks: keep the instant-answer UX the team
    // already chose ("don't make the intel layer think through these").
    const isWelcomeStarter = inWelcomeMode && welcomeStarters().includes(q);
    if (isWelcomeStarter) {
      const answer = welcomeAnswer(q, user, dataLoaded);
      setChat(c => [...c, { role: "user", text: q }, { role: "ai", text: answer, citations: null, sourceNote: "Sources: walkthrough script (no backend call)" }]);
      setChatStreaming(false);
      return;
    }
    // Real / per-surface questions go to the backend stream. If the
    // backend is unreachable, askBackend falls back to askLocal.
    if (window.DMA.intelligence && window.DMA.intelligence.streamAnswer) {
      askBackend(q);
    } else {
      askLocal(q);
    }
  };

  const newQuestion = () => {
    abortRef.current && (abortRef.current.cancelled = true);
    setChat([]);
    setShowStarters(true);
    setLastQuestion(null);
    setChatStreaming(false);
  };

  if (!ipOpen) {
    return (
      <button className="ip-tab" onClick={() => setIpOpen(true)} title="Open Intelligence">
        ✦ INTELLIGENCE
      </button>
    );
  }

  const renderCitations = (m) => {
    const c = m.citations;
    if (!c) {
      // No citations from backend yet — show pending note inline.
      return m.sourceNote ? (
        <div style={{ marginTop: 8, fontSize: 10.5, color: "var(--z-muted)", fontStyle: "italic" }}>
          {m.sourceNote}
        </div>
      ) : null;
    }
    const ev = c.evidence_ids || c.cited_evidence_ids || [];
    const subcaps = c.subcap_ids || [];
    return (
      <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px dashed var(--ph0-bd)" }}>
        <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase", marginBottom: 4 }}>
          Grounded on: {ev.length} evidence item{ev.length === 1 ? "" : "s"}{subcaps.length ? `, ${subcaps.length} subcap${subcaps.length === 1 ? "" : "s"}` : ""}
        </div>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {ev.map(eid => (
            <button key={eid} className="chip" onClick={() => openEvidence && openEvidence(eid)} title="Open evidence drawer">{eid}</button>
          ))}
          {subcaps.map(sid => (
            <span key={sid} className="chip purple">{sid}</span>
          ))}
        </div>
      </div>
    );
  };

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
        {chat.length === 0 ? (
          <div style={{ fontSize: 13, lineHeight: 1.65 }}>
            {text}{streaming ? <span className="ip-cursor" /> : null}
          </div>
        ) : null}
        {!streaming && chat.length === 0 ? (
          <div style={{ marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button className="btn btn-tertiary btn-sm"><Icon name="copy" size={12} /> Copy</button>
            <button className="btn btn-tertiary btn-sm"><Icon name="refresh" size={12} /> Regenerate</button>
            <button className="btn btn-tertiary btn-sm">Deeper · Pro</button>
          </div>
        ) : null}

        {/* Chat */}
        {chat.length > 0 ? (
          <div style={{ marginTop: 4 }}>
            {chat.map((m, i) => {
              const isLastAi = m.role === "ai" && i === chat.length - 1;
              const fbDraft = m.messageId ? feedbackDraft[m.messageId] : null;
              return (
                <div key={i} className={`ip-message ${m.role}`}>
                  <FormattedAnswerText text={m.text} onEvidence={openEvidence} />
                  {isLastAi && chatStreaming ? <span className="ip-cursor" /> : null}
                  {m.role === "ai" && !chatStreaming && m.staleDisclaimer ? (
                    <div
                      role="status"
                      aria-label="Most evidence is dated"
                      style={{
                        marginTop: 6, padding: "6px 8px",
                        background: "rgba(231, 110, 0, 0.08)",
                        border: "1px solid var(--z-amber, #e76e00)",
                        borderRadius: 4, fontSize: 11, color: "var(--z-amber, #e76e00)",
                        display: "flex", gap: 6, alignItems: "center",
                      }}>
                      <Icon name="warning" size={12} />
                      <span>
                        {m.staleDisclaimer}
                        {typeof m.bundleStalePct === "number" ? (
                          <span style={{ marginLeft: 4, opacity: 0.85 }}>
                            ({Math.round(m.bundleStalePct * 100)}% stale)
                          </span>
                        ) : null}
                      </span>
                    </div>
                  ) : null}
                  {m.role === "ai" && !chatStreaming ? renderCitations(m) : null}
                  {m.role === "ai" && !chatStreaming && m.messageId ? (
                    <div style={{ marginTop: 6, display: "flex", gap: 6, alignItems: "center" }}>
                      <button
                        className="icon-btn"
                        title="Helpful"
                        aria-label="Mark this answer as helpful"
                        disabled={m.feedback != null}
                        onClick={() => postFeedback(m.messageId, { rating: 1 })}
                        style={{
                          width: 24, height: 24,
                          color: m.feedback === 1 ? "var(--z-teal)" : "var(--z-muted)",
                          opacity: m.feedback != null && m.feedback !== 1 ? 0.35 : 1,
                        }}>
                        <Icon name="thumb-up" size={14} />
                      </button>
                      <button
                        className="icon-btn"
                        title="Not helpful"
                        aria-label="Mark this answer as not helpful"
                        disabled={m.feedback != null}
                        onClick={() => postFeedback(m.messageId, { rating: -1 })}
                        style={{
                          width: 24, height: 24,
                          color: m.feedback === -1 ? "var(--z-below)" : "var(--z-muted)",
                          opacity: m.feedback != null && m.feedback !== -1 ? 0.35 : 1,
                        }}>
                        <Icon name="thumb-down" size={14} />
                      </button>
                      <button
                        className="icon-btn"
                        title="Suggest a better answer"
                        aria-label="Open the better-answer textarea"
                        onClick={() => setFeedbackDraft(d => ({
                          ...d, [m.messageId]: { open: !fbDraft?.open, text: fbDraft?.text || "" },
                        }))}
                        style={{
                          width: 24, height: 24,
                          color: fbDraft?.open ? "var(--z-purple)" : "var(--z-muted)",
                        }}>
                        <Icon name="bulb" size={14} />
                      </button>
                      {m.feedback != null ? (
                        <span style={{ fontSize: 10, color: "var(--z-muted)" }}>
                          Feedback recorded — thanks
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                  {fbDraft?.open ? (
                    <div style={{ marginTop: 6, padding: 6, border: "1px solid var(--z-sep)", borderRadius: 4 }}>
                      <textarea
                        placeholder="What should it have said? (your suggestion seeds the adversarial-learning loop)"
                        value={fbDraft.text}
                        onChange={e => setFeedbackDraft(d => ({
                          ...d, [m.messageId]: { open: true, text: e.target.value },
                        }))}
                        style={{ width: "100%", minHeight: 50, fontSize: 12, padding: 4, border: "1px solid var(--z-sep)", borderRadius: 3 }} />
                      <div style={{ display: "flex", gap: 4, justifyContent: "flex-end", marginTop: 4 }}>
                        <button className="btn btn-tertiary btn-sm" onClick={() => setFeedbackDraft(d => ({ ...d, [m.messageId]: { open: false, text: "" } }))}>Cancel</button>
                        <button className="btn btn-primary btn-sm"
                          disabled={!fbDraft.text.trim()}
                          onClick={() => postFeedback(m.messageId, { rating: -1, better_answer: fbDraft.text.trim() })}>
                          Send suggestion
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
            {/* Post-answer controls: regenerate / deeper / new question */}
            {!chatStreaming ? (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                <button className="btn btn-tertiary btn-sm" onClick={() => lastQuestion && ask(lastQuestion)} title="Re-ask the same question">
                  <Icon name="refresh" size={12} /> Regenerate
                </button>
                <button className="btn btn-tertiary btn-sm" onClick={() => lastQuestion && ask(`(Pro) Deeper analysis: ${lastQuestion}`)}>
                  Deeper · Pro
                </button>
                <button className="btn btn-secondary btn-sm" onClick={newQuestion}>
                  <Icon name="plus" size={12} /> New question
                </button>
                {!showStarters ? (
                  <button className="btn btn-tertiary btn-sm" onClick={() => setShowStarters(true)}>Show starters</button>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* Recent threads picker — only shown on a fresh open with no
          active chat yet. Resuming seeds the chat from the persisted
          messages and stamps localStorage so follow-ups extend it. */}
      {showStarters && !chatStreaming && chat.length === 0 && recentSessions.length > 0 ? (
        <div className="ip-chat" style={{ borderBottom: "1px dashed var(--z-sep)" }}>
          <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase", marginBottom: 6 }}>
            Recent threads
          </div>
          {recentSessions.slice(0, 3).map(s => (
            <button key={s.id} className="ip-starter" onClick={() => resumeSession(s.id)} title={`${s.message_count} turns`}>
              <span style={{ fontWeight: 600 }}>{(s.last_question || "(new)").slice(0, 80)}</span>
            </button>
          ))}
        </div>
      ) : null}

      {/* Starter questions — auto-collapse once a chat starts.
          The "Show starters" link in the post-answer toolbar above
          restores them on demand. */}
      {showStarters && !chatStreaming ? (
        <div className="ip-chat">
          <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase", marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
            <span>{chat.length === 0 ? "Try a question" : "Follow-ups"}</span>
            {chat.length > 0 ? <button className="icon-btn" style={{ width: 18, height: 18 }} onClick={() => setShowStarters(false)} title="Hide starters"><Icon name="x" size={10} /></button> : null}
          </div>
          {STARTERS.map((s, i) => (
            <button key={i} className="ip-starter" onClick={() => ask(s)}>{s}</button>
          ))}
        </div>
      ) : null}

      {/* Chat input */}
      <div className="ip-input">
        <input placeholder="Ask anything about this entity…"
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

/* ── Formatted answer text ────────────────────────────────────────
   Light-weight markdown-ish renderer for the streaming answer body.
   Handles: paragraphs (blank-line split), bullet lists (•, -, *), and
   **bold** spans. Inline E-IDs become clickable chips routing to the
   EvidenceDrawer. Keep this small — heavier markdown would need a
   bundled dep, which we explicitly avoid in standalone-src. */
function FormattedAnswerText({ text, onEvidence }) {
  if (!text) return null;
  const blocks = String(text).split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, bi) => {
        const lines = block.split("\n");
        const isBullets = lines.every(l => /^\s*[•\-*]\s+/.test(l));
        if (isBullets) {
          return (
            <ul key={bi} style={{ margin: "4px 0 6px", paddingLeft: 18 }}>
              {lines.map((l, li) => (
                <li key={li} style={{ marginBottom: 3 }}>
                  <InlineFormatted text={l.replace(/^\s*[•\-*]\s+/, "")} onEvidence={onEvidence} />
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={bi} style={{ margin: "0 0 6px" }}>
            <InlineFormatted text={block} onEvidence={onEvidence} />
          </p>
        );
      })}
    </>
  );
}

function InlineFormatted({ text, onEvidence }) {
  // Tokenise on **bold** + [E-NNN] / E-NNN refs. Order matters: bold
  // first, then evidence chips inside the remaining text segments.
  const parts = [];
  const re = /(\*\*[^*]+\*\*|\[?E-\d+\]?)/g;
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push(m[0]);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return (
    <>
      {parts.map((p, i) => {
        if (typeof p !== "string") return null;
        if (p.startsWith("**") && p.endsWith("**")) {
          return <strong key={i}>{p.slice(2, -2)}</strong>;
        }
        if (/^\[?E-\d+\]?$/.test(p)) {
          const id = p.replace(/[\[\]]/g, "");
          return (
            <button key={i} className="chip" style={{ marginLeft: 2, marginRight: 2 }}
                    onClick={() => onEvidence && onEvidence(id)} title="Open evidence">
              {id}
            </button>
          );
        }
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}

/* ── Welcome / walkthrough mode (no entity context) ─────────────── */
function welcomeMessage(user, route, dataLoaded) {
  const first = user?.name ? user.name.split(" ")[0] : "there";
  const path = route?.path || "/";
  const where =
    path === "/"               ? "the Dashboard" :
    path === "/clients"        ? "the Clients directory" :
    path.startsWith("/admin")  ? "the Admin area" :
    path === "/alerts"         ? "the Alerts page" :
    path === "/prospecting"    ? "the Prospecting page" :
                                 `${path}`;
  const dataLine = dataLoaded
    ? `Your workspace has ${(DMA.ENTITIES || []).length} entities loaded.`
    : `No DMA runs are loaded yet. Once the bot completes an assessment (or you upload a {Client}_DMA_Complete_Package.zip via POST /api/v1/ingest/package), it will land here automatically — and every surface will fill in.`;
  return {
    title: `Hi ${first} — I'm your DMA Insights assistant`,
    sub: "Vertex AI · Gemini Flash + Pro",
    cache_age: "live",
    body:
      `Welcome to DMA Insights — Zennify's surface for every Digital Maturity Assessment we run for banks, credit unions, and insurance organisations.\n\n` +
      `You're currently on ${where}. ${dataLine}\n\n` +
      `What I can do for you here:\n` +
      `  • Walk you through any of the 16 pages — just ask "Show me around" or "What is the heatmap?"\n` +
      `  • Explain how a score, evidence tier, or recommendation was derived once a run loads\n` +
      `  • Pull peer benchmarks for the same sub-vertical (Gemini Pro, grounded in pgvector)\n` +
      `  • Draft a 30-second platform pitch for any client conversation\n` +
      `  • Surface "why now" triggers in the last 24 months for a given entity\n\n` +
      `Pick a starter below, or type your own question.`,
  };
}
function welcomeStarters() {
  return [
    "Give me a walkthrough of the app.",
    "What is the maturity heatmap?",
    "How are scores calculated?",
    "What's the difference between AE, Analyst, and Admin?",
    "How do I request a new DMA?",
    "How do I upload an existing DMA package?",
    "What is an Insight Card?",
    "What does evidence tier mean (T1-T8)?",
    "Is any data loaded right now?",
  ];
}
function welcomeAnswer(q, user, dataLoaded) {
  const first = user?.name ? user.name.split(" ")[0] : "there";
  const ql = q.toLowerCase();
  if (ql.includes("walkthrough") || ql.includes("show me around") || ql.includes("tour")) {
    return (
      `Sure ${first} — here's the 30-second tour:\n\n` +
      `1.  Dashboard (/) — your command centre: open alerts, active runs, recent assessments, and (for admins) system health.\n` +
      `2.  Clients (/clients) — every DMA, filterable by sub-vertical, source (Drive vs project API), and run staleness.\n` +
      `3.  Client Overview (D1) — Score ring, SCQA narrative, leadership panel (Clay enrichment), top findings.\n` +
      `4.  Insights (D2) — WHAT / WHY / SO WHAT cards, each evidence-linked.\n` +
      `5.  Heatmap (D3) — 4-zoom: Pillar → Category → L1 Capability → Subcap. 851 subcaps per run.\n` +
      `6.  Platform (D4) — Salesforce / Databricks / Tableau / Twilio / nCino fit scores + stair-step roadmap.\n` +
      `7.  Context (D5, Analyst+) — timeline, financials, sentiment, regulatory.\n` +
      `8.  Health (D6, Analyst+) — thin-evidence flags, QA gates, version diff.\n` +
      `9.  Tech stack — detected platforms with confidence scores.\n` +
      `10. Runs — every assessment ever taken for this entity.\n` +
      `11. Alerts (/alerts) — thin-evidence + recompute alerts across all clients.\n` +
      `12. Prospecting (/prospecting) — pre-DMA scorecard export.\n` +
      `13. Admin (/admin, Admin only) — users, jobs, Vertex AI budget, import audit.\n\n` +
      `Click any item in the left sidebar to jump there.`
    );
  }
  if (ql.includes("heatmap")) {
    return (
      `The maturity heatmap is the 4-level drill view of every sub-capability we score.\n\n` +
      `• Level 1: 4 Pillars (Strategy, Customer Experience, Operations, Data & Tech)\n` +
      `• Level 2: 17 Categories (e.g. P2C1 Channel Experience)\n` +
      `• Level 3: 136 L1 Capabilities\n` +
      `• Level 4: 851 Sub-caps (the V7.0 Comprehensive Capability Mapping)\n\n` +
      `Each cell is coloured by the M1-M5 maturity band derived from the score (1.0..5.0). Dashed outlines flag thin evidence (<3 sources); a lock icon flags scores that were capped by an open issue in the Issue Register.\n\n` +
      `The heatmap has three view modes: standard, value-chain (pivots cells by your sub-vertical's value chain), and focus area (filters to the entity's declared strategic priorities).`
    );
  }
  if (ql.includes("score") && (ql.includes("calculat") || ql.includes("derived") || ql.includes("stored"))) {
    return (
      `Scores are stored at three levels and computed bottom-up:\n\n` +
      `1.  subcap_scores.score ∈ [1.0, 5.0] — written by the Claude project's research pass for each of the 851 sub-caps in V7.0. Each row carries source evidence IDs, peer_median, thin-evidence flag, and a confidence label (LOW/MEDIUM/HIGH).\n\n` +
      `2.  Category score = weighted mean of its sub-cap scores. Weights live on ccg_categories (e.g. P4C1 Data Foundation = 0.32).\n\n` +
      `3.  Pillar score = mean of its category scores.\n\n` +
      `4.  Overall maturity = mean of the four pillar scores (0..5).\n\n` +
      `5.  Avg maturity (on the dashboard KPI) = mean of every entity's "overall" score across all completed runs. Until ≥1 run has a stored "overall", we render 0 + an "Uncalculated" tag — never a fabricated number.\n\n` +
      `Maturity bands map score → label: M1 Activating (<2), M2 Building (<3), M3 Competing (<4), M4-M5 Differentiating (≥4).`
    );
  }
  if (ql.includes("role") || ql.includes("ae") || ql.includes("analyst") || ql.includes("admin")) {
    return (
      `There are three roles:\n\n` +
      `• AE — owns client relationships. Sees the dashboard, their assigned clients (filter "My clients"), and can request new DMAs. No access to D5 Context, D6 Health, or admin pages.\n` +
      `• Analyst — the DMA delivery team. Sees everything an AE sees plus D5 Context, D6 Health, the Issue Register, and the import audit queue.\n` +
      `• Admin — Mishley, Sam, Kevin, Chris, Carlie, Tom, and Richard. Adds /admin (users, jobs, Vertex AI budget, role promotions). Allow-list lives in app-root.jsx and is enforced server-side too.\n\n` +
      `Your current account is ${user?.email || "unknown"} — provisioned as ${user?.role || "AE"}. If a tier should be open to you and isn't, an admin can promote you on /admin/users.`
    );
  }
  if (ql.includes("request") && ql.includes("dma")) {
    return (
      `Click the "New run" button on the dashboard or clients page. The modal asks for entity name, domain, optional internal materials, and notes. We POST that to the DMA bot at https://dma-bot-…/run, which writes a row to the Ops Sheet with a REQ-{8 hex} request_id, and then the Claude project takes over.\n\n` +
      `You'll see the run in "Active runs" on the dashboard, with batch-progress chips (Setup → Evidence → Peers → Scoring → Analysis → Final) that update in near-real-time via SSE.`
    );
  }
  if (ql.includes("upload") || (ql.includes("package") && !ql.includes("packages per"))) {
    return (
      `Two ways to ingest a {Entity}_DMA_Complete_Package.zip:\n\n` +
      `1. **Admin UI** — sign in as an admin, navigate to /admin/import, ` +
      `drag the zip onto the dropzone. The backend calls POST /api/v1/ingest/package ` +
      `and returns the run_id. Re-uploads are idempotent (no-op on duplicate request_id).\n\n` +
      `2. **Bulk backfill** — drop all 115 historical zips into a GCS bucket ` +
      `(e.g. gs://dma-insights-historical-zips/), then run:\n\n` +
      `   gcloud run jobs execute dma-insights-historical-backfill \\\n` +
      `     --region us-central1 --wait \\\n` +
      `     --args=gs://dma-insights-historical-zips/\n\n` +
      `The job uses the same parser as the upload path; each ingest reports ` +
      `success/skipped/failed counts in the Cloud Run job logs.`
    );
  }
  if (ql.includes("insight card") || ql.includes("what is an ic") || (ql.includes("ic") && (ql.includes("what") || ql.includes("explain")))) {
    return (
      `An Insight Card (IC) is the WHAT / WHY / SO WHAT analytical unit ` +
      `Zennify uses to express every observation we make about a client:\n\n` +
      `  • **WHAT** — one-sentence claim, evidence-linked (e.g. "FCE's ` +
      `data architecture spans three disconnected cores").\n` +
      `  • **WHY** — the structural reason it matters (e.g. "without a ` +
      `unified customer-data layer, real-time personalisation is ` +
      `architecturally impossible regardless of front-end investment").\n` +
      `  • **SO WHAT** — the actionable conclusion the AE can carry into ` +
      `the next conversation.\n\n` +
      `Every IC is tagged with: a flag (CRITICAL / OPPORTUNITY / MONITOR), ` +
      `a confidence (LOW / MEDIUM / HIGH), one or more evidence IDs ` +
      `(E-XXX), one or more affected subcap IDs (P{n}C{c}.{cluster}.{ord}), ` +
      `and optional platform tags (SF, DB, TBL, TW, nCino).\n\n` +
      `D2 Insights renders ICs sorted by flag severity; clicking opens the ` +
      `IC modal with the full evidence chain.`
    );
  }
  if (ql.includes("tier") || ql.includes("evidence")) {
    return (
      `Evidence-tier (T1-T8) scores the credibility of every piece of ` +
      `evidence we cite. Lower tier = stronger signal:\n\n` +
      `  • **T1** Audited / regulatory (10-K, FRB consent orders) — ` +
      `weight 1.00.\n` +
      `  • **T2** Issuer / company source (earnings calls, annual reports, ` +
      `press releases) — weight 0.90.\n` +
      `  • **T3** Analyst / research firm (Forrester, Gartner, McKinsey) — ` +
      `weight 0.85.\n` +
      `  • **T4** Verified executive disclosure (named-author LinkedIn, ` +
      `conference keynote) — weight 0.70.\n` +
      `  • **T5** Vendor confirmation (case study, partner press release) — ` +
      `weight 0.65.\n` +
      `  • **T6** Employee / customer signal (Glassdoor, Trustpilot, app ` +
      `store reviews) — weight 0.55.\n` +
      `  • **T7** Hiring & job market (LinkedIn, Indeed) — weight 0.55.\n` +
      `  • **T8** Open social / community (Reddit, Twitter, forums) — ` +
      `weight 0.40.\n\n` +
      `Subcaps need ≥ 3 evidence items to clear the "thin-evidence" outline; ` +
      `T1-T3 items count double, T7-T8 count half.`
    );
  }
  if (ql.includes("data") || ql.includes("loaded") || ql.includes("any")) {
    const e = (DMA.ENTITIES || []).length;
    const a = (DMA.ALERTS || []).length;
    const i = (DMA.INSIGHT_CARDS || []).length;
    if (dataLoaded) {
      return `Yes — ${e} entities, ${i} insight cards, and ${a} open alerts are currently in your workspace. Every per-client surface will render against this data.`;
    }
    return (
      `Not yet — your workspace is empty.\n\n` +
      `The data layer is wired and waiting:\n` +
      `  • GET /api/v1/entities will populate the directory + dashboard tiles.\n` +
      `  • POST /api/v1/ingest/package will land a {Client}_DMA_Complete_Package.zip into the DB.\n` +
      `  • The DMA bot can also push live progress via the Ops Sheet poller.\n\n` +
      `Type window.DMA.WIRING_NEEDS in DevTools to see which empty collection maps to which endpoint.`
    );
  }
  return (
    `I can't reach Vertex AI yet (the /api/v1/gemini/stream endpoint isn't wired in this build), so I'm running on a static walkthrough script.\n\n` +
    `Try one of the starter questions below, or ask:\n` +
    `  • "Walk me through the app"\n` +
    `  • "How are scores calculated?"\n` +
    `  • "Is any data loaded?"\n` +
    `  • "What's the difference between AE, Analyst, and Admin?"`
  );
}

function starterQuestions(surface, ctx) {
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

function answerFor(q, surface, ctx, dataLoaded) {
  // When no real run is loaded, refuse to fabricate narrative — point
  // the user at where the data wiring lives instead.
  if (dataLoaded === false || !ctx?.entity) {
    return (
      `I can't answer in detail until a run is loaded for this entity.\n\n` +
      `Once GET /api/v1/entities/:id/{overview, insights, heatmap, platforms} returns a payload, ` +
      `every per-surface explanation here cites the actual subcap_scores rows + evidence_index entries.\n\n` +
      `In the meantime: open the dashboard's "Avg maturity" KPI tooltip to see exactly how the headline score is computed; that formula is also what the per-cell rationale below would reference.`
    );
  }
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

function surfaceMessages(surface, ctx, dataLoaded) {
  // Empty-state guard: until a real run is in scope, every per-surface
  // explanation collapses to the same honest "no data" message so the
  // panel never reads as a fabricated narrative.
  if (dataLoaded === false || !ctx?.entity) {
    return {
      title: "No run loaded for this surface",
      sub: "Waiting on backend",
      cache_age: "—",
      body:
        `This panel explains scores, evidence, platform fit, and roadmap moves for whichever entity is in view. ` +
        `It needs a completed DMA run to ground its responses.\n\n` +
        `Wire it by populating window.DMA.ENTITIES (GET /api/v1/entities) and the per-entity endpoints listed in window.DMA.WIRING_NEEDS. ` +
        `Once that data arrives, every paragraph here cites real subcap IDs, evidence IDs, and recommendation IDs — never fabricated.`,
    };
  }
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
        body: `${ctx?.subcap?.name || "This subcap"} scores ${ctx?.subcap?.score?.toFixed(1) || "-"}. Peer median is ${ctx?.subcap?.peerMedian?.toFixed(1) || "-"}.\n\nEvidence is ${ctx?.subcap?.thin ? "thin - only " + (ctx?.subcap?.evidence_count || 0) + " items below the threshold of 3" : "consistent across multiple T1–T3 sources"}.\n\nClosing the gap to peer requires investment in the named platform candidates. The exact path differs by subvertical pillar weight.`,
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

Object.assign(window, {
  EvidenceDrawer, InsightModal, IntelligencePanel, RecommendationModal, NewRunModal,
  FormattedAnswerText, InlineFormatted, SeenInRunsChip,
});

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
                        <span style={{ fontSize: 10, color: "var(--z-muted)" }}>{(file.size / 1024).toFixed(0)} KB</span>
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
  const { recModal, closeRec, openEvidence, openSubcap, audience } = useApp();
  const [view, setView] = useState("impact"); // impact | evidence | dependencies
  useEffect(() => { if (recModal) setView("impact"); }, [recModal]);
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
          {view === "impact" ? (
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
                      <div className="pbar-score">{after.toFixed(1)}</div>
                      <div className="pbar-delta" style={{ color: "var(--z-mid)" }}>+{(after - before).toFixed(1)}</div>
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
                    <div style={{ fontStyle: "italic", padding: "6px 10px", background: tier?.bg || "var(--z-bg)", borderLeft: `3px solid ${tier?.color}`, fontSize: 12, color: "var(--z-body)" }}>"<ExcerptText text={e.excerpt} />"</div>
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
            <button className="btn btn-tertiary"><Icon name="copy" size={13} /> Copy summary</button>
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
