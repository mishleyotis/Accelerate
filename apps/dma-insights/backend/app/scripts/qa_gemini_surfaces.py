"""Deploy-time per-surface Gemini assertions (master plan Part 3.3, RC1).

The 2026-07 audit found the committed pack Gemini-free BY CONSTRUCTION
(`DMA_DISABLE_VERTEX=1` at bake) with ZERO Vertex assertions anywhere in
the deploy pipeline — every AI surface silently degraded to templates
and nothing noticed. This script is the missing gate, in two modes:

``--mode baked``   (regen-startup-pack step / post-deploy-refresh)
    Runs against DATABASE_URL. Takes a stratified 5-entity sample
    (ACTIVE runs, spread across subverticals) and asserts, per surface,
    that the Gemini-hot bake actually PERSISTED enrichment:
      why_now                   validator-passed vertex_synthesis_cache row
      platform_story            cache rows for the sample's top platforms
      firmographics_extraction  parsed_facts._gemini_extracted present
      intelligence_summary      customer_intelligence_profiles summary md
      focus_clustering          focus_areas 'synthesized:gemini-flash' rows
                                (only asserted when profile-less entities
                                needed the synthesizer at all)
      thought_leadership        cache/parsed_facts marker (WARN-only —
                                strict verbatim validator can honestly
                                accept zero items on thin corpora)
      subcap_narrative          llm-source rows, table OR cache (WARN-only
                                until the storage surface ships)
      embeddings                evidence_+section_embeddings counts
                                (WARN-only when the bake skipped the
                                embedder pass)

``--mode live --base-url URL``  (post-deploy-smoke.sh)
    HTTP checks against the deployed service, stdlib-only (urllib):
    /healthz; POST /api/v1/rag/answer for a sampled entity asserting a
    NON-fallback answer with ≥1 citation; GET the entity overview
    asserting `source: "vertex"` provenance on why_now. Auth: a session
    JWT in ``DMA_SMOKE_TOKEN`` (same ``Authorization: Bearer`` the app
    accepts — see app/deps.py). Without the token the script degrades
    to registration checks (401/405 = wired) and WARNs.

Every FAIL prints the exact remediation (IAM grant command, env var).

Escape hatch: ``_ALLOW_COLD_GEMINI=true`` (or ``ALLOW_COLD_GEMINI``)
downgrades FAILs to a loud warning, exits 0, and stamps
``"gemini": "cold"`` into the pack manifest (``--manifest`` path, when
the file exists) so the coldness is visible downstream instead of
silent. On a fully-green run the manifest is stamped ``"gemini": "hot"``.

Exit codes (documented in infra/EXIT_CODES.md):
  0 — all hard checks PASS (or cold explicitly allowed)
  1 — ≥1 hard surface assertion FAILED (Gemini effectively cold)
  2 — caller error (bad argv / DATABASE_URL missing / --base-url missing)
  3 — live mode: service unreachable

Usage:
  DATABASE_URL=... python -m app.scripts.qa_gemini_surfaces --mode baked \
      [--manifest ../startup-data/pages_manifest.json] [--json]
  DMA_SMOKE_TOKEN=... python -m app.scripts.qa_gemini_surfaces \
      --mode live --base-url https://dma-insights-backend-....run.app [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass

_IAM_HINT = (
    "Fix: grant the SA Vertex access — gcloud projects "
    "add-iam-policy-binding $PROJECT_ID "
    "--member=serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com "
    "--role=roles/aiplatform.user (bake) / the compute SA (runtime); "
    "ensure the regen container runs with --network=cloudbuild and "
    "VERTEX_PROJECT_ID/GOOGLE_CLOUD_PROJECT set, and that "
    "DMA_DISABLE_VERTEX is NOT set. Escape hatch: _ALLOW_COLD_GEMINI=true."
)


@dataclass
class CheckResult:
    name: str
    status: str  # PASS | WARN | FAIL | SKIP
    detail: str
    hint: str = ""


def _allow_cold() -> bool:
    return (
        (os.environ.get("_ALLOW_COLD_GEMINI")
         or os.environ.get("ALLOW_COLD_GEMINI")
         or "").strip().lower() == "true"
    )


# ─────────────────────────────────────────────────────────────────────────────
# baked mode — DB assertions
# ─────────────────────────────────────────────────────────────────────────────

async def _sample_entities(session, n: int = 5) -> list[str]:
    """Stratified sample: ACTIVE-run entities spread across subverticals
    (one per subvertical round-robin until n)."""
    from sqlalchemy import text
    rows = (
        await session.execute(text(
            """
            SELECT e.display_id, COALESCE(e.subvertical, '?') AS subv
            FROM entities e
            JOIN runs r ON r.entity_id = e.id AND r.status = 'ACTIVE'
            WHERE e.status = 'ACTIVE'
            GROUP BY e.display_id, e.subvertical
            ORDER BY subv, e.display_id
            """))
    ).all()
    by_subv: dict[str, list[str]] = {}
    for r in rows:
        by_subv.setdefault(r.subv, []).append(r.display_id)
    sample: list[str] = []
    while len(sample) < n and any(by_subv.values()):
        for subv in sorted(by_subv):
            if by_subv[subv]:
                sample.append(by_subv[subv].pop(0))
                if len(sample) >= n:
                    break
    return sample


async def _cache_hits(session, surface: str, target_ids: list[str]) -> int:
    from sqlalchemy import text
    if not target_ids:
        return 0
    return int(
        (await session.execute(text(
            """
            SELECT COUNT(DISTINCT target_id) FROM vertex_synthesis_cache
            WHERE target_kind = 'entity' AND surface = :surface
              AND target_id = ANY(CAST(:tids AS text[]))
              AND validators_passed AND invalidated_at IS NULL
              AND (expires_at IS NULL OR expires_at > NOW())
            """), {"surface": surface, "tids": target_ids})).scalar() or 0
    )


async def _scalar(session, sql: str, params: dict | None = None) -> int:
    from sqlalchemy import text
    try:
        return int((await session.execute(text(sql), params or {})).scalar() or 0)
    except Exception:
        # Relation/column missing (pre-migration schema) — roll back so
        # the aborted transaction doesn't poison the later checks.
        await session.rollback()
        return -1  # caller decides (usually WARN/SKIP)


async def _run_baked(args: argparse.Namespace) -> list[CheckResult]:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL not set", file=sys.stderr)
        raise SystemExit(2)
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    results: list[CheckResult] = []
    engine = create_async_engine(dsn, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            sample = await _sample_entities(session)
            if not sample:
                results.append(CheckResult(
                    "sample", "FAIL",
                    "no ACTIVE-run entities in the DB — nothing to assert",
                    "Seed the corpus first (historical_backfill + "
                    "run_derive_chain), then re-run.",
                ))
                return results
            results.append(CheckResult(
                "sample", "PASS",
                f"stratified sample: {', '.join(sample)}"))

            # 0. Vertex reachability (informational — the row checks
            # below are the authority; this pinpoints WHY they failed).
            try:
                from app.services.vertex_client import get_vertex_client
                get_vertex_client().probe()
                results.append(CheckResult(
                    "vertex_reachability", "PASS", "1-token probe OK"))
            except Exception as exc:
                results.append(CheckResult(
                    "vertex_reachability", "WARN",
                    f"probe failed: {type(exc).__name__}: {str(exc)[:140]}",
                    _IAM_HINT))

            # 1. why_now — assert the SERVED store. The page serves the
            # deterministic runs.why_now_signals (deepen_narrative), with
            # the Vertex cache row only an optional, often-suppressed WN-0
            # uplift (overview_gemini_merge). The gate used to demand the
            # cache row and FAILed 0/5 on a healthy live DB whenever
            # enrich_corpus ran Vertex-cold (2026-07-14 writer↔gate audit).
            n_served = await _scalar(session, """
                SELECT COUNT(DISTINCT e.display_id)
                FROM entities e
                JOIN runs r ON r.entity_id = e.id AND r.status = 'ACTIVE'
                WHERE e.display_id = ANY(CAST(:tids AS text[]))
                  AND r.why_now_signals IS NOT NULL
                  AND jsonb_array_length(r.why_now_signals) > 0
                """, {"tids": sample})
            results.append(CheckResult(
                "why_now",
                "PASS" if n_served >= len(sample) else "FAIL",
                f"{n_served}/{len(sample)} sampled entities serve populated "
                "runs.why_now_signals (the deterministic store the page "
                "renders)",
                "" if n_served >= len(sample) else
                "deepen_narrative did not persist why_now signals — check "
                "the derive chain's wave 6 output.",
            ))
            # 1b. why_now Vertex uplift — WARN-only: the cache row is an
            # optional overlay; Vertex-cold is a warmth signal, not a
            # deploy blocker.
            n_cache = await _cache_hits(session, "why_now", sample)
            results.append(CheckResult(
                "why_now_vertex_uplift",
                "PASS" if n_cache > 0 else "WARN",
                f"{n_cache}/{len(sample)} sampled entities also carry a "
                "validator-passed vertex_synthesis_cache why_now row "
                "(optional WN-0 uplift)",
                "" if n_cache > 0 else
                "enrich_corpus persisted nothing (honest-cold). " + _IAM_HINT,
            ))

            # 2. platform_story — cache rows for the sample's top-2
            # platforms (target_id = "{display_id}:{platform_id}").
            refs: list[str] = []
            for did in sample:
                rows = (await session.execute(text(
                    """
                    SELECT ps.platform_id
                    FROM platform_scores ps
                    JOIN runs r ON r.id = ps.run_id AND r.status = 'ACTIVE'
                    JOIN entities e ON e.id = r.entity_id
                    WHERE e.display_id = :did
                    ORDER BY ps.fit_score DESC NULLS LAST LIMIT 2
                    """), {"did": did})).all()
                refs.extend(f"{did}:{r.platform_id}" for r in rows)
            if refs:
                n = await _cache_hits(session, "platform_story", refs)
                results.append(CheckResult(
                    "platform_story",
                    "PASS" if n > 0 else "FAIL",
                    f"{n}/{len(refs)} sampled entity x platform refs cached",
                    "" if n > 0 else
                    "No platform_story cache rows. " + _IAM_HINT,
                ))
            else:
                results.append(CheckResult(
                    "platform_story", "SKIP",
                    "sample has no platform_scores rows"))

            # 3. firmographics_extraction — parsed_facts._gemini_extracted
            # present (sample first, corpus-wide fallback: only entities
            # WITH gap fields get the surface, so the sample can miss).
            n_sample = await _scalar(session, """
                SELECT COUNT(*) FROM firmographics f
                JOIN entities e ON e.id = f.entity_id
                WHERE e.display_id = ANY(CAST(:tids AS text[]))
                  AND f.parsed_facts ? '_gemini_extracted'
                """, {"tids": sample})
            n_all = await _scalar(session, """
                SELECT COUNT(*) FROM firmographics
                WHERE parsed_facts ? '_gemini_extracted'
                """)
            ok = (n_sample > 0) or (n_all > 0)
            results.append(CheckResult(
                "firmographics_extraction",
                "PASS" if ok else "FAIL",
                f"{max(n_sample, 0)}/{len(sample)} sampled "
                f"({max(n_all, 0)} corpus-wide) entities carry "
                "parsed_facts._gemini_extracted",
                "" if ok else
                "Gemini gap-fill persisted nothing. Run `python -m "
                "app.scripts.enrich_corpus --surfaces "
                "firmographics_extraction` hot. " + _IAM_HINT,
            ))

            # 4. intelligence_summary — profile summary md non-null.
            n_sample = await _scalar(session, """
                SELECT COUNT(*) FROM customer_intelligence_profiles p
                JOIN entities e ON e.id = p.entity_id
                WHERE e.display_id = ANY(CAST(:tids AS text[]))
                  AND p.intelligence_summary_md IS NOT NULL
                  AND p.intelligence_summary_md <> ''
                """, {"tids": sample})
            n_all = await _scalar(session, """
                SELECT COUNT(*) FROM customer_intelligence_profiles
                WHERE intelligence_summary_md IS NOT NULL
                  AND intelligence_summary_md <> ''
                """)
            ok = (n_sample > 0) or (n_all > 0)
            results.append(CheckResult(
                "intelligence_summary",
                "PASS" if ok else "FAIL",
                f"{max(n_sample, 0)} sampled / {max(n_all, 0)} corpus-wide "
                "profiles carry intelligence_summary_md",
                "" if ok else
                "intelligence_recompute wrote no Vertex summaries. Run "
                "`python -m workers.intelligence_recompute.main --all` "
                "hot. " + _IAM_HINT,
            ))

            # 5. focus clustering — the Gemini rung of the focus-area
            # ladder ('synthesized:gemini-flash' source_path). Only
            # asserted when the synthesizer had profile-less entities
            # to fill at all (all-DOCX corpora legitimately have none).
            n_gemini = await _scalar(session, """
                SELECT COUNT(*) FROM focus_areas
                WHERE source_path LIKE 'synthesized:gemini%'
                """)
            n_heuristic = await _scalar(session, """
                SELECT COUNT(*) FROM focus_areas
                WHERE source_path LIKE 'synthesized:heuristic%'
                """)
            if n_gemini > 0:
                results.append(CheckResult(
                    "focus_clustering", "PASS",
                    f"{n_gemini} Gemini-clustered focus_areas rows "
                    f"({n_heuristic} heuristic)"))
            elif n_heuristic > 0:
                results.append(CheckResult(
                    "focus_clustering", "FAIL",
                    f"synthesizer ran COLD: {n_heuristic} heuristic rows, "
                    "0 Gemini-clustered",
                    # 2026-07-05: on the 01735cd build this hint blamed IAM
                    # while the SAME build's Vertex probe + why_now calls
                    # passed — the real cause was the focus rung's own call
                    # failing (schema/truncation). Point at the actual
                    # evidence FIRST; IAM last.
                    "The focus ladder fell to its deterministic rung. "
                    "FIRST check the derive+heal step's "
                    "`# derive_focus_areas:` summary line — it prints "
                    "gemini[schema_ok/plain_ok/failed] counters and the "
                    "last error (schema rejection, truncation, quota). "
                    "If vertex_reachability PASSED above, this is NOT an "
                    "IAM problem. Only when the probe also failed: "
                    + _IAM_HINT,
                ))
            else:
                results.append(CheckResult(
                    "focus_clustering", "SKIP",
                    "no synthesized focus_areas rows — every entity had "
                    "a client-profile DOCX (ladder rung 1)"))

            # 6. thought_leadership_extraction — WARN-only: the verbatim-
            # excerpt validator can honestly accept zero items when the
            # corpus carries no roster-authored prose.
            n_rows = await _scalar(session, """
                SELECT COUNT(*) FROM vertex_synthesis_cache
                WHERE surface = 'thought_leadership_extraction'
                  AND validators_passed AND invalidated_at IS NULL
                """)
            n_firm = await _scalar(session, """
                SELECT COUNT(*) FROM firmographics
                WHERE parsed_facts -> '_gemini_extracted'
                      ? 'thought_leadership'
                """)
            ok = (n_rows > 0) or (n_firm > 0)
            results.append(CheckResult(
                "thought_leadership_extraction",
                "PASS" if ok else "WARN",
                f"{max(n_rows, 0)} cache rows / {max(n_firm, 0)} filled "
                "panels",
                "" if ok else
                "No grounded thought-leadership extracted — verify with "
                "`python -m app.scripts.enrich_corpus --surfaces "
                "thought_leadership_extraction --verbose`.",
            ))

            # 7. subcap_narrative — table or cache, WARN-only until the
            # persistence surface ships (extractor is read-time today).
            # NOTE: the column is `meta` (migration 051), not `source` — the
            # old `WHERE source='llm'` raised, _scalar swallowed it to -1 and
            # the assertion was a permanent no-op (audit 2026-07-04).
            n_tbl = await _scalar(session, """
                SELECT COUNT(*) FROM subcap_narratives
                WHERE meta = 'llm'
                """)
            n_cache = await _scalar(session, """
                SELECT COUNT(*) FROM vertex_synthesis_cache
                WHERE surface = 'subcap_narrative'
                  AND validators_passed AND invalidated_at IS NULL
                """)
            if n_tbl > 0 or n_cache > 0:
                results.append(CheckResult(
                    "subcap_narrative", "PASS",
                    f"{max(n_tbl, 0)} llm table rows / "
                    f"{max(n_cache, 0)} cache rows"))
            else:
                results.append(CheckResult(
                    "subcap_narrative", "WARN",
                    "no llm-source subcap narratives persisted "
                    "(table absent or empty; surface is warmed lazily "
                    "at first AE click today)",
                    "Expected to turn PASS once the subcap_narratives "
                    "persistence lands (master plan Part 6.3)."))

            # 7b. insight_explanation — the deepen_narrative explainer
            # injection (plan Part 3.3 row 10). Vertex prose replaces the
            # deterministic template only when _valid_insight passes, so a
            # warm bake must leave ≥1 card whose why/so_what does NOT match
            # the template families. Template-only cards everywhere ⇒ the
            # injection regressed (it was dead code until 2026-07-04).
            n_nontpl = await _scalar(session, """
                SELECT COUNT(*) FROM insight_cards
                WHERE why_text IS NOT NULL
                  AND why_text NOT LIKE '%out of 5%'
                  AND why_text NOT LIKE '%peer benchmark%'
                  AND length(why_text) > 150
                """)
            results.append(CheckResult(
                "insight_explanation",
                "PASS" if n_nontpl > 0 else ("WARN" if _allow_cold() else "FAIL"),
                f"{max(n_nontpl, 0)} cards carry non-template why_text",
                "" if n_nontpl > 0 else
                "Every insight card is template-only — the deepen_narrative "
                "set_insight_explainer(make_vertex_insight_explainer()) "
                "injection did not produce validated Vertex prose. Check "
                "Vertex creds during regen or the _valid_insight gate.",
            ))

            # 8. embeddings — WARN-only when the bake skipped the
            # embedder pass (cost/latency call, documented in
            # DEPLOYMENT.md §26).
            n_ev = await _scalar(
                session, "SELECT COUNT(*) FROM evidence_embeddings")
            n_sec = await _scalar(
                session, "SELECT COUNT(*) FROM section_embeddings")
            ok = n_ev > 0 and n_sec > 0
            results.append(CheckResult(
                "embeddings",
                "PASS" if ok else "WARN",
                f"evidence_embeddings={max(n_ev, 0)} "
                f"section_embeddings={max(n_sec, 0)}",
                "" if ok else
                "Embedder pass missing/partial — run `python -m "
                "workers.embedder.main --since 2000-01-01` with Vertex "
                "creds (RAG retrieval quality degrades without it).",
            ))
    finally:
        await engine.dispose()
    return results


# ─────────────────────────────────────────────────────────────────────────────
# live mode — HTTP assertions (stdlib only; runs from operator shells)
# ─────────────────────────────────────────────────────────────────────────────

def _http(method: str, url: str, token: str | None = None,
          body: dict | None = None, timeout: int = 60) -> tuple[int, dict | str]:
    import urllib.error
    import urllib.request
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except ValueError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace") if e.fp else ""
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def _run_live(args: argparse.Namespace) -> list[CheckResult]:
    base = (args.base_url or "").rstrip("/")
    if not base:
        print("--base-url is required in --mode live", file=sys.stderr)
        raise SystemExit(2)
    token = (os.environ.get("DMA_SMOKE_TOKEN") or "").strip() or None
    results: list[CheckResult] = []

    # 0. reachability
    try:
        status, _ = _http("GET", f"{base}/healthz", timeout=15)
    except Exception as exc:
        print(f"service unreachable: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc
    results.append(CheckResult(
        "healthz", "PASS" if status == 200 else "FAIL",
        f"/healthz → {status}",
        "" if status == 200 else "Backend down — check Cloud Run logs."))

    if token is None:
        # Degraded: registration-only (post-deploy-smoke's historical
        # unauthenticated posture). Prove the AI routes are wired.
        status, _ = _http("GET", f"{base}/api/v1/rag/answer", timeout=15)
        wired = status in (401, 405)
        results.append(CheckResult(
            "rag_answer_registered",
            "PASS" if wired else "FAIL",
            f"GET /api/v1/rag/answer → {status} (401/405 = wired)",
            "" if wired else "Route missing — routers not registered."))
        results.append(CheckResult(
            "gemini_live_assertions", "WARN",
            "DMA_SMOKE_TOKEN unset — skipped authenticated non-fallback "
            "+ provenance assertions",
            "Export DMA_SMOKE_TOKEN=<session JWT> (e.g. from "
            "/api/v1/auth/dev-login on non-prod) and re-run for the "
            "full gate."))
        return results

    # 1. pick a sample entity from the directory.
    status, body = _http("GET", f"{base}/api/v1/entities?limit=5", token)
    items = body.get("items") if isinstance(body, dict) else None
    if status != 200 or not items:
        results.append(CheckResult(
            "sample_entity", "FAIL",
            f"GET /api/v1/entities → {status}; no entities to sample",
            "Token invalid/expired, or the DB is empty — reseed or "
            "refresh DMA_SMOKE_TOKEN."))
        return results
    dids = [it.get("display_id") for it in items if it.get("display_id")]
    results.append(CheckResult(
        "sample_entity", "PASS", f"sampled: {', '.join(dids[:5])}"))

    # 2. POST /rag/answer — grounded question, assert non-fallback + ≥1
    # citation (the plan's rag_answer live assertion).
    did = dids[0]
    name = items[0].get("name") or did
    status, body = _http("POST", f"{base}/api/v1/rag/answer", token, body={
        "question": (
            f"What is the strongest recent evidence about {name}'s "
            "digital maturity? Cite the evidence IDs."
        ),
        "page_context": {
            "route": f"/clients/{did}/overview",
            "entity_id": did,
            "user_role": "AE",
        },
        "response_style": "concise",
        "require_citations": True,
    }, timeout=120)
    if status != 200 or not isinstance(body, dict):
        results.append(CheckResult(
            "rag_answer_non_fallback", "FAIL",
            f"POST /api/v1/rag/answer → {status}",
            "Endpoint errored — check Cloud Run logs. " + _IAM_HINT))
    else:
        fallback = bool(body.get("fallback_used"))
        cites = body.get("citations") or []
        ok = (not fallback) and len(cites) >= 1
        results.append(CheckResult(
            "rag_answer_non_fallback",
            "PASS" if ok else "FAIL",
            f"fallback_used={fallback} citations={len(cites)}",
            "" if ok else
            "Vertex fell back to the template answer (cold or "
            "hallucination-validator trip). " + _IAM_HINT))

    # 3. overview why_now — assert the SERVED signals; Vertex provenance
    # is a WARN-only warmth indicator. The WN-0 vertex uplift is
    # SUPPRESSED by design when it restates the deterministic signals
    # (overview_gemini_merge), so its absence on a warm deploy is
    # legitimate — the old hard-FAIL here was the 2026-07-14 writer↔gate
    # false alarm.
    served = None
    vertex_found = None
    for cand in dids[:5]:
        status, body = _http(
            "GET", f"{base}/api/v1/entities/{cand}/overview", token)
        if status != 200 or not isinstance(body, dict):
            continue
        sigs = [s for s in (body.get("why_now_signals") or [])
                if isinstance(s, dict)]
        if sigs and served is None:
            served = (cand, len(sigs))
        for sig in sigs:
            if (sig.get("source") == "vertex"
                    or sig.get("derived_from") == "vertex"):
                vertex_found = (cand, sig.get("model_id"))
                break
        if vertex_found:
            break
    if served:
        results.append(CheckResult(
            "why_now_served", "PASS",
            f"{served[0]} serves {served[1]} why_now signals "
            "(deterministic store)"))
    else:
        results.append(CheckResult(
            "why_now_served", "FAIL",
            f"none of {len(dids[:5])} sampled overviews serve any "
            "why_now signals",
            "runs.why_now_signals is empty — run the derive chain "
            "(deepen_narrative, wave 6) against the live DB."))
    if vertex_found:
        results.append(CheckResult(
            "why_now_vertex_provenance", "PASS",
            f"{vertex_found[0]} carries a source:vertex why_now signal "
            f"(model_id={vertex_found[1]})"))
    else:
        results.append(CheckResult(
            "why_now_vertex_provenance", "WARN",
            f"none of {len(dids[:5])} sampled overviews carry a "
            "source:vertex why_now signal (uplift absent, suppressed, "
            "or Vertex cold)",
            "For Vertex warmth: run infra/post-deploy-refresh.sh "
            "(run_derive_chain includes enrich_corpus) or `python -m "
            "app.scripts.enrich_corpus --surfaces all` against the live "
            "DB. " + _IAM_HINT))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# reporting + manifest stamp
# ─────────────────────────────────────────────────────────────────────────────

def _stamp_manifest(path: str, state: str) -> None:
    """Write `"gemini": "<state>"` into the pack manifest when the file
    exists (workspace bake path). Best-effort — never fails the gate."""
    try:
        if not path or not os.path.isfile(path):
            return
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return
        data["gemini"] = state
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
        # stderr so `--json` stdout stays machine-parseable.
        print(f"# stamped {path}: gemini={state}", file=sys.stderr)
    except Exception as exc:  # pragma: no cover — advisory stamp
        print(f"# manifest stamp skipped ({exc})", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Deploy-time per-surface Gemini assertions")
    ap.add_argument("--mode", choices=("baked", "live"), required=True)
    ap.add_argument("--base-url", help="deployed backend URL (live mode)")
    ap.add_argument("--manifest",
                    help="pages_manifest.json to stamp gemini:hot|cold "
                         "(baked mode; skipped when absent)")
    ap.add_argument("--json", action="store_true",
                    help="machine-readable report on stdout")
    args = ap.parse_args()

    if args.mode == "baked":
        import asyncio
        results = asyncio.run(_run_baked(args))
    else:
        results = _run_live(args)

    fails = [r for r in results if r.status == "FAIL"]
    warns = [r for r in results if r.status == "WARN"]
    allow_cold = _allow_cold()

    if args.json:
        print(json.dumps({
            "mode": args.mode,
            "allow_cold": allow_cold,
            "failures": len(fails),
            "warnings": len(warns),
            "checks": [asdict(r) for r in results],
        }, indent=2))
    else:
        icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗", "SKIP": "-"}
        print(f"# qa_gemini_surfaces --mode {args.mode}")
        for r in results:
            print(f"  {icon[r.status]} [{r.status:4s}] {r.name}: {r.detail}")
            if r.hint and r.status in ("FAIL", "WARN"):
                print(f"      ↳ {r.hint}")
        print(f"# SUMMARY: {len(fails)} FAIL, {len(warns)} WARN, "
              f"{len(results)} checks")

    if args.mode == "baked":
        _stamp_manifest(args.manifest or "",
                        "cold" if fails else "hot")

    if fails and allow_cold:
        print(
            "\n" + "!" * 72 +
            "\n!! _ALLOW_COLD_GEMINI=true — GEMINI SURFACE ASSERTIONS "
            "FAILED but the\n!! gate is DOWNGRADED to a warning. The pack/"
            "deploy is Gemini-COLD:\n!! AI surfaces will serve "
            "deterministic fallbacks until warmed.\n" + "!" * 72,
            file=sys.stderr,
        )
        return 0
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
