/**
 * Responsive table labels.
 *
 * The prototype's ≤760px rule stacks each table row into a card and prefixes
 * every cell with its column header via `td::before { content: attr(data-label) }`.
 * That needs a `data-label` on each `<td>`. Rather than hand-annotate every
 * `<td>` across 8 page files (and miss future tables), this derives the label
 * generically from each `table.tbl`'s own `<thead>` headers, by column index.
 *
 * `labelTableRows` is pure DOM (unit-tested). `installTableLabels` wires it to
 * a MutationObserver that watches ONLY childList/subtree — never `attributes` —
 * so our own `data-label` writes can't retrigger it (no loop), while newly
 * rendered/filtered rows still get labelled. Cheap: it only touches `table.tbl`.
 */

/** Set `data-label` on every body cell of every `.tbl` table under `root`. */
export function labelTableRows(root: ParentNode | null | undefined): void {
  if (!root || typeof (root as ParentNode).querySelectorAll !== "function") return;
  const tables = (root as ParentNode).querySelectorAll<HTMLTableElement>("table.tbl");
  tables.forEach((table) => {
    const headers = Array.from(table.querySelectorAll("thead th")).map((th) =>
      (th.textContent || "").trim(),
    );
    if (headers.length === 0) return;
    table.querySelectorAll("tbody tr").forEach((tr) => {
      Array.from(tr.children).forEach((cell, i) => {
        const label = headers[i] ?? "";
        // Guard: only write when the value actually changes (avoids redundant
        // attribute mutations).
        if (label && cell.getAttribute("data-label") !== label) {
          cell.setAttribute("data-label", label);
        }
      });
    });
  });
}

/**
 * Install the observer on `document.body`. Returns a teardown fn.
 * rAF-debounced so a burst of DOM mutations coalesces into one pass.
 */
export function installTableLabels(): () => void {
  if (typeof document === "undefined" || typeof MutationObserver === "undefined") {
    return () => undefined;
  }
  let scheduled = false;
  const run = (): void => {
    scheduled = false;
    labelTableRows(document);
  };
  const schedule = (): void => {
    if (scheduled) return;
    scheduled = true;
    (typeof requestAnimationFrame === "function"
      ? requestAnimationFrame
      : (cb: () => void) => setTimeout(cb, 16))(run);
  };
  // Initial pass + observe structural changes only (NOT attributes).
  labelTableRows(document);
  const observer = new MutationObserver(schedule);
  observer.observe(document.body, { childList: true, subtree: true });
  return () => observer.disconnect();
}
