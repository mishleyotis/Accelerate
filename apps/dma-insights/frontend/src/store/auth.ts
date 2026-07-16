/**
 * Auth store — current user + login state.
 *
 * Loaded on app boot via `/api/v1/auth/me`; updated after OAuth round-trip
 * and on `/logout`. Used by the audience toggle gate, role-gated routes,
 * and the IntelligencePanel display name.
 */
import { create } from "zustand";
import type { CurrentUser, Role } from "@/lib/auth";

/**
 * Acting-as role. The server-returned `user.role` is the FLOOR — an AE
 * cannot escalate to ADMIN via this selector. The 3 × 3 matrix is
 * downgrade-only (mirrors chrome.jsx `effectiveRole` per CLAUDE.md
 * "Admin flow"):
 *
 *     real ↓     | actingAs=AE | =ANALYST | =ADMIN | null
 *     ──────────────────────────────────────────────────────
 *     AE         |   AE        |   AE     |   AE   |  AE
 *     ANALYST    |   AE        |  ANALYST |  ANALYST |  ANALYST
 *     ADMIN      |   AE        |  ANALYST |  ADMIN |  ADMIN
 *     CUSTOMER   |   CUSTOMER  |  CUSTOMER|  CUSTOMER|  CUSTOMER
 *
 * Persisted to localStorage so SettingsPopover selection survives reload.
 */
const ROLE_RANK: Record<Role, number> = {
  AE: 1, ANALYST: 2, ADMIN: 3, CUSTOMER: 0,
};

export function effectiveRole(real: Role | undefined, actingAs: Role | null): Role {
  const r = real || "AE";
  if (!actingAs) return r;
  if (r === "CUSTOMER") return r;
  const ar = ROLE_RANK[actingAs] ?? 1;
  const rr = ROLE_RANK[r] ?? 1;
  return ar <= rr ? actingAs : r;
}

const ACTING_AS_KEY = "dma:acting-as";

function readActingAs(): Role | null {
  try {
    const v = window.localStorage.getItem(ACTING_AS_KEY);
    if (v && (v === "AE" || v === "ANALYST" || v === "ADMIN" || v === "CUSTOMER")) {
      return v as Role;
    }
  } catch { /* ignore */ }
  return null;
}

function writeActingAs(v: Role | null): void {
  try {
    if (v) window.localStorage.setItem(ACTING_AS_KEY, v);
    else window.localStorage.removeItem(ACTING_AS_KEY);
  } catch { /* ignore */ }
}

interface AuthState {
  user: CurrentUser | null;
  loading: boolean;
  /** Selected "acting as" role; null = use real role. */
  actingAs: Role | null;
  setUser: (u: CurrentUser | null) => void;
  setLoading: (b: boolean) => void;
  /** Sets the acting-as role, clamped to the user's `can_act_as` allow-list. */
  setActingAs: (r: Role | null) => void;
  /** Convenience selector — returns the downgrade-clamped effective role. */
  effectiveRole: () => Role;
}

// Mirror the canonical (server-returned) user into sessionStorage so
// a tampered `dma:user` value cannot survive the next /auth/me round-
// trip. Without this, an attacker who plants role=ADMIN in storage
// keeps the elevated value after the SPA hydrates against an AE
// session (2026-05-29 session_storage_user_does_not_override_lower_
// server_role e2e). Server response is the ONLY floor; storage is
// a UX-only cache and must be overwritten on every set.
const STORAGE_KEY = "dma:user";

function persistUser(u: CurrentUser | null): void {
  try {
    if (u) {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(u));
    } else {
      window.sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    /* private mode / quota — best-effort */
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  loading: true,
  actingAs: readActingAs(),
  setUser: (u) => {
    persistUser(u);
    // If the persisted actingAs is no longer in the user's allow-list
    // (or there's no user), drop it so we don't display a stale chip.
    const cur = get().actingAs;
    if (cur && (!u || !(u.can_act_as ?? []).includes(cur))) {
      writeActingAs(null);
      set({ user: u, loading: false, actingAs: null });
    } else {
      set({ user: u, loading: false });
    }
  },
  setLoading: (b) => set({ loading: b }),
  setActingAs: (r) => {
    const u = get().user;
    // Server-side `can_act_as` is the ONLY source of truth for what
    // downgrade options the AE/Analyst/Admin sees. If the role isn't in
    // the allow-list (or there's no user), drop the request — keep the
    // existing value.
    if (r && (!u || !(u.can_act_as ?? []).includes(r))) return;
    writeActingAs(r);
    set({ actingAs: r });
  },
  effectiveRole: () => effectiveRole(get().user?.role, get().actingAs),
}));

/**
 * Robust hook that returns the effective role, tolerant of test mocks that
 * `vi.spyOn(authStore, "useAuthStore").mockReturnValue({ user })` and don't
 * include the `effectiveRole` selector. Falls back to `user.role` (or "AE")
 * so pages don't throw when the store is partially mocked.
 */
export function useEffectiveRole(): Role {
  const state = useAuthStore() as Partial<AuthState>;
  if (typeof state.effectiveRole === "function") {
    return state.effectiveRole();
  }
  return effectiveRole(state.user?.role, state.actingAs ?? null);
}
