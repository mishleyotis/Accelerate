/**
 * D6 Health — Analyst+ only.
 *
 * Tab structure (2026-06 wireframe):
 *   Alerts | Age | Diff | Patterns | Gates
 *
 * Render states:
 *   1. role < ANALYST          → role gate empty
 *   2. ?view=customer          → "hidden in customer view"
 *   3. isLoading               → spinner
 *   4. error.status === 403    → role gate empty
 *   5. error (other)           → couldn't load
 *   6. no run                  → no active run empty
 *   7. all clean               → "Looks healthy" success state
 *   8. otherwise               → full Health panel with tabs
 */
import { useEffect, useState } from "react";
import { humanizeEnum } from "@/lib/labels";
import { useQuery } from "@tanstack/react-query";
import { apiGet, ApiError } from "@/lib/api";
import { useEffectiveRole } from "@/store/auth";
import { useUiStore } from "@/store/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "@/lib/api";
import { useRoute } from "@/lib/hash-router";
import { Icon, EmptyState, Pill, Spinner, TimeAgo, type PillTone } from "@/components/utils";
import { getBadgeStyle } from "@/lib/freshness";
import {
  useEntityHealth,
  useEntityRuns,
  useHealthPatterns,
  useRefreshEntityFeedbackFiles,
  type AlertOut,
  type EvidenceAgeOut,
  type QaVerdictOut,
  type SafeguardGateOut,
} from "@/lib/queries";
import { downloadCsv } from "@/lib/export";

// 2026-06-06 QA-4: backend's actual /health/version-diff shape. The
// pre-fix frontend type expected `run_a_request_id` + `run_b_request_id`
// + `diffs: VersionDiffEntry[]` (per-subcap diff rows). The backend
// returns aggregate deltas (pillar-level + thin-subcap turnover +
// alert turnover). Either side could move; aligning the frontend to
// what the backend already emits is the smaller change and keeps the
// per-subcap-diff feature as a future addition rather than a partial
// implementation.
interface VersionDiffResponse {
  entity_display_id: string;
  run_a: string;
  run_b: string;
  overall_score_delta: number;
  pillar_score_delta: Record<string, number>;
  thin_subcap_added: string[];
  thin_subcap_resolved: string[];
  alerts_opened: string[];
  alerts_resolved: string[];
}

function getDisplayId(path: string): string | null {
  const m = path.match(/^\/clients\/([^/]+)\/health$/);
  return m ? m[1] : null;
}

const GATE_TONE = {
  PASS: "green",
  PARTIAL: "amber",
  FAIL: "red",
  DEFERRED: "neutral",
} as const;

const SEVERITY_TONE: Record<string, "red" | "amber" | "neutral"> = {
  critical: "red",
  high: "red",
  medium: "amber",
  low: "neutral",
  info: "neutral",
};

// ── Tab components ────────────────────────────────────────────────────────────

function AlertsTab({ alerts, displayId }: { alerts: AlertOut[]; displayId: string | null }) {
  // Wireframe 09_pages_e.js health table: Severity | Subcap | Evidence
  // (n/3 mini-bar) | Action chip | Proxy | Status actions. The producer
  // fields (migration 040) bind the Evidence/Action/Proxy columns; the
  // In-review / Waive buttons hit the real POST /alerts/{id}/actions
  // and refresh this page's health query.
  const qc = useQueryClient();
  const pushToast = useUiStore((st) => st.pushToast);
  const actionMut = useMutation({
    mutationFn: (vars: { alertId: string; action: "acknowledge" | "waive" }) =>
      apiPost<unknown>(`/api/v1/alerts/${vars.alertId}/actions`, {
        action: vars.action, note: null,
      }),
    onSuccess: (_d, vars) => {
      pushToast(
        vars.action === "acknowledge" ? "Alert moved to in-review" : "Alert waived",
        "success",
      );
      void qc.invalidateQueries({ queryKey: ["entityHealth", displayId], exact: false });
      void qc.invalidateQueries({ queryKey: ["alerts"] });
    },
    onError: (err) => pushToast(`Alert action failed: ${(err as Error).message}`, "warn"),
  });

  function subcapOf(a: AlertOut): { name: string; id: string } {
    const id = a.linked_subcap_ids[0] ?? "";
    // Per-subcap alerts title as "Thin evidence: {name}"; aggregated
    // category alerts keep their title verbatim.
    const name = a.title.replace(/^Thin evidence:\s*/i, "");
    return { name, id: a.linked_subcap_ids.length > 1
      ? `${id} +${a.linked_subcap_ids.length - 1} more` : id };
  }

  return (
    <div className="card flush">
      <div className="card-head">
        <h3>Thin-evidence alerts</h3>
        <span className="b b-org">{alerts.length} open</span>
      </div>
      <table className="tbl">
        <thead>
          <tr>
            <th>Severity</th><th>Subcap</th><th>Evidence</th>
            <th>Action</th><th>Proxy</th>
            <th style={{ textAlign: "right" }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((a) => {
            const sc = subcapOf(a);
            const ec = a.evidence_count ?? 0;
            return (
              <tr key={a.id}>
                <td>
                  <span className={`b ${a.severity === "critical" || a.severity === "high" ? "b-below" : "b-org"}`}>
                    {a.severity.toUpperCase()}
                  </span>
                </td>
                <td>
                  <div style={{ fontSize: 12, fontWeight: 500 }}>{sc.name}</div>
                  <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{sc.id}</div>
                </td>
                <td>
                  <div style={{ fontSize: 12 }}>{ec} / 3</div>
                  <div className="prog" style={{ marginTop: 4, width: 80, height: 4 }}>
                    <div className="prog-fill" style={{ width: `${Math.min(100, (ec / 3) * 100)}%`, background: "var(--z-org)" }} />
                  </div>
                </td>
                <td>
                  {a.recommended_action
                    ? <span className="b b-purple">{a.recommended_action}</span>
                    : <span className="muted">—</span>}
                </td>
                <td>
                  {a.proxy_searched == null
                    ? <span className="muted" style={{ fontSize: 11 }}>—</span>
                    : a.proxy_searched
                      ? <span style={{ color: "var(--z-mid)", fontSize: 11 }}>✓ Searched</span>
                      : <span style={{ color: "var(--z-org)", fontSize: 11 }}>Not yet</span>}
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  <button type="button" className="btn btn-tertiary btn-sm"
                          disabled={actionMut.isPending}
                          onClick={() => actionMut.mutate({ alertId: a.id, action: "acknowledge" })}>
                    In review
                  </button>
                  <button type="button" className="btn btn-tertiary btn-sm"
                          disabled={actionMut.isPending}
                          onClick={() => actionMut.mutate({ alertId: a.id, action: "waive" })}>
                    Waive
                  </button>
                </td>
              </tr>
            );
          })}
          {alerts.length === 0 ? (
            <tr>
              <td colSpan={6} className="tbl-empty">
                <div style={{ color: "var(--z-mid)", fontSize: 13, fontWeight: 500 }}>✓ No open alerts</div>
                <div style={{ fontSize: 11, marginTop: 4 }}>Evidence coverage meets the minimum threshold.</div>
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Age tab (B-5). Renders `evidence_age[]` from the new health endpoint.
 * `freshness_band` is the SQL-side STORED authority — we render it
 * directly rather than recomputing an age threshold in the UI.
 */
function EvidenceAgeTab({ evidence }: { evidence: EvidenceAgeOut[] }) {
  if (evidence.length === 0) {
    return <EmptyState title="No evidence indexed" body="Evidence appears after the DMA assessment completes." />;
  }
  // Backend already orders oldest-first; preserve that.
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>E-ID</th>
          <th>Source</th>
          <th>Tier</th>
          <th>Published</th>
          <th>Recency</th>
          <th>Freshness</th>
        </tr>
      </thead>
      <tbody>
        {evidence.map((ev) => {
          const badge = getBadgeStyle(ev.freshness_band);
          return (
            <tr key={ev.e_id}>
              <td><code className="evidence-eid">{ev.e_id}</code></td>
              <td className="tbl-source">{ev.source_name}</td>
              <td className="muted">T{ev.tier}</td>
              <td>
                {ev.published_date
                  ? new Date(ev.published_date).toLocaleDateString()
                  : <span className="muted">—</span>}
              </td>
              <td>{ev.recency_months != null ? `${ev.recency_months} mo` : <span className="muted">—</span>}</td>
              <td>
                <span className={badge.className} title={badge.tooltip}>
                  {badge.label}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function VersionDiffTab({
  displayId,
}: {
  displayId: string | null;
}) {
  // 2026-06-06 QA-4: source runs from /entities/:id/runs (the run
  // selector's source of truth) instead of `data.available_runs`
  // which never existed on the backend HealthResponse. Pre-fix the
  // Diff tab rendered empty selectors because `data.available_runs`
  // was always undefined.
  const runsQ = useEntityRuns(displayId);
  const runs = runsQ.data?.items ?? [];

  // 2026-06-06 QA-M3: honour `?run_a` / `?run_b` deep-link params from
  // ClientRunsPage's "Compare" button. The URL drives the selector
  // defaults; once the user picks something else, local state wins.
  const { query } = useRoute();
  const urlRunA = typeof query.run_a === "string" ? query.run_a : null;
  const urlRunB = typeof query.run_b === "string" ? query.run_b : null;

  const [selectedA, setSelectedA] = useState<string>("");
  const [selectedB, setSelectedB] = useState<string>("");
  // Default selectors: URL params win; otherwise the two most-recent
  // runs. Runs the effect once runs[] is loaded -- the `!selectedA &&
  // !selectedB` guard prevents overriding the user's later choice.
  useEffect(() => {
    if (runs.length >= 2 && !selectedA && !selectedB) {
      const fallbackA = runs[1].request_id;
      const fallbackB = runs[0].request_id;
      // Only use URL params that actually match a loaded run; ignore
      // stale URLs that reference deleted/superseded run IDs.
      const knownIds = new Set(runs.map((r) => r.request_id));
      setSelectedA(urlRunA && knownIds.has(urlRunA) ? urlRunA : fallbackA);
      setSelectedB(urlRunB && knownIds.has(urlRunB) ? urlRunB : fallbackB);
    }
  }, [runs, selectedA, selectedB, urlRunA, urlRunB]);

  const { data, isLoading } = useQuery({
    queryKey: ["versionDiff", displayId, selectedA, selectedB],
    queryFn: () =>
      apiGet<VersionDiffResponse>(
        `/api/v1/entities/${displayId}/health/version-diff?run_a=${encodeURIComponent(selectedA)}&run_b=${encodeURIComponent(selectedB)}`,
      ),
    enabled: !!(displayId && selectedA && selectedB && selectedA !== selectedB),
    staleTime: 60_000,
  });

  if (runs.length < 2) {
    return <EmptyState title="Not enough runs" body="Version diff requires at least two completed runs." />;
  }

  // The backend emits aggregate deltas. Empty == no pillar deltas AND
  // no thin-subcap turnover AND no alert turnover.
  const noChange = data && (
    Object.values(data.pillar_score_delta || {}).every((v) => v === 0)
    && data.thin_subcap_added.length === 0
    && data.thin_subcap_resolved.length === 0
    && data.alerts_opened.length === 0
    && data.alerts_resolved.length === 0
  );

  return (
    <div>
      <div className="filter-bar">
        <label>
          <span className="filter-label">Run A (baseline)</span>
          <select
            className="btn btn-sm btn-secondary"
            value={selectedA}
            onChange={(e) => setSelectedA(e.target.value)}
          >
            {runs.map((r) => (
              <option key={r.request_id} value={r.request_id}>
                {r.request_id}{r.completed_at ? ` · ${new Date(r.completed_at).toLocaleDateString()}` : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="filter-label">Run B (compare)</span>
          <select
            className="btn btn-sm btn-secondary"
            value={selectedB}
            onChange={(e) => setSelectedB(e.target.value)}
          >
            {runs.map((r) => (
              <option key={r.request_id} value={r.request_id}>
                {r.request_id}{r.completed_at ? ` · ${new Date(r.completed_at).toLocaleDateString()}` : ""}
              </option>
            ))}
          </select>
        </label>
      </div>
      {isLoading ? <div className="page-loading"><Spinner /> Loading diff…</div> : null}
      {!isLoading && data && noChange ? (
        <EmptyState title="No differences" body="The two selected runs produce identical scores, gates, and alerts." />
      ) : null}
      {!isLoading && data && !noChange && (
        <>
          <div className="muted small" style={{ marginTop: 12 }}>
            Overall score change: <strong>{data.overall_score_delta > 0 ? "+" : ""}{data.overall_score_delta.toFixed(2)}</strong>
          </div>
          <table className="tbl" style={{ marginTop: 8 }}>
            <thead>
              <tr><th>Pillar</th><th style={{ textAlign: "right" }}>Δ score</th></tr>
            </thead>
            <tbody>
              {Object.entries(data.pillar_score_delta || {}).sort().map(([p, d]) => (
                <tr key={p}>
                  <td>{p}</td>
                  <td
                    style={{
                      textAlign: "right",
                      fontWeight: 700,
                      color: d > 0 ? "var(--z-teal)" : d < 0 ? "var(--z-below)" : "var(--z-muted)",
                    }}
                  >
                    {d > 0 ? "+" : ""}{d.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="g2" style={{ gap: 16, marginTop: 16 }}>
            <DiffTurnoverList title="Thin-evidence subcaps added" items={data.thin_subcap_added} tone="below" />
            <DiffTurnoverList title="Thin-evidence subcaps resolved" items={data.thin_subcap_resolved} tone="teal" />
            <DiffTurnoverList title="Alerts opened" items={data.alerts_opened} tone="below" />
            <DiffTurnoverList title="Alerts resolved" items={data.alerts_resolved} tone="teal" />
          </div>
        </>
      )}
    </div>
  );
}

// 2026-06-06 QA-4: small turnover helper used by VersionDiffTab's
// 2x2 grid of "added/resolved" lists.
function DiffTurnoverList({
  title, items, tone,
}: {
  title: string;
  items: string[];
  tone: "teal" | "below";
}): JSX.Element {
  return (
    <div className="card">
      <div className="bold" style={{ marginBottom: 6 }}>
        {title} <span className="muted">({items.length})</span>
      </div>
      {items.length === 0 ? (
        <div className="muted small">None</div>
      ) : (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {items.slice(0, 25).map((id) => (
            <li key={id}>
              <code className="subcap-id" style={{ color: `var(--z-${tone})` }}>{id}</code>
            </li>
          ))}
          {items.length > 25 ? (
            <li className="muted small">+ {items.length - 25} more</li>
          ) : null}
        </ul>
      )}
    </div>
  );
}


// Map a feedback-refresh state to AE-facing copy + toast tone.
function feedbackToastCopy(state: string, written: number): string {
  switch (state) {
    case "upload_ok": return `Feedback files written to Drive (${written})`;
    case "dev_skip": return "Skipped — feedback files only write in prod/staging";
    case "drive_folder_unknown": return "No Drive folder recorded for this client";
    case "drive_perms_missing": return "Drive write access missing — re-grant in Drive";
    case "upload_failed": return "Some feedback files failed to upload";
    case "no_active_run": return "No active run for this client yet";
    default: return `Feedback refresh: ${state}`;
  }
}
function feedbackToastTone(state: string): "success" | "warn" | "error" {
  if (state === "upload_ok") return "success";
  if (state === "upload_failed" || state === "drive_perms_missing") return "error";
  return "warn";
}

// D6 "Patterns" tab — recurring cross-entity gaps + open issues this client
// SHARES with its subvertical cohort, from the cross_entity_patterns worker.
// Honest empty states per backend `state` (the worker / cohort may be empty).
export function PatternsTab({ displayId }: { displayId: string | null }): JSX.Element {
  const { data, isLoading } = useHealthPatterns(displayId);
  if (isLoading) {
    return <div className="page-loading"><Spinner /> Loading patterns…</div>;
  }
  const patterns = data?.patterns ?? [];
  if (patterns.length === 0) {
    const body = data?.state === "insufficient_data"
      ? "Pattern detection needs at least 3 assessed entities in this client's subvertical cohort."
      : data?.state === "no_active_run"
        ? "No active run for this client yet."
        : "No recurring cross-entity patterns are shared with this client's cohort.";
    return <EmptyState title="No cross-entity patterns" body={body} />;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {patterns.map((p) => (
        <div key={`${p.pattern_type}:${p.pattern_key}`} className="card"
             style={{ padding: "12px 14px" }}>
          <div className="row" style={{ marginBottom: 6, gap: 8 }}>
            <span className={`b ${p.pattern_type === "issue_theme" ? "b-org" : "b-purple"}`}>
              {p.pattern_type === "issue_theme" ? "Issue" : "Gap"}
            </span>
            <strong style={{ fontSize: 13 }}>{p.pattern_label}</strong>
            <span className="spacer" />
            <span className="b b-teal">{p.entity_count} entities</span>
          </div>
          {p.median_peer_gap != null ? (
            <div style={{ fontSize: 12, color: "var(--z-muted)" }}>
              Median peer gap {p.median_peer_gap.toFixed(2)}
            </div>
          ) : null}
          {Object.keys(p.severity_mix).length > 0 ? (
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
              {Object.entries(p.severity_mix).map(([sev, n]) => (
                <span key={sev} className="chip">{sev}: {n}</span>
              ))}
            </div>
          ) : null}
          {p.sample_subcap_ids.length > 0 ? (
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
              {p.sample_subcap_ids.map((sid) => (
                <span key={sid} className="chip f-mono">{sid}</span>
              ))}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

// C5 (2026-06-07): map a `QaVerdictOut.verdict` headline string to a
// PillTone for visual ergonomics. Unknown values fall back to neutral
// so a future bot verdict shape doesn't render as an empty pill.
function verdictTone(verdict: string | null | undefined): PillTone {
  if (!verdict) return "neutral";
  const up = verdict.toUpperCase();
  if (up === "PASS") return "green";
  if (up === "PASS_WITH_NOTES" || up.includes("WARN")) return "amber";
  if (up === "FAIL" || up.includes("REJECT") || up.includes("BLOCK")) {
    return "red";
  }
  return "neutral";
}

// C5: 2-stage QA verdict chain card. Both verdicts may be null; we
// render distinct copy for each null branch so the analyst can tell
// "L1 not shipped" from "neither verdict shipped".
function VerdictChainCard({
  l1,
  l2,
}: {
  l1: QaVerdictOut | null;
  l2: QaVerdictOut | null;
}): JSX.Element | null {
  // Both null → no card.
  if (!l1 && !l2) return null;
  return (
    <div
      className="card"
      data-testid="qa-verdict-chain"
      style={{ marginBottom: 16 }}
    >
      <h4 style={{ margin: "0 0 8px" }}>QA verdict chain</h4>
      <table className="tbl">
        <thead>
          <tr>
            <th>Stage</th>
            <th>Verdict</th>
            <th>Recommendation</th>
            <th>Basis</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>
              <code className="chip">L1</code>{" "}
              <span className="muted">first-pass</span>
            </td>
            <td>
              {l1 ? (
                <Pill tone={verdictTone(l1.verdict)}>
                  {l1.verdict ?? "—"}
                </Pill>
              ) : (
                <span className="muted">L1 not shipped</span>
              )}
            </td>
            <td className="tbl-detail">
              {l1?.recommendation ?? (
                <span className="muted">—</span>
              )}
            </td>
            <td className="tbl-detail">
              {l1?.verdict_basis ?? <span className="muted">—</span>}
            </td>
          </tr>
          <tr>
            <td>
              <code className="chip">L2</code>{" "}
              <span className="muted">full review</span>
            </td>
            <td>
              {l2 ? (
                <Pill tone={verdictTone(l2.verdict)}>
                  {l2.verdict ?? "—"}
                </Pill>
              ) : (
                <span className="muted">L2 not shipped</span>
              )}
            </td>
            <td className="tbl-detail">
              {l2?.recommendation ?? (
                <span className="muted">—</span>
              )}
            </td>
            <td className="tbl-detail">
              {l2?.verdict_basis ?? <span className="muted">—</span>}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function GatesTab({
  gates,
  l1,
  l2,
}: {
  gates: SafeguardGateOut[];
  l1: QaVerdictOut | null;
  l2: QaVerdictOut | null;
}) {
  const verdictCard = <VerdictChainCard l1={l1} l2={l2} />;
  if (gates.length === 0) {
    return (
      <>
        {verdictCard}
        <EmptyState
          title="No safeguard gates"
          body="Gates populate once the assessment ingests."
        />
      </>
    );
  }
  return (
    <>
      {verdictCard}
      <table className="tbl">
        <thead>
          <tr>
            <th>Gate</th>
            <th>Status</th>
            <th>Detail</th>
            <th>Evaluated</th>
          </tr>
        </thead>
        <tbody>
          {gates.map((g) => (
            <tr key={g.gate_id}>
              <td>
                <code className="chip">{g.gate_id}</code>
              </td>
              <td>
                <Pill tone={GATE_TONE[g.status]}>{g.status}</Pill>
              </td>
              <td className="tbl-detail">
                {g.detail ?? <span className="muted">—</span>}
              </td>
              <td className="muted">
                <TimeAgo at={g.evaluated_at} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

// 2026-06-09 prototype parity (F3): the Caps (C10) and Audit (C7) tabs
// were removed with their panels per the operator's strict-5-tab
// decision — the prototype's Health page ships exactly alerts / diff /
// gates / age / patterns (09_pages_e.js:558). The caps_applied +
// audit_logs fields remain on HealthResponse server-side; restoring the
// surfaces means re-adding a tab + a renderer, not new backend work.
// (Removed CapsTab / AuditTab implementations live in git history at
// 4e8ed2a^ should they be resurrected.)
// ── Main component ─────────────────────────────────────────────────────────────

// Strict prototype parity (09_pages_e.js:558): five tabs, this order +
// these labels. Caps-determination and reasoning/contradiction audit are
// intentionally not surfaced as separate tabs per the 2026-06-09 decision.
const TABS = [
  { id: "alerts", label: "Thin-evidence alerts" },
  { id: "diff", label: "Version diff" },
  { id: "gates", label: "Safeguard gates" },
  { id: "age", label: "Evidence age" },
  { id: "patterns", label: "Cross-entity patterns" },
] as const;
type TabId = (typeof TABS)[number]["id"];

// 2026-06-06 QA-5: split into a thin guard component + a data component
// so React never sees a different hook order across renders. The pre-
// fix HealthPage called useEffectiveRole/useUiStore/useRoute BEFORE
// the audience/role early returns, then called useEntityHealth AFTER.
// When the role or audience flipped while the page stayed mounted, the
// number of hooks called between renders changed -- React threw a hook-
// order error. The guard / data split makes the boundary explicit.
export function HealthPage(): JSX.Element {
  const role = useEffectiveRole();
  const audience = useUiStore((s) => s.audience);
  const canView = role === "ADMIN" || role === "ANALYST";

  if (audience === "customer") {
    return <EmptyState title="Hidden in customer view" body="Health diagnostics are internal-only." />;
  }
  if (!canView) {
    return <EmptyState title="Analyst access required" body="Ask an admin to promote you to Analyst to see Health." />;
  }
  // Data component is rendered AFTER all guards pass. Its hooks fire
  // unconditionally for the duration of its mount; role/audience flips
  // unmount it entirely instead of changing the hook count.
  return <HealthPageData />;
}

function HealthPageData(): JSX.Element {
  const { path, query, setQuery } = useRoute();
  const displayId = getDisplayId(path);
  // 2026-06-06 QA-1: propagate `?run=<request_id>`.
  const selectedRun = typeof query.run === "string" ? query.run : null;
  const pushToast = useUiStore((s) => s.pushToast);

  const { data, isLoading, error } = useEntityHealth(displayId, selectedRun);
  const refreshFeedback = useRefreshEntityFeedbackFiles(displayId);

  // Terminal branches keep the `.page`/data-page shell (chrome
  // consistency + the e2e harnesses' [data-page] mount contract).
  const shell = (inner: JSX.Element) => (
    <div className="page" data-page="health" data-source="health-pending">{inner}</div>
  );
  if (isLoading) return <div className="page-loading"><Spinner /> Loading health…</div>;
  if (error) {
    if (error instanceof ApiError && error.status === 403) {
      return shell(<EmptyState title="Forbidden" body="Server-side role gate denied this request." />);
    }
    return shell(<EmptyState title="Couldn't load health" body={(error as Error).message} />);
  }
  if (!data || !data.run_request_id) {
    return shell(<EmptyState title="No active run" body="Health surfaces populate once a DMA ingests." />);
  }

  const allClean = data.thin_evidence_subcap_ids.length === 0
    && data.safeguard_gates.every((g) => g.status === "PASS" || g.status === "DEFERRED")
    && data.alerts.length === 0;
  if (allClean) {
    return shell(
      <EmptyState
        title="Looks healthy"
        body="No thin-evidence subcaps, all safeguard gates PASS/DEFERRED, no open alerts."
      />,
    );
  }

  const activeTab: TabId = (query.tab as TabId) || "alerts";
  const ageStale = data.evidence_age.filter(
    (e) => e.freshness_band === "stale" || e.freshness_band === "dated",
  ).length;
  const failingGates = data.safeguard_gates.filter((g) => g.status === "FAIL").length;
  const badgeCounts: Partial<Record<TabId, number>> = {
    alerts: data.alerts.length || undefined,
    age: ageStale || undefined,
    gates: failingGates || undefined,
  };

  const openAlerts = data.alerts.filter((a) => !a.closed_at).length;

  return (
    <div className="page" data-page="health" data-source="api">
      <div className="page-head">
        <div>
          <div className="eyebrow">Assessment health</div>
          <h1>Quality &amp; controls</h1>
          <div className="sub">
            {openAlerts} open alerts · {failingGates} failing gates
          </div>
        </div>
        <div className="actions">
          {/* 2026-06-06 QA-M2: honest copy + info tone until backend
              endpoints land. */}
          <button type="button" className="btn btn-tertiary"
                  disabled={refreshFeedback.isPending}
                  onClick={() => refreshFeedback.mutate(undefined, {
                    onSuccess: (r) => pushToast(
                      feedbackToastCopy(r.state, r.written.length),
                      feedbackToastTone(r.state),
                    ),
                    onError: (e) => pushToast(
                      `Feedback refresh failed: ${e.message}`, "error"),
                  })}>
            <Icon name="refresh" size={13} /> Re-run feedback file
          </button>
          <button type="button" className="btn btn-secondary"
                  onClick={() => {
                    downloadCsv(
                      `${displayId ?? "client"}-health-alerts.csv`,
                      ["id", "kind", "severity", "title", "opened_at", "age_days", "resolution"],
                      data.alerts.map((a) => [
                        a.id, a.kind, a.severity, a.title, a.opened_at, a.age_days, a.resolution,
                      ]),
                    );
                    pushToast(`Exported ${data.alerts.length} alerts to CSV`, "success");
                  }}>
            <Icon name="download" size={13} /> CSV export
          </button>
        </div>
      </div>

      <div className="filter-bar">
        <div className="toggle-row" role="tablist" aria-label="Health sections">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={activeTab === tab.id ? "on" : ""}
              onClick={() => setQuery({ tab: tab.id })}
            >
              {tab.label}
              {badgeCounts[tab.id] ? (
                <span style={{ marginLeft: 4, fontSize: 10, color: "var(--z-org)" }}>
                  · {badgeCounts[tab.id]}
                </span>
              ) : null}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "alerts" && <AlertsTab alerts={data.alerts} displayId={displayId} />}
      {activeTab === "age" && <EvidenceAgeTab evidence={data.evidence_age} />}
      {activeTab === "diff" && (
        <VersionDiffTab displayId={displayId} />
      )}
      {activeTab === "patterns" && <PatternsTab displayId={displayId} />}
      {activeTab === "gates" && (
        <GatesTab
          gates={data.safeguard_gates}
          l1={data.qa_verdict_l1 ?? null}
          l2={data.qa_verdict_l2 ?? null}
        />
      )}
    </div>
  );
}
