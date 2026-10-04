"""The run's NAMED peer set, scored or not — defined once (RC-10).

SWBC gold audit 2026-10-04 (RC-10; D-08, D-17). The owner decision for the
engagement is that peers are IDENTIFIED, not SCORED. The run still had a
locked peer set — Assurant, Fortegra, TruStage, in the research workbook's
`Handoff_Lock` and the report's Peer Comparison — and peer rows on two
platform tiles. Every peer gate keyed off `peer_scores` (empty by that
decision) or off a row that already carried peer fields, so:

  · AG-04 skipped any tile with neither peer_coverage nor peer_deployments
    (`if cov is None and not rows: continue`) — 6 of 8 tiles invisible,
    37 of 40 peer x tile verdicts absent rather than `deployed: null`;
  · O1's proxy_disclosure said "the comparison organisations identified for
    this assessment" and named none of them.

"Identified but not scored" was read as "no peers". This module is the one
definition both gates use:

    the run holds a named peer set  ⇔  peer_scores has rows for it
                                     ∨  the workbook states a locked_peer_set
                                        (run_manifest.payload.workbook_metadata)
                                     ∨  any peer_deployments row names a peer
                                        on this payload or the run's live
                                        platform / techstack submissions

Every read is failure-tolerant: a gate that cannot read its peer set must
not block a run on the strength of a set it never saw (the discipline
`_run_peer_names` keeps). The pure cores take dicts, so a unit test needs no
database.
"""
from __future__ import annotations

import json
import re

_PEER_PAGES = ("platform", "techstack")


def peer_key(name) -> str:
    """The first alphanumeric token, lowercased: 'TruStage/CUNA Mutual' and
    'TruStage' are one peer; 'Fortegra Group' and 'Fortegra' are one peer."""
    m = re.match(r"\W*([A-Za-z0-9]+)", str(name or ""))
    return m.group(1).lower() if m else ""


def split_locked(raw) -> list:
    """The workbook's `locked_peer_set` — 'A|B|C' on Handoff_Lock, or a list."""
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else re.split(r"[|;\n]", str(raw))
    return [str(x).strip() for x in items if x is not None and str(x).strip()]


def _rows(node):
    """Every peer_deployments row anywhere in a payload."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "peer_deployments" and isinstance(v, list):
                for r in v:
                    if isinstance(r, dict):
                        yield r
            else:
                yield from _rows(v)
    elif isinstance(node, list):
        for v in node:
            yield from _rows(v)


def _add(out: dict, name) -> None:
    k = peer_key(name)
    if k and k not in out:
        out[k] = str(name).strip()


def run_peer_set(conn, run_id, payload) -> dict:
    """{peer_key: display name}, first-seen order. Empty when the run
    demonstrably holds no named peer."""
    out: dict = {}
    if conn is not None:
        try:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT peer_name FROM peer_scores "
                        "WHERE run_id = %s ORDER BY peer_name", (run_id,))
            for (name,) in cur.fetchall():
                _add(out, name)
        except Exception:                                      # noqa: BLE001
            pass
        try:
            cur = conn.cursor()
            cur.execute("""SELECT payload -> 'workbook_metadata' -> 'locked_peer_set',
                                  payload -> 'manifest' -> 'locked_peer_set'
                             FROM run_manifest WHERE run_id = %s""", (run_id,))
            row = cur.fetchone()
            for raw in (row or ()):
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except ValueError:
                        pass
                for name in split_locked(raw):
                    _add(out, name)
        except Exception:                                      # noqa: BLE001
            pass
    for r in _rows(payload):
        _add(out, r.get("peer"))
    if conn is not None:
        from .validation2 import _live_submission
        for page in _PEER_PAGES:
            for r in _rows(_live_submission(conn, run_id, page)):
                _add(out, r.get("peer"))
    return out


def _reason(gate, section, path, message):
    return {"gate_id": gate, "section": section, "path": path,
            "message": message, "severity": "block"}


def named_peer_findings(page: str, payload: dict, peers: dict) -> list:
    """AG-04, the named-set half: every platform tile carries one
    peer_deployments row per named peer, each with a basis."""
    if page != "platform" or not peers or not isinstance(payload, dict):
        return []
    story = payload.get("platform_story")
    tiles = story.get("platforms") if isinstance(story, dict) else None
    if not isinstance(tiles, list):
        return []
    names = ", ".join(peers.values())
    out = []
    for i, t in enumerate(tiles):
        if not isinstance(t, dict):
            continue
        rows = [r for r in (t.get("peer_deployments") or []) if isinstance(r, dict)] \
            if isinstance(t.get("peer_deployments"), list) else []
        have = {peer_key(r.get("peer")) for r in rows}
        missing = [v for k, v in peers.items() if k not in have]
        unladdered = [str(r.get("peer")) for r in rows
                      if peer_key(r.get("peer")) in peers
                      and not str(r.get("basis") or "").strip()]
        problems = []
        if missing:
            problems.append(f"no row for {', '.join(missing)}")
        if unladdered:
            problems.append(f"no basis on the row for {', '.join(unladdered)}")
        if problems:
            out.append(_reason(
                "AG-04", "platform_story",
                f"platform_story.platforms[{i}].peer_deployments",
                f"{t.get('platform')!r}: {'; '.join(problems)}. This run identified "
                f"a peer set ({names}) — identified, not scored, is still a peer "
                "set — so every tile carries exactly one row per named peer: "
                "deployed true or false where established, deployed null where "
                "not, and every row states its basis (for null, the ladder that "
                "could not establish it). A tile silent about the peers reads as "
                "one nobody compared (SWBC: 6 of 8 tiles bare, 37 of 40 verdicts "
                "absent; RC-10, D-08)"))
    return out


def o1_cohort_findings(page: str, payload: dict, peers: dict) -> list:
    """CG-44, the named-cohort half: where O1 discloses that no peer median
    exists, it names the identified cohort; and a null peer_basis on a run
    with an identified set is stamped cannot_estimate."""
    if page != "overview" or not peers or not isinstance(payload, dict):
        return []
    scores = payload.get("scores")
    pillars = scores.get("pillars") if isinstance(scores, dict) else None
    entries = list(pillars.values()) if isinstance(pillars, dict) else pillars
    if not isinstance(entries, list):
        return []
    names = ", ".join(peers.values())
    silent, unstamped = [], []
    for e in entries:
        if not isinstance(e, dict) or e.get("peer_median") is not None:
            continue
        disc = str(e.get("proxy_disclosure") or "").lower()
        if not any(re.search(rf"\b{re.escape(k)}", disc) for k in peers):
            silent.append(str(e.get("pillar_id") or "?"))
        if e.get("peer_basis") is None:
            unstamped.append(str(e.get("pillar_id") or "?"))
    out = []
    if silent:
        out.append(_reason(
            "CG-44", "scores", "scores.pillars[].proxy_disclosure",
            f"pillar(s) {', '.join(silent)} disclose that no peer median exists "
            f"and name none of the identified peers ({names}). Name the cohort "
            "as identified, not scored — the owner allows it to the customer "
            "(2026-10-04) — so the absence states who it is about (RC-10(c), "
            "D-17)"))
    if unstamped:
        out.append(_reason(
            "CG-44", "scores", "scores.pillars[].peer_basis",
            f"pillar(s) {', '.join(unstamped)} carry peer_basis null on a run "
            f"with an identified peer set ({names}). Stamp cannot_estimate: "
            "null reads as never looked, cannot_estimate as looked and could "
            "not compare (RC-10(d))"))
    return out


def check_named_peer_set(conn, run_id, page, payload) -> list:
    """The wrapper validation2 calls: read the set once, run both halves."""
    if page not in ("platform", "overview"):
        return []
    peers = run_peer_set(conn, run_id, payload)
    if not peers:
        return []
    return (named_peer_findings(page, payload, peers)
            + o1_cohort_findings(page, payload, peers))
