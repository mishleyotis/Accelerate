# Local end-to-end transcript (fixture site, no network)

Producer (research-evidence-collector / enrichment-web-specialist):
```
research_brief(run_id='R-demo', entity={legal_name, domains, aliases}, facet='value',
  questions=['How many members does the credit union serve and how fast is membership growing?'],
  max_cards=3, provenance='standard', reference_date='2026-10-10')
```

### research_brief → cards (standard provenance) + coverage
```json
{
 "cards": [
  {
   "card_id": "EV-97cad1e7",
   "item": {
    "source_name": "www.example-fcu.test — Example Federal Credit Union reports record membership growth in 2025",
    "source_url": "https://www.example-fcu.test/news/2026-03-03-membership-growth.html",
    "excerpt": "ANYTOWN, ST, March 3, 2026 — Example Federal Credit Union today announced its results for the year ended December 31, 2025.",
    "tier": "T2",
    "published_date": "2026-03-03",
    "claim_type": "FACT",
    "linked_subcap_ids": [],
    "origin": "producer"
   },
   "provenance": {
    "url_status": "live",
    "recency": "CURRENT",
    "source_type_hint": "entity_owned",
    "entity_match": "confirmed",
    "origin_cluster": "OC-8560d25e",
    "syndication_count": 3,
    "context_handle": "CTX-58507954",
    "ladder_rung": "entity_site",
    "via": "searxng",
    "published_basis": "meta",
    "relevance": 0.6,
    "host": "www.example-fcu.test"
   }
  },
  {
   "card_id": "EV-281c6658",
   "item": {
    "source_name": "herald.example.test — Example Herald",
    "source_url": "https://herald.example.test/2026/08/15/cu-grows",
    "excerpt": "Example Federal Credit Union now serves 198,000 members across 14 branches, the Anytown lender said on Friday.",
    "tier": "T3",
    "published_date": "2026-08-15",
    "claim_type": "INFERENCE",
    "linked_subcap_ids": [],
    "origin": "producer"
   },
   "provenance": {
    "url_status": "live",
    "recency": "CURRENT",
    "source_type_hint": "other",
    "entity_match": "probable",
    "origin_cluster": "OC-efb68544",
    "syndication_count": 1,
    "context_handle": "CTX-3860b76e",
    "ladder_rung": "other",
    "via": "searxng",
    "published_basis": "meta",
    "relevance": 0.562,
    "host": "herald.example.test"
   }
  },
  {
   "card_id": "EV-30704dc7",
   "item": {
    "source_name": "regulator.example.test — Example Regulator",
    "source_url": "https://regulator.example.test/data/2026q2",
    "excerpt": "Example Federal Credit Union reported total assets of $3.1 billion and 212,000 members at June 30, 2026, according to the quarterly call report.",
    "tier": "T3",
    "published_date": "2026-09-01",
    "claim_type": "INFERENCE",
    "linked_subcap_ids": [],
    "origin": "producer"
   },
   "provenance": {
    "url_status": "live",
    "recency": "CURRENT",
    "source_type_hint": "other",
    "entity_match": "probable"…
```

Producer registers the card UNCHANGED (only the cells it decided are added):
```
register_evidence(run_id='<run>', item={"source_name": "www.example-fcu.test — Example Federal Credit Union reports record membership growth in 2025", "source_url": "https://www.example-fcu.test/news/2026-03-03-membership-growth.html", "excerpt": "ANYTOWN, ST, March 3, 2026 — Example Federal Credit Union today announced its results for the year ended December 31, 2025.", "tier": "T2", "published_date": "2026-03-03", "claim_type": "FACT", "linked_subcap_ids": ["P2C1.1"], "origin": "producer"})
```

A lean lane's batch line for the same card (`engine.cli evidence-brief` prints it):
```
evidence --source 'www.example-fcu.test — Example Federal Credit Union reports record membership growth in 2025' --url https://www.example-fcu.test/news/2026-03-03-membership-growth.html --tier T2 --excerpt 'ANYTOWN, ST, March 3, 2026 — Example Federal Credit Union today announced its results for the year ended December 31, 2025.' --claim-type FACT --origin public --published 2026-03-03 --subcap P2C1.1 --actor research-p2c1-collector
```

Verifier (adversarial-verifier / finding-challenger):
```
verify_cards(run_id='R-demo', card_ids=[...], recheck_liveness=True)
```

### verify_cards → per-card checks
```json
{
 "run_id": "R-demo",
 "results": [
  {
   "card_id": "EV-97cad1e7",
   "verdict": "PASS",
   "failed": [],
   "checks": {
    "offsets": "ok",
    "verbatim_in_connector_text": "ok",
    "contract": "ok",
    "date": "ok",
    "recency_now": "CURRENT",
    "liveness": "ok"
   }
  },
  {
   "card_id": "EV-281c6658",
   "verdict": "PASS",
   "failed": [],
   "checks": {
    "offsets": "ok",
    "verbatim_in_connector_text": "ok",
    "contract": "ok",
    "date": "ok",
    "recency_now": "CURRENT",
    "liveness": "ok"
   }
  },
  {
   "card_id": "EV-30704dc7",
   "verdict": "PASS",
   "failed": [],
   "checks": {
    "offsets": "ok",
    "verbatim_in_connector_text": "ok",
    "contract": "ok",
    "date": "ok",
    "recency_now": "CURRENT",
    "liveness": "ok"
   }
  },
  {
   "card_id": "EV-nope",
   "verdict": "NOT_FOUND"
  }
 ],
 "summary": {
  "passed": 3,
  "failed": 0,
  "not_found": 1
 },
 "note": "confidence only moves down: a FAIL here is final until the card is re-issued"
}
```

### expand_context (only when a span needs disambiguating)
```json
{
 "offsets": [
  0,
  300
 ],
 "context": "Example Federal Credit Union reports record membership growth in 2025\nANYTOWN, ST, March 3, 2026 — Example Federal Credit Union today announced its results for the year ended December 31, 2025.\nMembership grew 4.2 percent to 212,000 members, the largest annual increase in the credit union's history."
}
```
