/**
 * D8 ClientRuns — ported 1:1 from prototype
 * (standalone-src/src/pages-e.jsx · ClientRuns).
 *
 * .page-head w/ Trigger rerun action; .card.flush wrapping
 * .tbl.tbl-clickable with columns Run date / Run ID / Status / Source /
 * Score / Evidence mode / Subcaps / Actions (View · Compare).
 * Maturity score chip uses the canonical band classes (.b-act/.b-bld/
 * .b-cmp/.b-dif pair bg WITH the band text color — lib/maturity ADR 0008).
 */
import { useQuery } from "@tanstack/react-query";
import { nameFromSlug } from "@/lib/sanitize";
import { humanizeEnum } from "@/lib/labels";
import { Icon, EmptyState, Spinner } from "@/components/utils";
import { useRoute } from "@/lib/hash-router";
import { apiGet } from "@/lib/api";
import { useUiStore } from "@/store/ui";
import { maturityClass } from "@/lib/maturity";
import { useEntityOverview, useRequestNewRun } from "@/lib/queries";
import type { RunSummary } from "@/lib/queries";

function getDisplayId(path: string): string | null {
  const m = path.match(/^\/clients\/([^/]+)\/runs$/);
  return m ? m[1] : null;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

function sourceLabel(s: string): { text: string; cls: string } {
  if (s === "DRIVE_PARSE") return { text: "DRIVE PARSE", cls: "b-ph0" };
  if (s === "PROJECT_API") return { text: "PROJECT API", cls: "b-ph1" };
  // Backfills are Drive-side provenance — wireframe colors them in the
  // DRIVE PARSE purple family, never gray (QA audit 2026-06-11).
  if (s === "DRIVE_BACKFILL") return { text: "DRIVE BACKFILL", cls: "b-ph0" };
  if (s === "MANUAL_BACKFILL") return { text: "BACKFILL", cls: "b-ph0" };
  if (s === "BOT_REQUEST") return { text: "BOT REQUEST", cls: "b-ph1" };
  return { text: s.replace(/_/g, " "), cls: "b-muted" };
}

export function ClientRunsPage(): JSX.Element {
  const { path, navigate } = useRoute();
  const displayId = getDisplayId(path);
  const pushToast = useUiStore((s) => s.pushToast);
  const rerun = useRequestNewRun();
  // Entity name for the H1 ("Runs - {name}", per prototype). Served from the
  // ClientShell's cached overview query (no extra request); the run history
  // is not single-run-scoped, so the run-independent name needs no run arg.
  const entityName = useEntityOverview(displayId).data?.entity?.name ?? nameFromSlug(displayId);

  const { data, isLoading, error } = useQuery({
    queryKey: ["entityRuns", displayId],
    queryFn: () => apiGet<{ items: RunSummary[] }>(`/api/v1/entities/${displayId}/runs`),
    enabled: displayId !== null,
    staleTime: 30_000,
  });

  if (isLoading) {
    return <div className="page-loading"><Spinner /> Loading runs…</div>;
  }
  if (error || !data) {
    return <EmptyState title="Couldn't load runs" body={(error as Error)?.message} />;
  }

  // Parent run for a rerun request = the most recent run on record (the list
  // is sorted newest-first by the backend). Needed so the bot threads the new
  // run to this entity's lineage.
  const parentRequestId = data.items[0]?.request_id ?? null;

  async function triggerRerun(): Promise<void> {
    if (!displayId || !parentRequestId) {
      pushToast("Rerun requires a prior run on record", "warn");
      return;
    }
    try {
      const out = await rerun.mutateAsync({
        entity_name: entityName ?? displayId,
        is_rerun: true,
        parent_request_id: parentRequestId,
      });
      pushToast(
        out.eta_minutes != null
          ? `Rerun ${out.request_id} queued — ETA ${out.eta_minutes} min`
          : `Rerun ${out.request_id} queued`,
        "success",
      );
    } catch (err) {
      pushToast((err as Error).message || "Rerun request failed", "error");
    }
  }

  return (
    <div className="page" data-page="runs" data-source="api">
      <div className="page-head">
        <div>
          <div className="eyebrow">Run history</div>
          <h1>Runs - {entityName ?? "client"}</h1>
          <div className="sub">{data.items.length} immutable run record{data.items.length === 1 ? "" : "s"} · sortable by date</div>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
                  onClick={triggerRerun}
                  disabled={rerun.isPending || !displayId || !parentRequestId}>
            <Icon name="refresh" size={13} /> {rerun.isPending ? "Requesting…" : "Trigger rerun"}
          </button>
        </div>
      </div>

      {data.items.length === 0 ? (
        <EmptyState
          title="No runs yet"
          body="Runs appear after the DMA bot completes an assessment."
        />
      ) : (
        <div className="card flush">
          <table className="tbl tbl-clickable">
            <thead>
              <tr>
                <th>Run date</th>
                <th>Run ID</th>
                <th>Status</th>
                <th>Source</th>
                <th>Score</th>
                <th>Evidence mode</th>
                <th>Subcaps</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => {
                const src = sourceLabel(r.data_source);
                const score = (r as { overall_score?: number | null }).overall_score ?? null;
                return (
                  <tr key={r.id}>
                    <td><strong>{fmtDate(
                      (r as { assessment_date?: string | null }).assessment_date
                        ?? r.completed_at ?? r.created_at,
                    )}</strong></td>
                    <td className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>
                      {r.request_id}
                    </td>
                    <td>
                      <span className={`b ${r.status === "ACTIVE" ? "b-teal" : "b-muted"}`}>
                        {humanizeEnum(r.status)}
                      </span>
                    </td>
                    <td><span className={`b ${src.cls}`}>{src.text}</span></td>
                    <td>
                      {score !== null ? (
                        <span className={`b ${maturityClass(score)}`}>
                          {score.toFixed(1)}
                        </span>
                      ) : <span className="muted">—</span>}
                    </td>
                    <td>{r.evidence_mode ? r.evidence_mode.toUpperCase() : "—"}</td>
                    <td>{r.subcap_count ?? "—"}</td>
                    <td>
                      {/* 2026-06-06 QA-M3: View must navigate to the
                          SPECIFIC run the row represents, not the
                          latest ACTIVE. Pre-fix the button silently
                          opened the latest-run overview regardless of
                          which row was clicked -- AE thought they were
                          inspecting an old run but actually saw current
                          data. Now we encode the run's request_id into
                          `?run=` so the destination page's data hooks
                          (wired in Batch 7) resolve that exact run. */}
                      <button type="button" className="btn btn-tertiary btn-sm"
                              onClick={() => navigate(
                                `/clients/${displayId}/overview?run=${encodeURIComponent(r.request_id)}`,
                              )}>
                        View
                      </button>
                      {displayId ? (
                        /* QA-M3: Compare deep-links into Health → Diff
                           with this row preselected as run_b. The diff
                           tab also reads `run_a` if present, otherwise
                           defaults to the most-recent OTHER run. */
                        <button type="button" className="btn btn-tertiary btn-sm"
                                onClick={() => navigate(
                                  `/clients/${displayId}/health?tab=diff&run_b=${encodeURIComponent(r.request_id)}`,
                                )}>
                          Compare
                        </button>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
