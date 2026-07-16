"""Reproducer for the heatmap/subcap 500 caught by
test_live_endpoint_smoke.py::test_every_get_route_no_5xx_against_seeded_db
at the 2026-06-05 stage-7 deploy:

    500 /api/v1/entities/americu-credit-union-syn-0001/heatmap/subcap/P1C1.1.1
    500 /api/v1/entities/americu-credit-union-syn-0001/heatmap/subcap/P1C1.1.1?view=ae
    500 /api/v1/entities/americu-credit-union-syn-0001/heatmap/subcap/P1C1.1.1?view=customer

Root cause (verified by inspection + this test): heatmap_subcap composes
the parent heatmap() handler via a direct Python call. Pre-fix heatmap()
declared `run: str | None = Query(default=None)`. When called via FastAPI
HTTP dispatch the Query sentinel is resolved into a real string-or-None.
When heatmap_subcap calls heatmap() directly (Python-level, NOT through
the dispatch layer), Python's default-argument machinery hands the
function the literal `Query(default=None)` -- a `fastapi.params.Query`
INSTANCE that has no `.strip()` method.

That instance lands in maybe_resolve_entity_run(run_request_id=...),
which executes `run_request_id.strip()` and raises AttributeError. The
exception propagates as the generic 500 Internal Server Error.

This test reproduces the AttributeError WITHOUT a live DB: we patch
maybe_resolve_entity_run to a Pythonic identity that asserts the
incoming run_request_id is None or a string. Pre-fix the assertion
would catch a Query() instance instead. Post-fix it passes.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import params


@pytest.mark.asyncio
async def test_run_param_default_is_not_a_query_sentinel() -> None:
    """When heatmap_subcap calls heatmap() directly, the `run` arg the
    inner code path observes must be a real None, NOT a Query sentinel.

    This is the static contract; the regression test catches it
    without setting up a TestClient/DB stack."""
    import inspect

    from app.routers import heatmap as hm_mod

    sig = inspect.signature(hm_mod.heatmap)
    run_param = sig.parameters["run"]
    # The bug: default was Query(default=None) which is a sentinel object.
    # The fix: plain None.
    assert run_param.default is None, (
        f"heatmap.run default is {run_param.default!r} -- "
        f"must be a plain Python None so direct Python calls "
        f"don't propagate a Query sentinel into maybe_resolve_entity_run."
    )
    assert not isinstance(run_param.default, params.Query)


@pytest.mark.asyncio
async def test_heatmap_inner_call_does_not_propagate_query_sentinel() -> None:
    """Simulates the heatmap_subcap → heatmap composition. Patches the
    DB session + maybe_resolve_entity_run to observable spies, then
    invokes heatmap() WITHOUT specifying `run` (mimicking the inner
    call site). Asserts the spy received None for run_request_id, not
    a Query sentinel.
    """
    from app.deps import ViewMode
    from app.routers import heatmap as hm_mod
    from app.services.run_resolver import ResolvedRun

    # Stub the session + maybe_resolve so heatmap() doesn't actually
    # touch a DB. We only care that the `run_request_id` propagated
    # into maybe_resolve_entity_run is a plain str|None.
    fake_session = AsyncMock()

    observed_run_request_id: list[object] = []

    async def fake_resolve(
        session, display_id, *, run_request_id=None, allow_in_progress=False,
    ) -> ResolvedRun | None:
        observed_run_request_id.append(run_request_id)
        # Returning None hits heatmap()'s no-runs short-circuit branch
        # which renders an empty HeatmapResponse without hitting any
        # real DB queries below.
        return None

    # Patch the imported function INSIDE heatmap.py's local namespace.
    # heatmap.py does `from app.services.run_resolver import
    # maybe_resolve_entity_run` lazily at function-call time, so we
    # patch at the source module.
    with patch(
        "app.services.run_resolver.maybe_resolve_entity_run",
        side_effect=fake_resolve,
    ):
        # Also patch the inline entity SELECT (after the resolver call)
        # since maybe_resolve returning None still requires the entity
        # row to render the no-runs response. We make the session
        # return a fake row.
        class _EntRow:
            id = "fake-uuid"
            display_id = "americu-credit-union-syn-0001"
            subvertical = "credit_union"

        class _Result:
            def first(self):
                return _EntRow()

        fake_session.execute = AsyncMock(return_value=_Result())

        # The hash of this is: when heatmap_subcap does
        #     full = await heatmap(display_id, _user, session, internal_view,
        #                          zoom="subcap", hm="standard",
        #                          peer=False, issues=False)
        # ...what value does Python pass for `run` (which is unsupplied)?
        # Pre-fix: Query(default=None) sentinel.  Post-fix: None.
        try:
            await hm_mod.heatmap(
                display_id="americu-credit-union-syn-0001",
                _user=None,  # CurrentUserDep not exercised here
                session=fake_session,
                view=ViewMode(audience="internal"),
                zoom="subcap",
                hm="standard",
                peer=False,
                issues=False,
                # NOTE: `run` deliberately omitted to test the default.
            )
        except AttributeError as e:
            pytest.fail(
                f"heatmap() raised AttributeError -- the Query sentinel "
                f"leaked into the inner code path (this is the actual "
                f"production 500 bug):\n  {e}"
            )

    assert observed_run_request_id, "maybe_resolve_entity_run was not called"
    rrid = observed_run_request_id[0]
    # The fix: this MUST be None (plain Python), not Query(default=None).
    assert rrid is None, (
        f"maybe_resolve_entity_run received run_request_id={rrid!r} "
        f"(type {type(rrid).__name__}). Expected None. If this is "
        f"a Query sentinel object the production endpoint will 500."
    )
    assert not isinstance(rrid, params.Query), (
        "run_request_id is a Query sentinel -- the bug has regressed."
    )
