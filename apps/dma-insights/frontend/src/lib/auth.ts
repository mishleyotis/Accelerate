/**
 * Auth helpers — `/api/v1/auth/google` exchanges a Google ID token for our
 * RS256-signed session JWT (set as `dma_session` HttpOnly cookie).
 *
 * The frontend never reads the JWT body — `/api/v1/auth/me` returns the
 * decoded profile (user_id, email, role, name).
 */
import { apiGet, apiPost } from "./api";

export type Role = "ADMIN" | "ANALYST" | "AE" | "CUSTOMER";

export interface CurrentUser {
  user_id: string;
  email: string;
  role: Role;
  name: string;
  // Downgrade-only acting-as list — populated by the backend so the
  // SettingsPopover segmented control mirrors the server's hierarchy.
  // The frontend MUST NOT use this to elevate the user's effective
  // role; it's a UI hint only and the server re-checks every request.
  can_act_as?: Role[];
}

export async function exchangeGoogleIdToken(idToken: string): Promise<CurrentUser> {
  return apiPost<CurrentUser>("/api/v1/auth/google", { id_token: idToken });
}

export async function whoAmI(): Promise<CurrentUser | null> {
  try {
    const body = await apiGet<unknown>("/api/v1/auth/me");
    // Validate the response shape — `apiGet` falls back to plain text
    // on non-JSON 200 (e.g. nginx error page, captive portal HTML), so
    // without this guard `whoAmI` would return a string the caller
    // then stores as `user` and `App` renders the authenticated shell
    // instead of LoginPage. Treat anything that isn't a well-formed
    // CurrentUser as "no session" so the login surface renders cleanly.
    if (!body || typeof body !== "object" || typeof (body as { email?: unknown }).email !== "string") {
      return null;
    }
    return body as CurrentUser;
  } catch {
    return null;
  }
}

/**
 * Wipe the TanStack Query cache + IndexedDB persistence so the next
 * user signing in on the same browser/tab never reads the prior user's
 * cached entity data. Defense-in-depth — the backend still enforces
 * auth on every request, but cache reads bypass the backend entirely.
 *
 * Called by:
 *   - `logout()` (below) on explicit sign-out
 *   - `App.tsx` global `dma:auth-expired` listener (401 mid-session)
 *   - `store/ui.ts` `setAudience("customer")` to prevent internal data
 *     from leaking into a customer-mode render
 *
 * Idempotent + best-effort: a failed clear never throws so the caller
 * can still complete the surrounding action.
 */
export async function clearClientSessionCache(): Promise<void> {
  try {
    const [{ queryClient, idbStore }, idb] = await Promise.all([
      import("../entry"),
      import("idb-keyval"),
    ]);
    queryClient.clear();
    await idb.clear(idbStore);
  } catch {
    // Best-effort: caller still proceeds even if cache-clear fails.
  }
}

export async function logout(): Promise<void> {
  await apiPost<void>("/api/v1/auth/logout");
  await clearClientSessionCache();
}
