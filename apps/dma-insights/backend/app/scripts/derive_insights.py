"""Re-derive score-grounded narrative surfaces (D2 insight cards +
D1 SCQA) for runs already persisted in the DB.

Why this exists
---------------
Insight cards are normally produced AT INGEST by the deterministic
ladder in ``parsers/dma_package.py``. Any corpus seeded BEFORE that
ladder landed has ``insight_cards`` = 0 and D2 renders empty. This
script re-runs the SAME ladder against the data already in Postgres —
the builders are shared functions in ``parsers/section_analysis.py`` so
the two paths cannot drift (plan Part 5.1).

The 2026-07-02 rebuild (plan Part 5.1) replaced the old two-rung
ladder (recs → gaps; audit: 74.6% of 630 cards were category-gap
restatements, report-sourced 3.6%, 0-evidence 29.5%) with:

  1. **client_profile_findings** — the Client Profile Research Report's
     Key Findings / Strategic Priorities / Digital Evolution /
     Technology Landscape rows, re-mined from the persisted
     ``focus_areas`` quotes (verbatim, page-anchored, E-ID-cited).
  2. **section_analysis top_findings** — re-mined from the compressed
     ``raw_artifacts`` store (the same JSONs ingest parsed).
  3. **recommendations-derived** — kept; they carry the report's own
     root-cause text.
  4. **category-gaps** — LAST RESORT, capped 4/client, rotating
     non-template prose.
  Plus generated OPPORTUNITY cards: ``client_knowledge_sections``
  zennify_opportunity rows (fully evidenced via trigger_evidence
  E-IDs) and the hiring-signal x platform-absence x strategic-quote
  cross-signal pattern — each emitted only when fully evidenced.

Every card is then ENRICHED (also for pre-existing cards whose
``affects`` is NULL): multi-``affects[]`` via the subcap classifier
(similarity vs ccg_subcaps names + keyword anchors), ``platforms[]``
(card subcaps → platform families via ``subcap_scores.platform_tags``),
``interconnections`` JSONB (counter-evidence / related recs /
tech-stack absences / sibling cards / basis marker), ``theme``, and the
evidence ladder (inline citations → subcap evidence → category roll-up
→ explicit ``basis`` chip) that kills the 29.5% zero-evidence class.

Honest by construction: every field is computed from EXTRACTED report
text or scores; nothing is fabricated and no LLM is involved
(tier = DERIVED).

Idempotent: runs with existing cards are skipped (``--force`` deletes
and re-derives); skipped runs still get the interconnection enrichment
when their cards pre-date migration 046. Designed to run as a
post-deploy refresh step.

Usage:
  export DATABASE_URL=postgresql+asyncpg://...
  python -m app.scripts.derive_insights            # fill gaps only
  python -m app.scripts.derive_insights --force    # re-derive all
  python -m app.scripts.derive_insights --limit 5  # smoke test
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import sys
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Shared why-now composition helpers: the persist-floor backfill must emit the
# SAME full 14-field template shape as the deep miner (the legacy 5-key shape
# it used to write shipped off-template rows dated as far back as 2013 —
# audit 2026-07-06, pentegra-retirement-serv-0001).
from app.scripts.deepen_narrative import (
    _dedupe_plays,
    _ensure_deep_fields,
    _event_detail,
    _window_for,
    dedupe_why_now_by_containment,
    finalize_why_now,
)

# Same idempotent typography/flow cleaner the deep miner runs as its final step —
# the persist-floor cards/findings must ship it too so no producer re-grows the
# "..." clip / emoji / shout-label debris the 2026-07-06 deploy review measured.
from app.services.nlp.card_bridge import gold_cards_for_run
from app.services.nlp.composer import compose_findings, compose_why_now
from app.services.nlp.entity_knowledge import load_entity_state
from app.services.nlp.quality import proofread
from app.services.nlp.storyline import derive_thesis
from app.services.parsers.report_synthesis import build_derived_scqa
from app.services.parsers.section_analysis import (
    _PILLAR_SUBCAP_RE,
    LEGACY_COUNTER_NOTE,
    InsightCardRow,
    SubcapClassifier,
    attach_evidence_ladder,
    basis_marker,
    cards_from_section_analysis_payload,
    category_display_name,
    combine_insight_rungs,
    counter_evidence_ids,
    counter_evidence_note,
    insights_from_category_gaps,
    insights_from_profile_findings,
    insights_from_zennify_opportunities,
    offering_platform_family,
    profile_finding_from_quote,
    similarity_attach_evidence,
    strip_template_markers,
    theme_for_anchor,
)
from app.services.startup_enrich import capability_phrase, quote_span

_VALID_SEVERITY = {"critical", "high", "medium", "low"}

# Single source of truth for marker stripping lives next to the ingest
# builder so both paths present identically.
_clean_title = strip_template_markers

# Title finalizer (2026-07-09 deep-QA challenge): the card-persist point passed
# `title` RAW while what/why/so-what were proofread, so three AE-worthiness
# defects reached insights.json — a card titled with a bare "[E-021]" citation
# marker, a scaffolding "Capability dimension 30", or the title==body case where
# the "title" is just the first (mid-word-truncated) run of the WHAT. This
# normalizes every card's title at the single chokepoint: strip citation
# markers, and when the title is empty / scaffolding / merely a prefix of the
# body, craft a crisp headline off the WHAT via titlecraft.make_title (SVO core,
# word-boundary clip). Deterministic; no model.
# Match every bracketed E-ID citation form, including space/tag variants the
# corpus carries — "[E-021]", "[E-021:F1]", "[E-295 F3]", "[E-INT-0340]".
_EID_MARKER_RE = re.compile(r"\[E-[^\]]*\]")
_SCAFFOLD_TITLE_RE = re.compile(
    r"^(capability dimension|dimension|finding|top finding|insight|subcapability"
    # bare profile section labels ('Priority 2') are document scaffolding,
    # not verbed headlines (2026-07-13 sample vetting: a card shipped
    # titled literally 'Priority 2')
    r"|priority|objective|theme|section)"
    r"\s*\d*$", re.I)
# 'Priority 5 — Inorganic Growth via Merger Integration' carries a real
# headline after the label — strip the numbering prefix, keep the content.
_SCAFFOLD_PREFIX_RE = re.compile(
    r"^(?:priority|objective|theme|finding|section)\s*\d*\s*[—–:-]\s*", re.I)  # noqa: RUF001


# Citation support gate (2026-07-09 deep-QA challenge): the cross-encoder
# support check lived only in EntityKnowledge.challenge() — which just the gold
# composer calls. The deterministic ladder rungs (rec cards, cross-signal,
# section_analysis) set linked_e_ids DIRECTLY, so ~7% of persisted citations
# were topical-but-unsupported (a privacy notice, a DEF14A boilerplate, a peer's
# figure, a bare .pptx filename). This gate runs at the SINGLE persist point so
# every producer's citations are cross-encoder-verified against the WHAT.
_CITE_MIN_SUPPORT = 0.30
# Pillar → plain-language domain, for framing a card's SO-WHAT implication on the
# business area (not the raw P# code). Mirrors entity_knowledge._PILLAR_LABEL.
_PILLAR_DOMAIN = {
    "P1": "strategy & governance", "P2": "customer experience",
    "P3": "operations & process", "P4": "data & technology",
}


def _gate_citations(idx, cap: str, e_ids: list[str], ev_excerpts: dict) -> list[str]:
    """Drop citations whose evidence does not SUPPORT the WHAT (cross-encoder
    verified via rerank.support_scores, batched + budget-guarded). Citations we
    have no excerpt text to judge are KEPT (never drop blind). When the re-rank
    tier is absent/budget-spent this reduces to the raw bi-encoder cosine — the
    same 0.30 floor as before, so it never drops MORE than the old path."""
    from app.services.nlp import rerank as _rr

    have = [(eid, ev_excerpts[eid]) for eid in e_ids if ev_excerpts.get(eid)]
    if not have:
        return e_ids
    items = [(tx, idx.relevance(cap, tx)) for _eid, tx in have]
    sups = _rr.support_scores(cap, items)
    verified = {
        eid for (eid, _tx), s in zip(have, sups, strict=True)
        if s >= _CITE_MIN_SUPPORT
    }
    judged = {eid for eid, _tx in have}
    # keep verified citations + any we couldn't judge (missing excerpt text)
    return [eid for eid in e_ids if eid in verified or eid not in judged]


def _finalize_card_title(title: str, what_text: str) -> str:
    from app.services.nlp.titlecraft import make_title
    from app.services.startup_enrich import _declip_headline, finalize_title_text
    t = _EID_MARKER_RE.sub("", _clean_title(title or "") or "").strip(" —-·|").strip()
    t = _SCAFFOLD_PREFIX_RE.sub("", t).strip()
    what = _EID_MARKER_RE.sub("", what_text or "").strip()
    t = finalize_title_text(t, what)
    # W7 (2026-07-14): an evidence-derived title ingest-truncated at a
    # connective ("… systems, was the", "… from peak to") reads mid-thought
    # and the S16 headline gate rejects it — strip the dangling tail.
    t = _declip_headline(t) or t
    # 2026-07-15: full S16-inverse — also drop a trailing quoted score
    # ("… scores 1.56/5", "at 2.62/5") and any stacked dangling connective.
    from app.services.startup_enrich import _headline_safe
    t = _headline_safe(t) or t
    # A sentiment-derived title that LEADS with a score recital ("Culture
    # score 3.4/5 — the X opportunity", "Overall rating 2.4/5 (140+ reviews)
    # — the Y opportunity") puts the number where the capability belongs —
    # drop the score lead, keep the opportunity clause, recase the head.
    _lead = re.sub(r"^[^—]*?\b\d(?:\.\d)?\s*/\s*5\b[^—]*?—\s*", "", t)
    if _lead and _lead != t and len(_lead) >= 12:
        t = _lead[0].upper() + _lead[1:]
    # An inline parenthetical rating ("VFP's Indeed rating (5.0/5.0) is based
    # on only 2 reviews") drops the raw fraction from the headline — the
    # insight (small sample) survives, the score belongs in the stat chip.
    _np = re.sub(r"\s*\(\s*\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?\s*\)", "", t)
    if _np and len(_np) >= 12:
        t = re.sub(r"\s{2,}", " ", _np).strip()
    # empty or scaffolding → craft off the body (declipped: make_title clips
    # at a word boundary and can still land on a connective — W7)
    if not t or _SCAFFOLD_TITLE_RE.match(t):
        return (_declip_headline(make_title(what, max_chars=90))
                or t or "Capability signal")[:500]
    # title==body: the "title" is just the leading run of the WHAT (often cut
    # mid-word) — replace with a crafted headline when that yields something
    # cleaner/different.
    if len(t) > 30:
        tn = t.rstrip("… .").lower()
        wn = what[: len(t) + 2].rstrip("… .").lower()
        if wn.startswith(tn) or tn.startswith(what[: len(tn)].lower()):
            crafted = _declip_headline(make_title(what, max_chars=90))
            if crafted and crafted.rstrip("… .").lower() != tn:
                return crafted[:500]
    return t[:500]

# Hiring-signal detector for the cross-signal OPPORTUNITY generator.
# STRONG cues only, and only over the EXCERPT — a careers-page benefits
# paragraph ("job shadowing, mentoring…") is not a hiring signal even
# though its source is a careers page (2026-07-02 rubric audit: two XS
# cards quoted benefits prose as "investment intent").
_HIRING_RE = re.compile(
    r"job\s+post|open\s+(?:role|position)|is\s+hiring|hiring\s+(?:for|of|a\b)|"
    r"recruit(?:ing|ment)\s+for|job\s+(?:listing|description|opening)|"
    r"seeks?\s+(?:a|an|to\s+hire)|posted\s+(?:a\s+)?(?:role|position|job)|"
    r"new\s+(?:role|position)s?\s+(?:posted|open)|"
    r"indeed\.com|linkedin\.com/jobs|glassdoor\.com/job",
    re.IGNORECASE,
)


# Evidence-ladder rungs 2+3 (subcap-linked → category roll-up) live in
# the shared module so ingest and re-derive ground identically.
_attach_evidence = attach_evidence_ladder


@dataclass
class _CategoryScore:
    """Duck-typed shape `insights_from_category_gaps` reads via getattr."""
    category_id: str
    category_name: str
    score: float
    peer_median: float | None = None


@dataclass
class _RunStats:
    by_rung: dict = field(default_factory=dict)
    skipped_existing: int = 0
    skipped_no_data: int = 0
    enriched_existing: int = 0
    runs_filled: list[str] = field(default_factory=list)
    scqa_filled: list[str] = field(default_factory=list)

    def bump(self, rung: str, n: int) -> None:
        if n:
            self.by_rung[rung] = self.by_rung.get(rung, 0) + n


def _severity_from_score(score: float | None) -> str:
    if score is None:
        return "medium"
    if score < 2.0:
        return "high"
    if score < 3.0:
        return "medium"
    return "low"


def _anchor_display(anchor: str,
                    subcap_names: dict[str, str] | None) -> str:
    """AE-facing name for the anchored capability — never a raw P#C# code
    (internal-jargon rule) and never an artifact/document title occupying
    the capability slot (`capability_phrase`, 2026-07-06). Falls back to
    the category display name, then to honest generic prose."""
    name = capability_phrase((subcap_names or {}).get(anchor))
    if name:
        return name
    cat = category_display_name(anchor)
    # category_display_name echoes the raw id when unknown — that echo is
    # exactly the jargon this helper exists to keep out of prose.
    if cat and cat != (anchor or "") and not re.search(r"P[1-4]C\d", cat, re.I):
        return f"The {cat} capability this recommendation anchors on"
    return "The capability this recommendation anchors on"


# LOB-family leaf suffixes (Insurance Carrier IC / Brokerage IB / Credit Union
# CU / Retail Bank RB / Wealth Mgmt WM / Commercial Bank CB / Private Bank PB).
# A rec whose only anchor is a LOB leaf mis-attributes evidence: the leaf is a
# NO_EVIDENCE placeholder while the real evidence sits on the numeric siblings
# under the same subcategory (P2C3.2.1..8). See plan S5.
_LOB_LEAF_RE = re.compile(r"\.(?:IC|IB|CU|RB|WM|CB|PB)\d*$")


def _applicable_anchor(targets: list[str], sub_scores: dict[str, float]) -> str:
    """Pick the evidence-resolvable anchor for a rec's target subcaps (plan S5).

    Preference: a scored, non-LOB-family leaf → any non-LOB leaf → the parent
    SUBCATEGORY of the first LOB leaf (so the sibling-aware evidence matcher can
    reach the numeric siblings that actually carry evidence). Guarantees a card
    never anchors on a bare NO_EVIDENCE LOB placeholder leaf."""
    scored_non_lob = [t for t in targets
                      if t in sub_scores and not _LOB_LEAF_RE.search(t)]
    if scored_non_lob:
        return scored_non_lob[0]
    non_lob = [t for t in targets if not _LOB_LEAF_RE.search(t)]
    if non_lob:
        return non_lob[0]
    first = targets[0]
    return first.rsplit(".", 1)[0] if _LOB_LEAF_RE.search(first) else first


def _expand_what(
    what: str,
    *,
    cap_name: str,
    score: float | None,
    pm: float | None,
    cited: list[tuple[str, str]],
) -> str:
    """A WHAT must read as a paragraph (>=3 sentences, C1) — a one-line rec
    description gets grounded context appended: the verbatim first sentence
    of a cited excerpt, then the capability's run standing. Verbatim quotes
    and run-computed figures only — nothing is invented."""
    from app.services.nlp.segment import sentences as _sents
    out = (what or "").strip()
    if not out:
        return out
    if not out.endswith((".", "!", "?")):
        out += "."
    need = 3 - len(_sents(out))
    if need <= 0:
        return out
    from app.services.startup_enrich import _excerpt_relevant, clip_clean
    for e_id, excerpt in cited:
        first = next(iter(_sents(excerpt or "")), "").strip()
        # the woven quote must be ABOUT this capability (a CMO-hire /
        # balloon-tour line shipped as the evidence for website quality,
        # 2026-07-13 corpus QA) and must never cut mid-word ("at Pla")
        if len(first) >= 40 and _excerpt_relevant(first[:300], cap_name):
            _q = clip_clean(first, 220).rstrip(".")
            if len(_q) >= 40:
                out += f' The evidence on file records: "{_q}." ({e_id}).'
                need -= 1
                break
    if need > 0 and score is not None and pm is not None:
        out += (f" On the current run {cap_name} stands at {score:.1f}/5 "
                f"with the peer group at {pm:.1f}.")
    elif need > 0 and score is not None:
        out += (f" On the current run {cap_name} stands at {score:.1f}/5, "
                f"and this is the move the report sequences first.")
    return out


def _cards_from_db_recommendations(
    recs: list,
    sub_scores: dict[str, float],
    peer_medians: dict[str, float] | None = None,
    subcap_names: dict[str, str] | None = None,
    cat_names: dict[str, str] | None = None,
    ev_excerpts: dict[str, tuple[str, str]] | None = None,
) -> list[InsightCardRow]:
    """DERIVE cards from persisted `recommendations` rows.

    DB rows differ from the parser model (no root_cause/solution JSON —
    those live only in the package files), so this is the DB-faithful
    mapping: WHAT = the rec's own description (report text), WHY = the
    anchored subcap's real score standing vs its peer median, SO-WHAT =
    the report's proposed move + platform when named. Anchor = the first
    target subcap (NOT NULL contract); recs without any anchor are
    skipped, same rule as ingest. The WHY names the capability in plain
    language (`_anchor_display`) — a raw subcap code in AE-facing prose
    is internal jargon (2026-07-06).
    """
    peer_medians = peer_medians or {}
    subcap_names = subcap_names or {}
    cat_names = cat_names or {}
    out: list[InsightCardRow] = []
    seen: set[str] = set()
    for r in recs:
        targets = list(r.target_subcap_ids or [])
        if not targets:
            m = _PILLAR_SUBCAP_RE.search(f"{r.title or ''} {r.description or ''}")
            if m is None:
                continue
            targets = [m.group(0)]
        anchor = _applicable_anchor(targets, sub_scores)[:32]
        ic_id = f"INS-{r.rec_id}"[:16]
        if ic_id in seen:
            continue
        seen.add(ic_id)
        score = sub_scores.get(anchor)
        pm = peer_medians.get(anchor)
        # Plain-language capability NAME for the WHY — never the raw taxonomy
        # code (plan S1) and never an artifact/document title occupying the
        # capability slot (`capability_phrase`, 2026-07-06). Falls back
        # through the anchor's subcap/category name, then any named target,
        # then `_anchor_display`'s honest category/generic phrasing.
        cap_name = (capability_phrase(subcap_names.get(anchor))
                    or capability_phrase(cat_names.get(anchor))
                    or next((n for t in targets
                             if (n := capability_phrase(subcap_names.get(t)))),
                            None)
                    or _anchor_display(anchor, subcap_names))
        if score is not None and pm is not None:
            spread = pm - score
            if spread > 0:
                why = (f"{cap_name} runs at {score:.1f}/5 on this run while the "
                       f"peer group sits at {pm:.1f} — a {spread:.1f}-point "
                       f"spread this move is built to close.")
            else:
                why = (f"{cap_name} runs at {score:.1f}/5 on this run, at or "
                       f"ahead of the {pm:.1f} peer group — the base this move "
                       f"builds on.")
        elif score is not None:
            why = (f"{cap_name} runs at {score:.1f}/5 on this run, with "
                   f"headroom toward the peer benchmark.")
        else:
            why = (f"{cap_name} is a priority capability this assessment "
                   f"flagged for near-term investment.")
        title = _clean_title(r.title)
        if not title:
            # No rec title in the corpus row — compress the description
            # (nlp.titlecraft SVO core) instead of shipping "(untitled)".
            from app.services.nlp.titlecraft import make_title
            title = (make_title(_clean_title(r.description), max_chars=90)
                     or "(untitled)")
        # SO-WHAT is the IMPLICATION, not a restatement of the title: what acting
        # closes, framed on the pillar DOMAIN + the peer-gap it moves. Setting
        # `so_what = title` (the prior behaviour) made ~340 rec cards summaries,
        # not insights (2026-07-09 QA). The move itself is already the WHAT/title.
        domain = _PILLAR_DOMAIN.get((anchor or "")[:2], "this capability area")
        plat = None
        if r.platform_id:
            plat = str(r.platform_id).replace("-", " ").replace("_", " ").strip()
            plat = plat if plat[:1].isupper() else plat.title()
        if score is not None and pm is not None and score < pm:
            gap_pts = pm - score
            so_what = (f"Closes the {gap_pts:.1f}-point gap to the {pm:.1f} peer "
                       f"benchmark on {domain}")
            so_what += (f", with {plat} as the delivery vehicle" if plat
                        else ", moving the capability toward peer parity")
        elif plat:
            so_what = (f"Strengthens {domain} against the peer benchmark, with "
                       f"{plat} as the delivery vehicle")
        else:
            so_what = (f"A near-term priority to move {domain} toward peer parity "
                       f"this assessment flagged")
        # The rec's own root-cause citations are the card's faithful
        # evidence (D4 ingested the rec corpus; 370/649 recs carry them).
        root_e_ids = [
            str(e)[:16] for e in (getattr(r, "root_cause_e_ids", None) or [])
            if isinstance(e, str) and e.startswith("E-")
        ]
        # Sentence-boundary clip: a 4,000-char description is a report
        # dump, not a card — the full rec text lives in the D4 modal.
        from app.services.nlp.segment import clip_sentences
        what = _clean_title(r.description) or title
        if len(what) > 900:
            what = clip_sentences(what, 900)
        cited = [
            (e, (ev_excerpts or {}).get(e, ("", ""))[0])
            for e in root_e_ids[:3]
        ]
        what = _expand_what(what, cap_name=cap_name, score=score, pm=pm,
                            cited=[(e, x) for e, x in cited if x])
        out.append(InsightCardRow(
            ic_id=ic_id,
            severity=_severity_from_score(score),
            title=title[:500],
            # persist proofread'd bodies (no markdown **, no spliced clip
            # artifacts) — the export serves the stored value directly, so
            # cleaning only on read left "(2) **'Lending" on the pack
            what_text=(proofread(what) or what)[:4000],
            why_text=(proofread(why) or why),
            so_what_text=(proofread(f"{so_what}.") or f"{so_what}.")[:4000],
            linked_subcap_id=anchor,
            linked_e_ids=root_e_ids[:20],
            source_rec_id=str(r.rec_id)[:16] if r.rec_id else None,
        ))
    return out


def _cross_signal_opportunity_cards(
    *,
    evidence_rows: list[dict],
    absent_families: list[tuple[str, str]],
    strategic_quotes: list[dict],
    family_leafs: dict[str, str],
    sub_scores: dict[str, float],
) -> list[InsightCardRow]:
    """Generated cross-signal OPPORTUNITY card (plan 5.1): hiring signal
    + confirmed platform absence + strategic quote ⇒ one card, fully
    evidenced (hiring E-ID + strategic grounding) or not emitted."""
    hiring = [
        row for row in evidence_rows
        if _HIRING_RE.search(row.get("excerpt") or "")
        and row.get("e_id")
    ]
    if not (hiring and absent_families and strategic_quotes):
        return []
    hiring.sort(key=lambda r: int(r.get("tier") or 9))
    # Verbatim-quote mandate (2026-07-06): the card quotes the excerpt as
    # the researcher wrote it — truncated only at a claim boundary with an
    # ellipsis (`quote_span`). Rows with no claim-safe span are skipped in
    # tier order rather than misquoted.
    hit, excerpt = None, ""
    for row in hiring:
        excerpt = quote_span(row.get("excerpt") or "", 260)
        if excerpt:
            hit = row
            break
    if hit is None:
        return []
    # The absent family that addresses the run's scored subcaps
    # (family_leafs only contains families with platform-tagged subcaps).
    fam = next(
        ((fid, name) for fid, name in absent_families if fid in family_leafs),
        None,
    )
    if fam is None:
        return []
    fam_id, fam_name = fam
    anchor = family_leafs[fam_id]
    quote_row, quote = None, ""
    for qr in strategic_quotes:               # first claim-safe-quotable quote
        quote = quote_span(qr.get("quote") or "", 220)
        if quote:
            quote_row = qr
            break
    if quote_row is None:
        return []
    score = sub_scores.get(anchor)
    what = (
        f"Hiring signals show investment intent while no {fam_name} platform "
        f"is detected in the stack. "
        f'The research recorded: "{excerpt}" [{hit["e_id"]}].'
    )
    why = (
        f'The client\'s own stated priority — "{quote}" — needs the '
        f"{fam_name} capability that is currently absent."
        # never the raw subcap code as subject — the S1 scrub strips codes,
        # which orphaned this sentence ("… opportunity. scores 1.5/5 …")
        + (f" The capability it maps to scores {score:.1f}/5 on the "
           f"current assessment."
           if score is not None else "")
    )
    so_what = (
        f"Recommended play: open the {fam_name} conversation now — the "
        f"talent build shows budget and intent before a platform has been "
        f"chosen."
    )
    e_ids = [str(hit["e_id"])]
    for extra in quote_row.get("e_ids") or []:
        if extra not in e_ids:
            e_ids.append(str(extra))
    return [InsightCardRow(
        ic_id=f"XS-{fam_id[:10].upper()}"[:16],
        severity="high",
        title=f"Hiring signals ahead of a {fam_name} foundation"[:500],
        what_text=(proofread(what) or what)[:4000],
        why_text=(proofread(why) or why)[:4000],
        so_what_text=(proofread(so_what) or so_what)[:4000],
        linked_subcap_id=anchor[:32],
        linked_e_ids=[e[:16] for e in e_ids][:20],
    )]


def _enrich_card(
    card_text: dict,
    *,
    classifier: SubcapClassifier,
    platform_tags: dict[str, list[str]],
    evidence_rows: list[dict],
    rec_targets: list[tuple[str, list[str]]],
    absent_families: list[tuple[str, str]],
    sibling_eids: dict[str, set[str]],
    valid_subcaps: set[str] | None = None,
) -> dict:
    """Interconnection enrichment for ONE card → the migration-046
    columns {affects, platforms, interconnections, theme}.

    ``card_text``: {ic_id, title, what, why, anchor, e_ids, severity,
    source_rec_id}. Pure — all inputs preloaded per run."""
    anchor = card_text["anchor"]
    blob = f"{card_text['title']}. {card_text['what']} {card_text['why']}"
    affects = classifier.affects_for(blob, anchor=anchor, k=5)
    if valid_subcaps:
        # ASK-IC1-4 / QA-IC-03: an Affects chip must route to a scored cell
        # of THIS run — the classifier's catalogue-wide proposals outside
        # the run's subcap set are unroutable drilldowns.
        affects = [s for s in affects if s in valid_subcaps]

    platforms: list[str] = []
    for sid in affects:
        for tag in platform_tags.get(sid, []):
            if tag and tag not in platforms:
                platforms.append(tag)
    fam = offering_platform_family(blob) if not platforms else None
    if fam and fam not in platforms:
        platforms.append(fam)

    interconnections: list[dict] = []
    counters = counter_evidence_ids(
        anchor, card_text["severity"], card_text["e_ids"], evidence_rows,
    )
    if counters:
        # The "But also…" section must ANALYZE what the opposing evidence
        # shows — verbatim-quoted where load-bearing, E-ID-attributed —
        # not render a stub label over bare chips (2026-07-06 mandate).
        row_by_eid = {str(r.get("e_id")): r for r in evidence_rows or []}
        note = counter_evidence_note(
            [row_by_eid.get(e, {"e_id": e}) for e in counters],
            card_text["severity"],
        ) or LEGACY_COUNTER_NOTE
        interconnections.append({
            "kind": "counter_evidence", "target_id": anchor,
            "note": note,
            "e_ids": counters,
        })
    related = [
        rec_id for rec_id, subs in rec_targets
        if any(s == anchor or s.startswith(anchor + ".")
               or anchor.startswith(s + ".") for s in subs)
    ]
    for rec_id in related[:3]:
        if rec_id != card_text.get("source_rec_id"):
            interconnections.append({
                "kind": "related_rec", "target_id": rec_id,
                "note": "recommendation targeting the same capability",
                "e_ids": [],
            })
    for fid, fname in absent_families:
        if fid in platforms:
            interconnections.append({
                "kind": "tech_absence", "target_id": fid,
                "note": f"no {fname} platform detected in the stack",
                "e_ids": [],
            })
    own = set(card_text["e_ids"])
    if own:
        for other_ic, other_eids in sibling_eids.items():
            if other_ic == card_text["ic_id"]:
                continue
            if own & other_eids:
                interconnections.append({
                    "kind": "sibling_card", "target_id": other_ic,
                    "note": "shares supporting evidence",
                    "e_ids": sorted(own & other_eids)[:4],
                })
                if sum(1 for i in interconnections
                       if i["kind"] == "sibling_card") >= 3:
                    break
    if not card_text["e_ids"]:
        # Evidence ladder, final rung: the card must state its basis.
        interconnections.append(basis_marker())
    else:
        # Thin-evidence honesty (the heatmap THIN pattern): grounding
        # density scales with claim count — a long card the run's
        # evidence could not support says so on the card itself.
        from app.services.nlp.segment import sentences as _sents
        n_claims = len(_sents(
            f"{card_text['title']}. {card_text['what']} "
            f"{card_text['why']} {card_text.get('so_what') or ''}")) + 1
        needed = min(6, max(2, (n_claims + 3) // 4))
        if len(card_text["e_ids"]) < needed:
            interconnections.append(
                basis_marker("thin evidence — scores + peer benchmark"))

    # Citation-validity floor (2026-07-11 parity audit; mirrors
    # section_routing + apply_startup_data_fixes): sibling/counter e_ids
    # inherit prose-parsed card citations, which can dangle (no
    # evidence_index row → dead drawer chip; the pack fixer prunes them, so
    # the DB row must not carry them either or qa_pack_parity diffs pack vs
    # live). Empty evidence set disables the filter — the fixer's guard.
    known_eids = {str(r.get("e_id")) for r in (evidence_rows or [])
                  if isinstance(r, dict) and r.get("e_id")}
    if known_eids:
        for ic in interconnections:
            if ic.get("e_ids"):
                ic["e_ids"] = [e for e in ic["e_ids"] if e in known_eids]

    return {
        "affects": affects,
        "platforms": platforms,
        "interconnections": interconnections,
        "theme": theme_for_anchor(anchor),
    }


async def _insert_cards(
    session, run_id, entity_id,
    cards: list[InsightCardRow],
    enrichment: dict[str, dict] | None = None,
    ev_excerpts: dict[str, str] | None = None,
) -> int:
    inserted = 0
    enrichment = enrichment or {}
    # Build the run's evidence index ONCE for the citation support gate (below);
    # per-card relevance() reuses the cached embeddings, so the gate is bounded.
    _gate_idx = None
    if ev_excerpts:
        from app.services.nlp.semantic import SemanticIndex
        _gate_idx = SemanticIndex()
        _gate_idx.fit([(eid, tx) for eid, tx in ev_excerpts.items() if tx])
    for c in cards:
        sev = (c.severity or "").lower()
        if sev not in _VALID_SEVERITY or not c.linked_subcap_id:
            continue
        # Belt (plan S5): roll ANY LOB-family leaf anchor up to its parent
        # subcategory before persisting, so no card — from any composer
        # (rec/profile/cross-signal/gap) — anchors on a NO_EVIDENCE placeholder
        # leaf whose evidence actually sits on its numeric siblings.
        sub = c.linked_subcap_id
        if _LOB_LEAF_RE.search(sub):
            sub = sub.rsplit(".", 1)[0]
        extra = enrichment.get(c.ic_id, {})
        # Universal citation support gate: drop cited E-IDs whose evidence does
        # not support this card's WHAT (cross-encoder verified) — regardless of
        # which producer set them. Blind (no-excerpt) citations are kept.
        e_ids = list(c.linked_e_ids or [])
        if _gate_idx is not None and e_ids:
            e_ids = _gate_citations(
                _gate_idx, c.what_text or c.title or "", e_ids, ev_excerpts or {})
        await session.execute(
            text(
                """
                INSERT INTO insight_cards (
                    run_id, entity_id, ic_id, severity, title,
                    what_text, why_text, so_what_text, linked_subcap_id,
                    linked_e_ids, source_rec_id,
                    affects, platforms, interconnections, theme
                ) VALUES (
                    :rid, :eid, :ic, :sev, :t, :what, :why, :sw, :sub,
                    CAST(:eids AS varchar[]), :src,
                    CAST(:aff AS text[]), CAST(:plat AS text[]),
                    CAST(:inter AS jsonb), :theme
                )
                ON CONFLICT (run_id, ic_id) DO NOTHING
                """
            ),
            {
                "rid": run_id, "eid": entity_id,
                "ic": c.ic_id[:16], "sev": sev,
                "t": _finalize_card_title(c.title, c.what_text),
                # 2026-07-06 deploy review — narr.punct_debris (defensive): the
                # single card-persist point, so every card source (rec cards,
                # cross-signal, section_analysis) ships proofread'd what/why/so_what
                # — no excerpt-spliced "..." / emoji reaches insights.json.
                "what": proofread(c.what_text or "") or (c.what_text or ""),
                "why": proofread(c.why_text or "") or (c.why_text or ""),
                "sw": proofread(c.so_what_text or "") or (c.so_what_text or ""),
                "sub": sub[:32],
                "eids": e_ids,
                "src": (getattr(c, "source_rec_id", None) or None),
                "aff": extra.get("affects") or [sub],
                "plat": extra.get("platforms") or [],
                "inter": json.dumps(extra.get("interconnections") or []),
                "theme": (extra.get("theme") or None),
            },
        )
        inserted += 1
    return inserted


async def _load_run_context(session, run) -> dict:
    """All per-run inputs the ladder + enrichment need."""
    srows = (
        await session.execute(text(
            "SELECT subcap_id, score, peer_median, platform_tags "
            "FROM subcap_scores WHERE run_id = :rid"), {"rid": run.run_id})
    ).all()
    sub_scores = {r.subcap_id: float(r.score) for r in srows
                  if r.score is not None}
    peer_medians = {r.subcap_id: float(r.peer_median) for r in srows
                    if r.peer_median is not None}
    platform_tags = {r.subcap_id: list(r.platform_tags or []) for r in srows
                     if r.platform_tags}

    erows = (
        await session.execute(text(
            "SELECT e_id, tier, claim_type, excerpt, source_name, "
            "linked_subcap_ids FROM evidence_index WHERE run_id = :rid "
            "ORDER BY tier ASC NULLS LAST"), {"rid": run.run_id})
    ).all()
    evidence_rows = [
        {"e_id": r.e_id, "tier": r.tier, "claim_type": r.claim_type,
         "excerpt": r.excerpt, "source_name": r.source_name,
         "subcap_ids": list(r.linked_subcap_ids or [])}
        for r in erows
    ]

    farows = (
        await session.execute(text(
            """
            SELECT title, verbatim_quote, source_path, page_number,
                   involved_subcap_ids
            FROM focus_areas WHERE run_id = :rid
            ORDER BY created_at, id
            """), {"rid": run.run_id})
    ).all()

    knows = (
        await session.execute(text(
            "SELECT provenance FROM client_knowledge_sections "
            "WHERE run_id = :rid AND artifact_kind = 'zennify_opportunity' "
            "ORDER BY id"), {"rid": run.run_id})
    ).all()

    raws = (
        await session.execute(text(
            r"SELECT rel_path, content, codec FROM raw_artifacts "
            r"WHERE entity_id = :eid "
            r"AND rel_path ~* 'section_analysis_\d+\.json$' "
            r"ORDER BY rel_path"), {"eid": run.entity_id})
    ).all()

    trows = (
        await session.execute(text(
            "SELECT vendor, product FROM tech_stack_entries "
            "WHERE entity_id = :eid"), {"eid": run.entity_id})
    ).all()

    recs = (
        await session.execute(text(
            "SELECT rec_id, title, description, target_subcap_ids, "
            "platform_id, root_cause_e_ids "
            "FROM recommendations WHERE run_id = :rid "
            "ORDER BY rec_id"), {"rid": run.run_id})
    ).all()

    return {
        "sub_scores": sub_scores,
        "peer_medians": peer_medians,
        "platform_tags": platform_tags,
        "evidence_rows": evidence_rows,
        "focus_rows": farows,
        "zennify_rows": [
            r.provenance if isinstance(r.provenance, dict)
            else json.loads(r.provenance)
            for r in knows if r.provenance
        ],
        "raw_sections": raws,
        "tech_rows": trows,
        "recs": recs,
    }


def _family_leafs(platform_tags: dict[str, list[str]],
                  sub_scores: dict[str, float]) -> dict[str, str]:
    """Per platform family → the run's weakest subcap carrying its tag."""
    best: dict[str, tuple[float, str]] = {}
    for sid, tags in platform_tags.items():
        score = sub_scores.get(sid)
        if score is None:
            continue
        for tag in tags:
            cur = best.get(tag)
            if cur is None or score < cur[0]:
                best[tag] = (score, sid)
    return {tag: sid for tag, (_s, sid) in best.items()}


def _leaf_resolver(sub_scores: dict[str, float]):
    """category id → its lowest-scoring leaf subcap in this run."""
    def resolve(cat: str) -> str | None:
        best: tuple[float, str] | None = None
        for sid, score in sub_scores.items():
            if sid.startswith(cat + ".") and (best is None or score < best[0]):
                best = (score, sid)
        return best[1] if best else None
    return resolve


def _absent_families(tech_rows: list) -> list[tuple[str, str]]:
    """Scored platform families with zero detected rows (honest: only
    when the entity HAS technographic rows at all — mirrors the
    techstack read-model rule)."""
    if not tech_rows:
        return []
    from app.services.parsers.tech_linker import SCORED_PLATFORM_FAMILIES
    hay = " · ".join(
        f"{r.vendor or ''} {r.product or ''}" for r in tech_rows)
    return [(fid, name) for fid, name, rx in SCORED_PLATFORM_FAMILIES
            if not rx.search(hay)]


def _profile_findings_from_focus_rows(focus_rows: list) -> list:
    """Persisted ``focus_areas`` quotes → normalized ProfileFinding rows.

    Synthesized rows (D3 focus-area synthesizer / Gemini) are excluded —
    only the Client Profile DOCX rows are report findings."""
    findings = []
    for r in focus_rows:
        sp = (r.source_path or "")
        if sp.startswith(("synthesized", "derived", "gemini", "heuristic")):
            continue
        kind = ("strategic_priority" if sp == "docx:strategic_section"
                else "key_findings")
        pf = profile_finding_from_quote(
            r.title, r.verbatim_quote, page=r.page_number, source_kind=kind,
        )
        if pf is None:
            continue
        if not pf.subcap_refs and r.involved_subcap_ids:
            pf.subcap_refs = list(r.involved_subcap_ids)
        findings.append(pf)
    return findings


def _section_cards_from_raw(raw_rows: list) -> list[InsightCardRow]:
    """Re-mine section_analysis JSONs out of the compressed raw store."""
    if not raw_rows:
        return []
    from app.services.raw_artifact_store import decompress_payload
    out: list[InsightCardRow] = []
    seen: set[str] = set()
    for fi, row in enumerate(raw_rows):
        try:
            payload = json.loads(
                decompress_payload(bytes(row.content), row.codec))
        except Exception:
            continue
        cards_from_section_analysis_payload(payload, fi, out, seen)
    return out


async def main_async(args: argparse.Namespace) -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2
    engine = create_async_engine(dsn, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    stats = _RunStats()

    async with maker() as session:
        # Anti-generic distinctiveness table (composer tie-breaker toward
        # client-specific prose) — same fit deepen_narrative runs; the
        # scorer is a no-op when unfitted.
        try:
            from app.services.nlp.distinctiveness import fit_corpus
            _corpus = (await session.execute(text(
                "SELECT excerpt FROM evidence_index "
                "WHERE length(COALESCE(excerpt,'')) >= 60"))).scalars().all()
            print(f"  distinctiveness: fitted {fit_corpus(_corpus)} excerpts",
                  flush=True)
        except Exception as _exc:
            print(f"::warning::distinctiveness fit skipped: {_exc}",
                  file=sys.stderr)
        cat_names = {
            r.category_id: r.name for r in (
                await session.execute(text(
                    "SELECT category_id, name FROM ccg_categories"))
            ).all()
            if r.name and r.name != r.category_id
        }
        # Catalogue subcap names → the similarity tier of the affects
        # classifier (placeholder "Subcap …" names are dropped inside).
        subcap_names = {
            r.subcap_id: r.name for r in (
                await session.execute(text(
                    "SELECT DISTINCT ON (subcap_id) subcap_id, name "
                    "FROM ccg_subcaps WHERE name IS NOT NULL "
                    "ORDER BY subcap_id"))
            ).all()
            if r.name
        }
        runs = (
            await session.execute(text(
                """
                SELECT r.id AS run_id, r.entity_id, e.display_id,
                       e.name AS entity_name, e.subvertical,
                       -- grounded cards only: ungrounded rows never render
                       -- (fail-closed serve filter), so a run whose cards
                       -- all lack evidence links still NEEDS the composer
                       -- (2026-07-12: 12 clients under the 5-card floor,
                       -- 3 at zero, after the grounding contract landed)
                       (SELECT count(*) FROM insight_cards ic
                         WHERE ic.run_id = r.id
                           AND COALESCE(array_length(ic.linked_e_ids,1),0) > 0
                       ) AS n_cards,
                       (SELECT count(*) FROM insight_cards ic
                         WHERE ic.run_id = r.id AND ic.affects IS NULL
                       ) AS n_unenriched,
                       (SELECT count(*) FROM document_sections ds
                         WHERE ds.run_id = r.id
                           AND ds.section_kind = 'executive_summary_scqa'
                           AND length(coalesce(ds.body, '')) > 0
                       ) AS n_scqa
                FROM runs r JOIN entities e ON e.id = r.entity_id
                WHERE r.status = 'ACTIVE'
                """
                + ("AND e.display_id = :ent " if getattr(args, "entity", None)
                   else "")
                + "ORDER BY e.display_id"
                + ("" if args.limit is None else " LIMIT :lim")),
                {**({} if args.limit is None else {"lim": args.limit}),
                 **({"ent": args.entity} if getattr(args, "entity", None)
                    else {})},
            )
        ).all()

        # The TF-IDF name index costs seconds to fit over ~4k catalogue
        # names — build it ONCE; each run swaps in its own
        # category→weakest-leaf resolver via `with_resolver`.
        base_classifier = SubcapClassifier(subcap_names)

        for run in runs:
            ctx = await _load_run_context(session, run)
            sub_scores = ctx["sub_scores"]
            classifier = base_classifier.with_resolver(
                _leaf_resolver(sub_scores))
            family_leafs = _family_leafs(ctx["platform_tags"], sub_scores)
            absent = _absent_families(ctx["tech_rows"])
            ev_excerpts = {
                row["e_id"]: (row["excerpt"] or "", row["source_name"] or "")
                for row in ctx["evidence_rows"]
            }
            rec_targets = [
                (r.rec_id, list(r.target_subcap_ids or []))
                for r in ctx["recs"]
            ]
            ev_by_subcap: dict[str, list[str]] = {}
            for row in ctx["evidence_rows"]:
                for sid in row["subcap_ids"]:
                    ev_by_subcap.setdefault(sid, []).append(row["e_id"])

            # Per-category rollup vs the subvertical's peer medians —
            # shared input for the gap rung AND the SCQA backfill.
            categories: list[_CategoryScore] = []
            if sub_scores:
                by_cat: dict[str, list[float]] = {}
                for sid, sc in sub_scores.items():
                    cat = sid.split(".")[0][:8]
                    by_cat.setdefault(cat, []).append(sc)
                peer = {
                    r.cat: float(r.med) for r in (
                        await session.execute(text(
                            """
                            SELECT split_part(subcap_id, '.', 1) AS cat,
                                   AVG(median) AS med
                            FROM peer_benchmarks
                            WHERE subvertical = :sv
                            GROUP BY split_part(subcap_id, '.', 1)
                            """), {"sv": run.subvertical or ""})
                    ).all()
                }
                categories = [
                    _CategoryScore(
                        category_id=cat,
                        category_name=cat_names.get(cat) or "",
                        score=round(sum(v) / len(v), 2),
                        peer_median=peer.get(cat),
                    )
                    for cat, v in sorted(by_cat.items())
                ]

            # ── Insight cards (Part 5.1 ladder) ─────────────────────
            if run.n_cards and not args.force:
                stats.skipped_existing += 1
                # Interconnection enrichment for pre-046 cards: fill
                # affects/platforms/interconnections/theme in place —
                # prose (possibly report-derived) is NEVER touched.
                if run.n_unenriched:
                    existing = (
                        await session.execute(text(
                            "SELECT ic_id, severity, title, what_text, "
                            "why_text, so_what_text, linked_subcap_id, "
                            "linked_e_ids, "
                            "source_rec_id FROM insight_cards "
                            "WHERE run_id = :rid AND affects IS NULL"),
                            {"rid": run.run_id})
                    ).all()
                    sibling = {r.ic_id: set(r.linked_e_ids or [])
                               for r in existing}
                    for r in existing:
                        extra = _enrich_card(
                            {"ic_id": r.ic_id, "title": r.title,
                             "what": r.what_text, "why": r.why_text,
                             "so_what": r.so_what_text,
                             "anchor": r.linked_subcap_id,
                             "e_ids": list(r.linked_e_ids or []),
                             "severity": r.severity,
                             "source_rec_id": r.source_rec_id},
                            classifier=classifier,
                            platform_tags=ctx["platform_tags"],
                            evidence_rows=ctx["evidence_rows"],
                            rec_targets=rec_targets,
                            valid_subcaps=set(sub_scores),
                            absent_families=absent,
                            sibling_eids=sibling,
                        )
                        await session.execute(text(
                            "UPDATE insight_cards SET "
                            "affects = CAST(:aff AS text[]), "
                            "platforms = CAST(:plat AS text[]), "
                            "interconnections = CAST(:inter AS jsonb), "
                            "theme = :theme "
                            "WHERE run_id = :rid AND ic_id = :ic"),
                            {"aff": extra["affects"],
                             "plat": extra["platforms"],
                             "inter": json.dumps(extra["interconnections"]),
                             "theme": extra["theme"],
                             "rid": run.run_id, "ic": r.ic_id})
                        stats.enriched_existing += 1
            else:
                if args.force:
                    await session.execute(
                        text("DELETE FROM insight_cards WHERE run_id = :rid"),
                        {"rid": run.run_id},
                    )
                profile_findings = _profile_findings_from_focus_rows(
                    ctx["focus_rows"])
                profile_cards = insights_from_profile_findings(
                    profile_findings, sub_scores=sub_scores,
                    peer_medians=ctx["peer_medians"],
                    classifier=classifier,
                ) if profile_findings else []
                section_cards = _section_cards_from_raw(ctx["raw_sections"])
                rec_cards = _cards_from_db_recommendations(
                    ctx["recs"], sub_scores, ctx["peer_medians"],
                    subcap_names=subcap_names, cat_names=cat_names,
                    ev_excerpts=ev_excerpts)
                # L3 gold composer — the PRIMARY author, highest-priority rung.
                # Rubric-graded + PASS-only; combine_insight_rungs lets gold win
                # dedup and the deterministic ladder below fills any anchor gold
                # could not ground. Fail-safe: [] on any error (ladder-only).
                gold_cards = await gold_cards_for_run(session, run.display_id)
                cards = combine_insight_rungs(
                    gold_cards, profile_cards, section_cards, rec_cards)
                rung_counts = {
                    "gold": sum(1 for c in cards
                                if c.ic_id.startswith("GLD")),
                    "profile": sum(1 for c in cards
                                   if c.ic_id.startswith("CP-")),
                    "recs": sum(1 for c in cards
                                if c.ic_id.startswith("INS-")),
                }
                rung_counts["section"] = (
                    len(cards) - rung_counts["gold"] - rung_counts["profile"]
                    - rung_counts["recs"])
                if not cards and categories:
                    cards = insights_from_category_gaps(categories)
                    rung_counts["gaps"] = len(cards)
                # Generated OPPORTUNITY cards — zennify opportunity map
                # rows + the hiring x absence x strategy cross-signal.
                opp_cards = insights_from_zennify_opportunities(
                    ctx["zennify_rows"], sub_scores=sub_scores,
                    peer_medians=ctx["peer_medians"],
                    family_leafs=family_leafs,
                    evidence_excerpts=ev_excerpts,
                    classifier=classifier,
                ) if ctx["zennify_rows"] else []
                strategic_quotes = []
                for r in ctx["focus_rows"]:
                    if (r.source_path or "") != "docx:strategic_section":
                        continue
                    pf = profile_finding_from_quote(r.title, r.verbatim_quote)
                    strategic_quotes.append({
                        "quote": r.verbatim_quote,
                        "e_ids": pf.e_ids if pf else [],
                    })
                xsig = _cross_signal_opportunity_cards(
                    evidence_rows=ctx["evidence_rows"],
                    absent_families=absent,
                    strategic_quotes=strategic_quotes,
                    family_leafs=family_leafs,
                    sub_scores=sub_scores,
                )
                if opp_cards or xsig:
                    before = {c.ic_id for c in cards}
                    cards = combine_insight_rungs(cards, opp_cards, xsig)
                    rung_counts["opportunity"] = sum(
                        1 for c in cards if c.ic_id not in before)
                if not cards:
                    stats.skipped_no_data += 1
                else:
                    # Evidence ladder: inline citations already ride the
                    # cards; top up from subcap → category roll-up →
                    # lexical-similarity attach (23 runs carry evidence
                    # with NO subcap links at all — the structural rungs
                    # can never fire there). Basis chip is the terminal
                    # honest state. Report-cited E-IDs that the run's
                    # evidence_index doesn't carry are dropped first —
                    # they'd render dead chips (65-card audit class).
                    # Gold cards carry curated, support-checked, drilldown-
                    # resolvable citations from the L3 composer — the ladder's
                    # graph-proximity top-up would only re-introduce the
                    # misattributed / annotation-dirty E-IDs the composer avoids,
                    # so the E-ID-mutating steps run on the ladder cards only.
                    ladder_cards = [c for c in cards
                                    if not c.ic_id.startswith("GLD")]
                    valid_eids = {row["e_id"] for row in ctx["evidence_rows"]}
                    if valid_eids:
                        for c in ladder_cards:
                            c.linked_e_ids = [
                                e for e in (c.linked_e_ids or [])
                                if e in valid_eids
                            ]
                    _attach_evidence(ladder_cards, ev_by_subcap)
                    similarity_attach_evidence(ladder_cards, ctx["evidence_rows"])
                    sibling = {c.ic_id: set(c.linked_e_ids or [])
                               for c in cards}
                    enrichment = {
                        c.ic_id: _enrich_card(
                            {"ic_id": c.ic_id, "title": c.title,
                             "what": c.what_text, "why": c.why_text,
                             "so_what": c.so_what_text,
                             "anchor": c.linked_subcap_id,
                             "e_ids": list(c.linked_e_ids or []),
                             "severity": c.severity,
                             "source_rec_id": getattr(
                                 c, "source_rec_id", None)},
                            classifier=classifier,
                            platform_tags=ctx["platform_tags"],
                            evidence_rows=ctx["evidence_rows"],
                            rec_targets=rec_targets,
                            valid_subcaps=set(sub_scores),
                            absent_families=absent,
                            sibling_eids=sibling,
                        )
                        for c in cards
                    }
                    n = await _insert_cards(
                        session, run.run_id, run.entity_id, cards,
                        enrichment,
                        ev_excerpts={
                            r["e_id"]: r["excerpt"]
                            for r in ctx["evidence_rows"] if r.get("excerpt")
                        })
                    for rung, cnt in rung_counts.items():
                        stats.bump(rung, cnt)
                    stats.runs_filled.append(
                        f"{run.display_id}("
                        + ",".join(f"{k}:{v}" for k, v in
                                   sorted(rung_counts.items()) if v)
                        + f"={n})")

            # ── SCQA backfill (mirror of the ingest fallback at
            # dma_package.py: when no executive_summary_scqa section
            # shipped, derive one from the run's own category scores +
            # recs and persist it the same way ingest does — as a
            # document_sections row that section_routing already picks
            # up for the D1 overview narrative). ───────────────────
            if run.n_scqa == 0 and categories:
                derived = build_derived_scqa(
                    run.entity_name, categories, list(ctx["recs"]))
                if derived:
                    # A heading-only DOCX match can leave an EMPTY-body
                    # scqa row (28 entities, 2026-06-10 corpus census) —
                    # n_scqa above ignores it, so drop it here or the
                    # narrative builder may still pick the empty row.
                    await session.execute(text(
                        """
                        DELETE FROM document_sections
                        WHERE run_id = :rid
                          AND section_kind = 'executive_summary_scqa'
                          AND length(coalesce(body, '')) = 0
                        """),
                        {"rid": run.run_id},
                    )
                    await session.execute(text(
                        """
                        INSERT INTO document_sections (
                            run_id, entity_id, section_kind, ordinal,
                            heading, body, source_path
                        ) VALUES (
                            :rid, :eid, 'executive_summary_scqa',
                            COALESCE((SELECT max(ordinal) + 1
                                      FROM document_sections
                                      WHERE run_id = :rid), 0),
                            'Executive Summary', :body,
                            'derived://scqa-from-scores'
                        )
                        """),
                        {"rid": run.run_id, "eid": run.entity_id,
                         "body": derived},
                    )
                    stats.scqa_filled.append(run.display_id)

        await session.commit()
    await engine.dispose()

    # 2026-06-11 operator mandate ("no surprises for each of the 95
    # clients — ensure all pages have the PERSISTED information"):
    # why_now_signals + top_findings must be persisted 95/95, not just
    # read-time derived. Deterministic ladder, grounded on the run's
    # own rows, provenance-flagged:
    #   why_now:  latest timeline_events (kind→trigger) → top insight
    #             cards framed as triggers
    #   findings: top-4 severity-ranked insight cards
    # Idempotent: only rows whose array is empty are written; every
    # ACTIVE run has ≥1 insight card (census), so coverage is total.
    engine = create_async_engine(dsn, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        empty_runs = (await session.execute(text(
            """
            SELECT r.id AS run_id, r.entity_id, r.completed_at, e.display_id,
                   jsonb_array_length(COALESCE(r.why_now_signals,'[]'::jsonb)) AS n_wn,
                   jsonb_array_length(COALESCE(r.top_findings,'[]'::jsonb)) AS n_tf
            FROM runs r JOIN entities e ON e.id = r.entity_id
            WHERE r.status='ACTIVE'
            """
            + ("AND e.display_id = :ent " if getattr(args, "entity", None)
               else "")),
            ({"ent": args.entity} if getattr(args, "entity", None)
             else {}))).all()
        wn_filled = tf_filled = 0
        for run in empty_runs:
            cards = None
            if run.n_wn == 0 or run.n_tf == 0:
                cards = (await session.execute(text(
                    """
                    SELECT ic_id, title,
                           COALESCE(NULLIF(so_what_text,''), NULLIF(why_text,''),
                                    what_text, '') AS body,
                           severity, linked_subcap_id
                    FROM insight_cards WHERE run_id = :rid
                    ORDER BY CASE lower(severity) WHEN 'critical' THEN 0
                             WHEN 'high' THEN 1 WHEN 'opportunity' THEN 2
                             ELSE 3 END, ic_id LIMIT 4
                    """), {"rid": run.run_id})).all()
            if run.n_wn == 0:
                today = dt.date.today()
                # 24-month recency cutoff: a 2013 acquisition is not a live
                # "why now" trigger (the uncapped ORDER BY shipped one).
                tl = (await session.execute(text(
                    """
                    SELECT kind, title, COALESCE(body,'') AS body,
                           event_date, e_id
                    FROM timeline_events
                    WHERE entity_id = :eid AND event_date IS NOT NULL
                      AND event_date >= :cutoff
                    ORDER BY event_date DESC LIMIT 3
                    """), {"eid": run.entity_id,
                           "cutoff": today - dt.timedelta(days=730)})).all()
                kind_label = {"acquisition": "M&A", "regulatory": "REGULATORY",
                              "leadership": "LEADERSHIP", "milestone": "MILESTONE"}
                win_cat = {"M&A": "ma", "LEADERSHIP": "leadership",
                           "REGULATORY": "regulatory", "MILESTONE": "hiring"}
                signals: list[dict] = []
                if tl:
                    for t in tl:
                        kind = kind_label.get((t.kind or "").lower(),
                                              (t.kind or "SIGNAL").upper())
                        detail = _event_detail(t.title, t.body,
                                               t.event_date.strftime("%b %Y"))
                        signals.append({
                            "kind": kind, "text": t.title, "detail": detail,
                            "date": t.event_date.isoformat(),
                            "evidence": [t.e_id] if t.e_id else [],
                            "window": _window_for(detail, t.event_date,
                                                  win_cat.get(kind, "market"),
                                                  today),
                            "timeline": {"date": t.event_date.isoformat(),
                                         "event": (t.title or "")[:90]},
                            "derived_from": "timeline_events"})
                else:
                    # No dated timeline trigger — prefer the L3 why-now composer
                    # (finding thesis + play + window, graded on the rubric) over
                    # raw card reuse. Fail-safe: fall back on any error.
                    gold_wn = []
                    try:
                        _stw = await load_entity_state(
                            session, entity_display_id=run.display_id)
                        if _stw is not None:
                            gold_wn = compose_why_now(_stw, k=3)
                    except Exception:
                        gold_wn = []
                    if gold_wn:
                        signals = [
                            {"kind": "OPPORTUNITY", "text": w.title,
                             "detail": w.so_what,
                             "evidence": list(w.e_ids or [])[:6],
                             "metric": "opportunity flagged in the latest assessment",
                             "subcap_id": w.anchor_subcap,
                             "derived_from": "gold_composer"}
                            for w in gold_wn
                        ]
                    else:
                        sev_kind = {"critical": "GAP", "high": "GAP"}
                        signals = [
                            {"kind": sev_kind.get((c.severity or "").lower(),
                                                  "OPPORTUNITY"),
                             "text": c.title, "detail": c.body or c.title,
                             "evidence": [],
                             "metric": (f"{(c.severity or 'notable').lower()}"
                                        f"-severity finding in the latest assessment"),
                             "subcap_id": c.linked_subcap_id,
                             "derived_from": "insight_cards"}
                            for c in (cards or [])[:3]
                        ]
                if signals:
                    # Same 14-field template as the deep miner (shared
                    # helpers) — never the legacy 5-key shape. The generic
                    # play is a floor only; _dedupe_plays re-anchors any
                    # repeat on the signal's own label.
                    signals = _ensure_deep_fields(
                        signals,
                        "Open the conversation on this trigger and bring "
                        "the platform evaluation criteria early.")
                    signals = finalize_why_now(
                        signals, today=today,
                        assessment_date=(run.completed_at.date()
                                         if run.completed_at else None))
                    _dedupe_plays(signals)
                    # 2026-07-06 deploy review — why_now.dup_pairs=0: this floor
                    # producer must not re-grow the near-duplicate class either
                    # (ONE dedup contract shared with the deep miner).
                    signals = dedupe_why_now_by_containment(signals)
                    await session.execute(text(
                        "UPDATE runs SET why_now_signals = CAST(:v AS JSONB), "
                        "updated_at = NOW() WHERE id = :rid "
                        "AND jsonb_array_length(COALESCE(why_now_signals,'[]'::jsonb)) = 0"),
                        {"v": json.dumps(signals, default=str), "rid": run.run_id})
                    wn_filled += 1
            if run.n_tf == 0:
                # PRIMARY: the L3 findings composer — thesis-first, ranked by
                # evidenced peer-gap, deduped, graded on the same rubric. Reuses
                # the run's shared EntityState so the findings agree with the
                # cards. Fail-safe: any error falls back to the card-reuse floor.
                gold_f = []
                try:
                    _st = await load_entity_state(
                        session, entity_display_id=run.display_id)
                    if _st is not None:
                        # thesis-first: the findings support the client's ONE
                        # storyline spine (analyst SCQA answer when present, else
                        # the score-derived thesis) so surfaces cohere.
                        gold_f = compose_findings(
                            _st, k=4, thesis=derive_thesis(_st))
                except Exception:
                    gold_f = []
                if gold_f:
                    findings = [
                        {"title": f.title,
                         "body": proofread(f"{f.what} {f.why}".strip())
                         or f.what,
                         "evidence": list(f.e_ids or [])[:6], "platforms": [],
                         "subcap_id": f.anchor_subcap,
                         "derived_from": "gold_composer"}
                        for f in gold_f
                    ]
                elif cards:
                    findings = [
                        {"title": c.title, "body": c.body, "evidence": [],
                         "platforms": [], "subcap_id": c.linked_subcap_id,
                         "derived_from": "insight_cards"}
                        for c in cards
                    ]
                else:
                    findings = []
                if findings:
                    await session.execute(text(
                        "UPDATE runs SET top_findings = CAST(:v AS JSONB), "
                        "updated_at = NOW() WHERE id = :rid "
                        "AND jsonb_array_length(COALESCE(top_findings,'[]'::jsonb)) = 0"),
                        {"v": json.dumps(findings), "rid": run.run_id})
                    tf_filled += 1
        await session.commit()
    await engine.dispose()
    print(f"# derive_insights: why_now persisted+={wn_filled}, "
          f"top_findings persisted+={tf_filled}")

    rung_summary = ", ".join(
        f"{k}={v}" for k, v in sorted(stats.by_rung.items())) or "none"
    print(f"# derive_insights: runs filled={len(stats.runs_filled)} "
          f"(cards by rung: {rung_summary}); "
          f"scqa backfilled={len(stats.scqa_filled)}; "
          f"skipped existing={stats.skipped_existing} "
          f"(enriched in place={stats.enriched_existing}), "
          f"no-data={stats.skipped_no_data}")
    if args.verbose:
        for line in stats.runs_filled:
            print("  ", line)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--force", action="store_true",
                   help="delete + re-derive even when cards exist")
    p.add_argument("--limit", type=int, help="only first N runs")
    p.add_argument("--entity", default=None,
                   help="scope to one display_id (per-client processing)")
    p.add_argument("--verbose", action="store_true")
    return asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
