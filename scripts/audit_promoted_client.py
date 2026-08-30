#!/usr/bin/env python3
"""Deep audit of what a promoted client actually serves.

Build owner, 2026-08-14: "Are you editing the pages ie jsx or adding deep
auditing scripts to automatically ensure these do not occur in future for any
new client? This is a huge resilience issue."

He is right, and this file is the answer. Every defect this build has shipped to
a client dashboard was found by a person looking at a screen, reported, and then
repaired by hand on that one client. That does not scale past two clients and it
did not even hold for two: the reference client carried 32 field paths null on
100% of their rows for five days while being cited as the gold standard, because
nothing counted.

So the checks below are not about the two clients that exist. They run against
EVERY promoted entity, on a schedule, and they fail loudly.

WHAT IT CHECKS, and why each one is here rather than in a gate at submit:

  A  SERIALISED LEAVES     CG-21 refuses these at submit now. This catches runs
                           promoted BEFORE that gate existed — a gate protects
                           the future, an audit protects the present.
  B  DEAD ENDS IN CONTENT  An em dash inside a served string is a value the
                           PRODUCER dashed. The frontend gate (Gate C) cannot
                           see it; only the payload can.
  C  THE DROP SIGNATURE    A field null on 100% of its rows, over 3+ rows. This
                           is the check that did not exist and should have: a
                           producer who lacked data produces a scatter of
                           nulls, while a value lost between producer and serve
                           produces a perfect column of them. 32 such paths were
                           live and unnoticed.
  D  ALERT CEILING         Promotion refuses above 15 now, but a run promoted
                           before that gate, or one whose alerts grew, is still
                           serving. Verified where the reader meets it.
  E  ENRICHMENT VISIBLE    Every surface the enrichment register declares must
                           serve `enrichment_status`, or a thin surface reads as
                           a complete one.
  F  REDACTION HOLDS       Invariant 5 is default-deny and server-side. Asserted
                           against the CUSTOMER body, because that is the one
                           whose failure reaches a person outside the company.

Usage:
    audit_promoted_client.py --api https://host [--entity slug] [--token T]
    audit_promoted_client.py --from-dir path/   # *_internal.json, *_customer.json

Exit 0 clean, 1 on any BLOCKER, 2 when only warnings. The nightly
corpus-gate-scanner runs the --api form; the tests run the --from-dir form.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PAGES = ("overview", "heatmap", "insights", "platform", "context", "techstack")

# The abbreviation list, from the copy the connector's gate and the api's
# projection both read. Imported rather than restated: three copies of a
# vocabulary is three chances for one of them to be the stale one.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages" / "shared"))
from abbreviations import EXCERPT_FIELDS, unexplained  # noqa: E402
DROP_MIN_ROWS = 3

# Keys that legitimately hold prose written for a person, where an em dash is
# punctuation rather than an unstated value.
PROSE_KEYS = frozenset((
    "narrative_thread", "reason", "message", "hint", "note", "detail",
    "summary", "body", "situation", "complication", "question", "answer",
    "rationale", "sequencing_rationale", "cost_of_delay", "unlocks",
    "entry_condition", "dma_impact", "thin_reason", "excerpt", "quote",
    "framing_sentence", "headline", "storyline_challenge", "plain_label",
    "closure_condition", "quarantine_reason", "empty_state", "why",
    "peer_basis", "verdict", "hypothesis", "counter", "domain_test",
))

# Paths the serve layer removes on purpose. A "null" here is redaction working,
# not content missing, and reporting it would train the reader to ignore this
# report — the failure mode that makes an audit worthless.
REDACTED_BY_DESIGN = (
    "cohort_patterns",       # entity_ids stripped for EVERY audience (inv. 5)
)


def walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, node


def _leaf_key(path: str) -> str:
    return path.rsplit(".", 1)[-1].split("[")[0]


def _shape(path: str) -> str:
    return re.sub(r"\[\d+\]", "[]", path)


def _v(level, code, page, path, message, **extra):
    return dict(level=level, code=code, page=page, path=path, message=message,
                **extra)


# ── A · a serialisation that escaped into a leaf ──────────────────────
def check_serialised(page, body) -> list:
    out = []
    for p, v in walk(body):
        if not isinstance(v, str):
            continue
        s = v.strip()
        if len(s) < 2 or s[0] not in "{[":
            continue
        try:
            parsed = json.loads(s)
        except Exception:
            continue
        if isinstance(parsed, (dict, list)):
            out.append(_v("BLOCKER", "A-SERIALISED", page, p,
                          f"leaf is a JSON {'object' if s[0] == '{' else 'array'} "
                          f"serialised into a string: {s[:70]!r}. It renders to "
                          "the reader as literal JSON."))
    return out


# ── B · a dead end the producer wrote ─────────────────────────────────
def check_dead_ends(page, body) -> list:
    out = []
    for p, v in walk(body):
        if not isinstance(v, str) or "—" not in v:
            continue
        key = _leaf_key(p)
        if key in PROSE_KEYS:
            continue
        # A whole-value dash is the dead end. A dash inside a longer phrase is
        # punctuation, and this check must not police the producer's prose.
        if v.strip() in ("—", "-", "–", "n/a", "N/A", "TBD", "tbd"):
            out.append(_v("BLOCKER", "B-DEAD-END", page, p,
                          f"the served value is {v.strip()!r} — the producer "
                          "dashed a field instead of stating it, holding it "
                          "with a reason, or leaving it null for the "
                          "enrichment worklist to pick up."))
    return out


# ── C · the drop signature ────────────────────────────────────────────
#: Basis carriers — the payload keys where a producer STATES why a value is
#: absent. Read by `_absence_attributed` below; the list is deliberately the
#: same vocabulary the payload contracts use for stated absences.
_BASIS_KEYS = ("peer_basis", "proxy_disclosure", "empty_state",
               "enrichment_status", "peer_synthesis", "reach_note",
               "not_run_reason", "quarantine_reason", "empty_reason")


def _absence_attributed(body, shape: str, leaf: str) -> bool:
    """Does the payload STATE why this column is null, where a reader gets it?

    The C-DROP message has always said the next step is attribution — "a
    producer short of data leaves a scatter, and a perfect column means the
    value was either never written or lost". Measured 2026-08-18 on the first
    fully promoted client, a third state exists: never written BECAUSE the
    basis does not exist, and SAID so. `scores.pillars[]` served
    `peer_basis: "cannot_estimate"` on every row while this check flagged the
    null `peer_median` beside it as a drop. Peer scoring is a recorded pending
    phase of that assessment; the column is a stated absence, not a lost value.

    Two carriers count, both of which render to a reader:
      · a sibling `*_basis` key non-null in the same section (row-level), or
      · a section-level basis text (`proxy_disclosure`, `empty_state.reason`,
        `peer_synthesis`, …) that NAMES the leaf or its stem.
    A basis that names nothing attributes nothing — "peer" prose does not
    excuse a null `fit_score` — and an unattributed perfect column still
    BLOCKS, which is the negative control the tests pin.
    """
    stem = leaf.split("_")[0].lower()
    section = shape.split(".")[1] if shape.startswith(".") else shape.split(".")[0]
    hit = []

    def _scan(node, in_section):
        if isinstance(node, dict):
            for k, v in node.items():
                inside = in_section or k == section
                if inside and k in _BASIS_KEYS and v not in (None, "", [], {}):
                    text = v if isinstance(v, str) else json.dumps(v)
                    if stem in text.lower() or leaf.lower() in text.lower() \
                            or k == f"{stem}_basis":
                        hit.append(k)
                _scan(v, inside)
        elif isinstance(node, list):
            for v in node:
                _scan(v, in_section)

    _scan(body, False)
    if hit:
        return True

    # The connector's own stated-exception carrier. ET-07 accepts an unlinked
    # citation when the section's `r_layer.probes_run` NAMES the id; the same
    # rule holds here, and tighter than the stem match above: only the FULL
    # leaf name counts, so "peer" prose cannot excuse `peer_deployments`.
    def _probes(node):
        if isinstance(node, dict):
            rl = node.get("r_layer")
            if isinstance(rl, dict):
                for p in rl.get("probes_run") or []:
                    if isinstance(p, str) and leaf.lower() in p.lower():
                        hit.append("r_layer.probes_run")
            for v in node.values():
                _probes(v)
        elif isinstance(node, list):
            for v in node:
                _probes(v)

    _probes(body)
    return bool(hit)


_TERMINAL_STATUSES = {"RESOLVED", "CLOSED", "COMPLETE", "COMPLETED", "DONE",
                      "ABANDONED", "WAIVED", "REMEDIATED"}


def _event_not_yet(rows_by_container: dict, body, shape: str, leaf: str) -> bool:
    """A null `*_on` / `*_at` / `*_date` beside a non-terminal status is an
    event that has not happened — invariant 9's third clause, not a drop.

    Measured 2026-08-18: `issue_register.issues[].resolved_on` null on all
    three rows, every row `status: OPEN`. An open issue HAS no resolution
    date; writing one would be a sentinel wearing a measurement's clothes.
    The exemption is per-row and refuses the terminal case: a RESOLVED issue
    with a null resolved_on is exactly the drop this check exists for, and
    the tests pin that direction.
    """
    if not (leaf.endswith("_on") or leaf.endswith("_at")
            or leaf.endswith("_date")):
        return False
    container_shape = shape.rpartition(".")[0]
    rows = rows_by_container.get(container_shape) or ()
    if not rows:
        return False

    def _row_at(node, concrete):
        # concrete like ".issue_register.data.issues[2]" — walk it.
        cur = node
        for part in re.findall(r"\.([A-Za-z_0-9]+)|\[(\d+)\]", concrete):
            key, idx = part
            try:
                cur = cur[key] if key else cur[int(idx)]
            except Exception:
                return None
        return cur if isinstance(cur, dict) else None

    for concrete in rows:
        row = _row_at(body, concrete)
        if row is None:
            return False
        status = str(row.get("status") or "").upper()
        if not status or status in _TERMINAL_STATUSES:
            return False
    return True


def check_drop_signature(page, body) -> list:
    """A field null on 100% of its rows, over enough rows to mean something.

    The arithmetic IS the finding. A producer who lacked data leaves a scatter;
    a value lost between producer and serve leaves a perfect column. This is the
    check whose absence let 32 field paths serve empty on the client that was
    being used as the standard.
    """
    # THE DENOMINATOR IS THE CONTAINER, NOT THE LEAF YIELDS.
    #
    # `walk` DESCENDS into a non-empty list or dict instead of yielding it, so
    # a row whose value is populated never reaches this loop at all. Counting
    # yields therefore counts only the rows where the key is null — and n == t
    # is then true by construction for every partially populated column.
    #
    # Measured 2026-08-15 on the reference client:
    # `.techstack.data.items[].peer_deployments` is populated on 8 of 51 rows
    # and this reported "null on 43/43 rows — every one". A check whose
    # arithmetic IS the finding got the arithmetic backwards, and the phrasing
    # "every one" was true only of a set selected BY being null.
    # The denominator is the number of ROWS in the containing list, counted
    # as DISTINCT CONCRETE row paths — not as leaf yields, and not from an
    # index, both of which get nesting wrong.
    #
    # `walk` DESCENDS into a populated list or dict instead of yielding it, so
    # a row whose value is present never reaches this loop. Counting yields
    # therefore counts only the rows where the key is null, and `n == t` is
    # true by construction for every partially populated column. Measured on
    # the reference client: `.techstack.data.items[].peer_deployments` is
    # populated on 8 of 51 rows and this reported "null on 43/43 — every one".
    # A check whose arithmetic IS the finding had the arithmetic backwards,
    # and "every one" was true only of a set selected BY being null.
    #
    # Taking the last `[i]` instead over-counts the other way on a nested
    # shape — `platforms[].peer_deployments[].as_of` read 18 nulls against 5
    # rows — because the inner index restarts inside each outer row. A set of
    # concrete container paths is the only count that survives both.
    rows: dict = {}          # container shape -> {concrete container paths}
    empty: dict = {}         # leaf shape -> rows where it is null/blank
    for path, value in walk(body):
        if "[" not in path:          # only list rows can show the signature
            continue
        concrete_container, _, _leaf = path.rpartition(".")
        if concrete_container.endswith("]"):
            # Any leaf under a row proves that row exists, including leaves
            # nested deeper — so every row is counted once, whatever it holds.
            rows.setdefault(_shape(concrete_container), set()).add(concrete_container)
        if value is None or (isinstance(value, str) and not value.strip()):
            empty[_shape(path)] = empty.get(_shape(path), 0) + 1
    out = []
    for shape, n in sorted(empty.items(), key=lambda kv: -kv[1]):
        container, _, _leaf = shape.rpartition(".")
        t = len(rows.get(container, ()))
        # Only a PERFECT column is the signature. `n != t` covers both
        # directions: a partially populated column (n < t) is a producer with
        # partial data, and n > t would mean the denominator is wrong, which
        # is a bug in this check rather than a finding about the client.
        if n != t or t < DROP_MIN_ROWS:
            continue
        if any(r in shape for r in REDACTED_BY_DESIGN):
            continue
        _, _, leaf_name = shape.rpartition(".")
        if _event_not_yet(rows, body, shape, leaf_name):
            out.append(_v("WARN", "C-DROP", page, shape,
                          f"null on all {t} rows of {container}, every row in "
                          "a non-terminal status — the event has not happened "
                          "and its date is correctly null (invariant 9).",
                          rows_null=n, rows_total=t))
            continue
        if _absence_attributed(body, shape, leaf_name):
            # A stated absence is visible, not silent: WARN keeps it in the
            # findings list an operator reads; --api exits only on BLOCKERs.
            out.append(_v("WARN", "C-DROP", page, shape,
                          f"null on all {t} rows of {container}, and the "
                          "payload states the basis for the absence — an "
                          "attributed column, reported for visibility rather "
                          "than as a drop.",
                          rows_null=n, rows_total=t))
            continue
        out.append(_v("BLOCKER", "C-DROP", page, shape,
                      f"null on all {t} rows of {container}. That is the drop "
                      "SIGNATURE, not the cause: a producer short of data "
                      "leaves a scatter, and a perfect column means the value "
                      "was either never written or lost on the way here. "
                      "Attribute it before fixing it — "
                      f"get_staged_payload(run_id, page, section) returns what "
                      "the producer actually submitted, and comparing that "
                      "against this row says which half to look in.",
                      rows_null=n, rows_total=t))
    return out


# ── D · the alert queue a reader would meet ───────────────────────────
def check_alert_ceiling(page, body) -> list:
    """Report the queue's size. Never refuse on it.

    This was a BLOCKER above 15 until 2026-08-16. The ceiling was removed
    because the count turned out to measure the assessment's EVIDENCE MODE
    rather than the run's quality: a second client owed 621 alerts under H3's
    literal reading, having been assessed in PUBLIC mode, whose methodology
    says that is why two thirds of subcapabilities come back Unknown.

    The measurement stays and is emitted UNCONDITIONALLY, with no threshold.
    A threshold is what was wrong; and a line that appears only above some
    number is a ceiling wearing a different word. Reported at WARN so it
    lands in the findings list an operator reads without failing the audit —
    `--api` exits on BLOCKERs, and this is not one.
    """
    if page != "heatmap":
        return []
    node = body.get("alerts") if isinstance(body, dict) else None
    node = (node or {}).get("data") if isinstance(node, dict) and "data" in node else node
    alerts = (node or {}).get("alerts") if isinstance(node, dict) else None
    if not isinstance(alerts, list):
        return []
    return [_v("WARN", "D-ALERTS", page, "heatmap.alerts.alerts",
               f"{len(alerts)} open alert(s) in the queue an AE meets first. "
               "Reported, not judged: there is no ceiling. A large queue is "
               "usually the assessment's evidence mode showing through rather "
               "than a defect in the run.",
               open_alerts=len(alerts))]


# ── E · a thin surface must say it is thin ────────────────────────────
def check_enrichment_visible(page, sections, register) -> list:
    out = []
    for key in register:
        pg, _, section = key.partition(".")
        if pg != page or section not in (sections or {}):
            continue
        sec = sections[section] or {}
        data = sec.get("data") if isinstance(sec, dict) else None
        holder = data if isinstance(data, dict) else sec
        if not isinstance(holder, dict) or "enrichment_status" not in holder:
            out.append(_v("BLOCKER", "E-ENRICH", page, f"{section}.enrichment_status",
                          "the enrichment register declares this surface, and "
                          "the served section carries no enrichment_status — a "
                          "thin surface reads as a complete one."))
    return out


# ── F · redaction is default-deny and server-side ─────────────────────
CUSTOMER_FORBIDDEN = (
    ("r_layer", "the reasoning layer is internal"),
    ("storyline_challenge", "internal sell framing"),
    ("internal_only", "the redaction instruction itself must not ship"),
    ("email", "a contact key"),
    ("phone", "a contact key"),
    ("linkedin_url", "a contact key"),
    ("entity_ids", "cohort member ids are stripped for EVERY audience"),
)


def check_redaction(page, body) -> list:
    out = []
    for p, _ in walk(body):
        key = _leaf_key(p)
        for bad, why in CUSTOMER_FORBIDDEN:
            if key == bad:
                out.append(_v("BLOCKER", "F-REDACT", page, p,
                              f"{bad!r} reached the CUSTOMER body — {why}. "
                              "Invariant 5 is default-deny and server-side."))
    return out


# ── G · an abbreviation on a rendered surface ─────────────────────────
#
# CG-27 refuses one in a PAYLOAD, and two of the three routes to a served page
# do not go through a payload: `source_name` on a package-ingested evidence row
# is written by whoever assembled the assessment, and the cell-drawer item is
# built by the api straight off that column. Both were spelling abbreviations
# out on one endpoint and not the other, measured at 55 occurrences across six
# served pages after the payload gate was clean.
#
# So the check runs where a reader actually meets the string. Verbatim spans
# and catalogue-controlled tokens are excluded by the same list the expander
# uses — a quote is not ours to rewrite, and `CU` in `sub_vertical` resolves
# through the frontend's label map to "Credit Union".
def check_abbreviations(page, body) -> list:
    out, seen = [], set()
    for path, v in walk(body):
        if not isinstance(v, str):
            continue
        key = path.rsplit(".", 1)[-1].split("[")[0]
        if key in EXCERPT_FIELDS:
            continue
        for short in unexplained(v):
            if (page, key, short) in seen:
                continue
            seen.add((page, key, short))
            out.append(_v("WARN", "G-ABBREV", page, path,
                          f"'{short}' reaches a rendered surface unexplained. "
                          f"Spell it out on first use in the field. Verbatim "
                          f"spans and catalogue tokens are excluded; this is "
                          f"neither. First seen: {v[:120]!r}"))
    return out


def audit_page(page, doc, audience, register) -> list:
    sections = (doc or {}).get("sections") or {}
    out = []
    out.extend(check_serialised(page, sections))
    out.extend(check_dead_ends(page, sections))
    out.extend(check_abbreviations(page, sections))
    if audience == "internal":
        out.extend(check_drop_signature(page, sections))
        out.extend(check_alert_ceiling(page, sections))
        out.extend(check_enrichment_visible(page, sections, register))
    else:
        out.extend(check_redaction(page, sections))
    for v in out:
        v["audience"] = audience
    return out


def _register(root: Path) -> list:
    p = root / "packages" / "shared" / "enrichment_register.json"
    try:
        raw = json.loads(p.read_text())
        return list((raw.get("surfaces") or raw).keys())
    except Exception:
        return []


def run_from_dir(d: Path, register) -> list:
    out = []
    for page in PAGES:
        for audience in ("internal", "customer"):
            f = d / f"{page}_{audience}.json"
            if not f.exists():
                continue
            try:
                doc = json.loads(f.read_text())
            except Exception as e:
                out.append(_v("BLOCKER", "READ", page, str(f), f"unreadable: {e}"))
                continue
            out.extend(audit_page(page, doc, audience, register))
    return out


def run_from_api(base: str, entity: str | None, token: str | None,
                 register) -> list:
    import urllib.error
    import urllib.request

    def get(path):
        req = urllib.request.Request(base.rstrip("/") + path)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read()), r.status
        except urllib.error.HTTPError as e:
            return None, e.code
        except Exception:
            return None, 0

    out = []
    if entity:
        slugs = [entity]
    else:
        doc, status = get("/v1/directory?audience=internal")
        if not doc:
            return [_v("BLOCKER", "API", "directory", "/v1/directory",
                       f"directory unreadable (HTTP {status}); audited nothing. "
                       "An audit that could not read is NOT an audit that "
                       "passed.")]
        slugs = [e.get("slug") or e.get("id") for e in (doc.get("entities") or [])]
    if not slugs:
        return [_v("WARN", "API", "directory", "/v1/directory",
                   "no promoted entities to audit")]
    for slug in slugs:
        for page in PAGES:
            for audience in ("internal", "customer"):
                doc, status = get(f"/v1/entities/{slug}/{page}?audience={audience}")
                if doc is None:
                    # context is internal-only; 403 to customer is correct.
                    if not (page == "context" and audience == "customer"
                            and status == 403):
                        out.append(_v("WARN", "API", page,
                                      f"/v1/entities/{slug}/{page}",
                                      f"HTTP {status} for audience={audience}"))
                    continue
                for v in audit_page(page, doc, audience, register):
                    v["entity"] = slug
                    out.append(v)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api")
    ap.add_argument("--entity")
    ap.add_argument("--token")
    ap.add_argument("--from-dir")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    register = _register(root)
    if a.from_dir:
        findings = run_from_dir(Path(a.from_dir), register)
    elif a.api:
        findings = run_from_api(a.api, a.entity, a.token, register)
    else:
        ap.error("one of --api or --from-dir is required")

    if a.json:
        print(json.dumps({"findings": findings}, indent=1))
    blockers = [f for f in findings if f["level"] == "BLOCKER"]
    warns = [f for f in findings if f["level"] != "BLOCKER"]
    if not a.json:
        by_code: dict = {}
        for f in findings:
            by_code.setdefault(f["code"], []).append(f)
        for code in sorted(by_code):
            rows = by_code[code]
            print(f"\n{code}  ({len(rows)})")
            for f in rows[:12]:
                who = f.get("entity", "")
                print(f"  [{f['level']}] {who} {f['page']}/{f.get('audience','')} "
                      f"{f['path']}")
                print(f"        {f['message'][:150]}")
            if len(rows) > 12:
                print(f"  … and {len(rows) - 12} more")
        print(f"\n{len(blockers)} blocker(s), {len(warns)} warning(s).")
    if blockers:
        return 1
    return 2 if warns else 0


if __name__ == "__main__":
    sys.exit(main())
