export const meta = {
  name: 'dma-page-production',
  description: 'DMA page production per PAGE (engine.pipeline hands every page of a ship group that still needs work): per-surface producers in parallel, the finding-challenger and page-consolidator on the produce sections, then the surface-producer assembles; a page that failed its verdict goes straight to a repair assembly. The driver ships and promotes.',
  whenToUse: 'PAGES_A / PAGES_B of engine.pipeline in pages_mode=workflow: ONE invocation, args from <run>/07_qa/pages_workflow.json',
  phases: [
    { title: 'Fragments', detail: 'every per-surface producer of every page, side by side' },
    { title: 'Challenge', detail: 'finding-challenger on a page\'s produce sections, as soon as its fragments land' },
    { title: 'Consolidate', detail: 'page-consolidator over the fragments and the challenge report' },
    { title: 'Assemble', detail: 'the page\'s surface-producer leaves every final section file on disk' },
  ],
}

// WHY PER PAGE (owner, 2026-10-06: "speed is managed as done above: for
// scoring, reporting, promotion"). The lane path ran each phase as a barrier
// across every page in the group (all fragments, then all challenges, then
// all consolidations, then all assemblies), so the slowest producer of the
// slowest page held every other page. Here each page runs its own chain, and
// all pages of the group run side by side. Shipping and promotion stay with
// the driver (ship_page.py --claim): no workflow agent submits or promotes.
//
// args (engine.pipeline writes them to <root>/07_qa/pages_workflow.json):
//   {run, root, eng, version, connector_run, sections_dir, qa_dir,
//    pages: [{page, repair, fragments: [{agent, brief}], challenge_brief,
//             consolidate_brief, assemble_brief, last_verdict: [..]}]}

const A = args
const OUT = {
  type: 'object',
  properties: {
    page: { type: 'string' },
    status: { type: 'string' },
    files: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
  required: ['page', 'status'],
}

const common = (p) => `DMA run ${A.run}, connector run ${A.connector_run}, page ${p.page}, version ${A.version}. Work from ${A.eng}, foreground commands, long timeouts. Section files live at ${A.sections_dir}/${p.page}.*.json. You never submit, ship or promote: the driver does that after this workflow returns.`

const fragmentPrompt = (p, f) => `You are ${f.agent}. ${common(p)}
Your brief is ${f.brief}: read it and follow its role and rules exactly. Write ONLY the section file(s) your agent definition owns, to the paths in the brief's \`output\`. Other producers are writing the page's other sections at the same time: do not touch their files.
Return page ${p.page}, status "WRITTEN" or "BLOCKED" (with the reason), the files you wrote, one-line notes.`

const challengePrompt = (p) => `You are finding-challenger. ${common(p)}
Your brief is ${p.challenge_brief}: challenge ONLY the produce sections it names. You repair nothing.
Return page ${p.page}, status "CHALLENGED", and in notes your FULL challenge report (verdict per claim, with the JSON path): the consolidator reads it from your return value.`

const consolidatePrompt = (p, report) => `You are page-consolidator. ${common(p)}
Your brief is ${p.consolidate_brief}. The finding-challenger's report on this page is below; consolidate the page's section files against it.
--- CHALLENGE REPORT ---
${report || '(the challenger returned nothing: treat every produce section as unchallenged and say so)'}
--- END ---
Return page ${p.page}, status "CONSOLIDATED", and in notes the FULL consolidated changes (per section: the JSON path and its new value, or the whole section): the assembler applies them.`

const assemblePrompt = (p, consolidated) => `You are ${p.page}-surface-producer. ${common(p)}
Your brief is ${p.assemble_brief}: read it and follow its role and rules exactly.
${p.repair
    ? `REPAIR: this page failed its last verdict. Fix exactly what these reasons name, and change nothing else:\n${(p.last_verdict || []).map(r => `- ${r}`).join('\n') || '- (see last_verdict_reasons in the brief)'}`
    : 'Assemble the page from the per-surface files on disk.'}
${consolidated ? `Apply these consolidated changes, and save them verbatim to ${A.qa_dir}/consolidated_${p.page}.md for the record:\n--- CONSOLIDATED ---\n${consolidated}\n--- END ---` : ''}
Leave every final section at the path in the brief's \`output\`. Return page ${p.page}, status "ASSEMBLED" or "BLOCKED" (with the reason), the files you left, one-line notes.`

const chain = async (p) => {
  let consolidated = ''
  if (!p.repair) {
    const frags = await parallel((p.fragments || []).map(f => () => agent(fragmentPrompt(p, f), {
      label: `${p.page} ${f.agent}`, phase: 'Fragments', schema: OUT,
      agentType: `dma-insights:${f.agent}`,
    })))
    const blocked = frags.filter(f => !f || f.status === 'BLOCKED').length
    if (blocked) log(`${p.page}: ${blocked} fragment producer(s) blocked or died; the assembler writes what they did not`)
    if (p.challenge_brief) {
      const ch = await agent(challengePrompt(p), {
        label: `${p.page} challenge`, phase: 'Challenge', schema: OUT,
        agentType: 'dma-insights:finding-challenger',
      })
      const co = await agent(consolidatePrompt(p, ch && ch.notes), {
        label: `${p.page} consolidate`, phase: 'Consolidate', schema: OUT,
        agentType: 'dma-insights:page-consolidator',
      })
      consolidated = (co && co.notes) || ''
    }
  }
  return agent(assemblePrompt(p, consolidated), {
    label: `${p.page} ${p.repair ? 'repair' : 'assemble'}`, phase: 'Assemble', schema: OUT,
    agentType: `dma-insights:${p.page}-surface-producer`,
  })
}

log(`${(A.pages || []).length} page(s) for version ${A.version}: ${(A.pages || []).map(p => p.page + (p.repair ? ' (repair)' : '')).join(', ')}`)
const results = await parallel((A.pages || []).map(p => () => chain(p)))
return results.map((r, i) => r || { page: A.pages[i].page, status: 'DIED' })
