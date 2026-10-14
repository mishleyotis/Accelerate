#!/usr/bin/env node
// Runs workflows/dma-pillar-scoring.js — the SAME source the Workflow runtime
// executes — against a stubbed runtime (see research_governor_harness.mjs).
//
//   node scoring_governor_harness.mjs <scenario.json>
//
// scenario: {args, critic: ["FAIL", "PASS"] (verdict per round)}
// Each stub agent charges the price the handoff names for it to
// budget.spent() at the handoff's runtime rate.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const scen = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
const src = fs.readFileSync(
  path.join(here, '..', '..', '..', 'plugins', 'dma-insights', 'workflows', 'dma-pillar-scoring.js'), 'utf8')
const body = src.replace(/^export const meta\s*=/m, 'const meta =')

const A = scen.args
const B = A.budget || {}
const RATE = B.usd_per_runtime_token || 7.5e-6
const T = B.tier_usd || {}
let tokens = 0
let round = 0
const calls = []
const logs = []

function priceOf (opts) {
  const m = opts.label.match(/score (\d+)\//)
  if (m) return (B.brief_usd || [])[Number(m[1]) - 1] || 0
  if (/critic/.test(opts.label)) return T.critic || 0
  if (/rescore/.test(opts.label)) return T.rescore || 0
  if (/solutions/.test(opts.label)) return T.solutions || 0
  return 0
}

async function agent (prompt, opts) {
  calls.push({ label: opts.label, phase: opts.phase })
  tokens += priceOf(opts) / RATE
  if (/critic/.test(opts.label)) {
    const v = (scen.critic || ['PASS'])[round++] || 'PASS'
    return { pillar: A.pillar, verdict: v, moves: v === 'FAIL' ? 2 : 0 }
  }
  return { pillar: A.pillar, verdict: 'SCORED', scored: 60, moves: 0 }
}
const parallel = (fns) => Promise.all(fns.map(f => f()))
const budget = { spent: () => tokens }
const log = (s) => logs.push(String(s))

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const run = new AsyncFunction('args', 'agent', 'parallel', 'budget', 'log', body)
const result = await run(A, agent, parallel, budget, log)
console.log(JSON.stringify({ calls, logs, result, spent_usd: tokens * RATE }))
