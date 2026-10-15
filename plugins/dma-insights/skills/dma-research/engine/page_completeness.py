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

import json
import re
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
            barred = {_norm(x.get("platform")): x for x in
                      (shortlist.get("in_estate") or []) + (shortlist.get("replaces") or [])}
            for c in cards:
                b = barred.get(_norm(c.get("platform")))
                if b:
                    out.append((sect, f"CG-COMPLETE platform.platform_story: '{c.get('platform')}' "
                                      + (f"is already in the client's estate ({b.get('in_estate')})"
                                         if b.get("in_estate") else
                                         f"would replace {', '.join(b.get('replaces_in_estate') or [])}")
                                      + " and is a ranked card: it is an optimization "
                                        "recommendation (or a discard), never a card the page ranks."))
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
            owned = {_norm(p.get("platform")) for p in (shortlist.get("in_estate") or [])}
            cards = [c for c in cards if _norm(c.get("platform")) not in owned]
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
        if page == "overview":
            out.extend(estate_rules(sec, shortlist))
    if page == "platform" and not sl_bad:
        out.extend(optimization_rules(sec, shortlist))
    return out


_VERIFY = ("verify", "confirm")
#: Words that make a recommendation title OPTIMIZE what is owned rather than
#: sell something next to it (owner, 2026-10-15: "be more thorough in
#: optimization ... I feel you are banking on selling").
_OPTIMIZE = re.compile(r"\b(optimi[sz]\w*|health[ -]?check|reuse|re-use|adoption|"
                       r"rationali[sz]\w*|consolidat\w*|tune|tuning|verify|"
                       r"get more from|maximi[sz]\w*)\b", re.I)


def _optimizing_titles(recs) -> list[str]:
    return [_norm(r.get("title")) for r in recs
            if isinstance(r, dict) and _OPTIMIZE.search(str(r.get("title") or ""))]


def estate_rules(sec, shortlist) -> list[tuple[str, str]]:
    """What the client already owns, read deterministically off the engine's
    estate fields (`in_estate`, `vendor_in_estate`, `replaces_in_estate`).
    AAA WCNY (2026-10-15, owner: "be more thorough in optimization ... mention
    clearly to verify FSC rollout")."""
    out = []
    op = sec("overview.opportunity") or {}
    tiles = [t for t in (op.get("tiles") or []) if isinstance(t, dict)]
    owned = {_norm(p.get("platform")): p for p in (shortlist.get("in_estate") or [])}
    by = {_norm(p.get("platform")): p for p in (shortlist.get("shortlist") or [])}
    for i, t in enumerate(tiles):
        name = _norm(t.get("platform"))
        if name in owned:
            out.append(("overview.opportunity", f"CG-COMPLETE overview.opportunity.tiles[{i}] "
                        f"'{t.get('platform')}' is already in the client's estate "
                        f"({owned[name].get('in_estate')}): the contract discards a platform "
                        f"'the client already runs at the layer in question'. Move it to "
                        f"discarded[] and carry it as an optimization recommendation."))
            continue
        row = by.get(name) or {}
        ctx = f"{t.get('their_stack_context') or ''} {t.get('rank_rationale') or ''}"
        low = _norm(ctx)
        if row.get("vendor_in_estate") and not any(w in low for w in _VERIFY):
            out.append(("overview.opportunity", f"CG-COMPLETE overview.opportunity.tiles[{i}] "
                        f"'{t.get('platform')}' extends a vendor org the client already runs "
                        f"({row.get('vendor_in_estate')}): their_stack_context must say to "
                        f"verify (or confirm) its rollout and entitlement on that org before "
                        f"it is proposed."))
    replacing = {_norm(p.get("platform")): p for p in (shortlist.get("replaces") or [])}
    for i, t in enumerate(tiles):
        p = replacing.get(_norm(t.get("platform")))
        if p:
            out.append(("overview.opportunity", f"CG-COMPLETE overview.opportunity.tiles[{i}] "
                        f"'{t.get('platform')}' would replace "
                        f"{', '.join(p.get('replaces_in_estate') or [])}, which the client runs: "
                        f"a replacement is a discard with that reason, never a tile."))
    disc = {_norm(d.get("platform")) for d in (op.get("discarded") or []) if isinstance(d, dict)}
    for name, p in owned.items():
        if name not in disc:
            out.append(("overview.opportunity", f"CG-COMPLETE overview.opportunity.discarded: "
                        f"'{p.get('platform')}' is in the client's estate ({p.get('in_estate')}) "
                        f"and is not listed as discarded with that reason."))
    for name, p in replacing.items():
        if name not in disc:
            out.append(("overview.opportunity", f"CG-COMPLETE overview.opportunity.discarded: "
                        f"'{p.get('platform')}' would replace "
                        f"{', '.join(p.get('replaces_in_estate') or [])} and is not listed as "
                        f"discarded with that reason."))
    return out


def optimization_rules(sec, shortlist) -> list[tuple[str, str]]:
    """Every catalogue platform the client already runs is covered by an
    optimization recommendation on the platform page."""
    recs = (sec("platform.recommendations") or {}).get("recommendations") or []
    # An optimization recommendation is one whose TITLE names the owned
    # vendor or product AND optimizes it; naming a vendor while selling the
    # next licence beside it is not optimizing (AAA WCNY: "Extend Salesforce
    # with Service Cloud" named Salesforce and optimized nothing).
    text = " ".join(_optimizing_titles(recs))
    out = []
    for v in shortlist.get("estate_vendors") or []:
        if _norm(v) not in text:
            out.append(("platform.recommendations", f"CG-COMPLETE platform.recommendations: "
                        f"the client already runs {v} (technology register) and no "
                        f"recommendation TITLE optimizes it (optimize, health check, reuse, "
                        f"adoption, rationalize, consolidate, verify)."))
    owned = [p for p in shortlist.get("in_estate") or [] if isinstance(p, dict)]
    per_vendor: dict = {}
    for p in owned:
        per_vendor[_norm(p.get("vendor"))] = per_vendor.get(_norm(p.get("vendor")), 0) + 1
    for p in owned:
        name = _norm(p.get("platform"))
        vend = _norm(p.get("vendor"))
        bare = _norm(name.replace(vend, "", 1)) if vend else name
        alias = " ".join(re.findall(r"\(([^)]*)\)", str(p.get("platform") or "")))
        forms = {name, bare, _norm(re.sub(r"\([^)]*\)", " ", name)), _norm(alias)} - {""}
        covered = any(f in text for f in forms) or (
            vend and per_vendor.get(vend) == 1 and vend in text)
        if not covered:
            out.append(("platform.recommendations", f"CG-COMPLETE platform.recommendations: "
                        f"'{p.get('platform')}' is in the client's estate "
                        f"({p.get('in_estate')}) and no recommendation addresses optimizing "
                        f"it. The client's own estate is the first opportunity."))
    return out


def estate_plan(page: str, sec, shortlist) -> dict | None:
    """The deterministic plan a page lane is handed (the brief carries it, so
    it reaches a lane whatever plugin version the lane loaded): which
    platforms are cards and tiles, which are discards and why, which tiles
    must say 'verify', which owned vendors need an optimization
    recommendation. Computed from the shortlist and the platform cards; the
    checks above refuse anything else."""
    if not isinstance(shortlist, dict) or shortlist.get("error"):
        return None
    want = int(shortlist.get("tiles_wanted") or 0)
    owned = shortlist.get("in_estate") or []
    repl = shortlist.get("replaces") or []
    discards = ([{"platform": p.get("platform"),
                  "reason": f"Already in the client's estate ({p.get('in_estate')}): an "
                            f"optimization conversation, not a new platform."} for p in owned]
                + [{"platform": p.get("platform"),
                    "reason": f"Would replace {', '.join(p.get('replaces_in_estate') or [])}, "
                              f"which the client runs: a replacement, not an opportunity in "
                              f"what it owns."} for p in repl])
    verify = [p.get("platform") for p in shortlist.get("shortlist") or []
              if p.get("vendor_in_estate")]
    if page == "platform":
        return {"cards_required": [p.get("platform") for p in
                                   (shortlist.get("shortlist") or [])[:want]],
                "cards_forbidden": discards,
                "optimization_required": {
                    "vendors": shortlist.get("estate_vendors") or [],
                    "platforms": [p.get("platform") for p in owned]},
                "verify_on_owned_org": verify,
                "rule": ("rank cards only for cards_required (and other non-forbidden READY "
                         "platforms); a cards_forbidden platform is never a card — the owned "
                         "ones each get an OPTIMIZATION recommendation, and every vendor in "
                         "optimization_required.vendors has a recommendation whose TITLE names "
                         "it with an optimization verb (optimize, health check, reuse, "
                         "adoption, rationalize, consolidate, verify) — e.g. 'Salesforce org "
                         "health check and FSC entitlement verification', 'Reuse the MuleSoft "
                         "integration the club already licenses'")}
    if page == "overview":
        story = sec("platform.platform_story") if sec else None
        bar = {_norm(d["platform"]) for d in discards}
        cards = [c for c in ranked_cards(story) if _norm(c.get("platform")) not in bar][:want]
        return {"tiles": [{"platform": c.get("platform"), "rank": c.get("rank"),
                           "composite": c.get("fit_score"), "subtotal": c.get("subtotal"),
                           "readiness_multiplier": c.get("readiness_multiplier"),
                           "factors": c.get("factors"),
                           "must_say_verify": c.get("platform") in verify}
                          for c in cards] if story else None,
                "discarded_required": discards,
                "rule": ("serve exactly `tiles`, in this order, with these figures (they are "
                         "the platform cards'); write rank prose from them; a tile with "
                         "must_say_verify says in their_stack_context to VERIFY its rollout and "
                         "entitlement on the org the client already owns; list every "
                         "discarded_required platform in discarded[] with its reason")}
    return None
