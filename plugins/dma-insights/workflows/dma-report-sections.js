export const meta = {
  name: 'dma-report-sections',
  description: 'DMA report writing per SECTION (engine.pipeline hands every open section of both reports): one producer per section in parallel, its independent validator the moment it lands, a revise loop per section, then one whole-report cross-check per report',
  whenToUse: 'The REPORTS stage of engine.pipeline in reports_mode=workflow: ONE invocation, args from <run>/07_qa/reports_workflow.json',
  phases: [
    { title: 'Write', detail: 'one producer per open section, fresh context each' },
    { title: 'Validate', detail: 'that section\'s independent report-validator, as soon as it is written' },
    { title: 'Cross-check', detail: 'per report, once all its sections are READY: cross-section contradictions and prose figures vs sheets' },
  ],
}

// WHY PER SECTION (owner, 2026-10-06: "start /workflows to enable
// the report go faster ... future runs always spin /agents"). The lane path
// gave each report ONE producer that wrote every open section in turn, then
// ONE validator that reviewed every section of both reports in turn: two
// serial chains, ~45 min a round, three rounds. Here every open section is
// written and validated on its own chain, side by side, and a section that
// comes back REVISE is rewritten by its producer with the validator's note.
//
// args (engine.pipeline writes them to <root>/07_qa/reports_workflow.json):
//   {run, root, eng, rounds,
//    sections: [{report, section, heading, producer, brief, validator_brief}]}

const A = args
const R = `--run ${A.run} --root ${A.root}`
const ROUNDS = A.rounds || 2
const OUT = {
  type: 'object',
  properties: {
    report: { type: 'string' },
    section: { type: 'string' },
    verdict: { type: 'string' },
    notes: { type: 'string' },
  },
  required: ['report', 'section', 'verdict'],
}

const writePrompt = (s, round) => `You are ${s.producer} for DMA run ${A.run}. Work from ${A.eng}, foreground commands, long timeouts.
Your brief is ${s.brief}: read it once for the templates, rules and command sheet, and follow its rules exactly.
Write ONLY section ${s.section} ("${s.heading}") of report ${s.report}. Other agents are writing the other sections at the same time: do not write, rewrite or review any other section.
${round > 1 ? `This is revision round ${round}. Read the validator's note for this section first: python3 -m engine.cli narrative state ${R} --report ${s.report} — fix exactly what it names.` : 'If the section already carries a validator note (narrative state), fix what it names.'}
Write it through: python3 -m engine.cli narrative write ${R} --report ${s.report} --section ${s.section} --actor ${s.producer} --body-file <path> [--card <PREFIX>NN]. Read every refusal and fix the cause; never strip a fact to pass a check. Write the body file under ${A.root}/07_qa/agent_scratch/, never inside the repository.
Return report ${s.report}, section ${s.section}, verdict "WRITTEN" (or "BLOCKED" with the refusal), one-line notes.`

const validatePrompt = (s, round) => `You are report-validator for DMA run ${A.run}. Work from ${A.eng}.
${s.validator_brief ? `Your brief is ${s.validator_brief}: read it for the templates and the six dimensions.` : ''}
Review ONLY section ${s.section} ("${s.heading}") of report ${s.report}, round ${round}. You did not write it. Judge the six named dimensions against the sheets and the cited E-ids, and check every figure in the prose against the workbook.
Record exactly one verdict: python3 -m engine.cli narrative review ${R} --report ${s.report} --section ${s.section} --verdict PASS|REVISE|FAIL --actor report-validator --note '<what holds, and on REVISE exactly what to fix>' [--dimensions '{...}'].
Return report ${s.report}, section ${s.section}, verdict as recorded (PASS, REVISE or FAIL), one-line notes.`

const crossPrompt = (report, secs) => `You are report-validator for DMA run ${A.run}. Work from ${A.eng}.
Every open section of report ${report} has now passed its own review. Run the WHOLE-REPORT adversarial pass on ${report} only: cross-section contradictions, prose figures that drift from the sheets, the strongest case that the assessment is wrong, evidence concentrated on too few sources. Read the report with python3 -m engine.cli narrative state ${R} --report ${report} and the section bodies it points to.
If a section breaks on that pass, re-record its verdict as REVISE through python3 -m engine.cli narrative review ${R} --report ${report} --section <ID> --verdict REVISE --actor report-validator --note '<the contradiction or drift, exactly>'. Otherwise record nothing.
Sections rewritten this run: ${secs.join(', ')}.
Return report ${report}, section "ALL", verdict "PASS" if nothing reopened else "REVISE", notes naming any section reopened.`

const chain = async (s) => {
  let v = null
  for (let round = 1; round <= ROUNDS; round++) {
    const w = await agent(writePrompt(s, round), {
      label: `${s.report} §${s.section} write r${round}`, phase: 'Write', schema: OUT,
      agentType: `dma-insights:${s.producer}`,
    })
    if (!w || w.verdict === 'BLOCKED') return w
    v = await agent(validatePrompt(s, round), {
      label: `${s.report} §${s.section} validate r${round}`, phase: 'Validate', schema: OUT,
      agentType: 'dma-insights:report-validator',
    })
    if (v && v.verdict === 'PASS') return v
  }
  return v
}

const byReport = {}
for (const s of A.sections || []) (byReport[s.report] = byReport[s.report] || []).push(s)
log(`${(A.sections || []).length} open section(s) across ${Object.keys(byReport).length} report(s), up to ${ROUNDS} write/validate round(s) each`)

const results = await parallel(Object.entries(byReport).map(([report, secs]) => async () => {
  const done = await parallel(secs.map(s => () => chain(s)))
  const open = done.map((d, i) => (d && d.verdict === 'PASS') ? null : secs[i].section).filter(Boolean)
  if (open.length) {
    log(`${report}: section(s) ${open.join(', ')} not PASS after ${ROUNDS} round(s); cross-check skipped`)
    return { report, sections: done, cross: null, open }
  }
  const cross = await agent(crossPrompt(report, secs.map(s => s.section)), {
    label: `${report} cross-check`, phase: 'Cross-check', schema: OUT,
    agentType: 'dma-insights:report-validator',
  })
  return { report, sections: done, cross, open: [] }
}))
return results
