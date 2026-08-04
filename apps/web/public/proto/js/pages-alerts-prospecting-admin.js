/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Alerts, Prospecting, Admin pages
   ═══════════════════════════════════════════════════════════════════════ */

/* ── /alerts (Analyst alert dashboard) ───────────────────────────── */
function AlertsPage() {
  const {
    role,
    pushToast
  } = useApp();
  const [statusFilter, setStatusFilter] = useState("OPEN");
  const [severityFilter, setSeverityFilter] = useState("ALL");
  const [tab, setTab] = useState("alerts");
  const all = DMA.ALERTS;
  const filtered = all.filter(a => {
    if (statusFilter !== "ALL" && a.status !== statusFilter) return false;
    if (severityFilter !== "ALL" && a.severity !== severityFilter) return false;
    return true;
  });
  if (role !== "ANALYST" && role !== "ADMIN") {
    return /*#__PURE__*/React.createElement(PageShell, {
      title: "Alerts",
      crumbs: [{
        label: "Alerts"
      }]
    }, /*#__PURE__*/React.createElement("div", {
      className: "empty"
    }, /*#__PURE__*/React.createElement("div", {
      className: "icon"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "lock",
      size: 22
    })), /*#__PURE__*/React.createElement("h3", null, "Analyst access required"), /*#__PURE__*/React.createElement("p", null, "This page requires Analyst or Admin permissions.")));
  }
  return /*#__PURE__*/React.createElement(PageShell, {
    title: "Alerts",
    crumbs: [{
      label: "Alerts"
    }]
  }, /*#__PURE__*/React.createElement("div", {
    className: "page-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, "Global alert dashboard"), /*#__PURE__*/React.createElement("h1", null, "Thin-evidence alerts"), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, all.filter(a => a.status === "OPEN").length, " OPEN across ", new Set(all.map(a => a.entity_id)).size, " entities")), /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast(`Exporting ${filtered.length} alerts as CSV…`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Export CSV"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: () => pushToast("Feedback file regenerated — routed to DMA bot", "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13
  }), " Refresh feedback file"))), /*#__PURE__*/React.createElement("div", {
    className: "filter-bar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, /*#__PURE__*/React.createElement("button", {
    className: tab === "alerts" ? "on" : "",
    onClick: () => setTab("alerts")
  }, "Alerts"), /*#__PURE__*/React.createElement("button", {
    className: tab === "patterns" ? "on" : "",
    onClick: () => setTab("patterns")
  }, "Patterns"), /*#__PURE__*/React.createElement("button", {
    className: tab === "waived" ? "on" : "",
    onClick: () => setTab("waived")
  }, "Waived")), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), tab === "alerts" ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("select", {
    className: "inp",
    style: {
      maxWidth: 180
    },
    value: statusFilter,
    onChange: e => setStatusFilter(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: "ALL"
  }, "All statuses"), /*#__PURE__*/React.createElement("option", null, "OPEN"), /*#__PURE__*/React.createElement("option", null, "IN_REVIEW"), /*#__PURE__*/React.createElement("option", null, "RESOLVED")), /*#__PURE__*/React.createElement("select", {
    className: "inp",
    style: {
      maxWidth: 180
    },
    value: severityFilter,
    onChange: e => setSeverityFilter(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: "ALL"
  }, "All severities"), /*#__PURE__*/React.createElement("option", null, "HIGH"), /*#__PURE__*/React.createElement("option", null, "MEDIUM"))) : null), tab === "alerts" ? /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("table", {
    className: "tbl"
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Severity"), /*#__PURE__*/React.createElement("th", null, "Entity"), /*#__PURE__*/React.createElement("th", null, "Subcap"), /*#__PURE__*/React.createElement("th", null, "Evidence"), /*#__PURE__*/React.createElement("th", null, "Action"), /*#__PURE__*/React.createElement("th", {
    style: {
      textAlign: "right"
    }
  }, "Manage"))), /*#__PURE__*/React.createElement("tbody", null, filtered.map(a => {
    const e = DMA.getEntity(a.entity_id);
    return /*#__PURE__*/React.createElement("tr", {
      key: a.id
    }, /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("span", {
      className: `b ${a.severity === "HIGH" ? "b-below" : "b-org"}`
    }, a.severity)), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontWeight: 600,
        fontSize: 12.5
      }
    }, e?.name), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, DMA.SUBVERTICAL_LABEL[e?.subvertical])), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        fontWeight: 500
      }
    }, a.subcap_name), /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, a.subcap_id)), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        fontSize: 11
      }
    }, a.evidence_count, " / 3")), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, a.recommended_action)), /*#__PURE__*/React.createElement("td", {
      style: {
        textAlign: "right"
      }
    }, /*#__PURE__*/React.createElement("button", {
      className: "btn btn-tertiary btn-sm",
      onClick: () => navigate(`/clients/${a.entity_id}/heatmap`, {
        subcap: a.subcap_id
      })
    }, "Heatmap"), /*#__PURE__*/React.createElement("button", {
      className: "btn btn-tertiary btn-sm",
      onClick: () => pushToast(`${a.subcap_id} moved to IN_REVIEW`, "success")
    }, "Review"), /*#__PURE__*/React.createElement("button", {
      className: "btn btn-tertiary btn-sm",
      onClick: () => pushToast(`${a.subcap_id} waived — add rationale before close`, "warn")
    }, "Waive")));
  }), filtered.length === 0 ? /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", {
    colSpan: 6,
    className: "tbl-empty"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      color: "var(--z-mid)",
      fontSize: 13,
      fontWeight: 500
    }
  }, "\u2713 No open alerts matching"))) : null))) : tab === "patterns" ? /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", null, "Cross-entity pattern finder"), /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, "\u226560% subvertical concentration")), /*#__PURE__*/React.createElement("table", {
    className: "tbl"
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Pattern"), /*#__PURE__*/React.createElement("th", null, "Subvertical"), /*#__PURE__*/React.createElement("th", null, "Category"), /*#__PURE__*/React.createElement("th", null, "Cohort"), /*#__PURE__*/React.createElement("th", {
    style: {
      textAlign: "right"
    }
  }, "Action"))), /*#__PURE__*/React.createElement("tbody", null, DMA.PATTERNS.map((p, i) => /*#__PURE__*/React.createElement("tr", {
    key: i
  }, /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("strong", null, p.title)), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, DMA.SUBVERTICAL_LABEL[p.subvertical])), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("span", {
    className: "chip"
  }, p.category)), /*#__PURE__*/React.createElement("td", null, p.count, " / ", p.total, " entities"), /*#__PURE__*/React.createElement("td", {
    style: {
      textAlign: "right"
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => pushToast(`Drafting outreach campaign · ${p.title}`, "success")
  }, "Build campaign"))))))) : /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, /*#__PURE__*/React.createElement("div", {
    className: "icon"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 22
  })), /*#__PURE__*/React.createElement("h3", null, "No waived alerts"), /*#__PURE__*/React.createElement("p", null, "Waived alerts will appear here with their rationale."))));
}

/* ── /prospecting (AE self-service) ──────────────────────────────── */
function ProspectingPage() {
  const {
    pushToast
  } = useApp();
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [downloadReady, setDownloadReady] = useState(false);
  const matches = q ? DMA.ENTITIES.filter(e => e.name.toLowerCase().includes(q.toLowerCase()) && !e.in_progress).slice(0, 5) : [];
  return /*#__PURE__*/React.createElement(PageShell, {
    title: "Prospecting",
    crumbs: [{
      label: "Prospecting"
    }]
  }, /*#__PURE__*/React.createElement("div", {
    className: "page-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, "Customer-safe export"), /*#__PURE__*/React.createElement("h1", null, "Prospecting"), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, "Search \u2192 one-page scorecard \u2192 export PDF or HTML")), /*#__PURE__*/React.createElement("span", {
    className: "b b-org",
    style: {
      alignSelf: "center"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "lock",
    size: 10
  }), " CUSTOMER-SAFE MODE")), /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      maxWidth: 600
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "search",
    size: 14,
    style: {
      position: "absolute",
      top: 10,
      left: 10,
      color: "var(--z-muted)"
    }
  }), /*#__PURE__*/React.createElement("input", {
    className: "inp",
    style: {
      paddingLeft: 32,
      fontSize: 14,
      padding: "11px 14px 11px 32px"
    },
    placeholder: "Search by institution name\u2026",
    value: q,
    onChange: e => setQ(e.target.value)
  }), matches.length > 0 ? /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      top: 46,
      left: 0,
      right: 0,
      background: "#fff",
      border: "1px solid var(--z-sep)",
      borderRadius: 8,
      boxShadow: "var(--sh-lg)",
      zIndex: 5
    }
  }, matches.map(e => /*#__PURE__*/React.createElement("button", {
    key: e.id,
    style: {
      display: "flex",
      width: "100%",
      padding: "10px 14px",
      borderBottom: "1px solid var(--z-sep)",
      textAlign: "left",
      gap: 12,
      alignItems: "center"
    },
    onClick: () => {
      setPicked(e);
      setQ("");
      setDownloadReady(false);
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, e.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, DMA.SUBVERTICAL_LABEL[e.subvertical], " \xB7 ", e.hq)), /*#__PURE__*/React.createElement(MaturityChip, {
    score: e.overall
  })))) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 10,
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Recent searches: Synovus \xB7 Fulton Bank \xB7 SL Green")), picked ? /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "evidence",
    size: 16
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600,
      fontSize: 13
    }
  }, "Scorecard preview \xB7 always Customer View"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    disabled: exporting,
    onClick: () => {
      setExporting(true);
      setTimeout(() => {
        setExporting(false);
        setDownloadReady(true);
      }, 1400);
    }
  }, exporting ? /*#__PURE__*/React.createElement("span", {
    className: "row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "skel",
    style: {
      width: 12,
      height: 12,
      borderRadius: 6
    }
  }), " Generating\u2026") : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Export PDF")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: () => pushToast(`Downloaded standalone HTML scorecard · ${picked.name}`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Download HTML")), downloadReady ? /*#__PURE__*/React.createElement("div", {
    className: "co co-teal",
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 14
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "co-title"
  }, "Ready"), /*#__PURE__*/React.createElement("div", {
    className: "co-body"
  }, "Your PDF is ready - link valid for 24 hours."))) : null, /*#__PURE__*/React.createElement(ScorecardPreview, {
    e: picked
  })) : /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, /*#__PURE__*/React.createElement("div", {
    className: "icon"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "envelope",
    size: 22
  })), /*#__PURE__*/React.createElement("h3", null, "Search to begin"), /*#__PURE__*/React.createElement("p", null, "Search the institution name to load a one-page scorecard. The export is always Customer-safe - internal fields are stripped.")));
}
function ScorecardPreview({
  e
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--z-bg)",
      border: "1px solid var(--z-sep)",
      borderRadius: 12,
      padding: 24
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "flex-start",
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".1em"
    }
  }, "Zennify \xB7 DMA Scorecard"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 24,
      fontWeight: 600,
      marginTop: 4
    }
  }, e.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-muted)"
    }
  }, DMA.SUBVERTICAL_LABEL[e.subvertical], " \xB7 ", e.hq, " \xB7 ", fmtAssets(e.assets), " \xB7 Assessment ", fmtDate(e.assessment_date))), /*#__PURE__*/React.createElement(ScoreRing, {
    score: e.overall
  })), /*#__PURE__*/React.createElement("div", {
    className: "g4"
  }, DMA.PILLARS.map(p => /*#__PURE__*/React.createElement("div", {
    key: p.id,
    className: "card-tile"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, p.id), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, p.short), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 6
    }
  }, /*#__PURE__*/React.createElement(MaturityChip, {
    score: e.pillar_scores[p.id]
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, DMA.helpers.maturityLabel(e.pillar_scores[p.id])))))), /*#__PURE__*/React.createElement("div", {
    className: "sep"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      fontWeight: 600,
      marginBottom: 8
    }
  }, "Top 3 platform opportunities"), /*#__PURE__*/React.createElement("div", {
    className: "g3"
  }, Object.entries(e.oss).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([pid, score]) => /*#__PURE__*/React.createElement("div", {
    key: pid,
    className: "card-tile"
  }, /*#__PURE__*/React.createElement("strong", null, DMA.getPlatform(pid).name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 24,
      fontWeight: 200,
      color: "var(--z-teal)",
      marginTop: 4
    }
  }, score, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "/100")), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, DMA.getPlatform(pid).features.split(" · ").slice(0, 2).join(" · "))))));
}

/* ── Live import streaming panel (SSE-style progress) ────────────── */
const IMPORT_STAGES = [{
  key: "crawl",
  label: "Drive crawl",
  icon: "drive"
}, {
  key: "classify",
  label: "Classify",
  icon: "evidence"
}, {
  key: "dedupe",
  label: "Deduplicate",
  icon: "stack"
}, {
  key: "infer",
  label: "Entity inference",
  icon: "users"
}, {
  key: "ingest",
  label: "Ingest & index",
  icon: "play"
}];
const IMPORT_SCRIPT = [{
  stage: 0,
  log: "Connecting to Drive folder 1uvt3kh…2O0P",
  level: "info"
}, {
  stage: 0,
  log: "Listing candidate files…",
  c: {
    scanned: 64
  }
}, {
  stage: 0,
  log: "Found 187 candidate files in 12 subfolders",
  c: {
    scanned: 187
  }
}, {
  stage: 1,
  log: "Applying classification rules R01–R06",
  level: "info"
}, {
  stage: 1,
  log: "R03 excluded TEST_CASE_template.xlsx",
  level: "warn",
  c: {
    excluded: 1
  }
}, {
  stage: 1,
  log: "R05 excluded 4 sample / demo workbooks",
  level: "warn",
  c: {
    excluded: 5
  }
}, {
  stage: 1,
  log: "Classified 182 DMA reports · 5 excluded",
  c: {
    kept: 182
  }
}, {
  stage: 2,
  log: "Hashing content for near-duplicate detection",
  level: "info"
}, {
  stage: 2,
  log: "Collapsed 9 duplicate revisions into latest",
  c: {
    kept: 173
  }
}, {
  stage: 3,
  log: "Entity inference · 4-signal cascade",
  level: "info"
}, {
  stage: 3,
  log: "Matched “Farm Credit East” (filename + header)",
  c: {
    entities: 1
  }
}, {
  stage: 3,
  log: "Matched “Synovus Bank” (domain + content)",
  c: {
    entities: 2
  }
}, {
  stage: 3,
  log: "Matched “SL Green Realty” (firmographic)",
  c: {
    entities: 3
  }
}, {
  stage: 3,
  log: "3 low-confidence files queued for review",
  level: "warn"
}, {
  stage: 4,
  log: "Writing assessment rows to store",
  level: "info"
}, {
  stage: 4,
  log: "Indexing evidence + building intelligence cache",
  level: "info"
}, {
  stage: 4,
  log: "Import complete · 6 entities · 173 files",
  level: "ok",
  done: true
}];
function LiveImportStream() {
  const {
    pushToast
  } = useApp();
  const [idx, setIdx] = useState(0);
  const [logs, setLogs] = useState([]);
  const [counts, setCounts] = useState({
    scanned: 0,
    kept: 0,
    excluded: 0,
    entities: 0
  });
  const [running, setRunning] = useState(true);
  const [elapsed, setElapsed] = useState(0);
  const logRef = useRef(null);

  // advance through scripted events
  useEffect(() => {
    if (!running) return;
    if (idx >= IMPORT_SCRIPT.length) {
      setRunning(false);
      return;
    }
    const step = IMPORT_SCRIPT[idx];
    const t = setTimeout(() => {
      const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
      const ss = String(elapsed % 60).padStart(2, "0");
      setLogs(l => [...l, {
        ts: `${mm}:${ss}`,
        stage: step.stage,
        text: step.log,
        level: step.level || "info"
      }]);
      if (step.c) setCounts(c => ({
        ...c,
        ...step.c
      }));
      if (step.done) {
        setRunning(false);
        pushToast("Drive crawl complete · 6 entities imported", "success");
      }
      setIdx(i => i + 1);
    }, idx === 0 ? 450 : 720);
    return () => clearTimeout(t);
  }, [idx, running]);

  // elapsed clock
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(t);
  }, [running]);

  // autoscroll log to bottom
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);
  const reset = () => {
    setIdx(0);
    setLogs([]);
    setCounts({
      scanned: 0,
      kept: 0,
      excluded: 0,
      entities: 0
    });
    setElapsed(0);
    setRunning(true);
  };
  const cancel = () => {
    setRunning(false);
    pushToast("Crawl cancelled", "warn");
  };
  const activeStage = running ? Math.min(IMPORT_SCRIPT[Math.min(idx, IMPORT_SCRIPT.length - 1)]?.stage ?? 0, IMPORT_STAGES.length - 1) : IMPORT_STAGES.length - 1;
  const pct = running ? Math.min(99, Math.round(idx / IMPORT_SCRIPT.length * 100)) : 100;
  const done = !running && idx >= IMPORT_SCRIPT.length;
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");
  const levelColor = {
    info: "var(--z-muted)",
    warn: "var(--z-org)",
    ok: "var(--z-teal)"
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    style: {
      marginBottom: 16,
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "play",
    size: 14,
    style: {
      color: done ? "var(--z-teal)" : "var(--z-mid)"
    }
  }), /*#__PURE__*/React.createElement("h3", null, "Active job \xB7 IJ-10 \xB7 Drive crawl"), done ? /*#__PURE__*/React.createElement("span", {
    className: "b b-above"
  }, "COMPLETED") : /*#__PURE__*/React.createElement("span", {
    className: "b b-teal",
    style: {
      display: "inline-flex",
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "live-dot"
  }), " SSE LIVE")), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      fontVariantNumeric: "tabular-nums"
    }
  }, "Elapsed ", mm, ":", ss)), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "import-stages"
  }, IMPORT_STAGES.map((s, i) => {
    const state = i < activeStage || done ? "done" : i === activeStage && running ? "active" : i === activeStage ? "done" : "todo";
    return /*#__PURE__*/React.createElement("div", {
      key: s.key,
      className: `import-stage ${state}`
    }, /*#__PURE__*/React.createElement("div", {
      className: "import-stage-dot"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: state === "done" ? "check" : s.icon,
      size: 12
    })), /*#__PURE__*/React.createElement("div", {
      className: "import-stage-label"
    }, s.label), i < IMPORT_STAGES.length - 1 ? /*#__PURE__*/React.createElement("div", {
      className: "import-stage-bar"
    }, /*#__PURE__*/React.createElement("div", {
      className: "import-stage-bar-fill",
      style: {
        width: i < activeStage || done ? "100%" : "0%"
      }
    })) : null);
  })), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 16,
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11.5,
      fontWeight: 600,
      color: "var(--z-dark)"
    }
  }, done ? "Finished" : IMPORT_STAGES[activeStage].label), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11.5,
      color: "var(--z-muted)",
      fontVariantNumeric: "tabular-nums"
    }
  }, pct, "%")), /*#__PURE__*/React.createElement("div", {
    className: "prog"
  }, /*#__PURE__*/React.createElement("div", {
    className: "prog-fill",
    style: {
      width: `${pct}%`,
      background: done ? "var(--z-teal)" : "linear-gradient(90deg, var(--m-cmp), var(--m-bld))"
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "g4",
    style: {
      gap: 10,
      marginTop: 14
    }
  }, [{
    label: "Scanned",
    value: counts.scanned,
    color: "var(--z-mid)"
  }, {
    label: "Kept",
    value: counts.kept,
    color: "var(--z-teal)"
  }, {
    label: "Excluded",
    value: counts.excluded,
    color: "var(--z-org)"
  }, {
    label: "Entities",
    value: counts.entities,
    color: "var(--z-dpur)"
  }].map(k => /*#__PURE__*/React.createElement("div", {
    key: k.label,
    className: "card-tile",
    style: {
      padding: "10px 12px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".06em"
    }
  }, k.label), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 22,
      fontWeight: 200,
      color: k.color,
      marginTop: 2,
      fontVariantNumeric: "tabular-nums"
    }
  }, k.value)))), /*#__PURE__*/React.createElement("div", {
    ref: logRef,
    className: "import-log",
    "aria-live": "polite"
  }, logs.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "import-log-line",
    style: {
      color: "rgba(255,255,255,.4)"
    }
  }, "Awaiting first event\u2026") : null, logs.map((l, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "import-log-line"
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: "rgba(255,255,255,.35)"
    }
  }, l.ts), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "rgba(255,255,255,.3)"
    }
  }, "[", IMPORT_STAGES[l.stage].key, "]"), /*#__PURE__*/React.createElement("span", {
    style: {
      color: l.level === "warn" ? "#FEC07A" : l.level === "ok" ? "#7FE3D6" : "rgba(255,255,255,.82)"
    }
  }, l.text))), running ? /*#__PURE__*/React.createElement("div", {
    className: "import-log-line"
  }, /*#__PURE__*/React.createElement("span", {
    className: "import-cursor"
  })) : null), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 12,
      gap: 8
    }
  }, done ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary btn-sm",
    onClick: reset
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 12
  }), " Run new crawl"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => navigate("/admin/import/audit")
  }, "View audit queue ", /*#__PURE__*/React.createElement(Icon, {
    name: "arrow-r",
    size: 11
  }))) : /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: cancel
  }, "Cancel job"))));
}

/* ── Editable users & roles (Admin) ──────────────────────────────── */
function AdminUsersCard() {
  const {
    pushToast
  } = useApp();
  const [users, setUsers] = useState([{
    id: 1,
    name: "Mishley Andrade",
    email: "mishley@zennify.com",
    role: "ANALYST",
    active: true,
    last: "2 min ago"
  }, {
    id: 2,
    name: "Dev Patel",
    email: "dev@zennify.com",
    role: "ADMIN",
    active: true,
    last: "1 hr ago"
  }, {
    id: 3,
    name: "Sara Lin",
    email: "sara@zennify.com",
    role: "AE",
    active: true,
    last: "Yesterday"
  }, {
    id: 4,
    name: "Tom Reyes",
    email: "tom@zennify.com",
    role: "AE",
    active: false,
    last: "3 wk ago"
  }]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("AE");
  const setRole = (id, role) => {
    setUsers(us => us.map(u => u.id === id ? {
      ...u,
      role
    } : u));
    pushToast(`Role updated to ${role}`, "success");
  };
  const toggleActive = id => setUsers(us => us.map(u => u.id === id ? (pushToast(`${u.name} ${u.active ? "deactivated" : "reactivated"}`, u.active ? "warn" : "success"), {
    ...u,
    active: !u.active
  }) : u));
  const invite = () => {
    const email = inviteEmail.trim();
    if (!email) {
      pushToast("Enter an email to invite", "warn");
      return;
    }
    if (!/@zennify\.com$/i.test(email)) {
      pushToast("Only @zennify.com addresses can be invited", "warn");
      return;
    }
    const name = email.split("@")[0].split(".").map(s => s.charAt(0).toUpperCase() + s.slice(1)).join(" ");
    setUsers(us => [...us, {
      id: Date.now(),
      name,
      email,
      role: inviteRole,
      active: true,
      last: "Invited"
    }]);
    pushToast(`Invitation sent to ${email}`, "success");
    setInviteEmail("");
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "users",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Users & roles")), /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, users.filter(u => u.active).length, " active")), /*#__PURE__*/React.createElement("div", {
    style: {
      overflowX: "auto"
    }
  }, /*#__PURE__*/React.createElement("table", {
    className: "tbl"
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "User"), /*#__PURE__*/React.createElement("th", null, "Role"), /*#__PURE__*/React.createElement("th", null, "Last active"), /*#__PURE__*/React.createElement("th", null, "Status"), /*#__PURE__*/React.createElement("th", {
    style: {
      textAlign: "right"
    }
  }, "Action"))), /*#__PURE__*/React.createElement("tbody", null, users.map(u => /*#__PURE__*/React.createElement("tr", {
    key: u.id,
    style: {
      opacity: u.active ? 1 : 0.55
    }
  }, /*#__PURE__*/React.createElement("td", {
    "data-label": "User"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600,
      color: "var(--z-dark)"
    }
  }, u.name), /*#__PURE__*/React.createElement("div", {
    className: "f-mono",
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, u.email)), /*#__PURE__*/React.createElement("td", {
    "data-label": "Role"
  }, /*#__PURE__*/React.createElement("select", {
    className: "inp inp-sm",
    value: u.role,
    onChange: e => setRole(u.id, e.target.value),
    style: {
      maxWidth: 130
    },
    "aria-label": `Role for ${u.name}`
  }, /*#__PURE__*/React.createElement("option", {
    value: "AE"
  }, "AE"), /*#__PURE__*/React.createElement("option", {
    value: "ANALYST"
  }, "Analyst"), /*#__PURE__*/React.createElement("option", {
    value: "ADMIN"
  }, "Admin"))), /*#__PURE__*/React.createElement("td", {
    "data-label": "Last active",
    style: {
      fontSize: 11.5,
      color: "var(--z-muted)"
    }
  }, u.last), /*#__PURE__*/React.createElement("td", {
    "data-label": "Status"
  }, /*#__PURE__*/React.createElement("span", {
    className: `b ${u.active ? "b-above" : "b-muted"}`
  }, u.active ? "Active" : "Deactivated")), /*#__PURE__*/React.createElement("td", {
    "data-label": "Action",
    style: {
      textAlign: "right"
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => toggleActive(u.id)
  }, u.active ? "Deactivate" : "Reactivate"))))))), /*#__PURE__*/React.createElement("div", {
    className: "card-body",
    style: {
      borderTop: "1px solid var(--z-sep)",
      display: "flex",
      gap: 8,
      flexWrap: "wrap",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement("input", {
    className: "inp inp-sm",
    style: {
      flex: 1,
      minWidth: 200
    },
    placeholder: "name@zennify.com",
    value: inviteEmail,
    onChange: e => setInviteEmail(e.target.value),
    onKeyDown: e => {
      if (e.key === "Enter") invite();
    }
  }), /*#__PURE__*/React.createElement("select", {
    className: "inp inp-sm",
    value: inviteRole,
    onChange: e => setInviteRole(e.target.value),
    style: {
      maxWidth: 130
    },
    "aria-label": "Invite role"
  }, /*#__PURE__*/React.createElement("option", {
    value: "AE"
  }, "AE"), /*#__PURE__*/React.createElement("option", {
    value: "ANALYST"
  }, "Analyst"), /*#__PURE__*/React.createElement("option", {
    value: "ADMIN"
  }, "Admin")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary btn-sm",
    onClick: invite
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "plus",
    size: 12
  }), " Invite user")));
}

/* ── /admin home + import + audit ────────────────────────────────── */
function AdminPage() {
  const {
    role,
    pushToast
  } = useApp();
  const [scanning, setScanning] = useState(false);
  const [folder, setFolder] = useState("1uvt3kh…2O0P");
  const [schedule, setSchedule] = useState("6h");
  const [editingFolder, setEditingFolder] = useState(false);
  const [budgetCap, setBudgetCap] = useState(400);
  const [autoDowngrade, setAutoDowngrade] = useState(true);
  if (role !== "ADMIN") return /*#__PURE__*/React.createElement(PageShell, {
    title: "Admin"
  }, /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, /*#__PURE__*/React.createElement("div", {
    className: "icon"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "lock",
    size: 22
  })), /*#__PURE__*/React.createElement("h3", null, "Admin access required"), /*#__PURE__*/React.createElement("p", null, "Switch to the Admin role to manage users, ingest, and system settings.")));
  const runScan = kind => {
    setScanning(true);
    pushToast(kind === "full" ? "Full Drive rescan started" : "Delta scan started", "success");
    setTimeout(() => {
      setScanning(false);
      pushToast(`Scan complete: ${kind === "full" ? "187 files" : "3 new candidates"}`, "success");
    }, 2000);
  };
  return /*#__PURE__*/React.createElement(PageShell, {
    title: "Admin",
    crumbs: [{
      label: "Admin"
    }]
  }, /*#__PURE__*/React.createElement("div", {
    className: "page-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, "Settings & operations"), /*#__PURE__*/React.createElement("h1", null, "Admin"), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, "User management \xB7 ingest pipeline \xB7 system settings")), /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    disabled: scanning,
    onClick: () => runScan("delta")
  }, scanning ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
    className: "spinner"
  }), " Scanning\u2026") : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13
  }), " Delta scan")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: () => navigate("/admin/import")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "play",
    size: 13
  }), " Import & jobs"))), /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "users",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Pending review \xB7 Phase 0 entity inferences")), /*#__PURE__*/React.createElement("span", {
    className: "b b-org"
  }, DMA.PENDING_REVIEW.length, " entities")), /*#__PURE__*/React.createElement("div", {
    className: "card-body"
  }, DMA.PENDING_REVIEW.map(e => /*#__PURE__*/React.createElement("div", {
    key: e.id,
    className: "card-tile",
    style: {
      marginBottom: 8,
      padding: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 6,
      flexWrap: "wrap",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("strong", null, e.inferred_name), /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, DMA.SUBVERTICAL_LABEL[e.inferred_subvertical] || e.inferred_subvertical), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Confidence ", /*#__PURE__*/React.createElement("strong", {
    style: {
      color: "var(--z-mid)"
    }
  }, e.confidence.toFixed(2)))), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)"
    }
  }, "Inferred via ", /*#__PURE__*/React.createElement("strong", null, e.signal), " \xB7 source: ", /*#__PURE__*/React.createElement("span", {
    className: "f-mono"
  }, e.drive_file)), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 10,
      display: "flex",
      gap: 8,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary btn-sm",
    onClick: () => pushToast(`Confirmed ${e.inferred_name}`, "success")
  }, "Confirm"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => pushToast(`Rejected ${e.inferred_name}`, "warn")
  }, "Reject"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => navigate("/admin/import/audit")
  }, "View source")))))), /*#__PURE__*/React.createElement(AdminUsersCard, null), /*#__PURE__*/React.createElement("div", {
    className: "g2"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "drive",
    size: 16
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600,
      fontSize: 13
    }
  }, "Drive crawl"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Last crawl 2 hr ago")), /*#__PURE__*/React.createElement("label", {
    className: "field-label"
  }, "Target folder ID"), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8,
      marginBottom: 12
    }
  }, editingFolder ? /*#__PURE__*/React.createElement("input", {
    className: "inp inp-sm",
    style: {
      flex: 1
    },
    value: folder,
    autoFocus: true,
    onChange: e => setFolder(e.target.value),
    onBlur: () => {
      setEditingFolder(false);
      pushToast("Target folder updated", "success");
    },
    onKeyDown: e => {
      if (e.key === "Enter") {
        setEditingFolder(false);
        pushToast("Target folder updated", "success");
      }
    }
  }) : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
    className: "f-mono",
    style: {
      flex: 1,
      fontSize: 12,
      padding: "7px 10px",
      background: "var(--z-bg)",
      borderRadius: 6,
      border: "1px solid var(--z-sep)"
    }
  }, folder), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => setEditingFolder(true)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "edit",
    size: 12
  }), " Edit"))), /*#__PURE__*/React.createElement("label", {
    className: "field-label"
  }, "Crawl schedule"), /*#__PURE__*/React.createElement("select", {
    className: "inp inp-sm",
    value: schedule,
    onChange: e => {
      setSchedule(e.target.value);
      pushToast("Crawl schedule updated", "success");
    },
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("option", {
    value: "1h"
  }, "Every hour"), /*#__PURE__*/React.createElement("option", {
    value: "6h"
  }, "Every 6 hours"), /*#__PURE__*/React.createElement("option", {
    value: "24h"
  }, "Daily"), /*#__PURE__*/React.createElement("option", {
    value: "manual"
  }, "Manual only")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary btn-sm",
    disabled: scanning,
    onClick: () => runScan("delta")
  }, scanning ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
    className: "spinner"
  }), " Scanning\u2026") : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 12
  }), " Delta scan")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    disabled: scanning,
    onClick: () => runScan("full")
  }, "Full re-scan\u2026"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => navigate("/admin/import/audit")
  }, "Import audit \u2192"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => navigate("/admin/import")
  }, "Job history \u2192"))), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "money",
    size: 16
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600,
      fontSize: 13
    }
  }, "Vertex AI budget"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "$184 / $", budgetCap, " \xB7 ", Math.round(184 / budgetCap * 100), "%")), /*#__PURE__*/React.createElement("div", {
    className: "prog"
  }, /*#__PURE__*/React.createElement("div", {
    className: "prog-fill",
    style: {
      width: `${Math.min(100, 184 / budgetCap * 100)}%`,
      background: 184 / budgetCap > 0.8 ? "var(--z-org)" : "var(--z-teal)"
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 3,
      alignItems: "flex-end",
      height: 36,
      marginTop: 14
    }
  }, [12, 18, 9, 22, 14, 28, 19, 24, 11, 16, 21, 17].map((v, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    title: `Day ${i + 1} · $${v}`,
    style: {
      flex: 1,
      height: `${v / 28 * 100}%`,
      background: i % 3 === 2 ? "var(--z-dpur)" : "var(--z-mid)",
      borderRadius: 2,
      opacity: 0.85
    }
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      marginTop: 4
    }
  }, "Flash 76% \xB7 Pro 24% \xB7 last 12 days"), /*#__PURE__*/React.createElement("label", {
    className: "field-label",
    style: {
      marginTop: 14
    }
  }, "Monthly budget cap (USD)"), /*#__PURE__*/React.createElement("input", {
    className: "inp inp-sm",
    type: "number",
    min: "50",
    step: "50",
    value: budgetCap,
    onChange: e => setBudgetCap(Number(e.target.value) || 0),
    onBlur: () => pushToast(`Budget cap set to $${budgetCap}`, "success"),
    style: {
      marginBottom: 12
    }
  }), /*#__PURE__*/React.createElement("button", {
    className: "toggle-pill",
    onClick: () => {
      setAutoDowngrade(v => !v);
      pushToast(`Auto-downgrade to Flash ${!autoDowngrade ? "enabled" : "disabled"}`, "success");
    },
    "aria-pressed": autoDowngrade
  }, /*#__PURE__*/React.createElement("span", {
    className: `toggle-track ${autoDowngrade ? "on" : ""}`
  }, /*#__PURE__*/React.createElement("span", {
    className: "toggle-knob"
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      color: "var(--z-dark)"
    }
  }, "Auto-downgrade to Flash at 90% spend")))));
}
function ImportPage() {
  const {
    role,
    pushToast
  } = useApp();
  const [scanning, setScanning] = useState(false);
  const [tab, setTab] = useState("jobs");
  if (role !== "ADMIN") return /*#__PURE__*/React.createElement(PageShell, {
    title: "Import"
  }, /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, /*#__PURE__*/React.createElement("div", {
    className: "icon"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "lock",
    size: 22
  })), /*#__PURE__*/React.createElement("h3", null, "Admin access required")));
  const jobs = [{
    id: "IJ-09",
    kind: "Drive crawl",
    status: "COMPLETED",
    started: "Jun 4 09:12",
    files: 187,
    entities: 6,
    took: "2 m 14 s"
  }, {
    id: "IJ-08",
    kind: "Phase 1 ingest",
    status: "COMPLETED",
    started: "Jun 3 17:48",
    files: 1,
    entities: 1,
    took: "18 s"
  }, {
    id: "IJ-07",
    kind: "Drive crawl",
    status: "COMPLETED",
    started: "Jun 3 03:00",
    files: 182,
    entities: 0,
    took: "1 m 56 s"
  }, {
    id: "IJ-06",
    kind: "Catalog import",
    status: "FAILED",
    started: "Jun 2 14:22",
    files: 4,
    entities: 0,
    took: "6 s",
    err: "Invalid sheet header on P2 tab"
  }, {
    id: "IJ-05",
    kind: "Drive crawl",
    status: "COMPLETED",
    started: "Jun 2 03:00",
    files: 176,
    entities: 1,
    took: "1 m 38 s"
  }];
  return /*#__PURE__*/React.createElement(PageShell, {
    title: "Import & jobs",
    crumbs: [{
      label: "Admin",
      href: "/admin"
    }, {
      label: "Import & jobs"
    }]
  }, /*#__PURE__*/React.createElement("div", {
    className: "page-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, "Admin \xB7 ingest pipeline"), /*#__PURE__*/React.createElement("h1", null, "Import & jobs"), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, "Phase 0 Drive crawl \xB7 Phase 1 ingest payloads \xB7 V7 catalog updates")), /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    disabled: scanning,
    onClick: () => {
      setScanning(true);
      setTimeout(() => setScanning(false), 2400);
    }
  }, scanning ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
    className: "spinner"
  }), " Scanning\u2026") : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13
  }), " Delta scan")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: () => pushToast("Upload payload — drop your app_payload_v1.json file here", "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Upload payload"))), /*#__PURE__*/React.createElement("div", {
    className: "filter-bar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, /*#__PURE__*/React.createElement("button", {
    className: tab === "jobs" ? "on" : "",
    onClick: () => setTab("jobs")
  }, "Job history"), /*#__PURE__*/React.createElement("button", {
    className: tab === "drive" ? "on" : "",
    onClick: () => setTab("drive")
  }, "Drive crawl"), /*#__PURE__*/React.createElement("button", {
    className: tab === "phase1" ? "on" : "",
    onClick: () => setTab("phase1")
  }, "Phase 1 ingest"), /*#__PURE__*/React.createElement("button", {
    className: tab === "catalog" ? "on" : "",
    onClick: () => setTab("catalog")
  }, "V7 catalog"))), tab === "jobs" ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(LiveImportStream, null), /*#__PURE__*/React.createElement("div", {
    className: "card-head",
    style: {
      padding: "0 0 10px",
      border: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "evidence",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Job history")), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Last ", jobs.length, " jobs")), /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("table", {
    className: "tbl"
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Job"), /*#__PURE__*/React.createElement("th", null, "Kind"), /*#__PURE__*/React.createElement("th", null, "Started"), /*#__PURE__*/React.createElement("th", null, "Files"), /*#__PURE__*/React.createElement("th", null, "Entities"), /*#__PURE__*/React.createElement("th", null, "Took"), /*#__PURE__*/React.createElement("th", {
    style: {
      textAlign: "right"
    }
  }, "Status"))), /*#__PURE__*/React.createElement("tbody", null, jobs.map(j => /*#__PURE__*/React.createElement("tr", {
    key: j.id,
    title: j.err || ""
  }, /*#__PURE__*/React.createElement("td", {
    "data-label": "Job"
  }, /*#__PURE__*/React.createElement("span", {
    className: "chip"
  }, j.id)), /*#__PURE__*/React.createElement("td", {
    "data-label": "Kind"
  }, j.kind), /*#__PURE__*/React.createElement("td", {
    "data-label": "Started"
  }, j.started), /*#__PURE__*/React.createElement("td", {
    "data-label": "Files"
  }, j.files), /*#__PURE__*/React.createElement("td", {
    "data-label": "Entities"
  }, j.entities), /*#__PURE__*/React.createElement("td", {
    "data-label": "Took"
  }, j.took), /*#__PURE__*/React.createElement("td", {
    "data-label": "Status",
    style: {
      textAlign: "right"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `b ${j.status === "COMPLETED" ? "b-above" : j.status === "FAILED" ? "b-below" : "b-muted"}`
  }, j.status)))))))) : tab === "drive" ? /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "drive",
    size: 16
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600
    }
  }, "Drive folder \xB7 scheduled every 6 hours"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    className: "muted",
    style: {
      fontSize: 11
    }
  }, "Last crawl 2 h ago")), /*#__PURE__*/React.createElement("div", {
    className: "g3",
    style: {
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-tile"
  }, /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 10,
      textTransform: "uppercase",
      letterSpacing: ".08em"
    }
  }, "Candidates"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 22,
      fontWeight: 200,
      color: "var(--z-teal)",
      marginTop: 4
    }
  }, "187")), /*#__PURE__*/React.createElement("div", {
    className: "card-tile"
  }, /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 10,
      textTransform: "uppercase",
      letterSpacing: ".08em"
    }
  }, "Imported"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 22,
      fontWeight: 200,
      color: "var(--z-mid)",
      marginTop: 4
    }
  }, "6")), /*#__PURE__*/React.createElement("div", {
    className: "card-tile"
  }, /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 10,
      textTransform: "uppercase",
      letterSpacing: ".08em"
    }
  }, "Audit queue"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 22,
      fontWeight: 200,
      color: "var(--z-org)",
      marginTop: 4
    }
  }, DMA.IMPORT_AUDIT.length))), /*#__PURE__*/React.createElement("div", {
    className: "sep"
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => navigate("/admin/import/audit")
  }, "Open audit queue ", /*#__PURE__*/React.createElement(Icon, {
    name: "arrow-r",
    size: 12
  }))) : tab === "phase1" ? /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "play",
    size: 16
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600
    }
  }, "Phase 1 ingest"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    className: "b b-teal"
  }, "API key active")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 12.5,
      color: "var(--z-body)",
      lineHeight: 1.6
    }
  }, "Phase 1 receives ", /*#__PURE__*/React.createElement("code", null, "app_payload_v1.json"), " from the DMA Claude project on Batch 6 completion. Authenticated with a static bearer token rotated quarterly."), /*#__PURE__*/React.createElement("div", {
    className: "sep"
  }), /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "evidence",
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12
    }
  }, "Endpoint: ", /*#__PURE__*/React.createElement("code", null, "POST /api/v1/ingest/assessment"))), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 8
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast("API key rotated — new key sent via secure channel", "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13
  }), " Rotate API key"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: () => pushToast("Upload payload manually — select app_payload_v1.json", "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Upload payload manually"))) : /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "stack",
    size: 16
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600
    }
  }, "V7 capability catalog"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    className: "muted",
    style: {
      fontSize: 11
    }
  }, "Current: v7.2 \xB7 loaded May 1")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 12.5,
      color: "var(--z-body)",
      lineHeight: 1.6
    }
  }, "Updating the catalog creates a new version. Existing runs retain their original catalog reference."), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 10
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast("V7.3 catalog uploaded — new runs will use the new version", "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Upload v7.3"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast("Opening V7 catalog change log", "success")
  }, "View change log"))));
}
function ImportAuditPage() {
  const {
    pushToast
  } = useApp();
  const [tab, setTab] = useState("REVIEW");
  const items = DMA.IMPORT_AUDIT.filter(i => tab === "ALL" || i.status === tab);
  return /*#__PURE__*/React.createElement(PageShell, {
    title: "Import audit",
    crumbs: [{
      label: "Admin",
      href: "/admin"
    }, {
      label: "Import audit"
    }]
  }, /*#__PURE__*/React.createElement("div", {
    className: "page-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, "Admin \xB7 Phase 0"), /*#__PURE__*/React.createElement("h1", null, "Drive import audit"), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, "Files excluded or flagged for review during the last Drive crawl \xB7 6 rules R01\u2013R06"))), /*#__PURE__*/React.createElement("div", {
    className: "g4",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-tile"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      textTransform: "uppercase"
    }
  }, "Last crawl"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      marginTop: 4
    }
  }, "Jun 4, 09:12")), /*#__PURE__*/React.createElement("div", {
    className: "card-tile"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      textTransform: "uppercase"
    }
  }, "Candidates processed"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 22,
      fontWeight: 200,
      color: "var(--z-teal)",
      marginTop: 4
    }
  }, "187")), /*#__PURE__*/React.createElement("div", {
    className: "card-tile"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      textTransform: "uppercase"
    }
  }, "Excluded"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 22,
      fontWeight: 200,
      color: "var(--z-below)",
      marginTop: 4
    }
  }, DMA.IMPORT_AUDIT.filter(i => i.status === "EXCLUDED").length)), /*#__PURE__*/React.createElement("div", {
    className: "card-tile"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      textTransform: "uppercase"
    }
  }, "Awaiting review"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 22,
      fontWeight: 200,
      color: "var(--z-org)",
      marginTop: 4
    }
  }, DMA.IMPORT_AUDIT.filter(i => i.status === "REVIEW").length))), /*#__PURE__*/React.createElement("div", {
    className: "filter-bar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, /*#__PURE__*/React.createElement("button", {
    className: tab === "ALL" ? "on" : "",
    onClick: () => setTab("ALL")
  }, "All"), /*#__PURE__*/React.createElement("button", {
    className: tab === "REVIEW" ? "on" : "",
    onClick: () => setTab("REVIEW")
  }, "Review"), /*#__PURE__*/React.createElement("button", {
    className: tab === "EXCLUDED" ? "on" : "",
    onClick: () => setTab("EXCLUDED")
  }, "Excluded"))), /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("table", {
    className: "tbl"
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Filename"), /*#__PURE__*/React.createElement("th", null, "Rules"), /*#__PURE__*/React.createElement("th", null, "Owner"), /*#__PURE__*/React.createElement("th", null, "Modified"), /*#__PURE__*/React.createElement("th", null, "Status"), /*#__PURE__*/React.createElement("th", {
    style: {
      textAlign: "right"
    }
  }, "Action"))), /*#__PURE__*/React.createElement("tbody", null, items.map(i => /*#__PURE__*/React.createElement("tr", {
    key: i.id
  }, /*#__PURE__*/React.createElement("td", {
    "data-label": "Filename"
  }, /*#__PURE__*/React.createElement("div", {
    className: "f-mono",
    style: {
      fontSize: 11.5,
      fontWeight: 500
    }
  }, i.filename), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, i.rationale)), /*#__PURE__*/React.createElement("td", {
    "data-label": "Rules"
  }, i.rules.map(r => /*#__PURE__*/React.createElement("span", {
    key: r,
    className: "chip",
    style: {
      marginRight: 2
    }
  }, r))), /*#__PURE__*/React.createElement("td", {
    "data-label": "Owner",
    className: "f-mono",
    style: {
      fontSize: 10
    }
  }, i.owner), /*#__PURE__*/React.createElement("td", {
    "data-label": "Modified"
  }, fmtDate(i.modifiedTime)), /*#__PURE__*/React.createElement("td", {
    "data-label": "Status"
  }, /*#__PURE__*/React.createElement("span", {
    className: `b ${i.status === "REVIEW" ? "b-org" : "b-below"}`
  }, i.status)), /*#__PURE__*/React.createElement("td", {
    "data-label": "Action",
    style: {
      textAlign: "right"
    }
  }, i.status === "REVIEW" ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => pushToast(`${i.filename} imported`, "success")
  }, "Import"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => pushToast(`${i.filename} excluded`, "warn")
  }, "Exclude")) : /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "-"))))))));
}
Object.assign(window, {
  AlertsPage,
  ProspectingPage,
  AdminPage,
  ImportPage,
  ImportAuditPage
});