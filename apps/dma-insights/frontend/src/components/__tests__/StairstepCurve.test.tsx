/**
 * StairstepCurve — render matrix for the wireframe staircase
 * (08_pages_d.js · StairstepCurve port).
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StairstepCurve } from "../StairstepCurve";
import * as stairstep from "@/lib/stairstep";

function mk(over: Partial<ReturnType<typeof stairstep.useStairstep>>) {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    ...over,
  } as ReturnType<typeof stairstep.useStairstep>;
}

const CURRENTS = { P1: 2.5, P2: 4.5, P3: 4.0, P4: 2.0 };

describe("StairstepCurve", () => {
  it("renders nothing when displayId null", () => {
    // Hook runs unconditionally (rules-of-hooks) with the query disabled.
    vi.spyOn(stairstep, "useStairstep").mockReturnValue(mk({}));
    const { container } = render(<StairstepCurve displayId={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows loading state under the card head", () => {
    vi.spyOn(stairstep, "useStairstep").mockReturnValue(mk({ isLoading: true }));
    render(<StairstepCurve displayId="fce-001" />);
    expect(screen.getByText(/Stairstepped maturity curve/)).toBeTruthy();
    expect(screen.getByText(/Loading stairstep/i)).toBeTruthy();
  });

  it("shows error state", () => {
    vi.spyOn(stairstep, "useStairstep").mockReturnValue(mk({ error: new Error("x") }));
    render(<StairstepCurve displayId="fce-001" />);
    expect(screen.getByText(/Couldn't load stairstep/i)).toBeTruthy();
  });

  it("shows no-gaps empty state", () => {
    vi.spyOn(stairstep, "useStairstep").mockReturnValue(mk({
      data: {
        entity_display_id: "fce-001", run_request_id: null,
        steps_by_pillar: {}, current_by_pillar: {},
        end_score_by_pillar: {}, target_band_score: 4.0,
        empty_state: "no-gaps",
      },
    }));
    render(<StairstepCurve displayId="fce-001" />);
    expect(screen.getByText(/No scored subcaps yet/i)).toBeTruthy();
  });

  it("shows the ingest empty state when no run scored anything", () => {
    vi.spyOn(stairstep, "useStairstep").mockReturnValue(mk({
      data: {
        entity_display_id: "x", run_request_id: null,
        steps_by_pillar: { P1: [], P2: [], P3: [], P4: [] },
        current_by_pillar: { P1: 0, P2: 0, P3: 0, P4: 0 },
        end_score_by_pillar: { P1: 0, P2: 0, P3: 0, P4: 0 },
        target_band_score: 4.0,
        empty_state: null,
      },
    }));
    render(<StairstepCurve displayId="x" />);
    expect(screen.getByText(/No scored subcaps yet/i)).toBeTruthy();
  });

  it("still renders the staircase on no-recs — bands + honest empty notes", () => {
    vi.spyOn(stairstep, "useStairstep").mockReturnValue(mk({
      data: {
        entity_display_id: "x", run_request_id: "REQ-x",
        steps_by_pillar: { P1: [], P2: [], P3: [], P4: [] },
        current_by_pillar: CURRENTS,
        end_score_by_pillar: CURRENTS,
        target_band_score: 4.0,
        empty_state: "no-recs",
      },
    }));
    render(<StairstepCurve displayId="x" />);
    // 4 wireframe step bands (SVG label + meta chip each)
    for (const band of ["Building", "Competing", "Differentiating", "Leading"]) {
      expect(screen.getAllByText(new RegExp(band)).length).toBeGreaterThanOrEqual(1);
    }
    expect(screen.getAllByText(/No mapped recommendation in this run/i).length).toBeGreaterThanOrEqual(1);
  });

  it("renders the staircase (not a false at-target claim) on no-applicable-uplift", () => {
    vi.spyOn(stairstep, "useStairstep").mockReturnValue(mk({
      data: {
        entity_display_id: "x", run_request_id: "REQ-x",
        steps_by_pillar: { P1: [], P2: [], P3: [], P4: [] },
        current_by_pillar: { P1: 1.95, P2: 1.76, P3: 2.43, P4: 1.79 },
        end_score_by_pillar: { P1: 1.95, P2: 1.76, P3: 2.43, P4: 1.79 },
        target_band_score: 4.0,
        empty_state: "no-applicable-uplift",
      },
    }));
    render(<StairstepCurve displayId="x" focusPillar="P4" />);
    expect(screen.queryByText(/Already at target/i)).toBeNull();
    expect(screen.getByText(/Stairstepped maturity curve/)).toBeTruthy();
    // Current marker carries the real P4 score, honest to one decimal.
    expect(screen.getByText(/Today — current 1\.8 in Data & AI/)).toBeTruthy();
  });

  it("renders rec steps in the band their score_after reaches, with roadmap meta", () => {
    vi.spyOn(stairstep, "useStairstep").mockReturnValue(mk({
      data: {
        entity_display_id: "x", run_request_id: "REQ-x",
        steps_by_pillar: {
          P1: [
            {
              rec_id: "REC-1", title: "Adopt nCino", pillar: "P1",
              score_before: 2.5, score_after: 3.3, uplift: 0.8,
            },
          ],
          P2: [],
          P3: [],
          P4: [
            {
              rec_id: "REC-9", title: "Data Cloud", pillar: "P4",
              score_before: 2.0, score_after: 2.4, uplift: 0.4,
            },
          ],
        },
        current_by_pillar: CURRENTS,
        end_score_by_pillar: { P1: 3.3, P2: 4.5, P3: 4.0, P4: 2.4 },
        target_band_score: 4.0,
        empty_state: null,
      },
    }));
    const onRecClick = vi.fn();
    render(
      <StairstepCurve
        displayId="x"
        focusPillar="P1"
        recMeta={{ "REC-1": { platform: "nCino", duration: "4 mo" } }}
        onRecClick={onRecClick}
      />,
    );
    expect(screen.getByText(/Stairstepped maturity curve/)).toBeTruthy();
    expect(screen.getByText(/Adopt nCino/)).toBeTruthy();
    // Roadmap-payload platform + phase duration surface on the band tile
    expect(screen.getByText(/nCino · 4 mo/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Open recommendation REC-1/ }));
    expect(onRecClick).toHaveBeenCalledWith("REC-1");
  });

  it("re-focuses the staircase via the pillar toggle", () => {
    vi.spyOn(stairstep, "useStairstep").mockReturnValue(mk({
      data: {
        entity_display_id: "x", run_request_id: "REQ-x",
        steps_by_pillar: { P1: [], P2: [], P3: [], P4: [] },
        current_by_pillar: CURRENTS,
        end_score_by_pillar: CURRENTS,
        target_band_score: 4.0,
        empty_state: null,
      },
    }));
    render(<StairstepCurve displayId="x" focusPillar="P1" />);
    expect(screen.getByText(/Today — current 2\.5 in Strategy/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Data & AI" }));
    expect(screen.getByText(/Today — current 2\.0 in Data & AI/)).toBeTruthy();
  });
});
