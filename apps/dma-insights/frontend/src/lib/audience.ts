/**
 * Audience toggle — frontend mirror of backend's audience_strip.
 *
 * The backend is the source of truth (defense-in-depth requirement: a
 * malicious AE can't bypass by manipulating URL state — the API itself
 * returns 403 / strips fields).
 */
export type Audience = "internal" | "customer";

export const AUDIENCE_KEY = "dma:ui:audience";

export function readAudience(): Audience {
  const v = localStorage.getItem(AUDIENCE_KEY);
  return v === "customer" ? "customer" : "internal";
}

export function writeAudience(a: Audience): void {
  localStorage.setItem(AUDIENCE_KEY, a);
}

export const INTERNAL_ONLY_TABS = new Set(["context", "health"]);

export function isTabVisible(tabId: string, audience: Audience): boolean {
  if (audience === "customer" && INTERNAL_ONLY_TABS.has(tabId)) return false;
  return true;
}
