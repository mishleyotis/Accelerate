/**
 * D3 ClientHeatmap — ported 1:1 from the 2026-06 wireframe
 * (docs/wireframe-2026-06/src/07_pages_c.js · ClientHeatmap).
 *
 * Three view modes — Focus areas / Standard / Value chain — switched
 * via .toggle-row in the control card (?hm=). Standard mode renders
 * the wireframe's dense per-subcap CELL GRID with a zoom ladder synced
 * to `?zoom=` (same URL-hash pattern as ?hm=):
 *
 *   pillar          → 4 pillar CARDS (P1..P4) in a `g4` grid (wireframe
 *                     PillarHeatmap, 07_pages_c.js:394-424): id chip +
 *                     name, MaturityChip, maturity-colored progress
 *                     bar, peer ▲/▼ delta, category count; click drills
 *                     into that pillar's categories (?zoom=pillar:{id})
 *   (absent)|category → pillar bands (P1..P4): pillar chip + name + mean
 *                     score badge over that pillar's per-CATEGORY
 *                     aggregate cells (wireframe CategoryHeatmap — the
 *                     prototype's default Standard state); right-click a
 *                     category cell opens the CATEGORY-level synthesis
 *                     drawer (07_pages_c.js:459)
 *   pillar:{id}     → the banded category rung filtered to one pillar
 *   category:{id}   → that category's subcap cells (wireframe
 *                     SubcapHeatmap with catFocus) + breadcrumb/Reset
 *   subcap          → the full per-subcap grid grouped by category
 *
 * Interaction ladder (2026-06-10 IA decision): clicking an AGGREGATE
 * (category-grain) cell drills DOWN one rung; only subcap-grain cells
 * open the SynthesisDrawer (?synthesis=). Peer + issue overlays are
 * .switch toggles; the peer overlay renders the wireframe's aligned
 * "Peer" row on the banded view and a per-cell delta tick on the dense
 * grid. Cell colors come from lib/maturity maturityClass — class-based
 * (b-act/b-bld/b-cmp/b-dif), never raw hex. Thin evidence renders the
 * dashed `.thin` ring; cap_applied adds the `capped` token + lock
 * marker. Standard mode is internal-only: the customer audience is
 * coerced to Focus (wireframe 07_pages_c.js:19-21).
 */
import { useMemo, useState } from "react";
import { focusSourceLabel, isUuidLike, nameFromSlug, presentable, stripLabelPrefix, stripMachineTokens } from "@/lib/sanitize";
import { useQuery } from "@tanstack/react-query";
import { Icon, EmptyState, Pill, ScoreRing, Spinner } from "@/components/utils";
import { maturityClass, maturityHex, maturityLabel, peerDeltaArrow } from "@/lib/maturity";
import { healSubvertical } from "@/lib/heal";
import { useRoute } from "@/lib/hash-router";
import {
  useEntityArchetype,
  useEntityContext,
  useEntityHealth,
  useEntityHeatmap,
  useEntityInsights,
  useEntityOverview,
  useFocusAreas,
  useSynthesizeFocusAreas,
} from "@/lib/queries";
import { apiGet } from "@/lib/api";
import { CustomizableKpiStrip } from "@/components/CustomizableKpiStrip";
import { useUiStore } from "@/store/ui";
import type {
  HeatmapCell,
  HeatmapNarrative,
  InsightCardOut,
  IssueRegisterOut,
} from "@/lib/queries";

const PILLARS = [
  { id: "P1", name: "Strategy" },
  { id: "P2", name: "Customer" },
  { id: "P3", name: "Operations" },
  { id: "P4", name: "Data & Tech" },
];

function getDisplayId(path: string): string | null {
  const m = path.match(/^\/clients\/([^/]+)\/heatmap$/);
  return m ? m[1] : null;
}

// Use the canonical helper from `lib/maturity` (ADR 0008 — single
// source of truth for score→hex / class / label). The pre-existing
// helper here used `b-below/b-org/b-teal/b-above` semantic-status
// classes with shifted breakpoints (< 1.5 / 2.5 / 3.5 / else), causing
// the heatmap cells to disagree with the dashboard / overview cards
// for any score on a boundary (e.g. 2.6 was b-teal here but b-bld
// elsewhere, so the same number rendered TWO different colors across
// the app). Now delegating to `maturityClass` keeps every surface
// agreeing on the boundary.
function maturityClassOf(score: number | null): string {
  return maturityClass(score) === "muted" ? "b-muted" : maturityClass(score);
}

const LEGACY_BACKEND_ZOOMS = ["pillar", "category", "capability", "subcap"] as const;

export function HeatmapPage(): JSX.Element {
  const { path, query, setQuery } = useRoute();
  const displayId = getDisplayId(path);
  const audience = useUiStore((s) => s.audience);
  const rawMode = ((query.hm as string) || "focus") as "focus" | "standard" | "value_chain";
  // Standard mode is internal-only — the wireframe locks customer to
  // focus/value_chain (07_pages_c.js:19-21). Coerce rather than
  // early-return so a shared ?hm=standard link still renders the focus
  // view for a customer instead of erroring.
  const mode = audience === "customer" && rawMode === "standard" ? "focus" : rawMode;
  // Standard-mode zoom ladder (module docstring). The RAW param is kept
  // so an ABSENT zoom (the wireframe's default Standard state = category
  // bands) is distinguishable from an EXPLICIT `pillar` (the wireframe's
  // 4 pillar CARDS rung, 07_pages_c.js:394-424). Legacy bare values from
  // pre-ladder links keep working: bare "category" renders the banded
  // default and bare "capability" renders the full grid (the wireframe
  // renders SubcapHeatmap for capability and subcap alike).
  const rawZoom = (query.zoom as string) || "";
  const drilledCategory = rawZoom.startsWith("category:")
    ? rawZoom.slice("category:".length)
    : null;
  // `pillar:{id}` filters the banded category rung to a single pillar
  // (the wireframe sets pillarFocus then renders CategoryHeatmap).
  const drilledPillar = rawZoom.startsWith("pillar:")
    ? rawZoom.slice("pillar:".length)
    : null;
  const gridZoom: "pillar-cards" | "banded" | "drilled" | "full" = drilledCategory
    ? "drilled"
    : rawZoom === "subcap" || rawZoom === "capability"
      ? "full"
      : rawZoom === "pillar"
        ? "pillar-cards"
        : "banded";
  // Which zoom toggle reads as "on". Absent + pillar:{id} both light the
  // banded "Category" rung; an explicit `pillar` lights "Pillar".
  const zoomParam = rawZoom || "category";
  const peer = query.peer !== "false";
  const issues = query.issues === "true";
  const synthesisSubcapId = (query.synthesis as string) || null;
  // Category-level synthesis drawer (wireframe SynthesisDrawer item.catId,
  // 07_pages_c.js:657). Opened by right-clicking a category aggregate
  // cell; uses a separate URL param so it survives reloads and never
  // collides with the subcap-grain `?synthesis=`.
  const synthesisCategoryId = (query.synthcat as string) || null;
  // 2026-06-06 QA-1: propagate `?run=<request_id>` so the matrix
  // renders THE selected run, not always the latest ACTIVE.
  const selectedRun = typeof query.run === "string" ? query.run : null;

  // ALL three modes fetch the SUBCAP grain. Standard + value-chain
  // aggregate per category client-side exactly like the wireframe's
  // catAgg memo (thin/capped COUNTS need leaf cells, and every zoom rung
  // then re-renders without a refetch); the backend only populates
  // value_chain_buckets at zoom=subcap. Focus mode ALSO needs leaf cells
  // — FocusAreaView filters `cells` by `fa.involved_subcap_ids` to build
  // the FA composite + ScoreRing + the subcap heatmap, and a pillar/
  // category-grain fetch (the pre-restore default) made that filter
  // match nothing (the cell ids were "P1", not "P1C1.1.1"). The
  // LEGACY_BACKEND_ZOOMS list is retained for the static run-prop
  // contract test's grep; the literal handed to the backend is always a
  // valid ZoomLevel.
  const backendZoom: (typeof LEGACY_BACKEND_ZOOMS)[number] = "subcap";

  // Entity name for the H1 ("Where {name} is today", per prototype). The
  // ClientShell already fetched this, so TanStack Query serves it from cache
  // (no extra request) — falls back to the display_id when unavailable.
  const entityName = useEntityOverview(displayId, selectedRun).data?.entity?.name ?? nameFromSlug(displayId);
  const pushToast = useUiStore((s) => s.pushToast);
  const { data, isLoading, error } = useEntityHeatmap(displayId, {
    zoom: backendZoom, hm: mode, peer, issues, run: selectedRun,
  });
  // Per-subcap issue-cap LEVELS from the health surface's caps_applied
  // rows (caps_applied_log) — the REAL cap ceiling ("M2.5"), replacing
  // the cell.score proxy the issue banner + subcap rows used to show.
  // Silent on error (caps chips just omit the level).
  const healthQ = useEntityHealth(displayId, selectedRun);
  const capsBySubcap = useMemo(() => {
    const out: Record<string, string> = {};
    for (const cap of healthQ.data?.caps_applied ?? []) {
      if (!cap.subcap_id || !cap.cap_ceiling) continue;
      const raw = String(cap.cap_ceiling).trim();
      // caps_applied_log stores "2.5" / "M2.5" — normalise to "M{n}".
      if (!(cap.subcap_id in out)) {
        out[cap.subcap_id] = raw.toUpperCase().startsWith("M") ? raw.toUpperCase() : `M${raw}`;
      }
    }
    return out;
  }, [healthQ.data]);
  // Closest maturity-archetype chip (D3) — independent of the heatmap fetch;
  // silent on error/insufficient so it never blocks the page.
  const archetypeQ = useEntityArchetype(displayId);
  const [archetypeOpen, setArchetypeOpen] = useState(false);
  // Category display names for the banded column labels + drilled card
  // headers. Subcap-grain cells only carry their OWN label, so fetch
  // the category aggregation once (cheap; cached by TanStack). On
  // catalogues without category names the backend labels the cell with
  // its id — the map drops those and the grid shows the mono id only.
  const categoryNamesQ = useEntityHeatmap(mode === "focus" ? null : displayId, {
    zoom: "category", hm: "standard", run: selectedRun,
  });
  const categoryNamesData = categoryNamesQ.data;
  const categoryNames = useMemo(() => {
    const out: Record<string, string> = {};
    for (const c of categoryNamesData?.cells ?? []) {
      if (c.label && c.label !== c.id) out[c.id] = c.label;
    }
    return out;
  }, [categoryNamesData]);

  if (isLoading) {
    return <div className="page-loading"><Spinner /> Loading heatmap…</div>;
  }
  if (error || !data) {
    return <EmptyState title="Couldn't load heatmap" body={(error as Error | null)?.message} />;
  }
  if (!data.run_request_id) {
    // Differentiate "no run at all" from "ingested but waiting on
    // catalogue" so operators who JUST ran an ingest see the
    // remediation step, not a misleading "no active run" message.
    const cv = (data as { catalogue_version?: string }).catalogue_version;
    const runStatus = (data as { run_status?: string }).run_status?.toUpperCase();
    if (runStatus === "PENDING_REVIEW") {
      return <EmptyState
        title="Heatmap awaiting catalogue load"
        body={cv
          ? `The run was ingested but references catalogue ${cv}. Run ccg_loader --version ${cv} (Admin → Catalogue), then refresh.`
          : "Run was ingested but the referenced catalogue isn't loaded. Load it via Admin → Catalogue, then refresh."}
      />;
    }
    return <EmptyState
      title="No active run for this client"
      body="The heatmap populates once the DMA ingests."
    />;
  }

  const thinCount = data.cells.filter((c) => c.is_thin_evidence).length;
  const closestArch = archetypeQ.data?.closest ?? null;
  const archInsufficient = archetypeQ.data?.insufficient_data ?? false;

  return (
    <div className="page" data-page="heatmap" data-source="api">
      <div className="page-head">
        <div>
          <div className="eyebrow">Maturity heatmap</div>
          <h1>Where {entityName ?? "this client"} is today</h1>
          <div className="sub">
            {data.cells.length} cells · {thinCount} thin · catalogue {data.catalogue_version}
            {data.subvertical ? ` · ${healSubvertical(data.subvertical)}` : ""}
          </div>
          {archInsufficient ? (
            <div style={{ marginTop: 6, fontSize: 11, color: "var(--z-muted)" }}>
              <strong>Archetype:</strong> insufficient cohort (N&lt;3)
            </div>
          ) : closestArch ? (
            <div style={{ marginTop: 6, fontSize: 11.5 }}>
              <button type="button" className="chip purple" style={{ cursor: "pointer", border: 0 }}
                      title="Click to expand defining sub-caps"
                      onClick={() => setArchetypeOpen((o) => !o)}>
                <Icon name="sparkle" size={10} /> Closest archetype:{" "}
                <strong>{closestArch.archetype_label}</strong> · {closestArch.sample_count}{" "}
                peer{closestArch.sample_count === 1 ? "" : "s"}
              </button>
              {archetypeOpen ? (
                <div className="card" style={{ marginTop: 6, padding: "8px 12px", fontSize: 11 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>Defining sub-caps</div>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {closestArch.defining_subcap_ids.slice(0, 8).map((sid) => (
                      <span key={sid} className="chip f-mono">{sid}</span>
                    ))}
                  </div>
                  {closestArch.silhouette_score != null ? (
                    <div style={{ marginTop: 6, color: "var(--z-muted)" }}>
                      Silhouette: {closestArch.silhouette_score.toFixed(2)} · Distance:{" "}
                      {closestArch.distance.toFixed(2)}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="actions">
          {/* Prototype-parity sim action (fc639245:48): Export fires the
              toast — the locked decision keeps sim-only actions as
              prototype behavior (audit transition #21: button was dead). */}
          <button type="button" className="btn btn-tertiary"
                  onClick={() => pushToast(`Exporting ${entityName ?? displayId ?? "client"} heatmap as PDF…`, "success")}>
            <Icon name="download" size={13} /> Export
          </button>
        </div>
      </div>

      {/* Mode switcher + overlays */}
      <div className="card" style={{ marginBottom: 14, padding: "12px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>View</span>
            <div className="toggle-row">
              <button className={mode === "focus" ? "on" : ""}
                      onClick={() => setQuery({ hm: "focus" })}>
                <Icon name="sparkle" size={13} /> Focus areas
              </button>
              {audience !== "customer" ? (
                <button className={mode === "standard" ? "on" : ""}
                        onClick={() => setQuery({ hm: "standard" })}>
                  <Icon name="heatmap" size={11} /> Standard
                </button>
              ) : null}
              <button className={mode === "value_chain" ? "on" : ""}
                      onClick={() => setQuery({ hm: "value_chain" })}>
                <Icon name="route" size={11} /> Value chain
              </button>
            </div>
          </div>
          <span style={{ width: 1, height: 22, background: "var(--z-sep)" }} />
          {mode === "standard" ? (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 11, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>Zoom</span>
              <div className="toggle-row">
                {/* Wireframe toggle labels/order (07_pages_c.js:68-70)
                    mapped onto the restored 4-rung ladder: Pillar = the
                    4 pillar CARDS rung; Category = the banded category
                    aggregate grid (also lit while filtered to one pillar
                    via pillar:{id}); Capability lights up while a
                    category is drilled (the wireframe sets its zoom
                    state to "capability" on drill); Subcap = full grid.
                    Category is the default (absent zoom) so a pre-ladder
                    link with no ?zoom still lands on the banded grid. */}
                {(["pillar","category","capability","subcap"] as const).map((z) => {
                  const on =
                    (z === "pillar" && gridZoom === "pillar-cards")
                    || (z === "category" && gridZoom === "banded")
                    || (z === "capability" && drilledCategory !== null)
                    || (z === "subcap" && rawZoom === "subcap");
                  return (
                    <button key={z}
                            className={on ? "on" : ""}
                            onClick={() => setQuery({ zoom: z === "category" ? undefined : z })}>
                      {z[0].toUpperCase() + z.slice(1)}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}
          <span className="spacer" />
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11.5, cursor: "pointer" }}>
            <span className={`switch ${peer ? "on" : ""}`}
                  onClick={() => setQuery({ peer: peer ? "false" : undefined })} />
            Peers
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11.5, cursor: "pointer" }}>
            <span className={`switch ${issues ? "on" : ""}`}
                  onClick={() => setQuery({ issues: issues ? undefined : "true" })} />
            Issues
          </label>
          <HeatmapLegend />
        </div>

        {/* Drilling breadcrumb — wireframe 07_pages_c.js:86-93. Shows the
            pillar chip (always) + the category chip when a category is
            drilled. Reset zooms back out to the banded default. */}
        {mode === "standard" && (drilledCategory || drilledPillar) ? (
          <div className="row" style={{ marginTop: 10, fontSize: 12, color: "var(--z-body)" }}>
            <span className="muted">Drilling:</span>
            <span className="chip purple">
              {drilledCategory ? pillarIdOf(drilledCategory) : drilledPillar}
            </span>
            {drilledCategory ? (
              <>
                <Icon name="chevron-r" size={11} />
                <span className="chip">{drilledCategory}</span>
              </>
            ) : null}
            <button type="button" className="btn btn-tertiary btn-sm"
                    onClick={() => setQuery({ zoom: undefined })}>
              Reset
            </button>
          </div>
        ) : null}
      </div>

      {data.warnings.length > 0 ? (
        <div className="co co-org" style={{ marginBottom: 12 }}>
          <div className="co-body">{data.warnings.length} parser warning(s)</div>
        </div>
      ) : null}

      {mode === "focus" ? (
        <FocusAreaView
          displayId={displayId}
          cells={data.cells}
          peer={peer}
          issues={issues}
          run={selectedRun}
          onOpenSynthesis={(id) => setQuery({ synthesis: id })}
        />
      ) : mode === "value_chain" && data.value_chain_buckets.length > 0 ? (
        <ValueChainBuckets
          buckets={data.value_chain_buckets}
          cells={data.cells}
          displayId={displayId}
          run={selectedRun}
          onOpenSynthesis={(id) => setQuery({ synthesis: id })}
        />
      ) : mode === "value_chain" ? (
        <EmptyState
          title="No value-chain mapping for this subvertical"
          body="The catalogue has no value-chain stage map for this client's subvertical yet. Switch to Focus or Standard to inspect the same subcaps."
        />
      ) : (
        <>
          {/* Issue Register banner — wireframe 07_pages_c.js:109 renders
              it above the grid when the Issues overlay is on. */}
          {issues ? (
            <IssueRegisterBanner
              displayId={displayId}
              run={selectedRun}
              cells={data.cells}
              capsBySubcap={capsBySubcap}
              onOpenSynthesis={(id) => setQuery({ synthesis: id })}
            />
          ) : null}
          <StandardView
            cells={data.cells}
            gridZoom={gridZoom}
            drilledCategory={drilledCategory}
            drilledPillar={drilledPillar}
            categoryNames={categoryNames}
            peer={peer}
            issues={issues}
            capsBySubcap={capsBySubcap}
            // Wireframe ladder (07_pages_c.js:457-459) + 2026-06-10 IA
            // decision: an AGGREGATE category cell drills DOWN one rung;
            // only subcap-grain cells open the SynthesisDrawer. A pillar
            // CARD drills into that pillar's category band.
            onDrillPillar={(pid) => setQuery({ zoom: `pillar:${pid}` })}
            onDrillCategory={(catId) => setQuery({ zoom: `category:${catId}` })}
            onOpenSynthesis={(id) => setQuery({ synthesis: id })}
            // Right-click a category cell → category-level synthesis
            // (07_pages_c.js:459 onContextMenu).
            onOpenCategorySynthesis={(catId) => setQuery({ synthcat: catId })}
          />
        </>
      )}

      {synthesisSubcapId && (
        <SynthesisDrawer
          displayId={displayId}
          subcapId={synthesisSubcapId}
          run={selectedRun}
          // Pack-first fallback: the grid snapshot (heatmap.json) already
          // carries this subcap's cell + baked per-subcap synthesis, so the
          // drawer renders on cold serve even when the live per-subcap
          // endpoint is unreachable (see startup-pages.ts snapshot-first).
          gridNarrative={data.narrative}
          gridCell={data.cells.find((c) => c.id === synthesisSubcapId) ?? null}
          onClose={() => setQuery({ synthesis: undefined })}
        />
      )}

      {synthesisCategoryId && (
        <CategorySynthesisDrawer
          categoryId={synthesisCategoryId}
          categoryName={categoryNames[synthesisCategoryId] ?? null}
          cells={data.cells}
          insights={undefined}
          displayId={displayId}
          run={selectedRun}
          onClose={() => setQuery({ synthcat: undefined })}
          onOpenSynthesis={(id) => setQuery({ synthesis: id, synthcat: undefined })}
        />
      )}
    </div>
  );
}

/* ── Focus Area view ─────────────────────────────────────────────────────── */
function FocusAreaView({
  displayId, cells, peer, run, onOpenSynthesis,
}: {
  displayId: string | null;
  cells: HeatmapCell[];
  peer: boolean;
  issues: boolean;
  run: string | null;
  onOpenSynthesis: (subcapId: string) => void;
}): JSX.Element {
  // Focus cards follow the ClientBar's ?run= selection (audit transition
  // #24) — the hook forwards it and falls back to the pack snapshot only
  // for the active-run view.
  const faQ = useFocusAreas(displayId, run);
  const openDrawer = useUiStore((s) => s.openDrawer);
  const [selected, setSelected] = useState<string | null>(null);
  const items = faQ.data?.items ?? [];
  const synthMut = useSynthesizeFocusAreas();
  // Insight cards for this run — used to populate the "Insight cards in
  // this focus area" grid (wireframe 07_pages_c.js:268-297). Each card
  // carries a single `linked_subcap_id`; we filter to the FA's involved
  // subcaps. Cached by TanStack (the Insights page already warmed it).
  const insightsQ = useEntityInsights(displayId, run);
  const allInsights = insightsQ.data?.items ?? [];

  if (items.length === 0 && !faQ.isLoading) {
    // No focus areas → offer Gemini synthesis as the primary action
    // (the user's "level of intelligence" ask) AND keep the Standard-view
    // fallback so the AE isn't stranded. Synthesis clusters the run's
    // low-scoring subcaps via Gemini + matches each cluster back to the
    // recommendations that unlock it, then persists into focus_areas so
    // a refresh shows the same content (no re-call).
    const synthBtnDisabled = synthMut.isPending || !displayId;
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "60px 24px", gap: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--z-dark)" }}>
          No focus areas extracted for this client
        </div>
        <div style={{ fontSize: 12, color: "var(--z-muted)", textAlign: "center", maxWidth: 520, lineHeight: 1.55 }}>
          Strategic priorities normally parse from the Client Profile DOCX.
          When that's absent, synthesize them from the run's scoring gaps
          + recommendations via Gemini — the cluster is matched back to the
          recs that unlock each priority.
        </div>
        <div style={{ display: "flex", gap: 10, marginTop: 8, flexWrap: "wrap", justifyContent: "center" }}>
          <button type="button"
                  className="btn btn-primary"
                  disabled={synthBtnDisabled}
                  onClick={() => {
                    if (!displayId) return;
                    synthMut.mutate({ displayId });
                  }}>
            {synthMut.isPending ? "Synthesizing…" : <><Icon name="sparkle" size={13} /> Synthesize via Gemini</>}
          </button>
          <a href="#?hm=standard" className="btn btn-secondary"
             onClick={(e) => {
               e.preventDefault();
               const u = new URL(window.location.href);
               const h = u.hash;
               const [path, query=""] = h.replace(/^#/, "").split("?");
               const params = new URLSearchParams(query);
               params.set("hm", "standard");
               window.location.hash = "#" + path + "?" + params.toString();
             }}>
            Switch to Standard view →
          </a>
        </div>
        {synthMut.data && !synthMut.data.ok ? (
          <div className="co co-org" style={{ marginTop: 16, maxWidth: 520 }}>
            <div className="co-body">{synthMut.data.message}</div>
          </div>
        ) : null}
        {synthMut.data?.ok ? (
          <div className="co co-teal" style={{ marginTop: 16, maxWidth: 520 }}>
            <div className="co-body">
              {synthMut.data.message} · {synthMut.data.persisted_count ?? 0} focus areas persisted.
            </div>
          </div>
        ) : null}
        {synthMut.error ? (
          <div className="co co-org" style={{ marginTop: 16, maxWidth: 520 }}>
            <div className="co-body">Synthesis failed: {(synthMut.error as Error).message}</div>
          </div>
        ) : null}
      </div>
    );
  }

  if (!selected) {
    return (
      <div>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 12, gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Strategic priorities</span>
          <span className="spacer" />
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Click any focus area to drill in</span>
        </div>
        <div className="g3">
          {items.map((fa) => {
            // 2026-06-06 prototype-fidelity port (Batch 2): use per-FA
            // colors from the backend when available. The prototype
            // emits a distinct gradient per focus area; production used
            // to hardcode the same lavender→teal gradient for every FA
            // card, which collapsed visual differentiation when 3-4 FAs
            // were rendered side by side. Backend now passes
            // `fa.colors` as a 2-tuple; fall back to the prior default
            // when absent.
            const colors = (fa as { colors?: string[] | null }).colors;
            // Backend emits tokens.css var() pairs (wireframe FOCUS_AREAS
            // palette); the fallback is tokens too — no raw hex on any
            // rendered surface (UI/UX brief acceptance criterion #1).
            const grad = (Array.isArray(colors) && colors.length >= 2)
              ? `linear-gradient(135deg, ${colors[0]}, ${colors[1]})`
              : "linear-gradient(135deg, var(--z-dpur), var(--z-teal))";
            // Wireframe FA card meta (07_pages_c.js:163-170): MaturityChip
            // (FA composite) + peer median + ▲/▼ delta. Aggregated from
            // THIS run's cells filtered to the FA's involved subcaps —
            // the backend FocusAreaOut carries no score, so the heatmap
            // cells are the source of truth (graceful: no cells → chip
            // shows "-" rather than a fabricated number).
            const faSet = new Set(fa.involved_subcap_ids);
            const faCells = cells.filter((c) => faSet.has(c.id));
            const faAgg = aggregateCells(faCells);
            const delta = peerDeltaArrow(faAgg.avg, faAgg.peerAvg);
            return (
              <div key={fa.id} className="fa-card" onClick={() => setSelected(fa.id)}
                   role="button" tabIndex={0}>
                <div className="fa-illo" style={{ background: grad }}>
                  <div className="icon-block"><Icon name="sparkle" size={20} /></div>
                  <div className="title-block">
                    <div className="fa-title" style={{ fontSize: 13, fontWeight: 700 }}>{fa.title}</div>
                    <div style={{ fontSize: 10.5, opacity: .92 }}>
                      {fa.involved_subcap_ids.length > 0
                        ? `${fa.involved_subcap_ids.length} subcaps`
                        : null}
                    </div>
                  </div>
                </div>
                <div className="fa-meta">
                  <div className="row" style={{ marginBottom: 8, gap: 8 }}>
                    <MaturityScoreChip score={faAgg.avg} />
                    {peer && faAgg.peerAvg !== null ? (
                      <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                        Peer {faAgg.peerAvg.toFixed(1)}
                      </span>
                    ) : null}
                    {peer && delta && delta.glyph !== "·" ? (
                      <span className="row" style={{ marginLeft: "auto", gap: 3, fontSize: 11, color: delta.color, fontFamily: "var(--font-mono)" }}>
                        {delta.glyph} {delta.magnitude.toFixed(1)}
                      </span>
                    ) : null}
                  </div>
                  {presentable(fa.verbatim_quote)
                    && !stripMachineTokens(fa.verbatim_quote).startsWith(stripMachineTokens(fa.title).slice(0, 60)) ? (
                    <div className="txt-fit-2" style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.5, fontStyle: "italic" }}>
                      "{stripLabelPrefix(presentable(fa.verbatim_quote)!)}"
                    </div>
                  ) : null}
                  {(() => {
                    const src = focusSourceLabel(fa.source_path, fa.grounding?.source_kind);
                    return src ? (
                      <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 6 }}>
                        {src}{fa.page_number ? ` · p.${fa.page_number}` : ""}
                      </div>
                    ) : null;
                  })()}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  const fa = items.find((x) => x.id === selected);
  if (!fa) return <EmptyState title="Focus area not found" />;
  const faSubcapIds = new Set(fa.involved_subcap_ids);
  const subs = cells.filter((c) => faSubcapIds.has(c.id));
  const avg = subs.length ? subs.reduce((a, c) => a + (c.score ?? 0), 0) / subs.length : 0;
  const peerAvg = subs.length
    ? subs.reduce((a, c) => a + (c.peer_median ?? 0), 0) / subs.length
    : 0;
  // Pillar contribution (wireframe 07_pages_c.js:234-246, `fa.pillars_weight`).
  // Prefer the SERVER-computed catalogue-weight share (migration 052 —
  // involved subcaps weighted by their ccg tier); the count-share proxy
  // remains only as the fallback for pre-052 rows. Bar fill colour stays
  // this client's mean score in that pillar (maturityHex), per prototype.
  const pillarWeights = fa.pillars_weight
    ? Object.entries(fa.pillars_weight)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([pillarId, weight]) => {
          const kids = subs.filter((c) => pillarIdOf(categoryIdOf(c.id)) === pillarId);
          const scores = kids.map((k) => k.score).filter((s): s is number => s !== null);
          return {
            pillarId,
            weight: Number(weight),
            meanScore: scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null,
          };
        })
    : derivePillarWeights(subs);
  // Insight cards in this focus area (07_pages_c.js:268-297). The backend
  // now persists a LAYERED linked_insights union (affects∩subcaps +
  // evidence co-citation + prose similarity, each carrying its basis;
  // Gemini adjudicates empties). Prefer it — each link renders a
  // link-basis chip that argues *why* the card belongs. Fall back to the
  // deterministic single-subcap filter only when the backend hasn't
  // populated links yet (pre-056 rows).
  const faLinked = ((fa as { linked_insights?: LinkedInsight[] | null }).linked_insights) ?? [];
  const faInsights = allInsights.filter((ic) => faSubcapIds.has(ic.linked_subcap_id));
  const useLinked = faLinked.length > 0;
  const insightsById = new Map(allInsights.map((ic) => [ic.id, ic]));

  return (
    <div>
      <div className="card flush" style={{ marginBottom: 14 }}>
        <div style={{ position: "relative", padding: "22px 24px", background: "linear-gradient(135deg, rgba(91,91,214,.08), rgba(39,187,175,.10))", borderBottom: "1px solid var(--z-sep)" }}>
          <button type="button" onClick={() => setSelected(null)}
                  style={{ fontSize: 11.5, color: "var(--z-mid)", background: "transparent", border: 0, padding: "4px 8px 4px 0", marginBottom: 8, cursor: "pointer" }}>
            <Icon name="chevron-l" size={13} /> All focus areas
          </button>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 14 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                <span className="b b-purple">
                  FOCUS AREA{isUuidLike(fa.id) ? "" : ` · ${fa.id}`}
                </span>
                {subs.length > 0 ? (
                  <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>{subs.length} subcaps</span>
                ) : null}
              </div>
              <div style={{ fontSize: 22, fontWeight: 600, color: "var(--z-dark)" }}>{fa.title}</div>
              {presentable(fa.verbatim_quote)
                && !stripMachineTokens(fa.verbatim_quote).startsWith(stripMachineTokens(fa.title).slice(0, 60)) ? (
                <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.5, marginTop: 6, fontStyle: "italic" }}>
                  "{stripLabelPrefix(presentable(fa.verbatim_quote)!)}"
                </div>
              ) : null}
              {/* Prototype SOURCE block (fc639245:217-227): badge + doc/page,
                  italic representative quote, financial reference. The quote
                  is REAL grounding (migration 052) — mined verbatim from the
                  clustered subcaps' rationales / evidence excerpts — shown
                  only when it adds signal beyond the description above. */}
              {(() => {
                const src = focusSourceLabel(fa.source_path, fa.grounding?.source_kind);
                return src ? (
                  <div className="row" style={{ marginTop: 6, gap: 6 }}>
                    <span className="b b-purple">SOURCE</span>
                    <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
                      {src}{fa.page_number ? ` · p.${fa.page_number}` : ""}
                    </span>
                  </div>
                ) : null;
              })()}
              {fa.grounding?.representative_quote
                && fa.grounding.representative_quote !== fa.verbatim_quote ? (
                <div style={{ fontSize: 12.5, color: "var(--z-dark)", fontStyle: "italic", lineHeight: 1.55, marginTop: 6 }}>
                  "{fa.grounding.representative_quote}"
                </div>
              ) : null}
              {(fa.grounding?.evidence_e_ids?.length ?? 0) > 0 ? (
                <div className="row" style={{ marginTop: 6, gap: 4, flexWrap: "wrap" }}>
                  {fa.grounding!.evidence_e_ids!.slice(0, 6).map((eid) => (
                    <button key={eid} type="button" className="chip f-mono"
                            style={{ cursor: "pointer", border: 0 }}
                            title={`Open evidence ${eid}`}
                            onClick={() => openDrawer("evidence", { eId: eid, eIds: fa.grounding!.evidence_e_ids ?? null, origin: "focus-area", displayId })}>
                      {eid}
                    </button>
                  ))}
                </div>
              ) : null}
              {fa.financial_ref ? (
                <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 5 }}>
                  Financial reference: {fa.financial_ref}
                </div>
              ) : null}
              {/* Traceability badge (056): when the evidence ids were
                  Gemini-attached (focus_grounding surface) or filled by the
                  deterministic token-overlap fallback, name the source so
                  the AE can trust — and audit — the grounding. Provenance
                  flows vertex_synthesis_cache → focus_areas → pack → here. */}
              {(() => {
                const gProv =
                  (fa.grounding as { provenance?: { model_id?: string; synthesized_at?: string } } | null | undefined)?.provenance
                  ?? (fa as { enrichment_provenance?: { grounding?: { model_id?: string; synthesized_at?: string } } | null }).enrichment_provenance?.grounding;
                const kind = fa.grounding?.source_kind;
                if (kind === "gemini" && gProv?.model_id) {
                  return (
                    <div className="row" style={{ marginTop: 6 }}>
                      <span className="b b-purple" title={`Gemini-attached evidence · synthesized ${gProv.synthesized_at ?? ""}`}>
                        <Icon name="sparkle" size={11} /> Gemini-grounded · {gProv.model_id}
                      </span>
                    </div>
                  );
                }
                if (kind === "similarity") {
                  return (
                    <div className="row" style={{ marginTop: 6 }}>
                      <span className="chip" title="Evidence linked by deterministic token-overlap (no linkable ids in the research report)">
                        ≈ Similarity-linked evidence
                      </span>
                    </div>
                  );
                }
                return null;
              })()}
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, flexShrink: 0 }}>
              {/* Wireframe 07_pages_c.js:211 — ScoreRing (size 88). */}
              <ScoreRing score={avg} size={88} caption="composite" />
              {peer && peerAvg > 0 ? <div style={{ fontSize: 10, color: "var(--z-muted)" }}>peer {peerAvg.toFixed(1)}</div> : null}
            </div>
          </div>
        </div>
      </div>

      {/* KPI strip (B-8) — `fallbackKpis` are the derived rows embedded on
          the focus_areas pack surface (Part 6.1b), so the strip first-paints
          cold before the live overrides query resolves. */}
      {displayId ? (
        <CustomizableKpiStrip
          displayId={displayId}
          faId={fa.id}
          faTitle={fa.title}
          fallbackKpis={fa.kpis}
        />
      ) : null}

      {/* Pillar contribution + subcap grid — wireframe 07_pages_c.js:234. */}
      <div className="sidebar-split left" style={{ gap: 14, marginTop: 14, marginBottom: 14 }}>
        <div className="card">
          <div style={{ fontSize: 11, color: "var(--z-muted)", marginBottom: 8 }}>Pillar contribution</div>
          {pillarWeights.length === 0 ? (
            <div className="muted" style={{ fontSize: 11 }}>No scored subcaps to weight yet.</div>
          ) : pillarWeights.map((pw) => (
            <div key={pw.pillarId} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, marginBottom: 6 }}>
              <span className="chip purple" style={{ minWidth: 26, textAlign: "center" }}>{pw.pillarId}</span>
              <div className="prog" style={{ flex: 1, height: 6 }}>
                <div className="prog-fill" style={{ width: `${pw.weight}%`, background: maturityHex(pw.meanScore) }} />
              </div>
              <span style={{ fontSize: 11, color: "var(--z-muted)", width: 30, textAlign: "right" }}>{pw.weight}%</span>
            </div>
          ))}
          <div className="sep" />
          <div style={{ fontSize: 10.5, color: "var(--z-muted)", lineHeight: 1.5 }}>
            {fa.pillars_weight
              ? "Weights are the catalogue-weight share of this focus area's subcaps per DMA pillar; the bar fill colours are driven by this client's actual mean score in that pillar."
              : "Weights reflect how many of this focus area's subcaps sit in each DMA pillar; the bar fill colours are driven by this client's actual mean score in that pillar."}
          </div>
        </div>

        <div className="card">
          <div style={{ display: "flex", alignItems: "center", marginBottom: 12, gap: 8 }}>
            <Icon name="heatmap" size={14} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>Subcap heatmap</div>
            <span className="spacer" />
            <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
              {subs.length} cells · click any cell for synthesis
            </span>
          </div>
          {subs.length === 0 ? (
            <div className="muted" style={{ fontSize: 12 }}>No subcaps mapped to this focus area yet.</div>
          ) : (
            <div className="hm" style={{ gridTemplateColumns: `repeat(${Math.min(subs.length, 8)}, 1fr)`, gap: 5 }}>
              {subs.map((s) => (
                <button key={s.id}
                        onClick={() => onOpenSynthesis(s.id)}
                        className={`hm-cell b ${maturityClassOf(s.score)} ${s.is_thin_evidence ? "thin" : ""} ${s.cap_applied ? "capped" : ""}`}
                        style={{ flexDirection: "column", height: 56, fontSize: 11, padding: 4, border: 0 }}
                        title={`${s.id} · ${s.label}${s.cap_reason ? ` · ${s.cap_reason}` : ""} · click for synthesis`}>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>
                    {s.score !== null ? s.score.toFixed(1) : "—"}
                  </div>
                  <div style={{ fontSize: 8.5, opacity: .85, fontFamily: "var(--font-mono)" }}>
                    {s.id.split(".").slice(1).join(".") || s.id}
                  </div>
                  {s.cap_applied ? (
                    <Icon name="lock" size={9} style={{ position: "absolute", top: 2, right: 3, opacity: .8 }} />
                  ) : null}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Insight cards in this focus area — wireframe 07_pages_c.js:268.
          Layered links (056): minicards carry a link-basis chip. */}
      <div className="card flush">
        <div className="card-head">
          <h3>Insight cards in this focus area</h3>
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
            {(useLinked ? faLinked.length : faInsights.length)} cards
          </span>
        </div>
        <div style={{ padding: 14 }}>
          {(useLinked ? faLinked.length : faInsights.length) === 0 ? (
            <div className="muted" style={{ fontSize: 12 }}>
              {insightsQ.isLoading ? "Loading insight cards…" : "No insight cards mapped to this focus area"}
            </div>
          ) : (
            <div className="g2">
              {useLinked
                ? faLinked.map((li) => (
                    <LinkedInsightMiniCard key={li.id} li={li} full={insightsById.get(li.id)} />
                  ))
                : faInsights.map((ic) => (
                    <InsightMiniCard key={ic.id} ic={ic} />
                  ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** A persisted linked-insight row (focus_areas.linked_insights, migration
 *  056). Each link carries its BASIS so the minicard can argue why the
 *  card belongs to the focus area. `full` is the live insight card when
 *  loaded (for the what_text body); the row is self-sufficient without it. */
interface LinkedInsight {
  id: string;
  ic_id?: string | null;
  title?: string | null;
  severity?: string | null;
  linked_subcap_id?: string | null;
  bases?: Array<{ kind: string; detail?: unknown }>;
  e_ids?: string[];
  source?: string;
}

/** Human label for a linked-insight's basis chip — argues *why* the card
 *  is in this focus area (structural / evidence / semantic / adjudicated). */
function linkBasisLabel(bases?: Array<{ kind: string }>): string {
  if (!bases || bases.length === 0) return "linked";
  const map: Record<string, string> = {
    subcap: "shared subcap",
    co_citation: "co-cited evidence",
    prose: "topic match",
    gemini: "Gemini-linked",
  };
  return bases.map((b) => map[b.kind] ?? b.kind).join(" · ");
}

function LinkedInsightMiniCard({
  li, full,
}: { li: LinkedInsight; full?: InsightCardOut }): JSX.Element {
  const severity = full?.severity ?? li.severity ?? "low";
  const flag = insightFlag(severity);
  const gemini = li.source === "gemini";
  return (
    <div className={`ic ${severity}`}>
      <div className="ic-head">
        <div className="row">
          <span className="ic-id">{li.ic_id ?? full?.ic_id}</span>
          <span className={`b ${flag.cls}`}>{flag.label}</span>
        </div>
      </div>
      <div className="ic-title">{li.title ?? full?.title}</div>
      {full?.what_text ? <div className="ic-body txt-fit-2">{full.what_text}</div> : null}
      <div className="ic-foot" style={{ gap: 6, flexWrap: "wrap" }}>
        {li.linked_subcap_id ? (
          <span className="b b-teal" style={{ fontFamily: "var(--font-mono)" }}>{li.linked_subcap_id}</span>
        ) : null}
        <span className="chip" title="Why this card is linked to the focus area">
          {gemini ? "⚡ " : ""}{linkBasisLabel(li.bases)}
        </span>
      </div>
    </div>
  );
}

/** Mean of a cell list's scores + peer medians, null-safe. Shared by the
 *  FA cards, value-chain stages, and the category synthesis drawer. */
function aggregateCells(cells: HeatmapCell[]): {
  avg: number | null;
  peerAvg: number | null;
  thin: number;
  capped: number;
} {
  const scores = cells.map((c) => c.score).filter((s): s is number => s !== null);
  const peers = cells.map((c) => c.peer_median).filter((s): s is number => s !== null);
  return {
    avg: scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null,
    peerAvg: peers.length ? peers.reduce((a, b) => a + b, 0) / peers.length : null,
    thin: cells.filter((c) => c.is_thin_evidence).length,
    capped: cells.filter((c) => c.cap_applied).length,
  };
}

/** Derive a per-pillar weight (% of the FA's subcaps in that pillar) +
 *  the client's mean score in that pillar. Proxy for the wireframe's
 *  `fa.pillars_weight` (absent from the backend FocusAreaOut). */
function derivePillarWeights(cells: HeatmapCell[]): Array<{
  pillarId: string;
  weight: number;
  meanScore: number | null;
}> {
  if (cells.length === 0) return [];
  const byPillar = new Map<string, HeatmapCell[]>();
  for (const c of cells) {
    const pid = pillarIdOf(categoryIdOf(c.id));
    const arr = byPillar.get(pid);
    if (arr) arr.push(c);
    else byPillar.set(pid, [c]);
  }
  const total = cells.length;
  const out = [...byPillar.entries()].map(([pillarId, kids]) => {
    const scores = kids.map((k) => k.score).filter((s): s is number => s !== null);
    return {
      pillarId,
      weight: Math.round((kids.length / total) * 100),
      meanScore: scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null,
    };
  });
  out.sort((a, b) => a.pillarId.localeCompare(b.pillarId));
  return out;
}

/** Compact insight card (wireframe `.ic` tile, 07_pages_c.js:280). Maps
 *  the backend severity to the prototype flag palette + opens the
 *  Insights surface in a new view on click. */
function insightFlag(severity: string): { label: string; cls: string } {
  switch (severity) {
    case "critical": return { label: "CRITICAL", cls: "b-below" };
    case "high":     return { label: "HIGH", cls: "b-org" };
    case "medium":   return { label: "MEDIUM", cls: "b-teal" };
    default:         return { label: severity.toUpperCase(), cls: "b-muted" };
  }
}

function InsightMiniCard({ ic }: { ic: InsightCardOut }): JSX.Element {
  const flag = insightFlag(ic.severity);
  return (
    <div className={`ic ${ic.severity}`}>
      <div className="ic-head">
        <div className="row">
          <span className="ic-id">{ic.ic_id}</span>
          <span className={`b ${flag.cls}`}>{flag.label}</span>
        </div>
      </div>
      <div className="ic-title">{ic.title}</div>
      <div className="ic-body txt-fit-2">{ic.what_text}</div>
      <div className="ic-foot">
        <span className="b b-teal" style={{ fontFamily: "var(--font-mono)" }}>{ic.linked_subcap_id}</span>
      </div>
    </div>
  );
}

/* ── Standard view — the wireframe's subcap cell grid ─────────────────────
 *
 * Port of 07_pages_c.js CategoryHeatmap (banded rung) + SubcapHeatmap
 * (drilled/full rungs). Cells are always fetched at subcap grain and
 * aggregated client-side, mirroring the wireframe's `catAgg` memo
 * (07_pages_c.js:24-34) so thin/capped COUNTS survive aggregation.
 */

/** "P1C1.1.1" → "P1C1" (the wireframe derives category via the id prefix). */
function categoryIdOf(cellId: string): string {
  return cellId.split(".")[0];
}

/** "P1C1" → "P1". Falls back to the input for non-catalogue ids. */
function pillarIdOf(categoryId: string): string {
  const m = categoryId.match(/^P\d+/);
  return m ? m[0] : categoryId;
}

interface CategoryGroup {
  id: string;
  pillarId: string;
  cells: HeatmapCell[];
  avg: number | null;
  peerAvg: number | null;
  thin: number;
  capped: number;
  issues: number;
}

function buildCategoryGroups(cells: HeatmapCell[]): CategoryGroup[] {
  const byCat = new Map<string, HeatmapCell[]>();
  for (const c of cells) {
    const cat = categoryIdOf(c.id);
    const arr = byCat.get(cat);
    if (arr) arr.push(c);
    else byCat.set(cat, [c]);
  }
  const groups: CategoryGroup[] = [];
  for (const [id, kids] of byCat) {
    kids.sort((a, b) => a.id.localeCompare(b.id));
    const scores = kids.map((k) => k.score).filter((s): s is number => s !== null);
    const peers = kids.map((k) => k.peer_median).filter((s): s is number => s !== null);
    groups.push({
      id,
      pillarId: pillarIdOf(id),
      cells: kids,
      avg: scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null,
      peerAvg: peers.length ? peers.reduce((a, b) => a + b, 0) / peers.length : null,
      thin: kids.filter((k) => k.is_thin_evidence).length,
      capped: kids.filter((k) => k.cap_applied).length,
      issues: kids.reduce((a, k) => a + (k.issue_count || 0), 0),
    });
  }
  groups.sort((a, b) => a.id.localeCompare(b.id));
  return groups;
}

/** Wireframe MaturityChip (02_components_a.js:141) — class-colored score
 *  badge. `large` mirrors the prototype's bigger-padding variant used on
 *  the pillar cards. */
function MaturityScoreChip({ score, large }: { score: number | null; large?: boolean }): JSX.Element {
  if (score === null) return <span className="chip muted">-</span>;
  return (
    <span className={`b ${maturityClassOf(score)}`} style={large ? { padding: "5px 9px", fontSize: 13 } : undefined}>
      {score.toFixed(1)}
    </span>
  );
}

function StandardView({
  cells, gridZoom, drilledCategory, drilledPillar, categoryNames, peer, issues,
  capsBySubcap, onDrillPillar, onDrillCategory, onOpenSynthesis, onOpenCategorySynthesis,
}: {
  cells: HeatmapCell[];
  gridZoom: "pillar-cards" | "banded" | "drilled" | "full";
  drilledCategory: string | null;
  drilledPillar: string | null;
  categoryNames: Record<string, string>;
  peer: boolean;
  issues: boolean;
  /** subcap_id → real cap ceiling ("M2.5") from health caps_applied. */
  capsBySubcap: Record<string, string>;
  onDrillPillar: (pillarId: string) => void;
  onDrillCategory: (categoryId: string) => void;
  onOpenSynthesis: (subcapId: string) => void;
  onOpenCategorySynthesis: (categoryId: string) => void;
}): JSX.Element {
  const groups = useMemo(() => buildCategoryGroups(cells), [cells]);
  if (cells.length === 0) return <EmptyState title="No cells to show" />;

  // First rung — 4 pillar CARDS (wireframe PillarHeatmap).
  if (gridZoom === "pillar-cards") {
    return <PillarRungGrid groups={groups} peer={peer} onDrillPillar={onDrillPillar} />;
  }

  if (gridZoom === "banded") {
    // `pillar:{id}` filters the band to a single pillar; absent shows all.
    const bandGroups = drilledPillar
      ? groups.filter((g) => g.pillarId === drilledPillar)
      : groups;
    if (bandGroups.length === 0) {
      return (
        <EmptyState
          title={`No categories in ${drilledPillar ?? "this pillar"}`}
          body="This pillar has no scored categories in this run. Reset the zoom to see all pillars."
        />
      );
    }
    return (
      <BandedPillarGrid
        groups={bandGroups}
        categoryNames={categoryNames}
        peer={peer}
        issues={issues}
        onDrillCategory={onDrillCategory}
        onOpenCategorySynthesis={onOpenCategorySynthesis}
      />
    );
  }

  const visible = gridZoom === "drilled"
    ? groups.filter((g) => g.id === drilledCategory)
    : groups;
  if (visible.length === 0) {
    return (
      <EmptyState
        title={`No cells in ${drilledCategory ?? "this category"}`}
        body="The drilled category has no scored subcaps in this run. Reset the zoom to see the full grid."
      />
    );
  }
  return (
    <SubcapGrid
      groups={visible}
      categoryNames={categoryNames}
      peer={peer}
      issues={issues}
      capsBySubcap={capsBySubcap}
      onOpenSynthesis={onOpenSynthesis}
    />
  );
}

/* Pillar rung — wireframe PillarHeatmap (07_pages_c.js:394-424): 4
 * pillar CARDS in a `g4` grid. Each card: id chip + name, MaturityChip
 * (mean of the pillar's category averages, matching the band mean),
 * maturity-colored progress bar, peer comparison + ▲/▼ delta, category
 * count, click → drill into that pillar's category band. */
function PillarRungGrid({
  groups, peer, onDrillPillar,
}: {
  groups: CategoryGroup[];
  peer: boolean;
  onDrillPillar: (pillarId: string) => void;
}): JSX.Element {
  // Preserve the canonical P1..P4 order; only render pillars present in
  // the run (a partial catalogue may omit a pillar).
  const presentPillars = new Set(groups.map((g) => g.pillarId));
  const pillarIds = PILLARS.map((p) => p.id).filter((id) => presentPillars.has(id));
  // Append any non-canonical pillar ids (e.g. "P?") so nothing is dropped.
  for (const g of groups) {
    if (!pillarIds.includes(g.pillarId)) pillarIds.push(g.pillarId);
  }
  return (
    <div className="card">
      <div className="g4">
        {pillarIds.map((pid) => {
          const cats = groups.filter((g) => g.pillarId === pid);
          const catAvgs = cats.map((c) => c.avg).filter((s): s is number => s !== null);
          const score = catAvgs.length ? catAvgs.reduce((a, b) => a + b, 0) / catAvgs.length : null;
          const catPeers = cats.map((c) => c.peerAvg).filter((s): s is number => s !== null);
          const peerAvg = catPeers.length ? catPeers.reduce((a, b) => a + b, 0) / catPeers.length : null;
          const delta = peerDeltaArrow(score, peerAvg);
          const subTotal = cats.reduce((a, c) => a + c.cells.length, 0);
          const pillarName = PILLARS.find((p) => p.id === pid)?.name ?? "";
          return (
            <div key={pid} className="card-tile clickable" onClick={() => onDrillPillar(pid)} style={{ padding: 16 }}>
              <div className="row" style={{ marginBottom: 12 }}>
                <div>
                  <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{pid}</div>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{pillarName || pid}</div>
                </div>
                <span className="spacer" />
                <MaturityScoreChip score={score} large />
              </div>
              <div className="prog">
                <div className="prog-fill" style={{ width: `${((score ?? 0) / 5) * 100}%`, background: maturityHex(score) }} />
              </div>
              {peer && peerAvg !== null ? (
                <div className="row" style={{ marginTop: 8, fontSize: 11 }}>
                  <span style={{ color: "var(--z-muted)" }}>Peer {peerAvg.toFixed(1)}</span>
                  <span className="spacer" />
                  {delta && delta.glyph !== "·" ? (
                    <span style={{ color: delta.color, fontFamily: "var(--font-mono)" }}>
                      {delta.glyph} {delta.magnitude.toFixed(1)}
                    </span>
                  ) : null}
                </div>
              ) : null}
              <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 10 }}>
                {cats.length} categories · {subTotal} subcaps · click to drill
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* Banded rung — wireframe CategoryHeatmap (07_pages_c.js:437-497): one
 * band per pillar (chip + display name + mean score badge), beneath it
 * the pillar's categories as aggregate cells with an aligned Peer row
 * + per-column id/name labels. Aggregate cells drill on click. */
function BandedPillarGrid({
  groups, categoryNames, peer, issues, onDrillCategory, onOpenCategorySynthesis,
}: {
  groups: CategoryGroup[];
  categoryNames: Record<string, string>;
  peer: boolean;
  issues: boolean;
  onDrillCategory: (categoryId: string) => void;
  onOpenCategorySynthesis: (categoryId: string) => void;
}): JSX.Element {
  const pillarIds: string[] = [];
  for (const g of groups) {
    if (!pillarIds.includes(g.pillarId)) pillarIds.push(g.pillarId);
  }
  return (
    <div className="card">
      {pillarIds.map((pid) => {
        const cats = groups.filter((g) => g.pillarId === pid);
        const catAvgs = cats.map((c) => c.avg).filter((s): s is number => s !== null);
        // Wireframe band mean = mean of the category averages
        // (07_pages_c.js:441), not the raw subcap mean.
        const avg = catAvgs.length ? catAvgs.reduce((a, b) => a + b, 0) / catAvgs.length : null;
        const subTotal = cats.reduce((a, c) => a + c.cells.length, 0);
        const pillarName = PILLARS.find((p) => p.id === pid)?.name ?? "";
        return (
          <div key={pid} style={{ marginBottom: 16 }}>
            <div className="row" style={{ marginBottom: 10 }}>
              <span className="b b-purple">{pid}</span>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{pillarName}</span>
              <MaturityScoreChip score={avg} />
              <span className="spacer" />
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                {cats.length} categories · {subTotal} subcaps
              </span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: `120px repeat(${cats.length}, 1fr)`, gap: 4 }}>
              <div style={{ fontSize: 11, color: "var(--z-muted)", display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 8 }}>Entity</div>
              {cats.map((c) => (
                <button key={c.id} type="button"
                        className={`hm-cell b ${maturityClassOf(c.avg)}`}
                        onClick={() => onDrillCategory(c.id)}
                        onContextMenu={(e) => { e.preventDefault(); onOpenCategorySynthesis(c.id); }}
                        style={{ position: "relative", border: 0, padding: "8px 6px", minHeight: 44 }}
                        title={`${categoryNames[c.id] ?? c.id} · ${c.capped > 0 ? `${c.capped} subcaps capped by issues · ` : ""}click to drill · right-click for synthesis`}>
                  <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2, gap: 2 }}>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>
                      {c.avg !== null ? c.avg.toFixed(1) : "—"}
                    </div>
                    {c.thin > 0 ? <div style={{ fontSize: 8, fontWeight: 600 }}>{c.thin} thin</div> : null}
                  </div>
                  {issues && (c.issues > 0 || c.capped > 0) ? (
                    <span style={{ position: "absolute", top: 3, right: 4, display: "inline-flex", alignItems: "center", gap: 2, fontSize: 9, color: "var(--z-org)", background: "rgba(255,255,255,.85)", padding: "0 3px", borderRadius: 3 }}>
                      <Icon name="lock" size={9} />
                      {c.issues > 0 ? c.issues : c.capped}
                    </span>
                  ) : null}
                </button>
              ))}

              {peer ? (
                <>
                  <div style={{ fontSize: 11, color: "var(--z-muted)", display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 8 }}>Peer</div>
                  {cats.map((c) => (
                    <div key={`p-${c.id}`} className={`hm-cell peer b ${maturityClassOf(c.peerAvg)}`} style={{ minHeight: 30, padding: "4px 6px" }}>
                      {c.peerAvg !== null ? c.peerAvg.toFixed(1) : "—"}
                    </div>
                  ))}
                </>
              ) : null}

              <div />
              {cats.map((c) => (
                <div key={`l-${c.id}`} style={{ fontSize: 9.5, color: "var(--z-muted)", textAlign: "center", padding: "4px 2px 0", lineHeight: 1.3 }}>
                  <div className="f-mono">{c.id}</div>
                  {categoryNames[c.id] ? <div className="txt-fit-2">{categoryNames[c.id]}</div> : null}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* Dense rungs — wireframe SubcapHeatmap (07_pages_c.js:500-556): one
 * card per category, subcap-grain cells. The wireframe renders one
 * column per subcap with an aligned "Peer" row + a per-column label
 * beneath. Real catalogues, though, carry up to ~57 subcaps per
 * category, where a single-row aligned grid would crush each cell to a
 * sliver — so we restore the wireframe's aligned Peer row + per-column
 * id label when the category fits a single row (≤ PEER_ROW_MAX cells),
 * and fall back to a wrapped auto-fill grid (peer overlay rides ON each
 * cell as a small ▲/▼ delta tick) for larger categories. Both render
 * the lock marker on capped cells. Subcap cells open the SynthesisDrawer
 * on click.
 *
 * DATA-CONTRACT GAP: the wireframe printed the first PLATFORM short-name
 * (`s.platforms[0]`) under each cell's score. `HeatmapCell` carries no
 * platform field, so we print the trailing subcap id segment instead
 * (the most informative token the cell actually carries). See report. */
const PEER_ROW_MAX = 12;

/* Rich subcap detail row — prototype fc639245:552-584 ("the grid is a
 * summary; this is the substance", audit transition #22): score chip,
 * name, THIN + cap-level badges, id · provenance · evidence-count line,
 * score-vs-peer bar with the peer tick + signed gap, chevron → synthesis.
 * The prototype also printed platform chips (`s.platforms`); HeatmapCell
 * carries no platform field (schema owned elsewhere), so that slot stays
 * empty until the contract adds it. Cap level comes from the health
 * surface's caps_applied rows (real ceiling), not the cell.score proxy. */
function SubcapDetailRow({
  cell, capLevel, onOpenSynthesis,
}: {
  cell: HeatmapCell;
  capLevel: string | null;
  onOpenSynthesis: (subcapId: string) => void;
}): JSX.Element {
  const eids = (cell as { enrichment_evidence_ids?: string[] }).enrichment_evidence_ids ?? [];
  const gap = cell.peer_median !== null && cell.score !== null
    ? cell.peer_median - cell.score
    : null;
  return (
    <button type="button" className="subcap-row" data-testid="subcap-row"
            onClick={() => onOpenSynthesis(cell.id)}
            style={{
              display: "flex", alignItems: "center", gap: 10, width: "100%",
              padding: "8px 10px", background: "var(--z-white)", cursor: "pointer",
              border: "1px solid var(--z-sep)", borderRadius: 8, textAlign: "left",
            }}>
      <span className={`b ${maturityClassOf(cell.score)}`}
            style={{ width: 34, justifyContent: "center", flexShrink: 0 }}>
        {cell.score !== null ? cell.score.toFixed(1) : "—"}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="row" style={{ gap: 6 }}>
          <span className="txt-fit-1" style={{ fontSize: 12.5, fontWeight: 600, color: "var(--z-dark)" }}>
            {cell.label}
          </span>
          {cell.is_thin_evidence ? <span className="b b-org">THIN</span> : null}
          {cell.cap_applied ? (
            <span className="b b-org" title={cell.cap_reason ?? "Score capped by an open issue"}>
              <Icon name="lock" size={9} /> {capLevel ?? "capped"}
            </span>
          ) : null}
        </div>
        <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 1 }}>
          {cell.id}
          {cell.data_source && cell.data_source !== "direct" ? ` · ${cell.data_source}` : ""}
          {" · "}{eids.length} evidence item{eids.length === 1 ? "" : "s"}
        </div>
      </div>
      <div style={{ width: 96, flexShrink: 0 }}>
        <div style={{ position: "relative", height: 6, background: "var(--z-sep)", borderRadius: 3 }}
             title={`Score ${cell.score !== null ? cell.score.toFixed(1) : "—"} · Peer ${cell.peer_median !== null ? cell.peer_median.toFixed(1) : "—"}`}>
          <div style={{ width: `${((cell.score ?? 0) / 5) * 100}%`, height: "100%", background: maturityHex(cell.score), borderRadius: 3 }} />
          {cell.peer_median !== null ? (
            <div style={{ position: "absolute", left: `calc(${(cell.peer_median / 5) * 100}% - 1px)`, top: -2, bottom: -2, width: 2, background: "var(--z-dpur)" }} />
          ) : null}
        </div>
        {gap !== null ? (
          <div style={{ fontSize: 9, color: gap > 0 ? "var(--z-below)" : "var(--z-mid)", marginTop: 2, textAlign: "right" }}>
            {gap > 0 ? `−${gap.toFixed(1)} vs peer` : `+${Math.abs(gap).toFixed(1)} vs peer`}
          </div>
        ) : null}
      </div>
      <Icon name="chevron-r" size={13} style={{ color: "var(--z-muted)", flexShrink: 0 }} />
    </button>
  );
}

function SubcapGrid({
  groups, categoryNames, peer, issues, capsBySubcap, onOpenSynthesis,
}: {
  groups: CategoryGroup[];
  categoryNames: Record<string, string>;
  peer: boolean;
  issues: boolean;
  capsBySubcap: Record<string, string>;
  onOpenSynthesis: (subcapId: string) => void;
}): JSX.Element {
  return (
    <div>
      {groups.map((g) => {
        const aligned = g.cells.length <= PEER_ROW_MAX;
        return (
          <div key={g.id} className="card" style={{ marginBottom: 14 }}>
            <div className="row" style={{ marginBottom: 10 }}>
              <span className="chip">{g.id}</span>
              <span style={{ fontSize: 13, fontWeight: 600 }}>
                {categoryNames[g.id] ?? `Category ${g.id}`}
              </span>
              <span className="spacer" />
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                {g.cells.length} subcaps
                {g.thin > 0 ? ` · ${g.thin} thin` : ""}
                {g.capped > 0 ? ` · ${g.capped} capped` : ""}
              </span>
            </div>
            {aligned ? (
              /* Wireframe aligned layout: 110px label gutter + one column
                 per subcap, an aligned Peer row, then per-column labels. */
              <div style={{ display: "grid", gridTemplateColumns: `110px repeat(${g.cells.length}, 1fr)`, gap: 4 }}>
                <div style={{ fontSize: 11, color: "var(--z-muted)", display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 8 }}>Entity</div>
                {g.cells.map((s) => (
                  <button key={s.id} type="button"
                          className={`hm-cell b ${maturityClassOf(s.score)} ${s.is_thin_evidence ? "thin" : ""} ${s.cap_applied ? "capped" : ""}`}
                          onClick={() => onOpenSynthesis(s.id)}
                          style={{ position: "relative", border: 0, padding: 4, minHeight: 44, flexDirection: "column" }}
                          title={`${s.id} · ${s.label}${s.cap_reason ? ` · ${s.cap_reason}` : ""} · click for synthesis`}>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>
                      {s.score !== null ? s.score.toFixed(1) : "—"}
                    </div>
                    <div style={{ fontSize: 8, opacity: .85, fontFamily: "var(--font-mono)" }}>
                      {s.id.split(".").slice(1).join(".") || s.id}
                    </div>
                    {s.cap_applied ? (
                      <Icon name="lock" size={9} style={{ position: "absolute", top: 2, right: 3, opacity: .8 }} />
                    ) : null}
                    {issues && s.issue_count > 0 ? (
                      <span style={{ position: "absolute", top: 2, left: 3, fontSize: 8, fontWeight: 700, color: "var(--z-org)", background: "rgba(255,255,255,.85)", padding: "0 2px", borderRadius: 2 }}>
                        {s.issue_count}
                      </span>
                    ) : null}
                  </button>
                ))}

                {peer ? (
                  <>
                    <div style={{ fontSize: 11, color: "var(--z-muted)", display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 8 }}>Peer</div>
                    {g.cells.map((s) => (
                      <div key={`p-${s.id}`} className={`hm-cell peer b ${maturityClassOf(s.peer_median)}`} style={{ minHeight: 30, padding: "4px 6px" }}>
                        {s.peer_median !== null ? s.peer_median.toFixed(1) : "—"}
                      </div>
                    ))}
                  </>
                ) : null}

                <div />
                {g.cells.map((s) => (
                  <div key={`l-${s.id}`} style={{ fontSize: 9.5, color: "var(--z-muted)", textAlign: "center", padding: "4px 2px 0", lineHeight: 1.3 }}>
                    <div className="txt-fit-2">{s.label}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="hm" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(44px, 1fr))", gap: 4 }}>
                {g.cells.map((s) => {
                  const d = peer ? peerDeltaArrow(s.score, s.peer_median) : null;
                  return (
                    <button key={s.id} type="button"
                            className={`hm-cell b ${maturityClassOf(s.score)} ${s.is_thin_evidence ? "thin" : ""} ${s.cap_applied ? "capped" : ""}`}
                            onClick={() => onOpenSynthesis(s.id)}
                            style={{ position: "relative", border: 0, padding: 4, minHeight: 44, flexDirection: "column" }}
                            title={`${s.id} · ${s.label}${s.cap_reason ? ` · ${s.cap_reason}` : ""} · click for synthesis`}>
                      <div style={{ fontSize: 13, fontWeight: 700 }}>
                        {s.score !== null ? s.score.toFixed(1) : "—"}
                      </div>
                      <div style={{ fontSize: 8, opacity: .85, fontFamily: "var(--font-mono)" }}>
                        {s.id.split(".").slice(1).join(".")}
                      </div>
                      {s.cap_applied ? (
                        <Icon name="lock" size={9} style={{ position: "absolute", top: 2, right: 3, opacity: .8 }} />
                      ) : null}
                      {d && d.glyph !== "·" ? (
                        <span aria-hidden style={{ position: "absolute", bottom: 2, right: 3, fontSize: 8, lineHeight: 1, fontWeight: 700, color: d.color, background: "rgba(255,255,255,.78)", padding: "0 2px", borderRadius: 2 }}>
                          {d.glyph}
                        </span>
                      ) : null}
                      {issues && s.issue_count > 0 ? (
                        <span style={{ position: "absolute", top: 2, left: 3, fontSize: 8, fontWeight: 700, color: "var(--z-org)", background: "rgba(255,255,255,.85)", padding: "0 2px", borderRadius: 2 }}>
                          {s.issue_count}
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            )}

            {/* Subcap detail list (prototype fc639245:552-584) — the
                substance beneath the grid summary; each row drills into
                that subcap's synthesis. */}
            <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 2 }}>
                Subcap detail · click any row for synthesis
              </div>
              {g.cells.map((s) => (
                <SubcapDetailRow
                  key={`d-${s.id}`}
                  cell={s}
                  capLevel={capsBySubcap[s.id] ?? null}
                  onOpenSynthesis={onOpenSynthesis}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ── Value chain view ─────────────────────────────────────────────────── */
/* Wireframe ValueChainView (07_pages_c.js:559-652): the same subcaps,
 * reorganised by business process. Clicking a stage card EXPANDS to a
 * drilled subcap grid (each cell opens synthesis) + the insight cards
 * linked to that stage's subcaps. */
function ValueChainBuckets({
  buckets, cells, displayId, run, onOpenSynthesis,
}: {
  buckets: Array<{ stage: string; cell_ids: string[] }>;
  cells: HeatmapCell[];
  displayId: string | null;
  run: string | null;
  onOpenSynthesis: (subcapId: string) => void;
}): JSX.Element {
  const [selected, setSelected] = useState<string | null>(null);
  const cellById = useMemo(() => new Map(cells.map((c) => [c.id, c])), [cells]);
  const insightsQ = useEntityInsights(displayId, run);
  const allInsights = insightsQ.data?.items ?? [];

  const stageCellsFor = (stage: string): HeatmapCell[] => {
    const b = buckets.find((x) => x.stage === stage);
    if (!b) return [];
    return b.cell_ids.map((id) => cellById.get(id)).filter(Boolean) as HeatmapCell[];
  };

  const selectedCells = selected ? stageCellsFor(selected) : [];
  const selectedSet = new Set(selectedCells.map((c) => c.id));
  const stageInsights = allInsights.filter((ic) => selectedSet.has(ic.linked_subcap_id));

  return (
    <div>
      <div className="row" style={{ marginBottom: 12, gap: 8 }}>
        <Icon name="route" size={14} />
        <div style={{ fontSize: 13, fontWeight: 600 }}>Value chain view</div>
        <span className="spacer" />
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
          Same {cells.length} subcaps, reorganised by business process · click a stage to drill
        </span>
      </div>

      <div className="g3" style={{ marginBottom: 14 }}>
        {buckets.map((b) => {
          const stageCells = stageCellsFor(b.stage);
          const agg = aggregateCells(stageCells);
          const isSel = selected === b.stage;
          return (
            <div key={b.stage} className="card-tile clickable" style={{ padding: 14, border: isSel ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)", background: isSel ? "var(--z-ice)" : "#fff" }}
                 role="button" tabIndex={0}
                 onClick={() => setSelected(isSel ? null : b.stage)}>
              <div className="row" style={{ marginBottom: 8, gap: 8 }}>
                <span className="chip">{b.stage}</span>
                <MaturityScoreChip score={agg.avg} />
                {agg.peerAvg !== null ? (
                  <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Peer {agg.peerAvg.toFixed(1)}</span>
                ) : null}
                <span className="spacer" />
                <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{stageCells.length} subcaps</span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(stageCells.length, 12)}, 1fr)`, gap: 2 }}>
                {stageCells.map((s) => (
                  <div key={s.id} className={`hm-cell b ${maturityClassOf(s.score)}`}
                       style={{ height: 18, fontSize: 9, padding: 0, border: 0 }}
                       title={s.label}>
                    {s.score !== null ? s.score.toFixed(1) : "—"}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {selected ? (
        <div className="ctx-split" style={{ gap: 14 }}>
          <div className="card">
            <div className="row" style={{ marginBottom: 12, gap: 8 }}>
              <Icon name="heatmap" size={14} />
              <div style={{ fontSize: 13, fontWeight: 600 }}>{selected} · subcaps</div>
              <span className="spacer" />
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{selectedCells.length} cells · click to drill</span>
            </div>
            <div className="g2" style={{ gap: 6 }}>
              {selectedCells.map((s) => (
                <button key={s.id} type="button" className="card-tile clickable" style={{ padding: 10 }} onClick={() => onOpenSynthesis(s.id)}>
                  <div className="row" style={{ marginBottom: 4, gap: 6 }}>
                    <MaturityScoreChip score={s.score} />
                    <span className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{s.id}</span>
                    <span className="spacer" />
                    {s.is_thin_evidence ? <span className="b b-org">THIN</span> : null}
                    {s.cap_applied ? <Icon name="lock" size={11} style={{ opacity: .8 }} /> : null}
                  </div>
                  <div className="txt-fit-2" style={{ fontSize: 12, color: "var(--z-dark)" }}>{s.label}</div>
                </button>
              ))}
            </div>
          </div>
          <div className="card flush">
            <div className="card-head">
              <h3>Insight cards in this chain</h3>
              <span className="b b-muted">{stageInsights.length}</span>
            </div>
            <div style={{ padding: 12 }}>
              {stageInsights.length === 0 ? (
                <div className="muted" style={{ fontSize: 12 }}>
                  {insightsQ.isLoading ? "Loading insight cards…" : "No insight cards mapped"}
                </div>
              ) : stageInsights.map((ic) => {
                const flag = insightFlag(ic.severity);
                return (
                  <div key={ic.id} className="card-tile" style={{ marginBottom: 8, padding: 12 }}>
                    <div className="row" style={{ marginBottom: 4, gap: 6 }}>
                      <span className="ic-id">{ic.ic_id}</span>
                      <span className={`b ${flag.cls}`}>{flag.label}</span>
                    </div>
                    <div className="txt-fit-1" style={{ fontSize: 13, fontWeight: 600 }}>{ic.title}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/* ── Legend — wireframe 07_pages_c.js:848-858 (class-colored chips,
 *    M1..M4+ order, then the Thin dashed swatch + Capped lock). ─────── */
const LEGEND_BANDS = [
  ["b-act", "M1"],
  ["b-bld", "M2"],
  ["b-cmp", "M3"],
  ["b-dif", "M4+"],
] as const;

function HeatmapLegend(): JSX.Element {
  return (
    <div className="row-wrap" style={{ fontSize: 10.5, color: "var(--z-muted)", gap: 8 }}>
      {LEGEND_BANDS.map(([cls, label]) => (
        <span key={cls} className="row" style={{ gap: 4 }}>
          <span className={`b ${cls}`} style={{ width: 12, height: 12, padding: 0, borderRadius: 3 }} />
          {label}
        </span>
      ))}
      <span className="row" style={{ gap: 4 }}>
        <span style={{ width: 12, height: 12, border: "2px dashed var(--z-org)", borderRadius: 3 }} />
        Thin
      </span>
      <span className="row" style={{ gap: 4 }}>
        <Icon name="lock" size={10} /> Capped
      </span>
    </div>
  );
}

/* ── Synthesis drawer ─────────────────────────────────────────────────── */
/**
 * Backend `/api/v1/entities/{id}/heatmap/subcap/{subcap_id}` returns:
 *   {
 *     entity_display_id: string,
 *     subcap_id: string,
 *     cells: HeatmapCell[],   // typically length 1 (the requested subcap)
 *     narrative: HeatmapNarrative | null,
 *     catalogue_version: string,
 *     run_request_id: string | null
 *   }
 *
 * Pre-2026-06-05 this drawer assumed a flat shape (data.name, data.score,
 * data.rationale, data.evidence_e_ids) that the backend never returned —
 * caused `data.score.toFixed` to throw when score was undefined. Now we
 * read from cells[0] + narrative.per_subcap_md[subcap_id]. The drawer
 * defers evidence display to the existing EvidenceDrawer (opened via a
 * "View evidence" button) since per-subcap E-ID resolution requires a
 * separate run-scoped query.
 */
interface SubcapEvidenceRow {
  e_id: string;
  source_name: string;
  source_url: string | null;
  excerpt: string;
  claim_type: string;
  tier: number;
  recency_months: number | null;
  published_date: string | null;
  freshness_band: string | null;
}

interface SubcapIssueRow {
  issue_id: string;
  title: string;
  severity: string;
  rationale: string | null;
  opened_on: string | null;
  /** REAL cap ceiling from caps_applied_log ("2.5"); null when unrecorded. */
  cap_ceiling: string | null;
}

interface SubcapDetailResponse {
  entity_display_id: string;
  subcap_id: string;
  cells: HeatmapCell[];
  narrative: HeatmapNarrative | null;
  // Batch 6 (heatmap.py:425): polished rationale + cap_reason. Optional —
  // older runs / customer-stripped responses may omit them.
  polished_rationale?: string | null;
  polished_cap_reason?: string | null;
  /** Migration 051 durable per-subcap synthesis (llm > heuristic). */
  synthesis_md?: string | null;
  synthesis_source?: "llm" | "heuristic" | null;
  synthesis_evidence_e_ids?: string[];
  synthesis_model?: string | null;
  /** Evidence-first list (evidence_index rows linked to this subcap). */
  evidence?: SubcapEvidenceRow[];
  /** Open issues linked to this subcap, each with its real cap level. */
  issues?: SubcapIssueRow[];
  catalogue_version: string;
  run_request_id: string | null;
}

/* Tall peer-scale visualization — wireframe SynthesisDrawer (07_pages_c.js:
 * 700-719): a 36px track with M1..M5 gridlines, an entity marker (maturity-
 * colored block) and a peer-median tick, then the M1..M5 axis labels +
 * Entity/Peer legend with the signed gap. Shared by the subcap + category
 * synthesis drawers. */
function PeerScaleViz({ score, peer }: { score: number | null; peer: number | null }): JSX.Element {
  const gap = score != null && peer != null ? peer - score : null;
  return (
    <div className="card-tile" style={{ marginBottom: 14, background: "var(--z-lav)", border: 0 }}>
      <div className="row" style={{ marginBottom: 10, gap: 6 }}>
        <Icon name="scale" size={13} />
        <span style={{ fontSize: 12, fontWeight: 600 }}>Peer comparison</span>
      </div>
      <div style={{ position: "relative", height: 36, background: "#fff", borderRadius: 6, overflow: "hidden", marginBottom: 8 }}>
        {[1, 2, 3, 4, 5].map((t) => (
          <div key={t} style={{ position: "absolute", left: `${((t - 1) / 4) * 100}%`, top: 0, bottom: 0, width: 1, background: "var(--z-sep)" }} />
        ))}
        {score != null ? (
          <div title="Entity" style={{ position: "absolute", left: `calc(${((score - 1) / 4) * 100}% - 6px)`, top: 4, width: 12, height: 28, background: maturityHex(score), borderRadius: 3, boxShadow: "0 1px 3px rgba(0,0,0,.2)" }} />
        ) : null}
        {peer != null ? (
          <div title="Peer median" style={{ position: "absolute", left: `calc(${((peer - 1) / 4) * 100}% - 1px)`, top: 0, bottom: 0, width: 2, background: "var(--z-dpur)" }} />
        ) : null}
      </div>
      <div className="row" style={{ fontSize: 11, color: "var(--z-muted)" }}>
        <span>M1</span><span className="spacer" /><span>M2</span><span className="spacer" /><span>M3</span><span className="spacer" /><span>M4</span><span className="spacer" /><span>M5</span>
      </div>
      <div className="row" style={{ marginTop: 10, fontSize: 12 }}>
        <span className="row" style={{ gap: 5 }}>
          <span style={{ width: 10, height: 10, borderRadius: 3, background: maturityHex(score) }} /> Entity <strong>{score != null ? score.toFixed(1) : "—"}</strong>
        </span>
        <span className="spacer" />
        <span className="row" style={{ gap: 5 }}>
          <span style={{ width: 2, height: 12, background: "var(--z-dpur)" }} /> Peer <strong>{peer != null ? peer.toFixed(1) : "—"}</strong>
        </span>
        <span className="spacer" />
        {gap != null ? (
          <span style={{ fontSize: 11, color: gap > 0 ? "var(--z-below)" : "var(--z-mid)" }}>
            {gap > 0 ? `−${gap.toFixed(1)}` : `+${Math.abs(gap).toFixed(1)}`}
          </span>
        ) : null}
      </div>
    </div>
  );
}

/* Capped-by-issue callout — wireframe SynthesisDrawer (07_pages_c.js:723).
 * The subcap endpoint returns `cap_reason` (+ a polished variant) but not a
 * structured issue→cap map, so we render the cap reason prose + the cell's
 * issue_count rather than the wireframe's per-issue chip list. */
function CappedCallout({ reason, issueCount }: { reason: string | null; issueCount: number }): JSX.Element | null {
  if (!reason && issueCount === 0) return null;
  return (
    <div className="co co-org" style={{ marginBottom: 14 }}>
      <Icon name="lock" size={14} />
      <div style={{ flex: 1 }}>
        <div className="co-title">
          {issueCount > 0 ? `Capped by ${issueCount} issue${issueCount === 1 ? "" : "s"}` : "Score capped"}
        </div>
        {reason ? <div style={{ fontSize: 12, marginTop: 4, lineHeight: 1.5 }}>{reason}</div> : null}
      </div>
    </div>
  );
}

function SynthesisDrawer({
  displayId, subcapId, run, gridNarrative, gridCell, onClose,
}: {
  displayId: string | null;
  subcapId: string;
  // 2026-06-06 QA-2: drawer must follow the parent page's selected
  // run. Without `run` here, an operator on a historical run got
  // drawer content from the latest ACTIVE run (different data).
  run: string | null;
  // Pack-first fallbacks from the already-fetched grid snapshot. The live
  // per-subcap endpoint is unreachable when the app serves the pack first
  // (cold deploy), so on cold serve the drawer renders this subcap's cell +
  // baked synthesis from the grid instead of empty.
  gridNarrative?: HeatmapNarrative | null;
  gridCell?: HeatmapCell | null;
  onClose: () => void;
}): JSX.Element {
  const openDrawer = useUiStore((s) => s.openDrawer);
  const setIpSurface = useUiStore((s) => s.setIpSurface);
  const setIpOpen = useUiStore((s) => s.setIpOpen);
  const pushToast = useUiStore((s) => s.pushToast);
  const { data, isLoading } = useQuery({
    // `run` MUST be in the query key so React Query treats different
    // runs as distinct cache entries.
    queryKey: ["subcapDetail", displayId, subcapId, run ?? "active"],
    queryFn: () =>
      apiGet<SubcapDetailResponse>(
        `/api/v1/entities/${displayId}/heatmap/subcap/${encodeURIComponent(subcapId)}`,
        { run: run ?? undefined },
      ),
    enabled: !!(displayId && subcapId),
    staleTime: 5 * 60_000,
  });

  // Defensive: even with cells[] returning length 1, treat the first cell
  // as optional so a future "subcap aliased + no longer mapped" case
  // renders the empty branch instead of crashing. On cold/pack serve the
  // live fetch yields nothing, so fall back to the grid snapshot's cell.
  const cell = data?.cells?.[0] ?? gridCell ?? null;
  // Prefer the Batch-6 polished rationale; fall back to the raw per-subcap
  // narrative markdown the heatmap response carries.
  const rationale = data?.polished_rationale ?? data?.narrative?.per_subcap_md?.[subcapId] ?? null;
  const capReason = data?.polished_cap_reason ?? cell?.cap_reason ?? null;
  // Evidence-first list (prototype "Source reports & evidence",
  // fc639245:772-805): structured evidence_index rows from the subcap
  // endpoint — tier chip + tier·claim + recency + title + excerpt, each
  // opening the EvidenceDrawer scoped to that E-ID. Falls back to the
  // cell's attached E-IDs (bare chips) for pre-upgrade responses.
  const evidenceRows = data?.evidence ?? [];
  const fallbackEvidence = evidenceRows.length === 0
    ? ((cell as { enrichment_evidence_ids?: string[] } | null)
        ?.enrichment_evidence_ids ?? []).slice(0, 5)
    : [];
  // Per-issue caps block (prototype fc639245:757-770) — real cap levels.
  const issueRows = data?.issues ?? [];
  // Durable per-subcap synthesis (migration 051; llm > heuristic). The live
  // per-subcap endpoint wins; on cold/pack serve it returns nothing, so fall
  // back to the same synthesis baked into the grid snapshot's narrative
  // (export_startup_pages folds subcap_narratives into heatmap.json).
  const snapshotSynthesisMd = gridNarrative?.per_subcap_md?.[subcapId] ?? null;
  const snapshotSynthesisSource = gridNarrative?.per_subcap_meta?.[subcapId] ?? null;
  const synthesisMd = data?.synthesis_md ?? snapshotSynthesisMd;
  const synthesisSource = data?.synthesis_source ?? snapshotSynthesisSource;

  const copySynthesis = (): void => {
    // Prototype footer action (fc639245:841-845, audit transition #23).
    const lines = [
      cell?.label ?? subcapId,
      `Score ${cell?.score != null ? cell.score.toFixed(1) : "—"}`
        + (cell?.band ? ` (${cell.band})` : "")
        + (cell?.peer_median != null ? ` · peer median ${cell.peer_median.toFixed(1)}` : ""),
      synthesisMd ?? rationale ?? "",
    ].filter(Boolean);
    try {
      void navigator.clipboard.writeText(lines.join("\n"));
      pushToast("Synthesis copied", "success");
    } catch {
      pushToast("Couldn't access clipboard", "warn");
    }
  };

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && onClose()}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,.35)",
        // Match the app drawer scale (.drawer-mask 90 / .drawer 95) so
        // the drawer overlays the grid AND the global .ip panel (z 70)
        // never covers an open drawer. The old inline 600 beat the
        // entire app z-scale (incl. tooltips + toasts).
        zIndex: 90, display: "flex", justifyContent: "flex-end",
      }}
    >
      <div role="dialog" aria-label="Sub-capability synthesis"
           style={{
             width: 480, maxWidth: "100%", background: "var(--z-white)",
             height: "100%", overflowY: "auto", padding: "24px 20px",
             display: "flex", flexDirection: "column", gap: 20,
           }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 4 }}>
              SYNTHESIS
            </div>
            <code style={{ fontSize: 13, color: "var(--z-mid)" }}>{subcapId}</code>
          </div>
          <button type="button" className="btn btn-tertiary btn-sm" onClick={onClose} aria-label="Close synthesis"><Icon name="x" size={14} /></button>
        </div>

        {isLoading && <div className="page-loading"><Spinner /> Loading…</div>}

        {!isLoading && cell && (
          <>
            <div>
              <h3 style={{ margin: "0 0 8px", fontSize: 16 }}>{cell.label}</h3>
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                {cell.score != null && (
                  <span style={{ fontSize: 24, fontWeight: 700, color: maturityHex(cell.score) }}>
                    {cell.score.toFixed(1)}
                  </span>
                )}
                {cell.band && <Pill tone="neutral">{cell.band}</Pill>}
                {cell.is_thin_evidence && <span className="b b-org">THIN</span>}
                {cell.cap_applied && (
                  <span title={cell.cap_reason ?? "Score capped by an unresolved issue"}>
                    <Pill tone="red">Capped</Pill>
                  </span>
                )}
              </div>
            </div>

            {/* Tall peer-scale viz with M1..M5 markers (fc639245:728-754). */}
            {cell.peer_median != null ? (
              <PeerScaleViz score={cell.score} peer={cell.peer_median} />
            ) : null}

            {/* Caps block (fc639245:757-770): per-issue chip + Cap M{n}
                from caps_applied_log; falls back to the prose callout
                when the cell is capped but no issue rows resolved. */}
            {issueRows.length > 0 ? (
              <div className="co co-org" style={{ marginBottom: 0 }}>
                <Icon name="lock" size={14} />
                <div style={{ flex: 1 }}>
                  <div className="co-title">
                    Capped by {issueRows.length} issue{issueRows.length === 1 ? "" : "s"}
                  </div>
                  {issueRows.map((iss) => (
                    <div key={iss.issue_id} style={{ fontSize: 12, marginTop: 4 }}>
                      <span className="chip" style={{ marginRight: 6 }}>{iss.issue_id}</span>
                      {(iss.rationale ?? iss.title ?? "").slice(0, 70)}
                      {(iss.rationale ?? iss.title ?? "").length > 70 ? "…" : ""}{" "}
                      {iss.cap_ceiling ? (
                        <strong>
                          Cap {String(iss.cap_ceiling).toUpperCase().startsWith("M")
                            ? String(iss.cap_ceiling).toUpperCase()
                            : `M${iss.cap_ceiling}`}
                        </strong>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : cell.cap_applied ? (
              <CappedCallout reason={capReason} issueCount={cell.issue_count} />
            ) : null}

            {/* Source reports & evidence — shown BEFORE any AI section
                (fc639245:772-805). Tier chip + tier·claim + recency +
                title + source + italic excerpt; click opens the
                EvidenceDrawer scoped to that E-ID. */}
            <div>
              <div className="row" style={{ marginBottom: 8, gap: 6 }}>
                <Icon name="evidence" size={13} style={{ color: "var(--z-mid)" }} />
                <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-dark)", textTransform: "uppercase" }}>
                  Source reports &amp; evidence
                </span>
                <span className="b b-muted">{evidenceRows.length || fallbackEvidence.length}</span>
                <span className="spacer" />
                <span style={{ fontSize: 10, color: "var(--z-muted)" }}>click an ID to open</span>
              </div>
              {evidenceRows.length === 0 && fallbackEvidence.length === 0 ? (
                <div className="co co-org" style={{ marginBottom: 0 }}>
                  <Icon name="warn" size={13} />
                  <div className="co-body">
                    No evidence item directly cites this subcap in this run —
                    the score is inferred. Treat as provisional until corroborated.
                  </div>
                </div>
              ) : evidenceRows.length > 0 ? (
                evidenceRows.map((ev) => (
                  <button key={ev.e_id} type="button" className="card-tile clickable"
                          data-testid="evidence-row"
                          style={{ width: "100%", padding: 11, marginBottom: 6, textAlign: "left" }}
                          onClick={() => openDrawer("evidence", {
                            eId: ev.e_id, subcapId, origin: "synthesis-drawer", displayId,
                            // Full citation list of this subcap's rows so the
                            // drawer scopes to exactly what's listed here.
                            eIds: evidenceRows.map((r) => r.e_id),
                            score: cell?.score ?? null,
                          })}>
                    <div className="row" style={{ marginBottom: 4, gap: 6 }}>
                      <span className={`tier-chip tier-T${ev.tier}`}>{ev.e_id}</span>
                      <span className="b b-muted">T{ev.tier} · {ev.claim_type}</span>
                      <span className="spacer" />
                      <span style={{ fontSize: 10, color: "var(--z-muted)" }}>
                        {ev.recency_months != null ? `${ev.recency_months}mo` : ev.freshness_band ?? ""}
                      </span>
                    </div>
                    <div className="txt-fit-1" style={{ fontSize: 12, fontWeight: 600, color: "var(--z-dark)" }}>
                      {ev.source_name}
                    </div>
                    {ev.excerpt ? (
                      <div style={{ fontSize: 11, color: "var(--z-body)", lineHeight: 1.5, marginTop: 6, paddingLeft: 8, borderLeft: "2px solid var(--z-sep)", fontStyle: "italic" }}>
                        "{ev.excerpt.slice(0, 220)}{ev.excerpt.length > 220 ? "…" : ""}"
                      </div>
                    ) : null}
                  </button>
                ))
              ) : (
                fallbackEvidence.map((eid) => (
                  <button key={eid} type="button" className="card-tile clickable"
                          style={{ width: "100%", padding: 11, marginBottom: 6, textAlign: "left" }}
                          onClick={() => openDrawer("evidence", {
                            eId: eid, subcapId, origin: "synthesis-drawer", displayId,
                            eIds: fallbackEvidence,
                            score: cell?.score ?? null,
                          })}>
                    <div className="row" style={{ gap: 6 }}>
                      <span className="chip">{eid}</span>
                      <span className="spacer" />
                      <Icon name="chevron-r" size={11} />
                    </div>
                  </button>
                ))
              )}
            </div>

            {rationale && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--z-muted)", marginBottom: 6 }}>
                  Score rationale
                </div>
                <p style={{ margin: 0, fontSize: 13, color: "var(--z-body)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
                  {rationale}
                </p>
              </div>
            )}

            {/* AI synthesis — explicitly layered AFTER the evidence above
                (fc639245:823-838). Body = the durable subcap_narratives
                row (validated Gemini when available, deterministic
                composer floor otherwise); the source chip mirrors the
                cell's data-source provenance contract. */}
            {synthesisMd ? (
              <div className="card-tile" data-testid="ai-synthesis"
                   style={{ background: "var(--ph0-lt)", border: "1px solid var(--ph0-bd)", padding: 12 }}>
                <div className="row" style={{ marginBottom: 6, gap: 6 }}>
                  <Icon name="sparkle" size={13} style={{ color: "var(--z-dpur)" }} />
                  <span style={{ fontSize: 11, fontWeight: 700, color: "var(--z-dpur)", letterSpacing: ".08em", textTransform: "uppercase" }}>
                    AI synthesis
                  </span>
                  {synthesisSource ? (
                    <span className="b b-muted" data-source={synthesisSource}>{synthesisSource}</span>
                  ) : null}
                  <span className="spacer" />
                  <span style={{ fontSize: 9.5, color: "var(--z-dpur)", opacity: .85 }}>
                    on the {evidenceRows.length || fallbackEvidence.length} item{(evidenceRows.length || fallbackEvidence.length) === 1 ? "" : "s"} above
                  </span>
                </div>
                <div style={{ fontSize: 12.5, color: "#3B0764", lineHeight: 1.6 }}>
                  {synthesisMd}
                </div>
              </div>
            ) : null}

            <div>
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={() =>
                  openDrawer("evidence", {
                    subcapId,
                    origin: "synthesis-drawer",
                    displayId,
                    // Header subline context (proto "score · confidence").
                    score: cell?.score ?? null,
                  })
                }
              >
                View evidence for {subcapId}
              </button>
            </div>
          </>
        )}

        {!isLoading && !cell && (
          <EmptyState title="Subcap detail unavailable" body="No score detail found for this cell." />
        )}

        {/* 2026-07 Part 10.1 fix: the drawer used to EMBED a second
            IntelligencePanel instance here (open={!!data}, no-op
            onClose) — it auto-opened over the drawer the moment data
            loaded, was un-dismissable, and opened a duplicate SSE
            stream. The prototype SynthesisDrawer has no embedded panel;
            the single global panel (DrawerHost) opens on demand only,
            via this explicit button (same pattern as PlatformPage
            "Platform story"). */}
        {displayId && (
          <div>
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => {
                setIpSurface("subcap_narrative", { ref: `${displayId}:${subcapId}` });
                setIpOpen(true);
              }}
            >
              <Icon name="sparkle" size={13} /> Ask AI about this subcap
            </button>
          </div>
        )}

        {/* Footer — prototype drawer-foot (fc639245:840-847): Copy
            synthesis + Close. */}
        <div className="row" style={{ marginTop: "auto", paddingTop: 12, borderTop: "1px solid var(--z-sep)", gap: 8 }}>
          <button type="button" className="btn btn-tertiary" onClick={copySynthesis}>
            <Icon name="copy" size={13} /> Copy synthesis
          </button>
          <span className="spacer" />
          <button type="button" className="btn btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

/* ── Category synthesis drawer ────────────────────────────────────────────
 * Wireframe SynthesisDrawer category path (07_pages_c.js:657-789, item.catId):
 * a category-level rollup with the peer-scale viz, the linked insight cards,
 * and the category's subcaps as a list that drills into per-subcap synthesis.
 * Built entirely from the already-fetched heatmap cells (no extra request) —
 * the backend has no category-detail endpoint, so this composes client-side
 * exactly like the wireframe. */
function CategorySynthesisDrawer({
  categoryId, categoryName, cells, displayId, run, onClose, onOpenSynthesis,
}: {
  categoryId: string;
  categoryName: string | null;
  cells: HeatmapCell[];
  // `insights` was an early prop; the drawer now fetches its own via the
  // run-scoped hook. Kept off the type to avoid a dead parameter.
  insights?: undefined;
  displayId: string | null;
  run: string | null;
  onClose: () => void;
  onOpenSynthesis: (subcapId: string) => void;
}): JSX.Element {
  const subs = useMemo(
    () => cells.filter((c) => categoryIdOf(c.id) === categoryId).sort((a, b) => a.id.localeCompare(b.id)),
    [cells, categoryId],
  );
  const agg = aggregateCells(subs);
  const insightsQ = useEntityInsights(displayId, run);
  const catInsights = (insightsQ.data?.items ?? []).filter(
    (ic) => categoryIdOf(ic.linked_subcap_id) === categoryId,
  );

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && onClose()}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,.35)",
        // Drawer scale (see SynthesisDrawer): mask 90 keeps parity with
        // .drawer-mask; the .ip panel (z 70) stays underneath.
        zIndex: 90, display: "flex", justifyContent: "flex-end",
      }}
    >
      <div role="dialog" aria-label="Category synthesis"
           style={{ width: 480, maxWidth: "100%", background: "var(--z-white)", height: "100%", overflowY: "auto", padding: "24px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="row" style={{ marginBottom: 4, gap: 6 }}>
              <span className="b b-teal">SYNTHESIS</span>
              <span className="chip">{categoryId}</span>
            </div>
            <div style={{ fontSize: 15, fontWeight: 600 }}>{categoryName ?? `Category ${categoryId}`}</div>
            <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 2 }}>
              {subs.length} subcaps
              {agg.thin > 0 ? ` · ${agg.thin} thin` : ""}
              {agg.capped > 0 ? ` · ${agg.capped} capped` : ""}
            </div>
          </div>
          <button type="button" className="btn btn-tertiary btn-sm" onClick={onClose} aria-label="Close synthesis"><Icon name="x" size={14} /></button>
        </div>

        <PeerScaleViz score={agg.avg} peer={agg.peerAvg} />

        {catInsights.length > 0 ? (
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>
              Linked insight cards · {catInsights.length}
            </div>
            {catInsights.map((ic) => {
              const flag = insightFlag(ic.severity);
              return (
                <div key={ic.id} className="card-tile" style={{ width: "100%", padding: 11, marginBottom: 6 }}>
                  <div className="row" style={{ marginBottom: 4, gap: 6 }}>
                    <span className="ic-id">{ic.ic_id}</span>
                    <span className={`b ${flag.cls}`}>{flag.label}</span>
                  </div>
                  <div className="txt-fit-1" style={{ fontSize: 12.5, fontWeight: 600 }}>{ic.title}</div>
                </div>
              );
            })}
          </div>
        ) : null}

        <div>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>
            Subcaps · {subs.length}
          </div>
          {subs.length === 0 ? (
            <div className="muted" style={{ fontSize: 12 }}>No scored subcaps in this category.</div>
          ) : subs.map((s) => (
            <button key={s.id} type="button" className="card-tile clickable"
                    style={{ width: "100%", padding: 11, marginBottom: 6, textAlign: "left" }}
                    onClick={() => onOpenSynthesis(s.id)}>
              <div className="row" style={{ gap: 6 }}>
                <MaturityScoreChip score={s.score} />
                <span className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{s.id}</span>
                <span className="spacer" />
                {s.is_thin_evidence ? <span className="b b-org">THIN</span> : null}
                {s.cap_applied ? <Icon name="lock" size={11} style={{ opacity: .8 }} /> : null}
              </div>
              <div className="txt-fit-1" style={{ fontSize: 12, color: "var(--z-dark)", marginTop: 3 }}>{s.label}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Issue Register banner ─────────────────────────────────────────────────
 * Prototype IssueRegisterBanner (fc639245:853-920, audit transition #16):
 * rendered above the Standard grid when the Issues overlay is on. Each OPEN
 * issue is an EXPANDABLE tile — the header button toggles a detail panel
 * (spanning the full row) with the Status / Cap M{n} / Since facts, the
 * capped-subcap chips (`{sid} · M{cap} · {name}` → that subcap's synthesis)
 * and the linked evidence chips (→ EvidenceDrawer scoped to the E-ID).
 *
 * Data: the D5 context endpoint's `issue_register` (OPEN/RESOLVED +
 * linked_subcap_ids) + `capsBySubcap` — the REAL per-subcap cap ceiling
 * from the health surface's caps_applied rows (caps_applied_log), which
 * replaces the old cell.score proxy. Evidence chips come from the capped
 * cells' enrichment_evidence_ids (now attached router-side). */
function IssueRegisterBanner({
  displayId, run, cells, capsBySubcap, onOpenSynthesis,
}: {
  displayId: string | null;
  run: string | null;
  cells: HeatmapCell[];
  capsBySubcap: Record<string, string>;
  onOpenSynthesis: (subcapId: string) => void;
}): JSX.Element | null {
  const ctxQ = useEntityContext(displayId, run);
  const openDrawer = useUiStore((s) => s.openDrawer);
  const [openId, setOpenId] = useState<string | null>(null);
  const cellById = useMemo(() => new Map(cells.map((c) => [c.id, c])), [cells]);
  // Client-business issues only (the backend already filters
  // assessment-QA meta rows; the kind guard is defensive for old packs).
  const openIssues: IssueRegisterOut[] = (ctxQ.data?.issue_register ?? []).filter(
    (i) => i.status === "OPEN" && (i.kind ?? "client") !== "assessment_qa",
  );
  if (openIssues.length === 0) return null;

  const sevClass = (sev: string): string => {
    const s = sev.toUpperCase();
    if (s === "CRITICAL") return "b-below";
    if (s === "MATERIAL" || s === "HIGH" || s === "MAJOR") return "b-org";
    return "b-muted";
  };

  return (
    <div className="card" style={{ marginBottom: 12, padding: 14, background: "rgba(254,151,50,.06)", border: "1px solid rgba(254,151,50,.28)" }}>
      <div className="row" style={{ marginBottom: 10, gap: 8 }}>
        <Icon name="warn" size={14} style={{ color: "var(--z-org)" }} />
        <strong style={{ fontSize: 13, color: "var(--z-dark)" }}>Issue register · {openIssues.length} open</strong>
        <span className="b b-muted">click an issue to drill in</span>
        <span className="spacer" />
        {displayId ? (
          <a href={`#/clients/${displayId}/context`} style={{ fontSize: 11, color: "var(--z-mid)", fontWeight: 600 }}>Full register →</a>
        ) : null}
      </div>
      <div className="g2" style={{ gap: 8 }}>
        {openIssues.map((iss) => {
          const caps = iss.linked_subcap_ids ?? [];
          const isOpen = openId === iss.id;
          // Per-issue cap level: the issue's own parsed cap levels
          // (register Cap_Value / "CAPS P1C2 @3.0") first, then the
          // ceiling recorded for its linked subcaps (caps_applied_log);
          // "—" when neither recorded.
          const ownCapLevels = Object.values(iss.caps ?? {});
          const issueCap =
            (ownCapLevels.length ? `M${Math.min(...ownCapLevels)}` : null)
            ?? caps.map((sid) => capsBySubcap[sid]).find(Boolean)
            ?? null;
          // Evidence chips: union of the capped cells' attached E-IDs.
          const evidenceIds = isOpen
            ? [...new Set(caps.flatMap((sid) =>
                ((cellById.get(sid) as { enrichment_evidence_ids?: string[] } | undefined)
                  ?.enrichment_evidence_ids ?? [])))].slice(0, 8)
            : [];
          return (
            <div key={iss.id} className="card-tile" data-testid="issue-tile"
                 style={{ padding: 0, background: "#fff", gridColumn: isOpen ? "1 / -1" : "auto", overflow: "hidden" }}>
              <button type="button"
                      onClick={() => setOpenId((o) => (o === iss.id ? null : iss.id))}
                      aria-expanded={isOpen}
                      style={{ width: "100%", background: "none", border: 0, cursor: "pointer", textAlign: "left", padding: 10 }}>
                <div className="row" style={{ marginBottom: 6, gap: 6 }}>
                  <span className="chip">{iss.issue_id}</span>
                  <span className={`b ${sevClass(iss.severity)}`}>{iss.severity}</span>
                  <span className="spacer" />
                  <Icon name="lock" size={11} style={{ color: "var(--z-org)" }} />
                  <span style={{ fontSize: 10, color: "var(--z-muted)" }}>caps {caps.length}</span>
                  <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={13} style={{ color: "var(--z-muted)" }} />
                </div>
                <div className={isOpen ? "" : "txt-fit-2"} style={{ fontSize: 12, color: "var(--z-dark)", lineHeight: 1.5 }}>
                  {iss.rationale ?? iss.title}
                </div>
              </button>
              {isOpen ? (
                <div style={{ padding: "0 10px 10px" }}>
                  <div className="row" style={{ gap: 12, fontSize: 11, color: "var(--z-muted)", marginBottom: 8, flexWrap: "wrap" }}>
                    <span>Status <strong style={{ color: "var(--z-org)" }}>{iss.status}</strong></span>
                    <span>Cap <strong style={{ color: "var(--z-dark)" }}>{issueCap ?? "—"}</strong></span>
                    {iss.opened_on ? (
                      <span>Since <strong style={{ color: "var(--z-dark)" }}>{iss.opened_on}</strong></span>
                    ) : null}
                  </div>
                  {iss.dma_impact ? (
                    <div data-testid="issue-dma-impact" style={{ fontSize: 11.5, fontWeight: 600, color: "var(--z-dark)", lineHeight: 1.5, marginBottom: 8 }}>
                      {iss.dma_impact}
                    </div>
                  ) : null}
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 4 }}>
                    Capped subcaps · click to drill
                  </div>
                  <div className="row" style={{ flexWrap: "wrap", gap: 4, marginBottom: evidenceIds.length ? 10 : 0 }}>
                    {caps.map((sid) => {
                      const cell = cellById.get(sid);
                      // The issue's own parsed level for this subcap wins;
                      // caps_applied_log ceiling is the fallback.
                      const ownLevel = iss.caps?.[sid];
                      const capLevel = ownLevel != null ? `M${ownLevel}` : capsBySubcap[sid];
                      const label = `${sid}${capLevel ? ` · ${capLevel}` : ""}${cell?.label ? ` · ${cell.label}` : ""}`;
                      return (
                        <button key={sid} type="button" className="chip purple"
                                onClick={() => onOpenSynthesis(sid)}
                                title={`${cell?.label ?? sid}${capLevel ? ` · capped at ${capLevel}` : ""}${cell?.cap_reason ? ` · ${cell.cap_reason}` : ""}`}>
                          {label}
                        </button>
                      );
                    })}
                  </div>
                  {evidenceIds.length > 0 ? (
                    <>
                      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 4 }}>
                        Evidence · click to open
                      </div>
                      <div className="row" style={{ flexWrap: "wrap", gap: 4 }}>
                        {evidenceIds.map((eid) => (
                          <button key={eid} type="button" className="chip f-mono"
                                  style={{ cursor: "pointer", border: 0 }}
                                  title={`Open evidence ${eid}`}
                                  onClick={() => openDrawer("evidence", { eId: eid, eIds: evidenceIds, origin: "issue-banner", displayId })}>
                            {eid}
                          </button>
                        ))}
                      </div>
                    </>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export { maturityLabel };
