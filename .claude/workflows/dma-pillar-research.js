export const meta = {
  name: 'dma-pillar-research',
  description: 'One DMA pillar: its 4 category researchers in parallel, each challenged and floors-gated, looping until the gate passes',
  whenToUse: 'Research one pillar of a DMA run as a persisted, resumable workflow (one per pillar)',
  phases: [
    { title: 'Research', detail: 'category producer works its cells capability by capability, holding the connectors itself' },
    { title: 'Challenge', detail: 'independent challenger + floors gate per category' },
  ],
}

const A = args
const ENG = A.eng
const R = `--run ${A.run} --root ${A.root}`

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

function researchPrompt(cat, round, prev) {
  const lc = cat.toLowerCase()
  return `You are research-${lc}-producer for DMA run ${A.run} (root ${A.root}), round ${round}.
Work ONLY category ${cat}. Run every command from ${ENG} in the FOREGROUND with a long timeout (600000); never end your turn to wait.
Your role file is ${A.plugin}/agents/research/categories/research-${lc}-producer.md and the protocol is ${ENG}/references/RESEARCH-PROTOCOL.md — read the role file, and only the sections of the protocol you need.

Start:
  python3 -m engine.cli checkpoint ${R} --category ${cat} --position "workflow round ${round}"
  python3 -m engine.brief dispatch ${R} --category ${cat}${round > 1 ? ' --with-handback' : ''}
${prev ? `Last round ended: gate ${prev.gate}; blocking ${JSON.stringify(prev.blocking_terms).slice(0, 600)}. Fix those first.` : ''}

Work a CAPABILITY at a time: python3 -m engine.cli card ${R} --capability <cap>. Fire all owed facets for it as PARALLEL searches in one turn; log each (python3 -m engine.cli search ${R} --subcap <each answered cell> --facet <f> --tool <tool> --query '...' --hits N --kept K), chaining with && in one Bash call.
YOU HOLD THE ENRICHMENT CONNECTORS directly (this is an in-session workflow agent, not a headless lane): Exa (mcp__Exa__web_search_exa / web_fetch_exa), Tavily (mcp__Tavily__tavily_search / tavily_extract), Clay (mcp__Clay__search-companies with dslQuery 'select from companies where domain = "swbc.com" limit 1', mcp__Clay__search-contacts with companyIdentifiers ["swbc.com"]) — load schemas with ToolSearch. Fire connector volleys yourself (log with --tool exa|tavily|clay) instead of emitting search_requests; if Exa refuses for credits (402), use Tavily for the same query. Every cell needs at least one connector volley besides web_search before it can be declared absent.
Internal evidence (HYBRID): ${A.root}/01_intake/SWBC_Context_for_DMA_2026-09.md — register what bears on your cells with --origin internal.
Evidence: cache connector text first (python3 -m engine.cli fetch ${R} --url <U> --via-text <file>), then python3 -m engine.cli evidence ${R} ... --actor research-${lc}-producer; reuse other lanes' rows with engine.cli attach.
Synthesis: python3 -m engine.cli synthesis-template shows the record; python3 -m engine.cli synthesise ${R} --subcap X --json <file> --actor research-${lc}-producer. An honestly empty, fully searched cell closes with python3 -m engine.cli absence (see --help).
Pass --actor research-${lc}-producer on every write. Never invent a source, a quote, a number or a person.
Stop when every cell is synthesised or declared absent, or when the search window reports 0 remaining. Then run python3 -m engine.cli gate ${R} --category ${cat} and return its verdict and blocking terms.`
}

function challengePrompt(cat, round) {
  return `Independent challenge for category ${cat} of DMA run ${A.run} (root ${A.root}), round ${round}. Run commands from ${ENG}, foreground, long timeouts.
1) python3 -m engine.brief challenge-batch ${R} --only ${cat} --out-dir ${A.root}/briefs/wf_challenge_${cat}_r${round} --json
2) If it lists packets, work each prompt file exactly as research-challenger: judge every cell on the seven dimensions and record each verdict with python3 -m engine.cli challenge ... --actor research-challenger. You never challenge a cell you wrote and never search.
3) python3 -m engine.cli gate ${R} --category ${cat} --require-synthesis
Return the gate verdict, its blocking terms, and how many cells are still open.`
}

log(`Pillar ${A.pillar}: ${A.cats.join(', ')} · up to ${A.rounds} round(s) each`)

const results = await pipeline(A.cats, async (cat) => {
  let prev = null
  for (let round = 1; round <= A.rounds; round++) {
    const r = await agent(researchPrompt(cat, round, prev), {
      label: `${cat} research r${round}`, phase: 'Research', schema: OUT, model: 'sonnet',
    })
    const c = await agent(challengePrompt(cat, round), {
      label: `${cat} challenge r${round}`, phase: 'Challenge', schema: OUT, model: 'sonnet',
      agentType: 'dma-insights:research-challenger',
    })
    prev = c || r
    if (prev) log(`${cat} r${round}: gate ${prev.gate}, ${prev.still_open} open`)
    if (prev && prev.gate === 'PASS') break
  }
  return prev
})

return { pillar: A.pillar, categories: results }
