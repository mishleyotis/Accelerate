/**
 * Icon — guards the 55-glyph registry against regressing to an empty <svg>
 * stub (the prior production bug where every icon rendered blank).
 */
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Icon } from "../utils";

// Representative coverage across nav / action / domain / status families.
const GLYPHS = [
  "home", "grid", "bell", "search", "user", "settings", "drive", "x", "check",
  "chevron-r", "chevron-l", "chevron-d", "chevron-u", "arrow-r", "arrow-up",
  "arrow-dn", "lock", "external", "filter", "plus", "minus", "edit", "download",
  "copy", "warn", "info", "evidence", "ai", "menu", "logout", "platform",
  "heatmap", "insight", "timeline", "shield", "stack", "drilldown", "users",
  "envelope", "money", "refresh", "scale", "sparkle", "calendar", "linkedin",
  "phone", "doc", "route", "building", "stairs", "play", "globe", "share",
  "switch", "lightbulb",
];

describe("Icon", () => {
  it("renders a non-empty SVG with vector content for every known glyph", () => {
    for (const name of GLYPHS) {
      const { container } = render(<Icon name={name} />);
      const svg = container.querySelector("svg");
      expect(svg, `missing <svg> for "${name}"`).toBeTruthy();
      // The stub rendered an empty <svg/> with zero children — assert real geometry.
      const shapes = svg!.querySelectorAll("path, rect, circle, polygon, line");
      expect(shapes.length, `glyph "${name}" rendered no vector shapes`).toBeGreaterThan(0);
    }
  });

  it("applies the canonical 1.8px round monochrome stroke and currentColor", () => {
    const { container } = render(<Icon name="home" />);
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("stroke")).toBe("currentColor");
    expect(svg.getAttribute("stroke-width")).toBe("1.8");
    expect(svg.getAttribute("stroke-linecap")).toBe("round");
    expect(svg.getAttribute("fill")).toBe("none");
    expect(svg.getAttribute("viewBox")).toBe("0 0 24 24");
  });

  it("honours the size prop on width/height", () => {
    const { container } = render(<Icon name="bell" size={24} />);
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("width")).toBe("24");
    expect(svg.getAttribute("height")).toBe("24");
  });

  it("falls back to a placeholder circle for an unknown glyph", () => {
    const { container } = render(<Icon name="not-a-real-glyph" />);
    expect(container.querySelector("svg circle")).toBeTruthy();
  });
});
