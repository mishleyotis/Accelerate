# Deliverable 6 — what shipping `dma-research` v4.2 into the plugin costs

**Headline: the reasoning rigour the owner wants is UNSHIPPED, not MISSING.** It is built,
it validates clean, and packaging is not the obstacle.

## What is actually there (measured on `/tmp/dmar/dma-research`)

| | Installed (`plugins/dma-insights/skills/dma-research/`) | Supplied v4.2 |
|---|---|---|
| Version banner / CHANGELOG | v2.3 / — | **SKILL.md says v3.0, CHANGELOG says v4.2** |
| Files (excl. `__pycache__`) | 26 | **94** |
| `kg/` | absent | **7.1 MB**: 16 category packs, semantic index, SV binder, source catalog |
| Briefs | — | **851, five-facet histogram `{5: 851}`, 4,255 DQ rows, 0 yes/no** |
| Own validator | — | `validate_kg.py` → **851 briefs, FAILS=0, WARNS=10** (all W3 pack-size soft budget) |

## The packaging question, answered: it is not the blocker

| Constraint | Limit | v4.2 | Verdict |
|---|---|---|---|
| `MAX_ZIP_BYTES` | 50 MB | `.skill` zip = **944 KB**; unpacked 7.9 MB against a current plugin of 8.6 MB | **fits, ~5× headroom** |
| `FORBIDDEN_TOP_LEVEL` | `{"bin"}` only | ships `kg/ scripts/ references/ templates/ tests/ assets/ curation/` | **no collision** |
| Skill discovery | `PLUGIN.rglob("*")` — a directory scan | a new skill folder is picked up automatically | **no manifest edit needed for the skill itself** |
| `DESCRIPTION_MAX` = 500 | governs the **plugin manifest**, currently 441 chars | *(it does NOT bound a SKILL.md description; `audit_skills.py` has no such check either)* | **not applicable** — correcting my own first reading |
| Python deps | `scripts/requirements.txt`: openpyxl, PyYAML, jsonschema, python-docx | all four import successfully in this container; two other installed skills already ship their own `requirements.txt` | **precedent exists, deps satisfied** |

## What actually has to happen, and what stays broken until it does

**Cheap and mechanical:**
1. Drop the 94 files in, replacing the 26. No manifest change for discovery.
2. Fix the two-version banner (SKILL.md `v3.0` vs CHANGELOG `v4.2`), and the same in `scripts/requirements.txt`, whose header also says "dma-research v3.0".

**Real work, because the defects are inside v4.2 itself:**
3. `scripts/engine/ledger.py:125` — `NameError: name '_stats' is not defined`. R27's whole token-budget rule routes through `ledger.py stats` and it has never run.
4. The **gate-id namespace collision**: all of `G1`–`G12` mean one thing in `validate_kg.py` and a different thing in `references/protocols/safeguard_gates.md`. The app side already solved this exact problem for `AG-06/07/08/10` with a two-directional test that cannot pass vacuously (`tests/skills/test_gate_guidance_reaches_producers.py`); the research skill has no analogue.
5. **G10's scope gap**: it scans `dq[].q`, `category_dq.q` and `sweep_queries` and never `q.primary` — where the shipped KG already carries **103 vendor names**, e.g. `P1C1.5.4` → `"{entity}" Einstein OR Agentforce OR copilot`. And `kg_reader briefs --context` injects vendor names into `routes[].q` **after** validation.

**Does not get fixed by shipping v4.2 at all:**
6. The downstream taxonomy constants. `plugins/dma-insights/skills/dma-research/scripts/merge_evidence.py:185` hardcodes `total_subcaps=836`; `plugins/dma-insights/skills/dma-assessment/scripts/validate_contracts.py:133-141` hardcodes a 17-id `expected_cats` set **including the killed `P1C5`**. Both are outside the archive.
7. **The enrichment connectors.** v4.2 is search-saturated (4,255 DQs, R27 capping each conversation at 40 search-ops, `FULL` scope = 30–36 conversations ⇒ 1,200–1,440 search-ops). No DMA Routine carries Exa or Tavily, and nothing consumes `search_requests`. Shipping v4.2 makes the *reasoning* available and leaves the *evidence* unreachable.

## The one-sentence answer

Shipping v4.2 is a small packaging job that unlocks a large amount of already-built,
already-validated reasoning discipline — and it buys nothing until a headless session can
actually run a web search.
