"""Shared cross-surface knowledge + adversarial grounding — the anti-silo,
evidence-challenging core of the synthesis AI system (L1+L2 of
GOLD_STANDARD_NLP_ARCHITECTURE.md).

Every surface composer reads ONE cohesive per-entity understanding
(:class:`EntityKnowledge`) instead of re-mining the corpus in isolation: any
script can pull topically-aligned, ownership-checked evidence for a capability
(cohesive, never duplicated), and every claim is CHALLENGED before it may
surface —

  * topical support — the cited evidence must be semantically aligned to the
    claim's capability (else the citation is dropped: kills the
    exec-roster-under-"Speed-to-Lead" misattribution);
  * ownership — a peer/benchmark-owned figure is rejected (peer-NPS fence);
  * contradiction — same-subject opposing claims are detected and RESOLVED
    (tier → recency → client-owned → specificity); the loser is suppressed and
    the resolution recorded, never surfaced as a raw conflict.

Pure-logic and tier-agnostic: uses :class:`~app.services.nlp.semantic.
SemanticIndex` (MiniLM when baked, TF-IDF fallback) so it never raises and works
on a cold regen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.nlp import rerank as _rerank
from app.services.nlp.polarity import signal as _polarity
from app.services.nlp.semantic import SemanticIndex

# Domain opposition: presence vs absence of a role/capability is the most common
# contradiction shape here ("CISO filled" vs "no CISO / leadership gap"), and the
# generic polarity lexicon misses it — so detect it explicitly.
_ABSENCE_RE = re.compile(
    r"\b(lacks?|without(?: an?)?|absent|missing|unfilled|vacan|"
    r"no [a-z]|not yet|does not have|has no|gap\b)", re.I)
_PRESENCE_RE = re.compile(
    r"\b(filled|staffed|in place|deployed|confirmed|established|live|"
    r"operational|already (?:has|runs)|has an? |runs |uses )", re.I)

# ── Peer/benchmark ownership fence ─────────────────────────────────────────
# An excerpt whose SUBJECT is a peer / industry / benchmark figure ("peer median
# NPS is 45", "industry average onboarding is 3 days") is NOT the client's own
# evidence — citing it to ground a client capability is the "peer-NPS"
# misattribution the fence exists to stop. High-precision by design (precision >
# recall — wrongly fencing a client fact is worse than missing a peer figure):
# the peer/benchmark term must LEAD the excerpt's first clause (the subject
# position). A client fact that merely names a benchmark as a trailing COMPARATOR
# ("M1FCU app 2.2/5 — below the industry-standard 4.0", "no CISO, consistent with
# the industry norm") stays client-owned. A client-ownership cue (the client's
# own name or a first-party possessive) short-circuits to owned regardless.
_PEER_LEAD_RE = re.compile(
    r"^\W*(?:the\s+)?(?:"
    r"(?:peer|industry|competitor|market)[\s-]+"
    r"(?:median|average|mean|norm|benchmark|baseline|standard|typical)"
    r"|(?:peers|competitors|other\s+(?:banks|credit\s+unions|institutions|firms))\s+"
    r"(?:typically|generally|on\s+average|average|median|tend\s+to|report|achieve|score)"
    r"|industry(?:[\s-]?wide)?\s+(?:average|median|benchmark|norm|standard)"
    r"|benchmark(?:ed|s)?\b"
    r")",
    re.I)
_CLIENT_CUE_RE = re.compile(
    r"\b(its own|our own|the (?:bank|credit union|company|firm|institution|"
    r"organization|organisation|client)'s|\bwe\b|\bour\b|the client's)",
    re.I)
# split off the leading clause at the first sentence / colon / spaced-dash
# boundary (em-dash U+2014, en-dash U+2013, or hyphen).
_LEAD_SPLIT_RE = re.compile("(?<=[.;:])\\s|\\s[\\u2014\\u2013-]\\s")


def classify_owned(
    excerpt: str, *, entity_name: str | None = None,
) -> bool:
    """Is this excerpt the CLIENT's own evidence (True) or a peer/benchmark figure
    (False)? Defaults True (the corpus is overwhelmingly first-party); returns
    False ONLY for a high-confidence peer/benchmark statement that LEADS with the
    benchmark as its subject and carries no client-ownership framing — the
    peer-NPS fence. Pure + never raises."""
    t = (excerpt or "").strip()
    if not t:
        return True
    # A client-ownership cue means the sentence is ABOUT the client (even if it
    # cites a peer as comparison) → the client's own evidence.
    first = (entity_name or "").split()
    if first and len(first[0]) >= 3 and re.search(
            r"\b" + re.escape(first[0]) + r"\b", t, re.I):
        return True
    if _CLIENT_CUE_RE.search(t):
        return True
    # Only the LEADING clause decides ownership — a benchmark named as a trailing
    # comparator does not make a client fact peer-owned.
    lead = _LEAD_SPLIT_RE.split(t, maxsplit=1)[0]
    return not bool(_PEER_LEAD_RE.match(lead))


@dataclass
class Evidence:
    e_id: str
    text: str
    tier: int = 8            # 1 (best) .. 8 (weakest/undated)
    year: int | None = None  # publication/event year, when known
    owned: bool = True       # the client's own evidence, not a peer/benchmark


@dataclass
class Claim:
    text: str
    capability: str                              # canonical subcap/label the claim is about
    e_ids: list[str] = field(default_factory=list)
    kind: str | None = None                      # optional surface hint (finding/card/…)
    support: float = 0.0                          # filled by challenge()
    verdict: str = "unchecked"                    # grounded | ungrounded | unchecked


def _best_tier(claim: Claim, by_id: dict[str, Evidence]) -> int:
    tiers = [by_id[e].tier for e in claim.e_ids if e in by_id and by_id[e].tier]
    return min(tiers) if tiers else 8


def _latest_year(claim: Claim, by_id: dict[str, Evidence]) -> int:
    ys = [by_id[e].year for e in claim.e_ids if e in by_id and by_id[e].year]
    return max(ys) if ys else 0


class EntityKnowledge:
    """One cohesive per-entity understanding, read by every surface composer."""

    def __init__(self, evidence: list[Evidence],
                 preferred_eids: frozenset[str] = frozenset()) -> None:
        self.by_id: dict[str, Evidence] = {e.e_id: e for e in evidence}
        # Learned preferred evidence (compose-time prior, B) — the default boost
        # set for supporting_evidence when a caller doesn't override per call.
        self.preferred_eids: frozenset[str] = frozenset(preferred_eids or frozenset())
        self._idx = SemanticIndex()
        self._idx.fit([(e.e_id, e.text) for e in evidence])
        # exact-term recall twin (BM25): MiniLM under-weights rare exact
        # tokens (product names, regulators, acronyms) — the union recall
        # catches both paraphrase and exact-name material; the
        # cross-encoder stays the judge.
        from app.services.nlp.bm25 import BM25Index
        self._bm25 = BM25Index()
        self._bm25.fit([(e.e_id, e.text) for e in evidence])

    def supporting_evidence(
        self, capability: str, k: int = 5, min_score: float = 0.30,
        owned_only: bool = True, preferred_eids: frozenset[str] | None = None,
        boost: float = 0.15,
    ) -> list[tuple[str, float]]:
        """Topically-ranked, ownership-checked evidence for a capability — the
        cohesive cross-script retrieval primitive (no duplication, no silos).

        Hybrid retrieve-then-rerank-then-diversify: bi-encoder AND BM25
        RECALL a wide candidate union at a low floor (paraphrase + exact
        term); the cross-encoder (rerank.py) re-scores each pair for
        genuine SUPPORT and the fused, calibrated score both ranks and
        gates; MMR then displaces near-duplicate excerpts so the k slots
        carry BREADTH, not one fact five times. Degrades to the exact
        bi-encoder ordering + floor when the cross-encoder tier is absent
        (cold regen / lexical-forced test).

        ``preferred_eids`` (2026-07-14, B): learned preferred evidence from the
        compose-time prior — a matching in-corpus row gets ``+boost`` so the
        pack composers lean toward what past HELPFUL answers relied on, the same
        additive re-rank the RAG path applies. Cohort-safe: only evidence this
        entity actually has can be boosted."""
        pref = self.preferred_eids if preferred_eids is None else preferred_eids

        def _boost(hits: list[tuple[str, float]]) -> list[tuple[str, float]]:
            if not pref or not hits:
                return hits
            out = [(e, s + boost if e in pref else s) for e, s in hits]
            out.sort(key=lambda t: t[1], reverse=True)
            return out
        seen: dict[str, float] = {}
        for eid, cos in self._idx.top_k(
            capability, max(k * 4, 12), min_score=min(min_score, 0.12),
        ):
            seen[eid] = cos
        for eid, bs in self._bm25.top_k(capability, max(k * 2, 8),
                                        min_score=0.35):
            # scaled into the cosine recall band; the CE re-scores anyway
            seen.setdefault(eid, 0.12 + 0.2 * bs)
        recalled: list[tuple[str, float]] = []
        for eid, cos in sorted(seen.items(), key=lambda t: -t[1]):
            ev = self.by_id.get(eid)
            if ev is None or (owned_only and not ev.owned):
                continue
            recalled.append((eid, cos))
        if not recalled:
            return []
        reranked = _rerank.rerank(
            capability,
            [(eid, self.by_id[eid].text, cos) for eid, cos in recalled],
        )
        if reranked is None:  # cross-encoder unavailable → original behaviour
            base = [(eid, cos) for eid, cos in recalled if cos >= min_score]
            return _boost(base)[:k]
        kept = _boost([(eid, sup) for eid, sup in reranked if sup >= min_score])
        return self._mmr(kept, k)

    def _mmr(self, ranked: list[tuple[str, float]], k: int,
             lam: float = 0.72, dup_ceiling: float = 0.92) -> list[tuple[str, float]]:
        """Maximal-marginal-relevance selection over reranked evidence:
        each slot maximizes support MINUS similarity to what's already
        chosen, so five near-identical excerpts can't crowd out breadth.
        A candidate above ``dup_ceiling`` cosine to a chosen item is a
        restatement, not corroboration — excluded outright (no support
        score buys back a duplicate), with lower-ranked items backfilling
        only when nothing diverse is left. Identity on the lexical
        fallback (no vectors) or tiny lists."""
        if len(ranked) <= 2 or k <= 1:
            return ranked[:k]
        vecs = {eid: self._idx.vector(eid) for eid, _ in ranked}
        if any(v is None for v in vecs.values()):
            return ranked[:k]
        chosen: list[tuple[str, float]] = [ranked[0]]
        pool = ranked[1:]
        skipped_dups: list[tuple[str, float]] = []
        while pool and len(chosen) < k:
            best_i, best_val = -1, -1e9
            for i, (eid, sup) in enumerate(pool):
                red = max(float(vecs[eid] @ vecs[ceid]) for ceid, _ in chosen)
                if red >= dup_ceiling:
                    continue
                val = lam * sup - (1.0 - lam) * red
                if val > best_val:
                    best_i, best_val = i, val
            if best_i < 0:  # only near-duplicates remain
                skipped_dups.extend(pool)
                break
            # migrate newly-revealed duplicates out so the loop shrinks
            chosen.append(pool.pop(best_i))
        for item in skipped_dups:  # backfill: k slots still beat empty ones
            if len(chosen) >= k:
                break
            chosen.append(item)
        return chosen[:k]

    def challenge(self, claim: Claim, min_support: float = 0.30) -> Claim:
        """Drop cited E-IDs that don't resolve, are peer-owned, or aren't
        topically aligned to the claim's capability; set support + verdict."""
        cap = (claim.capability or claim.text or "").strip()
        owned = [
            (eid, ev) for eid in claim.e_ids
            if (ev := self.by_id.get(eid)) is not None and ev.owned
        ]
        # cross-encoder-verified, calibrated support — computed for ALL of this
        # claim's citations in ONE batched call (rerank.support_scores), not one
        # cross-encoder call per citation. Raw bi-encoder cosine when the re-rank
        # tier is absent/budget-spent. This is what drops a topical-but-
        # unsupported citation the bare cosine would have kept.
        items = [(ev.text, self._idx.relevance(cap, ev.text)) for _eid, ev in owned]
        sups = _rerank.support_scores(cap, items)
        kept: list[str] = []
        best = 0.0
        for (eid, _ev), rel in zip(owned, sups, strict=True):
            if rel >= min_support:
                kept.append(eid)
                best = max(best, rel)
        claim.e_ids = kept
        claim.support = round(best, 3)
        claim.verdict = "grounded" if kept else "ungrounded"
        return claim

    def is_supported(self, text: str, capability: str, min_support: float = 0.30) -> bool:
        """Would this narrative sentence be grounded by the entity's evidence?"""
        hits = self.supporting_evidence(capability, k=1, min_score=min_support, owned_only=True)
        if not hits:
            return False
        return self._idx.relevance((capability + " " + text).strip(), self.by_id[hits[0][0]].text) >= min_support


def _same_subject(idx: SemanticIndex, a: str, b: str, threshold: float) -> bool:
    """Do two claims speak to the SAME subject? The bi-encoder cosine RECALLS
    relatedness; the cross-encoder then re-scores the pair JOINTLY so a mere
    word-overlap (e.g. two unrelated claims that both say "member") does not read
    as same-subject and trigger a spurious contradiction suppression. Degrades to
    the raw bi-encoder cosine when the cross-encoder tier is cold (zero
    regression — ``support_score`` returns ``bi_cos`` unchanged)."""
    cos = idx.relevance(a, b)
    return _rerank.support_score(a, b, cos) >= threshold


def _opposes(a: str, b: str) -> bool:
    """Do these two same-subject claims assert opposing things? Presence-vs-
    absence of a capability/role first (the dominant shape), then generic
    polarity opposition as a fallback."""
    aa, ab = bool(_ABSENCE_RE.search(a)), bool(_ABSENCE_RE.search(b))
    pa, pb = bool(_PRESENCE_RE.search(a)), bool(_PRESENCE_RE.search(b))
    if (ab and pa and not aa) or (aa and pb and not ab):
        return True
    return {_polarity(a), _polarity(b)} == {"positive", "negative"}


def resolve_contradictions(
    claims: list[Claim], evidence: list[Evidence], sim_threshold: float = 0.55,
) -> tuple[list[Claim], list[str]]:
    """Detect same-subject opposing claims and resolve them so only the
    strongest-grounded survives. Winner = better tier → more recent → client-
    owned → more specific. Returns (surviving_claims, resolution_notes)."""
    by_id = {e.e_id: e for e in evidence}
    idx = SemanticIndex()
    idx.fit([(i, c.text) for i, c in enumerate(claims)])
    suppressed: set[int] = set()
    notes: list[str] = []

    def strength(c: Claim) -> tuple:
        # higher is better: lower tier number, later year, owned, longer/specific
        owned = any(by_id[e].owned for e in c.e_ids if e in by_id) or not c.e_ids
        return (-_best_tier(c, by_id), _latest_year(c, by_id), int(owned), len(c.text))

    for i in range(len(claims)):
        if i in suppressed:
            continue
        for j in range(i + 1, len(claims)):
            if j in suppressed:
                continue
            a, b = claims[i], claims[j]
            if not _same_subject(idx, a.text, b.text, sim_threshold):
                continue
            if not _opposes(a.text, b.text):
                continue
            win, lose = (i, j) if strength(a) >= strength(b) else (j, i)
            suppressed.add(lose)
            subject = claims[win].capability or claims[win].text[:40]
            notes.append(
                f"contradiction on '{subject}': kept the stronger-grounded claim "
                f"(better tier / more recent / client-owned), suppressed the weaker one"
            )
    survivors = [c for k, c in enumerate(claims) if k not in suppressed]
    return survivors, notes


def build_entity_knowledge(
    excerpt_by_eid: dict[str, str],
    tier_by_eid: dict[str, int] | None = None,
    peer_eids: frozenset[str] | set[str] = frozenset(),
    preferred_eids: frozenset[str] | set[str] = frozenset(),
) -> EntityKnowledge | None:
    """Assemble a per-entity :class:`EntityKnowledge` from the run's evidence
    corpus so the pack composers (exec summary, why-now, platform) can CHALLENGE
    a candidate fact — cross-encoder-verified support + peer-ownership fence —
    the same way the insight-card path does, before weaving it (2026-07-14
    audit: those composers relied on a lighter lexical relevance check only).

    Returns None when there is nothing to fit; the caller then skips the
    challenge and never blocks (self-heal / graceful degrade). Evidence whose
    id is in ``peer_eids`` is marked ``owned=False`` so a peer/benchmark row can
    never be the sole support for a client claim. Never raises."""
    tier_by_eid = tier_by_eid or {}
    try:
        ev = [
            Evidence(e_id=str(eid), text=str(txt),
                     tier=int(tier_by_eid.get(eid) or 8),
                     owned=eid not in peer_eids)
            for eid, txt in (excerpt_by_eid or {}).items() if txt
        ]
        if not ev:
            return None
        # Cohort fence: only boost evidence this entity actually has.
        corpus = {e.e_id for e in ev}
        pref = frozenset(str(p) for p in (preferred_eids or ())) & corpus
        return EntityKnowledge(ev, preferred_eids=pref)
    except Exception:
        return None


def fact_supported(
    ek: EntityKnowledge | None, fact: str, capability: str,
    eids: list[str] | None = None, min_support: float = 0.30,
) -> bool:
    """None-safe adversarial gate: does the woven fact's CITED evidence actually
    support ``capability``? Runs the same :meth:`EntityKnowledge.challenge` the
    insight-card path uses — the cited evidence must clear the (cross-encoder-
    calibrated, or lexical when the tier is cold) support floor for this
    capability, and peer-owned rows are fenced out. A bio/roster line cited
    under a technical capability fails; the genuine finding passes.

    Returns True when ``ek`` is None / inputs are empty / no ids are cited
    (never blocks on a missing tier or an un-cited fact). Never raises."""
    if ek is None or not fact or not capability or not eids:
        return True
    try:
        claim = Claim(text=fact, capability=capability, e_ids=list(eids))
        ek.challenge(claim, min_support=min_support)
        return claim.verdict == "grounded"
    except Exception:
        return True
