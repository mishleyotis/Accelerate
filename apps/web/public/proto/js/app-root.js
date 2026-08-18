/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · App root - router + provider + tweaks
   ═══════════════════════════════════════════════════════════════════════ */

/* `audience_default` is "customer", and that is a deliberate reversal.

   It was "internal", and because audience is a UI toggle rather than
   anything derived from the signed-in role, EVERY reader landed on the
   internal body: the reasoning traces, the capability ceilings, the evidence
   census and the whole Context dashboard, on the first page load, with no
   action taken to ask for them. Reported three times as "information I
   instructed to be removed still shows up", and each time it was this line
   rather than a redaction defect — the API withholds all of it from the
   customer audience already, and had been all along.

   Defaulting to the client-safe body matches what every other layer here
   does: `normalise_audience` resolves an unknown audience to `customer`,
   and `build_page` no longer defaults at all. The browser was the one tier
   still failing open.

   The toggle is unchanged and one click away, so an analyst who wants the
   internal body still has it — they now ask for it, which is the right way
   round for a surface a client can be sitting in front of. */
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "role": "ANALYST",
  "audience_default": "customer",
  "ip_open_default": false,
  "overview_layout": "balanced",
  "heatmap_density": "comfortable",
  "show_thin_outline": true,
  "phase_mode": "phase1",
  "accent_palette": "teal"
} /*EDITMODE-END*/;

/* ── App provider ────────────────────────────────────────────────── */
function AppProvider({
  children
}) {
  // The role the SERVER granted this session. Never settable from the UI: it
  // decides whether an "acting as" control exists at all, and the proxy clamps
  // every read against it (lib/identity.effectiveRole).
  const grantedRole = typeof window !== "undefined" && window.DMA_LIVE && window.DMA_LIVE.role || TWEAK_DEFAULTS.role;
  // Whether this session may preview another role. An AE has exactly one view,
  // so it gets no toggle rather than a toggle with one dead option.
  const canActAs = ["ADMIN", "ANALYST"].includes(String(grantedRole).toUpperCase());
  // EVERY session lands on the AE view. The AE is the reader the pages are
  // written for, so an analyst or admin should see what the field sees first and
  // opt into the internal detail deliberately. Previously the landing view was
  // the granted role, so an admin never saw the page an AE opens.
  const _landingRole = "AE";
  const [tweaks, setTweaks] = useState({
    ...TWEAK_DEFAULTS,
    role: _landingRole
  });
  const [role, setRole] = useState(_landingRole);
  // Production divergence: the host page verifies the session cookie
  // server-side and passes the verdict in DMA_LIVE.
  const [authed, setAuthed] = useState(!!(typeof window !== "undefined" && window.DMA_LIVE && window.DMA_LIVE.authed));
  const [audience, setAudience] = useState(TWEAK_DEFAULTS.audience_default);
  const [ipOpen, setIpOpen] = useState(TWEAK_DEFAULTS.ip_open_default);
  const [ipSurface, setIpSurface] = useState("why_now");
  const [ipContext, setIpContext] = useState(null);
  const [evidenceDrawer, setEvidenceDrawer] = useState(null);
  const [insightModal, setInsightModal] = useState(null);
  const [recModal, setRecModal] = useState(null);
  const [newRunOpen, setNewRunOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [toasts, setToasts] = useState([]);
  const route = useRoute();

  // Sync role tweak — but a session that may not act as another role cannot be
  // moved off its own view by the tweaks panel either.
  useEffect(() => {
    setRole(canActAs ? tweaks.role : grantedRole);
  }, [tweaks.role, canActAs, grantedRole]);

  // Compute alert + active counts
  const openAlerts = DMA.ALERTS.filter(a => a.status === "OPEN").length;
  const activeRuns = DMA.ENTITIES.filter(e => e.in_progress).length;
  const pushToast = (text, kind) => {
    const id = Date.now() + Math.random();
    setToasts(t => [...t, {
      id,
      text,
      kind
    }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4200);
  };
  const removeToast = id => setToasts(t => t.filter(x => x.id !== id));

  // Set up tweaks panel persistence
  const setTweak = useCallback((key, val) => {
    setTweaks(t => {
      const next = typeof key === "object" ? {
        ...t,
        ...key
      } : {
        ...t,
        [key]: val
      };
      try {
        window.parent.postMessage({
          type: "__edit_mode_set_keys",
          edits: next
        }, "*");
      } catch (e) {}
      return next;
    });
  }, []);
  const openEvidence = (evidenceId, subcap) => setEvidenceDrawer({
    evidenceId,
    subcap
  });
  const closeEvidence = () => setEvidenceDrawer(null);
  const openSubcap = subcapId => {
    // Find subcap across entities, jump to heatmap if on a client page
    if (route.path.startsWith("/clients/")) {
      const parts = route.path.split("/");
      const eid = parts[2];
      navigate(`/clients/${eid}/heatmap`, {
        subcap: subcapId
      });
    }
  };
  const openInsight = id => setInsightModal(id);
  const closeInsight = () => setInsightModal(null);
  const openRec = id => setRecModal(id);
  const closeRec = () => setRecModal(null);
  const openNewRun = () => setNewRunOpen(true);
  const closeNewRun = () => setNewRunOpen(false);
  const ctx = {
    tweaks,
    setTweak,
    role,
    setRole,
    grantedRole,
    canActAs,
    authed,
    setAuthed,
    audience,
    setAudience,
    ipOpen,
    setIpOpen,
    ipSurface,
    setIpSurface,
    ipContext,
    setIpContext,
    evidenceDrawer,
    openEvidence,
    closeEvidence,
    insightModal,
    openInsight,
    closeInsight,
    recModal,
    openRec,
    closeRec,
    newRunOpen,
    openNewRun,
    closeNewRun,
    sidebarOpen,
    setSidebarOpen,
    openSubcap,
    pushToast,
    openAlerts,
    activeRuns,
    route
  };
  return /*#__PURE__*/React.createElement(AppCtx.Provider, {
    value: ctx
  }, children, /*#__PURE__*/React.createElement(ToastStack, {
    toasts: toasts,
    remove: removeToast
  }));
}

/* ── Tweaks panel content ────────────────────────────────────────── */
function MyTweaks() {
  const {
    tweaks,
    setTweak,
    canActAs
  } = useApp();
  if (!window.TweaksPanel) return null;
  const {
    TweaksPanel,
    TweakSection,
    TweakRadio,
    TweakToggle,
    TweakSelect
  } = window;
  return /*#__PURE__*/React.createElement(TweaksPanel, {
    title: "Tweaks"
  }, /*#__PURE__*/React.createElement(TweakSection, {
    title: "Persona"
  }, canActAs ? /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Role (preview)",
    value: tweaks.role,
    onChange: v => setTweak("role", v),
    options: (() => {
      const RANK = {
        AE: 0,
        ANALYST: 1,
        ADMIN: 2
      };
      const cap = RANK[grantedRole()] ?? 0;
      return [{
        label: "AE",
        value: "AE"
      }, {
        label: "Analyst",
        value: "ANALYST"
      }, {
        label: "Admin",
        value: "ADMIN"
      }].filter(o => RANK[o.value] <= cap);
    })()
  }) : null, /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Audience",
    value: tweaks.audience_default,
    onChange: v => setTweak("audience_default", v),
    options: [{
      label: "Internal",
      value: "internal"
    }, {
      label: "Customer",
      value: "customer"
    }]
  }), /*#__PURE__*/React.createElement(TweakToggle, {
    label: "Intelligence panel default",
    value: tweaks.ip_open_default,
    onChange: v => setTweak("ip_open_default", v)
  })), /*#__PURE__*/React.createElement(TweakSection, {
    title: "Overview layout"
  }, /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Hero layout",
    value: tweaks.overview_layout,
    onChange: v => setTweak("overview_layout", v),
    options: [{
      label: "Balanced",
      value: "balanced"
    }, {
      label: "Ring-left",
      value: "ring-left"
    }]
  })), /*#__PURE__*/React.createElement(TweakSection, {
    title: "Heatmap"
  }, /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Cell density",
    value: tweaks.heatmap_density,
    onChange: v => setTweak("heatmap_density", v),
    options: [{
      label: "Compact",
      value: "compact"
    }, {
      label: "Comfortable",
      value: "comfortable"
    }]
  }), /*#__PURE__*/React.createElement(TweakToggle, {
    label: "Thin evidence outline",
    value: tweaks.show_thin_outline,
    onChange: v => setTweak("show_thin_outline", v)
  })), /*#__PURE__*/React.createElement(TweakSection, {
    title: "Phase"
  }, /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Run pipeline",
    value: tweaks.phase_mode,
    onChange: v => setTweak("phase_mode", v),
    options: [{
      label: "Phase 0",
      value: "phase0"
    }, {
      label: "Phase 1",
      value: "phase1"
    }]
  })));
}

/* ── Client-scoped route ─────────────────────────────────────────────
   ONE set of page components, fixture or live. The prototype is the
   renderer; in production its accessors read the promoted payload through
   window.DMA_ENTITY, which useLiveEntity installs before the first render
   and clears on every entity change. There is no second renderer to keep
   in step, and no path by which the fixture's fictional institution can
   appear under a real client's name — in LIVE mode every entity-scoped
   accessor answers null rather than falling back (data.js, and
   tests/adapter.test.js).

   What LIVE still changes is WHEN we render: nothing is drawn until the
   promoted pages have arrived, because a page that renders empty and then
   fills in reads as a page with nothing on it. */
const LIVE_MODE = typeof window !== "undefined" && !!window.DMA_LIVE;

/* The firmographics section states each figure as its own row; the prototype's
   entity shape reads them as named properties. Mapped by field name, and only
   where the producer stated a value — a field it left null stays absent so the
   panel prints a dash rather than a zero. */
/* Field names this mapper pins onto the prototype's entity shape. Everything
   NOT in here still renders — see `extra_fields` below — because the contract
   says the SUB-VERTICAL decides which fields exist ("SV5: AUM, client count,
   revenue, ADVISOR COUNT"), and a reader with a fixed vocabulary silently
   drops whatever its author had not met.

   Measured 2026-08-14 on a wealth-manager run: 13 fields served, 5 rendered
   nowhere (AUM, HQ, advisor_count, ownership, business_model) and Assets
   printed an em dash while `AUM 18.0 CAD billions` sat in the payload. The
   panel read as "this client disclosed almost nothing"; the producer had
   disclosed it and the reader threw it away. */
/* ONE declaration, read by both halves of this panel: the slot a served key
   maps onto, and — derived from it below — the set of keys a pinned row has
   already consumed.

   It is one table because it was two, and the two drifted. `cagr` was rendered
   as a pinned row and was NOT in the pinned key set, so the passthrough that
   exists to stop fields being dropped printed it a SECOND time underneath, as
   "Cagr". The build owner saw both rows. `footprint` had the same shape and had
   simply not been stated by a run yet. A key added to the row list now cannot
   be forgotten here, because there is no second place to forget it in. */
const FIRMO_ROWS = [
// The contract states this one as a disjunction ("AUM or assets"), so a
// sub-vertical reports one of the three and the panel keeps one row.
{
  slot: "assets",
  keys: ["total_assets", "assets", "aum"]
}, {
  slot: "employees",
  keys: ["employees"]
}, {
  slot: "branches",
  keys: ["branches"]
}, {
  slot: "members",
  keys: ["member_count"]
}, {
  slot: "customers",
  keys: ["customer_count"]
}, {
  slot: "cagr",
  keys: ["cagr", "growth_rate"]
}, {
  slot: "net_worth_ratio",
  keys: ["net_worth_ratio"]
}, {
  slot: "regulator",
  keys: ["primary_regulator"]
},
// The spellings match the read path in dma_api/computed.py::_entity_domains,
// because the same stated field both renders here and supplies O11's
// denominator — one field recognised in two places by two different lists is
// the drift class this build has paid for repeatedly.
{
  slot: "website",
  keys: ["website", "web site", "domain", "primary domain", "web domain", "entity website", "url"]
}, {
  slot: "hq",
  keys: ["hq", "headquarters"]
}, {
  slot: "footprint",
  keys: ["footprint"]
}, {
  slot: "charter",
  keys: ["charter"]
}, {
  slot: "founded",
  keys: ["founded", "founded_year", "year_founded"]
}];
const FIRMO_PINNED = new Set(FIRMO_ROWS.flatMap(r => r.keys));
const FIRMO_SLOT = new Map(FIRMO_ROWS.flatMap(r => r.keys.map(k => [k, r.slot])));

/* `AUM` and `total_assets` are the same row on this panel: the contract's
   must-present set names them as a disjunction ("AUM or assets"), so a
   sub-vertical states one or the other and the panel has one Assets row. */
function firmoFields(firmo) {
  const out = {};
  // A `fields` that is not a list is not an absent section: it is a section
  // that cannot be read. `for…of` on it throws HERE, above every card and
  // above the shell, which is the one place a boundary cannot save the page —
  // so the shape is checked and the panel is told, rather than printing an em
  // dash per row and passing a malformed payload off as an unstated one.
  const fields = firmo && firmo.fields;
  if (fields !== null && fields !== undefined && !Array.isArray(fields)) {
    return {
      firmographics_unreadable: true
    };
  }
  out.extra_fields = [];
  for (const f of fields || []) {
    const key = String(f.field == null ? "" : f.field).trim().toLowerCase();
    if (f.value === null || f.value === undefined || f.value === "") {
      // A field the producer HELD — quarantined, with the ladder that failed
      // written out — is the most defensible thing on this panel, and it has
      // to reach the reader as a held field rather than as silence.
      //
      // It did not, for the NINE fields the contract makes mandatory. The
      // condition here was `f.quarantined && !FIRMO_PINNED.has(key)`, so a
      // held field that IS pinned fell through to `continue` and rendered
      // nothing at all — no row, no reason, no trace. Measured on the
      // reference client: `founded` is quarantined with a 297-character
      // reason naming the searches that failed, and the panel showed no
      // Founded row whatsoever. The em-dash pass did not catch it because it
      // only ever touched the unpinned branch.
      //
      // Pinned held fields now mark their SLOT, so the panel's own row prints
      // the hold and its reason; unpinned ones keep going to extra_fields.
      if (f.quarantined) {
        const slot = FIRMO_SLOT.get(key);
        if (slot) {
          out.held = out.held || {};
          out.held[slot] = f.quarantine_reason || "held by the producer";
        } else {
          out.extra_fields.push({
            field: f.field,
            value: null,
            unit: null,
            as_of: f.as_of || null,
            held: true,
            reason: f.quarantine_reason || null
          });
        }
      }
      continue;
    }
    /* A number when the producer wrote one, the producer's own words when
       they did not, null only when there is nothing there. `Number()` alone
       returned NaN for `employees: "more than 800"` — a stated, cited,
       UNVERIFIED-badged headcount — and the row that read it disappeared
       from the panel entirely. A figure written in words is a stated figure. */
    const coerced = numOrText(f.value);
    const num = typeof coerced === "number" ? coerced : null;
    if (!FIRMO_PINNED.has(key)) {
      /* The passthrough rendered `${value} ${unit}`, which printed
         `8051646636 USD` two rows under an Assets row rendering the same
         magnitude, through the shared formatter, as `$9.7B`.
          `value` is now the string a READER should see — the unit is applied
         and folded in, so a row that appends it adds nothing and a row that
         calls `fmtFieldValue` again gets the same string back unchanged.
         The producer's own figure and unit are kept verbatim on `raw_value`
         and `raw_unit` for anything that needs to compute on them; `display`
         is the same string as `value`, named for callers that would rather
         say so. */
      const shown = fmtFieldValue(f.value, f.unit);
      out.extra_fields.push({
        field: f.field,
        value: shown != null ? shown : f.value,
        unit: shown != null ? null : f.unit || null,
        display: shown,
        raw_value: f.value,
        raw_unit: f.unit || null,
        as_of: f.as_of || null,
        held: false,
        reason: null
      });
      continue;
    }
    switch (FIRMO_SLOT.get(key)) {
      // One Assets row, whichever of the disjunction the sub-vertical states.
      case "assets":
        out.assets = num;
        out.assets_unit = f.unit;
        out.assets_label = key === "aum" ? "AUM" : "Assets";
        break;
      // The four COUNT slots keep the producer's words when the figure is
      // not written as a number. `fmtCount` renders either; a slot that
      // silently coerced to NaN rendered neither.
      case "employees":
        out.employees = coerced;
        break;
      case "branches":
        out.branches = coerced;
        break;
      case "regulator":
        out.regulator = f.value;
        break;
      case "members":
        out.members = coerced;
        break;
      case "customers":
        out.customers = coerced;
        break;
      case "net_worth_ratio":
        out.net_worth_ratio = num;
        break;
      case "founded":
        out.founded = f.value;
        break;
      case "charter":
        out.charter = f.value;
        break;
      case "hq":
        out.hq = f.value;
        break;
      case "website":
        out.website = f.value;
        break;
      case "footprint":
        out.stated_footprint = f.value;
        break;
      // The panel's CAGR row prefers the value COMPUTED from the promoted
      // financial series (adapter `cagrOf`), because a growth rate is a derived
      // value and the series is its source of truth. A run that also STATES one
      // is kept here as the fallback, carrying its own basis — so a client whose
      // series is too sparse to compute a rate still shows the rate it stated,
      // and neither renders twice.
      case "cagr":
        out.stated_cagr = num;
        out.stated_cagr_basis = f.unit || null;
        break;
      default:
        break;
    }
  }
  return out;
}

/* `advisor_count` -> "Advisor count". The producer's own key, humanised — not
   translated, because a label this app invented would disagree with the field
   name every other surface and every verdict uses. */
function humaniseFieldName(k) {
  const s = String(k == null ? "" : k).replace(/[_-]+/g, " ").trim();
  if (!s) return "";
  // Acronyms the producer wrote in caps stay in caps (AUM, CAGR, HQ, ROA).
  return s.split(" ").map(w => w.length <= 4 && w === w.toUpperCase() ? w : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(" ");
}
function ClientRoute({
  id,
  tab,
  sub
}) {
  const {
    route,
    audience,
    role
  } = useApp();
  const entity = DMA.getEntity(id);
  const runId = route.params.run;
  const run = entity && (runId && entity.runs.find(r => r.id === runId) || entity.runs[0]);
  // The acting-as role is part of the read key: switching view re-fetches so the
  // SERVER decides what that role sees, rather than the client hiding fields it
  // already holds.
  const live = useLiveEntity(LIVE_MODE && entity ? entity.id : null, audience, run && run.run_id, role);
  if (!entity) {
    return /*#__PURE__*/React.createElement(PageShell, {
      title: "Not found"
    }, /*#__PURE__*/React.createElement("div", {
      className: "empty"
    }, /*#__PURE__*/React.createElement("h3", null, "Entity not found")));
  }
  // The directory row carries identity (name, slug, runs, sub-vertical); the
  // promoted payload carries the assessment (cells, scores, platform fit).
  // Merged here, once, so every prototype component receives the entity shape
  // it was written against and none of them needs to know about LIVE.
  const ent = LIVE_MODE && live.status === "ready" && live.entity ? {
    ...entity,
    ...firmoFields(live.entity.firmographics),
    subcaps: live.entity.subcaps,
    oss: live.entity.oss,
    pillar_scores: Object.keys(live.entity.pillar_scores || {}).length ? live.entity.pillar_scores : entity.pillar_scores,
    // Whatever this merge omits reaches no card, which is how the run's own
    // peer medians and framing sentence stayed unread while the hero
    // rendered a constant offset and a hardcoded gap.
    pillar_peer_medians: live.entity.pillar_peer_medians || {},
    // The run's own pillar/category table (heatmap.workbook_scores): stated
    // category scores and peer medians, including categories the CURRENT
    // catalogue does not list. Every heatmap grain reads it, so a run
    // scored against v5.0's 17 categories renders all 17 instead of
    // silently dropping the ones v7.0 killed.
    workbookScores: live.entity.workbookScores || null,
    // The per-cell citation lists the producer actually sent. The drawer
    // resolves these ids rather than reverse-deriving a list from the link
    // table, which is what made one cell's drawer contradict its payload.
    cellEvidence: live.entity.cellEvidence || [],
    // CAGR is computed from the promoted financial series (adapter
    // `cagrOf`); footprint is the regulatory section's jurisdictions. Both
    // were adapted and then dropped here, so the firmographics card printed
    // an em dash for two values the run actually carries. Whatever this
    // merge omits reaches no card — that is the failure mode this block
    // keeps reproducing, so each new field is added here deliberately.
    cagr: (live.entity.financials && live.entity.financials.cagr) != null ? live.entity.financials.cagr : null,
    cagr_basis: live.entity.financials && live.entity.financials.cagr_basis || null,
    footprint: live.entity.regulatory && live.entity.regulatory.jurisdictions || entity.footprint || [],
    license: live.entity.regulatory && live.entity.regulatory.license_type || entity.license || null,
    framing: live.entity.framing || null,
    posture: live.entity.posture || null,
    posture_basis: live.entity.posture_basis || null,
    overall: live.entity.overall != null ? live.entity.overall : entity.overall,
    assessment_date: live.entity.run && live.entity.run.completed_at || entity.assessment_date || null
  } : entity;
  if (LIVE_MODE && live.status === "loading") {
    return /*#__PURE__*/React.createElement(ClientShell, {
      entity: entity,
      run: run,
      tab: tab
    }, /*#__PURE__*/React.createElement(SectionLoader, null));
  }
  if (LIVE_MODE && live.status === "error") {
    // Two different failures, and telling them apart is the whole point: a run
    // with nothing promoted is a state of the RUN; a payload the adapter could
    // not read is a state of this APP, and calling the second one "nothing
    // promoted" would blame the producer for the reader's page.
    const unreadable = live.code === "payload_unreadable";
    return /*#__PURE__*/React.createElement(ClientShell, {
      entity: entity,
      run: run,
      tab: tab
    }, /*#__PURE__*/React.createElement("div", {
      className: "empty"
    }, /*#__PURE__*/React.createElement("h3", null, unreadable ? "This run's payload could not be read into the page" : "Nothing promoted for this run"), /*#__PURE__*/React.createElement("p", null, unreadable ? "The run promoted, but one of its sections did not arrive in the shape this page reads. Nothing here is missing from the assessment." : live.code === "no_promoted_pages" ? "No page of this run has promoted yet, so there is nothing to show." : live.code), unreadable && live.detail ? /*#__PURE__*/React.createElement("p", {
      className: "f-mono",
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)",
        marginTop: 8
      }
    }, live.detail) : null));
  }

  // A dashboard the server refused: a locked state naming the reason, not a
  // white page. The refusal is the API's (default-deny, invariant 5); the app
  // reports it rather than re-deciding it.
  const withheldReason = LIVE_MODE && live.withheld && live.withheld[tab] || null;
  if (withheldReason) {
    return /*#__PURE__*/React.createElement(ClientShell, {
      entity: ent,
      run: run,
      tab: tab
    }, /*#__PURE__*/React.createElement("div", {
      className: "empty"
    }, /*#__PURE__*/React.createElement("div", {
      className: "icon"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "lock",
      size: 20
    })), /*#__PURE__*/React.createElement("h3", null, "This dashboard is not available in the current view"), /*#__PURE__*/React.createElement("p", null, withheldReason), /*#__PURE__*/React.createElement("p", {
      style: {
        marginTop: 8
      }
    }, audience === "customer" ? "Switch back to the internal audience to read it." : "Ask an administrator if you need access.")));
  }
  let page = null;
  switch (tab) {
    case "overview":
      page = /*#__PURE__*/React.createElement(ClientOverview, {
        entity: ent,
        run: run
      });
      break;
    case "insights":
      page = /*#__PURE__*/React.createElement(ClientInsights, {
        entity: ent,
        run: run
      });
      break;
    case "heatmap":
      page = /*#__PURE__*/React.createElement(ClientHeatmap, {
        entity: ent,
        run: run
      });
      break;
    case "platform":
      page = /*#__PURE__*/React.createElement(ClientPlatform, {
        entity: ent,
        run: run
      });
      break;
    case "context":
      page = /*#__PURE__*/React.createElement(ClientContext, {
        entity: ent,
        run: run
      });
      break;
    case "health":
      page = /*#__PURE__*/React.createElement(ClientHealth, {
        entity: ent,
        run: run
      });
      break;
    case "techstack":
      page = sub ? /*#__PURE__*/React.createElement(ClientTechStackDetail, {
        entity: ent,
        run: run,
        techId: sub
      }) : /*#__PURE__*/React.createElement(ClientTechStack, {
        entity: ent,
        run: run
      });
      break;
    case "runs":
      page = /*#__PURE__*/React.createElement(ClientRuns, {
        entity: ent
      });
      break;
    default:
      page = /*#__PURE__*/React.createElement(ClientOverview, {
        entity: ent,
        run: run
      });
  }
  // The boundary sits INSIDE the shell, never around it: a page that cannot
  // render must leave the reader the tab strip, the client bar and the nav,
  // because the way out of a broken dashboard is the next dashboard. Cards
  // carry their own boundaries (CardBoundary, per surface); this one only
  // catches what is above them — a page's own frame, or a section list the
  // page walks before it reaches a card.
  return /*#__PURE__*/React.createElement(ClientShell, {
    entity: ent,
    run: run,
    tab: tab
  }, /*#__PURE__*/React.createElement(PageBoundary, {
    name: TAB_LABEL[tab] || tab
  }, page));
}
const TAB_LABEL = {
  overview: "overview",
  insights: "insight cards",
  heatmap: "capability heatmap",
  platform: "platform fit",
  context: "context",
  health: "assessment health",
  techstack: "technology stack",
  runs: "runs"
};

/* ── Router ──────────────────────────────────────────────────────── */
function Router() {
  const {
    route,
    authed
  } = useApp();
  const {
    path
  } = route;

  // Auth gate: always start at /login until signed in
  if (!authed && path !== "/login") return /*#__PURE__*/React.createElement(LoginPage, null);
  if (path === "/login") return /*#__PURE__*/React.createElement(LoginPage, null);

  // Client-scoped routes — a component of its own because it holds hooks
  // (the live serving-tier read), and a hook inside a router branch would
  // change hook order as the route changes.
  const m = path.match(/^\/clients\/([^/]+)(?:\/([^/]+))?(?:\/(.+))?$/);
  if (m) return /*#__PURE__*/React.createElement(ClientRoute, {
    id: m[1],
    tab: m[2] || "overview",
    sub: m[3]
  });

  // Global pages
  if (path === "/" || path === "") return /*#__PURE__*/React.createElement(DashboardHome, null);
  if (path === "/clients") return /*#__PURE__*/React.createElement(EntityDirectoryPage, null);
  if (path === "/alerts") return /*#__PURE__*/React.createElement(AlertsPage, null);
  if (path === "/prospecting") return /*#__PURE__*/React.createElement(ProspectingPage, null);
  // Production divergence: admin surfaces require the server-granted
  // ADMIN role — direct hash navigation included, not just the nav.
  if (path.startsWith("/admin")) {
    if (grantedRole() !== "ADMIN") {
      return /*#__PURE__*/React.createElement(PageShell, {
        title: "Not authorised"
      }, /*#__PURE__*/React.createElement("div", {
        className: "empty"
      }, /*#__PURE__*/React.createElement("h3", null, "Not authorised"), /*#__PURE__*/React.createElement("p", null, "The admin console requires an ADMIN grant on your account."), /*#__PURE__*/React.createElement("button", {
        className: "btn btn-primary",
        onClick: () => navigate("/")
      }, "Back to Dashboard")));
    }
    if (path === "/admin") return /*#__PURE__*/React.createElement(AdminPage, null);
    if (path === "/admin/import") return /*#__PURE__*/React.createElement(ImportPage, null);
    if (path === "/admin/import/audit") return /*#__PURE__*/React.createElement(ImportAuditPage, null);
  }
  return /*#__PURE__*/React.createElement(PageShell, {
    title: "Not found"
  }, /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, /*#__PURE__*/React.createElement("h3", null, "Page not found"), /*#__PURE__*/React.createElement("p", null, path), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: () => navigate("/")
  }, "Back to Dashboard")));
}

/* ── Root ────────────────────────────────────────────────────────── */
/* The backstop. It renders the app's own frame — brand, a sentence, and the
   two actions that exist — so a fault above every card is a page the reader
   can act on rather than a white screen. It claims nothing about the data. */
function RootBoundary({
  children
}) {
  return /*#__PURE__*/React.createElement(RenderBoundary, {
    name: "application",
    fallback: err => /*#__PURE__*/React.createElement("div", {
      className: "loader-page"
    }, /*#__PURE__*/React.createElement("div", {
      className: "loader-card"
    }, /*#__PURE__*/React.createElement(BrandMark, {
      size: 34
    }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "loader-title"
    }, "This page could not be rendered"), /*#__PURE__*/React.createElement("div", {
      className: "loader-body",
      style: {
        marginTop: 6
      }
    }, "DMA Insights hit a value it cannot draw. Nothing in the assessment has changed, and no data was written.")), /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 10.5,
        color: "var(--z-muted)",
        wordBreak: "break-word"
      }
    }, err && err.message || String(err)), /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 8
      }
    }, /*#__PURE__*/React.createElement("button", {
      className: "btn btn-primary",
      onClick: () => window.location.reload()
    }, "Reload"), /*#__PURE__*/React.createElement("button", {
      className: "btn btn-tertiary",
      onClick: () => {
        navigate("/");
        window.location.reload();
      }
    }, "Back to dashboard"))))
  }, children);
}
function App() {
  const [booting, setBooting] = useState(true);
  useEffect(() => {
    const fontsReady = typeof document !== "undefined" && document.fonts && document.fonts.ready || Promise.resolve();
    Promise.all([fontsReady, new Promise(r => setTimeout(r, 600))]).then(() => setBooting(false));
  }, []);
  if (booting) return /*#__PURE__*/React.createElement(LoadingScreen, {
    variant: "boot",
    dark: true
  });
  return /*#__PURE__*/React.createElement(AppProvider, null, /*#__PURE__*/React.createElement(ConnectionWatcher, null), /*#__PURE__*/React.createElement(RootBoundary, null, /*#__PURE__*/React.createElement(Router, null)), /*#__PURE__*/React.createElement(EvidenceDrawer, null), /*#__PURE__*/React.createElement(InsightModal, null), /*#__PURE__*/React.createElement(RecommendationModal, null), /*#__PURE__*/React.createElement(NewRunModal, null), /*#__PURE__*/React.createElement(IntelligencePanel, null), /*#__PURE__*/React.createElement(MyTweaks, null));
}

// Production divergence: mount OUTSIDE the host framework's hydration
// tree (the host page renders no #app), so server hydration never
// reconciles SPA-owned DOM.
const _mount = document.getElementById("app") || (() => {
  const d = document.createElement("div");
  d.id = "app";
  document.body.appendChild(d);
  return d;
})();
const root = ReactDOM.createRoot(_mount);
root.render(/*#__PURE__*/React.createElement(App, null));