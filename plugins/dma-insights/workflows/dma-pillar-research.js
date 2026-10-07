export const meta = {
  name: 'dma-pillar-research',
  description: 'DMA research for the categories in args (engine.pipeline hands ONE category per invocation): capability-batch researchers in parallel, then an independent challenge and floors gate',
  whenToUse: 'The RESEARCH stage of engine.pipeline in research_mode=workflow: one invocation per category, all started in one message, args from <run>/07_qa/research_workflow.json',
  phases: [
    { title: 'Research', detail: 'one agent per batch of capabilities (<= 12 open cells), fresh context each' },
    { title: 'Challenge', detail: 'independent research-challenger + floors gate per category' },
  ],
}

// WHY A WORKFLOW (owner, 2026-09-30: "research works as background tasks and
// not real persisted /workflows"). engine.pipeline is a Python process and
// cannot start a Workflow; it hands the stage to the session, which runs this
// once per pillar. Its agents run in-session, so they hold Exa / Tavily / Clay
// directly (no relay).
//
// WHY BATCHES, NOT ONE AGENT PER CATEGORY (measured 2026-09-30, a multi-LOB run, round 1): a
// category agent reached 116-200K tokens of context in 39-71 turns and ended
// with 0 of 43-68 cells synthesised. 229 Tavily calls at max_results 8
// returned 1.81M chars (avg 7K, max 22K) — the context was spent on search
// payloads, plus --help / orient exploration and sleep-polling. So: a batch of
// <= 12 open cells per agent, compact connector settings, and the exact
// command sheet in the prompt so nothing is spent discovering the CLI.
//
// args (written by engine.pipeline to <root>/07_qa/research_workflow.json):
//   {pillar, cats, batches: {cat: [[cap, ...], ...]},
//    repairs: {cat: {cell: [term, ...]}}, repair_batches: {cat: [[cell, ...], ...]},
//    run, root, eng, plugin, rounds, entity, domain}

const A = args
const ENG = A.eng
const R = `--run ${A.run} --root ${A.root}`
const DOMAIN = A.domain || '<the entity\'s registrable domain, from engine.profile state>'

// --- PROMPTS BEGIN (render-prompts.mjs evaluates this region verbatim, so a
// session without the Workflow tool runs the SAME prompts as in-session agents) ---
const OUT = {
  type: 'object',
  properties: {
    category: { type: 'string' },
    cells_synthesised: { type: 'number' },
    declared_absent: { type: 'number' },
    still_open: { type: 'number' },
    searches_logged: { type: 'number' },
    evidence_registered: { type: 'number' },
    gate: { type: 'string' },
    blocking_terms: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
  required: ['category', 'still_open', 'gate', 'blocking_terms'],
}

const SHEET = `COMMAND SHEET (exact; do not run --help, orient or kg route — this is everything):
  checkpoint:  python3 -m engine.cli checkpoint ${R} --category <CAT> --position '<your batch>'   (ONLY if a search is refused with "search-op ceiling reached": the driver already opened this category's window sized for every batch of this round, and a checkpoint at start would reset your siblings' window mid-capability)
  card:        python3 -m engine.cli card ${R} --capability <CAP>            (the cells, their questions and owed facets)
  log search:  python3 -m engine.cli search ${R} --subcap <CELL> [--subcap <CELL2>] --facet primary|works|fails|value|contradicts|corroborates --tool web_search|exa|tavily|clay|internal --query '<q>' --hits N --kept K --actor $ACT
  cache text:  python3 -m engine.cli fetch ${R} --url <U> --query '<question>' --via-text <file with the connector's text>
  evidence:    python3 -m engine.cli evidence ${R} --subcap <CELL> --source '<publisher>' --url <U> --tier T1|T2|T3|T4 --excerpt '<verbatim 50-500 chars>' [--published <the date THE PAGE states>] --claim-type FACT|INFERENCE --origin public|internal --actor $ACT
               --published ONLY when the source itself states a date; an undated page OMITS it (the row bands UNVERIFIED). Never today's date, never a placeholder.
  reuse row:   python3 -m engine.cli attach ${R} --e-id E-NNN --subcap <CELL> --actor $ACT
  synthesise:  python3 -m engine.cli synthesis-template   (once), then  python3 -m engine.cli synthesise ${R} --subcap <CELL> --json <file> --actor $ACT
  absent:      python3 -m engine.cli absence ${R} --subcap <CELL> --actor $ACT --hunted '<what, where, what came back>' --ladder '<json>' --validation-question '<q>'   (only after a primary web_search AND one connector volley on the cell)
               --hunted becomes the cell's What_We_Found and the gate refuses boilerplate: name the exact queries, the sites/tools searched and the nearest thing that came back (a proper noun, a date or an E-id).
TURN ECONOMY: every turn re-reads your whole context, so turns are the cost. Per capability aim for ~4 turns: (1) card, (2) all searches in parallel, (3) ONE Bash call writing the synthesis/absence JSON files and the ops file, (4) ONE engine.cli batch call.`

const SEARCH_RULES = `SEARCH ECONOMY (your context is the budget — a 200K-token context ends your turn with nothing written):
  - web_search (WebSearch) is the primary volley: compact results. Fire a capability's queries in PARALLEL in one turn.
  - Tavily: ALWAYS {max_results: 3, search_depth: "basic"} and include_domains when a domain fits; ONE Tavily volley per capability covers all its cells (log it with several --subcap). Never tavily_extract a whole site; extract one URL, then fetch --via-text.
  - Exa: {numResults: 3}. If Exa answers HTTP 402/429 once, stop using it for this batch and use Tavily for the same query.
  - Clay: do NOT re-fetch the company record (PRELIM holds firmographics). Use mcp__Clay__search-contacts (companyIdentifiers ["${DOMAIN}"]) only when a cell asks who owns a function, once per batch.
  - CONNECTOR CHECK FIRST: you should hold Exa, Tavily and Clay (mcp__Exa__*, mcp__Tavily__*, mcp__Clay__*). If none of them is callable, stop after your first capability and return gate "NO_CONNECTORS" naming the tools you do have: no cell can be declared absent without one, so continuing only spends budget.
  - Never sleep, poll, background a command, or re-run the gate mid-batch. Run commands in the FOREGROUND with timeout 600000.`

// DEGRADED (engine.pipeline sets args.degraded when the connector baseline is
// short — measured 2026-10-01, Cross Insurance: Exa 402, Tavily 432/429,
// Firecrawl 402). The NO_CONNECTORS stop above would end EVERY batch after its
// first capability and close nothing, which is exactly the stall the degraded
// path exists to prevent; so a degraded run gets its own rules instead.
const DEGRADED_RULES = `DEGRADED RUN (the driver recorded enrichment_degraded; this REPLACES the connector rules):
  - Exa, Tavily and Firecrawl are unavailable for this run: do NOT call them and do NOT stop with NO_CONNECTORS.
  - WebSearch / WebFetch are the search tools (log as --tool web_search). Fire a capability's queries in PARALLEL in one turn; WebFetch one URL at most per cell, then fetch --via-text.
  - Clay search-contacts (companyIdentifiers ["${DOMAIN}"]) only when a cell asks who owns a function, once per batch.
  - Declare an empty cell absent only after a primary WebSearch volley on it, and add --enrichment-unavailable to engine.cli absence (the connector volley cannot run). --hunted still names the exact queries, sites and nearest thing found.
  - Never sleep, poll, background a command, or re-run the gate mid-batch. Run commands in the FOREGROUND with timeout 600000.`

// REPAIR WORK IS ROUTED, NOT INFERRED (measured 2026-10-05, a CL run,
// round 2): every blocker of 13 failing categories sat on a cell already
// synthesised or declared absent, while the batch prompt said to skip closed
// cells — so each category spent a round writing nothing. The driver now
// hands `repairs: {cat: {cell: [terms]}}` and `repair_batches` from the
// gate's own findings; a later round re-reads them from floors_<cat>.json.
const REPAIRS = A.repairs || {}
const REPAIR_BATCHES = A.repair_batches || {}
const isRepair = (cat, caps) => caps.length === 1 && String(caps[0]).startsWith(`${cat} (`)
// ONE CELL, ONE LANE (measured 2026-10-07): the gate names open cells too
// (absence_unsearched, volleys_incomplete, synthesis_missing), so a repair
// agent that read the raw verdict worked the same cells as the open-cell
// batches running beside it. `--repair-cells` leaves the open cells to the
// batches; `--include-open` is for a round in which no batch runs.
const READ_BLOCKERS = (cat, includeOpen) => `python3 -m engine.floors_gate ${R} --category ${cat} --repair-cells${includeOpen ? ' --include-open' : ''}`

function repairPrompt(cat, cells, round, includeOpen) {
  const lc = cat.toLowerCase()
  const named = cells && cells.length
    ? `YOUR CELLS and the gate terms each one fails:\n${cells.map(c => `  ${c}: ${((REPAIRS[cat] || {})[c] || []).join(', ')}`).join('\n')}\nFor the detail of each finding (missing facets, the single source), run once: ${READ_BLOCKERS(cat, false)} and read ${A.root}/07_qa/floors_${cat}.json only for these cells.`
    : `YOUR CELLS: every cell the gate names${includeOpen ? '' : ' that is already synthesised or declared absent — an OPEN cell (no synthesis, no absence) belongs to the capability batch running beside you; never touch one'}. Print them once (from ${ENG}): ${READ_BLOCKERS(cat, !!includeOpen)}\nThat is {cell: [blocking terms]}; read ${A.root}/07_qa/floors_${cat}.json for each finding's detail.`
  return `You are research-${lc}-producer for DMA run ${A.run} (${A.entity || 'the entity'}), round ${round}, REPAIR batch. Work from ${ENG}; set ACT=research-${lc}-producer.
These cells are ALREADY synthesised or declared absent, and the category's floors gate FAILS on them. Repair them in place. Do NOT skip a cell because it is closed. Touch no other cell.
Do NOT run engine.cli checkpoint at start: the driver opened ${cat}'s search window sized for every batch of this round (checkpoint only if a search is refused with "search-op ceiling reached").
${named}
Per blocking term:
  - primary_unfired: fire a primary web_search on the cell and log it (--facet primary).
  - volleys_incomplete: fire and log each facet listed under "missing" for that cell; register evidence for anything a search returns.
  - single_source_fact: look for a second independent source (not the same domain). If you find one, register it. If you don't, re-synthesise the cell with Claim_Label INFERENCE. Never keep FACT on one domain.
  - absence_undeclared_empty / absence_unsearched: fire primary plus one connector volley, then declare the absence with the hunted/ladder you actually ran.
  - evidence_smear: give each named sibling its own evidence, or re-synthesise so each states only what the shared item supports for that cell.
  - boilerplate / synthesis_missing: rewrite the named field with a checkable figure, date, proper noun or E-id.
  - challenge_failed: an independent challenger FAILED this claim. Read why first: python3 -c "from engine import runstate,ledger as L;from pathlib import Path;wb=runstate.locate('${A.run}',Path('${A.root}')).open();print(L.challenge_for(wb,'<CELL>'))". Repair exactly what it names (a missing counter-source, an overstated claim, an unregistered figure), with new searches and evidence where it asks for them, then re-synthesise. Re-synthesis clears the old verdict and the challenge step re-challenges it; never re-synthesise unchanged text.
  - a cell id equal to the category (${cat}) is a category-level finding: read its detail and act on the cells it names.
Re-synthesise with synthesise --json (the same command replaces the cell's synthesis). The engine REFUSES a re-synthesis whose record is identical to the text the challenger FAILED — change what the verdict names, never re-send the same text. Every change goes through ONE engine.cli batch per capability, as below.

${SHEET}

${A.degraded ? DEGRADED_RULES : SEARCH_RULES}

Never invent a source, a quote, a number or a person. Pass --actor $ACT on every write. Do not run the gate: the challenge step runs it.
Return: category ${cat}, cells_synthesised (cells re-synthesised), declared_absent, still_open 0, searches_logged, evidence_registered, gate "BATCH_DONE", blocking_terms (each one you could NOT repair, as "term: cell"), and one-line notes.`
}

function batchPrompt(cat, caps, round, prev) {
  if (isRepair(cat, caps)) return repairPrompt(cat, null, round)
  const lc = cat.toLowerCase()
  return `You are research-${lc}-producer for DMA run ${A.run} (${A.entity || 'the entity'}), round ${round}. Work from ${ENG}; set ACT=research-${lc}-producer.
YOUR BATCH: capabilities ${caps.join(', ')} of category ${cat} — ONLY their open cells (a cell with a synthesis or declared absence is done; skip it).
${prev ? `The category's last gate: ${prev.gate}; blocking ${JSON.stringify(prev.blocking_terms || []).slice(0, 500)}. Close those for your cells.` : ''}
Your brief's shared.internal_documents (python3 -m engine.brief dispatch ${R} --category ${cat} | head -c 4000, once) lists the run's internal documents: grep them for your cells and register what bears on them with --origin internal (HYBRID run).

${SHEET}

${A.degraded ? DEGRADED_RULES : SEARCH_RULES}

Do NOT run engine.cli checkpoint at start: the driver opened ${cat}'s search window sized for every batch of this round (checkpoint only if a search is refused with "search-op ceiling reached").
LOOP, one capability at a time: card -> parallel searches (primary + the owed facets, one turn) -> cache connector text (fetch --via-text) -> write the synthesis/absence JSON files -> ONE engine.cli batch call for the whole capability. Finish a capability before starting the next.
WRITES GO THROUGH engine.cli batch (mandatory): put every search log, evidence, attach, synthesise and absence line for the capability in one ops file — one command per line, (the "python3 -m engine.cli" prefix and --run/--root may be omitted) — then run: python3 -m engine.cli batch ${R} --file <ops file>
One write outside a batch costs ~10 s under the run-wide lock that every researcher shares; a batch is one load, one lock, one save. The batch reports each command's result; fix and re-batch only the refused lines. Order inside the file matters: search logs, then evidence, then attach, then synthesise/absence.
Never invent a source, a quote, a number or a person. Pass --actor $ACT on every write.
Return: category ${cat}, cells_synthesised, declared_absent, still_open (your batch), searches_logged, evidence_registered, gate "BATCH_DONE", blocking_terms [] and one-line notes.`
}

function challengePrompt(cat, round) {
  return `Independent challenge for category ${cat} of DMA run ${A.run} (root ${A.root}), round ${round}. Run commands from ${ENG}, foreground, long timeouts.
1) python3 -m engine.brief challenge-batch ${R} --only ${cat} --out-dir ${A.root}/briefs/wf_challenge_${cat}_r${round} --json
2) If it lists packets, work each prompt file exactly as research-challenger: judge every cell on the seven dimensions and record each verdict with python3 -m engine.cli challenge ... --actor research-challenger. You never challenge a cell you wrote and never search.
3) python3 -m engine.cli gate ${R} --category ${cat} --require-synthesis --summary
   It prints {gate, blocking: {term: [cells]}, advisory: [terms], repair_cells}. Read it exactly: advisory terms do not block.
Return gate (as printed), blocking_terms as "term: cell, cell" strings copied from \`blocking\` (never an advisory term), still_open = repair_cells, and one-line notes. Do not compute any other count.`
}

// --- PROMPTS END ---

const BATCHES = A.batches || {}
log(`${A.pillar} · ${A.cats.map(c => `${c}×${(BATCHES[c] || [[]]).length}`).join(', ')} batch(es) · up to ${A.rounds} round(s)`)

const results = await pipeline(A.cats, async (cat) => {
  let prev = null
  // Round 1: the open-cell batches plus the gate's repair batches, side by
  // side. No routed work at all falls back to a repair agent that reads the
  // gate's cells itself (a hand-started invocation, or an older handoff).
  let jobs = [
    ...(BATCHES[cat] || []).map(caps => ({ caps, prompt: (r, p) => batchPrompt(cat, caps, r, p) })),
    ...(REPAIR_BATCHES[cat] || []).map(cells => ({ caps: cells, prompt: (r) => repairPrompt(cat, cells, r) })),
  ]
  // No routed work at all: the lone repair agent owns the open cells too.
  if (!jobs.length) jobs = [{ caps: [`${cat} (cells the gate names)`], prompt: (r) => repairPrompt(cat, null, r, true) }]
  for (let round = 1; round <= A.rounds; round++) {
    const done = await parallel(jobs.map((j, i) => () => agent(j.prompt(round, prev), {
      label: `${cat} r${round} b${i + 1} ${j.caps[0]}${j.caps.length > 1 ? '…' : ''}`, phase: 'Research', schema: OUT, model: 'sonnet',
    })))
    const got = done.filter(Boolean)
    log(`${cat} r${round}: ${got.reduce((a, r) => a + (r.cells_synthesised || 0) + (r.declared_absent || 0), 0)} cells closed, ${got.reduce((a, r) => a + (r.still_open || 0), 0)} open across ${jobs.length} batch(es)`)
    // AN AGENT ERROR IS NOT A ROUND (measured 2026-10-05: a spend limit failed
    // every agent, and each workflow still launched its challenge, round 2
    // and a second challenge — ~80K tokens apiece for nothing). Nothing ran,
    // so nothing is challenged or retried; the driver re-hands the category.
    if (!got.length) {
      log(`${cat} r${round}: every research agent failed — stopping; the driver re-hands it`)
      return { category: cat, still_open: -1, gate: 'AGENT_ERROR', blocking_terms: ['agent_error: no research agent returned'] }
    }
    const c = await agent(challengePrompt(cat, round), {
      label: `${cat} challenge r${round}`, phase: 'Challenge', schema: OUT, model: 'sonnet',
      agentType: 'dma-insights:research-challenger',
    })
    if (!c) {
      log(`${cat} r${round}: the challenge agent failed — stopping; the driver re-reads the gate`)
      return { category: cat, still_open: -1, gate: 'AGENT_ERROR', blocking_terms: ['agent_error: challenge did not return'] }
    }
    prev = c
    log(`${cat} r${round}: gate ${prev.gate}, ${prev.still_open} repair cell(s)`)
    if (prev.gate === 'PASS') break
    // A failing agent this round makes the next one a retry into the same
    // fault: stop and let the driver decide.
    if (got.length < jobs.length) {
      log(`${cat} r${round}: ${jobs.length - got.length} research agent(s) failed — not starting another round`)
      break
    }
    // Round 2 keeps unfinished open batches and repairs whatever the gate
    // names now — read fresh from floors_<cat>.json, not from agent prose.
    // The two sets are DISJOINT: while an open batch re-runs, the repair
    // agent reads closed cells only; with no open batch left it takes the
    // open cells as well, so nothing the gate names is worked twice or not
    // at all.
    const reopen = jobs.filter((j, i) => !isRepair(cat, j.caps) && !(REPAIR_BATCHES[cat] || []).includes(j.caps)
                                      && done[i] && (done[i].still_open || 0) > 0)
    jobs = [
      ...reopen,
      { caps: [`${cat} (cells the gate names)`], prompt: (r) => repairPrompt(cat, null, r, reopen.length === 0) },
    ]
  }
  if (prev && prev.gate !== 'PASS') log(`${cat}: still failing after ${A.rounds} round(s) — the driver's floors gate decides what happens next`)
  return prev
})

return { pillar: A.pillar, categories: results }
