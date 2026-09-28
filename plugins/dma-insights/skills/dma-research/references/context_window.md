# Context Window Management (CRITICAL)

Moved out of `SKILL.md` on 28-09-2026 (QA audit F-B04-027: the skill file was over 500 lines, and a file nobody can read in one sitting is a file nobody reads). The SKILL.md reading manifest says which phase reads this.

## Context Window Management (CRITICAL)

| Batch | Max Tokens | Focus |
|-------|-----------|-------|
| 1 | ~4,000 | Entity profile — one line per finding |
| 2 | ~15,000 | P1+P2 evidence — one line per fact |
| 3 | ~15,000 | P3+P4 + tech deep dive |
| 4 | ~8,000 | Workbook generation — code-heavy |
| 5 | ~6,000 | Report — code-heavy |
| 6 | ~4,000 | Appendices + handoff |

**Anti-Bloat Rules:**
1. NEVER narrate what you're about to do — just do it
2. NEVER explain methodology in chat — it's in the reference files
3. Evidence findings: ONE LINE per fact — no paragraphs
4. Batch summaries: MAX 15 lines
5. File generation: go straight to code — no preamble
6. Approaching context limit: CHECKPOINT immediately
7. Reference files: read ONCE at batch start, don't re-read

**Scratchpad-First Pattern (CRITICAL for Batches 2-3):**
Do NOT accumulate evidence findings in chat. Instead:
1. Search → extract facts → append to `evidence_index.json` on disk using this pattern:
   ```python
   import json, os
   EI_PATH = f"{RUN_DIR}/01_evidence/evidence_index.json"
   
   def append_evidence(subcap_id, items):
       """Append evidence for one subcap. Call after scoring each subcap."""
       if os.path.exists(EI_PATH):
           with open(EI_PATH) as f:
               data = json.load(f)
       else:
           data = {"run_id": RUN_ID, "items": []}
       data["items"].extend(items)
       with open(EI_PATH, "w") as f:
           json.dump(data, f, indent=2)
   
   # Call after EACH subcap's searches complete:
   append_evidence("P1C1.1.1", [
       {"evidence_id": "E-001", "source_name": "...", "url": "https://...",
        "tier": "T2", "ers_score": 3.2, "subcap_mappings": ["P1C1.1.1"],
        "facts": [{"fact_id": "F1", "text": "...", "claim_label": "FACT"}],
        "publish_date": "2024-06", "signal_direction": "POSITIVE"}
   ])
   ```
2. Chat output: only print capability-level progress (e.g., "P1C1: 12 facts, 4 subcaps covered")
3. After each CATEGORY: save checkpoint, print coverage stats (3 lines max)
4. This keeps context clean for the next category's searches

If you are printing more than 5 lines of evidence per capability in chat, you are wasting
context. Write to disk, summarize in chat.

**Banned patterns:** "Let me search for..." / "I'll now look into..." / "Based on my
research..." / "Now I'll create..." / "First, I'll..." — Just DO it.

### Cross-Conversation Execution (SUPPORTED)

Batches can run in separate conversations. All state lives in checkpoint files within
`$RUN_DIR/checkpoints/`. On new conversation start:

1. Read this SKILL.md
2. Load the most recent checkpoint from `$RUN_DIR/checkpoints/`
3. Confirm entity name, batch number, and progress with user
4. Proceed from the checkpoint — do NOT re-derive prior batches' output from conversation

When approaching context limits mid-batch, save an emergency checkpoint at the nearest
category boundary and instruct the user to continue in a new conversation.

---
