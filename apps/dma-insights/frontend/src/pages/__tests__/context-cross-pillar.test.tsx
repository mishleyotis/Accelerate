/**
 * D5 CrossPillarStoriesPanel — pillar filter, items, empty state, fail-closed.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { CrossPillarStoriesPanel } from "@/pages/ContextPage";
import * as queries from "@/lib/queries";
import type {
  CrossPillarStoryListResponse,
  CrossPillarStoryOut,
} from "@/lib/queries";

function loaded<T>(data: T) {
  return { data, isLoading: false, isError: false, error: null };
}

function story(over: Partial<CrossPillarStoryOut> = {}): CrossPillarStoryOut {
  return {
    story_key: "S1", origin_pillar: "P1", origin_subcap_id: "P1C1.1.1",
    origin_capability: "Strategy Capability", target_pillar: "P4",
    themes: ["data-readiness"], subcaps_touched: ["P1C1.1.1"],
    sample_subcap_names: ["Strategy Foundation"],
    why_this_matters: "Below peer median.",
    ...over,
  };
}

function resp(stories: CrossPillarStoryOut[]): CrossPillarStoryListResponse {
  return {
    entity_display_id: "alma-bank-0001", catalogue_version: "v7.0",
    pillar_filter: null, total: stories.length, stories,
    state: stories.length ? "full_match" : "no_subverticals_match",
  };
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("CrossPillarStoriesPanel (D5)", () => {
  it("renders story rows with origin/target pillar + why + subcap chips", () => {
    vi.spyOn(queries, "useCrossPillarStories").mockReturnValue(
      loaded(resp([story()])) as ReturnType<typeof queries.useCrossPillarStories>,
    );
    render(<CrossPillarStoriesPanel displayId="alma-bank-0001" />);
    expect(screen.getByText("Cross-pillar stories")).toBeTruthy();
    expect(screen.getByText("Strategy Capability")).toBeTruthy();   // heading
    expect(screen.getByText("Strategy Foundation")).toBeTruthy();   // subcap chip
    expect(screen.getByText(/Below peer median/)).toBeTruthy();
    expect(screen.getByText("→ P4")).toBeTruthy();
  });

  it("clicking a pillar filter re-queries with that origin pillar", () => {
    const spy = vi.spyOn(queries, "useCrossPillarStories").mockReturnValue(
      loaded(resp([story()])) as ReturnType<typeof queries.useCrossPillarStories>,
    );
    render(<CrossPillarStoriesPanel displayId="alma-bank-0001" />);
    expect(spy).toHaveBeenLastCalledWith("alma-bank-0001", null);   // ALL → null
    fireEvent.click(screen.getByRole("button", { name: "P2" }));
    expect(spy).toHaveBeenLastCalledWith("alma-bank-0001", "P2");
  });

  it("unfiltered empty renders NOTHING (fail-closed, ADR contract)", () => {
    // An empty card in the page's prime slot pushes the timeline below
    // the fold (all-94 parity capture) — no stories at "All" → null.
    vi.spyOn(queries, "useCrossPillarStories").mockReturnValue(
      loaded(resp([])) as ReturnType<typeof queries.useCrossPillarStories>,
    );
    const { container } = render(<CrossPillarStoriesPanel displayId="alma-bank-0001" />);
    expect(container.firstChild).toBeNull();
  });

  it("pillar-filtered empty keeps the contextual empty state", () => {
    // Interactive filter state IS worth explaining — the panel already
    // rendered (stories existed at "All"), the user narrowed to a pillar
    // with none.
    const spy = vi.spyOn(queries, "useCrossPillarStories").mockReturnValue(
      loaded(resp([story()])) as ReturnType<typeof queries.useCrossPillarStories>,
    );
    render(<CrossPillarStoriesPanel displayId="alma-bank-0001" />);
    spy.mockReturnValue(
      loaded(resp([])) as ReturnType<typeof queries.useCrossPillarStories>,
    );
    fireEvent.click(screen.getByRole("button", { name: "P2" }));
    expect(screen.getByText(/No stories originate from P2/i)).toBeTruthy();
  });

  it("fail-closed: query error + no stories → renders nothing", () => {
    vi.spyOn(queries, "useCrossPillarStories").mockReturnValue(
      { data: undefined, isLoading: false, isError: true, error: new Error("403") } as
        ReturnType<typeof queries.useCrossPillarStories>,
    );
    const { container } = render(<CrossPillarStoriesPanel displayId="alma-bank-0001" />);
    expect(container.firstChild).toBeNull();
  });
});
