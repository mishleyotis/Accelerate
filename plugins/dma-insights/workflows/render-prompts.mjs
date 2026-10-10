#!/usr/bin/env node
// Render the research workflow's batch and challenge prompts to files, from the
// SAME source the Workflow runtime executes (the region between the PROMPTS
// markers in dma-pillar-research.js).
//
// Why: a resumed session can lose the Workflow tool (measured 2026-10-01, Cross
// Insurance), and the only remedy was "restart the session" — an owner who
// will not restart had a run stalled at RESEARCH with nothing to do. With the
// prompts on disk the conducting session runs each one as an in-session Agent
// (same prompt, same fast tier, same tools the workflow's agents would hold),
// then runs the challenge prompt with the research-challenger agent type.
//
//   node render-prompts.mjs <research_workflow.json|reports_workflow.json> <out_dir> [round]
//
// Writes <CAT>_b<N>.md per batch and <CAT>_challenge.md per category, plus
// manifest.json: [{category, kind, file, model, subagent_type}].
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const [handoff, outDir, roundArg] = process.argv.slice(2)
if (!handoff || !outDir) {
  console.error('usage: render-prompts.mjs <research_workflow.json|reports_workflow.json> <out_dir> [round]')
  process.exit(2)
}
const round = Number(roundArg || 1)
const here = path.dirname(fileURLToPath(import.meta.url))
const doc = JSON.parse(fs.readFileSync(handoff, 'utf8'))
fs.mkdirSync(outDir, { recursive: true })

function region (file) {
  const text = fs.readFileSync(path.join(here, file), 'utf8')
  const b = text.indexOf('// --- PROMPTS BEGIN')
  const e = text.indexOf('// --- PROMPTS END')
  if (b < 0 || e < 0) {
    console.error(`PROMPTS markers missing in ${file}`)
    process.exit(3)
  }
  return text.slice(b, e)
}

// REPORTS (engine.pipeline report_mode=workflow): the same write, review and
// cross-section prompts dma-reports.js runs, one file each, so a session that
// lost the Workflow tool runs them as in-session agents (Arbor Bank,
// 2026-10-06: a restarted worker dropped the Workflow tool mid-run).
if (String(doc.workflow || '').endsWith('dma-reports.js')) {
  const reg = region('dma-reports.js')
  const manifest = []
  for (const A of doc.invocations || []) {
    // eslint-disable-next-line no-new-func
    const P = new Function('A', `${reg}\nreturn { writePrompt, reviewPrompt, crossPrompt }`)(A)
    for (const s of A.sections || []) {
      const w = path.join(outDir, `${A.report}_s${s.section}_write.md`)
      fs.writeFileSync(w, P.writePrompt(s, round))
      manifest.push({ report: A.report, section: String(s.section), kind: 'write', file: w,
                      model: 'sonnet', subagent_type: `dma-insights:${s.agent}` })
      const r = path.join(outDir, `${A.report}_s${s.section}_review.md`)
      fs.writeFileSync(r, P.reviewPrompt(s, round))
      manifest.push({ report: A.report, section: String(s.section), kind: 'review', file: r,
                      subagent_type: 'dma-insights:report-validator' })
    }
    const x = path.join(outDir, `${A.report}_cross.md`)
    fs.writeFileSync(x, P.crossPrompt(round))
    manifest.push({ report: A.report, kind: 'cross', file: x,
                    subagent_type: 'dma-insights:report-validator' })
  }
  fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 1))
  console.log(`${manifest.length} prompt(s) -> ${outDir}`)
  process.exit(0)
}

const src = fs.readFileSync(path.join(here, 'dma-pillar-research.js'), 'utf8')
const b = src.indexOf('// --- PROMPTS BEGIN')
const e = src.indexOf('// --- PROMPTS END')
if (b < 0 || e < 0) {
  console.error('PROMPTS markers missing in dma-pillar-research.js')
  process.exit(3)
}
// RESEARCH (2026-10-09, the tiers): one `collect` row per batch on the
// collector model (research-evidence-collector), one `orchestrate` row per
// category on the synthesis model (research-category-orchestrator), one
// `challenge` row per category. A session without the Workflow tool runs the
// collect rows in parallel, then the orchestrate row, then the challenge row;
// the orchestrator's `gaps` are a second collect pass by hand if it names any.
const researchRegion = src.slice(b, e)
const manifest = []
for (const inv of doc.invocations || []) {
  const A = inv
  const ENG = A.eng
  const R = `--run ${A.run} --root ${A.root}`
  const DOMAIN = A.domain || "<the entity's registrable domain, from engine.profile state>"
  const MODELS = Object.assign({ collector: 'haiku', synthesis: 'sonnet', challenge: 'sonnet' }, A.models || {})
  const CARDS = A.cards_dir || `${A.root}/briefs/research_cards`
  // eslint-disable-next-line no-new-func
  const P = new Function('A', 'ENG', 'R', 'DOMAIN', 'MODELS', 'CARDS',
    `${researchRegion}\nreturn { collectPrompt, synthPrompt, challengePrompt }`)(A, ENG, R, DOMAIN, MODELS, CARDS)
  for (const cat of inv.cats) {
    // A COLLECT ROW ONLY WHERE THERE IS COLLECTION (2026-10-10): a category
    // whose handoff lists no open batch and no collect repair gets NO
    // collector — its work is the orchestrator's (re-synthesis) or the
    // challenger's. The "(all open capabilities)" row stays only for a
    // handoff written before batches existed (no `batches` key at all).
    const hasBatches = inv.batches && Object.prototype.hasOwnProperty.call(inv.batches, cat)
    const batches = hasBatches ? (inv.batches[cat] || []) : [[`${cat} (all open capabilities)`]]
    batches.forEach((caps, i) => {
      const f = path.join(outDir, `${cat}_collect${i + 1}.md`)
      fs.writeFileSync(f, P.collectPrompt(cat, caps, round, null))
      manifest.push({ category: cat, kind: 'collect', file: f, model: MODELS.collector,
                      capabilities: caps,
                      subagent_type: 'dma-insights:research-evidence-collector' })
    })
    const rb = (inv.repair_batches || {})[cat] || []
    rb.forEach((cells, i) => {
      const f = path.join(outDir, `${cat}_repair${i + 1}.md`)
      const caps = [...new Set(cells.map(c => c.split('.').slice(0, 2).join('.')))]
      const repairs = Object.fromEntries(cells.map(c => [c, ((inv.repairs || {})[cat] || {})[c] || []]))
      fs.writeFileSync(f, P.collectPrompt(cat, caps, round, repairs))
      manifest.push({ category: cat, kind: 'collect', file: f, model: MODELS.collector,
                      capabilities: caps, cells,
                      subagent_type: 'dma-insights:research-evidence-collector' })
    })
    const o = path.join(outDir, `${cat}_orchestrate.md`)
    const resynth = ((inv.resynth_reasons || {})[cat]) || Object.fromEntries(
      Object.entries(((inv.resynth || {})[cat]) || {}).map(([c, t]) => [c, (t || []).join(', ')]))
    fs.writeFileSync(o, P.synthPrompt(cat, round, [], null, resynth))
    manifest.push({ category: cat, kind: 'orchestrate', file: o, model: MODELS.synthesis,
                    subagent_type: 'dma-insights:research-category-orchestrator' })
    const f = path.join(outDir, `${cat}_challenge.md`)
    fs.writeFileSync(f, P.challengePrompt(cat, round))
    manifest.push({ category: cat, kind: 'challenge', file: f, model: MODELS.challenge,
                    subagent_type: 'dma-insights:research-challenger' })
  }
}
fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 1))
console.log(`${manifest.length} prompt(s) -> ${outDir}`)
