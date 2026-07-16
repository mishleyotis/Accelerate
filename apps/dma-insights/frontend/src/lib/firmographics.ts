// Firmographics presentation helpers.
//
// The D5 Context "Regulatory & firmographics" card renders a scalar
// key/value grid. The firmographics payload also carries non-scalar
// members (`leadership` / `thought_leadership` arrays) and the prose
// `narrative_md` (rendered in its own AboutCard). Those must be excluded
// from the KV grid — otherwise arrays were JSON.stringify'd into an
// unreadable blob in the `dd` cell (fixed 2026-06-09).

export type FirmographicsScalar = string | number | boolean;

/**
 * The scalar [key, value] entries of a firmographics object, suitable for
 * a KV grid. Drops null/empty values, `narrative_md`, and any non-scalar
 * (object/array) member.
 */
export function scalarFirmographicEntries(
  firm: Record<string, unknown> | null,
): Array<[string, FirmographicsScalar]> {
  if (!firm) return [];
  return Object.entries(firm).filter(
    (entry): entry is [string, FirmographicsScalar] => {
      const [k, v] = entry;
      return (
        v != null &&
        v !== "" &&
        k !== "narrative_md" &&
        (typeof v === "string" || typeof v === "number" || typeof v === "boolean")
      );
    },
  );
}
