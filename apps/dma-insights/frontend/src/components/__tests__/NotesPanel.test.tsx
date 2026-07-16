/**
 * NotesPanel — AE-notes segment on rec-card / roadmap drilldowns
 * (migration 057 feature).
 *
 * Pins:
 *   - notes list renders author identity, role/status badges, body;
 *   - the add-note form posts target scoping + recalibrate flag;
 *   - CUSTOMER role sees no add form (internal-only writes);
 *   - recalibration chip: SIMULATED is expandable, FAILED renders the
 *     honest "did not pass validation" line instead of raw output;
 *   - RecommendationModal exposes the "AE notes" tab (internal) and
 *     hides it for the customer audience;
 *   - authorInitials pure helper.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NotesPanel } from "../NotesPanel";
import { RecommendationModal } from "../RecommendationModal";
import * as notesLib from "@/lib/notes";
import * as recs from "@/lib/recommendations";
import * as entityRecs from "@/lib/entityRecommendations";
import * as queries from "@/lib/queries";
import * as authStore from "@/store/auth";
import { useUiStore } from "@/store/ui";
import { authorInitials, type AeNote } from "@/lib/notes";
import type { RecommendationDetail } from "@/lib/recommendations";

const NOTE: AeNote = {
  id: "n1",
  target_kind: "recommendation",
  target_id: "REC-08",
  author_email: "mishley.otiende@zennify.com",
  author_role: "AE",
  status: "PENDING",
  body: "Client confirmed the nCino go-live slipped to Q4.",
  sf_opp_id: "OPP-1234",
  recalibrate: false,
  created_at: "2026-07-06T10:00:00Z",
  assessment_status: null,
};

function mkNotesQ(items: AeNote[]) {
  return {
    data: { entity_display_id: "fce-001", items },
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof notesLib.useEntityNotes>;
}

const mutateMock = vi.fn();

beforeEach(() => {
  vi.restoreAllMocks();
  mutateMock.mockReset();
  vi.spyOn(notesLib, "useEntityNotes").mockReturnValue(mkNotesQ([NOTE]));
  vi.spyOn(notesLib, "useCreateNote").mockReturnValue({
    mutate: mutateMock, isPending: false, isError: false, error: null,
  } as unknown as ReturnType<typeof notesLib.useCreateNote>);
  vi.spyOn(notesLib, "useNoteAssessment").mockReturnValue({
    data: undefined, isLoading: false, error: null,
  } as unknown as ReturnType<typeof notesLib.useNoteAssessment>);
  vi.spyOn(authStore, "useEffectiveRole").mockReturnValue("AE");
});

describe("NotesPanel", () => {
  it("renders note rows with author identity and badges", () => {
    render(<NotesPanel displayId="fce-001" targetKind="recommendation" targetId="REC-08" />);
    expect(screen.getByText("mishley.otiende@zennify.com")).toBeTruthy();
    expect(screen.getByText("AE")).toBeTruthy();
    // "PENDING" also exists as a <select> option in the add form — assert
    // the badge inside the note row specifically.
    const row = screen.getByTestId("ae-note-row");
    expect(row.textContent).toContain("PENDING");
    expect(screen.getByText(/nCino go-live slipped to Q4/)).toBeTruthy();
    expect(screen.getByText("OPP-1234")).toBeTruthy();
    expect(screen.getByText("MO")).toBeTruthy(); // initials avatar
  });

  it("posts the note with target scoping + recalibrate flag", () => {
    render(<NotesPanel displayId="fce-001" targetKind="recommendation" targetId="REC-08" />);
    fireEvent.change(screen.getByLabelText(/Add a note/i), {
      target: { value: "They finished the CDP rollout." },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /Save note/i }));
    expect(mutateMock).toHaveBeenCalledTimes(1);
    expect(mutateMock.mock.calls[0][0]).toEqual({
      target_kind: "recommendation",
      target_id: "REC-08",
      body: "They finished the CDP rollout.",
      status: "PENDING",
      sf_opp_id: null,
      recalibrate: true,
    });
  });

  it("CUSTOMER role gets no add form", () => {
    vi.spyOn(authStore, "useEffectiveRole").mockReturnValue("CUSTOMER");
    render(<NotesPanel displayId="fce-001" targetKind="recommendation" targetId="REC-08" />);
    expect(screen.queryByLabelText(/Add a note/i)).toBeNull();
    // Existing notes still listed (panel itself is audience-gated upstream).
    expect(screen.getByText(/nCino go-live slipped/)).toBeTruthy();
  });

  it("SIMULATED recalibration chip expands to the validated assessment", () => {
    vi.spyOn(notesLib, "useEntityNotes").mockReturnValue(
      mkNotesQ([{ ...NOTE, recalibrate: true, assessment_status: "SIMULATED" }]),
    );
    vi.spyOn(notesLib, "useNoteAssessment").mockReturnValue({
      data: {
        id: "a1", note_id: "n1", status: "SIMULATED",
        assessment_md: "**Simulated impact** — P3C1.1.1 direction up.",
        impact: {}, model: "gemini-flash",
        grounding_evidence_ids: ["E-047"], validators_passed: true,
        failure_reason: null, created_at: "2026-07-06T10:05:00Z",
      },
      isLoading: false, error: null,
    } as unknown as ReturnType<typeof notesLib.useNoteAssessment>);
    render(<NotesPanel displayId="fce-001" targetKind="recommendation" targetId="REC-08" />);
    const chip = screen.getByTestId("recalibration-chip");
    expect(chip.textContent).toContain("awaiting admin review");
    fireEvent.click(chip);
    const md = screen.getByTestId("assessment-md");
    expect(md.textContent).toContain("Simulated impact");
    expect(md.textContent).toContain("E-047");
    expect(md.textContent).toContain("gemini-flash");
  });

  it("FAILED simulation renders the honest validation line, never raw output", () => {
    vi.spyOn(notesLib, "useEntityNotes").mockReturnValue(
      mkNotesQ([{ ...NOTE, recalibrate: true, assessment_status: "FAILED" }]),
    );
    render(<NotesPanel displayId="fce-001" targetKind="recommendation" targetId="REC-08" />);
    const chip = screen.getByTestId("recalibration-chip");
    expect(chip.textContent).toContain("rejected by validators");
    // FAILED is not expandable — no assessment body can appear.
    fireEvent.click(chip);
    expect(screen.queryByTestId("assessment-md")).toBeNull();
  });
});

describe("RecommendationModal AE-notes tab", () => {
  const baseData: RecommendationDetail = {
    id: "r1", rec_id: "REC-08", title: "Adopt nCino",
    description: "Replaces 14 manual steps.", entity_display_id: "fce-001",
    target_subcap_ids: [], platform_id: "ncino", addressable_offerings: [],
    uplift_per_pillar: null, effort_band: "large",
    cited_features: [], cited_constructs: [], cited_agents: [],
    unresolved_count: 0, catalogue_version: "v7.0",
    dependencies: { prerequisites: [], unlocks: [] },
  };

  beforeEach(() => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue({
      data: baseData, isLoading: false, isError: false, error: null,
    } as unknown as ReturnType<typeof recs.useRecommendationDetail>);
    vi.spyOn(entityRecs, "useEntityRecommendations").mockReturnValue({
      data: [],
    } as unknown as ReturnType<typeof entityRecs.useEntityRecommendations>);
    vi.spyOn(queries, "useEntityOverview").mockReturnValue({
      data: { pillar_scores: [] }, isLoading: false, error: null,
    } as unknown as ReturnType<typeof queries.useEntityOverview>);
    useUiStore.setState({ audience: "internal" });
  });

  it("shows the AE notes tab internally and mounts the panel", () => {
    render(
      <RecommendationModal open onClose={() => undefined}
                           recommendationId="r1" displayId="fce-001" />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "AE notes" }));
    expect(screen.getByTestId("ae-notes-panel")).toBeTruthy();
  });

  it("hides the AE notes tab for the customer audience", () => {
    useUiStore.setState({ audience: "customer" });
    render(
      <RecommendationModal open onClose={() => undefined}
                           recommendationId="r1" displayId="fce-001" />,
    );
    expect(screen.queryByRole("tab", { name: "AE notes" })).toBeNull();
  });
});

describe("authorInitials", () => {
  it("derives initials from the email local part", () => {
    expect(authorInitials("mishley.otiende@zennify.com")).toBe("MO");
    expect(authorInitials("sam@zennify.com")).toBe("SA");
    expect(authorInitials("")).toBe("?");
  });
});
