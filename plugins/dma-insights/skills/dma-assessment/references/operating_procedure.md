# operating procedure

Moved out of `SKILL.md` on 28-09-2026 (QA audit F-B04-027: the skill file was over 500 lines, and a file nobody can read in one sitting is a file nobody reads). The SKILL.md reading manifest says which phase reads this.

## Context Window Management (CRITICAL)

| Phase | Max Tokens | Focus |
|-------|-----------|-------|
| 0 | ~2,000 | Setup, parameter lock |
| 1 | ~20,000 | Evidence collection |
| 2 | ~8,000 | Peer scoring — batch by peer |
| 3 | ~3,000 | Issue register |
| 4 | ~25,000 | Scoring — code-heavy |
| 4.5 | ~8,000 | Critic pass — table format |
| 5 | ~4,000 | Analysis — computed output |
| 6 | ~6,000 | Recommendations — structured |
| 7 | ~15,000 | Deliverables — code-heavy |
| 8 | ~4,000 | QA — script + computed verdict |

**Anti-Bloat Rules:**
1. Go straight to code/action — no "Let me now..." or "I'll proceed to..."
2. Phase gate acknowledgments: MAX 5 lines
3. Scoring rationales go in workbook, NOT in chat — chat gets summary stats only
4. Workbook/report generation: output code blocks only — no explanatory prose
5. Checkpoint BEFORE context limit — don't try to squeeze more in

**Scratchpad-First Scoring (CRITICAL for Phase 4):**
Do NOT score subcaps in chat prose. Instead:
1. Load evidence for ONE capability at a time (see Evidence Loading below)
2. Score all subcaps in that capability → write rows directly to a JSON scratchpad file
   on disk: `$DMA_ROOT/checkpoints/scoring_scratchpad.json`
3. Chat output: ONLY print capability summary (e.g., "P1C1: 8 subcaps scored, range 1.5-3.0, 3 caps applied")
4. After each PILLAR: save checkpoint, print pillar stats (5 lines max)
5. After ALL pillars: run a Python script to convert scratchpad JSON → XLSX workbook with
   ALL 11 sheets (P1-P4_Subcap_Scoring, Executive_Summary, Pillar_Summary, Category_Detail,
   Evidence_Master, Peer_Benchmarks, Recommendations, Run_Metadata)

**Why this matters:** If you try to score 700+ subcaps in chat, you WILL exhaust context.
The scratchpad pattern keeps context for the CURRENT capability only (~5-12 subcaps), while
all previous scores are safely on disk. The final workbook is built from the scratchpad
in one code block — guaranteeing all tabs exist and all data is included.

**If chat stalls or requires "continue":** You are printing too much in chat. Write to disk,
summarize in chat. The user should not need to press "continue" during normal scoring.

### Cross-Conversation Execution (SUPPORTED)

Each phase can run in a separate conversation. All state lives in checkpoint files — prior
conversation context is NOT required. On new conversation start:

1. Read this SKILL.md
2. Load the most recent checkpoint from `$DMA_ROOT/checkpoints/`
3. Confirm parameters and current phase with user
4. Proceed from the checkpoint — do NOT re-derive prior phases' output from conversation

This is the primary mechanism for managing long assessments without context overflow. When
approaching context limits mid-phase, save a checkpoint at the nearest category boundary
and instruct the user to continue in a new conversation.

---

## Memory, Batching & Caching

**Checkpoint files** saved to `$DMA_ROOT/checkpoints/` after each phase:

| Phase | File | Contents |
|-------|------|----------|
| 0 | `00_parameters.json` | Institution, SV, size, mode, docs |
| 1 | `01_evidence_index.json` | All evidence with IDs, tiers, facts |
| 2 | `02_peer_benchmarks.json` | Peers, scores, benchmarks |
| 3 | `03_issue_register.json` | Issues, severity, caps |
| 4 | `04_scores.json` + Workbook XLSX | All subcap scores + rationales |
| 5 | `05_priorities.json` | Priority scores, ranked |
| 6 | `06_recommendations.json` | Full argument structures |

**On resume:** Check checkpoints/ first. Confirm resume vs. fresh start.

**Batching:** Evidence by pillar→save. Peers one at a time→save. Scoring by pillar (Pass 1)→save→Pass 2 cross-pillar. Report section by section.

**Caching:** Evidence=immutable once collected. Peers=immutable. Scores=mutable (cap changes invalidate downstream). Internal docs=read-once→index. Calculation traces=cacheable, trace forward on change.

**Evidence Loading During Scoring (CRITICAL for context management):**

During Phase 4, NEVER load the full evidence index into context. Instead, load evidence
one CAPABILITY at a time using a targeted extraction:

```python
import json
data = json.load(open(f'{DMA_ROOT}/checkpoints/01_evidence_index.json'))
cap_evidence = [e for e in data['items'] if any(
    s.startswith('P1C1.1') for s in e.get('subcap_mappings', [])
)]
```

Score all subcaps in that capability, write results to the workbook, then discard the
evidence slice and load the next capability. A capability typically contains 5-12 subcaps
worth of evidence (~2-5K tokens), which is manageable. This preserves the ability to see
all evidence for related subcaps together while keeping the context footprint bounded.

---

## Output Directory Taxonomy (MANDATORY)

```
{DMA_ROOT}/                         # DMA-ASM-{INST}-{DATE}-{SEQ}
├── run_manifest.json
├── 00_setup/
├── 01_evidence/
├── 02_peers/
├── 03_issues/
├── 04_scoring/
│   ├── Workbook.xlsx
│   ├── caps_applied_log.csv
│   ├── contradiction_log.csv
│   ├── reasoning_chain_log.json
│   └── exports/                    # Canonical export layer
├── 05_analysis/
├── 06_recommendations/
├── 07_deliverables/
│   ├── Report.docx
│   └── charts/
├── 08_qa/
│   ├── qa_verdict.json
│   └── qa_findings_register.csv
├── governance/                     # Layer 2 handoff
└── checkpoints/
```

**Run ID:** `DMA-ASM-{INST_CODE}-{YYYYMMDD}-{SEQ}`
**Provenance:** Every artifact references run_id. CSVs: header comment. Workbook: Run_Metadata sheet. Charts: footer. Mismatch = build fails.
**Clean build:** Never reuse from different RUN_ID.

---
