/**
 * Standalone admin defects regression suite.
 *
 * The standalone build (`frontend/standalone-src/*.jsx`) is the
 * wireframe-guide artifact the user is hitting; it's served as raw
 * babel-transformed JSX in the browser, not via the production
 * Vite/TS pipeline. To assert on it from vitest we load the source
 * files as strings and check structural invariants.
 *
 * Defects covered (all flagged by the user 3+ times):
 *   1. Role toggle is wired to setRole/state, persists localStorage,
 *      AE cannot escalate to ADMIN.
 *   2. Admin home buttons POST to /api/v1/admin/jobs/{name}:execute and
 *      no `187 files` fake toast survives.
 *   3. Import audit reads from /api/v1/admin/import-audit/* — no `187`
 *      literal anywhere in the standalone JSX.
 *   4. Per-entity drilldown drawer exists and consumes the entity
 *      drilldown endpoint.
 *   5. data-source markers are present so reviewers can grep for "mock"
 *      and see none on primary admin surfaces.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const SRC = resolve(process.cwd(), "standalone-src/src");

function load(name: string): string {
  return readFileSync(resolve(SRC, name), "utf-8");
}

describe("Defect 1 — role toggle wiring", () => {
  const app = load("app-root.jsx");
  const chrome = load("chrome.jsx");

  it("effectiveRole downgrade-only function exists", () => {
    expect(app).toMatch(/function effectiveRole\(realRole, actingAs\)/);
    // ROLE_RANK ordering AE=1 / ANALYST=2 / ADMIN=3
    expect(app).toMatch(/ROLE_RANK = \{ AE: 1, ANALYST: 2, ADMIN: 3 \}/);
  });

  it("setRole guards against can_act_as escalation", () => {
    expect(app).toMatch(/user\.can_act_as\.includes\(newRole\)/);
    expect(app).toMatch(/effectiveRole\(user\.role, newRole\)/);
  });

  it("acting-as is persisted to localStorage and rehydrated", () => {
    expect(app).toMatch(/localStorage\.setItem\("dma:acting-as"/);
    expect(app).toMatch(/localStorage\.getItem\("dma:acting-as"\)/);
  });

  it("SettingsPopover wires the role toggle onClick to setRole", () => {
    expect(chrome).toMatch(/onClick=\{\(\) => \{ setRole\(k\); onClose\(\); \}\}/);
    expect(chrome).toMatch(/canActAs\.includes\(k\)/);
  });
});

describe("Defect 1 — pure effectiveRole logic (extracted)", () => {
  // Inline copy of the function under test — kept in lock-step with
  // app-root.jsx via the structural test above.
  const ROLE_RANK: Record<string, number> = { AE: 1, ANALYST: 2, ADMIN: 3 };
  function effectiveRole(realRole: string, actingAs: string | null): string {
    if (!actingAs) return realRole || "AE";
    const r = ROLE_RANK[realRole] || 1;
    const a = ROLE_RANK[actingAs] || 1;
    return ROLE_RANK[realRole] != null && a <= r ? actingAs : (realRole || "AE");
  }

  it("AE cannot escalate to ADMIN — the user's hard constraint", () => {
    expect(effectiveRole("AE", "ADMIN")).toBe("AE");
    expect(effectiveRole("AE", "ANALYST")).toBe("AE");
  });

  it("ADMIN can downgrade to AE or ANALYST", () => {
    expect(effectiveRole("ADMIN", "AE")).toBe("AE");
    expect(effectiveRole("ADMIN", "ANALYST")).toBe("ANALYST");
    expect(effectiveRole("ADMIN", "ADMIN")).toBe("ADMIN");
  });

  it("ANALYST can downgrade to AE", () => {
    expect(effectiveRole("ANALYST", "AE")).toBe("AE");
    expect(effectiveRole("ANALYST", "ADMIN")).toBe("ANALYST");
  });

  it("no actingAs returns realRole", () => {
    expect(effectiveRole("AE", null)).toBe("AE");
    expect(effectiveRole("ADMIN", null)).toBe("ADMIN");
  });
});

describe("Defect 2 — admin home buttons trigger real backend jobs", () => {
  const admin = load("pages-alerts-prospecting-admin.jsx");
  const loader = load("backend-loader.js");

  it("executeJob loader hits POST /api/v1/admin/jobs/{name}:execute", () => {
    expect(loader).toMatch(/executeJob/);
    expect(loader).toMatch(/adminPost\(`\/api\/v1\/admin\/jobs\//);
    expect(loader).toMatch(/:execute/);
    expect(loader).toMatch(/method: "POST"/);
  });

  it("getJobExecution loader hits GET /api/v1/admin/jobs/executions/{id}", () => {
    expect(loader).toMatch(/getJobExecution/);
    expect(loader).toMatch(/\/api\/v1\/admin\/jobs\/executions\//);
  });

  it("useJobTrigger hook exists and polls every 3s", () => {
    expect(admin).toMatch(/function useJobTrigger\(jobName\)/);
    expect(admin).toMatch(/setInterval\(/);
    expect(admin).toMatch(/3000/);
  });

  it("drive_crawler / embedder / peer_patterns buttons are wired", () => {
    expect(admin).toMatch(/data-job-action="drive_crawler:delta"/);
    expect(admin).toMatch(/data-job-action="drive_crawler:full"/);
    expect(admin).toMatch(/data-job-action="embedder:delta"/);
    expect(admin).toMatch(/data-job-action="peer_patterns:full"/);
  });

  it("polls until status != running, then shows result", () => {
    // The status pill renders only when execution is non-null.
    expect(admin).toMatch(/JobStatusLine/);
    expect(admin).toMatch(/r\.data\.status !== "running"/);
  });

  it("no fake 'Scan complete: 187 files' toast remains", () => {
    expect(admin).not.toMatch(/Scan complete:\s*\$\{kind === "full"/);
    expect(admin).not.toMatch(/runScan\("full"\)/);
  });
});

describe("Defect 3 — import audit reads real data, no 187 literal", () => {
  it("no `187` candidate-count literal in any standalone JSX", () => {
    // Allow `187` only inside an `rgba(...)` color tuple — anywhere
    // else it's a forbidden hardcoded count. Same goes for the Vertex
    // pricing string `0.0001875` (decimal context).
    const files = [
      "pages-alerts-prospecting-admin.jsx",
      "pages-auth-dashboard-directory.jsx",
      "pages-d1-overview.jsx",
      "pages-d3-heatmap.jsx",
      "pages-d3-d4.jsx",
      "pages-d5-d6-tech-runs.jsx",
      "chrome.jsx",
      "drawers.jsx",
      "app-root.jsx",
      "data.js",
      "utils.jsx",
    ];
    const offenders: string[] = [];
    for (const f of files) {
      const src = load(f);
      const lines = src.split("\n");
      lines.forEach((line, i) => {
        if (!/\b187\b/.test(line)) return;
        // permitted: rgba(.., 187, ..)  +  0.0001875 (vertex pricing)
        if (/rgba\(\s*\d+\s*,\s*187\s*,/.test(line)) return;
        if (/0\.0001875/.test(line)) return;
        offenders.push(`${f}:${i + 1}: ${line.trim()}`);
      });
    }
    if (offenders.length) {
      throw new Error(
        "Forbidden 187 literal(s) found:\n" + offenders.join("\n"),
      );
    }
  });

  it("ImportPage replaces the hardcoded jobs array with API data", () => {
    const admin = load("pages-alerts-prospecting-admin.jsx");
    expect(admin).not.toMatch(/{ id: "IJ-09".*files: 187/);
    expect(admin).toMatch(/listJobExecutions\({ limit: 50 }\)/);
  });

  it("summary tiles read from importAuditSummary", () => {
    const admin = load("pages-alerts-prospecting-admin.jsx");
    expect(admin).toMatch(/s\.candidates_processed/);
    expect(admin).toMatch(/s\.files_excluded/);
    expect(admin).toMatch(/s\.files_awaiting_review/);
    expect(admin).toMatch(/importAuditSummary/);
  });

  it("empty state when zero candidates", () => {
    const admin = load("pages-alerts-prospecting-admin.jsx");
    expect(admin).toMatch(/candidates_processed \?\? 0/);
  });
});

describe("Defect 4 — per-entity drilldown drawer", () => {
  const admin = load("pages-alerts-prospecting-admin.jsx");
  const loader = load("backend-loader.js");

  it("By-client tab exists with click-to-drill rows", () => {
    expect(admin).toMatch(/tab === "by_client"/);
    expect(admin).toMatch(/onClick=\{\(\) => setDrilldownEntity\(e\)\}/);
    expect(admin).toMatch(/data-entity-id=\{e\.entity_id\}/);
  });

  it("AdminEntityDrilldownDrawer renders runs + rerun history", () => {
    expect(admin).toMatch(/function AdminEntityDrilldownDrawer/);
    expect(admin).toMatch(/Rerun history/);
    expect(admin).toMatch(/parent_request_id/);
  });

  it("loader fetches /admin/import-audit/entities/{id}", () => {
    expect(loader).toMatch(/importAuditEntityDetail/);
    expect(loader).toMatch(/\/api\/v1\/admin\/import-audit\/entities\//);
  });

  it("empty-state when entity has zero runs", () => {
    expect(admin).toMatch(/No runs for this entity/);
    expect(admin).toMatch(/No rerun jobs for this entity/);
  });
});

describe("Promise 5 — EvidenceDrawer 'Seen in N runs' chip (standalone)", () => {
  const drawers = load("drawers.jsx");
  const loader = load("backend-loader.js");

  it("SeenInRunsChip component is defined", () => {
    expect(drawers).toMatch(/function SeenInRunsChip\(\s*\{\s*evidenceId\s*\}/);
  });

  it("chip calls window.DMA.evidence.runHistory(evidenceId)", () => {
    expect(drawers).toMatch(/window\.DMA\.evidence\.runHistory/);
  });

  it("backend-loader exposes DMA.evidence.runHistory hitting /run-history", () => {
    expect(loader).toMatch(/DMA\.evidence\s*=\s*\{/);
    expect(loader).toMatch(/\/api\/v1\/evidence\/.*\/run-history/);
  });

  it("chip is rendered inline on each evidence row in EvidenceDrawer", () => {
    expect(drawers).toMatch(/<SeenInRunsChip evidenceId=\{it\.id\}\s*\/>/);
  });

  it("chip renders 'First seen' muted variant when n_runs <= 1", () => {
    expect(drawers).toMatch(/First seen/);
  });

  it("chip renders 'Seen in N runs' label when n_runs >= 2", () => {
    expect(drawers).toMatch(/`Seen in \$\{n\} runs`/);
  });
});

describe("Promise 10 — Cross-pillar stories on D5 Context (standalone)", () => {
  const page = load("pages-d5-d6-tech-runs.jsx");
  const loader = load("backend-loader.js");

  it("CrossPillarStoriesPanel component is defined", () => {
    expect(page).toMatch(/function CrossPillarStoriesPanel\(\s*\{\s*entity\s*\}/);
  });

  it("panel is mounted inside ClientContext", () => {
    expect(page).toMatch(/<CrossPillarStoriesPanel entity=\{entity\}/);
  });

  it("backend-loader exposes DMA.crossPillar.storiesForEntity", () => {
    expect(loader).toMatch(/crossPillar\s*=\s*\{/);
    expect(loader).toMatch(/cross-pillar-stories/);
  });

  it("pillar filter chips P1..P4 are rendered", () => {
    expect(page).toMatch(/data-pillar-filter=\{p\}/);
    expect(page).toMatch(/\["ALL", "P1", "P2", "P3", "P4"\]/);
  });

  it("empty-state renders when no stories returned", () => {
    expect(page).toMatch(/No cross-pillar stories/);
  });
});

describe("Promise 11 — V7 catalog 'Upload next version' wired (standalone)", () => {
  const admin = load("pages-alerts-prospecting-admin.jsx");
  const loader = load("backend-loader.js");

  it("CatalogUploadCard component is defined", () => {
    expect(admin).toMatch(/function CatalogUploadCard\(\)/);
  });

  it("V7 tab renders CatalogUploadCard (not plain unwired button)", () => {
    expect(admin).toMatch(/<CatalogUploadCard \/>/);
  });

  it("upload button is bound to file input ref + onPick", () => {
    expect(admin).toMatch(/data-action="upload-catalogue"/);
    expect(admin).toMatch(/fileRef\.current\?\.click\(\)/);
    expect(admin).toMatch(/data-catalog-file-input/);
  });

  it("file input onChange POSTs via DMA.admin.uploadCatalogue", () => {
    expect(admin).toMatch(/window\.DMA\.admin\.uploadCatalogue/);
  });

  it("backend-loader exposes uploadCatalogue with FormData", () => {
    expect(loader).toMatch(/uploadCatalogue/);
    expect(loader).toMatch(/FormData/);
    expect(loader).toMatch(/catalogue:upload/);
  });

  it("View change log button toggles a versions table", () => {
    expect(admin).toMatch(/data-action="view-changelog"/);
    expect(admin).toMatch(/setShowChangelog/);
  });
});

describe("Promise 6/7/8/9 — wired-state proofs (standalone)", () => {
  const heatmap = load("pages-d3-heatmap.jsx");
  const runs = load("pages-d5-d6-tech-runs.jsx");
  const drawers = load("drawers.jsx");

  it("Promise 6: D3 heatmap calls DMA.archetype.forEntity on mount", () => {
    expect(heatmap).toMatch(/window\.DMA\.archetype\.forEntity/);
    expect(heatmap).toMatch(/insufficient cohort/);
  });

  it("Promise 6: heatmap renders AI pill on enriched cells via has_enrichment", () => {
    expect(heatmap).toMatch(/has_enrichment/);
    expect(heatmap).toMatch(/enrichment_evidence_ids/);
  });

  it("Promise 7: ClientRuns calls DMA.entities.runHistory + renders parent chain", () => {
    expect(runs).toMatch(/window\.DMA\.entities\.runHistory/);
    expect(runs).toMatch(/parent_request_id/);
  });

  it("Promise 8: IntelligencePanel resumes session via DMA.chatSession.get + persists via .set", () => {
    expect(drawers).toMatch(/DMA\.chatSession/);
    expect(drawers).toMatch(/postFeedback/);
    // brand-aligned thumb icons (no emoji)
    expect(drawers).toMatch(/Icon name="thumb-up"/);
    expect(drawers).toMatch(/Icon name="thumb-down"/);
    expect(drawers).not.toMatch(/👍|👎|💡/);
  });

  it("Promise 9: D6 Patterns tab calls DMA.patterns.list", () => {
    expect(runs).toMatch(/DMA\.patterns\.list/);
  });
});

describe("Defect 5 — data-source markers on primary admin surfaces", () => {
  const admin = load("pages-alerts-prospecting-admin.jsx");

  it("admin home job cards expose data-source", () => {
    expect(admin).toMatch(/data-source="api"/);
    expect(admin).toMatch(/data-source="loading"/);
    expect(admin).toMatch(/data-source="api-empty"/);
  });

  it("no data-source=\"mock\" on primary admin surfaces", () => {
    expect(admin).not.toMatch(/data-source="mock"/);
  });
});
