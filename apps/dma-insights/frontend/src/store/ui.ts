/**
 * UI store — audience toggle, sidebar collapsed state, intelligence-panel
 * visibility, current drawers/modals/popovers, toast queue, the selected
 * run for the active client (mirror of `?run=` hash query). All ephemeral;
 * persisted only when marked (audience to localStorage, sidebar to
 * localStorage, IP state to Redis via the backend's user_session_state).
 */
import { create } from "zustand";
import { readAudience, writeAudience, type Audience } from "@/lib/audience";

export type DrawerKind =
  | "evidence"
  | "insight"
  | "recommendation"
  | "newRun"
  | "synthesis"
  | null;

export type PopoverKind = "search" | "notifications" | "settings" | null;

/**
 * Canonical payload for `openDrawer("evidence", …)` (plan Part 11.1).
 * Every E-ID chip app-wide passes `eId` so the drawer can scroll-to +
 * highlight the exact cited row (resetting the tier chip filter — and
 * dropping the subcap scope — when either would hide the target).
 * `subcapId` keeps the existing subcap scoping; `origin` is a free-form
 * provenance tag for QA/analytics only.
 */
export interface EvidenceDrawerPayload {
  displayId: string | null;
  subcapId?: string | null;
  eId?: string | null;
  origin?: string;
}

export type ToastKind = "success" | "warn" | "error";

export interface Toast {
  id: number;
  text: string;
  kind: ToastKind;
}

interface UiState {
  audience: Audience;
  sidebarCollapsed: boolean;
  /** Mobile slide-in nav drawer (≤760px). Ephemeral — never persisted. */
  mobileNavOpen: boolean;
  ipOpen: boolean;
  ipSurface: string;
  ipContext: unknown;
  activeDrawer: DrawerKind;
  drawerPayload: unknown;
  activePopover: PopoverKind;
  /** Mirror of the `?run=` hash query (hash router is the source of truth
   *  so deep-links work); set by the route binding in App.tsx + ClientBar. */
  selectedRunId: string | null;
  toasts: Toast[];
  setAudience: (a: Audience) => void;
  toggleSidebar: () => void;
  setMobileNavOpen: (b: boolean) => void;
  toggleMobileNav: () => void;
  setIpOpen: (b: boolean) => void;
  setIpSurface: (s: string, ctx?: unknown) => void;
  /** Payload is kind-specific: `EvidenceDrawerPayload` for "evidence",
   *  `{ recommendationId }` for "recommendation", etc. Kept as a union so
   *  the single store cell can host every drawer kind; `DrawerHost`
   *  narrows via its `as*Payload` parsers. */
  openDrawer: (kind: DrawerKind, payload?: EvidenceDrawerPayload | Record<string, unknown> | null) => void;
  closeDrawer: () => void;
  openPopover: (p: PopoverKind) => void;
  closePopover: () => void;
  setSelectedRunId: (r: string | null) => void;
  pushToast: (text: string, kind?: ToastKind) => void;
  dismissToast: (id: number) => void;
}

const SIDEBAR_KEY = "dma:ui:sidebar_collapsed";

function readSidebar(): boolean {
  return localStorage.getItem(SIDEBAR_KEY) === "1";
}

function writeSidebar(b: boolean): void {
  localStorage.setItem(SIDEBAR_KEY, b ? "1" : "0");
}

let _toastSeq = 0;

export const useUiStore = create<UiState>((set, get) => ({
  audience: readAudience(),
  sidebarCollapsed: readSidebar(),
  mobileNavOpen: false,
  ipOpen: false,
  ipSurface: "why_now",
  ipContext: null,
  activeDrawer: null,
  drawerPayload: null,
  activePopover: null,
  selectedRunId: null,
  toasts: [],
  setAudience: (a) => {
    const prev = get().audience;
    writeAudience(a);
    set({ audience: a });
    // When transitioning to customer mode, DROP the cached query data so
    // any internal-stripped fields fetched earlier (peer_median,
    // peer_cohort_n, firmographics.internal_only_md, etc.) can't render
    // against a customer-facing audience. 2026-06-10 fix: this used to
    // call clearClientSessionCache() — queryClient.clear() + a FULL
    // IndexedDB wipe — which raced the PersistQueryClientProvider
    // restore/persist cycle and reset auth-adjacent state, leaving the
    // page in a never-resolving loading state ("customer view just
    // loads"). resetQueries() drops the cached data (same security
    // property: internal-stripped fields are gone; the audience-keyed
    // queryKeys already partition customer vs internal buckets) AND
    // refetches active observers — removeQueries()/clear() leave
    // observed queries in a pending state that never resolves (the
    // hang reproduced on /heatmap, 2026-06-10 click-through). No
    // persister/IndexedDB wipe: the persister rewrites its single key
    // from the reset cache automatically.
    if (prev !== a && a === "customer") {
      void import("../entry").then(({ queryClient }) =>
        queryClient.resetQueries(),
      );
    }
  },
  toggleSidebar: () => {
    const next = !get().sidebarCollapsed;
    writeSidebar(next);
    set({ sidebarCollapsed: next });
  },
  setMobileNavOpen: (b) => set({ mobileNavOpen: b }),
  toggleMobileNav: () => set({ mobileNavOpen: !get().mobileNavOpen }),
  setIpOpen: (b) => set({ ipOpen: b }),
  setIpSurface: (s, ctx) =>
    set({ ipSurface: s, ipContext: ctx ?? null }),
  openDrawer: (kind, payload) =>
    set({ activeDrawer: kind, drawerPayload: payload ?? null, activePopover: null }),
  closeDrawer: () => set({ activeDrawer: null, drawerPayload: null }),
  openPopover: (p) => set({ activePopover: p }),
  closePopover: () => set({ activePopover: null }),
  setSelectedRunId: (r) => set({ selectedRunId: r }),
  pushToast: (text, kind = "success") => {
    const id = ++_toastSeq;
    set((s) => ({ toasts: [...s.toasts, { id, text, kind }] }));
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, 4200);
  },
  dismissToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
