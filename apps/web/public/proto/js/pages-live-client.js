/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Live client pages (production only)

   Production divergence, and the most important one in this app: a
   client-scoped page in production renders PROMOTED sections or an honest
   empty state — never the prototype's example content. The prototype's
   pages carry illustrative prose about a fictional bank (three cores, an
   nCino migration, named executive hires); rendered under a real client's
   name that is fabrication, so in LIVE mode those components are not
   reached at all.

   Surfaces already wired to their designed cards render as designed. A
   section this module has not yet given its card renders as a provenance
   panel — what promoted, when, by which producer version, how many
   evidence ids it cites — plus the raw promoted payload for the internal
   audience only. That is honest about the build state and still useful,
   and it is replaced surface by surface as each page's audit lands.
   ═══════════════════════════════════════════════════════════════════════ */

const LIVE_PAGE_SECTIONS = {
  overview: ["scores", "firmographics", "why_now", "exec_summary", "opportunity", "findings", "leadership", "financial_series", "sentiment", "ceilings", "evidence_coverage", "thought_leadership"],
  insights: ["insights", "landscape"],
  heatmap: ["workbook_scores", "focus_areas", "cell_evidence", "evidence", "value_chain", "alerts", "safeguard_gates", "evidence_age", "cohort_patterns"],
  platform: ["platform_story", "recommendations", "starters", "roadmap", "stairstep"],
  context: ["timeline", "issue_register", "regulatory_standing", "context_sentiment", "acquisitions"],
  techstack: ["techstack"]
};
const SECTION_TITLES = {
  scores: "Scores & peer benchmarks",
  firmographics: "Firmographics",
  why_now: "Why now",
  exec_summary: "Executive summary",
  opportunity: "Opportunity surface",
  findings: "Top findings",
  leadership: "Leadership",
  financial_series: "Financial trajectory",
  sentiment: "Sentiment",
  ceilings: "Capability ceilings & uncertainty",
  evidence_coverage: "Evidence coverage & tier mix",
  thought_leadership: "Thought leadership",
  insights: "Insight cards",
  landscape: "Technology landscape",
  workbook_scores: "Workbook grain scores",
  focus_areas: "Focus areas",
  cell_evidence: "Cell evidence",
  evidence: "Evidence store",
  value_chain: "Value chain",
  alerts: "Thin-evidence alerts",
  safeguard_gates: "Safeguard gates",
  evidence_age: "Evidence age",
  cohort_patterns: "Cross-entity patterns",
  platform_story: "Platform story",
  recommendations: "Recommendations",
  starters: "Conversation starters",
  roadmap: "Roadmap",
  stairstep: "Stair-step",
  timeline: "Timeline",
  issue_register: "Issue register",
  regulatory_standing: "Regulatory standing",
  context_sentiment: "Context sentiment",
  acquisitions: "Acquisitions",
  techstack: "Technology register"
};

/* ── O1 · the hero: composite, bands, pillar strip ────────────────── */
function LiveHero({
  data,
  entity
}) {
  const h = DMA.helpers;
  const composite = data.composite;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      alignItems: "flex-start",
      gap: 28,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: "center",
      minWidth: 150
    }
  }, /*#__PURE__*/React.createElement(ScoreRing, {
    score: composite,
    size: 130
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 8,
      fontSize: 13,
      fontWeight: 600,
      color: h.maturityHex(composite)
    }
  }, composite == null ? "No score" : h.maturityLabel(composite)), data.posture ? /*#__PURE__*/React.createElement("span", {
    className: "b b-muted",
    style: {
      marginTop: 6
    }
  }, data.posture) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 300
    }
  }, data.framing ? /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 14,
      lineHeight: 1.6,
      color: "var(--z-dark)",
      marginBottom: 14
    }
  }, data.framing) : null, (data.pillars || []).map(p => {
    const pct = p.score == null ? 0 : Math.min(100, p.score / 5 * 100);
    const label = (DMA.PILLARS.find(x => x.id === p.pillar_id) || {}).name || p.pillar_id;
    return /*#__PURE__*/React.createElement("div", {
      key: p.pillar_id,
      style: {
        marginBottom: 10
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        fontSize: 12,
        marginBottom: 4
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontWeight: 600,
        color: "var(--z-dark)"
      }
    }, label), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      className: "f-mono"
    }, p.score == null ? "—" : p.score.toFixed(1)), p.peer_median != null ? /*#__PURE__*/React.createElement("span", {
      style: {
        color: p.delta > 0 ? "var(--z-teal)" : "var(--z-org)",
        fontSize: 11
      }
    }, p.delta > 0 ? "▲" : "▼", " ", Math.abs(p.delta).toFixed(2), " vs ", p.peer_median.toFixed(1)) : /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, "no peer figure")), /*#__PURE__*/React.createElement("div", {
      className: "prog"
    }, /*#__PURE__*/React.createElement("div", {
      className: "prog-fill",
      style: {
        width: `${pct}%`,
        background: h.maturityHex(p.score)
      }
    })));
  }), data.posture_basis ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      marginTop: 10,
      lineHeight: 1.55
    }
  }, data.posture_basis) : null)));
}

/* ── O4 · executive summary (SCQA) ────────────────────────────────── */
function LiveExecSummary({
  data
}) {
  const parts = [["Situation", data.situation], ["Complication", data.complication], ["Question", data.question], ["Answer", data.answer], ["Why this order", data.sequencing_rationale], ["Cost of delay", data.cost_of_delay]].filter(([, v]) => v);
  if (!parts.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "doc",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Executive summary"))), /*#__PURE__*/React.createElement("div", {
    className: "card-body",
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 12
    }
  }, parts.map(([label, text]) => /*#__PURE__*/React.createElement("div", {
    key: label
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      marginBottom: 4
    }
  }, label), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 13,
      lineHeight: 1.65,
      color: "var(--z-body)"
    }
  }, text)))));
}

/* ── O6 · top findings, in the order they were sent ───────────────── */
function LiveFindings({
  data
}) {
  const [open, setOpen] = useState(null);
  const rows = data.findings || [];
  if (!rows.length) return null;
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
    name: "insight",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Top findings")), /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, rows.length, " \xB7 ranked by ", data.ranking_basis || "impact")), /*#__PURE__*/React.createElement("div", {
    className: "card-body"
  }, data.narrative_thread ? /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 12.5,
      color: "var(--z-body)",
      lineHeight: 1.6,
      marginBottom: 12
    }
  }, data.narrative_thread) : null, rows.map((f, i) => {
    const isOpen = open === i;
    return /*#__PURE__*/React.createElement("div", {
      key: f.f_id || i,
      className: "card-tile",
      style: {
        marginBottom: 8,
        padding: 14
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setOpen(isOpen ? null : i),
      style: {
        all: "unset",
        cursor: "pointer",
        display: "block",
        width: "100%"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 8,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip"
    }, f.f_id), f.theme ? /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, f.theme) : null, /*#__PURE__*/React.createElement("strong", {
      style: {
        fontSize: 13.5,
        color: "var(--z-dark)"
      }
    }, f.title), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), f.consequence ? /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11.5,
        color: "var(--z-mid)"
      }
    }, f.consequence) : null, /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-d" : "chevron-r",
      size: 12
    }))), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 10,
        borderTop: "1px solid var(--z-sep)",
        paddingTop: 10
      }
    }, f.body ? /*#__PURE__*/React.createElement("p", {
      style: {
        fontSize: 12.5,
        lineHeight: 1.6,
        color: "var(--z-body)"
      }
    }, f.body) : null, f.rejected_alternative ? /*#__PURE__*/React.createElement("p", {
      style: {
        fontSize: 12,
        lineHeight: 1.6,
        color: "var(--z-muted)",
        marginTop: 8
      }
    }, /*#__PURE__*/React.createElement("strong", null, "Considered and rejected: "), f.rejected_alternative) : null, f.strategic_alignment && f.strategic_alignment.statement ? /*#__PURE__*/React.createElement("p", {
      style: {
        fontSize: 12,
        lineHeight: 1.6,
        color: "var(--z-body)",
        marginTop: 8
      }
    }, /*#__PURE__*/React.createElement("strong", null, "Alignment: "), f.strategic_alignment.statement) : null, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 6,
        marginTop: 10,
        flexWrap: "wrap"
      }
    }, (f.e_ids || []).map(e => /*#__PURE__*/React.createElement("span", {
      key: e,
      className: "chip f-mono"
    }, e)))) : null);
  })));
}

/* ── O3 · why-now signals ─────────────────────────────────────────── */
function LiveWhyNow({
  data
}) {
  const rows = data.signals || [];
  if (!rows.length) return null;
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
    name: "bell",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Why now")), /*#__PURE__*/React.createElement("span", {
    className: "b b-org"
  }, rows.length, " signals")), /*#__PURE__*/React.createElement("div", {
    className: "card-body"
  }, rows.map((s, i) => /*#__PURE__*/React.createElement("div", {
    key: s.wn_id || i,
    className: "card-tile",
    style: {
      marginBottom: 8,
      padding: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8,
      marginBottom: 6,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-teal"
  }, s.kind), /*#__PURE__*/React.createElement("span", {
    className: "f-mono",
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, s.dated_on)), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 13,
      lineHeight: 1.6,
      color: "var(--z-dark)"
    }
  }, s.trigger), [["Window", s.window], ["If this waits", s.consequence_of_waiting], ["Cost of acting now", s.cost_of_acting_now], ["Why first", s.why_this_sequence]].filter(([, v]) => v).map(([label, text]) => /*#__PURE__*/React.createElement("div", {
    key: label,
    style: {
      marginTop: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      marginBottom: 2
    }
  }, label), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 12,
      lineHeight: 1.55,
      color: "var(--z-body)"
    }
  }, text)))))));
}

/* ── O2 · firmographics strip ─────────────────────────────────────── */
function LiveFirmographics({
  data
}) {
  const rows = (data.fields || []).filter(f => f.value !== null && f.value !== undefined);
  if (!rows.length) return null;
  const fmt = f => typeof f.value === "number" ? f.value.toLocaleString(undefined, {
    maximumFractionDigits: 2
  }) : String(f.value);
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "building",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Firmographics"))), /*#__PURE__*/React.createElement("div", {
    className: "card-body g3",
    style: {
      gap: 10
    }
  }, rows.map(f => /*#__PURE__*/React.createElement("div", {
    key: f.field,
    className: "card-tile"
  }, /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 10,
      textTransform: "uppercase",
      letterSpacing: ".08em"
    }
  }, f.field.replace(/_/g, " ")), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 18,
      fontWeight: 300,
      color: "var(--z-dark)",
      marginTop: 4
    }
  }, fmt(f), f.unit ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, " ", f.unit) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 4
    }
  }, f.as_of ? `as of ${f.as_of}` : "undated", f.source_e_id ? ` · ${f.source_e_id}` : "")))));
}

/* ── Provenance panel for a section not yet given its designed card ── */
function LiveSectionPanel({
  name,
  section,
  audience
}) {
  const [open, setOpen] = useState(false);
  const title = SECTION_TITLES[name] || name;
  const st = section || {};
  const empty = st.empty_state;
  const withheld = st.data_source === "withheld";
  const notPromoted = empty && empty.kind === "section_not_promoted";
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "doc",
    size: 13
  }), /*#__PURE__*/React.createElement("h3", null, title)), /*#__PURE__*/React.createElement("span", {
    className: `b ${withheld ? "b-muted" : notPromoted ? "b-below" : "b-above"}`
  }, withheld ? "withheld for this audience" : notPromoted ? "not promoted" : st.data_source || "—")), /*#__PURE__*/React.createElement("div", {
    className: "card-body"
  }, empty ? /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 12.5,
      color: "var(--z-body)",
      lineHeight: 1.6
    }
  }, empty.reason) : /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-muted)"
    }
  }, st.producer_version ? `produced by ${st.producer_version}` : "producer unknown", st.produced_at ? ` · promoted ${String(st.produced_at).slice(0, 19).replace("T", " ")}` : "", ` · cites ${(st.e_ids || []).length} evidence id${(st.e_ids || []).length === 1 ? "" : "s"}`, st.provenance ? ` · ${st.provenance}` : ""), st.data && audience !== "customer" ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 10
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => setOpen(v => !v)
  }, open ? "Hide" : "Show", " promoted payload"), open ? /*#__PURE__*/React.createElement("pre", {
    className: "f-mono",
    style: {
      marginTop: 8,
      fontSize: 10.5,
      lineHeight: 1.5,
      background: "var(--z-bg)",
      padding: 10,
      borderRadius: 6,
      maxHeight: 340,
      overflow: "auto",
      border: "1px solid var(--z-sep)"
    }
  }, JSON.stringify(st.data, null, 1)) : null) : null));
}

/* ── The live client page ─────────────────────────────────────────── */
function LiveClientPage({
  entity,
  run,
  tab,
  live
}) {
  const {
    audience
  } = useApp();
  const page = tab === "health" ? "heatmap" : tab;
  const names = LIVE_PAGE_SECTIONS[page];
  if (!names) {
    return /*#__PURE__*/React.createElement("div", {
      className: "empty"
    }, /*#__PURE__*/React.createElement("div", {
      className: "icon"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "doc",
      size: 22
    })), /*#__PURE__*/React.createElement("h3", null, "No promoted page for this tab"), /*#__PURE__*/React.createElement("p", null, "This tab has no serving sections; it is not part of the six promoted pages."));
  }
  if (!live || live.status === "loading") {
    return /*#__PURE__*/React.createElement("div", {
      className: "card"
    }, /*#__PURE__*/React.createElement("div", {
      className: "card-body row",
      style: {
        gap: 10
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "spinner"
    }), " ", /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        color: "var(--z-body)"
      }
    }, "Loading promoted sections\u2026")));
  }
  if (live.status === "error") {
    const messages = {
      entity_not_found: "No promoted run for this client yet. Content appears once a synthesis run promotes — the application renders nothing it was not given.",
      audience_forbidden: "This dashboard is not served to the current audience or role.",
      run_superseded: "The pinned run is no longer the active one.",
      not_signed_in: "The session expired. Sign in again to continue.",
      api_unreachable: "The serving API did not answer. No cached content is shown, because a stale page under a client's name is worse than an honest gap."
    };
    return /*#__PURE__*/React.createElement("div", {
      className: "empty"
    }, /*#__PURE__*/React.createElement("div", {
      className: "icon"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "warn",
      size: 22
    })), /*#__PURE__*/React.createElement("h3", null, live.code === "entity_not_found" ? "Nothing promoted yet" : "Not available"), /*#__PURE__*/React.createElement("p", null, messages[live.code] || live.detail || live.code));
  }
  const designed = {
    scores: LiveHero,
    firmographics: LiveFirmographics,
    why_now: LiveWhyNow,
    exec_summary: LiveExecSummary,
    findings: LiveFindings
  };
  return /*#__PURE__*/React.createElement("div", null, names.map(name => {
    const st = liveSectionState(live, name);
    const data = liveSection(live, name);
    const Designed = designed[name];
    if (Designed && data) {
      return /*#__PURE__*/React.createElement(Designed, {
        key: name,
        data: data,
        entity: entity,
        run: run
      });
    }
    return /*#__PURE__*/React.createElement(LiveSectionPanel, {
      key: name,
      name: name,
      section: st,
      audience: live.audience || audience
    });
  }));
}
Object.assign(window, {
  LiveClientPage,
  LIVE_PAGE_SECTIONS
});