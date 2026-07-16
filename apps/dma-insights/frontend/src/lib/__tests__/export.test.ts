/**
 * Client-side export helpers — CSV serialization + print-to-PDF.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { csvCell, downloadCsv, printView, toCsv } from "@/lib/export";

afterEach(() => { vi.restoreAllMocks(); });

describe("csvCell", () => {
  it("quotes values and escapes embedded quotes; null/undefined → empty", () => {
    expect(csvCell("hi")).toBe('"hi"');
    expect(csvCell('a "b" c')).toBe('"a ""b"" c"');
    expect(csvCell(null)).toBe('""');
    expect(csvCell(undefined)).toBe('""');
    expect(csvCell(42)).toBe('"42"');
  });
});

describe("toCsv", () => {
  it("builds an escaped RFC-4180 CSV (header + rows)", () => {
    expect(toCsv(["a", "b"], [["x", 'y"z'], [1, null]]))
      .toBe('"a","b"\n"x","y""z"\n"1",""');
  });
});

describe("downloadCsv", () => {
  it("triggers an anchor download with the filename + revokes the url", () => {
    // jsdom doesn't define these — assign rather than spy.
    URL.createObjectURL = vi.fn(() => "blob:fake") as typeof URL.createObjectURL;
    const revoke = vi.fn();
    URL.revokeObjectURL = revoke as typeof URL.revokeObjectURL;
    const click = vi.fn();
    const created: HTMLAnchorElement[] = [];
    const realCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = realCreate(tag);
      if (tag === "a") { (el as HTMLAnchorElement).click = click; created.push(el as HTMLAnchorElement); }
      return el;
    });

    downloadCsv("out.csv", ["a"], [["x"]]);

    expect(click).toHaveBeenCalledOnce();
    expect(created[0]?.download).toBe("out.csv");
    expect(revoke).toHaveBeenCalledWith("blob:fake");
  });
});

describe("printView", () => {
  it("invokes the browser print dialog (Save-as-PDF)", () => {
    const print = vi.fn();
    window.print = print;
    printView();
    expect(print).toHaveBeenCalledOnce();
  });
});
