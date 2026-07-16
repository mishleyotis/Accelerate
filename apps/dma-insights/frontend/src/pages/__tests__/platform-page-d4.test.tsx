/**
 * D4 PlatformPage — Part 7 rebuild contract:
 *   1. Fit tiles carry the prototype badges (N gaps, N absent,
 *      readiness pill, "Top: {2 subcap names}" line).
 *   2. 6-column gap table renders name+id | pillar | score | peer |
 *      gap | evidence tier-chip; rows CLICK → EvidenceDrawer payload
 *      (displayId + subcapId).
 *   3. Prereq accordion expands to backing subcaps + evidence chips.
 *   4. Fit-score click opens the fit-breakdown drilldown (factor bars +
 *      readiness penalty + contributing subcaps + E-ID chips).
 *   5. Rich recommendation cards render root-cause chips + outcomes
 *      grid + phase pill.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { PlatformPage } from "@/pages/PlatformPage";
import * as queries from "@/lib/queries";
import * as hashRouter from "@/lib/hash-router";
import * as stairstep from "@/lib/stairstep";
import { useUiStore } from "@/store/ui";
import type { PlatformCard, PlatformsResponse } from "@/lib/queries";

function q<T>(data: T) {
  return { data, isLoading: false, error: null } as never;
}

const CARD: PlatformCard = {
  platform_id: "salesforce",
  display_name: "Salesforce",
  pillar: "P2",
  fit_score: 72.4,
  readiness_index: "amber",
  state: "READY",
  addressable_subcap_ids: ["P2C1.1.1", "P4C1.1.1"],
  prereq_checks: [
    { name: "Customer data foundation", required_subcap_id: "P4C1.1.1",
      threshold: 3.0, status: "PARTIAL", current_score: 2.6, note: null },
  ],
  conversation_starter: null,
  conversation_starters: ["Acme scores 1.8 on Unified Profile (P4C1.1.1) [E-047]."],
  fit_breakdown: {
    engine: "v2",
    target_band: "M4",
    factors: {
      opportunity: { value: 0.71, points: 42.6 },
      interconnect: { value: 0.3, points: 7.5, dependent_subcaps: 9 },
      absent_boost: { value: 1, points: 15 },
      readiness: { light: "amber", multiplier: 0.85, penalty_points: -9.8 },
    },
    evidence_strength: 0.44,
    n_addressable: 2,
    top_subcaps: [
      { subcap_id: "P4C1.1.1", name: "Unified Customer Profile", pillar: "P4",
        score: 1.8, peer_median: 3.0, gap: 2.2, opportunity: 0.61,
        e_ids: ["E-047", "E-141"], tier: 2 },
      { subcap_id: "P2C1.1.1", name: "Digital Account Opening", pillar: "P2",
        score: 2.2, peer_median: 2.9, gap: 1.8, opportunity: 0.5,
        e_ids: [], tier: null },
    ],
    absent_families: ["Salesforce"],
    sequence: { rank: 2, after: ["ncino"] },
  },
  sequence_rank: 2,
  absent_count: 3,
  top_subcap_names: ["Unified Customer Profile", "Digital Account Opening"],
};

const RESP: PlatformsResponse = {
  entity_display_id: "acme-0001",
  run_request_id: "REQ-1",
  cards: [CARD],
  pillar_offerings: {},
  narrative: null,
};

beforeEach(() => {
  vi.spyOn(hashRouter, "useRoute").mockReturnValue({
    path: "/clients/acme-0001/platform",
    query: { platform: "salesforce" },
    setQuery: vi.fn(),
    navigate: vi.fn(),
  } as unknown as ReturnType<typeof hashRouter.useRoute>);
  vi.spyOn(queries, "useEntityPlatforms").mockReturnValue(q(RESP));
  vi.spyOn(queries, "useEntityRecommendationsList").mockReturnValue(q([
    { id: "uuid-1", rec_id: "REC-04", title: "Unified customer data foundation",
      platform_id: "salesforce", feature: "Data Cloud", phase: 1,
      root_cause_e_ids: ["E-047", "E-141"],
      outcomes: { time: "6-9 months", effort: "M",
                  metric: "Single customer view across 3 cores", peer: "Synovus" } },
  ]));
  vi.spyOn(queries, "useEntityPlatformRoadmap").mockReturnValue(q({
    entity_display_id: "acme-0001", run_request_id: "REQ-1",
    phases: [], total_duration_months: 0,
  }));
  vi.spyOn(stairstep, "useStairstep").mockReturnValue(
    q({ entity_display_id: "acme-0001", run_request_id: "REQ-1",
        steps_by_pillar: {}, current_by_pillar: {}, end_score_by_pillar: {},
        target_band_score: 4, empty_state: "no-gaps" }),
  );
  useUiStore.setState({ activeDrawer: null, drawerPayload: undefined });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("PlatformPage (D4 Part 7)", () => {
  it("fit tile renders gaps + absent badge + readiness pill + Top names", () => {
    render(<PlatformPage />);
    const tile = screen.getByTestId("fit-tile-salesforce");
    expect(tile.textContent).toContain("2 gaps");
    expect(tile.textContent).toContain("3 absent");
    expect(tile.textContent).toContain("AMBER");
    expect(tile.textContent).toContain("Top: Unified Customer Profile · Digital Account Opening");
  });

  it("6-col gap table renders name+id, score/peer chips, gap and tier-chip", () => {
    render(<PlatformPage />);
    const table = screen.getByTestId("gap-table");
    // 6 column headers
    expect(table.querySelectorAll("thead th").length).toBe(6);
    const row = screen.getByTestId("gap-row-P4C1.1.1");
    expect(row.textContent).toContain("Unified Customer Profile");
    expect(row.textContent).toContain("P4C1.1.1");
    expect(row.textContent).toContain("1.8");
    expect(row.textContent).toContain("3.0");
    expect(row.textContent).toContain("−1.2"); // peer 3.0 − score 1.8
    expect(row.querySelector(".tier-chip")?.textContent).toBe("E-047");
    // Evidence-less row falls back to the platform feature text.
    const row2 = screen.getByTestId("gap-row-P2C1.1.1");
    expect(row2.textContent).toContain("Agentforce");
  });

  it("gap table row click opens the EvidenceDrawer scoped to the subcap", () => {
    render(<PlatformPage />);
    fireEvent.click(screen.getByTestId("gap-row-P4C1.1.1"));
    const s = useUiStore.getState();
    expect(s.activeDrawer).toBe("evidence");
    expect(s.drawerPayload).toMatchObject({
      displayId: "acme-0001", subcapId: "P4C1.1.1",
    });
  });

  it("prereq accordion expands to backing subcaps + evidence chips", () => {
    render(<PlatformPage />);
    expect(screen.queryByTestId("prereq-body-P4C1.1.1")).toBeNull();
    fireEvent.click(screen.getByTestId("prereq-toggle-P4C1.1.1"));
    const body = screen.getByTestId("prereq-body-P4C1.1.1");
    expect(body.textContent).toContain("Backing subcaps");
    expect(body.textContent).toContain("Unified Customer Profile");
    expect(body.textContent).toContain("Evidence");
    expect(body.textContent).toContain("E-047");
    // Collapses again.
    fireEvent.click(screen.getByTestId("prereq-toggle-P4C1.1.1"));
    expect(screen.queryByTestId("prereq-body-P4C1.1.1")).toBeNull();
  });

  it("fit-score click opens the breakdown drilldown with factor bars + E-ID chips", () => {
    render(<PlatformPage />);
    expect(screen.queryByTestId("fit-breakdown-modal")).toBeNull();
    fireEvent.click(screen.getByTestId("fit-score-salesforce"));
    const modal = screen.getByTestId("fit-breakdown-modal");
    expect(modal.textContent).toContain("Opportunity");
    expect(modal.textContent).toContain("+42.6 pts");
    expect(modal.textContent).toContain("Interconnect");
    expect(modal.textContent).toContain("9 dependent subcaps");
    expect(modal.textContent).toContain("Absent boost");
    expect(modal.textContent).toContain("Readiness gate (AMBER)");
    expect(modal.textContent).toContain("-9.8 pts");
    expect(modal.textContent).toContain("sequence #2");
    expect(modal.textContent).toContain("E-047");
  });

  it("rich rec card renders root-cause chips + outcomes grid + phase pill", () => {
    render(<PlatformPage />);
    const rec = screen.getByTestId("rec-card-REC-04");
    expect(rec.textContent).toContain("Phase 1");
    expect(rec.textContent).toContain("Data Cloud");
    expect(rec.textContent).toContain("Root cause:");
    expect(rec.textContent).toContain("E-141");
    expect(rec.textContent).toContain("6-9 months");
    expect(rec.textContent).toContain("Single customer view across 3 cores");
  });

  it("INSUFFICIENT_EVIDENCE state renders the honest tile badge", () => {
    vi.spyOn(queries, "useEntityPlatforms").mockReturnValue(q({
      ...RESP,
      cards: [{ ...CARD, state: "INSUFFICIENT_EVIDENCE" as const }],
    }));
    render(<PlatformPage />);
    expect(screen.getByTestId("fit-tile-salesforce").textContent)
      .toContain("INSUFFICIENT EVIDENCE");
  });

  it("dossier panel renders 3 sections + story + provenance E-ID chip opens drawer", () => {
    const DOSSIER_CARD: PlatformCard = {
      ...CARD,
      story_md: "DocuSign anchors Acme's customer-experience stack today [E-127]. "
        + "The Salesforce platform targets Unified Customer Profile at 1.8/5 "
        + "against a 3.0 peer median [E-047].",
      dossier: {
        readiness_now: {
          light: "amber",
          confirmed_systems: [
            { name: "DocuSign", status: "CONFIRMED", e_ids: ["E-127"], peer_coverage: 0.39 },
          ],
          family_present: [],
          greenfield: true,
          absent_families: ["Salesforce"],
          open_prereqs: [
            { name: "Customer data foundation", required_subcap_id: "P4C1.1.1",
              current: 2.6, threshold: 3.0, status: "PARTIAL" },
          ],
          total_prereqs: 1,
        },
        opportunity: {
          gap_count: 2,
          opportunity_points: 42.6,
          lead_subcap: { name: "Unified Customer Profile", score: 1.8,
                         peer_median: 3.0, e_ids: ["E-047"] },
          next_subcaps: [{ name: "Digital Account Opening", score: 2.2 }],
        },
        why_sequence: { rank: 2, after: ["ncino"] },
      },
      narrative_provenance: [
        { claim: "DocuSign anchors the stack.", source_kind: "techstack", e_ids: ["E-127"] },
      ],
    };
    vi.spyOn(queries, "useEntityPlatforms").mockReturnValue(q({
      ...RESP, cards: [DOSSIER_CARD],
    }));
    render(<PlatformPage />);
    const panel = screen.getByTestId("platform-dossier");
    expect(panel.textContent).toContain("Where they are today");
    expect(panel.textContent).toContain("DocuSign");
    expect(panel.textContent).toContain("Why Salesforce");
    expect(panel.textContent).toContain("Path to ready");
    expect(panel.textContent).toContain("1.8/5 vs 3.0 peer median");
    expect(panel.textContent).toContain("greenfield");
    // provenance/story E-ID chip opens the EvidenceDrawer via the eIds pattern
    const chips = screen.getAllByText("E-047");
    fireEvent.click(chips[0]);
    const s = useUiStore.getState();
    expect(s.activeDrawer).toBe("evidence");
    expect(s.drawerPayload).toMatchObject({ displayId: "acme-0001", eId: "E-047" });
  });

  it("legacy card without dossier renders no dossier panel (additive guard)", () => {
    render(<PlatformPage />);
    expect(screen.queryByTestId("platform-dossier")).toBeNull();
  });

  it("integrate-lens dossier renders the integration badge with the named incumbent", () => {
    // 2026-07-14 skew audit: an absent family whose category is occupied
    // by a third-party incumbent frames as integration, never greenfield.
    const INTEGRATE_CARD: PlatformCard = {
      ...CARD,
      story_md: "Snowflake already anchors that layer [E-127].",
      dossier: {
        readiness_now: {
          light: "amber",
          confirmed_systems: [
            { name: "Snowflake", status: "CONFIRMED", e_ids: ["E-127"], peer_coverage: 0.3 },
          ],
          family_present: [],
          greenfield: false,
          lens: "integrate",
          category_incumbents: ["Snowflake"],
          absent_families: ["Databricks"],
          open_prereqs: [],
          total_prereqs: 0,
        },
        opportunity: {
          gap_count: 1,
          opportunity_points: 30.1,
          lead_subcap: { name: "Data Foundation", score: 1.9,
                         peer_median: 3.0, e_ids: ["E-047"] },
          next_subcaps: [],
        },
        why_sequence: { rank: 2, after: [] },
      },
      narrative_provenance: [],
    };
    vi.spyOn(queries, "useEntityPlatforms").mockReturnValue(q({
      ...RESP, cards: [INTEGRATE_CARD],
    }));
    render(<PlatformPage />);
    const panel = screen.getByTestId("platform-dossier");
    expect(panel.textContent).toContain("integration · Snowflake");
    expect(panel.textContent).not.toContain("greenfield");
  });
});
