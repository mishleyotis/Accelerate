#!/usr/bin/env bash
# SearXNG engine health — measured, not assumed (brief §6b "engine health
# measured before and after the static IP"; §10 HALT if fewer than 3
# general-web engines respond). Runs ten FSI-shaped queries through the
# instance's JSON API and prints, per engine, how many queries it answered
# and how many it errored or sat suspended on. Usage:
#   SEARXNG_JSON_URL=http://127.0.0.1:8080 ./health.sh > before.txt
set -euo pipefail
BASE="${SEARXNG_JSON_URL:?set SEARXNG_JSON_URL to the instance's JSON API base}"
QUERIES=(
  "credit union annual report 2025 total assets"
  "bank digital banking app launch press release"
  "NCUA call report credit union members"
  "FDIC enforcement action consent order bank 2026"
  "community bank core banking conversion"
  "credit union mobile app rating members"
  "insurance carrier claims automation announcement"
  "wealth manager client portal launch"
  "bank chief digital officer appointed"
  "credit union data analytics platform case study"
)
python3 - "$BASE" "${QUERIES[@]}" <<'EOF'
import json, sys, urllib.parse, urllib.request, collections, time
base, queries = sys.argv[1], sys.argv[2:]
answered = collections.Counter(); errored = collections.Counter(); seen = set()
unresponsive = collections.Counter()
for q in queries:
    url = f"{base}/search?" + urllib.parse.urlencode({"q": q, "format": "json", "categories": "general", "language": "en-US"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.load(r)
    except Exception as e:
        print(f"query failed: {q!r}: {e}"); continue
    engines = set()
    for res in d.get("results", []):
        for e in res.get("engines", []):
            engines.add(e)
    for e in engines:
        answered[e] += 1; seen.add(e)
    for e in d.get("unresponsive_engines", []):
        name = e[0] if isinstance(e, (list, tuple)) else str(e)
        reason = e[1] if isinstance(e, (list, tuple)) and len(e) > 1 else ""
        unresponsive[(name, reason)] += 1; seen.add(name)
    print(f"{len(engines):2d} engines answered {q!r} in {time.time()-t0:.1f}s")
print("\nengine        answered/10  unresponsive")
general = 0
for e in sorted(seen):
    unr = sum(v for (n, _), v in unresponsive.items() if n == e)
    print(f"{e:13s} {answered[e]:2d}/10       {unr}")
    if answered[e] >= 5 and e not in ("wikipedia", "arxiv", "semantic scholar", "openalex", "crossref"):
        general += 1
print(f"\nresponding general-web engines (>=5/10): {general}  (HALT threshold: fewer than 3)")
for (n, r), v in sorted(unresponsive.items()):
    print(f"  {n}: {r} x{v}")
EOF
