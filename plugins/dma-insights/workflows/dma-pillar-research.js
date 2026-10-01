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
//   {pillar, cats, batches: {cat: [[cap, ...], ...]}, run, root, eng, plugin,
//    rounds, entity, domain}

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

const SHEET = `COMMAND SHEET (exact; do not run --help, orient or kg route — this is everything):
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

// WHY SHARED QUERIES (measured 2026-10-01, Cross Insurance P4C4): per-cell
// volleys are ~6 searches x 694 cells ~= 4,000 calls against a 200-call
// WebSearch session cap; one category spent the whole cap and 612K subagent
// tokens and closed nothing. A capability's cells answer neighbouring
// diagnostic questions, so ONE query per facet per capability, logged with
// every --subcap it genuinely addresses, satisfies each cell's volley at ~1/6
// of the calls and context.
function searchRules(tools) {
  const conn = tools ? [tools.exa && 'Exa', tools.tavily && 'Tavily'].filter(Boolean) : null
  return `SEARCH ECONOMY (your context is the budget — a 200K-token context ends your turn with nothing written):
  - SHARED VOLLEYS: per capability fire ONE query per facet (primary, works, fails, value, contradicts, corroborates) that covers all its open cells' diagnostic questions, and log each with every --subcap it addresses (engine.cli search --subcap A --subcap B ...). Budget: <= 8 web_search calls per capability. A cell needing its own query (its DQ shares nothing with the others) gets one extra, not six.
  - web_search (WebSearch) is the primary volley: compact results. Fire a capability's queries in PARALLEL in one turn.
  - Tavily: ALWAYS {max_results: 3, search_depth: "basic"} and include_domains when a domain fits; ONE Tavily volley per capability covers all its cells (log it with several --subcap). Never tavily_extract a whole site; extract one URL, then fetch --via-text.
  - Exa: {numResults: 3}. ONE Exa volley per capability, logged with several --subcap.
  - A tool that answers HTTP 402 / 429 / 432 or "budget exhausted" ONCE is dead for the rest of your batch: never call it again, and never log a search it did not run.
  - Clay: do NOT re-fetch the company record (PRELIM holds firmographics). Use mcp__Clay__search-contacts (companyIdentifiers ["${DOMAIN}"]) only when a cell asks who owns a function, once per batch.
${tools ? `  - MEASURED BEFORE DISPATCH: web_search ${tools.web_search ? 'answers' : 'REFUSED'}; enrichment connectors answering: ${conn.length ? conn.join(', ') : 'NONE'}.${conn.length ? '' : ' Do not call Exa or Tavily. Synthesise every cell your searches evidence; leave an unevidenced cell OPEN (no absence — one needs a connector volley) and say so in notes.'}` : `  - CONNECTOR CHECK FIRST: if neither Exa nor Tavily answers, stop after your first capability and return gate "NO_CONNECTORS".`}
  - Never sleep, poll, background a command, or re-run the gate mid-batch. Run commands in the FOREGROUND with timeout 600000.`
}

function batchPrompt(cat, caps, round, prev, tools) {
  const lc = cat.toLowerCase()
  return `You are research-${lc}-producer for DMA run ${A.run} (${A.entity || 'the entity'}), round ${round}. Work from ${ENG}; set ACT=research-${lc}-producer.
YOUR BATCH: capabilities ${caps.join(', ')} of category ${cat} — ONLY their open cells (a cell with a synthesis or declared absence is done; skip it).
${prev ? `The category's last gate: ${prev.gate}; blocking ${JSON.stringify(prev.blocking_terms || []).slice(0, 500)}. Close those for your cells.` : ''}
Your brief's shared.internal_documents (python3 -m engine.brief dispatch ${R} --category ${cat} | head -c 4000, once) lists the run's internal documents: grep them for your cells and register what bears on them with --origin internal (HYBRID run).

${SHEET}

${searchRules(tools)}

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

// PROBE BEFORE FAN-OUT: one cheap call per tool, so a dead search estate costs
// one small agent rather than a category's worth of batch agents.
const PROBE = {
  type: 'object',
  properties: { web_search: { type: 'boolean' }, exa: { type: 'boolean' }, tavily: { type: 'boolean' }, detail: { type: 'string' } },
  required: ['web_search', 'exa', 'tavily'],
}
const tools = await agent(`Connectivity probe for a DMA research run. Make exactly ONE call to each and nothing else:
  WebSearch {query: "${A.entity || DOMAIN} ${DOMAIN}"}; mcp__Exa__web_search_exa {query: "${A.entity || DOMAIN}", objective: "probe", numResults: 1}; mcp__Tavily__tavily_search {query: "${A.entity || DOMAIN}", max_results: 1}.
A tool is true only if it returned results (an HTTP 402/429/432, a "budget" or "credits" message, or a missing tool is false). Return the three booleans and a one-line detail quoting each error.`,
  { label: `${A.pillar} search probe`, phase: 'Research', schema: PROBE, model: 'haiku' })
log(`probe: web_search=${tools && tools.web_search} exa=${tools && tools.exa} tavily=${tools && tools.tavily} ${(tools && tools.detail) || ''}`)
if (!tools || (!tools.web_search && !tools.exa && !tools.tavily)) {
  return { pillar: A.pillar, categories: A.cats.map(c => ({ category: c, still_open: -1, gate: 'NO_SEARCH',
    blocking_terms: ['no search tool answered the probe'], notes: (tools && tools.detail) || 'probe returned nothing' })) }
}

const results = await pipeline(A.cats, async (cat) => {
  let prev = null
  let batches = BATCHES[cat] && BATCHES[cat].length ? BATCHES[cat] : [[`${cat} (all open capabilities)`]]
  for (let round = 1; round <= A.rounds; round++) {
    const done = await parallel(batches.map((caps, i) => () => agent(batchPrompt(cat, caps, round, prev, tools), {
      label: `${cat} r${round} b${i + 1} ${caps[0]}${caps.length > 1 ? '…' : ''}`, phase: 'Research', schema: OUT, model: 'sonnet',
    })))
    const got = done.filter(Boolean)
    const closed = got.reduce((a, r) => a + (r.cells_synthesised || 0) + (r.declared_absent || 0), 0)
    log(`${cat} r${round}: ${closed} cells closed, ${got.reduce((a, r) => a + (r.still_open || 0), 0)} open across ${batches.length} batch(es)`)
    // FAIL FAST: a round that closed nothing will not be rescued by a challenge
    // (nothing to challenge) or by a second identical round (same tools).
    if (closed === 0) {
      const why = [...new Set(got.flatMap(r => r.blocking_terms || []))].slice(0, 6)
      prev = { category: cat, still_open: got.reduce((a, r) => a + (r.still_open || 0), 0), gate: 'NO_PROGRESS',
        blocking_terms: why, notes: `round ${round} closed 0 cells; challenge and further rounds skipped` }
      log(`${cat}: no progress in round ${round} — stopping this category (${why.join('; ')})`)
      break
    }
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
  if (prev && prev.gate !== 'PASS') log(`${cat}: still failing after its round(s) — the driver's floors gate decides what happens next`)
  return prev
})

return { pillar: A.pillar, search_probe: tools, categories: results }
