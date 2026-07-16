/**
 * TransformationRoadmap — wireframe contract (08_pages_d.js port):
 * dark chevron columns by default, payload-driven sequencing rationale
 * (never hardcoded prose), rec chips with titles, prose-only fallback.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TransformationRoadmap } from "../TransformationRoadmap";
import type { RoadmapPhase } from "@/lib/queries";

const PHASES: RoadmapPhase[] = [
  { phase: 1, label: "Quick Wins", duration: "2 mo", platform: "Salesforce", target: "Maturity +0.4", metric: "First metric", rec_ids: ["REC-01"] },
  { phase: 2, label: "Foundational", duration: "4 mo", platform: "Databricks", target: "Maturity +0.6", metric: "Second metric", rec_ids: ["REC-02"] },
  { phase: 3, label: "Strategic", duration: "8 mo", platform: "Twilio", target: "—", metric: "Third metric", rec_ids: [] },
];

describe("TransformationRoadmap", () => {
  it("renders null with no phases and no prose", () => {
    const { container } = render(<TransformationRoadmap phases={[]} roadmapMd={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("falls back to the payload prose card when phases are absent", () => {
    render(<TransformationRoadmap phases={[]} roadmapMd="Roadmap prose from the package." />);
    expect(screen.getByText(/Roadmap prose from the package/)).toBeTruthy();
  });

  it("chevron view is the default, with dark prototype phase colors", () => {
    const { container } = render(<TransformationRoadmap phases={PHASES} roadmapMd={null} />);
    const on = container.querySelector(".toggle-row button.on");
    expect(on?.textContent).toMatch(/Chevrons/);
    // Dark teal ramp from the prototype ROADMAP data — never the amber
    // maturity-band ramp that produced the QA'd "amber wall".
    const html = container.innerHTML;
    expect(html).toContain("var(--z-dark2)");
    expect(html).toContain("var(--z-mid)");
    expect(html).toContain("var(--z-teal)");
    expect(html).not.toContain("var(--m-act)");
    // Per-phase strip: eyebrow + label + duration
    expect(screen.getAllByText(/Phase 1/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Quick Wins")).toBeTruthy();
    expect(screen.getByText("2 mo")).toBeTruthy();
    expect(screen.getByText(/3-phase sequencing/)).toBeTruthy();
  });

  it("rec chips carry payload titles and open the rec drawer target", () => {
    render(
      <TransformationRoadmap
        phases={PHASES}
        roadmapMd={null}
        recTitles={{ "REC-01": "Establish unified customer data foundation" }}
      />,
    );
    const chip = screen.getByText("REC-01").closest("button");
    expect(chip?.textContent).toContain("Establish unified customer data foundation");
    fireEvent.click(chip as HTMLElement); // must not throw (opens drawer via store)
  });

  it("renders the sequencing rationale ONLY from payload prose", () => {
    const { container, rerender } = render(
      <TransformationRoadmap phases={PHASES} roadmapMd="Phased roadmap sequenced by dependency." />,
    );
    expect(screen.getByText(/Sequencing rationale/i)).toBeTruthy();
    expect(screen.getByText(/Phased roadmap sequenced by dependency/)).toBeTruthy();
    // Honest empty: no payload prose → no footnote, no fabricated copy.
    rerender(<TransformationRoadmap phases={PHASES} roadmapMd={null} />);
    expect(container.textContent).not.toMatch(/Sequencing rationale/i);
    expect(container.textContent).not.toMatch(/staffing is concurrent/i);
  });
});
