/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · New data-driven cards (real DMA deliverable shapes)
   ───────────────────────────────────────────────────────────────────────
   Every card below renders from a DMA.* accessor and is tagged with a
   data-source="<canonical file> :: <field>" attribute on its root element
   AND a // SOURCE: comment, so the extraction-script bindings are
   discoverable directly from the code. Full map: SOURCES.md.

   Cards: EvidenceTierCard · SentimentCard · FinancialTrajectoryCard
          CoverageByPillarCard · CeilingEstimateCard
   All INTERNAL-only cards respect the audience toggle (hidden for customer).
   ═══════════════════════════════════════════════════════════════════════ */

/* ── Evidence tier distribution (T1–T5) ────────────────────────────────
   SOURCE: 01_evidence/research_handoff.json :: evidence_summary.tier_distribution */
function EvidenceTierCard({
  entity
}) {
  const s = DMA.evidenceSummaryFor(entity.id);
  const tiers = Object.entries(s.tiers);
  const max = Math.max(...tiers.map(([, v]) => v), 1);
  return /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    "data-source": "research_handoff.json :: evidence_summary.tier_distribution"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "evidence",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Evidence tier distribution")), /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, s.total_items, " items \xB7 ", s.total_facts, " facts")), /*#__PURE__*/React.createElement("div", {
    className: "card-body"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-end",
      gap: 10,
      height: 120,
      padding: "4px 0 0"
    }
  }, tiers.map(([t, v]) => {
    const tier = DMA.getTier(t) || {};
    return /*#__PURE__*/React.createElement("div", {
      key: t,
      style: {
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 6
      },
      title: tier.label || t
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        fontWeight: 600,
        color: "var(--z-dark)",
        fontVariantNumeric: "tabular-nums"
      }
    }, v), /*#__PURE__*/React.createElement("div", {
      style: {
        width: "100%",
        height: `${v / max * 84}px`,
        minHeight: 3,
        background: tier.color || "var(--z-mid)",
        borderRadius: "4px 4px 0 0",
        transition: "height var(--motion-slow) var(--ease)"
      }
    }), /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, t));
  })), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 12,
      gap: 6,
      flexWrap: "wrap"
    }
  }, Object.entries(s.claims).filter(([, v]) => v > 0).map(([k, v]) => /*#__PURE__*/React.createElement("span", {
    key: k,
    className: "chip",
    title: "claim_distribution"
  }, k.replace("_", " ").toLowerCase(), " \xB7 ", v)))));
}

/* ── Multi-source sentiment scorecard ──────────────────────────────────
   SOURCE: 08_appendices/A6_sentiment_data.csv  (INTERNAL-only) */
function SentimentCard({
  entity,
  audience
}) {
  if (audience === "customer") return null; // internal-only strip
  const s = DMA.sentimentFor(entity.id);
  const Row = ({
    r
  }) => {
    const pct = r.score / (r.scale || 5) * 100;
    const tone = r.score >= 4 ? "var(--z-teal)" : r.score >= 3 ? "var(--z-org)" : "var(--z-below)";
    return /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "120px 1fr 40px",
        gap: 8,
        alignItems: "center",
        padding: "5px 0"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-body)"
      }
    }, r.source, /*#__PURE__*/React.createElement("span", {
      style: {
        color: "var(--z-muted)"
      }
    }, " \xB7 ", r.metric)), /*#__PURE__*/React.createElement("div", {
      style: {
        height: 7,
        background: "var(--z-sep)",
        borderRadius: 4,
        overflow: "hidden"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        width: `${pct}%`,
        height: "100%",
        background: tone,
        borderRadius: 4,
        transition: "width var(--motion-slow) var(--ease)"
      }
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        fontWeight: 600,
        color: tone,
        textAlign: "right",
        fontVariantNumeric: "tabular-nums"
      }
    }, r.score.toFixed(1)));
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    "data-source": "A6_sentiment_data.csv :: employee[],customer[]"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "users",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Sentiment"), s.b2b_b2c_gap ? /*#__PURE__*/React.createElement("span", {
    className: "b b-org"
  }, "B2B/B2C gap") : null), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Industry avg ", s.industry_avg.toFixed(1))), /*#__PURE__*/React.createElement("div", {
    className: "card-body"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".06em",
      marginBottom: 2
    }
  }, "Employee"), s.employee.map((r, i) => /*#__PURE__*/React.createElement(Row, {
    key: "e" + i,
    r: r
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".06em",
      margin: "10px 0 2px"
    }
  }, "Customer"), s.customer.map((r, i) => /*#__PURE__*/React.createElement(Row, {
    key: "c" + i,
    r: r
  }))));
}

/* ── Financial trajectory ──────────────────────────────────────────────
   SOURCE: 00_entity_profile/financial_baseline.json + entity_profile.json */
function FinancialTrajectoryCard({
  entity
}) {
  const f = DMA.financialsFor(entity.id);
  const maxA = Math.max(...f.total_assets);
  return /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    "data-source": "financial_baseline.json :: total_assets[],net_income_m[],nim_pct[]"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "money",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Financial trajectory")), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, f.headline)), /*#__PURE__*/React.createElement("div", {
    className: "card-body"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-end",
      gap: 10,
      height: 120
    }
  }, f.fy.map((y, i) => /*#__PURE__*/React.createElement("div", {
    key: y,
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      gap: 5
    },
    title: `${y} · $${f.total_assets[i]}${f.unit} · NIM ${f.nim_pct[i]}%`
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      fontWeight: 600,
      color: "var(--z-dark)"
    }
  }, "$", f.total_assets[i], f.unit), /*#__PURE__*/React.createElement("div", {
    style: {
      width: "100%",
      height: `${f.total_assets[i] / maxA * 80}px`,
      background: "linear-gradient(180deg, var(--z-teal), var(--z-mid))",
      borderRadius: "4px 4px 0 0",
      transition: "height var(--motion-slow) var(--ease)"
    }
  }), /*#__PURE__*/React.createElement("div", {
    className: "f-mono",
    style: {
      fontSize: 9.5,
      color: "var(--z-muted)"
    }
  }, y.replace("FY", "'"))))), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 10,
      gap: 6,
      flexWrap: "wrap",
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "chip"
  }, f.regulator), /*#__PURE__*/React.createElement("span", null, f.geography), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", null, f.branches, " branches \xB7 ", f.employees[f.employees.length - 1].toLocaleString(), " FTE"))));
}

/* ── Coverage by pillar ─────────────────────────────────────────────────
   SOURCE: 03_scoring_workbook/export_coverage_stats.csv */
function CoverageByPillarCard({
  entity
}) {
  const c = DMA.coverageFor(entity.id);
  return /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    "data-source": "export_coverage_stats.csv :: by_pillar[].pct"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Evidence coverage")), /*#__PURE__*/React.createElement("span", {
    className: "b b-above"
  }, c.overall_pct, "% overall")), /*#__PURE__*/React.createElement("div", {
    className: "card-body"
  }, c.by_pillar.map(p => {
    const pill = DMA.PILLARS.find(x => x.id === p.pillar);
    const pass = p.pct >= c.gate_pct;
    return /*#__PURE__*/React.createElement("div", {
      key: p.pillar,
      style: {
        display: "grid",
        gridTemplateColumns: "90px 1fr 38px",
        gap: 8,
        alignItems: "center",
        padding: "5px 0"
      },
      title: `${p.scored}/${p.subcaps} subcaps`
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-body)"
      }
    }, pill ? pill.short : p.pillar), /*#__PURE__*/React.createElement("div", {
      style: {
        height: 7,
        background: "var(--z-sep)",
        borderRadius: 4,
        overflow: "hidden",
        position: "relative"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        position: "absolute",
        left: `${c.gate_pct}%`,
        top: -2,
        bottom: -2,
        width: 1,
        background: "var(--z-org)"
      }
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        width: `${p.pct}%`,
        height: "100%",
        background: pass ? "var(--z-teal)" : "var(--z-org)",
        borderRadius: 4,
        transition: "width var(--motion-slow) var(--ease)"
      }
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        fontWeight: 600,
        color: pass ? "var(--z-teal)" : "var(--z-org)",
        textAlign: "right",
        fontVariantNumeric: "tabular-nums"
      }
    }, p.pct, "%"));
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      marginTop: 6
    }
  }, "Orange line = ", c.gate_pct, "% hard gate")));
}

/* ── Capability ceiling + uncertainty bands ────────────────────────────
   SOURCE: 02_research_workbook/uncertainty_bands.json :: {base,modifiers,total} */
function CeilingEstimateCard({
  entity,
  audience
}) {
  if (audience === "customer") return null; // ceilings are internal estimates
  const {
    openEvidence
  } = useApp();
  const [open, setOpen] = useState(null);
  const u = DMA.uncertaintyFor(entity.id);
  const rows = Object.entries(u);
  return /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    "data-source": "uncertainty_bands.json :: total,modifiers,evidence ; peer_comparison_table.csv :: *_Ceiling"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "stack",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Capability ceiling & uncertainty")), /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, rows.length, " categories \xB7 click to drill")), /*#__PURE__*/React.createElement("div", {
    className: "card-body",
    style: {
      maxHeight: 340,
      overflowY: "auto"
    }
  }, rows.map(([cat, d]) => {
    const cdef = DMA.getCategory(cat);
    const lo = Math.max(1, d.ceiling - d.band),
      hi = Math.min(5, d.ceiling + d.band);
    const pct = v => (v - 1) / 4 * 100;
    const tone = d.ceiling <= 2 ? "var(--z-below)" : d.ceiling < 3 ? "var(--z-org)" : "var(--z-teal)";
    const isOpen = open === cat;
    const ev = (d.evidence || []).map(id => DMA.getEvidence(id)).filter(Boolean);
    return /*#__PURE__*/React.createElement("div", {
      key: cat,
      style: {
        borderBottom: "1px solid var(--z-sep)"
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setOpen(o => o === cat ? null : cat),
      style: {
        width: "100%",
        display: "grid",
        gridTemplateColumns: "128px 1fr 62px 16px",
        gap: 8,
        alignItems: "center",
        padding: "8px 0",
        background: "none",
        border: 0,
        cursor: "pointer",
        textAlign: "left"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-body)"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "f-mono"
    }, cat), " ", cdef ? cdef.name.slice(0, 14) : ""), /*#__PURE__*/React.createElement("div", {
      style: {
        position: "relative",
        height: 8,
        background: "var(--z-sep)",
        borderRadius: 4
      },
      title: `Band ${lo.toFixed(1)}–${hi.toFixed(1)}`
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        position: "absolute",
        left: `${pct(lo)}%`,
        width: `${pct(hi) - pct(lo)}%`,
        top: 0,
        bottom: 0,
        background: "rgba(124,93,201,.25)",
        borderRadius: 4
      }
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        position: "absolute",
        left: `calc(${pct(d.ceiling)}% - 4px)`,
        top: -1,
        width: 8,
        height: 10,
        borderRadius: 2,
        background: tone
      }
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        fontWeight: 600,
        color: tone,
        textAlign: "right",
        fontVariantNumeric: "tabular-nums"
      }
    }, d.ceiling.toFixed(1), /*#__PURE__*/React.createElement("span", {
      style: {
        color: "var(--z-muted)",
        fontWeight: 400
      }
    }, " \xB1", d.band)), /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-u" : "chevron-d",
      size: 12,
      style: {
        color: "var(--z-muted)"
      }
    })), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        padding: "2px 0 12px",
        paddingLeft: 4
      }
    }, d.rationale ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        lineHeight: 1.55,
        marginBottom: 8
      }
    }, d.rationale) : null, d.modifiers && d.modifiers.length ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        marginBottom: 3
      }
    }, "Ceiling modifiers"), d.modifiers.map((m, i) => /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        fontSize: 11,
        color: "var(--z-org)",
        fontFamily: "var(--font-mono)"
      }
    }, m))) : null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        marginBottom: 4
      }
    }, "Evidence \xB7 click to open"), ev.length ? /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        flexDirection: "column",
        gap: 4
      }
    }, ev.map(e => /*#__PURE__*/React.createElement("button", {
      key: e.id,
      onClick: () => openEvidence(e.id),
      style: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "7px 9px",
        background: "var(--z-bg)",
        border: "1px solid var(--z-sep)",
        borderRadius: 6,
        cursor: "pointer",
        textAlign: "left",
        transition: "border-color 120ms"
      },
      onMouseEnter: ev2 => ev2.currentTarget.style.borderColor = "var(--z-teal)",
      onMouseLeave: ev2 => ev2.currentTarget.style.borderColor = "var(--z-sep)"
    }, /*#__PURE__*/React.createElement("span", {
      className: `tier-chip tier-${e.tier}`
    }, e.id), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-dark)",
        fontWeight: 500,
        flex: 1,
        minWidth: 0
      },
      className: "txt-fit-1"
    }, e.source_pretty), /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-r",
      size: 11,
      style: {
        color: "var(--z-mid)"
      }
    })))) : /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, "No evidence linked \u2014 inferred ceiling.")) : null);
  })));
}

/* Share with other Babel scripts (see CLAUDE.md note on cross-file scope) */
Object.assign(window, {
  EvidenceTierCard,
  SentimentCard,
  FinancialTrajectoryCard,
  CoverageByPillarCard,
  CeilingEstimateCard
});