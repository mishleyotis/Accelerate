/**
 * DashboardHome — ported 1:1 from the prototype
 * (standalone-src/src/pages-auth-dashboard-directory.jsx · DashboardHome).
 *
 * Mock-data reads (DMA.ENTITIES / DMA.ALERTS / DMA.INSIGHT_CARDS) are
 * replaced with the real TanStack-Query hooks (`useDashboard`,
 * `useEntities`, `useAlerts`). Section structure / class vocabulary /
 * layout grid (`.page-head`, `.g4`, `.card.flush`, `.card-tile`,
 * `.batch-row`, etc.) is kept verbatim so the page renders 1:1 with the
 * prototype.
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAlerts, useDashboard, useEntities } from "@/lib/queries";
import { apiGet } from "@/lib/api";
import { maturityHex, maturityLabel } from "@/lib/maturity";
import { useRoute } from "@/lib/hash-router";
import { useAuthStore, useEffectiveRole } from "@/store/auth";
import { useUiStore } from "@/store/ui";
import { Icon, FreshnessDot, TimeAgo } from "@/components/utils";
import { subverticalLabel } from "@/lib/labels";
import { healName, healSubvertical } from "@/lib/heal";

const PILLARS = [
  { id: "P1", short: "Strategy" },
  { id: "P2", short: "Customer" },
  { id: "P3", short: "Operations" },
  { id: "P4", short: "Data & Tech" },
];

// ── Admin System-health card sources (plan Part 11.2) ────────────────
// Mirrors backend `/admin/import-audit/summary`, `/admin/vertex-budget`,
// `/admin/pending-review` (all live endpoints — see routers/admin.py).
interface ImportAuditSummary {
  last_crawl_at: string | null;
  candidates_processed: number;
  files_imported: number;
  files_excluded: number;
  files_awaiting_review: number;
  files_errored: number;
}
interface VertexBudgetResponse {
  period: string;
  spent_usd: number;
  budget_usd: number;
  pct_used: number;
}
interface PendingReviewResponse {
  items: unknown[];
  counts_by_kind: Record<string, number>;
}

interface EntitySummaryUI {
  id: string;
  display_id: string;
  name: string;
  subvertical: string | null;
  hq?: string | null;
  overall: number | null;
  assessment_date: string | null;
  data_source: string | null;
  open_alerts: number;
  in_progress: boolean;
  status: string | null;
  current_batch: number | null;
  pillar_scores?: Record<string, number> | null;
  oss?: Record<string, number> | null;
}

export function DashboardPage(): JSX.Element {
  const role = useEffectiveRole();
  // Wireframe greeting is personal: "Good morning, Mishley" — bind the
  // signed-in user's first name (the page previously hardcoded a name
  // for analysts, a wireframe-completeness violation).
  const userName = useAuthStore((s) => s.user?.name ?? null);
  const firstName =
    typeof userName === "string" && userName.trim()
      ? userName.trim().split(/\s+/)[0]
      : null;
  const { navigate } = useRoute();
  const openDrawer = useUiStore((s) => s.openDrawer);

  const dashQ = useDashboard("all");
  const entitiesQ = useEntities({ owner: "all" });
  const alertsQ = useAlerts();

  // System-health card (ADMIN only) — pre-fix all three rows rendered a
  // hardcoded "—" although the backend endpoints have been live since
  // migration 020 (Drive crawl) / deliverable #7 (budget + pending).
  const isAdminRole = role === "ADMIN";
  const importSummaryQ = useQuery({
    queryKey: ["adminImportSummary"],
    queryFn: () => apiGet<ImportAuditSummary>("/api/v1/admin/import-audit/summary"),
    enabled: isAdminRole,
    staleTime: 60 * 1000,
    retry: 0,
  });
  const vertexBudgetQ = useQuery({
    queryKey: ["adminVertexBudget"],
    queryFn: () => apiGet<VertexBudgetResponse>("/api/v1/admin/vertex-budget"),
    enabled: isAdminRole,
    staleTime: 60 * 1000,
    retry: 0,
  });
  const pendingReviewQ = useQuery({
    queryKey: ["adminPendingReview"],
    queryFn: () => apiGet<PendingReviewResponse>("/api/v1/admin/pending-review"),
    enabled: isAdminRole,
    staleTime: 60 * 1000,
    retry: 0,
  });

  // Map the real `EntityListResponse` items into the prototype's UI shape.
  // Pre-2026-06-05 every field below was an `(e as {...}).field` cast
  // that hid contract drift -- the page read `last_run_completed_at`
  // when the backend exposed `last_run_at`, so every assessment date
  // rendered as `—`. Synced the frontend EntitySummary type to the
  // backend schema so the compiler enforces the contract; the casts
  // are gone, the dates show up. `hq` / `oss` aren't on backend yet --
  // explicitly null until the corresponding columns ship.
  const ent: EntitySummaryUI[] = useMemo(() => {
    const items = entitiesQ.data?.items ?? [];
    return items.map((e) => ({
      id: e.display_id,
      display_id: e.display_id,
      name: e.name,
      subvertical: e.subvertical,
      // 2026-06-13: hq + top-OSS chip now ship from the backend
      // (firmographics.hq_address + the top platform_scores LATERAL).
      // top_platform is null when there is no real fit signal, so the
      // card chip is omitted (matches the prototype's `{top ? …}`).
      hq: e.hq,
      overall: e.overall_score,
      assessment_date: e.assessment_date ?? e.last_run_at,
      data_source: e.data_source,
      // 2026-06-06 QA-M4: backend now emits per-entity open_alerts via
      // the entities-list endpoint LATERAL subquery; consume it
      // verbatim instead of hard-coding 0.
      open_alerts: e.open_alerts,
      in_progress: e.in_progress,
      status: e.last_run_status,
      current_batch: e.current_batch,
      pillar_scores: e.pillar_scores,
      oss: e.top_platform ? { [e.top_platform.short]: e.top_platform.fit_score } : null,
    }));
  }, [entitiesQ.data]);

  const active = ent.filter((e) => e.in_progress);
  const recent = ent
    .filter((e) => !e.in_progress)
    .slice()
    .sort((a, b) => {
      const at = a.assessment_date ? Date.parse(a.assessment_date) : 0;
      const bt = b.assessment_date ? Date.parse(b.assessment_date) : 0;
      return bt - at;
    });
  const stale = ent
    .filter((e) => e.assessment_date && Date.parse(e.assessment_date) < Date.now() - 180 * 86_400_000)
    .slice(0, 3);
  const totalAlerts = alertsQ.data?.open_count ?? 0;
  // KPI tiles bind to the SERVER (dashboard endpoint) — not a client-side
  // reduce over the loaded page. Pre-fix "Active assessments" + "Avg
  // maturity" were computed in the browser, so they were wrong/stale until
  // every entity loaded (and never matched the startup-data snapshot). The
  // backend now emits assessment_count + avg_maturity tiles.
  const tile = (kind: string): number | string | undefined =>
    dashQ.data?.tiles?.find((t) => t.kind === kind)?.value;
  const scored = ent.filter((e) => e.overall != null);
  const avgMatTile = tile("avg_maturity");
  const avgMaturity =
    typeof avgMatTile === "number"
      ? avgMatTile
      : scored.length
        ? scored.reduce((acc, e) => acc + (e.overall ?? 0), 0) / scored.length
        : null;

  // QA marker: "startup" while painting the committed first-paint snapshot,
  // flips to "api" once the live refetch has resolved after mount.
  const hydratedFromApi =
    dashQ.isFetchedAfterMount && entitiesQ.isFetchedAfterMount;

  return (
    <div className="page" data-page="dashboard"
         data-source={hydratedFromApi ? "api" : "startup"}>
      <div className="page-head">
        <div>
          <div className="eyebrow">Command centre</div>
          <h1>Good morning{firstName ? `, ${firstName}` : ""}</h1>
          <div className="sub">
            {ent.length} entities · {totalAlerts} open alerts ·
            {" "}{active.length} run{active.length === 1 ? "" : "s"} in progress
            {/* Part 11.2: the two server tiles that previously rendered
                nowhere — completions dedupe to the directory's entity set
                and the catalogue version comes from ccg_catalog_versions. */}
            {tile("recent_completions") != null
              ? <> · {tile("recent_completions")} completed (7d)</>
              : null}
            {typeof tile("catalogue_version") === "string" && tile("catalogue_version") !== "—"
              ? <> · Catalogue {tile("catalogue_version")}</>
              : null}
          </div>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-tertiary" onClick={() => navigate("/admin")}>
            <Icon name="refresh" size={13} /> Re-scan Drive
          </button>
          <button type="button" className="btn btn-primary" onClick={() => openDrawer("newRun")}>
            <Icon name="plus" size={13} /> New run
          </button>
        </div>
      </div>

      {/* KPI strip */}
      <div className="g4" style={{ marginBottom: 14 }}>
        <KpiCard label="Active assessments" value={tile("assessment_count") ?? "—"}
                 sub="all subverticals" icon="users" accent="var(--z-teal)" />
        <KpiCard label="Open alerts" value={tile("open_alerts") ?? totalAlerts}
                 sub="thin-evidence" icon="bell" accent="var(--z-org)" />
        <KpiCard label="Insight cards"
                 // Backend emits `insight_count` as a tile kind on
                 // DashboardResponse; fall back to "—" only on first mount.
                 value={tile("insight_count") ?? "—"}
                 sub="across all active runs" icon="insight" accent="var(--z-mid)" />
        <KpiCard label="Avg maturity" value={avgMaturity != null ? avgMaturity.toFixed(1) : "—"}
                 sub={avgMaturity != null ? maturityLabel(avgMaturity) : "no scored runs"}
                 icon="heatmap" accent="var(--z-dpur)" />
      </div>

      {/* Active runs */}
      {active.length === 0 ? (
        <div className="card flush" style={{ marginBottom: 14 }}>
          <div className="card-head"><h3>Active runs</h3></div>
          <div style={{ padding: 16, color: "var(--z-muted)" }} data-source="api-empty">
            No active runs.
          </div>
        </div>
      ) : (
        <div className="card flush" style={{ marginBottom: 14 }}>
          <div className="card-head">
            <div className="row">
              <Icon name="play" size={14} style={{ color: "var(--z-mid)" }} />
              <h3>Active runs</h3>
              <span className="b b-teal">SSE LIVE</span>
            </div>
            <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
              {active.length} in progress
            </span>
          </div>
          <div style={{ padding: 16 }}>
            {active.map((e) => (
              <div
                key={e.id}
                className="sidebar-split"
                style={{ gap: 18, alignItems: "center", marginBottom: 8 }}
              >
                <div>
                  <div className="row" style={{ marginBottom: 6 }}>
                    <strong style={{ fontSize: 14 }}>{healName(e.name)}</strong>
                    {e.subvertical ? <span className="b b-muted">{healSubvertical(e.subvertical)}</span> : null}
                    <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                      Batch {e.current_batch ?? 1} / 6 ·{" "}
                      {(e.status ?? "in_progress").replace(/_/g, " ").toLowerCase()}
                    </span>
                  </div>
                  <div className="batch-row">
                    {/* Pill state binds the real current_batch (1..6): pills
                        before it are done, the current one is active, the rest
                        idle. Defaults to 1 for a just-started run. */}
                    {["Setup", "Evidence", "Peers", "Scoring", "Analysis", "Final"].map((b, i) => {
                      const cur = e.current_batch ?? 1;
                      const cls = i + 1 < cur ? "done" : i + 1 === cur ? "active" : "";
                      return <div key={b} className={`batch-pill ${cls}`}>{i + 1}</div>;
                    })}
                  </div>
                </div>
                <button type="button" className="btn btn-secondary btn-sm"
                        onClick={() => navigate(`/clients/${e.display_id}/overview`)}>
                  Open <Icon name="arrow-r" size={11} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Two-col: client cards + sidebar */}
      <div
        className={role === "AE" ? "col" : "sidebar-split w-320"}
        style={{ gap: 14, marginBottom: 14 }}
      >
        <div>
          <div className="row" style={{ marginBottom: 10 }}>
            <Icon name="users" size={15} />
            <h3 style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>Recent assessments</h3>
            <span className="spacer" />
            <a href="#/clients"
               style={{ fontSize: 11, color: "var(--z-mid)", fontWeight: 600 }}
               onClick={(e) => { e.preventDefault(); navigate("/clients"); }}>
              View all <Icon name="arrow-r" size={11} />
            </a>
          </div>
          <div className="g2">
            {recent.slice(0, 6).map((e) => (
              <DashboardEntityCard key={e.id} e={e} onOpen={() => navigate(`/clients/${e.display_id}/overview`)} />
            ))}
            {recent.length === 0 ? (
              <div className="card muted" style={{ padding: 24 }}>No completed assessments yet.</div>
            ) : null}
          </div>
        </div>

        {role !== "AE" ? (
          <div className="col" style={{ gap: 14, display: "flex", flexDirection: "column" }}>
            <div className="card">
              <div className="row" style={{ marginBottom: 10 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: 7,
                  background: "rgba(254,151,50,.18)", color: "var(--z-org)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}><Icon name="bell" size={14} /></div>
                <strong style={{ fontSize: 13 }}>Needs attention</strong>
                <span className="b b-org" style={{ marginLeft: "auto" }}>{totalAlerts}</span>
              </div>
              <p style={{ fontSize: 12, color: "var(--z-body)", marginBottom: 10, lineHeight: 1.55 }}>
                Thin-evidence alerts across {
                  // 2026-06-06 QA-M6: was `new Set(...alerts.map(a => a.id))`
                  // which counts DISTINCT ALERT IDs (always == alerts.length
                  // since IDs are unique) -- not distinct ENTITIES. The
                  // copy says "across N entities" so the count must
                  // collapse alerts to their owning entity.
                  new Set(
                    (alertsQ.data?.items ?? [])
                      .map((a) => a.entity_display_id)
                      .filter((id): id is string => id != null),
                  ).size
                } entities.
              </p>
              <button type="button" className="btn btn-secondary btn-sm"
                      style={{ width: "100%", justifyContent: "center" }}
                      onClick={() => navigate("/alerts")}>
                Review alerts <Icon name="arrow-r" size={11} />
              </button>
            </div>

            <div className="card">
              <div className="row" style={{ marginBottom: 10 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: 7,
                  background: "rgba(194,80,8,.14)", color: "var(--z-below)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}><Icon name="warn" size={14} /></div>
                <strong style={{ fontSize: 13 }}>Stale entities</strong>
              </div>
              {stale.length === 0 ? (
                <div className="muted small" style={{ padding: "8px 0" }}>None &gt; 180 days.</div>
              ) : stale.map((e) => (
                <div key={e.id} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "8px 0", borderTop: "1px solid var(--z-sep)",
                }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600 }} className="txt-fit-1">{e.name}</div>
                    <div style={{ fontSize: 10, color: "var(--z-muted)" }}>
                      {e.assessment_date ? <TimeAgo at={e.assessment_date} /> : "—"}
                    </div>
                  </div>
                  <button type="button" className="btn btn-tertiary btn-sm"
                          onClick={() => navigate(`/clients/${e.display_id}/overview`)}>
                    Rerun
                  </button>
                </div>
              ))}
            </div>

            {role === "ADMIN" ? (
              <div className="card">
                <div className="row" style={{ marginBottom: 10 }}>
                  <div style={{
                    width: 28, height: 28, borderRadius: 7,
                    background: "var(--ph0-lt)", color: "var(--z-dpur)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}><Icon name="drive" size={14} /></div>
                  <strong style={{ fontSize: 13 }}>System health</strong>
                </div>
                {/* Part 11.2: real sources — pre-fix every row was a
                    hardcoded "—". Each row fails-closed back to "—" when
                    its endpoint errors or hasn't resolved. */}
                <div style={{ display: "grid", gap: 8, fontSize: 11.5 }} data-testid="system-health-rows">
                  <div className="row">
                    <span className="muted">Drive crawl</span><span className="spacer" />
                    <span>
                      {importSummaryQ.data?.last_crawl_at
                        ? <TimeAgo at={importSummaryQ.data.last_crawl_at} />
                        : importSummaryQ.data ? "never" : "—"}
                    </span>
                  </div>
                  <div className="row">
                    <span className="muted">Vertex AI budget</span><span className="spacer" />
                    <span>
                      {vertexBudgetQ.data
                        ? `$${vertexBudgetQ.data.spent_usd.toFixed(2)} / $${vertexBudgetQ.data.budget_usd.toFixed(0)}`
                        : "—"}
                    </span>
                  </div>
                  <div className="row">
                    <span className="muted">Pending review</span><span className="spacer" />
                    <span>
                      {pendingReviewQ.data
                        ? Object.values(pendingReviewQ.data.counts_by_kind)
                            .reduce((a, n) => a + n, 0)
                        : "—"}
                    </span>
                  </div>
                </div>
                <button type="button" className="btn btn-tertiary btn-sm"
                        style={{ width: "100%", justifyContent: "center", marginTop: 10 }}
                        onClick={() => navigate("/admin")}>
                  Open admin <Icon name="arrow-r" size={11} />
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

interface KpiCardProps {
  label: string; value: string | number; sub: string;
  icon: string; accent: string;
}

function KpiCard({ label, value, sub, icon, accent }: KpiCardProps): JSX.Element {
  return (
    <div className="card-tile" style={{ padding: 14, borderTop: `3px solid ${accent}` }}>
      <div className="row" style={{ marginBottom: 6 }}>
        <Icon name={icon} size={14} style={{ color: accent }} />
        <span style={{
          fontSize: 10, color: "var(--z-muted)",
          textTransform: "uppercase", letterSpacing: ".08em",
        }}>{label}</span>
      </div>
      <div style={{
        fontSize: 28, fontWeight: 200, color: "var(--z-dark)",
        letterSpacing: "-.02em", lineHeight: 1,
      }}>{value}</div>
      <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 4 }}>{sub}</div>
    </div>
  );
}

function DashboardEntityCard({ e, onOpen }: { e: EntitySummaryUI; onOpen: () => void }): JSX.Element {
  const matHex = maturityHex(e.overall ?? 2.5);
  const matLab = maturityLabel(e.overall ?? 2.5);
  const top = e.oss
    ? Object.entries(e.oss).sort((a, b) => b[1] - a[1])[0]
    : null;
  return (
    <div
      className="card-tile clickable"
      onClick={onOpen}
      style={{ padding: 14, display: "flex", flexDirection: "column" }}
    >
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start", marginBottom: 10 }}>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: `linear-gradient(135deg, ${matHex}, var(--z-mid))`,
          color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 14, fontWeight: 700, flexShrink: 0,
        }}>
          {healName(e.name).split(" ").map((n) => n[0]).slice(0, 2).join("")}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)", lineHeight: 1.3 }}
               className="txt-fit-2" title={healName(e.name)}>{healName(e.name)}</div>
          <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 2, lineHeight: 1.35 }}
               className="txt-fit-2">
            {subverticalLabel(e.subvertical)}{e.hq ? ` · ${e.hq}` : ""}
          </div>
        </div>
        <div style={{
          textAlign: "right", flexShrink: 0,
          display: "flex", flexDirection: "column", alignItems: "flex-end",
        }}>
          <div style={{ fontSize: 22, fontWeight: 200, color: matHex, lineHeight: 1 }}>
            {e.overall != null ? e.overall.toFixed(1) : "—"}
          </div>
          <div style={{
            fontSize: 8.5, color: matHex, fontWeight: 700,
            textTransform: "uppercase", letterSpacing: ".04em", marginTop: 3, whiteSpace: "nowrap",
          }}>{matLab}</div>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6, marginBottom: 10 }}>
        {PILLARS.map((p) => {
          const s = e.pillar_scores?.[p.id];
          return (
            <div key={p.id} title={`${p.id} · ${s != null ? s.toFixed(1) : "—"}`}
                 style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontSize: 9, color: "var(--z-muted)", fontWeight: 600 }}>{p.id}</span>
                <span style={{ fontSize: 9, color: "var(--z-body)", fontWeight: 600 }}>
                  {s != null ? s.toFixed(1) : "–"}
                </span>
              </div>
              <div style={{ height: 5, background: "var(--z-sep)", borderRadius: 2.5, overflow: "hidden" }}>
                {s != null ? (
                  <div style={{ width: `${s / 5 * 100}%`, height: "100%", background: maturityHex(s) }} />
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ flex: 1 }} />
      <div className="row" style={{ paddingTop: 8, borderTop: "1px solid var(--z-sep)" }}>
        <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
          <span className={`b ${e.data_source === "DRIVE_PARSE" ? "b-ph0" : "b-ph1"}`}>
            {e.data_source === "DRIVE_PARSE" ? "DRIVE" : "API"}
          </span>
          {e.open_alerts > 0 ? (
            <span className="b b-org"><Icon name="bell" size={9} /> {e.open_alerts}</span>
          ) : null}
          {e.assessment_date ? <FreshnessDot at={e.assessment_date} /> : null}
        </div>
        {top ? (
          <span className="spacer" style={{ fontSize: 11, color: "var(--z-mid)", textAlign: "right" }}>
            {top[0].slice(0, 3).toUpperCase()} <strong>{top[1]}</strong>
          </span>
        ) : null}
      </div>
    </div>
  );
}
