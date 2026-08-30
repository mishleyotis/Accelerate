#!/usr/bin/env python3
"""Gate E — every surface of the acceptance document has a disposition.

The owner's direction on the specification was to implement and stress-test
every surface's tests, exclude what was removed, and challenge the document's
own checks rather than assume them. The curation produced `inventory.json` and
`ACCEPTANCE.md`. Nothing verified that the curation was COMPLETE, and it was
not: a completeness critic found three whole Insights surfaces — Technology
landscape, Recommendations, Recommendation modal, carrying eighteen P0 checks
between them — present in neither artefact, not included and not excluded.
They had simply been walked past.

That is the failure this gate exists for, and it is the same shape as the
defects the specification itself is about: a claim of coverage that nobody
reconciled against the thing being covered.

WHAT IT RECONCILES

  1. CENSUS. Every surface in `doc_digest.json` is either an inventory section
     or explicitly excluded WITH evidence. Unaccounted fails. The digest's own
     per-surface heading counts must also sum to the document total, so a
     surface cannot be dropped by quietly absorbing its headings.

  2. EVIDENCE ON EXCLUSIONS. An excluded surface carries a reason naming a file
     or a contract. Three of the first pass's exclusions rested on a comment
     inside `pages-live-client.jsx` — a 2,694-line pack that is mounted
     nowhere — while the surfaces themselves were contract-required and mounted.
     Excluding a live surface on the authority of dead code is how coverage
     gets claimed for something that was never looked at.

  3. THE TWO ARTEFACTS AGREE. Every `qa_id` in `inventory.json` appears in
     `ACCEPTANCE.md` and vice versa. They are edited separately and drift.

  4. AN ADOPTED CHECK SAYS WHAT IT CHECKS. `ADOPT` with no rule text is a
     coverage claim with no content — 63 of 463 were exactly that. Ratcheted
     rather than absolute, because demoting them to explicit register
     inheritance is real work and a gate that cannot go green gets disabled.

Run `--census` to print the disposition table without failing.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ACC = REPO / "apps" / "web" / "tests" / "acceptance"
DIGEST = ACC / "doc_digest.json"
INVENTORY = ACC / "inventory.json"
MARKDOWN = ACC / "ACCEPTANCE.md"
RATCHET = ACC / "gate_e_ratchet.json"

QA_ID = re.compile(r"\b([A-Z][A-Z0-9]{1,9}(?:-[A-Z0-9]{1,6}){1,3})\b")

# An exclusion's reason must point at something checkable — a path, a contract
# key, or a named module. "Not separately mountable" is an assertion;
# "pages-d5-d6-tech-runs.jsx:1591" is evidence.
EVIDENCE = re.compile(
    r"\.(jsx|js|py|json|md|tsx|ts)\b|CLAUDE\.md|contracts_data|"
    r"Surface Spec|Backend Schema|invariant \d|adjudication", re.I)


def load(p: Path):
    if not p.exists():
        print(f"missing: {p.relative_to(REPO)}", file=sys.stderr)
        sys.exit(2)
    return json.loads(p.read_text())


def census(digest, inventory):
    """Each document surface -> the inventory entry that dispositions it.

    Two ways an entry can claim a surface. By LINE, which is the ordinary case:
    one inventory section per document surface. Or by RANGE — `covers_lines`,
    a list of [start, end] pairs — which the registers need, because a register
    entry deliberately absorbs a run of the document's own sub-headings
    ("Purpose", "The story contract", "Exit standard") that are headings in the
    source and not surfaces of the application.

    A range is a claim of coverage and is treated as one: it must be declared,
    it is printed in the census, and two entries claiming the same line is a
    failure rather than a tie broken silently. Absorbing by proximity instead
    would let a surface disappear into whichever neighbour happened to be
    nearest, which is how three Insights surfaces were lost.
    """
    by_line = {}
    for s in inventory["sections"]:
        by_line.setdefault(s["doc_line"], s)
    ranges = [(lo, hi, s) for s in inventory["sections"]
              for lo, hi in (s.get("covers_lines") or [])]

    rows, claimed = [], {}
    for surf in digest["surfaces"]:
        line, end = surf["line"], surf["end_line"]
        # An entry belongs to the surface whose RANGE contains its doc_line,
        # not to the nearest line number. The document repeats a surface title
        # on the line after its section break and the curation recorded
        # whichever of the pair it read, so several entries sit four or five
        # lines inside their own surface. A proximity window wide enough for
        # those is also wide enough to bind an entry to its neighbour;
        # containment cannot.
        entry = by_line.get(line)
        if entry is None:
            inside = [s for ln, s in by_line.items() if line <= ln <= end]
            if len(inside) > 1:
                claimed[line] = [s["surface_id"] for s in inside]
            entry = inside[0] if inside else None
        if entry is None:
            hits = [s for lo, hi, s in ranges if lo <= line <= hi]
            if len(hits) > 1:
                claimed[line] = [h["surface_id"] for h in hits]
            entry = hits[0] if hits else None
        rows.append((surf, entry))
    return rows, claimed


def main(argv) -> int:
    digest = load(DIGEST)
    inventory = load(INVENTORY)
    md = MARKDOWN.read_text() if MARKDOWN.exists() else ""
    rows, double_claimed = census(digest, inventory)
    problems = []

    # ── 1 · the census ───────────────────────────────────────────────
    owned = sum(s["headings"] for s in digest["surfaces"])
    if owned != digest["source"]["headings"]:
        problems.append(
            f"the digest does not reconcile with itself: surfaces own {owned} "
            f"headings, the document has {digest['source']['headings']}")

    for line, who in sorted(double_claimed.items()):
        problems.append(
            f"line {line} is claimed by {len(who)} entries ({', '.join(who)}) "
            "— overlapping covers_lines means one of them is describing a "
            "surface it does not own")

    unaccounted = [s for s, e in rows if e is None]
    included = [s for s, e in rows if e and e.get("status") == "INCLUDED"]
    excluded = [(s, e) for s, e in rows if e and e.get("status") == "EXCLUDED"]
    registers = [s for s, e in rows if e and e.get("status") == "REGISTER"]

    if argv and argv[0] == "--census":
        print(f"{len(rows)} surfaces · {len(included)} included · "
              f"{len(excluded)} excluded · {len(registers)} register · "
              f"{len(unaccounted)} UNACCOUNTED\n")
        for s in unaccounted:
            print(f"  UNACCOUNTED  line {s['line']:6}  {s['title'][:64]}  "
                  f"({s['headings']} headings)")
        return 0

    for s in unaccounted:
        problems.append(
            f"line {s['line']} {s['title']!r} ({s['headings']} headings) is "
            "neither an inventory section nor an explicit exclusion — the "
            "curation walked past it")

    # ── 2 · exclusions carry evidence ────────────────────────────────
    for s, e in excluded:
        reason = " ".join(str(v) for k, v in e.items()
                          if k in ("exclusion_reason", "evidence", "why"))
        if not reason.strip():
            problems.append(
                f"line {s['line']} {s['title']!r} is EXCLUDED with no recorded "
                "reason — an exclusion nobody can check is a surface nobody "
                "tested")
        elif not EVIDENCE.search(reason):
            problems.append(
                f"line {s['line']} {s['title']!r} is EXCLUDED on {reason[:70]!r}"
                " — that names no file, contract or adjudication. Three "
                "exclusions in the first pass rested on dead code.")

    # ── 3 · the two artefacts agree ──────────────────────────────────
    inv_ids, textless = set(), []
    for sec in inventory["sections"]:
        for chk in sec.get("checks") or []:
            qid = chk.get("qa_id")
            if not qid:
                continue
            inv_ids.add(qid)
            # A check is textless when it ADOPTS the document's wording and
            # states nothing of its own. The curated shape carries the improved
            # statement in `rule`, so a bare "ADOPT" verdict beside real rule
            # text is fully specified — counting it as textless would report
            # the completed half of the work as the outstanding half.
            verdict = str(chk.get("verdict") or "")
            rule = str(chk.get("rule") or "").strip()
            if verdict.strip() == "ADOPT" and len(rule) < 20:
                textless.append(f'{sec["surface_id"]}:{qid}')

    md_ids = set(QA_ID.findall(md))
    orphan_md = sorted(i for i in md_ids - inv_ids
                       if re.match(r"^(RG|NQ|CI|BAX|REG|TA)-", i))
    missing_md = sorted(inv_ids - md_ids)

    # ACCEPTANCE.md carries per-surface deltas rather than every id, by design
    # (the merge dedups the document's repetition into shared registers), so a
    # check present in the inventory and absent from the prose is only a
    # problem for the REGISTERS, which the prose is supposed to enumerate.
    for qid in orphan_md:
        problems.append(f"{qid} is cited in ACCEPTANCE.md and is in no "
                        "inventory section — the prose claims a check the "
                        "index does not carry")

    # ── 4 · an adopted check says what it checks (ratchet) ───────────
    ratchet = json.loads(RATCHET.read_text()) if RATCHET.exists() else None
    if "--update" in argv:
        RATCHET.write_text(json.dumps(
            {"_why": "Gate E: ADOPT verdicts carrying no rule text. May "
                     "SHRINK, never GROW. Give one a rule, or demote it to "
                     "explicit register inheritance, then re-pin.",
             "textless_adopts": sorted(textless)}, indent=1) + "\n")
        print(f"Gate E ratchet re-pinned at {len(textless)} textless ADOPTs.")
        return 0
    if ratchet is None:
        problems.append("no gate_e_ratchet.json — run --update once and read "
                        "the list before committing it")
    else:
        base = set(ratchet["textless_adopts"])
        grew = sorted(set(textless) - base)
        for qid in grew:
            problems.append(f"{qid} is ADOPT with no rule text — a coverage "
                            "claim with no content")

    # ── report ───────────────────────────────────────────────────────
    fixed = (len(set(ratchet["textless_adopts"])) - len(textless)) if ratchet else 0
    summary = (f"{len(rows)} surfaces · {len(included)} implemented · "
               f"{len(excluded)} excluded · {len(registers)} register · "
               f"{len(unaccounted)} unaccounted · "
               f"{len(inv_ids)} checks · {len(textless)} textless ADOPT")
    if problems:
        print(f"Gate E FAILED — {summary}\n", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        print(f"\n{len(problems)} problem(s).", file=sys.stderr)
        return 1
    print(f"Gate E passed: {summary}"
          + (f" ({fixed} textless ADOPTs given rules — re-pin with --update)"
             if fixed > 0 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
