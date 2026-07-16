/**
 * Client-side export helpers — CSV download + print-to-PDF.
 *
 * `downloadCsv` builds a CSV from already-loaded rows and triggers a browser
 * download (no backend round-trip). `printView` opens the browser's native
 * print dialog (Save as PDF), scoped by the `@media print` rules in app.css
 * so the page content exports without the chrome.
 */

/** RFC-4180 cell quoting — wrap in quotes, double any embedded quote. */
export function csvCell(v: unknown): string {
  const s = v === null || v === undefined ? "" : String(v);
  return `"${s.replace(/"/g, '""')}"`;
}

export type CsvValue = string | number | boolean | null | undefined;

/** Serialize a header + rows into an RFC-4180 CSV string (pure, testable). */
export function toCsv(headers: string[], rows: CsvValue[][]): string {
  return [
    headers.map(csvCell).join(","),
    ...rows.map((r) => r.map(csvCell).join(",")),
  ].join("\n");
}

export function downloadCsv(
  filename: string,
  headers: string[],
  rows: CsvValue[][],
): void {
  const blob = new Blob([toCsv(headers, rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Open the browser print dialog (Save-as-PDF). The `@media print` block in
 *  app.css hides the sidebar / topbar / action buttons so the page exports
 *  cleanly. */
export function printView(): void {
  window.print();
}
