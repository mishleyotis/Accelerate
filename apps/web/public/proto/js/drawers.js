/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Drawer/Modal components - Evidence drawer, Insight modal,
   Intelligence panel, simple toast helpers
   ═══════════════════════════════════════════════════════════════════════ */

/* ── Evidence drawer ─────────────────────────────────────────────── */
function EvidenceDrawer() {
  const {
    evidenceDrawer,
    closeEvidence,
    role,
    audience,
    openSubcap,
    pushToast
  } = useApp();
  const [tierFilter, setTierFilter] = useState("ALL");
  if (!evidenceDrawer) return null;
  const ev = DMA.getEvidence(evidenceDrawer.evidenceId);
  const subcap = evidenceDrawer.subcap;
  const ic = evidenceDrawer.insight && DMA.getInsight(evidenceDrawer.insight);

  // Pull evidence items
  let items = [];
  if (ev) items = [ev];else if (ic) items = ic.evidence.map(id => DMA.getEvidence(id)).filter(Boolean);else if (subcap) {
    // Find evidence items that reference this subcap, plus pad to subcap.evidence_count
    items = DMA.EVIDENCE.filter(e => e.subcaps && e.subcaps.includes(subcap.id));
    if (items.length === 0) items = DMA.EVIDENCE.slice(0, Math.max(1, Math.min(subcap.evidence_count, 4)));
  }

  // Tier filter
  const filtered = tierFilter === "ALL" ? items : items.filter(it => it.tier === tierFilter);

  // Tier distribution for filter
  const dist = {};
  items.forEach(it => {
    dist[it.tier] = (dist[it.tier] || 0) + 1;
  });
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "drawer-mask",
    onClick: closeEvidence
  }), /*#__PURE__*/React.createElement("div", {
    className: "drawer"
  }, /*#__PURE__*/React.createElement("div", {
    className: "drawer-head"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0,
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 6,
      alignItems: "center",
      marginBottom: 4,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-teal"
  }, "EVIDENCE"), subcap ? /*#__PURE__*/React.createElement("span", {
    className: "chip purple"
  }, subcap.id) : null, ev ? /*#__PURE__*/React.createElement("span", {
    className: `tier-chip tier-${ev.tier}`
  }, ev.tier) : null), /*#__PURE__*/React.createElement("div", {
    className: "title",
    style: {
      fontSize: 14
    }
  }, subcap ? subcap.name : ic ? ic.title : ev ? ev.title : "Evidence"), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, items.length, " evidence item", items.length === 1 ? "" : "s", subcap ? ` · score ${subcap.score} · ${subcap.confidence}` : "")), /*#__PURE__*/React.createElement("button", {
    className: "icon-btn close",
    onClick: closeEvidence,
    "aria-label": "Close"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "x",
    size: 16
  }))), /*#__PURE__*/React.createElement("div", {
    className: "drawer-body"
  }, subcap && role !== "AE" && audience !== "customer" ? /*#__PURE__*/React.createElement("div", {
    className: "co co-teal",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 14
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "co-title"
  }, "Rationale"), /*#__PURE__*/React.createElement("div", {
    className: "co-body"
  }, "Score ", subcap.score.toFixed(1), " \xB7 peer median ", subcap.peerMedian.toFixed(1), ". ", subcap.thin ? "Evidence is below the threshold of 3 - flagged as thin." : "Evidence ceiling: T2 with consistent FACT-class claims."))) : null, items.length > 1 ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 5,
      flexWrap: "wrap",
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: `btn btn-tertiary btn-sm ${tierFilter === "ALL" ? "" : ""}`,
    style: {
      background: tierFilter === "ALL" ? "var(--z-dark)" : "transparent",
      color: tierFilter === "ALL" ? "#fff" : "var(--z-body)"
    },
    onClick: () => setTierFilter("ALL")
  }, "All \xB7 ", items.length), Object.entries(dist).sort().map(([t, n]) => /*#__PURE__*/React.createElement("button", {
    key: t,
    className: `tier-chip tier-${t}`,
    style: {
      opacity: tierFilter === "ALL" || tierFilter === t ? 1 : 0.45,
      cursor: "pointer"
    },
    onClick: () => setTierFilter(t === tierFilter ? "ALL" : t)
  }, t, " \xB7 ", n))) : null, filtered.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, /*#__PURE__*/React.createElement("div", {
    className: "icon"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "evidence",
    size: 20
  })), /*#__PURE__*/React.createElement("h3", null, "No evidence in this tier"), /*#__PURE__*/React.createElement("p", null, "Try another tier or clear the filter.")) : filtered.map(it => {
    const tier = DMA.getTier(it.tier);
    return /*#__PURE__*/React.createElement("div", {
      key: it.id,
      style: {
        borderBottom: "1px solid var(--z-sep)",
        padding: "12px 0"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 6,
        alignItems: "center",
        marginBottom: 6,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip"
    }, it.id), /*#__PURE__*/React.createElement("span", {
      className: `tier-chip tier-${it.tier}`,
      title: tier?.desc
    }, it.tier, " \xB7 ", tier?.label), /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, it.claim), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, it.recency), role !== "AE" && audience !== "customer" ? /*#__PURE__*/React.createElement("span", {
      style: {
        marginLeft: "auto",
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, "ERS ", /*#__PURE__*/React.createElement("strong", {
      style: {
        color: "var(--z-mid)"
      }
    }, it.ers)) : null), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600,
        color: "var(--z-dark)",
        marginBottom: 5
      }
    }, it.title), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-body)",
        lineHeight: 1.55,
        fontStyle: "italic",
        padding: "8px 10px",
        background: tier?.bg || "var(--z-bg)",
        borderLeft: `3px solid ${tier?.color || "var(--z-teal)"}`,
        borderRadius: 3
      }
    }, "\"", it.excerpt, "\""), /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 6,
        display: "flex",
        gap: 8,
        alignItems: "center",
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement("a", {
      href: `https://${it.source}`,
      target: "_blank",
      rel: "noreferrer",
      style: {
        fontSize: 11,
        color: "var(--z-mid)",
        textDecoration: "none",
        display: "inline-flex",
        alignItems: "center",
        gap: 4
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "external",
      size: 11
    }), " ", it.source_pretty || it.source), it.subcaps && it.subcaps.length > 0 ? /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement("span", null, "\xB7 supports:"), it.subcaps.slice(0, 3).map(sid => /*#__PURE__*/React.createElement("button", {
      key: sid,
      className: "chip",
      onClick: () => openSubcap(sid)
    }, sid))) : null));
  })), /*#__PURE__*/React.createElement("div", {
    className: "drawer-foot"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => {
      const lines = filtered.map(it => `${it.id} · ${it.tier} · ${it.title} — "${it.excerpt}" (${it.source_pretty || it.source})`).join("\n");
      try {
        navigator.clipboard.writeText(lines);
        pushToast(`Copied ${filtered.length} citation${filtered.length === 1 ? "" : "s"}`, "success");
      } catch (e) {
        pushToast("Couldn't access clipboard", "warn");
      }
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "copy",
    size: 13
  }), " Copy citation"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: closeEvidence
  }, "Close"))));
}

/* ── Insight card modal ──────────────────────────────────────────── */
function InsightModal() {
  const {
    insightModal,
    closeInsight,
    openEvidence,
    openSubcap,
    openRec,
    audience,
    pushToast
  } = useApp();
  const [tab, setTab] = useState("detail");
  const [note, setNote] = useState("");
  const [annStatus, setAnnStatus] = useState("ACTIONED");
  useEffect(() => {
    if (insightModal) setTab("detail");
  }, [insightModal]);
  if (!insightModal) return null;
  const ic = DMA.getInsight(insightModal);
  if (!ic) return null;
  const rec = ic.rec ? DMA.getRecommendation(ic.rec) : null;
  const platform = ic.platforms[0] ? DMA.getPlatform(ic.platforms[0]) : null;
  return /*#__PURE__*/React.createElement("div", {
    className: "modal-mask",
    onClick: closeInsight
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal",
    onClick: e => e.stopPropagation(),
    style: {
      width: 820
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal-head"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 6,
      alignItems: "center",
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `b ${ic.flag === "CRITICAL" ? "b-below" : ic.flag === "OPPORTUNITY" ? "b-org" : "b-teal"}`
  }, ic.flag), /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, ic.pillar), /*#__PURE__*/React.createElement("span", {
    className: "chip"
  }, ic.id), platform ? /*#__PURE__*/React.createElement("span", {
    className: "b b-teal"
  }, platform.name) : null, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Confidence \xB7 ", ic.confidence)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 17,
      fontWeight: 600,
      color: "var(--z-dark)",
      letterSpacing: "-.005em"
    }
  }, ic.title)), /*#__PURE__*/React.createElement("button", {
    className: "icon-btn",
    onClick: closeInsight
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "x",
    size: 18
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      padding: "0 22px",
      borderBottom: "1px solid var(--z-sep)"
    }
  }, ["detail", "evidence", "annotations", "linked"].map(t => /*#__PURE__*/React.createElement("button", {
    key: t,
    className: `client-tab`,
    style: {
      background: "transparent",
      color: tab === t ? "var(--z-teal)" : "var(--z-muted)",
      borderBottom: tab === t ? "2px solid var(--z-teal)" : "2px solid transparent"
    },
    onClick: () => setTab(t)
  }, t[0].toUpperCase() + t.slice(1), t === "annotations" && ic.annotation ? " · 1" : ""))), /*#__PURE__*/React.createElement("div", {
    className: "modal-body"
  }, tab === "detail" ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Block, {
    title: "WHAT",
    body: ic.what,
    evIds: ic.evidence,
    onEv: openEvidence
  }), /*#__PURE__*/React.createElement(Block, {
    title: "WHY",
    body: ic.why
  }), /*#__PURE__*/React.createElement(Block, {
    title: "SO WHAT",
    body: ic.so_what,
    accent: true
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--z-lav)",
      borderRadius: 8,
      padding: "12px 14px",
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: ".1em",
      color: "var(--z-muted)",
      marginBottom: 8,
      textTransform: "uppercase"
    }
  }, "Affects \xB7 ", ic.affects.length, " capabilities"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: 6
    }
  }, ic.affects.map(sid => /*#__PURE__*/React.createElement("button", {
    key: sid,
    className: "chip purple",
    onClick: () => openSubcap(sid)
  }, sid)))), rec && audience !== "customer" ? /*#__PURE__*/React.createElement("div", {
    className: "co co-teal",
    style: {
      marginTop: 12,
      cursor: "pointer"
    },
    onClick: () => {
      closeInsight();
      openRec(rec.id);
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "platform",
    size: 14
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "co-title"
  }, "Linked recommendation \xB7 click for impact"), /*#__PURE__*/React.createElement("div", {
    className: "co-body"
  }, /*#__PURE__*/React.createElement("strong", null, rec.id), " - ", rec.title, ". ", DMA.getPlatform(rec.platform).name, " \xB7 ", rec.feature, " \xB7 ", rec.phase, ".")), /*#__PURE__*/React.createElement(Icon, {
    name: "arrow-r",
    size: 14,
    style: {
      color: "var(--z-mid)"
    }
  })) : null) : tab === "evidence" ? /*#__PURE__*/React.createElement("div", null, ic.evidence.map(eid => {
    const e = DMA.getEvidence(eid);
    if (!e) return null;
    return /*#__PURE__*/React.createElement("div", {
      key: eid,
      style: {
        padding: "12px 0",
        borderBottom: "1px solid var(--z-sep)"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 8,
        alignItems: "center",
        marginBottom: 6
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip"
    }, e.id), /*#__PURE__*/React.createElement("span", {
      className: "b b-muted"
    }, e.tier), /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, e.claim), /*#__PURE__*/React.createElement("span", {
      style: {
        marginLeft: "auto",
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, e.recency, " \xB7 ERS ", e.ers)), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600,
        marginBottom: 4
      }
    }, e.title), /*#__PURE__*/React.createElement("div", {
      style: {
        fontStyle: "italic",
        padding: "6px 10px",
        background: "var(--z-bg)",
        borderLeft: "2px solid var(--z-teal)",
        fontSize: 12,
        color: "var(--z-body)"
      }
    }, "\"", e.excerpt, "\""));
  })) : tab === "annotations" ? /*#__PURE__*/React.createElement("div", null, ic.annotation ? /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--z-lav)",
      borderRadius: 8,
      padding: 14,
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8,
      alignItems: "center",
      marginBottom: 6,
      fontSize: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "sb-avatar",
    style: {
      width: 22,
      height: 22,
      fontSize: 9
    }
  }, "MO"), /*#__PURE__*/React.createElement("strong", null, ic.annotation.author), /*#__PURE__*/React.createElement("span", {
    className: "b b-teal"
  }, ic.annotation.role), /*#__PURE__*/React.createElement("span", {
    className: "b b-above"
  }, ic.annotation.status), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto",
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, ic.annotation.when)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      color: "var(--z-body)",
      lineHeight: 1.55
    }
  }, ic.annotation.body)) : /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      marginBottom: 12,
      fontSize: 12
    }
  }, "No annotations yet."), /*#__PURE__*/React.createElement("div", {
    className: "field-group"
  }, /*#__PURE__*/React.createElement("label", {
    className: "inp-label"
  }, "Add a note"), /*#__PURE__*/React.createElement("textarea", {
    className: "inp",
    rows: 4,
    placeholder: "Discussed with Delivery Lead before the call\u2026",
    value: note,
    onChange: e => setNote(e.target.value)
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8,
      marginTop: 8,
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement("select", {
    className: "inp",
    style: {
      maxWidth: 180
    },
    value: annStatus,
    onChange: e => setAnnStatus(e.target.value)
  }, /*#__PURE__*/React.createElement("option", null, "ACTIONED"), /*#__PURE__*/React.createElement("option", null, "PENDING"), /*#__PURE__*/React.createElement("option", null, "SUPERSEDED")), /*#__PURE__*/React.createElement("input", {
    className: "inp",
    style: {
      maxWidth: 220
    },
    placeholder: "Salesforce opp ID (optional)"
  }), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary btn-sm",
    onClick: () => {
      setNote("");
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 12
  }), " Save note")))) : /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-body)"
    }
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("strong", null, "Subcapabilities affected:")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: 6,
      marginBottom: 14
    }
  }, ic.affects.map(sid => /*#__PURE__*/React.createElement("span", {
    key: sid,
    className: "chip purple"
  }, sid))), /*#__PURE__*/React.createElement("p", {
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("strong", null, "Implicated platforms:")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 6
    }
  }, ic.platforms.map(p => /*#__PURE__*/React.createElement("span", {
    key: p,
    className: "b b-teal"
  }, DMA.getPlatform(p)?.name))))), /*#__PURE__*/React.createElement("div", {
    className: "modal-foot"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => {
      const text = `${ic.id} · ${ic.flag} · ${ic.pillar}\n${ic.title}\n\nWHAT: ${ic.what}\n\nWHY: ${ic.why}\n\nSO WHAT: ${ic.so_what}`;
      try {
        navigator.clipboard.writeText(text);
        pushToast("Insight card copied to clipboard", "success");
      } catch (e) {
        pushToast("Couldn't access clipboard", "warn");
      }
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "copy",
    size: 13
  }), " Copy card"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast(`Exporting ${ic.id} as PDF…`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Export")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: closeInsight
  }, "Close"))));
}
function Block({
  title,
  body,
  evIds,
  onEv,
  accent
}) {
  // Render body and inject tier-colored E-ID chips for any tokens like [E-047]
  const parts = [];
  let last = 0;
  const re = /\[?E-\d+\]?/g;
  let m;
  while ((m = re.exec(body)) !== null) {
    if (m.index > last) parts.push(body.slice(last, m.index));
    parts.push({
      chip: m[0].replace(/[\[\]]/g, "")
    });
    last = m.index + m[0].length;
  }
  if (last < body.length) parts.push(body.slice(last));
  const renderChip = id => {
    const ev = DMA.getEvidence(id);
    const tier = ev?.tier || "T1";
    return /*#__PURE__*/React.createElement("button", {
      key: id,
      className: `tier-chip tier-${tier}`,
      style: {
        marginLeft: 4,
        cursor: "pointer"
      },
      onClick: () => onEv && onEv(id),
      title: ev?.title
    }, id, /*#__PURE__*/React.createElement("span", {
      style: {
        fontWeight: 400,
        opacity: .65,
        marginLeft: 4
      }
    }, "\xB7", tier));
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 14,
      borderLeft: accent ? "3px solid var(--z-teal)" : "3px solid var(--z-sep)",
      paddingLeft: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: ".12em",
      color: accent ? "var(--z-mid)" : "var(--z-muted)",
      textTransform: "uppercase",
      marginBottom: 6
    }
  }, title), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13.5,
      color: "var(--z-dark)",
      lineHeight: 1.65
    }
  }, parts.map((p, i) => typeof p === "string" ? /*#__PURE__*/React.createElement("span", {
    key: i
  }, p) : renderChip(p.chip)), evIds && evIds.length ? /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: 6
    }
  }, evIds.map(eid => renderChip(eid))) : null));
}

/* ── Intelligence Panel ─────────────────────────────────────────── */
function IntelligencePanel() {
  const {
    ipOpen,
    setIpOpen,
    ipSurface,
    ipContext,
    authed,
    pushToast,
    openEvidence
  } = useApp();
  const [text, setText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [chat, setChat] = useState([]); // [{role: 'user'|'ai', text}]
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
      if (i >= messages.body.length) {
        clearInterval(id);
        setStreaming(false);
      }
    }, 16);
    return () => clearInterval(id);
  }, [ipOpen, messages]);
  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [chat, chatStreaming]);
  const STARTERS = useMemo(() => starterQuestions(ipSurface, ipContext), [ipSurface, ipContext]);

  // Never show before sign-in (rule of hooks: gate AFTER all hook calls)
  if (!authed) return null;
  const ask = question => {
    const q = (question || chatInput).trim();
    if (!q) return;
    setChat(c => [...c, {
      role: "user",
      text: q
    }, {
      role: "ai",
      text: ""
    }]);
    setChatInput("");
    setChatStreaming(true);
    const answer = answerFor(q, ipSurface, ipContext);
    let i = 0;
    const id = setInterval(() => {
      i += 3;
      setChat(c => {
        const next = [...c];
        next[next.length - 1] = {
          role: "ai",
          text: answer.slice(0, i)
        };
        return next;
      });
      if (i >= answer.length) {
        clearInterval(id);
        setChatStreaming(false);
      }
    }, 14);
  };
  if (!ipOpen) {
    return /*#__PURE__*/React.createElement("button", {
      className: "ip-tab",
      onClick: () => setIpOpen(true),
      title: "Open Intelligence"
    }, "\u2726 INTELLIGENCE");
  }
  return /*#__PURE__*/React.createElement("aside", {
    className: "ip"
  }, /*#__PURE__*/React.createElement("div", {
    className: "ip-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "ai"
  }, "\u2726"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "title txt-fit-1"
  }, messages.title), /*#__PURE__*/React.createElement("div", {
    className: "sub txt-fit-1"
  }, messages.sub)), /*#__PURE__*/React.createElement("button", {
    className: "icon-btn",
    onClick: () => setIpOpen(false)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "x",
    size: 14
  }))), /*#__PURE__*/React.createElement("div", {
    ref: bodyRef,
    className: "ip-body"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      lineHeight: 1.65
    }
  }, text, streaming ? /*#__PURE__*/React.createElement("span", {
    className: "ip-cursor"
  }) : null), !streaming && ipSurface === "why_now" ? /*#__PURE__*/React.createElement(WhyNowSignals, {
    ctx: ipContext,
    openEvidence: openEvidence,
    pushToast: pushToast
  }) : null, !streaming ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 10,
      display: "flex",
      gap: 6,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => {
      try {
        navigator.clipboard.writeText(text);
        pushToast("Copied response", "success");
      } catch (e) {
        pushToast("Couldn't access clipboard", "warn");
      }
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "copy",
    size: 12
  }), " Copy"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => {
      setText("");
      setStreaming(true);
      let i = 0;
      const id = setInterval(() => {
        i += 4;
        setText(messages.body.slice(0, i));
        if (i >= messages.body.length) {
          clearInterval(id);
          setStreaming(false);
        }
      }, 16);
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 12
  }), " Regenerate"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => pushToast("Routed to Gemini Pro — deeper analysis takes ~8s", "success")
  }, "Deeper \xB7 Pro")) : null, chat.length > 0 ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14,
      paddingTop: 12,
      borderTop: "1px dashed var(--ph0-bd)"
    }
  }, chat.map((m, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: `ip-message ${m.role}`
  }, m.text, m.role === "ai" && chatStreaming && i === chat.length - 1 ? /*#__PURE__*/React.createElement("span", {
    className: "ip-cursor"
  }) : null))) : null), !chatStreaming ? /*#__PURE__*/React.createElement("div", {
    className: "ip-chat"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 9.5,
      fontWeight: 700,
      letterSpacing: ".1em",
      color: "var(--z-dpur)",
      textTransform: "uppercase",
      marginBottom: 6
    }
  }, chat.length === 0 ? "Try a question" : "Follow-ups"), STARTERS.map((s, i) => /*#__PURE__*/React.createElement("button", {
    key: i,
    className: "ip-starter",
    onClick: () => ask(s)
  }, s))) : null, /*#__PURE__*/React.createElement("div", {
    className: "ip-input"
  }, /*#__PURE__*/React.createElement("input", {
    placeholder: "Ask anything about this entity\u2026",
    value: chatInput,
    onChange: e => setChatInput(e.target.value),
    onKeyDown: e => e.key === "Enter" && ask()
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary btn-sm",
    onClick: () => ask(),
    disabled: !chatInput.trim() || chatStreaming
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "arrow-r",
    size: 12
  }))));
}
function WhyNowSignals({
  ctx,
  openEvidence,
  pushToast
}) {
  const [open, setOpen] = useState(null);
  const entId = ctx?.entity?.id || "fce-001";
  const signals = DMA.whyNowFor(entId);
  if (!signals || !signals.length) return null;
  const CAT = {
    core_migration: {
      icon: "refresh",
      color: "var(--z-teal)"
    },
    leadership: {
      icon: "users",
      color: "var(--z-dpur)"
    },
    hiring: {
      icon: "users",
      color: "var(--z-mid)"
    },
    regulatory: {
      icon: "lock",
      color: "var(--z-org)"
    },
    market: {
      icon: "stack",
      color: "var(--z-mid)"
    }
  };
  const STR = {
    STRONG: "b-teal",
    LEADING: "b-purple",
    SUPPORTING: "b-muted"
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14,
      paddingTop: 12,
      borderTop: "1px dashed var(--ph0-bd)"
    },
    "data-source": "evidence_index.json (trigger) + timeline_events.csv"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 9.5,
      fontWeight: 700,
      letterSpacing: ".1em",
      color: "var(--z-dpur)",
      textTransform: "uppercase",
      marginBottom: 8
    }
  }, "Trigger signals \xB7 click to drill in"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 6
    }
  }, signals.map(s => {
    const isOpen = open === s.id;
    const cat = CAT[s.category] || CAT.market;
    return /*#__PURE__*/React.createElement("div", {
      key: s.id,
      className: "wn-signal",
      style: {
        border: "1px solid var(--ph0-bd)",
        borderRadius: 8,
        overflow: "hidden",
        background: "rgba(255,255,255,.04)"
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setOpen(o => o === s.id ? null : s.id),
      style: {
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "9px 10px",
        background: "none",
        border: 0,
        cursor: "pointer",
        textAlign: "left"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 22,
        height: 22,
        borderRadius: 6,
        background: cat.color,
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: cat.icon,
      size: 12
    })), /*#__PURE__*/React.createElement("span", {
      style: {
        flex: 1,
        minWidth: 0,
        fontSize: 12.5,
        fontWeight: 600,
        color: "#fff"
      },
      className: "txt-fit-1"
    }, s.label), /*#__PURE__*/React.createElement("span", {
      className: `b ${STR[s.strength] || "b-muted"}`
    }, s.strength), /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-u" : "chevron-d",
      size: 13,
      style: {
        color: "rgba(255,255,255,.6)",
        flexShrink: 0
      }
    })), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        padding: "0 10px 10px",
        fontSize: 12,
        lineHeight: 1.6,
        color: "rgba(255,255,255,.85)"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 5,
        flexWrap: "wrap",
        marginBottom: 8
      }
    }, s.confidence ? /*#__PURE__*/React.createElement("span", {
      className: "b",
      style: {
        background: "rgba(255,255,255,.12)",
        color: "#fff"
      }
    }, s.confidence, " confidence") : null, s.claim ? /*#__PURE__*/React.createElement("span", {
      className: "b",
      style: {
        background: "rgba(255,255,255,.12)",
        color: "rgba(255,255,255,.85)"
      }
    }, s.claim) : null), s.metric ? /*#__PURE__*/React.createElement("div", {
      style: {
        background: "rgba(255,255,255,.06)",
        border: "1px solid rgba(255,255,255,.1)",
        borderRadius: 6,
        padding: "6px 9px",
        marginBottom: 8,
        fontSize: 11.5,
        color: "#fff",
        fontFamily: "var(--font-mono, monospace)"
      }
    }, s.metric) : null, /*#__PURE__*/React.createElement("div", {
      style: {
        marginBottom: 8
      }
    }, s.detail), s.peer_context ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 9.5,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "rgba(255,255,255,.5)",
        textTransform: "uppercase"
      }
    }, "Peer context \xB7 "), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11.5
      }
    }, s.peer_context)) : null, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        fontSize: 11,
        color: "rgba(255,255,255,.65)",
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "timeline",
      size: 11
    }), /*#__PURE__*/React.createElement("span", {
      className: "f-mono"
    }, s.timeline.date), " \xB7 ", s.timeline.event), s.play ? /*#__PURE__*/React.createElement("div", {
      style: {
        background: "rgba(39,187,175,.14)",
        borderLeft: "2px solid var(--z-teal)",
        borderRadius: 4,
        padding: "7px 9px",
        fontSize: 11.5,
        color: "#DFF6F2",
        marginBottom: 6
      }
    }, /*#__PURE__*/React.createElement("strong", {
      style: {
        color: "var(--z-teal)"
      }
    }, "Play \xB7 "), s.play) : null, /*#__PURE__*/React.createElement("div", {
      style: {
        background: "rgba(39,187,175,.14)",
        borderLeft: "2px solid var(--z-teal)",
        borderRadius: 4,
        padding: "7px 9px",
        fontSize: 11.5,
        color: "#DFF6F2",
        marginBottom: 6
      }
    }, /*#__PURE__*/React.createElement("strong", {
      style: {
        color: "var(--z-teal)"
      }
    }, "So what \xB7 "), s.impact), s.risk ? /*#__PURE__*/React.createElement("div", {
      style: {
        background: "rgba(254,151,50,.14)",
        borderLeft: "2px solid var(--z-org)",
        borderRadius: 4,
        padding: "7px 9px",
        fontSize: 11.5,
        color: "#FEDFC0",
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement("strong", {
      style: {
        color: "#FEC07A"
      }
    }, "Risk if ignored \xB7 "), s.risk) : null, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "rgba(255,255,255,.5)",
        textTransform: "uppercase",
        letterSpacing: ".08em"
      }
    }, "Evidence"), s.evidence && s.evidence.length ? s.evidence.map(eid => {
      const e = DMA.getEvidence(eid);
      return /*#__PURE__*/React.createElement("button", {
        key: eid,
        className: `tier-chip tier-${e?.tier || "T3"}`,
        style: {
          cursor: "pointer",
          border: 0
        },
        title: e ? `${e.title} · ${e.source_pretty}` : eid,
        onClick: () => {
          openEvidence(eid);
        }
      }, eid);
    }) : /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "rgba(255,255,255,.45)"
      }
    }, "Inferred \u2014 confirm in discovery"), /*#__PURE__*/React.createElement("span", {
      style: {
        flex: 1
      }
    }), /*#__PURE__*/React.createElement("span", {
      className: "b",
      style: {
        background: (CAT[s.category] || CAT.market).color,
        color: "#fff"
      }
    }, s.window))) : null);
  })));
}
function starterQuestions(surface, ctx) {
  const ent = ctx?.entity?.name || "this entity";
  switch (surface) {
    case "why_now":
      return ["What's the single most timely platform conversation?", "Which evidence is strongest for the integration window?", `Where will ${ent} be in 9 months without intervention?`];
    case "subcap_narrative":
      return ["What pulled this score down?", "Which platforms would close the gap fastest?", "Show me peer benchmarks for this subcap."];
    case "platform_story":
      return ["What are the readiness gaps blocking this platform?", "Which insight cards link to this platform?", "Give me a 30-second pitch I can use in the next meeting."];
    case "focus_area":
      return ["Which subcaps move the most if we close this focus area?", "What's the customer impact, not the technical impact?", "Show me peers that closed this focus area in the last 18 months."];
    default:
      return ["Summarise this entity in 30 seconds.", "What is the most-asked question on a first call here?", "What's our differentiation against the incumbent?"];
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
  const ent = ctx?.entity?.name || "this entity";
  switch (surface) {
    case "why_now":
      return {
        title: "Why now",
        sub: "Triggers in the last 24 months",
        cache_age: "instant",
        body: `${ent} is mid-migration from a legacy core to nCino, with target completion Q2 2026. The P4 score reflects fragmentation across three production systems, not absence of investment.\n\nTwo new C-suite hires (CTO from Wells Fargo in April; CDO in May) create a 6–9 month policy window. Five Data Cloud Architect openings posted in Q1 are a leading signal that the team is preparing for a customer-data platform decision - without yet committing to a vendor.\n\nThe right conversation today: position Salesforce Data Cloud + Databricks Lakehouse as the substrate, before a point-solution (Snowflake-only, or vendor-bundled) creates the next decade of fragmentation.`
      };
    case "subcap_narrative":
      return {
        title: "Subcap narrative",
        sub: ctx?.subcap?.id || "Heatmap selection",
        cache_age: "200ms",
        body: `${ctx?.subcap?.name || "This subcap"} scores ${ctx?.subcap?.score?.toFixed(1) || "-"}. Peer median is ${ctx?.subcap?.peerMedian?.toFixed(1) || "-"}.\n\nEvidence is ${ctx?.subcap?.thin ? "thin - only " + (ctx?.subcap?.evidence_count || 0) + " items below the threshold of 3" : "consistent across multiple T1–T3 sources"}.\n\nClosing the gap to peer requires investment in the named platform candidates. The exact path differs by subvertical pillar weight.`
      };
    case "platform_story":
      return {
        title: "Platform story",
        sub: ctx?.platform || "Highest fit",
        cache_age: "cached at ingest",
        body: `Salesforce has the strongest commercial case for ${ent}. Composite Fit Score is 82/100. The platform addresses 34 subcap gaps where confidence is high and the technology footprint is confirmed-absent.\n\nLead with Data Cloud as the foundation conversation, sequence Agentforce after the P2C2 ≥ 2.0 prerequisite is met, and use Marketing Cloud + Twilio Engage to land a customer-experience story on top.\n\nThe meeting opens with the CDO hire signal; the meeting closes with the integration window before nCino go-live.`
      };
    case "focus_area":
      return {
        title: "Focus area synthesis",
        sub: ctx?.focusArea?.name || "Strategic priority",
        cache_age: "synthesized",
        body: `${ctx?.focusArea?.name || "This focus area"} is one of ${ent}'s declared strategic priorities - the supporting quote is verbatim from the Client Profile Research Report.\n\nThe current composite maturity is below peer median; closing it requires investment across multiple subcaps that share an underlying constraint. The constraint is the same one surfaced in the related insight cards and platform fit scores.`
      };
    default:
      return {
        title: "Intelligence",
        sub: "Gemini Flash",
        cache_age: "instant",
        body: `Select a subcap, platform, focus area, or insight card to see contextual analysis here. The panel is additive - every page works without it.`
      };
  }
}
Object.assign(window, {
  EvidenceDrawer,
  InsightModal,
  IntelligencePanel,
  RecommendationModal,
  NewRunModal
});

/* ── New Run modal ──────────────────────────────────────────────── */
function NewRunModal() {
  const {
    newRunOpen,
    closeNewRun,
    pushToast
  } = useApp();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    name: "",
    website: "",
    subvertical: "REGIONAL_BANK",
    notes: "",
    files: [],
    passToDmaBot: true
  });
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => {
    if (newRunOpen) {
      setStep(1);
      setForm({
        name: "",
        website: "",
        subvertical: "REGIONAL_BANK",
        notes: "",
        files: [],
        passToDmaBot: true
      });
    }
  }, [newRunOpen]);
  if (!newRunOpen) return null;
  const valid1 = form.name.trim().length > 1 && form.website.trim().length > 3;
  const onFile = e => {
    const fs = Array.from(e.target.files || []);
    setForm(f => ({
      ...f,
      files: [...f.files, ...fs.map(file => ({
        name: file.name,
        size: file.size
      }))]
    }));
  };
  const removeFile = i => setForm(f => ({
    ...f,
    files: f.files.filter((_, x) => x !== i)
  }));
  const submit = () => {
    setSubmitting(true);
    setTimeout(() => {
      setSubmitting(false);
      pushToast(`Payload passed to DMA bot for ${form.name} - first batch in ~3 min`, "success");
      closeNewRun();
    }, 1200);
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "modal-mask",
    onClick: closeNewRun
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal",
    onClick: e => e.stopPropagation(),
    style: {
      width: 640
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal-head"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      marginBottom: 4
    }
  }, "Trigger new assessment"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 17,
      fontWeight: 600,
      color: "var(--z-dark)"
    }
  }, step === 1 ? "Entity details" : step === 2 ? "Context & files" : "Confirm")), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 6,
      marginRight: 8
    }
  }, [1, 2, 3].map(n => /*#__PURE__*/React.createElement("div", {
    key: n,
    style: {
      width: 22,
      height: 22,
      borderRadius: 11,
      fontSize: 11,
      fontWeight: 600,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: step >= n ? "var(--z-teal)" : "var(--z-sep)",
      color: step >= n ? "#fff" : "var(--z-muted)"
    }
  }, n))), /*#__PURE__*/React.createElement("button", {
    className: "icon-btn",
    onClick: closeNewRun
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "x",
    size: 18
  }))), /*#__PURE__*/React.createElement("div", {
    className: "modal-body"
  }, step === 1 ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "field-group"
  }, /*#__PURE__*/React.createElement("label", {
    className: "inp-label"
  }, "Client name ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-below)"
    }
  }, "*")), /*#__PURE__*/React.createElement("input", {
    className: "inp",
    placeholder: "e.g. Provident Bank",
    value: form.name,
    onChange: e => setForm(f => ({
      ...f,
      name: e.target.value
    }))
  })), /*#__PURE__*/React.createElement("div", {
    className: "field-group"
  }, /*#__PURE__*/React.createElement("label", {
    className: "inp-label"
  }, "Website ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-below)"
    }
  }, "*")), /*#__PURE__*/React.createElement("input", {
    className: "inp",
    placeholder: "https://provident.com",
    value: form.website,
    onChange: e => setForm(f => ({
      ...f,
      website: e.target.value
    }))
  }), /*#__PURE__*/React.createElement("div", {
    className: "inp-help"
  }, "Used as the primary entity match for Explorium technographic sync.")), /*#__PURE__*/React.createElement("div", {
    className: "field-group"
  }, /*#__PURE__*/React.createElement("label", {
    className: "inp-label"
  }, "Subvertical"), /*#__PURE__*/React.createElement("select", {
    className: "inp",
    value: form.subvertical,
    onChange: e => setForm(f => ({
      ...f,
      subvertical: e.target.value
    }))
  }, Object.entries(DMA.SUBVERTICAL_LABEL).map(([k, v]) => /*#__PURE__*/React.createElement("option", {
    key: k,
    value: k
  }, v))))) : step === 2 ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "field-group"
  }, /*#__PURE__*/React.createElement("label", {
    className: "inp-label"
  }, "Additional context (optional)"), /*#__PURE__*/React.createElement("textarea", {
    className: "inp",
    rows: 5,
    placeholder: "Anything the DMA bot should know - recent news, pending discovery items, prior conversations...",
    value: form.notes,
    onChange: e => setForm(f => ({
      ...f,
      notes: e.target.value
    })),
    style: {
      resize: "vertical"
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "field-group"
  }, /*#__PURE__*/React.createElement("label", {
    className: "inp-label"
  }, "Supporting files (optional)"), /*#__PURE__*/React.createElement("label", {
    style: {
      display: "block",
      padding: "20px 14px",
      border: "2px dashed var(--z-sep)",
      borderRadius: 8,
      textAlign: "center",
      cursor: "pointer",
      background: "var(--z-bg)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 18
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      fontWeight: 600,
      color: "var(--z-dark)",
      marginTop: 6
    }
  }, "Drop files or click to browse"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 3
    }
  }, "10-K \xB7 annual reports \xB7 prior assessment artifacts \xB7 max 50MB each"), /*#__PURE__*/React.createElement("input", {
    type: "file",
    multiple: true,
    onChange: onFile,
    style: {
      display: "none"
    }
  })), form.files.length > 0 ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 10,
      display: "flex",
      flexDirection: "column",
      gap: 6
    }
  }, form.files.map((file, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      padding: "6px 10px",
      background: "var(--z-lav)",
      borderRadius: 6
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "doc",
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      flex: 1,
      minWidth: 0
    },
    className: "txt-trunc"
  }, file.name), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, (file.size / 1024).toFixed(0), " KB"), /*#__PURE__*/React.createElement("button", {
    className: "icon-btn",
    style: {
      width: 22,
      height: 22
    },
    onClick: () => removeFile(i)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "x",
    size: 11
  }))))) : null), /*#__PURE__*/React.createElement("label", {
    className: "row",
    style: {
      fontSize: 12,
      padding: "10px 12px",
      background: "var(--z-ice)",
      borderRadius: 6,
      cursor: "pointer"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `switch ${form.passToDmaBot ? "on" : ""}`,
    onClick: () => setForm(f => ({
      ...f,
      passToDmaBot: !f.passToDmaBot
    }))
  }), /*#__PURE__*/React.createElement("span", null, "Pass payload to DMA bot site for ingestion"))) : /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "card-tile",
    style: {
      padding: 14,
      marginBottom: 12,
      background: "var(--z-ice)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 8
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 15,
    style: {
      color: "var(--z-mid)"
    }
  }), /*#__PURE__*/React.createElement("strong", {
    style: {
      fontSize: 13
    }
  }, "Ready to submit")), /*#__PURE__*/React.createElement(Row, {
    k: "Client name",
    v: form.name
  }), /*#__PURE__*/React.createElement(Row, {
    k: "Website",
    v: form.website
  }), /*#__PURE__*/React.createElement(Row, {
    k: "Subvertical",
    v: DMA.SUBVERTICAL_LABEL[form.subvertical]
  }), /*#__PURE__*/React.createElement(Row, {
    k: "Files",
    v: form.files.length === 0 ? "-" : `${form.files.length} attached`
  }), /*#__PURE__*/React.createElement(Row, {
    k: "Pass to DMA bot",
    v: form.passToDmaBot ? "Yes" : "No (manual queue)"
  }), form.notes ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "sep"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      marginBottom: 4
    }
  }, "Notes"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-body)",
      lineHeight: 1.5
    }
  }, form.notes)) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-muted)",
      lineHeight: 1.55
    }
  }, "On submit, the payload is sent to the DMA bot site. The bot will: (1) crawl public sources, (2) classify evidence into tiers, (3) score each subcap, (4) generate insight cards, (5) post results back to this app. First batch is typically available within 3 minutes."))), /*#__PURE__*/React.createElement("div", {
    className: "modal-foot"
  }, step > 1 ? /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => setStep(s => s - 1)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-l",
    size: 12
  }), " Back") : /*#__PURE__*/React.createElement("span", null), step < 3 ? /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    disabled: step === 1 && !valid1,
    onClick: () => setStep(s => s + 1)
  }, "Continue ", /*#__PURE__*/React.createElement(Icon, {
    name: "arrow-r",
    size: 12
  })) : /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    disabled: submitting,
    onClick: submit
  }, submitting ? "Submitting…" : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Icon, {
    name: "play",
    size: 12
  }), " Start assessment")))));
}
function Row({
  k,
  v
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      padding: "3px 0",
      fontSize: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-muted)"
    }
  }, k), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-dark)",
      fontWeight: 500
    }
  }, v));
}

/* ── Recommendation modal ───────────────────────────────────────── */
function RecommendationModal() {
  const {
    recModal,
    closeRec,
    openEvidence,
    openSubcap,
    audience,
    pushToast
  } = useApp();
  const [view, setView] = useState("rationale"); // rationale | impact | evidence | dependencies
  const [note, setNote] = useState("");
  useEffect(() => {
    if (recModal) setView("rationale");
  }, [recModal]);
  useEffect(() => {
    if (recModal) {
      try {
        setNote(localStorage.getItem("dma_rec_note_" + recModal) || "");
      } catch (e) {
        setNote("");
      }
    }
  }, [recModal]);
  const saveNote = v => {
    setNote(v);
    try {
      localStorage.setItem("dma_rec_note_" + recModal, v);
    } catch (e) {}
  };
  if (!recModal) return null;
  const r = DMA.getRecommendation(recModal);
  if (!r) return null;
  const plat = DMA.getPlatform(r.platform);
  const impact = DMA.ROADMAP_IMPACTS[r.id];
  const linkedSubcaps = DMA.INSIGHT_CARDS.filter(c => c.rec === r.id).flatMap(c => c.affects);
  return /*#__PURE__*/React.createElement("div", {
    className: "modal-mask",
    onClick: closeRec
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal",
    onClick: e => e.stopPropagation(),
    style: {
      width: 820
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal-head"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 6,
      alignItems: "center",
      marginBottom: 6,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "chip"
  }, r.id), /*#__PURE__*/React.createElement("span", {
    className: "b b-teal"
  }, plat?.name, " \xB7 ", r.feature), /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, r.phase), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Effort ", r.outcomes.effort, " \xB7 ", r.outcomes.time)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 17,
      fontWeight: 600,
      color: "var(--z-dark)"
    }
  }, r.title)), /*#__PURE__*/React.createElement("button", {
    className: "icon-btn",
    onClick: closeRec
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "x",
    size: 18
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      padding: "0 22px",
      borderBottom: "1px solid var(--z-sep)"
    }
  }, [["rationale", "Rationale & notes"], ["impact", "DMA impact"], ["evidence", "Root cause evidence"], ["dependencies", "Sequencing"]].map(([k, l]) => /*#__PURE__*/React.createElement("button", {
    key: k,
    className: "client-tab",
    style: {
      background: "transparent",
      color: view === k ? "var(--z-teal)" : "var(--z-muted)",
      borderBottom: view === k ? "2px solid var(--z-teal)" : "2px solid transparent"
    },
    onClick: () => setView(k)
  }, l))), /*#__PURE__*/React.createElement("div", {
    className: "modal-body"
  }, view === "rationale" ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      padding: 14,
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "sparkle",
    size: 14,
    style: {
      color: "var(--z-dpur)"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600,
      fontSize: 13
    }
  }, "Why this recommendation")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 12
    }
  }, [{
    n: "1",
    k: "Trigger",
    v: /*#__PURE__*/React.createElement(React.Fragment, null, "Surfaced by ", r.root_cause.length, " evidence item", r.root_cause.length === 1 ? "" : "s", " (", r.root_cause.map((eid, i) => /*#__PURE__*/React.createElement("span", {
      key: eid
    }, /*#__PURE__*/React.createElement("button", {
      className: "chip",
      style: {
        marginRight: 3
      },
      onClick: () => openEvidence(eid)
    }, eid))), ") showing a capability gap the client cannot close with current tooling.")
  }, {
    n: "2",
    k: "Mechanism",
    v: /*#__PURE__*/React.createElement(React.Fragment, null, plat?.name, "'s ", /*#__PURE__*/React.createElement("strong", null, r.feature), " directly addresses the root cause. It is the lowest-friction path to the target maturity because the platform footprint is already ", plat ? "present or adjacent" : "in scope", ".")
  }, {
    n: "3",
    k: "Sequencing",
    v: /*#__PURE__*/React.createElement(React.Fragment, null, "Scheduled in ", /*#__PURE__*/React.createElement("strong", null, r.phase), impact ? ` (phase ${impact.phase})` : "", ". ", impact && impact.dependencies && impact.dependencies.length ? /*#__PURE__*/React.createElement(React.Fragment, null, "Depends on ", impact.dependencies.map(d => /*#__PURE__*/React.createElement("span", {
      key: d,
      className: "chip",
      style: {
        marginRight: 3
      }
    }, d)), " landing first.") : "No prerequisites — this can land first and unblock later phases.")
  }, {
    n: "4",
    k: "Expected outcome",
    v: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("strong", null, r.outcomes.metric), " \xB7 ", r.outcomes.time, " \xB7 ", r.outcomes.effort, " effort")
  }].map(row => /*#__PURE__*/React.createElement("div", {
    key: row.n,
    style: {
      display: "flex",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 22,
      height: 22,
      borderRadius: 6,
      background: "var(--z-lav)",
      color: "var(--z-dpur)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: 11,
      fontWeight: 700,
      flexShrink: 0
    }
  }, row.n), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: ".08em",
      color: "var(--z-muted)",
      textTransform: "uppercase",
      marginBottom: 2
    }
  }, row.k), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      color: "var(--z-body)",
      lineHeight: 1.6
    }
  }, row.v)))))), /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      padding: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 8
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "edit",
    size: 14,
    style: {
      color: "var(--z-mid)"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600,
      fontSize: 13
    }
  }, "AE notes"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), note ? /*#__PURE__*/React.createElement("span", {
    className: "b b-teal"
  }, "saved locally") : null), /*#__PURE__*/React.createElement("textarea", {
    value: note,
    onChange: e => saveNote(e.target.value),
    placeholder: "Add client-specific framing, objections to handle, or discovery follow-ups for this recommendation\u2026",
    style: {
      width: "100%",
      minHeight: 96,
      resize: "vertical",
      padding: 10,
      border: "1px solid var(--z-sep)",
      borderRadius: 8,
      fontSize: 12.5,
      fontFamily: "var(--font-sans)",
      lineHeight: 1.55,
      color: "var(--z-dark)",
      boxSizing: "border-box"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 6,
      display: "flex",
      gap: 6,
      alignItems: "flex-start"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "sparkle",
    size: 11,
    style: {
      color: "var(--z-dpur)",
      flexShrink: 0,
      marginTop: 1
    }
  }), /*#__PURE__*/React.createElement("span", null, "These notes may be synthesized into future runs to make recommendations dynamic and responsive.")))) : view === "impact" ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "g3",
    style: {
      marginBottom: 14
    }
  }, Object.entries(impact?.customer_impact || {}).map(([k, v]) => /*#__PURE__*/React.createElement("div", {
    key: k,
    className: "card-tile",
    style: {
      background: "var(--z-ice)",
      padding: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-mid)",
      textTransform: "uppercase",
      letterSpacing: ".06em",
      marginBottom: 4
    }
  }, k.replace(/_/g, " ")), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 18,
      fontWeight: 700,
      color: "var(--z-dark)"
    }
  }, v)))), /*#__PURE__*/React.createElement("div", {
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
    name: "heatmap",
    size: 14
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600,
      fontSize: 13
    }
  }, "Projected pillar uplift")), impact && Object.entries(impact.after).map(([p, after]) => {
    const before = impact.before[p];
    return /*#__PURE__*/React.createElement("div", {
      key: p,
      className: "pbar",
      style: {
        pointerEvents: "none"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "pbar-name"
    }, p, " \xB7 ", DMA.PILLARS.find(x => x.id === p)?.short), /*#__PURE__*/React.createElement("div", {
      className: "pbar-track",
      style: {
        position: "relative"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "pbar-fill",
      style: {
        width: `${before / 5 * 100}%`,
        background: DMA.helpers.maturityHex(before),
        opacity: .45
      }
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        position: "absolute",
        left: 0,
        top: 0,
        height: "100%",
        width: `${after / 5 * 100}%`,
        background: DMA.helpers.maturityHex(after),
        borderRadius: 4,
        transition: "width 1.2s var(--ease)"
      }
    })), /*#__PURE__*/React.createElement("div", {
      className: "pbar-score"
    }, after.toFixed(1)), /*#__PURE__*/React.createElement("div", {
      className: "pbar-delta",
      style: {
        color: "var(--z-mid)"
      }
    }, "+", (after - before).toFixed(1)));
  })), linkedSubcaps.length > 0 ? /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      padding: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "heatmap",
    size: 14
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600,
      fontSize: 13
    }
  }, "Subcaps affected \xB7 ", linkedSubcaps.length)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: 6
    }
  }, linkedSubcaps.map(sid => /*#__PURE__*/React.createElement("button", {
    key: sid,
    className: "chip purple",
    onClick: () => {
      closeRec();
      openSubcap(sid);
    }
  }, sid)))) : null) : view === "evidence" ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 12,
      color: "var(--z-muted)",
      marginBottom: 12
    }
  }, "The root cause is grounded in the following evidence. Click any chip to open the full source."), r.root_cause.map(eid => {
    const e = DMA.getEvidence(eid);
    if (!e) return null;
    const tier = DMA.getTier(e.tier);
    return /*#__PURE__*/React.createElement("div", {
      key: eid,
      style: {
        padding: "12px 0",
        borderBottom: "1px solid var(--z-sep)"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 6
      }
    }, /*#__PURE__*/React.createElement("button", {
      className: "chip",
      onClick: () => openEvidence(eid)
    }, e.id), /*#__PURE__*/React.createElement("span", {
      className: `tier-chip tier-${e.tier}`
    }, e.tier, " \xB7 ", tier?.label), /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, e.claim), /*#__PURE__*/React.createElement("span", {
      style: {
        marginLeft: "auto",
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, e.recency, " \xB7 ERS ", e.ers)), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600,
        marginBottom: 5
      }
    }, e.title), /*#__PURE__*/React.createElement("div", {
      style: {
        fontStyle: "italic",
        padding: "6px 10px",
        background: tier?.bg || "var(--z-bg)",
        borderLeft: `3px solid ${tier?.color}`,
        fontSize: 12,
        color: "var(--z-body)"
      }
    }, "\"", e.excerpt, "\""));
  })) : /*#__PURE__*/React.createElement(DependencyMap, {
    rec: r
  })), /*#__PURE__*/React.createElement("div", {
    className: "modal-foot"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Linked from insight cards \xB7 ", DMA.INSIGHT_CARDS.filter(c => c.rec === r.id).map(c => c.id).join(", ") || "-"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => {
      const summary = `${r.id} · ${r.title}\n${plat?.name} · ${r.feature} · ${r.phase}\nEffort ${r.outcomes.effort} · ${r.outcomes.time}`;
      try {
        navigator.clipboard.writeText(summary);
        pushToast("Recommendation summary copied", "success");
      } catch (e) {
        pushToast("Couldn't access clipboard", "warn");
      }
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "copy",
    size: 13
  }), " Copy summary"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: closeRec
  }, "Close")))));
}
function DependencyMap({
  rec
}) {
  const impact = DMA.ROADMAP_IMPACTS[rec.id];
  const deps = (impact?.dependencies || []).map(id => DMA.getRecommendation(id)).filter(Boolean);
  const followups = Object.values(DMA.ROADMAP_IMPACTS).map(x => ({
    ...x,
    _id: Object.keys(DMA.ROADMAP_IMPACTS).find(k => DMA.ROADMAP_IMPACTS[k] === x)
  })).filter(x => x.dependencies.includes(rec.id));
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, "PHASE ", impact?.phase || "-"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12
    }
  }, "Sequencing position in the transformation roadmap")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 1fr 1fr",
      gap: 12,
      alignItems: "stretch"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      padding: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: ".1em",
      color: "var(--z-muted)",
      textTransform: "uppercase",
      marginBottom: 8
    }
  }, "Prerequisites"), deps.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 12
    }
  }, "No prerequisites \xB7 can land first") : deps.map(d => /*#__PURE__*/React.createElement("div", {
    key: d.id,
    style: {
      padding: "8px 10px",
      background: "var(--z-ice)",
      borderRadius: 6,
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      fontWeight: 600
    }
  }, d.id), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, d.title)))), /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      padding: 12,
      background: "var(--z-lav)",
      border: "2px solid var(--z-teal)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: ".1em",
      color: "var(--z-mid)",
      textTransform: "uppercase",
      marginBottom: 8
    }
  }, "This initiative"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 700,
      color: "var(--z-dark)"
    }
  }, rec.id), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-body)",
      marginTop: 4
    }
  }, rec.title), /*#__PURE__*/React.createElement("div", {
    className: "sep"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11
    }
  }, "Phase ", impact?.phase, " \xB7 ", rec.outcomes.time)), /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      padding: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: ".1em",
      color: "var(--z-muted)",
      textTransform: "uppercase",
      marginBottom: 8
    }
  }, "Unlocks"), followups.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 12
    }
  }, "No downstream initiatives") : followups.map(d => {
    const r = DMA.getRecommendation(d._id);
    if (!r) return null;
    return /*#__PURE__*/React.createElement("div", {
      key: d._id,
      style: {
        padding: "8px 10px",
        background: "var(--ph0-lt)",
        borderRadius: 6,
        marginBottom: 6
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        fontWeight: 600
      }
    }, r.id), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, r.title));
  }))));
}