/**
 * Admin page — ADMIN-only (the backend enforces; the page short-circuits
 * for non-admins so we don't even attempt the requests).
 *
 * Three live sections, each backed by an admin API:
 *   /api/v1/admin/users       → user list (role PATCH inline)
 *   /api/v1/admin/build-qa    → per-stage QA gate ledger
 *   /api/v1/admin/catalogue   → ccg_loader_runs awaiting approval
 *
 * Render-state matrix:
 *   1. role !== ADMIN          → forbidden empty state
 *   2. isLoading               → spinner
 *   3. error                   → "Couldn't load admin"
 *   4. happy path              → 3 stacked sections
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { humanizeEnum } from "@/lib/labels";
import { apiGet, apiPatch, apiPost } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { useUiStore } from "@/store/ui";
import { Icon, EmptyState, Pill, Spinner, TimeAgo } from "@/components/utils";

interface UserOut {
  id: string;
  email: string;
  name: string;
  role: "ADMIN" | "ANALYST" | "AE" | "CUSTOMER";
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}
interface UserListResponse { items: UserOut[]; }

interface BuildQaGateOut {
  id: string;
  stage: string;
  gate_id: string;
  category: string;
  description: string;
  acceptance_criteria: string;
  status: "PENDING" | "PASS" | "PARTIAL" | "FAIL" | "DEFERRED";
  evidence_url: string | null;
  evaluated_at: string | null;
  git_sha: string | null;
}
interface BuildQaResponse {
  items: BuildQaGateOut[];
  summary: Record<string, number>;
}

interface CatalogueRunOut {
  id: string;
  version: string;
  status: "STAGING" | "AWAITING_APPROVAL" | "APPLIED" | "REJECTED";
  loader_started_at: string;
  loader_finished_at: string | null;
}
interface CatalogueQueueResponse {
  awaiting_approval: CatalogueRunOut[];
  recent_applied: CatalogueRunOut[];
}

// ── Prompt-quality (self-improving prompts read side) ──────────────────
// Mirrors backend `app.schemas.admin.PromptQualityResponse`. Powered by
// the rollup at `app/services/prompt_quality.py` — surface × prompt-
// template-version aggregator + sliding-baseline pairwise diff. Verdict
// strings are gated by _MIN_RESPONSES_FOR_VERDICT=25 + _TIE_BAND=0.02
// (kept in sync with the backend so the operator never sees a verdict
// the backend wouldn't have rendered).
interface PromptQualitySurfaceRow {
  surface: string;
  versions_observed: number;
  active_version: string | null;
  total_responses: number;
  total_hallucinations: number;
  hallucination_rate: number;
  estimated_cost_usd: number;
}
interface PromptQualityVersionRow {
  surface: string;
  prompt_template_version: string;
  total_responses: number;
  total_hallucinations: number;
  hallucination_rate: number;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost_usd: number;
  first_seen: string | null;
  last_seen: string | null;
  is_active_version: boolean;
}
interface PromptQualityVersionDiffRow {
  surface: string;
  baseline_version: string;
  candidate_version: string;
  baseline_hallucination_rate: number;
  candidate_hallucination_rate: number;
  rate_delta: number;
  baseline_responses: number;
  candidate_responses: number;
  verdict: "candidate_better" | "candidate_worse" | "tie" | "insufficient_data";
}
interface PromptQualityResponse {
  by_surface: PromptQualitySurfaceRow[];
  by_version: PromptQualityVersionRow[];
  version_diffs: PromptQualityVersionDiffRow[];
  window_days: number | null;
}

const VERDICT_TONE: Record<
  PromptQualityVersionDiffRow["verdict"],
  "green" | "red" | "amber" | "neutral"
> = {
  candidate_better: "green",
  candidate_worse: "red",
  tie: "amber",
  insufficient_data: "neutral",
};

const VERDICT_LABEL: Record<PromptQualityVersionDiffRow["verdict"], string> = {
  candidate_better: "Candidate better",
  candidate_worse: "Candidate worse",
  tie: "Tie (<2pp)",
  insufficient_data: "Collecting samples…",
};

const GATE_TONE = {
  PASS: "green",
  PARTIAL: "amber",
  FAIL: "red",
  DEFERRED: "neutral",
  PENDING: "neutral",
} as const;

const ROLE_TONE: Record<string, "teal" | "neutral" | "amber"> = {
  ADMIN: "teal",
  ANALYST: "teal",
  AE: "neutral",
  CUSTOMER: "amber",
};

interface ImportFileOut {
  id: string;
  filename: string;
  file_kind: string;
  status: string;
  parser_warnings: Record<string, unknown> | null;
  drive_file_id: string | null;
  drive_modified_time: string | null;
  processed_at: string | null;
  created_at: string;
  entity_display_id: string | null;
  run_request_id: string | null;
}
interface ImportAuditResponse { items: ImportFileOut[]; }

const FILE_STATUS_TONE: Record<string, "green" | "amber" | "red" | "neutral"> = {
  PARSED: "green",
  PENDING_REVIEW: "amber",
  PARSE_FAILED: "red",
  QUEUED: "neutral",
};

// ── Pending review · Phase 0 entity inferences (F6) ─────────────────────
// Mirrors backend `app.schemas.enrichment.PendingReviewItem`. The admin
// list endpoint returns runs + entities + import files; this card renders
// the *entity* inferences only (prototype 10_pages_f.js:474-497), with
// Confirm → PATCH :confirm (PENDING_REVIEW→ACTIVE) and Reject →
// PATCH :reject (→ARCHIVED).
interface PendingReviewItem {
  kind: "run" | "entity" | "import_file";
  id: string;
  display_id: string | null;
  title: string;
  detail: string | null;
  created_at: string;
  entity_id: string | null;
  entity_name: string | null;
}
interface PendingReviewResponse {
  items: PendingReviewItem[];
  counts_by_kind: Record<string, number>;
}

function DeltaScanButton({ enabled }: { enabled: boolean }) {
  const pushToast = useUiStore((s) => s.pushToast);
  const scan = useMutation({
    mutationFn: () =>
      apiPost<{ id: string }>("/api/v1/admin/jobs/drive_crawler:execute", {
        mode: "delta",
      }),
    onSuccess: () => pushToast("Delta scan started — progress in Import & jobs", "success"),
    onError: (e: Error) => pushToast(e.message, "error"),
  });
  if (!enabled) return null;
  return (
    <button type="button" className="btn btn-tertiary"
            disabled={scan.isPending}
            onClick={() => scan.mutate()}>
      {scan.isPending
        ? <><Spinner /> Scanning…</>
        : <><Icon name="refresh" size={13} /> Delta scan</>}
    </button>
  );
}

function PendingReviewSection({ enabled }: { enabled: boolean }) {
  const pushToast = useUiStore((s) => s.pushToast);
  const qc = useQueryClient();
  const pending = useQuery({
    queryKey: ["adminPendingReview"],
    queryFn: () => apiGet<PendingReviewResponse>("/api/v1/admin/pending-review"),
    staleTime: 60 * 1000,
    enabled,
  });
  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "confirm" | "reject" }) =>
      apiPatch<{ name: string; status: string }>(
        `/api/v1/admin/entities/${id}:${action}`,
        action === "reject" ? { reason: "rejected from Admin pending-review" } : undefined,
      ),
    onSuccess: (res, vars) => {
      pushToast(
        vars.action === "confirm"
          ? `Confirmed ${res.name}`
          : `Rejected ${res.name}`,
        vars.action === "confirm" ? "success" : "warn",
      );
      void qc.invalidateQueries({ queryKey: ["adminPendingReview"] });
      void qc.invalidateQueries({ queryKey: ["entities"] });
    },
    onError: (err: Error) => pushToast(err.message, "error"),
  });

  const entities = (pending.data?.items ?? []).filter((i) => i.kind === "entity");
  if (pending.isLoading || pending.error) {
    // Quiet while loading; on error the rest of the admin page still works —
    // surface the failure inline rather than blanking the page.
    return pending.error ? (
      <section className="admin-section">
        <h3>Pending review · Phase 0 entity inferences</h3>
        <EmptyState title="Couldn't load pending review" body={(pending.error as Error).message} />
      </section>
    ) : null;
  }
  if (entities.length === 0) return null; // prototype shows the card only when entities are queued

  return (
    <div className="card flush" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <div className="row">
          <Icon name="users" size={14} />
          <h3>Pending review · Phase 0 entity inferences</h3>
        </div>
        <span className="b b-org">{entities.length} entities</span>
      </div>
      <div className="card-body">
        {entities.map((e) => (
          <div key={e.id} className="card-tile" style={{ marginBottom: 8, padding: 14 }}>
            <div className="row" style={{ marginBottom: 6, flexWrap: "wrap", gap: 6 }}>
              <strong>{e.entity_name ?? e.title}</strong>
              {e.display_id ? <span className="b b-purple">{e.display_id}</span> : null}
              <span className="spacer" />
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                <TimeAgo at={e.created_at} />
              </span>
            </div>
            {e.detail ? (
              <div style={{ fontSize: 11.5, color: "var(--z-body)" }}>
                Inferred via <strong>{e.detail}</strong>
              </div>
            ) : null}
            <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button type="button" className="btn btn-primary btn-sm"
                      disabled={act.isPending}
                      onClick={() => act.mutate({ id: e.id, action: "confirm" })}>
                Confirm
              </button>
              <button type="button" className="btn btn-tertiary btn-sm"
                      disabled={act.isPending}
                      onClick={() => act.mutate({ id: e.id, action: "reject" })}>
                Reject
              </button>
              <button type="button" className="btn btn-tertiary btn-sm"
                      onClick={() => { window.location.hash = "#/admin/import/audit"; }}>
                View source
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function AdminPage() {
  const { user } = useAuthStore();

  // All hooks must be called unconditionally (Rules of Hooks). We gate
  // the visible output on the role check AFTER hooks have run; the
  // queries are still cheap on first render (TanStack short-circuits
  // disabled queries below) and never reach the network unless ADMIN.
  const isAdmin = user?.role === "ADMIN";
  const users = useQuery({
    queryKey: ["adminUsers"],
    queryFn: () => apiGet<UserListResponse>("/api/v1/admin/users"),
    staleTime: 60 * 1000,
    enabled: isAdmin,
  });
  const qa = useQuery({
    queryKey: ["adminBuildQa"],
    queryFn: () => apiGet<BuildQaResponse>("/api/v1/admin/build-qa"),
    staleTime: 5 * 60 * 1000,
    enabled: isAdmin,
  });
  const catalogue = useQuery({
    queryKey: ["adminCatalogue"],
    queryFn: () => apiGet<CatalogueQueueResponse>("/api/v1/admin/catalogue"),
    staleTime: 5 * 60 * 1000,
    enabled: isAdmin,
  });
  const promptQuality = useQuery({
    queryKey: ["adminPromptQuality", "30d"],
    queryFn: () =>
      apiGet<PromptQualityResponse>("/api/v1/admin/prompt-quality", {
        days: 30,
      }),
    // 5-min cache: prompt-quality is a slow-moving signal; an operator
    // viewing the tile twice in a row shouldn't burn extra DB cycles.
    staleTime: 5 * 60 * 1000,
    enabled: isAdmin,
  });

  if (!isAdmin) {
    return (
      <EmptyState
        title="Admin only"
        body="Ask an admin to grant your account ADMIN to see this page."
      />
    );
  }

  return (
    <div className="page" data-page="admin" data-source="api">
      <div className="page-head">
        <div>
          <div className="eyebrow">Settings &amp; operations</div>
          <h1>Admin</h1>
          <div className="sub">User management · ingest pipeline · system settings</div>
        </div>
        <div className="actions">
          {/* Prototype 10_pages_f.js:469 — Delta scan ahead of the
              primary Import & jobs action; wired to the real
              drive_crawler job (delta mode is its default). */}
          <DeltaScanButton enabled={isAdmin} />
          <button type="button" className="btn btn-primary"
                  onClick={() => { window.location.hash = "#/admin/import"; }}>
            <Icon name="play" size={13} /> Import &amp; jobs
          </button>
        </div>
      </div>

      {/* F6: Phase-0 entity-inference approvals sit ABOVE operations,
          matching the prototype's section order (10_pages_f.js:474). */}
      <PendingReviewSection enabled={isAdmin} />

      <section className="admin-section">
        <h3>Users</h3>
        {users.isLoading ? (
          <div className="page-loading"><Spinner /> Loading users…</div>
        ) : users.error ? (
          <EmptyState title="Couldn't load users" body={users.error.message} />
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Email</th><th>Name</th><th>Role</th><th>Last login</th>
              </tr>
            </thead>
            <tbody>
              {users.data?.items?.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>{u.name}</td>
                  <td><Pill tone={ROLE_TONE[u.role] ?? "neutral"}>{u.role}</Pill></td>
                  <td><TimeAgo at={u.last_login_at} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="admin-section">
        <h3>Build QA gates</h3>
        {qa.isLoading ? (
          <div className="page-loading"><Spinner /> Loading QA gates…</div>
        ) : qa.error ? (
          <EmptyState title="Couldn't load QA gates" body={qa.error.message} />
        ) : !qa.data?.items?.length ? (
          <EmptyState
            title="No gate verdicts yet"
            body="CI writes one row per gate per build into build_qa_gates."
          />
        ) : (
          <>
            <div className="qa-summary">
              {Object.entries(qa.data.summary).map(([status, n]) => (
                <Pill key={status} tone={GATE_TONE[status as keyof typeof GATE_TONE] ?? "neutral"}>
                  {status}: {n}
                </Pill>
              ))}
            </div>
            <table className="admin-table">
              <thead>
                <tr><th>Stage</th><th>Gate</th><th>Category</th><th>Status</th><th>Evaluated</th></tr>
              </thead>
              <tbody>
                {qa.data?.items?.map((g) => (
                  <tr key={g.id}>
                    <td>{g.stage}</td>
                    <td><code>{g.gate_id}</code></td>
                    <td>{g.category}</td>
                    <td><Pill tone={GATE_TONE[g.status]}>{g.status}</Pill></td>
                    <td><TimeAgo at={g.evaluated_at} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      <section className="admin-section">
        <h3>Catalogue queue</h3>
        {catalogue.isLoading ? (
          <div className="page-loading"><Spinner /> Loading catalogue queue…</div>
        ) : catalogue.error ? (
          <EmptyState title="Couldn't load catalogue queue" body={catalogue.error.message} />
        ) : !catalogue.data?.awaiting_approval?.length ? (
          <EmptyState
            title="No catalogue revisions awaiting approval"
            body="A new ccg_loader_run lands here when the loader finishes
            against gs://dma-insights-catalogue-staging/."
          />
        ) : (
          <table className="admin-table">
            <thead>
              <tr><th>Version</th><th>Started</th><th>Finished</th><th>Status</th></tr>
            </thead>
            <tbody>
              {catalogue.data?.awaiting_approval?.map((c) => (
                <tr key={c.id}>
                  <td>{c.version}</td>
                  <td><TimeAgo at={c.loader_started_at} /></td>
                  <td><TimeAgo at={c.loader_finished_at} /></td>
                  <td><Pill tone="amber">{c.status}</Pill></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <PromptQualitySection query={promptQuality} />
    </div>
  );
}

// ── PromptQualitySection ─────────────────────────────────────────────────
// Read-side of the "self-improving prompts" mandate: shows per-surface
// rollups (responses, hallucination rate, $/month), per-version
// breakdowns (active vs deprecated), and the sliding-baseline pairwise
// diff so the operator can see "v2 reduced hallucinations from 12% to
// 3% (candidate_better)" at a glance.
//
// Render-state matrix:
//   1. isLoading → spinner
//   2. error     → typed empty state with the error message
//   3. by_surface empty → "no synthesis activity yet" empty state
//   4. happy path → 3 stacked sub-views (by surface · by version · diffs)
function PromptQualitySection({
  query,
}: {
  query: ReturnType<typeof useQuery<PromptQualityResponse>>;
}) {
  if (query.isLoading) {
    return (
      <section className="admin-section">
        <h3>Prompt quality</h3>
        <div className="page-loading"><Spinner /> Loading prompt quality…</div>
      </section>
    );
  }
  if (query.error) {
    return (
      <section className="admin-section">
        <h3>Prompt quality</h3>
        <EmptyState
          title="Couldn't load prompt quality"
          body={query.error.message}
        />
      </section>
    );
  }
  const data = query.data;
  if (!data?.by_surface?.length) {
    return (
      <section className="admin-section">
        <h3>Prompt quality</h3>
        <EmptyState
          title="No synthesis activity in the last 30 days"
          body="Rollup is empty because vertex_synthesis_cache has no rows
          younger than the window. Run a few /rag/answer requests or wait
          for the next scheduled ingest."
        />
      </section>
    );
  }
  return (
    <section className="admin-section" data-source="api">
      <h3>
        Prompt quality
        <span className="sub" style={{ marginLeft: 8, fontWeight: 400, fontSize: 11 }}>
          surface × version rollup · last {data.window_days ?? 30}d
        </span>
      </h3>

      <div style={{ marginBottom: 16 }}>
        <h4 style={{ fontSize: 13, marginBottom: 8 }}>By surface</h4>
        <table className="admin-table">
          <thead>
            <tr>
              <th>Surface</th>
              <th>Active version</th>
              <th>Versions</th>
              <th>Responses</th>
              <th>Halluc rate</th>
              <th>Spend (est)</th>
            </tr>
          </thead>
          <tbody>
            {data.by_surface.map((r) => (
              <tr key={r.surface}>
                <td><code>{r.surface}</code></td>
                <td>
                  {r.active_version ? (
                    <Pill tone="teal">{r.active_version}</Pill>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>{r.versions_observed}</td>
                <td>{r.total_responses.toLocaleString()}</td>
                <td>
                  <Pill tone={r.hallucination_rate > 0.05 ? "red" : "green"}>
                    {(r.hallucination_rate * 100).toFixed(1)}%
                  </Pill>
                </td>
                <td>${r.estimated_cost_usd.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(data.by_version?.length ?? 0) > 0 ? (
        <div style={{ marginBottom: 16 }}>
          <h4 style={{ fontSize: 13, marginBottom: 8 }}>By version</h4>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Surface</th>
                <th>Version</th>
                <th>Responses</th>
                <th>Halluc rate</th>
                <th>Tokens (in / out)</th>
                <th>Last seen</th>
              </tr>
            </thead>
            <tbody>
              {data.by_version.map((r) => (
                <tr key={`${r.surface}:${r.prompt_template_version}`}>
                  <td><code>{r.surface}</code></td>
                  <td>
                    {r.is_active_version ? (
                      <Pill tone="teal">{r.prompt_template_version} · active</Pill>
                    ) : (
                      <Pill tone="neutral">{r.prompt_template_version}</Pill>
                    )}
                  </td>
                  <td>{r.total_responses.toLocaleString()}</td>
                  <td>{(r.hallucination_rate * 100).toFixed(1)}%</td>
                  <td>
                    {r.prompt_tokens.toLocaleString()} /{" "}
                    {r.completion_tokens.toLocaleString()}
                  </td>
                  <td><TimeAgo at={r.last_seen} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {(data.version_diffs?.length ?? 0) > 0 ? (
        <div>
          <h4 style={{ fontSize: 13, marginBottom: 8 }}>
            Sliding-baseline diffs (v<sub>n</sub> vs v<sub>n-1</sub>)
          </h4>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Surface</th>
                <th>Baseline → Candidate</th>
                <th>Halluc Δ</th>
                <th>Verdict</th>
                <th>Samples (B / C)</th>
              </tr>
            </thead>
            <tbody>
              {data.version_diffs.map((d, i) => (
                <tr key={`${d.surface}:${d.baseline_version}->${d.candidate_version}:${i}`}>
                  <td><code>{d.surface}</code></td>
                  <td>
                    <code>{d.baseline_version}</code> →{" "}
                    <code>{d.candidate_version}</code>
                  </td>
                  <td>
                    {(d.rate_delta * 100 >= 0 ? "+" : "") +
                      (d.rate_delta * 100).toFixed(1)}
                    pp
                  </td>
                  <td>
                    <Pill tone={VERDICT_TONE[d.verdict]}>
                      {VERDICT_LABEL[d.verdict]}
                    </Pill>
                  </td>
                  <td>
                    {d.baseline_responses.toLocaleString()} /{" "}
                    {d.candidate_responses.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

// ── ImportAuditView ────────────────────────────────────────────────────────
//
// Drive-crawler audit ledger — lists every `import_files` row in reverse
// chronological order, surfacing R01–R06 routing decisions + parse
// warnings so the analyst can approve PENDING_REVIEW files.
//
// Render-state matrix:
//   1. ADMIN gate failed       → handled by parent (EmptyState)
//   2. isLoading               → spinner
//   3. error                   → 'Couldn't load import audit'
//   4. empty                   → "No imports yet" empty state
//   5. happy path              → table of files w/ status + warnings

export function ImportAuditPage() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === "ADMIN";
  const audit = useQuery({
    queryKey: ["adminImportAudit"],
    queryFn: () => apiGet<ImportAuditResponse>("/api/v1/admin/imports/audit"),
    staleTime: 60 * 1000,
    enabled: isAdmin,
  });

  if (!isAdmin) {
    return (
      <EmptyState
        title="Admin only"
        body="Ask an admin to grant your account ADMIN to see this page."
      />
    );
  }

  return (
    <div className="page-body">
      <h2>Drive import audit</h2>
      <p className="muted">
        Every file parsed (or quarantined) by the Drive crawler. Click a
        PENDING_REVIEW row to approve, override the file kind, or escalate.
      </p>

      <section className="admin-section">
        {audit.isLoading ? (
          <div className="page-loading"><Spinner /> Loading audit…</div>
        ) : audit.error ? (
          <EmptyState title="Couldn't load import audit" body={audit.error.message} />
        ) : !audit.data?.items?.length ? (
          <EmptyState
            title="No imports yet"
            body="The Drive crawler hasn't recorded any files. Trigger a crawl from `/admin` or wait for the 6 h scheduled run."
          />
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Kind</th>
                <th>Entity</th>
                <th>Run</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {audit.data?.items?.map((f) => (
                <tr key={f.id}>
                  <td>
                    <code className="filename">{f.filename}</code>
                    {f.parser_warnings && Object.keys(f.parser_warnings).length > 0 ? (
                      <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                        <Icon name="warn" size={12} /> {Object.keys(f.parser_warnings).length} parser warning(s)
                      </div>
                    ) : null}
                  </td>
                  <td>{humanizeEnum(f.file_kind)}</td>
                  <td>{f.entity_display_id ?? "—"}</td>
                  <td>{f.run_request_id ?? "—"}</td>
                  <td>
                    <Pill tone={FILE_STATUS_TONE[f.status] ?? "neutral"}>
                      {humanizeEnum(f.status)}
                    </Pill>
                  </td>
                  <td><TimeAgo at={f.created_at} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
