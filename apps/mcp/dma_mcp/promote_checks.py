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

Five checks:

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
  completeness   CG-COMPLETE: peer figures the package's peer table holds are
                 served, and the opportunity tiles / platform cards cover the
                 full catalogue's top min(5, READY) platforms through the fit
                 engine (AAA WCNY, 2026-10-15).
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


# ── completeness (CG-COMPLETE) ───────────────────────────────────────────
TILES_WANTED = 5          # the contract's "Five tiles"


def _norm(name) -> str:
    return " ".join(str(name or "").casefold().split())


def _block(section, path, message):
    return {"gate_id": "CG-COMPLETE", "section": section, "path": path,
            "severity": "block", "message": message}


def _peered_categories(cur, run_id) -> set:
    cur.execute("""SELECT category_id FROM peer_scores
                    WHERE run_id = %s AND score IS NOT NULL
                    GROUP BY category_id HAVING count(*) >= 3""", (run_id,))
    return {str(r[0]).upper() for r in cur.fetchall() if r and r[0]}


def _catalogue_ready(conn, cur, run_id) -> list:
    """The full catalogue through the fit engine: READY rows, engine order."""
    return [p for p in _catalogue_scored(conn, cur, run_id)
            if p.get("state") == "READY"]


def _catalogue_scored(conn, cur, run_id) -> list:
    """Every catalogue platform through the fit engine, engine order."""
    from . import fit as fit_mod
    cur.execute("""
        SELECT p.l3_id, p.platform_name FROM ccg_l3_platforms p
         WHERE p.version = COALESCE(
                  (SELECT r.ccg_catalog_version FROM runs r WHERE r.id = %s),
                  (SELECT version FROM ccg_versions WHERE is_current))
         ORDER BY p.l3_id""", (run_id,))
    cands = [{"platform": name, "l3_area": f"[{code}] {name}"}
             for code, name in cur.fetchall() if code and name]
    if not cands:
        return []
    got = fit_mod.platform_fit(conn, run_id, cands) or {}
    rows = [p for p in (got.get("platforms") or []) if isinstance(p, dict)]
    return sorted(rows, key=lambda p: (p.get("rank") is None, p.get("rank") or 999,
                                       -(p.get("fit_score") or 0)))


def _estate_vendors(pay, cur, run_id) -> list:
    """Catalogue vendors the promoted register places in the estate."""
    items = ((pay.get("techstack") or {}).get("techstack") or {}).get("items") or []
    held = {str(i.get("vendor") or "").strip().lower(): str(i.get("vendor")).strip()
            for i in items if isinstance(i, dict)
            and str(i.get("status") or "").upper() in ("CONFIRMED", "INFERRED", "CLAIMED")}
    try:
        cur.execute("""
            SELECT DISTINCT p.vendor FROM ccg_l3_platforms p
             WHERE p.version = COALESCE(
                      (SELECT r.ccg_catalog_version FROM runs r WHERE r.id = %s),
                      (SELECT version FROM ccg_versions WHERE is_current))""", (run_id,))
        cat = {v.strip().lower() for (raw,) in cur.fetchall() if raw
               for v in re.split(r"\s*/\s*", str(raw))}
    except Exception:                                 # noqa: BLE001
        return []
    return sorted(v for k, v in held.items() if k and k in cat)


def completeness(conn, run_id, live: dict) -> dict:
    """{page: reasons} — CG-COMPLETE. Arithmetic over the staged payloads, the
    package's peer_scores and the fit engine; nothing here is a judgement."""
    out: dict = {}
    cur = conn.cursor()
    pay = {p: payload_json((live.get(p) or {}).get("payload")) or {} for p in live}

    peered = _peered_categories(cur, run_id)
    pillars = {c[:2] for c in peered}
    if peered:
        for row in ((pay.get("overview") or {}).get("scores") or {}).get("pillars") or []:
            if isinstance(row, dict) and str(row.get("pillar_id") or "").upper() in pillars \
                    and row.get("peer_median") is None:
                out.setdefault("overview", []).append(_block(
                    "scores", f"overview.scores.pillars[{row.get('pillar_id')}].peer_median",
                    f"peer_median is null for {row.get('pillar_id')} while the package's "
                    f"peer table scores {len(peered)} categor(ies) with three or more "
                    f"peers. Serve the workbook's peer figure with its basis."))
        ws = (pay.get("heatmap") or {}).get("workbook_scores") or {}
        for grain, keys in (("pillars", pillars), ("categories", peered)):
            rows = ws.get(grain) if isinstance(ws, dict) else None
            if not isinstance(rows, dict):
                continue
            for k, v in rows.items():
                if str(k).upper() in keys and isinstance(v, dict) and v.get("peer_median") is None:
                    out.setdefault("heatmap", []).append(_block(
                        "workbook_scores", f"heatmap.workbook_scores.{grain}.{k}.peer_median",
                        f"peer_median is null for {k} while the package's peer table "
                        f"scores it with three or more peers."))

    try:
        scored = _catalogue_scored(conn, cur, run_id)
    except Exception as exc:                          # noqa: BLE001
        msg = (f"the fit engine could not score the catalogue at promote "
               f"({type(exc).__name__}); an opportunity set nobody checked is "
               f"unchecked, not complete")
        out.setdefault("overview", []).append(_block("opportunity", "overview.opportunity", msg))
        return out
    # THE ESTATE (the fit engine's in_estate / vendor_in_estate /
    # replaces_in_estate): what the client already runs is discarded and
    # optimized, never tiled; a replacement is discarded; an extension of an
    # org the client owns says to verify its rollout first.
    owned = [p for p in scored if p.get("in_estate")]
    ready_all = [p for p in scored if p.get("state") == "READY" and not p.get("in_estate")]
    ready = [p for p in ready_all if not p.get("replaces_in_estate")]
    want = min(TILES_WANTED, len(ready))
    cut = ready[want - 1] if want else None
    replaces = [p for p in ready_all if p.get("replaces_in_estate")
                and (cut is None or ready_all.index(p) < ready_all.index(cut))]
    op = (pay.get("overview") or {}).get("opportunity") or {}
    disc = {_norm(d.get("platform")) for d in (op.get("discarded") or []) if isinstance(d, dict)}
    tiles_all = [t for t in (op.get("tiles") or []) if isinstance(t, dict)]
    by_name = {_norm(p.get("platform")): p for p in scored}
    for i, t in enumerate(tiles_all):
        p = by_name.get(_norm(t.get("platform"))) or {}
        ctx = _norm(f"{t.get('their_stack_context') or ''} {t.get('rank_rationale') or ''}")
        if p.get("in_estate"):
            out.setdefault("overview", []).append(_block(
                "opportunity", f"overview.opportunity.tiles[{i}]",
                f"'{t.get('platform')}' is already in the client's estate ({p['in_estate']}): "
                f"the contract discards a platform the client already runs; carry it as an "
                f"optimization recommendation."))
        elif p.get("replaces_in_estate"):
            out.setdefault("overview", []).append(_block(
                "opportunity", f"overview.opportunity.tiles[{i}]",
                f"'{t.get('platform')}' would replace {', '.join(p['replaces_in_estate'])}, "
                f"which the client runs: a replacement is a discard, never a tile."))
        elif p.get("vendor_in_estate") and not any(w in ctx for w in ("verify", "confirm")):
            out.setdefault("overview", []).append(_block(
                "opportunity", f"overview.opportunity.tiles[{i}].their_stack_context",
                f"'{t.get('platform')}' extends a vendor org the client already runs: say to "
                f"verify its rollout and entitlement on that org before it is proposed."))
    for p in owned + replaces:
        if _norm(p.get("platform")) not in disc:
            out.setdefault("overview", []).append(_block(
                "opportunity", "overview.opportunity.discarded",
                f"'{p.get('platform')}' "
                + (f"is in the client's estate ({p['in_estate']})" if p.get("in_estate")
                   else f"would replace {', '.join(p.get('replaces_in_estate') or [])}")
                + " and is not listed as discarded with that reason."))
    recs = json.dumps(((pay.get("platform") or {}).get("recommendations") or {})
                      .get("recommendations") or []).lower()
    recs = " ".join(re.sub(r"[^a-z0-9]+", " ", recs).split())
    for v in _estate_vendors(pay, cur, run_id):
        if " ".join(re.sub(r"[^a-z0-9]+", " ", v.lower()).split()) not in recs:
            out.setdefault("platform", []).append(_block(
                "recommendations", "platform.recommendations",
                f"the client already runs {v} (technology register) and no recommendation "
                f"addresses optimizing what it owns there."))
    if not want:
        return out
    story = (pay.get("platform") or {}).get("platform_story") or {}
    cards = [c for c in (story.get("platforms") or []) if isinstance(c, dict)]
    have = {_norm(c.get("platform")) for c in cards}
    miss = [str(p.get("platform")) for p in ready[:want] if _norm(p.get("platform")) not in have]
    if miss:
        out.setdefault("platform", []).append(_block(
            "platform_story", "platform.platform_story.platforms",
            f"the catalogue's top {want} READY platform(s) need a card each; missing "
            f"{', '.join(miss)} ({len(ready)} READY of the full catalogue)."))
    tiles = [t for t in ((pay.get("overview") or {}).get("opportunity") or {}).get("tiles") or []
             if isinstance(t, dict)]
    if len(tiles) < want:
        out.setdefault("overview", []).append(_block(
            "opportunity", "overview.opportunity.tiles",
            f"{len(tiles)} tile(s); the fit engine scores {len(ready)} READY platform(s) "
            f"across the full catalogue, so the overview serves {want}."))
    skip = {_norm(p.get("platform")) for p in owned + replaces}
    ranked = sorted([c for c in cards if isinstance(c.get("rank"), (int, float))
                     and _norm(c.get("platform")) not in skip],
                    key=lambda c: c["rank"])[:want]
    if [_norm(t.get("platform")) for t in tiles[:want]] != [_norm(c.get("platform")) for c in ranked]:
        out.setdefault("overview", []).append(_block(
            "opportunity", "overview.opportunity.tiles",
            f"the tiles must be the top {want} platform cards in card-rank order "
            f"({', '.join(str(c.get('platform')) for c in ranked)}); served "
            f"{', '.join(str(t.get('platform')) for t in tiles)}."))
    return out


def extra_reasons(conn, run_id, live: dict) -> tuple[dict, dict]:
    """Every promote-time re-check, merged by page, plus a report."""
    merged: dict = {}
    for page, rs in completeness(conn, run_id, live).items():
        merged.setdefault(page, []).extend(rs)
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
