// k6 load test — POST /api/v1/rag/answer (offline / mocked Vertex)
//
// SLO: p95 < 3000 ms at 5 VUs × 60 s. The 3s budget assumes Vertex
// offline-mode fallback OR a warm synthesis cache; live Vertex Pro
// can blow past 3s and that's by design (use cache_hit gate instead).
//
// Usage:
//   curl -c /tmp/cookies.txt -X POST \
//     "$BE/api/v1/auth/dev-login?email=ae.test@zennify.com"
//   COOKIE=$(awk '/dma_session/ {print "dma_session="$NF}' /tmp/cookies.txt)
//   BACKEND_URL=http://127.0.0.1:8000 SESSION_COOKIE=$COOKIE \
//     k6 run perf/k6-rag-answer.js

import http from 'k6/http';
import { check } from 'k6';
import { Rate } from 'k6/metrics';

const BACKEND = __ENV.BACKEND_URL || 'http://127.0.0.1:8000';
const COOKIE = __ENV.SESSION_COOKIE || '';

export const options = {
  vus: 5,
  duration: '60s',
  thresholds: {
    http_req_duration: ['p(95)<3000'],
    http_req_failed: ['rate<0.05'],   // 5% fail tolerance — RAG offline mode
                                       // may legitimately return 503 if Vertex
                                       // creds are completely absent
  },
};

const errorRate = new Rate('errors');

// 8 representative questions — exercises the synthesis cache (first
// pass = miss → synthesize; subsequent passes = hit → 0 tokens).
const QUESTIONS = [
  "What is the entity's biggest gap?",
  "Which pillar should we prioritise?",
  "Summarise the entity's strengths.",
  "What are the top 3 risks?",
  "Compare this entity to peer median.",
  "Which platform offerings are highest fit?",
  "Are there any data freshness concerns?",
  "What's the maturity trend over time?",
];

export default function () {
  const q = QUESTIONS[Math.floor(Math.random() * QUESTIONS.length)];
  const body = JSON.stringify({
    question: q,
    page_context: { route: "/clients" },
    response_style: "concise",
    max_paragraphs: 3,
    require_citations: false,
  });
  const params = {
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    cookies: COOKIE
      ? { dma_session: COOKIE.replace(/^dma_session=/, '') }
      : undefined,
  };
  const r = http.post(`${BACKEND}/api/v1/rag/answer`, body, params);
  const ok = check(r, {
    'status 200 or 503': (res) => res.status === 200 || res.status === 503,
    'NOT 4xx': (res) => res.status < 400 || res.status === 503,
  });
  errorRate.add(ok ? 0 : 1);
}
