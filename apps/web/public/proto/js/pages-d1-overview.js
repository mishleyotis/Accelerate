/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · D1 Entity Intelligence Hub (refined)
   ═══════════════════════════════════════════════════════════════════════ */

function ClientOverview({
  entity,
  run
}) {
  const {
    audience,
    openEvidence,
    openInsight,
    role,
    setIpSurface,
    setIpContext,
    setIpOpen,
    tweaks,
    pushToast
  } = useApp();
  const [findingOpen, setFindingOpen] = useState(null);
  const [scqaExp, setScqaExp] = useState(false);
  const layout = tweaks.overview_layout || "balanced";
  useEffect(() => {
    setIpSurface("why_now");
    setIpContext({
      entity
    });
  }, [entity?.id]);
  if (entity.in_progress) {
    return /*#__PURE__*/React.createElement(InProgressBanner, {
      run: run,
      entity: entity
    });
  }
  const findings = [{
    id: "F-01",
    title: "Data fragmentation is the root constraint, not under-investment",
    theme: "Data foundation",
    platforms: ["SF", "DB"],
    evidence: ["E-047", "E-141"],
    what: "Three production cores run in parallel with no canonical customer profile — a customer with a mortgage, a deposit account, and a card appears as three unrelated records.",
    why: "Each core was retained through prior acquisitions rather than consolidated. The organization has invested heavily in analytics on top, but every downstream initiative inherits the fragmentation underneath.",
    so_what: "Every channel or CX investment made before the substrate is fixed compounds the problem. The data foundation is the highest-leverage conversation on the board right now.",
    magnitude: "Blocks 34 downstream subcaps"
  }, {
    id: "F-02",
    title: "Loan origination is where automation lands first",
    theme: "Workflow",
    platforms: ["nCino"],
    evidence: ["E-236"],
    what: "Loan origination is still substantially manual — hand-offs between underwriting, credit, and closing are tracked in email and spreadsheets.",
    why: "The nCino migration already underway includes a Workflow Engine that isn't yet switched on for origination. The capability is bought but unused.",
    so_what: "This is the fastest credible win: a 5–7 month cycle compression using a tool they already own, with no new procurement. It builds the proof point for the larger data conversation.",
    magnitude: "5–7 month cycle compression"
  }, {
    id: "F-03",
    title: "The team generates insight faster than it acts on it",
    theme: "Decisioning",
    platforms: ["DB", "TBL"],
    evidence: ["E-250", "E-283"],
    what: "Tableau adoption is strong and broad, but insight rarely converts into an automated action or a next-best-action in the channel.",
    why: "The reporting layer matured ahead of the activation layer. Analysts produce dashboards; there's no decisioning fabric to operationalize what they surface.",
    so_what: "The appetite for data is already proven — so lead with activation (Data Cloud + Agentforce), not more BI. The muscle exists; it needs a destination.",
    magnitude: "Readiness signal, not a gap"
  }, {
    id: "F-04",
    title: "Mobile is the weakest customer-facing channel",
    theme: "Channels",
    platforms: ["TW", "SF"],
    evidence: ["E-271"],
    what: "App-store sentiment sits meaningfully below regional-bank peers; customers cite friction in onboarding and servicing, not missing features.",
    why: "The mobile experience is built on the fragmented data layer — personalization and straight-through servicing can't work when the customer isn't a single record.",
    so_what: "Mobile is a symptom of F-01, not an independent project. Twilio Engage + Service Cloud close most of the experience gap once the profile is unified — sequence it after the substrate.",
    magnitude: "Trails peer sentiment by ~0.8★"
  }, {
    id: "F-05",
    title: "Two C-suite hires open a 6–9 month decision window",
    theme: "Timing",
    platforms: [],
    evidence: ["E-203"],
    what: "A new CTO (ex-Wells Fargo, Apr 2026) and CDO (ex-JPM, May 2026) are both in their first two quarters.",
    why: "New executives set platform direction early and lock commitments after. Combined with five open Data Cloud Architect roles, the organization is visibly preparing for a CDP decision it hasn't made yet.",
    so_what: "This is the relationship window of the cycle. Engage now to shape the criteria before a point-solution is chosen — the technical case (F-01) and the political timing align exactly once.",
    magnitude: "Window closes at nCino go-live"
  }];
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "page-head",
    style: {
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, "Entity intelligence"), /*#__PURE__*/React.createElement("h1", {
    style: {
      marginBottom: 4
    }
  }, entity.name), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, DMA.SUBVERTICAL_LABEL[entity.subvertical], " \xB7 ", entity.hq, " \xB7 ", fmtAssets(entity.assets), " assets \xB7 Assessment ", fmtDate(entity.assessment_date))), /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast(`Customer-safe scorecard generated · ${entity.name}`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Scorecard"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast("Rerun queued — first batch in ~3 min", "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13
  }), " Request rerun"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: () => {
      setIpSurface("why_now");
      setIpContext({
        entity
      });
      setIpOpen(true);
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "sparkle",
    size: 13
  }), " Meeting prep"))), /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "20px 22px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: layout === "ring-left" ? "140px 1fr 280px" : "1fr 280px",
      gap: 28,
      alignItems: "stretch"
    }
  }, layout === "ring-left" ? /*#__PURE__*/React.createElement(ScoreRing, {
    score: entity.overall
  }) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, layout !== "ring-left" ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 18,
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement(ScoreRing, {
    score: entity.overall
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8,
      marginBottom: 8,
      alignItems: "center",
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `b ${DMA.helpers.maturityClass(entity.overall)}`
  }, DMA.helpers.maturityLabel(entity.overall).toUpperCase()), /*#__PURE__*/React.createElement("span", {
    className: "b b-ph1"
  }, "EVIDENCE \xB7 ", run.evidence_mode), /*#__PURE__*/React.createElement(FreshnessDot, {
    date: entity.assessment_date,
    withLabel: true
  }), entity.data_source === "DRIVE_PARSE" ? /*#__PURE__*/React.createElement("span", {
    className: "b b-ph0"
  }, "DRIVE PARSE") : null), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      color: "var(--z-body)",
      lineHeight: 1.5
    }
  }, "Trails ", DMA.SUBVERTICAL_LABEL[entity.subvertical].toLowerCase(), " peer median by ", ((entity.pillar_scores.P1 + entity.pillar_scores.P2 + entity.pillar_scores.P3 + entity.pillar_scores.P4) / 4 - entity.overall - 0.3).toFixed(1), " points. Gap concentrated in P4 Data foundation."))) : null, /*#__PURE__*/React.createElement("div", null, DMA.PILLARS.map(p => {
    const s = entity.pillar_scores[p.id];
    const peer = s + 0.3;
    const w = s / 5 * 100;
    const peerL = peer / 5 * 100;
    const delta = s - peer;
    return /*#__PURE__*/React.createElement("div", {
      className: "pbar",
      key: p.id,
      onClick: () => navigate(`/clients/${entity.id}/heatmap`, {
        pillar: p.id,
        run: run.id
      }),
      style: {
        cursor: "pointer"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "pbar-name"
    }, p.id, " \xB7 ", p.short), /*#__PURE__*/React.createElement("div", {
      className: "pbar-track"
    }, /*#__PURE__*/React.createElement("div", {
      className: "pbar-fill",
      style: {
        width: `${w}%`,
        background: DMA.helpers.maturityHex(s)
      }
    }), /*#__PURE__*/React.createElement("div", {
      className: "pbar-peer",
      style: {
        left: `calc(${peerL}% - 1px)`
      },
      title: `Peer ${peer.toFixed(1)}`
    })), /*#__PURE__*/React.createElement("div", {
      className: "pbar-score"
    }, s.toFixed(1)), /*#__PURE__*/React.createElement("div", {
      className: "pbar-delta",
      style: {
        color: delta < 0 ? "var(--z-below)" : "var(--z-mid)"
      }
    }, delta >= 0 ? "▲" : "▼", " ", Math.abs(delta).toFixed(1)));
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 8,
      fontSize: 10.5,
      color: "var(--z-muted)",
      display: "flex",
      gap: 14,
      paddingLeft: 122
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      gap: 4,
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 12,
      height: 4,
      background: "var(--z-teal)",
      borderRadius: 2
    }
  }), " Entity"), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      gap: 4,
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 2,
      height: 10,
      background: "var(--z-dpur)"
    }
  }), " Peer median")))), /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--z-lav)",
      borderRadius: 12,
      padding: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      marginBottom: 8
    }
  }, "Firmographics"), /*#__PURE__*/React.createElement(Row, {
    k: "Assets",
    v: fmtAssets(entity.assets)
  }), /*#__PURE__*/React.createElement(Row, {
    k: "Employees",
    v: entity.employees?.toLocaleString() || "-"
  }), /*#__PURE__*/React.createElement(Row, {
    k: "Branches",
    v: entity.branches?.toString() || "-"
  }), /*#__PURE__*/React.createElement(Row, {
    k: "CAGR",
    v: entity.cagr ? `${fmtPct(entity.cagr)} · ${entity.trend}` : "-"
  }), /*#__PURE__*/React.createElement(Row, {
    k: "Regulator",
    v: entity.regulator
  }), /*#__PURE__*/React.createElement(Row, {
    k: "Footprint",
    v: entity.footprint?.join(" · ") || "-"
  })))), /*#__PURE__*/React.createElement(WhyNowStrip, {
    entity: entity,
    openEvidence: openEvidence,
    audience: audience
  }), /*#__PURE__*/React.createElement(SCQACard, {
    entity: entity,
    expanded: scqaExp,
    onToggle: () => setScqaExp(o => !o),
    openEvidence: openEvidence
  }), /*#__PURE__*/React.createElement(OpportunitySurfaceStrip, {
    entity: entity,
    run: run
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1.55fr 1fr",
      gap: 16,
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement(TopFindingsCard, {
    findings: findings,
    openFinding: findingOpen,
    setOpenFinding: setFindingOpen,
    openEvidence: openEvidence
  }), /*#__PURE__*/React.createElement(LeadershipPanel, {
    audience: audience
  })), /*#__PURE__*/React.createElement("div", {
    className: "section-label",
    style: {
      display: "flex",
      alignItems: "baseline",
      gap: 8,
      margin: "4px 0 12px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      fontWeight: 600,
      color: "var(--z-dark)",
      textTransform: "uppercase",
      letterSpacing: ".06em"
    }
  }, "Evidence & benchmarks"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "extracted from scoring workbook \xB7 evidence index \xB7 peer set")), /*#__PURE__*/React.createElement("div", {
    className: "cards-grid-3",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement(FinancialTrajectoryCard, {
    entity: entity
  }), /*#__PURE__*/React.createElement(CoverageByPillarCard, {
    entity: entity
  }), /*#__PURE__*/React.createElement(EvidenceTierCard, {
    entity: entity
  })), /*#__PURE__*/React.createElement("div", {
    className: "cards-grid-2",
    style: {
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement(CeilingEstimateCard, {
    entity: entity,
    audience: audience
  }), /*#__PURE__*/React.createElement(SentimentCard, {
    entity: entity,
    audience: audience
  })), audience !== "customer" ? /*#__PURE__*/React.createElement(ThoughtLeadershipPanel, null) : null);
}

/* ── Score ring ─────────────────────────────────────────────────── */
function ScoreRing({
  score,
  size = 110
}) {
  if (score == null) return null;
  const r = size * 0.34,
    c = 2 * Math.PI * r,
    pct = score / 5;
  return /*#__PURE__*/React.createElement("div", {
    className: "score-ring",
    style: {
      width: size,
      height: size,
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: size,
    height: size
  }, /*#__PURE__*/React.createElement("circle", {
    cx: size / 2,
    cy: size / 2,
    r: r,
    className: "ring-bg",
    strokeWidth: "6"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: size / 2,
    cy: size / 2,
    r: r,
    className: "ring-fg",
    stroke: DMA.helpers.maturityHex(score),
    strokeWidth: "6",
    strokeDasharray: c,
    strokeDashoffset: c * (1 - pct),
    strokeLinecap: "round"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      textAlign: "center",
      inset: 0,
      display: "flex",
      flexDirection: "column",
      justifyContent: "center",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "num",
    style: {
      color: DMA.helpers.maturityHex(score),
      fontSize: size * 0.32,
      fontWeight: 300,
      lineHeight: 1
    }
  }, score.toFixed(1))));
}

/* ── Why-now strip · expandable, drillable, per-client ──────────────
   Sources DMA.whyNowFor(entity.id): hand-authored for the flagship,
   synthesized from each client's own scoring/evidence otherwise.
   Collapsed → label + strength + window + one-line "so what".
   Expanded → detail · metric · timeline event · the play · peer context ·
   risk-if-ignored · tier-coded evidence · confidence + claim type.
   Customer view keeps positive framing and strips internal rationale. */
function WhyNowStrip({
  entity,
  openEvidence,
  audience
}) {
  const [open, setOpen] = useState(0); // first signal expanded by default
  const signals = DMA.whyNowFor(entity.id) || [];
  const isCust = audience === "customer";
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
      icon: "shield",
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
  const CLAIM = {
    FACT: "b-teal",
    INFERENCE: "b-purple",
    HYPOTHESIS: "b-org"
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 28,
      height: 28,
      borderRadius: 7,
      background: "var(--ph0-lt)",
      color: "var(--ph0)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "sparkle",
    size: 14
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      color: "var(--z-dark)"
    }
  }, "Why now signals"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, signals.length, " trigger", signals.length === 1 ? "" : "s", " \xB7 click any signal to drill into the evidence")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => navigate(`/clients/${entity.id}/context`)
  }, "View timeline ", /*#__PURE__*/React.createElement(Icon, {
    name: "arrow-r",
    size: 11
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, signals.map((s, i) => {
    const openNow = open === i;
    const cat = CAT[s.category] || CAT.market;
    return /*#__PURE__*/React.createElement("div", {
      key: s.id || i,
      style: {
        border: `1px solid ${openNow ? "var(--ph0-bd)" : "var(--z-sep)"}`,
        borderRadius: 10,
        overflow: "hidden",
        background: openNow ? "var(--ph0-lt)" : "#fff",
        transition: "background 140ms var(--ease), border-color 140ms var(--ease)"
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setOpen(o => o === i ? -1 : i),
      style: {
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: 11,
        padding: "12px 14px",
        background: "none",
        border: 0,
        cursor: "pointer",
        textAlign: "left"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 30,
        height: 30,
        borderRadius: 8,
        background: cat.color,
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: cat.icon,
      size: 15
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 7,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        fontWeight: 600,
        color: "var(--z-dark)"
      }
    }, s.label), !isCust ? /*#__PURE__*/React.createElement("span", {
      className: `b ${STR[s.strength] || "b-muted"}`
    }, s.strength) : null), !openNow ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        marginTop: 3,
        lineHeight: 1.4
      },
      className: "txt-fit-1"
    }, s.impact) : null), /*#__PURE__*/React.createElement("span", {
      className: "b",
      style: {
        background: "rgba(115,91,161,.14)",
        color: "var(--z-dpur)",
        flexShrink: 0
      }
    }, s.window), /*#__PURE__*/React.createElement(Icon, {
      name: openNow ? "chevron-u" : "chevron-d",
      size: 15,
      style: {
        color: "var(--z-muted)",
        flexShrink: 0
      }
    })), openNow ? /*#__PURE__*/React.createElement("div", {
      style: {
        padding: "0 14px 14px 55px"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12.5,
        color: "var(--z-body)",
        lineHeight: 1.6,
        marginBottom: 10
      }
    }, isCust ? s.impact : s.detail), !isCust && s.metric ? /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 11.5,
        color: "var(--z-dark)",
        background: "#fff",
        border: "1px solid var(--z-sep)",
        borderRadius: 6,
        padding: "7px 10px",
        marginBottom: 10,
        display: "inline-block"
      }
    }, s.metric) : null, s.timeline ? /*#__PURE__*/React.createElement("button", {
      onClick: () => navigate(`/clients/${entity.id}/context`),
      style: {
        display: "flex",
        alignItems: "center",
        gap: 7,
        background: "none",
        border: 0,
        padding: 0,
        cursor: "pointer",
        marginBottom: 12
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "timeline",
      size: 12,
      style: {
        color: "var(--ph0)"
      }
    }), /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        fontSize: 11,
        color: "var(--z-mid)"
      }
    }, s.timeline.date), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)"
      }
    }, s.timeline.event), /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-r",
      size: 10,
      style: {
        color: "var(--z-muted)"
      }
    })) : null, s.play ? /*#__PURE__*/React.createElement("div", {
      style: {
        background: "rgba(39,187,175,.1)",
        borderLeft: "3px solid var(--z-teal)",
        borderRadius: "0 6px 6px 0",
        padding: "8px 12px",
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        fontWeight: 700,
        letterSpacing: ".1em",
        color: "var(--z-teal)",
        textTransform: "uppercase",
        marginBottom: 2
      }
    }, "The play"), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-dark)",
        lineHeight: 1.55,
        fontWeight: 500
      }
    }, s.play)) : null, !isCust && s.peer_context ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-muted)",
        lineHeight: 1.5,
        margin: "6px 0"
      }
    }, /*#__PURE__*/React.createElement("strong", {
      style: {
        color: "var(--z-body)"
      }
    }, "Peer context \xB7 "), s.peer_context) : null, !isCust && s.risk ? /*#__PURE__*/React.createElement("div", {
      style: {
        background: "rgba(214,109,42,.08)",
        borderLeft: "3px solid var(--z-org)",
        borderRadius: "0 6px 6px 0",
        padding: "8px 12px",
        marginBottom: 10
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        fontWeight: 700,
        letterSpacing: ".1em",
        color: "var(--z-org)",
        textTransform: "uppercase",
        marginBottom: 2
      }
    }, "If ignored"), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-body)",
        lineHeight: 1.55
      }
    }, s.risk)) : null, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        flexWrap: "wrap",
        marginTop: 10
      }
    }, s.evidence && s.evidence.length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 9.5,
        color: "var(--z-muted)",
        textTransform: "uppercase",
        letterSpacing: ".08em"
      }
    }, "Evidence"), s.evidence.map(eid => {
      const e = DMA.getEvidence(eid);
      return /*#__PURE__*/React.createElement("button", {
        key: eid,
        className: `tier-chip tier-${e ? e.tier : "T3"}`,
        style: {
          cursor: "pointer",
          border: 0
        },
        title: e ? e.title : eid,
        onClick: () => openEvidence(eid)
      }, eid);
    })) : /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)",
        fontStyle: "italic"
      }
    }, "No direct evidence yet \u2014 confirm in first meeting"), /*#__PURE__*/React.createElement("span", {
      style: {
        flex: 1
      }
    }), !isCust && s.claim ? /*#__PURE__*/React.createElement("span", {
      className: `b ${CLAIM[s.claim] || "b-muted"}`
    }, s.claim) : null, !isCust && s.confidence ? /*#__PURE__*/React.createElement("span", {
      className: "b b-muted"
    }, s.confidence, " confidence") : null)) : null);
  })));
}

/* ── SCQA card ──────────────────────────────────────────────────── */
function SCQACard({
  entity,
  expanded,
  onToggle,
  openEvidence
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
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
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "doc",
    size: 14
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "Executive narrative"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "SCQA \xB7 Assessment Report \xB7 stored verbatim")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: onToggle
  }, expanded ? "Collapse ↑" : "Read full ↓")), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      color: "var(--z-dark)",
      lineHeight: 1.7,
      maxWidth: 880
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 600
    }
  }, entity.name), " is a mid-tier ", DMA.SUBVERTICAL_LABEL[entity.subvertical].toLowerCase(), " mid-way through a multi-year digital transformation. Current overall maturity (", entity.overall.toFixed(1), " / 5) trails the peer median by 0.4, with the gap concentrated in P4 Data Foundation. Two recent C-suite hires open a 6-9 month integration window.", " ", expanded ? /*#__PURE__*/React.createElement(React.Fragment, null, "The institution has invested visibly in front-end channels (Tableau Cloud, Marketing Cloud roles, mobile redesign) but lacks the data substrate to operate any of these as a coherent customer-experience system. Without intervention, fragmentation deepens as nCino lands on top of FIS Profile core, and a future re-platform becomes harder. The strategic question is whether to invest now in a unified customer-data layer ahead of the nCino go-live, or continue to layer point solutions and accept the operating cost. Recommendation: lead the next 9 months with Salesforce Data Cloud + Databricks as the substrate ", /*#__PURE__*/React.createElement("button", {
    className: "chip",
    onClick: () => openEvidence("E-047")
  }, "E-047"), " ", /*#__PURE__*/React.createElement("button", {
    className: "chip",
    onClick: () => openEvidence("E-089")
  }, "E-089"), ".") : null));
}

/* ── Opportunity Surface - platform cards ───────────────────────── */
function OpportunitySurfaceStrip({
  entity,
  run
}) {
  const sorted = Object.entries(entity.oss).sort((a, b) => b[1] - a[1]);
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 14
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
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "platform",
    size: 14
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "Opportunity Surface \xB7 per platform"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Composite fit score 0\u2013100 \xB7 \u03A3(priority \xD7 gap) for ABSENT, high-confidence subcaps")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => navigate(`/clients/${entity.id}/platform`, {
      run: run.id
    })
  }, "Open matrix ", /*#__PURE__*/React.createElement(Icon, {
    name: "arrow-r",
    size: 11
  }))), /*#__PURE__*/React.createElement("div", {
    className: "g5"
  }, sorted.map(([pid, score]) => {
    const p = DMA.getPlatform(pid);
    return /*#__PURE__*/React.createElement("div", {
      key: pid,
      className: "card-tile clickable",
      onClick: () => navigate(`/clients/${entity.id}/platform`, {
        platform: pid,
        run: run.id
      })
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600,
        color: "var(--z-dark)"
      }
    }, p.name), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        marginTop: 2
      }
    }, p.features.split(" · ").slice(0, 2).join(" · "))), /*#__PURE__*/React.createElement("div", {
      style: {
        textAlign: "right"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 24,
        fontWeight: 200,
        color: "var(--z-teal)",
        lineHeight: 1
      }
    }, score), /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 9,
        color: "var(--z-muted)"
      }
    }, "fit score"))), /*#__PURE__*/React.createElement("div", {
      className: "prog",
      style: {
        height: 5
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "prog-fill",
      style: {
        width: `${score}%`,
        background: score >= 60 ? "var(--z-teal)" : score >= 35 ? "var(--m-bld)" : "var(--m-act)"
      }
    })));
  })));
}

/* ── Top findings ───────────────────────────────────────────────── */
function TopFindingsCard({
  findings,
  openFinding,
  setOpenFinding,
  openEvidence
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", null, "Top findings"), /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, findings.length)), /*#__PURE__*/React.createElement("div", null, findings.map(f => {
    const isOpen = openFinding === f.id;
    return /*#__PURE__*/React.createElement("div", {
      key: f.id,
      style: {
        padding: "12px 16px",
        borderTop: "1px solid var(--z-sep)",
        transition: "background 120ms"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        cursor: "pointer"
      },
      onClick: () => setOpenFinding(o => o === f.id ? null : f.id),
      onMouseEnter: e => e.currentTarget.parentElement.style.background = "var(--z-lav)",
      onMouseLeave: e => e.currentTarget.parentElement.style.background = ""
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip",
      style: {
        marginTop: 1
      }
    }, f.id), /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontWeight: 600,
        fontSize: 13,
        lineHeight: 1.35
      }
    }, f.title), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        marginTop: 4,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-mid)",
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: ".05em"
      }
    }, f.theme), f.magnitude ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
      style: {
        color: "var(--z-sep)"
      }
    }, "\xB7"), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-body)"
      }
    }, f.magnitude)) : null)), f.platforms.map(p => /*#__PURE__*/React.createElement("span", {
      key: p,
      className: "b b-teal",
      style: {
        marginTop: 1
      }
    }, DMA.getPlatform(p)?.short)), /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-u" : "chevron-d",
      size: 14,
      style: {
        color: "var(--z-muted)",
        marginTop: 3,
        flexShrink: 0
      }
    })), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 10,
        padding: 14,
        background: "var(--z-bg)",
        borderRadius: 8
      }
    }, [{
      k: "What",
      v: f.what,
      c: "var(--z-dark)"
    }, {
      k: "Why",
      v: f.why,
      c: "var(--z-body)"
    }].map(row => /*#__PURE__*/React.createElement("div", {
      key: row.k,
      style: {
        marginBottom: 10
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".1em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        marginBottom: 3
      }
    }, row.k), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12.5,
        color: row.c,
        lineHeight: 1.6
      }
    }, row.v))), /*#__PURE__*/React.createElement("div", {
      style: {
        background: "rgba(39,187,175,.1)",
        borderLeft: "3px solid var(--z-teal)",
        borderRadius: "0 6px 6px 0",
        padding: "9px 12px",
        marginBottom: f.evidence.length ? 12 : 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".1em",
        color: "var(--z-teal)",
        textTransform: "uppercase",
        marginBottom: 3
      }
    }, "So what"), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12.5,
        color: "var(--z-dark)",
        lineHeight: 1.6,
        fontWeight: 500
      }
    }, f.so_what)), f.evidence.length > 0 ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".1em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        marginBottom: 6
      }
    }, "Evidence \xB7 click to view"), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        flexDirection: "column",
        gap: 4
      }
    }, f.evidence.map(eid => {
      const e = DMA.getEvidence(eid);
      if (!e) return null;
      return /*#__PURE__*/React.createElement("button", {
        key: eid,
        onClick: ev => {
          ev.stopPropagation();
          openEvidence(eid);
        },
        style: {
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 10px",
          background: "#fff",
          border: "1px solid var(--z-sep)",
          borderRadius: 6,
          cursor: "pointer",
          textAlign: "left",
          transition: "all 120ms"
        },
        onMouseEnter: e => {
          e.currentTarget.style.borderColor = "var(--z-teal)";
          e.currentTarget.style.transform = "translateX(2px)";
        },
        onMouseLeave: e => {
          e.currentTarget.style.borderColor = "var(--z-sep)";
          e.currentTarget.style.transform = "";
        }
      }, /*#__PURE__*/React.createElement("span", {
        className: `tier-chip tier-${e.tier}`
      }, eid), /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 11.5,
          color: "var(--z-dark)",
          fontWeight: 500,
          flex: 1,
          minWidth: 0
        },
        className: "txt-fit-1"
      }, e.title), /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 10,
          color: "var(--z-muted)"
        }
      }, e.recency), /*#__PURE__*/React.createElement(Icon, {
        name: "arrow-r",
        size: 11,
        style: {
          color: "var(--z-mid)"
        }
      }));
    }))) : null) : null);
  })));
}

/* ── Leadership panel + Clay enrichment ─────────────────────────── */
function LeadershipPanel({
  audience
}) {
  const [enriched, setEnriched] = useState({}); // id → "loading" | "done"
  const [enrichingAll, setEnrichingAll] = useState(false);
  const enrich = id => {
    setEnriched(e => ({
      ...e,
      [id]: "loading"
    }));
    setTimeout(() => setEnriched(e => ({
      ...e,
      [id]: "done"
    })), 900);
  };
  const enrichAll = () => {
    setEnrichingAll(true);
    DMA.LEADERSHIP.forEach((ex, i) => setTimeout(() => {
      if (ex.gap_flag) return;
      enrich(ex.id);
      if (i === DMA.LEADERSHIP.length - 1) setTimeout(() => setEnrichingAll(false), 1000);
    }, i * 240));
  };
  const anyEnriched = Object.values(enriched).some(v => v === "done");
  return /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "users",
    size: 15
  }), " Leadership panel"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary btn-sm",
    onClick: enrichAll,
    disabled: enrichingAll
  }, enrichingAll ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
    className: "skel",
    style: {
      width: 10,
      height: 10,
      borderRadius: 5
    }
  }), " Enriching\u2026") : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Icon, {
    name: "sparkle",
    size: 11
  }), " Enrich all via Clay"))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "8px 16px 14px"
    }
  }, DMA.LEADERSHIP.map(ex => {
    const state = enriched[ex.id]; // undefined | "loading" | "done"
    const hasClay = ex.clay && !ex.gap_flag;
    const isEnriched = state === "done" && hasClay;
    return /*#__PURE__*/React.createElement("div", {
      key: ex.id,
      style: {
        display: "flex",
        gap: 10,
        padding: "12px 0",
        borderBottom: "1px solid var(--z-sep)"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        width: 36,
        height: 36,
        borderRadius: 18,
        background: ex.gap_flag ? "var(--z-sep)" : "linear-gradient(135deg, var(--z-teal), var(--z-mid))",
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 12,
        fontWeight: 600,
        flexShrink: 0
      }
    }, ex.gap_flag ? "?" : ex.name.split(" ").map(n => n[0]).join("").slice(0, 2)), /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 6,
        alignItems: "center",
        flexWrap: "wrap"
      }
    }, ex.gap_flag ? /*#__PURE__*/React.createElement("span", {
      style: {
        fontWeight: 600,
        fontSize: 13
      }
    }, "-") : isEnriched && ex.clay?.linkedin ? /*#__PURE__*/React.createElement("a", {
      href: `https://${ex.clay.linkedin}`,
      target: "_blank",
      rel: "noreferrer",
      style: {
        fontWeight: 600,
        fontSize: 13,
        color: "var(--z-mid)",
        textDecoration: "none"
      },
      onClick: e => e.stopPropagation()
    }, ex.name) : /*#__PURE__*/React.createElement("span", {
      style: {
        fontWeight: 600,
        fontSize: 13,
        color: "var(--z-dark)"
      }
    }, ex.name), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-mid)",
        fontWeight: 600
      }
    }, ex.title), ex.gap_flag ? /*#__PURE__*/React.createElement("span", {
      className: "b b-below"
    }, "GAP") : ex.recent_hire ? /*#__PURE__*/React.createElement("span", {
      className: "b b-org"
    }, "NEW \xB7 ", ex.tenure_months, " mo") : /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, "\xB7 ", Math.round(ex.tenure_months / 12), " yr")), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        marginTop: 4,
        lineHeight: 1.5
      }
    }, ex.background), hasClay && audience !== "customer" ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 8,
        padding: "8px 10px",
        background: isEnriched ? "var(--z-ice)" : state === "loading" ? "var(--z-lav)" : "var(--z-bg)",
        border: `1px solid ${isEnriched ? "rgba(39,187,175,.35)" : "var(--z-sep)"}`,
        borderRadius: 6
      }
    }, !state ? /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        fontSize: 11
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "lock",
      size: 11,
      style: {
        color: "var(--z-muted)"
      }
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        color: "var(--z-muted)"
      }
    }, "Email \xB7 LinkedIn hidden until enriched"), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("button", {
      className: "btn btn-tertiary btn-sm",
      style: {
        padding: "3px 8px"
      },
      onClick: () => enrich(ex.id)
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "sparkle",
      size: 10
    }), " Enrich via Clay")) : state === "loading" ? /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        fontSize: 11,
        color: "var(--z-dpur)"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "skel",
      style: {
        width: 12,
        height: 12,
        borderRadius: 6
      }
    }), /*#__PURE__*/React.createElement("span", null, "Querying Clay enrichment\u2026")) : /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        flexDirection: "column",
        gap: 4
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        fontSize: 11,
        color: "var(--z-mid)"
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "check",
      size: 11
    }), /*#__PURE__*/React.createElement("strong", {
      style: {
        color: "var(--z-mid)"
      }
    }, "Enriched"), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, "via Clay \xB7 just now")), /*#__PURE__*/React.createElement("a", {
      href: `mailto:${ex.clay.email}`,
      style: {
        fontSize: 11,
        color: "var(--z-mid)",
        textDecoration: "none",
        display: "inline-flex",
        alignItems: "center",
        gap: 5
      },
      onClick: e => e.stopPropagation()
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "envelope",
      size: 11
    }), " ", ex.clay.email), /*#__PURE__*/React.createElement("a", {
      href: `https://${ex.clay.linkedin}`,
      target: "_blank",
      rel: "noreferrer",
      style: {
        fontSize: 11,
        color: "var(--z-mid)",
        textDecoration: "none",
        display: "inline-flex",
        alignItems: "center",
        gap: 5
      },
      onClick: e => e.stopPropagation()
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "linkedin",
      size: 11
    }), " ", ex.clay.linkedin))) : null));
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "10px 16px",
      background: "var(--z-lav)",
      fontSize: 11,
      color: "var(--z-muted)",
      display: "flex",
      alignItems: "center",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 11
  }), /*#__PURE__*/React.createElement("span", null, "Critical roles flagged: ", /*#__PURE__*/React.createElement("strong", {
    style: {
      color: "var(--z-below)"
    }
  }, "CISO absent"), " from evidence"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), anyEnriched ? /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-mid)",
      fontWeight: 600
    }
  }, "\u2713 ", Object.values(enriched).filter(v => v === "done").length, " of ", DMA.LEADERSHIP.filter(x => !x.gap_flag).length, " enriched") : null));
}

/* ── Thought leadership ─────────────────────────────────────────── */
function ThoughtLeadershipPanel() {
  return /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    style: {
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "lightbulb",
    size: 15
  }), " Thought leadership signal"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "From executives - recent 6 months")), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "g3"
  }, DMA.THOUGHT_LEADERSHIP.map(tl => /*#__PURE__*/React.createElement("div", {
    key: tl.id,
    className: "card-tile",
    style: {
      padding: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, tl.type.toUpperCase()), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, fmtDate(tl.date))), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      lineHeight: 1.4,
      marginBottom: 6
    }
  }, tl.title), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-body)",
      lineHeight: 1.55,
      fontStyle: "italic"
    }
  }, "\"", tl.excerpt, "\""), /*#__PURE__*/React.createElement("div", {
    className: "sep",
    style: {
      margin: "8px 0"
    }
  }), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, /*#__PURE__*/React.createElement("span", null, tl.author), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("a", {
    href: `https://${tl.url}`,
    target: "_blank",
    rel: "noreferrer",
    style: {
      color: "var(--z-mid)",
      display: "inline-flex",
      alignItems: "center",
      gap: 3
    }
  }, "Open ", /*#__PURE__*/React.createElement(Icon, {
    name: "external",
    size: 10
  }))))))));
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
      fontSize: 11.5,
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-muted)",
      flexShrink: 0,
      whiteSpace: "nowrap"
    }
  }, k), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-dark)",
      fontWeight: 500,
      textAlign: "right",
      minWidth: 0
    }
  }, v));
}
function InProgressBanner({
  run,
  entity
}) {
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      background: "var(--ph1-lt)",
      border: "1px solid var(--ph1-bd)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 16,
    style: {
      color: "var(--ph1)"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      fontWeight: 600,
      color: "#1E3A8A"
    }
  }, "Assessment in progress \xB7 Batch ", run.current_batch, " of 6"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    className: "b b-ph1"
  }, "SSE LIVE")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 12,
      color: "#1E3A8A",
      marginBottom: 12,
      lineHeight: 1.55
    }
  }, entity.name, " is currently being researched. Subcap scoring begins at Batch 4. Insight cards appear after Batch 5."), /*#__PURE__*/React.createElement("div", {
    className: "batch-row",
    style: {
      marginBottom: 16
    }
  }, ["Setup", "Evidence", "Peers", "Scoring", "Analysis", "Final"].map((b, i) => /*#__PURE__*/React.createElement("div", {
    key: b,
    className: `batch-pill ${i + 1 < run.current_batch ? "done" : i + 1 === run.current_batch ? "active" : ""}`
  }, i + 1, " ", b))), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Per-tab unlocks: D3 Heatmap unlocks at Batch 4 \xB7 D2 Insights at Batch 5 \xB7 D5 Context at Batch 6")));
}

/* ── D2 Insight card surface ─────────────────────────────────────── */
/* Group insight cards into clusters for D2. Priority is the default lens;
   Pillar and Theme are alternates. Cards sort by priority score within a group. */
function groupInsights(cards, mode) {
  const withP = cards.map(c => ({
    c,
    p: DMA.insightPriority(c)
  }));
  const byScore = (a, b) => b.p.score - a.p.score || a.c.id.localeCompare(b.c.id);
  if (mode === "pillar") {
    return DMA.PILLARS.map(p => ({
      key: p.id,
      label: `${p.id} · ${p.short}`,
      color: "purple",
      desc: p.name,
      items: withP.filter(x => x.c.pillar === p.id).sort(byScore)
    })).filter(g => g.items.length);
  }
  if (mode === "theme") {
    const themes = [...new Set(withP.map(x => x.c.theme || "Other"))];
    return themes.map(t => ({
      key: t,
      label: t,
      color: "purple",
      desc: `${withP.filter(x => (x.c.theme || "Other") === t).length} card${withP.filter(x => (x.c.theme || "Other") === t).length === 1 ? "" : "s"}`,
      items: withP.filter(x => (x.c.theme || "Other") === t).sort(byScore)
    })).sort((a, b) => b.items[0].p.score - a.items[0].p.score);
  }
  const defs = [{
    key: 1,
    label: "Act now",
    color: "below",
    desc: "Critical gaps + high-confidence, actionable opportunities — lead with these"
  }, {
    key: 2,
    label: "Plan next",
    color: "org",
    desc: "Opportunities to sequence into the roadmap"
  }, {
    key: 3,
    label: "Watch",
    color: "teal",
    desc: "Stable or monitoring items — no immediate action needed"
  }];
  return defs.map(d => ({
    ...d,
    items: withP.filter(x => x.p.tier === d.key).sort(byScore)
  })).filter(g => g.items.length);
}
function ClientInsights({
  entity,
  run
}) {
  const {
    openInsight,
    openEvidence,
    audience,
    pushToast
  } = useApp();
  const [flag, setFlag] = useState("ALL");
  const [pillar, setPillar] = useState("ALL");
  const [conf, setConf] = useState("ALL");
  const [groupBy, setGroupBy] = useState("priority");
  const [collapsed, setCollapsed] = useState({});
  const filtered = useMemo(() => DMA.INSIGHT_CARDS.filter(c => {
    if (flag !== "ALL" && c.flag !== flag) return false;
    if (pillar !== "ALL" && c.pillar !== pillar) return false;
    if (conf !== "ALL" && c.confidence !== conf) return false;
    return true;
  }), [flag, pillar, conf]);
  const groups = useMemo(() => groupInsights(filtered, groupBy), [filtered, groupBy]);
  const tierCounts = {
    1: 0,
    2: 0,
    3: 0
  };
  DMA.INSIGHT_CARDS.forEach(c => tierCounts[DMA.insightPriority(c).tier]++);
  const filtersActive = flag !== "ALL" || pillar !== "ALL" || conf !== "ALL";
  const renderCard = ({
    c,
    p
  }) => /*#__PURE__*/React.createElement("div", {
    key: c.id,
    className: `ic ${c.flag.toLowerCase()}`,
    onClick: () => openInsight(c.id)
  }, /*#__PURE__*/React.createElement("div", {
    className: "ic-head"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 6,
      alignItems: "center",
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "ic-id"
  }, c.id), /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, c.pillar), /*#__PURE__*/React.createElement("span", {
    className: `b b-${p.tierColor}`
  }, p.tierLabel), groupBy !== "theme" && c.theme ? /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, c.theme) : null), c.annotation ? /*#__PURE__*/React.createElement("span", {
    className: "b b-above",
    title: "Annotated"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "edit",
    size: 9
  }), " NOTE") : null), /*#__PURE__*/React.createElement("div", {
    className: "ic-title"
  }, c.title), /*#__PURE__*/React.createElement("div", {
    className: "ic-body"
  }, c.what.slice(0, 170), c.what.length > 170 ? "…" : ""), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 4,
      flexWrap: "wrap",
      marginTop: 4
    }
  }, c.evidence.slice(0, 4).map(eid => {
    const e = DMA.getEvidence(eid);
    if (!e) return null;
    return /*#__PURE__*/React.createElement("span", {
      key: eid,
      className: `tier-chip tier-${e.tier}`,
      title: e.title
    }, eid);
  }), c.evidence.length > 4 ? /*#__PURE__*/React.createElement("span", {
    className: "chip muted"
  }, "+", c.evidence.length - 4) : null), /*#__PURE__*/React.createElement("div", {
    className: "ic-foot"
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      marginRight: "auto"
    }
  }, c.evidence.length, " evidence \xB7 ", c.affects.length, " caps ", c.rec ? `· ${c.rec}` : ""), c.platforms.map(pf => /*#__PURE__*/React.createElement("span", {
    key: pf,
    className: "b b-teal"
  }, DMA.getPlatform(pf)?.short))));
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "page-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, "Insight cards"), /*#__PURE__*/React.createElement("h1", null, DMA.INSIGHT_CARDS.length, " insight cards"), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-below",
    style: {
      marginRight: 6
    }
  }, tierCounts[1], " ACT NOW"), /*#__PURE__*/React.createElement("span", {
    className: "b b-org",
    style: {
      marginRight: 6
    }
  }, tierCounts[2], " PLAN NEXT"), /*#__PURE__*/React.createElement("span", {
    className: "b b-teal"
  }, tierCounts[3], " WATCH"))), /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast(`Exporting ${filtered.length} insight cards as PDF…`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Export PDF"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: () => pushToast("Add a note from any insight card — click a card to start", "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "plus",
    size: 13
  }), " Add note"))), /*#__PURE__*/React.createElement("div", {
    className: "filter-bar"
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      fontWeight: 600,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".06em"
    }
  }, "Group by"), /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, [["priority", "Priority"], ["pillar", "Pillar"], ["theme", "Theme"]].map(([k, l]) => /*#__PURE__*/React.createElement("button", {
    key: k,
    className: groupBy === k ? "on" : "",
    onClick: () => setGroupBy(k)
  }, l))), /*#__PURE__*/React.createElement("span", {
    style: {
      width: 1,
      height: 22,
      background: "var(--z-sep)",
      margin: "0 4px"
    }
  }), /*#__PURE__*/React.createElement("select", {
    className: "inp",
    style: {
      maxWidth: 150
    },
    value: pillar,
    onChange: e => setPillar(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: "ALL"
  }, "All pillars"), DMA.PILLARS.map(p => /*#__PURE__*/React.createElement("option", {
    key: p.id,
    value: p.id
  }, p.id, " \xB7 ", p.short))), /*#__PURE__*/React.createElement("select", {
    className: "inp",
    style: {
      maxWidth: 150
    },
    value: flag,
    onChange: e => setFlag(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: "ALL"
  }, "All flags"), /*#__PURE__*/React.createElement("option", null, "CRITICAL"), /*#__PURE__*/React.createElement("option", null, "OPPORTUNITY"), /*#__PURE__*/React.createElement("option", null, "MONITOR")), /*#__PURE__*/React.createElement("select", {
    className: "inp",
    style: {
      maxWidth: 160
    },
    value: conf,
    onChange: e => setConf(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: "ALL"
  }, "All confidence"), /*#__PURE__*/React.createElement("option", null, "HIGH"), /*#__PURE__*/React.createElement("option", null, "MEDIUM"), /*#__PURE__*/React.createElement("option", null, "LOW")), filtersActive ? /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => {
      setFlag("ALL");
      setPillar("ALL");
      setConf("ALL");
    }
  }, "Clear") : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, filtered.length, " of ", DMA.INSIGHT_CARDS.length, " shown")), groups.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "empty",
    style: {
      padding: 40
    }
  }, /*#__PURE__*/React.createElement("h3", null, "No insight cards match"), /*#__PURE__*/React.createElement("p", null, "Adjust the filters to see cards.")) : groups.map(g => {
    const gid = `${groupBy}:${g.key}`;
    const isCollapsed = !!collapsed[gid];
    return /*#__PURE__*/React.createElement("div", {
      key: g.key,
      style: {
        marginBottom: 16
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setCollapsed(o => ({
        ...o,
        [gid]: !isCollapsed
      })),
      style: {
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 0",
        background: "none",
        border: 0,
        borderBottom: "2px solid var(--z-sep)",
        cursor: "pointer",
        textAlign: "left",
        marginBottom: 12
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: `b b-${g.color}`
    }, g.label), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        fontWeight: 700,
        color: "var(--z-dark)"
      }
    }, g.items.length), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11.5,
        color: "var(--z-muted)",
        flex: 1,
        minWidth: 0
      },
      className: "txt-fit-1"
    }, g.desc), /*#__PURE__*/React.createElement(Icon, {
      name: isCollapsed ? "chevron-d" : "chevron-u",
      size: 15,
      style: {
        color: "var(--z-muted)",
        flexShrink: 0
      }
    })), !isCollapsed ? /*#__PURE__*/React.createElement("div", {
      className: "g2"
    }, g.items.map(renderCard)) : null);
  }), /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    style: {
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", null, "Technology landscape"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => navigate(`/clients/${entity.id}/techstack`, {
      run: run.id
    })
  }, "Open full stack ", /*#__PURE__*/React.createElement(Icon, {
    name: "arrow-r",
    size: 11
  }))), /*#__PURE__*/React.createElement("div", {
    className: "card-body"
  }, /*#__PURE__*/React.createElement("div", {
    className: "g4"
  }, [{
    label: "Confirmed",
    count: DMA.TECH_STACK.filter(t => t.status === "CONFIRMED").length,
    tone: "b-teal",
    sub: "T1–T3 evidence",
    desc: "Active deployments validated via Explorium and primary sources."
  }, {
    label: "Inferred",
    count: DMA.TECH_STACK.filter(t => t.status === "INFERRED").length,
    tone: "b-purple",
    sub: "Job + press signals",
    desc: "Strong circumstantial signal - not yet confirmed."
  }, {
    label: "Claimed",
    count: 7,
    tone: "b-org",
    sub: "T4–T5 marketing",
    desc: "Marketing pages reference platforms not yet confirmed."
  }, {
    label: "Gaps",
    count: DMA.TECH_STACK.filter(t => t.status === "ABSENT").length,
    tone: "b-below",
    sub: "ABSENT confirmed",
    desc: "Data Cloud · Databricks · Mosaic AI · Twilio Engage."
  }].map((q, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "card-tile"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `b ${q.tone}`
  }, q.label), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 24,
      fontWeight: 200,
      color: "var(--z-teal)",
      letterSpacing: "-.02em",
      lineHeight: 1
    }
  }, q.count)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, q.sub), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      marginTop: 6,
      lineHeight: 1.5
    }
  }, q.desc)))))));
}
Object.assign(window, {
  ClientOverview,
  ClientInsights,
  ScoreRing
});