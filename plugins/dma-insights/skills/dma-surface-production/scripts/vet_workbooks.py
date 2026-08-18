#!/usr/bin/env python3
"""Workbook hygiene, before the parser sees anything.

Every check here corresponds to a defect that reached a rendered page. The script
REPORTS; you decide whether to refuse. Read `02-inputs/4-vetting.md` for what each
finding does downstream — the consequence is the reason the check exists.

    python scripts/vet_workbooks.py <package-dir> [--subvertical CU]
    python scripts/vet_workbooks.py <scoring.xlsx> [research.xlsx]

Give it the entity's sub-vertical code and it names the variant cells the workbook
scored for somebody else — they render nowhere, and 59 of them reached a credit
union's promoted heatmap.

Exit 0 clean · 1 findings that need a decision · 2 could not read the input.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

try:
    from openpyxl import load_workbook
except ImportError:                                            # pragma: no cover
    print("openpyxl is required: pip install openpyxl", file=sys.stderr)
    raise SystemExit(2)

# Headers that are STATISTICS, not peer institutions. A parser that treats an
# unrecognised score column as a peer invented 54 rows of institutions literally
# named "Median", and the median cross-check then never ran.
STAT_HEADERS = {"median", "p25", "p75", "mean", "average", "avg", "stdev",
                "std", "min", "max", "count", "n", "quartile"}

CELL_RE = re.compile(r"^P[1-4]C\d+(\.\d+)*(\.[A-Z]{2,3}\d+)?$", re.I)
EID_RE = re.compile(r"^E[-_][A-Z0-9]+[-_]?\d*(:F\d+)?$", re.I)

# The suffix codes that name exactly ONE sub-vertical. A family or product code
# (BK depository, WM wealth, PEN retirement) serves every entity and is not
# evidence that a cell belongs to somebody else.
SUBVERTICAL_CODES = {"RB", "CU", "CL", "CIB", "FC", "AM", "RIA", "IC", "IB"}
VARIANT_RE = re.compile(r"^([A-Z]{2,3})(\d+)$")

findings: list[tuple[str, str]] = []
entity_sv: str | None = None


def note(level: str, msg: str) -> None:
    findings.append((level, msg))


def sheets_of(path: Path):
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        return {ws.title: [list(r) for r in ws.iter_rows(max_row=400, values_only=True)]
                for ws in wb.worksheets}
    finally:
        wb.close()


def header_row(rows):
    """The first row with three or more non-empty string cells."""
    for i, r in enumerate(rows[:20]):
        strs = [c for c in r if isinstance(c, str) and c.strip()]
        if len(strs) >= 3:
            return i, [str(c).strip() if c is not None else "" for c in r]
    return None, []


def vet_scoring(path: Path) -> None:
    print(f"\n=== scoring workbook · {path.name}")
    tabs = sheets_of(path)
    print(f"tabs ({len(tabs)}): {', '.join(list(tabs)[:12])}"
          + (" …" if len(tabs) > 12 else ""))
    if len(tabs) <= 3:
        note("REFUSE", f"only {len(tabs)} tab(s) — this may be a generation the "
                       f"parser does not know. Name the tabs in your refusal.")

    cells: list[str] = []
    scores: list[float] = []
    e_ids: list[str] = []
    missing_source_cell = 0
    saw_source_cell_col = False

    for name, rows in tabs.items():
        hi, hdr = header_row(rows)
        if hi is None:
            continue
        low = [h.lower() for h in hdr]

        # peer columns that are really statistics
        for h in hdr:
            hl = h.strip().lower()
            if hl in STAT_HEADERS:
                note("WARN", f"{name}: column {h!r} is a STATISTIC. Confirm the "
                             f"parser does not read it as a peer institution.")
            if "peer" in hl and any(sh in hl for sh in ("median", "p25", "p75")):
                pass  # correctly qualified

        if "source_cell" in low:
            saw_source_cell_col = True
        idx_src = low.index("source_cell") if "source_cell" in low else None

        for r in rows[hi + 1:]:
            if r is None or all(c is None or str(c).strip() == "" for c in r):
                continue
            for c in r:
                if isinstance(c, str):
                    t = c.strip()
                    if CELL_RE.match(t):
                        cells.append(t.upper())
                    elif EID_RE.match(t):
                        e_ids.append(t.upper())
                elif isinstance(c, (int, float)):
                    if 0 < float(c) <= 5.0 or float(c) == 0:
                        pass
            if idx_src is not None and (idx_src >= len(r) or r[idx_src] in (None, "")):
                missing_source_cell += 1

        # score range, per column named like a score
        for j, h in enumerate(low):
            if "score" not in h or "peer" in h:
                continue
            for r in rows[hi + 1:]:
                if r is None or j >= len(r):
                    continue
                v = r[j]
                if isinstance(v, (int, float)):
                    scores.append(float(v))

    bad = [v for v in scores if v != 0 and not (1.0 <= v <= 5.0)]
    if bad:
        note("REFUSE", f"{len(bad)} score(s) outside 1.0–5.0 "
                       f"(e.g. {sorted(set(bad))[:5]}). A 0 bands as Activating "
                       f"and looks assessed.")
    zeros = [v for v in scores if v == 0]
    if zeros:
        note("WARN", f"{len(zeros)} score(s) are exactly 0 — confirm these are "
                     f"blanks, not measurements.")

    # duplicate evidence ids lose rows silently under ON CONFLICT DO NOTHING
    dupes = {k: n for k, n in Counter(e_ids).items() if n > 1}
    if dupes:
        worst = sorted(dupes.items(), key=lambda kv: -kv[1])[:6]
        note("REFUSE", f"{len(dupes)} evidence id(s) appear more than once "
                       f"({', '.join(f'{k}×{n}' for k, n in worst)}). Repeated ids "
                       f"for DIFFERENT sources lose rows with no observation.")

    # catalogue version, from the category count
    cats = {c.split(".")[0] for c in cells if CELL_RE.match(c)}
    cats = {c for c in cats if re.fullmatch(r"P[1-4]C\d+", c, re.I)}
    if cats:
        print(f"categories seen: {len(cats)}")
        if len(cats) == 17:
            note("PIN", "17 categories → this is a v5.0-shaped assessment. Pin "
                        "runs.ccg_catalog_version to v5.0, or every cell name "
                        "joins against v7.0 and comes back NULL.")
        elif len(cats) == 16:
            note("PIN", "16 categories → v7.0. Confirm the run is pinned.")
        else:
            note("WARN", f"{len(cats)} categories — matches neither v7.0 (16) nor "
                         f"v5.0 (17). State what you inferred and from what.")
    print(f"cells seen: {len(set(cells))} · evidence ids seen: {len(set(e_ids))}")

    # variant cells the workbook scored for OTHER sub-verticals. They are the
    # catalogue's, not this entity's, and the serve layer drops them — so a payload
    # that cites one cites a cell that renders nowhere.
    variants = Counter()
    for c in set(cells):
        m = VARIANT_RE.match(c.rsplit(".", 1)[-1])
        if m and m.group(1) in SUBVERTICAL_CODES:
            variants[m.group(1)] += 1
    if variants:
        print("variant cells by sub-vertical: "
              + " · ".join(f"{k}×{n}" for k, n in sorted(variants.items())))
        if entity_sv:
            foreign = {k: n for k, n in variants.items() if k != entity_sv}
            if foreign:
                note("WARN", f"{sum(foreign.values())} variant cell(s) belong to another "
                             f"sub-vertical on a {entity_sv} run "
                             f"({', '.join(f'{k}×{n}' for k, n in sorted(foreign.items()))}). "
                             f"They stay in the workbook and out of the payload — cite one "
                             f"and it resolves here and renders nowhere.")
        elif len(variants) > 1:
            note("WARN", f"variant cells span {len(variants)} sub-verticals. Pass "
                         f"--subvertical to name the entity's, or the payload will cite "
                         f"cells the run cannot serve.")
    if saw_source_cell_col and missing_source_cell:
        note("REFUSE", f"{missing_source_cell} row(s) have no source_cell. It "
                       f"cannot be backfilled after the scan.")


def vet_research(path: Path) -> None:
    print(f"\n=== research workbook · {path.name}")
    tabs = sheets_of(path)
    print(f"tabs ({len(tabs)}): {', '.join(list(tabs)[:12])}"
          + (" …" if len(tabs) > 12 else ""))
    excerpts: list[str] = []
    dated = 0
    ers = 0
    rows_seen = 0
    for name, rows in tabs.items():
        hi, hdr = header_row(rows)
        if hi is None:
            continue
        low = [h.lower() for h in hdr]
        col = lambda *keys: next(  # noqa: E731
            (low.index(k) for k in keys if k in low), None)
        i_ex = col("evidence_excerpt", "excerpt", "quote", "passage")
        i_dt = col("date_published", "published_date", "publish_date", "date")
        i_er = col("ers_total", "ers", "ers_score")
        for r in rows[hi + 1:]:
            if r is None or all(c is None or str(c).strip() == "" for c in r):
                continue
            rows_seen += 1
            if i_ex is not None and i_ex < len(r) and isinstance(r[i_ex], str):
                excerpts.append(r[i_ex].strip())
            if i_dt is not None and i_dt < len(r) and r[i_dt] not in (None, ""):
                dated += 1
            if i_er is not None and i_er < len(r) and r[i_er] not in (None, ""):
                ers += 1
    if excerpts:
        lens = sorted(len(e) for e in excerpts)
        med = lens[len(lens) // 2]
        short = sum(1 for n in lens if n < 50)
        empty = sum(1 for e in excerpts if not e)
        print(f"excerpts: {len(excerpts)} · median {med} chars · "
              f"{short} under the 50-char floor · {empty} empty")
        if med < 120:
            note("WARN", f"excerpt median is {med} chars. An excerpt that clears "
                         f"the floor and says nothing passes every gate and helps "
                         f"no reader. Take the whole claim.")
        if short:
            note("REFUSE", f"{short} excerpt(s) under 50 characters will be "
                           f"refused at registration.")
    else:
        note("WARN", "no excerpt column found — the evidence tier's authority is "
                     "this workbook; confirm the tab names.")
    if rows_seen:
        print(f"rows: {rows_seen} · with a date: {dated} · with ERS: {ers}")
        if dated < rows_seen * 0.5:
            note("WARN", f"only {dated} of {rows_seen} rows carry a publication "
                         f"date. Undated items band UNVERIFIED and the recency "
                         f"ladder cannot rank them.")


def main(argv: list[str]) -> int:
    global entity_sv
    argv = list(argv)
    if any(a in ("-h", "--help") for a in argv[1:]):
        print(__doc__ or "mechanical vetting of an assessment package")
        print("usage: vet_workbooks.py <package-dir> [--subvertical <CODE>]")
        return 0
    if "--subvertical" in argv:
        i = argv.index("--subvertical")
        if i + 1 >= len(argv):
            print("--subvertical needs a code "
                  f"({' '.join(sorted(SUBVERTICAL_CODES))})", file=sys.stderr)
            return 2
        entity_sv = argv[i + 1].strip().upper()
        del argv[i:i + 2]
        if entity_sv not in SUBVERTICAL_CODES:
            print(f"unknown sub-vertical code {entity_sv!r} — expected one of "
                  f"{' '.join(sorted(SUBVERTICAL_CODES))}", file=sys.stderr)
            return 2
    if len(argv) < 2:
        print(__doc__)
        return 2
    target = Path(argv[1])
    scoring: Path | None = None
    research: Path | None = None
    if target.is_dir():
        for p in sorted(target.rglob("*.xls[xm]")):
            n = p.name.lower()
            if "research" in n and research is None:
                research = p
            elif "scoring" in n and scoring is None:
                scoring = p
        if scoring is None:
            xl = [p for p in sorted(target.rglob("*.xls[xm]")) if p != research]
            scoring = xl[0] if xl else None
    else:
        scoring = target
        research = Path(argv[2]) if len(argv) > 2 else None

    if scoring is None:
        print("no workbook found", file=sys.stderr)
        return 2
    try:
        vet_scoring(scoring)
        if research:
            vet_research(research)
        else:
            note("REFUSE", "no research workbook found. It is the authority for "
                           "evidence ids, excerpts, ERS and published dates; "
                           "without it every item bands UNVERIFIED.")
    except Exception as e:                                     # noqa: BLE001
        print(f"could not read: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    print("\n=== findings")
    if not findings:
        print("clean — nothing to decide.")
        return 0
    for level, msg in findings:
        print(f"[{level}] {msg}")
    print("\nA REFUSE line means: do not hand this to the parser. Say what is "
          "dirty, in which tab and column, and how many rows.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
