/**
 * Render-time heal layer (frontend self-healing, ADR-0008 aligned).
 *
 * The backend completeness healer guarantees the DATA is present and correct;
 * this module guarantees it RENDERS cleanly and identically across every
 * card/list/drawer/modal on every page (Directory ↔ Dashboard ↔ D1–D7 stay
 * congruent because they all normalise through the same helpers). It never
 * fabricates — it only formats/guards what the API returns. Reuses the
 * canonical maturity scale (`maturity.ts`) and subvertical labels (`labels.ts`)
 * so there is one source of truth for colour and naming.
 */
import { subverticalLabel } from "./labels";
import { maturityHex, maturityLabel } from "./maturity";

// A bare Drive/file id: one 20+ char token with no whitespace. Drive ids are
// base64-ish (mixed case + digits + _/-), e.g. "1NYe2zU3wmBEvd8ZRFWEHpAGIU…",
// so match the whole-token shape — not just lowercase hex (the old
// /^[0-9a-f]{16,}$/i missed the real, mixed-case Drive ids that leaked through).
const _DRIVE_ID = /^[A-Za-z0-9_-]{20,}$/;
// A leaf folder/file mis-parsed as an entity name: "03_scoring_workbook", …
const _FOLDER_ARTIFACT = /^\d{2}[-_ ](scoring|reports|appendices|research|governance|evidence|narrative)/i;
// A DMA *package* folder/file name that leaked in as the entity name:
//   "VNO DMA Engagement FINAL", "Acme - DMA", "Foo_DMA_Complete_Package".
// These are Zennify-internal artifacts, never a client's real display name.
const _PACKAGE_ARTIFACT = /\bdma\s+engagement\b|\bdma[_\s]complete[_\s]package\b|[-_\s]dma\s*$/i;

/** A display-safe entity name — never a bare Drive id or folder/package artifact. */
export function healName(name: string | null | undefined, fallback = "Unnamed client"): string {
  const n = (name ?? "").trim();
  if (!n || _DRIVE_ID.test(n) || _FOLDER_ARTIFACT.test(n) || _PACKAGE_ARTIFACT.test(n)) {
    return fallback;
  }
  return n;
}

/** Subvertical CODE → human label (RB → "Regional Bank"); never a raw code. */
export function healSubvertical(code: string | null | undefined): string {
  const label = subverticalLabel(code);
  return label && label !== code ? label : (label || "—");
}

/** An HQ string, never a JSON-dict/array blob that leaked from parsed_facts. */
export function healHq(hq: unknown): string | null {
  if (typeof hq !== "string") return null;
  const s = hq.trim();
  if (!s || s.startsWith("{") || s.startsWith("[")) return null;
  return s;
}

/** Score → hex via the canonical maturity scale (single source of truth). */
export function healColor(score: number | null | undefined): string {
  return maturityHex(score ?? null);
}

/** Score → maturity band label ("Building" …); null-safe. */
export function healBand(score: number | null | undefined): string {
  return maturityLabel(score ?? null);
}

/** Clamp a maturity score to [1,5]; null when absent/non-finite. */
export function healScore(score: number | null | undefined): number | null {
  if (score == null || !Number.isFinite(score)) return null;
  return Math.min(5, Math.max(1, score));
}

/** Trim overflowing text to `max` chars with an ellipsis (card-name fit). */
export function healText(s: string | null | undefined, max = 80): string {
  const t = (s ?? "").trim();
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t;
}
