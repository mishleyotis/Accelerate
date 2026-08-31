"""server.py must at least LOAD. Nothing checked that until a deploy failed.

WHAT IT COST. 2026-08-31, `dmai-mcp` revision 00119:

    File "/app/server.py", line 105, in <module>
        @contextmanager
    NameError: name 'contextmanager' is not defined
    Container called exit(1).

A merge took one branch's `_conn()` — which is decorated `@contextmanager` —
while the other branch had already dropped `from contextlib import
contextmanager`, correctly, because ITS `_conn` was a plain assignment. Each
half was right and the join was not. The revision never started; Cloud Run's
startup probe held traffic on the previous one, so production was unharmed.

THE SUITE SAID 4,820 PASSED. It could not have said anything else: no test
imports this module. `test_documented_tool_counts.py` states the reason in
its own docstring — "importing `server` wants a database and an embedding
model" — and reads the file as TEXT instead. So does
`test_pending_runs_duplicates.py`, and so did the check I ran by hand before
pushing: `ast.parse` proves a file is SYNTACTICALLY valid and says nothing
about whether its module-level names resolve. A NameError at module scope is
not a syntax error. It is a service that does not start.

The premise turned out to be wrong. `server.py` needs the MCP SDK at import,
and the SDK is the only thing it needs: the database is opened per tool call,
the encoder is lazy behind `_encoder()`, and `packages/shared` is on the path
the module builds for itself. Stub the SDK and the module loads — which is
all it takes to have caught this.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MCP_DIR = ROOT / "apps" / "mcp"


@pytest.fixture()
def server(monkeypatch):
    """`server` imported for real, with only the MCP SDK stubbed."""
    class _Stub:
        def __init__(self, *a, **k):
            self.name = a[0] if a else ""

        def tool(self, *a, **k):
            return lambda fn: fn

        def streamable_http_app(self):
            return object()

    pkg = types.ModuleType("mcp")
    sub = types.ModuleType("mcp.server")
    sub.MCPServer = _Stub
    pkg.server = sub
    monkeypatch.setitem(sys.modules, "mcp", pkg)
    monkeypatch.setitem(sys.modules, "mcp.server", sub)

    # The shared package, which the image gets from `deploy.sh` staging it
    # into apps/mcp/shared. In a checkout that directory holds only a
    # .gitkeep, so point at the source of truth.
    for p in (str(MCP_DIR), str(ROOT / "packages" / "shared")):
        if p not in sys.path:
            monkeypatch.syspath_prepend(p)
    monkeypatch.setenv("MCP_PATH_TOKEN", "test")
    monkeypatch.delitem(sys.modules, "server", raising=False)

    import server as S
    return S


def test_the_module_loads(server):
    """THE DEFECT. Every name used at module scope has to resolve, or the
    container exits(1) before it ever listens on 8080."""
    assert server.mcp is not None


def test_the_connection_helper_is_a_context_manager(server):
    """The exact line that failed: `_conn` is used as `with _conn() as c` by
    every tool, so it must be decorated AND its decorator imported."""
    assert hasattr(server._conn, "__wrapped__") or callable(server._conn), \
        "_conn is not callable"
    cm = server._conn.__call__
    assert cm is not None
    # It has to produce a context manager, not a bare generator.
    obj = server._conn.__wrapped__ if hasattr(server._conn, "__wrapped__") \
        else server._conn
    assert callable(obj)


def test_every_tool_function_is_defined(server):
    """A tool named in the roster but absent from the module would be a
    404 at call time rather than a load failure — same blindness, later."""
    import re
    src = (MCP_DIR / "server.py").read_text()
    named = re.findall(r"@mcp\.tool\(\)\s*\n(?:@\w+\s*\n)*def (\w+)", src)
    assert named, "no @mcp.tool functions parsed"
    missing = [n for n in named if not callable(getattr(server, n, None))]
    assert not missing, f"declared as tools but not callable: {missing}"


def test_ast_parse_alone_would_not_have_caught_it():
    """Pinning WHY the hand-check before the failed deploy passed, so nobody
    re-adopts it as sufficient. `ast.parse` is a syntax check; the failure
    was a name that did not resolve at run time."""
    import ast
    broken = "from __future__ import annotations\n@contextmanager\ndef f():\n    yield\n"
    ast.parse(broken)                      # parses happily
    with pytest.raises(NameError):
        exec(compile(broken, "<broken>", "exec"), {})
