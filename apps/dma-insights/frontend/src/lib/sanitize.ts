/**
 * Presentation-text sanitizer (2026-06-10 operator mandate: "no wrong
 * or empty info presented"). Three leak classes were found live:
 *
 *   1. Pipeline metadata served as content — focus-area "quotes" like
 *      "SECTION 1 COMPLETE — Assessment ID DMA-RES-CPB-… | Evidence
 *      Mode: PUBLIC | …" (bot run-log lines the DOCX parser captured).
 *   2. Label/ID prefixes leaking into titles — "F-002 | Hybrid
 *      digital-branch model…", "Maturity implication | M3+ …".
 *   3. display_id slugs shown while the entity name loads —
 *      "alma-bank-0002" → users read "client name with 0002".
 *
 * Backend cleans at the SOURCE (parsers strip on ingest); these
 * helpers are the defense-in-depth at render time so no historical or
 * third-party row can put junk on screen.
 */

const META_RE =
  /SECTION\s+\d+\s+COMPLETE|Assessment\s+ID\s+DMA-|Evidence\s+Mode:\s*(PUBLIC|HYBRID)|^Batch\s+\d+\s*\/|^run_id\s*:/i;

const PLACEHOLDERS = new Set([
  "", "-", "—", "(unknown)", "(untitled)", "null", "undefined", "n/a", "none",
]);

/** True when the string is junk a user should never read. */
export function isJunkText(t: string | null | undefined): boolean {
  const v = (t ?? "").trim();
  if (PLACEHOLDERS.has(v.toLowerCase())) return true;
  if (META_RE.test(v)) return true;
  // Pure digit/punctuation blobs ("2026-04-29 0001 | 5.0 | …").
  if (v.length > 3 && /^[\d\s.,;:|%·/-]+$/.test(v)) return true;
  return false;
}

/** Returns trimmed text, or null when it isn't fit to present. */
export function presentable(t: string | null | undefined): string | null {
  const v = (t ?? "").trim();
  return isJunkText(v) ? null : v;
}

/**
 * Strip a leading "TOKEN | " label prefix (id or field label the bot
 * concatenated into the prose). Only fires for short prefixes so real
 * sentences containing a pipe stay intact.
 */
export function stripLabelPrefix(t: string | null | undefined): string {
  const v = (t ?? "").trim();
  const m = v.match(/^(#?\d{1,3}|[A-Za-z][\w .#&-]{0,30})\s*\|\s+(.{8,})$/s);
  return m ? m[2].trim() : v;
}

/**
 * Human fallback for a display_id slug while the entity name loads —
 * "alma-bank-0002" → "Alma Bank" (never show the numeric suffix).
 */
export function nameFromSlug(displayId: string | null | undefined): string {
  const v = (displayId ?? "").trim();
  if (!v) return "Client";
  const words = v
    .replace(/-[0-9a-f]{4}$|-\d{2,4}$/i, "")
    .split(/-+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1));
  return words.join(" ") || "Client";
}


/** 2026-06-11 live-corpus QA: newer handoff packages ship focus-area
 *  titles as full pipe-delimited analyst lines with a trailing
 *  "(→OBJ-1, HIGH)" routing suffix and wrapping quotes. Mirror of the
 *  backend focus_area_sanity._strip_machine_tokens so titles heal on a
 *  frontend deploy even before the backend image catches up. */
export function stripMachineTokens(text: string | null | undefined): string {
  if (!text) return "";
  let t = text.trim().replace(/^["\u201c\u201d]+|["\u201c\u201d]+$/g, "").trim();
  t = t.split("|", 1)[0].trim();
  t = t.replace(/\s*\(\s*(?:→|->)?\s*OBJ[- ]?\d+\s*,?\s*(?:HIGH|MEDIUM|LOW)?\s*\)\s*$/i, "");
  return t.replace(/[\s\-—·]+$/g, "").trim();
}

/** True when the id is a storage UUID (never render those as chips). */
export function isUuidLike(id: string | null | undefined): boolean {
  return !!id && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
}

/**
 * Human label for a focus area's SOURCE footer. The DB `source_path`
 * carries machine values — "(unknown)" (236 rows live), "docx:strategic_
 * section", "synthesized:heuristic", and occasionally leaked excerpt
 * TEXT — none of which an AE should read verbatim. Falls back to the
 * grounding source_kind; returns null when there is nothing meaningful
 * (caller omits the line).
 */
export function focusSourceLabel(
  sourcePath: string | null | undefined,
  sourceKind?: string | null,
): string | null {
  const sp = (sourcePath ?? "").trim();
  const kind = (sourceKind ?? "").trim().toLowerCase();
  const KIND_LABEL: Record<string, string> = {
    docx: "Client research report",
    gemini: "AI-clustered from capability gaps",
    heuristic: "Derived from scored capability gaps",
  };
  if (sp && !PLACEHOLDERS.has(sp.toLowerCase())) {
    if (sp.startsWith("docx:")) {
      const section = sp.slice(5).replace(/_/g, " ").trim();
      return section ? `Client research report · ${section}` : "Client research report";
    }
    if (sp.startsWith("synthesized:")) {
      return KIND_LABEL[sp.slice(12).split(/[^a-z]/i, 1)[0].toLowerCase()]
        ?? "Synthesized from capability gaps";
    }
    // A real document path (contains a filename-ish tail, no spaces).
    if (/^[\w./\\-]+\.(docx|pdf|xlsx|csv|json|md)$/i.test(sp)) {
      return sp.split(/[/\\]/).pop() ?? sp;
    }
    // Anything else is leaked excerpt text, not a source — fall through.
  }
  return KIND_LABEL[kind] ?? null;
}
