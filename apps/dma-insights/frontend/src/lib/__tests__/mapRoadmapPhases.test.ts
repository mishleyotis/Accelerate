/**
 * mapRoadmapPhases — backend /platforms/roadmap → TransformationRoadmap phases.
 */
import { describe, expect, it } from "vitest";
import { mapRoadmapPhases, type PlatformRoadmapResponse } from "@/lib/queries";

const RESP: PlatformRoadmapResponse = {
  entity_display_id: "e1",
  run_request_id: "REQ-1",
  total_duration_months: 12,
  phases: [
    {
      phase: 1, name: "Data foundation", duration_months: 6,
      recommendations: [
        { rec_id: "REC-1", title: "Lakehouse", platform_id: "databricks", platform_name: "Databricks", maturity_lift: "+0.6" },
        { rec_id: "REC-2", title: "Integrations", platform_id: "mulesoft", platform_name: "MuleSoft", maturity_lift: null },
      ],
    },
    {
      phase: 2, name: "Rollout", duration_months: 6,
      recommendations: [
        { rec_id: "REC-3", title: "FSC", platform_id: "salesforce", platform_name: "Salesforce", maturity_lift: null },
      ],
    },
  ],
};

describe("mapRoadmapPhases", () => {
  it("returns [] for empty/undefined", () => {
    expect(mapRoadmapPhases(undefined)).toEqual([]);
    expect(mapRoadmapPhases({ ...RESP, phases: [] })).toEqual([]);
  });

  it("maps phases with label/duration/platforms/rec_ids", () => {
    const out = mapRoadmapPhases(RESP);
    expect(out).toHaveLength(2);
    expect(out[0]).toMatchObject({
      phase: 1, label: "Data foundation", duration: "6 mo",
      platform: "Databricks · MuleSoft",
      target: "Maturity +0.6",
      metric: "Lakehouse",
      rec_ids: ["REC-1", "REC-2"],
    });
    expect(out[0].customer_impact).toEqual({ "Maturity lift": "+0.6" });
  });

  it("falls back to '—' target + rec count metric when data is sparse", () => {
    const out = mapRoadmapPhases({
      ...RESP,
      phases: [{ phase: 1, name: "P", duration_months: 3, recommendations: [{ rec_id: "R", title: "", platform_id: "", platform_name: "", maturity_lift: null }] }],
    });
    expect(out[0].target).toBe("—");
    expect(out[0].platform).toBe("—");
    expect(out[0].metric).toBe("1 recommendation(s)");
  });

  it("Part 7.3: real server per-phase fields win over the client derivation", () => {
    const out = mapRoadmapPhases({
      ...RESP,
      phases: [{
        phase: 1, name: "Quick Wins", duration_months: 6,
        label: "Foundation",
        target: "M2 → M3 in P4C1",
        metric: "Loan origination cycle -40%",
        platform: "SF Data Cloud + nCino",
        customer_impact: { "Loan cycle": "-40%", "STP rate": "+25pt" },
        dependencies: ["REC-00"],
        recommendations: [
          { rec_id: "REC-1", title: "Lakehouse", platform_id: "databricks",
            platform_name: "Databricks", maturity_lift: "+0.6" },
        ],
      }],
    });
    expect(out[0]).toMatchObject({
      label: "Foundation",
      target: "M2 → M3 in P4C1",
      metric: "Loan origination cycle -40%",
      platform: "SF Data Cloud + nCino",
      dependencies: ["REC-00"],
    });
    // Real customer_impact replaces the maturity-lift synthesis.
    expect(out[0].customer_impact).toEqual({ "Loan cycle": "-40%", "STP rate": "+25pt" });
  });

  it("Part 7.3: per-rec outcome metric beats the rec-title-as-metric fallback", () => {
    const out = mapRoadmapPhases({
      ...RESP,
      phases: [{
        phase: 1, name: "P", duration_months: 3,
        recommendations: [
          { rec_id: "R1", title: "A title, not a metric", platform_id: "",
            platform_name: "", maturity_lift: null, metric: "Branch deflection +18pts" },
        ],
      }],
    });
    expect(out[0].metric).toBe("Branch deflection +18pts");
  });
});
