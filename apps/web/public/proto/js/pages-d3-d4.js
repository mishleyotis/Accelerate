/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Client pages - D3 Heatmap, D4 Platform Matrix
   ═══════════════════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Client pages - D4 Platform Matrix + Stairstep + Roadmap
   (heatmap moved to client-heatmap.jsx)
   ═══════════════════════════════════════════════════════════════════════ */

function hashCode(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h << 5) - h + s.charCodeAt(i);
  return h;
}
window.hashCode = hashCode;

/* ── D4 Platform opportunity matrix ──────────────────────────────── */
function ClientPlatform({
  entity,
  run
}) {
  const route = useRoute();
  const {
    setIpSurface,
    setIpContext,
    setIpOpen,
    openEvidence,
    openRec,
    pushToast
  } = useApp();
  const [platform, setPlatform] = useState(route.params.platform || "SF");
  const [openPrereq, setOpenPrereq] = useState(null);
  useEffect(() => {
    setIpSurface("platform_story");
    setIpContext({
      entity,
      platform
    });
  }, [platform, entity?.id]);
  const platformData = DMA.PLATFORMS;
  const selected = DMA.getPlatform(platform) || {
    id: platform,
    name: platform,
    short: platform,
    features: ""
  };
  const recs = DMA.recsFor(entity.id);

  // Build gap-to-platform mapping from subcaps
  const gaps = entity.subcaps.filter(s => s.score < 3.0 && s.platforms.includes(platform));
  const platformGapCount = pid => entity.subcaps.filter(s => s.score < 3.0 && s.platforms.includes(pid)).length;
  const livePrereqs = (() => {
    const out = [];
    for (const r of recs || []) {
      for (const q of r.prerequisites || []) {
        if (!q || typeof q !== "object") continue;
        out.push({
          id: q.cell || q.condition || r.id,
          name: q.condition || q.cell || r.title,
          min: q.minimum == null ? null : Number(q.minimum),
          current: q.current == null ? null : Number(q.current),
          met: q.verdict ? q.verdict === "MET" : q.minimum != null && q.current != null ? Number(q.current) >= Number(q.minimum) : null,
          basis: q.basis || null,
          note: q.note || null
        });
      }
    }
    return out;
  })();
  const liveStarters = (DMA.startersFor ? DMA.startersFor(entity.id) || [] : []).slice().sort((a, b) => (a.rank || 99) - (b.rank || 99)).map(x => x.text).filter(Boolean);
  const prerequisites = {
    SF: [{
      id: "P4C1",
      name: "Data foundation",
      min: 2.0,
      current: entity.pillar_scores.P4 - 0.1,
      met: entity.pillar_scores.P4 - 0.1 >= 2.0
    }, {
      id: "P2C2",
      name: "Digital service model",
      min: 2.0,
      current: entity.pillar_scores.P2 - 0.2,
      met: entity.pillar_scores.P2 - 0.2 >= 2.0
    }, {
      id: "P1C1",
      name: "Digital strategy",
      min: 2.0,
      current: entity.pillar_scores.P1,
      met: entity.pillar_scores.P1 >= 2.0
    }],
    DB: [{
      id: "P4C1",
      name: "Data foundation",
      min: 2.5,
      current: entity.pillar_scores.P4 - 0.1,
      met: entity.pillar_scores.P4 - 0.1 >= 2.5
    }, {
      id: "P4C2",
      name: "Analytics & insight",
      min: 2.0,
      current: entity.pillar_scores.P4 + 0.6,
      met: entity.pillar_scores.P4 + 0.6 >= 2.0
    }],
    TBL: [{
      id: "P4C1",
      name: "Data foundation",
      min: 2.0,
      current: entity.pillar_scores.P4 - 0.1,
      met: entity.pillar_scores.P4 - 0.1 >= 2.0
    }, {
      id: "P4C2",
      name: "Analytics & insight",
      min: 1.5,
      current: entity.pillar_scores.P4 + 0.6,
      met: entity.pillar_scores.P4 + 0.6 >= 1.5
    }],
    TW: [{
      id: "P2C1",
      name: "Channel experience",
      min: 2.0,
      current: entity.pillar_scores.P2 + 0.1,
      met: entity.pillar_scores.P2 + 0.1 >= 2.0
    }, {
      id: "P2C3",
      name: "Customer journey",
      min: 1.5,
      current: entity.pillar_scores.P2,
      met: entity.pillar_scores.P2 >= 1.5
    }],
    nCino: [{
      id: "P3C1",
      name: "Workflow automation",
      min: 1.5,
      current: entity.pillar_scores.P3,
      met: entity.pillar_scores.P3 >= 1.5
    }, {
      id: "P3C2",
      name: "Loan origination",
      min: 1.5,
      current: entity.pillar_scores.P3 - 0.3,
      met: entity.pillar_scores.P3 - 0.3 >= 1.5
    }]
  };
  const conversationStarters = {
    SF: [`${entity.name}'s P4 score of ${fx(entity.pillar_scores.P4, 1)} in Data Foundation is ${fx(entity.pillar_scores.P4 - (entity.pillar_scores.P4 + 0.3), 1)} below the ${DMA.SUBVERTICAL_LABEL[entity.subvertical].toLowerCase()} peer median. Synovus deployed Data Cloud in Q3 2025 after a similar finding [E-047]. Evidence confirms the root constraint is architectural, not strategic.`, `Three CDO-equivalent hires in your subvertical over the last 12 months - including yours in May 2026 - have led with Data Cloud as the first investment. The 6-9 month integration window before nCino go-live is the highest-leverage moment.`, `Agentforce prerequisites (P4C1 ≥ 2.0, P2C2 ≥ 2.0) are 67% met. The conversation order is: Data Cloud → FSC → Agentforce - not all three at once.`],
    DB: [`${entity.name}'s analytics adoption (Tableau Cloud, 1,800 users) is 1.3 points ahead of its decisioning capability. Mosaic AI on Databricks bridges the gap with existing skill base - no re-platforming.`, `Peer cohort: 22% of regional banks have deployed Databricks for risk decisioning. Capital One and Truist published case studies in 2025.`, `Lakeflow can land on top of the existing Azure footprint - no architectural rework.`],
    TBL: [`Tableau is already deployed at ${entity.name} (1,800 users, 2025 rollout). Tableau Pulse extends to operations leadership with no new infrastructure.`, `Job postings reference "Tableau Pulse Specialist" - the technical curiosity already exists internally.`, `Lower-friction commercial path than introducing a net-new platform - adoption velocity is the differentiator.`],
    TW: [`App store ratings trail regional bank peer median by 0.8 stars. Twilio Engage compresses mobile friction without core replacement.`, `BMO and Truist deployed Twilio in 2025 with 18-point branch deflection within 10 months.`, `Twilio Engage + Service Cloud sequencing reduces operating cost in the branch network while improving NPS.`],
    nCino: [`${entity.name} is mid-migration to nCino core - Workflow Engine is a low-risk extension during go-live.`, `Loan origination cycle is currently 12 days median. First Citizens went from 11 to 4 days post-Workflow Engine deployment.`, `STP rate at 1.8 - Workflow Engine can move this to 3.5 in 6 months on the existing core migration roadmap.`]
  };

  // Live wins; the fixture answers only when there is no promoted data (the
  // standalone prototype). Never undefined.
  const prereqRows = livePrereqs.length ? livePrereqs : prerequisites[platform] || [];
  const starterRows = liveStarters.length ? liveStarters : conversationStarters[platform] || [];
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
        platform
      });
      setIpOpen(true);
    }
  }, "\u2726 Platform story"))), /*#__PURE__*/React.createElement("div", {
    className: "g5",
    style: {
      marginBottom: 16
    }
  }, platformData.map(p => {
    const score = (entity.oss || {})[p.id];
    const isSel = p.id === platform;
    return /*#__PURE__*/React.createElement("div", {
      key: p.id,
      className: `card-tile clickable`,
      onClick: () => setPlatform(p.id),
      style: {
        border: isSel ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)",
        background: isSel ? "var(--z-ice)" : "#fff"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start"
      }
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12.5,
        fontWeight: 600
      }
    }, p.name), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        color: "var(--z-muted)"
      }
    }, p.features.split(" · ").slice(0, 3).join(" · "))), /*#__PURE__*/React.createElement("div", {
      style: {
        textAlign: "right"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 26,
        fontWeight: 200,
        color: score == null ? "var(--z-muted)" : "var(--z-teal)",
        lineHeight: 1
      }
    }, score == null ? "—" : score), /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 9,
        color: "var(--z-muted)"
      }
    }, "/100 OSS"))), /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 10,
        fontSize: 11,
        color: "var(--z-body)"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "b b-org",
      style: {
        marginRight: 4
      }
    }, platformGapCount(p.id), " gaps"), /*#__PURE__*/React.createElement("span", {
      className: "b b-below"
    }, "3 absent")), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        marginTop: 6
      }
    }, "Top: ", entity.subcaps.filter(s => s.platforms.includes(p.id) && s.score < 3).slice(0, 2).map(s => s.name).join(" · ")));
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 380px",
      gap: 16,
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", null, "Gap-to-platform mapping \xB7 ", selected.name), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, gaps.length, " high-priority subcap gaps")), /*#__PURE__*/React.createElement("div", {
    className: "card-body",
    style: {
      padding: 0
    }
  }, /*#__PURE__*/React.createElement("table", {
    className: "tbl"
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Subcap"), /*#__PURE__*/React.createElement("th", null, "Pillar"), /*#__PURE__*/React.createElement("th", null, "Score"), /*#__PURE__*/React.createElement("th", null, "Peer"), /*#__PURE__*/React.createElement("th", null, "Gap"), /*#__PURE__*/React.createElement("th", null, "Feature / L4"))), /*#__PURE__*/React.createElement("tbody", null, gaps.slice(0, 10).map(s => {
    const rowEv = DMA.EVIDENCE.filter(e => e.subcaps && e.subcaps.includes(s.id));
    return /*#__PURE__*/React.createElement("tr", {
      key: s.id,
      className: rowEv.length ? "tbl-click" : "",
      style: rowEv.length ? {
        cursor: "pointer"
      } : null,
      onClick: rowEv.length ? () => openEvidence(rowEv[0].id) : null,
      title: rowEv.length ? `Open evidence ${rowEv[0].id}` : "No direct evidence"
    }, /*#__PURE__*/React.createElement("td", {
      "data-label": "Subcap"
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        fontWeight: 500
      }
    }, s.name), /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, s.id)), /*#__PURE__*/React.createElement("td", {
      "data-label": "Pillar"
    }, /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, s.pillar)), /*#__PURE__*/React.createElement("td", {
      "data-label": "Score"
    }, /*#__PURE__*/React.createElement(MaturityChip, {
      score: s.score
    })), /*#__PURE__*/React.createElement("td", {
      "data-label": "Peer"
    }, /*#__PURE__*/React.createElement(MaturityChip, {
      score: s.peerMedian
    })), /*#__PURE__*/React.createElement("td", {
      "data-label": "Gap"
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontFamily: "var(--font-mono)",
        color: "var(--z-below)"
      }
    }, "\u2212", fx(s.peerMedian - s.score, 1))), /*#__PURE__*/React.createElement("td", {
      "data-label": "Evidence"
    }, rowEv.length ? /*#__PURE__*/React.createElement("span", {
      className: `tier-chip tier-${rowEv[0].tier}`
    }, rowEv[0].id) : /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-body)"
      }
    }, recs.find(r => r.platform === platform)?.feature || "Platform")));
  }), gaps.length === 0 ? /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", {
    colSpan: 6,
    className: "tbl-empty"
  }, "No high-priority gaps for this platform - entity already at or above peer median.")) : null)))), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "shield",
    size: 16
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "Readiness \xB7 ", selected.name), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, "click a row to drill in")), prereqRows.map(p => {
    const isOpen = openPrereq === p.id;
    const subs = entity.subcaps.filter(s => s.id.startsWith(p.id));
    const ev = DMA.EVIDENCE.filter(e => e.subcaps && e.subcaps.some(sid => sid.startsWith(p.id)));
    return /*#__PURE__*/React.createElement("div", {
      key: p.id,
      style: {
        borderBottom: "1px solid var(--z-sep)"
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setOpenPrereq(o => o === p.id ? null : p.id),
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
      className: "b b-purple"
    }, p.id), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 12,
        flex: 1
      }
    }, p.name), /*#__PURE__*/React.createElement("span", {
      className: `b ${p.met ? "b-above" : "b-org"}`
    }, p.met ? "MET" : "PARTIAL"), /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-u" : "chevron-d",
      size: 13,
      style: {
        color: "var(--z-muted)"
      }
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, "Min ", fx(p.min, 1), " \xB7 Current ", fx(p.current, 1), " \xB7 ", subs.length, " subcaps \xB7 ", ev.length, " evidence"), /*#__PURE__*/React.createElement("div", {
      className: "prog",
      style: {
        marginTop: 4,
        height: 4
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "prog-fill",
      style: {
        width: `${Math.min(100, p.current / p.min * 100)}%`,
        background: p.met ? "var(--z-mid)" : "var(--z-org)"
      }
    }))), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        padding: "2px 0 12px"
      }
    }, subs.length ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        margin: "6px 0 4px"
      }
    }, "Backing subcaps") : null, subs.slice(0, 6).map(s => /*#__PURE__*/React.createElement("div", {
      key: s.id,
      className: "row",
      style: {
        gap: 6,
        padding: "3px 0"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: `b ${DMA.helpers.maturityClass(s.score)}`,
      style: {
        width: 30,
        justifyContent: "center"
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
        color: "var(--z-muted)"
      }
    }, s.id))), ev.length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        margin: "8px 0 4px"
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
      onClick: () => openEvidence(e.id)
    }, e.id)))) : null) : null);
  }), prereqRows.some(p => p.met === false) ? /*#__PURE__*/React.createElement("div", {
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
  }, "Lead with the foundation prerequisite conversation before introducing ", selected.name, "."))) : null)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: 16,
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", null, "Recommendations \xB7 ", selected.name)), /*#__PURE__*/React.createElement("div", null, recs.filter(r => r.platform === platform).map(r => /*#__PURE__*/React.createElement("div", {
    key: r.id,
    className: "rec-row",
    onClick: () => openRec(r.id),
    title: "Open full recommendation",
    style: {
      padding: "12px 18px",
      borderBottom: "1px solid var(--z-sep)",
      cursor: "pointer"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "chip"
  }, r.id), /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 600,
      fontSize: 13
    }
  }, r.title), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    className: "b b-teal"
  }, r.phase), /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-r",
    size: 13,
    style: {
      color: "var(--z-muted)"
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      lineHeight: 1.55,
      margin: "6px 0"
    }
  }, "Root cause: ", r.root_cause.map(eid => /*#__PURE__*/React.createElement("button", {
    key: eid,
    className: "chip",
    style: {
      marginRight: 4
    },
    onClick: e => {
      e.stopPropagation();
      openEvidence(eid);
    }
  }, eid))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4, 1fr)",
      gap: 8,
      marginTop: 8,
      fontSize: 11
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 10
    }
  }, "Time"), /*#__PURE__*/React.createElement("strong", null, r.outcomes.time)), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 10
    }
  }, "Effort"), /*#__PURE__*/React.createElement("strong", null, r.outcomes.effort)), /*#__PURE__*/React.createElement("div", {
    style: {
      gridColumn: "span 2"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 10
    }
  }, "Metric"), /*#__PURE__*/React.createElement("strong", null, r.outcomes.metric))))), recs.filter(r => r.platform === platform).length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, "No recommendations for this platform in this run.") : null)), /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", null, "Conversation starters"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => {
      const text = starterRows.map((cs, i) => `#${i + 1} — ${cs}`).join("\n\n");
      try {
        navigator.clipboard.writeText(text);
        pushToast(`Copied ${starterRows.length} conversation starters`, "success");
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
  }, starterRows.map((cs, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      padding: 10,
      marginBottom: 8,
      background: "var(--ph0-lt)",
      border: "1px solid var(--ph0-bd)",
      borderRadius: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, "#", i + 1), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-dpur)"
    }
  }, "Template-fill \xB7 evidence-cited"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    style: {
      color: "var(--z-dpur)"
    },
    onClick: () => {
      try {
        navigator.clipboard.writeText(cs);
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
    }
  }, cs)))))), /*#__PURE__*/React.createElement(StairstepCurve, {
    entity: entity
  }), /*#__PURE__*/React.createElement(TransformationRoadmap, {
    entity: entity
  }));
}

/* ── Stairstepped Maturity Curve component ───────────────────────── */
function StairstepCurve({
  entity
}) {
  const [cluster, setCluster] = useState("P4-data");
  const C = DMA.STAIRSTEP_CLUSTERS[cluster];
  const {
    openEvidence
  } = useApp();
  const W = 880,
    H = 280,
    padL = 60,
    padR = 40,
    padT = 30,
    padB = 60;
  const stepW = (W - padL - padR) / 4;
  // y for each step: M2 lowest, M5 highest
  const stepY = i => H - padB - (i + 1) * (H - padT - padB) / 5;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16
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
    name: "stairs",
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
  }, "Stairstepped maturity curve \xB7 ", C.label), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Where ", entity.name, " is today \u2192 M3 \u2192 M4 \u2192 M5 \xB7 with the platform that enables each step-up")), /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, Object.entries(DMA.STAIRSTEP_CLUSTERS).map(([k, v]) => /*#__PURE__*/React.createElement("button", {
    key: k,
    className: cluster === k ? "on" : "",
    onClick: () => setCluster(k)
  }, v.label)))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 280px",
      gap: 18,
      alignItems: "stretch"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
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
  }, "Leading"), C.steps.map((s, i) => {
    const x = padL + i * stepW;
    const y = stepY(i);
    const w = stepW - 8;
    const h = H - padB - y;
    const platform = (s.platforms || [])[0];
    const plat = DMA.getPlatform(platform) || {
      id: platform,
      name: platform,
      short: platform
    };
    const color = i === 0 ? "var(--m-act)" : i === 1 ? "var(--m-bld)" : i === 2 ? "var(--m-cmp)" : "var(--m-dif)";
    return /*#__PURE__*/React.createElement("g", {
      key: i
    }, /*#__PURE__*/React.createElement("rect", {
      x: x,
      y: y,
      width: w,
      height: h,
      fill: color,
      rx: "6",
      ry: "6",
      opacity: i === 0 ? .6 : 1
    }), /*#__PURE__*/React.createElement("circle", {
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
    }, "M", s.m), /*#__PURE__*/React.createElement("text", {
      x: x + w / 2,
      y: y + 18,
      fontSize: "12",
      fontWeight: "600",
      fill: i >= 2 ? "#fff" : "var(--z-dark)",
      textAnchor: "middle"
    }, s.label), /*#__PURE__*/React.createElement("text", {
      x: x + w / 2,
      y: y + 35,
      fontSize: "9.5",
      fill: i >= 2 ? "rgba(255,255,255,.85)" : "var(--z-body)",
      textAnchor: "middle",
      style: {
        fontFamily: "var(--font-mono)"
      }
    }, platform === "-" ? "" : `via ${plat?.short || platform}`));
  }), C.steps.slice(0, -1).map((s, i) => {
    const x1 = padL + (i + 1) * stepW - 8;
    const y1 = stepY(i);
    const x2 = padL + (i + 1) * stepW;
    const y2 = stepY(i + 1) + (H - padB - stepY(i + 1));
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
  }), /*#__PURE__*/React.createElement("g", null, /*#__PURE__*/React.createElement("circle", {
    cx: padL + 16,
    cy: stepY(0) - 14,
    r: "20",
    fill: "none",
    stroke: "var(--z-org)",
    strokeWidth: "2",
    strokeDasharray: "4 3"
  }), /*#__PURE__*/React.createElement("text", {
    x: padL - 6,
    y: stepY(0) - 30,
    fontSize: "9.5",
    fill: "var(--z-org)",
    fontWeight: "700",
    textAnchor: "end"
  }, "CURRENT"), /*#__PURE__*/React.createElement("text", {
    x: padL - 6,
    y: stepY(0) - 17,
    fontSize: "11",
    fill: "var(--z-dark)",
    fontWeight: "700",
    textAnchor: "end"
  }, fx(C.current, 1))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, C.steps.map((s, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      padding: "10px 12px",
      background: i === 0 ? "var(--m-act)" : i === 1 ? "rgba(98,215,184,.15)" : i === 2 ? "var(--z-ice)" : "rgba(19,159,148,.10)",
      borderRadius: 8,
      border: "1px solid var(--z-sep)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `b ${i === 0 ? "b-act" : i === 1 ? "b-bld" : i === 2 ? "b-cmp" : "b-dif"}`
  }, "M", s.m, " ", s.label), s.platforms[0] !== "-" ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-mid)"
    }
  }, s.platforms.map(p => DMA.getPlatform(p)?.short || p).join(" + ")) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-dark)",
      lineHeight: 1.55
    }
  }, s.note))))));
}

/* ── Transformation Roadmap (Pattern J: 3-phase chevrons) ───────── */
function TransformationRoadmap({
  entity
}) {
  const {
    openEvidence,
    openRec,
    pushToast
  } = useApp();
  const [view, setView] = useState("chevrons"); // chevrons | curve | impact
  const roadmap = DMA.ROADMAP;
  const recs = DMA.RECOMMENDATIONS;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 16
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
    name: "route",
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
  }, "Transformation roadmap"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "From Assessment Report \xB7 3-phase sequencing aligned to the maturity curve above")), /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, /*#__PURE__*/React.createElement("button", {
    className: view === "chevrons" ? "on" : "",
    onClick: () => setView("chevrons")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "route",
    size: 11
  }), " Chevrons"), /*#__PURE__*/React.createElement("button", {
    className: view === "curve" ? "on" : "",
    onClick: () => setView("curve")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "stairs",
    size: 11
  }), " Step curve"), /*#__PURE__*/React.createElement("button", {
    className: view === "impact" ? "on" : "",
    onClick: () => setView("impact")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "users",
    size: 11
  }), " Customer impact")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => pushToast(`Exporting ${entity.name} roadmap (${view} view)…`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 11
  }), " Export")), view === "chevrons" ? /*#__PURE__*/React.createElement(ChevronView, {
    roadmap: roadmap,
    recs: recs,
    openRec: openRec
  }) : view === "curve" ? /*#__PURE__*/React.createElement(StepCurveView, {
    roadmap: roadmap,
    entity: entity
  }) : /*#__PURE__*/React.createElement(CustomerImpactView, {
    roadmap: roadmap,
    recs: recs,
    openRec: openRec
  }), /*#__PURE__*/React.createElement("div", {
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
  }, "Foundation (P4C1) must reach M3 before Phase 2 can deliver on Marketing + Engage. Mosaic AI in Phase 3 requires the Lakehouse from Phase 1 to be operational. Phases overlap - staffing is concurrent, not sequential."))));
}
function ChevronView({
  roadmap,
  recs,
  openRec
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(3, 1fr)",
      gap: 12,
      marginBottom: 12
    }
  }, roadmap.map((r, i) => /*#__PURE__*/React.createElement("div", {
    key: r.phase,
    style: {
      position: "relative"
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
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
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
      textAlign: "right"
    }
  }, r.duration))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(3, 1fr)",
      gap: 12
    }
  }, roadmap.map(r => /*#__PURE__*/React.createElement("div", {
    key: r.phase,
    style: {
      background: r.color,
      borderRadius: 8,
      padding: 14,
      color: "#fff"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "rgba(255,255,255,.7)",
      letterSpacing: ".06em",
      textTransform: "uppercase",
      marginBottom: 4
    }
  }, "Platform"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      marginBottom: 10
    }
  }, r.platform), /*#__PURE__*/React.createElement("div", {
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
    }
  }, r.target), /*#__PURE__*/React.createElement("div", {
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
  }, r.metric), /*#__PURE__*/React.createElement("div", {
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
  }, r.recs.map(rid => {
    const rec = recs.find(x => x.id === rid);
    return rec ? /*#__PURE__*/React.createElement("button", {
      key: rid,
      onClick: e => {
        e.stopPropagation();
        openRec(rid);
      },
      style: {
        padding: "6px 8px",
        background: "rgba(255,255,255,.14)",
        borderRadius: 5,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 6,
        border: 0,
        color: "#fff",
        textAlign: "left",
        cursor: "pointer",
        transition: "background 120ms"
      },
      onMouseEnter: e => e.currentTarget.style.background = "rgba(255,255,255,.22)",
      onMouseLeave: e => e.currentTarget.style.background = "rgba(255,255,255,.14)"
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10.5,
        fontWeight: 600
      }
    }, rec.id), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10.5,
        color: "rgba(255,255,255,.85)",
        flex: 1,
        minWidth: 0
      },
      className: "txt-trunc"
    }, rec.title), /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-r",
      size: 11
    })) : null;
  }))))));
}
function StepCurveView({
  roadmap,
  entity
}) {
  const [selectedStep, setSelectedStep] = useState(null);
  const {
    openRec
  } = useApp();
  // Plot composite maturity over time
  const points = [{
    t: 0,
    m: entity.overall,
    label: "Today",
    phase: null
  }, {
    t: 6,
    m: entity.overall + 0.3,
    label: "End P1",
    phase: 1
  }, {
    t: 12,
    m: entity.overall + 0.7,
    label: "End P2",
    phase: 2
  }, {
    t: 18,
    m: entity.overall + 1.1,
    label: "End P3",
    phase: 3
  }];
  const W = 880,
    H = 280,
    padL = 50,
    padR = 30,
    padT = 30,
    padB = 50;
  const xFor = t => padL + t / 18 * (W - padL - padR);
  const yFor = m => H - padB - (m - 1) / 4 * (H - padT - padB);
  const selectedPhase = selectedStep != null ? roadmap.find(r => r.phase === points[selectedStep].phase) : null;
  const recs = DMA.RECOMMENDATIONS;
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      background: "linear-gradient(180deg, var(--z-bg), #fff)",
      borderRadius: 10,
      padding: 14,
      border: "1px solid var(--z-sep)",
      position: "relative",
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: assetUrl("illo_curvesTL", "brand/illustrations/curves_topleft.png"),
    alt: "",
    style: {
      position: "absolute",
      top: 0,
      left: 0,
      width: 300,
      opacity: .4,
      pointerEvents: "none"
    }
  }), /*#__PURE__*/React.createElement("svg", {
    width: "100%",
    viewBox: `0 0 ${W} ${H}`,
    style: {
      display: "block",
      position: "relative"
    }
  }, [1, 2, 3, 4, 5].map(m => /*#__PURE__*/React.createElement("g", {
    key: m
  }, /*#__PURE__*/React.createElement("line", {
    x1: padL,
    y1: yFor(m),
    x2: W - padR,
    y2: yFor(m),
    stroke: "var(--z-sep)",
    strokeDasharray: "3 3"
  }), /*#__PURE__*/React.createElement("text", {
    x: padL - 8,
    y: yFor(m) + 3,
    fontSize: "10",
    fill: "var(--z-muted)",
    textAnchor: "end"
  }, "M", m))), roadmap.map((r, i) => /*#__PURE__*/React.createElement("rect", {
    key: r.phase,
    x: xFor(i === 0 ? 0 : i === 1 ? 6 : 12),
    y: padT,
    width: xFor(6) - padL,
    height: H - padT - padB,
    fill: r.color,
    opacity: ".06"
  })), /*#__PURE__*/React.createElement("path", {
    d: `M ${xFor(0)} ${yFor(points[0].m)} ${points.slice(1).map(p => `L ${xFor(p.t)} ${yFor(p.m)}`).join(" ")}`,
    fill: "none",
    stroke: "var(--z-teal)",
    strokeWidth: "2.5"
  }), points.map((p, i) => /*#__PURE__*/React.createElement("g", {
    key: i,
    style: {
      cursor: "pointer"
    },
    onClick: () => setSelectedStep(i === selectedStep ? null : i)
  }, /*#__PURE__*/React.createElement("circle", {
    cx: xFor(p.t),
    cy: yFor(p.m),
    r: "14",
    fill: "transparent"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: xFor(p.t),
    cy: yFor(p.m),
    r: selectedStep === i ? "10" : "7",
    fill: "#fff",
    stroke: selectedStep === i ? "var(--z-mid)" : "var(--z-teal)",
    strokeWidth: "3"
  }), /*#__PURE__*/React.createElement("text", {
    x: xFor(p.t),
    y: yFor(p.m) - 16,
    fontSize: "11",
    fontWeight: "700",
    fill: "var(--z-dark)",
    textAnchor: "middle"
  }, fx(p.m, 1)), /*#__PURE__*/React.createElement("text", {
    x: xFor(p.t),
    y: H - padB + 18,
    fontSize: "10",
    fill: selectedStep === i ? "var(--z-mid)" : "var(--z-muted)",
    fontWeight: selectedStep === i ? 700 : 400,
    textAnchor: "middle"
  }, p.label), /*#__PURE__*/React.createElement("text", {
    x: xFor(p.t),
    y: H - padB + 32,
    fontSize: "9",
    fill: "var(--z-muted)",
    textAnchor: "middle"
  }, p.t === 0 ? "0 mo" : `${p.t} mo`))), roadmap.map((r, i) => {
    const x = xFor(i === 0 ? 3 : i === 1 ? 9 : 15);
    return /*#__PURE__*/React.createElement("text", {
      key: r.phase,
      x: x,
      y: padT - 8,
      fontSize: "11",
      fontWeight: "700",
      fill: r.color,
      textAnchor: "middle"
    }, r.label.toUpperCase());
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      textAlign: "center",
      marginTop: 6
    }
  }, "Click any milestone for the phase plan")), selectedPhase ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 12,
      padding: 16,
      background: selectedPhase.color,
      borderRadius: 10,
      color: "#fff",
      position: "relative"
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => setSelectedStep(null),
    className: "icon-btn",
    style: {
      position: "absolute",
      top: 10,
      right: 10,
      color: "rgba(255,255,255,.7)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "x",
    size: 14
  })), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      color: "rgba(255,255,255,.8)",
      letterSpacing: ".08em",
      textTransform: "uppercase"
    }
  }, "Phase ", selectedPhase.phase), /*#__PURE__*/React.createElement("strong", {
    style: {
      fontSize: 16
    }
  }, selectedPhase.label), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-mint-lt)"
    }
  }, selectedPhase.duration, " \xB7 target ", selectedPhase.target)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      color: "var(--z-mint-lt)",
      marginBottom: 10,
      lineHeight: 1.55
    }
  }, "By the end of this phase, ", entity.name, " reaches ", /*#__PURE__*/React.createElement("strong", {
    style: {
      color: "#fff"
    }
  }, fx(points.find(p => p.phase === selectedPhase.phase).m, 1)), " composite maturity (", Math.round((points.find(p => p.phase === selectedPhase.phase).m - entity.overall) * 100) / 100, " from today). Success metric: ", selectedPhase.metric, "."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: 8
    }
  }, selectedPhase.recs.map(rid => {
    const r = recs.find(x => x.id === rid);
    if (!r) return null;
    return /*#__PURE__*/React.createElement("button", {
      key: rid,
      onClick: () => openRec(rid),
      style: {
        padding: "10px 12px",
        background: "rgba(255,255,255,.16)",
        border: 0,
        borderRadius: 6,
        textAlign: "left",
        cursor: "pointer",
        color: "#fff",
        transition: "background 120ms"
      },
      onMouseEnter: e => e.currentTarget.style.background = "rgba(255,255,255,.24)",
      onMouseLeave: e => e.currentTarget.style.background = "rgba(255,255,255,.16)"
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 4
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10.5,
        fontWeight: 700
      }
    }, r.id), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-r",
      size: 11
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        fontWeight: 500
      }
    }, r.title), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-mint-lt)",
        marginTop: 4
      }
    }, r.outcomes.time, " \xB7 effort ", r.outcomes.effort));
  }))) : null);
}
function CustomerImpactView({
  roadmap,
  recs,
  openRec
}) {
  // For each phase, show customer-facing metrics
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(3, 1fr)",
      gap: 12
    }
  }, roadmap.map(r => {
    // Get impact from ROADMAP_IMPACTS for this phase's recs
    const impacts = r.recs.map(rid => DMA.ROADMAP_IMPACTS[rid]).filter(Boolean);
    const merged = {};
    impacts.forEach(im => Object.entries(im.customer_impact).forEach(([k, v]) => {
      merged[k] = v;
    }));
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
        marginBottom: 10
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        color: r.color,
        letterSpacing: ".08em",
        textTransform: "uppercase"
      }
    }, "Phase ", r.phase), /*#__PURE__*/React.createElement("strong", {
      style: {
        fontSize: 13
      }
    }, r.label)), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        textTransform: "uppercase",
        letterSpacing: ".06em",
        marginBottom: 8
      }
    }, "Customer-facing impact"), Object.entries(merged).map(([k, v]) => /*#__PURE__*/React.createElement("div", {
      key: k,
      className: "row",
      style: {
        padding: "6px 0",
        borderTop: "1px solid var(--z-sep)"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        flex: 1
      }
    }, k.replace(/_/g, " ")), /*#__PURE__*/React.createElement("strong", {
      style: {
        fontSize: 12,
        color: "var(--z-mid)"
      }
    }, v))), /*#__PURE__*/React.createElement("div", {
      className: "sep",
      style: {
        margin: "10px 0"
      }
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        flexDirection: "column",
        gap: 4
      }
    }, r.recs.map(rid => {
      const rec = recs.find(x => x.id === rid);
      return rec ? /*#__PURE__*/React.createElement("button", {
        key: rid,
        onClick: () => openRec(rid),
        style: {
          padding: "6px 8px",
          background: "var(--z-lav)",
          border: 0,
          borderRadius: 5,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          textAlign: "left",
          cursor: "pointer",
          fontSize: 10.5
        }
      }, /*#__PURE__*/React.createElement("strong", {
        style: {
          color: "var(--z-dark)"
        }
      }, rec.id), /*#__PURE__*/React.createElement("span", {
        style: {
          color: "var(--z-muted)",
          flex: 1,
          marginLeft: 6
        },
        className: "txt-trunc"
      }, rec.title), /*#__PURE__*/React.createElement(Icon, {
        name: "arrow-r",
        size: 11,
        style: {
          color: "var(--z-muted)"
        }
      })) : null;
    })));
  }));
}
Object.assign(window, {
  ClientPlatform
});