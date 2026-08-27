#!/usr/bin/env python3
"""Generate MCP-TOOLS.md from apps/mcp/server.py — signatures via AST, prose
from the tools' own docstrings. Regenerate rather than hand-edit."""
import ast, json, pathlib, subprocess, textwrap, sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
# Works from a repo checkout (apps/mcp/server.py) and from inside the
# packaged service, where server.py sits at the archive root.
SERVER = ROOT / "apps/mcp/server.py"
if not SERVER.exists():
    SERVER = ROOT / "server.py"
if not SERVER.exists():
    raise SystemExit(f"no server.py under {ROOT.resolve()}")
OUT = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pathlib.Path("MCP-TOOLS.md")

GROUPS = [
 ("Read the assessment", "Pure reads of what the package and the catalogue already say. None of them write; all of them are safe to call again.",
  ["get_report_bundle","get_capability_catalogue","get_page_contract","get_evidence","get_platform_fit"]),
 ("Run and session state", "Which runs exist, who holds them, and what is still outstanding. `list_open_rejections` is the one to read first in any producer session.",
  ["list_pending_runs","claim_run","get_run_progress","get_client_state","list_open_rejections"]),
 ("Author and submit", "The write path. Content enters the system only here, and only through `submit_page_payload`.",
  ["register_evidence","open_payload","append_payload_part","submit_page_payload","get_staged_payload"]),
 ("Verdicts and promotion", "What the gates said, and moving a run on or off the client surface.",
  ["get_validation_verdict","explain_gate","promote_run","withdraw_run","list_withdrawn_runs"]),
 ("Enrichment ledger", "Holds together the two halves of \"the work was done but it is not showing\": what was enriched, and what is still empty.",
  ["record_enrichment","list_enrichment_gaps"]),
 ("Findings memory", "What went wrong, how it was measured, what was changed, and whether the change held. These write no serving content.",
  ["record_finding","search_findings","list_open_findings","get_finding","list_defect_classes",
   "record_refinement","resolve_finding","report_recurrence","get_memory_digest"]),
 ("Reviewer feedback", "Reviewer verdicts on insight cards, and their route into the findings memory.",
  ["list_reviewer_feedback","ingest_reviewer_feedback"]),
]

def collect():
    tree = ast.parse(SERVER.read_text())
    out = {}
    order = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(getattr(d.func if isinstance(d, ast.Call) else d, "attr", None) == "tool"
                   for d in node.decorator_list):
            continue
        a = node.args
        defaults = [None]*(len(a.args)-len(a.defaults)) + [ast.unparse(d) for d in a.defaults]
        params = [{"name": arg.arg,
                   "type": ast.unparse(arg.annotation) if arg.annotation else "",
                   "default": defaults[i]} for i, arg in enumerate(a.args)]
        out[node.name] = {
            "name": node.name,
            "params": params,
            "returns": ast.unparse(node.returns) if node.returns else "",
            "doc": (ast.get_docstring(node) or "").strip(),
            "async": isinstance(node, ast.AsyncFunctionDef),
        }
        order.append(node.name)
    return out, order

def sig(t):
    bits = []
    for p in t["params"]:
        s = p["name"]
        if p["type"]: s += f": {p['type']}"
        if p["default"] is not None: s += f" = {p['default']}"
        bits.append(s)
    return f"{t['name']}({', '.join(bits)})" + (f" -> {t['returns']}" if t["returns"] else "")

def git(*args, default="unknown"):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return default

def main():
    tools, order = collect()
    named = [n for _, _, names in GROUPS for n in names]
    missing = [n for n in order if n not in named]
    extra = [n for n in named if n not in tools]
    if missing or extra:
        raise SystemExit(f"grouping out of date — ungrouped: {missing}  unknown: {extra}")

    sha, date = git("rev-parse","HEAD"), git("log","-1","--format=%ad","--date=short")
    L = []
    w = L.append
    w("# DMA Insights MCP connector — tool reference\n")
    rel = SERVER.relative_to(ROOT) if SERVER.is_relative_to(ROOT) else SERVER
    prov = (f"at commit `{sha[:10]}` ({date})" if sha != "unknown"
            else "outside a git checkout, so no commit is stamped")
    w(f"Generated from `{rel}` {prov} by "
      "`gen_tools_md.py`. Signatures and defaults are read from the source with "
      "`ast`; the description of each tool is that tool's own docstring, verbatim. "
      "Regenerate rather than hand-edit.\n")
    w(f"**{len(tools)} tools.** Python MCP SDK over streamable HTTP, deployed as the "
      "`mcp` Cloud Run service on session-mode pooling (promotion holds locks).\n")

    w("## What constrains every tool here\n")
    w("These are properties of the connector, not advice — a tool that appears to "
      "offer a way around one is being misread.\n")
    w("| | |")
    w("|---|---|")
    w("| **Content enters only here** | The API writes annotations and alert actions and nothing else. No endpoint writes serving content. |")
    w("| **Promotion is atomic across all six pages** | One transaction, `SELECT … FOR UPDATE` on the run row, ordered writers, all-or-nothing. Promoted staging rows are retained, so one page can be fixed and re-promoted without re-synthesising five. |")
    w("| **Evidence fails closed** | Every cited id must resolve, belong to this entity and this run, and carry a verbatim 50–500 character excerpt. `get_evidence` returns `found` / `not_found` / `foreign`, and **`foreign` halts production**. |")
    w("| **The server allocates identifiers** | The agent mints only `ic_id`, `f_id`, `fa_id`, `ts_id`, `wn_id` and authored `rec_id`. Everything else comes from the catalogue or from `register_evidence`. |")
    w("| **Verdicts name the gate, the JSON path and the arithmetic** | Gate families: AG (analysis), SG (safeguard), ET (entity/identity), CG (contract/grain). A failing SG discloses and still promotes; a failing evidence reason never does. |")
    w("| **No model call on the serving path** | The bundled 384-dim embedding model runs only inside this connector, at submit, for the V4 grounding check. |")
    w("")

    w("## Index\n")
    w("| # | Tool | Group | What it is for |")
    w("|---:|---|---|---|")
    i = 0
    for title, _, names in GROUPS:
        for n in names:
            i += 1
            first = " ".join(tools[n]["doc"].split("\n")[0:2]).strip()
            first = first.split(". ")[0].rstrip(".")
            if len(first) > 96: first = first[:93].rstrip() + "…"
            w(f"| {i} | [`{n}`](#{n.replace('_','-')}) | {title} | {first} |")
    w("")

    for title, blurb, names in GROUPS:
        w(f"## {title}\n")
        w(blurb + "\n")
        for n in names:
            t = tools[n]
            w(f"### `{n}`\n")
            w("```python")
            w(textwrap.fill(sig(t), 88, subsequent_indent="    "))
            w("```\n")
            ps = [p for p in t["params"] if p["name"] != "self"]
            if ps:
                w("| Parameter | Type | Default |")
                w("|---|---|---|")
                for p in ps:
                    d = "**required**" if p["default"] is None else f"`{p['default']}`"
                    w(f"| `{p['name']}` | `{p['type'] or '—'}` | {d} |")
                w("")
            else:
                w("*No parameters.*\n")
            w(t["doc"] if t["doc"] else "_No docstring in source._")
            w("")

    w("---\n")
    w(f"_{len(tools)} tools · generated from `{rel}`"
      + (f" @ `{sha[:10]}`._" if sha != "unknown" else "._"))
    OUT.write_text("\n".join(L) + "\n")
    print(f"wrote {OUT}  ({len(tools)} tools, {OUT.stat().st_size} bytes)")

main()
