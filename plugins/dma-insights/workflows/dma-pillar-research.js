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
// once per CATEGORY (sixteen side by side: the runtime caps concurrency per
// workflow). Its agents run in-session, so they hold Exa / Tavily / Clay
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
//   {pillar, cats, batches: {cat: [[cap, ...], ...]}, repair: {cat: {cell: [term]}},
//    run, root, eng, plugin, rounds, entity, domain}
// `repair` names CLOSED cells the floors gate still refuses on a researcher's
// term (J-09, measured 2026-10-01: 35 such cells kept 8 categories failing
// forever, because a batch skipped every closed cell).

const A = args
const ENG = A.eng
const R = `--run ${A.run} --root ${A.root}`
const DOMAIN = A.domain || '<the entity\'s registrable domain, from engine.profile state>'

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

const DOWN = A.enrichment_down || {}
const DOWN_NOTE = Object.keys(DOWN).length
  ? `\n  - ALREADY MEASURED DOWN FOR THIS RUN — do not call: ${Object.entries(DOWN).map(([t, w]) => `${t} (${w})`).join('; ')}.`
  : ''

const SHEET = `COMMAND SHEET (exact; do not run --help, orient or kg route — this is everything):
  card:        python3 -m engine.cli card ${R} --capability <CAP>            (the cells, their questions and owed facets)
  log search:  python3 -m engine.cli search ${R} --subcap <CELL> [--subcap <CELL2>] --facet primary|works|fails|value|contradicts|corroborates --tool web_search|exa|tavily|clay|internal --query '<q>' --hits N --kept K --actor $ACT
  cache text:  python3 -m engine.cli fetch ${R} --url <U> --query '<question>' --via-text <file with the connector's text>
  evidence:    python3 -m engine.cli evidence ${R} --subcap <CELL> --source '<publisher>' --url <U> --tier T1|T2|T3|T4 --excerpt '<verbatim 50-500 chars>' [--published <the date THE PAGE states>] --claim-type FACT|INFERENCE --origin public|internal --actor $ACT
               --published ONLY when the source itself states a date; an undated page OMITS it (the row bands UNVERIFIED). Never today's date, never a placeholder.
  reuse row:   python3 -m engine.cli attach ${R} --e-id E-NNN --subcap <CELL> --actor $ACT
  fix a date:  python3 -m engine.cli redate ${R} --e-id E-NNN (--undated | --published <stated date>) --reason '<where the page states it, or that it does not>' --actor $ACT
  synthesise:  python3 -m engine.cli synthesis-template   (once), then  python3 -m engine.cli synthesise ${R} --subcap <CELL> --json <file> --actor $ACT
  absent:      python3 -m engine.cli absence ${R} --subcap <CELL> --actor $ACT --hunted '<what, where, what came back>' --ladder '<json>' --validation-question '<q>'   (only after a primary web_search AND one connector volley on the cell)
               --hunted becomes the cell's What_We_Found and the gate refuses boilerplate: name the exact queries, the sites/tools searched and the nearest thing that came back (a proper noun, a date or an E-id).
TURN ECONOMY: every turn re-reads your whole context, so turns are the cost. Per capability aim for ~4 turns: (1) card, (2) all searches in parallel, (3) ONE Bash call writing the synthesis/absence JSON files and the ops file, (4) ONE engine.cli batch call.`

const SEARCH_RULES = `SEARCH ECONOMY (your context is the budget — a 200K-token context ends your turn with nothing written):
  - WebSearch is a SESSION-POOLED budget: 200 calls shared by EVERY agent of EVERY category workflow in this session (J-22, measured 2026-10-01: 32 agents spent it in 18 minutes, then every call was refused). So Tavily is the volley tool and WebSearch the fallback: one query per FACET per CAPABILITY (log it with a --subcap for every cell it answers), never one per cell. Fire a capability's queries in PARALLEL in one turn.
  - Tavily: ALWAYS {max_results: 3, search_depth: "basic"} and include_domains when a domain fits. Never tavily_extract a whole site; extract one URL, then fetch --via-text.
  - Exa: {numResults: 3}. If Exa answers HTTP 402/429 once, stop using it for this batch and use Tavily for the same query.
  - Clay: do NOT re-fetch the company record (PRELIM holds firmographics). Use mcp__Clay__search-contacts (companyIdentifiers ["${DOMAIN}"]) only when a cell asks who owns a function, once per batch. Filter roles with  select from people where headline contains "<word>" limit 10  — `headline` is the filter field; `latest_experience_title` is only in the RESPONSE (J-20: 35 of 38 calls failed guessing job_title / title / latest_experience_title).
  - CONNECTOR CHECK FIRST: you should hold Exa, Tavily and Clay (mcp__Exa__*, mcp__Tavily__*, mcp__Clay__*). If none of them is callable, stop after your first capability and return gate "NO_CONNECTORS" naming the tools you do have: no cell can be declared absent without one, so continuing only spends budget.
  - A connector that answers 401/402/403/429 (credits, auth, rate-blocked) is DOWN for the run: record it ONCE — python3 -m engine.cli connector-down ${R} --tool exa|tavily --status <code> --error '<its own words>' --actor $ACT — and stop calling it. When every web connector is down the run is degraded: close an empty cell with absence ... --enrichment-unavailable after its web_search volleys (the gate discloses REDUCED rigour); never log a search you did not fire to get round it.${DOWN_NOTE}
  - Never sleep, poll, background a command, or re-run the gate mid-batch. Run commands in the FOREGROUND with timeout 600000.`

const REPAIR_HOW = `HOW TO REPAIR A CLOSED CELL (do exactly what its term names, nothing more):
  primary_unfired           -> fire the card's primary diagnostic question and log it: search --facet primary
  volleys_incomplete:<f,..> -> fire and log each named facet for the cell (a volley that found nothing is still logged, --hits 0)
  boilerplate:<field>       -> an absence: re-run absence with --hunted naming the exact queries, sites/tools and the nearest thing that came back (proper noun, date or E-id); a synthesis: re-synthesise with that field naming a figure, date, proper noun or E-id
  single_source_fact        -> register or attach a second source on a DIFFERENT host and re-synthesise; if none exists, re-synthesise with Claim_Label INFERENCE
  absence_single_tool       -> fire one exa or tavily volley on the cell, then re-declare the absence
  date_placeholder:<E-id>   -> the row is dated the day it was retrieved: redate --e-id <E-id> --undated --reason '<page states no date>' (or --published <the date the page states> with the page's dated words in --reason)
  anything else             -> the term is the floors gate's own field name: fix that field and re-write the cell`

function repairsFor(cat, caps) {
  const rep = (A.repair || {})[cat] || {}
  return Object.entries(rep).filter(([cell]) => caps.some(cap => cell.startsWith(cap + '.')))
}

function batchPrompt(cat, caps, round, prev) {
  const lc = cat.toLowerCase()
  const rep = repairsFor(cat, caps)
  return `You are research-${lc}-producer for DMA run ${A.run} (${A.entity || 'the entity'}), round ${round}. Work from ${ENG}; set ACT=research-${lc}-producer.
YOUR BATCH: capabilities ${caps.join(', ')} of category ${cat} — their OPEN cells${rep.length ? ', plus the REPAIR cells below' : ''}. Any other cell with a synthesis or declared absence is done; skip it.
${rep.length ? `REPAIR (closed cells the floors gate still refuses — cell: terms):\n${rep.map(([c, t]) => `  ${c}: ${t.join(' ')}`).join('\n')}\n${REPAIR_HOW}\n` : ''}${prev ? `The category's last gate: ${prev.gate}; blocking ${JSON.stringify(prev.blocking_terms || []).slice(0, 500)}. Close those for your cells.` : ''}
${(A.internal_docs || []).length ? `INTERNAL DOCUMENTS (this run is HYBRID): ${A.internal_docs.join('; ')}. Grep them for your cells and register every span you rely on with --origin internal (and log the grep: search --tool internal). Internal T2 outweighs public T3-T5 for the same cell.` : ''}

${SHEET}

${SEARCH_RULES}

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
3) python3 -m engine.cli gate ${R} --category ${cat} --require-synthesis
Return the gate verdict, its blocking terms, and how many cells are still open.`
}

const BATCHES = A.batches || {}
log(`${A.pillar} · ${A.cats.map(c => `${c}×${(BATCHES[c] || [[]]).length}`).join(', ')} batch(es) · up to ${A.rounds} round(s)`)

const results = await pipeline(A.cats, async (cat) => {
  let prev = null
  let batches = BATCHES[cat] && BATCHES[cat].length ? BATCHES[cat] : [[`${cat} (all open capabilities)`]]
  for (let round = 1; round <= A.rounds; round++) {
    const done = await parallel(batches.map((caps, i) => () => agent(batchPrompt(cat, caps, round, prev), {
      label: `${cat} r${round} b${i + 1} ${caps[0]}${caps.length > 1 ? '…' : ''}`, phase: 'Research', schema: OUT, model: 'sonnet',
    })))
    const got = done.filter(Boolean)
    log(`${cat} r${round}: ${got.reduce((a, r) => a + (r.cells_synthesised || 0) + (r.declared_absent || 0), 0)} cells closed, ${got.reduce((a, r) => a + (r.still_open || 0), 0)} open across ${batches.length} batch(es)`)
    const c = await agent(challengePrompt(cat, round), {
      label: `${cat} challenge r${round}`, phase: 'Challenge', schema: OUT, model: 'sonnet',
      agentType: 'dma-insights:research-challenger',
    })
    prev = c
    if (prev) log(`${cat} r${round}: gate ${prev.gate}, ${prev.still_open} open`)
    if (prev && prev.gate === 'PASS') break
    // Round 2 re-batches only what is still open: batches that finished stay finished.
    const open = got.filter(r => (r.still_open || 0) > 0).length
    if (open === 0 && got.length === batches.length) batches = [[`${cat} (cells the gate names)`]]
    else batches = batches.filter((_, i) => !done[i] || (done[i].still_open || 0) > 0)
    if (!batches.length) batches = [[`${cat} (cells the gate names)`]]
  }
  if (prev && prev.gate !== 'PASS') log(`${cat}: still failing after ${A.rounds} round(s) — the driver's floors gate decides what happens next`)
  return prev
})

return { pillar: A.pillar, categories: results }
