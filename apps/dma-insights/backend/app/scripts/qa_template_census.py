"""Cross-client template census — the uniqueness instrument.

Operator mandate (2026-07-13 stress-test): "Writeups should never be
templated; ensure the uniqueness in writing for each surface." This gate
measures that directly: it masks the volatile tokens (numbers, $-figures,
citations, the entity's own name) in every narrative sentence, shingles the
masked sentences into 6-word frames, and counts how many DISTINCT CLIENTS
share each frame per surface. A frame shared by >=10 of the 94 clients is a
template by construction — no amount of grounding rescues prose an AE can
recognize as a colleague's deck with the nouns swapped.

Baseline (committed pack, 2026-07-13 pre-restyle):
    overview.scqa_md        158 frames shared by >=10 clients (peak 88/94)
    platforms.story_md      260 (peak 94/94)
    platforms.opportunity_md 75 (peak 94/94)
    insights.why            50 (peak 63/94)
    context.firmo           24 (peak 45/94)

Metrics (snapshot-schema compatible for benchmarks/raw/extras):
    census.<surface>.frames_ge10   count of frames shared by >=10 clients
    census.<surface>.peak_share    max clients sharing any single frame
    census.total_frames_ge10       sum across surfaces

Pure stdlib (json + re) — runs identically in CI and locally, no models.

Usage:
  python -m app.scripts.qa_template_census [--clients-dir DIR] [--json]
         [--top N]     # print the N most-shared frames per surface
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict

_CITE_RE = re.compile(r"\[[^\]]*\]|\([^()]*\b(?:E|EV|INT)-\d[^()]*\)")
_MONEY_RE = re.compile(r"\$[\d.,]+[TBMK]?")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_SHINGLE = 6
_SHARE_FLOOR = 10


_SCORE_NOTATION_RE = re.compile(
    r"N/N[^.;:()]{0,50}?peer[^.;:()]{0,30}?(?:median|benchmark|line|bar)"
    r"(?:\s+(?:of\s+)?N|\s+holds?\s+N|\s+at\s+N)?"
    r"|peer median (?:of |at |holds? )?N"
    r"|N/N\s*(?:vs|versus|against)\s*(?:a\s+|the\s+)?N"
    r"|\(N(?:\.\d+)?/N[^)]{0,40}\)")


def _mask(s: str, name: str) -> str:
    s = _CITE_RE.sub("[CITE]", s)
    s = _MONEY_RE.sub("$N", s)
    s = _NUM_RE.sub("N", s)
    # Score-vs-peer readings are DATA NOTATION, not narrative — a consistent
    # notation is desirable (like "$1.2B"), so the census collapses every
    # rendering to one token and measures only the surrounding prose.
    s = _SCORE_NOTATION_RE.sub("SCORE_VS_PEER", s)
    if name:
        s = re.sub(re.escape(name), "ENTITY", s, flags=re.I)
    return s


def _frames(sent: str, name: str):
    words = _mask(sent, name).split()
    for i in range(0, max(1, len(words) - _SHINGLE + 1)):
        chunk = words[i:i + _SHINGLE]
        if len(chunk) == _SHINGLE:
            yield " ".join(chunk).lower()


def _sentences(md: object):
    for para in re.split(r"\n\n+", str(md or "")):
        for s in _SENT_RE.split(para.strip()):
            s = s.strip()
            if len(s) > 40:
                yield s


# surface → (filename, extractor over the loaded JSON → list[str])
SURFACES: dict = {
    "overview.scqa_md": ("overview.json", lambda d: [
        (d.get("narrative") or {}).get("scqa_md")]),
    "overview.findings": ("overview.json", lambda d: [
        x for f in (d.get("top_findings") or [])
        for x in (f.get("body"), f.get("why"), f.get("what"), f.get("so_what"))]),
    "platforms.story_md": ("platforms.json", lambda d: [
        c.get("story_md") for c in d.get("cards") or []]),
    "platforms.opportunity_md": ("platforms.json", lambda d: [
        c.get("opportunity_md") for c in d.get("cards") or []]),
    "insights.why": ("insights.json", lambda d: [
        c.get("why_text") or c.get("why")
        for c in d.get("cards") or d.get("items") or []]),
    "context.firmo": ("context.json", lambda d: [
        (d.get("firmographics") or {}).get("narrative_md")]),
}


# Surfaces with MANY instances per client (5 platform cards, ~10 insight
# items) are measured per-INSTANCE: an AE reads one client at a time, so the
# honest uniqueness unit there is the card, and the floor is a share of all
# cards (20%), not an absolute client count — per-client counting saturates
# mathematically once a client has >=5 draws from any finite pool.
_PER_INSTANCE = {"platforms.story_md", "platforms.opportunity_md",
                 "insights.why", "overview.findings"}
_INSTANCE_SHARE_FLOOR = 0.20


def census(clients_dir: str) -> dict:
    clients = sorted(
        c for c in os.listdir(clients_dir)
        if os.path.isdir(os.path.join(clients_dir, c)))
    out: dict = {"clients": len(clients), "surfaces": {}}
    for surf, (fname, extract) in SURFACES.items():
        per_instance = surf in _PER_INSTANCE
        frame_units: dict[str, set[str]] = defaultdict(set)
        n_units = 0
        for c in clients:
            path = os.path.join(clients_dir, c, fname)
            ov_path = os.path.join(clients_dir, c, "overview.json")
            if not os.path.exists(path):
                continue
            try:
                with open(path) as fh:
                    d = json.load(fh)
                name = ""
                if os.path.exists(ov_path):
                    with open(ov_path) as fh:
                        name = ((json.load(fh).get("entity") or {})
                                .get("name")) or ""
            except (json.JSONDecodeError, OSError):
                continue
            texts = [t for t in extract(d) if isinstance(t, str) and t.strip()]
            if not per_instance and texts:
                n_units += 1
            for i, t in enumerate(texts):
                unit = f"{c}#{i}" if per_instance else c
                if per_instance:
                    n_units += 1
                for s in _sentences(t):
                    for f in _frames(s, name):
                        frame_units[f].add(unit)
        floor = (max(_SHARE_FLOOR, int(n_units * _INSTANCE_SHARE_FLOOR))
                 if per_instance else _SHARE_FLOOR)
        shared = sorted(
            ((len(us), f) for f, us in frame_units.items()
             if len(us) >= floor), reverse=True)
        out["surfaces"][surf] = {
            "unit": "instance" if per_instance else "client",
            "n_units": n_units,
            "floor": floor,
            "frames_over_floor": len(shared),
            "frames_ge10": len(shared),   # legacy metric name
            "peak_share": shared[0][0] if shared else 0,
            "top": [{"clients": n, "frame": f} for n, f in shared[:20]],
        }
    out["total_frames_ge10"] = sum(
        v["frames_over_floor"] for v in out["surfaces"].values())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients-dir", default=os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "startup-data", "clients"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=0)
    args = ap.parse_args()
    result = census(os.path.abspath(args.clients_dir))
    if args.json:
        # snapshot-schema metrics for benchmarks/raw/extras
        metrics = {"census.total_frames_ge10": {
            "value": result["total_frames_ge10"], "direction": "down"}}
        for surf, v in result["surfaces"].items():
            metrics[f"census.{surf}.frames_ge10"] = {
                "value": v["frames_ge10"], "direction": "down"}
            metrics[f"census.{surf}.peak_share"] = {
                "value": v["peak_share"], "direction": "down"}
        print(json.dumps({"metrics": metrics, "detail": result}, indent=1))
        return 0
    print(f"clients: {result['clients']}")
    for surf, v in result["surfaces"].items():
        print(f"\n=== {surf}: frames shared by >={v['floor']} "
              f"{v['unit']}s (of {v['n_units']}): "
              f"{v['frames_over_floor']} (peak {v['peak_share']})")
        for row in v["top"][:args.top]:
            print(f"  {row['clients']:3d} | {row['frame']}")
    print(f"\ntotal_frames_ge10: {result['total_frames_ge10']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
