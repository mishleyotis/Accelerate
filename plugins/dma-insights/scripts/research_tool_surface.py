"""The research layer's tool surface: specific names, clear descriptions,
preset arguments — applied by evidence_proxy.py, read by the hooks.

WHY (owner, 2026-10-11): "For each of the MCP tools, avoid generic names,
split by functionality to ensure thorough results, as per gold standard
requirements. Ensure clear description of tools." The four plugin research
services (evidence, searxng, fetch, edgar) are third-party or engine
servers whose tool names say what the CODE does (`research_brief`, `fetch`,
`get_company_facts`), not what the agent gets: which source class, which
tier it earns, which gold-workbook columns the output fills. One proxy
process already sits between every agent and each service, so the surface
lives there — no fork of a third-party server, and a change ships with the
plugin version that describes it.

THE RULE.
  present(service, upstream_tools) — the agent's tools/list: one tool per
    entry in references/research_tool_surface.json whose upstream tool the
    service lists, under the entry's name, with its description (+ the named
    appendix) and the upstream schema minus `preset` and `hide` arguments.
    An upstream tool no entry names is NOT listed.
  to_upstream(service, params) — a tools/call's params with the surfaced
    name mapped back to the upstream tool and the preset arguments set
    (a preset wins over anything the caller sent). An unknown name passes
    through unchanged, so the service answers it as it always has.
  full_name(service, name) — `mcp__plugin_dma-insights_<service>__<name>`,
    the name hooks and agent manifests carry (<= 64 characters, the API's
    limit; the test pins it).
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
SURFACE_PATH = HERE.parent / "references" / "research_tool_surface.json"
SERVICES = ("evidence", "searxng", "fetch", "edgar")
PREFIX = "mcp__plugin_dma-insights_"
MAX_TOOL_NAME = 64


@lru_cache(maxsize=1)
def surface() -> dict:
    return json.loads(SURFACE_PATH.read_text(encoding="utf-8"))


def entries(service: str) -> list[dict]:
    return list(surface().get(service) or [])


def full_name(service: str, name: str) -> str:
    return f"{PREFIX}{service}__{name}"


def names(service: str, kinds=None) -> list[str]:
    """Surfaced short names for a service, optionally only those of `kinds`."""
    return [e["name"] for e in entries(service) if kinds is None or e.get("kind") in kinds]


def full_names(service: str, kinds=None) -> tuple[str, ...]:
    return tuple(full_name(service, n) for n in names(service, kinds))


def description(entry: dict) -> str:
    text = entry["description"].strip()
    app = entry.get("appendix")
    if app:
        text += "\n\n" + surface()["appendices"][app].strip()
    return text


def _schema(upstream_schema: dict, drop: set[str]) -> dict:
    s = copy.deepcopy(upstream_schema or {"type": "object", "properties": {}})
    props = s.get("properties") or {}
    for k in drop:
        props.pop(k, None)
    if "required" in s:
        s["required"] = [r for r in s["required"] if r not in drop]
    s["properties"] = props
    return s


def present(service: str, upstream_tools: list) -> list:
    """The agent-facing listing for one service. A service the surface does
    not describe is served unchanged."""
    if service not in surface():
        return list(upstream_tools or [])
    by_name = {t.get("name"): t for t in upstream_tools or [] if isinstance(t, dict)}
    out = []
    for e in entries(service):
        up = by_name.get(e["upstream"])
        if up is None:
            continue
        drop = set(e.get("preset") or {}) | set(e.get("hide") or ())
        tool = {"name": e["name"], "description": description(e),
                "inputSchema": _schema(up.get("inputSchema") or {}, drop)}
        for k in ("annotations", "title"):
            if k in up:
                tool[k] = copy.deepcopy(up[k])
        out.append(tool)
    return out


def instructions(service: str) -> str | None:
    """The server instructions an agent reads at initialize, naming the
    surfaced tools (the upstream service's own text names the generic ones)."""
    return (surface().get("instructions") or {}).get(service)


def with_instructions(service: str, result: dict) -> dict:
    """An upstream initialize result with this service's instructions set."""
    text = instructions(service)
    if not text or not isinstance(result, dict):
        return result
    return {**result, "instructions": text}


def to_upstream(service: str, params: dict) -> dict:
    """tools/call params, surfaced name -> upstream name + presets."""
    params = dict(params or {})
    for e in entries(service):
        if e["name"] == params.get("name"):
            args = dict(params.get("arguments") or {})
            for k in e.get("hide") or ():
                args.pop(k, None)
            args.update(copy.deepcopy(e.get("preset") or {}))
            params.update(name=e["upstream"], arguments=args)
            return params
    return params


def upstream_of(service: str, name: str) -> str:
    for e in entries(service):
        if e["name"] == name:
            return e["upstream"]
    return name
