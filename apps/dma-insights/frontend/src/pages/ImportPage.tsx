/**
 * ImportPage — /admin/import ("Import & jobs"), 1:1 with the wireframe
 * (10_pages_f.js ImportPage + LiveImportStream).
 *
 * QA audit 2026-06-11: the Sidebar linked /admin/import but App.tsx's
 * `startsWith("/admin/")` catch-all swallowed it into AdminPage — the
 * dedicated import surface (stage pipeline, live log, job history)
 * never existed in production.
 *
 * Every visible number is backend-sourced (CLAUDE.md admin-flow
 * contract — never the wireframe fixture):
 *   - Active job card + history  GET  /api/v1/admin/jobs/executions
 *   - Delta scan                 POST /api/v1/admin/jobs/drive_crawler:execute
 *   - Cancel                     POST /api/v1/admin/jobs/executions/{id}:abort
 *   - Drive tiles                GET  /api/v1/admin/import-audit/summary
 *   - Catalogue tab              GET  /api/v1/admin/catalogue
 *   - Upload payload             POST /api/v1/ingest/package (multipart)
 *
 * The wireframe's scripted IMPORT_SCRIPT demo is replaced by honest
 * live state: the stage pipeline lights from the newest execution's
 * counters, the log panel tails `stderr_tail`/`result_summary`, and
 * the card disappears entirely when no execution exists yet.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { useRoute } from "@/lib/hash-router";
import { useEffectiveRole } from "@/store/auth";
import { useUiStore } from "@/store/ui";
import { Icon, Spinner, TimeAgo } from "@/components/utils";
import { humanizeEnum } from "@/lib/labels";

interface JobExecutionOut {
  id: string;
  job_name: string;
  status: "running" | "succeeded" | "failed" | "cancelled";
  started_at: string;
  completed_at: string | null;
  duration_sec: number | null;
  folders_seen: number | null;
  files_parsed: number | null;
  files_skipped: number | null;
  files_errored: number | null;
  rows_added: number | null;
  stderr_tail: string | null;
  result_summary: string;
  error_message: string | null;
}

interface JobExecutionListResponse {
  items: JobExecutionOut[];
}

interface ImportAuditSummary {
  last_crawl_at: string | null;
  candidates_processed: number;
  files_imported: number;
  files_excluded: number;
  files_awaiting_review: number;
  files_errored: number;
}

interface CatalogueRunOut {
  version: string;
  status: string;
  approved_at?: string | null;
  created_at?: string | null;
}

const IMPORT_STAGES = [
  { key: "crawl", label: "Drive crawl", icon: "drive" },
  { key: "classify", label: "Classify", icon: "evidence" },
  { key: "dedupe", label: "Deduplicate", icon: "stack" },
  { key: "infer", label: "Entity inference", icon: "users" },
  { key: "ingest", label: "Ingest & index", icon: "play" },
] as const;

/** Map an execution's milestone counters onto the wireframe's 5-stage
 *  pipeline. Counters land in order as the worker progresses, so the
 *  furthest non-null counter is the active stage; a finished run
 *  lights everything. */
function activeStageOf(ex: JobExecutionOut): number {
  if (ex.status !== "running") return IMPORT_STAGES.length - 1;
  if (ex.rows_added != null) return 4;
  if (ex.files_skipped != null) return 2;
  if (ex.files_parsed != null) return 1;
  return 0;
}

function fmtTook(sec: number | null): string {
  if (sec == null) return "—";
  if (sec < 60) return `${Math.round(sec)} s`;
  const m = Math.floor(sec / 60);
  return `${m} m ${Math.round(sec - m * 60)} s`;
}

function fmtStarted(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function statusChip(s: JobExecutionOut["status"]): { cls: string; text: string } {
  if (s === "succeeded") return { cls: "b-above", text: "COMPLETED" };
  if (s === "failed") return { cls: "b-below", text: "FAILED" };
  if (s === "cancelled") return { cls: "b-muted", text: "CANCELLED" };
  return { cls: "b-teal", text: "RUNNING" };
}

/** Active/most-recent job card — the wireframe's LiveImportStream with
 *  honest live data: stage dots from counters, mono log from
 *  stderr_tail / result_summary, Cancel wired to :abort. */
function ActiveJobCard({
  ex, onAborted,
}: { ex: JobExecutionOut; onAborted: () => void }): JSX.Element {
  const pushToast = useUiStore((s) => s.pushToast);
  const logRef = useRef<HTMLDivElement | null>(null);
  const running = ex.status === "running";
  const done = ex.status === "succeeded";
  const stage = activeStageOf(ex);

  const logLines = useMemo(() => {
    const out: { text: string; level: "info" | "warn" | "ok" }[] = [];
    if (ex.stderr_tail) {
      for (const line of ex.stderr_tail.split("\n").slice(-40)) {
        if (line.trim()) out.push({ text: line, level: "info" });
      }
    }
    if (ex.error_message) out.push({ text: ex.error_message, level: "warn" });
    if (!running && ex.result_summary) {
      out.push({ text: ex.result_summary, level: done ? "ok" : "warn" });
    }
    return out;
  }, [ex.stderr_tail, ex.error_message, ex.result_summary, running, done]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logLines.length]);

  async function abort(): Promise<void> {
    try {
      await apiPost(`/api/v1/admin/jobs/executions/${ex.id}:abort`);
      pushToast("Abort requested", "warn");
      onAborted();
    } catch {
      pushToast("Couldn't abort the job", "warn");
    }
  }

  const counters = [
    { label: "Folders seen", value: ex.folders_seen, color: "var(--z-mid)" },
    { label: "Files parsed", value: ex.files_parsed, color: "var(--z-teal)" },
    { label: "Skipped", value: ex.files_skipped, color: "var(--z-org)" },
    { label: "Rows added", value: ex.rows_added, color: "var(--z-dpur)" },
  ];

  return (
    <div className="card flush" style={{ marginBottom: 16, overflow: "hidden" }}>
      <div className="card-head">
        <div className="row">
          <Icon name="play" size={14} style={{ color: done ? "var(--z-teal)" : "var(--z-mid)" }} />
          <h3>
            {running ? "Active job" : "Latest job"} · {humanizeEnum(ex.job_name)}
          </h3>
          {running ? (
            <span className="b b-teal" style={{ display: "inline-flex", gap: 4 }}>
              <span className="live-dot" /> LIVE
            </span>
          ) : (
            <span className={`b ${statusChip(ex.status).cls}`}>{statusChip(ex.status).text}</span>
          )}
        </div>
        <span style={{ fontSize: 11, color: "var(--z-muted)", fontVariantNumeric: "tabular-nums" }}>
          {running ? <>Started <TimeAgo at={ex.started_at} /></> : <>Took {fmtTook(ex.duration_sec)}</>}
        </span>
      </div>
      <div style={{ padding: 16 }}>
        <div className="import-stages">
          {IMPORT_STAGES.map((s, i) => {
            const state = i < stage || !running ? "done" : i === stage ? "active" : "todo";
            return (
              <div key={s.key} className={`import-stage ${state}`}>
                <div className="import-stage-dot">
                  <Icon name={state === "done" ? "check" : s.icon} size={12} />
                </div>
                <div className="import-stage-label">{s.label}</div>
                {i < IMPORT_STAGES.length - 1 ? (
                  <div className="import-stage-bar">
                    <div
                      className="import-stage-bar-fill"
                      style={{ width: i < stage || !running ? "100%" : "0%" }}
                    />
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>

        <div className="g4" style={{ gap: 10, marginTop: 14 }}>
          {counters.map((k) => (
            <div key={k.label} className="card-tile" style={{ padding: "10px 12px" }}>
              <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".06em" }}>
                {k.label}
              </div>
              <div style={{ fontSize: 22, fontWeight: 200, color: k.color, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>
                {k.value ?? "—"}
              </div>
            </div>
          ))}
        </div>

        <div ref={logRef} className="import-log" aria-live="polite">
          {logLines.length === 0 ? (
            <div className="import-log-line" style={{ color: "rgba(255,255,255,.4)" }}>
              {running ? "Awaiting first event…" : "No log output captured."}
            </div>
          ) : (
            logLines.map((l, i) => (
              <div key={i} className="import-log-line">
                <span
                  style={{
                    color: l.level === "warn" ? "#FEC07A" : l.level === "ok" ? "#7FE3D6" : "rgba(255,255,255,.82)",
                  }}
                >
                  {l.text}
                </span>
              </div>
            ))
          )}
          {running ? <div className="import-log-line"><span className="import-cursor" /></div> : null}
        </div>

        {running ? (
          <div className="row" style={{ marginTop: 10 }}>
            <span className="spacer" />
            <button type="button" className="btn btn-tertiary btn-sm" onClick={() => void abort()}>
              Cancel job
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function ImportPage(): JSX.Element {
  const { navigate } = useRoute();
  const role = useEffectiveRole();
  const pushToast = useUiStore((s) => s.pushToast);
  const [tab, setTab] = useState<"jobs" | "drive" | "phase1" | "catalog">("jobs");
  const [executions, setExecutions] = useState<JobExecutionOut[]>([]);
  const [summary, setSummary] = useState<ImportAuditSummary | null>(null);
  const [catalogue, setCatalogue] = useState<CatalogueRunOut[]>([]);
  const [scanning, setScanning] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const hasRunning = executions.some((e) => e.status === "running");

  // Poll executions while anything is running (3s, per the admin-flow
  // contract); otherwise refresh lazily on mount/trigger.
  useEffect(() => {
    if (role !== "ADMIN") return;
    let stop = false;
    async function load(): Promise<void> {
      try {
        const res = await apiGet<JobExecutionListResponse>(
          "/api/v1/admin/jobs/executions?limit=50",
        );
        if (!stop) setExecutions(res.items);
      } catch {
        /* surfaced via empty states */
      } finally {
        if (!stop) setLoaded(true);
      }
    }
    void load();
    const t = setInterval(() => { if (hasRunning) void load(); }, 3000);
    return () => { stop = true; clearInterval(t); };
  }, [role, hasRunning]);

  useEffect(() => {
    if (role !== "ADMIN") return;
    apiGet<ImportAuditSummary>("/api/v1/admin/import-audit/summary")
      .then(setSummary)
      .catch(() => undefined);
    apiGet<{ items: CatalogueRunOut[] }>("/api/v1/admin/catalogue")
      .then((r) => setCatalogue(r.items ?? []))
      .catch(() => undefined);
  }, [role]);

  if (role !== "ADMIN") {
    return (
      <div className="page" data-page="admin-import">
        <div className="empty">
          <div className="icon"><Icon name="lock" size={22} /></div>
          <h3>Admin access required</h3>
        </div>
      </div>
    );
  }

  async function deltaScan(): Promise<void> {
    setScanning(true);
    try {
      await apiPost("/api/v1/admin/jobs/drive_crawler:execute");
      pushToast("Delta scan started — drive_crawler dispatched", "success");
    } catch {
      pushToast("Couldn't start the Drive crawl", "warn");
    } finally {
      setScanning(false);
    }
  }

  async function uploadPackage(file: File): Promise<void> {
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch("/api/v1/ingest/package", {
        method: "POST", body: fd, credentials: "include",
      });
      if (!res.ok) throw new Error(String(res.status));
      pushToast(`Ingest accepted: ${file.name}`, "success");
    } catch {
      pushToast("Package upload failed — check the file and try again", "warn");
    }
  }

  const newest = executions[0] ?? null;
  const appliedCatalogue = catalogue.find((c) => c.status === "APPLIED") ?? null;

  return (
    <div className="page" data-page="admin-import">
      <input
        ref={fileRef}
        type="file"
        accept=".zip,application/zip"
        style={{ display: "none" }}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void uploadPackage(f);
          e.currentTarget.value = "";
        }}
      />
      <div className="page-head">
        <div>
          <div className="eyebrow">Admin · ingest pipeline</div>
          <h1>Import &amp; jobs</h1>
          <div className="sub">Phase 0 Drive crawl · Phase 1 ingest payloads · V7 catalog updates</div>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-tertiary" disabled={scanning} onClick={() => void deltaScan()}>
            {scanning ? <><Spinner /> Scanning…</> : <><Icon name="refresh" size={13} /> Delta scan</>}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => fileRef.current?.click()}>
            <Icon name="download" size={13} /> Upload payload
          </button>
        </div>
      </div>

      <div className="filter-bar">
        <div className="toggle-row">
          <button type="button" className={tab === "jobs" ? "on" : ""} onClick={() => setTab("jobs")}>Job history</button>
          <button type="button" className={tab === "drive" ? "on" : ""} onClick={() => setTab("drive")}>Drive crawl</button>
          <button type="button" className={tab === "phase1" ? "on" : ""} onClick={() => setTab("phase1")}>Phase 1 ingest</button>
          <button type="button" className={tab === "catalog" ? "on" : ""} onClick={() => setTab("catalog")}>V7 catalog</button>
        </div>
      </div>

      {tab === "jobs" ? (
        <>
          {newest ? (
            <ActiveJobCard ex={newest} onAborted={() => setExecutions((x) => [...x])} />
          ) : null}
          <div className="card-head" style={{ padding: "0 0 10px", border: 0 }}>
            <div className="row"><Icon name="evidence" size={14} /><h3>Job history</h3></div>
            <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
              Last {executions.length} jobs
            </span>
          </div>
          <div className="card flush">
            {executions.length === 0 ? (
              <div className="empty" style={{ padding: 28 }}>
                <h3>{loaded ? "No job executions yet" : "Loading…"}</h3>
                {loaded ? (
                  <p className="muted">Trigger a Delta scan or run a backfill to see jobs here.</p>
                ) : null}
              </div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Job</th><th>Kind</th><th>Started</th><th>Files</th>
                    <th>Rows</th><th>Took</th>
                    <th style={{ textAlign: "right" }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {executions.map((j) => {
                    const chip = statusChip(j.status);
                    return (
                      <tr key={j.id} title={j.error_message ?? ""}>
                        <td data-label="Job">
                          <span className="chip">{j.id.slice(0, 8)}</span>
                        </td>
                        <td data-label="Kind">{humanizeEnum(j.job_name)}</td>
                        <td data-label="Started">{fmtStarted(j.started_at)}</td>
                        <td data-label="Files">{j.files_parsed ?? "—"}</td>
                        <td data-label="Rows">{j.rows_added ?? "—"}</td>
                        <td data-label="Took">{fmtTook(j.duration_sec)}</td>
                        <td data-label="Status" style={{ textAlign: "right" }}>
                          <span className={`b ${chip.cls}`}>{chip.text}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </>
      ) : tab === "drive" ? (
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="drive" size={16} />
            <div style={{ fontWeight: 600 }}>Drive folder · scheduled every 6 hours</div>
            <span className="spacer" />
            <span className="muted" style={{ fontSize: 11 }}>
              {summary?.last_crawl_at
                ? <>Last crawl <TimeAgo at={summary.last_crawl_at} /></>
                : "No crawl recorded yet"}
            </span>
          </div>
          <div className="g3" style={{ gap: 10 }}>
            <div className="card-tile">
              <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".08em" }}>Candidates</div>
              <div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-teal)", marginTop: 4 }}>
                {summary?.candidates_processed ?? "—"}
              </div>
            </div>
            <div className="card-tile">
              <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".08em" }}>Imported</div>
              <div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-mid)", marginTop: 4 }}>
                {summary?.files_imported ?? "—"}
              </div>
            </div>
            <div className="card-tile">
              <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".08em" }}>Audit queue</div>
              <div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-org)", marginTop: 4 }}>
                {summary?.files_awaiting_review ?? "—"}
              </div>
            </div>
          </div>
          <div className="sep" />
          <button type="button" className="btn btn-tertiary" onClick={() => navigate("/admin/import/audit")}>
            Open audit queue <Icon name="arrow-r" size={12} />
          </button>
        </div>
      ) : tab === "phase1" ? (
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="play" size={16} />
            <div style={{ fontWeight: 600 }}>Phase 1 ingest</div>
            <span className="spacer" />
            <span className="b b-teal">Bearer + admin-cookie auth</span>
          </div>
          <p style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6 }}>
            Phase 1 receives the canonical <code>{"{Entity}"}_DMA_Complete_Package.zip</code>{" "}
            from the DMA pipeline. The endpoint accepts the bot bearer token OR an
            admin session cookie (ADR 0012) — manual uploads from this page use yours.
          </p>
          <div className="sep" />
          <div className="row">
            <Icon name="evidence" size={14} />
            <span style={{ fontSize: 12 }}>Endpoint: <code>POST /api/v1/ingest/package</code></span>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <button
              type="button"
              className="btn btn-tertiary"
              disabled
              title="Bot bearer tokens are rotated in Google Secret Manager — not from the UI"
            >
              <Icon name="refresh" size={13} /> Rotate API key
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => fileRef.current?.click()}>
              <Icon name="download" size={13} /> Upload payload manually
            </button>
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="stack" size={16} />
            <div style={{ fontWeight: 600 }}>V7 capability catalog</div>
            <span className="spacer" />
            <span className="muted" style={{ fontSize: 11 }}>
              {appliedCatalogue
                ? <>Current: {appliedCatalogue.version}
                    {appliedCatalogue.approved_at
                      ? <> · applied <TimeAgo at={appliedCatalogue.approved_at} /></>
                      : null}</>
                : "No applied catalogue version"}
            </span>
          </div>
          <p style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6 }}>
            Updating the catalog creates a new version. Existing runs retain their
            original catalog reference (per-run <code>ccg_catalog_version</code> pinning).
          </p>
          <div className="row" style={{ marginTop: 10 }}>
            <button type="button" className="btn btn-tertiary" onClick={() => navigate("/admin")}>
              Open catalogue queue <Icon name="arrow-r" size={12} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
