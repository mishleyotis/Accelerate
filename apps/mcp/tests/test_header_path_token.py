"""The capability token as a header: /mcp + X-DMA-Path-Token reaches the
connector; everything else meets the same 404 a wrong path always met.

Why this exists (owner, 2026-08-20): a plugin whose server URL embeds the
token cannot connect until a human pastes it into plugin config, so every
install sat "MCP pending". The wrapper rewrites /mcp with the right header
to the mounted capability path; the negative cases matter more than the
positive — a wrapper that rewrites on a WRONG token is the capability URL
with the capability removed.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dma_mcp.transport import HeaderPathToken  # noqa: E402

CAP_FIXTURE = "correct-capability-fixture-value"


class _Recorder:
    def __init__(self):
        self.scope = None

    async def __call__(self, scope, receive, send):
        self.scope = scope


def _run(scope):
    inner = _Recorder()
    asyncio.run(HeaderPathToken(inner, CAP_FIXTURE)(scope, None, None))
    return inner.scope


def _scope(path, headers):
    return {"type": "http", "path": path,
            "raw_path": path.encode(), "headers": headers}


def test_right_header_on_static_path_rewrites_to_the_capability_path():
    out = _run(_scope("/mcp", [(b"x-dma-path-token", CAP_FIXTURE.encode())]))
    assert out["path"] == f"/mcp/{CAP_FIXTURE}"
    assert out["raw_path"] == f"/mcp/{CAP_FIXTURE}".encode()


def test_trailing_slash_is_the_same_door():
    out = _run(_scope("/mcp/", [(b"x-dma-path-token", CAP_FIXTURE.encode())]))
    assert out["path"] == f"/mcp/{CAP_FIXTURE}"


def test_wrong_token_passes_through_untouched():
    """The 404 the inner app gives a wrong path is the whole error story —
    the wrapper must not create a distinguishable one."""
    out = _run(_scope("/mcp", [(b"x-dma-path-token", b"wrong-token")]))
    assert out["path"] == "/mcp"


def test_missing_header_passes_through_untouched():
    out = _run(_scope("/mcp", []))
    assert out["path"] == "/mcp"


def test_url_segment_form_is_untouched_backcompat():
    path = f"/mcp/{CAP_FIXTURE}"
    out = _run(_scope(path, []))
    assert out["path"] == path


def test_header_on_a_non_mcp_path_grants_nothing():
    out = _run(_scope("/health", [(b"x-dma-path-token", CAP_FIXTURE.encode())]))
    assert out["path"] == "/health"


def test_original_scope_object_is_not_mutated():
    """Stateless servers may reuse scope dicts; the rewrite must be a copy."""
    scope = _scope("/mcp", [(b"x-dma-path-token", CAP_FIXTURE.encode())])
    _run(scope)
    assert scope["path"] == "/mcp"
