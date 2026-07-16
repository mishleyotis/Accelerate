// k6 load test — GET /api/v1/dashboard
//
// SLO: p95 latency < 800 ms at 50 VUs × 30 s sustained,
//      error rate < 1 %.
//
// Usage:
//   curl -c /tmp/cookies.txt -X POST \
//     "$BE/api/v1/auth/dev-login?email=ae.test@zennify.com"
//   COOKIE=$(awk '/dma_session/ {print "dma_session="$NF}' /tmp/cookies.txt)
//   BACKEND_URL=http://127.0.0.1:8000 SESSION_COOKIE=$COOKIE \
//     k6 run perf/k6-dashboard.js

import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BACKEND = __ENV.BACKEND_URL || 'http://127.0.0.1:8000';
const COOKIE = __ENV.SESSION_COOKIE || '';

export const options = {
  vus: 50,
  duration: '30s',
  thresholds: {
    // BLOCKING SLOs — k6 exits non-zero on breach.
    http_req_duration: ['p(95)<800'],
    http_req_failed: ['rate<0.01'],
    'errors{type:5xx}': ['rate<0.01'],
  },
};

const errorRate = new Rate('errors');

export default function () {
  const params = {
    headers: { Accept: 'application/json' },
    cookies: COOKIE
      ? { dma_session: COOKIE.replace(/^dma_session=/, '') }
      : undefined,
  };
  const r = http.get(`${BACKEND}/api/v1/dashboard?scope=all`, params);
  const ok = check(r, {
    'status 200': (res) => res.status === 200,
    'response is JSON object': (res) => {
      try { return typeof res.json() === 'object'; }
      catch (_) { return false; }
    },
    'response has active_runs key': (res) => {
      try { return 'active_runs' in res.json(); }
      catch (_) { return false; }
    },
  });
  if (!ok) {
    errorRate.add(1, { type: r.status >= 500 ? '5xx' : '4xx' });
  } else {
    errorRate.add(0);
  }
}
