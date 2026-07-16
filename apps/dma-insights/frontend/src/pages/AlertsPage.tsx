/**
 * AlertsPage — ported 1:1 from prototype
 * (standalone-src/src/pages-f.jsx · AlertsPage; tabs vs proto e7dc5590).
 *
 * .page-head w/ Export CSV + Refresh feedback file actions.
 * .filter-bar .toggle-row for tabs Alerts / Patterns / Waived +
 * status + severity selects (Alerts tab only). .card.flush wrapping
 * .tbl with severity / entity / subcap / evidence / action / manage
 * (Heatmap · Review · Waive). Locked .empty for non-Analyst users.
 *
 * 2026-07-02 (plan Part 11.2) — both placeholder tabs are now live:
 *   Patterns → GET /api/v1/alerts/patterns (cross_entity_patterns worker
 *              output; rows carry affected-entity names + subcap chips).
 *              State branches: full | insufficient_data | empty | error.
 *   Waived   → GET /api/v1/alerts?resolution=waive (closed rows + the
 *              ≥50-char waive rationale). Empty state is honest copy.
 *   Row "Heatmap" deep-link now carries `?subcap=` so D3 can focus the
 *   alerted subcap on arrival.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon, EmptyState, Spinner } from "@/components/utils";
import { useAlerts, useRefreshAllFeedbackFiles, type AlertOut } from "@/lib/queries";
import { downloadCsv } from "@/lib/export";
import { subverticalLabel } from "@/lib/labels";
import { useAuthStore } from "@/store/auth";
import { useUiStore } from "@/store/ui";
import { useRoute } from "@/lib/hash-router";
import { apiGet, apiPost } from "@/lib/api";

// ── Patterns tab (GET /api/v1/alerts/patterns) ────────────────────────
// Mirrors backend `app.schemas.health.GlobalPatternOut` — the nightly
// cross_entity_patterns worker rollup, fleet-wide (no anchor entity).
interface GlobalPatternOut {
  pattern_type: string;
  pattern_key: string;
  pattern_label: string;
  subvertical: string;
  catalogue_version: string;
  primary_subcap_id: string | null;
  entity_count: number;
  severity_mix: Record<string, number>;
  median_peer_gap: number | null;
  sample_subcap_ids: string[];
  affected_entity_names: string[];
}
interface GlobalPatternsResponse {
  items: GlobalPatternOut[];
  state: "full" | "insufficient_data" | "empty";
}

/** Waived rows re-use the AlertOut contract + the waive rationale the
 *  backend LATERAL-joins from alert_actions. */
type WaivedAlertRow = AlertOut & { waive_note?: string | null };

export function AlertsPage(): JSX.Element {
  const { navigate } = useRoute();
  const { user } = useAuthStore();
  const pushToast = useUiStore((s) => s.pushToast);
  const isAnalystOrAdmin = user?.role === "ADMIN" || user?.role === "ANALYST";
  const isAdmin = user?.role === "ADMIN";
  const refreshAll = useRefreshAllFeedbackFiles();

  const [tab, setTab] = useState<"alerts" | "patterns" | "waived">("alerts");
  const [statusFilter, setStatusFilter] = useState<string>("OPEN");
  const [severityFilter, setSeverityFilter] = useState<string>("ALL");

  const { data, isLoading, error } = useAlerts();
  const items = data?.items ?? [];
  // Lazy per-tab fetches — only fire when the operator opens the tab.
  const patternsQ = useQuery({
    queryKey: ["alertPatterns"],
    queryFn: () => apiGet<GlobalPatternsResponse>("/api/v1/alerts/patterns"),
    enabled: isAnalystOrAdmin && tab === "patterns",
    staleTime: 5 * 60 * 1000,
  });
  const waivedQ = useQuery({
    queryKey: ["alerts", "waived"],
    queryFn: () => apiGet<{ items: WaivedAlertRow[]; open_count: number }>(
      "/api/v1/alerts", { resolution: "waive" },
    ),
    enabled: isAnalystOrAdmin && tab === "waived",
    staleTime: 30 * 1000,
  });
  // 2026-06-05 QA finding 9: wire the Review/Waive buttons to the
  // existing backend POST /alerts/{id}/actions. Pre-fix the buttons
  // only fired a toast and never persisted.
  const qc = useQueryClient();
  const alertActionMut = useMutation({
    mutationFn: async (vars: { alertId: string; action: "acknowledge" | "waive" | "escalate" | "close"; note?: string }) =>
      apiPost<unknown>(`/api/v1/alerts/${vars.alertId}/actions`, {
        action: vars.action,
        note: vars.note ?? null,
      }),
    onSuccess: (_data, vars) => {
      const verb = vars.action === "acknowledge" ? "moved to IN_REVIEW" : `${vars.action}d`;
      pushToast(`Alert ${verb}`, "success");
      void qc.invalidateQueries({ queryKey: ["alerts"] });
    },
    onError: (err) => {
      pushToast(`Alert action failed: ${(err as Error).message}`, "error");
    },
  });

  const filtered = useMemo(() => {
    return items.filter((a) => {
      const status = a.closed_at ? "RESOLVED" : "OPEN";
      if (statusFilter !== "ALL" && status !== statusFilter) return false;
      if (severityFilter !== "ALL" && a.severity.toUpperCase() !== severityFilter) return false;
      return true;
    });
  }, [items, statusFilter, severityFilter]);

  if (isLoading) {
    return <div className="page-loading"><Spinner /> Loading alerts…</div>;
  }
  if (error || !data) {
    return <EmptyState title="Couldn't load alerts" body={(error as Error)?.message} />;
  }

  if (!isAnalystOrAdmin) {
    return (
      <div className="page" data-page="alerts">
        <div className="empty">
          <h3>Analyst access required</h3>
          <p>This page requires Analyst or Admin permissions.</p>
        </div>
      </div>
    );
  }

  const openCount = items.filter((a) => !a.closed_at).length;
  // 2026-06-05: count distinct affected entities via the backend-supplied
  // entity_display_id instead of slicing the subcap id (which was never
  // an entity slug). Falls back to 0 for alerts without an entity link.
  const entityCount = new Set(
    items.flatMap((a) => (a.entity_display_id ? [a.entity_display_id] : [])),
  ).size;

  return (
    <div className="page" data-page="alerts" data-source="api">
      <div className="page-head">
        <div>
          <div className="eyebrow">Global alert dashboard</div>
          <h1>Thin-evidence alerts</h1>
          <div className="sub">
            {openCount} OPEN
            {entityCount > 0 ? ` across ${entityCount} entities` : ""}
          </div>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-tertiary"
                  onClick={() => {
                    downloadCsv(
                      "dma-alerts.csv",
                      ["id", "kind", "severity", "title", "entity", "opened_at", "age_days", "resolution", "recommended_action"],
                      filtered.map((a) => [
                        a.id, a.kind, a.severity, a.title, a.entity_display_id,
                        a.opened_at, a.age_days, a.resolution, a.recommended_action ?? "",
                      ]),
                    );
                    pushToast(`Exported ${filtered.length} alerts to CSV`, "success");
                  }}>
            <Icon name="download" size={13} /> Export CSV
          </button>
          {isAdmin ? (
            <button type="button" className="btn btn-secondary"
                    disabled={refreshAll.isPending}
                    onClick={() => refreshAll.mutate(undefined, {
                      onSuccess: (r) => {
                        const ok = r.by_state.upload_ok ?? 0;
                        const skipped = r.by_state.dev_skip ?? 0;
                        pushToast(
                          `Refreshed ${r.total} clients — ${ok} written, ${skipped} skipped`,
                          ok > 0 ? "success" : "warn");
                      },
                      onError: (e) => pushToast(
                        `Feedback refresh failed: ${e.message}`, "error"),
                    })}>
              <Icon name="refresh" size={13} /> Refresh feedback files
            </button>
          ) : null}
        </div>
      </div>

      <div className="filter-bar">
        <div className="toggle-row">
          <button className={tab === "alerts" ? "on" : ""} onClick={() => setTab("alerts")}>Alerts</button>
          <button className={tab === "patterns" ? "on" : ""} onClick={() => setTab("patterns")}>Patterns</button>
          <button className={tab === "waived" ? "on" : ""} onClick={() => setTab("waived")}>Waived</button>
        </div>
        <span className="spacer" />
        {tab === "alerts" ? (
          <>
            <select className="inp" style={{ maxWidth: 180 }}
                    value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                    aria-label="Filter by status">
              <option value="ALL">All statuses</option>
              <option>OPEN</option>
              <option>RESOLVED</option>
            </select>
            <select className="inp" style={{ maxWidth: 180 }}
                    value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}
                    aria-label="Filter by severity">
              <option value="ALL">All severities</option>
              <option>CRITICAL</option>
              <option>HIGH</option>
              <option>MEDIUM</option>
              <option>LOW</option>
            </select>
          </>
        ) : null}
      </div>

      {tab === "alerts" ? (
        <div className="card flush">
          <table className="tbl">
            <thead>
              {/* F8 prototype parity (10_pages_f.js:61): Severity ·
                  Entity · Subcap · Evidence · Action · Manage. */}
              <tr>
                <th>Severity</th>
                <th>Entity</th>
                <th>Subcap</th>
                <th>Evidence</th>
                <th>Action</th>
                <th style={{ textAlign: "right" }}>Manage</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: 16, textAlign: "center" }}>
                    <div style={{ color: "var(--z-mid)", fontSize: 13, fontWeight: 500 }}>
                      <Icon name="check" size={13} /> No open alerts matching
                    </div>
                  </td>
                </tr>
              ) : filtered.map((a) => {
                const sev = a.severity.toUpperCase();
                // 2026-06-05: navigate to the REAL entity. Pre-fix this
                // sliced `linked_subcap_ids[0][:6]` (e.g. "P3C1.7" ->
                // "/clients/P3C1.7/heatmap") which never matched an
                // entity. Backend now returns entity_display_id on the
                // alert; fall back to null when an alert isn't tied to
                // a specific entity (rare, but possible for org-wide).
                const entityDisplayId = a.entity_display_id;
                return (
                  <tr key={a.id}>
                    <td>
                      <span className={`b ${sev === "CRITICAL" || sev === "HIGH" ? "b-below" : "b-org"}`}>{sev}</span>
                    </td>
                    <td>
                      <div style={{ fontWeight: 600, fontSize: 12.5 }}>
                        {a.entity_name ?? a.entity_display_id ?? "—"}
                      </div>
                      <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{a.title}</div>
                    </td>
                    <td>
                      {a.linked_subcap_ids[0] ? (
                        <>
                          <div style={{ fontSize: 12, fontWeight: 500 }}>{a.body || a.title}</div>
                          <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>
                            {a.linked_subcap_ids[0]}
                          </div>
                        </>
                      ) : <span className="muted">—</span>}
                    </td>
                    <td>
                      <span className="f-mono" style={{ fontSize: 11 }}>
                        {(a.evidence_count ?? a.linked_e_ids.length)} / 3
                      </span>
                      <div className="prog" style={{ marginTop: 4, width: 64, height: 4 }}>
                        <div className="prog-fill" style={{
                          width: `${Math.min(100, ((a.evidence_count ?? a.linked_e_ids.length) / 3) * 100)}%`,
                          background: "var(--z-org)",
                        }} />
                      </div>
                    </td>
                    <td>
                      <span className="b b-purple">
                        {a.recommended_action ?? a.kind.replace(/_/g, " ")}
                      </span>
                      <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{a.age_days}d open</div>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {entityDisplayId ? (
                        <button type="button" className="btn btn-tertiary btn-sm"
                                onClick={() => {
                                  // Part 11.2: carry the alerted subcap so the
                                  // heatmap can focus it on arrival.
                                  const sid = a.linked_subcap_ids[0];
                                  navigate(
                                    `/clients/${entityDisplayId}/heatmap` +
                                    (sid ? `?subcap=${encodeURIComponent(sid)}` : ""),
                                  );
                                }}>
                          Heatmap
                        </button>
                      ) : null}
                      <button type="button" className="btn btn-tertiary btn-sm"
                              onClick={() => alertActionMut.mutate({ alertId: a.id, action: "acknowledge" })}
                              disabled={alertActionMut.isPending}>
                        Review
                      </button>
                      <button type="button" className="btn btn-tertiary btn-sm"
                              onClick={() => {
                                // Backend requires a >=50-char note on waive --
                                // prompt the operator for rationale before
                                // firing the mutation.
                                const note = window.prompt(
                                  "Waive rationale (required, min 50 chars):",
                                  "",
                                );
                                if (note === null) return;
                                if (note.trim().length < 50) {
                                  pushToast(
                                    "Waive rationale must be at least 50 characters.",
                                    "warn",
                                  );
                                  return;
                                }
                                alertActionMut.mutate({
                                  alertId: a.id, action: "waive", note,
                                });
                              }}
                              disabled={alertActionMut.isPending}>
                        Waive
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : tab === "patterns" ? (
        <div className="card flush" data-testid="alerts-patterns-tab">
          <div className="card-head">
            <h3>Cross-entity pattern finder</h3>
            <span className="b b-muted">nightly fleet rollup</span>
          </div>
          {patternsQ.isLoading ? (
            <div className="page-loading" style={{ padding: 16 }}><Spinner /> Loading patterns…</div>
          ) : patternsQ.error ? (
            <EmptyState title="Couldn't load patterns" body={(patternsQ.error as Error).message} />
          ) : !patternsQ.data || patternsQ.data.state === "empty" ? (
            <div className="empty" data-source="api-empty">
              <h3>No cross-entity patterns computed</h3>
              <p>The nightly pattern worker hasn't produced results for this fleet yet.</p>
            </div>
          ) : patternsQ.data.state === "insufficient_data" ? (
            <div className="empty" data-source="api-empty">
              <h3>Not enough cohort data</h3>
              <p>Every subvertical cohort is below the minimum size for pattern detection.</p>
            </div>
          ) : (
            <table className="tbl">
              <thead>
                {/* Proto e7dc5590 :94 columns: Pattern · Subvertical ·
                    Category · Cohort — Category renders the real subcap
                    chips; Cohort carries the affected entity names. */}
                <tr>
                  <th>Pattern</th>
                  <th>Subvertical</th>
                  <th>Subcaps</th>
                  <th>Cohort</th>
                </tr>
              </thead>
              <tbody>
                {patternsQ.data.items.map((p) => {
                  const subcaps = [
                    ...(p.primary_subcap_id ? [p.primary_subcap_id] : []),
                    ...p.sample_subcap_ids.filter((s) => s !== p.primary_subcap_id),
                  ].slice(0, 3);
                  const names = p.affected_entity_names;
                  return (
                    <tr key={`${p.subvertical}:${p.pattern_type}:${p.pattern_key}`}>
                      <td>
                        <strong style={{ fontSize: 12.5 }}>{p.pattern_label}</strong>
                        <div style={{ fontSize: 10, color: "var(--z-muted)" }}>
                          {p.pattern_type.replace(/_/g, " ")}
                          {p.median_peer_gap != null
                            ? ` · median peer gap ${p.median_peer_gap.toFixed(1)}`
                            : ""}
                        </div>
                      </td>
                      <td><span className="b b-purple">{subverticalLabel(p.subvertical)}</span></td>
                      <td>
                        {subcaps.length === 0 ? <span className="muted">—</span> :
                          subcaps.map((sid) => (
                            <span key={sid} className="chip" style={{ marginRight: 4 }}>{sid}</span>
                          ))}
                      </td>
                      <td>
                        <div style={{ fontSize: 12, fontWeight: 600 }}>
                          {p.entity_count} entit{p.entity_count === 1 ? "y" : "ies"}
                        </div>
                        {names.length > 0 ? (
                          <div style={{ fontSize: 10, color: "var(--z-muted)" }} className="txt-fit-1"
                               title={names.join(", ")}>
                            {names.slice(0, 3).join(", ")}
                            {names.length > 3 ? ` +${names.length - 3} more` : ""}
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="card flush" data-testid="alerts-waived-tab">
          {waivedQ.isLoading ? (
            <div className="page-loading" style={{ padding: 16 }}><Spinner /> Loading waived alerts…</div>
          ) : waivedQ.error ? (
            <EmptyState title="Couldn't load waived alerts" body={(waivedQ.error as Error).message} />
          ) : (waivedQ.data?.items ?? []).length === 0 ? (
            <div className="empty" data-source="api-empty">
              <h3>No waived alerts</h3>
              <p>Waived alerts will appear here with their rationale.</p>
            </div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Entity</th>
                  <th>Alert</th>
                  <th>Waived</th>
                  <th>Rationale</th>
                </tr>
              </thead>
              <tbody>
                {(waivedQ.data?.items ?? []).map((a) => {
                  const sev = a.severity.toUpperCase();
                  return (
                    <tr key={a.id}>
                      <td>
                        <span className={`b ${sev === "CRITICAL" || sev === "HIGH" ? "b-below" : "b-org"}`}>{sev}</span>
                      </td>
                      <td>
                        <div style={{ fontWeight: 600, fontSize: 12.5 }}>
                          {a.entity_name ?? a.entity_display_id ?? "—"}
                        </div>
                        {a.linked_subcap_ids[0] ? (
                          <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>
                            {a.linked_subcap_ids[0]}
                          </div>
                        ) : null}
                      </td>
                      <td style={{ fontSize: 12 }}>{a.title}</td>
                      <td style={{ fontSize: 11, whiteSpace: "nowrap" }}>
                        {a.closed_at ? new Date(a.closed_at).toLocaleDateString() : "—"}
                      </td>
                      <td style={{ fontSize: 11.5, color: "var(--z-body)", maxWidth: 380 }}>
                        {a.waive_note ?? <span className="muted">—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
