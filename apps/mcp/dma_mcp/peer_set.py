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

Three corrections from the branch review (2026-10-04):

  · A STATISTIC IS NOT A PEER. Baxter's promoted run c1351d25 carries
    peer_scores rows named `Median`, `P25` and `P75` beside its five credit
    unions, and AG-04 asked every platform tile for "a row for Median, P25,
    P75". `is_statistic_name` drops statistic and cohort pseudo-names from
    every source the set is read from.
  · ONE ROW CAN NAME SEVERAL PEERS. goeasy's single peer_scores row is five
    names joined by semicolons; it is split as the locked set is.
  · THE LOCK IS THE SET. Where the workbook states a `locked_peer_set`, it
    is the run's peer set — the scored table and the payload rows are what a
    parser or a producer wrote, the lock is what the assessment fixed. Only
    without one is the set the union above. And the live submission of the
    page being validated is never read back into the set: it is what this
    submit replaces, and reading it made any peer once submitted impossible
    to correct.
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


#: Normalised names that are a statistic or a cohort label, never an
#: institution. Matched on the WHOLE normalised name (after the qualifier
#: below is stripped), so `Median Bancorp` and `Mean Green Credit Union` stay
#: peers while `Median`, `Peer median` and `Median (n=5)` do not.
_STAT_NAMES = frozenset({
    "median", "mean", "average", "avg", "mode", "min", "minimum", "max",
    "maximum", "range", "iqr", "count", "n", "total", "sum", "std", "stdev",
    "std_dev", "stddev", "sd", "standard_deviation", "variance", "delta",
    "gap", "benchmark", "benchmarks", "peer", "peers", "cohort", "group",
    "peer_group", "all", "all_peers", "industry", "sector", "best_in_class",
    "top_performer", "top_performers", "unknown", "n_a", "na", "none", "tbd",
    "blank", "other", "others", "entity", "entity_score", "score", "subject",
})
#: A qualifier that turns a statistic into a cohort statistic: `Peer
#: median`, `Cohort average`, `Industry P75`. Stripped once, from the front.
_STAT_QUALIFIER = re.compile(r"^(peer|peers|cohort|industry|sector|group|"
                             r"all_peers|peer_group|segment)_")
_STAT_PATTERNS = (
    re.compile(r"^p\d{1,2}$"),                                 # P25, P75, P90
    re.compile(r"^q[1-4]$"),                                    # Q1, Q3
    re.compile(r"^\d{1,2}(st|nd|rd|th)?_?(percentile|pctl|pct)$"),
    re.compile(r"^(percentile|pctl|pct)_?\d{1,2}(st|nd|rd|th)?$"),
    re.compile(r"^(top|bottom|upper|lower|first|second|third|fourth|"
               r"1st|2nd|3rd|4th)_(quartile|quintile|decile|tercile|half)$"),
    re.compile(r"^(quartile|quintile|decile|tercile)(_\d)?$"),
    # The worker's stat-header rules (workbook_parser._STAT_PATTERNS): gap
    # and difference columns. NOT a bare `delta_*`: Delta Community CU is a
    # real credit union.
    re.compile(r"^(gap|diff|difference|variance)(_|$)"),
    re.compile(r"^delta_(vs|to|from|median|peer)"),
    re.compile(r"(^|_)vs_"),
)


def is_statistic_name(name) -> bool:
    """True when `name` labels a statistic or a cohort, not an institution:
    Median, P25, P75, Mean, Average, Top quartile, Peer median, Q1, 25th
    percentile, Median (n=5), Gap_vs_Median, Peer group, Benchmark.

    A name that is a statistic is not a peer whatever table it sits in — a
    peer_scores row called `Median` is the cohort's median scored as if it
    were a credit union, and a gate that asks a platform tile for a
    deployment row about it is asking about arithmetic."""
    n = re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_")
    if not n:
        return True
    # A stated sample size is a qualifier, not part of the name: `Median
    # (n=5)`, `Average n 12`.
    n = re.sub(r"_n_?\d+$", "", n)
    candidates = {n, _STAT_QUALIFIER.sub("", n, count=1)}
    for c in candidates:
        if c in _STAT_NAMES or any(p.search(c) for p in _STAT_PATTERNS):
            return True
    return False


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
    """Add every institution `name` names — one row may join several with
    `;` or `|` — and nothing that is a statistic."""
    for one in split_locked(name if isinstance(name, list) else
                            (None if name is None else str(name))):
        if is_statistic_name(one):
            continue
        k = peer_key(one)
        if k and k not in out:
            out[k] = one


def _locked_set(conn, run_id) -> dict:
    """The workbook's locked_peer_set (run_manifest.payload.workbook_metadata,
    or a manifest that states one), statistics dropped. {} when none."""
    out: dict = {}
    try:
        cur = conn.cursor()
        cur.execute("""SELECT payload -> 'workbook_metadata' -> 'locked_peer_set',
                              payload -> 'manifest' -> 'locked_peer_set'
                         FROM run_manifest WHERE run_id = %s""", (run_id,))
        row = cur.fetchone()
    except Exception:                                          # noqa: BLE001
        return out
    for raw in (row or ()):
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                pass
        for name in split_locked(raw):
            _add(out, name)
    return out


def run_peer_set(conn, run_id, payload, page: str | None = None) -> dict:
    """{peer_key: display name}, first-seen order. Empty when the run
    demonstrably holds no named peer.

    The workbook's locked set, where it states one, IS the set. Otherwise the
    union of peer_scores names, this payload's peer_deployments rows and the
    live submissions of the OTHER peer pages — never `page`'s own, which is
    what the submission under validation replaces."""
    if conn is not None:
        locked = _locked_set(conn, run_id)
        if locked:
            return locked
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
    for r in _rows(payload):
        _add(out, r.get("peer"))
    if conn is not None:
        from .validation2 import _live_submission
        for other in _PEER_PAGES:
            if other == page:
                continue
            for r in _rows(_live_submission(conn, run_id, other)):
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
    peers = run_peer_set(conn, run_id, payload, page=page)
    if not peers:
        return []
    return (named_peer_findings(page, payload, peers)
            + o1_cohort_findings(page, payload, peers))
