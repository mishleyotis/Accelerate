"""Parse the package's peer-benchmark artifacts → per-category peer
distribution (median / p25 / p75 / n).

Feeds D1 peer-median ticks + D3 heatmap peer overlay. Today
`CategoryScoreRow.peer_median` is populated ONLY from the scoring
workbook / `export_category_summary.csv` `peer_median` column — but many
packages (e.g. Greenstone) ship no such column and instead carry the
peer cohort in `06_peers/`:

  - `peer_comparison_table.csv` (78 packages): wide table — one column
    per peer plus `Peer Median`, `P25`, `P75`, `Gap vs Median`. May be
    prefixed by `#` comment lines.
  - `peer_benchmarks.json` (33 packages): `{benchmarks: {<cat>: {
    peer_median, p25, p75, gap_vs_median, peer_scores:{…}}}}` — richer
    (carries the per-peer scores), so it is preferred when both exist.

Both key categories like `P1C1_digital_strategy`; we normalise to the
catalogue category id (`P1C1`) so the values merge onto the parsed
`CategoryScoreRow`s by `category_id`.

Pure / no DB. Returns `{}` when no peer artifact is present.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

_CAT_RE = re.compile(r"^\s*(P\d+C\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class PeerBenchmark:
    median: float | None = None
    p25: float | None = None
    p75: float | None = None
    n: int | None = None
    gap_vs_median: float | None = None


def _cat_key(raw: str | None) -> str | None:
    """`P1C1_digital_strategy` / `p1c1` → canonical `P1C1`."""
    if not raw:
        return None
    m = _CAT_RE.match(str(raw))
    return m.group(1).upper() if m else None


def _to_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        s = str(v).strip().rstrip("%")
        return float(s) if s not in ("", "-", "N/A", "n/a", "NA") else None
    except (TypeError, ValueError):
        return None


def parse_peer_benchmarks_json(path: Path) -> dict[str, PeerBenchmark]:
    """Read `peer_benchmarks.json` → {category_id: PeerBenchmark}."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Accept {benchmarks:{…}} / {category_benchmarks:{…}} / top-level {<cat>:{…}}.
    blocks = data
    for key in ("benchmarks", "category_benchmarks"):
        if isinstance(data.get(key), dict):
            blocks = data[key]
            break
    if not isinstance(blocks, dict):
        return {}
    out: dict[str, PeerBenchmark] = {}
    for raw_cat, b in blocks.items():
        cat = _cat_key(raw_cat)
        if cat is None or not isinstance(b, dict):
            continue
        peer_scores = b.get("peer_scores")
        n = len(peer_scores) if isinstance(peer_scores, dict) else None
        bench = PeerBenchmark(
            median=_to_float(b.get("peer_median") or b.get("median")),
            p25=_to_float(b.get("p25")),
            p75=_to_float(b.get("p75")),
            n=n,
            gap_vs_median=_to_float(b.get("gap_vs_median")),
        )
        if bench.median is not None:
            out[cat] = bench
    if out:
        return out

    # Flat {category: median_scalar} variants: peer_medians_by_category
    # (Calprivate), peer_medians (Vestgen), or a top-level flat map
    # (standalone peer_medians.json).
    for flat_key in ("peer_medians_by_category", "peer_median_by_category",
                     "peer_medians", "medians"):
        flat = data.get(flat_key)
        if isinstance(flat, dict):
            for raw_cat, val in flat.items():
                cat = _cat_key(raw_cat)
                med = _to_float(val if not isinstance(val, dict)
                                else val.get("median") or val.get("peer_median"))
                if cat and med is not None and cat not in out:
                    out[cat] = PeerBenchmark(median=med)
            if out:
                return out
    # Top-level flat map (e.g. {"P1C1": 2.5, …}).
    for raw_cat, val in data.items():
        cat = _cat_key(raw_cat)
        med = _to_float(val) if not isinstance(val, dict | list) else None
        if cat and med is not None:
            out[cat] = PeerBenchmark(median=med)
    return out


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (h or "").strip().lower()).strip("_")


def parse_peer_comparison_csv(path: Path) -> dict[str, PeerBenchmark]:
    """Read `peer_comparison_table.csv` → {category_id: PeerBenchmark}.

    Tolerates leading `#` comment lines and header drift (e.g.
    `Peer Median` / `peer_median`). `n` (peer count) is the number of
    score columns between `Category` and the first benchmark column,
    minus the assessed entity's own column.
    """
    if not path.exists():
        return {}
    try:
        raw_lines = path.read_text().splitlines()
    except OSError:
        return {}
    # Strip leading comment / blank lines so DictReader sees the header.
    lines = [ln for ln in raw_lines if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return {}
    reader = csv.DictReader(lines)
    if not reader.fieldnames:
        return {}
    norm_map = {_norm_header(h): h for h in reader.fieldnames}
    # Header drift: "Peer Median" (GreenStone) vs bare "Median" (Corporate
    # America). Accept either.
    med_key = norm_map.get("peer_median") or norm_map.get("median")
    if med_key is None:
        return {}
    p25_key = norm_map.get("p25")
    p75_key = norm_map.get("p75")
    gap_key = norm_map.get("gap_vs_median")
    cat_key_col = norm_map.get("category") or reader.fieldnames[0]
    # Peer count: columns before "Peer Median", excluding Category + entity.
    med_idx = reader.fieldnames.index(med_key)
    n_peers = max(med_idx - 2, 0) or None

    out: dict[str, PeerBenchmark] = {}
    for row in reader:
        cat = _cat_key(row.get(cat_key_col))
        median = _to_float(row.get(med_key))
        if cat is None or median is None:
            continue
        out[cat] = PeerBenchmark(
            median=median,
            p25=_to_float(row.get(p25_key)) if p25_key else None,
            p75=_to_float(row.get(p75_key)) if p75_key else None,
            n=n_peers,
            gap_vs_median=_to_float(row.get(gap_key)) if gap_key else None,
        )
    return out


def parse_peer_transposed_csv(path: Path) -> dict[str, PeerBenchmark]:
    """Transposed peer table (TowneBank): one row per PEER, columns are
    pillar scores (`P1_Strategy_Governance`, `P2_…`). Compute a peer median
    per PILLAR; returned PILLAR-keyed (`P1`/`P2`/…) so the caller broadcasts
    each pillar median to its categories (DERIVED — same shallow-broadcast
    pattern the app already uses for category→subcap)."""
    import statistics
    if not path.exists():
        return {}
    lines = [
        ln for ln in (path.read_text().splitlines() if path.exists() else [])
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    if not lines:
        return {}
    reader = csv.DictReader(lines)
    if not reader.fieldnames:
        return {}
    pillar_cols = {
        h: m.group(1).upper()
        for h in reader.fieldnames
        if (m := re.match(r"^(P\d+)_", h.strip(), re.IGNORECASE))
    }
    if not pillar_cols:
        return {}
    by_pillar: dict[str, list[float]] = {}
    for row in reader:
        for h, pillar in pillar_cols.items():
            v = _to_float(row.get(h))
            if v is not None:
                by_pillar.setdefault(pillar, []).append(v)
    out: dict[str, PeerBenchmark] = {}
    for pillar, vals in by_pillar.items():
        if vals:
            out[pillar] = PeerBenchmark(median=round(statistics.median(vals), 2),
                                        n=len(vals))
    return out


def load_peer_benchmarks(root: Path) -> dict[str, PeerBenchmark]:
    """Resolve the per-category peer distribution for a package, preferring
    the richer JSON. Searches RECURSIVELY (peer artifacts land in 06_peers,
    08_appendices, 03_scoring_workbook, Background-Research subdirs). Returns
    {} when no artifact is present.
    """
    for name in ("peer_benchmarks.json", "peer_medians.json"):
        for p in sorted(root.glob(f"**/{name}")):
            benchmarks = parse_peer_benchmarks_json(p)
            if benchmarks:
                return benchmarks
    for p in sorted(root.glob("**/peer_comparison_table.csv")):
        benchmarks = parse_peer_comparison_csv(p)
        if benchmarks:
            return benchmarks
        # category-per-row parse empty → try the transposed (peer-per-row,
        # pillar-column) layout, returned PILLAR-keyed for broadcast.
        transposed = parse_peer_transposed_csv(p)
        if transposed:
            return transposed
    return {}
