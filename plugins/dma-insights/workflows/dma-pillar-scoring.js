export const meta = {
  name: 'dma-pillar-scoring',
  description: 'DMA scoring for ONE pillar (engine.pipeline hands one invocation per pillar): scorer lanes in parallel, then that pillar\'s independent critic, then the critic\'s moves applied, until the critic passes',
  whenToUse: 'The SCORING stage of engine.pipeline in scoring_mode=workflow: one invocation per pillar, all started in one message, args from <run>/07_qa/scoring_workflow.json',
  phases: [
    { title: 'Score', detail: 'one agent per scoring brief (about 25-60 rows), fresh context each' },
    { title: 'Critique', detail: 'the pillar\'s independent scoring-critic, as soon as ITS scorers finish' },
    { title: 'Rescore', detail: 'the pillar\'s own scorer applies exactly the critic\'s --move rows' },
  ],
}

// WHY A WORKFLOW PER PILLAR (owner, 2026-10-05: "running for hours — use
// /workflows"). Measured on a 2026-10-05 run: SCORING took 294 min because the
// driver ran every pillar's scorers, then ONE critic lane over all four
// pillars, then a barrier — and the critic's moves were never handed back,
// so it named the same rows four rounds running. Here each pillar is its own
// workflow: its critic starts the moment its own scorers finish, its moves
// go straight to its own scorer, and four pillars run side by side.
//
// args (engine.pipeline writes them to <root>/07_qa/scoring_workflow.json):
//   {pillar, run, root, eng, plugin, briefs: [<scorer brief .md>, ...],
//    critic_brief: <.md or "">, rounds, solutions_brief: <.md or "">}
//
// `solutions_brief` rides on ONE invocation (the first pillar's) while the
// Solution_Catalogue / Platform_Peer_Adoption tabs are still empty: the
// technographic-scanner's solutions duty runs beside that pillar's scorers.
// The lane path ran it beside the scorers; a workflow that dropped it left
// the assessment report's preconditions shut forever (2026-10-06).

const A = args
const R = `--run ${A.run} --root ${A.root}`
const P = A.pillar
const ACT = `scoring-${P.toLowerCase()}-producer`
const OUT = {
  type: 'object',
  properties: {
    pillar: { type: 'string' },
    verdict: { type: 'string' },
    scored: { type: 'number' },
    moves: { type: 'number' },
    notes: { type: 'string' },
  },
  required: ['pillar', 'verdict'],
}

const scorerPrompt = (file) => `You are ${ACT} for DMA run ${A.run}. Work from ${A.eng}, foreground commands, long timeouts.
Your brief is the file ${file}: read it once and follow it exactly. Score EVERY row it lists through \`python3 -m engine.assessment score ${R} ... --actor ${ACT}\`.
The engine refuses a score above the row's ceiling (its own Ceiling_Band top, 2.0 on own-site-only evidence, the evidence tiers) and a stale row without ADJ_STALE: read the refusal and re-strike lower or apply ADJ_STALE. Never edit a fact out of a rationale to pass a check.
Return pillar ${P}, verdict "SCORED", scored (rows you struck), moves 0, and one-line notes.`

const criticPrompt = (round) => `You are the scoring-critic for pillar ${P} of DMA run ${A.run}, round ${round}. Work from ${A.eng}.
${A.critic_brief ? `Your brief is ${A.critic_brief}: read it first.` : ''}
Critique pillar ${P} ONLY. You struck none of its scores. ${round === 1 ? 'Round 1: re-derive a sample (at least one row per capability) from its rationale and rubric descriptor and hunt the score that flatters.' : 'Re-critique round: judge ONLY the rows you moved last round (did each land at or below its target with a rationale that now holds) and rows changed since your last verdict. Do not draw a fresh sample - a critic that re-samples every round never converges. PASS when the moved rows hold.'}
Record exactly one verdict: python3 -m engine.assessment critique ${R} --pillar ${P} --verdict PASS|FAIL --actor scoring-critic --note '<80+ chars>' and, on a FAIL, one --move CELL:TARGET:why per row you would move (the engine refuses a FAIL without them).
${round > 1 ? 'The engine ENFORCES the re-critique rule: after a FAIL, a --move may name only a row you moved before or a row re-scored since your last verdict; any other row is refused unless you give --widen \'<40+ chars naming the rule the earlier pass missed>\', which goes on the record.' : ''}
The engine already refuses band, own-site and stale breaches at write time — judge what a rule cannot.
Return pillar ${P}, verdict PASS or FAIL as recorded, moves (how many --move you gave), and one-line notes.`

const rescorePrompt = (round) => `You are ${ACT} for DMA run ${A.run}, round ${round}, RESCORE. Work from ${A.eng}.
The independent critic moved rows of pillar ${P}. List them: python3 -m engine.assessment moves ${R} --pillar ${P}
For EACH row: re-strike it at or below its "to" through python3 -m engine.assessment score ${R} --subcap <CELL> --score <to or lower> --actor ${ACT}, keeping its confidence and overlay (shown with the move), with the critic's reason at the head of the existing rationale. Touch no other row.
Return pillar ${P}, verdict "RESCORED", scored (rows re-struck), moves 0, notes.`

const solutionsPrompt = (file) => `You are the technographic-scanner for DMA run ${A.run}, carrying the SCORING stage's solutions duty. Work from ${A.eng}, foreground commands, long timeouts.
Your brief is ${file}: read it once and follow its rules exactly. Fill Solution_Catalogue (one row per platform the assessment can argue for, through engine.assessment solution) and Platform_Peer_Adoption (engine.assessment peer-adoption), DECLARING through engine.cli complete declare what cannot be examined. You score nothing and touch no pillar's rows.
Return pillar ${P}, verdict "SOLUTIONS_DONE" or "BLOCKED" (with the refusal), scored 0, moves 0, notes.`

const solutions = A.solutions_brief ? agent(solutionsPrompt(A.solutions_brief), {
  label: 'solutions duty', phase: 'Score', schema: OUT,
  agentType: 'dma-insights:technographic-scanner',
}) : null
const scored = await parallel((A.briefs || []).map((f, i) => () => agent(scorerPrompt(f), {
  label: `${P} score ${i + 1}/${A.briefs.length}`, phase: 'Score', schema: OUT, model: 'sonnet',
  agentType: `dma-insights:${ACT}`,
})))
if (solutions) {
  const sol = await solutions
  log(`solutions duty: ${sol ? sol.verdict : 'agent died'}`)
}
if ((A.briefs || []).length && !scored.filter(Boolean).length) {
  return { pillar: P, verdict: 'AGENT_ERROR', notes: 'every scorer agent failed; nothing to critique' }
}

let last = null
for (let round = 1; round <= (A.rounds || 3); round++) {
  last = await agent(criticPrompt(round), {
    label: `${P} critic r${round}`, phase: 'Critique', schema: OUT,
    agentType: 'dma-insights:scoring-critic',
  })
  if (!last) return { pillar: P, verdict: 'AGENT_ERROR', notes: 'the critic did not return' }
  log(`${P} r${round}: critic ${last.verdict}, ${last.moves || 0} move(s)`)
  if (last.verdict === 'PASS') break
  if (!last.moves) break                     // a FAIL the engine accepted always carries moves
  const rs = await agent(rescorePrompt(round), {
    label: `${P} rescore r${round}`, phase: 'Rescore', schema: OUT, model: 'sonnet',
    agentType: `dma-insights:${ACT}`,
  })
  if (!rs) return { pillar: P, verdict: 'AGENT_ERROR', notes: 'the rescore agent did not return' }
}
return last
