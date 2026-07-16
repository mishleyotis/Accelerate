"""Regression: route handlers that call each other directly must NOT
use `Query(default=X)` as a parameter default for optional inputs the
inner call wants as a plain Python value.

The bug shape:

    @router.get("/heatmap")
    async def heatmap(..., run: str | None = Query(default=None)):
        resolved = await maybe_resolve_entity_run(
            session, display_id, run_request_id=run,
        )

    @router.get("/heatmap/subcap/{id}")
    async def heatmap_subcap(..., view, ...):
        # Direct Python call, NOT via FastAPI's dependency injection layer.
        full = await heatmap(display_id, _user, session, view,
                             zoom="subcap", hm="standard", peer=False, issues=False)
        # `run` is unsupplied -> Python uses the function's literal default
        # value, which is `Query(default=None)` -- a sentinel object.
        # maybe_resolve_entity_run then tries run_request_id.strip() and
        # raises AttributeError -> 500 on every probe of that route.

Caught by tests/test_live_endpoint_smoke.py against seeded PG, but the
class of bug deserves its own static guard so future signatures don't
re-introduce it during refactors.

Contract enforced here: any handler in heatmap/entities/platforms/
context/health/insights that exposes a `run: str | None = ...` query
parameter must use a plain `None` default (not `Query(default=None)`).
"""
from __future__ import annotations

import inspect

import pytest


def _handler_run_default(handler_callable):
    """Return the literal default value of the `run` parameter on the
    handler, or `_NO_RUN_PARAM` if the handler has no such parameter."""
    sig = inspect.signature(handler_callable)
    p = sig.parameters.get("run")
    if p is None:
        return _NO_RUN_PARAM
    return p.default


class _Sentinel:
    pass


_NO_RUN_PARAM = _Sentinel()


HANDLERS_THAT_TAKE_RUN = [
    # (module_path, attr_name)
    ("app.routers.heatmap", "heatmap"),
    ("app.routers.entities", "entity_overview"),
    ("app.routers.platforms", "platforms"),
    ("app.routers.platforms", "platforms_roadmap"),
    ("app.routers.context", "context"),
    ("app.routers.health", "health"),
    ("app.routers.insights", "insights"),
    ("app.routers.insights", "evidence"),
]


@pytest.mark.parametrize("module_path,attr_name", HANDLERS_THAT_TAKE_RUN)
def test_run_param_default_is_plain_none(module_path: str, attr_name: str) -> None:
    """Handlers that expose a `run` query param must use `= None` not
    `= Query(default=None)`. Otherwise direct Python calls to the
    handler (route-to-route composition) pass the Query sentinel into
    downstream code that expects `str | None`, producing AttributeError
    in production.
    """
    import importlib

    from fastapi import params

    module = importlib.import_module(module_path)
    handler = getattr(module, attr_name)
    default = _handler_run_default(handler)

    assert default is not _NO_RUN_PARAM, (
        f"{module_path}.{attr_name} no longer accepts a `run` parameter -- "
        f"if intentional, update this test's HANDLERS_THAT_TAKE_RUN list."
    )

    # The actual contract: default must be None (plain Python None),
    # never a Query/Path/Header/Cookie sentinel.
    assert default is None, (
        f"{module_path}.{attr_name} declares `run` with default={default!r} "
        f"(type {type(default).__name__}). Use `run: str | None = None` "
        f"so direct Python calls receive a plain None, not a FastAPI "
        f"sentinel. The HTTP path still binds `?run=` correctly because "
        f"FastAPI inspects the type annotation -- the Query() wrapper "
        f"only matters for advanced metadata (regex, alias, etc.)."
    )
    assert not isinstance(default, params.Query), (
        f"{module_path}.{attr_name} uses a Query() sentinel as the "
        f"default for `run`; this breaks route-to-route Python composition."
    )


def test_coerce_run_request_id_handles_query_sentinel() -> None:
    """Runtime safety net: even if a future caller passes a Query
    sentinel into resolve_entity_run, the resolver MUST coerce it
    to None instead of raising AttributeError on `.strip()`. This is
    belt-and-braces with the static signature contract above."""
    from fastapi import Query

    from app.services.run_resolver import _coerce_run_request_id

    # Plain None passes through.
    assert _coerce_run_request_id(None) is None
    # Strings pass through.
    assert _coerce_run_request_id("REQ-12345678") == "REQ-12345678"
    assert _coerce_run_request_id("") == ""
    # The Query sentinel that caused the production 500.
    assert _coerce_run_request_id(Query(default=None)) is None
    # Anything else (int, dict, list) also coerces -> None (defensive).
    assert _coerce_run_request_id(42) is None
    assert _coerce_run_request_id({}) is None
    assert _coerce_run_request_id(["DMA-RES-X"]) is None


def test_audit_route_composition_safety_detects_query_sentinel() -> None:
    """The startup-time audit must spot any handler that uses a Query
    sentinel as the default for `run`. Catches the regression at boot
    time -- before the bug can serve a single request.

    The audit accepts any logger object that exposes `.info(...)` and
    `.warning(...)` taking arbitrary keyword args (the structlog
    interface used in main.py). We pass a minimal stub that records
    the calls so we can assert observable output."""
    from fastapi import FastAPI, Query

    from app.services.run_resolver import audit_route_composition_safety

    class _StubLogger:
        def __init__(self) -> None:
            self.info_calls: list[tuple] = []
            self.warning_calls: list[tuple] = []

        def info(self, msg: str, **kwargs) -> None:
            self.info_calls.append((msg, kwargs))

        def warning(self, msg: str, **kwargs) -> None:
            self.warning_calls.append((msg, kwargs))

    # Clean app -- no `run` params at all.
    app_clean = FastAPI()

    @app_clean.get("/safe/{x}")
    async def safe_handler(x: str, run: str | None = None) -> dict:
        return {"x": x, "run": run}

    logger_clean = _StubLogger()
    n_offenders_clean = audit_route_composition_safety(app_clean, logger_clean)
    assert n_offenders_clean == 0
    assert any(
        call[0] == "route_composition_audit.clean" for call in logger_clean.info_calls
    )

    # Buggy app -- one handler uses Query(default=None) for `run`.
    app_buggy = FastAPI()

    @app_buggy.get("/buggy/{x}")
    async def buggy_handler(x: str, run: str | None = Query(default=None)) -> dict:
        return {"x": x, "run": run}

    logger_buggy = _StubLogger()
    n_offenders_buggy = audit_route_composition_safety(app_buggy, logger_buggy)
    assert n_offenders_buggy == 1, (
        "audit failed to spot Query(default=None) on `run` param"
    )
    # The offender warning is structured + actionable.
    unsafe_calls = [
        c for c in logger_buggy.warning_calls
        if c[0] == "route_composition_audit.unsafe_default"
    ]
    assert len(unsafe_calls) == 1
    assert "/buggy/{x}" in unsafe_calls[0][1]["path"]
    assert "Query" in unsafe_calls[0][1]["default_type"]


def test_heatmap_subcap_composes_with_heatmap_safely() -> None:
    """Smoke contract: heatmap_subcap composes heatmap() directly, so
    BOTH must be compatible with direct Python calls. Specifically, the
    inner call site must NOT pass a Query sentinel as `run`.
    """
    import inspect

    from app.routers import heatmap as hm_mod

    src = inspect.getsource(hm_mod.heatmap_subcap)
    # Either: explicit `run=None` keyword, or no `run=` in the inner call
    # (which is fine because the outer heatmap defaults to None now).
    assert "Query(default=None)" not in src, (
        "heatmap_subcap source references Query(default=None) -- the "
        "sentinel must not leak into direct calls."
    )
