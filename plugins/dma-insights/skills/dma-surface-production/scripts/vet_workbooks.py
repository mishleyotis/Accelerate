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

# Columns whose header contains "score" and which are NOT 1–5 maturity
# scores. Measured across 111 corpus clients, which carry 130 distinct
# *score* headers between them — matching on the substring alone refused
# Houlihan Lokey for 26 "scores outside 1.0–5.0" that were a COUNT of
# sub-capabilities scored (14–25) and a recommendation PRIORITY on its own
# scale (6.0–7.05). Neither is a maturity score and neither was dirty.
NON_MATURITY_SCORE = (
    "scored",        # subcaps_scored, scored_count, categories_scored — counts
    "priority",      # priority_score — its own ranking scale
    "ers",           # ers_score — evidence strength, a different scale
    "delta",         # score_delta — a difference, legitimately negative
    "max_", "max ",  # max_score — the scale's ceiling, not a measurement
    "target",        # target_score — an aspiration
    "weighted",      # weighted_score — score x weight, exceeds 5 by design
    "rationale",     # score_rationale — prose
    "count", "total", "/",
)


def is_maturity_score_column(header: str) -> bool:
    h = (header or "").strip().lower()
    if "score" not in h or "peer" in h:
        return False
    return not any(m in h for m in NON_MATURITY_SCORE)

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


#: Where a cap can be recorded. A cap is a scoring ceiling the assessment
#: applied, and it is written wherever that assessment kept its issue log —
#: a workbook sheet, a CSV, a JSON ledger, a column on the scoring detail.
CAPS_RE = re.compile(r"caps?[_ ]?applied|caps?[_ ]?log|issues?|"
                     r"contradiction", re.I)

#: A `Caps_Applied` cell saying, in the ways packages say it, "none".
NO_CAP = {"", "-", "--", "n/a", "na", "none", "no", "no cap", "no caps",
          "not applied", "nil", "0", "0.0", "false"}


def _is_cap_value(v) -> bool:
    return str(v if v is not None else "").strip().lower() not in NO_CAP


def scan_caps(root: Path, pm: dict, books: list) -> dict:
    """Every place this package could have recorded a cap, and what is in them.

    THE RULE THIS EXISTS TO ENFORCE (owner, 2026-08-23): "Caps applied may
    even exist in the scoring and research workbook and usually relate to
    the issue log or issues raised in the client research report, or an
    issue log in csv or any other format. If no caps were applied, then
    there were no issues."

    Both halves matter. Caps are not confined to a `Caps_Applied_Log` sheet,
    so looking only there and finding nothing proves nothing — and an EMPTY
    result is a real answer, not a missing one. On 2026-08-23 a vetter
    refused three consecutive packages for a missing sheet and the routine
    burned its entire reserve list in one firing on a state that means "this
    assessment raised no issues".

    So this returns what it found and where it looked, and the caller reports
    both. Nothing here refuses.
    """
    checked, sources, records = [], [], 0
    for book in [b for b in books if b]:
        try:
            tabs = sheets_of(book)
        except Exception:                                      # noqa: BLE001
            continue
        rel = str(book)
        counted_sheets = set()
        for name, rows in tabs.items():
            if CAPS_RE.search(name):
                checked.append(f"{Path(rel).name}[{name}]")
                counted_sheets.add(name)
                body = [r for r in rows[1:] if any(
                    str(c or "").strip() for c in r)]
                if body:
                    sources.append(f"{Path(rel).name}[{name}]: {len(body)} row(s)")
                    records += len(body)
        # The COLUMN, which is where a cap is recorded per scored row and
        # which no "is the sheet present" check can see. A sheet already
        # counted whole is skipped: an Issue_Log sheet with an `Issue`
        # column would otherwise be counted once as rows and again as cells.
        for name, rows in tabs.items():
            if not rows or name in counted_sheets:
                continue
            hdr = [str(c or "").strip().lower() for c in rows[0]]
            cols = [i for i, h in enumerate(hdr) if CAPS_RE.search(h)]
            if not cols:
                continue
            checked.append(f"{Path(rel).name}[{name}].{hdr[cols[0]]}")
            hits = sum(1 for r in rows[1:] for i in cols
                       if i < len(r) and _is_cap_value(r[i]))
            if hits:
                sources.append(f"{Path(rel).name}[{name}] column "
                               f"{hdr[cols[0]]!r}: {hits} capped row(s)")
                records += hits

    # Files, in any format the package chose.
    for rel in (pm.get("governance") or []) + (pm.get("other") or []) + \
            (pm.get("evidence_tables") or []):
        if not CAPS_RE.search(rel):
            continue
        p = root / rel
        checked.append(rel)
        try:
            if p.suffix.lower() in (".csv", ".tsv"):
                lines = [ln for ln in p.read_text(
                    errors="replace").splitlines() if ln.strip()]
                n = max(0, len(lines) - 1)
            elif p.suffix.lower() in (".json", ".jsonl"):
                import json                                    # noqa: PLC0415
                if p.suffix.lower() == ".jsonl":
                    n = sum(1 for ln in p.read_text(
                        errors="replace").splitlines() if ln.strip())
                else:
                    d = json.loads(p.read_text(errors="replace"))
                    n = len(d) if isinstance(d, list) else len(
                        next((v for v in d.values() if isinstance(v, list)), []))
            else:
                continue
        except Exception:                                      # noqa: BLE001
            continue
        if n:
            sources.append(f"{rel}: {n} row(s)")
            records += n

    # A report is where a human reads the issues; it is named, never parsed.
    prose = [r for r in (pm.get("reports") or []) if CAPS_RE.search(r)]
    return {"records": records, "sources": sources, "checked": checked,
            "prose": prose}


def report_caps(caps: dict) -> None:
    """Say what was found, and say plainly that nothing found is an answer."""
    if caps["records"]:
        note("PIN", f"caps applied: {caps['records']} record(s) across "
                    f"{len(caps['sources'])} source(s) — "
                    f"{'; '.join(caps['sources'][:4])}. Every cap is a "
                    f"scoring ceiling the assessment applied; it belongs in "
                    f"the payload's caps[] and is NOT a safeguard gate")
        return
    where = (f"looked in {len(caps['checked'])} place(s): "
             f"{', '.join(caps['checked'][:6])}"
             if caps["checked"] else
             "no caps sheet, log or column exists anywhere in this package")
    note("PIN", f"NO CAPS APPLIED — {where}. This is a valid state and NEVER "
                f"a refusal (owner, 2026-08-23): if no caps were applied, "
                f"then there were no issues. Serve caps[] empty and say so; "
                f"do not hunt for a Caps_Applied_Log that a clean assessment "
                f"had no reason to write")
    if caps["prose"]:
        note("PIN", f"issue narrative to read if a cap is later claimed: "
                    f"{', '.join(caps['prose'][:3])}")


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
    ev_defs: dict[str, list[str]] = {}
    missing_source_cell = 0
    saw_source_cell_col = False

    for name, rows in tabs.items():
        hi, hdr = header_row(rows)
        if hi is None:
            continue
        low = [h.lower() for h in hdr]
        is_register = "evidence" in name.lower()

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
            row_eids: list[str] = []
            for c in r:
                if isinstance(c, str):
                    t = c.strip()
                    if CELL_RE.match(t):
                        cells.append(t.upper())
                    elif EID_RE.match(t):
                        e_ids.append(t.upper())
                        row_eids.append(t.upper())
                elif isinstance(c, (int, float)):
                    if 0 < float(c) <= 5.0 or float(c) == 0:
                        pass
            if is_register and len(row_eids) == 1:
                fp = " | ".join(
                    re.sub(r"\s+", " ", str(c).strip().lower())
                    for c in r
                    if c is not None and str(c).strip()
                    and str(c).strip().upper() != row_eids[0])
                ev_defs.setdefault(row_eids[0], []).append(fp)
            if idx_src is not None and (idx_src >= len(r) or r[idx_src] in (None, "")):
                missing_source_cell += 1

        # score range, per column named like a score
        for j, h in enumerate(low):
            if "score" not in h or "peer" in h:
                continue
            col = []
            for r in rows[hi + 1:]:
                if r is None or j >= len(r):
                    continue
                v = r[j]
                if isinstance(v, (int, float)):
                    col.append(float(v))
            if not col:
                continue
            if not is_maturity_score_column(h):
                note("WARN", f"{name}: column {hdr[j]!r} is named like a "
                             f"score and is not one (a count, a different "
                             f"scale, or prose). Its range is NOT checked "
                             f"against 1.0-5.0.")
                continue
            live = [v for v in col if v != 0]
            in_range = [v for v in live if 1.0 <= v <= 5.0]
            if live and not in_range:
                # EVERY value out of range is a misidentified column, not
                # 26 dirty measurements. Refusing here is how a package is
                # halted for a header this script did not recognise.
                note("WARN", f"{name}: column {hdr[j]!r} holds no value in "
                             f"1.0-5.0 at all ({len(live)} values, e.g. "
                             f"{sorted(set(live))[:4]}) — it is very likely "
                             f"not a maturity score. Name it here if it is.")
                continue
            scores.extend(col)

    bad = [v for v in scores if v != 0 and not (1.0 <= v <= 5.0)]
    if bad:
        note("REFUSE", f"{len(bad)} score(s) outside 1.0–5.0 "
                       f"(e.g. {sorted(set(bad))[:5]}). A 0 bands as Activating "
                       f"and looks assessed.")
    zeros = [v for v in scores if v == 0]
    if zeros:
        note("WARN", f"{len(zeros)} score(s) are exactly 0 — confirm these are "
                     f"blanks, not measurements.")

    # Evidence ids are unique PER CLIENT, and one id cited from many tabs is
    # a reference, not a defect (owner adjudication 2026-08-20: 43 false
    # REFUSEs on the first live vetting were exactly this). The defect that
    # loses rows silently under ON CONFLICT DO NOTHING is one id DEFINED
    # more than once with DIFFERENT content in a register tab — duplicate
    # by content decides, never duplicate by id alone.
    conflicting = {k: v for k, v in ev_defs.items() if len(set(v)) > 1}
    repeated = {k: len(v) for k, v in ev_defs.items()
                if len(v) > 1 and len(set(v)) == 1}
    if conflicting:
        worst = sorted(conflicting.items(), key=lambda kv: -len(kv[1]))[:6]
        note("REFUSE", f"{len(conflicting)} evidence id(s) defined more than "
                       f"once with DIFFERENT content "
                       f"({', '.join(f'{k}×{len(v)}' for k, v in worst)}). One "
                       f"of each pair would be lost silently — adjudicate "
                       f"which row is real before parsing.")
    if repeated:
        note("WARN", f"{len(repeated)} evidence id(s) re-defined with "
                     f"identical content — benign repetition; dedup is by "
                     f"content hash. Ids are unique per client only: any "
                     f"cross-client ledger entry carries the client slug as "
                     f"a prefix (e.g. t-rowe-price-group-inc:E-017).")

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
        # Discovery goes through package_map: packages come in at least four
        # structure generations (wrappers, 03_Assessment, workbooks in
        # 08_appendices, version stacks with INTERIM copies beside the live
        # workbook — measured across the 178-client corpus, 2026-08-20).
        # Naive rglob picked whichever xlsx sorted first.
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]
                               / "scripts"))
        import package_map  # noqa: PLC0415
        pm = package_map.map_package(target)
        scoring = Path(pm["scoring"]["primary"]) \
            if pm["scoring"]["primary"] else None
        research = Path(pm["research"]["primary"]) \
            if pm["research"]["primary"] else None
        for amb in pm["ambiguities"]:
            note("WARN", f"package_map: {amb}")
        for aux in pm["auxiliary_xlsx"]:
            note("PIN", f"auxiliary workbook (not vetted as scoring): {aux}")
        if pm["evidence_tables"]:
            note("PIN", f"{len(pm['evidence_tables'])} evidence stores "
                        f"beyond the workbooks — evidence_normalize.py "
                        f"merges them; vet gaps there, not here")
        report_caps(scan_caps(target, pm, [scoring, research]))
    else:
        scoring = target
        research = Path(argv[2]) if len(argv) > 2 else None

    if scoring is None:
        print("no scoring workbook found — package_map classified the tree; "
              "a briefing- or research-only folder is not a synthesis input",
              file=sys.stderr)
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
