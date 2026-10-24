# ROUTING EVAL — 28-09-2026 · dma-insights 1.20.0

Method: 64 labelled utterances (`routing_eval.jsonl`) routed by a fresh Sonnet agent that saw ONLY the 35 installed descriptions (`installed_skill_descriptions.json`: 6 plugin skills, 3 plugin commands, 26 account-level synced skills incl. the three retired ones). Results in `routing_eval_results.jsonl`.

| metric | value | pass |
|---|---|---|
| top-1 strict (plugin copy required) | 54/64 = 84.4% | ≥95% → FAIL |
| top-1 lenient (account duplicate counted as the same skill) | 58/64 = 90.6% | ≥95% → FAIL |
| routes to retired skills | 6 | 0 → FAIL |
| pre/post-assessment deck confusions | 0 | 0 → PASS |
| account-duplicate picked over plugin copy | 2 (ids 56, 64: 'M1-M5' wording matches the account description's 'scored M1-M5') | 0 → FAIL |

## Confusion by utterance class
| class | hit | miss |
|---|---|---|
| ai-overlay | 2 | 0 |
| ambiguous | 4 | 0 |
| assessment | 5 | 0 |
| deck | 2 | 0 |
| first-call | 5 | 0 |
| governance | 5 | 0 |
| hubbl | 3 | 0 |
| ops | 2 | 0 |
| out-of-scope | 4 | 0 |
| out-of-scope-research | 2 | 0 |
| post-assessment-deck | 4 | 0 |
| production | 6 | 0 |
| rectifier | 3 | 0 |
| repair | 2 | 0 |
| research | 2 | 0 |
| research-start | 4 | 0 |
| retired-phrase | 0 | 6 |
| thin-evidence | 1 | 0 |
| trap-m5 | 2 | 0 |

## Misses and the description text behind each
| id | utterance | routed to | expected | trigger phrase quoted by the router |
|---|---|---|---|---|
| 19 | P1 research for Logix Federal Credit Union | anthropic-skills:dma-p1 | dma-insights:dma-research | 'P1 research for Logix Federal Credit Union' matches dma-p1's own identity 'Pillar 1 ... r |
| 20 | Produce the research handoff for Baxter | anthropic-skills:dma-p1 | dma-insights:dma-research | 'Produce the research handoff' matches the verb in 'Produces research_handoff.json for dow |
| 21 | Run the DMA engagement for Frost, Pillar 1 only, hybrid mode | anthropic-skills:dma-orchestrator | dma-insights:dma-research | 'Run the DMA engagement ... Pillar 1 only, hybrid mode' matches 'DMA engagement', 'orchest |
| 22 | Inspect the CCG and RSG state for the current run | anthropic-skills:dma-core | dma-insights:dma-research | 'Inspect the CCG and RSG state' is an almost word-for-word match to 'Use directly ONLY whe |
| 23 | ESG research for an FSI, P1C5 | anthropic-skills:dma-p1 | dma-insights:dma-research | 'ESG research for an FSI, P1C5' is a verbatim match to dma-p1's trigger 'ESG research for  |
| 24 | Do the Phase A onboarding and SIB assembly for a new credit  | anthropic-skills:dma-p1 | dma-insights:dma-research | 'Phase A onboarding and SIB assembly' is verbatim to dma-p1's 'Phase A through Phase E pip |

Every miss is a retired-skill phrase landing on a retired description that still advertises it (`P1 research`, `research_handoff.json`, `DMA engagement … hybrid`, `CCG/RSG`, `ESG research for an FSI`, `Phase A … SIB Assembly`). The plugin's dma-research description does not claim these phrases, so the retired copies win on text. Fix: delete the retired copies (F-A05-001) and add the legacy phrases as redirects in dma-research's description (F-B03-002).