/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Live client pages (production only)

   Production divergence, and the most important one in this app: a
   client-scoped page in production renders PROMOTED sections or an honest
   empty state — never the prototype's example content. The prototype's
   pages carry illustrative prose about a fictional bank (three cores, an
   nCino migration, named executive hires); rendered under a real client's
   name that is fabrication, so in LIVE mode those components are not
   reached at all.

   What this module IS, then, is the prototype's layout — the same card
   anatomy, the same grids, the same primitives (ScoreRing, MaturityChip,
   pbar, hm-cell, Row, cards-grid-N) — reading the promoted payload
   instead of the fixture. Every surface here is designed; a section that
   did not promote says so in place, and no raw payload is ever the
   client-facing rendering of a surface.

   Charter constraints this file must honour:
   · no colour comes from the payload — score → band → hex happens here,
     in the ONE resolver (DMA.helpers.maturityHex/maturityClass);
   · nothing is recomputed that the producer already computed (deltas,
     shares, ages, counts all render as promoted);
   · a null derived value renders as an EnrichmentGap naming the field,
     never as 0 and never as a sentinel that looks like data. Not an em
     dash either: an em dash cannot say whether the field was searched,
     held or never asked for, and gives the reader no route to filling it.
   ═══════════════════════════════════════════════════════════════════════ */

const LIVE_PAGE_SECTIONS = {
  overview: ["scores", "firmographics", "why_now", "exec_summary", "opportunity", "findings", "leadership", "financial_series", "sentiment", "ceilings", "evidence_coverage", "thought_leadership"],
  insights: ["insights", "landscape"],
  heatmap: ["workbook_scores", "focus_areas", "cell_evidence", "evidence", "value_chain", "alerts", "safeguard_gates", "evidence_age", "cohort_patterns"],
  platform: ["platform_story", "recommendations", "starters", "roadmap", "stairstep"],
  context: ["timeline", "issue_register", "regulatory_standing", "context_sentiment", "acquisitions"],
  techstack: ["techstack"]
};

/* Sections whose contract names no payload field yet: promote writes an
   envelope, so `data` is legitimately empty. The reason is structural, not a
   production failure, and it must not read as a broken card. */
const ENVELOPE_ONLY = {
  landscape: "the D4 landscape recomputes from the technology register (T1); its own payload contract is unauthored, so this run promoted an envelope only",
  context_sentiment: "the D5 sentiment contract names no payload field yet - the promoted sentiment for this run is on the overview page",
  value_chain: "the H9 value-chain arrangement is server-derived and pinned at stage 6.3; no contract field exists to promote yet"
};

/* A section with no meaningful content: every key is null, or the only keys
   left are the two that every section carries. */
function isBlank(data) {
  if (!data || typeof data !== "object") return true;
  return !Object.keys(data).some(k => {
    if (k === "r_layer" || k === "narrative_thread") return false;
    const v = data[k];
    if (v === null || v === undefined || v === "") return false;
    if (Array.isArray(v)) return v.length > 0;
    if (typeof v === "object") return Object.keys(v).length > 0;
    return true;
  });
}
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

/* ══ formatting ═════════════════════════════════════════════════════
   Numbers reach the payload as strings, because the producer must not
   round or localise anything. Presentation happens here, once. */

const NBSP = " ";

/* Renderable text from a payload value. A contract can hand back a shape a
   card did not anticipate; React throws on an object child and one throw used
   to blank the whole page, so nothing reaches JSX without passing through
   here. Objects are summarised from their own naming keys — a client surface
   never shows raw JSON. */
function asText(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "string") return v || null;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(asText).filter(Boolean).join(" · ") || null;
  if (typeof v === "object") {
    for (const k of ["statement", "text", "label", "name", "title", "clause", "value"]) {
      const t = asText(v[k]);
      if (t) return t;
    }
    return null;
  }
  return String(v);
}
function fmtNum(v, opts) {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(String(v).replace(/,/g, ""));
  if (!isFinite(n)) return String(v);
  const decimals = opts && opts.decimals !== undefined ? opts.decimals : String(v).includes(".") ? (String(v).split(".")[1] || "").length : 0;
  return n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
}
function fmtMoney(n, unit) {
  const u = String(unit || "").toLowerCase();
  const num = Number(n);
  if (!isFinite(num)) return null;
  if (u.includes("trillion")) return `$${fmtNum(n)}T`;
  if (u.includes("billion")) return `$${fmtNum(n)}B`;
  if (u.includes("million")) return `$${fmtNum(n)}M`;
  if (u.includes("thousand")) return `$${fmtNum(n)}K`;
  return `$${fmtNum(n)}`;
}

/* A firmographic field is {field, value, unit, …}. The unit decides the
   presentation: money scales to a suffix, a percent takes a sign, a bare
   count keeps its noun, and a year is never given a thousands separator. */
function fmtFirmoValue(f) {
  const raw = f.value;
  if (raw === null || raw === undefined || raw === "") return null;
  const unit = String(f.unit || "");
  const u = unit.toLowerCase();
  if (!/^-?[\d.,]+$/.test(String(raw).trim())) return String(raw); // prose
  if (u.includes("usd") || u.includes("dollar")) return fmtMoney(raw, unit);
  if (u.includes("percent") || unit === "%") return `${fmtNum(raw)}%`;
  if (u === "year") return String(raw);
  if (u.includes("ratio") || u === "x") return `${fmtNum(raw)}×`;
  const n = fmtNum(raw);
  return unitRestatesLabel(f) ? n : unit ? `${n}${NBSP}${unit}` : n;
}

/* "Employees 767 full and part-time employees" says employees twice. A unit
   whose words the row's own label already carries is redundant on the row; it
   stays in the row's title, so nothing from the payload is lost. */
function unitRestatesLabel(f) {
  const unit = String(f.unit || "").toLowerCase();
  if (!unit) return false;
  const label = firmoLabel(f.field).toLowerCase();
  const stem = w => w.replace(/(ies|es|s)$/, "");
  const labelStems = label.split(/[^a-z]+/).filter(Boolean).map(stem);
  return unit.split(/[^a-z]+/).filter(Boolean).map(stem).some(w => w.length > 3 && labelStems.includes(w));
}
const FIRMO_LABELS = {
  total_assets: "Assets",
  member_count: "Members",
  customer_count: "Customers",
  employees: "Employees",
  branches: "Branches",
  founded: "Founded",
  net_worth_ratio: "Net worth ratio",
  charter: "Charter",
  primary_regulator: "Regulator",
  shares: "Shares",
  loans: "Loans",
  roa: "ROA",
  aum: "AUM",
  deposits: "Deposits",
  revenue: "Revenue",
  premiums_written: "Premiums written"
};
function firmoLabel(k) {
  return FIRMO_LABELS[k] || String(k).replace(/_/g, " ").replace(/^\w/, c => c.toUpperCase());
}
const BAND_CLASS = {
  activating: "b-m1",
  building: "b-m2",
  competing: "b-m3",
  differentiating: "b-m4"
};

/* Band class from either a raw score or a band word. The score path defers to
   the ONE resolver; the word path maps the four-value enum and nothing else —
   an unknown word gets no colour rather than a wrong one. */
function bandClass(v) {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v);
  if (isFinite(n)) return DMA.helpers.maturityClass(n);
  return BAND_CLASS[String(v).trim().toLowerCase()] || "";
}

/* fmtScore and fmtPctVal return TEXT, because both are also read into title
   attributes, where a React element cannot go. The absent case is therefore a
   plain word here; every JSX site that can receive a null renders
   <EnrichmentGap> instead, which names the field and carries the route to
   enrichment. */
function fmtScore(v) {
  return v === null || v === undefined ? "not stated" : Number(v).toFixed(1);
}
function fmtPctVal(v, decimals) {
  if (v === null || v === undefined) return "not stated";
  return `${fmtNum(v, {
    decimals: decimals === undefined ? 0 : decimals
  })}%`;
}

/* Delta is PROMOTED, never recomputed here (invariant 8). An absent delta is
   an absent peer comparison, not a zero — it renders as the enrichment gap in
   its compact form, because every delta on this page sits in a narrow
   fixed-width numeric column. */
function DeltaBadge({
  delta,
  direction,
  audience
}) {
  if (delta === null || delta === undefined) {
    return /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: "Peer delta",
      audience: audience,
      compact: true
    });
  }
  const below = direction ? direction === "below" : delta < 0;
  return /*#__PURE__*/React.createElement("span", {
    className: "f-mono",
    style: {
      fontSize: 11,
      color: below ? "var(--z-below)" : "var(--z-mid)"
    }
  }, below ? "▼" : "▲", " ", Math.abs(delta).toFixed(2));
}
function ClaimChip({
  label,
  confidence
}) {
  if (!label) return null;
  const cls = label === "FACT" ? "b-ph1" : label === "INFERENCE" ? "b-ph0" : "b-purple";
  return /*#__PURE__*/React.createElement("span", {
    className: "row",
    style: {
      gap: 5
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `b ${cls}`
  }, label), confidence ? /*#__PURE__*/React.createElement("span", {
    className: "b"
  }, confidence) : null);
}

/* Every surface carries its provenance line — who produced it, when it
   promoted, how many evidence ids it cites. Small, at the card's foot. */
function ProvFoot({
  state
}) {
  if (!state) return null;
  const bits = [];
  if (state.producer_version) bits.push(state.producer_version);
  if (state.produced_at) bits.push(`promoted ${fmtDate(state.produced_at)}`);
  const n = (state.e_ids || []).length;
  if (n) bits.push(`${n} evidence id${n === 1 ? "" : "s"}`);
  if (!bits.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      marginTop: 10,
      fontFamily: "var(--font-mono)"
    }
  }, bits.join(" · "));
}

/* A section that did not promote, was withheld, or lives elsewhere. This
   is the ONLY non-designed rendering left, and it carries no payload. */
function LiveMissing({
  name,
  state
}) {
  const es = state && state.empty_state || {};
  const kind = ENVELOPE_ONLY[name] ? "no_contract_field" : es.kind || state && state.data_source || "unavailable";
  const label = {
    section_not_promoted: "Not promoted",
    withheld_for_audience: "Not shown to this audience",
    served_from_evidence_store: "Read per evidence id",
    no_contract_field: "No payload contract yet",
    empty: "Nothing to show"
  }[kind] || "Unavailable";
  const reason = ENVELOPE_ONLY[name] || es.reason;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 14,
      padding: "14px 18px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12.5,
      fontWeight: 600
    }
  }, SECTION_TITLES[name] || name), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    className: "b"
  }, label)), reason ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-muted)",
      marginTop: 6,
      lineHeight: 1.5
    }
  }, reason) : null);
}

/* One bad field must not take the page. A section that throws degrades to a
   notice naming itself, and its neighbours still render — the alternative,
   which this app shipped until now, is a white screen for the whole client. */
class SectionBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      failed: null
    };
  }
  static getDerivedStateFromError(err) {
    return {
      failed: err
    };
  }
  componentDidCatch(err) {
    if (typeof console !== "undefined") console.error("section render failed", err);
  }
  render() {
    if (this.state.failed) {
      return /*#__PURE__*/React.createElement("div", {
        className: "card",
        style: {
          marginBottom: 14,
          padding: "14px 18px",
          borderLeft: "3px solid var(--z-org)"
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "row"
      }, /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 12.5,
          fontWeight: 600
        }
      }, SECTION_TITLES[this.props.name] || this.props.name), /*#__PURE__*/React.createElement("span", {
        className: "spacer"
      }), /*#__PURE__*/React.createElement("span", {
        className: "b b-org"
      }, "Could not render")), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 11.5,
          color: "var(--z-muted)",
          marginTop: 6
        }
      }, "This section promoted, but its payload did not fit the surface. The other sections on this page are unaffected."));
    }
    return this.props.children;
  }
}
function Sec({
  name,
  children
}) {
  return /*#__PURE__*/React.createElement(SectionBoundary, {
    name: name
  }, children);
}
function SectionHead({
  title,
  note,
  right
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, title), note ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      marginTop: 2
    }
  }, note) : null), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), right || null);
}

/* ══ O1 · snapshot strip: ring · pillar bars · firmographics ═════════
   The prototype's D1 opening card, three columns, unchanged in shape. */
function LiveSnapshot({
  scores,
  firmo,
  entity,
  run,
  state,
  audience
}) {
  const d = scores || {};
  const pillars = d.pillars || [];
  const byId = {};
  pillars.forEach(p => {
    byId[p.pillar_id] = p;
  });
  const fields = (firmo && firmo.fields || []).filter(f => f.value !== null && f.value !== undefined && f.value !== "");
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "20px 22px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: fields.length ? "1fr 280px" : "1fr",
      gap: 28,
      alignItems: "stretch"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 18,
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement(ScoreRing, {
    score: d.composite
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
  }, d.composite != null ? /*#__PURE__*/React.createElement("span", {
    className: `b ${DMA.helpers.maturityClass(d.composite)}`
  }, DMA.helpers.maturityLabel(d.composite).toUpperCase()) : null, d.posture ? /*#__PURE__*/React.createElement("span", {
    className: "b b-ph1"
  }, "POSTURE \xB7 ", d.posture) : null, d.posture_basis ? /*#__PURE__*/React.createElement("span", {
    className: "b"
  }, d.posture_basis) : null, /*#__PURE__*/React.createElement(ClaimChip, {
    label: d.claim_label,
    confidence: d.confidence
  })), d.framing ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      color: "var(--z-body)",
      lineHeight: 1.5
    }
  }, d.framing) : null)), pillars.length ? /*#__PURE__*/React.createElement("div", null, DMA.PILLARS.map(p => {
    const row = byId[p.id];
    if (!row) return null;
    const s = row.score,
      peer = row.peer_median;
    return /*#__PURE__*/React.createElement("div", {
      className: "pbar",
      key: p.id,
      style: {
        cursor: "pointer"
      },
      onClick: () => navigate(`/clients/${entity.id}/heatmap`, {
        pillar: p.id,
        run: run && run.id
      })
    }, /*#__PURE__*/React.createElement("div", {
      className: "pbar-name"
    }, p.id, " \xB7 ", p.short), /*#__PURE__*/React.createElement("div", {
      className: "pbar-track"
    }, /*#__PURE__*/React.createElement("div", {
      className: "pbar-fill",
      style: {
        width: `${s / 5 * 100}%`,
        background: DMA.helpers.maturityHex(s)
      }
    }), peer != null ? /*#__PURE__*/React.createElement("div", {
      className: "pbar-peer",
      style: {
        left: `calc(${peer / 5 * 100}% - 1px)`
      },
      title: `Peer median ${fmtScore(peer)}${row.peer_n ? ` · n=${row.peer_n}` : ""}`
    }) : null), /*#__PURE__*/React.createElement("div", {
      className: "pbar-score"
    }, s == null ? /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: `${p.id} pillar score`,
      audience: audience,
      compact: true
    }) : fmtScore(s)), /*#__PURE__*/React.createElement("div", {
      className: "pbar-delta"
    }, /*#__PURE__*/React.createElement(DeltaBadge, {
      delta: row.delta,
      direction: row.direction,
      audience: audience
    })));
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 8,
      fontSize: 10.5,
      color: "var(--z-muted)",
      display: "flex",
      gap: 14,
      paddingLeft: 122,
      flexWrap: "wrap"
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
  }), "Peer median"), pillars[0] && pillars[0].peer_basis ? /*#__PURE__*/React.createElement("span", null, "peer basis: ", pillars[0].peer_basis) : null)) : null, d.narrative_thread ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14,
      paddingTop: 12,
      borderTop: "1px solid var(--z-sep)",
      fontSize: 12,
      color: "var(--z-body)",
      lineHeight: 1.55
    }
  }, d.narrative_thread) : null, /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  })), fields.length ? /*#__PURE__*/React.createElement("div", {
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
  }, "Firmographics"), fields.map(f => /*#__PURE__*/React.createElement(Row, {
    key: f.field,
    k: /*#__PURE__*/React.createElement("span", {
      style: {
        whiteSpace: "nowrap"
      }
    }, firmoLabel(f.field)),
    v: /*#__PURE__*/React.createElement("span", {
      title: [f.unit, f.as_of ? `as of ${f.as_of}` : null, f.source_e_id, f.confidence].filter(Boolean).join(" · ")
    }, fmtFirmoValue(f), f.recency_band && f.recency_band !== "CURRENT" ? /*#__PURE__*/React.createElement("span", {
      className: "b",
      style: {
        marginLeft: 6,
        fontSize: 8.5
      }
    }, f.recency_band) : null, f.quarantined ? /*#__PURE__*/React.createElement("span", {
      className: "b b-org",
      style: {
        marginLeft: 6,
        fontSize: 8.5
      }
    }, "QUARANTINED") : null)
  })), (firmo && firmo.fields || []).some(f => f.value === null) ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      marginTop: 8,
      paddingTop: 8,
      borderTop: "1px solid rgba(0,0,0,.06)"
    }
  }, "Not established: ", (firmo.fields || []).filter(f => f.value === null).map(f => firmoLabel(f.field).toLowerCase()).join(", ")) : null) : null));
}

/* ══ O2 · why now ══════════════════════════════════════════════════ */
function LiveWhyNow({
  data,
  state
}) {
  const signals = data && data.signals || [];
  if (!signals.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Why now",
    note: "dated triggers, with the cost of waiting and of acting",
    right: /*#__PURE__*/React.createElement("span", {
      className: "b b-org"
    }, signals.length, " signal", signals.length === 1 ? "" : "s")
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 12
    }
  }, signals.map((s, i) => /*#__PURE__*/React.createElement("div", {
    key: s.wn_id || i,
    className: "card-tile",
    style: {
      padding: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 6,
      gap: 8
    }
  }, s.dated_on ? /*#__PURE__*/React.createElement("span", {
    className: "b f-mono"
  }, s.dated_on) : /*#__PURE__*/React.createElement("span", {
    className: "b b-org"
  }, "UNDATED"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement(ClaimChip, {
    label: s.claim_label,
    confidence: s.confidence
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      lineHeight: 1.45,
      marginBottom: 8
    }
  }, s.trigger), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 8
    }
  }, [["If this waits", s.consequence_of_waiting], ["Cost of acting now", s.cost_of_acting_now], ["Why first", s.why_this_sequence]].map(([k, v]) => v ? /*#__PURE__*/React.createElement("div", {
    key: k
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      fontSize: 9.5
    }
  }, k), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      lineHeight: 1.5
    }
  }, v)) : null)), (s.linked_subcap_ids || []).length ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 10,
      gap: 4,
      flexWrap: "wrap"
    }
  }, s.linked_subcap_ids.map(id => /*#__PURE__*/React.createElement("span", {
    key: id,
    className: "chip f-mono",
    style: {
      fontSize: 9.5
    }
  }, id))) : null))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ O3 · SCQA executive summary ═══════════════════════════════════ */
function LiveExecSummary({
  data,
  state
}) {
  if (!data) return null;
  const parts = [["Situation", data.situation], ["Complication", data.complication], ["Question", data.question], ["Answer", data.answer], ["Why this order", data.sequencing_rationale], ["Cost of delay", data.cost_of_delay]];
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Executive summary",
    note: "situation \xB7 complication \xB7 question \xB7 answer",
    right: /*#__PURE__*/React.createElement(ClaimChip, {
      label: data.claim_label
    })
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 12
    }
  }, parts.map(([k, v]) => v ? /*#__PURE__*/React.createElement("div", {
    key: k
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      fontSize: 9.5,
      marginBottom: 3
    }
  }, k), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      color: "var(--z-body)",
      lineHeight: 1.6
    }
  }, v)) : null)), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ O4 · opportunity surface ══════════════════════════════════════ */
function LiveOpportunity({
  data,
  state
}) {
  const tiles = data && data.tiles || [];
  const discarded = data && data.discarded || [];
  if (!tiles.length && !discarded.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Opportunity surface",
    note: "where capability gap meets a platform that closes it"
  }), /*#__PURE__*/React.createElement("div", {
    className: "g4"
  }, tiles.slice().sort((a, b) => (a.rank || 99) - (b.rank || 99)).map((t, i) => /*#__PURE__*/React.createElement("div", {
    key: t.platform || i,
    className: "card-tile",
    style: {
      padding: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 8,
      gap: 6
    }
  }, t.rank != null ? /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, t.rank, ".") : null, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12.5,
      fontWeight: 600,
      flex: 1,
      minWidth: 0
    }
  }, t.platform), t.composite != null ? /*#__PURE__*/React.createElement("span", {
    className: "b b-ph1 f-mono",
    title: "composite opportunity score"
  }, fmtNum(t.composite, {
    decimals: 2
  })) : null), t.relevance ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      lineHeight: 1.5,
      marginBottom: 6
    }
  }, t.relevance) : null, t.their_stack_context ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      lineHeight: 1.5,
      marginBottom: 6
    }
  }, t.their_stack_context) : null, (t.factors || []).length ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 8
    }
  }, t.factors.map((f, j) => /*#__PURE__*/React.createElement("div", {
    key: j,
    className: "row",
    style: {
      fontSize: 10.5,
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "muted",
    style: {
      minWidth: 104
    },
    title: f.weight != null ? `weight ${f.weight}` : ""
  }, String(f.name || "").replace(/_/g, " ")), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "prog",
    style: {
      height: 4
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "prog-fill",
    style: {
      width: `${Math.min(100, Number(f.value) / 10 * 100)}%`,
      background: "var(--z-teal)"
    }
  }))), /*#__PURE__*/React.createElement("span", {
    className: "f-mono",
    style: {
      minWidth: 26,
      textAlign: "right"
    }
  }, fmtNum(f.value)), f.contribution != null ? /*#__PURE__*/React.createElement("span", {
    className: "muted f-mono",
    style: {
      minWidth: 40,
      textAlign: "right",
      fontSize: 9.5
    },
    title: "contribution to the composite"
  }, "+", fmtNum(f.contribution, {
    decimals: 1
  })) : null))) : null, t.rank_rationale ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      lineHeight: 1.5
    }
  }, t.rank_rationale) : null, (t.addressable_cells || []).length ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 8,
      paddingTop: 8,
      borderTop: "1px solid var(--z-sep)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      fontSize: 9,
      marginBottom: 5
    }
  }, "Cells it addresses \xB7 ", t.addressable_cells.length), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 4
    }
  }, t.addressable_cells.slice(0, 6).map((c, j) => /*#__PURE__*/React.createElement("div", {
    key: j,
    className: "row",
    style: {
      gap: 6,
      fontSize: 10.5
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "chip f-mono",
    style: {
      fontSize: 9
    }
  }, typeof c === "string" ? c : c.subcap_id), typeof c === "object" && c.current != null ? /*#__PURE__*/React.createElement("span", {
    className: `b ${bandClass(c.current)}`
  }, fmtScore(c.current)) : null, /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      minWidth: 0,
      color: "var(--z-body)",
      lineHeight: 1.4
    }
  }, typeof c === "object" ? asText(c.feature_that_addresses_it) || asText(c.name) || "" : ""))), t.addressable_cells.length > 6 ? /*#__PURE__*/React.createElement("span", {
    className: "muted",
    style: {
      fontSize: 9.5
    }
  }, "+", t.addressable_cells.length - 6, " more cells") : null)) : null))), discarded.length ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14,
      paddingTop: 12,
      borderTop: "1px solid var(--z-sep)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      fontSize: 9.5,
      marginBottom: 6
    }
  }, "Considered and set aside"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 5
    }
  }, discarded.map((x, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      fontSize: 11.5,
      color: "var(--z-muted)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-dark)",
      fontWeight: 500
    }
  }, x.platform || x.name), x.reason || x.why_not ? ` — ${x.reason || x.why_not}` : "")))) : null, /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ O5 · top findings ═════════════════════════════════════════════ */
function LiveFindings({
  data,
  state
}) {
  const findings = data && data.findings || [];
  const [open, setOpen] = useState(null);
  if (!findings.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Top findings",
    note: data.ranking_basis ? `ranked by ${data.ranking_basis.replace(/_/g, " ")}` : null
  }), data.narrative_thread ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-body)",
      lineHeight: 1.55,
      marginBottom: 12
    }
  }, data.narrative_thread) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 8
    }
  }, findings.map((f, i) => {
    const isOpen = open === (f.f_id || i);
    return /*#__PURE__*/React.createElement("div", {
      key: f.f_id || i,
      className: "card-tile clickable",
      style: {
        padding: "12px 14px"
      },
      onClick: () => setOpen(isOpen ? null : f.f_id || i)
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 8,
        alignItems: "flex-start"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "b f-mono"
    }, f.f_id), f.theme ? /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, f.theme) : null, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        fontWeight: 600,
        lineHeight: 1.4,
        flex: 1,
        minWidth: 0
      }
    }, f.title), f.consequence ? /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10.5,
        color: "var(--z-org)",
        textAlign: "right",
        maxWidth: 210
      }
    }, f.consequence) : null, /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-d" : "chevron-r",
      size: 12
    })), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 10,
        display: "grid",
        gap: 10
      }
    }, f.body ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-body)",
        lineHeight: 1.6
      }
    }, f.body) : null, f.rejected_alternative ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "eyebrow",
      style: {
        fontSize: 9.5
      }
    }, "Alternative considered"), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        lineHeight: 1.5
      }
    }, f.rejected_alternative)) : null, f.strategic_alignment ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "eyebrow",
      style: {
        fontSize: 9.5
      }
    }, "Strategic alignment", f.strategic_alignment.score != null ? ` · ${fmtNum(f.strategic_alignment.score, {
      decimals: 2
    })}` : ""), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        lineHeight: 1.5
      }
    }, asText(f.strategic_alignment.statement))) : null, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 4,
        flexWrap: "wrap"
      }
    }, (f.platform_chips || []).map(p => /*#__PURE__*/React.createElement("span", {
      key: p,
      className: "chip purple"
    }, p)), (f.linked_subcap_ids || []).map(id => /*#__PURE__*/React.createElement("span", {
      key: id,
      className: "chip f-mono",
      style: {
        fontSize: 9.5
      }
    }, id)), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement(ClaimChip, {
      label: f.claim_label,
      confidence: f.confidence
    })), /*#__PURE__*/React.createElement(RLayer, {
      r: f.r_layer
    })) : null);
  })), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* The producer's own challenge record. Internal reading, shown inline
   because a finding without its counter-case is half the finding. */
function RLayer({
  r
}) {
  if (!r) return null;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--z-lav)",
      borderRadius: 8,
      padding: "10px 12px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 5
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "eyebrow",
    style: {
      fontSize: 9.5
    }
  }, "Challenge record"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), r.verdict ? /*#__PURE__*/React.createElement("span", {
    className: `b ${r.verdict === "ACCEPT" ? "b-ph1" : "b-org"}`
  }, r.verdict) : null, r.confidence ? /*#__PURE__*/React.createElement("span", {
    className: "b"
  }, r.confidence) : null), r.hypothesis ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement("b", null, "Hypothesis."), " ", r.hypothesis) : null, r.counter ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      marginBottom: 4
    }
  }, r.counter) : null, r.domain_test ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement("b", null, "Domain test."), " ", r.domain_test) : null, (r.probes_run || []).length ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)"
    }
  }, "Probes: ", r.probes_run.join(" · ")) : null);
}

/* ══ O6 · leadership roster ════════════════════════════════════════ */
function LiveLeadership({
  data,
  state
}) {
  const roster = data && data.roster || [];
  if (!roster.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Leadership",
    note: `${roster.length} named`
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 8
    }
  }, roster.map((p, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "card-tile",
    style: {
      padding: "10px 12px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12.5,
      fontWeight: 600
    }
  }, p.name), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)"
    }
  }, p.title), p.domain ? /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, p.domain) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), p.appointed_on ? /*#__PURE__*/React.createElement("span", {
    className: "b f-mono"
  }, "since ", p.appointed_on) : null, p.tenure_months != null ? /*#__PURE__*/React.createElement("span", {
    className: "muted",
    style: {
      fontSize: 10
    }
  }, p.tenure_months, " months") : null, p.confidence ? /*#__PURE__*/React.createElement("span", {
    className: "b"
  }, p.confidence) : null), p.relevance_note ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-body)",
      marginTop: 5,
      lineHeight: 1.5
    }
  }, p.relevance_note) : null, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 4,
      gap: 6
    }
  }, p.as_of ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9.5,
      color: "var(--z-muted)"
    }
  }, "as of ", p.as_of) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), p.source_e_id ? /*#__PURE__*/React.createElement("span", {
    className: "chip f-mono",
    style: {
      fontSize: 9
    }
  }, p.source_e_id) : null)))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ O7 · financial trajectory ═════════════════════════════════════ */
function LiveFinancials({
  data,
  state,
  audience
}) {
  const series = data && data.series || [];
  if (!series.length) return null;
  const points = series.filter(s => s.value != null);
  const max = Math.max(...points.map(p => Number(p.value) || 0), 1);
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      padding: "16px 18px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Financial trajectory",
    note: data.trend ? `trend ${data.trend.toLowerCase()}` : null,
    right: data.verified_sparse ? /*#__PURE__*/React.createElement("span", {
      className: "b b-org"
    }, "SPARSE") : null
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-end",
      gap: 8,
      height: 90,
      marginBottom: 8
    }
  }, series.map((p, i) => {
    const v = Number(p.value);
    const h = isFinite(v) ? Math.max(4, v / max * 82) : 0;
    return /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        flex: 1,
        textAlign: "center"
      },
      title: [p.period, p.value == null ? "not established" : p.unit ? fmtMoney(p.value, p.unit) : fmtNum(p.value), p.as_of ? `as of ${p.as_of}` : null].filter(Boolean).join(" · ")
    }, p.value == null ? /*#__PURE__*/React.createElement("div", {
      style: {
        height: 82,
        border: "1px dashed var(--z-sep)",
        borderRadius: 4
      }
    }) : /*#__PURE__*/React.createElement("div", {
      style: {
        height: h,
        background: "var(--z-teal)",
        borderRadius: "4px 4px 0 0"
      }
    }));
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8
    }
  }, series.map((p, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      flex: 1,
      textAlign: "center",
      fontSize: 9.5,
      color: "var(--z-muted)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "f-mono"
  }, p.period || /*#__PURE__*/React.createElement(EnrichmentGap, {
    what: "Reporting period",
    audience: audience,
    compact: true
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      color: "var(--z-dark)",
      fontWeight: 500
    }
  }, p.value == null ? /*#__PURE__*/React.createElement(EnrichmentGap, {
    what: p.period ? `${p.period} figure` : "Financial figure",
    audience: audience,
    compact: true
  }) : p.unit ? fmtMoney(p.value, p.unit) : fmtNum(p.value))))), series.some(p => p.basis) ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      marginTop: 8
    }
  }, asText(series.find(p => p.basis).basis), series.find(p => p.source_e_id) ? ` · ${series.find(p => p.source_e_id).source_e_id}` : "") : null, /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ O8 · evidence coverage & tier mix ═════════════════════════════ */
function LiveCoverage({
  data,
  state,
  audience
}) {
  if (!data) return null;
  const per = data.per_pillar || [];
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      padding: "16px 18px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Evidence coverage",
    right: data.overall_pct != null ? /*#__PURE__*/React.createElement("span", {
      className: "b b-ph1 f-mono"
    }, fmtPctVal(data.overall_pct, 1)) : null
  }), per.map((p, i) => /*#__PURE__*/React.createElement("div", {
    key: p.pillar_id || i,
    style: {
      marginBottom: 9
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      fontSize: 11,
      marginBottom: 3,
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "f-mono"
  }, p.pillar_id), p.pillar_name && p.pillar_name !== p.pillar_id ? /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, p.pillar_name) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), p.cells_covered != null && p.cells_total != null ? /*#__PURE__*/React.createElement("span", {
    className: "muted",
    style: {
      fontSize: 10
    }
  }, fmtNum(p.cells_covered), "/", fmtNum(p.cells_total)) : null, /*#__PURE__*/React.createElement("span", {
    className: "f-mono"
  }, p.pct == null ? /*#__PURE__*/React.createElement(EnrichmentGap, {
    what: `${p.pillar_id || "Pillar"} evidence coverage`,
    audience: audience,
    compact: true
  }) : fmtPctVal(p.pct, 1)), p.below_gate ? /*#__PURE__*/React.createElement("span", {
    className: "b b-org",
    title: "below the corpus gate threshold"
  }, "BELOW GATE") : null), /*#__PURE__*/React.createElement("div", {
    className: "prog"
  }, /*#__PURE__*/React.createElement("div", {
    className: "prog-fill",
    style: {
      width: `${Math.min(100, Number(p.pct) || 0)}%`,
      background: p.below_gate ? "var(--z-org)" : "var(--z-teal)"
    }
  })))), data.gate_pct != null ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 8
    }
  }, "Corpus gate threshold ", fmtPctVal(data.gate_pct, 0)) : null, data.denominator_definition ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 6,
      lineHeight: 1.5
    }
  }, data.denominator_definition) : null, data.note ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 6,
      lineHeight: 1.5
    }
  }, data.note) : null, /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ O9 · sentiment ════════════════════════════════════════════════ */
function LiveSentiment({
  data,
  state,
  title
}) {
  const bars = data && data.bars || [];
  if (!bars.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      padding: "16px 18px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: title || "Sentiment"
  }), bars.map((b, i) => {
    // A rating is only a bar if its own scale gives it bounds. NPS runs
    // -100..100, a star rating 0..5; a bar drawn on the wrong scale is a
    // lie, so an unrecognised scale shows the figure and no bar.
    const scale = String(b.scale || "");
    const m = scale.match(/(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)/);
    const lo = m ? Number(m[1]) : null,
      hi = m ? Number(m[2]) : null;
    const pct = m && b.rating != null && hi > lo ? Math.max(0, Math.min(100, (Number(b.rating) - lo) / (hi - lo) * 100)) : null;
    return /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        marginBottom: 12
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        fontSize: 11.5,
        marginBottom: 3,
        gap: 6
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontWeight: 500,
        flex: 1,
        minWidth: 0
      }
    }, asText(b.source)), b.audience ? /*#__PURE__*/React.createElement("span", {
      className: "b"
    }, b.audience) : null, b.rating != null ? /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        fontWeight: 600
      }
    }, fmtNum(b.rating, {
      decimals: 1
    })) : null, b.n != null ? /*#__PURE__*/React.createElement("span", {
      className: "muted",
      style: {
        fontSize: 10
      }
    }, "n=", fmtNum(b.n)) : null), pct != null ? /*#__PURE__*/React.createElement("div", {
      className: "prog"
    }, /*#__PURE__*/React.createElement("div", {
      className: "prog-fill",
      style: {
        width: `${pct}%`,
        background: "var(--z-teal)"
      }
    })) : null, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginTop: 4,
        gap: 6,
        fontSize: 9.5,
        color: "var(--z-muted)"
      }
    }, b.scale ? /*#__PURE__*/React.createElement("span", {
      className: "f-mono"
    }, b.scale) : null, b.trend_vs_prior ? /*#__PURE__*/React.createElement("span", null, asText(b.trend_vs_prior)) : null, /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), b.as_of ? /*#__PURE__*/React.createElement("span", null, "as of ", b.as_of) : null, b.url ? /*#__PURE__*/React.createElement("a", {
      href: b.url,
      target: "_blank",
      rel: "noreferrer",
      style: {
        color: "var(--z-teal)"
      }
    }, "source \u2197") : null, b.e_id ? /*#__PURE__*/React.createElement("span", {
      className: "chip f-mono",
      style: {
        fontSize: 9
      }
    }, b.e_id) : null));
  }), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ O10 · capability ceilings ═════════════════════════════════════ */
function LiveCeilings({
  data,
  state
}) {
  const rows = data && data.rows || [];
  const [all, setAll] = useState(false);
  if (!rows.length) return null;
  const shown = all ? rows : rows.slice(0, 8);
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      padding: "16px 18px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Capability ceilings & uncertainty",
    note: `${rows.length} bounded estimate${rows.length === 1 ? "" : "s"}`
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 6
    }
  }, shown.map((r, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "card-tile",
    style: {
      padding: "10px 12px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "f-mono b"
  }, r.category_id), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      fontWeight: 500,
      flex: 1,
      minWidth: 0
    }
  }, r.category_name), r.uncertainty_band != null ? /*#__PURE__*/React.createElement("span", {
    className: "b f-mono",
    title: "uncertainty band on the estimate"
  }, "\xB1", fmtNum(r.uncertainty_band, {
    decimals: 2
  })) : null, r.ceiling != null ? /*#__PURE__*/React.createElement("span", {
    className: `b ${bandClass(r.ceiling)}`,
    title: "the highest band the evidence tier licenses"
  }, "ceiling ", isFinite(Number(r.ceiling)) ? fmtScore(r.ceiling) : r.ceiling) : null), r.rationale ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-body)",
      marginTop: 5,
      lineHeight: 1.5
    }
  }, r.rationale) : null, r.limiting_absence ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-org)",
      marginTop: 4,
      lineHeight: 1.5
    }
  }, "What is missing: ", r.limiting_absence) : null, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 4,
      gap: 4,
      flexWrap: "wrap"
    }
  }, (r.urf_modifiers || []).map((m, j) => /*#__PURE__*/React.createElement("span", {
    key: j,
    className: "chip",
    style: {
      fontSize: 9.5
    },
    title: "uncertainty-reduction modifier applied to the band"
  }, typeof m === "object" && m ? [asText(m.clause), m.value != null ? fmtNum(m.value, {
    decimals: 2
  }) : null].filter(Boolean).join(" ") : asText(m))), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement(ClaimChip, {
    label: r.claim_label,
    confidence: r.confidence
  }))))), rows.length > 8 ? /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    style: {
      marginTop: 8
    },
    onClick: () => setAll(o => !o)
  }, all ? "Show fewer" : `Show all ${rows.length}`) : null, /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ O11 · thought leadership (internal) ═══════════════════════════ */
function LiveThoughtLeadership({
  data,
  state
}) {
  const entries = data && data.entries || [];
  if (!entries.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Thought leadership",
    note: "what the institution says in public, in its own words",
    right: /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, "INTERNAL")
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 10
    }
  }, entries.map((e, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "card-tile",
    style: {
      padding: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8,
      marginBottom: 5
    }
  }, e.kind ? /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, e.kind) : null, e.author_name ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      fontWeight: 600
    }
  }, e.author_name) : null, e.author_role ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, e.author_role) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), e.published_on ? /*#__PURE__*/React.createElement("span", {
    className: "b f-mono"
  }, e.published_on) : null, /*#__PURE__*/React.createElement(ClaimChip, {
    label: e.claim_label
  })), e.headline ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      fontWeight: 600,
      lineHeight: 1.45,
      marginBottom: 6
    }
  }, e.headline) : null, e.quote ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      fontStyle: "italic",
      lineHeight: 1.55,
      borderLeft: "2px solid var(--z-teal)",
      paddingLeft: 10
    }
  }, "\u201C", e.quote, "\u201D") : null, e.alignment ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 8,
      gap: 8,
      alignItems: "flex-start"
    }
  }, typeof e.alignment === "object" && e.alignment.value ? /*#__PURE__*/React.createElement("span", {
    className: "b b-ph1",
    title: "how this signal relates to the assessment"
  }, e.alignment.value) : null, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      flex: 1,
      minWidth: 0,
      lineHeight: 1.5
    }
  }, typeof e.alignment === "object" ? asText(e.alignment.clause) : asText(e.alignment))) : null, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 6,
      gap: 4,
      flexWrap: "wrap"
    }
  }, (e.linked_subcap_ids || []).map(id => /*#__PURE__*/React.createElement("span", {
    key: id,
    className: "chip f-mono",
    style: {
      fontSize: 9
    }
  }, id)), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), e.url ? /*#__PURE__*/React.createElement("a", {
    href: e.url,
    target: "_blank",
    rel: "noreferrer",
    style: {
      fontSize: 10,
      color: "var(--z-teal)"
    },
    onClick: ev => ev.stopPropagation()
  }, "source \u2197") : null, e.e_id ? /*#__PURE__*/React.createElement("span", {
    className: "chip f-mono",
    style: {
      fontSize: 9
    }
  }, e.e_id) : null)))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ H4 · the workbook grid ════════════════════════════════════════
   The prototype's category heatmap, rendered from promoted pillar and
   category scores. Colour is resolved here from the raw score — the
   payload carries no hex, by invariant 7. */
function LiveWorkbookGrid({
  data,
  state,
  entity,
  run,
  onDrill,
  audience
}) {
  const [showPeers, setShowPeers] = useState(true);
  const [pillarFocus, setPillarFocus] = useState(null);
  if (!data) return null;
  const pillars = data.pillars || {};
  const cats = data.categories || {};
  const shown = DMA.PILLARS.filter(p => !pillarFocus || p.id === pillarFocus);
  const offCatalogue = Object.keys(cats).filter(cid => !DMA.CATEGORIES.some(c => c.id === cid)).sort();
  const catsOf = pid => Object.keys(cats).filter(c => c.startsWith(pid)).sort();
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Maturity grid",
    note: [`${Object.keys(pillars).length} pillars`, `${Object.keys(cats).length} categories, as scored in the workbook`, offCatalogue.length ? `${offCatalogue.join(", ")} not in the current catalogue` : null].filter(Boolean).join(" · "),
    right: /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 10
      }
    }, /*#__PURE__*/React.createElement("label", {
      className: "row",
      style: {
        fontSize: 11,
        cursor: "pointer"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: `switch ${showPeers ? "on" : ""}`,
      onClick: () => setShowPeers(p => !p)
    }), " Peers"), pillarFocus ? /*#__PURE__*/React.createElement("button", {
      className: "btn btn-tertiary btn-sm",
      onClick: () => setPillarFocus(null)
    }, "Reset") : null)
  }), /*#__PURE__*/React.createElement("div", {
    className: "g4",
    style: {
      marginBottom: 18
    }
  }, DMA.PILLARS.map(p => {
    const row = pillars[p.id];
    if (!row) return null;
    return /*#__PURE__*/React.createElement("div", {
      key: p.id,
      className: "card-tile clickable",
      style: {
        padding: 14
      },
      onClick: () => setPillarFocus(pillarFocus === p.id ? null : p.id)
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 10
      }
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)"
      }
    }, p.id), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, p.name)), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement(MaturityChip, {
      score: row.score,
      large: true
    })), row.band ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        color: "var(--z-muted)",
        marginBottom: 6,
        letterSpacing: ".04em"
      },
      title: "band generated by the database from the raw score"
    }, String(row.band).toUpperCase()) : null, /*#__PURE__*/React.createElement("div", {
      className: "prog"
    }, /*#__PURE__*/React.createElement("div", {
      className: "prog-fill",
      style: {
        width: `${row.score / 5 * 100}%`,
        background: DMA.helpers.maturityHex(row.score)
      }
    })), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginTop: 8,
        fontSize: 10.5
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        color: "var(--z-muted)"
      }
    }, row.peer_median == null ? /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: `${p.id} peer median`,
      audience: audience,
      compact: true
    }) : `Peer ${fmtScore(row.peer_median)}`), row.delta != null ? /*#__PURE__*/React.createElement(DeltaBadge, {
      delta: Number(row.delta),
      audience: audience
    }) : null, /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 9.5,
        color: "var(--z-muted)"
      }
    }, catsOf(p.id).length, " categories")), row.source_cell ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9,
        color: "var(--z-muted)",
        marginTop: 6,
        fontFamily: "var(--font-mono)"
      }
    }, row.source_cell) : null);
  })), shown.map(p => {
    const ids = catsOf(p.id);
    if (!ids.length) return null;
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
    }, p.name), pillars[p.id] ? /*#__PURE__*/React.createElement(MaturityChip, {
      score: pillars[p.id].score
    }) : null, /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)"
      }
    }, ids.length, " categories")), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: `72px repeat(${ids.length}, minmax(0,1fr))`,
        gap: 4
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)",
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        paddingRight: 8
      }
    }, "Entity"), ids.map(cid => {
      const c = cats[cid];
      return /*#__PURE__*/React.createElement("button", {
        key: cid,
        className: `hm-cell b ${DMA.helpers.maturityClass(c.score)}`,
        onClick: () => onDrill && onDrill(cid),
        style: {
          border: 0,
          padding: "8px 6px",
          minHeight: 44
        },
        title: [cid, c.band, `score ${fmtScore(c.score)}`, c.peer_median != null ? `peer ${fmtScore(c.peer_median)}` : null, c.delta != null ? `delta ${Number(c.delta) >= 0 ? "+" : ""}${Number(c.delta).toFixed(2)}` : null, c.source_cell, "click for cell evidence"].filter(Boolean).join(" · ")
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          display: "flex",
          flexDirection: "column",
          lineHeight: 1.15,
          gap: 1
        }
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 13,
          fontWeight: 700
        }
      }, c.score == null ? /*#__PURE__*/React.createElement(EnrichmentGap, {
        what: `${cid} score`,
        audience: audience,
        compact: true
      }) : fmtScore(c.score)), c.delta != null ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 8,
          fontWeight: 600
        }
      }, Number(c.delta) >= 0 ? "▲" : "▼", Math.abs(Number(c.delta)).toFixed(1)) : null));
    }), showPeers ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)",
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        paddingRight: 8
      }
    }, "Peer"), ids.map(cid => {
      const pm = cats[cid].peer_median;
      /* A null median is NOT a zero: banded and printed as 0.0
         it would read as a peer set that scores nothing. It is
         a gap in the cohort benchmark, and it is enrichable. */
      return pm == null ? /*#__PURE__*/React.createElement("div", {
        key: cid,
        className: "hm-cell peer",
        style: {
          minHeight: 30,
          padding: "4px 6px"
        }
      }, /*#__PURE__*/React.createElement(EnrichmentGap, {
        what: `${cid} peer median`,
        audience: audience,
        compact: true
      })) : /*#__PURE__*/React.createElement("div", {
        key: cid,
        className: `hm-cell peer b ${DMA.helpers.maturityClass(pm)}`,
        style: {
          minHeight: 30,
          padding: "4px 6px"
        }
      }, fmtScore(pm));
    })) : null, /*#__PURE__*/React.createElement("div", null), ids.map(cid => {
      const cat = DMA.CATEGORIES.find(c => c.id === cid);
      const label = cat && cat.name && cat.name !== cid ? cat.name : null;
      return /*#__PURE__*/React.createElement("div", {
        key: `l-${cid}`,
        style: {
          fontSize: 9,
          color: "var(--z-muted)",
          textAlign: "center",
          padding: "4px 2px 0",
          lineHeight: 1.3
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "f-mono"
      }, cid), label ? /*#__PURE__*/React.createElement("div", {
        className: "txt-fit-2"
      }, label) : !cat ? /*#__PURE__*/React.createElement("div", {
        className: "txt-fit-2",
        style: {
          color: "var(--z-org)"
        },
        title: `${cid} is not in catalogue ${window.DMA_LIVE && window.DMA_LIVE.catalogue_version || "current"}; the run scored it, so it renders`
      }, "off-catalogue") : null);
    })));
  }), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 10,
      gap: 10,
      flexWrap: "wrap"
    }
  }, [["Activating", 1.5], ["Building", 2.5], ["Competing", 3.5], ["Differentiating", 4.5]].map(([label, s]) => /*#__PURE__*/React.createElement("span", {
    key: label,
    className: "row",
    style: {
      gap: 5,
      fontSize: 10.5
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 12,
      height: 12,
      borderRadius: 3,
      background: DMA.helpers.maturityHex(s)
    }
  }), label))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ H1 · focus areas ══════════════════════════════════════════════ */
function LiveFocusAreas({
  data,
  state,
  audience
}) {
  const areas = data && data.focus_areas || [];
  const [open, setOpen] = useState(null);
  if (!areas.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Focus areas",
    note: "where the assessment concentrates, in the client's own words"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 10
    }
  }, areas.map((fa, i) => {
    const isOpen = open === (fa.fa_id || i);
    const delta = fa.entity_score != null && fa.peer_score != null ? fa.entity_score - fa.peer_score : null;
    return /*#__PURE__*/React.createElement("div", {
      key: fa.fa_id || i,
      className: "card-tile clickable",
      style: {
        padding: 14
      },
      onClick: () => setOpen(isOpen ? null : fa.fa_id || i)
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 10,
        alignItems: "flex-start"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "b f-mono"
    }, fa.fa_id), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        fontWeight: 600,
        flex: 1,
        minWidth: 0,
        lineHeight: 1.4
      }
    }, fa.name), fa.entity_score != null ? /*#__PURE__*/React.createElement(MaturityChip, {
      score: fa.entity_score
    }) : null, fa.peer_score != null ? /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)"
      }
    }, "peer ", fmtScore(fa.peer_score)) : null, delta != null ? /*#__PURE__*/React.createElement(DeltaBadge, {
      delta: delta,
      audience: audience
    }) : null), fa.verbatim_quote ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        fontStyle: "italic",
        marginTop: 8,
        borderLeft: "2px solid var(--z-teal)",
        paddingLeft: 10,
        lineHeight: 1.55
      }
    }, "\u201C", fa.verbatim_quote, "\u201D") : null, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginTop: 8,
        gap: 6,
        flexWrap: "wrap"
      }
    }, fa.source_document ? /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, fa.source_document, fa.source_page ? ` p.${fa.source_page}` : "") : null, /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), fa.currency_status ? /*#__PURE__*/React.createElement("span", {
      className: `b ${fa.currency_status === "CONFIRMED_CURRENT" ? "b-ph1" : "b-org"}`
    }, fa.currency_status.replace(/_/g, " ")) : null), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 10,
        paddingTop: 10,
        borderTop: "1px solid var(--z-sep)"
      }
    }, fa.currency_note ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        marginBottom: 8,
        lineHeight: 1.5
      }
    }, fa.currency_note) : null, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 4,
        flexWrap: "wrap"
      }
    }, (fa.involved_subcap_ids || []).map(id => /*#__PURE__*/React.createElement("span", {
      key: id,
      className: "chip f-mono",
      style: {
        fontSize: 9.5
      }
    }, id)))) : null);
  })), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ H2 · cell evidence ════════════════════════════════════════════
   The grid's drill target. 69 flat rows is a list, not a drilldown, so the
   cells group by category and open on the one the grid was clicked on. */
function LiveCellEvidence({
  data,
  state,
  filter,
  onClearFilter
}) {
  const all = data && data.cells || [];
  const [q, setQ] = useState("");
  const [open, setOpen] = useState({});
  if (!all.length) return null;
  const matches = all.filter(c => {
    const id = c.subcap_id || "";
    if (filter && !String(id).startsWith(filter)) return false;
    if (q && !JSON.stringify(c).toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });
  const groups = {};
  matches.forEach(c => {
    const cat = String(c.subcap_id || "?").slice(0, 4);
    (groups[cat] = groups[cat] || []).push(c);
  });
  const cats = Object.keys(groups).sort();
  // A filter or a search is itself the intent to look inside.
  const forced = !!(filter || q);
  const catName = cid => {
    const c = DMA.CATEGORIES.find(x => x.id === cid);
    return c && c.name && c.name !== cid ? c.name : null;
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Cell evidence",
    note: `${matches.length} of ${all.length} evidenced cells across ${cats.length} categor${cats.length === 1 ? "y" : "ies"}`,
    right: /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 8
      }
    }, filter ? /*#__PURE__*/React.createElement("span", {
      className: "chip purple",
      style: {
        cursor: "pointer"
      },
      onClick: onClearFilter,
      title: "clear the grid filter"
    }, filter, " \u2715") : null, /*#__PURE__*/React.createElement("input", {
      className: "inp",
      placeholder: "Filter cells\u2026",
      value: q,
      onChange: e => setQ(e.target.value),
      style: {
        fontSize: 11,
        padding: "4px 8px",
        width: 160
      }
    }))
  }), cats.length ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 6
    }
  }, cats.map(cid => {
    const rows = groups[cid];
    const cited = rows.reduce((a, c) => a + (c.grounded_on != null ? Number(c.grounded_on) : (c.e_ids || []).length), 0);
    const thin = rows.filter(c => (c.grounded_on != null ? Number(c.grounded_on) : (c.e_ids || []).length) === 0).length;
    const isOpen = forced || !!open[cid];
    return /*#__PURE__*/React.createElement("div", {
      key: cid,
      className: "card-tile",
      style: {
        padding: 0,
        overflow: "hidden"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row clickable",
      style: {
        gap: 8,
        padding: "10px 12px",
        cursor: "pointer"
      },
      onClick: () => setOpen(o => ({
        ...o,
        [cid]: !o[cid]
      }))
    }, /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-d" : "chevron-r",
      size: 11
    }), /*#__PURE__*/React.createElement("span", {
      className: "b f-mono"
    }, cid), catName(cid) ? /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 12,
        fontWeight: 600
      }
    }, catName(cid)) : null, /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)"
      }
    }, rows.length, " cell", rows.length === 1 ? "" : "s", " \xB7 ", cited, " citation", cited === 1 ? "" : "s"), thin ? /*#__PURE__*/React.createElement("span", {
      className: "b b-org",
      title: "cells with no citation on this run"
    }, thin, " uncited") : null), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        borderTop: "1px solid var(--z-sep)"
      }
    }, rows.map((c, i) => {
      const n = c.grounded_on != null ? Number(c.grounded_on) : (c.e_ids || []).length;
      return /*#__PURE__*/React.createElement("div", {
        key: c.subcap_id || i,
        style: {
          padding: "8px 12px",
          borderBottom: i === rows.length - 1 ? 0 : "1px solid var(--z-sep)"
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          gap: 8
        }
      }, /*#__PURE__*/React.createElement("span", {
        className: "f-mono",
        style: {
          fontSize: 11,
          minWidth: 78
        }
      }, c.subcap_id), /*#__PURE__*/React.createElement("span", {
        className: `b ${n === 0 ? "b-org" : ""}`,
        title: "grounded_on - the length of the citation list, computed by the database"
      }, n, " cited"), /*#__PURE__*/React.createElement("span", {
        className: "spacer"
      }), (c.e_ids || []).slice(0, 8).map(e => /*#__PURE__*/React.createElement("span", {
        key: e,
        className: "chip f-mono",
        style: {
          fontSize: 9
        }
      }, e)), (c.e_ids || []).length > 8 ? /*#__PURE__*/React.createElement("span", {
        className: "muted",
        style: {
          fontSize: 9.5
        }
      }, "+", c.e_ids.length - 8) : null), c.synthesis ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 11.5,
          color: "var(--z-body)",
          marginTop: 5,
          lineHeight: 1.5
        }
      }, c.synthesis) : null);
    })) : null);
  })) : /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-muted)"
    }
  }, "No evidenced cell matches this filter."), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ H5 · thin-evidence alerts ═════════════════════════════════════ */
function LiveAlerts({
  data,
  state
}) {
  const alerts = data && data.alerts || [];
  if (!alerts.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Thin-evidence alerts",
    right: /*#__PURE__*/React.createElement("span", {
      className: "b b-org"
    }, alerts.length, " open")
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 6
    }
  }, alerts.map((a, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "card-tile",
    style: {
      padding: "10px 12px",
      borderLeft: "3px solid var(--z-org)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8
    }
  }, a.subcap_id ? /*#__PURE__*/React.createElement("span", {
    className: "f-mono b"
  }, a.subcap_id) : null, a.severity ? /*#__PURE__*/React.createElement("span", {
    className: "b b-org"
  }, a.severity) : null, a.state ? /*#__PURE__*/React.createElement("span", {
    className: "b"
  }, a.state.replace(/_/g, " ")) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)"
    }
  }, a.evidence_count != null ? `${a.evidence_count} evidence item${a.evidence_count === 1 ? "" : "s"}` : "", a.score != null ? ` · scored ${fmtScore(a.score)}` : " · unscored", a.runs_open ? ` · open ${a.runs_open} run${a.runs_open === 1 ? "" : "s"}` : "")), a.justification ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      marginTop: 6,
      lineHeight: 1.55
    }
  }, a.justification) : null, a.closure_condition ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-teal)",
      marginTop: 6
    }
  }, "Closes on: ", a.closure_condition) : null, (a.sources_searched || []).length ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      marginTop: 6,
      lineHeight: 1.5
    }
  }, "Searched: ", a.sources_searched.join(" · ")) : null))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ H6 · caps applied + safeguard gates ═══════════════════════════
   Two arrays, never one blob (charter correction): caps the assessment
   applied, and SG results — a failing gate DISCLOSES and still promotes,
   so it must render, with its plain label, not be hidden. */
function LiveSafeguards({
  data,
  state
}) {
  const caps = data && data.caps || [];
  const gates = data && data.gates || [];
  if (!caps.length && !gates.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Caps & safeguard gates",
    note: "caps the assessment applied \xB7 gate results disclosed with the run"
  }), caps.length ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: gates.length ? 14 : 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      fontSize: 9.5,
      marginBottom: 6
    }
  }, "Caps applied"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 6
    }
  }, caps.map((c, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "card-tile",
    style: {
      padding: "10px 12px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "lock",
    size: 11
  }), /*#__PURE__*/React.createElement("span", {
    className: "b f-mono"
  }, c.cap_id), c.kind ? /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, c.kind) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), (c.affected_categories || []).map(cat => /*#__PURE__*/React.createElement("span", {
    key: cat,
    className: "chip f-mono",
    style: {
      fontSize: 9.5
    }
  }, cat)), c.ceiling != null ? /*#__PURE__*/React.createElement("span", {
    className: `b ${bandClass(c.ceiling)}`
  }, "ceiling ", isFinite(Number(c.ceiling)) ? fmtScore(c.ceiling) : c.ceiling) : null), c.rationale ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      marginTop: 5,
      lineHeight: 1.5
    }
  }, c.rationale) : null, (c.e_ids || []).length ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 5,
      gap: 4,
      flexWrap: "wrap"
    }
  }, c.e_ids.map(e => /*#__PURE__*/React.createElement("span", {
    key: e,
    className: "chip f-mono",
    style: {
      fontSize: 9
    }
  }, e))) : null)))) : null, gates.length ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      fontSize: 9.5,
      marginBottom: 6
    }
  }, "Safeguard gates"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 6
    }
  }, gates.map((g, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "row",
    style: {
      gap: 8,
      fontSize: 11.5,
      borderBottom: "1px solid var(--z-sep)",
      paddingBottom: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "f-mono b"
  }, g.gate_id || g.gate), /*#__PURE__*/React.createElement("span", {
    className: `b ${g.result === "PASS" ? "b-ph1" : g.result === "NOT_RUN" ? "" : "b-org"}`
  }, g.result), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, g.plain_label), g.reason ? /*#__PURE__*/React.createElement("span", {
    className: "muted",
    style: {
      fontSize: 10.5
    }
  }, g.reason) : null)))) : null, /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ H7 · evidence age ═════════════════════════════════════════════ */
/* The evidence ladder's own vocabulary (12/24/36/48 months). The DB
   generates band and status; nothing here recomputes them — this map only
   chooses a tone for a value that already arrived. */
const AGE_BANDS = ["FRESH", "CURRENT", "AGING", "DATED", "STALE", "UNDATED"];
const AGE_TONE = {
  FRESH: "b-ph1",
  CURRENT: "b-ph1",
  AGING: "",
  DATED: "b-org",
  STALE: "b-org",
  UNDATED: "b-org"
};
function LiveEvidenceAge({
  data,
  state,
  audience
}) {
  const rows = data && data.rows || [];
  const [all, setAll] = useState(false);
  if (!rows.length) return null;
  const counts = {};
  rows.forEach(r => {
    const b = r.status || r.band || "UNDATED";
    counts[b] = (counts[b] || 0) + 1;
  });
  const shown = all ? rows : rows.slice(0, 10);
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Evidence age",
    note: `${rows.length} evidence items on the 12/24/36/48-month ladder`
  }), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 6,
      marginBottom: 12,
      flexWrap: "wrap"
    }
  }, AGE_BANDS.filter(b => counts[b]).map(b => /*#__PURE__*/React.createElement("span", {
    key: b,
    className: `b ${AGE_TONE[b] || ""}`
  }, b, " ", counts[b])), Object.keys(counts).filter(b => !AGE_BANDS.includes(b)).map(b => /*#__PURE__*/React.createElement("span", {
    key: b,
    className: "b"
  }, b, " ", counts[b]))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 4
    }
  }, shown.map((r, i) => /*#__PURE__*/React.createElement("div", {
    key: r.e_id || i,
    className: "row",
    style: {
      gap: 8,
      fontSize: 11,
      borderBottom: "1px solid var(--z-sep)",
      paddingBottom: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "f-mono",
    style: {
      minWidth: 88
    }
  }, r.e_id), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      minWidth: 0,
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    },
    title: r.title || ""
  }, r.title || /*#__PURE__*/React.createElement(EnrichmentGap, {
    what: `Title of ${r.e_id || "this evidence item"}`,
    audience: audience,
    compact: true
  })), r.source_domain ? /*#__PURE__*/React.createElement("span", {
    className: "muted",
    style: {
      minWidth: 110,
      fontSize: 10,
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, r.source_domain) : null, /*#__PURE__*/React.createElement("span", {
    className: "muted f-mono",
    style: {
      minWidth: 76,
      textAlign: "right"
    }
  }, r.published_or_asof || "undated"), r.age_months != null ? /*#__PURE__*/React.createElement("span", {
    className: "muted f-mono",
    style: {
      minWidth: 48,
      textAlign: "right",
      fontSize: 10
    },
    title: "months between publication and the run's reference date, computed by the database"
  }, r.age_months, "mo") : null, r.identity_ok === false ? /*#__PURE__*/React.createElement("span", {
    className: "b b-org",
    title: "the cited domain did not resolve to this entity"
  }, "IDENTITY") : null, /*#__PURE__*/React.createElement("span", {
    className: `b ${AGE_TONE[r.status || r.band] || ""}`
  }, r.status || r.band || "UNDATED")))), rows.length > 10 ? /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    style: {
      marginTop: 8
    },
    onClick: () => setAll(o => !o)
  }, all ? "Show fewer" : `Show all ${rows.length}`) : null, /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ H8 · cohort patterns (entity ids always stripped server-side) ══ */
function LiveCohorts({
  data,
  state,
  audience
}) {
  const patterns = data && data.patterns || [];
  const insufficient = data && data.insufficient_cohorts || [];
  if (!patterns.length && !insufficient.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Cross-entity patterns",
    note: data.threshold_pct != null ? `shares at or above ${fmtPctVal(data.threshold_pct, 0)} of the cohort` : null
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 5
    }
  }, patterns.map((p, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "row",
    style: {
      gap: 8,
      fontSize: 11.5
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "f-mono",
    style: {
      minWidth: 70
    }
  }, p.category_id || p.subcap_id), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "prog"
  }, /*#__PURE__*/React.createElement("div", {
    className: "prog-fill",
    style: {
      width: `${Math.min(100, Number(p.share_pct) || 0)}%`,
      background: "var(--z-dpur)"
    }
  }))), /*#__PURE__*/React.createElement("span", {
    className: "f-mono",
    style: {
      minWidth: 52,
      textAlign: "right"
    }
  }, p.share_pct == null ? /*#__PURE__*/React.createElement(EnrichmentGap, {
    what: "Cohort share",
    audience: audience,
    compact: true
  }) : fmtPctVal(p.share_pct, 0))))), insufficient.length ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 10
    }
  }, "Cohorts too small to report: ", insufficient.map(c => `${c.sub_vertical} (n=${c.entity_count})`).join(", ")) : null, /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ D4 · insight cards ════════════════════════════════════════════ */
function LiveInsights({
  data,
  state
}) {
  const cards = data && data.cards || [];
  const [open, setOpen] = useState(null);
  if (!cards.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Insight cards",
    note: `${cards.length} promoted`
  }), data.narrative_thread ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-body)",
      lineHeight: 1.55,
      marginBottom: 12
    }
  }, data.narrative_thread) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 10
    }
  }, cards.map((c, i) => {
    const isOpen = open === (c.ic_id || i);
    return /*#__PURE__*/React.createElement("div", {
      key: c.ic_id || i,
      className: "card-tile clickable",
      style: {
        padding: 14
      },
      onClick: () => setOpen(isOpen ? null : c.ic_id || i)
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 8,
        alignItems: "flex-start"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "b f-mono"
    }, c.ic_id), c.pillar_id ? /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, c.pillar_id) : null, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        fontWeight: 600,
        flex: 1,
        minWidth: 0,
        lineHeight: 1.4
      }
    }, c.title), c.severity ? /*#__PURE__*/React.createElement("span", {
      className: "b b-org",
      title: c.severity_rationale || ""
    }, c.severity) : null, /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-d" : "chevron-r",
      size: 12
    })), c.so_what_text ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        marginTop: 6,
        lineHeight: 1.55
      }
    }, c.so_what_text) : null, isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 10,
        display: "grid",
        gap: 8
      }
    }, [["What", c.what_text], ["Why", c.why_text], ["Alternative explanation", c.alternative_explanation], ["Severity rationale", c.severity_rationale], ["Affects", c.affects], ["Validation question", c.validation_question]].map(([k, v]) => v ? /*#__PURE__*/React.createElement("div", {
      key: k
    }, /*#__PURE__*/React.createElement("div", {
      className: "eyebrow",
      style: {
        fontSize: 9.5
      }
    }, k), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        lineHeight: 1.55
      }
    }, v)) : null), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 4,
        flexWrap: "wrap"
      }
    }, c.linked_subcap_id ? /*#__PURE__*/React.createElement("span", {
      className: "chip f-mono",
      style: {
        fontSize: 9.5
      }
    }, c.linked_subcap_id) : null, c.linked_rec_id ? /*#__PURE__*/React.createElement("span", {
      className: "chip purple",
      style: {
        fontSize: 9.5
      }
    }, "\u2192 ", c.linked_rec_id) : null, (c.supporting_e_ids || []).map(e => /*#__PURE__*/React.createElement("span", {
      key: e,
      className: "chip f-mono",
      style: {
        fontSize: 9
      }
    }, e)), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement(ClaimChip, {
      label: c.claim_label,
      confidence: c.confidence
    })), /*#__PURE__*/React.createElement(RLayer, {
      r: c.r_layer
    })) : null);
  })), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ D2 · platform story ═══════════════════════════════════════════ */
function LivePlatformStory({
  data,
  state
}) {
  const platforms = data && data.platforms || [];
  const discarded = data && data.discarded || [];
  if (!platforms.length && !discarded.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Platform story",
    note: "what the estate needs, and what was ruled out"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 10
    }
  }, platforms.map((p, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "card-tile",
    style: {
      padding: 14
    }
  }, (p.gaps || []).length ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      fontSize: 9.5,
      marginBottom: 6
    }
  }, "Gaps this platform closes \xB7 ", p.gaps.length), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 6
    }
  }, p.gaps.map((g, j) => /*#__PURE__*/React.createElement("div", {
    key: j,
    className: "card-tile",
    style: {
      padding: "9px 11px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8
    }
  }, g.subcap_id ? /*#__PURE__*/React.createElement("span", {
    className: "b f-mono"
  }, g.subcap_id) : null, g.pillar ? /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, g.pillar) : null, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      fontWeight: 600,
      flex: 1,
      minWidth: 0
    }
  }, asText(g.name)), g.current_score != null ? /*#__PURE__*/React.createElement(MaturityChip, {
    score: g.current_score
  }) : null, g.peer_score != null ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)"
    }
  }, "peer ", fmtScore(g.peer_score)) : g.peer_basis ? /*#__PURE__*/React.createElement("span", {
    className: "b",
    title: asText(g.peer_note) || ""
  }, String(g.peer_basis).replace(/_/g, " ")) : null), g.catalogue_path ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      marginTop: 4
    }
  }, asText(g.catalogue_path)) : null, asText(g.gap) ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      marginTop: 4,
      lineHeight: 1.5
    }
  }, asText(g.gap)) : null, (g.e_ids || []).length ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 4,
      gap: 4,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), g.e_ids.map(e => /*#__PURE__*/React.createElement("span", {
    key: e,
    className: "chip f-mono",
    style: {
      fontSize: 9
    }
  }, e))) : null)))) : null, p.story_md ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-body)",
      lineHeight: 1.65,
      whiteSpace: "pre-wrap"
    }
  }, p.story_md) : null))), discarded.length ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14,
      paddingTop: 12,
      borderTop: "1px solid var(--z-sep)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      fontSize: 9.5,
      marginBottom: 6
    }
  }, "Ruled out"), discarded.map((x, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "row",
    style: {
      fontSize: 11.5,
      marginBottom: 5,
      gap: 8,
      alignItems: "flex-start"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 500,
      minWidth: 190
    }
  }, asText(x.platform) || asText(x.name)), x.relevance != null ? /*#__PURE__*/React.createElement("span", {
    className: "b f-mono",
    title: "relevance to the assessed gaps"
  }, fmtNum(x.relevance, {
    decimals: 2
  })) : null, /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-muted)",
      flex: 1,
      minWidth: 0,
      lineHeight: 1.5
    }
  }, asText(x.reason))))) : null, /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ D2 · recommendations ══════════════════════════════════════════ */
function LiveRecommendations({
  data,
  state,
  audience
}) {
  const recs = data && data.recommendations || [];
  const [open, setOpen] = useState(null);
  if (!recs.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Recommendations",
    note: `${recs.length} authored`
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 8
    }
  }, recs.map((r, i) => {
    const isOpen = open === (r.rec_id || i);
    return /*#__PURE__*/React.createElement("div", {
      key: r.rec_id || i,
      className: "card-tile clickable",
      style: {
        padding: "12px 14px"
      },
      onClick: () => setOpen(isOpen ? null : r.rec_id || i)
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 8,
        alignItems: "flex-start"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "b f-mono"
    }, r.rec_id), r.phase ? /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, r.phase) : null, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 13,
        fontWeight: 600,
        flex: 1,
        minWidth: 0,
        lineHeight: 1.4
      }
    }, r.title), r.effort_band ? /*#__PURE__*/React.createElement("span", {
      className: "b"
    }, r.effort_band) : null, (r.dma_impact || []).length ? /*#__PURE__*/React.createElement("span", {
      className: "b b-ph1",
      title: "cells this recommendation moves"
    }, r.dma_impact.length, " cell", r.dma_impact.length === 1 ? "" : "s") : null, /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-d" : "chevron-r",
      size: 12
    })), r.l3_area || r.l4_feature ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)",
        marginTop: 4
      }
    }, [r.l3_area, r.l4_feature].filter(Boolean).join(" · ")) : null, isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 10,
        display: "grid",
        gap: 8
      }
    }, [["Root cause", r.root_cause], ["Cost of inaction", r.cost_of_inaction], ["Why in this order", r.sequencing_reason], ["Depends on", (r.dependencies || []).map(asText).filter(Boolean).join(" · ")]].map(([k, v]) => v ? /*#__PURE__*/React.createElement("div", {
      key: k
    }, /*#__PURE__*/React.createElement("div", {
      className: "eyebrow",
      style: {
        fontSize: 9.5
      }
    }, k), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        lineHeight: 1.55
      }
    }, v)) : null), (r.dma_impact || []).length ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "eyebrow",
      style: {
        fontSize: 9.5
      }
    }, "Projected movement"), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gap: 3
      }
    }, r.dma_impact.map((c, j) => /*#__PURE__*/React.createElement("div", {
      key: j,
      className: "row",
      style: {
        gap: 6,
        fontSize: 10.5
      },
      title: asText(c.target_basis) || ""
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip f-mono",
      style: {
        fontSize: 9
      }
    }, c.subcap_id), /*#__PURE__*/React.createElement("span", {
      style: {
        flex: 1,
        minWidth: 0
      }
    }, asText(c.name)), /*#__PURE__*/React.createElement("span", {
      className: "f-mono"
    }, c.current == null ? /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: `${c.subcap_id || "Cell"} current score`,
      audience: audience,
      compact: true
    }) : fmtScore(c.current)), /*#__PURE__*/React.createElement(Icon, {
      name: "chevron-r",
      size: 9
    }), /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        fontWeight: 600
      }
    }, c.target == null ? /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: `${c.subcap_id || "Cell"} target score`,
      audience: audience,
      compact: true
    }) : fmtScore(c.target)), c.delta != null ? /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        minWidth: 34,
        textAlign: "right",
        color: "var(--z-mid)"
      }
    }, "+", fmtNum(c.delta, {
      decimals: 2
    })) : null))), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        color: "var(--z-muted)",
        marginTop: 4
      }
    }, "projections from the assessment's stated uplift, not measurements")) : null, (r.prerequisites || []).length ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "eyebrow",
      style: {
        fontSize: 9.5
      }
    }, "Prerequisites"), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gap: 4
      }
    }, r.prerequisites.map((q, j) => /*#__PURE__*/React.createElement("div", {
      key: j,
      className: "row",
      style: {
        gap: 6,
        fontSize: 11
      }
    }, q.verdict ? /*#__PURE__*/React.createElement("span", {
      className: `b ${q.verdict === "MET" ? "b-ph1" : "b-org"}`
    }, q.verdict) : null, q.cell ? /*#__PURE__*/React.createElement("span", {
      className: "chip f-mono",
      style: {
        fontSize: 9
      }
    }, q.cell) : null, /*#__PURE__*/React.createElement("span", {
      style: {
        flex: 1,
        minWidth: 0,
        lineHeight: 1.45
      }
    }, asText(q.condition) || (q.minimum != null ? `at or above ${fmtScore(q.minimum)}` : ""), q.current != null ? /*#__PURE__*/React.createElement("span", {
      className: "muted"
    }, " \u2014 currently ", fmtScore(q.current)) : null, asText(q.note) ? /*#__PURE__*/React.createElement("span", {
      className: "muted"
    }, " ", asText(q.note)) : null), q.basis ? /*#__PURE__*/React.createElement("span", {
      className: "b"
    }, q.basis) : null)))) : null, r.validation_gate && typeof r.validation_gate === "object" ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "eyebrow",
      style: {
        fontSize: 9.5
      }
    }, "Validation gate"), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 6,
        fontSize: 11,
        marginBottom: 4
      }
    }, r.validation_gate.verdict ? /*#__PURE__*/React.createElement("span", {
      className: `b ${r.validation_gate.verdict === "MET" ? "b-ph1" : "b-org"}`
    }, r.validation_gate.verdict) : null, /*#__PURE__*/React.createElement("span", {
      className: "f-mono"
    }, asText(r.validation_gate.threshold)), r.validation_gate.cell ? /*#__PURE__*/React.createElement("span", {
      className: "chip f-mono",
      style: {
        fontSize: 9
      }
    }, r.validation_gate.cell) : null), (r.validation_gate.backing_cells || []).length ? /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 5,
        flexWrap: "wrap"
      }
    }, r.validation_gate.backing_cells.map((b, j) => /*#__PURE__*/React.createElement("span", {
      key: j,
      className: "chip f-mono",
      style: {
        fontSize: 9
      },
      title: asText(b.name) || ""
    }, b.subcap_id, " ", b.score == null ? /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: `${b.subcap_id || "Backing cell"} score`,
      audience: audience,
      compact: true
    }) : fmtScore(b.score)))) : null, asText(r.validation_gate.grain_note) ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        color: "var(--z-muted)",
        marginTop: 4,
        lineHeight: 1.45
      }
    }, asText(r.validation_gate.grain_note)) : null) : null, r.kpi_triple && typeof r.kpi_triple === "object" ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "eyebrow",
      style: {
        fontSize: 9.5
      }
    }, "KPI", r.kpi_triple.baseline_as_of ? ` · baseline as of ${r.kpi_triple.baseline_as_of}` : ""), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "repeat(3, minmax(0,1fr))",
        gap: 8
      }
    }, [["Metric", r.kpi_triple.metric], ["Baseline", r.kpi_triple.baseline], ["Target", r.kpi_triple.target]].map(([k, v]) => /*#__PURE__*/React.createElement("div", {
      key: k
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9,
        color: "var(--z-muted)",
        textTransform: "uppercase",
        letterSpacing: ".06em"
      }
    }, k), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        lineHeight: 1.45
      }
    }, asText(v) || /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: `KPI ${k.toLowerCase()}`,
      audience: audience,
      compact: true
    })))))) : null, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 4,
        flexWrap: "wrap"
      }
    }, (r.evidence_ids || []).map(e => /*#__PURE__*/React.createElement("span", {
      key: e,
      className: "chip f-mono",
      style: {
        fontSize: 9
      }
    }, e)), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement(ClaimChip, {
      label: r.claim_label
    })), /*#__PURE__*/React.createElement(RLayer, {
      r: r.r_layer
    })) : null);
  })), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ D2 · conversation starters ════════════════════════════════════ */
function LiveStarters({
  data,
  state
}) {
  const starters = data && data.starters || [];
  if (!starters.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Conversation starters",
    note: "questions the evidence earns the right to ask"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 8
    }
  }, starters.slice().sort((a, b) => (a.rank || 99) - (b.rank || 99)).map((st, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "card-tile",
    style: {
      padding: "12px 14px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8,
      marginBottom: 5
    }
  }, st.rank != null ? /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, st.rank, ".") : null, st.opens_on ? /*#__PURE__*/React.createElement("span", {
    className: "b"
  }, st.opens_on) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), st.named_gap_subcap_id ? /*#__PURE__*/React.createElement("span", {
    className: "chip f-mono",
    style: {
      fontSize: 9.5
    }
  }, st.named_gap_subcap_id) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      fontWeight: 500,
      lineHeight: 1.5
    }
  }, st.text), st.followup_question ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      marginTop: 6,
      lineHeight: 1.5
    }
  }, "Follow up: ", st.followup_question) : null, st.peer_reference ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      marginTop: 5,
      lineHeight: 1.5
    }
  }, "Peer: ", st.peer_reference) : null, st.their_system_reference ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      marginTop: 3,
      lineHeight: 1.5
    }
  }, "Their estate: ", st.their_system_reference) : null, (st.e_ids || []).length ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 6,
      gap: 4,
      flexWrap: "wrap"
    }
  }, st.e_ids.map(e => /*#__PURE__*/React.createElement("span", {
    key: e,
    className: "chip f-mono",
    style: {
      fontSize: 9
    }
  }, e))) : null))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ D2 · roadmap ══════════════════════════════════════════════════ */
function LiveRoadmap({
  data,
  state
}) {
  const phases = data && data.phases || [];
  if (!phases.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Roadmap",
    note: `${phases.length} phases, in sequence`
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: `repeat(${phases.length}, minmax(0,1fr))`,
      gap: 10
    }
  }, phases.map((p, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "card-tile",
    style: {
      padding: 14,
      borderTop: "3px solid var(--z-teal)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, i + 1), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12.5,
      fontWeight: 600
    }
  }, p.phase)), p.horizon ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginBottom: 6
    }
  }, p.horizon) : null, p.rationale ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      lineHeight: 1.5
    }
  }, p.rationale) : null, (p.depends_on || []).length ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 6
    }
  }, "after ", p.depends_on.join(" · ")) : null, (p.rec_ids || []).length ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 8,
      gap: 4,
      flexWrap: "wrap"
    }
  }, p.rec_ids.map(id => /*#__PURE__*/React.createElement("span", {
    key: id,
    className: "chip f-mono",
    style: {
      fontSize: 9
    }
  }, id))) : null))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ D2 · stair-step ladder ════════════════════════════════════════ */
function LiveStairstep({
  data,
  state
}) {
  const ladder = data && data.ladder || {};
  const steps = ladder.steps || [];
  if (!steps.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Stair-step",
    note: ladder.theme || null
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 8
    }
  }, steps.map((st, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "card-tile",
    style: {
      padding: "12px 14px",
      marginLeft: i * 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, st.step_level != null ? st.step_level : i + 1), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12.5,
      fontWeight: 600,
      flex: 1,
      minWidth: 0
    }
  }, st.label), st.effort_band ? /*#__PURE__*/React.createElement("span", {
    className: "b"
  }, st.effort_band) : null, st.current_position ? /*#__PURE__*/React.createElement("span", {
    className: "b b-ph1",
    title: "the estate is here today"
  }, "YOU ARE HERE") : null), st.entry_condition ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      marginTop: 5,
      lineHeight: 1.5
    }
  }, "Entry: ", st.entry_condition) : null, st.unlocks ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-teal)",
      marginTop: 5
    }
  }, "Unlocks: ", st.unlocks) : null, (st.blocking_findings || []).length ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 5,
      gap: 4,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-org)"
    }
  }, "Blocked by:"), st.blocking_findings.map((f, i) => {
    const id = findingChipId(f);
    return /*#__PURE__*/React.createElement("span", {
      key: `${id}-${i}`,
      className: "chip f-mono",
      style: {
        fontSize: 9
      }
    }, id);
  })) : null, (st.covered_subcap_ids || []).length ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 9.5,
      color: "var(--z-muted)",
      marginTop: 5
    }
  }, st.covered_subcap_ids.length, " cells covered") : null))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ D5 · timeline ═════════════════════════════════════════════════ */
function LiveTimeline({
  data,
  state
}) {
  const events = data && data.events || [];
  if (!events.length && !data.storyline) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Timeline",
    note: data.arc_shape ? data.arc_shape.replace(/_/g, " ") : null,
    right: data.verified_sparse ? /*#__PURE__*/React.createElement("span", {
      className: "b b-org"
    }, "SPARSE") : null
  }), data.storyline ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-body)",
      lineHeight: 1.6,
      marginBottom: 14
    }
  }, data.storyline) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      borderLeft: "2px solid var(--z-sep)",
      paddingLeft: 16
    }
  }, events.map((e, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      position: "relative",
      paddingBottom: 14
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      left: -22,
      top: 4,
      width: 8,
      height: 8,
      borderRadius: 4,
      background: e.event_date ? "var(--z-teal)" : "var(--z-org)"
    }
  }), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b f-mono"
  }, e.event_date || "undated"), e.kind ? /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, e.kind) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), (window.splitMaturityEffect ? window.splitMaturityEffect(e.maturity_effect).token : null) ? /*#__PURE__*/React.createElement("span", {
    className: "b b-ph1",
    title: "effect on assessed maturity"
  }, window.splitMaturityEffect(e.maturity_effect).token.replace(/_/g, " ")) : null, /*#__PURE__*/React.createElement(ClaimChip, {
    label: e.claim_label
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      fontWeight: 600,
      marginTop: 4,
      lineHeight: 1.45
    }
  }, e.title), e.body ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      marginTop: 4,
      lineHeight: 1.5
    }
  }, e.body) : null, (window.splitMaturityEffect ? window.splitMaturityEffect(e.maturity_effect).reason : null) ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-dark)",
      marginTop: 5,
      paddingLeft: 9,
      borderLeft: "2px solid var(--z-lav)",
      lineHeight: 1.5
    }
  }, window.splitMaturityEffect(e.maturity_effect).reason) : null, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 5,
      gap: 4,
      flexWrap: "wrap"
    }
  }, (e.capability_ids || []).map(id => /*#__PURE__*/React.createElement("span", {
    key: id,
    className: "chip f-mono",
    style: {
      fontSize: 9
    }
  }, id)), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), (e.e_ids || []).map(x => /*#__PURE__*/React.createElement("span", {
    key: x,
    className: "chip f-mono",
    style: {
      fontSize: 9
    }
  }, x)))))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ D5 · issue register ═══════════════════════════════════════════ */
function LiveIssueRegister({
  data,
  state
}) {
  const issues = data && data.issues || [];
  if (!issues.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Issue register",
    note: `${issues.length} recorded`
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 6
    }
  }, issues.map((x, i) => /*#__PURE__*/React.createElement("div", {
    key: x.issue_id || i,
    className: "card-tile",
    style: {
      padding: "10px 12px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8
    }
  }, x.issue_id ? /*#__PURE__*/React.createElement("span", {
    className: "b f-mono"
  }, x.issue_id) : null, x.severity ? /*#__PURE__*/React.createElement("span", {
    className: "b b-org"
  }, x.severity) : null, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      fontWeight: 500,
      flex: 1,
      minWidth: 0
    }
  }, x.title), x.status ? /*#__PURE__*/React.createElement("span", {
    className: "b"
  }, x.status) : null, x.opened_on ? /*#__PURE__*/React.createElement("span", {
    className: "muted f-mono",
    style: {
      fontSize: 10
    },
    title: "opened"
  }, x.opened_on) : null, x.resolved_on ? /*#__PURE__*/React.createElement("span", {
    className: "b b-ph1 f-mono",
    style: {
      fontSize: 9
    },
    title: "resolved"
  }, "\u2192 ", x.resolved_on) : null), x.rationale ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      marginTop: 5,
      lineHeight: 1.5
    }
  }, x.rationale) : null, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 6,
      gap: 4,
      flexWrap: "wrap"
    }
  }, (x.linked_subcap_ids || []).length ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, "Caps:") : null, (x.linked_subcap_ids || []).map(id => /*#__PURE__*/React.createElement("span", {
    key: id,
    className: "chip f-mono",
    style: {
      fontSize: 9
    }
  }, id)), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), (x.e_ids || []).map(e => /*#__PURE__*/React.createElement("span", {
    key: e,
    className: "chip f-mono",
    style: {
      fontSize: 9
    }
  }, e)))))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ D5 · regulatory standing ══════════════════════════════════════ */
function LiveRegulatory({
  data,
  state,
  audience
}) {
  if (!data) return null;
  const enf = data.enforcement_actions || [];
  const abs = data.absence_of_enforcement || null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Regulatory standing"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: 18
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Row, {
    k: "Primary regulator",
    v: data.primary_regulator || /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: "Primary regulator",
      audience: audience
    })
  }), /*#__PURE__*/React.createElement(Row, {
    k: "Licence type",
    v: data.license_type || /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: "Licence type",
      audience: audience
    })
  }), /*#__PURE__*/React.createElement(Row, {
    k: "Charter date",
    v: data.charter_date || /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: "Charter date",
      audience: audience
    })
  }), /*#__PURE__*/React.createElement(Row, {
    k: "Additional",
    v: (data.additional_regulators || []).join(" · ") || /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: "Additional regulators",
      audience: audience
    })
  }), /*#__PURE__*/React.createElement(Row, {
    k: "Jurisdictions",
    v: (data.jurisdictions || []).join(" · ") || /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: "Jurisdictions",
      audience: audience
    })
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      fontSize: 9.5,
      marginBottom: 6
    }
  }, "Enforcement"), enf.length ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 6
    }
  }, enf.map((a, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "card-tile",
    style: {
      padding: "8px 10px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-org"
  }, a.kind || "ACTION"), a.dated_on ? /*#__PURE__*/React.createElement("span", {
    className: "b f-mono"
  }, a.dated_on) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      marginTop: 4
    }
  }, a.detail || a.title)))) : abs ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 6,
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `b ${abs.verified ? "b-ph1" : "b-org"}`
  }, abs.verified ? "NONE FOUND · VERIFIED" : "NOT VERIFIED")), (abs.sources_searched || []).length ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      lineHeight: 1.5
    }
  }, "Searched: ", abs.sources_searched.join(" · ")) : null) : /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-muted)"
    }
  }, "Not established."))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ D5 · acquisitions ═════════════════════════════════════════════ */
function LiveAcquisitions({
  data,
  state,
  audience
}) {
  const rows = data && data.rows || [];
  if (!rows.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Acquisitions & mergers",
    note: `${rows.length} recorded`
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 6
    }
  }, rows.map((r, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "card-tile",
    style: {
      padding: "10px 12px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12.5,
      fontWeight: 600
    }
  }, r.target_name), r.kind ? /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, r.kind) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), r.closed_on ? /*#__PURE__*/React.createElement("span", {
    className: "b f-mono"
  }, r.closed_on) : null, r.status ? /*#__PURE__*/React.createElement("span", {
    className: "b"
  }, r.status) : null, (window.splitMaturityEffect ? window.splitMaturityEffect(r.maturity_effect).token : null) ? /*#__PURE__*/React.createElement("span", {
    className: "b b-ph1",
    title: "effect on assessed maturity"
  }, window.splitMaturityEffect(r.maturity_effect).token.replace(/_/g, " ")) : null), r.scale_metrics && typeof r.scale_metrics === "object" ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 10,
      marginTop: 5,
      flexWrap: "wrap"
    }
  }, Object.keys(r.scale_metrics).map(k => /*#__PURE__*/React.createElement("span", {
    key: k,
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)"
    }
  }, k.replace(/_/g, " "), " ", /*#__PURE__*/React.createElement("b", {
    style: {
      color: "var(--z-dark)"
    }
  }, fmtNum(r.scale_metrics[k]) || asText(r.scale_metrics[k]) || /*#__PURE__*/React.createElement(EnrichmentGap, {
    what: `${r.target_name || "Target"} ${k.replace(/_/g, " ")}`,
    audience: audience,
    compact: true
  }))))) : null, r.integration_target ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      marginTop: 5
    }
  }, "Lands on: ", r.integration_target) : null, r.effect_note ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      marginTop: 5,
      lineHeight: 1.5
    }
  }, r.effect_note) : null, (r.affected_subcap_ids || []).length ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 6,
      gap: 4,
      flexWrap: "wrap"
    }
  }, r.affected_subcap_ids.map(id => /*#__PURE__*/React.createElement("span", {
    key: id,
    className: "chip f-mono",
    style: {
      fontSize: 9
    }
  }, id))) : null))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ D6 · technology register ══════════════════════════════════════
   Four required statuses (charter correction): CONFIRMED · INFERRED ·
   CLAIMED · ABSENT, and the four layer keys OPS/CUST/DATA/INFRA — never
   L2–L5, which would collide with evidence levels. */
const TECH_STATUS = {
  CONFIRMED: {
    cls: "b-ph1",
    note: "verified in evidence"
  },
  INFERRED: {
    cls: "b-purple",
    note: "derived, not stated"
  },
  CLAIMED: {
    cls: "b-org",
    note: "asserted, unverified"
  },
  ABSENT: {
    cls: "",
    note: "searched, not found"
  }
};
const TECH_LAYERS = [["OPS", "Operations"], ["CUST", "Customer"], ["DATA", "Data"], ["INFRA", "Infrastructure"]];
const LAYER_NAME = {
  OPS: "Operations",
  CUST: "Customer",
  DATA: "Data",
  INFRA: "Infrastructure"
};
function LiveTechStack({
  data,
  state
}) {
  const items = data && data.items || [];
  const [layer, setLayer] = useState(null);
  const [status, setStatus] = useState(null);
  if (!items.length) return null;
  const rows = items.filter(it => (!layer || it.layer === layer) && (!status || it.status === status));
  const countBy = (key, v) => items.filter(it => it[key] === v).length;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Technology register",
    note: `${rows.length} of ${items.length} systems`,
    right: /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 6,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "toggle-row"
    }, /*#__PURE__*/React.createElement("button", {
      className: !layer ? "on" : "",
      onClick: () => setLayer(null)
    }, "All"), TECH_LAYERS.filter(([k]) => countBy("layer", k)).map(([k, name]) => /*#__PURE__*/React.createElement("button", {
      key: k,
      className: layer === k ? "on" : "",
      onClick: () => setLayer(layer === k ? null : k),
      title: name
    }, k, " ", countBy("layer", k)))))
  }), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 6,
      marginBottom: 12,
      flexWrap: "wrap"
    }
  }, Object.keys(TECH_STATUS).map(s => {
    const n = countBy("status", s);
    if (!n) return null;
    return /*#__PURE__*/React.createElement("span", {
      key: s,
      className: `b ${TECH_STATUS[s].cls}`,
      style: {
        cursor: "pointer",
        opacity: status && status !== s ? 0.45 : 1
      },
      title: TECH_STATUS[s].note,
      onClick: () => setStatus(status === s ? null : s)
    }, s, " ", n);
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 5
    }
  }, rows.map((it, i) => {
    const st = TECH_STATUS[it.status] || TECH_STATUS.ABSENT;
    const provisional = it.status === "CLAIMED" || it.status === "INFERRED";
    return /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "card-tile",
      style: {
        padding: "9px 12px",
        border: provisional ? "1px dashed var(--z-sep)" : undefined
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 8
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 12,
        fontWeight: 600,
        minWidth: 0
      }
    }, it.product), it.vendor && it.vendor !== it.product ? /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, it.vendor) : null, /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), it.pillar_id ? /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, it.pillar_id) : null, it.layer ? /*#__PURE__*/React.createElement("span", {
      className: "b",
      title: LAYER_NAME[it.layer] || it.layer
    }, it.layer) : null, it.evidence_level ? /*#__PURE__*/React.createElement("span", {
      className: "chip f-mono",
      style: {
        fontSize: 9.5
      },
      title: "evidence level on the L1\u2013L4 ladder"
    }, it.evidence_level) : null, /*#__PURE__*/React.createElement("span", {
      className: `b ${st.cls}`,
      title: st.note
    }, it.status)), it.detection_basis ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-body)",
        marginTop: 4,
        lineHeight: 1.5
      }
    }, it.detection_basis) : null, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginTop: 4,
        gap: 4,
        flexWrap: "wrap"
      }
    }, (it.linked_subcap_ids || []).slice(0, 6).map(id => /*#__PURE__*/React.createElement("span", {
      key: id,
      className: "chip f-mono",
      style: {
        fontSize: 9
      }
    }, id)), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), (it.e_ids || []).map(e => /*#__PURE__*/React.createElement("span", {
      key: e,
      className: "chip f-mono",
      style: {
        fontSize: 9
      }
    }, e))));
  })), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ page assembly ═════════════════════════════════════════════════
   Each page lays its promoted sections out in the prototype's order and
   grid. A section that did not promote renders LiveMissing, in place —
   the page never silently loses a row. */

function PageHead({
  eyebrow,
  title,
  sub,
  right
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "page-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, eyebrow), /*#__PURE__*/React.createElement("h1", null, title), sub ? /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, sub) : null), right ? /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, right) : null);
}
function LiveClientPage({
  entity,
  run,
  tab,
  live
}) {
  const {
    audience
  } = useApp();
  const [cellFilter, setCellFilter] = useState(null);
  const page = tab === "health" ? "heatmap" : tab;
  const sections = LIVE_PAGE_SECTIONS[page];
  if (tab === "runs") {
    return /*#__PURE__*/React.createElement(LiveRuns, {
      entity: entity,
      run: run
    });
  }
  if (!sections) {
    return /*#__PURE__*/React.createElement("div", {
      className: "empty"
    }, /*#__PURE__*/React.createElement("h3", null, "Not a promoted surface"), /*#__PURE__*/React.createElement("p", null, "The ", tab, " view is not part of the promoted page set."));
  }
  if (live && live.loading) return /*#__PURE__*/React.createElement(SectionLoader, null);
  if (live && live.error) {
    return /*#__PURE__*/React.createElement("div", {
      className: "empty"
    }, /*#__PURE__*/React.createElement("h3", null, "Could not load this page"), /*#__PURE__*/React.createElement("p", null, live.error));
  }
  const S = name => liveSection(live, name);
  const St = name => liveSectionState(live, name);
  const has = name => {
    const d = S(name);
    return !!d && !isBlank(d);
  };
  const missing = name => /*#__PURE__*/React.createElement(LiveMissing, {
    key: name,
    name: name,
    state: St(name)
  });
  const runMeta = live && live.run || {};
  const subline = [runMeta.request_id, runMeta.scored_cells != null && runMeta.catalogue_cells != null ? `${fmtNum(runMeta.scored_cells)} of ${fmtNum(runMeta.catalogue_cells)} cells scored` : null, runMeta.ccg_catalog_version ? `catalogue ${runMeta.ccg_catalog_version}` : null, runMeta.promoted_at ? `promoted ${fmtDate(runMeta.promoted_at)}` : null].filter(Boolean).join(" · ");
  if (page === "overview") {
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(PageHead, {
      eyebrow: "Assessment overview",
      title: entity.name,
      sub: subline
    }), has("scores") || has("firmographics") ? /*#__PURE__*/React.createElement(Sec, {
      name: "scores"
    }, /*#__PURE__*/React.createElement(LiveSnapshot, {
      scores: S("scores"),
      firmo: S("firmographics"),
      entity: entity,
      run: run,
      state: St("scores"),
      audience: audience
    })) : missing("scores"), has("why_now") ? /*#__PURE__*/React.createElement(Sec, {
      name: "why_now"
    }, /*#__PURE__*/React.createElement(LiveWhyNow, {
      data: S("why_now"),
      state: St("why_now")
    })) : missing("why_now"), has("exec_summary") ? /*#__PURE__*/React.createElement(Sec, {
      name: "exec_summary"
    }, /*#__PURE__*/React.createElement(LiveExecSummary, {
      data: S("exec_summary"),
      state: St("exec_summary")
    })) : missing("exec_summary"), has("opportunity") ? /*#__PURE__*/React.createElement(Sec, {
      name: "opportunity"
    }, /*#__PURE__*/React.createElement(LiveOpportunity, {
      data: S("opportunity"),
      state: St("opportunity")
    })) : missing("opportunity"), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: has("leadership") ? "1.55fr 1fr" : "1fr",
        gap: 16,
        marginBottom: 18,
        alignItems: "start"
      }
    }, has("findings") ? /*#__PURE__*/React.createElement(Sec, {
      name: "findings"
    }, /*#__PURE__*/React.createElement(LiveFindings, {
      data: S("findings"),
      state: St("findings")
    })) : missing("findings"), has("leadership") ? /*#__PURE__*/React.createElement(Sec, {
      name: "leadership"
    }, /*#__PURE__*/React.createElement(LiveLeadership, {
      data: S("leadership"),
      state: St("leadership")
    })) : null), /*#__PURE__*/React.createElement("div", {
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
    }, "from the scoring workbook, evidence index and peer set")), /*#__PURE__*/React.createElement("div", {
      className: "cards-grid-3",
      style: {
        marginBottom: 16
      }
    }, has("financial_series") ? /*#__PURE__*/React.createElement(Sec, {
      name: "financial_series"
    }, /*#__PURE__*/React.createElement(LiveFinancials, {
      data: S("financial_series"),
      state: St("financial_series"),
      audience: audience
    })) : missing("financial_series"), has("evidence_coverage") ? /*#__PURE__*/React.createElement(Sec, {
      name: "evidence_coverage"
    }, /*#__PURE__*/React.createElement(LiveCoverage, {
      data: S("evidence_coverage"),
      state: St("evidence_coverage"),
      audience: audience
    })) : missing("evidence_coverage"), has("sentiment") ? /*#__PURE__*/React.createElement(Sec, {
      name: "sentiment"
    }, /*#__PURE__*/React.createElement(LiveSentiment, {
      data: S("sentiment"),
      state: St("sentiment")
    })) : missing("sentiment")), has("ceilings") ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginBottom: 18
      }
    }, /*#__PURE__*/React.createElement(Sec, {
      name: "ceilings"
    }, /*#__PURE__*/React.createElement(LiveCeilings, {
      data: S("ceilings"),
      state: St("ceilings")
    }))) : missing("ceilings"), audience !== "customer" ? has("thought_leadership") ? /*#__PURE__*/React.createElement(Sec, {
      name: "thought_leadership"
    }, /*#__PURE__*/React.createElement(LiveThoughtLeadership, {
      data: S("thought_leadership"),
      state: St("thought_leadership")
    })) : missing("thought_leadership") : null);
  }
  if (page === "heatmap") {
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(PageHead, {
      eyebrow: "Maturity heatmap",
      title: `Where ${entity.name} is today`,
      sub: subline
    }), has("workbook_scores") ? /*#__PURE__*/React.createElement(Sec, {
      name: "workbook_scores"
    }, /*#__PURE__*/React.createElement(LiveWorkbookGrid, {
      data: S("workbook_scores"),
      state: St("workbook_scores"),
      entity: entity,
      run: run,
      onDrill: setCellFilter,
      audience: audience
    })) : missing("workbook_scores"), has("focus_areas") ? /*#__PURE__*/React.createElement(Sec, {
      name: "focus_areas"
    }, /*#__PURE__*/React.createElement(LiveFocusAreas, {
      data: S("focus_areas"),
      state: St("focus_areas"),
      audience: audience
    })) : missing("focus_areas"), has("cell_evidence") ? /*#__PURE__*/React.createElement(Sec, {
      name: "cell_evidence"
    }, /*#__PURE__*/React.createElement(LiveCellEvidence, {
      data: S("cell_evidence"),
      state: St("cell_evidence"),
      filter: cellFilter,
      onClearFilter: () => setCellFilter(null)
    })) : missing("cell_evidence"), has("value_chain") ? /*#__PURE__*/React.createElement(Sec, {
      name: "value_chain"
    }, /*#__PURE__*/React.createElement(LiveValueChain, {
      data: S("value_chain"),
      state: St("value_chain")
    })) : missing("value_chain"), has("alerts") ? /*#__PURE__*/React.createElement(Sec, {
      name: "alerts"
    }, /*#__PURE__*/React.createElement(LiveAlerts, {
      data: S("alerts"),
      state: St("alerts")
    })) : missing("alerts"), has("safeguard_gates") ? /*#__PURE__*/React.createElement(Sec, {
      name: "safeguard_gates"
    }, /*#__PURE__*/React.createElement(LiveSafeguards, {
      data: S("safeguard_gates"),
      state: St("safeguard_gates")
    })) : missing("safeguard_gates"), has("evidence_age") ? /*#__PURE__*/React.createElement(Sec, {
      name: "evidence_age"
    }, /*#__PURE__*/React.createElement(LiveEvidenceAge, {
      data: S("evidence_age"),
      state: St("evidence_age"),
      audience: audience
    })) : missing("evidence_age"), has("cohort_patterns") ? /*#__PURE__*/React.createElement(Sec, {
      name: "cohort_patterns"
    }, /*#__PURE__*/React.createElement(LiveCohorts, {
      data: S("cohort_patterns"),
      state: St("cohort_patterns"),
      audience: audience
    })) : missing("cohort_patterns"), missing("evidence"));
  }
  if (page === "insights") {
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(PageHead, {
      eyebrow: "Insights",
      title: `What the evidence says about ${entity.name}`,
      sub: subline
    }), has("insights") ? /*#__PURE__*/React.createElement(Sec, {
      name: "insights"
    }, /*#__PURE__*/React.createElement(LiveInsights, {
      data: S("insights"),
      state: St("insights")
    })) : missing("insights"), has("landscape") ? /*#__PURE__*/React.createElement(Sec, {
      name: "landscape"
    }, /*#__PURE__*/React.createElement(LiveLandscape, {
      data: S("landscape"),
      state: St("landscape")
    })) : missing("landscape"));
  }
  if (page === "platform") {
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(PageHead, {
      eyebrow: "Platform recommendation",
      title: `What ${entity.name} should build next`,
      sub: subline
    }), has("platform_story") ? /*#__PURE__*/React.createElement(Sec, {
      name: "platform_story"
    }, /*#__PURE__*/React.createElement(LivePlatformStory, {
      data: S("platform_story"),
      state: St("platform_story")
    })) : missing("platform_story"), has("recommendations") ? /*#__PURE__*/React.createElement(Sec, {
      name: "recommendations"
    }, /*#__PURE__*/React.createElement(LiveRecommendations, {
      data: S("recommendations"),
      state: St("recommendations"),
      audience: audience
    })) : missing("recommendations"), has("roadmap") ? /*#__PURE__*/React.createElement(Sec, {
      name: "roadmap"
    }, /*#__PURE__*/React.createElement(LiveRoadmap, {
      data: S("roadmap"),
      state: St("roadmap")
    })) : missing("roadmap"), has("stairstep") ? /*#__PURE__*/React.createElement(Sec, {
      name: "stairstep"
    }, /*#__PURE__*/React.createElement(LiveStairstep, {
      data: S("stairstep"),
      state: St("stairstep")
    })) : missing("stairstep"), has("starters") ? /*#__PURE__*/React.createElement(Sec, {
      name: "starters"
    }, /*#__PURE__*/React.createElement(LiveStarters, {
      data: S("starters"),
      state: St("starters")
    })) : missing("starters"));
  }
  if (page === "context") {
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(PageHead, {
      eyebrow: "Context",
      title: `How ${entity.name} got here`,
      sub: subline
    }), has("timeline") ? /*#__PURE__*/React.createElement(Sec, {
      name: "timeline"
    }, /*#__PURE__*/React.createElement(LiveTimeline, {
      data: S("timeline"),
      state: St("timeline")
    })) : missing("timeline"), has("acquisitions") ? /*#__PURE__*/React.createElement(Sec, {
      name: "acquisitions"
    }, /*#__PURE__*/React.createElement(LiveAcquisitions, {
      data: S("acquisitions"),
      state: St("acquisitions"),
      audience: audience
    })) : missing("acquisitions"), has("regulatory_standing") ? /*#__PURE__*/React.createElement(Sec, {
      name: "regulatory_standing"
    }, /*#__PURE__*/React.createElement(LiveRegulatory, {
      data: S("regulatory_standing"),
      state: St("regulatory_standing"),
      audience: audience
    })) : missing("regulatory_standing"), has("issue_register") ? /*#__PURE__*/React.createElement(Sec, {
      name: "issue_register"
    }, /*#__PURE__*/React.createElement(LiveIssueRegister, {
      data: S("issue_register"),
      state: St("issue_register")
    })) : missing("issue_register"), has("context_sentiment") ? /*#__PURE__*/React.createElement(Sec, {
      name: "context_sentiment"
    }, /*#__PURE__*/React.createElement(LiveSentiment, {
      data: S("context_sentiment"),
      state: St("context_sentiment"),
      title: "Context sentiment"
    })) : missing("context_sentiment"));
  }
  if (page === "techstack") {
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(PageHead, {
      eyebrow: "Technology",
      title: `${entity.name}'s estate`,
      sub: subline
    }), has("techstack") ? /*#__PURE__*/React.createElement(Sec, {
      name: "techstack"
    }, /*#__PURE__*/React.createElement(LiveTechStack, {
      data: S("techstack"),
      state: St("techstack")
    })) : missing("techstack"));
  }
  return null;
}

/* ══ Run register ══════════════════════════════════════════════════
   Not a promoted page: the run rows come from the directory, which is the
   one materialised view the app reads for header and rows alike
   (invariant 8). Active is whichever run promote flagged — never recomputed
   here, and never inferred from ordering. */
function LiveRuns({
  entity,
  run
}) {
  const runs = (entity.runs || []).slice();
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(PageHead, {
    eyebrow: "Run history",
    title: `${entity.name} · runs`,
    sub: `${runs.length} promoted run${runs.length === 1 ? "" : "s"}`
  }), runs.length ? /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 6
    }
  }, runs.map((r, i) => {
    const active = r.status === "ACTIVE";
    return /*#__PURE__*/React.createElement("div", {
      key: r.run_id || i,
      className: "card-tile clickable",
      style: {
        padding: "12px 14px",
        borderLeft: active ? "3px solid var(--z-teal)" : undefined
      },
      onClick: () => navigate(`/clients/${entity.id}/overview`, {
        run: r.id
      })
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 8
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "b f-mono"
    }, r.id), /*#__PURE__*/React.createElement("span", {
      className: `b ${active ? "b-ph1" : ""}`
    }, active ? "ACTIVE" : r.status), r.overall != null ? /*#__PURE__*/React.createElement(MaturityChip, {
      score: r.overall
    }) : null, /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), r.subcap_count != null ? /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)"
      }
    }, fmtNum(r.subcap_count), " cells scored") : null, r.promoted_at ? /*#__PURE__*/React.createElement("span", {
      className: "muted f-mono",
      style: {
        fontSize: 10
      }
    }, "promoted ", fmtDate(r.promoted_at)) : null), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginTop: 4,
        gap: 8,
        fontSize: 9.5,
        color: "var(--z-muted)"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "f-mono"
    }, r.run_id), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), r.date ? /*#__PURE__*/React.createElement("span", null, "assessed ", r.date) : /*#__PURE__*/React.createElement("span", null, "assessment date not stated in the package"), r.data_source ? /*#__PURE__*/React.createElement("span", {
      className: "b"
    }, r.data_source) : null));
  }))) : /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, /*#__PURE__*/React.createElement("h3", null, "No promoted runs"), /*#__PURE__*/React.createElement("p", null, "This entity exists in the register but has never promoted a run.")));
}

/* ══ H3 · value chain (optional heatmap section) ═══════════════════ */
function LiveValueChain({
  data,
  state
}) {
  const stages = data && (data.stages || data.rows) || [];
  if (!stages.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Value chain",
    note: "capability read along the member journey"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: `repeat(${stages.length}, minmax(0,1fr))`,
      gap: 6
    }
  }, stages.map((s, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "card-tile",
    style: {
      padding: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      fontWeight: 600,
      marginBottom: 6
    }
  }, s.stage || s.name), s.score != null ? /*#__PURE__*/React.createElement(MaturityChip, {
    score: s.score
  }) : null, (s.subcap_ids || []).length ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 9.5,
      color: "var(--z-muted)",
      marginTop: 6
    }
  }, s.subcap_ids.length, " cells") : null))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}

/* ══ D4 · technology landscape (recomputed from the T1 register) ════ */
function LiveLandscape({
  data,
  state
}) {
  const tiles = data && (data.tiles || data.layers) || [];
  if (!tiles.length) return /*#__PURE__*/React.createElement(LiveMissing, {
    name: "landscape",
    state: state
  });
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 18,
      padding: "18px 20px"
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Technology landscape",
    note: "recomputed from the technology register, never stored"
  }), /*#__PURE__*/React.createElement("div", {
    className: "g4"
  }, tiles.map((t, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
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
    className: "b"
  }, t.layer || t.key), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), t.count != null ? /*#__PURE__*/React.createElement("span", {
    className: "f-mono",
    style: {
      fontSize: 15,
      fontWeight: 700
    }
  }, fmtNum(t.count)) : null), t.label || t.name ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      fontWeight: 500
    }
  }, t.label || t.name) : null, t.detail ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-body)",
      marginTop: 5,
      lineHeight: 1.5
    }
  }, t.detail) : null))), /*#__PURE__*/React.createElement(ProvFoot, {
    state: state
  }));
}
Object.assign(window, {
  LiveClientPage,
  LIVE_PAGE_SECTIONS,
  SECTION_TITLES,
  fmtNum,
  fmtMoney,
  fmtFirmoValue,
  firmoLabel
});