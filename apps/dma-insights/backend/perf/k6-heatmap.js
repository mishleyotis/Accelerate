// k6 load test — GET /api/v1/entities/{display_id}/heatmap?zoom=subcap
//
// Probes the heaviest analytics endpoint: ~700 subcap_scores aggregated
// into a per-cell grid. SLO: p95 < 500 ms at 20 VUs × 60 s.
//
// Usage:
//   curl -c /tmp/cookies.txt -X POST \
//     "$BE/api/v1/auth/dev-login?email=ae.test@zennify.com"
//   COOKIE=$(awk '/dma_session/ {print "dma_session="$NF}' /tmp/cookies.txt)
//   BACKEND_URL=http://127.0.0.1:8000 SESSION_COOKIE=$COOKIE \
//     ENTITY_ID=wsfs-financial-corporati-0001 \
//     k6 run perf/k6-heatmap.js

import http from 'k6/http';
import { check } from 'k6';
import { Rate } from 'k6/metrics';

const BACKEND = __ENV.BACKEND_URL || 'http://127.0.0.1:8000';
const COOKIE = __ENV.SESSION_COOKIE || '';
const ENTITY = __ENV.ENTITY_ID || 'wsfs-financial-corporati-0001';

export const options = {
  vus: 20,
  duration: '60s',
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
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
  const url = `${BACKEND}/api/v1/entities/${ENTITY}/heatmap?zoom=subcap`;
  const r = http.get(url, params);
  const ok = check(r, {
    'status 200 or 404': (res) => res.status === 200 || res.status === 404,
    // 404 is acceptable in cold envs (no data); 5xx is NOT.
    'NOT 5xx': (res) => res.status < 500,
  });
  errorRate.add(ok ? 0 : 1);
}
