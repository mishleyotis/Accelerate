/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · D3 Maturity Heatmap (refactored)
   Multiple view modes · synthesis drawer · working overlays
   ═══════════════════════════════════════════════════════════════════════ */

function ClientHeatmap({
  entity,
  run
}) {
  const route = useRoute();
  const {
    audience,
    openEvidence,
    openInsight,
    setIpSurface,
    setIpContext,
    tweaks,
    pushToast
  } = useApp();
  const [mode, setMode] = useState(route.params.hm || (audience === "customer" ? "focus" : "focus")); // focus | standard | value_chain
  const [zoom, setZoom] = useState(route.params.zoom || "category");
  const [pillarFocus, setPillarFocus] = useState(route.params.pillar || null);
  const [catFocus, setCatFocus] = useState(route.params.cat || null);
  const [showPeers, setShowPeers] = useState(true);
  const [showIssues, setShowIssues] = useState(false);
  const [focusArea, setFocusArea] = useState(null);
  const [synthSubcap, setSynthSubcap] = useState(null);

  // In customer mode, lock to focus / value_chain views only
  useEffect(() => {
    if (audience === "customer" && mode === "standard") setMode("focus");
  }, [audience]);

  // Compute per-category aggregate scores
  const catAgg = useMemo(() => {
    const out = {};
    for (const cat of DMA.CATEGORIES) {
      const subs = entity.subcaps.filter(s => s.category === cat.id);
      const avg = subs.reduce((a, s) => a + s.score, 0) / Math.max(1, subs.length);
      const peer = subs.reduce((a, s) => a + s.peerMedian, 0) / Math.max(1, subs.length);
      const thin = subs.filter(s => s.thin).length;
      out[cat.id] = {
        avg,
        peer,
        thin,
        total: subs.length
      };
    }
    return out;
  }, [entity?.id]);

  // Synth helper: derive what subcap belongs to focus area
  const subcapsForFocusArea = fa => fa ? entity.subcaps.filter(s => fa.subcaps.some(prefix => s.id.startsWith(prefix.slice(0, 4)))) : [];
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "page-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, "Maturity heatmap"), /*#__PURE__*/React.createElement("h1", null, "Where ", entity.name, " is today"), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, entity.subcaps.length, " subcaps \xB7 ", entity.subcaps.filter(s => s.thin).length, " thin \xB7 overall maturity ", DMA.helpers.maturityLabel(entity.overall).toLowerCase())), /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast(`Exporting ${entity.name} heatmap as PDF…`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Export"))), /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 14,
      padding: "12px 16px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      flexWrap: "wrap",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".08em"
    }
  }, "View"), /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, /*#__PURE__*/React.createElement("button", {
    className: mode === "focus" ? "on" : "",
    onClick: () => {
      setMode("focus");
      setFocusArea(null);
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "sparkle",
    size: 11
  }), " Focus areas"), /*#__PURE__*/React.createElement("button", {
    className: mode === "standard" ? "on" : "",
    onClick: () => setMode("standard")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "heatmap",
    size: 11
  }), " Standard"), /*#__PURE__*/React.createElement("button", {
    className: mode === "value_chain" ? "on" : "",
    onClick: () => setMode("value_chain")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "route",
    size: 11
  }), " Value chain"))), /*#__PURE__*/React.createElement("span", {
    style: {
      width: 1,
      height: 22,
      background: "var(--z-sep)"
    }
  }), mode === "standard" ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".08em"
    }
  }, "Zoom"), /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, ["pillar", "category", "capability", "subcap"].map(z => /*#__PURE__*/React.createElement("button", {
    key: z,
    className: zoom === z ? "on" : "",
    onClick: () => setZoom(z)
  }, z[0].toUpperCase() + z.slice(1))))) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("label", {
    className: "row",
    style: {
      fontSize: 11.5,
      cursor: "pointer"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `switch ${showPeers ? "on" : ""}`,
    onClick: () => setShowPeers(p => !p)
  }), "Peers"), /*#__PURE__*/React.createElement("label", {
    className: "row",
    style: {
      fontSize: 11.5,
      cursor: "pointer"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `switch ${showIssues ? "on" : ""}`,
    onClick: () => setShowIssues(p => !p)
  }), "Issues"), /*#__PURE__*/React.createElement(Legend, null)), (pillarFocus || catFocus) && mode === "standard" ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 10,
      fontSize: 12,
      color: "var(--z-body)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, "Drilling:"), pillarFocus ? /*#__PURE__*/React.createElement("span", {
    className: "chip purple"
  }, pillarFocus) : null, catFocus ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-r",
    size: 11
  }), /*#__PURE__*/React.createElement("span", {
    className: "chip"
  }, catFocus)) : null, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => {
      setPillarFocus(null);
      setCatFocus(null);
      setZoom("category");
    }
  }, "Reset")) : null), mode === "focus" ? /*#__PURE__*/React.createElement(FocusAreaView, {
    entity: entity,
    run: run,
    focusArea: focusArea,
    setFocusArea: setFocusArea,
    subcapsForFocusArea: subcapsForFocusArea,
    openSubcap: setSynthSubcap,
    openEvidence: openEvidence,
    openInsight: openInsight,
    showIssues: showIssues
  }) : mode === "value_chain" ? /*#__PURE__*/React.createElement(ValueChainView, {
    entity: entity,
    subcapsForFocusArea: subcapsForFocusArea,
    openSubcap: setSynthSubcap,
    openInsight: openInsight
  }) : /*#__PURE__*/React.createElement(React.Fragment, null, showIssues ? /*#__PURE__*/React.createElement(IssueRegisterBanner, {
    entity: entity,
    onSubcap: s => setSynthSubcap({
      kind: "subcap",
      subcap: s
    }),
    openEvidence: openEvidence
  }) : null, zoom === "pillar" ? /*#__PURE__*/React.createElement(PillarHeatmap, {
    entity: entity,
    setPillarFocus: p => {
      setPillarFocus(p);
      setZoom("category");
    }
  }) : zoom === "category" ? /*#__PURE__*/React.createElement(CategoryHeatmap, {
    entity: entity,
    pillarFocus: pillarFocus,
    catAgg: catAgg,
    showPeers: showPeers,
    showIssues: showIssues,
    setCatFocus: c => {
      setCatFocus(c);
      setZoom("capability");
    },
    onSynth: catId => {
      setSynthSubcap({
        kind: "category",
        catId
      });
    }
  }) : /*#__PURE__*/React.createElement(SubcapHeatmap, {
    entity: entity,
    catFocus: catFocus,
    pillarFocus: pillarFocus,
    showPeers: showPeers,
    showIssues: showIssues,
    setCatFocus: setCatFocus,
    onSynth: s => setSynthSubcap({
      kind: "subcap",
      subcap: s
    })
  })), synthSubcap ? /*#__PURE__*/React.createElement(SynthesisDrawer, {
    entity: entity,
    item: synthSubcap,
    onClose: () => setSynthSubcap(null),
    openEvidence: openEvidence,
    openInsight: openInsight,
    showIssues: showIssues
  }) : null);
}

/* ─────────────────────── FOCUS AREA VIEW ─────────────────────── */
function FocusAreaView({
  entity,
  run,
  focusArea,
  setFocusArea,
  subcapsForFocusArea,
  openSubcap,
  openEvidence,
  openInsight
}) {
  if (!focusArea) {
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 12
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "sparkle",
      size: 15,
      style: {
        color: "var(--z-dpur)"
      }
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, "Strategic priorities for ", entity.name), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, "Click any focus area to drill in")), /*#__PURE__*/React.createElement("div", {
      className: "g3"
    }, DMA.FOCUS_AREAS.map(fa => {
      const subs = subcapsForFocusArea(fa);
      const avg = subs.length ? subs.reduce((a, s) => a + s.score, 0) / subs.length : 2.5;
      const peer = subs.length ? subs.reduce((a, s) => a + s.peerMedian, 0) / subs.length : 2.8;
      const gap = peer - avg;
      return /*#__PURE__*/React.createElement("div", {
        key: fa.id,
        className: "fa-card",
        onClick: () => setFocusArea(fa)
      }, /*#__PURE__*/React.createElement("div", {
        className: "fa-illo",
        style: {
          background: `linear-gradient(135deg, ${fa.colors[0]}, ${fa.colors[1]})`
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "icon-block"
      }, /*#__PURE__*/React.createElement(Icon, {
        name: fa.icon,
        size: 16
      })), /*#__PURE__*/React.createElement("div", {
        className: "title-block"
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 13,
          fontWeight: 700
        }
      }, fa.name), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10.5,
          opacity: .92
        }
      }, subs.length, " subcaps"))), /*#__PURE__*/React.createElement("div", {
        className: "fa-meta"
      }, /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          marginBottom: 8
        }
      }, /*#__PURE__*/React.createElement(MaturityChip, {
        score: avg
      }), /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 11,
          color: "var(--z-muted)"
        }
      }, "Peer ", peer.toFixed(1)), gap > 0.3 ? /*#__PURE__*/React.createElement("span", {
        className: "b b-below",
        style: {
          marginLeft: "auto"
        }
      }, "\u2212", gap.toFixed(1)) : /*#__PURE__*/React.createElement("span", {
        className: "b b-above",
        style: {
          marginLeft: "auto"
        }
      }, "at peer")), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 12,
          color: "var(--z-body)",
          lineHeight: 1.5
        },
        className: "txt-fit-2"
      }, fa.description)));
    })));
  }

  // Selected focus area detail
  const fa = focusArea;
  const subs = subcapsForFocusArea(fa);
  const avg = subs.length ? subs.reduce((a, s) => a + s.score, 0) / subs.length : 2.5;
  const peer = subs.length ? subs.reduce((a, s) => a + s.peerMedian, 0) / subs.length : 2.8;
  const insights = DMA.INSIGHT_CARDS.filter(ic => ic.affects.some(sid => fa.subcaps.some(p => sid.startsWith(p.slice(0, 4)))));
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      padding: "22px 24px",
      background: `linear-gradient(135deg, ${fa.colors[0]}10, ${fa.colors[1]}1a)`,
      borderBottom: "1px solid var(--z-sep)",
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: assetUrl("illo_curvesTR", "brand/illustrations/curves_topright.png"),
    alt: "",
    style: {
      position: "absolute",
      right: -60,
      top: -40,
      width: 360,
      height: "auto",
      opacity: .55,
      pointerEvents: "none"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      display: "flex",
      justifyContent: "space-between",
      alignItems: "flex-start",
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0,
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => setFocusArea(null),
    className: "row",
    style: {
      fontSize: 11.5,
      color: "var(--z-mid)",
      background: "transparent",
      padding: "4px 8px 4px 0",
      border: 0,
      marginBottom: 8,
      cursor: "pointer"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-l",
    size: 12
  }), " All focus areas"), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 36,
      height: 36,
      borderRadius: 9,
      background: fa.colors[0],
      color: "#fff",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: fa.icon,
    size: 18
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 6,
      marginBottom: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, "FOCUS AREA \xB7 ", fa.id), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)"
    }
  }, subs.length, " subcaps")), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 22,
      fontWeight: 600,
      color: "var(--z-dark)",
      letterSpacing: "-.015em"
    }
  }, fa.name))), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      color: "var(--z-body)",
      lineHeight: 1.5,
      maxWidth: 640
    }
  }, fa.description)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 16,
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(ScoreRing, {
    score: avg,
    size: 88
  })))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "14px 20px",
      background: "var(--z-bg)",
      display: "flex",
      gap: 14,
      alignItems: "flex-start",
      borderBottom: "1px solid var(--z-sep)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "doc",
    size: 16,
    style: {
      color: "var(--z-dpur)",
      flexShrink: 0,
      marginTop: 2
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, "SOURCE"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, fa.source.type, " \xB7 p.", fa.source.page, " \xB7 ", fa.source.doc)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      color: "var(--z-dark)",
      fontStyle: "italic",
      lineHeight: 1.55
    }
  }, "\"", fa.strategic_quote.replace(/[“”]/g, ""), "\""), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 5
    }
  }, "Financial reference: ", fa.financial_ref)))), /*#__PURE__*/React.createElement(CustomizableKpiStrip, {
    fa: fa,
    entity: entity
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "280px 1fr",
      gap: 14,
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      marginBottom: 8
    }
  }, "Pillar contribution"), Object.entries(fa.pillars_weight).map(([p, w]) => /*#__PURE__*/React.createElement("div", {
    key: p,
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      fontSize: 11,
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "chip purple",
    style: {
      minWidth: 26,
      textAlign: "center"
    }
  }, p), /*#__PURE__*/React.createElement("div", {
    className: "prog",
    style: {
      flex: 1,
      height: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "prog-fill",
    style: {
      width: `${w}%`,
      background: DMA.helpers.maturityHex(entity.pillar_scores[p])
    }
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      width: 30,
      textAlign: "right"
    }
  }, w, "%"))), /*#__PURE__*/React.createElement("div", {
    className: "sep"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      lineHeight: 1.5
    }
  }, "Weights reflect how much each DMA pillar contributes to this focus area composite. ", entity.name, "'s actual scores drive the bar fill colours.")), /*#__PURE__*/React.createElement("div", {
    className: "card"
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
      fontSize: 13,
      fontWeight: 600
    }
  }, "Subcap heatmap"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, subs.length, " cells \xB7 click any cell for synthesis")), /*#__PURE__*/React.createElement("div", {
    className: "hm",
    style: {
      gridTemplateColumns: `repeat(${Math.min(subs.length, 8)}, 1fr)`,
      gap: 5
    }
  }, subs.map(s => /*#__PURE__*/React.createElement("button", {
    key: s.id,
    onClick: () => openSubcap({
      kind: "subcap",
      subcap: s
    }),
    className: `hm-cell b ${DMA.helpers.maturityClass(s.score)} ${s.thin ? "thin" : ""}`,
    style: {
      flexDirection: "column",
      height: 56,
      fontSize: 11,
      padding: 4,
      border: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      fontWeight: 700
    }
  }, s.score.toFixed(1)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 8.5,
      opacity: .85,
      fontFamily: "var(--font-mono)"
    }
  }, s.id.split(".").slice(1).join("."))))))), /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", null, "Insight cards in this focus area"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, insights.length, " cards")), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 14
    }
  }, insights.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 12
    }
  }, "No insight cards yet") : /*#__PURE__*/React.createElement("div", {
    className: "g2"
  }, insights.map(ic => /*#__PURE__*/React.createElement("div", {
    key: ic.id,
    className: `ic ${ic.flag.toLowerCase()}`,
    onClick: () => openInsight(ic.id)
  }, /*#__PURE__*/React.createElement("div", {
    className: "ic-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "ic-id"
  }, ic.id), /*#__PURE__*/React.createElement("span", {
    className: `b ${ic.flag === "CRITICAL" ? "b-below" : ic.flag === "OPPORTUNITY" ? "b-org" : "b-teal"}`
  }, ic.flag))), /*#__PURE__*/React.createElement("div", {
    className: "ic-title"
  }, ic.title), /*#__PURE__*/React.createElement("div", {
    className: "ic-body txt-fit-2"
  }, ic.what), /*#__PURE__*/React.createElement("div", {
    className: "ic-foot"
  }, ic.platforms.map(p => /*#__PURE__*/React.createElement("span", {
    key: p,
    className: "b b-teal"
  }, DMA.getPlatform(p)?.short)))))))));
}

/* ── Customisable KPI strip ─────────────────────────────────────── */
function CustomizableKpiStrip({
  fa,
  entity
}) {
  // Each KPI gets a "source mode": "public" (inferred from public DMA) or "client" (provided / awaiting client input) or "hidden"
  const [modes, setModes] = useState(() => fa.kpis.reduce((m, k) => {
    m[k.label] = "public";
    return m;
  }, {}));
  const [editing, setEditing] = useState(null);
  const [drafts, setDrafts] = useState({});
  const cycleMode = label => {
    setModes(m => ({
      ...m,
      [label]: m[label] === "public" ? "client" : m[label] === "client" ? "hidden" : "public"
    }));
  };
  const saveDraft = label => {
    setEditing(null);
  };
  return /*#__PURE__*/React.createElement("div", {
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
    name: "scale",
    size: 14
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "KPI baseline \xB7 target"), /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, "Customise per client"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Toggle each KPI between Public inference \xB7 Client-provided \xB7 Hidden")), /*#__PURE__*/React.createElement("div", {
    className: "g3"
  }, fa.kpis.map(k => {
    const mode = modes[k.label];
    const isEditing = editing === k.label;
    const isHidden = mode === "hidden";
    const isClient = mode === "client";
    const meta = isClient ? {
      tag: "Client-provided",
      color: "var(--z-dpur)",
      bg: "var(--ph0-lt)",
      bd: "var(--ph0-bd)",
      icon: "user"
    } : isHidden ? {
      tag: "Not available",
      color: "var(--z-muted)",
      bg: "var(--z-lav)",
      bd: "var(--z-sep)",
      icon: "lock"
    } : {
      tag: "Public DMA inference",
      color: "var(--z-mid)",
      bg: "var(--z-ice)",
      bd: "rgba(39,187,175,.3)",
      icon: "globe"
    };
    return /*#__PURE__*/React.createElement("div", {
      key: k.label,
      className: "card-tile",
      style: {
        padding: 12,
        border: `1px solid ${meta.bd}`,
        background: meta.bg
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 6
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        textTransform: "uppercase",
        letterSpacing: ".06em",
        flex: 1
      },
      className: "txt-fit-1"
    }, k.label), /*#__PURE__*/React.createElement("button", {
      className: "icon-btn",
      style: {
        width: 22,
        height: 22,
        color: meta.color
      },
      title: `Source: ${meta.tag} · click to change`,
      onClick: () => cycleMode(k.label)
    }, /*#__PURE__*/React.createElement(Icon, {
      name: meta.icon,
      size: 11
    })), /*#__PURE__*/React.createElement("button", {
      className: "icon-btn",
      style: {
        width: 22,
        height: 22,
        color: "var(--z-muted)"
      },
      title: "Edit values",
      onClick: () => setEditing(isEditing ? null : k.label)
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "edit",
      size: 11
    }))), !isHidden && !isEditing ? /*#__PURE__*/React.createElement("div", {
      className: "row"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 16,
        fontWeight: 700,
        color: "var(--z-dark)"
      }
    }, drafts[k.label + "_current"] || k.current), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9,
        color: "var(--z-muted)"
      }
    }, "current")), /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-r",
      size: 12,
      style: {
        color: "var(--z-muted)"
      }
    }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 16,
        fontWeight: 700,
        color: meta.color
      }
    }, drafts[k.label + "_target"] || k.target), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9,
        color: "var(--z-muted)"
      }
    }, "target")), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      className: `b`,
      style: {
        background: meta.bd,
        color: meta.color,
        fontSize: 9
      }
    }, k.delta)) : isEditing ? /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        flexDirection: "column",
        gap: 6
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 6
      }
    }, /*#__PURE__*/React.createElement("input", {
      className: "inp",
      style: {
        padding: "4px 8px",
        fontSize: 11
      },
      placeholder: "Current",
      defaultValue: drafts[k.label + "_current"] || k.current,
      onChange: e => setDrafts(d => ({
        ...d,
        [k.label + "_current"]: e.target.value
      }))
    }), /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-r",
      size: 11,
      style: {
        color: "var(--z-muted)"
      }
    }), /*#__PURE__*/React.createElement("input", {
      className: "inp",
      style: {
        padding: "4px 8px",
        fontSize: 11
      },
      placeholder: "Target",
      defaultValue: drafts[k.label + "_target"] || k.target,
      onChange: e => setDrafts(d => ({
        ...d,
        [k.label + "_target"]: e.target.value
      }))
    })), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 4
      }
    }, /*#__PURE__*/React.createElement("button", {
      className: "btn btn-primary btn-sm",
      style: {
        padding: "3px 8px",
        fontSize: 10.5
      },
      onClick: () => saveDraft(k.label)
    }, "Save"), /*#__PURE__*/React.createElement("button", {
      className: "btn btn-tertiary btn-sm",
      style: {
        padding: "3px 8px",
        fontSize: 10.5
      },
      onClick: () => setEditing(null)
    }, "Cancel"))) : /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: meta.color,
        padding: "4px 0",
        display: "flex",
        alignItems: "center",
        gap: 6
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "lock",
      size: 11
    }), " Hidden - not inferable from public sources"), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        color: meta.color,
        marginTop: 5,
        fontWeight: 600
      }
    }, meta.tag.toUpperCase()));
  })), /*#__PURE__*/React.createElement("div", {
    className: "co co-teal",
    style: {
      marginTop: 10
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 13
  }), /*#__PURE__*/React.createElement("div", {
    className: "co-body"
  }, "Some KPIs can only be inferred indirectly from public sources (annual reports, hiring signals, app store reviews). Click the source icon to switch a KPI between ", /*#__PURE__*/React.createElement("strong", null, "Public DMA inference"), ", ", /*#__PURE__*/React.createElement("strong", null, "Client-provided"), " (when you receive direct data in a meeting), or ", /*#__PURE__*/React.createElement("strong", null, "Hidden"), " (when no reliable source exists). Use the edit icon to enter values directly.")));
}

/* ─────────────────────── PILLAR HEATMAP ─────────────────────── */
function PillarHeatmap({
  entity,
  setPillarFocus
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "g4"
  }, DMA.PILLARS.map(p => {
    const score = entity.pillar_scores[p.id];
    const peer = score + 0.3;
    return /*#__PURE__*/React.createElement("div", {
      key: p.id,
      className: "card-tile clickable",
      onClick: () => setPillarFocus(p.id),
      style: {
        padding: 16
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 12
      }
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, p.id), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 14,
        fontWeight: 600
      }
    }, p.name)), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement(MaturityChip, {
      score: score,
      large: true
    })), /*#__PURE__*/React.createElement("div", {
      className: "prog"
    }, /*#__PURE__*/React.createElement("div", {
      className: "prog-fill",
      style: {
        width: `${score / 5 * 100}%`,
        background: DMA.helpers.maturityHex(score)
      }
    })), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginTop: 8,
        fontSize: 11
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        color: "var(--z-muted)"
      }
    }, "Peer ", peer.toFixed(1)), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        color: score < peer ? "var(--z-below)" : "var(--z-mid)",
        fontFamily: "var(--font-mono)"
      }
    }, score >= peer ? "▲" : "▼", " ", Math.abs(score - peer).toFixed(1))), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)",
        marginTop: 10
      }
    }, DMA.CATEGORIES.filter(c => c.pillar === p.id).length, " categories \xB7 click to drill"));
  })));
}

/* ─────────────────────── CATEGORY HEATMAP ─────────────────────── */
function CategoryHeatmap({
  entity,
  pillarFocus,
  catAgg,
  showPeers,
  showIssues,
  setCatFocus,
  onSynth
}) {
  const pillars = pillarFocus ? DMA.PILLARS.filter(p => p.id === pillarFocus) : DMA.PILLARS;
  // Build category → has-caps map
  const catCaps = {};
  Object.values(DMA.ISSUE_CAPS).forEach(info => {
    Object.keys(info.caps).forEach(sid => {
      const catId = sid.slice(0, 4);
      catCaps[catId] = (catCaps[catId] || 0) + 1;
    });
  });
  return /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, pillars.map(p => {
    const cats = DMA.CATEGORIES.filter(c => c.pillar === p.id);
    const avg = cats.reduce((a, c) => a + catAgg[c.id].avg, 0) / Math.max(1, cats.length);
    return /*#__PURE__*/React.createElement("div", {
      key: p.id,
      style: {
        marginBottom: 16
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 10
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, p.id), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, p.name), /*#__PURE__*/React.createElement(MaturityChip, {
      score: avg
    }), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, cats.length, " categories \xB7 ", entity.subcaps.filter(s => s.pillar === p.id).length, " subcaps")), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: `120px repeat(${cats.length}, 1fr)`,
        gap: 4
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)",
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        paddingRight: 8
      }
    }, "Entity"), cats.map(c => {
      const agg = catAgg[c.id];
      const capCount = catCaps[c.id] || 0;
      return /*#__PURE__*/React.createElement("button", {
        key: c.id,
        className: `hm-cell b ${DMA.helpers.maturityClass(agg.avg)}`,
        onClick: () => setCatFocus(c.id),
        onContextMenu: e => {
          e.preventDefault();
          onSynth(c.id);
        },
        style: {
          position: "relative",
          border: 0,
          padding: "8px 6px",
          minHeight: 44
        },
        title: `${c.name} · ${capCount > 0 ? capCount + " subcaps capped by issues · " : ""}click to drill`
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          display: "flex",
          flexDirection: "column",
          lineHeight: 1.2,
          gap: 2
        }
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 13,
          fontWeight: 700
        }
      }, agg.avg.toFixed(1)), agg.thin > 0 ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 8,
          fontWeight: 600
        }
      }, agg.thin, " thin") : null), showIssues && capCount > 0 ? /*#__PURE__*/React.createElement("span", {
        style: {
          position: "absolute",
          top: 3,
          right: 4,
          display: "inline-flex",
          alignItems: "center",
          gap: 2,
          fontSize: 9,
          color: "var(--z-org)",
          background: "rgba(255,255,255,.85)",
          padding: "0 3px",
          borderRadius: 3
        }
      }, /*#__PURE__*/React.createElement(Icon, {
        name: "lock",
        size: 9
      }), capCount) : null);
    }), showPeers ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)",
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        paddingRight: 8
      }
    }, "Peer"), cats.map(c => /*#__PURE__*/React.createElement("div", {
      key: c.id,
      className: `hm-cell peer b ${DMA.helpers.maturityClass(catAgg[c.id].peer)}`,
      style: {
        minHeight: 30,
        padding: "4px 6px"
      }
    }, catAgg[c.id].peer.toFixed(1)))) : null, /*#__PURE__*/React.createElement("div", null), cats.map(c => /*#__PURE__*/React.createElement("div", {
      key: `l-${c.id}`,
      style: {
        fontSize: 9.5,
        color: "var(--z-muted)",
        textAlign: "center",
        padding: "4px 2px 0",
        lineHeight: 1.3
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "f-mono"
    }, c.id), /*#__PURE__*/React.createElement("div", {
      className: "txt-fit-2"
    }, c.name)))));
  }));
}

/* ─────────────────────── SUBCAP HEATMAP ─────────────────────── */
function SubcapHeatmap({
  entity,
  catFocus,
  pillarFocus,
  showPeers,
  showIssues,
  onSynth,
  setCatFocus
}) {
  const [openClusters, setOpenClusters] = useState({});
  const cats = catFocus ? DMA.CATEGORIES.filter(c => c.id === catFocus) : pillarFocus ? DMA.CATEGORIES.filter(c => c.pillar === pillarFocus) : null;

  // No category/pillar in focus → show a picker instead of dumping all 102 subcaps
  if (!cats || cats.length === 0) {
    const pillars = DMA.PILLARS;
    return /*#__PURE__*/React.createElement("div", {
      className: "card",
      style: {
        marginBottom: 14
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 4
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "grid",
      size: 14
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, "Select a category to view its sub-capabilities")), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-muted)",
        marginBottom: 14
      }
    }, "The subcap view drills into one category at a time so you can read the evidence behind each score. Pick a category below."), pillars.map(p => {
      const pcats = DMA.CATEGORIES.filter(c => c.pillar === p.id);
      return /*#__PURE__*/React.createElement("div", {
        key: p.id,
        style: {
          marginBottom: 12
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          marginBottom: 6,
          gap: 6
        }
      }, /*#__PURE__*/React.createElement("span", {
        className: "b b-purple"
      }, p.id), /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 11.5,
          fontWeight: 600,
          color: "var(--z-dark)"
        }
      }, p.short || p.name)), /*#__PURE__*/React.createElement("div", {
        className: "g4",
        style: {
          gap: 8
        }
      }, pcats.map(c => {
        const subs = entity.subcaps.filter(s => s.category === c.id);
        const avg = subs.length ? subs.reduce((a, s) => a + s.score, 0) / subs.length : 0;
        const thin = subs.filter(s => s.thin).length;
        return /*#__PURE__*/React.createElement("button", {
          key: c.id,
          className: "card-tile clickable",
          style: {
            padding: 11,
            textAlign: "left"
          },
          onClick: () => setCatFocus && setCatFocus(c.id),
          disabled: !subs.length
        }, /*#__PURE__*/React.createElement("div", {
          className: "row",
          style: {
            marginBottom: 6,
            gap: 5
          }
        }, /*#__PURE__*/React.createElement("span", {
          className: "chip"
        }, c.id), /*#__PURE__*/React.createElement("span", {
          className: "spacer"
        }), subs.length ? /*#__PURE__*/React.createElement("span", {
          className: `b ${DMA.helpers.maturityClass(avg)}`
        }, avg.toFixed(1)) : /*#__PURE__*/React.createElement("span", {
          className: "b b-muted"
        }, "\u2014")), /*#__PURE__*/React.createElement("div", {
          style: {
            fontSize: 12,
            fontWeight: 600,
            color: "var(--z-dark)"
          },
          className: "txt-fit-2"
        }, c.name), /*#__PURE__*/React.createElement("div", {
          style: {
            fontSize: 10.5,
            color: "var(--z-muted)",
            marginTop: 3
          }
        }, subs.length, " subcaps", thin ? ` · ${thin} thin` : ""));
      })));
    }));
  }
  return /*#__PURE__*/React.createElement("div", null, catFocus ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => setCatFocus && setCatFocus(null)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-l",
    size: 12
  }), " All categories"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Showing sub-capabilities for ", catFocus)) : null, cats.map(c => {
    const subs = entity.subcaps.filter(s => s.category === c.id);
    // group into L1 capability clusters (Category → L1 cluster → L2 sub-cap)
    const clusters = [];
    const byL1 = {};
    subs.forEach(s => {
      if (!byL1[s.l1]) {
        byL1[s.l1] = {
          l1: s.l1,
          name: s.l1name,
          items: []
        };
        clusters.push(byL1[s.l1]);
      }
      byL1[s.l1].items.push(s);
    });
    return /*#__PURE__*/React.createElement("div", {
      key: c.id,
      className: "card",
      style: {
        marginBottom: 14
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 12
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip"
    }, c.id), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, c.name), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, subs.length, " subcaps \xB7 ", clusters.length, " capabilities \xB7 weight ", (c.weight * 100).toFixed(0), "%")), clusters.map(cl => {
      const key = `${c.id}.${cl.l1}`;
      const open = openClusters[key] !== false; // default open
      const avg = cl.items.reduce((a, s) => a + s.score, 0) / cl.items.length;
      const capped = showIssues ? cl.items.filter(s => DMA.issueCapsFor(s.id).length).length : 0;
      return /*#__PURE__*/React.createElement("div", {
        key: key,
        style: {
          border: "1px solid var(--z-sep)",
          borderRadius: 8,
          marginBottom: 8,
          overflow: "hidden"
        }
      }, /*#__PURE__*/React.createElement("button", {
        onClick: () => setOpenClusters(o => ({
          ...o,
          [key]: !open
        })),
        style: {
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "9px 12px",
          background: "var(--z-bg)",
          border: 0,
          cursor: "pointer",
          textAlign: "left"
        }
      }, /*#__PURE__*/React.createElement("span", {
        className: `b ${DMA.helpers.maturityClass(avg)}`,
        style: {
          width: 34,
          justifyContent: "center",
          flexShrink: 0
        }
      }, avg.toFixed(1)), /*#__PURE__*/React.createElement("span", {
        style: {
          flex: 1,
          minWidth: 0,
          fontSize: 12.5,
          fontWeight: 600,
          color: "var(--z-dark)"
        },
        className: "txt-fit-1"
      }, cl.name), /*#__PURE__*/React.createElement("span", {
        className: "f-mono",
        style: {
          fontSize: 10,
          color: "var(--z-muted)"
        }
      }, c.id, ".", cl.l1), /*#__PURE__*/React.createElement("span", {
        className: "b b-muted"
      }, cl.items.length), capped ? /*#__PURE__*/React.createElement("span", {
        className: "b b-org"
      }, /*#__PURE__*/React.createElement(Icon, {
        name: "lock",
        size: 9
      }), " ", capped) : null, /*#__PURE__*/React.createElement(Icon, {
        name: open ? "chevron-u" : "chevron-d",
        size: 13,
        style: {
          color: "var(--z-muted)",
          flexShrink: 0
        }
      })), open ? /*#__PURE__*/React.createElement("div", {
        style: {
          display: "flex",
          flexDirection: "column",
          gap: 5,
          padding: "8px 10px"
        }
      }, cl.items.map(s => {
        const caps = showIssues ? DMA.issueCapsFor(s.id) : [];
        const gap = s.peerMedian - s.score;
        const evCount = DMA.EVIDENCE.filter(e => e.subcaps && e.subcaps.includes(s.id)).length;
        return /*#__PURE__*/React.createElement("button", {
          key: s.id,
          className: "subcap-row",
          onClick: () => onSynth(s)
        }, /*#__PURE__*/React.createElement("span", {
          className: `b ${DMA.helpers.maturityClass(s.score)}`,
          style: {
            width: 34,
            justifyContent: "center",
            flexShrink: 0
          }
        }, s.score.toFixed(1)), /*#__PURE__*/React.createElement("div", {
          style: {
            flex: 1,
            minWidth: 0
          }
        }, /*#__PURE__*/React.createElement("div", {
          className: "row",
          style: {
            gap: 6
          }
        }, /*#__PURE__*/React.createElement("span", {
          style: {
            fontSize: 12,
            fontWeight: 500,
            color: "var(--z-dark)"
          },
          className: "txt-fit-1"
        }, s.name), s.thin ? /*#__PURE__*/React.createElement("span", {
          className: "b b-org"
        }, "THIN") : null, caps.length ? /*#__PURE__*/React.createElement("span", {
          className: "b b-org"
        }, /*#__PURE__*/React.createElement(Icon, {
          name: "lock",
          size: 9
        }), " M", caps[0].cap) : null), /*#__PURE__*/React.createElement("div", {
          className: "f-mono",
          style: {
            fontSize: 10,
            color: "var(--z-muted)",
            marginTop: 1
          }
        }, s.id, " \xB7 ", s.confidence, " \xB7 ", evCount, " evidence")), /*#__PURE__*/React.createElement("div", {
          style: {
            width: 90,
            flexShrink: 0
          }
        }, /*#__PURE__*/React.createElement("div", {
          style: {
            position: "relative",
            height: 6,
            background: "var(--z-sep)",
            borderRadius: 3
          },
          title: `Score ${s.score.toFixed(1)} · Peer ${s.peerMedian.toFixed(1)}`
        }, /*#__PURE__*/React.createElement("div", {
          style: {
            width: `${s.score / 5 * 100}%`,
            height: "100%",
            background: DMA.helpers.maturityHex(s.score),
            borderRadius: 3
          }
        }), /*#__PURE__*/React.createElement("div", {
          style: {
            position: "absolute",
            left: `calc(${s.peerMedian / 5 * 100}% - 1px)`,
            top: -2,
            bottom: -2,
            width: 2,
            background: "var(--z-dpur)"
          }
        })), /*#__PURE__*/React.createElement("div", {
          style: {
            fontSize: 9,
            color: gap > 0 ? "var(--z-below)" : "var(--z-mid)",
            marginTop: 2,
            textAlign: "right"
          }
        }, gap > 0 ? `−${gap.toFixed(1)}` : `+${Math.abs(gap).toFixed(1)}`, " vs peer")), /*#__PURE__*/React.createElement("div", {
          style: {
            display: "flex",
            gap: 3,
            flexShrink: 0
          }
        }, s.platforms.slice(0, 2).map(p => /*#__PURE__*/React.createElement("span", {
          key: p,
          className: "b b-teal"
        }, DMA.getPlatform(p)?.short || p))), /*#__PURE__*/React.createElement(Icon, {
          name: "chevron-r",
          size: 13,
          style: {
            color: "var(--z-muted)",
            flexShrink: 0
          }
        }));
      })) : null);
    }));
  }));
}

/* ─────────────────────── VALUE CHAIN VIEW ─────────────────────── */
function ValueChainView({
  entity,
  subcapsForFocusArea,
  openSubcap,
  openInsight
}) {
  const [selected, setSelected] = useState(null);
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "route",
    size: 14
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "Value chain view"), /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Same ", entity.subcaps.length, " subcaps, reorganised by business process")), /*#__PURE__*/React.createElement("div", {
    className: "g3",
    style: {
      marginBottom: 14
    }
  }, DMA.VALUE_CHAINS.map(vc => {
    // Pick subcaps representative of value chain - sample from subcaps
    const idx = Math.abs(hashCode(vc.id)) % entity.subcaps.length;
    const subs = entity.subcaps.slice(idx, idx + 8);
    const avg = subs.reduce((a, s) => a + s.score, 0) / Math.max(1, subs.length);
    const peer = subs.reduce((a, s) => a + s.peerMedian, 0) / Math.max(1, subs.length);
    return /*#__PURE__*/React.createElement("div", {
      key: vc.id,
      className: "card-tile clickable",
      style: {
        padding: 14,
        border: selected === vc.id ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)",
        background: selected === vc.id ? "var(--z-ice)" : "#fff"
      },
      onClick: () => setSelected(vc.id === selected ? null : vc.id)
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip"
    }, vc.id), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, vc.name)), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement(MaturityChip, {
      score: avg
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, "Peer ", peer.toFixed(1)), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, subs.length, " subcaps")), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: `repeat(${subs.length}, 1fr)`,
        gap: 2
      }
    }, subs.map(s => /*#__PURE__*/React.createElement("div", {
      key: s.id,
      className: `hm-cell b ${DMA.helpers.maturityClass(s.score)}`,
      style: {
        height: 18,
        fontSize: 9,
        padding: 0,
        border: 0
      }
    }, s.score.toFixed(1)))));
  })), selected ? (() => {
    const vc = DMA.VALUE_CHAINS.find(x => x.id === selected);
    const idx = Math.abs(hashCode(vc.id)) % entity.subcaps.length;
    const subs = entity.subcaps.slice(idx, idx + 8);
    const insights = DMA.INSIGHT_CARDS.filter(ic => ic.affects.some(sid => subs.some(s => s.id === sid)));
    return /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "1.4fr 1fr",
        gap: 14
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "card"
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
        fontSize: 13,
        fontWeight: 600
      }
    }, vc.name, " \xB7 subcaps"), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, subs.length, " cells \xB7 click to drill")), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 6
      }
    }, subs.map(s => /*#__PURE__*/React.createElement("button", {
      key: s.id,
      className: "card-tile clickable",
      style: {
        padding: 10
      },
      onClick: () => openSubcap({
        kind: "subcap",
        subcap: s
      })
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 4
      }
    }, /*#__PURE__*/React.createElement(MaturityChip, {
      score: s.score
    }), /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, s.id), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), s.thin ? /*#__PURE__*/React.createElement("span", {
      className: "b b-org"
    }, "THIN") : null), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-dark)"
      },
      className: "txt-fit-2"
    }, s.name))))), /*#__PURE__*/React.createElement("div", {
      className: "card flush"
    }, /*#__PURE__*/React.createElement("div", {
      className: "card-head"
    }, /*#__PURE__*/React.createElement("h3", null, "Insight cards in this chain"), /*#__PURE__*/React.createElement("span", {
      className: "b b-muted"
    }, insights.length)), /*#__PURE__*/React.createElement("div", {
      style: {
        padding: 12
      }
    }, insights.length === 0 ? /*#__PURE__*/React.createElement("div", {
      className: "muted",
      style: {
        fontSize: 12
      }
    }, "No insight cards mapped") : insights.map(ic => /*#__PURE__*/React.createElement("button", {
      key: ic.id,
      className: "card-tile clickable",
      style: {
        marginBottom: 8,
        padding: 12,
        width: "100%",
        textAlign: "left"
      },
      onClick: () => openInsight(ic.id)
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 4
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "ic-id"
    }, ic.id), /*#__PURE__*/React.createElement("span", {
      className: `b ${ic.flag === "CRITICAL" ? "b-below" : ic.flag === "OPPORTUNITY" ? "b-org" : "b-teal"}`
    }, ic.flag)), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600
      },
      className: "txt-fit-1"
    }, ic.title))))));
  })() : null);
}

/* ─────────────────────── SYNTHESIS DRAWER ─────────────────────── */
function SynthesisDrawer({
  entity,
  item,
  onClose,
  openEvidence,
  openInsight,
  showIssues
}) {
  const subcap = item.subcap;
  const category = item.catId ? DMA.getCategory(item.catId) : null;
  if (!subcap && !category) return null;

  // Linked insight cards
  const linkedIC = subcap ? DMA.INSIGHT_CARDS.filter(ic => ic.affects.includes(subcap.id)) : DMA.INSIGHT_CARDS.filter(ic => ic.affects.some(sid => sid.startsWith(category.id)));

  // Linked evidence (look for evidence that lists this subcap)
  const linkedEv = subcap ? DMA.EVIDENCE.filter(e => e.subcaps && e.subcaps.includes(subcap.id)) : DMA.EVIDENCE.filter(e => e.subcaps && e.subcaps.some(sid => sid.startsWith(category.id)));

  // Issue caps (subcap only)
  const caps = subcap ? DMA.issueCapsFor(subcap.id) : [];

  // Peer comparison (for category we use category aggregate)
  const score = subcap ? subcap.score : entity.subcaps.filter(s => s.category === category.id).reduce((a, s, _, arr) => a + s.score / arr.length, 0);
  const peer = subcap ? subcap.peerMedian : score + 0.3;
  const gap = peer - score;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "drawer-mask",
    onClick: onClose
  }), /*#__PURE__*/React.createElement("div", {
    className: "drawer",
    style: {
      width: 480
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "drawer-head"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0,
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-teal"
  }, "SYNTHESIS"), subcap ? /*#__PURE__*/React.createElement("span", {
    className: "chip purple"
  }, subcap.id) : /*#__PURE__*/React.createElement("span", {
    className: "chip"
  }, category.id), subcap?.thin ? /*#__PURE__*/React.createElement("span", {
    className: "b b-org"
  }, "THIN") : null), /*#__PURE__*/React.createElement("div", {
    className: "title",
    style: {
      fontSize: 15
    }
  }, subcap?.name || category?.name), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, subcap ? `Score ${subcap.score.toFixed(1)} · ${subcap.confidence}` : `${entity.subcaps.filter(s => s.category === category.id).length} subcaps · weight ${(category.weight * 100).toFixed(0)}%`)), /*#__PURE__*/React.createElement("button", {
    className: "icon-btn",
    onClick: onClose
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "x",
    size: 16
  }))), /*#__PURE__*/React.createElement("div", {
    className: "drawer-body"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-tile",
    style: {
      marginBottom: 14,
      background: "var(--z-lav)",
      border: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "scale",
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      fontWeight: 600
    }
  }, "Peer comparison")), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      height: 36,
      background: "#fff",
      borderRadius: 6,
      overflow: "hidden",
      marginBottom: 8
    }
  }, [1, 2, 3, 4, 5].map(t => /*#__PURE__*/React.createElement("div", {
    key: t,
    style: {
      position: "absolute",
      left: `${(t - 1) / 4 * 100}%`,
      top: 0,
      bottom: 0,
      width: 1,
      background: "var(--z-sep)"
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      left: `calc(${(score - 1) / 4 * 100}% - 6px)`,
      top: 4,
      width: 12,
      height: 28,
      background: DMA.helpers.maturityHex(score),
      borderRadius: 3,
      boxShadow: "0 1px 3px rgba(0,0,0,.2)"
    },
    title: "Entity"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      left: `calc(${(peer - 1) / 4 * 100}% - 1px)`,
      top: 0,
      bottom: 0,
      width: 2,
      background: "var(--z-dpur)"
    },
    title: "Peer median"
  })), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, /*#__PURE__*/React.createElement("span", null, "M1"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", null, "M2"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", null, "M3"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", null, "M4"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", null, "M5")), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 10,
      fontSize: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "row",
    style: {
      gap: 5
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 10,
      height: 10,
      borderRadius: 3,
      background: DMA.helpers.maturityHex(score)
    }
  }), " Entity ", /*#__PURE__*/React.createElement("strong", null, score.toFixed(1))), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    className: "row",
    style: {
      gap: 5
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 2,
      height: 12,
      background: "var(--z-dpur)"
    }
  }), " Peer ", /*#__PURE__*/React.createElement("strong", null, peer.toFixed(1))), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: gap > 0 ? "var(--z-below)" : "var(--z-mid)"
    }
  }, gap > 0 ? `−${gap.toFixed(1)}` : `+${Math.abs(gap).toFixed(1)}`))), caps.length > 0 ? /*#__PURE__*/React.createElement("div", {
    className: "co co-org",
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "lock",
    size: 14
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "co-title"
  }, "Capped by ", caps.length, " issue", caps.length === 1 ? "" : "s"), caps.map(c => /*#__PURE__*/React.createElement("div", {
    key: c.id,
    style: {
      fontSize: 12,
      marginTop: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "chip",
    style: {
      marginRight: 6
    }
  }, c.id), c.issue?.desc.slice(0, 70), "\u2026 ", /*#__PURE__*/React.createElement("strong", null, "Cap M", c.cap))))) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 8,
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "evidence",
    size: 13,
    style: {
      color: "var(--z-mid)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: ".08em",
      color: "var(--z-dark)",
      textTransform: "uppercase"
    }
  }, "Source reports & evidence"), /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, linkedEv.length), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, "click an ID to open")), linkedEv.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "co co-org",
    style: {
      marginBottom: 0
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "warn",
    size: 13
  }), /*#__PURE__*/React.createElement("div", {
    className: "co-body"
  }, "No evidence item directly cites this ", subcap ? "subcap" : "category", " in this run \u2014 the score is inferred. Treat as provisional until corroborated.")) : linkedEv.map(e => {
    const tier = DMA.getTier(e.tier);
    return /*#__PURE__*/React.createElement("button", {
      key: e.id,
      className: "card-tile clickable",
      style: {
        width: "100%",
        padding: 11,
        marginBottom: 6,
        textAlign: "left"
      },
      onClick: () => openEvidence(e.id)
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 4,
        gap: 6
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: `tier-chip tier-${e.tier}`
    }, e.id), /*#__PURE__*/React.createElement("span", {
      className: "b b-muted",
      title: tier?.label
    }, e.tier, " \xB7 ", e.claim), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, e.recency)), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        fontWeight: 600,
        color: "var(--z-dark)"
      },
      className: "txt-fit-1"
    }, e.title), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 5,
        marginTop: 3
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "drive",
      size: 10,
      style: {
        color: "var(--z-muted)"
      }
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10.5,
        color: "var(--z-mid)",
        fontWeight: 500
      },
      className: "txt-fit-1"
    }, e.source_pretty)), e.excerpt ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-body)",
        lineHeight: 1.5,
        marginTop: 6,
        paddingLeft: 8,
        borderLeft: "2px solid var(--z-sep)",
        fontStyle: "italic"
      }
    }, "\u201C", e.excerpt, "\u201D") : null);
  })), linkedIC.length > 0 ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: ".1em",
      color: "var(--z-muted)",
      textTransform: "uppercase",
      marginBottom: 8
    }
  }, "Linked insight cards \xB7 ", linkedIC.length), linkedIC.map(ic => /*#__PURE__*/React.createElement("button", {
    key: ic.id,
    className: "card-tile clickable",
    style: {
      width: "100%",
      padding: 11,
      marginBottom: 6,
      textAlign: "left"
    },
    onClick: () => openInsight(ic.id)
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "ic-id"
  }, ic.id), /*#__PURE__*/React.createElement("span", {
    className: `b ${ic.flag === "CRITICAL" ? "b-below" : ic.flag === "OPPORTUNITY" ? "b-org" : "b-teal"}`
  }, ic.flag)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      fontWeight: 600
    },
    className: "txt-fit-1"
  }, ic.title)))) : null, subcap ? /*#__PURE__*/React.createElement("div", {
    className: "card-tile",
    style: {
      marginBottom: 4,
      background: "var(--ph0-lt)",
      border: "1px solid var(--ph0-bd)",
      padding: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 6,
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "sparkle",
    size: 13,
    style: {
      color: "var(--z-dpur)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      fontWeight: 700,
      color: "var(--z-dpur)",
      letterSpacing: ".08em",
      textTransform: "uppercase"
    }
  }, "AI synthesis"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9.5,
      color: "var(--z-dpur)",
      opacity: .85
    }
  }, "on the ", linkedEv.length, " item", linkedEv.length === 1 ? "" : "s", " above")), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      color: "#3B0764",
      lineHeight: 1.6
    }
  }, subcap.thin ? `This subcap has thin evidence (${subcap.evidence_count} / 3) - confidence is LOW. The score is provisional.` : gap > 0.5 ? `Trails peer by ${gap.toFixed(1)} - addressable via the linked recommendation. Closing this lifts the parent category by ${(gap * 0.18).toFixed(2)} points.` : `At or above peer median. No platform investment needed for this subcap specifically; protect against regression.`)) : null), /*#__PURE__*/React.createElement("div", {
    className: "drawer-foot"
  }, subcap ? /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => {
      const label = subcap?.name || category?.name || "selection";
      const text = `${label}\nScore ${subcap?.score?.toFixed(1) ?? "-"} · confidence ${subcap?.confidence ?? "-"} · peer median ${subcap?.peerMedian?.toFixed(1) ?? "-"}.`;
      try {
        navigator.clipboard.writeText(text);
      } catch (e) {}
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "copy",
    size: 13
  }), " Copy synthesis") : /*#__PURE__*/React.createElement("span", null), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: onClose
  }, "Close"))));
}
function IssueRegisterBanner({
  entity,
  onSubcap,
  openEvidence
}) {
  const openIssues = DMA.ISSUES.filter(i => i.status === "OPEN");
  const [open, setOpen] = useState(null);
  if (openIssues.length === 0) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 12,
      padding: 14,
      background: "rgba(254,151,50,.06)",
      border: "1px solid rgba(254,151,50,.28)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "warn",
    size: 14,
    style: {
      color: "var(--z-org)"
    }
  }), /*#__PURE__*/React.createElement("strong", {
    style: {
      fontSize: 13,
      color: "var(--z-dark)"
    }
  }, "Issue register \xB7 ", openIssues.length, " open"), /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, "click an issue to drill in"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("a", {
    href: `#/clients/${entity.id}/context`,
    style: {
      fontSize: 11,
      color: "var(--z-mid)",
      fontWeight: 600
    }
  }, "Full register \u2192")), /*#__PURE__*/React.createElement("div", {
    className: "g2",
    style: {
      gap: 8
    }
  }, openIssues.map(iss => {
    const caps = Object.entries(DMA.ISSUE_CAPS[iss.id]?.caps || {});
    const isOpen = open === iss.id;
    const ev = DMA.EVIDENCE.filter(e => e.subcaps && e.subcaps.some(sid => caps.some(([cid]) => sid.slice(0, 4) === cid.slice(0, 4))));
    return /*#__PURE__*/React.createElement("div", {
      key: iss.id,
      className: "card-tile",
      style: {
        padding: 0,
        background: "#fff",
        gridColumn: isOpen ? "1 / -1" : "auto",
        overflow: "hidden"
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setOpen(o => o === iss.id ? null : iss.id),
      style: {
        width: "100%",
        background: "none",
        border: 0,
        cursor: "pointer",
        textAlign: "left",
        padding: 10
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 6,
        gap: 6
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip"
    }, iss.id), /*#__PURE__*/React.createElement("span", {
      className: "b b-muted"
    }, iss.type), /*#__PURE__*/React.createElement("span", {
      className: `b ${iss.severity === "CRITICAL" ? "b-below" : iss.severity === "MATERIAL" ? "b-org" : "b-muted"}`
    }, iss.severity), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement(Icon, {
      name: "lock",
      size: 11,
      style: {
        color: "var(--z-org)"
      }
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, "caps ", caps.length), /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-u" : "chevron-d",
      size: 13,
      style: {
        color: "var(--z-muted)"
      }
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-dark)",
        lineHeight: 1.5
      },
      className: isOpen ? "" : "txt-fit-2"
    }, iss.desc)), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        padding: "0 10px 10px"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 12,
        fontSize: 11,
        color: "var(--z-muted)",
        marginBottom: 8,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement("span", null, "Status ", /*#__PURE__*/React.createElement("strong", {
      style: {
        color: "var(--z-org)"
      }
    }, iss.status)), /*#__PURE__*/React.createElement("span", null, "Cap ", /*#__PURE__*/React.createElement("strong", {
      style: {
        color: "var(--z-dark)"
      }
    }, "M", iss.cap_value)), /*#__PURE__*/React.createElement("span", null, "Since ", /*#__PURE__*/React.createElement("strong", {
      style: {
        color: "var(--z-dark)"
      }
    }, iss.start)), iss.end ? /*#__PURE__*/React.createElement("span", null, "Resolved ", iss.end) : null), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        marginBottom: 4
      }
    }, "Capped subcaps \xB7 click to drill"), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        flexWrap: "wrap",
        gap: 4,
        marginBottom: ev.length ? 10 : 0
      }
    }, caps.map(([sid, cap]) => {
      const subcap = entity.subcaps.find(s => s.id === sid);
      return /*#__PURE__*/React.createElement("button", {
        key: sid,
        className: "chip purple",
        onClick: () => subcap && onSubcap(subcap),
        title: (subcap?.name || sid) + " · capped at M" + cap
      }, sid, " \xB7 M", cap, subcap ? ` · ${subcap.name}` : "");
    })), ev.length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        marginBottom: 4
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
      onClick: () => openEvidence && openEvidence(e.id)
    }, e.id)))) : null) : null);
  })));
}
function Legend() {
  return /*#__PURE__*/React.createElement("div", {
    className: "row-wrap",
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      gap: 8
    }
  }, [["b-act", "M1"], ["b-bld", "M2"], ["b-cmp", "M3"], ["b-dif", "M4+"]].map(([c, l]) => /*#__PURE__*/React.createElement("span", {
    key: c,
    className: "row",
    style: {
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `b ${c}`,
    style: {
      width: 12,
      height: 12,
      padding: 0,
      borderRadius: 3
    }
  }), l)), /*#__PURE__*/React.createElement("span", {
    className: "row",
    style: {
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 12,
      height: 12,
      border: "2px dashed var(--z-org)",
      borderRadius: 3
    }
  }), " Thin"), /*#__PURE__*/React.createElement("span", {
    className: "row",
    style: {
      gap: 4
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "lock",
    size: 10
  }), " Capped"));
}
function hashCode(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h << 5) - h + s.charCodeAt(i);
  return h;
}
window.hashCode = hashCode;
Object.assign(window, {
  ClientHeatmap
});