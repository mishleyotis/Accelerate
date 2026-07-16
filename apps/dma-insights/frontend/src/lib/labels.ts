/**
 * Enum → human label helpers. The 2026-06-10 chrome audit found raw
 * underscore enums (MANUAL_BACKFILL, PENDING_REVIEW, thin_evidence)
 * rendered verbatim across pages — debug output in AE-facing UI.
 * Every JSX site that prints an enum value goes through these so the
 * class can't recur page-by-page.
 */

/** Underscores → spaces, original casing kept (badges are CAPS via CSS). */
export function humanizeEnum(v: string | null | undefined): string {
  return (v ?? "").replace(/_/g, " ");
}

/**
 * Tech-stack row source badge (prototype parity: "Annual report",
 * "Press release", "Explorium" — never raw enums). The live column
 * carries machine values: "report_mention", "Explorium tech_it_security
 * + tech_finance_and_accounting", CSV filenames ("A4_Tech_Stack_Map.csv").
 * Full detail stays in the badge's title tooltip at the call site.
 */
export function techSourceLabel(s: string | null | undefined): string {
  const v = (s ?? "").trim();
  if (!v) return "";
  if (/^explorium/i.test(v)) return "Explorium";
  if (/\.csv$/i.test(v)) return "Stack inventory CSV";
  if (/report_mention/i.test(v)) return "Report mention";
  if (/job[_ ]posting/i.test(v)) return "Job posting";
  if (/press[_ ]release/i.test(v)) return "Press release";
  const t = humanizeEnum(v);
  return t.length > 26 ? `${t.slice(0, 24)}…` : t;
}

/** Run/data-source badge text (prototype 09_pages_e.js parity). */
export function sourceLabelText(s: string | null | undefined): string {
  switch (s) {
    case "DRIVE_PARSE": return "DRIVE PARSE";
    case "DRIVE_BACKFILL": return "DRIVE BACKFILL";
    case "PROJECT_API": return "PROJECT API";
    case "MANUAL_BACKFILL": return "BACKFILL";
    case "BOT_REQUEST": return "BOT REQUEST";
    default: return humanizeEnum(s);
  }
}

/**
 * Subvertical code → human label. The wireframe (01_data.js) keyed this
 * on long codes (REGIONAL_BANK…); the live corpus normalises subverticals
 * to the short codes the entities table actually stores (RB, CU, CL, …).
 * Cards render `SUBVERTICAL_LABEL[code] ?? code`, and the New-run wizard's
 * dropdown is built from this map, so the slug an AE picks round-trips to
 * the bot as a recognised subvertical.
 */
export const SUBVERTICAL_LABEL: Record<string, string> = {
  RB: "Regional Bank",
  CU: "Credit Union",
  CL: "Commercial Lending",
  AM: "Asset Manager",
  CIB: "Corporate & Investment Banking",
  FC: "Farm Credit",
  IB: "Insurance Broker",
  IC: "Insurance Carrier",
  RIA: "Wealth / RIA",
};

/** Subvertical label with graceful fallback to the raw code. */
export function subverticalLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return SUBVERTICAL_LABEL[code] ?? code;
}
