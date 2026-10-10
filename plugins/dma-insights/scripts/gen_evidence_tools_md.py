#!/usr/bin/env python3
"""Generate docs/EVIDENCE-ENGINE-TOOLS.md from apps/evidence-engine/evidence_server.py.

Signatures via `ast`, prose from each tool's own docstring, verbatim —
the same discipline as gen_mcp_tools_md.py. Regenerate, never hand-edit:

    python3 plugins/dma-insights/scripts/gen_evidence_tools_md.py [--check]
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SERVER = REPO / "apps" / "evidence-engine" / "evidence_server.py"
OUT = HERE.parent / "docs" / "EVIDENCE-ENGINE-TOOLS.md"


def tools() -> list[dict]:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    out = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(isinstance(d, ast.Call) and getattr(getattr(d.func, "attr", None), "__str__", lambda: "")() == "tool"
                   or (isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool") for d in node.decorator_list):
            continue
        args = []
        a = node.args
        defaults = [None] * (len(a.args) - len(a.defaults)) + list(a.defaults)
        for arg, d in zip(a.args, defaults):
            ann = ast.unparse(arg.annotation) if arg.annotation else ""
            s = f"{arg.arg}: {ann}" if ann else arg.arg
            if d is not None:
                s += f" = {ast.unparse(d)}"
            args.append(s)
        out.append({"name": node.name, "args": args, "doc": ast.get_docstring(node) or ""})
    return out


def render(ts: list[dict]) -> str:
    lines = ["# The evidence engine — tool reference", "",
             f"Generated from `apps/evidence-engine/evidence_server.py` by `gen_evidence_tools_md.py`; "
             "signatures read with `ast`, descriptions are each tool's docstring verbatim. Regenerate rather than hand-edit.",
             "", f"**{len(ts)} tools**, FastMCP over streamable HTTP, deployed as `dmai-evidence` "
             "(plugin server name `evidence`, scoped tool prefix `mcp__plugin_dma-insights_evidence__`). "
             "Contract: `apps/evidence-engine/docs/CARD-CONTRACT.md`.", "",
             "| Tool | Signature |", "|---|---|"]
    for t in ts:
        lines.append(f"| `{t['name']}` | `{t['name']}({', '.join(t['args'])})` |")
    lines.append("")
    for t in ts:
        lines += [f"## `{t['name']}`", "", "```", f"{t['name']}({', '.join(t['args'])})", "```", "", t["doc"], ""]
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None) -> int:
    check = "--check" in (argv or sys.argv[1:])
    text = render(tools())
    if check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT} is stale; run gen_evidence_tools_md.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
