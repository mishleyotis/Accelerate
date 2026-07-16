/**
 * ClientBar — the dark client-context bar that sits below the TopBar on
 * every `/clients/{display_id}/*` route.
 *
 * Per the 2026-06 wireframe (chrome.jsx `ClientBar`/`ClientShell`):
 *
 *   ┌──────────────────────────────────────────────────────────────────┐
 *   │  ‹ Clients   Provident Bank   [ACTIVE] [DRIVE PARSE] [● Current] │
 *   │                                          [run selector]  [audience]│
 *   ├──────────────────────────────────────────────────────────────────┤
 *   │  Overview · Insights · Heatmap · Platform · Context · Tech · …   │
 *   └──────────────────────────────────────────────────────────────────┘
 *
 * Role/audience tab gating (from chrome.jsx ClientBar, ported verbatim):
 *   - always:                overview / insights / heatmap / platform /
 *                            techstack / runs
 *   - audience !== customer: + context
 *   - effectiveRole ∈        + health (with open_alerts badge)
 *     {ANALYST, ADMIN}
 *     && audience !== customer
 *
 * Banners (top of the bar):
 *   - Customer view banner   audience='customer'
 *   - Superseded run banner  selectedRunId set + that run.status !== ACTIVE
 *
 * Run selector mirrors the `?run=` hash query so the deep-link wins;
 * selecting a row navigates to `/clients/{id}/{tab}?run={request_id}`.
 */
import { useEffect, useMemo, useState } from "react";
import { useEntityRuns, type RunHistoryItem } from "@/lib/queries";
import { useRoute, buildHash } from "@/lib/hash-router";
import { useEffectiveRole } from "@/store/auth";
import { useUiStore } from "@/store/ui";
import { AudienceToggle } from "@/components/AudienceToggle";
import { Icon, TimeAgo } from "@/components/utils";
import { humanizeEnum } from "@/lib/labels";

// Prototype tab set incl. icons + ORDER (03_components_b.js:355-362 —
// note Health sits BEFORE Runs).
const CORE_TABS = [
  { key: "overview", label: "Overview", icon: "home" },
  { key: "insights", label: "Insights", icon: "insight" },
  { key: "heatmap", label: "Heatmap", icon: "heatmap" },
  { key: "platform", label: "Platform", icon: "platform" },
  { key: "techstack", label: "Tech stack", icon: "stack" },
  { key: "runs", label: "Runs", icon: "refresh" },
];

interface ClientBarProps {
  displayId: string;
  entityName: string;
  /** Active run summary for the entity (for the status / source / freshness
   *  pills) — usually `data.run` from `useEntityOverview`. */
  activeRun?: {
    request_id: string;
    status?: string | null;
    data_source?: string | null;
    completed_at?: string | null;
  } | null;
  /** Optional open-alert count for the Health tab badge. */
  openAlerts?: number;
}


// Prototype source badges (09_pages_e.js / ClientRunsPage parity):
// raw enums like MANUAL_BACKFILL read as debug output in the chrome.
function sourceText(s: string): string {
  if (s === "DRIVE_PARSE") return "DRIVE PARSE";
  if (s === "DRIVE_BACKFILL") return "DRIVE BACKFILL";
  if (s === "PROJECT_API") return "PROJECT API";
  if (s === "MANUAL_BACKFILL") return "BACKFILL";
  if (s === "BOT_REQUEST") return "BOT REQUEST";
  return s.replace(/_/g, " ");
}

// Prototype freshness pill (01_data.js freshnessOf + ClientBar:316):
// "● {label} · {n} mo", pill-fresh <=12mo else pill-stale.
function freshPill(completedAt: string | null | undefined): JSX.Element | null {
  if (!completedAt) return null;
  const months = (Date.now() - new Date(completedAt).getTime())
    / (1000 * 60 * 60 * 24 * 30.4);
  const label = months > 12 ? "Stale" : months > 6 ? "Aging" : "Current";
  const cls = months > 12 ? "pill-stale" : "pill-fresh";
  return (
    <span className={`pill ${cls}`}>
      ● {label} · {Math.max(0, Math.round(months))} mo
    </span>
  );
}


export function ClientBar({
  displayId,
  entityName,
  activeRun,
  openAlerts,
}: ClientBarProps): JSX.Element {
  const { path, query, navigate } = useRoute();
  const tab = pathTab(path);

  const audience = useUiStore((s) => s.audience);
  const setSelectedRunId = useUiStore((s) => s.setSelectedRunId);
  const effectiveRole = useEffectiveRole();

  const runQ = useEntityRuns(displayId);
  const runs = runQ.data?.items ?? [];
  const selectedRequestId = query.run ?? null;
  const selectedRun = useMemo(() => {
    if (!selectedRequestId) return runs.find((r) => r.status === "ACTIVE") ?? null;
    return runs.find((r) => r.request_id === selectedRequestId) ?? null;
  }, [runs, selectedRequestId]);

  // Mirror the resolved run's REQUEST_ID into the store. Pre-2026-06-05
  // this stored selectedRun?.id (DB UUID) but the URL hash carries
  // ?run=REQ-... (request_id) and the backend endpoints take request_id
  // too. Mixing DB uuid and request_id meant every consumer that
  // subscribed to the store and forwarded it as a query param hit the
  // wrong identifier -- one of the root causes of "run selector
  // decorative" QA finding 3.
  useEffect(() => {
    setSelectedRunId(selectedRun?.request_id ?? null);
  }, [selectedRun?.request_id, setSelectedRunId]);

  const supersededBanner =
    selectedRun && selectedRun.status === "SUPERSEDED";
  const customerBanner = audience === "customer";

  const visibleTabs = useMemo(() => {
    const out = [...CORE_TABS];
    // Context: hidden in customer view (it's the analyst's worksheet).
    if (audience !== "customer") {
      // Insert Context just before TechStack so order matches the wireframe.
      const tsIdx = out.findIndex((t) => t.key === "techstack");
      out.splice(tsIdx, 0, { key: "context", label: "Context", icon: "timeline" });
    }
    if (
      (effectiveRole === "ANALYST" || effectiveRole === "ADMIN") &&
      audience !== "customer"
    ) {
      // Prototype order: Health sits BEFORE Runs (03_components_b.js:361).
      const runsIdx = out.findIndex((t) => t.key === "runs");
      out.splice(runsIdx, 0, { key: "health", label: "Health", icon: "shield" });
    }
    return out;
  }, [audience, effectiveRole]);

  function goTab(key: string): void {
    const q: Record<string, string | undefined> = { ...query };
    navigate(buildHash(`/clients/${displayId}/${key}`, q));
  }

  return (
    <div className="client-bar-wrap" data-source="api">
      {customerBanner ? (
        <div className="customer-banner">
          <Icon name="users" size={14} />
          <span>
            <strong>Customer view</strong> - share-safe presentation mode ·
            evidence rationale, ERS, alert counts, and the Context tab are
            hidden
          </span>
          <span className="spacer" />
          <button
            type="button"
            className="btn btn-tertiary btn-sm"
            style={{ color: "#7C3500" }}
            onClick={() => useUiStore.getState().setAudience("internal")}
          >
            Switch back to Internal →
          </button>
        </div>
      ) : null}
      {supersededBanner ? (
        <div className="superseded-banner">
          <span>
            Viewing a <strong>SUPERSEDED</strong> run
            {selectedRun?.completed_at ? (
              <> · <TimeAgo at={selectedRun.completed_at} /></>
            ) : null}
            . The ACTIVE run is the default.
          </span>
          <button
            type="button"
            className="link-button"
            onClick={() => navigate(buildHash(`/clients/${displayId}/${tab}`))}
          >
            Return to active →
          </button>
        </div>
      ) : null}

      <div className="client-bar">
        <button
          type="button"
          className="icon-btn"
          style={{ color: "rgba(255,255,255,.7)" }}
          onClick={() => navigate("/clients")}
          aria-label="Back to clients"
          title="Back to directory"
        >
          <Icon name="chevron-l" size={16} />
        </button>
        <div className="client-bar-l">
          <div className="name">{entityName}</div>
          {activeRun?.status ? (
            <span className="pill pill-active">
              {activeRun.status.replace(/_/g, " ")}
            </span>
          ) : null}
          {activeRun?.data_source ? (
            <span
              className={`pill ${
                /drive/i.test(activeRun.data_source) ? "pill-drive" : "pill-api"
              }`}
            >
              {sourceText(activeRun.data_source)}
            </span>
          ) : null}
          {freshPill(activeRun?.completed_at)}
        </div>
        <div className="client-bar-r">
          <RunSelector
            runs={runs}
            selectedId={selectedRun?.request_id ?? null}
            onSelect={(rid) =>
              navigate(buildHash(`/clients/${displayId}/${tab}`, { run: rid }))
            }
            isLoading={runQ.isLoading}
          />
          <AudienceToggle />
        </div>
      </div>

      <div className="client-tabs" role="tablist">
        {visibleTabs.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`client-tab ${tab === t.key ? "on" : ""}`}
            onClick={() => goTab(t.key)}
          >
            {"icon" in t && t.icon ? <Icon name={t.icon} size={13} /> : null}
            <span>{t.label}</span>
            {t.key === "health" && openAlerts && openAlerts > 0 ? (
              <span className="count">{openAlerts}</span>
            ) : null}
          </button>
        ))}
      </div>
    </div>
  );
}

function pathTab(path: string): string {
  const m = path.match(/^\/clients\/[^/]+\/([^/?]+)/);
  return m ? m[1] : "overview";
}

function fmtRunDate(r: RunHistoryItem): string {
  const d = r.assessment_date ?? r.completed_at;
  if (!d) return "—";
  return new Date(d).toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
  });
}

interface RunSelectorProps {
  runs: RunHistoryItem[];
  selectedId: string | null;
  onSelect: (request_id: string) => void;
  isLoading: boolean;
}

function RunSelector({ runs, selectedId, onSelect, isLoading }: RunSelectorProps) {
  const [open, setOpen] = useState(false);
  const selected = runs.find((r) => r.request_id === selectedId)
    ?? runs.find((r) => r.status === "ACTIVE")
    ?? runs[0]
    ?? null;

  if (isLoading) {
    return (
      <div className="run-selector run-selector-loading" aria-busy="true">
        Loading runs…
      </div>
    );
  }
  if (!selected) {
    return (
      <div className="run-selector run-selector-empty">No completed runs</div>
    );
  }
  // Wireframe RUN pill renders the ASSESSMENT date (migration 039);
  // pre-039 REQ-hex rows fall back to the ingest completion timestamp.
  const pillDate = selected.assessment_date ?? selected.completed_at;
  const dateLabel = pillDate
    ? new Date(pillDate).toLocaleDateString(undefined, {
        month: "short", day: "numeric", year: "numeric",
      })
    : "Pick a run";
  const score = (selected as { overall_score?: number | null }).overall_score;
  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        className="run-selector"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Icon name="calendar" size={12} />
        <span>{dateLabel}{score != null ? ` · ${score.toFixed(1)}` : ""}</span>
        <Icon name="chevron-d" size={12} />
      </button>
      {open ? (
        <ul className="run-selector-menu" role="listbox">
          {runs.map((r) => (
            <li
              key={r.request_id}
              role="option"
              aria-selected={r.request_id === selected.request_id}
            >
              <button
                type="button"
                className={`run-selector-item ${
                  r.request_id === selected.request_id ? "active" : ""
                }`}
                onClick={() => {
                  onSelect(r.request_id);
                  setOpen(false);
                }}
              >
                {/* Wireframe row anatomy (03_components_b.js:330-338):
                    date · score (teal) over the mono run id, then a
                    status chip and a DRIVE/API source chip. */}
                <span style={{ flex: 1, minWidth: 0, textAlign: "left" }}>
                  <span style={{ display: "block", fontSize: 12, fontWeight: 600 }}>
                    {fmtRunDate(r)}
                    {r.overall_score != null ? (
                      <> · <span style={{ color: "var(--z-teal)" }}>
                        {r.overall_score.toFixed(1)}
                      </span></>
                    ) : null}
                  </span>
                  <span
                    className="f-mono"
                    style={{ display: "block", fontSize: 10, color: "var(--z-muted)",
                             overflow: "hidden", textOverflow: "ellipsis" }}
                  >
                    {r.request_id}
                  </span>
                </span>
                <span className={`b ${r.status === "ACTIVE" ? "b-teal" : "b-muted"}`}>
                  {humanizeEnum(r.status)}
                </span>
                <span className={`b ${/drive/i.test(r.data_source) ? "b-ph0" : "b-ph1"}`}>
                  {/drive/i.test(r.data_source) ? "DRIVE" : "API"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
