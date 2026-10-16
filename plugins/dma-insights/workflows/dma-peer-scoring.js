export const meta = {
  name: 'dma-peer-scoring',
  description: 'DMA peer scoring when the sub-vertical cohort is below its floor: one agent per pillar scores every LOCKED peer on each of the pillar\'s categories from abbreviated public evidence (the assessment skill\'s Peer Scoring Protocol) and records the median and quartiles with basis inferred; one agent completes the peer estate (Tech_Peer_Deployments, Platform_Peer_Adoption) for every locked peer',
  whenToUse: 'When engine.pipeline stops NEEDS_PEER_SCORING (a locked peer set, a cohort below the floor, no peer figure on any category), or an owner asks for peer figures on a run that served none; args from <run>/07_qa/peer_scoring_workflow.json',
  phases: [
    { title: 'Score peers', detail: 'one agent per pillar: 4 categories x every locked peer, abbreviated T1-T3 evidence, same rubric, same caps' },
    { title: 'Peer estate', detail: 'deployment and platform-adoption rows for every locked peer the register and the platform page compare against' },
  ],
}

// Owner, 2026-10-15 (Verus Financial Partners): "Peer data is empty." The run
// named four peers, the RIA cohort held no other assessed entity, and every
// peer field on every page served null. The owner decision of 2026-10-06
// (the peer figure is the cohort mean) presumed a cohort; below the floor the
// assessment skill's own fallback applies — score the locked peers on
// abbreviated public evidence — and the cohort mean replaces those figures
// once the sub-vertical has three assessed entities (prelim.peer_row_wants_cohort).

const A = args
const R = `--run ${A.run} --root ${A.root}`
const OUT = {
  type: 'object',
  properties: {
    lane: { type: 'string' },
    status: { type: 'string' },
    recorded: { type: 'number' },
    notes: { type: 'string' },
  },
  required: ['lane', 'status'],
}

const peerList = A.peers.map((p, i) => `  ${i + 1}. ${p}`).join('\n')
const common = `DMA run ${A.run}, root ${A.root}. Every engine command runs from ${A.eng} with \`${R}\`. Foreground commands, long timeouts. The LOCKED peer set (names verbatim, in this positional order):\n${peerList}\nEvidence rows already registered about these peers (reuse them before searching; read each with a short Python openpyxl snippet over the workbook's Evidence_Detail tab, read-only): ${A.known_evidence}. The entity under assessment is ${A.entity} (${A.sub_vertical}); NEVER write a score, evidence link or anything else against the entity's own cells, never edit the workbook by hand (openpyxl writes are forbidden; the engine commands below are the only writes), never submit or promote. Search order: the plugin evidence server (find_evidence_all_sources / find_regulator_evidence / find_trade_press_evidence), then searxng, then Parallel web_search, then WebSearch; Exa and Tavily are out of credit. Log EVERY search: \`python3 -m engine.cli search ${R} --actor <your actor> --subcap <the category's first cell, e.g. P1C1.1.1> --facet corroborates --tool <evidence_engine|searxng|parallel|web_search|web_fetch> --query 'PEER <peer name>: <query>' --hits N --kept N --outcome '<terminal outcome>'\`; if a search is refused with "search-op ceiling", run \`python3 -m engine.cli checkpoint ${R} --category RELAY --position '<where you got to>'\` once and continue. Register every span you rely on as PROFILE evidence (it supports the peer comparison, not a cell): \`python3 -m engine.cli evidence ${R} --profile --actor <your actor> --source '<publisher — document>' --url <url> --tier T1..T5 --excerpt '<verbatim 50-500 chars>' [--published YYYY-MM-DD] --claim-type FACT|INFERENCE\` and keep the E-id it returns.`

const scorerPrompt = (pl) => `You are the peer scorer for pillar ${pl.pillar} (actor peer-scoring-${pl.pillar.toLowerCase()}). ${common}
Read first, in full: ${A.refs.peer_benchmarking} (Peer Scoring Protocol and Benchmark Calculation), ${A.refs.scoring_methodology} and ${A.refs.capability_criteria} (the category descriptors for ${pl.pillar}).
TASK: for EACH of these categories — ${pl.categories.map(c => `${c.id} ${c.name}`).join('; ')} — score EVERY locked peer 1.0-5.0 on the category rubric from abbreviated public evidence (T1-T3 preferred: Form ADV Parts 1A/2A on adviserinfo.sec.gov, the peer's own site, trade press, regulator records; one or two searches per peer per category, reusing the registered rows). Apply the SAME caps the entity got: own-site-only evidence caps a score at 2.0; a single source holds the score at or below the band its tier allows; no evidence after the ladder = NA, never a guessed number. Give each peer score a confidence (LOW/MED/HIGH). Then compute the category's median, p25 and p75 from the scored peers exactly as peer_benchmarking.md states (4 scored: median=(s[1]+s[2])/2, p25=s[0], p75=s[3]; 3: s[1], s[0], s[2]; 2: mean, min, max; 1: that score for all three; 0: cannot_estimate).
RECORD each category with ONE command: \`python3 -m engine.prelim peer-median ${R} --category <ID> --median <M> --p25 <L> --p75 <H> --basis inferred --peer-scores "<s1>,<s2>,<s3>,<s4>" --source "abbreviated public-evidence scoring of the locked peers, ${A.today}: <peer short name>=<score> (<conf>; E-ids), ... ; same rubric and caps as the entity"\` — the --peer-scores list is POSITIONAL in the locked order above, one figure per peer, NA for a peer with none (the engine refuses a mismatched length). Where no peer could be scored, record \`--basis cannot_estimate\` with no median and the ladder in --source. Then record the rationale: \`python3 -m engine.cli gate-log ${R} --gate PEER_SCORE --scope <ID> --verdict PASS --detail '<per peer: level argued in the rubric's words, the key E-ids, the cap applied; <=900 chars>'\`.
Return lane "${pl.pillar}", status "SCORED" (or "PARTIAL" naming what is missing), recorded (categories recorded), and notes listing per category the four scores, median/p25/p75 and confidence.`

const estatePrompt = () => `You are the peer-estate recorder (actor peer-estate). ${common}
TASK A — Tech_Peer_Deployments: the tab holds rows for ONE peer only (Godsey & Gibb) on TS-001 (Schwab Advisor Services custody), TS-002 (Orion client portal), TS-003 (ShareFile secure messaging), TS-004 (Calendly, ABSENT), TS-008 (Pontera held-away), TS-009 (Glass Lewis proxy voting). For EACH of the other three locked peers and EACH of TS-001, TS-002, TS-003, TS-008 (and TS-009 where a Form ADV Part 2A answers it), establish deployed / not deployed / unknown from Form ADV Part 2A (custodian, held-away tools, proxy voting), the peer's homepage client-login markup (portal vendor, secure-message vendor), and the registered rows (E-173..E-181 already cover Schwab custody at Kanawha and others), then record each with \`python3 -m engine.techscan peer-record ${R} --ts <TS-nnn> --peer '<locked name verbatim>' --deployed|--not-deployed|--unknown --basis '<one clause naming the page and what it shows>' --url <url> --as-of <YYYY-MM-DD the page states, else the retrieval date>\`. --unknown is a real answer after a real search, never a skipped one.
TASK B — Platform_Peer_Adoption: the tab holds one peer (Godsey & Gibb) at UNKNOWN on Financial Services Cloud, Data Cloud, CRM Analytics (Tableau), GRC Platform and Digital Strategy Workshop. For EACH of the other three peers and EACH of those five products, run one keyword search (peer name + product) and record \`python3 -m engine.assessment peer-adoption ${R} --product '<product exactly as the tab spells it>' --peer '<locked name verbatim>' --verdict YES|NO|UNKNOWN --basis '<what the search found or did not>' --source '<url or "not established">' --as-of ${A.today}\`.
Return lane "estate", status "RECORDED" (or "PARTIAL"), recorded (rows written), and notes with the verdict per peer per row.`

log(`peer scoring for ${A.pillars.length} pillar(s) x ${A.peers.length} locked peer(s), plus the peer estate`)
const results = await parallel([
  ...A.pillars.map(pl => () => agent(scorerPrompt(pl), {
    label: `peers ${pl.pillar}`, phase: 'Score peers', schema: OUT, agentType: 'claude', model: 'sonnet',
  })),
  () => agent(estatePrompt(), {
    label: 'peer estate', phase: 'Peer estate', schema: OUT, agentType: 'claude', model: 'sonnet',
  }),
])
return results.map((r, i) => r || { lane: i < A.pillars.length ? A.pillars[i].pillar : 'estate', status: 'DIED' })
