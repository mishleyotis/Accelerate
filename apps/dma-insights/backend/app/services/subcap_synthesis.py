"""Deterministic per-subcap synthesis composer (D3 SynthesisDrawer floor).

The 2026-06 heatmap audit measured per-subcap narrative coverage at 1/94:
`subcap_narrative_extractor` (Vertex Pro) only ever produced rows for the
one client whose pillar deep-dive DOCX was ingested AND whose extraction
validated, and its output had no durable home until migration 051 added
`subcap_narratives`. This module is the deterministic floor beneath the
Gemini rung — for EVERY scored subcap cell it composes a 2-4 sentence
narrative from the cell's REAL values:

  score · band · peer_median (where benchmarked) · thin-evidence flag ·
  issue-cap flag/reason · top evidence excerpt (via evidence_index
  links) · linked insight-card / recommendation titles.

Three variants mirror the prototype's AI-synthesis block
(fc639245:832-836): thin-evidence phrasing, peer-gap phrasing, and
at/above-peer phrasing — always with the actual numbers, never a
template family from the `nlp.quality` filler blacklist (the banned-
phrase guard is a unit test: tests/test_subcap_synthesis.py).

Writers persist through `app.scripts.derive_subcap_narratives` into
`subcap_narratives` with meta='heuristic'; the Gemini extractor UPSERTs
meta='llm' rows over the floor when it validates at deploy. Readers:
the heatmap subcap endpoint (llm > heuristic) + the pack writer.

Every function here is pure so the composer variants are directly
unit-testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.nlp.segment import clip_excerpt_verbatim, clip_sentences

# Peer gap below which we consider the subcap "at peer".
_AT_PEER_TOLERANCE = 0.3
# Excerpt budget inside a narrative sentence.
_EXCERPT_MAX_CHARS = 220

# Catalogue-stub / placeholder names the auto-bootstrap writes when the
# real workbook name is unknown ("Subcap 7", "Subcap P1C1.1.1",
# "capability dimension 10", "Process Automation — Subcap 10"). The
# 2026-07 depth stress-test found 2,169 narratives leaking them: a
# generic name must be resolved from the catalogue or OMITTED — never
# rendered.
_GENERIC_NAME_RE = re.compile(
    r"(?:^|[\s—–(-])sub-?cap\s*(?:\d+|P\d)|capability\s+dimension|^placeholder\b",  # noqa: RUF001
    re.IGNORECASE,
)

# cap_reason values that are storage artifacts, not reasons — "None" is
# a literal str(None) persisted upstream; it produced the shipped bug
# "An open issue caps this score: None".
_DEGENERATE_REASONS = frozenset({"none", "null", "n/a", "na", "-", ""})


def is_generic_subcap_name(name: str | None, subcap_id: str) -> bool:
    """True when the catalogue name is a bootstrap stub / placeholder
    (or just the id echoed back) rather than a real capability name."""
    stripped = (name or "").strip()
    if not stripped or stripped == subcap_id:
        return True
    return bool(_GENERIC_NAME_RE.search(stripped))


@dataclass
class SubcapFacts:
    """Everything the composer may cite — all REAL run values."""
    subcap_id: str
    name: str | None
    score: float
    band: str
    peer_median: float | None = None
    is_thin_evidence: bool = False
    cap_applied: bool = False
    cap_reason: str | None = None
    # rank of this cell's peer gap among the run's below-peer gaps
    # (1 = widest); None when unranked. A superlative is only honest
    # for the actual argmax (reasoning audit 2026-07-12: 'widest-
    # leverage direction' shipped on 32,217 cells, 94% not the widest).
    gap_rank: int | None = None
    n_gapped: int | None = None
    evidence_count: int = 0
    evidence_e_ids: list[str] = field(default_factory=list)
    # Parallel to evidence_e_ids — the composer weaves the first CITABLE
    # excerpt's substance into the narrative (the AE-depth contract:
    # cite AND use the evidence, never a content-free "grounded on
    # E-105" pointer).
    evidence_excerpts: list[str] = field(default_factory=list)
    top_excerpt: str | None = None
    insight_titles: list[str] = field(default_factory=list)
    rec_titles: list[str] = field(default_factory=list)
    # v7 use-case corpus playbook (use_case_stories.load_playbooks): the
    # platform feature set the catalogue's validated use cases pair with
    # this subcap, and how many stories validate it. Only woven for
    # below-peer cells (a proven pattern is the path, not the trophy).
    playbook_features: list[str] = field(default_factory=list)
    playbook_stories: int = 0


def _fmt(value: float) -> str:
    return f"{value:.1f}"


def _lead_sentence(facts: SubcapFacts) -> str:
    name = (facts.name or "").strip()
    if is_generic_subcap_name(name, facts.subcap_id):
        # Never render "Subcap 7 (P2C2.1.7)"-class placeholders — the
        # bare id is more honest than a stub name.
        return (
            f"{facts.subcap_id} scored {_fmt(facts.score)} "
            f"({facts.band}) in this run."
        )
    return (
        f"{name} ({facts.subcap_id}) scored {_fmt(facts.score)} "
        f"({facts.band}) in this run."
    )


def _playbook_sentence(facts: SubcapFacts) -> str | None:
    """The catalogue-validated implementation pattern, for gap cells only.

    Grounded in the v7 use-case corpus (ccg_user_stories): names the
    recurring feature set and how many catalogued use cases validate it —
    a concrete 'how it closes', never a vendor pitch lead (QA-GLB-07:
    the sentence trails the assessment, it doesn't open it)."""
    if not facts.playbook_features or facts.playbook_stories < 2:
        return None
    if facts.peer_median is None or facts.peer_median - facts.score <= _AT_PEER_TOLERANCE:
        return None
    feats = facts.playbook_features[:3]
    if len(feats) == 1:
        fx = feats[0]
    elif len(feats) == 2:
        fx = f"{feats[0]} and {feats[1]}"
    else:
        fx = f"{feats[0]}, {feats[1]} and {feats[2]}"
    return (f"The capability catalogue maps a proven implementation "
            f"pattern here — {fx} — validated across "
            f"{facts.playbook_stories} catalogued use cases.")


def _peer_sentence(facts: SubcapFacts) -> str | None:
    if facts.peer_median is None:
        return None
    gap = facts.peer_median - facts.score
    if gap > _AT_PEER_TOLERANCE:
        if facts.gap_rank == 1:
            tail = "— the widest peer gap in this run."
        elif facts.gap_rank is not None and facts.gap_rank <= 5:
            tail = (f"— among the run's widest peer gaps "
                    f"(#{facts.gap_rank} of {facts.n_gapped}).")
        else:
            tail = "— real headroom against the cohort."
        return (
            f"That trails the peer median of {_fmt(facts.peer_median)} by "
            f"{_fmt(gap)} {tail}"
        )
    if gap < -_AT_PEER_TOLERANCE:
        return (
            f"That sits {_fmt(abs(gap))} above the peer median of "
            f"{_fmt(facts.peer_median)}; the priority here is protecting "
            f"the lead, not new investment."
        )
    return (
        f"That is at the peer median ({_fmt(facts.peer_median)}), so "
        f"movement depends on adjacent capabilities rather than this "
        f"cell alone."
    )


def _thin_sentence(facts: SubcapFacts) -> str:
    n = facts.evidence_count
    cited = (
        f"{n} corroborating evidence item{'s' if n != 1 else ''}"
        if n else "no directly-linked evidence items"
    )
    return (
        f"Evidence is thin — {cited} in this run — so treat the score "
        f"as provisional until corroborated."
    )


# Leading storage artifact glued onto a real reason ("None; CRITIC_
# CHALLENGE: SINGLE-SOURCE …" — str(None) concatenated upstream).
_DEGENERATE_PREFIX_RE = re.compile(r"^(?:none|null|n/?a)\s*[;,:.—-]\s*", re.IGNORECASE)


def _cap_sentence(facts: SubcapFacts) -> str | None:
    if not facts.cap_applied:
        return None
    reason = (facts.cap_reason or "").strip()
    reason = _DEGENERATE_PREFIX_RE.sub("", reason).strip()
    # Storage artifacts ("None", "null", "-") are NOT reasons — emit the
    # generic clause instead of "caps this score: None".
    if reason.lower() in _DEGENERATE_REASONS:
        reason = ""
    if reason:
        # internal scoring-machinery tokens read as leakage in AE prose:
        # "CRITIC_CHALLENGE: 4.0->3.0" -> "challenged in scoring review
        # (4.0->3.0)"
        reason = re.sub(
            r"\bCRITIC[_ ]CHALLENGE:?\s*([\d.]+\s*(?:→|->)\s*[\d.]+)?",
            lambda m: ("challenged in scoring review"
                       + (f" ({m.group(1)})" if m.group(1) else "")),
            reason)
        clipped = clip_sentences(reason, 180) or reason[:180]
        return f"An open issue caps this score: {clipped.rstrip('.')}."
    return "An open issue in the register caps this score until resolved."


def _citable(excerpt: str) -> bool:
    """Reject placeholder / degenerate excerpts ("(no excerpt)", "N/A",
    bare parentheticals, sub-25-char fragments) — quoting those would be
    worse than citing the E-ID alone."""
    stripped = excerpt.strip()
    if len(stripped) < 25:
        return False
    if stripped.startswith("(") and stripped.endswith(")"):
        return False
    return stripped.lower() not in {"n/a", "none", "no excerpt"}


def _citable_pairs(facts: SubcapFacts) -> list[tuple[str, str]]:
    """(e_id, excerpt) pairs with a CITABLE excerpt, in evidence order.
    `evidence_excerpts` is parallel to `evidence_e_ids`; the legacy
    `top_excerpt` field feeds the first slot when the list is absent."""
    excerpts = list(facts.evidence_excerpts)
    if not excerpts and facts.top_excerpt:
        excerpts = [facts.top_excerpt]
    out: list[tuple[str, str]] = []
    for i, eid in enumerate(facts.evidence_e_ids):
        excerpt = (excerpts[i] if i < len(excerpts) else "").strip()
        if excerpt and _citable(excerpt):
            out.append((eid, excerpt))
    return out


# Researcher-markup tags embedded in excerpts ("[ERS: 2.20] [FACT]
# [E-094:F1] Model Risk… [ERS: 2.50]") — stripped ANYWHERE (they are
# scoring metadata, not prose) so the substance sentence reads clean.
_MARKUP_TAGS_RE = re.compile(
    r"\s*\[(?:ERS|FACT|INFERENCE|HYPOTHESIS|CLAIM|E-)[^\]]*\]", re.IGNORECASE,
)


# leading analyst shout-labels ("COMPANY FOCUS:", "MAJOR TECH FIND:",
# "DIRECT EVIDENCE:") — a run of ALL-CAPS words before a colon; they are
# research-tool emphasis, not prose, and they opened 54.9k drawer
# sentences with no tie to the score sentence (cohesion sweep).
_SHOUT_PREFIX_RE = re.compile(
    r"^\s*(?:[A-Z][A-Z0-9/&'-]{1,18}\s+){0,4}[A-Z][A-Z0-9/&'-]{1,18}"
    r"\s*[:\u2014\u2013-]\s+(?=[A-Z0-9])")


def _clean_excerpt(excerpt: str) -> str:
    cleaned = _MARKUP_TAGS_RE.sub("", excerpt)
    # Any remaining leading bracket tag (unknown families) + newlines.
    cleaned = re.sub(r"^\s*(?:\[[^\]]{1,32}\]\s*)+", "", cleaned)
    m = _SHOUT_PREFIX_RE.match(cleaned)
    if m and m.group(0).strip(" :\u2014\u2013-").isupper():
        cleaned = cleaned[m.end():]
    return re.sub(r"\s+", " ", cleaned).strip(" :;—-")


_FIELD_LABEL_RE = re.compile(
    r"\b[A-Z][A-Z_ ]{2,44}(?:\s*\([^)]{0,20}\))?\s*[=:]\s*['\"]?")
_SYMBOL_RE = re.compile(r"[=/;|]")


def _prose_like(text: str) -> bool:
    """Reads as a sentence, not a structured note: low symbol density and
    at least one ordinary lowercase word run."""
    if not text:
        return False
    symbols = len(_SYMBOL_RE.findall(text))
    words = max(len(text.split()), 1)
    return symbols / words < 0.08 and bool(re.search(r"\b[a-z]{3,}\s+[a-z]{3,}", text))


def _destructure(text: str) -> str:
    """Strip analyst field labels ("VISION='...'", "PRIORITIES (4):") and
    note separators from an excerpt that has no prose-like alternative —
    keep the values, drop the notation."""
    out = _FIELD_LABEL_RE.sub("", text)
    out = re.sub(r"\s*/\s*", "; ", out)
    out = re.sub(r"\s=\s", ": ", out)          # note-shorthand '=' -> ':'
    out = re.sub(r"\s*'\s*(?=[;,.]|$)", "", out)  # orphaned closing quotes
    return re.sub(r"\s+", " ", out).strip(" ;'\"")


def _substance_sentence(facts: SubcapFacts) -> str | None:
    """The AE-depth sentence: weave the FIRST citable evidence excerpt's
    concrete content (systems, numbers, events) into the rationale as
    evidence-framed, INTERPRETED prose tied to the score — not a
    'Grounding [E-x]: "quote."' dump (the 2026-07-06 heatmap-drawer defect
    the user singled out: "the score rationale is not communicated in a way
    the AE can read through well")."""
    pairs = [(eid, _clean_excerpt(ex)) for eid, ex in _citable_pairs(facts)]
    pairs = [(eid, ex) for eid, ex in pairs if _citable(ex)]
    # the most readable REAL evidence leads; structured notes only when
    # nothing prose-like exists, and then with their notation stripped
    ordered = ([p for p in pairs if _prose_like(p[1])]
               or [(eid, _destructure(ex)) for eid, ex in pairs])
    for eid, excerpt in ordered:
        if not _citable(excerpt):
            continue
        # Verbatim mandate (2026-07-06): only whole trailing sentences may be
        # dropped (marked with an ellipsis) — never a mid-claim cut.
        clipped = clip_excerpt_verbatim(excerpt, _EXCERPT_MAX_CHARS)
        fact = clipped if clipped.endswith("…") else clipped.rstrip(" .;:—–-")  # noqa: RUF001
        # tie the evidence sentence back to the score sentence (referential
        # opener, varied by standing so no single skeleton recurs), then the
        # interpretation tying it to the band — a cohesive chain, not a
        # quoted block.
        opener = ("Behind that score, " if str(facts.band).upper() in ("M1", "M2")
                  else "Underpinning that standing, ")
        # decapitalize only an ordinary capitalized word — never an
        # acronym / identifier lead ("SR 11-7 requires ...") and never a
        # proper-noun bigram ("Cetera Financial ..." stays capitalized;
        # a company/person lead is a name, not a sentence-case artifact)
        _next = re.split(r"\s+", fact, maxsplit=2)
        _proper_bigram = (len(_next) > 1 and _next[1][:1].isupper()
                          and _next[0] not in ("The", "A", "An", "It",
                                               "This", "That", "Its",
                                               "Their", "Our"))
        if (len(fact) > 1 and fact[0].isupper() and fact[1].islower()
                and not _proper_bigram):
            fact = fact[0].lower() + fact[1:]
        return (f"{opener}{fact} — the concrete detail "
                f"the {facts.band} score rests on [{eid}].")
    return None


def _grounding_sentence(facts: SubcapFacts) -> str | None:
    """Fallback pointer when NO excerpt is citable — cite the E-IDs."""
    eid = facts.evidence_e_ids[0] if facts.evidence_e_ids else None
    if eid is None:
        return None
    others = len(facts.evidence_e_ids) - 1
    suffix = f" and {others} further item{'s' if others != 1 else ''}" if others > 0 else ""
    return f"The score is grounded on {eid}{suffix} in the evidence index."


def _usable_title(title: str) -> bool:
    """Linked-item titles are quoted verbatim — skip stubs that would
    leak generic placeholders ('Strengthen P3C4: capability dimension
    25') into the narrative."""
    stripped = title.strip().rstrip(".")
    return bool(stripped) and not _GENERIC_NAME_RE.search(stripped)


def _linked_sentence(facts: SubcapFacts) -> str | None:
    """Tie to the linked insight / recommendation titles (real joins)."""
    for raw in facts.insight_titles:
        if _usable_title(raw):
            title = raw.strip().rstrip(".")
            more = len(facts.insight_titles) - 1
            suffix = f" (+{more} more)" if more > 0 else ""
            # "That standing" ties the chip-style closer back to the
            # peer/score sentence before it (cohesion sweep:
            # disconnected) — same demonstrative-bridge pattern as the
            # platform readiness and SCQA complication fixes
            return (f'That standing pairs with a linked insight: '
                    f'"{title}"{suffix}.')
    for raw in facts.rec_titles:
        if _usable_title(raw):
            title = raw.strip().rstrip(".")
            return f'The linked recommendation "{title}" addresses this gap directly.'
    return None


def compose_subcap_narrative(facts: SubcapFacts) -> str:
    """Compose the 2-4 sentence deterministic narrative.

    Variant selection (mutually reinforcing, priority order):
      thin      — is_thin_evidence or <2 evidence items ⇒ provisional-score
                  phrasing leads the assessment.
      peer-gap  — peer_median present and gap > 0.3 ⇒ trailing phrasing.
      at-peer   — everything else with a peer median ⇒ at/above phrasing.
    A cap sentence is appended whenever an issue cap applies; grounding /
    linked-item sentences fill the remaining budget. Output is clamped to
    4 sentences.
    """
    sentences: list[str] = [_lead_sentence(facts)]

    thin = facts.is_thin_evidence or facts.evidence_count < 2
    if thin:
        sentences.append(_thin_sentence(facts))

    # AE-depth contract: when a citable excerpt exists its substance is
    # GUARANTEED a slot (it outranks the peer sentence in the budget) —
    # citing E-IDs without using their content fails the depth gate.
    substance = _substance_sentence(facts)
    if substance:
        sentences.append(substance)

    cap = _cap_sentence(facts)
    if cap:
        sentences.append(cap)

    peer = _peer_sentence(facts)
    if peer and len(sentences) < 4:
        sentences.append(peer)

    # gap cells close on the catalogue-validated path to next level
    playbook = _playbook_sentence(facts)
    if playbook and len(sentences) < 4:
        sentences.append(playbook)

    if len(sentences) < 4 and not substance:
        grounding = _grounding_sentence(facts)
        if grounding:
            sentences.append(grounding)

    if len(sentences) < 4:
        linked = _linked_sentence(facts)
        if linked:
            sentences.append(linked)

    if len(sentences) < 2:
        # No peer, not thin, no cap, no evidence, no links — still say
        # something real about the score's meaning.
        sentences.append(
            f"No peer benchmark or linked evidence is attached to this "
            f"cell in this run; the {facts.band} banding rests on the "
            f"scoring workbook alone."
        )

    return " ".join(sentences[:4])


# ── Shared grid-narrative twin (pack exporter ⇄ live heatmap route) ─────
# Two consumers MUST stay byte-identical on the heatmap grid's
# narrative.per_subcap_md / per_subcap_meta: export_startup_pages bakes
# them into the committed pack's heatmap.json (cold/pack-first serve of
# the SynthesisDrawer), and the live grid route must serve the SAME merge
# or qa_pack_parity --strict fails structurally (2026-07-04 fresh-DB
# regen sim: 14 findings — pack narrative dicts vs live None, because the
# route read only document_sections lineage while the exporter also read
# subcap_narratives; the drilldown route already reads the table).


async def load_subcap_synthesis_for_run(
    session, run_id,
) -> tuple[dict[str, str], dict[str, str]]:
    """``(per_subcap_md, per_subcap_meta)`` for one run, llm-first.

    Sourced from ``subcap_narratives`` (migration 051 — the deterministic
    composer floor above + validator-passed Gemini rows). Empty dicts when
    the run has no rows or the table is absent (legacy DBs) — the merge is
    then a no-op.
    """
    from sqlalchemy import text
    try:
        rows = (await session.execute(
            text(
                "SELECT subcap_id, narrative_md, meta FROM subcap_narratives "
                "WHERE run_id = CAST(:rid AS uuid) "
                "ORDER BY CASE meta WHEN 'llm' THEN 0 ELSE 1 END, subcap_id"
            ),
            {"rid": str(run_id)},
        )).all()
    except Exception:
        # subcap_narratives absent on legacy DBs — grid keeps its skeleton.
        await session.rollback()
        return {}, {}
    # The ORDER BY makes an llm row win over a heuristic row for the same
    # subcap; the FIRST value seen (via setdefault) is therefore the best.
    # Read-time hygiene (same contract as the findings/why-now polish):
    # persisted drawer rows carry analyst-note caps ("WORKDAY HRIS
    # DEPLOYED") — proofread is deterministic, idempotent, never grows
    # text, and runs here so the export bake and the live route serve
    # byte-identical prose (pack parity).
    from app.services.nlp.quality import proofread
    per_md: dict[str, str] = {}
    per_meta: dict[str, str] = {}
    for r in rows:
        if r.narrative_md:
            per_md.setdefault(r.subcap_id,
                              proofread(r.narrative_md) or r.narrative_md)
            per_meta.setdefault(r.subcap_id, r.meta)
    return per_md, per_meta


def merge_subcap_synthesis(
    body: dict, per_md: dict[str, str], per_meta: dict[str, str],
) -> None:
    """Fold per-subcap synthesis into a heatmap body's narrative, in place.

    ``subcap_narratives`` is authoritative for the keys it carries; any
    section-routing ``per_subcap_md`` entry it does not cover is
    preserved. Populating ``per_subcap_meta`` also satisfies the
    ``heatmap_subcap_synthesis_clients`` pack counter. No-op when
    ``per_md`` is empty so an entity with no rows keeps ``narrative``
    exactly as section routing built it (possibly None).
    """
    if not per_md:
        return
    narr = body.get("narrative")
    if not isinstance(narr, dict):
        narr = {}
    merged_md = dict(narr.get("per_subcap_md") or {})
    merged_meta = dict(narr.get("per_subcap_meta") or {})
    merged_md.update(per_md)
    merged_meta.update(per_meta)
    narr["per_subcap_md"] = merged_md
    narr["per_subcap_meta"] = merged_meta
    body["narrative"] = narr
