export const meta = {
  name: 'dma-pillar-research',
  description: 'DMA research for the category in args (engine.pipeline hands ONE category per invocation): haiku evidence collectors in waves, a sonnet category orchestrator that judges completeness and writes the syntheses, a gap-only repair wave, then the independent challenge and floors gate — every wave priced against the RESEARCH envelope before it starts',
  whenToUse: 'The RESEARCH stage of engine.pipeline in research_mode=workflow: one invocation per category, all started in one message, args from <run>/07_qa/research_workflow.json',
  phases: [
    { title: 'Collect', detail: 'haiku research-evidence-collector per batch of <= batch_cells open cells (whole capabilities), fresh context each' },
    { title: 'Synthesise', detail: 'sonnet research-category-orchestrator: completeness from the gate summary + the evidence pack, every synthesis and absence, the gap list' },
    { title: 'Repair', detail: 'haiku collectors over the orchestrator\'s gap cells only, then the orchestrator again on those cells' },
    { title: 'Challenge', detail: 'independent research-challenger + floors gate per category' },
  ],
}

// WHY A WORKFLOW (owner, 2026-09-30: "research works as background tasks and
// not real persisted /workflows"). engine.pipeline is a Python process and
// cannot start a Workflow; it hands the stage to the session, which runs this
// once per category. Its agents run in-session, so they hold Exa / Tavily /
// Clay directly when the session does (no relay).
//
// WHY TIERS (owner, 2026-10-09, decided against the gold workbook — see
// engine/cost.py RESEARCH_TIERS): the gold EVIDENCE row (a verbatim span the
// fetch cache verifies, a tier from the ladder, a date the page states, the
// cells it answers) is mechanical and the ledger refuses what is wrong with
// it at the write — so collection runs on haiku, in batches of whole
// capabilities, with the cards pre-rendered to disk so the first turn reads
// them all at once. The gold SYNTHESIS row (one checkable claim, >= 120 chars
// of what was found, the triangulation step named, a ceiling that follows the
// tier table, a label the excerpts earn, a declared absence with its ladder)
// is judgement the challenge FAILs on, and a repair round re-pays a context
// floor — so synthesis and completeness stay on sonnet, once per category,
// from the evidence pack, with no search tool.
//
// WHY A GOVERNOR: "whether research runs degraded or using connectors, my
// expectation is the great batching enables the budget to be as set". The
// driver hands `budget` = {ceiling, remaining, share_usd, usd_per_output_token,
// tier_usd}; every wave is priced BEFORE it starts against (a) what is left of
// the run's envelope, converted from the output tokens the runtime can see
// (`budget.spent()` is shared by every workflow of this turn), and (b) this
// invocation's own share. A wave that does not fit is not started: the
// handback names the cells it did not reach as AT_STAGE_BUDGET, the driver
// records them, and a person raises `--stage-budget RESEARCH=<usd>` or
// narrows the scope. Degraded or connector-backed changes the search tool,
// never the shape, so the same arithmetic holds on both.
//
// args (written by engine.pipeline to <root>/07_qa/research_workflow.json):
//   {pillar, cats, batches: {cat: [[cap, ...], ...]},
//    repairs: {cat: {cell: [term, ...]}}, repair_batches: {cat: [[cell, ...], ...]},
//    models: {collector, synthesis, challenge}, batch_cells, cards_dir,
//    budget: {ceiling, spent, remaining, share_usd, share_cells, usd_per_output_token,
//             tier_usd: {collector_batch, orchestrator, challenge}, fits_envelope},
//    run, root, eng, plugin, rounds, entity, domain, degraded}

const A = args
const ENG = A.eng
const R = `--run ${A.run} --root ${A.root}`
const DOMAIN = A.domain || '<the entity\'s registrable domain, from engine.profile state>'
const MODELS = Object.assign({ collector: 'haiku', synthesis: 'sonnet', challenge: 'sonnet' }, A.models || {})
const CARDS = A.cards_dir || `${A.root}/briefs/research_cards`

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

const COLLECT_OUT = {
  type: 'object',
  properties: {
    category: { type: 'string' },
    capabilities: { type: 'array', items: { type: 'string' } },
    cells_touched: { type: 'number' },
    evidence_registered: { type: 'number' },
    attached: { type: 'number' },
    searches_logged: { type: 'number' },
    nothing_found: { type: 'array', items: { type: 'string' }, description: 'one string per cell with no citable result: "<cell>: <exact queries> -> <nearest thing found: proper noun, date or E-id>"' },
    refused: { type: 'array', items: { type: 'string' }, description: 'batch lines refused that you could not fix, verbatim rule' },
    status: { type: 'string', description: 'DONE | PARTIAL | NO_CONNECTORS | ERROR' },
    notes: { type: 'string' },
  },
  required: ['category', 'cells_touched', 'evidence_registered', 'nothing_found', 'status'],
}

const SYNTH_OUT = {
  type: 'object',
  properties: {
    category: { type: 'string' },
    cells_synthesised: { type: 'number' },
    declared_absent: { type: 'number' },
    gaps: { type: 'array', items: { type: 'string' }, description: 'one string per cell you could neither synthesise nor honestly declare absent: "<cell>: <gate term>, <gate term> — <the facet or source it still owes>"' },
    refused: { type: 'array', items: { type: 'string' } },
    status: { type: 'string', description: 'DONE | PARTIAL | ERROR' },
    notes: { type: 'string' },
  },
  required: ['category', 'cells_synthesised', 'declared_absent', 'gaps', 'status'],
}

const SHEET = `COMMAND SHEET (exact; do not run --help, orient, kg route or brief dispatch — this is everything; run from ${ENG}):
  open (turn 1, ONE Bash call): python3 -m engine.cli checkpoint ${R} --category <CAT> --position '<your batch>' && cat ${CARDS}/<CAT>/_shared.json ${CARDS}/<CAT>/<CAP>.json ...   (every card of your batch; a card names each open cell, the facets it owes — primary first — and the question per facet; a GAP-ONLY wave cats ${CARDS}/<CAT>/_repairs.json instead)
  log search:  python3 -m engine.cli search ${R} --subcap <CELL> [--subcap <CELL2> ...] --facet primary|works|fails|value|contradicts|corroborates --tool web_search|exa|tavily|clay|internal --query '<q>' --hits N --kept K --actor $ACT
  cache text:  python3 -m engine.cli fetch ${R} --url <U> --query '<question>' --via-text <file with the page text you read>   (BEFORE the evidence line that quotes it; the ledger verifies the span against this text)
  evidence:    python3 -m engine.cli evidence ${R} --subcap <CELL> [--subcap <CELL2>] --source '<publisher>' --url <U> --tier T1|T2|T3|T4|T5 --excerpt '<verbatim 50-500 chars from the cached text>' [--published <the date THE PAGE states>] [--origin public|vendor|internal] [--unverified '<why the page could not be fetched>'] --actor $ACT
               --published ONLY when the source itself states a date (2026-08-18, 2026-Q2, 2026) — 'engine.cli fetch' prints it as 'published YYYY-MM-DD (basis)', and the ledger fills it from a fetched page when you omit it; an undated page OMITS it (the row bands UNVERIFIED). Never today's date: the ledger refuses a publication date equal to the retrieval date. Omit --claim-type: the ledger derives it from the tier (T1/T2 FACT, weaker INFERENCE). The entity's own site is never T1 (annual report / press release T2, product and about pages T5); a vendor's customer page is T3 --origin vendor.
  reuse row:   python3 -m engine.cli attach ${R} --e-id E-NNN --subcap <CELL> --actor $ACT   (a fact _shared.json's prelim_evidence or a capability sibling already registered — cite it, never search for it again)
  writes:      put the capability's search, fetch, evidence and attach lines in ONE ops file (one command per line; the "python3 -m engine.cli" prefix and --run/--root may be omitted), in that order, then: python3 -m engine.cli batch ${R} --file <ops file>
               One write outside a batch costs ~10 s under the run-wide lock every collector shares; a batch is one load, one lock, one save. The result names each line's outcome and the rule a refused line broke: fix that line only and re-batch it.
TURN ECONOMY: every turn re-reads your whole context, so turns are the cost. The shape: turn 1 open; per capability turn A = ALL its searches in parallel, turn B = ONE Bash call that writes the fetched text files, the ops file and runs the batch. Finish a capability before starting the next. Never sleep, poll, background a command, or run the gate. Foreground, timeout 600000.`

const SEARCH_RULES = `SEARCH ECONOMY (your context is the budget — a 200K-token context ends your turn with nothing written):
  - web_search (WebSearch) is the primary volley: compact results. Fire a capability's queries in PARALLEL in one turn.
  - Tavily: ALWAYS {max_results: 3, search_depth: "basic"} and include_domains when a domain fits; ONE Tavily volley per capability covers all its cells (log it with several --subcap). Never tavily_extract a whole site; extract one URL, then fetch --via-text.
  - Exa: {numResults: 3}. If Exa answers HTTP 402/429 once, stop using it for this batch and use Tavily for the same query.
  - Clay: do NOT re-fetch the company record (PRELIM holds firmographics). Use mcp__Clay__search-contacts (companyIdentifiers ["${DOMAIN}"]) only when a cell asks who owns a function, once per batch.
  - CONNECTOR CHECK FIRST: you should hold Exa and Tavily (mcp__Exa__*, mcp__Tavily__*). If neither is callable, finish your first capability with WebSearch and return status "NO_CONNECTORS" naming the tools you do have.
  - Never sleep, poll, background a command, or re-run the gate mid-batch. Run commands in the FOREGROUND with timeout 600000.`

// DEGRADED (engine.pipeline sets args.degraded when the connector baseline is
// short — measured 2026-10-01, Cross Insurance: Exa 402, Tavily 432/429,
// Firecrawl 402; 2026-10-09, IMA Financial Group: Exa 402, Tavily 432). The
// shape is the same, the search tool is WebSearch, and the orchestrator
// declares absences with --enrichment-unavailable.
const DEGRADED_RULES = `DEGRADED RUN (the driver recorded enrichment_degraded; this REPLACES the connector rules):
  - Exa, Tavily and Firecrawl are unavailable for this run: do NOT call them and do NOT stop with NO_CONNECTORS.
  - WebSearch is the search tool (log as --tool web_search). Fire a capability's queries in PARALLEL in one turn; WebFetch one URL at most per cell, then fetch --via-text with the text it returned.
  - Clay search-contacts (companyIdentifiers ["${DOMAIN}"]) only when a cell asks who owns a function, once per batch.
  - A cell with nothing citable after its primary WebSearch volley goes in nothing_found with the exact queries and the nearest thing that came back; the orchestrator declares the absence with --enrichment-unavailable.
  - Never sleep, poll, background a command, or re-run the gate mid-batch. Run commands in the FOREGROUND with timeout 600000.`

// REPAIR WORK IS ROUTED, NOT INFERRED (measured 2026-10-05, a CL run, round
// 2): every blocker of 13 failing categories sat on a cell already
// synthesised or declared absent. The driver hands `repairs: {cat: {cell:
// [terms]}}` from the gate's own findings; the orchestrator hands `gaps` the
// same way after each wave; a repair wave collects for exactly those cells.
const REPAIRS = A.repairs || {}
const REPAIR_BATCHES = A.repair_batches || {}
const READ_BLOCKERS = (cat) => `python3 -c "import json;from engine import floors_gate as F;print(json.dumps(F.blocking_cells(F.read_verdict('${A.root}/07_qa','${cat}'))))"`

function collectPrompt(cat, caps, wave, repairs) {
  const lc = cat.toLowerCase()
  const act = `research-${lc}-collector`
  const repairLines = repairs && Object.keys(repairs).length
    ? `GAP-ONLY WAVE. Collect for THESE cells and no other — each with the gate term it fails or the facet it owes:\n${Object.entries(repairs).map(([c, t]) => `  ${c}: ${(t || []).join(', ')}`).join('\n')}\nPer term: primary_unfired → fire and log the primary query; volleys_incomplete → fire and log the missing facets; single_source_fact → find a second independent source (a different domain) and register it; absence_undeclared_empty / absence_unsearched → fire the primary volley and report the cell in nothing_found with the exact queries; evidence_smear → register each sibling's own evidence; challenge_failed → the challenger's reason is in floors_${cat}.json: collect the counter-source or the figure it names. THESE CELLS ARE CLOSED (synthesised or declared absent) and are NOT on the open-cell cards: read ${CARDS}/${cat}/_repairs.json instead — it carries, per cell, the gate terms and the diagnostic question per facet. Work them; "not on the cards" is expected, not a scope mismatch.`
    : ''
  return `You are research-evidence-collector for category ${cat} of DMA run ${A.run} (${A.entity || 'the entity'}), wave ${wave}. Work from ${ENG}; set ACT=${act} and pass --actor $ACT on every write (the scope refuses a synthesis or an absence from this actor — you collect, the orchestrator judges).
YOUR BATCH: capabilities ${caps.join(', ')} of category ${cat} — ONLY their open cells (a cell with a synthesis or a declared absence is done; skip it).
${repairLines}
READ FIRST (turn 1, in the open call): ${CARDS}/${cat}/_shared.json carries shared.prelim_evidence — the institution's profile, leaders, timeline and connector scans PRELIM already registered (E-ids with excerpts). A fact a PRELIM row states is cited with 'attach --e-id <E> --subcap <cell>', never searched for again (measured 2026-10-05..08: 26 PRELIM rows per run, 0-2 ever cited). On a HYBRID run shared.internal_documents lists the files to grep for your cells (register with --origin internal).
WHAT A GOLD EVIDENCE ROW IS (the ledger refuses the rest at the write): a verbatim 50-500 character span from the text you cached with fetch --via-text; the tier the ladder gives (never the entity's own site at T1); a date only when the page states it; the cells it answers; every search logged once per cell it bears on.
SPEAK THE ENTITY'S LANGUAGE: _shared.json opens with search_lexicon — how THIS sub-vertical names the customer, the product, the application and the account, the public artefacts that would show a capability, the systems that betray one, and catalogue words that do not exist in this business (not_applicable). Translate every question into those words before you search. Queries are SHORT (3-8 words: the entity's name in quotes + the thing in its own vocabulary + at most one artefact or system name). Never paste a card question into a search box.
ONE MESSAGE OF SEARCHES PER CAPABILITY (the floors gate counts volleys per cell; a cell missing one cannot be synthesised OR declared absent):
  - PRIMARY, ONE PER OPEN CELL: each cell's OWN diagnostic question, translated, as its own query, logged with --facet primary and --subcap <that cell> ALONE. A primary shared across cells is refused at the absence (primary_shared) — it never asked the cell's question.
  - FIVE FACET VOLLEYS PER CAPABILITY: works, fails, value, contradicts, corroborates — one query each, covering the capability's cells, logged once with every cell it bears on (the card's facets_owed[<facet>].log line, filled in).
  Fire all of them together in ONE message (a capability of 5 cells is 10 parallel WebSearch calls), never one per turn.
  YOUR SEARCH WINDOW IS THE CAPABILITY'S: its cells + the five facets + a little slack (the ledger prints the figure and refuses the search past it). A facet volley is fired ONCE per capability and logged with every cell; a repair wave re-fires only the facet or primary the gate names, never the whole volley. When the ledger refuses a search as over the window, write what you have for that capability and move to the next — the cells you did not reach are the next round's, not this turn's.
  YOUR LANE HAS A DOLLAR CEILING (--max-budget-usd, printed in your prompt's header by the driver when set): finish a capability's batch before starting the next, so what you wrote is kept if the ceiling stops you.
READ A PAGE THE CHEAP WAY: python3 -m engine.cli fetch ${R} --url <U> --query '<what you need from it>' fetches the raw page itself, caches it, and prints the verbatim windows to quote — no model call. Use WebFetch only when fetch reports an error (403, paywall, script-only page), then cache its text with --via-text. Never read a page just to confirm a search snippet: register from the window fetch printed.
Do not read any file under skills/, docs/ or engine/ (the sheet is complete); do not call ToolSearch or Firecrawl.

${SHEET}

${A.degraded ? DEGRADED_RULES : SEARCH_RULES}

Never invent a source, a quote, a number, a date or a person. You write no synthesis and no absence.
Return: category ${cat}, capabilities, cells_touched, evidence_registered, attached, searches_logged, nothing_found (one string per cell with nothing citable, naming THAT cell's own primary query first: "<cell>: <its primary query>; <facet queries> -> <nearest thing found for this cell>"), refused (lines you could not fix, with the rule), status DONE|PARTIAL|NO_CONNECTORS|ERROR, and one-line notes.`
}

function synthPrompt(cat, wave, collected, cells, resynth) {
  const lc = cat.toLowerCase()
  const notes = (collected || []).flatMap(c => c.nothing_found || []).slice(0, 80)
  const rs = Object.entries(resynth || {})
  const scope = cells && cells.length
    ? `YOUR CELLS this pass: ${cells.join(', ')} — the gap list of the previous pass, re-collected for. Touch no other cell.`
    : `YOUR CELLS: every open cell of ${cat} the collectors touched, plus every cell they report in nothing_found.`
  // RE-SYNTHESIS IS THIS TIER'S REPAIR (2026-10-10, R-INTERAC-20261010): a
  // failed claim, a boilerplate row or a label the evidence does not earn is
  // rewritten here — a new synthesis clears the old verdict and the
  // challenger judges the new text. No collector is paid for these.
  const resynthBlock = rs.length
    ? `\nRE-SYNTHESISE THESE CLOSED CELLS (the gate names each with its reason; rewrite the row through 'synthesise' from the evidence it already carries — tense held to the recency band, label and ceiling to the tier table, a figure, date, proper noun or E-id in What_We_Found — or, when the rows do not carry a claim, close it through 'absence'; nothing new was collected for them unless THE COLLECTORS' RETURNS below say so):\n${rs.map(([c, why]) => `  ${c}: ${why}`).join('\n')}`
    : ''
  return `You are research-category-orchestrator for category ${cat} of DMA run ${A.run} (${A.entity || 'the entity'}), pass ${wave}. Work from ${ENG}; set ACT=research-${lc}-producer and pass --actor $ACT on every write (the category's actor, so the challenge's independence is checkable). You hold no search tool: you judge what the collectors registered, and a cell whose evidence does not carry a claim is a GAP you name, never a search you run.
${scope}${resynthBlock}
TURN 1 (ONE Bash call, nothing else): cat ${CARDS}/${cat}/_pack.json — the driver rendered your whole evidence pack after the collectors returned: the gate's verdict and blocking term per cell (advisory terms never block), and per cell every registered row (E-id, excerpt, tier, published, recency, host), the facets with a logged search, the rows you may attach ('attach --e-id E --subcap <cell>') and the collectors' absence notes. Do NOT run the gate and do NOT call 'engine.brief reuse' per cell: the pack IS that read, once. Only if the pack file is missing, fall back to python3 -m engine.cli gate ${R} --category ${cat} --require-synthesis --summary and python3 -m engine.brief reuse ${R} --subcap <CELL> --json per cell.
THE COLLECTORS' ABSENCE NOTES (cells with nothing citable, their queries and the nearest thing found):
${notes.length ? notes.map(n => `  - ${n}`).join('\n') : '  (none reported)'}
WHAT A GOLD SYNTHESIS ROW IS (python3 -m engine.cli synthesis-template prints the shape once): Dominant_Claim one checkable thing in the entity's own terms; What_We_Found >= 120 chars naming figures, dates and the E-ids that carry them; Triangulation naming the step from the excerpts to the claim; Ceiling_Reasoning following the tier table (T1/T2 5.0 · T3 4.0 · T4 2.5 · T5 2.0 · single source 3.0) with Ceiling_Band; Why_It_Matters and DMA_Impact specific to this cell; the five DQ facets answered from the logged searches or 'NOT_RUN: <reason>'. Your tense follows the recency band the rows carry — UNVERIFIED is never current.
WRITE-TIME RULES the ledger refuses (no challenge round needed to learn them): FACT = two source identities on T1/T2; INFERENCE = 2+ evidence ids AND the step named (implies / suggests / consistent with …); a FACT/INFERENCE with no evidence id is refused (close the cell through 'absence' instead); a DQ_Contradicts finding needs a Contradiction_Disposition (>= 20 chars: outweighed by …, superseded by …); a Dominant_Claim that asserts an absence is not a synthesis — close it through 'absence'; every figure or year in a synthesis must appear in an excerpt registered on THAT cell (attach the row first, or drop the figure); What_We_Found names a figure, a date, a proper noun, a domain or an E-id; on 'absence', --inferable and --validation-question come together or not at all. A refused line in the batch result names the rule — fix that line, do not re-search.
DECLARED ABSENCE — ONE LINE PER CELL (2026-10-10; do not open --help, the engine source or the protocol):
  absence --subcap <CELL> --actor $ACT --from-log --note '<the nearest thing that came back for THIS cell: a proper noun, a date, an E-id, or "nothing naming it">'${A.degraded ? ' --enrichment-unavailable' : ''}
  --from-log composes the ladder (the cell's own primary as the direct rung, one of its facet volleys as the proxy rung), the proxy log and the hunt from the cell's own Search_Log — the engine holds them; you decide WHICH cells are exhausted and what came back. Every refusal still applies: a primary_shared refusal means the cell's own question was never asked — name it as "<cell>: primary_unfired — its own question" in gaps, never re-word around it. The long form (--ladder / --proxy-log / --hunted / --validation-question) stays for a cell whose hunt you must state yourself.
  A cell may be declared absent only when EVERY askable facet has a logged search on it (floors_${cat}.json "volleys_incomplete" lists the missing facets per cell): a cell with a missing facet is a GAP — name it as "<cell>: volleys_incomplete — <the missing facets>" so the repair wave fires them — never an absence. ${A.degraded ? 'This run is DEGRADED: every absence carries --enrichment-unavailable.' : 'A connector volley must also be logged on the cell.'}
WRITES: per capability ONE ops file (attach lines, then synthesise lines — 'synthesise --subcap <CELL> --json <file> --actor $ACT' — then absence lines; the "python3 -m engine.cli" prefix and --run/--root may be omitted), then python3 -m engine.cli batch ${R} --file <ops>. About eight cells a turn. Never run the gate a second time; the challenge step runs it. Do not read any file under skills/, docs/ or engine/: everything the writes need is on this sheet, and the ledger's refusal names the rule when a line is wrong.
Return: category ${cat}, cells_synthesised, declared_absent, gaps (one string per cell you could neither synthesise nor honestly declare absent: "<cell>: <gate term>, <gate term> — <the facet or source it still owes>" — this list is the repair wave's work, so name only what another search can close), refused, status DONE|PARTIAL|ERROR, one-line notes. Never score, never challenge, never submit, never promote.`
}

function challengePrompt(cat, round) {
  return `Independent challenge for category ${cat} of DMA run ${A.run} (root ${A.root}), round ${round}. Run commands from ${ENG}, foreground, long timeouts.
1) python3 -m engine.brief challenge-batch ${R} --only ${cat} --out-dir ${A.root}/briefs/wf_challenge_${cat}_r${round} --json
2) If it lists packets, work each prompt file exactly as research-challenger: judge every cell on the seven dimensions and record each verdict with python3 -m engine.cli challenge ... --actor research-challenger — put the verdict lines of a packet in ONE ops file and run python3 -m engine.cli batch ${R} --file <ops> (one lock, one save). You never challenge a cell you wrote and never search.
3) python3 -m engine.cli gate ${R} --category ${cat} --require-synthesis --summary
   It prints {gate, blocking: {term: [cells]}, advisory: [terms], repair_cells}. Read it exactly: advisory terms do not block.
Return gate (as printed), blocking_terms as "term: cell, cell" strings copied from \`blocking\` (never an advisory term), still_open = repair_cells, and one-line notes. Do not compute any other count.`
}

// --- PROMPTS END ---

const BATCHES = A.batches || {}
const BATCH_CELLS = A.batch_cells || 12

// THE ROSTER IS BOUND AT SESSION START. A session that started before the
// plugin gained an agent type cannot resolve it (measured 2026-10-09,
// R-IMA-20261009: 'dma-insights:research-evidence-collector' not found — the
// session was bound to the 74-agent roster). The work is the prompt and the
// model, not the registry entry, so the agent runs as the plain workflow
// subagent on the SAME model, and the handback says so once; every other
// error is the agent's and stays an AGENT_ERROR.
const unbound = new Set()
async function spawn(prompt, opts) {
  try {
    return await agent(prompt, opts)
  } catch (e) {
    const msg = String(e && e.message || e)
    if (opts.agentType && /agent type .* not found/i.test(msg)) {
      if (!unbound.has(opts.agentType)) {
        unbound.add(opts.agentType)
        log(`${opts.agentType} is not bound in this session (the plugin roster moved after it started) — running on model ${opts.model} as a plain subagent; restart the session to bind it`)
      }
      const { agentType, ...rest } = opts
      return agent(prompt, rest)
    }
    throw e
  }
}
const BUDGET = A.budget || null
const TIER_USD = Object.assign({ collector_batch: 0.14, orchestrator: 0.52, challenge: 0.32 }, (BUDGET && BUDGET.tier_usd) || {})
// budget.spent() counts more than output tokens (measured 2026-10-09: 8-10x
// the output figure), so the conversion is the MEASURED runtime rate the
// driver hands, never the price model's output rate.
const RATE = (BUDGET && (BUDGET.usd_per_runtime_token || BUDGET.usd_per_output_token)) || 0
const ROUNDS = BUDGET && BUDGET.fits_envelope === false ? 1 : (A.rounds || 2)

// THE GOVERNOR. `budget.spent()` is the OUTPUT tokens of every workflow in
// this turn (shared pool), converted at the handoff's blended $/output token;
// `est` is this invocation's own estimated spend by tier. A wave starts only
// when it fits BOTH what is left of the run's envelope and this invocation's
// share. `unreached` collects every cell a refused wave would have worked.
const base = budget.spent()
let est = 0
const unreached = []
const spentUsd = () => (budget.spent() - base) * RATE
function affordable(usd, what) {
  if (!BUDGET || BUDGET.remaining == null) return true
  const runLeft = BUDGET.remaining - spentUsd()
  const shareLeft = BUDGET.share_usd == null ? Infinity : BUDGET.share_usd - est
  if (usd <= runLeft + 1e-9 && usd <= shareLeft + 1e-9) return true
  log(`AT_STAGE_BUDGET: ${what} needs ~$${usd.toFixed(2)}; run envelope has ~$${Math.max(0, runLeft).toFixed(2)} left (of $${BUDGET.ceiling}), this category's share ~$${shareLeft === Infinity ? '∞' : Math.max(0, shareLeft).toFixed(2)} — not started`)
  return false
}
function chunk(items, n) { const out = []; for (let i = 0; i < items.length; i += n) out.push(items.slice(i, i + n)); return out }
function parseGaps(list) {
  const out = {}
  for (const s of list || []) {
    const m = String(s).match(/^\s*([A-Z]\d+C\d+(?:\.\d+)+(?:\.[A-Z]+\d*)?)\s*:\s*([^—]*)/)
    if (!m) continue
    out[m[1]] = m[2].split(',').map(t => t.trim()).filter(Boolean)
  }
  return out
}

log(`${A.pillar} · ${A.cats.map(c => `${c}×${(BATCHES[c] || []).length} batch(es)`).join(', ')} · collectors ${MODELS.collector}, orchestrator ${MODELS.synthesis}, up to ${ROUNDS} round(s)`
    + (BUDGET && BUDGET.ceiling != null ? ` · RESEARCH envelope $${BUDGET.spent} of $${BUDGET.ceiling} spent, share $${BUDGET.share_usd}, est $${BUDGET.estimate_usd}` : ''))

// A category is scored only when its cells are collected for, synthesised
// AND challenged — evidence with no synthesis buys nothing. So the first wave
// RESERVES the orchestrator and the challenge before it spends a dollar on a
// collector, and a share that cannot carry one batch plus that reserve hands
// the whole category back untouched (no spend) rather than half-collected.
const RESERVE = TIER_USD.orchestrator + TIER_USD.challenge
async function collectWave(cat, jobs, wave) {
  // Price the wave; run the batches that fit, in order; name the rest.
  const runnable = []
  const reserve = wave === 1 ? RESERVE : 0
  for (const j of jobs) {
    if (affordable(TIER_USD.collector_batch + reserve, `${cat} collector wave ${wave} batch ${j.caps[0]} (+ the orchestrator and challenge reserve)`)) { runnable.push(j); est += TIER_USD.collector_batch }
    else unreached.push(...(j.cells || j.caps))
  }
  if (!runnable.length) return { done: [], jobs: runnable }
  const done = await parallel(runnable.map((j, i) => () => spawn(collectPrompt(cat, j.caps, wave, j.repairs), {
    label: `${cat} w${wave} collect ${i + 1} ${j.caps[0]}${j.caps.length > 1 ? '…' : ''}`, phase: wave === 1 ? 'Collect' : 'Repair',
    schema: COLLECT_OUT, model: MODELS.collector, agentType: 'dma-insights:research-evidence-collector',
  })))
  return { done, jobs: runnable }
}

async function synthesise(cat, wave, collected, cells, resynth) {
  if (!affordable(TIER_USD.orchestrator, `${cat} orchestrator pass ${wave}`)) return null
  est += TIER_USD.orchestrator
  return spawn(synthPrompt(cat, wave, collected, cells, resynth), {
    label: `${cat} p${wave} orchestrate`, phase: wave === 1 ? 'Synthesise' : 'Repair',
    schema: SYNTH_OUT, model: MODELS.synthesis, agentType: 'dma-insights:research-category-orchestrator',
  })
}

const results = await pipeline(A.cats, async (cat) => {
  let prev = null
  // Wave 1: the open-cell batches plus the gate's repair batches (gap-only).
  let jobs = [
    ...(BATCHES[cat] || []).map(caps => ({ caps })),
    ...(REPAIR_BATCHES[cat] || []).map(cells => ({ caps: [...new Set(cells.map(c => c.split('.').slice(0, 2).join('.')))], cells,
                                                    repairs: Object.fromEntries(cells.map(c => [c, (REPAIRS[cat] || {})[c] || []])) })),
  ]
  // RE-SYNTHESIS NEEDS NO COLLECTOR (2026-10-10): a category whose only
  // work is the closed cells the gate routed to the orchestrator skips the
  // collect wave in round 1 and goes straight to the orchestrator and the
  // challenge — Interac paid seven collector lanes for exactly this.
  const RESYNTH = (A.resynth_reasons || {})[cat] || Object.fromEntries(
    Object.entries((A.resynth || {})[cat] || {}).map(([c, t]) => [c, (t || []).join(', ')]))
  const resynthOnly = !jobs.length && Object.keys(RESYNTH).length > 0
  if (!jobs.length && !resynthOnly) jobs = [{ caps: [`${cat} (cells the gate names)`], repairs: REPAIRS[cat] || {}, gateOnly: true }]
  for (let round = 1; round <= ROUNDS; round++) {
    const skipCollect = resynthOnly && round === 1
    const { done, jobs: ran } = skipCollect ? { done: [], jobs: [] } : await collectWave(cat, jobs, round)
    const got = done.filter(Boolean)
    if (ran.length && !got.length) {
      // AN AGENT ERROR IS NOT A ROUND (measured 2026-10-05): nothing ran, so
      // nothing is synthesised, challenged or retried; the driver re-hands it.
      log(`${cat} r${round}: every collector failed — stopping; the driver re-hands it`)
      return { category: cat, still_open: -1, gate: 'AGENT_ERROR', blocking_terms: ['agent_error: no collector returned'], unreached_cells: unreached, spent_est_usd: est }
    }
    if (!ran.length && !skipCollect) {
      log(`${cat} r${round}: no collector wave fit the envelope — handing back`)
      return { category: cat, still_open: -1, gate: 'AT_STAGE_BUDGET', blocking_terms: [`at_stage_budget: ${unreached.length} cell(s)/capabilit(ies) not reached`], unreached_cells: unreached, spent_est_usd: est }
    }
    if (skipCollect) log(`${cat} r1: ${Object.keys(RESYNTH).length} cell(s) routed to the orchestrator for re-synthesis — no collector paid for`)
    else log(`${cat} r${round}: ${got.reduce((a, r) => a + (r.evidence_registered || 0), 0)} evidence rows, ${got.reduce((a, r) => a + (r.cells_touched || 0), 0)} cells touched, ${got.reduce((a, r) => a + ((r.nothing_found || []).length), 0)} empty across ${ran.length} batch(es)`
        + (got.some(r => r.status === 'NO_CONNECTORS') ? ' — NO_CONNECTORS reported' : ''))
    const synth = await synthesise(cat, round, got, round === 1 ? null : Object.keys(jobs.reduce((a, j) => Object.assign(a, j.repairs || {}), {})), round === 1 ? RESYNTH : null)
    if (synth === null) {
      return { category: cat, still_open: -1, gate: 'AT_STAGE_BUDGET', blocking_terms: ['at_stage_budget: evidence collected, orchestrator pass not affordable — the syntheses are owed'], unreached_cells: unreached, spent_est_usd: est }
    }
    if (!synth) {
      log(`${cat} r${round}: the orchestrator failed — stopping; the driver re-hands it`)
      return { category: cat, still_open: -1, gate: 'AGENT_ERROR', blocking_terms: ['agent_error: orchestrator did not return'], unreached_cells: unreached, spent_est_usd: est }
    }
    log(`${cat} p${round}: ${synth.cells_synthesised || 0} synthesised, ${synth.declared_absent || 0} declared absent, ${(synth.gaps || []).length} gap(s)`)
    // A gap list the orchestrator can name is the repair wave's work, BEFORE a
    // challenge is paid for: a cell the collectors missed is collected for
    // once more and synthesised once more, then the category is challenged.
    const gaps = parseGaps(synth.gaps)
    if (round === 1 && Object.keys(gaps).length && ROUNDS > 1) {
      const cells = Object.keys(gaps)
      const rjobs = chunk(cells, BATCH_CELLS).map(cs => ({ caps: [...new Set(cs.map(c => c.split('.').slice(0, 2).join('.')))], cells: cs,
                                                            repairs: Object.fromEntries(cs.map(c => [c, gaps[c]])) }))
      const { done: rdone, jobs: rran } = await collectWave(cat, rjobs, 2)
      const rgot = rdone.filter(Boolean)
      if (rran.length && rgot.length) {
        const s2 = await synthesise(cat, 2, rgot, cells)
        if (s2) log(`${cat} p2: ${s2.cells_synthesised || 0} synthesised, ${s2.declared_absent || 0} declared absent, ${(s2.gaps || []).length} gap(s) remain`)
      }
    }
    if (!affordable(TIER_USD.challenge, `${cat} challenge r${round}`)) {
      return { category: cat, still_open: -1, gate: 'AT_STAGE_BUDGET', blocking_terms: ['at_stage_budget: syntheses written, challenge not affordable'], unreached_cells: unreached, spent_est_usd: est }
    }
    est += TIER_USD.challenge
    const c = await spawn(challengePrompt(cat, round), {
      label: `${cat} challenge r${round}`, phase: 'Challenge', schema: OUT, model: MODELS.challenge,
      agentType: 'dma-insights:research-challenger',
    })
    if (!c) {
      log(`${cat} r${round}: the challenge agent failed — stopping; the driver re-reads the gate`)
      return { category: cat, still_open: -1, gate: 'AGENT_ERROR', blocking_terms: ['agent_error: challenge did not return'], unreached_cells: unreached, spent_est_usd: est }
    }
    prev = Object.assign(c, { unreached_cells: unreached, spent_est_usd: est })
    log(`${cat} r${round}: gate ${prev.gate}, ${prev.still_open} repair cell(s), est $${est.toFixed(2)} this category`)
    if (prev.gate === 'PASS') break
    if (got.length < ran.length) {
      log(`${cat} r${round}: ${ran.length - got.length} collector(s) failed — not starting another round`)
      break
    }
    if (skipCollect) break          // a re-synthesis pass is one pass; the driver re-reads the gate
    // Round 2 collects for whatever the gate names now — read fresh from
    // floors_<cat>.json by the collector, not from agent prose.
    jobs = [{ caps: [`${cat} (cells the gate names)`], repairs: Object.fromEntries((prev.blocking_terms || []).flatMap(s => {
      const [term, cells] = String(s).split(':'); return (cells || '').split(',').map(c => c.trim()).filter(Boolean).map(c => [c, [term.trim()]])
    })), gateOnly: true }]
    if (!Object.keys(jobs[0].repairs).length) jobs[0].repairs = REPAIRS[cat] || {}
  }
  if (prev && prev.gate !== 'PASS') log(`${cat}: still failing after ${ROUNDS} round(s) — the driver's floors gate decides what happens next`)
  if (unreached.length) log(`${cat}: ${unreached.length} cell(s)/capabilit(ies) not reached inside the envelope: ${unreached.slice(0, 12).join(', ')}${unreached.length > 12 ? '…' : ''}`)
  return prev
})

return { pillar: A.pillar, categories: results, unreached_cells: unreached, spent_est_usd: est }
