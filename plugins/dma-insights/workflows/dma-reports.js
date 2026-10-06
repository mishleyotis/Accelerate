export const meta = {
  name: 'dma-reports',
  description: 'DMA report sections for ONE report (engine.pipeline hands one invocation per report): each open section written and independently reviewed on its own track, upstream blockers routed out of the loop, then one whole-report adversarial pass',
  whenToUse: 'The REPORTS stage of engine.pipeline in report_mode=workflow: one invocation per report still open, all started in one message, args from <run>/07_qa/reports_workflow.json',
  phases: [
    { title: 'Write', detail: 'one writer per open section, fresh context, its own brief only' },
    { title: 'Review', detail: 'the report-validator on that section, as soon as its writer returns' },
    { title: 'Cross-section', detail: 'one whole-report pass once every section passes; reopens only the sections it names' },
  ],
}

// WHY A WORKFLOW PER REPORT, A TRACK PER SECTION (owner, 2026-10-06: "taking
// longer than expected for just a few remainder sections ... employ /workflows
// and /agents"). Measured at Arbor Bank: REPORTS ran 430 min over 19 driver
// rounds and 137 reviews (99 non-PASS, 19 PASS->reopened). Each round handed
// WHOLE reports to two writers and both reports to one validator behind a
// barrier: a passed section waited on the slowest, a writer rewriting its
// report reopened passed sections, and over a third of the non-PASS notes named
// something no writer could supply (a probe never run, an owner decision, a
// sheet at odds with the prose), so the writer was re-sent against each until
// the stall rule ended the stage. Here a section is written and reviewed on its
// own track the moment its writer returns; a review that names an upstream
// blocker (`--upstream KIND: detail`) takes the section OUT of the loop and back
// to the conducting session, which holds the connectors and the person.
//
// args (engine.pipeline writes them to <root>/07_qa/reports_workflow.json):
//   {report, title, run, root, eng, plugin, ready,
//    sections: [{section, brief, agent}], rounds}

const A = args

// --- PROMPTS BEGIN (render-prompts.mjs evaluates this region with A in scope)
const R = `--run ${A.run} --root ${A.root}`
const K = A.report

const writePrompt = (s, round) => `You are ${s.agent} for DMA run ${A.run}, ${K} §${s.section}, round ${round}. Work from ${A.eng}, foreground commands, long timeouts.
Your brief is the file ${s.brief}: read it once, then the section's latest state with \`python3 -m engine.cli narrative state ${R} --report ${K}\` (from round 2 on, the validator's newest note on §${s.section} is in ${A.root}/07_qa/report_reviews.jsonl — read the LAST entry for this report and section, in full).
Write §${s.section} ONLY, through \`python3 -m engine.cli narrative write ${R} --report ${K} --section ${s.section} --actor ${s.agent} --json <record.json>\` (cards: one write per card with --card). Every other section belongs to someone else: rewriting one clears its verdict.
The engine refuses a body outside the template's LENGTH band, a figure no cited excerpt carries, and a citation the register does not hold. Read each refusal and fix the cause; never delete a fact to pass a check.
If the note asks for something you cannot supply from the run as it stands — a search nobody ran, a sheet that disagrees with the prose, evidence not registered, a decision only the engagement owner can make, a score not yet struck — do NOT write around it: return status BLOCKED_UPSTREAM with one upstream row per item, kind one of probe|sheet|evidence|owner|scores.
VERIFY before you return: \`narrative state ${R} --report ${K}\` must show §${s.section} as UNREVIEWED (written, awaiting review). If it does not, your write did not persist — say so.
Return report ${K}, section "${s.section}", status WRITTEN or BLOCKED_UPSTREAM, words, upstream[], and one-line notes.`

const reviewPrompt = (s, round) => `You are the report-validator for DMA run ${A.run}, ${K} §${s.section}, round ${round}. Work from ${A.eng}. You wrote none of this report.
Review §${s.section} ONLY, across the six named dimensions, against its pinned control block (\`python3 -m engine.cli narrative contract --report ${K}\`) and the sheets it reads. Open every E-id it cites.
Record exactly one verdict: \`python3 -m engine.cli narrative review ${R} --report ${K} --section ${s.section} --verdict PASS|REVISE|FAIL --actor report-validator --dimensions '<json>' --note '<80+ chars: what you checked, then every fix numbered>'\`.
When a fix needs something no writer can supply, add one \`--upstream 'KIND: what exactly is needed'\` per item (KIND: probe | sheet | evidence | owner | scores) — that takes the section out of the writer loop until it is supplied. Writer-fixable defects go in the note only; never mark a writer fix as upstream.
Do not review any other section and do not run the whole-report pass — that comes after every section passes.
Return report ${K}, section "${s.section}", verdict as recorded, upstream[] as recorded, and the note's first 200 chars.`

const crossPrompt = (round) => `You are the report-validator for DMA run ${A.run}: the WHOLE-REPORT adversarial pass on ${K} (${A.title}), round ${round}. Work from ${A.eng}. Every section has your per-section PASS.
Read the report end to end (\`python3 -m engine.cli narrative state ${R} --report ${K}\` lists the sections; the bodies are the Report_Narrative rows). Hunt what per-section review cannot: a contradiction between sections, a prose figure that drifts from the sheet it claims (re-derive it), evidence concentrated on too few sources and not disclosed, and the strongest case that the assessment is wrong. Check the other report's sections only where they state the same fact.
For each section with a real defect, withdraw its PASS: record REVISE on THAT section with a numbered note (and --upstream when the fix is upstream). Touch no section that holds. Recording nothing is the right answer when the report holds.
Return report ${K}, verdict PASS (nothing reopened) or REVISE, reopened[] (section ids you recorded REVISE on), upstream[], notes.`
// --- PROMPTS END

const UP = { type: 'array', items: { type: 'object', properties: { kind: { type: 'string' }, detail: { type: 'string' } }, required: ['kind', 'detail'] } }
const WOUT = { type: 'object', properties: { report: { type: 'string' }, section: { type: 'string' }, status: { type: 'string' }, words: { type: 'number' }, upstream: UP, notes: { type: 'string' } }, required: ['section', 'status'] }
const ROUT = { type: 'object', properties: { report: { type: 'string' }, section: { type: 'string' }, verdict: { type: 'string' }, upstream: UP, note: { type: 'string' } }, required: ['section', 'verdict'] }
const XOUT = { type: 'object', properties: { report: { type: 'string' }, verdict: { type: 'string' }, reopened: { type: 'array', items: { type: 'string' } }, upstream: UP, notes: { type: 'string' } }, required: ['verdict'] }

const ROUNDS = A.rounds || 3

// One section's track: write -> review, again only on a writer-fixable REVISE.
async function track(s, startRound) {
  for (let round = startRound; round < startRound + ROUNDS; round++) {
    const w = await agent(writePrompt(s, round), {
      label: `${K} §${s.section} write r${round}`, phase: 'Write', schema: WOUT,
      model: 'sonnet', agentType: `dma-insights:${s.agent}`,
    })
    if (!w) return { section: s.section, status: 'AGENT_ERROR', upstream: [], notes: 'writer did not return' }
    if (w.status === 'BLOCKED_UPSTREAM') return { section: s.section, status: 'UPSTREAM', upstream: w.upstream || [], notes: w.notes || '' }
    const r = await agent(reviewPrompt(s, round), {
      label: `${K} §${s.section} review r${round}`, phase: 'Review', schema: ROUT,
      agentType: 'dma-insights:report-validator',
    })
    if (!r) return { section: s.section, status: 'AGENT_ERROR', upstream: [], notes: 'reviewer did not return' }
    log(`${K} §${s.section} r${round}: ${r.verdict}${(r.upstream || []).length ? ` (${r.upstream.length} upstream)` : ''}`)
    if (r.verdict === 'PASS') return { section: s.section, status: 'PASS', upstream: [] }
    if ((r.upstream || []).length) return { section: s.section, status: 'UPSTREAM', upstream: r.upstream, notes: r.note || '' }
  }
  return { section: s.section, status: 'OPEN', upstream: [], notes: `not passed after ${ROUNDS} write/review round(s)` }
}

const sections = A.sections || []
if (!sections.length && !A.ready) {
  log(`${K}: no writable section — every open section waits on an upstream item`)
}
// No barrier: each section runs its own write/review loop concurrently.
let results = (await pipeline(sections, (s) => track(s, 1))).map((r, i) => r || { section: sections[i].section, status: 'AGENT_ERROR', upstream: [] })

// The whole-report pass needs EVERY section's result — a genuine barrier.
let cross = null
if (results.every((r) => r.status === 'PASS')) {
  phase('Cross-section')
  cross = await agent(crossPrompt(1), { label: `${K} cross-section`, phase: 'Cross-section', schema: XOUT, agentType: 'dma-insights:report-validator' })
  const reopened = new Set((cross && cross.reopened) || [])
  const again = sections.filter((s) => reopened.has(String(s.section)))
  if (cross && cross.reopened && cross.reopened.some((id) => !sections.find((s) => String(s.section) === String(id)))) {
    log(`${K}: cross-section reopened section(s) with no brief in this invocation (${cross.reopened.join(', ')}); the driver re-hands them`)
  }
  if (again.length && !(cross.upstream || []).length) {
    const fixed = (await pipeline(again, (s) => track(s, ROUNDS + 1))).filter(Boolean)
    results = results.map((r) => fixed.find((f) => f.section === r.section) || r)
  }
}

const upstream = results.flatMap((r) => (r.upstream || []).map((u) => ({ section: r.section, ...u })))
  .concat(((cross && cross.upstream) || []).map((u) => ({ section: 'cross', ...u })))
const passed = results.filter((r) => r.status === 'PASS').length
log(`${K}: ${passed}/${results.length} section(s) passed, ${upstream.length} upstream item(s)`)
return {
  report: K,
  passed,
  sections: results,
  cross: cross ? { verdict: cross.verdict, reopened: cross.reopened || [] } : null,
  upstream,
  next: upstream.length ? 'service every upstream item, then run the driver again' : 'run the driver again (it re-reads the ledger and renders when both reports are READY)',
}
