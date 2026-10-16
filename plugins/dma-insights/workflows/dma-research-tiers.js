export const meta = {
  name: 'dma-research-tiers',
  description: 'DMA research as LEAN headless tiers: ONE small runner per round starts every category job (haiku collectors, sonnet orchestrator, sonnet challenger, floors gate — each a lean lane at a ~10K-token floor with its exact cost booked) and reports each phase',
  whenToUse: 'The RESEARCH stage of engine.pipeline in research_mode=tiers (a degraded run): ONE invocation for the round (every category in args.cats), args from <run>/07_qa/research_workflow.json',
  phases: [
    { title: 'Tiers', detail: 'one runner for the round: engine.tiers start every category, then wait until all are done' },
  ],
}

// WHY THIS SHAPE (owner, 2026-10-09). "Fix the context floor too, run
// collectors headless": an in-session workflow subagent opens at 73,778
// tokens and a lean headless lane at ~6.5K plus its manifest, so the WORK runs
// in lean lanes (engine.tiers -> agent_run.py lean rows). "I do not see the
// workflow": research has been a visible, persisted workflow since 2026-09-30,
// so this workflow is its face — ONE runner for the round, a handful of turns
// at the haiku tier, reporting every category's phases, dollars and gate.
// One runner, not one per category: a runner is an in-session subagent at the
// session's floor, measured at $0.12-$0.31 a round (R-IMA-20261009 P2C1), so
// sixteen of them would have spent ~$5 a round watching. The lean
// lanes are watchable live with `agent_run.py watch --log-dir <root>/agent_logs`.
//
// args: {cats: [CAT, ...], run, root, eng, round, budget, budgets, ...} (the
// invocation the driver writes for a tiers handoff).

const A = args
const CATS = (A.cats || []).map(c => String(c).toUpperCase())
const R = `--run ${A.run} --root ${A.root}`

const CAT_ROW = {
  type: 'object',
  properties: {
    category: { type: 'string' },
    state: { type: 'string' },
    gate: { type: 'string' },
    repair_cells: { type: 'number' },
    usd: { type: 'number' },
    elapsed_s: { type: 'number' },
    phases: { type: 'array', items: { type: 'string' } },
    error: { type: 'string' },
  },
  required: ['category', 'state'],
}
const OUT = {
  type: 'object',
  properties: {
    state: { type: 'string', description: 'done | running (if you stopped waiting)' },
    usd: { type: 'number' },
    categories: { type: 'array', items: CAT_ROW, description: 'the "categories" list of the last wait, verbatim' },
    error: { type: 'string' },
  },
  required: ['state'],
}

// --- PROMPTS BEGIN ---
function runnerPrompt(cats) {
  const list = cats.join(',')
  return `You run ONE round of jobs and report it; you do no research yourself. Work from ${A.eng}. Foreground, timeout 600000 on every command.
1) python3 -m engine.tiers start ${R} --category ${list}${A.round != null ? ` --round ${A.round}` : ''}
2) python3 -m engine.tiers wait ${R} --category ${list} --timeout 540
   Repeat step 2 (the same command) until the printed "state" is "done". Do nothing else between waits: no reading files, no other commands.
Then return: state, usd, and categories exactly as the last wait printed them (category, state, gate, repair_cells, usd, elapsed_s, phases, error).`
}
// --- PROMPTS END ---

if (!CATS.length) {
  return { error: 'no category in args.cats' }
}
log(`${CATS.length} categor${CATS.length === 1 ? 'y' : 'ies'} (${CATS.join(', ')}) · lean tiers round ${A.round != null ? A.round + 1 : '?'}`
    + (A.budget && A.budget.share_usd != null ? ` · $${A.budget.share_usd} of the RESEARCH envelope ($${A.budget.remaining} left)` : ''))
const res = await agent(runnerPrompt(CATS), {
  label: CATS.length === 1 ? `${CATS[0]} tiers` : `tiers · ${CATS.length} categories`,
  phase: 'Tiers', schema: OUT, model: 'haiku', effort: 'low',
})
if (!res) {
  log(`the runner did not return — the jobs may still be running; \`python3 -m engine.tiers status ${R}\` reads them`)
  return { state: 'unknown', cats: CATS }
}
for (const c of res.categories || []) {
  log(`${c.category}: ${c.state}${c.gate ? ` · gate ${c.gate}` : ''}${c.repair_cells != null ? ` · ${c.repair_cells} repair cell(s)` : ''}`
      + `${c.usd != null ? ` · $${Number(c.usd).toFixed(2)}` : ''}${c.elapsed_s != null ? ` · ${Math.round(c.elapsed_s / 60)} min` : ''}`
      + `${c.error ? ` · ${c.error}` : ''}${(c.phases || []).length ? `\n  ${c.phases.join('\n  ')}` : ''}`)
}
return res
