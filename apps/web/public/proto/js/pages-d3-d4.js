/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Client page — D4 Platform opportunity
   (heatmap moved to pages-d3-heatmap.jsx)

   The unit of recommendation on this surface is the L3 PLATFORM AREA and its
   L4 features — not a vendor brand. The page used to open with the static
   five-vendor catalogue (`DMA.PLATFORMS`: Salesforce / Databricks / Tableau /
   Twilio / nCino), score it from `entity.oss` through a vendor-alias fold, and
   filter every panel below by `r.platform === "SF"`. For a real client that
   produced five tiles reading "—", a readiness list of every recommendation's
   prerequisites under the heading "Readiness · Salesforce", and "No
   recommendations for this platform in this run" against eight promoted ones.
   Nothing on the page came from the run.

   So there are now two independent controls, each keyed on something the
   payload actually states:

     · the fit tiles ARE the promoted opportunity tiles — platform name,
       composite, factors, the cells each addresses — read, never re-ranked;
     · the area toggle selects an L3 area, taken from the recommendations'
       own `l3_area`, and scopes the gaps, the readiness rows and the
       recommendation list to it.

   The two cannot be joined: the opportunity tile carries a vendor name and no
   L3 area, and `platform_story.platforms[]` carries gaps and a story but — per
   the connector contract — no platform name at all. Rather than guess a
   pairing (a wrong vendor beside a recommendation is worse than none), each
   surface renders what it states, and the platform story is filed under the L3
   area ITS OWN GAP ROWS name.
   ═══════════════════════════════════════════════════════════════════════ */

function pfNum(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return isFinite(n) ? n : null;
}

/* Renderable text from a payload value.
   React throws on an object child (#31) and there is no error boundary, so one
   such value blanks the entire application — that is exactly how the
   recommendation drawer takes the page down today (it renders the
   `validation_gate` object raw). Nothing from the payload reaches JSX in this
   file without passing through here: an object is summarised from its own
   naming keys, never printed as JSON, and an unusable value becomes null so the
   surrounding code renders its absent state.

   It also raises the opening letter (`sentence`). Several promoted fields on
   this page are written as fragments — "with plans to increase our member
   base…" — and land under a heading where they read as sentences, so the
   page showed lowercase openings throughout. The connector refuses these at
   submit now, but a run already in the database still has to read properly.
   `sentence` leaves a deliberate lowercase name (nCino) alone. */
function pfText(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "string") return v ? sentence(v) : null;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(pfText).filter(Boolean).join(" · ") || null;
  if (typeof v === "object") {
    for (const k of ["statement", "text", "label", "name", "title", "value"]) {
      const t = pfText(v[k]);
      if (t) return t;
    }
    return null;
  }
  return String(v);
}

/* Evidence chips for a promoted id list.
   Fail-closed on evidence (invariant 4): an id that does not resolve in the
   run's served evidence renders as an unresolved token and is NOT clickable —
   a chip that opens an empty drawer reads as evidence that exists. */
function PlatformEvChips({
  ids,
  openEvidence,
  label
}) {
  const list = (ids || []).filter(Boolean);
  if (!list.length) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      flexWrap: "wrap",
      gap: 4,
      alignItems: "center"
    }
  }, label ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      color: "var(--z-muted)",
      letterSpacing: ".06em",
      textTransform: "uppercase"
    }
  }, label) : null, list.map(eid => {
    const e = DMA.getEvidence(eid);
    return e ? /*#__PURE__*/React.createElement("button", {
      key: eid,
      className: `tier-chip tier-${e.tier}`,
      style: {
        cursor: "pointer",
        border: 0
      },
      title: `${e.title || eid} · ${e.source_pretty || ""}`,
      onClick: ev => {
        ev.stopPropagation();
        openEvidence(eid);
      }
    }, eid) : /*#__PURE__*/React.createElement("span", {
      key: eid,
      className: "chip muted",
      title: "cited id \u2014 not in this run's served evidence"
    }, eid);
  }));
}

/* The L3 platform areas this run promoted, in the order the roadmap reaches
   them (earliest phase first). The area is the recommendation's own `l3_area`;
   an area is never invented and never renamed. */
function platformAreasOf(recs, storyPlatforms) {
  const order = [];
  const seen = {};
  const add = (area, phase) => {
    if (!area) return;
    if (seen[area] === undefined) {
      seen[area] = order.length;
      order.push({
        area,
        phase
      });
    } else if (phase != null) {
      const cur = order[seen[area]];
      if (cur.phase == null || Number(phase) < Number(cur.phase)) cur.phase = phase;
    }
  };
  for (const r of recs || []) add(r.l3, r.phase);
  // A platform story states its area only through its gap rows, so an area
  // that has a story but no recommendation still gets a tab rather than
  // leaving the story unreachable.
  for (const p of storyPlatforms || []) {
    for (const g of p.gaps || []) add(g.l3_area, null);
  }
  return order.slice().sort((a, b) => (pfNum(a.phase) === null ? 99 : Number(a.phase)) - (pfNum(b.phase) === null ? 99 : Number(b.phase))).map(x => x.area);
}

/* One readiness row per DISTINCT prerequisite across the selected area's
   recommendations, carrying which of them require it.

   Two things were wrong before. Every prerequisite of every recommendation was
   listed regardless of area (sixteen rows under one platform heading), and the
   list was keyed by `q.cell || q.condition` — so the five recommendations that
   each require P4C3 produced five rows with the same React key and one shared
   open state: clicking any of them expanded all five.

   A cell threshold and a text condition are different shapes, so they are kept
   apart here rather than flattened into one row that renders the same string
   twice. P4C3 ≥ 2.0 and P4C3 ≥ 2.5 are DIFFERENT prerequisites with different
   verdicts, so the key carries the minimum — deduping on the cell alone would
   silently drop the stricter of the two. */
function areaPrereqs(recs) {
  const byKey = new Map();
  for (const r of recs || []) {
    for (const q of r.prerequisites || []) {
      if (!q || typeof q !== "object") continue;
      const cell = q.cell || null;
      const cond = q.condition || null;
      if (!cell && !cond) continue;
      const min = pfNum(q.minimum);
      const key = cell ? `cell:${cell}:${min === null ? "" : min}` : `cond:${cond}`;
      const row = byKey.get(key) || {
        key,
        kind: cell ? "cell" : "condition",
        cell,
        condition: cond,
        min,
        current: pfNum(q.current),
        verdict: q.verdict || null,
        basis: q.basis || null,
        note: q.note || null,
        recs: []
      };
      if (!row.recs.includes(r.id)) row.recs.push(r.id);
      byKey.set(key, row);
    }
  }
  return [...byKey.values()].sort((a, b) => a.kind === b.kind ? 0 : a.kind === "cell" ? -1 : 1);
}

/* MET / NOT MET as the run states it. The verdict used to be collapsed to a
   boolean and re-labelled "PARTIAL", which is a word no payload contains — the
   run says "NOT MET". Where no verdict was stated but both figures were, the
   comparison is computed and marked as computed. */
function prereqVerdict(p) {
  if (p.verdict) return {
    text: String(p.verdict),
    met: String(p.verdict).toUpperCase() === "MET",
    computed: false
  };
  if (p.min !== null && p.current !== null) {
    const met = p.current >= p.min;
    return {
      text: met ? "MET" : "NOT MET",
      met,
      computed: true
    };
  }
  return null;
}

/* ── D4 Platform opportunity ──────────────────────────────────────── */
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
    openSubcap,
    pushToast
  } = useApp();
  const recs = DMA.recsFor(entity.id) || [];
  const story = DMA.platformStoryFor(entity.id) || null;
  const opportunity = DMA.opportunityFor(entity.id) || null;
  const storyPlatforms = story && story.platforms || [];
  const areas = platformAreasOf(recs, storyPlatforms);

  // The route parameter only wins if the run promoted that area; a stale link
  // must not select a tab that does not exist and blank the page below.
  const routeArea = route.params.platform && areas.includes(route.params.platform) ? route.params.platform : null;
  const [areaSel, setAreaSel] = useState(routeArea);
  const area = areaSel && areas.includes(areaSel) ? areaSel : areas[0] || null;
  const [openPrereq, setOpenPrereq] = useState(null);
  const [openTile, setOpenTile] = useState(null);
  useEffect(() => {
    setIpSurface("platform_story");
    setIpContext({
      entity,
      platform: area
    });
  }, [area, entity?.id]);
  const oss = entity.oss || {};
  const tiles = (opportunity && opportunity.tiles || []).slice().sort((a, b) => (pfNum(a.rank) === null ? 99 : Number(a.rank)) - (pfNum(b.rank) === null ? 99 : Number(b.rank)));
  const areaRecs = recs.filter(r => r.l3 === area).sort((a, b) => String(a.phase || "").localeCompare(String(b.phase || "")) || String(a.id).localeCompare(String(b.id)));

  // The promoted gap rows for this area, with the story that argues for them.
  // Each row states its own cell, score, peer basis, L4 feature, catalogue path
  // and evidence — none of which the old generic subcap scan carried.
  const areaGaps = [];
  const areaStories = [];
  for (const p of storyPlatforms) {
    const rows = (p.gaps || []).filter(g => g.l3_area === area);
    if (!rows.length) continue;
    areaGaps.push(...rows);
    if (pfText(p.story_md)) areaStories.push(p.story_md);
  }
  // Only render the peer and gap columns when at least one row states a peer
  // figure. Before, every row printed "−-2.5": a unary minus prepended to an
  // already-negative difference, computed against a peer median that does not
  // exist for these cells.
  const anyPeer = areaGaps.some(g => pfNum(g.peer_score) !== null);

  /* Which area a platform tile drives. The tiles rank PLATFORMS; everything
     below the tiles is scoped by AREA — so a tile click expanded a breakdown
     and left the whole page beneath it unchanged, which reads as a dead
     control on the page's most prominent row of cards. The two axes do meet
     in the story: each platform's gap rows name their own `l3_area`, so the
     area a platform bears on most is a fact the run states rather than a
     mapping invented here. A platform whose story names no area selects
     nothing — the breakdown still opens, and nothing false is claimed. */
  const areaForPlatform = name => {
    const p = storyPlatforms.find(x => pfText(x.platform) === pfText(name));
    if (!p) return null;
    const tally = {};
    for (const g of p.gaps || []) {
      if (g.l3_area && areas.includes(g.l3_area)) {
        tally[g.l3_area] = (tally[g.l3_area] || 0) + 1;
      }
    }
    const best = Object.entries(tally).sort((a, b) => b[1] - a[1])[0];
    return best ? best[0] : null;
  };
  const prereqRows = areaPrereqs(areaRecs);
  const starters = (DMA.startersFor ? DMA.startersFor(entity.id) || [] : []).slice().sort((a, b) => (pfNum(a.rank) === null ? 99 : Number(a.rank)) - (pfNum(b.rank) === null ? 99 : Number(b.rank)));
  // "Why not X" — the platform page's own discarded list where it promoted one,
  // otherwise the overview's. Never both merged: the two sections word the same
  // decision differently and a merge would show one platform twice with
  // conflicting reasons.
  const discarded = (story && story.discarded || []).length ? story.discarded : opportunity && opportunity.discarded || [];
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
        platform: area
      });
      setIpOpen(true);
    }
  }, "\u2726 Platform story"))), /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", null, "Platform fit \xB7 ", tiles.length, " promoted"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Composite read from the run, never re-ranked here")), /*#__PURE__*/React.createElement("div", {
    className: "card-body"
  }, tiles.length ? /*#__PURE__*/React.createElement("div", {
    className: tiles.length === 5 ? "g5" : "g4",
    style: {
      alignItems: "start"
    }
  }, tiles.map((t, i) => {
    // Keyed by the PROMOTED platform string. The vendor-alias fold
    // collapsed "Salesforce Data Cloud" and "Service Cloud
    // consolidation" onto one key and destroyed a tile.
    const composite = oss[t.platform] != null ? pfNum(oss[t.platform]) : pfNum(t.composite);
    const cells = (t.addressable_cells || []).length;
    const isOpen = openTile === (t.platform || i);
    return /*#__PURE__*/React.createElement("div", {
      key: t.platform || i,
      className: "card-tile clickable",
      onClick: () => {
        const nowOpen = openTile !== (t.platform || i);
        setOpenTile(nowOpen ? t.platform || i : null);
        if (!nowOpen) return;
        const a = areaForPlatform(t.platform);
        if (a && a !== area) {
          setAreaSel(a);
          requestAnimationFrame(() => {
            const el = document.getElementById("platform-area-detail");
            if (el) el.scrollIntoView({
              behavior: "smooth",
              block: "start"
            });
          });
        }
      },
      style: {
        border: isOpen ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)",
        background: isOpen ? "var(--z-ice)" : "#fff"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        gap: 8
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 5,
        marginBottom: 2
      }
    }, t.rank != null ? /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, "#", t.rank) : null, t.relevance != null ? /*#__PURE__*/React.createElement("span", {
      className: "b b-muted f-mono",
      title: "relevance to the assessed gaps"
    }, Number(t.relevance).toFixed(2)) : null), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12.5,
        fontWeight: 600,
        lineHeight: 1.3
      }
    }, pfText(t.platform) || "Platform not named")), /*#__PURE__*/React.createElement("div", {
      style: {
        textAlign: "right",
        flexShrink: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 26,
        fontWeight: 200,
        color: composite === null ? "var(--z-muted)" : "var(--z-teal)",
        lineHeight: 1
      }
    }, composite === null ? "—" : composite.toFixed(1)), /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 9,
        color: "var(--z-muted)"
      }
    }, "/100 fit"))), /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 10,
        fontSize: 11
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "b b-org"
    }, cells, " cell", cells === 1 ? "" : "s", " addressed")), t.their_stack_context ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)",
        marginTop: 6,
        lineHeight: 1.5
      },
      className: isOpen ? "" : "txt-fit-3"
    }, pfText(t.their_stack_context)) : null, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginTop: 8,
        fontSize: 10,
        color: "var(--z-mid)"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "spacer"
    }), /*#__PURE__*/React.createElement("span", null, isOpen ? "hide breakdown" : "breakdown"), /*#__PURE__*/React.createElement(Icon, {
      name: isOpen ? "chevron-u" : "chevron-d",
      size: 12
    })), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 8,
        paddingTop: 8,
        borderTop: "1px solid var(--z-sep)"
      }
    }, (t.factors || []).length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      className: "eyebrow",
      style: {
        fontSize: 9,
        marginBottom: 5
      }
    }, "Composite factors"), t.factors.map((f, j) => /*#__PURE__*/React.createElement("div", {
      key: j,
      className: "row",
      style: {
        fontSize: 10,
        gap: 5,
        marginBottom: 3
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        color: "var(--z-muted)",
        width: 78,
        flexShrink: 0
      },
      title: f.weight != null ? `weight ${f.weight}` : ""
    }, String(f.name || "").replace(/_/g, " ")), /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "prog",
      style: {
        height: 4
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "prog-fill",
      style: {
        width: `${Math.max(0, Math.min(100, (pfNum(f.value) || 0) * 10))}%`
      }
    }))), f.contribution != null ? /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        fontSize: 9,
        color: "var(--z-muted)",
        width: 34,
        textAlign: "right",
        flexShrink: 0
      },
      title: "contribution to the composite"
    }, "+", Number(f.contribution).toFixed(1)) : null))) : null, (t.addressable_cells || []).length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      className: "eyebrow",
      style: {
        fontSize: 9,
        margin: "8px 0 5px"
      }
    }, "Cells it addresses"), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gap: 4
      }
    }, t.addressable_cells.map((c, j) => {
      const sid = pfText(c.subcap_id);
      return /*#__PURE__*/React.createElement("div", {
        key: j,
        className: "row",
        style: {
          gap: 5,
          fontSize: 10,
          alignItems: "flex-start"
        }
      }, sid ? /*#__PURE__*/React.createElement("button", {
        className: "chip f-mono",
        style: {
          fontSize: 9,
          flexShrink: 0
        },
        title: `open ${sid} in the heatmap`,
        onClick: ev => {
          ev.stopPropagation();
          openSubcap(sid);
        }
      }, sid) : null, pfNum(c.current) !== null ? /*#__PURE__*/React.createElement(MaturityChip, {
        score: pfNum(c.current)
      }) : null, /*#__PURE__*/React.createElement("span", {
        style: {
          flex: 1,
          minWidth: 0,
          color: "var(--z-body)",
          lineHeight: 1.45
        }
      }, pfText(c.feature_that_addresses_it) || pfText(c.name) || ""));
    }))) : null, t.rank_rationale ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-body)",
        marginTop: 8,
        lineHeight: 1.55
      }
    }, pfText(t.rank_rationale)) : null) : null);
  })) : /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-muted)"
    }
  }, "The opportunity surface did not promote for this run, so no platform fit score is available."))), discarded.length ? /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "filter",
    size: 14
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "Considered and set aside \xB7 ", discarded.length), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)"
    }
  }, "why the run did not lead with these")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 7
    }
  }, discarded.map((x, i) =>
  /*#__PURE__*/
  /* The name column was a fixed 210px in a no-wrap row, so on a
     narrow viewport the reason text was squeezed to a sliver
     beside it. The row wraps: when the reason no longer fits at a
     readable width it drops to its own full-width line. */
  React.createElement("div", {
    key: i,
    className: "row",
    style: {
      gap: 10,
      alignItems: "flex-start",
      fontSize: 11.5,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 500,
      color: "var(--z-dark)",
      flex: "0 0 210px",
      maxWidth: "100%",
      lineHeight: 1.45
    }
  }, pfText(x.platform) || pfText(x.name) || "Platform not named"), x.relevance != null ? /*#__PURE__*/React.createElement("span", {
    className: "b b-muted f-mono",
    style: {
      flexShrink: 0
    },
    title: "relevance to the assessed gaps"
  }, Number(x.relevance).toFixed(2)) : null, /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-muted)",
      flex: "1 1 240px",
      minWidth: 0,
      lineHeight: 1.5
    }
  }, pfText(x.reason) || pfText(x.why_not) || "No reason promoted."))))) : null, areas.length ? /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16,
      padding: "12px 16px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 10,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      letterSpacing: ".06em",
      textTransform: "uppercase",
      fontWeight: 700
    }
  }, "Platform area"), /*#__PURE__*/React.createElement("div", {
    className: "toggle-row",
    style: {
      flexWrap: "wrap"
    }
  }, areas.map(a =>
  /*#__PURE__*/
  /* The open readiness row is identified by its index in THIS
     area's list, so it is closed on a switch rather than
     expanding whatever row happens to land at that index. */
  React.createElement("button", {
    key: a,
    className: a === area ? "on" : "",
    onClick: () => {
      setAreaSel(a);
      setOpenPrereq(null);
    }
  }, a))), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)"
    }
  }, "The L3 area is the unit of recommendation"))) : null, /*#__PURE__*/React.createElement("div", {
    id: "platform-area-detail",
    style: {
      display: "flex",
      flexWrap: "wrap",
      alignItems: "flex-start",
      gap: 16,
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    style: {
      flex: "999 1 400px",
      minWidth: 0,
      maxWidth: "100%"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", null, "Gaps this area closes \xB7 ", area || "no area promoted"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, areaGaps.length, " promoted gap row", areaGaps.length === 1 ? "" : "s")), /*#__PURE__*/React.createElement("div", {
    className: "card-body",
    style: {
      padding: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      overflowX: "auto"
    }
  }, /*#__PURE__*/React.createElement("table", {
    className: "tbl",
    style: {
      minWidth: "min(720px, calc(100vw - 64px))"
    }
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Cell"), /*#__PURE__*/React.createElement("th", {
    style: {
      whiteSpace: "nowrap"
    }
  }, "Pillar"), /*#__PURE__*/React.createElement("th", {
    style: {
      whiteSpace: "nowrap"
    }
  }, "Score"), /*#__PURE__*/React.createElement("th", {
    style: {
      whiteSpace: "nowrap"
    }
  }, anyPeer ? "Peer" : "Peer basis"), anyPeer ? /*#__PURE__*/React.createElement("th", {
    style: {
      whiteSpace: "nowrap"
    }
  }, "Gap") : null, /*#__PURE__*/React.createElement("th", null, "L4 feature"), /*#__PURE__*/React.createElement("th", null, "Evidence"))), /*#__PURE__*/React.createElement("tbody", null, areaGaps.map((g, i) => {
    const cur = pfNum(g.current_score);
    const peer = pfNum(g.peer_score);
    // Computed-or-null: a delta exists only where both figures do,
    // and it carries its own sign — no minus is prepended.
    const delta = cur !== null && peer !== null ? Math.round((cur - peer) * 100) / 100 : null;
    return /*#__PURE__*/React.createElement("tr", {
      key: g.subcap_id || i
    }, /*#__PURE__*/React.createElement("td", {
      "data-label": "Cell"
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        fontWeight: 500
      }
    }, pfText(g.name) || g.subcap_id), /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, pfText(g.subcap_id))), /*#__PURE__*/React.createElement("td", {
      "data-label": "Pillar"
    }, g.pillar ? /*#__PURE__*/React.createElement("span", {
      className: "b b-purple"
    }, pfText(g.pillar)) : /*#__PURE__*/React.createElement("span", {
      className: "chip muted"
    }, "\u2014")), /*#__PURE__*/React.createElement("td", {
      "data-label": "Score"
    }, /*#__PURE__*/React.createElement(MaturityChip, {
      score: cur
    })), anyPeer ? /*#__PURE__*/React.createElement("td", {
      "data-label": "Peer"
    }, peer !== null ? /*#__PURE__*/React.createElement(MaturityChip, {
      score: peer
    }) : /*#__PURE__*/React.createElement("span", {
      style: {
        color: "var(--z-muted)"
      },
      title: pfText(g.peer_note) || String(g.peer_basis || "").replace(/_/g, " ")
    }, "\u2014")) :
    /*#__PURE__*/
    /* Every row here states cannot_estimate with a note
       explaining why. That is the answer, so it is what the
       column shows — the old table printed "-". */
    React.createElement("td", {
      "data-label": "Peer basis"
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        color: "var(--z-muted)"
      },
      title: pfText(g.peer_note) || String(g.peer_basis || "").replace(/_/g, " ")
    }, "\u2014")), anyPeer ? /*#__PURE__*/React.createElement("td", {
      "data-label": "Gap"
    }, delta === null ? /*#__PURE__*/React.createElement("span", {
      style: {
        color: "var(--z-muted)"
      }
    }, "\u2014") : /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        color: delta < 0 ? "var(--z-below)" : "var(--z-above)"
      }
    }, delta > 0 ? `+${delta.toFixed(1)}` : delta.toFixed(1))) : null, /*#__PURE__*/React.createElement("td", {
      "data-label": "L4 feature"
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-dark)"
      }
    }, pfText(g.l4_feature) || "—"), g.catalogue_path ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9.5,
        color: "var(--z-muted)",
        marginTop: 3,
        lineHeight: 1.4
      }
    }, pfText(g.catalogue_path)) : null), /*#__PURE__*/React.createElement("td", {
      "data-label": "Evidence"
    }, /*#__PURE__*/React.createElement(PlatformEvChips, {
      ids: g.e_ids,
      openEvidence: openEvidence
    })));
  }), areaGaps.length === 0 ? /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", {
    colSpan: anyPeer ? 7 : 6,
    className: "tbl-empty"
  }, storyPlatforms.length ? `The platform story promoted gap rows for ${storyPlatforms.length} platform${storyPlatforms.length === 1 ? "" : "s"}, none of them in ${area || "this area"}.` : "No platform story promoted for this run, so no gap rows are available.")) : null))), areaStories.map((s, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      padding: "12px 18px",
      borderTop: "1px solid var(--z-sep)",
      fontSize: 12,
      color: "var(--z-body)",
      lineHeight: 1.65
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      fontSize: 9.5,
      marginBottom: 5
    }
  }, "What this platform changes"), pfText(s))))), /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      flex: "1 1 300px",
      minWidth: 0,
      maxWidth: "100%"
    }
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
      fontWeight: 600,
      flex: 1,
      minWidth: 0
    }
  }, "Readiness"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      flexShrink: 0
    }
  }, prereqRows.length, " prerequisite", prereqRows.length === 1 ? "" : "s")), prereqRows.map((p, idx) => {
    const v = prereqVerdict(p);
    if (p.kind === "condition") {
      /* A text condition has no cell, no minimum and no current value,
         so it gets its own row shape. It used to render the SAME string
         twice — once as a 317px badge, once as a name span flexed to
         0px beside it, which wrapped to one character per line and
         produced an 8px-wide, 900px-tall column of letters. */
      return /*#__PURE__*/React.createElement("div", {
        key: p.key,
        style: {
          borderBottom: "1px solid var(--z-sep)",
          padding: "10px 0"
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          gap: 6,
          marginBottom: 4
        }
      }, /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 9,
          color: "var(--z-muted)",
          letterSpacing: ".06em",
          textTransform: "uppercase"
        }
      }, "Condition"), /*#__PURE__*/React.createElement("span", {
        className: "spacer"
      }), p.basis ? /*#__PURE__*/React.createElement("span", {
        className: "b b-muted"
      }, pfText(p.basis)) : null), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 12,
          color: "var(--z-dark)",
          lineHeight: 1.5
        }
      }, pfText(p.condition)), p.note ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 11,
          color: "var(--z-muted)",
          marginTop: 4,
          lineHeight: 1.5
        }
      }, pfText(p.note)) : null, /*#__PURE__*/React.createElement("div", {
        className: "row",
        style: {
          gap: 4,
          marginTop: 5,
          flexWrap: "wrap"
        }
      }, p.recs.map(rid => /*#__PURE__*/React.createElement("button", {
        key: rid,
        className: "chip",
        style: {
          cursor: "pointer",
          border: 0
        },
        title: `Open ${rid}`,
        onClick: () => openRec(rid)
      }, rid))));
    }
    // Cell threshold. Keyed by index so two thresholds on the same cell
    // cannot share an open state.
    const isOpen = openPrereq === idx;
    const subs = (entity.subcaps || []).filter(s => s.id.startsWith(`${p.cell}.`));
    const ev = (DMA.EVIDENCE || []).filter(e => e.subcaps && e.subcaps.some(sid => String(sid).startsWith(`${p.cell}.`)));
    const pct = p.min !== null && p.current !== null && p.min > 0 ? Math.max(0, Math.min(100, p.current / p.min * 100)) : null;
    return /*#__PURE__*/React.createElement("div", {
      key: p.key,
      style: {
        borderBottom: "1px solid var(--z-sep)"
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setOpenPrereq(o => o === idx ? null : idx),
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
    }, pfText(p.cell)), /*#__PURE__*/React.createElement("span", {
      className: "f-mono",
      style: {
        fontSize: 11.5,
        flex: 1,
        minWidth: 0
      }
    }, p.min === null ? "threshold not stated" : `≥ ${p.min.toFixed(1)}`), v ? /*#__PURE__*/React.createElement("span", {
      className: `b ${v.met ? "b-above" : "b-org"}`,
      title: v.computed ? "computed from the stated minimum and current value" : "verdict as promoted"
    }, v.text) : null, /*#__PURE__*/React.createElement(Icon, {
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
    }, "Current ", p.current === null ? "not stated" : p.current.toFixed(2), " \xB7 ", subs.length, " cells \xB7 ", ev.length, " evidence"), pct !== null ? /*#__PURE__*/React.createElement("div", {
      className: "prog",
      style: {
        marginTop: 4,
        height: 4
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "prog-fill",
      style: {
        width: `${pct}%`,
        background: v && v.met ? "var(--z-mid)" : "var(--z-org)"
      }
    })) : null), isOpen ? /*#__PURE__*/React.createElement("div", {
      style: {
        padding: "2px 0 12px"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 4,
        flexWrap: "wrap",
        marginBottom: 6
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 9,
        color: "var(--z-muted)",
        letterSpacing: ".06em",
        textTransform: "uppercase"
      }
    }, "Required by"), p.recs.map(rid => /*#__PURE__*/React.createElement("button", {
      key: rid,
      className: "chip",
      style: {
        cursor: "pointer",
        border: 0
      },
      title: `Open ${rid}`,
      onClick: () => openRec(rid)
    }, rid))), subs.length ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        margin: "6px 0 4px"
      }
    }, "Backing cells") : null, subs.slice(0, 6).map(s => /*#__PURE__*/React.createElement("div", {
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
        justifyContent: "center",
        flexShrink: 0
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
        color: "var(--z-muted)",
        flexShrink: 0
      }
    }, s.id))), subs.length > 6 ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        marginTop: 3
      }
    }, "+", subs.length - 6, " more cells in ", p.cell) : null, ev.length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".08em",
        color: "var(--z-muted)",
        textTransform: "uppercase",
        margin: "8px 0 4px"
      }
    }, "Evidence \xB7 click to open"), /*#__PURE__*/React.createElement(PlatformEvChips, {
      ids: ev.slice(0, 12).map(e => e.id),
      openEvidence: openEvidence
    })) : null) : null);
  }), prereqRows.length === 0 ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-muted)"
    }
  }, areaRecs.length ? "No prerequisites promoted for this area's recommendations." : "No recommendation promoted for this area, so no readiness gate applies.") : null, prereqRows.some(p => {
    const v = prereqVerdict(p);
    return v && !v.met;
  }) ? /*#__PURE__*/React.createElement("div", {
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
  }, "A threshold in this area is not met. The unmet prerequisite is the conversation that comes first."))) : null)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 340px), 1fr))",
      gap: 16,
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", null, "Recommendations \xB7 ", area || "no area promoted"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, areaRecs.length, " of ", recs.length, " promoted")), /*#__PURE__*/React.createElement("div", null, areaRecs.map(r => {
    const gate = r.validation_gate || null;
    const kpi = r.kpi || null;
    const impacts = (r.dma_impact || []).length;
    return /*#__PURE__*/React.createElement("div", {
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
        marginBottom: 4,
        gap: 6
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "chip"
    }, r.id), /*#__PURE__*/React.createElement("span", {
      style: {
        fontWeight: 600,
        fontSize: 13,
        flex: 1,
        minWidth: 0
      }
    }, pfText(r.title)), r.phase != null ? /*#__PURE__*/React.createElement("span", {
      className: "b b-teal",
      style: {
        flexShrink: 0
      }
    }, "Phase ", pfText(r.phase)) : null, r.effort ? /*#__PURE__*/React.createElement("span", {
      className: "b b-muted",
      style: {
        flexShrink: 0
      },
      title: "effort band"
    }, pfText(r.effort)) : null, /*#__PURE__*/React.createElement(Icon, {
      name: "chevron-r",
      size: 13,
      style: {
        color: "var(--z-muted)",
        flexShrink: 0
      }
    })), r.l4 ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-mid)",
        marginBottom: 5
      }
    }, pfText(r.l4)) : null, r.root_cause_text ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11.5,
        color: "var(--z-body)",
        lineHeight: 1.55,
        margin: "6px 0"
      },
      className: "txt-fit-3"
    }, pfText(r.root_cause_text)) : null, /*#__PURE__*/React.createElement(PlatformEvChips, {
      ids: r.root_cause,
      openEvidence: openEvidence,
      label: "cites"
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "repeat(2, 1fr)",
        gap: 8,
        marginTop: 8,
        fontSize: 11
      }
    }, gate && gate.threshold ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "muted",
      style: {
        fontSize: 10
      }
    }, "Readiness gate"), /*#__PURE__*/React.createElement("strong", {
      className: "f-mono",
      style: {
        fontSize: 11
      },
      title: pfText(gate.grain_note) || ""
    }, pfText(gate.threshold)), gate.verdict ? /*#__PURE__*/React.createElement("span", {
      className: `b ${String(gate.verdict).toUpperCase() === "MET" ? "b-above" : "b-org"}`,
      style: {
        marginLeft: 5
      }
    }, pfText(gate.verdict)) : null) : null, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "muted",
      style: {
        fontSize: 10
      }
    }, "Cells it moves"), /*#__PURE__*/React.createElement("strong", null, impacts)), kpi && kpi.metric ? /*#__PURE__*/React.createElement("div", {
      style: {
        gridColumn: "span 2"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "muted",
      style: {
        fontSize: 10
      }
    }, "KPI"), /*#__PURE__*/React.createElement("strong", {
      style: {
        fontWeight: 500
      }
    }, pfText(kpi.metric)), kpi.baseline ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)",
        marginTop: 2,
        lineHeight: 1.5
      }
    }, "Baseline \xB7 ", pfText(kpi.baseline), kpi.baseline_as_of ? ` · ${kpi.baseline_as_of}` : "") : null, kpi.target ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10.5,
        color: "var(--z-mid)",
        marginTop: 2,
        lineHeight: 1.5
      }
    }, "Target \xB7 ", pfText(kpi.target)) : null) : null));
  }), areaRecs.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, recs.length ? /*#__PURE__*/React.createElement("p", null, "No recommendation promoted for ", area, ". ", recs.length, " promoted across the other areas.") : /*#__PURE__*/React.createElement("p", null, "No recommendation promoted in this run.")) : null, recs.some(r => !r.l3) ? /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "10px 18px",
      fontSize: 11,
      color: "var(--z-muted)",
      borderTop: "1px solid var(--z-sep)"
    }
  }, recs.filter(r => !r.l3).length, " promoted recommendation", recs.filter(r => !r.l3).length === 1 ? "" : "s", " state no platform area and appear under no tab: ", recs.filter(r => !r.l3).map(r => r.id).join(" · ")) : null)), /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("h3", null, "Conversation starters \xB7 ", starters.length), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => {
      const text = starters.map((s, i) => {
        const head = `#${s.rank != null ? s.rank : i + 1}`;
        return [`${head} — ${pfText(s.text) || ""}`, s.followup_question ? `Follow-up: ${pfText(s.followup_question)}` : null, (s.e_ids || []).length ? `Evidence: ${s.e_ids.join(", ")}` : null].filter(Boolean).join("\n");
      }).join("\n\n");
      try {
        navigator.clipboard.writeText(text);
        pushToast(`Copied ${starters.length} conversation starters`, "success");
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
  }, starters.map((s, i) => /*#__PURE__*/React.createElement("div", {
    key: s.rank != null ? `r${s.rank}` : i,
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
      marginBottom: 6,
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, "#", s.rank != null ? s.rank : i + 1), s.opens_on ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-dpur)"
    }
  }, "opens on ", String(s.opens_on).replace(/_/g, " ")) : null, s.named_gap_subcap_id ? /*#__PURE__*/React.createElement("button", {
    className: "chip f-mono",
    style: {
      fontSize: 9
    },
    title: `the gap this starter names — open ${pfText(s.named_gap_subcap_id)} in the heatmap`,
    onClick: () => openSubcap(pfText(s.named_gap_subcap_id))
  }, pfText(s.named_gap_subcap_id)) : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    style: {
      color: "var(--z-dpur)"
    },
    onClick: () => {
      const one = [pfText(s.text), s.followup_question ? `Follow-up: ${pfText(s.followup_question)}` : null].filter(Boolean).join("\n");
      try {
        navigator.clipboard.writeText(one);
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
  }, pfText(s.text)), s.their_system_reference ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-dpur)",
      marginTop: 6,
      lineHeight: 1.5
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      letterSpacing: ".06em",
      textTransform: "uppercase",
      opacity: .75
    }
  }, "Their system \xB7 "), pfText(s.their_system_reference)) : null, s.peer_reference ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-dpur)",
      marginTop: 4,
      lineHeight: 1.5
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      letterSpacing: ".06em",
      textTransform: "uppercase",
      opacity: .75
    }
  }, "Peer \xB7 "), pfText(s.peer_reference)) : null, s.followup_question ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "#3B0764",
      marginTop: 6,
      lineHeight: 1.55,
      paddingLeft: 8,
      borderLeft: "2px solid var(--ph0-bd)"
    }
  }, pfText(s.followup_question)) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 6
    }
  }, /*#__PURE__*/React.createElement(PlatformEvChips, {
    ids: s.e_ids,
    openEvidence: openEvidence,
    label: "cites"
  })))), starters.length === 0 ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--z-muted)"
    }
  }, "No conversation starter promoted for this run.") : null))), /*#__PURE__*/React.createElement(StairstepCurve, {
    entity: entity
  }), /*#__PURE__*/React.createElement(TransformationRoadmap, {
    entity: entity
  }));
}

/* ── Stair-step ladder ───────────────────────────────────────────────
   The ladder's rungs are ORDERED STEPS, not maturity bands. They used to be
   drawn as "M1 … M4" in band colours, which asserts that rung 4 is the
   Differentiating band — the payload says nothing of the kind, and the run's
   own composite is 2.71. Rungs are numbered and coloured from their index
   (presentation, deterministic, claiming nothing), and the position marker is
   the rung the run flags as `current_position` rather than always the first. */
const RUNG_COLORS = ["var(--z-dark2)", "var(--z-mid)", "var(--z-dpur)", "var(--z-teal)", "var(--z-purple)"];

/* SVG text does not wrap, and the promoted rung labels are sentences: at one
   line each they ran straight through the neighbouring rungs. Wrapped on word
   boundaries to the rectangle's own width, capped at two lines with the full
   label kept in a <title>. */
function wrapSvgLabel(text, maxChars, maxLines) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (next.length > maxChars && cur) {
      lines.push(cur);
      cur = w;
    } else cur = next;
  }
  if (cur) lines.push(cur);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  kept[maxLines - 1] = `${kept[maxLines - 1].slice(0, Math.max(0, maxChars - 1))}…`;
  return kept;
}
function StairstepCurve({
  entity
}) {
  // The default cluster key was hardcoded "P4-data", so any run whose ladder
  // does not carry that theme threw on C.label and blanked the whole lower
  // half of the platform page — the missing maturity curve and roadmap.
  const clusters = DMA.STAIRSTEP_CLUSTERS || {};
  const keys = Object.keys(clusters);
  const [cluster, setCluster] = useState(null);
  const active = cluster && clusters[cluster] ? cluster : keys[0];
  const C = active ? clusters[active] : null;
  if (!C || !(C.steps || []).length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "card",
      style: {
        marginBottom: 16
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "stairs",
      size: 14
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, "Maturity stair-step")), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-muted)"
      }
    }, "No stair-step ladder promoted for this run."));
  }
  const steps = C.steps;
  const n = steps.length;
  // Sized from the rung count, not a hardcoded four: a three- or five-rung
  // ladder used to be squeezed into or spill out of four columns.
  const W = 880,
    H = 420,
    padL = 60,
    padR = 40,
    padT = 40,
    padB = 70;
  const stepW = (W - padL - padR) / n;
  const stepY = i => H - padB - (i + 1) * (H - padT - padB) / (n + 1);
  const rungW = stepW - 8;
  const charsPerLine = Math.max(10, Math.floor(rungW / 5.9));
  const monoChars = Math.max(8, Math.floor(rungW / 5.7));
  // The rung the run marks as the current position (1-based level).
  const currentIdx = steps.findIndex(s => Number(s.m) === Number(C.current));
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 14,
      flexWrap: "wrap"
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
      justifyContent: "center",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "stairs",
    size: 14
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "Stair-step ladder \xB7 ", C.label), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, n, " rung", n === 1 ? "" : "s", " \xB7 where ", entity.name, " stands today, and what each rung requires")), keys.length > 1 ? /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, Object.entries(clusters).map(([k, v]) => /*#__PURE__*/React.createElement("button", {
    key: k,
    className: active === k ? "on" : "",
    onClick: () => setCluster(k)
  }, v.label))) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: "999 1 400px",
      minWidth: 0,
      maxWidth: "100%",
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
  }, "Leading"), steps.map((s, i) => {
    const x = padL + i * stepW;
    const y = stepY(i);
    const h = H - padB - y;
    const color = RUNG_COLORS[i % RUNG_COLORS.length];
    const lines = wrapSvgLabel(pfText(s.label), charsPerLine, 2);
    // Cell count and effort only. The blocking findings are chips in
    // the list beside the chart: inside the rung they ran past both
    // edges of the rectangle, because a centred SVG string cannot be
    // clipped to its box.
    const meta = [(s.subcaps || []).length ? `${s.subcaps.length} cells` : null, s.effort ? `effort ${s.effort}` : null].filter(Boolean).join(" · ");
    return /*#__PURE__*/React.createElement("g", {
      key: i
    }, /*#__PURE__*/React.createElement("title", null, `Step ${s.m}: ${pfText(s.label) || ""}`), /*#__PURE__*/React.createElement("rect", {
      x: x,
      y: y,
      width: rungW,
      height: h,
      fill: color,
      rx: "6",
      ry: "6"
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
    }, s.m), lines.map((ln, k) => /*#__PURE__*/React.createElement("text", {
      key: k,
      x: x + rungW / 2,
      y: y + 20 + k * 14,
      fontSize: "11",
      fontWeight: "600",
      fill: "#fff",
      textAnchor: "middle"
    }, ln)), meta ? /*#__PURE__*/React.createElement("text", {
      x: x + rungW / 2,
      y: y + 22 + lines.length * 14,
      fontSize: "9",
      fill: "rgba(255,255,255,.85)",
      textAnchor: "middle",
      style: {
        fontFamily: "var(--font-mono)"
      }
    }, meta.length > monoChars ? `${meta.slice(0, monoChars - 1)}…` : meta) : null);
  }), steps.slice(0, -1).map((s, i) => {
    const x1 = padL + (i + 1) * stepW - 8;
    const y1 = stepY(i);
    const x2 = padL + (i + 1) * stepW;
    const y2 = H - padB;
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
  }), currentIdx >= 0 ? /*#__PURE__*/React.createElement("g", null, /*#__PURE__*/React.createElement("circle", {
    cx: padL + currentIdx * stepW + 16,
    cy: stepY(currentIdx) - 14,
    r: "20",
    fill: "none",
    stroke: "var(--z-org)",
    strokeWidth: "2",
    strokeDasharray: "4 3"
  }), /*#__PURE__*/React.createElement("text", {
    x: padL + currentIdx * stepW + 16,
    y: stepY(currentIdx) - 53,
    fontSize: "9.5",
    fill: "var(--z-org)",
    fontWeight: "700",
    textAnchor: "middle"
  }, "YOU ARE HERE"), /*#__PURE__*/React.createElement("text", {
    x: padL + currentIdx * stepW + 16,
    y: stepY(currentIdx) - 40,
    fontSize: "9",
    fill: "var(--z-muted)",
    textAnchor: "middle"
  }, `step ${steps[currentIdx].m} of ${n}`)) : null)), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: "1 1 280px",
      minWidth: 0,
      maxWidth: "100%",
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, steps.map((s, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      padding: "10px 12px",
      background: i === currentIdx ? "var(--z-ice)" : "var(--z-bg)",
      borderRadius: 8,
      border: i === currentIdx ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 4,
      gap: 6,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "b b-purple",
    style: {
      flexShrink: 0
    }
  }, "Step ", s.m), i === currentIdx ? /*#__PURE__*/React.createElement("span", {
    className: "b b-teal",
    style: {
      flexShrink: 0
    }
  }, "current") : null, s.effort ? /*#__PURE__*/React.createElement("span", {
    className: "b b-muted",
    style: {
      flexShrink: 0
    },
    title: "effort band"
  }, pfText(s.effort)) : null, (s.blocking || []).map(b => /*#__PURE__*/React.createElement("span", {
    key: b,
    className: "b b-org",
    style: {
      flexShrink: 0
    },
    title: "blocking finding"
  }, pfText(b)))), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      fontWeight: 600,
      color: "var(--z-dark)",
      lineHeight: 1.4
    }
  }, pfText(s.label)), s.note ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-body)",
      lineHeight: 1.55,
      marginTop: 4
    }
  }, pfText(s.note)) : null, (s.subcaps || []).length ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      marginTop: 4
    }
  }, s.subcaps.length, " cells covered") : null)))));
}

/* ── Transformation Roadmap (Pattern J: phase chevrons) ─────────── */
function TransformationRoadmap({
  entity
}) {
  const {
    openRec,
    pushToast
  } = useApp();
  const [view, setView] = useState("chevrons"); // chevrons | impact
  const roadmap = DMA.ROADMAP || [];
  const recs = DMA.RECOMMENDATIONS || [];
  if (!roadmap.length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "card",
      style: {
        marginBottom: 16
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "route",
      size: 14
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 600
      }
    }, "Transformation roadmap")), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-muted)"
      }
    }, "No roadmap promoted for this run."));
  }
  const phaseRecs = r => (r.recs || []).map(rid => recs.find(x => x.id === rid)).filter(Boolean);
  const impactRows = roadmap.reduce((a, r) => a + phaseRecs(r).reduce((b, rec) => b + (rec.dma_impact || []).length, 0), 0);
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 16,
      flexWrap: "wrap"
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
      justifyContent: "center",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "route",
    size: 14
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
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
  }, roadmap.length, " promoted phase", roadmap.length === 1 ? "" : "s", " \xB7 ", roadmap.reduce((a, r) => a + (r.recs || []).length, 0), " recommendations")), /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, /*#__PURE__*/React.createElement("button", {
    className: view === "chevrons" ? "on" : "",
    onClick: () => setView("chevrons")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "route",
    size: 11
  }), " Phases"), /*#__PURE__*/React.createElement("button", {
    className: view === "impact" ? "on" : "",
    onClick: () => setView("impact")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "stairs",
    size: 11
  }), " Cell impact")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => pushToast(`Exporting ${entity.name} roadmap (${view} view)…`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 11
  }), " Export")), view === "chevrons" ? /*#__PURE__*/React.createElement(ChevronView, {
    roadmap: roadmap,
    recs: recs,
    openRec: openRec
  }) : /*#__PURE__*/React.createElement(CellImpactView, {
    roadmap: roadmap,
    phaseRecs: phaseRecs,
    openRec: openRec,
    impactRows: impactRows
  }));
}
function ChevronView({
  roadmap,
  recs,
  openRec
}) {
  return (
    /*#__PURE__*/
    /* One fluid column per phase, each carrying its own chevron header AND its
       own content card. This used to be two parallel `repeat(N, 1fr)` grids —
       N hard columns whatever the viewport, so at tablet widths every phase
       was crushed to a sliver, and the two grids could not wrap without the
       chevrons drifting away from their phases. Whole phases wrap together
       instead, and only when a column would drop below a readable width. */
    React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 230px), 1fr))",
        gap: 12
      }
    }, roadmap.map((r, i) => /*#__PURE__*/React.createElement("div", {
      key: r.phase,
      style: {
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        gap: 12
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
        alignItems: "center",
        gap: 8
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
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
        textAlign: "right",
        flexShrink: 0
      }
    }, (r.recs || []).length, " rec", (r.recs || []).length === 1 ? "" : "s")), /*#__PURE__*/React.createElement("div", {
      style: {
        background: r.color,
        borderRadius: 8,
        padding: 14,
        color: "#fff",
        flex: 1
      }
    }, r.rationale ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "rgba(255,255,255,.7)",
        letterSpacing: ".06em",
        textTransform: "uppercase",
        marginBottom: 4
      }
    }, "Why this phase"), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        marginBottom: 10,
        lineHeight: 1.5
      }
    }, pfText(r.rationale))) : null, (r.depends_on || []).length ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "rgba(255,255,255,.7)",
        letterSpacing: ".06em",
        textTransform: "uppercase",
        marginBottom: 4
      }
    }, "Depends on"), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        marginBottom: 10
      }
    }, r.depends_on.join(" · "))) : null, /*#__PURE__*/React.createElement("div", {
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
    }, (r.recs || []).map(rid => {
      const rec = recs.find(x => x.id === rid);
      return rec ? /*#__PURE__*/React.createElement("button", {
        key: rid,
        onClick: e => {
          e.stopPropagation();
          openRec(rid);
        }
        /* The title ellipsises to one line by design; without this
           the rest of the sentence is unreachable by any means. */,
        title: `${rec.id} · ${pfText(rec.title) || ""}`,
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
          fontWeight: 600,
          flexShrink: 0
        }
      }, rec.id), /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 10.5,
          color: "rgba(255,255,255,.85)",
          flex: 1,
          minWidth: 0
        },
        className: "txt-trunc"
      }, pfText(rec.title)), /*#__PURE__*/React.createElement(Icon, {
        name: "arrow-r",
        size: 11
      })) :
      /*#__PURE__*/
      /* A phase that names a recommendation this run did not serve
         says so — it used to render nothing at all. */
      React.createElement("span", {
        key: rid,
        style: {
          fontSize: 10.5,
          color: "rgba(255,255,255,.7)"
        }
      }, rid, " \xB7 not served in this run");
    }))))))
  );
}

/* Per-phase cell movement, from `recommendations[].dma_impact`.
   This replaces the "Customer impact" view, which read DMA.ROADMAP_IMPACTS —
   an accessor pointing at the key `roadmapImpacts`, which nothing in the live
   payload sets and no promoted section carries. It rendered three phase
   headers with zero rows. `dma_impact` is what the run does state about
   movement: per cell, its current score, the projected target and the delta —
   with `target_basis` stating in the producer's own words that the target is a
   projection, which is printed rather than paraphrased. */
function CellImpactView({
  roadmap,
  phaseRecs,
  openRec,
  impactRows
}) {
  if (!impactRows) {
    return /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: "var(--z-muted)"
      }
    }, "No recommendation in this roadmap promoted a cell-impact table, so there is nothing to show per phase.");
  }
  return (
    /*#__PURE__*/
    /* Fluid, like the chevron view: N hard columns crushed each phase's
       impact table at tablet widths; phases wrap when a column would drop
       below a readable width. */
    React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))",
        gap: 12
      }
    }, roadmap.map(r => {
      const rs = phaseRecs(r);
      const bases = [];
      for (const rec of rs) {
        for (const im of rec.dma_impact || []) {
          if (im.target_basis && !bases.includes(im.target_basis)) bases.push(im.target_basis);
        }
      }
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
          marginBottom: 4,
          gap: 6
        }
      }, /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 10,
          fontWeight: 700,
          color: r.color,
          letterSpacing: ".08em",
          textTransform: "uppercase",
          flexShrink: 0
        }
      }, "Phase ", pfText(r.phase)), /*#__PURE__*/React.createElement("strong", {
        style: {
          fontSize: 12.5,
          flex: 1,
          minWidth: 0
        }
      }, r.label)), /*#__PURE__*/React.createElement("div", {
        className: "eyebrow",
        style: {
          fontSize: 9.5,
          margin: "8px 0 6px"
        }
      }, "Cells this phase moves"), rs.map(rec => /*#__PURE__*/React.createElement("div", {
        key: rec.id,
        style: {
          marginBottom: 10
        }
      }, /*#__PURE__*/React.createElement("button", {
        onClick: () => openRec(rec.id),
        title: `${rec.id} · ${pfText(rec.title) || ""}`,
        style: {
          padding: 0,
          background: "none",
          border: 0,
          cursor: "pointer",
          textAlign: "left",
          display: "flex",
          gap: 6,
          alignItems: "center",
          width: "100%"
        }
      }, /*#__PURE__*/React.createElement("strong", {
        style: {
          fontSize: 10.5,
          color: "var(--z-dark)",
          flexShrink: 0
        }
      }, rec.id), /*#__PURE__*/React.createElement("span", {
        style: {
          fontSize: 10.5,
          color: "var(--z-muted)",
          flex: 1,
          minWidth: 0
        },
        className: "txt-trunc"
      }, pfText(rec.title)), /*#__PURE__*/React.createElement(Icon, {
        name: "arrow-r",
        size: 11,
        style: {
          color: "var(--z-muted)",
          flexShrink: 0
        }
      })), (rec.dma_impact || []).length ? (rec.dma_impact || []).map((im, j) => {
        const cur = pfNum(im.current),
          tgt = pfNum(im.target),
          d = pfNum(im.delta);
        return /*#__PURE__*/React.createElement("div", {
          key: j,
          className: "row",
          style: {
            padding: "5px 0",
            borderTop: "1px solid var(--z-sep)",
            gap: 6,
            alignItems: "flex-start"
          }
        }, /*#__PURE__*/React.createElement("div", {
          style: {
            flex: 1,
            minWidth: 0
          }
        }, /*#__PURE__*/React.createElement("div", {
          style: {
            fontSize: 11,
            color: "var(--z-body)",
            lineHeight: 1.35
          }
        }, pfText(im.name) || im.subcap_id), /*#__PURE__*/React.createElement("div", {
          className: "f-mono",
          style: {
            fontSize: 9,
            color: "var(--z-muted)"
          }
        }, pfText(im.subcap_id))), /*#__PURE__*/React.createElement("span", {
          style: {
            flexShrink: 0
          }
        }, /*#__PURE__*/React.createElement(MaturityChip, {
          score: cur
        })), /*#__PURE__*/React.createElement("span", {
          style: {
            fontSize: 10,
            color: "var(--z-muted)",
            flexShrink: 0
          }
        }, "\u2192"), /*#__PURE__*/React.createElement("span", {
          style: {
            flexShrink: 0
          }
        }, /*#__PURE__*/React.createElement(MaturityChip, {
          score: tgt
        })), d !== null ? /*#__PURE__*/React.createElement("span", {
          className: "f-mono",
          style: {
            fontSize: 10,
            color: "var(--z-mid)",
            width: 30,
            textAlign: "right",
            flexShrink: 0
          }
        }, d > 0 ? `+${d.toFixed(1)}` : d.toFixed(1)) : null);
      }) : /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 10.5,
          color: "var(--z-muted)",
          padding: "4px 0"
        }
      }, "No cell impact promoted for this recommendation."))), !rs.length ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 11,
          color: "var(--z-muted)"
        }
      }, (r.recs || []).length ? `This phase names ${r.recs.join(" · ")}, none of them served in this run.` : "This phase names no recommendation.") : null, bases.length ? /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 9.5,
          color: "var(--z-muted)",
          marginTop: 8,
          paddingTop: 8,
          borderTop: "1px solid var(--z-sep)",
          lineHeight: 1.5
        }
      }, bases.map((b, i) => /*#__PURE__*/React.createElement("div", {
        key: i,
        style: {
          marginBottom: 3
        }
      }, pfText(b)))) : null);
    }))
  );
}
Object.assign(window, {
  ClientPlatform
});