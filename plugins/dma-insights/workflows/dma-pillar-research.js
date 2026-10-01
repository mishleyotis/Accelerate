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

const SHEET = `COMMAND SHEET (exact; everything you need is in this prompt — never read engine source, SKILL.md or references, never run --help/orient/kg route; a refusal message says what to fix):
  card:        python3 -m engine.cli card ${R} --capability <CAP>            (the open cells, their questions and the facets still missing)
  log search:  python3 -m engine.cli search ${R} --subcap <CELL> [--subcap <CELL2> ...] --facet primary|works|fails|value|contradicts|corroborates --tool web_search|tavily|firecrawl|exa|clay|indeed --query '<q>' --hits N --kept K --actor $ACT
  cache text:  python3 -m engine.cli fetch ${R} --url <U> --query '<question>' [--via-text <file holding the page text a connector returned>]
  evidence:    python3 -m engine.cli evidence ${R} --subcap <CELL> --source '<publisher>' --url <U> --tier T1|T2|T3|T4|T5 --excerpt '<verbatim 50-500 chars>' [--published <the date THE PAGE states>] --claim-type FACT|INFERENCE --origin public --actor $ACT
               --published ONLY when the source itself states a date; an undated page OMITS it (the row bands UNVERIFIED). Never today's date, never a placeholder.
  reuse row:   python3 -m engine.cli attach ${R} --e-id E-NNN --subcap <CELL> --actor $ACT
  synthesise:  python3 -m engine.cli synthesise ${R} --subcap <CELL> --json <file> --actor $ACT   (JSON keys: python3 -m engine.cli synthesis-template — once per batch)
  absence:     python3 -m engine.cli absence ${R} --subcap <CELL> --actor $ACT --ladder '<json>' --proxy-log '<text>' --hunted '<text>' [--inferable '<text>' --validation-question '<q?>']
TIERS: T1 regulator / court / statutory filing / machine scan (BuiltWith-type); T2 the entity's official disclosures (its own press releases, announcements, filed statements); T3 independent third party (trade press, rankings, analysts, review sites, job boards, LinkedIn profiles); T5 marketing claims (the entity's own marketing pages, vendor puff, profile aggregators like ZoomInfo/RocketReach). FACT only at T1/T2; everything else INFERENCE.
ABSENCE CONTRACT (the engine refuses anything less): for EACH cell, every facet the card lists as missing has a logged search for that cell (one search line may carry several --subcap), the primary facet included; at least ONE of those searches ran through a connector (--tool tavily|firecrawl|exa|clay|indeed — web_search does not count); --ladder is a JSON list with rungs "direct" and "proxy" whose "query" is EXACTLY a query already logged, e.g. '[{"rung":"direct","query":"<logged q1>"},{"rung":"proxy","query":"<logged q2>"}]'; --proxy-log and --hunted >= 40 chars each, naming the exact queries, the sites/tools and the nearest thing that came back (a proper noun, a date or an E-id — the gate refuses boilerplate); a cell that cites evidence, or that a register row names, is synthesised instead.
TURN ECONOMY: every turn re-reads your whole context, so turns are the cost. Per capability aim for ~4 turns: (1) card, (2) all searches in parallel, (3) ONE Bash call writing the synthesis/absence JSON files and the ops file, (4) ONE engine.cli batch call.`

const HEALTH = Object.entries(A.connectors || {}).map(([k, v]) => `${k}: ${v}`).join('; ')
const DEAD = Object.entries(A.connectors || {}).filter(([, v]) => /^(NO_CREDITS|FAILED|EXHAUSTED)/.test(String(v))).map(([k]) => k)
// C-27 (measured 2026-10-01): Claude Code caps WebSearch PER SESSION (200 by
// default) and every workflow agent runs inside the conducting session, so
// one run's agents share it. When the session records it EXHAUSTED, Tavily is
// the primary volley.
const WS_DEAD = DEAD.includes('web_search')
const PRIMARY = WS_DEAD ? 'Tavily {max_results: 3, search_depth: "basic"} (WebSearch is EXHAUSTED for this session — do not call it)' : 'WebSearch'

const SEARCH_RULES = `CONNECTORS — measured by the session before launch: ${HEALTH || 'not probed: try each once'}.${DEAD.length ? ` Do NOT call ${DEAD.join(', ')}.` : ''}
FIRST TURN: load your tools once — ToolSearch "select:WebSearch,mcp__Tavily__tavily_search,mcp__Firecrawl__firecrawl_search,mcp__Firecrawl__firecrawl_scrape,mcp__Clay__search-contacts" — then run the first card in the same turn.
SEARCH ECONOMY (your context is the budget — a 200K-token context ends your turn with nothing written):
  - ${PRIMARY} is the primary volley: compact results. Fire a capability's queries in PARALLEL in one turn. If WebSearch answers "Web search was not performed … web search budget", it is exhausted for the whole session: use Tavily as primary from then on.
  - NAME COLLISIONS: put the entity's name in quotes ("${A.entity || 'the entity'}") and add the domain ${DOMAIN} or the HQ city to every query; on Tavily set exact_match: true. Measured 2026-10-01: unquoted "Cross Insurance" queries returned A.T. Cross pens, CBP "CROSS" rulings and Wikipedia "Cross" — an absence over an off-topic result set is not an absence.
  - EACH ABSENCE IS ITS OWN: --hunted names that cell's own query and its own nearest hit; three cells closed with the same --hunted text read as a template and the connector refuses them (CG-15).
  - ONE connector volley per capability covers all its cells (log it with several --subcap): Tavily {max_results: 3, search_depth: "basic"}, else mcp__Firecrawl__firecrawl_search {limit: 3} (--tool firecrawl) — skipping any family the CONNECTORS line marks NO_CREDITS/FAILED. A 402/quota answer means that family is dead for the batch. A 429 is a TRANSIENT rate limit: do not switch to a dead family — carry on with your WebSearch volleys and re-issue the same connector call ONCE in a later turn (it usually clears); a call that 429s twice is logged with --outcome RATE_LIMITED and the cell stays open for the next round rather than being declared absent.
  - A page that answers 403/999 to engine.cli fetch or WebFetch (the entity's own site sits behind Cloudflare): read it with mcp__Firecrawl__firecrawl_scrape {url, formats: ["query"], queryOptions: {prompt: "<what the cell needs>", mode: "directQuote"}} — verbatim quotes only, never the whole page into your context — write the quotes to a file in your WORKDIR, then engine.cli fetch --url <U> --via-text <file> so the excerpt can be verified. At most one scrape per capability.
  - Clay returns ~15 KB of company data per call: at most ONE call per batch, and only when a cell asks who owns a function — mcp__Clay__search-contacts {companyIdentifiers: ["${DOMAIN}"], dslQuery: 'select from people where headline contains ("chief", "director", "<function word>") limit 10'} (the field is headline; job_title/title do not exist). The PRELIM leaders below usually answer it already.
  - CONNECTOR CHECK: if no connector tool (Tavily, Firecrawl, Exa, Clay) is callable at all, stop after your first capability and return gate "NO_CONNECTORS" naming the tools you do have: no cell can be declared absent without one.
  - Never sleep, poll, background a command, or re-run the gate mid-batch. Run commands in the FOREGROUND with timeout 600000.`

const BACKGROUND = A.background ? `BACKGROUND FROM PRELIM (already researched — use it, do not re-find it):\n${A.background}\n` : ''

// C-11 (measured 2026-10-01, Cross Insurance): the internal-documents step
// ran in every batch agent of a PUBLIC run — one turn and ~4 KB of brief per
// batch, 79 batches, for a list that is empty by construction.
const INTERNAL = ['HYBRID', 'INTERNAL'].includes(String(A.mode || '').toUpperCase()) || !A.mode

function batchPrompt(cat, caps, round, prev, idx) {
  const lc = cat.toLowerCase()
  return `You are research-${lc}-producer for DMA run ${A.run} (${A.entity || 'the entity'}, domain ${DOMAIN}), round ${round}. Work from ${ENG}; set ACT=research-${lc}-producer.
YOUR BATCH: capabilities ${caps.join(', ')} of category ${cat} — ONLY their open cells (a cell with a synthesis or declared absence is done; skip it).
${prev ? `The category's last gate: ${prev.gate}; blocking ${JSON.stringify(prev.blocking_terms || []).slice(0, 500)}. Close those for your cells.\n` : ''}${INTERNAL ? `Your brief's shared.internal_documents (python3 -m engine.brief dispatch ${R} --category ${cat} | head -c 4000, once) lists the run's internal documents: grep them for your cells and register what bears on them with --origin internal (${A.mode} run).\n` : ''}WORKDIR for your JSON, page-text and ops files: ${A.root}/wf/${cat}_r${round}_b${idx} (mkdir -p it once; a run-root path is auto-approved and survives in the snapshot).
${BACKGROUND}
${SHEET}

${SEARCH_RULES}

LOOP, one capability at a time: card -> parallel searches (primary + the missing facets + one connector volley, one turn) -> cache page text (fetch / --via-text) -> write the synthesis/absence JSON files and the ops file -> ONE engine.cli batch call for the whole capability. Finish a capability before starting the next.
WRITES GO THROUGH engine.cli batch (mandatory): put every search log, evidence, attach, synthesise and absence line for the capability in one ops file — one command per line, (the "python3 -m engine.cli" prefix and --run/--root may be omitted) — then run: python3 -m engine.cli batch ${R} --file <ops file>
One write outside a batch costs ~10 s under the run-wide lock that every researcher shares; a batch is one load, one lock, one save. The batch reports each command's result; fix and re-batch only the refused lines. Order inside the file matters: search logs, then evidence, then attach, then synthesise/absence.
Never invent a source, a quote, a number or a person. Pass --actor $ACT on every write.
Return: category ${cat}, cells_synthesised, declared_absent, still_open (your batch), searches_logged, evidence_registered, gate "BATCH_DONE", blocking_terms [] and one-line notes (name any refusal you could not clear, verbatim).`
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
  // An EXPLICITLY empty batch list means every cell is closed: the category
  // owes only its challenge and floors gate (C-29, measured 2026-10-01 — P3C4
  // was handed `batches: []` and the fallback spent a research agent on it).
  const closed = Array.isArray(BATCHES[cat]) && BATCHES[cat].length === 0
  let batches = BATCHES[cat] && BATCHES[cat].length ? BATCHES[cat] : [[`${cat} (all open capabilities)`]]
  for (let round = 1; round <= A.rounds; round++) {
    const done = (closed && round === 1) ? [] : await parallel(batches.map((caps, i) => () => agent(batchPrompt(cat, caps, round, prev, i + 1), {
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
    if (closed || (open === 0 && got.length === batches.length)) batches = [[`${cat} (cells the gate names)`]]
    else batches = batches.filter((_, i) => !done[i] || (done[i].still_open || 0) > 0)
    if (!batches.length) batches = [[`${cat} (cells the gate names)`]]
  }
  if (prev && prev.gate !== 'PASS') log(`${cat}: still failing after ${A.rounds} round(s) — the driver's floors gate decides what happens next`)
  return prev
})

return { pillar: A.pillar, categories: results }
