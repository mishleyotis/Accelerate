#!/usr/bin/env node
// Runs workflows/dma-pillar-research.js — the SAME source the Workflow runtime
// executes — against a stubbed runtime, so the governor's spend order is
// tested as code, not as a reading of the source.
//
//   node research_governor_harness.mjs <scenario.json>
//
// scenario: {args, gaps: ["CELL: term", ...] (what the round-1 orchestrator
// names), gate: "PASS"|"FAIL" (what every challenge returns)}
// Prints {calls: [{label, phase}], logs, result, spent_usd}.
//
// Each stub agent charges its tier price to budget.spent() at the runtime
// rate the handoff names, so the governor's run-envelope check sees real
// spend the way it does in a session.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const scen = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
const src = fs.readFileSync(
  path.join(here, '..', '..', '..', 'plugins', 'dma-insights', 'workflows', 'dma-pillar-research.js'), 'utf8')
const body = src.replace(/^export const meta\s*=/m, 'const meta =')

const A = scen.args
const B = A.budget || {}
const RATE = B.usd_per_runtime_token || B.usd_per_output_token || 1e-6
const T = B.tier_usd || {}
let tokens = 0
const calls = []
const logs = []

function priceOf (opts) {
  if (/collect/.test(opts.label)) return T.collector_batch || 0
  if (/orchestrate/.test(opts.label)) return T.orchestrator || 0
  if (/challenge/.test(opts.label)) return T.challenge || 0
  return 0
}

async function agent (prompt, opts) {
  calls.push({ label: opts.label, phase: opts.phase })
  tokens += priceOf(opts) / RATE
  if (/collect/.test(opts.label)) {
    return { category: A.cats[0], cells_touched: 1, evidence_registered: 1, attached: 1,
             searches_logged: 2, nothing_found: [], refused: [], status: 'DONE' }
  }
  if (/orchestrate/.test(opts.label)) {
    const first = /p1 orchestrate/.test(opts.label)
    return { category: A.cats[0], cells_synthesised: 1, declared_absent: 0,
             gaps: first ? (scen.gaps || []) : [], status: 'DONE' }
  }
  return { category: A.cats[0], still_open: scen.gate === 'PASS' ? 0 : 1,
           gate: scen.gate || 'FAIL',
           blocking_terms: scen.gate === 'PASS' ? [] : [`challenge_failed: ${A.cats[0]}.1.1`] }
}
const parallel = (fns) => Promise.all(fns.map(f => f()))
const pipeline = (items, fn) => Promise.all(items.map(fn))
const budget = { spent: () => tokens }
const log = (s) => logs.push(String(s))

// eslint-disable-next-line no-new-func
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const run = new AsyncFunction('args', 'agent', 'parallel', 'pipeline', 'budget', 'log', body)
const result = await run(A, agent, parallel, pipeline, budget, log)
console.log(JSON.stringify({ calls, logs, result, spent_usd: tokens * RATE }))
