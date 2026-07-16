/**
 * labelTableRows — derives td[data-label] from a .tbl table's own headers,
 * so the ≤760px stacked-card layout shows the right column prefixes.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { labelTableRows } from "@/lib/tableLabels";

function mkTable(html: string): HTMLElement {
  const root = document.createElement("div");
  root.innerHTML = html;
  return root;
}

describe("labelTableRows", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("labels each body cell by its column header index", () => {
    const root = mkTable(`
      <table class="tbl">
        <thead><tr><th>Date</th><th>Status</th><th>Score</th></tr></thead>
        <tbody>
          <tr><td>2024</td><td>Done</td><td>3.4</td></tr>
          <tr><td>2025</td><td>Active</td><td>4.1</td></tr>
        </tbody>
      </table>`);
    labelTableRows(root);
    const cells = root.querySelectorAll("tbody td");
    expect(cells[0].getAttribute("data-label")).toBe("Date");
    expect(cells[1].getAttribute("data-label")).toBe("Status");
    expect(cells[2].getAttribute("data-label")).toBe("Score");
    expect(cells[3].getAttribute("data-label")).toBe("Date");
    expect(cells[5].getAttribute("data-label")).toBe("Score");
  });

  it("ignores tables without a .tbl class", () => {
    const root = mkTable(`
      <table>
        <thead><tr><th>A</th></tr></thead>
        <tbody><tr><td>x</td></tr></tbody>
      </table>`);
    labelTableRows(root);
    expect(root.querySelector("td")?.hasAttribute("data-label")).toBe(false);
  });

  it("is a no-op when there is no thead", () => {
    const root = mkTable(`<table class="tbl"><tbody><tr><td>x</td></tr></tbody></table>`);
    labelTableRows(root);
    expect(root.querySelector("td")?.hasAttribute("data-label")).toBe(false);
  });

  it("does not throw on null/invalid roots", () => {
    expect(() => labelTableRows(null)).not.toThrow();
    expect(() => labelTableRows(undefined)).not.toThrow();
  });

  it("only rewrites when the label actually changes (idempotent)", () => {
    const root = mkTable(`
      <table class="tbl">
        <thead><tr><th>Name</th></tr></thead>
        <tbody><tr><td>Acme</td></tr></tbody>
      </table>`);
    labelTableRows(root);
    const td = root.querySelector("td")!;
    expect(td.getAttribute("data-label")).toBe("Name");
    // Second pass is a no-op (same value).
    labelTableRows(root);
    expect(td.getAttribute("data-label")).toBe("Name");
  });
});
