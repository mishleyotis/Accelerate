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
    openSubcap,
    role,
    setIpSurface,
    setIpContext,
    setIpOpen,
    tweaks,
    pushToast
  } = useApp();
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
  }, [DMA.SUBVERTICAL_LABEL[entity.subvertical], entity.hq, entity.assets != null ? `${fmtAssets(entity.assets, entity.assets_unit)} assets` : null, entity.assessment_date ? `Assessment ${fmtDate(entity.assessment_date)}` : null, entity.members != null ? `${entity.members.toLocaleString()} members` : null].filter(Boolean).join(" · "))), /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast(`Customer-safe scorecard generated · ${entity.name}`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Scorecard"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast("Rerun queued - first batch in ~3 min", "success")
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
  }), " Meeting prep"))), /*#__PURE__*/React.createElement(CardBoundary, {
    name: "snapshot"
  }, /*#__PURE__*/React.createElement(SnapshotStrip, {
    entity: entity,
    run: run,
    layout: layout,
    audience: audience
  })), /*#__PURE__*/React.createElement(CardBoundary, {
    name: "why-now signals"
  }, /*#__PURE__*/React.createElement(WhyNowStrip, {
    entity: entity,
    openEvidence: openEvidence,
    audience: audience,
    openSubcap: openSubcap
  })), /*#__PURE__*/React.createElement(CardBoundary, {
    name: "executive narrative"
  }, /*#__PURE__*/React.createElement(SCQACard, {
    entity: entity,
    expanded: scqaExp,
    onToggle: () => setScqaExp(o => !o),
    openEvidence: openEvidence,
    audience: audience
  })), /*#__PURE__*/React.createElement(CardBoundary, {
    name: "opportunity surface"
  }, /*#__PURE__*/React.createElement(OpportunitySurfaceStrip, {
    entity: entity,
    run: run,
    audience: audience
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1.55fr 1fr",
      gap: 16,
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement(CardBoundary, {
    name: "top findings"
  }, /*#__PURE__*/React.createElement(TopFindingsCard, {
    entity: entity,
    openEvidence: openEvidence,
    audience: audience
  })), /*#__PURE__*/React.createElement(CardBoundary, {
    name: "leadership panel"
  }, /*#__PURE__*/React.createElement(LeadershipPanel, {
    audience: audience
  }))), /*#__PURE__*/React.createElement("div", {
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
    className: "cards-grid-2",
    style: {
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement(CardBoundary, {
    name: "financial trajectory"
  }, /*#__PURE__*/React.createElement(FinancialTrajectoryD1, {
    entity: entity,
    audience: audience
  })), /*#__PURE__*/React.createElement(CardBoundary, {
    name: "sentiment"
  }, /*#__PURE__*/React.createElement(SentimentCard, {
    entity: entity,
    audience: audience
  }))), audience !== "customer" ? /*#__PURE__*/React.createElement(CardBoundary, {
    name: "thought leadership"
  }, /*#__PURE__*/React.createElement(ThoughtLeadershipPanel, null)) : null, /*#__PURE__*/React.createElement("div", {
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
  }, "How this assessment was evidenced"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "reach of the evidence behind the scores above \xB7 what would lift each ceiling")), /*#__PURE__*/React.createElement("div", {
    className: audience === "customer" ? "" : "cards-grid-2",
    style: {
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement(CardBoundary, {
    name: "evidence coverage"
  }, /*#__PURE__*/React.createElement(OvCoverageBand, {
    entity: entity,
    audience: audience
  })), audience !== "customer" ? /*#__PURE__*/React.createElement(CardBoundary, {
    name: "capability ceilings"
  }, /*#__PURE__*/React.createElement(OvCeilingCard, {
    entity: entity,
    audience: audience
  })) : null));
}

/* ── The producer's reasoning trace, per section ──────────────────────
   INTERNAL ONLY.

   Every section of this page promotes an `r_layer`: the hypothesis the
   producer worked from, the strongest counter-case they could put against
   their own answer, the probes they ran, the domain test and their own
   verdict. Twelve of the twelve sections on the reference run carry one, and
   not one word of any of them reached a reader — the shaped views the cards
   read (`adaptCoverage`, `adaptLeadership`, `adaptUncertainty`) return the
   figures and drop the trace, so it travelled from the producer to Postgres
   to the browser and stopped there. A finding without its counter-case is
   half the finding.

   Collapsed by default and opened per card. A trace is 400–1500 characters
   of prose and eleven of them expanded would bury the page they explain;
   collapsed, the reader sees that the section was challenged and chooses
   which challenge to read. The treatment is the insights modal's
   (`drawers.jsx`) — including its reason for the "Self-check ·" prefix: a
   bare pill reading ACCEPT beside nothing else was read as a button with a
   missing Reject.

   `probes_run` IS rendered here, where the modal deliberately does not. The
   modal's probes are chip-sized fragments; a section's are whole sentences
   naming the route that was tried and what it returned ("the institution's
   own domain does not serve a non-browser client"), which is exactly the
   working a reader asking "did you look?" wants. */
function OvTrace({
  section,
  audience
}) {
  const [open, setOpen] = useState(false);
  const customer = String(audience || "").toLowerCase() === "customer";
  const r = customer ? null : DMA.rLayerFor ? DMA.rLayerFor(section) : null;
  const parts = [["Hypothesis", r && r.hypothesis], ["Counter-case", r && r.counter], ["Domain test", r && r.domain_test]].map(([k, v]) => [k, asText(v)]).filter(([, v]) => v);
  const probes = (r && r.probes_run || []).map(asText).filter(Boolean);
  if (!r || !parts.length && !probes.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    "data-trace": section,
    style: {
      borderTop: "1px solid var(--z-sep)",
      marginTop: 12,
      paddingTop: 8
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: e => {
      e.stopPropagation();
      setOpen(o => !o);
    },
    style: {
      display: "flex",
      alignItems: "center",
      gap: 7,
      width: "100%",
      background: "none",
      border: 0,
      padding: "2px 0",
      cursor: "pointer",
      textAlign: "left"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "eyebrow",
    style: {
      fontSize: 9.5,
      color: "var(--z-dpur)"
    }
  }, "Reasoning trace"), r.verdict ? /*#__PURE__*/React.createElement("span", {
    className: "b b-purple",
    style: {
      cursor: "pointer"
    },
    title: "the producer's own verdict on its hypothesis, promoted with the section \u2014 not a control"
  }, "Self-check \xB7 ", r.verdict) : null, r.confidence ? /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, r.confidence) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer",
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)"
    }
  }, open ? "Hide" : "Show"), /*#__PURE__*/React.createElement(Icon, {
    name: open ? "chevron-u" : "chevron-d",
    size: 12,
    style: {
      color: "var(--z-muted)",
      flexShrink: 0
    }
  })), open ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 8
    }
  }, parts.map(([k, v]) => /*#__PURE__*/React.createElement("div", {
    key: k,
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
      marginBottom: 2
    }
  }, k), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-body)",
      lineHeight: 1.55
    }
  }, v))), probes.length ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 9.5,
      fontWeight: 700,
      letterSpacing: ".08em",
      color: "var(--z-muted)",
      textTransform: "uppercase",
      marginBottom: 3
    }
  }, "Probes run"), /*#__PURE__*/React.createElement("ul", {
    style: {
      margin: 0,
      paddingLeft: 16
    }
  }, probes.map((t, i) => /*#__PURE__*/React.createElement("li", {
    key: i,
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      lineHeight: 1.5,
      marginBottom: 3
    }
  }, t)))) : null) : null);
}

/* ── O1 · the four pillar bars ────────────────────────────────────────
   A bar with no figure must not look like a bar with a figure of zero, and
   the reason it carries none must be on the page beside it.

   What this run rendered before: four `.pbar-track` elements at their grey
   background with a zero-width fill, an empty 32px score column, an empty
   50px delta column, and a legend promising a peer median beside a tick that
   is never drawn. Nothing said the pillar grain does not resolve on this run
   — although the payload says exactly that, at length, on all four rows
   (`proxy_disclosure`, ~900 characters, promoted and served).

   So: a served figure renders as a bar; an unserved one renders as the
   sentence saying so, in the slot the bar would have occupied; the promoted
   explanation renders once beneath the rows (identical on all four here, and
   printing one paragraph four times is noise, not disclosure); and the legend
   names only the marks that are actually drawn. The moment a pillar figure or
   a peer median IS served, the same code draws it — this is one renderer
   handling both states, not a special case for an empty run. */
function OvPillarBars({
  entity,
  run,
  audience
}) {
  const sec = DMA.scoresFor ? DMA.scoresFor(entity.id) : null;
  const rows = {};
  for (const r of sec && sec.pillars || []) {
    if (r && r.pillar_id) rows[r.pillar_id] = r;
  }
  const scores = entity.pillar_scores || {};
  const peers = entity.pillar_peer_medians || {};
  const num = v => v === null || v === undefined || v === "" || !isFinite(Number(v)) ? null : Number(v);
  const anyScore = DMA.PILLARS.some(p => num(scores[p.id]) != null);
  const anyPeer = DMA.PILLARS.some(p => num(peers[p.id]) != null);
  const anyBlank = DMA.PILLARS.some(p => num(scores[p.id]) == null || num(peers[p.id]) == null);

  /* The promoted explanation, de-duplicated. The producer writes it per row
     because a future run may have a different reason per pillar; on this one
     all four are the same paragraph. */
  const why = [];
  for (const p of DMA.PILLARS) {
    const t = asText((rows[p.id] || {}).proxy_disclosure);
    if (t && !why.includes(t)) why.push(t);
  }
  /* The basis a served figure was computed on, where the run states one.
     Rendered as the row's own tooltip and, when every row agrees, once under
     the bars — a mean nobody can resolve to a basis is the thing the maturity
     grid exists to avoid publishing. */
  const basisOf = row => asText(row.basis || row.score_basis) || null;
  const nOf = row => num(row.n != null ? row.n : row.n_cells);
  const bases = [];
  for (const p of DMA.PILLARS) {
    const b = basisOf(rows[p.id] || {});
    if (b && !bases.includes(b)) bases.push(b);
  }
  return /*#__PURE__*/React.createElement("div", null, DMA.PILLARS.map(p => {
    const row = rows[p.id] || {};
    const s = num(scores[p.id]);
    const peer = num(peers[p.id]);
    const peerL = peer == null ? null : peer / 5 * 100;
    // Both ends or no delta: `null - peer` is -peer, which rendered an
    // unscored pillar as ▼peer — a movement nobody measured.
    const delta = peer == null || s == null ? null : s - peer;
    const basis = basisOf(row),
      n = nOf(row);
    const rowTitle = s != null ? [`${p.id} ${fx(s, 1)} / 5`, basis, n != null ? `n=${n}` : null].filter(Boolean).join(" · ") : asText(row.proxy_disclosure) || undefined;
    return /*#__PURE__*/React.createElement("div", {
      className: "pbar",
      key: p.id,
      title: rowTitle,
      onClick: () => navigate(`/clients/${entity.id}/heatmap`, {
        pillar: p.id,
        run: run.id
      }),
      style: {
        cursor: "pointer"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "pbar-name"
    }, p.id, " \xB7 ", p.short), s != null || peer != null ? /*#__PURE__*/React.createElement("div", {
      className: "pbar-track"
    }, s == null ? null : /*#__PURE__*/React.createElement("div", {
      className: "pbar-fill",
      style: {
        width: `${s / 5 * 100}%`,
        background: DMA.helpers.maturityHex(s)
      }
    }), peerL == null ? null : /*#__PURE__*/React.createElement("div", {
      className: "pbar-peer",
      style: {
        left: `calc(${peerL}% - 1px)`
      },
      title: `Peer ${fx(peer, 1)}`
    })) :
    /*#__PURE__*/
    /* No track at all. An 8px grey rail with nothing in it is read
       as a score of zero by every reader who does not know the
       payload, and this run scores none of these pillars — it does
       not score them at nought. */
    React.createElement("div", {
      style: {
        flex: 1,
        fontSize: 11,
        color: "var(--z-muted)",
        lineHeight: 1.4
      },
      "data-no-figure": p.id
    }, "No pillar figure is served on this run"), /*#__PURE__*/React.createElement("div", {
      className: "pbar-score"
    }, s == null ? null : fx(s, 1)), /*#__PURE__*/React.createElement("div", {
      className: "pbar-delta",
      style: {
        color: delta == null ? "var(--z-muted)" : delta < 0 ? "var(--z-below)" : "var(--z-mid)"
      }
    }, delta == null ? null : /*#__PURE__*/React.createElement(React.Fragment, null, delta >= 0 ? "▲" : "▼", " ", fx(Math.abs(delta), 1))));
  }), anyScore || anyPeer ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 8,
      fontSize: 10.5,
      color: "var(--z-muted)",
      display: "flex",
      gap: 14,
      paddingLeft: 122
    }
  }, anyScore ? /*#__PURE__*/React.createElement("span", {
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
  }), " Entity") : null, anyPeer ? /*#__PURE__*/React.createElement("span", {
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
  }), " Peer median") : null) : null, bases.length && anyScore ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 6,
      paddingLeft: 122,
      fontSize: 10.5,
      color: "var(--z-muted)"
    }
  }, "Basis \xB7 ", bases.join(" · ")) : null, why.length && anyBlank ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 10,
      paddingLeft: 122
    }
  }, why.map((t, i) => /*#__PURE__*/React.createElement("p", {
    key: i,
    style: {
      margin: i ? "8px 0 0" : 0,
      fontSize: 11,
      color: "var(--z-muted)",
      lineHeight: 1.55
    }
  }, t))) : null, /*#__PURE__*/React.createElement(OvTrace, {
    section: "overview.scores",
    audience: audience
  }));
}

/* ── O1 · snapshot strip ──────────────────────────────────────────── */
function SnapshotStrip({
  entity,
  run,
  layout,
  audience
}) {
  return /*#__PURE__*/React.createElement("div", {
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
  }, DMA.helpers.maturityLabel(entity.overall) ? /*#__PURE__*/React.createElement("span", {
    className: `b ${DMA.helpers.maturityClass(entity.overall)}`
  }, DMA.helpers.maturityLabel(entity.overall).toUpperCase()) : null, /*#__PURE__*/React.createElement("span", {
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
  }, asText(entity.framing) || asText(entity.posture_basis) || (entity.overall != null ? `Composite ${fx(entity.overall, 1)} / 5 across ${DMA.PILLARS.length} pillars.` : /*#__PURE__*/React.createElement(EnrichmentGap, {
    what: "Run framing",
    audience: audience
  }))))) : null, /*#__PURE__*/React.createElement(OvPillarBars, {
    entity: entity,
    run: run,
    audience: audience
  })), /*#__PURE__*/React.createElement(FirmographicsPanel, {
    entity: entity,
    audience: audience
  })));
}

/* ── Firmographics · the promoted figures, and only those ─────────── */
function FirmographicsPanel({
  entity,
  audience
}) {
  /* One absent-state builder for every pinned row, so the three states a
     firmographic can be in stay distinguishable wherever they occur:
        stated   the value renders
       HELD     quarantined with the ladder that failed — a finding, and the
                reason is the content
       silent   nobody established it; it is in the connector's worklist
      Held is read from `entity.held[slot]`, which app-root's firmoFields sets
     for a pinned field. Before that existed, a held pinned field rendered no
     row at all and was indistinguishable from one never asked for — which is
     the exact confusion this whole component was rebuilt to end. */
  /* One row builder. A row whose value cannot be established is NOT
     rendered — owner adjudication 2026-08-14, replacing the three-state gap
     vocabulary ("Not stated · queued for enrichment", "Held · reason") with
     silence on the page.
      The reason that is safe now and was not before: the omission is no longer
     invisible to the SYSTEM. `list_enrichment_gaps(run_id)` computes the same
     empty set from the staged payload, and audit_promoted_client.py fails on
     it — so a field the reader never sees is still on the producer's worklist
     and still blocks a clean audit. Hiding it from the page hid it from
     everyone only while nothing else counted.
      `held` is likewise not surfaced: a quarantine reason is internal
     provenance, and the row it belonged to now simply does not appear. */
  const rows = [];
  const row = (k, v) => {
    if (v !== null && v !== undefined && v !== "") rows.push([k, v]);
  };
  row(entity.assets_label || "Assets", fmtAssets(entity.assets, entity.assets_unit));
  row("Employees", entity.employees != null ? entity.employees.toLocaleString() : null);
  row("Branches", entity.branches != null ? String(entity.branches) : null);
  row("Members", entity.members != null ? entity.members.toLocaleString() : null);
  row("Customers", entity.customers != null ? entity.customers.toLocaleString() : null);
  /* ONE CAGR row. It rendered twice until 2026-08-14: pinned here from the
     series the adapter computes, and printed again by the passthrough below
     because `cagr` was missing from the pinned KEY set. Computed wins — a
     growth rate is derived and the promoted series is its source of truth —
     and a run that stated its own falls back in with its own basis. */
  row("CAGR", entity.cagr != null ? `${fmtPct(entity.cagr)}${entity.cagr_basis ? ` · ${entity.cagr_basis}` : ""}` : entity.stated_cagr != null ? `${fx(entity.stated_cagr, 1)}%${entity.stated_cagr_basis ? ` · ${entity.stated_cagr_basis}` : ""}` : null);
  row("Net worth ratio", entity.net_worth_ratio != null ? `${fx(entity.net_worth_ratio, 2)}%` : null);
  row("Regulator", entity.regulator || null);
  // Linked because a domain a reader cannot open is half a fact.
  row("Website", entity.website ? /*#__PURE__*/React.createElement("a", {
    href: /^https?:/i.test(entity.website) ? entity.website : `https://${entity.website}`,
    target: "_blank",
    rel: "noopener noreferrer"
  }, entity.website) : null);
  row("HQ", entity.hq || null);
  // Footprint reads the regulatory section's jurisdictions first, then a
  // footprint the firmographics stated — both consumed by this one row.
  row("Footprint", entity.footprint?.length ? entity.footprint.join(" · ") : entity.stated_footprint ? String(entity.stated_footprint) : null);
  row("Charter", entity.charter || null);
  row("Founded", entity.founded ? String(entity.founded).slice(0, 4) : null);
  return /*#__PURE__*/React.createElement("div", {
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
  }, "Firmographics"), entity.firmographics_unreadable ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-org)",
      lineHeight: 1.5,
      marginBottom: 8
    }
  }, "The firmographics section did not arrive as a list of fields, so no figure below is read from it.") : null, rows.map(([k, v], i) => /*#__PURE__*/React.createElement(Row, {
    key: `f${i}`,
    k: k,
    v: v
  })), (entity.extra_fields || []).map((f, i) => /*#__PURE__*/React.createElement(Row, {
    key: `x${i}`,
    k: humaniseFieldName(f.field),
    v: f.held ? /*#__PURE__*/React.createElement(EnrichmentGap, {
      what: humaniseFieldName(f.field),
      held: true,
      reason: f.reason,
      audience: audience
    }) : `${f.value}${f.unit ? ` ${f.unit}` : ""}`
  })), /*#__PURE__*/React.createElement(EnrichmentFlag, {
    s: (DMA.LIVE_ENRICHMENT || {}).firmographics,
    what: "firmographics",
    audience: audience
  }), /*#__PURE__*/React.createElement(OvTrace, {
    section: "overview.firmographics",
    audience: audience
  }));
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
  }, fx(score, 1))));
}

/* ── Why-now strip · card row + full-width drilldown, per-client ────
   Sources DMA.whyNowFor(entity.id): hand-authored for the flagship,
   synthesized from each client's own scoring/evidence otherwise.
   The face is one horizontal row of compact cards — kind chip over the
   trigger sentence — because four stacked full-width rows pushed the rest
   of the page below the fold and read as four cards instead of one strip.
   The drilldown carries everything the stacked rows did (detail · metric ·
   dated event · window · the play · peer context · risk-if-ignored · cost
   of acting · bears-on cells · tier-coded evidence · claim + confidence),
   but it opens BELOW the strip at full width: the detail is prose, and
   expanding it inside a 200px column crushed every sentence. The window
   moves into the drilldown as a labelled row for the same reason it once
   broke the stacked header — it is a 20-40-word clause naming the closing
   event, not a chip-sized phrase. One signal open at a time; none open by
   default — the strip is the summary, the reader chooses the drilldown.
   Customer view keeps positive framing and strips internal rationale. */
function WhyNowStrip({
  entity,
  openEvidence,
  audience,
  openSubcap
}) {
  const [open, setOpen] = useState(null); // no drilldown until a card is chosen
  const signals = DMA.whyNowFor(entity.id) || [];
  const isCust = audience === "customer";
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
  // The chip is the signal's `kind`, compressed to one word. The contract's
  // vocabulary is already chip-sized (LEADERSHIP · REGULATORY · TECHNOLOGY);
  // the exceptions map to the word a reader would say, and anything else —
  // fixture categories, future kinds — falls back to the kind text itself,
  // uppercased. Never invented: no kind, no guess, just SIGNAL.
  const CHIP_WORD = {
    "M&A": "MERGER",
    "CORE_MIGRATION": "MIGRATION"
  };
  const chipOf = kind => {
    if (!kind) return "SIGNAL";
    const k = String(kind).toUpperCase();
    return CHIP_WORD[k] || k.replace(/_/g, " ");
  };
  const kindChip = kind => /*#__PURE__*/React.createElement("span", {
    className: "f-mono",
    style: {
      fontSize: 9.5,
      fontWeight: 700,
      letterSpacing: ".08em",
      textTransform: "uppercase",
      color: "var(--z-dpur)",
      background: "rgba(115,91,161,.14)",
      borderRadius: 4,
      padding: "2px 7px",
      flexShrink: 0
    }
  }, chipOf(kind));
  const sel = open != null ? signals[open] : null;
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
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
      gap: 10
    }
  }, signals.map((s, i) => {
    const openNow = open === i;
    return /*#__PURE__*/React.createElement("button", {
      key: s.id || i,
      onClick: () => setOpen(o => o === i ? null : i),
      style: {
        textAlign: "left",
        cursor: "pointer",
        background: "var(--z-lav)",
        border: `1px solid ${openNow ? "var(--ph0-bd)" : "var(--z-sep)"}`,
        borderRadius: 10,
        padding: "11px 13px",
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        gap: 8,
        transition: "border-color 140ms var(--ease)"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        flexWrap: "wrap"
      }
    }, kindChip(s.category), !isCust && s.strength ? /*#__PURE__*/React.createElement("span", {
      className: `b ${STR[s.strength] || "b-muted"}`
    }, s.strength) : null), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 12,
        fontWeight: 500,
        color: "var(--z-dark)",
        lineHeight: 1.45
      },
      title: s.detail || s.label
    }, s.label));
  })), sel ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 12,
      border: "1px solid var(--ph0-bd)",
      borderRadius: 10,
      background: "var(--ph0-lt)",
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => setOpen(null),
    style: {
      width: "100%",
      display: "flex",
      alignItems: "center",
      gap: 9,
      padding: "12px 14px",
      background: "none",
      border: 0,
      cursor: "pointer",
      textAlign: "left"
    }
  }, kindChip(sel.category), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      fontSize: 13,
      fontWeight: 600,
      color: "var(--z-dark)",
      minWidth: 0
    }
  }, sel.label), /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-u",
    size: 15,
    style: {
      color: "var(--z-muted)",
      flexShrink: 0
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "0 14px 14px"
    }
  }, (isCust ? sel.impact : sel.detail) ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      color: "var(--z-body)",
      lineHeight: 1.6,
      marginBottom: 10
    }
  }, isCust ? sel.impact : sel.detail) : null, !isCust && sel.metric ? /*#__PURE__*/React.createElement("div", {
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
  }, sel.metric) : null, sel.timeline ? /*#__PURE__*/React.createElement("button", {
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
  }, sel.timeline.date), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)"
    }
  }, sel.timeline.event), /*#__PURE__*/React.createElement(Icon, {
    name: "arrow-r",
    size: 10,
    style: {
      color: "var(--z-muted)"
    }
  })) : null, sel.window ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-muted)",
      lineHeight: 1.5,
      margin: "0 0 10px"
    }
  }, /*#__PURE__*/React.createElement("strong", {
    style: {
      color: "var(--z-dpur)"
    }
  }, "Window \xB7 "), sel.window) : null, sel.play ? /*#__PURE__*/React.createElement("div", {
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
  }, sel.play)) : null, !isCust && sel.peer_context ? /*#__PURE__*/React.createElement("div", {
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
  }, "Peer context \xB7 "), sel.peer_context) : null, !isCust && sel.risk ? /*#__PURE__*/React.createElement("div", {
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
  }, sel.risk)) : null, sel.cost_now ? /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--z-lav)",
      borderLeft: "3px solid var(--z-dpur)",
      borderRadius: "0 6px 6px 0",
      padding: "8px 12px",
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 9.5,
      fontWeight: 700,
      letterSpacing: ".1em",
      color: "var(--z-dpur)",
      textTransform: "uppercase",
      marginBottom: 2
    }
  }, "Cost of acting now"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-body)",
      lineHeight: 1.55
    }
  }, sel.cost_now)) : null, (sel.subcaps || []).length ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 5,
      flexWrap: "wrap",
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9.5,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".08em"
    }
  }, "Bears on"), sel.subcaps.map(cid => /*#__PURE__*/React.createElement("button", {
    key: cid,
    className: "chip purple",
    style: {
      cursor: "pointer",
      border: 0
    },
    onClick: () => openSubcap && openSubcap(cid)
  }, cid))) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 6,
      flexWrap: "wrap",
      marginTop: 10
    }
  }, sel.evidence && sel.evidence.length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9.5,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".08em"
    }
  }, "Evidence"), sel.evidence.map(eid => {
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
  }), !isCust && sel.claim ? /*#__PURE__*/React.createElement("span", {
    className: `b ${CLAIM[sel.claim] || "b-muted"}`
  }, sel.claim) : null, !isCust && sel.confidence ? /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, sel.confidence, " confidence") : null))) : null, /*#__PURE__*/React.createElement(OvTrace, {
    section: "overview.why_now",
    audience: audience
  }));
}

/* ── SCQA card ──────────────────────────────────────────────────── */
function SCQACard({
  entity,
  expanded,
  onToggle,
  openEvidence,
  audience
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
  }, expanded ? "Collapse ↑" : "Read full ↓")), /*#__PURE__*/React.createElement(SCQABody, {
    entity: entity,
    expanded: expanded,
    openEvidence: openEvidence,
    audience: audience
  }), /*#__PURE__*/React.createElement(OvTrace, {
    section: "overview.exec_summary",
    audience: audience
  }));
}

/* ── The storyline, challenged ────────────────────────────────────────
   INTERNAL ONLY, and the customer envelope proves it was meant to render
   somewhere: `storyline_challenge` is one of the two fields the server strips
   for that audience (`redacted_count 2`), which is a redaction decision about
   content that had no renderer at all.

   Five volleys on the reference run — the client executive defending a public
   decision, finance asking for the return, the incumbent vendor, the rival,
   and our own AE — each with the challenge, the answer, whether the storyline
   HELD or CHANGED, and what changed when it did. This is the single most
   useful thing on the page for anyone about to walk into the meeting, and it
   travelled from the producer to the browser and stopped.

   Rendered inside the expanded narrative, because that is where a reader is
   already reading the story these volleys were fired at. */
function OvStorylineChallenge({
  challenge,
  audience
}) {
  const [open, setOpen] = useState(null);
  if (String(audience || "").toLowerCase() === "customer") return null;
  const volleys = (challenge && challenge.volleys || []).filter(v => v && (v.challenge || v.answer));
  if (!volleys.length) return null;
  const who = v => asText(v.challenger) ? String(v.challenger).replace(/_/g, " ") : "challenge";
  return /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14,
      borderTop: "1px solid var(--z-sep)",
      paddingTop: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8,
      marginBottom: 8,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "eyebrow",
    style: {
      fontSize: 9.5,
      color: "var(--z-dpur)"
    }
  }, "Storyline challenge"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, volleys.length, " ", volleys.length === 1 ? "volley" : "volleys", " \xB7 the objections this story was tested against, and what it did with each")), volleys.map((v, i) => {
    const isOpen = open === i;
    const held = String(v.outcome || "").toLowerCase() === "held";
    return /*#__PURE__*/React.createElement("div", {
      key: v.volley != null ? v.volley : i,
      style: {
        borderTop: i ? "1px solid var(--z-sep)" : 0,
        padding: "8px 0"
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setOpen(o => o === i ? null : i),
      style: {
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        width: "100%",
        background: "none",
        border: 0,
        padding: 0,
        cursor: "pointer",
        textAlign: "left"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        fontSize: 9.5,
        fontWeight: 700,
        letterSpacing: ".06em",
        textTransform: "uppercase",
        color: "var(--z-dpur)",
        background: "rgba(115,91,161,.14)",
        borderRadius: 4,
        padding: "2px 7px",
        flexShrink: 0,
        whiteSpace: "nowrap"
      }
    }, who(v)), /*#__PURE__*/React.createElement("span", {
      style: {
        flex: 1,
        minWidth: 0,
        fontSize: 12.5,
        color: "var(--z-dark)",
        lineHeight: 1.5
      }
    }, asText(v.challenge)), v.outcome ? /*#__PURE__*/React.createElement("span", {
      className: `b ${held ? "b-muted" : "b-org"}`,
      style: {
        flexShrink: 0
      }
    }, held ? "Story held" : "Story changed") : null, /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-u" : "chevron-d",
      size: 13,
      style: {
        color: "var(--z-muted)",
        flexShrink: 0,
        marginTop: 2
      }
    })), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 8,
        paddingLeft: 4
      }
    }, asText(v.answer) ? /*#__PURE__*/React.createElement("div", {
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
        marginBottom: 2
      }
    }, "Answer"), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12.5,
        color: "var(--z-body)",
        lineHeight: 1.6
      }
    }, asText(v.answer))) : null, asText(v.changed) ? /*#__PURE__*/React.createElement("div", {
      style: {
        background: "var(--z-lav)",
        borderLeft: "3px solid var(--z-dpur)",
        borderRadius: "0 6px 6px 0",
        padding: "8px 12px"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-dpur)",
        textTransform: "uppercase",
        marginBottom: 2
      }
    }, "What changed"), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-body)",
        lineHeight: 1.55
      }
    }, asText(v.changed))) : null) : null);
  }));
}

/* The promoted SCQA, and nothing else. This card used to interpolate three
   fields into a paragraph of prose about a fictional bank — "a mid-tier …
   trails the peer median by 0.4 … Two recent C-suite hires open a 6-9 month
   integration window", then an expanded body naming nCino, FIS Profile and
   Databricks with two hardcoded evidence chips. All of it rendered under a
   real client's name while the run's own six-field SCQA sat adapted and
   unread. The contract's fields are the card. */
const SCQA_PARTS = [["situation", "Situation"], ["complication", "Complication"], ["question", "Question"], ["answer", "Answer"], ["sequencing_rationale", "Why this order"], ["cost_of_delay", "Cost of delay"]];
function SCQABody({
  entity,
  expanded,
  openEvidence,
  audience
}) {
  const s = DMA.execSummaryFor(entity.id);
  const parts = SCQA_PARTS.filter(([k]) => s && asText(s[k]));
  if (!parts.length) {
    return /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12.5,
        color: "var(--z-muted)"
      }
    }, "No executive narrative promoted for this run.");
  }
  // Collapsed shows the situation and the complication — the constraint is the
  // point of the card; expanded shows all six with their headings.
  const shown = expanded ? parts : parts.slice(0, 2);
  const eIds = Array.isArray(s.e_ids) ? s.e_ids : [];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      color: "var(--z-dark)",
      lineHeight: 1.7,
      maxWidth: 880
    }
  }, shown.map(([key, heading]) => /*#__PURE__*/React.createElement("div", {
    key: key,
    style: {
      marginBottom: 10
    }
  }, expanded ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      fontWeight: 700,
      letterSpacing: ".06em",
      color: "var(--z-mid)",
      textTransform: "uppercase",
      marginBottom: 3
    }
  }, heading) : null, /*#__PURE__*/React.createElement("div", null, asText(s[key])))), expanded && eIds.length ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 6,
      flexWrap: "wrap",
      marginTop: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)"
    }
  }, "EVIDENCE"), eIds.map(eid => /*#__PURE__*/React.createElement("button", {
    key: eid,
    className: "chip",
    style: {
      cursor: "pointer",
      border: 0
    },
    onClick: () => openEvidence(eid)
  }, eid))) : null, expanded ? /*#__PURE__*/React.createElement(OvStorylineChallenge, {
    challenge: s.storyline_challenge,
    audience: audience
  }) : null);
}

/* ── Opportunity Surface · per platform ───────────────────────────────
   O8. Two defects, one component.

   THE SCORE COLUMN. The tile was a flex row with a shrinkable right-hand
   block and no `white-space` rule on the number inside it, so on a five-column
   grid the column collapsed to about 22px and Chromium wrapped the score one
   character per line: `55.5` rendered as `5`/`5.`/`5` in a 72px-tall stack,
   and the label under it as `fit`/`sco`/`re`. Three of the five tiles. The
   fix is the score column refusing to shrink and refusing to wrap, and the
   platform NAME taking the give instead — a name is prose and wraps well, a
   number is not and does not. The figure also goes through `fx(v, 1)`, the
   same formatter D4 uses, because the same composite printed `66.75` here and
   `66.8` there.

   THE TILE BODY. Everything the producer wrote ABOUT the ranking — the cells
   each platform addresses and the feature that addresses each one, the three
   weighted factors and their contributions, the stack context, the rank
   rationale, and the platforms considered and set aside with the reason —
   was promoted on all five tiles, in both audiences, and rendered nowhere. A
   fit score with no working shown is a number a reader has to take on trust;
   it is also the first thing a client asks about. The working opens under the
   strip rather than inside a 200px column, for the same reason the why-now
   drilldown does: the content is prose.

   Navigation is untouched — the tile still opens the platform page — so the
   working is reached from a separate control on the tile rather than by
   replacing the click that was already there. */
function OpportunitySurfaceStrip({
  entity,
  run,
  audience
}) {
  const [open, setOpen] = useState(null);
  const sec = DMA.opportunityFor ? DMA.opportunityFor(entity.id) : null;
  const num = v => v === null || v === undefined || v === "" || !isFinite(Number(v)) ? null : Number(v);
  /* The promoted tiles carry the platform's own name, so the static vendor
     catalogue is consulted only for a fixture-mode key. Falls back to the
     score-only `oss` map when no section arrived. */
  const promoted = (sec && sec.tiles || []).filter(t => t && t.platform).map(t => ({
    ...t,
    composite: num(t.composite)
  }));
  const tiles = promoted.length ? promoted.slice().sort((a, b) => {
    const ra = num(a.rank),
      rb = num(b.rank);
    if (ra != null && rb != null && ra !== rb) return ra - rb;
    return (b.composite || 0) - (a.composite || 0);
  }) : Object.entries(entity.oss || {}).sort((a, b) => b[1] - a[1]).map(([pid, score]) => ({
    platform: pid,
    composite: num(score)
  }));
  const discarded = (sec && sec.discarded || []).filter(d => d && (d.platform || d.reason));
  if (!tiles.length && !discarded.length) return null;
  const sel = open != null ? tiles[open] : null;
  const factorRows = t => (t.factors || []).filter(f => f && f.name).map(f => ({
    name: asText(f.name),
    value: num(f.value),
    weight: num(f.weight),
    contribution: num(f.contribution)
  }));
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
  }, tiles.map((t, i) => {
    const pid = t.platform;
    const cat = DMA.getPlatform(pid);
    const name = cat && cat.name || pid;
    const score = t.composite;
    const cells = (t.addressable_cells || []).filter(c => c && c.subcap_id);
    const sub = asText(t.headline) || (cat && cat.features ? cat.features.split(" · ").slice(0, 2).join(" · ") : null);
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
        gap: 8,
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600,
        color: "var(--z-dark)",
        lineHeight: 1.3
      }
    }, name), sub ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        marginTop: 2,
        lineHeight: 1.4
      }
    }, sub) : null), /*#__PURE__*/React.createElement("div", {
      style: {
        textAlign: "right",
        flexShrink: 0,
        minWidth: 46
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 24,
        fontWeight: 200,
        color: "var(--z-teal)",
        lineHeight: 1,
        whiteSpace: "nowrap"
      }
    }, score == null ? null : fx(score, 1)), /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 9,
        color: "var(--z-muted)",
        whiteSpace: "nowrap"
      }
    }, "fit score"))), /*#__PURE__*/React.createElement("div", {
      className: "prog",
      style: {
        height: 5
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "prog-fill",
      style: {
        width: `${score == null ? 0 : score}%`,
        background: (score || 0) >= 60 ? "var(--z-teal)" : (score || 0) >= 35 ? "var(--m-bld)" : "var(--m-act)"
      }
    })), cells.length || t.rank != null || factorRows(t).length ? /*#__PURE__*/React.createElement("button", {
      onClick: e => {
        e.stopPropagation();
        setOpen(o => o === i ? null : i);
      },
      style: {
        marginTop: 8,
        display: "flex",
        alignItems: "center",
        gap: 5,
        background: "none",
        border: 0,
        padding: 0,
        cursor: "pointer",
        fontSize: 10.5,
        color: "var(--z-mid)",
        whiteSpace: "nowrap"
      }
    }, t.rank != null ? /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        color: "var(--z-muted)"
      }
    }, "#", t.rank) : null, /*#__PURE__*/React.createElement("span", null, cells.length ? `Cells it addresses · ${cells.length}` : "Why this ranks"), /*#__PURE__*/React.createElement(Icon, {
      name: open === i ? "chevron-u" : "chevron-d",
      size: 11
    })) : null);
  })), sel ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 12,
      border: "1px solid var(--z-sep)",
      borderRadius: 10,
      background: "var(--z-bg)",
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => setOpen(null),
    style: {
      width: "100%",
      display: "flex",
      alignItems: "center",
      gap: 9,
      padding: "12px 14px",
      background: "none",
      border: 0,
      cursor: "pointer",
      textAlign: "left"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      fontSize: 13,
      fontWeight: 600,
      color: "var(--z-dark)",
      minWidth: 0
    }
  }, (DMA.getPlatform(sel.platform) || {}).name || sel.platform, sel.composite == null ? null : /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-muted)",
      fontWeight: 400
    }
  }, " \xB7 ", fx(sel.composite, 1), " / 100")), /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-u",
    size: 15,
    style: {
      color: "var(--z-muted)",
      flexShrink: 0
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "0 14px 14px"
    }
  }, asText(sel.rank_rationale) ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: ".04em",
      color: "var(--z-muted)",
      marginBottom: 3
    }
  }, "Why it ranks here"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      color: "var(--z-body)",
      lineHeight: 1.6
    }
  }, asText(sel.rank_rationale))) : null, asText(sel.their_stack_context) ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: ".04em",
      color: "var(--z-muted)",
      marginBottom: 3
    }
  }, "Against their stack"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      color: "var(--z-body)",
      lineHeight: 1.6
    }
  }, asText(sel.their_stack_context))) : null, factorRows(sel).length ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: ".04em",
      color: "var(--z-muted)",
      marginBottom: 4
    }
  }, "How the score is made"), (fs => fs.map((f, i) => {
    /* The bar is the factor's SHARE OF THE COMPOSITE, which is
       what "how the score is made" means. Drawn as `value * 10`
       it ranked the factors in the wrong order: a gap-depth
       count of 11 drew a full bar while the relevance fraction
       of 0.85 — the larger contribution — drew a sliver. The
       three factors here are a count and two fractions; only
       their contributions are on one scale. */
    const total = fs.reduce((a, x) => a + (x.contribution || 0), 0);
    const share = f.contribution != null && total > 0 ? f.contribution / total * 100 : null;
    return /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        display: "grid",
        gridTemplateColumns: "180px 1fr 96px",
        gap: 8,
        alignItems: "center",
        padding: "3px 0"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-body)"
      }
    }, f.name), /*#__PURE__*/React.createElement("div", {
      style: {
        height: 6,
        background: "var(--z-sep)",
        borderRadius: 3,
        overflow: "hidden"
      }
    }, share == null ? null : /*#__PURE__*/React.createElement("div", {
      style: {
        width: `${share}%`,
        height: "100%",
        background: "var(--z-mid)",
        borderRadius: 3
      }
    })), /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)",
        textAlign: "right",
        whiteSpace: "nowrap"
      }
    }, f.contribution == null ? null : `+${fx(f.contribution, 1)}`, f.value != null && f.weight != null ? ` · ${f.value}×${f.weight}` : ""));
  }))(factorRows(sel))) : null, (sel.addressable_cells || []).filter(c => c && c.subcap_id).length ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: ".04em",
      color: "var(--z-muted)",
      marginBottom: 4
    }
  }, "Cells it addresses"), (sel.addressable_cells || []).filter(c => c && c.subcap_id).map(c => /*#__PURE__*/React.createElement("div", {
    key: c.subcap_id,
    style: {
      display: "flex",
      gap: 8,
      alignItems: "flex-start",
      padding: "5px 0",
      borderTop: "1px solid var(--z-sep)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "chip purple",
    style: {
      flexShrink: 0
    }
  }, c.subcap_id), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-dark)",
      fontWeight: 500
    }
  }, asText(c.name) || c.subcap_id), asText(c.feature_that_addresses_it) ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      lineHeight: 1.45
    }
  }, asText(c.feature_that_addresses_it)) : null), /*#__PURE__*/React.createElement("div", {
    className: "f-mono",
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      textAlign: "right",
      flexShrink: 0,
      whiteSpace: "nowrap"
    }
  }, num(c.current) == null ? null : `now ${fx(num(c.current), 1)}`, num(c.gap) == null ? null : ` · gap ${fx(num(c.gap), 1)}`)))) : null)) : null, discarded.length ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14,
      borderTop: "1px solid var(--z-sep)",
      paddingTop: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8,
      marginBottom: 6,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10.5,
      fontWeight: 700,
      letterSpacing: ".04em",
      color: "var(--z-dark)"
    }
  }, "Considered and set aside"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, discarded.length, " ", discarded.length === 1 ? "platform" : "platforms", ", each with the reason it is not ranked")), discarded.map((d, i) => /*#__PURE__*/React.createElement("div", {
    key: `${d.platform}-${i}`,
    style: {
      display: "flex",
      gap: 8,
      alignItems: "flex-start",
      padding: "6px 0",
      borderTop: i ? "1px solid var(--z-sep)" : 0
    }
  }, asText(d.platform) ? /*#__PURE__*/React.createElement("span", {
    className: "chip",
    style: {
      flexShrink: 0
    }
  }, asText(d.platform)) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0,
      fontSize: 11.5,
      color: "var(--z-body)",
      lineHeight: 1.55
    }
  }, asText(d.reason))))) : null, /*#__PURE__*/React.createElement(OvTrace, {
    section: "overview.opportunity",
    audience: audience
  }));
}

/* ── Top findings ─────────────────────────────────────────────────
   The card reads and maps its OWN section. It used to be handed a mapped
   array built in ClientOverview's body, which put the read above every
   boundary: one finding that arrived as null took `f.f_id` with it and the
   whole application unmounted, on a page where four other cards had nothing
   wrong with them. A card owns its read, so a card owns its failure. */
function TopFindingsCard({
  entity,
  openEvidence,
  audience
}) {
  const [openFinding, setOpenFinding] = useState(null);
  // The promoted findings, mapped onto the card's shape. This was a hardcoded
  // five-item array of fictional prose — "three production cores", a CTO
  // "ex-Wells Fargo", a CDO "ex-JPM" — rendered identically for every client,
  // whose evidence ids resolved against nothing, which is why the card's
  // "Evidence · click to view" list was always empty.
  const findings = (DMA.findingsFor(entity.id) || []).map(f => ({
    id: f.f_id,
    title: asText(f.title),
    theme: asText(f.theme),
    platforms: f.platform_chips || [],
    evidence: f.e_ids || [],
    what: asText(f.body),
    why: asText(f.rejected_alternative),
    // The drilldown's SO WHAT is the strategic-alignment argument — which of
    // the client's OWN stated objectives this finding bears on. It was
    // `asText(f.consequence)`: the face's 6–14-word consequence line printed
    // AGAIN under a heading that promises a decision, which is why every
    // drilldown read as generic. The consequence line stays on the face
    // (magnitude, below); the contract states alignment as prose or as
    // {score, statement} — asText unwraps either, never a raw dict — and the
    // stated score travels separately so the card can print it as data.
    so_what: asText(f.strategic_alignment),
    so_what_score: f.strategic_alignment && typeof f.strategic_alignment === "object" && isFinite(Number(f.strategic_alignment.score)) ? Number(f.strategic_alignment.score) : null,
    magnitude: asText(f.consequence),
    subcaps: f.linked_subcap_ids || []
  }));

  // Nothing to list is a STATE, not a blank panel. This card used to render
  // its header, the count 0 and then literally nothing below the rule — a
  // void that reads as "loading" or as a bug, when the API has already said
  // what happened and why in the section envelope.
  if (!findings.length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "card flush"
    }, /*#__PURE__*/React.createElement("div", {
      className: "card-head"
    }, /*#__PURE__*/React.createElement("h3", null, "Top findings"), /*#__PURE__*/React.createElement("span", {
      className: "b"
    }, "Nothing to show")), /*#__PURE__*/React.createElement("div", {
      className: "card-body"
    }, /*#__PURE__*/React.createElement(SectionEmpty, {
      section: "overview.findings",
      absent: "No findings section promoted for this run.",
      empty: "The findings section promoted with no findings in it."
    })));
  }
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
    }, f.so_what || "The run states no strategic-alignment argument for this finding."), f.so_what && f.so_what_score != null ? /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        marginTop: 4
      }
    }, "alignment to stated objectives \xB7 ", f.so_what_score) : null), f.evidence.length > 0 ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
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
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "0 16px 12px"
    }
  }, /*#__PURE__*/React.createElement(OvTrace, {
    section: "overview.findings",
    audience: audience
  })));
}

/* ── Leadership panel + Clay enrichment ─────────────────────────── */
function LeadershipPanel({
  audience
}) {
  /* Contact detail is PROMOTED, not fetched — and revealed, not shown.
      Clay runs in the PRODUCER's session at synthesis time; its output is
     registered as evidence and written into the roster item (migration 0018),
     so by the time this panel renders the contact route is already a column
     in Postgres, arriving in the same read as the name. The app never calls
     Clay while serving (invariant 1) — which is exactly why the "Enrich via
     Clay" button can exist at all: it is a curtain over data the run already
     holds, not a request. A click flips component state, waits a beat so the
     reveal reads as an action, and shows what was stored. A person the
     producer found no route for gets a transient toast and the curtain comes
     down entirely — a box left standing would promise a route the run cannot
     produce.
      WHAT PERSISTS, and what does not. Owner, 2026-08-15: "When I click enrich
     via Clay, this is not persisted across sessions to me as a user such that
     I never click it again." Correct, and the original "nothing persists" was
     the wrong call for a reader: the curtain reads as a request the first time
     and as busywork every time after, over data the run already holds.
      A REVEAL now persists, per browser and per entity. It is a view
     preference, not content — invariant 2 is untouched, nothing is written
     anywhere the serving tier can see, and a customer-audience payload carries
     no contact columns at all, so a restored reveal on that audience uncovers
     an empty box rather than a leak.
      A "no route" result does NOT persist, deliberately. It is a statement about
     what THIS run found, and freezing it would keep a curtain down over a
     contact a later run fills. Absence is recomputed; only the reader's
     decision is remembered. */
  const {
    pushToast
  } = useApp();
  /* Per-entity so a reveal on one client never uncovers another's roster —
     the same identity discipline the registry reads follow. */
  const revealKey = (() => {
    const m = String(typeof window !== "undefined" && window.location.hash || "").match(/#\/clients\/([^/?]+)/);
    return m ? `dma.reveal.${decodeURIComponent(m[1])}` : null;
  })();
  const [revealed, setRevealed] = useState(() => {
    // Restored on first render rather than in an effect: an effect would paint
    // the closed curtain first and reopen it, which reads as a flicker on
    // exactly the surface this is meant to stop nagging the reader about.
    if (!revealKey || typeof localStorage === "undefined") return {};
    try {
      const ids = JSON.parse(localStorage.getItem(revealKey) || "[]");
      return Array.isArray(ids) ? Object.fromEntries(ids.map(id => [id, "done"])) : {};
    } catch (e) {
      return {}; // corrupt storage is not worth a broken panel
    }
  }); // id → "loading" | "done" | "none"
  const remember = id => {
    if (!revealKey || typeof localStorage === "undefined") return;
    try {
      const ids = new Set(JSON.parse(localStorage.getItem(revealKey) || "[]"));
      ids.add(id);
      localStorage.setItem(revealKey, JSON.stringify([...ids]));
    } catch (e) {/* private mode, quota — the reveal still works this session */}
  };
  const [enrichingAll, setEnrichingAll] = useState(false);
  const roster = DMA.LEADERSHIP || [];
  // One route shape for both worlds: live rows carry the promoted email /
  // linkedin_url / phone columns; the fixture's simulated enrichment carries
  // `clay.{email,linkedin}`. Whichever exists is what the reveal shows.
  const routeOf = ex => ({
    email: ex.email || ex.clay && ex.clay.email || null,
    linkedin: ex.linkedin_url || (ex.clay && ex.clay.linkedin ? `https://${ex.clay.linkedin}` : null),
    phone: ex.phone || null
  });
  const hasRoute = ex => {
    const r = routeOf(ex);
    return !!(r.email || r.linkedin || r.phone);
  };
  // An entry with neither a name nor a role. The adapter files it as a gap
  // because it has no name; a gap the producer meant carries the TITLE of the
  // role that is missing, so an entry with neither is not a gap, it is a value
  // this page cannot read. It is never counted as one and never enriched.
  const isUnreadable = ex => !ex.title && (!ex.name || ex.name === "-");
  const enrich = (ex, quiet) => {
    setRevealed(m => ({
      ...m,
      [ex.id]: "loading"
    }));
    setTimeout(() => {
      if (hasRoute(ex)) {
        setRevealed(m => ({
          ...m,
          [ex.id]: "done"
        }));
        remember(ex.id);
      } else {
        if (!quiet) pushToast(`No stored contact route for ${ex.name}`, "warn");
        setRevealed(m => ({
          ...m,
          [ex.id]: "none"
        }));
      }
    }, 400);
  };
  const enrichable = roster.filter(x => !x.gap_flag && !isUnreadable(x));
  const enrichAll = () => {
    const targets = enrichable.filter(x => revealed[x.id] !== "done");
    if (!targets.length) return;
    setEnrichingAll(true);
    targets.forEach((ex, i) => setTimeout(() => enrich(ex, true), i * 180));
    // One toast for the whole sweep — a stack of per-person "no route"
    // toasts is noise; one naming the misses is an answer.
    setTimeout(() => {
      const missing = targets.filter(x => !hasRoute(x)).map(x => x.name);
      if (missing.length) pushToast(`No stored contact route for ${missing.join(" · ")}`, "warn");
      setEnrichingAll(false);
    }, targets.length * 180 + 450);
  };
  const doneCount = enrichable.filter(x => revealed[x.id] === "done").length;

  // An empty roster used to render the header, an "Enrich all" button over
  // nobody, and a footer asserting "No critical role gaps in the promoted
  // roster" — a clean bill of health derived from an absence of evidence,
  // which is the fabricated zero-assertion this whole app exists to refuse.
  // Nothing promoted means nothing is claimed, and the API's own account of
  // the absence is what the card shows instead.
  if (!roster.length) {
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
    }), " Leadership panel"), /*#__PURE__*/React.createElement("span", {
      className: "b"
    }, "Nothing to show")), /*#__PURE__*/React.createElement("div", {
      className: "card-body"
    }, /*#__PURE__*/React.createElement(SectionEmpty, {
      section: "overview.leadership",
      absent: "No leadership section promoted for this run.",
      empty: "The leadership section promoted with no named executives in it."
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-muted)",
        lineHeight: 1.55,
        marginTop: 8
      }
    }, "With no roster, no role can be called present and none can be called missing.")));
  }
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
  }), " Leadership panel"), audience !== "customer" ? /*#__PURE__*/React.createElement("button", {
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
  }), " Enrich all via Clay")) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "8px 16px 14px"
    }
  }, roster.map(ex => {
    const state = revealed[ex.id]; // undefined | "loading" | "done" | "none"
    const route = routeOf(ex);
    // A row with neither a name nor a title says nothing. The adapter
    // reads "no name" as a role gap, which is right for a producer's
    // deliberate gap row — those carry the title of the missing role —
    // and wrong for an entry that arrived as a string or a number, where
    // every field is undefined. Rendering that as "critical role absent"
    // invents a finding out of a malformed field. Named instead.
    if (isUnreadable(ex)) {
      return /*#__PURE__*/React.createElement("div", {
        key: ex.id,
        style: {
          display: "flex",
          gap: 10,
          padding: "12px 0",
          borderBottom: "1px solid var(--z-sep)"
        },
        "data-unreadable-roster-row": ex.id
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          width: 36,
          height: 36,
          borderRadius: 18,
          background: "var(--z-sep)",
          color: "var(--z-muted)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 14,
          flexShrink: 0
        }
      }, "?"), /*#__PURE__*/React.createElement("div", {
        style: {
          flex: 1,
          minWidth: 0,
          fontSize: 11.5,
          color: "var(--z-muted)",
          lineHeight: 1.5
        }
      }, "This roster entry carries neither a name nor a role, so it states no person and no gap. It is shown rather than dropped: the roster promoted with it in."));
    }
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
    }, "-") : state === "done" && route.linkedin ? /*#__PURE__*/React.createElement("a", {
      href: route.linkedin,
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
    }, "NEW \xB7 ", ex.tenure_months, " mo") : ex.tenure_months != null ? /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, "\xB7 ", Math.round(ex.tenure_months / 12), " yr") : null), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        marginTop: 4,
        lineHeight: 1.5
      }
    }, ex.background), ex.gap_flag || audience === "customer" || state === "none" ? null : state === "done" ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 8,
        padding: "8px 10px",
        background: "var(--z-ice)",
        border: "1px solid rgba(39,187,175,.35)",
        borderRadius: 6
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        flexDirection: "column",
        gap: 4
      }
    }, route.email ? /*#__PURE__*/React.createElement("a", {
      href: `mailto:${route.email}`,
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
    }), " ", route.email) : null, route.linkedin ? /*#__PURE__*/React.createElement("a", {
      href: route.linkedin,
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
    }), " ", String(route.linkedin).replace(/^https?:\/\/(www\.)?/, "")) : null, route.phone ? /*#__PURE__*/React.createElement("a", {
      href: `tel:${String(route.phone).replace(/[^+\d]/g, "")}`,
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
      name: "phone",
      size: 11
    }), " ", route.phone) : null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        marginTop: 2
      }
    }, "via Clay", ex.enriched_at ? ` · stored ${ex.enriched_at}` : ""))) : state === "loading" ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 8,
        padding: "8px 10px",
        background: "var(--z-lav)",
        border: "1px solid var(--z-sep)",
        borderRadius: 6
      }
    }, /*#__PURE__*/React.createElement("div", {
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
    }), /*#__PURE__*/React.createElement("span", null, "Checking stored Clay enrichment\u2026"))) : /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 8,
        padding: "8px 10px",
        background: "var(--z-bg)",
        border: "1px solid var(--z-sep)",
        borderRadius: 6
      }
    }, /*#__PURE__*/React.createElement("div", {
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
        padding: "3px 8px",
        flexShrink: 0
      },
      onClick: () => enrich(ex)
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "sparkle",
      size: 10
    }), " Enrich via Clay")))));
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
  }), (() => {
    // Read from THIS card's roster, the one rendered above — the line is
    // a statement about the rows on screen, and it is only reachable
    // when there are rows (the empty branch returns above).
    const gaps = roster.filter(x => x.gap_flag && !isUnreadable(x));
    if (gaps.length) {
      const titles = gaps.map(g => g.title || g.domain).filter(Boolean);
      return /*#__PURE__*/React.createElement("span", null, "Critical roles flagged:", " ", /*#__PURE__*/React.createElement("strong", {
        style: {
          color: "var(--z-below)"
        }
      }, titles.length ? `${titles.join(" · ")} absent` : `${gaps.length} absent`), " ", "from evidence");
    }
    const st = (DMA.LIVE_ENRICHMENT || {}).leadership || null;
    const expected = st && st.thin_below != null && isFinite(Number(st.thin_below)) ? Number(st.thin_below) : null;
    const namedRows = roster.filter(x => !x.gap_flag && !isUnreadable(x)).length;
    if (expected != null && namedRows < expected) {
      const short = expected - namedRows;
      return /*#__PURE__*/React.createElement("span", null, namedRows, " of the ", expected, " leadership seats this assessment reads for", namedRows === 1 ? " is named" : " are named", " on this run;", " ", short === 1 ? "the other one is" : `the other ${short} are`, " not established from a citable source, so no seat below is called present or absent.");
    }
    if (expected != null) {
      return /*#__PURE__*/React.createElement("span", null, "No critical role gaps in the promoted roster \u2014 ", namedRows, " of ", expected, " seats named.");
    }
    // No expected count stated: say what is here, claim nothing about
    // what is not. Silence about the denominator is not a clean roster.
    return /*#__PURE__*/React.createElement("span", null, namedRows, " ", namedRows === 1 ? "executive" : "executives", " named on this run;", " ", "it states no expected roster size, so no seat can be called missing.");
  })(), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), doneCount ? /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-mid)",
      fontWeight: 600
    }
  }, "\u2713 ", doneCount, " of ", enrichable.length, " enriched") : null), /*#__PURE__*/React.createElement(EnrichmentFlag, {
    s: (DMA.LIVE_ENRICHMENT || {}).leadership,
    what: "roster",
    audience: audience
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "0 16px 12px"
    }
  }, /*#__PURE__*/React.createElement(OvTrace, {
    section: "overview.leadership",
    audience: audience
  })));
}

/* ── Financial trajectory · D1's own copy ───────────────────────────
   The shared card (cards-data-driven.jsx) prints the regulator through the
   `.chip` class — the right weight for the fixture's "FCA", three mono
   characters, but a credit union's statutory regulator is a full clause
   ("National Credit Union Administration (share insurance); Illinois
   Department of …"), and a chip that long renders as a highlighted block
   that outweighs the chart above it. It also carries the chip's
   cursor:pointer while clicking it does nothing — the page's one dead
   control. The strip is context, not a claim and not a drilldown: the
   prototype's visual weight is small muted text with the regulator in mono,
   nothing highlighted, nothing clickable — so that is what D1 renders. */
function FinancialTrajectoryD1({
  entity,
  audience
}) {
  const f = DMA.financialsFor(entity.id);
  if (!f || !(f.fy || []).length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "card flush"
    }, /*#__PURE__*/React.createElement("div", {
      className: "card-head"
    }, /*#__PURE__*/React.createElement("div", {
      className: "row"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "money",
      size: 14
    }), /*#__PURE__*/React.createElement("h3", null, "Financial trajectory")), /*#__PURE__*/React.createElement("span", {
      className: "b"
    }, absenceBadge("overview.financial_series"))), /*#__PURE__*/React.createElement("div", {
      className: "card-body"
    }, /*#__PURE__*/React.createElement(SectionEmpty, {
      section: "overview.financial_series",
      absent: "No financial series promoted for this run.",
      empty: "The financial-series section promoted with no years in it."
    })));
  }
  const values = (f.total_assets || []).filter(v => v != null);
  const maxA = values.length ? Math.max(...values) : 1;
  const fte = (f.employees || [])[(f.employees || []).length - 1];
  const counts = [f.branches != null ? `${f.branches} branches` : null, fte != null ? `${fte.toLocaleString()} FTE` : null].filter(Boolean).join(" · ");
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
    title: [y, f.total_assets[i] != null ? `$${f.total_assets[i]}${f.unit}` : null, f.nim_pct[i] != null ? `NIM ${f.nim_pct[i]}%` : null].filter(Boolean).join(" · ")
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      fontWeight: 600,
      color: "var(--z-dark)"
    }
  }, f.total_assets[i] != null ? `$${f.total_assets[i]}${f.unit}` : null), /*#__PURE__*/React.createElement("div", {
    style: {
      width: "100%",
      height: `${(f.total_assets[i] || 0) / maxA * 80}px`,
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
  }, f.regulator ? /*#__PURE__*/React.createElement("span", {
    className: "f-mono",
    style: {
      fontSize: 10
    }
  }, f.regulator) : null, f.geography ? /*#__PURE__*/React.createElement("span", null, f.geography) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), counts ? /*#__PURE__*/React.createElement("span", {
    style: {
      flexShrink: 0
    }
  }, counts) : null), /*#__PURE__*/React.createElement(OvTrace, {
    section: "overview.financial_series",
    audience: audience
  })));
}

/* ── Thought leadership ───────────────────────────────────────────
   Three to five entries, not three. The grid was `g3` — three hard columns —
   so a fourth and fifth entry landed in a ragged second row of two, which is
   what made three look like the cap even though nothing here enforced one.
   `auto-fit` with a readable floor lays 3, 4 or 5 out the same way, and the
   heading counts what arrived rather than implying a window.

   WHICH entries are chosen, and how they are weighted towards positions
   Zennify can act on, is the producer's judgement and stays there. This
   renders what the run promoted, in the order it promoted it. */
function ThoughtLeadershipPanel() {
  // `audience` decides how much of the enrichment limit a reader is told: the
  // customer gets the limit on the reading, an internal reader also gets which
  // sources reached it. Read from context rather than threaded through props —
  // passing it in was a ReferenceError the card boundary caught, which is the
  // boundary working and the change still being wrong.
  const {
    openEvidence,
    openSubcap,
    audience
  } = useApp();
  const entries = DMA.THOUGHT_LEADERSHIP || [];
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
  }, entries.length ? `${entries.length} named executive${entries.length === 1 ? "" : "s"}, in their own words` : "Nothing to show")), !entries.length ? /*#__PURE__*/React.createElement("div", {
    className: "card-body"
  }, /*#__PURE__*/React.createElement(SectionEmpty, {
    section: "overview.thought_leadership",
    absent: "No thought-leadership section promoted for this run.",
    empty: "The thought-leadership section promoted with no entries in it."
  })) : /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "g3"
  }, entries.map(tl => {
    /* `alignment` is the field the contract calls the most valuable
       thing on this card — a CONTRADICTS entry is the one that must
       never be filtered out — and it was adapted and never rendered.
       An executive quote that argues AGAINST the assessment reads as
       corroboration when its stance is invisible. */
    const al = tl.alignment && typeof tl.alignment === "object" ? tl.alignment : null;
    const stance = al ? String(al.value || "").toUpperCase() : null;
    const stanceTone = stance === "CONTRADICTS" ? "b-org" : stance === "EXTENDS" ? "b-purple" : "b-teal";
    return /*#__PURE__*/React.createElement("div", {
      key: tl.id,
      className: "card-tile",
      style: {
        padding: 14
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 6,
        gap: 6,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, String(tl.kind || tl.type || "SIGNAL").toUpperCase()), stance ? /*#__PURE__*/React.createElement("span", {
      className: `b ${stanceTone}`,
      title: al.clause || ""
    }, stance) : null, /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", {
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
    }, tl.title), tl.author ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        fontWeight: 600,
        color: "var(--z-mid)",
        marginBottom: 5
      }
    }, tl.author) : null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-body)",
        lineHeight: 1.55,
        fontStyle: "italic"
      }
    }, "\"", tl.excerpt, "\""), al && al.clause ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)",
        lineHeight: 1.5,
        marginTop: 6
      }
    }, al.clause) : null, (tl.subcaps || []).length || (tl.evidence || []).length ? /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 4,
        flexWrap: "wrap",
        marginTop: 8
      }
    }, (tl.subcaps || []).map(sid => /*#__PURE__*/React.createElement("button", {
      key: sid,
      className: "chip f-mono",
      style: {
        fontSize: 9,
        cursor: "pointer",
        border: 0
      },
      title: `Open ${sid} in the heatmap`,
      onClick: () => openSubcap && openSubcap(sid)
    }, sid)), (tl.evidence || []).map(eid => {
      const e = DMA.getEvidence(eid);
      return e ? /*#__PURE__*/React.createElement("button", {
        key: eid,
        className: `tier-chip tier-${e.tier}`,
        style: {
          cursor: "pointer",
          border: 0
        },
        title: `${e.title || eid} · ${e.source_pretty || ""}`,
        onClick: () => openEvidence && openEvidence(eid)
      }, eid) : /*#__PURE__*/React.createElement("span", {
        key: eid,
        className: "chip muted",
        title: "cited id - not in this run's served evidence"
      }, eid);
    })) : null, /*#__PURE__*/React.createElement("div", {
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
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        minWidth: 0
      }
    }, tl.author), /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), tl.url ? /*#__PURE__*/React.createElement("a", {
      href: `https://${tl.url}`,
      target: "_blank",
      rel: "noreferrer",
      style: {
        color: "var(--z-mid)",
        display: "inline-flex",
        alignItems: "center",
        gap: 3,
        whiteSpace: "nowrap",
        flexShrink: 0
      }
    }, "Open ", /*#__PURE__*/React.createElement(Icon, {
      name: "external",
      size: 10
    })) : null));
  }))), /*#__PURE__*/React.createElement(EnrichmentFlag, {
    s: (DMA.LIVE_ENRICHMENT || {}).thought_leadership,
    what: "entries",
    audience: audience
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "0 16px 12px"
    }
  }, /*#__PURE__*/React.createElement(OvTrace, {
    section: "overview.thought_leadership",
    audience: audience
  })));
}

/* ── How this assessment was evidenced ────────────────────────────────
   O10 `evidence_coverage` and O11 `ceilings`: 5 percentages, a five-tier
   histogram, three claim classes and 16 complete ceiling rows — zero nulls on
   all ten of their columns — promoted, served, and rendered on NO page of the
   application in either audience. `CoverageByPillarCard` and
   `CeilingEstimateCard` are both defined and exported in
   `cards-data-driven.jsx` and neither has a call site.

   They were removed from D1 on 2026-08-05 because they report on the
   ASSESSMENT's own workings rather than on the institution, and D7 Health is
   where that belongs. That reasoning is kept: they are restored BELOW the
   institution's content, under a heading that says what they are, rather than
   back among the findings. If D7 grows a mount, this band is the thing to
   move, not to copy.

   Coverage is served to BOTH audiences (the producer's redaction kept it);
   ceilings are internal — the customer payload carries `data: null` for that
   section, and the card is gated on audience as well, because default-deny is
   not a thing to infer from an absence.

   The ceiling card here is D1's own rather than the shared one for a single
   reason: `ceilings[].ceiling` speaks the assessment's `M1…M5` LEVEL
   vocabulary, not `band_t`, and the shared card both fails to resolve the
   token (`adaptUncertainty` yields null, so the row renders no figure at all)
   and then colours the figure on its own thresholds — `<= 2` red — which is a
   second score→colour rule beside the resolver. Invariant 7 allows exactly
   one. Here the token resolves to its level and the level goes through
   `DMA.helpers.maturityHex`, the same resolver the pillar bars use. */
function OvCeilingCard({
  entity,
  audience
}) {
  const [open, setOpen] = useState(null);
  const {
    openEvidence
  } = useApp();
  if (String(audience || "").toLowerCase() === "customer") return null;
  const u = DMA.uncertaintyFor(entity.id);
  const rows = u ? Object.entries(u) : [];
  if (!rows.length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "card flush"
    }, /*#__PURE__*/React.createElement("div", {
      className: "card-head"
    }, /*#__PURE__*/React.createElement("div", {
      className: "row"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "stack",
      size: 14
    }), /*#__PURE__*/React.createElement("h3", null, "Capability ceiling & uncertainty"))), /*#__PURE__*/React.createElement("div", {
      className: "card-body"
    }, /*#__PURE__*/React.createElement(SectionEmpty, {
      section: "overview.ceilings",
      absent: "No ceiling estimates promoted for this run.",
      empty: "The ceilings section promoted with no rows in it."
    })));
  }
  /* `M3` is maturity LEVEL three, which is the score 3.0 on the same 1–5 axis
     every other figure on this page uses. It is resolved here and nowhere
     else, and the four-value band vocabulary is unchanged by it: the level
     goes to the resolver and the resolver names the band. */
  const levelOf = d => {
    if (d.ceiling != null && isFinite(Number(d.ceiling))) return Number(d.ceiling);
    const m = String(d.ceiling_stated == null ? "" : d.ceiling_stated).trim().match(/^M([1-5])(\.\d+)?$/i);
    return m ? Number(m[1] + (m[2] || "")) : null;
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "card flush"
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
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      lineHeight: 1.5,
      marginBottom: 8
    }
  }, "The highest maturity the evidence on this run could support per category, with the artefact that would lift it. A ceiling is a research backlog, not a score."), rows.map(([cat, d]) => {
    const lvl = levelOf(d);
    const band = d.band != null && isFinite(Number(d.band)) ? Number(d.band) : null;
    const lo = lvl == null || band == null ? null : Math.max(1, lvl - band);
    const hi = lvl == null || band == null ? null : Math.min(5, lvl + band);
    const pct = v => (v - 1) / 4 * 100;
    const isOpen = open === cat;
    const ev = (d.evidence || []).map(id => DMA.getEvidence(id)).filter(Boolean);
    const name = d.category_name || (DMA.getCategory(cat) || {}).name || null;
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
        gridTemplateColumns: "150px 1fr 78px 16px",
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
        color: "var(--z-body)",
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "f-mono"
    }, cat), name ? ` ${name}` : ""), /*#__PURE__*/React.createElement("div", {
      style: {
        position: "relative",
        height: 8,
        background: "var(--z-sep)",
        borderRadius: 4
      },
      title: lvl == null ? `${cat} ceiling not stated` : lo == null ? `Ceiling ${fx(lvl, 1)}` : `Ceiling ${fx(lvl, 1)} · band ${fx(lo, 1)}–${fx(hi, 1)}`
    }, lo == null ? null : /*#__PURE__*/React.createElement("div", {
      style: {
        position: "absolute",
        left: `${pct(lo)}%`,
        width: `${pct(hi) - pct(lo)}%`,
        top: 0,
        bottom: 0,
        background: "rgba(124,93,201,.25)",
        borderRadius: 4
      }
    }), lvl == null ? null : /*#__PURE__*/React.createElement("div", {
      style: {
        position: "absolute",
        left: `calc(${pct(lvl)}% - 4px)`,
        top: -1,
        width: 8,
        height: 10,
        borderRadius: 2,
        background: DMA.helpers.maturityHex(lvl)
      }
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        fontWeight: 600,
        textAlign: "right",
        whiteSpace: "nowrap",
        color: lvl == null ? "var(--z-muted)" : DMA.helpers.maturityHex(lvl)
      }
    }, lvl == null ? d.ceiling_stated ? String(d.ceiling_stated) : null : /*#__PURE__*/React.createElement(React.Fragment, null, d.ceiling_stated ? `${d.ceiling_stated} · ` : "", fx(lvl, 1), band == null ? null : /*#__PURE__*/React.createElement("span", {
      style: {
        color: "var(--z-muted)",
        fontWeight: 400
      }
    }, " \xB1", band))), /*#__PURE__*/React.createElement(Icon, {
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
    }, lvl == null ? null : /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)",
        marginBottom: 6
      }
    }, "Ceiling band \xB7 ", DMA.helpers.maturityLabel(lvl)), d.rationale ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        lineHeight: 1.55,
        marginBottom: 8
      }
    }, d.rationale) : null, d.limiting_absence ? /*#__PURE__*/React.createElement("div", {
      style: {
        background: "var(--z-lav)",
        borderLeft: "3px solid var(--z-dpur)",
        borderRadius: "0 6px 6px 0",
        padding: "8px 12px",
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-dpur)",
        textTransform: "uppercase",
        marginBottom: 2
      }
    }, "What would lift it"), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        lineHeight: 1.55
      }
    }, d.limiting_absence)) : null, d.modifiers && d.modifiers.length ? /*#__PURE__*/React.createElement("div", {
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
        color: "var(--z-body)",
        lineHeight: 1.5
      }
    }, m))) : null, d.claim || d.confidence ? /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 6,
        marginBottom: 8,
        flexWrap: "wrap"
      }
    }, d.claim ? /*#__PURE__*/React.createElement("span", {
      className: "b b-muted"
    }, d.claim) : null, d.confidence ? /*#__PURE__*/React.createElement("span", {
      className: "b b-muted"
    }, d.confidence) : null) : null, ev.length ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        marginBottom: 4
      }
    }, "Evidence \xB7 click to open"), /*#__PURE__*/React.createElement("div", {
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
        textAlign: "left"
      }
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
    }, e.source_pretty || e.title), /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-r",
      size: 11,
      style: {
        color: "var(--z-mid)"
      }
    }))))) : null) : null);
  }), /*#__PURE__*/React.createElement(OvTrace, {
    section: "overview.ceilings",
    audience: audience
  })));
}

/* The coverage card's own read, wrapped so the section's reasoning trace and
   its denominator definition travel with the five percentages. The bars
   themselves are `CoverageByPillarCard`, which is correct as written — a
   coverage percentage against a gate is a pass/fail, not a maturity band, so
   its colours are not the resolver's business. */
function OvCoverageBand({
  entity,
  audience
}) {
  const c = DMA.coverageFor(entity.id);
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(CoverageByPillarCard, {
    entity: entity
  }), c && c.denominator_definition ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      lineHeight: 1.5,
      padding: "8px 2px 0"
    }
  }, c.denominator_definition) : null, c && c.note ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      lineHeight: 1.5,
      padding: "6px 2px 0"
    }
  }, c.note) : null, /*#__PURE__*/React.createElement(OvTrace, {
    section: "overview.evidence_coverage",
    audience: audience
  }));
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
    },
    title: typeof v === "string" ? v : undefined
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
  // An entry that is not an object is not an insight card, and it must not be
  // scored, filed under a pillar or counted as a "Watch" item — every one of
  // those is a judgement about a card nobody can read. They are held back
  // here and named at the end of the page, each still rendered in place
  // through its own boundary.
  const readable = [],
    unreadable = [];
  for (const c of cards) (c && typeof c === "object" ? readable : unreadable).push(c);
  const groups = groupReadableInsights(readable, mode);
  if (unreadable.length) {
    groups.push({
      key: "__unreadable",
      label: "Could not be read",
      color: "org",
      desc: `${unreadable.length} entr${unreadable.length === 1 ? "y" : "ies"} in the ` + "promoted list is not an insight-card object",
      items: unreadable.map((c, i) => ({
        c,
        p: {
          score: -1,
          tier: 0,
          tierLabel: "unreadable",
          tierColor: "org",
          key: i
        }
      }))
    });
  }
  return groups;
}
function groupReadableInsights(cards, mode) {
  const withP = cards.map(c => ({
    c,
    p: DMA.insightPriority(c)
  }));
  // Sorting runs ABOVE every card boundary — it walks the whole list before
  // one card renders — so a card whose id is missing must not be able to throw
  // here: `undefined.localeCompare` took the entire page, and the tie-break it
  // was doing is only a stable order. Ordering by an absent id as the empty
  // string states nothing about the card; it just puts it somewhere fixed.
  const byScore = (a, b) => b.p.score - a.p.score || String(a.c && a.c.id || "").localeCompare(String(b.c && b.c.id || ""));
  if (mode === "pillar") {
    const groups = DMA.PILLARS.map(p => ({
      key: p.id,
      label: `${p.id} · ${p.short}`,
      color: "purple",
      desc: p.name,
      items: withP.filter(x => x.c.pillar === p.id).sort(byScore)
    })).filter(g => g.items.length);
    // A card with no pillar and no cell to derive one from is named as such,
    // not filed under a pillar it was never assigned to.
    const orphans = withP.filter(x => !x.c.pillar).sort(byScore);
    if (orphans.length) {
      groups.push({
        key: "__nopillar",
        label: "No pillar stated",
        color: "org",
        desc: "the run did not state a pillar and the card cites no cell to derive one from",
        items: orphans
      });
    }
    return groups;
  }
  if (mode === "theme") {
    // "Other" was doing two different jobs: a card the producer themed as
    // "Other", and a card with NO theme at all. Every Baxter card was the
    // second kind, so the theme lens showed one bucket called Other and looked
    // broken. Untriaged cards now group by their pillar with the reason stated,
    // so the lens still clusters usefully while naming what is missing.
    // An insight card has no theme of its own in any contract — the adapter
    // DERIVES it from the O6 finding that shares the card's cell, so a card
    // still without one is a card no finding touches.
    const themed = withP.filter(x => x.c.theme);
    const unthemed = withP.filter(x => !x.c.theme);
    const groups = [...new Set(themed.map(x => x.c.theme))].map(t => {
      const items = themed.filter(x => x.c.theme === t).sort(byScore);
      const why = [...new Set(items.map(x => x.c.theme_source).filter(Boolean))];
      return {
        key: t,
        label: t,
        color: "purple",
        desc: `${items.length} card${items.length === 1 ? "" : "s"}` + (why.length ? ` · themed by the ${why.join(" / ")}` : ""),
        items
      };
    }).sort((a, b) => b.items[0].p.score - a.items[0].p.score);
    if (unthemed.length) {
      for (const p of DMA.PILLARS) {
        const items = unthemed.filter(x => x.c.pillar === p.id).sort(byScore);
        if (items.length) {
          groups.push({
            key: `__untheme-${p.id}`,
            label: `${p.id} · ${p.short} · no theme derivable`,
            color: "org",
            desc: `${items.length} card${items.length === 1 ? "" : "s"} whose cells no top finding touches — grouped by pillar instead`,
            items
          });
        }
      }
      const loose = unthemed.filter(x => !x.c.pillar).sort(byScore);
      if (loose.length) {
        groups.push({
          key: "__untheme-none",
          label: "No theme and no pillar",
          color: "org",
          desc: "these cards cite no cell, so neither a pillar nor a finding's theme can be derived",
          items: loose
        });
      }
    }
    return groups;
  }
  const defs = [{
    key: 1,
    label: "Act now",
    color: "below",
    desc: "Critical gaps + high-confidence, actionable opportunities - lead with these"
  }, {
    key: 2,
    label: "Plan next",
    color: "org",
    desc: "Opportunities to sequence into the roadmap"
  }, {
    key: 3,
    label: "Watch",
    color: "teal",
    desc: "Stable or monitoring items - no immediate action needed"
  }];
  return defs.map(d => ({
    ...d,
    items: withP.filter(x => x.p.tier === d.key).sort(byScore)
  })).filter(g => g.items.length);
}

/* One insight card's face. Its own component so React invokes it inside the
   boundary that wraps it — see renderCard. */
function InsightTile({
  c,
  p,
  groupBy,
  onOpen
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: `ic ${c.flag.toLowerCase()}`,
    onClick: () => onOpen(c.id)
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
    // An entry that is not a card cannot answer a filter question. It is kept
    // rather than dropped: dropping it would hide a malformed payload behind a
    // count that looks right, and groupInsights names it at the foot instead.
    if (!c || typeof c !== "object") return true;
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
  // Counted over the cards that ARE cards. A tier is a reading of a card's
  // flag and confidence; an entry with neither cannot be read into one, and
  // adding it to WATCH would be a count of something nobody assessed.
  const readableCards = DMA.INSIGHT_CARDS.filter(c => c && typeof c === "object");
  const unreadableCount = DMA.INSIGHT_CARDS.length - readableCards.length;
  readableCards.forEach(c => tierCounts[DMA.insightPriority(c).tier]++);
  const filtersActive = flag !== "ALL" || pillar !== "ALL" || conf !== "ALL";

  // Each card renders inside its OWN boundary. This is the granularity that
  // matters on this page: the list is long, its items come straight from the
  // promoted payload, and until now one item with a title that was an object
  // (or a body that was null) threw during render and React unmounted the
  // WHOLE app — every card on this page, the chrome, the nav, the <body>.
  // One bad item now costs one tile.
  //
  // The tile is a COMPONENT, not a function called inline. An inline call runs
  // during THIS component's render — outside the boundary it was handed to —
  // so the throw would escape and the boundary would never see it. React must
  // be the one to invoke it.
  const renderCard = ({
    c,
    p
  }, i) => /*#__PURE__*/React.createElement(ItemBoundary, {
    key: c && c.id || `insight-${i}`,
    name: c && c.id || "an insight card"
  }, /*#__PURE__*/React.createElement(InsightTile, {
    c: c,
    p: p,
    groupBy: groupBy,
    onOpen: openInsight
  }));
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
  }, tierCounts[3], " WATCH"), unreadableCount ? /*#__PURE__*/React.createElement("span", {
    className: "b b-org",
    style: {
      marginLeft: 6
    },
    title: "entries in the promoted list that are not insight-card objects"
  }, unreadableCount, " UNREADABLE") : null)), /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => pushToast(`Exporting ${filtered.length} insight cards as PDF…`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Export PDF"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: () => pushToast("Add a note from any insight card - click a card to start", "success")
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
  }, filtered.length, " of ", DMA.INSIGHT_CARDS.length, " shown")), groups.length === 0 ? DMA.INSIGHT_CARDS.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "empty",
    style: {
      padding: 40
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "icon"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "insight",
    size: 20
  })), /*#__PURE__*/React.createElement("h3", null, "No insight cards for this run"), /*#__PURE__*/React.createElement(SectionEmpty, {
    section: "insights.insights",
    absent: "The insights section did not promote for this run.",
    empty: "The insights section promoted with no cards in it."
  })) : /*#__PURE__*/React.createElement("div", {
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
  }), /*#__PURE__*/React.createElement(CardBoundary, {
    name: "technology landscape"
  }, /*#__PURE__*/React.createElement("div", {
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
  }, !DMA.TECH_STACK.length ? /*#__PURE__*/React.createElement(SectionEmpty, {
    section: "techstack.techstack",
    absent: "No technology register promoted for this run, so this run states no landscape.",
    empty: "The technology section promoted with no rows in it."
  }) : /*#__PURE__*/React.createElement("div", {
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
  },
  /* Counts are computed from the register, never asserted — the
     Claimed tile carried a hardcoded 7 — and the Gaps tile names
     the products THIS client is actually missing rather than the
     fixture's four. */
  {
    label: "Claimed",
    count: DMA.TECH_STACK.filter(t => t.status === "CLAIMED").length,
    tone: "b-org",
    sub: "T4–T5 marketing",
    desc: "Marketing pages reference platforms not yet confirmed."
  }, {
    label: "Gaps",
    count: DMA.TECH_STACK.filter(t => t.status === "ABSENT").length,
    tone: "b-below",
    sub: "ABSENT confirmed",
    desc: DMA.TECH_STACK.filter(t => t.status === "ABSENT").map(t => t.name).filter(Boolean).slice(0, 4).join(" · ") || "No confirmed absences in the register."
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
  }, q.desc))))))));
}
Object.assign(window, {
  ClientOverview,
  ClientInsights,
  ScoreRing,
  SnapshotStrip,
  FirmographicsPanel,
  TopFindingsCard,
  LeadershipPanel,
  InsightTile,
  groupInsights
});