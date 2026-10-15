"""Deterministic first-promotion completeness checks — one pure function, read
at two moments: on the section files before a page ships, and on the payload
the connector actually STAGED before `promote_run`.

AAA WCNY (2026-10-15) promoted with no peer figures and two opportunity tiles
while the workbook held a peer table and the catalogue held 22 READY
platforms. The connector's parity gate only WARNS on list length (owner,
2026-10-04), and every earlier control here was a producer instruction — a
probability, not a control. These are arithmetic over the payload: no model
reads them and no model can talk past them. Each returns
(section, message) pairs; an empty list is the only pass.

Fail-closed by construction: a missing shortlist, a shortlist for another
connector run, a missing card set or a workbook without peer medians is a
refusal, never a skipped check.
"""
from __future__ import annotations

from typing import Callable

TILES_WANTED = 5            # the contract's "Five tiles"; gold runs carry 4-5
SHORTLIST_FILE = "platform_shortlist.json"


def _norm(name) -> str:
    return " ".join(str(name or "").casefold().split())


def null_peer_paths(node, path: str = "") -> list[str]:
    """Every `peer_median` key holding null, anywhere in a section."""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else k
            if k == "peer_median" and v is None:
                out.append(p)
            else:
                out.extend(null_peer_paths(v, p))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.extend(null_peer_paths(v, f"{path}[{i}]"))
    return out


def shortlist_problem(sl, connector_run: str | None) -> str | None:
    if not isinstance(sl, dict):
        return ("no full-catalogue platform shortlist (07_qa/platform_shortlist.json): "
                "the fit engine never scored the catalogue for this version")
    if sl.get("error"):
        return f"the full-catalogue shortlist failed: {sl['error']}"
    if connector_run and sl.get("connector_run") and sl["connector_run"] != connector_run:
        return (f"the shortlist was scored on connector run {sl['connector_run']}, "
                f"not {connector_run}: rebuild it on the version being shipped")
    if not isinstance(sl.get("tiles_wanted"), int):
        return "the shortlist carries no integer tiles_wanted"
    return None


def ranked_cards(story) -> list[dict]:
    cards = [c for c in ((story or {}).get("platforms") or []) if isinstance(c, dict)]
    return sorted([c for c in cards if isinstance(c.get("rank"), (int, float))],
                  key=lambda c: c["rank"])


def check(page: str, sec: Callable[[str], dict | None], *, shortlist,
          connector_run: str | None, peer_categories: int) -> list[tuple[str, str]]:
    """`sec(name)` returns a section dict (`overview.opportunity`) or None;
    `peer_categories` is how many Peer_Benchmarks rows carry a median."""
    out: list[tuple[str, str]] = []
    sl_bad = shortlist_problem(shortlist, connector_run)
    want = int((shortlist or {}).get("tiles_wanted") or 0) if not sl_bad else 0

    if page in ("overview", "heatmap"):
        name = "overview.scores" if page == "overview" else "heatmap.workbook_scores"
        if peer_categories <= 0:
            out.append((name, f"CG-COMPLETE {page} peers: Peer_Benchmarks carries no median "
                              f"for any category. A first promotion never serves 'no peer "
                              f"benchmark': the SCORING peer gate fills the table (cohort, or "
                              f"three locked peers scored by the protocol) before any page."))
        else:
            body = sec(name)
            if body is None:
                out.append((name, f"CG-COMPLETE {page} peers: {name} is missing."))
            else:
                nulls = null_peer_paths(body)
                if nulls:
                    out.append((name, f"CG-COMPLETE {page} peers: {len(nulls)} peer_median "
                                      f"null ({', '.join(nulls[:4])}) while Peer_Benchmarks "
                                      f"carries {peer_categories} categor(ies) with a median. "
                                      f"Serve the workbook's figures with their basis."))

    if page in ("overview", "platform"):
        sect = "overview.opportunity" if page == "overview" else "platform.platform_story"
        if sl_bad:
            out.append((sect, f"CG-COMPLETE {page}: {sl_bad}."))
            return out
        story = sec("platform.platform_story")
        cards = ranked_cards(story)
        if page == "platform":
            have = {_norm(c.get("platform")) for c in ((story or {}).get("platforms") or [])
                    if isinstance(c, dict)}
            top = [p.get("platform") for p in (shortlist.get("shortlist") or [])[:want]]
            miss = [p for p in top if _norm(p) not in have]
            if story is None:
                out.append((sect, "CG-COMPLETE platform: platform.platform_story is missing."))
            elif miss:
                out.append((sect, f"CG-COMPLETE platform.platform_story: the full-catalogue "
                                  f"top {want} READY platform(s) need a card each; missing "
                                  f"{', '.join(map(str, miss))} (engine spelling)."))
            if story is not None and len(cards) < want:
                out.append((sect, f"CG-COMPLETE platform.platform_story: {len(cards)} ranked "
                                  f"card(s); the overview tiles the top {want}."))
        else:
            op = sec("overview.opportunity") or {}
            tiles = [t for t in (op.get("tiles") or []) if isinstance(t, dict)]
            if len(tiles) < want:
                out.append((sect, f"CG-COMPLETE overview.opportunity.tiles: {len(tiles)} tile(s); "
                                  f"the full-catalogue fit engine has {shortlist.get('ready')} "
                                  f"READY platform(s). Serve the top {want} as tiles."))
            if story is None:
                if want:
                    out.append((sect, "CG-COMPLETE overview.opportunity: no platform cards to "
                                      "pin the tiles to (platform.platform_story missing)."))
                return out
            top_cards = [_norm(c.get("platform")) for c in cards[:want]]
            got = [_norm(t.get("platform")) for t in tiles]
            if want and got[:want] != top_cards:
                out.append((sect, f"CG-COMPLETE overview.opportunity.tiles: the tiles must be "
                                  f"the top {want} platform cards in card-rank order "
                                  f"({', '.join(str(c.get('platform')) for c in cards[:want])}); "
                                  f"served {', '.join(str(t.get('platform')) for t in tiles)}."))
            by = {_norm(c.get("platform")): c for c in cards}
            for i, t in enumerate(tiles):
                c = by.get(_norm(t.get("platform")))
                if not c:
                    continue
                bad = []
                if t.get("rank") != c.get("rank"):
                    bad.append(f"rank {t.get('rank')} vs card {c.get('rank')}")
                fs, comp = c.get("fit_score"), t.get("composite")
                if not (isinstance(fs, (int, float)) and isinstance(comp, (int, float))
                        and abs(float(fs) - float(comp)) <= 0.05):
                    bad.append(f"composite {comp} vs card fit_score {fs}")
                if bad:
                    out.append((sect, f"CG-31 overview.opportunity.tiles[{i}] "
                                      f"'{t.get('platform')}': " + "; ".join(bad)
                                      + ". Every figure, the order and the rank prose come "
                                        "from the card in platform.platform_story."))
    return out
