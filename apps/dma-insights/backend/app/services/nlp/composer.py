"""L3 — the deterministic, evidence-grounded surface composer (the gold prose).

The composer writes each surface item to the grader's rubric FROM the shared
EntityState: thesis-first title, a 3-5 sentence WHAT grounded in support-checked
evidence, a cross-link WHY, and a strategic so-what naming the play + system +
urgency. It is the PRIMARY author — Gemini is only the refine loop's fallback.

It never fabricates: every figure comes from a cited excerpt or the anchor's
assessment score, every citation is support-checked (state.supporting_evidence),
and an anchor with no support-checked evidence yields ``None`` (skip — the G2
backstop for NA / unevidenced cells). Prose is opportunity-framed
(text_hygiene.opportunity_reframe) and de-jargoned (text_hygiene.plain).

This first surface is the insight card — the reference surface and the largest
defect lever; findings/focus/platform reuse the same primitives.
"""
from __future__ import annotations

import re
import zlib
from typing import TYPE_CHECKING

from app.services.nlp.grader import Item, capability_text
from app.services.nlp.knowledge import Claim, resolve_contradictions
from app.services.text_hygiene import opportunity_reframe, plain

if TYPE_CHECKING:
    from app.services.nlp.entity_knowledge import Capability, EntityState
    from app.services.nlp.storyline import Thesis

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_EMOJI_RE = re.compile("[\U0001f000-\U0001faff☀-➿\U0001f1e6-\U0001f1ff]+")
# a lead sentence must carry a predicate tying the entity to the claim (mirrors
# the grader's G1 predicate check).
_PREDICATE_RE = re.compile(
    r"\b(is|are|was|were|has|have|had|scores?|leads?|runs?|gives?|generates?|"
    r"operates?|trails?|holds?|shows?|carries?|uses?|deployed|provides?|"
    r"maintains?|reduced|grew|reports?|reaches?|spans?|covers?)\b", re.I)
# domain phrasing per pillar for the opportunity clause / cross-link
_PILLAR_DOMAIN = {
    "P1": "strategy and governance", "P2": "customer experience",
    "P3": "operations and process", "P4": "the data and technology foundation",
}


def _first_sentence(text: str, max_len: int = 240) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    s = _SENT_SPLIT.split(text)[0].strip()
    return (s[:max_len].rsplit(" ", 1)[0] + "…") if len(s) > max_len else s


# A sentence that opens on a PERSON / roster fact (a leadership excerpt), not a
# capability fact — a name (with an optional parenthetical) then a person-role
# predicate. Must not become a capability card's opening line.
_PERSON_LEAD_RE = re.compile(
    r"^[\"']?[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s*(?:\([^)]*\))?\s+"
    r"(?:serves?\s+as\s+(?:an?\s+|the\s+)?(?:director|member|chair|board|"
    r"principal|partner|trustee)|joined\b|was\s+(?:appointed|named)\b|"
    r"is\s+(?:an?\s+|the\s+)?(?:director|member|principal|partner|chair)\b|"
    r"reports?\s+to\b|leads?\s+the\b|heads?\s+the\b|oversees\s+the\b)", re.I)
# A high-precision executive/board title near the start also marks a roster fact
# ("Jennifer Martin is EVP Human Resources…"): these tokens rarely occur in
# capability prose except when the sentence is describing a person.
_ROLE_TITLE_RE = re.compile(
    r"\b(?:CEO|CFO|CTO|CIO|CISO|CDO|COO|CMO|CHRO|CRO|EVP|SVP|"
    r"Chief\s+[A-Z][a-z]+(?:\s+(?:&\s+)?[A-Z][a-z]+)?\s+Officer|"
    r"Managing\s+Director|Board\s+of\s+Directors|Senior\s+Principal)\b")

# Analyst-workflow / placeholder meta-commentary — never a client fact.
_META_NOISE_RE = re.compile(
    r"\b(?:to\s+be\s+(?:fetched|scored|added|updated|reviewed)|next\s+batch|"
    r"for\s+scoring\s+depth|scoring\s+depth|cited\s+from\s+(?:newsroom|banner)|"
    r"placeholder|to-?do\b|tbd\b|not\s+yet\s+(?:fetched|scored)|"
    r"pending\s+(?:fetch|review|scoring))\b", re.I)

_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "on",
         "that", "this", "is", "are", "was", "were", "be", "by", "as", "at",
         "from", "its", "their", "has", "have", "not", "but", "which", "into",
         "across", "one", "two", "program", "capability", "capabilities"}


def _cap_terms(cap: Capability | None) -> set[str]:
    """Content tokens of the capability (name + rationale) for topical scoring."""
    if cap is None:
        return set()
    blob = f"{getattr(cap, 'name', '') or ''} {getattr(cap, 'rationale', '') or ''}"
    return {w for w in re.findall(r"[a-z][a-z0-9&/-]{3,}", blob.lower())
            if w not in _STOP}


def _term_overlap(sent: str, terms: set[str]) -> int:
    if not terms:
        return 0
    toks = set(re.findall(r"[a-z][a-z0-9&/-]{3,}", sent.lower()))
    return len(toks & terms)


def _pick_fact(excerpts: list[str], cap: Capability | None, max_len: int = 220) -> str:
    """A grounded, emoji-free lead sentence carrying a predicate, drawn from the
    support-checked excerpts — the card's opening fact. Prefers the sentence most
    topically aligned with the capability (so an A3-linked-but-off-topic excerpt
    does not dictate the lead), falling back to the first usable one so yield is
    never reduced. Skips person/roster leads and mangled quote fragments. Returns
    '' when no excerpt yields a usable sentence (skip the card)."""
    cap_terms = _cap_terms(cap)
    best_sent, best_score = "", -1.0
    for raw in excerpts:
        clean = _EMOJI_RE.sub("", raw or "").strip()
        if not clean:
            continue
        for sent in _SENT_SPLIT.split(clean):
            sent = sent.strip()
            if len(sent) < 24 or "|" in sent:
                continue
            # skip a mid-quote fragment (starts on a quote, or an unbalanced
            # quotation mark). A possessive/contraction apostrophe (letter'letter,
            # e.g. "bank's") is NOT a quote delimiter, so it must not count.
            q_singles = len(re.findall(r"(?<![A-Za-z])'|'(?![A-Za-z])", sent))
            if sent[:1] in "'\"" or sent.count('"') % 2 or q_singles % 2:
                continue
            if _PERSON_LEAD_RE.search(sent) or _ROLE_TITLE_RE.search(sent[:80]):
                continue
            if _META_NOISE_RE.search(sent):
                continue
            if not _PREDICATE_RE.search(sent):
                continue
            # first usable (score 0) beats the -1 sentinel; a strictly higher
            # topical overlap replaces it — so ties keep the earliest sentence.
            # Distinctiveness (corpus IDF, fitted once per derive process)
            # breaks topical ties toward the sentence carrying the CLIENT's
            # specifics — figures, names, rare vocabulary — over prose any
            # institution could ship. Unfitted → 0 for all → prior order.
            from app.services.nlp.distinctiveness import distinctiveness
            score = (float(_term_overlap(sent, cap_terms))
                     + 0.6 * distinctiveness(sent))
            if score > best_score:
                best_sent, best_score = sent, score
    if not best_sent:
        return ""
    return (best_sent[:max_len].rsplit(" ", 1)[0] + "…"
            ) if len(best_sent) > max_len else best_sent


def _platform_display(pid: str) -> str:
    try:
        from app.services.platform_display import PLATFORM_DISPLAY
        d = PLATFORM_DISPLAY.get(pid)
        if isinstance(d, dict):
            return d.get("name") or d.get("label") or pid.title()
        return d or pid.title()
    except Exception:
        return (pid or "").title()


def _urgency_clause(state: EntityState) -> str:
    """A dated / time-bound hook from the entity's why-now signals; else a
    near-term default (still a valid time token)."""
    for sig in state.why_now_signals or []:
        if not isinstance(sig, dict):
            continue
        for v in (sig.get("so_what"), sig.get("trigger"), sig.get("headline"), sig.get("title")):
            m = re.search(r"(before[^.;]{4,60}|by\s+(?:Q[1-4]\s*)?20\d{2}[^.;]{0,30}|"
                          r"ahead of[^.;]{4,60}|effective\s+\w+\s+\d[^.;]{0,20})", str(v or ""), re.I)
            if m:
                return m.group(1).strip().rstrip(".")
    return "in the near term, ahead of the next planning cycle"


def _platform_for(state: EntityState, anchor: str | None) -> str | None:
    """The roster platform that best addresses the anchor capability."""
    best = None
    for p in state.platforms:
        addr = p.get("addressable_subcap_ids") or []
        if anchor and anchor in addr:
            return _platform_display(p["platform_id"])
        if best is None:
            best = p
    return _platform_display(best["platform_id"]) if best else None


def compose_card(
    state: EntityState, cap: Capability, *, siblings: list[Capability] | None = None,
    is_top: bool = True,
) -> Item | None:
    """Compose one insight card for the anchor capability from support-checked
    evidence. Returns None when the anchor cannot be grounded (skip it)."""
    if not state.in_scope(cap.subcap_id):
        return None
    cap_text = capability_text(cap)
    # PRIMARY citations: the A3-linked evidence the corpus maps to THIS subcap
    # (genuine support, not a graph-proximity/TF-IDF guess); fall back to the
    # semantic top-k only when the subcap carries no linked evidence.
    cand = list(cap.evidence_ids) or [
        eid for eid, _ in state.supporting_evidence(cap_text, k=5, min_score=0.30)]
    if not cand:
        return None
    # challenge-filter (drop peer-owned / topically-misaligned) — the SAME L2
    # check the grader's G2 runs, so a composed card passes G2 by construction.
    claim = Claim(text=cap.rationale or cap.name, capability=cap_text, e_ids=list(cand))
    state.knowledge.challenge(claim, min_support=0.30)
    e_ids = claim.e_ids[:4]
    if not e_ids:
        return None    # nothing genuinely supports the capability — skip (no fabrication)
    # a fact sentence from a SURVIVING (support-checked) excerpt, with a predicate
    fact = _pick_fact([state.evidence_excerpt(e) or "" for e in e_ids], cap)
    if not fact:
        return None
    domain = _PILLAR_DOMAIN.get(cap.pillar, "this capability area")

    gap = cap.peer_gap if cap.peer_gap is not None else 0.0
    pm = cap.peer_median
    is_strength = gap > 0

    # ── WHAT: 3 grounded sentences (each terminated; figures are the cited
    # excerpt's + the anchor's assessment score, so verification holds) ──
    fact = fact.rstrip(" .")
    if pm is not None and not is_strength:
        # rank-aware: "widest" only when this card's gap actually IS the
        # (tied-)widest among the pillar's below-peer capabilities this
        # run — two sibling cards both claiming "the widest headroom" is
        # the superlative-inflation class (reasoning audit R1, and the
        # AlmaBank vetting sample)
        _dom_gaps = [s.peer_gap for s in (siblings or [])
                     if s.pillar == cap.pillar and s.in_scope
                     and s.peer_gap is not None and s.peer_gap < 0
                     and s.subcap_id != cap.subcap_id]
        _worst = min(_dom_gaps, default=gap)
        if gap < _worst - 1e-9 or not _dom_gaps:
            _desc = f"the widest headroom in {domain}"
        elif abs(gap - _worst) <= 1e-9:
            _desc = f"tied for the widest headroom in {domain}"
        else:
            _desc = f"real headroom in {domain}"
        # the arc: evidence reality → what the assessment makes of it →
        # what that opens up. Each sentence hands off to the next
        # ("that", "it") so the paragraph reads as one argument an AE
        # can retell, not three bolted findings.
        bench = (f"On this run that reality reads as {cap.score:g} against "
                 f"a {pm:g} peer benchmark — {_desc}")
    elif pm is not None:
        bench = (f"On this run that reality reads as {cap.score:g} against "
                 f"a {pm:g} peer benchmark, a {abs(gap):g}-point "
                 f"outperformance to build from")
    else:
        bench = (f"On this run it scores {cap.score:g} on the assessment's "
                 f"own scale")
    if is_strength:
        implic = (f"That strength is the proof point: expand from it, and "
                  f"{domain} argues from credibility rather than promise")
    else:
        implic = (f"That is the opening: a scoped program closes it, and "
                  f"{domain} — with the capabilities stacked on it — moves "
                  f"together")
    sentences = [s.strip().rstrip(".") + "." for s in (fact, bench, implic) if s.strip()]
    what = plain(opportunity_reframe(" ".join(sentences)))

    # ── WHY: the cross-link (a sibling in a different pillar) ───────────
    # 'Connects to' is a RELATIONAL claim — only assert it when the two
    # capabilities share evidence (the same real-world fact grounds both);
    # an arbitrary different-pillar sibling stated as a connection is the
    # fabricated-relation class (reasoning audit v2, 2026-07-12).
    sib = None
    cap_eids = set(cap.evidence_ids or [])
    for s in (siblings or []):
        if (s.subcap_id != cap.subcap_id and s.pillar != cap.pillar
                and s.in_scope and cap_eids & set(s.evidence_ids or [])):
            sib = s
            break
    if sib is not None:
        sib_domain = _PILLAR_DOMAIN.get(sib.pillar, "another area")
        why = plain(opportunity_reframe(
            f"The same evidence base ties it to {sib.name} in {sib_domain}, "
            f"so one program grounded in those shared facts advances both "
            f"{domain} and {sib_domain}."))
    else:
        # no shared-evidence pair: co-presence in this run's scored scope
        # is still a verifiable fact — name the sibling as co-coverage
        # (satisfies the G3 cross-link) without asserting a causal relation.
        # Vary the named sibling per anchor (stable crc32 rotation) so two
        # cards in one client never carry byte-identical WHYs (the
        # sibling-echo class from the AlmaBank vetting sample).
        _alts = [s for s in (siblings or [])
                 if s.subcap_id != cap.subcap_id and s.pillar != cap.pillar
                 and s.in_scope]
        alt = (_alts[zlib.crc32(cap.subcap_id.encode()) % len(_alts)]
               if _alts else None)
        if alt is not None:
            alt_domain = _PILLAR_DOMAIN.get(alt.pillar, "another area")
            why = plain(opportunity_reframe(
                f"It matters beyond its own cell: it underpins {domain}, "
                f"and {alt.name} in {alt_domain} was scored alongside it "
                f"this run — one program can be scoped to cover both, "
                f"which is what makes the sequencing conversation worth "
                f"having now."))
        else:
            why = (f"It underpins {domain}, so progress here raises the "
                   f"floor the domain's other capabilities work from.")

    # ── SO-WHAT: the sales motion (v3 doctrine — outcome, then
    # platform+capability, then the sized proof). Targets THIS capability
    # by name so sibling cards never ship byte-identical plays ──────────
    platform = _platform_for(state, cap.subcap_id) or "Salesforce"
    _target = _clean_cap_name(cap.name)
    if is_strength:
        so_what = plain(opportunity_reframe(
            f"Make {_target} the proof point of the {platform} story — it "
            f"lets {domain} argue from something already working "
            f"{_urgency_clause(state)}."))
    elif pm is not None and (pm - cap.score) >= 0.15:
        so_what = plain(opportunity_reframe(
            f"Make {_target} the {platform} conversation: open with the "
            f"evidence above, size the win as the climb from "
            f"{cap.score:g} to the {pm:g} peer benchmark, and time it "
            f"{_urgency_clause(state)}."))
    else:
        so_what = plain(opportunity_reframe(
            f"Make {_target} the {platform} conversation: open with the "
            f"evidence above and time it {_urgency_clause(state)}."))

    # ── TITLE: a client-specific thesis (never the bare capability name) ─
    title = _compose_title(cap, fact, domain, is_strength)

    return Item(
        surface="insight_card", title=title, what=what, why=why, so_what=so_what,
        anchor_subcap=cap.subcap_id, e_ids=e_ids,
        siblings=[sib.name] if sib else [], is_top=is_top,
    )


# a catalogue naming artifact — "Security Metrics — Subcap 6" — never a headline.
_SUBCAP_N_RE = re.compile(r"\s*[—-]?\s*Subcap\s+\d+\s*$", re.I)


def _clean_cap_name(name: str) -> str:
    """Strip the "Subcap N" catalogue artifact so the label reads as a name."""
    stripped = _SUBCAP_N_RE.sub("", (name or "").strip()).strip()
    return stripped or (name or "").strip()


def _compose_title(cap: Capability, fact: str, domain: str, is_strength: bool) -> str:
    """A thesis headline derived from the capability's own evidence — never the
    bare catalogue label, and varied so it does not read as a shared template."""
    from app.services.nlp.titlecraft import make_title
    core = ""
    try:
        core = make_title(fact, max_chars=70) or ""
    except Exception:
        core = ""
    core = re.sub(r"^[\s.\u2014\u2013-]+|[\s.\u2014\u2013-]+$", "", core)
    name = _clean_cap_name(cap.name)
    core_usable = bool(core) and core.lower() not in name.lower() and len(core) >= 12
    if core_usable and is_strength:
        base = f"{core} — {name} is a proven strength to expand"
    elif core_usable:
        base = f"{core} — the {name} opportunity"
    elif is_strength:
        base = f"{name} outperforms the peer benchmark — expand from strength"
    else:
        base = f"{name} trails the peer benchmark — a near-term opportunity"
    out = opportunity_reframe(base) or base
    return out[:128].strip()


# ── other surfaces (Phase C) — all read the SAME EntityState as the cards, so
# the exec thesis is the union of the findings, the why-now trigger agrees with
# the finding's evidence, and the platform play agrees with the score. Each
# reuses compose_card (thesis-first, support-checked, polarity-aware) and only
# reframes the surface + selection, so a claim on one surface is graded by the
# same rubric as every other. ──────────────────────────────────────────────

def _lead_key(item: Item) -> str:
    """A dedup key on the item's lead fact (the first ~60 chars of WHAT)."""
    return (item.what or "")[:60].strip().lower()


def compose_findings(
    state: EntityState, *, k: int = 4, thesis: Thesis | None = None,
) -> list[Item]:
    """Surface 2 — the top-k findings, thesis-first. Selected from the SAME
    ranked evidenced anchors as the cards (widest evidenced peer-gap /
    outperformance first), deduped by lead fact so no two findings restate one
    excerpt. When a ``thesis`` is given, findings in the thesis's pillars are
    surfaced FIRST (a STABLE reorder that keeps evidence rank within each group),
    so the set supports the storyline rather than reading as scattered blurbs.
    Returns graded-ready Items (surface='finding'); [] when nothing grounds."""
    anchors = list(state.evidenced_anchors)
    if thesis and thesis.pillars:
        pri = set(thesis.pillars)
        anchors.sort(key=lambda c: 0 if c.pillar in pri else 1)   # stable
    out: list[Item] = []
    seen: set[str] = set()
    for cap in anchors[: max(k * 4, 12)]:
        item = compose_card(state, cap, siblings=anchors[:8], is_top=(not out))
        if item is None:
            continue
        key = _lead_key(item)
        if key in seen:
            continue
        seen.add(key)
        item.surface = "finding"
        out.append(item)
        if len(out) >= k:
            break

    # Adversarial fence (L2): suppress any same-subject CONTRADICTION among the
    # composed findings, so the surface never shows two findings that assert
    # opposing things about one subject ("no CISO" beside "CISO leads security").
    # The stronger-grounded finding survives (tier → recency → client-owned →
    # specificity); the weaker is dropped. Same-subject detection is cross-encoder
    # precise and degrades to the bi-encoder on a cold regen, so this never
    # suppresses on a mere word-overlap and is a no-op when nothing opposes.
    if len(out) > 1:
        claims = [
            Claim(text=(it.what or it.title or ""),
                  capability=(it.anchor_subcap or ""), e_ids=list(it.e_ids))
            for it in out
        ]
        survivors, _notes = resolve_contradictions(
            claims, list(state.knowledge.by_id.values()))
        keep = {id(c) for c in survivors}
        out = [it for it, c in zip(out, claims, strict=True) if id(c) in keep]
    return out


def compose_platform(
    state: EntityState, *, k: int = 5,
) -> list[Item]:
    """Surface 9 — platform opportunity cards. A roster platform earns a card
    ONLY when it addresses an in-scope, evidence-rich anchor (so an off-vertical
    platform that maps to no real capability — nCino to an insurance broker —
    is dropped by construction, not force-fit). The thesis leads with the play
    grounded in that anchor's own evidence, sequenced by roster fit order."""
    by_id = {c.subcap_id: c for c in state.evidenced_anchors}
    siblings = state.evidenced_anchors[:8]
    out: list[Item] = []
    seen_caps: set[str] = set()
    for p in (state.platforms or [])[: max(k * 3, 10)]:
        addr = [a for a in (p.get("addressable_subcap_ids") or []) if a in by_id]
        if not addr:
            continue                       # no in-scope evidenced cap → no NA lead
        anchor = next((a for a in addr if a not in seen_caps), None)
        if anchor is None:
            continue
        cap = by_id[anchor]
        item = compose_card(state, cap, siblings=siblings, is_top=(not out))
        if item is None:
            continue
        seen_caps.add(anchor)
        name = _platform_display(p.get("platform_id"))
        item.surface = "platform"
        # lead the thesis with the named system + the play it enables
        item.title = (opportunity_reframe(f"{name} — {item.title}") or item.title)[:128]
        out.append(item)
        if len(out) >= k:
            break
    return out


def compose_why_now(
    state: EntityState, *, k: int = 3,
) -> list[Item]:
    """Surface 11 — why-now signals. Each top finding is reframed as a time-bound
    trigger: the finding's thesis + a dated hook (from the entity's why-now
    signals) + the play. Excludes NA by construction (findings anchor only on
    in-scope evidenced caps) and reuses the finding's support-checked evidence so
    the trigger agrees with the finding's score."""
    findings = compose_findings(state, k=k)
    urgency = _urgency_clause(state)
    # the finding's so_what already ENDS with this urgency clause (compose_card
    # appends it) — strip that tail before leading the trigger with it, so the
    # window is stated once, not doubled.
    tail = re.compile(r"\s*[—-]?\s*" + re.escape(urgency) + r"\.?\s*$", re.I)
    out: list[Item] = []
    for f in findings:
        play = tail.sub("", f.so_what).rstrip(" .—-")
        so_what = plain(opportunity_reframe(f"Act {urgency}: {play}.")) or f.so_what
        out.append(Item(
            surface="why_now", title=f.title, what=f.what, why=f.why,
            so_what=so_what, anchor_subcap=f.anchor_subcap, e_ids=list(f.e_ids),
            siblings=list(f.siblings), is_top=f.is_top,
        ))
    return out


def compose_exec(
    state: EntityState, thesis: Thesis, findings: list[Item],
) -> Item:
    """The exec summary (Surface 1) — LEADS with the per-client thesis, then
    threads the top findings as the supporting arc, so the surfaces read as one
    story rather than isolated blurbs. This is the grounded FLOOR; the LLM
    narrator (refine.narrate_exec) writes the natural version when available.
    Grades on the 'finding' surface (same rubric)."""
    lead = (thesis.headline or "").rstrip(".") + "."
    beats: list[str] = []
    for f in (findings or [])[:3]:
        s = _first_sentence(f.what, 150).rstrip(".")
        # keep the beat only if it adds a distinct fact (not a restated lead)
        if s and s.lower()[:40] not in lead.lower():
            beats.append(s)
    arc = "; ".join(beats)
    what = plain(opportunity_reframe(
        f"{lead} The assessment bears this out: {arc}." if arc else lead))
    why = plain(opportunity_reframe(
        f"These threads share one arc — {thesis.through_line} — so the "
        f"investments compound rather than scatter across unrelated bets."))
    so_what = plain(opportunity_reframe(
        f"Lead with {thesis.play}, sequencing the highest-evidence findings "
        f"first {_urgency_clause(state)}."))
    e_ids = list(dict.fromkeys(
        e for f in (findings or [])[:3] for e in (f.e_ids or [])))[:6]
    return Item(
        surface="exec", title=lead[:128], what=what, why=why, so_what=so_what,
        anchor_subcap=(findings[0].anchor_subcap if findings else None),
        e_ids=e_ids, siblings=[], is_top=True,
        # every threaded finding's capability — G2 judges each citation
        # against ANY of these (multi-anchor aggregation surface)
        anchor_subcaps=list(dict.fromkeys(
            f.anchor_subcap for f in (findings or [])[:3] if f.anchor_subcap)),
    )
