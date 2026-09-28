# Batch Execution Protocol

Moved out of `SKILL.md` on 28-09-2026 (QA audit F-B04-027: the skill file was over 500 lines, and a file nobody can read in one sitting is a file nobody reads). The SKILL.md reading manifest says which phase reads this.

## Batch Execution Protocol

6 batches × up to 851 subcaps × 3-5 searches/subcap = 2,500-4,200 web searches + Moody's enrichment + 100-300 web_fetches.
Each subcap gets its OWN 3-5 queries derived from its diagnostic question.
Shared document mining (annual reports, 10-Ks) supplements but does NOT replace per-subcap searches.
Complete batch → HANDOFF SUMMARY → STOP → wait for "continue."

When user says "continue": find most recent HANDOFF → resume next batch. NEVER restart.

### Batch 1: ENTITY PROFILING, CLASSIFICATION & PEER SELECTION
Follow Dual-Source Research Protocol (web_search FIRST, then Moody's, then regulatory).
1. Entity identity + website → 2. Regulatory search → 3. Financial metrics (3-5yr T1/T2)
→ 4. Subvertical classification → 5. Issues & enforcement → 6. Sentiment
→ 7. **PEER SET SELECTION** → 8. PARAMETER LOCK

**Step 7 — Peer Set Selection & Lock (NEW):**
Select 3-5 peers based on: sub-vertical match, size tier proximity, geographic overlap,
competitive relevance. For each peer, document:
- peer_name, size_tier, key_metric (assets, revenue or AUM)
- geography, overlap_pct, selection_rationale
Save to `00_entity_profile/peer_set.json`.
**Peer set is IMMUTABLE after Batch 1.** Assessment skill inherits this set unchanged.

**Output:** Compact findings. **Stop:** "--- BATCH 1 COMPLETE ---"

### Batch 2: P1 + P2 SUBCAP-LEVEL RESEARCH
**READ `references/deep_search_protocol.md` FIRST — it defines the query tier system.**
Follow Dual-Source Research Protocol: web_search FIRST (≥70%), then Moody's enrichment.

**Execute this EXACT loop for P1, then repeat for P2:**
```
FOR each category in pillar (e.g., P1C1, P1C2, P1C3...):
  FOR each capability in category (e.g., P1C1.1, P1C1.2...):
    subcaps = extract_subcaps(capability)  # from Pillar XLSX Column H
    
    # Step A: Fetch shared rich documents ONCE per capability
    rich_docs = web_fetch(annual_report, 10K, proxy_statement)  # if not already fetched
    shared_facts = extract_all_facts(rich_docs)  # map facts to ALL subcaps they apply to
    
    FOR each subcap in subcaps (e.g., P1C1.1.1, P1C1.1.2, P1C1.1.3...):
      diagnostic_q = subcap.column_H
      
      # Step B: Run 3-5 SUBCAP-SPECIFIC searches derived from THIS diagnostic Q
      queries = decompose_diagnostic_q(diagnostic_q, entity_name)  # 3-5 unique queries
      results = []
      for q in queries:
        results += web_search(q)
        results += moodys_search(q)  # if applicable
      
      # Step C: Combine shared_facts relevant to THIS subcap + subcap-specific results
      subcap_evidence = shared_facts.filter(subcap.id) + results
      
      # Step D: Proxy escalation if evidence is thin
      IF len(subcap_evidence) < 3:
        proxy_queries = generate_proxy_queries(subcap, entity_name)  # Tiers 7-10
        subcap_evidence += execute_searches(proxy_queries)
      
      # Step E: Write to disk immediately (NOT to chat)
      append_to_evidence_index(subcap.id, subcap_evidence)
    
    # Checkpoint after each capability
    save_checkpoint(capability.id, evidence_count)
    print(f"{capability.id}: {len(subcaps)} subcaps, {evidence_count} items")  # 1 line
  
  # Checkpoint after each category
  save_category_checkpoint(category.id)
  print(f"--- {category.id} complete: {coverage}% coverage ---")  # 1 line
```

**The agent MUST execute this loop literally.** "For each subcap" means opening each
subcap's diagnostic question and generating queries specific to THAT question.
If you are running fewer searches than `(number_of_subcaps × 3)`, you are not
executing the loop — you are batching at category level.

For HYBRID/INTERNAL: Load internal evidence FIRST per Internal Evidence Integration Protocol.
**Stop:** "--- BATCH 2 COMPLETE ---"

### Batch 3: P3 + P4 + TECH DEEP DIVE
**READ `references/deep_search_protocol.md` if not already loaded this conversation.**
Follow Dual-Source Research Protocol: web_search FIRST (≥70%), then Moody's enrichment.

**Execute the SAME subcap-by-subcap loop as Batch 2, for P3 then P4.**
P4 adds utilization analysis per `references/tech_discovery.md`:
- After finding tech evidence, search separately for UTILIZATION evidence
- Presence ≠ utilization. "Uses Salesforce" ≠ "Uses Salesforce effectively"
- Flag utilization uncertainty on every tech finding

→ After P4 subcaps: tech stack discovery → org capability proxies.
For HYBRID/INTERNAL: Load internal evidence FIRST per Internal Evidence Integration Protocol.
**Stop:** "--- BATCH 3 COMPLETE ---"

### Batch 4: CONSOLIDATION — the workbook is already populated

There is NO population step. Every evidence item, search, synthesis and declared absence
went into the run's ONE workbook as it was found (`engine.cli evidence / search / synthesise /
absence`, Step 4 above); a batch that "builds the workbook" at the end is the defect the
retired `scripts/populate_workbook.py` produced — a second, differently-shaped workbook beside
the run. That retired script and the retired `scripts/validate_workbook.py` (it validated the
22-column layout the engine replaced) both refuse and name the engine commands.

Batch 4 is the close-out, in this order, every command refusing on its own terms:
1. `engine.cli gate --run <R> --root <ROOT> --category <CAT> --require-synthesis` for every
   category in scope — the floors gate (five volleys + primary question fired, ≥20 items per
   category, every evidenced cell synthesised and independently challenged, every empty cell
   DECLARED through `engine.cli absence` with an enrichment connector in its Search_Log).
2. `engine.cli validate --run <R> --root <ROOT>` — shape against `engine/contract.py`,
   vocabularies, cross-references, rule 8 (no absence flag without its Provenance row).
3. `engine.cli ers recompute --run <R> --root <ROOT>` — ERS is computed, never typed.
4. `engine.cli complete check --run <R> --root <ROOT>` — every tab filled or its emptiness
   declared with a reason (`engine.cli complete declare`), never silently blank.
5. `engine.cli handoff --run <R> --root <ROOT>` — the research handoff the scoring stage and
   the strip read; `engine.cli strip` refuses until the handoff carries the working area.

**Rationale format (Column J at the scoring stage; the research columns L–AG carry the
synthesis):** `[ERS: X.XX] [CLAIM_TYPE] [E-xxx:Fy] Source (Tier, Recency): Finding.`
**Stop:** "--- BATCH 4 COMPLETE ---"

### Batch 5: RESEARCH REPORT (Client Profile)

**Template is MANDATORY — NO deviation.**

1. Read the `docx` skill FIRST (invoke it by name; do not hardcode a path to it)
2. **Retrieve `DMA_Client_Profile_Research_Template.docx` from the project knowledge base.**
   This is the ONLY acceptable report structure. Do NOT create ad hoc layouts.
3. Execute PRE-WRITE PROTOCOL before writing ANY section:
   ```
   a. WHAT DATA is relevant for this entity? (Load evidence, count items, identify patterns)
   b. WHY is it important to a Sales Account Executive? (Business impact, risk, opportunity)
   c. WHAT is the implication to Zennify? (Which of the 12 Zennify solutions apply and why?)
   ```
4. Fill template sections in order:
   - Section 1 (Executive Summary): Entity snapshot, top findings WITH Zennify relevance column, critical gaps
   - Section 2 (Entity Profile): Corporate identity, scale metrics, regulatory standing, business composition
   - Section 3 (Market Position): **Peer set from Batch 1 (LOCKED)**, financial trajectory, digital evolution timeline, sentiment
   - Section 4 (Strategic Intelligence): Insight Cards using WHAT/WHY/SO WHAT structure, tech landscape, leadership overview
   - Section 5 (Risk & Issues): Issue register with timeline, negative search results, assumptions register
   - Appendix A (Assessment Quality): Evidence summary, capability coverage map, safeguard gates
   - Appendix B (Handoff Package): Parameter lock, priority/caution capabilities, cap triggers, internal evidence request
   - Appendix C (Metadata): Assessment ID, evidence mode, search log, audit trail
5. **Assessment ID and Evidence Mode on cover page, header, and Appendix C MUST match run_manifest.json**
6. **Analyze → Synthesize → Write.** Do NOT just list facts. For every insight: what does the data MEAN for this institution?

**Stop:** "--- BATCH 5 COMPLETE ---"

### Batch 6: APPENDIX & HANDOFF
CSVs (A2,A7-A9) + VIZ PNGs + research_handoff.json. **Stop:** "--- RESEARCH COMPLETE ---"

### Handoff Summary Template (MAX 15 lines)
```
=== BATCH [N] HANDOFF ===
Entity: [Name] | Classification: [SV]
Assessment ID: [RUN_ID] | Evidence Mode: [PUBLIC/INTERNAL/HYBRID]
Evidence: E-001–E-[XXX] | Subcaps: [N]/[SELECTED] ([X]%)
Coverage: [N] ≥3, [M] thin, [P] none | Claims: [F/I/H/CE counts]
Tech: [N] total, [M] Zennify-priority | Gates: [N] PASS, [M] FAIL
Peers (LOCKED): [Peer1, Peer2, Peer3, ...]
Key findings: [5 bullets max]
Next: Batch [N+1] | Inputs: [what's needed]
=== END ===
```

### Emergency Checkpoint
```
--- CHECKPOINT: Batch [N], Step [X], Category [P#C#].
Completed: [N] subcaps, [M] evidence. Remaining: [list].
CONTINUE to resume from [subcap ID]. ---
```

---
