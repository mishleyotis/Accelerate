/**
 * Backend API client — thin wrapper over fetch with consistent error mapping
 * and credential handling. All endpoints are auth-gated via HttpOnly cookie
 * (set during the OAuth flow); the client never reads the JWT.
 *
 * Audience propagation (defense-in-depth, 2026-06-05): every GET passes
 * through `withAudienceQuery` which appends `view=customer` whenever the
 * UI is in customer mode. Backend `audience_strip` is the source of truth
 * (it strips internal-only peer/cohort fields server-side), but without
 * this client-side wiring an in-memory cached response from an earlier
 * internal session would render unstripped in customer mode. The
 * `view=customer` token also participates in TanStack query keys via
 * `currentAudience()` so cache invalidation on audience-switch is implicit.
 */
import { readAudience, type Audience } from "@/lib/audience";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public body: unknown,
  ) {
    super(`[${status}] ${detail}`);
    this.name = "ApiError";
  }
}

export interface ApiOptions extends RequestInit {
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Override the default 15 s request timeout. Use 0 to disable. */
  timeoutMs?: number;
  /** Skip audience injection (rare — only auth/admin endpoints). */
  skipAudience?: boolean;
}

/** Current audience (read at every call so audience switches are reflected
 *  without a re-render). Exported so query keys can include it without
 *  importing the Zustand store from `lib/`. */
export function currentAudience(): Audience {
  return readAudience();
}

/** Augment a `query` object with `view=customer` when the UI is in
 *  customer audience. Honours caller-provided `view` (never overrides). */
function withAudienceQuery(
  query: ApiOptions["query"] | undefined,
  skip: boolean,
): ApiOptions["query"] {
  if (skip) return query;
  const audience = readAudience();
  if (audience !== "customer") return query;
  if (query && Object.prototype.hasOwnProperty.call(query, "view")) return query;
  return { ...query, view: "customer" };
}

// Default fetch timeout — protects against a backend that accepts the
// connection but never responds (Cloud Run cold-start hang, network
// blackhole). Long enough for legitimate slow queries but short enough
// that the UI doesn't sit on a forever-spinner.
const DEFAULT_TIMEOUT_MS = 15_000;

export async function api<T = unknown>(path: string, opts: ApiOptions = {}): Promise<T> {
  const { query, timeoutMs, signal: callerSignal, skipAudience, ...init } = opts;
  // Standalone demo / visual-regression build (ADR 0016): no backend — resolve
  // from the type-checked mock so the production tree renders populated. Live
  // builds tree-shake this out (`__STANDALONE__` is false).
  if (typeof __STANDALONE__ !== "undefined" && __STANDALONE__) {
    const { getStandaloneMock } = await import("@/mock/standalone-mock");
    const mock = getStandaloneMock(path, (init.method ?? "GET").toUpperCase(), query);
    if (mock !== undefined) {
      await new Promise((r) => setTimeout(r, 30)); // mimic async for loading states
      return mock as T;
    }
  }
  let url = path.startsWith("http") ? path : path.startsWith("/") ? path : `/${path}`;
  // Auth endpoints exchange tokens — audience injection there is meaningless
  // and would only widen the surface for replay tools. Audience also doesn't
  // apply to admin endpoints (admins always read internal). Path-based
  // exclusion list mirrors the existing 401-loop exclusion below.
  const isAuthOrAdmin =
    path.includes("/api/v1/auth/") ||
    path.includes("/api/v1/admin/");
  const augmentedQuery = withAudienceQuery(query, !!skipAudience || isAuthOrAdmin);
  if (augmentedQuery && Object.keys(augmentedQuery).length) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(augmentedQuery)) {
      if (v === undefined || v === null || v === "") continue;
      params.set(k, String(v));
    }
    const qs = params.toString();
    if (qs) url += (url.includes("?") ? "&" : "?") + qs;
  }

  const effectiveTimeout = timeoutMs ?? DEFAULT_TIMEOUT_MS;
  let timeoutAbort: AbortController | null = null;
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
  let signal: AbortSignal | null = callerSignal ?? null;
  if (effectiveTimeout > 0) {
    timeoutAbort = new AbortController();
    timeoutHandle = setTimeout(() => timeoutAbort?.abort(), effectiveTimeout);
    // Chain caller's abort signal into our timeout controller so the
    // caller can still cancel mid-flight.
    if (callerSignal) {
      callerSignal.addEventListener("abort", () => timeoutAbort?.abort(), { once: true });
    }
    signal = timeoutAbort.signal;
  }

  let res: Response;
  try {
    // 2026-06-06 QA-M8: spread `init` FIRST, then layer the framework
    // defaults on top. Pre-fix order spread `...init` AFTER the
    // headers/signal/credentials, so any caller-provided field on
    // `init` would clobber the defaults -- a caller who passed
    // `headers: { 'X-Custom': 'foo' }` lost the Content-Type default;
    // a caller who passed `signal: callerSignal` separately would
    // double-set it (init also carried it because the destructure
    // above doesn't fully strip it from `init` when caller also
    // included raw `headers`). The contract should be:
    //   1. Caller's `init` shape is respected (method, body, mode)
    //   2. Framework injects credentials + signal + content-type
    //   3. Caller can override Content-Type via init.headers (kept
    //      via the merge below) but cannot accidentally drop it.
    res = await fetch(url, {
      ...init,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...init.headers,
      },
      signal,
    });
  } catch (err) {
    if (timeoutHandle) clearTimeout(timeoutHandle);
    if ((err as Error).name === "AbortError" && timeoutAbort?.signal.aborted) {
      throw new ApiError(0, `Request timed out after ${effectiveTimeout} ms`, null);
    }
    throw err;
  }
  if (timeoutHandle) clearTimeout(timeoutHandle);
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    const detail =
      (body && typeof body === "object" && "detail" in body && typeof body.detail === "string"
        ? (body as { detail: string }).detail
        : null) ?? res.statusText;
    // Global 401 hook — fired when the JWT expires mid-session. Lets
    // app shells listen and prompt re-login instead of cascading
    // generic "Couldn't load X" banners across every page query.
    // The auth endpoint itself is excluded so the LoginPage's own
    // exchange call doesn't redirect-loop.
    if (res.status === 401 && !path.includes("/api/v1/auth/")) {
      try {
        window.dispatchEvent(new CustomEvent("dma:auth-expired"));
      } catch {
        /* best-effort */
      }
    }
    throw new ApiError(res.status, detail, body);
  }
  return body as T;
}

export function apiGet<T>(path: string, query?: ApiOptions["query"]): Promise<T> {
  return api<T>(path, { method: "GET", query });
}

export function apiPost<T>(path: string, body?: unknown, query?: ApiOptions["query"]): Promise<T> {
  return api<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
    query,
  });
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return api<T>(path, {
    method: "PATCH",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return api<T>(path, {
    method: "PUT",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiDelete<T>(path: string): Promise<T> {
  return api<T>(path, { method: "DELETE" });
}


/**
 * Blob/binary variant of `api()` — for export endpoints that return
 * a downloadable file (PDF, CSV, XLSX, HTML scorecard).
 *
 * Pre-fix (2026-06-06 QA-M7), `exportScorecard` used a raw `fetch`
 * call so it BYPASSED the shared 15s timeout, audience injection,
 * the `dma:auth-expired` 401 hook, and the framework headers/
 * credentials defaults. Operators who let a session expire and then
 * clicked "Export" saw an opaque "Export failed (401): {...}" toast
 * with no re-login prompt; the shared `api()` would have fired the
 * `auth-expired` event and the chrome would have surfaced the login
 * dialog instead.
 *
 * `apiBlob` re-uses the same plumbing as `api()` but returns the raw
 * `Response.blob()` + filename derived from `Content-Disposition`.
 * The framework-default `Content-Type: application/json` header is
 * STRIPPED here because POST-without-body would otherwise send a
 * spurious JSON content type for an empty-body request.
 */
export async function apiBlob(
  path: string,
  opts: ApiOptions = {},
): Promise<{ blob: Blob; filename: string }> {
  const { query, timeoutMs, signal: callerSignal, skipAudience, ...init } = opts;
  let url = path.startsWith("http") ? path : path.startsWith("/") ? path : `/${path}`;
  const isAuthOrAdmin =
    path.includes("/api/v1/auth/") || path.includes("/api/v1/admin/");
  const augmentedQuery = withAudienceQuery(query, !!skipAudience || isAuthOrAdmin);
  if (augmentedQuery && Object.keys(augmentedQuery).length) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(augmentedQuery)) {
      if (v === undefined || v === null || v === "") continue;
      params.set(k, String(v));
    }
    const qs = params.toString();
    if (qs) url += (url.includes("?") ? "&" : "?") + qs;
  }

  const effectiveTimeout = timeoutMs ?? DEFAULT_TIMEOUT_MS;
  let timeoutAbort: AbortController | null = null;
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
  let signal: AbortSignal | null = callerSignal ?? null;
  if (effectiveTimeout > 0) {
    timeoutAbort = new AbortController();
    timeoutHandle = setTimeout(() => timeoutAbort?.abort(), effectiveTimeout);
    signal = timeoutAbort.signal;
  }

  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      credentials: "include",
      // No JSON default Content-Type for blob requests; export
      // endpoints take query-string or empty bodies.
      headers: { ...init.headers },
      signal,
    });
  } catch (err) {
    if (timeoutHandle) clearTimeout(timeoutHandle);
    if ((err as Error).name === "AbortError" && timeoutAbort?.signal.aborted) {
      throw new ApiError(0, `Request timed out after ${effectiveTimeout} ms`, null);
    }
    throw err;
  }
  if (timeoutHandle) clearTimeout(timeoutHandle);

  if (!res.ok) {
    // Mirror api()'s 401 hook so blob-returning endpoints fire the
    // same auth-expired event as JSON endpoints.
    if (res.status === 401 && !path.includes("/api/v1/auth/")) {
      try {
        window.dispatchEvent(new CustomEvent("dma:auth-expired"));
      } catch {
        /* best-effort */
      }
    }
    const detail = await res.text().catch(() => "");
    throw new ApiError(res.status, detail.slice(0, 500), null);
  }

  // Filename derivation from Content-Disposition: attachment; filename="..."
  // Falls back to the URL pathname's last segment when the header is
  // missing or malformed (some Cloud Run setups strip the header;
  // some test mocks don't provide `res.headers` at all).
  let filename = "";
  const cd = res.headers?.get?.("content-disposition") ?? "";
  const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  if (m) {
    filename = decodeURIComponent(m[1]);
  } else {
    filename = path.split("/").pop() ?? "download";
  }
  const blob = await res.blob();
  return { blob, filename };
}
