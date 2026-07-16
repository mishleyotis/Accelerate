"""Contract test: server-side adversarial resilience (Batch 5 gate).

Per the integrated batched plan Batch 5 spec + the operator mandate
"craft code that thinks through most common errors and addresses them
before they even happen": this test pins the contract that EVERY
page-render endpoint returns HTTP 200 / 4xx (graceful degradation) on
adversarial inputs, NEVER HTTP 500.

The full-corpus harness lives at
``app/scripts/qa_adversarial_resilience.py`` (8840 cells across 104
entities x 85 probe x endpoint combinations). This test runs a
faster sample (3 representative entities x all 85 cells = 255 cells)
so it stays inside the pytest budget while still catching regressions.

The 3 anchor entities are deliberately picked to span the package-
shape range:

  - acuity-a-mutual-insuranc-0001 -- canonical, fully-populated
                                     package (615 direct subcap_scores)
  - american-homes-4-rent-lp-0001 -- broadcast package (1085
                                     shallow_broadcast rows from
                                     Batch 3)
  - <thinnest active entity>      -- chosen dynamically at runtime
                                     (fewest subcap_scores). 0-subcap
                                     (DOCX-only / pre-subcap-framework)
                                     packages are now DROPPED at ingest,
                                     so the sparsest SURVIVING shape is
                                     selected from the DB rather than
                                     hard-coded (was the former
                                     ameris-bank Class-A anchor).

If the test flags any HTTP 500 against any anchor, the operator can
run the full harness for the endpoint x probe breakdown.

Operator mandate ("no test skips, no silent errors"): the live-DB
gate uses ``DATABASE_URL_SYNC`` (matches the SEED_CI_PG_URL
convention used by 20+ other live-DB tests in this suite).
"""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.deps import CurrentUser, get_current_user
from app.main import app
from app.scripts.qa_adversarial_resilience import (
    RENDER_ENDPOINTS,
    _build_probe,
)

# Fixed anchor entities -- span the package-shape range. A 3rd anchor
# (the thinnest SURVIVING entity) is appended dynamically at runtime;
# 0-subcap (DOCX-only / pre-subcap-framework) packages are dropped at
# ingest, so the former hard-coded "ameris-bank" Class-A anchor no
# longer exists.
ANCHOR_DISPLAY_IDS = (
    "acuity-a-mutual-insuranc-0001",   # canonical fully-populated
    "american-homes-4-rent-lp-0001",   # broadcast (Batch 3)
)


def _live_db() -> bool:
    return bool(os.environ.get("DATABASE_URL_SYNC", ""))


pytestmark = pytest.mark.skipif(
    not _live_db(),
    reason=(
        "DATABASE_URL_SYNC not set -- adversarial resilience test "
        "requires live PG. Set DATABASE_URL_SYNC to the local Postgres "
        "connection string."
    ),
)


def _fake_user() -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid4()),
        email="qa@dma.local",
        role="ADMIN",
        name="QA Adversarial",
    )


def test_adversarial_resilience_end_to_end() -> None:
    """For each anchor entity x every endpoint x every adversarial
    probe, the server MUST return HTTP 200 / 4xx (graceful
    degradation), NEVER HTTP 500.

    Server errors on adversarial inputs are deploy-blocking
    regressions: they ship an unprotected attack surface. The test
    ALSO pre-checks that the 3 anchor entities exist in the live DB;
    if missing, surfaces an actionable remediation message.

    Single asyncio.run block: avoids the "Event loop is closed"
    teardown error that fires when a second asyncio.run tries to
    reuse engines created in the first.
    """
    app.dependency_overrides[get_current_user] = _fake_user

    async def _run() -> tuple[
        list[str], list[tuple[str, str, str, int, str]]
    ]:
        # Pre-flight: anchor entities exist.
        engine = create_async_engine(
            get_settings().database_url, echo=False,
        )
        sm = async_sessionmaker(engine, expire_on_commit=False)
        missing: list[str] = []
        probe_ids: list[str] = list(ANCHOR_DISPLAY_IDS)
        try:
            async with sm() as session:
                for d in ANCHOR_DISPLAY_IDS:
                    r = await session.execute(
                        text(
                            "SELECT 1 FROM entities "
                            "WHERE display_id = :d AND status='ACTIVE'"
                        ),
                        {"d": d},
                    )
                    if r.scalar() is None:
                        missing.append(d)
                # 3rd anchor, chosen dynamically: the thinnest SURVIVING
                # entity (fewest subcap_scores). Exercises the no-500
                # contract on the sparsest real package shape without a
                # brittle hard-coded id (corpus membership shifts as the
                # drop-at-ingest policy + new reports change the set).
                thin = (
                    await session.execute(
                        text(
                            "SELECT e.display_id FROM entities e "
                            "JOIN runs r ON r.entity_id = e.id "
                            "JOIN subcap_scores s ON s.run_id = r.id "
                            "WHERE e.status='ACTIVE' "
                            "  AND e.display_id IS NOT NULL "
                            "GROUP BY e.display_id "
                            "ORDER BY count(s.id) ASC, e.display_id ASC "
                            "LIMIT 1"
                        )
                    )
                ).scalar()
                if thin and thin not in probe_ids:
                    probe_ids.append(thin)
        finally:
            await engine.dispose()

        if missing:
            return missing, []

        # Probe every (anchor, endpoint, probe) cell.
        fail500: list[tuple[str, str, str, int, str]] = []
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test",
        ) as client:
            for display_id in probe_ids:
                for ep_name, ep_template, probes in RENDER_ENDPOINTS:
                    for probe in probes:
                        path_did, query = _build_probe(probe, display_id)
                        url = ep_template.format(display_id=path_did)
                        try:
                            r = await client.get(url, params=query)
                        except Exception as e:
                            fail500.append((
                                display_id, ep_name, probe, 0,
                                f"TRANSPORT: {type(e).__name__}: {e!s}",
                            ))
                            continue
                        if r.status_code == 500:
                            try:
                                detail = (r.json() or {}).get("detail", "?")
                            except (ValueError, TypeError):
                                detail = "?"
                            fail500.append((
                                display_id, ep_name, probe, 500,
                                f"detail={detail}",
                            ))
        return missing, fail500

    missing, fail500 = asyncio.run(_run())
    assert not missing, (
        f"Anchor entities missing from DB: {missing}. Run "
        f"`python -m app.scripts.historical_backfill "
        f"--dir tests/fixtures/dma_packages_batches --force` to restore."
    )
    assert not fail500, (
        f"Found {len(fail500)} HTTP-500 / transport failures on "
        f"adversarial inputs (deploy-blocking):\n"
        + "\n".join(
            f"  {did:40} {ep:18} {probe:22} -> "
            f"{code if code else 'TRANSPORT'} {detail[:60]}"
            for did, ep, probe, code, detail in fail500[:30]
        )
        + ("\n  ..." if len(fail500) > 30 else "")
    )
