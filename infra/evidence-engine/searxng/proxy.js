// The one door of dmai-searxng. Dependency-free (node:http).
//   POST/GET /mcp-<token>[/...]        -> http://127.0.0.1:8001/mcp[/...]   (mcp-searxng via Supergateway)
//   GET      /searx-json/<token>/search?... -> http://127.0.0.1:8080/search?...&format=json
//   GET      /healthz                   -> 200 when both upstreams answer
//   anything else                       -> 404 (never a hint about the right path)
// The token is read from the environment once and compared with a
// constant-time check; it is never logged.
'use strict';
const http = require('http');
const crypto = require('crypto');

const TOKEN = process.env.MCP_PATH_TOKEN || '';
const PORT = parseInt(process.env.PORT || '8000', 10);
if (!TOKEN) { console.error('proxy: MCP_PATH_TOKEN missing'); process.exit(2); }

function same(a, b) {
  const ab = Buffer.from(String(a)); const bb = Buffer.from(String(b));
  return ab.length === bb.length && crypto.timingSafeEqual(ab, bb);
}

function pipe(req, res, host, port, path) {
  const headers = Object.assign({}, req.headers, { host: `${host}:${port}` });
  const up = http.request({ host, port, path, method: req.method, headers }, (ur) => {
    res.writeHead(ur.statusCode || 502, ur.headers);
    ur.pipe(res);
  });
  up.on('error', () => { res.writeHead(502); res.end('upstream unavailable'); });
  req.pipe(up);
}

function ping(host, port, path) {
  return new Promise((resolve) => {
    const r = http.get({ host, port, path, timeout: 3000 }, (ur) => { ur.resume(); resolve(ur.statusCode && ur.statusCode < 500); });
    r.on('error', () => resolve(false)); r.on('timeout', () => { r.destroy(); resolve(false); });
  });
}

http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const segs = url.pathname.split('/').filter(Boolean);
  if (url.pathname === '/healthz') {
    const ok = (await ping('127.0.0.1', 8080, '/healthz')) && (await ping('127.0.0.1', 8001, '/healthz'));
    res.writeHead(ok ? 200 : 503); return res.end(ok ? 'ok' : 'degraded');
  }
  if (url.pathname === '/') {
    res.writeHead(200, { 'content-type': 'text/plain' });
    return res.end('dmai-searxng: SearXNG (AGPL-3.0, https://github.com/searxng/searxng) behind mcp-searxng (MIT) and Supergateway (MIT). No public path.\n');
  }
  if (segs.length >= 1 && segs[0].startsWith('mcp-') && same(segs[0].slice(4), TOKEN)) {
    const rest = '/' + segs.slice(1).join('/');
    return pipe(req, res, '127.0.0.1', 8001, '/mcp' + (rest === '/' ? '' : rest) + url.search);
  }
  if (segs.length >= 3 && segs[0] === 'searx-json' && same(segs[1], TOKEN) && segs[2] === 'search' && req.method === 'GET') {
    url.searchParams.set('format', 'json');
    return pipe(req, res, '127.0.0.1', 8080, '/search?' + url.searchParams.toString());
  }
  res.writeHead(404); res.end();
}).listen(PORT, '0.0.0.0');
