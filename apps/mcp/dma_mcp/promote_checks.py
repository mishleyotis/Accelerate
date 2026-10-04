"""What promote_run re-checks on RETAINED rows, beyond the pure pass-1 gates.

RC-13 (SWBC gold audit, 2026-10-04): validation ran at submit; promote
re-ran only `validate_pass1`, which is pure. Everything that depends on the
WORLD rather than on the payload — the fit engine, the run's own lifecycle
status, the gold shape, the deployed revision — was carried forward from the
day each page was submitted. Measured on the run that prompted the audit:

  · served relevance 1.0 and fits 58.9 / … while today's engine, after the
    2026-10-02 sub-vertical binding and the 2026-10-04 deploy, returned
    0.971-0.98 and 57.2 / 39.7 / 44.6 / 28.2 — CG-30/CG-31 had run once, at
    submit, against an engine context that no longer existed;
  · a section produced while the run was WITHDRAWN promoted unchanged, so a
    promoted page told its reader the run was "withheld pending repair";
  · no structural parity measurement ever touched the run (RC-02).

Invariant 3 keeps retained staging rows — correctly, so one page can be
fixed without re-synthesising five. These checks are what makes a retained
row safe to carry: each returns blocking reasons in the verdict shape, keyed
by page, and promote refuses on them exactly as it refuses a pass-1 reason
(SG excepted, per invariant 12). The refusal names the page; resubmitting
that one page is the repair.

Four checks:

  refit          CG-30 and CG-31 re-run against `get_platform_fit` now, and a
                 tile or card built on an UNCHECKED engine context (the
                 entity's sub-vertical unresolved, so relevance is null) is
                 refused under CG-30.
  run state      CG-STALE: a page that asserts the run being promoted is
                 withdrawn / withheld pending repair is refused — promotion
                 makes that sentence false the moment it succeeds.
  parity         CG-PAR: the staged pages against the committed gold shape
                 (`parity.py`, `surface_gold.json`), leaving the run's own
                 gold record out and preferring gold of its sub-vertical. A
                 STRUCTURAL gap refuses (owner decision B, 2026-10-04);
                 counts and fill ratios are warnings in the verdict.
  revision       the deployed connector's contract / gold / gate-set
                 fingerprint against what the caller's repo assumes, when the
                 caller says (`expected_revision`); otherwise RECORDED on the
                 result as unchecked — never reported as matched.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from . import parity

# ── run state ────────────────────────────────────────────────────────────
#
# Narrow on purpose. "withdrawn" alone is a real word in this corpus — an
# HMDA application withdrawn, a why-now signal withdrawn — and a gate that
# refused those would be refusing the client's facts. What is refused is a
# sentence about THIS RUN's lifecycle, which promotion makes false.
_RUN_STATE = re.compile(
    r"(withheld|withdrawn)\s+pending\s+repair"
    r"|\b(this|the|own)\s+(client'?s\s+own\s+)?run\b[^.;]{0,60}?"
    r"\b(is|was|has\s+been|remains|stays)\s+(withdrawn|withheld)\b",
    re.I)


def _strings(node, path=""):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, f"{path}[{i}]")


def stale_run_state(page: str, payload: dict) -> list:
    """CG-STALE over one page: empty_state and narrative_thread text that
    asserts the run being promoted is withdrawn or withheld."""
    out = []
    for section, body in sorted((payload or {}).items()):
        if not isinstance(body, dict):
            continue
        for key in ("empty_state", "narrative_thread"):
            for path, text in _strings(body.get(key), key):
                m = _RUN_STATE.search(text)
                if m:
                    out.append({
                        "gate_id": "CG-STALE", "section": section,
                        "path": f"{page}.{section}.{path}",
                        "severity": "block",
                        "message": (
                            f"this text says the run is {m.group(0)!r}, and "
                            "promoting it makes that false the moment it "
                            "succeeds. It was written while the run was "
                            "withdrawn and carried forward on a retained row. "
                            "Restate it for a promoted run (count what it "
                            "counts now) and resubmit this page.")})
    return out


# ── refit ────────────────────────────────────────────────────────────────
def refit(conn, run_id, live: dict) -> dict:
    """{page: reasons} — CG-30 on platform, CG-31 on overview, re-run now."""
    from . import validation2 as V
    out = {}
    plat = (live.get("platform") or {}).get("payload") or {}
    ov = (live.get("overview") or {}).get("payload") or {}
    try:
        r30 = V._check_platform_fit_is_the_engine_s(conn, run_id, "platform",
                                                    plat)
    except Exception as exc:                          # noqa: BLE001
        r30 = [{"gate_id": "CG-30", "section": "platform_story",
                "path": "platform.platform_story", "severity": "block",
                "message": f"the fit engine could not be re-run at promote "
                           f"({type(exc).__name__}); a fit nobody re-checked "
                           "is unchecked, not clean"}]
    r30 = list(r30) + _unchecked_context(conn, run_id, plat)
    if r30:
        out["platform"] = r30
    try:
        r31 = V._check_opportunity_tiles_are_the_engine_s(conn, run_id,
                                                          "overview", ov)
    except Exception as exc:                          # noqa: BLE001
        r31 = [{"gate_id": "CG-31", "section": "opportunity",
                "path": "overview.opportunity", "severity": "block",
                "message": f"the tile re-check raised {type(exc).__name__} at "
                           "promote; unchecked is not clean"}]
    if r31:
        out["overview"] = list(r31)
    return out


def _unchecked_context(conn, run_id, plat: dict) -> list:
    """A card scored while the engine could not see the client's vertical."""
    rows = ((plat.get("platform_story") or {}).get("platforms")
            if isinstance(plat.get("platform_story"), dict) else None)
    if not isinstance(rows, list) or not rows:
        return []
    try:
        from . import fit as fit_mod
        got = fit_mod.platform_fit(conn, run_id, [
            {"platform": r.get("platform"), "l3_area": r.get("l3_area")}
            for r in rows if isinstance(r, dict)])
    except Exception:                                 # noqa: BLE001
        return []          # the CG-30 re-run above already refused on this
    if (got.get("context") or {}).get("relevance_state") != "unchecked":
        return []
    return [{"gate_id": "CG-30", "section": "platform_story",
             "path": "platform.platform_story.platforms",
             "severity": "block",
             "message": ("the engine cannot resolve this entity's "
                         "sub-vertical, so vertical relevance is UNCHECKED "
                         "and every fit on these cards rests on a neutral "
                         "default. Bind the entity's sub-vertical, re-read "
                         "get_platform_fit, resubmit platform and overview.")}]


# ── parity ───────────────────────────────────────────────────────────────
def gold_parity(live: dict, run_id=None, sub_vertical=None) -> tuple[dict, dict]:
    """({page: CG-PAR reasons}, report) — the staged pages against the gold.

    Owner decision B (2026-10-04): only a STRUCTURAL gap refuses — a section
    or key the gold always serves is missing, or a must-present field is null
    or held beyond the decision-2 cap. Count and fill-ratio differences come
    back in `report["warnings"]` (severity "warn"), part of the promote
    verdict and never a refusal. The run being promoted is left out of its
    own reference set, and the gold of its sub-vertical is preferred; with
    none, the other gold is the reference for structure only.

    A missing or unreadable gold file REFUSES: a parity check that could not
    run must not read as parity (CHECK_NEVER_RAN_READS_AS_UNKNOWN)."""
    pages = {p: (s.get("payload") or {}) for p, s in live.items()}
    try:
        res = parity.check_run(pages, run_id=run_id,
                               sub_vertical=sub_vertical)
    except Exception as exc:                          # noqa: BLE001
        reason = {"gate_id": parity.GATE_ID, "section": None,
                  "path": "surface_gold.json", "severity": "block",
                  "message": f"the gold-shape parity check could not run "
                             f"({type(exc).__name__}: {str(exc)[:120]}); "
                             "unchecked is not parity"}
        return {"overview": [reason]}, {"error": str(exc)[:200]}

    def _reason(g):
        where = ".".join(str(x) for x in (g["page"], g["section"], g["key"])
                         if x)
        against = ", ".join(g.get("against") or []) or "the contract"
        return {"gate_id": parity.GATE_ID, "section": g["section"],
                "path": where, "severity": g["severity"], "kind": g["kind"],
                "message": (f"[{g['kind']}] {g['why']} (against {against}): "
                            f"{g['detail']}")}

    out: dict = {}
    for g in res["blocking"]:
        out.setdefault(g["page"], []).append(_reason(g))
    report = {"gaps": len(res["blocking"]),
              "warnings": [_reason(g) for g in res["warnings"]],
              "disclosed": res["disclosed"],
              "gold_runs": res["gold_runs"],
              "compared_against": res["compared_against"],
              "left_out": res["left_out"], "tier": res["tier"],
              "sub_vertical": res["sub_vertical"], "floors": res["floors"]}
    return out, report


def _sub_vertical(conn, run_id):
    """The entity's primary sub-vertical code, or None — read the way ET-05
    reads it, so parity and scope agree on who the client is."""
    try:
        from .validation2 import _entity_scope
        return _entity_scope(conn, run_id)[0]
    except Exception:                                 # noqa: BLE001
        return None      # unknown: cross-sub-vertical tier, structure only


# ── revision ─────────────────────────────────────────────────────────────
def _digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:
        return None


def deployed_revision() -> dict:
    """What THIS connector process validates against. Every field is read,
    none is assumed: an unset environment variable is reported as None."""
    from .submit import contract_version
    from . import gates
    here = Path(__file__).parent
    gate_ids = ",".join(sorted(gates.GATES))
    return {
        "contract_version": contract_version(),
        "gold_version": "sg-" + (_digest(here / "surface_gold.json") or "missing"),
        "gates_version": "gs-" + hashlib.sha256(gate_ids.encode()).hexdigest()[:12],
        # Set by the deploy when it knows the commit; Cloud Run sets
        # K_REVISION itself. Neither is guessed.
        "source_sha": os.environ.get("DMA_SOURCE_SHA") or None,
        "cloud_run_revision": os.environ.get("K_REVISION") or None,
    }


def revision_check(expected) -> tuple[dict | None, dict]:
    """(refusal-or-None, record). MEM-0039 / MEM-0562: a promote was nearly
    made against a production that did not carry the fixes the repository
    said were in. The connector cannot see the repository, so the caller
    states what its gates assumed; a mismatch refuses, an absence is
    recorded as UNCHECKED and never as a match."""
    rev = deployed_revision()
    if not isinstance(expected, dict) or not expected:
        return None, {"deployed_revision": rev,
                      "revision_check": ("unchecked: no expected_revision "
                                         "supplied, so whether production "
                                         "is behind the repository the "
                                         "gates assume was not measured")}
    behind, unknown = {}, []
    for key, want in sorted(expected.items()):
        have = rev.get(key)
        if have is None:
            unknown.append(key)
        elif str(want) != str(have):
            behind[key] = {"expected": want, "deployed": have}
    if behind:
        return ({"promoted": False, "error": "deployed_revision_behind",
                 "mismatch": behind, "deployed_revision": rev,
                 "hint": ("The connector serving this promote does not run "
                          "the contract/gates your repository assumes. "
                          "Deploy (merge to the default branch deploys), "
                          "confirm with verify_deployed, then promote. "
                          "Promoting now would validate against rules the "
                          "repository has already changed.")},
                {"deployed_revision": rev})
    note = "matched" if not unknown else (
        "matched on " + ", ".join(k for k in expected if k not in unknown)
        + "; unchecked (not exposed by this deployment): "
        + ", ".join(unknown))
    return None, {"deployed_revision": rev, "revision_check": note}


def local_revision(repo_root: Path) -> dict:
    """The same fingerprint computed from a checkout — what a caller passes
    as `expected_revision`. Mirrors `deployed_revision` field for field."""
    import importlib.util
    data = (repo_root / "apps" / "mcp" / "dma_mcp" / "contracts_data.json").read_bytes()
    gold = repo_root / "apps" / "mcp" / "dma_mcp" / "surface_gold.json"
    spec = importlib.util.spec_from_file_location(
        "_gates_local", repo_root / "apps" / "mcp" / "dma_mcp" / "gates.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    gate_ids = ",".join(sorted(mod.GATES))
    return {
        "contract_version": "cr-" + hashlib.sha256(data).hexdigest()[:12],
        "gold_version": "sg-" + (_digest(gold) or "missing"),
        "gates_version": "gs-" + hashlib.sha256(gate_ids.encode()).hexdigest()[:12],
    }


def extra_reasons(conn, run_id, live: dict) -> tuple[dict, dict]:
    """Every promote-time re-check, merged by page, plus a report."""
    merged: dict = {}
    for page, rs in refit(conn, run_id, live).items():
        merged.setdefault(page, []).extend(rs)
    for page, sub in live.items():
        rs = stale_run_state(page, sub.get("payload") or {})
        if rs:
            merged.setdefault(page, []).extend(rs)
    par, report = gold_parity(live, run_id=run_id,
                              sub_vertical=_sub_vertical(conn, run_id))
    for page, rs in par.items():
        merged.setdefault(page, []).extend(rs)
    return merged, {"parity": report}


def payload_json(payload):
    """Staged payloads may arrive as JSON text from some drivers."""
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except ValueError:
            return {}
    return payload
