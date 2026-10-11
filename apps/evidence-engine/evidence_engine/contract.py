"""The evidence card contract (docs/CARD-CONTRACT.md), enforced.

`item` is the `register_evidence` argument verbatim and the exact flag set
`engine.cli evidence` takes; `provenance` is the engine's. Every rule the
two write paths apply BEFORE they fetch is applied here, so a card the
engine emits is one they will not refuse on shape. Vocabulary is the
repo's: the five tiers, the four claim labels, the six-word recency ladder.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from dataclasses import dataclass, field, asdict

from .textnorm import normalise, word_count

TIERS = ("T1", "T2", "T3", "T4", "T5")
FACT_TIERS = ("T1", "T2")
CLAIM_LABELS = ("FACT", "INFERENCE", "HYPOTHESIS", "CEILING_ESTIMATE")
#: months before the reference date; the sixth word is for undated/future.
RECENCY_LADDER = (("CURRENT", 12), ("RECENT", 24), ("DATED", 36), ("STALE", 48))
RECENCY_ARCHIVAL = "ARCHIVAL"
RECENCY_UNVERIFIED = "UNVERIFIED"
RECENCY_WORDS = tuple(w for w, _ in RECENCY_LADDER) + (RECENCY_ARCHIVAL, RECENCY_UNVERIFIED)

SOURCE_TYPES = ("regulator", "filing", "entity_owned", "trade_press", "news",
                "academic", "vendor", "job_board", "review_site", "other")
URL_STATUS = ("live", "archived")
ENTITY_MATCH = ("confirmed", "probable", "ambiguous")
FACETS = ("works", "fails", "value", "contradicts", "corroborates")
LADDER_RUNGS = ("entity_site", "regulator", "filings", "trade_press", "news",
                "careers", "academic", "other")

EXCERPT_MIN, EXCERPT_MAX = 50, 500
#: a preference, not a cap (docs/DISCOVERY.md §1)
EXCERPT_TARGET_WORDS = 40
SOURCE_NAME_MAX = 160
#: the connector's hard-clip signature width (packages/shared/excerpt_clip.py)
CLAUSE_CLIP_WIDTH = 140
#: Widths the connector clipped at historically (golden v1 carries 80/100/120
#: clips too); the engine refuses every one, the connector only the current.
CLAUSE_CLIP_WIDTHS = (80, 100, 120, CLAUSE_CLIP_WIDTH)
CLAUSE_SPLIT = " | "


def claim_label_for(tier: str) -> str:
    """The label the tier LICENSES — the ledger's own derivation
    (engine/contract.py claim_label_for)."""
    return "FACT" if tier in FACT_TIERS else "INFERENCE"


def recency_band(published: str | None, reference: _dt.date | None = None) -> str:
    """Six-word ladder against the run's reference date (default today).
    Undated or future ⇒ UNVERIFIED; the arithmetic is the connector's
    (`register._recency_band`): whole months, inclusive upper bounds."""
    d = iso_date(published)
    if d is None:
        return RECENCY_UNVERIFIED
    ref = reference or _dt.date.today()
    if d > ref:
        return RECENCY_UNVERIFIED
    months = (ref.year - d.year) * 12 + (ref.month - d.month)
    for word, hi in RECENCY_LADDER:
        if months <= hi:
            return word
    return RECENCY_ARCHIVAL


def iso_date(v) -> _dt.date | None:
    if v is None:
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    s = str(v).strip()
    try:
        return _dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def clause_truncated(excerpt: str, width: int | None = None) -> str | None:
    """The connector's own check (excerpt_clip.clause_truncated), copied, over
    every historical clip width unless one is named."""
    if not excerpt:
        return None
    widths = (width,) if width else CLAUSE_CLIP_WIDTHS
    for w in widths:
        if any(len(c) == w and c[-1:].isalnum() for c in str(excerpt).split(CLAUSE_SPLIT)):
            return f"excerpt_clause_truncated: clause of exactly {w} chars ends mid-word"
    return None


_TERMINAL = re.compile(r"[.!?…]['\")\]]*$|[%)\]\"]$|\d$")


def sentence_complete(excerpt: str) -> bool:
    """Starts like a sentence (not a lower-case fragment, not punctuation)
    and ends on a terminal mark, a closing bracket/quote, a figure or a
    percent sign. A span cut inside a word or a clause fails."""
    s = (excerpt or "").strip()
    if not s:
        return False
    if s[-1] in ",;:-–—/(" or s.endswith(" and") or s.endswith(" or") or s.endswith(" the"):
        return False
    if not _TERMINAL.search(s):
        return False
    first = s[0]
    return first.isupper() or first.isdigit() or first in "\"'(["


@dataclass
class Item:
    source_name: str
    source_url: str
    excerpt: str
    tier: str
    published_date: str | None = None
    claim_type: str | None = None
    linked_subcap_ids: list = field(default_factory=list)
    origin: str = "producer"

    def __post_init__(self):
        if self.claim_type is None:
            self.claim_type = claim_label_for(self.tier)


@dataclass
class Provenance:
    url_status: str = "live"
    original_url: str | None = None
    archive_timestamp: str | None = None
    retrieved: str = ""
    recency: str = RECENCY_UNVERIFIED
    source_type_hint: str = "other"
    tier_basis: str = ""
    excerpt_offsets: tuple = (0, 0)
    content_hash: str = ""
    context_handle: str = ""
    facet_hints: list = field(default_factory=list)
    query_ids: list = field(default_factory=list)
    origin_cluster: str = ""
    syndication_count: int = 1
    relevance: float = 0.0
    entity_match: str = "ambiguous"
    entity_match_basis: str = ""
    ladder_rung: str = "other"
    via: str = ""


@dataclass
class Card:
    card_id: str
    item: Item
    provenance: Provenance

    def to_dict(self, provenance: str = "full") -> dict:
        d = {"card_id": self.card_id, "item": asdict(self.item)}
        p = asdict(self.provenance)
        p["excerpt_offsets"] = list(p["excerpt_offsets"])
        if provenance == "minimal":
            p = {k: p[k] for k in ("url_status", "recency", "entity_match",
                                   "origin_cluster", "context_handle")}
        d["provenance"] = p
        return d


def card_id_for(source_url: str, excerpt: str) -> str:
    h = hashlib.sha256(f"{source_url}|{normalise(excerpt)}".encode("utf-8")).hexdigest()
    return "EV-" + h[:8]


def context_handle_for(content_hash: str, start: int, end: int) -> str:
    h = hashlib.sha256(f"{content_hash}|{start}|{end}".encode("utf-8")).hexdigest()
    return "CTX-" + h[:8]


def item_problems(item: dict, *, own_hosts: set[str] | None = None,
                  abbreviations: dict | None = None) -> list[str]:
    """Every refusal `register_evidence` / `ledger.append_evidence` would
    apply to this item BEFORE fetching, as a list of reasons (empty = clean)."""
    out: list[str] = []
    excerpt = str(item.get("excerpt") or "")
    url = item.get("source_url")
    tier = str(item.get("tier") or "")
    claim = str(item.get("claim_type") or "")
    origin = str(item.get("origin") or "producer")
    name = str(item.get("source_name") or "")
    if not name:
        out.append("source_name: required")
    if len(name) > SOURCE_NAME_MAX:
        out.append(f"source_name: {len(name)} chars > {SOURCE_NAME_MAX}")
    if not url:
        out.append("source_url: required — unsourced evidence does not exist")
    if not (EXCERPT_MIN <= len(excerpt) <= EXCERPT_MAX):
        out.append(f"excerpt_length: {len(excerpt)} chars — {EXCERPT_MIN}-{EXCERPT_MAX} required")
    clipped = clause_truncated(excerpt)
    if clipped:
        out.append(clipped)
    if not sentence_complete(excerpt):
        out.append("excerpt_not_sentence_complete: span must start and end at sentence boundaries")
    if tier not in TIERS:
        out.append(f"tier: {tier!r} not in {TIERS}")
    if claim not in CLAIM_LABELS:
        out.append(f"claim_type: {claim!r} not in {CLAIM_LABELS}")
    if claim == "FACT" and tier not in FACT_TIERS:
        out.append(f"fact_tier: FACT on a {tier} source (ET-10)")
    if origin != "producer":
        out.append(f"origin: engine emits 'producer' only, got {origin!r}")
    if item.get("linked_subcap_ids"):
        out.append("linked_subcap_ids: the engine never links cells")
    pd = item.get("published_date")
    if pd is not None:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(pd)) or iso_date(pd) is None:
            out.append(f"published_date: {pd!r} is not ISO YYYY-MM-DD")
        elif iso_date(pd) > _dt.date.today():
            out.append(f"published_date: {pd!r} is in the future")
    if own_hosts and url and tier == "T1":
        host = host_of(url)
        if any(host == h or host.endswith("." + h) for h in own_hosts):
            out.append("own_domain_t1: the entity's own domain is never T1")
    if abbreviations:
        for abbr in abbreviations:
            if re.search(rf"(?<![A-Za-z]){re.escape(abbr)}(?![A-Za-z])", name):
                out.append(f"source_name_abbreviation: {abbr!r} must be spelled out in a label")
    return out


def host_of(url: str | None) -> str:
    m = re.match(r"^[a-z]+://(?:www\.)?([^/:?#]+)", url or "", flags=re.I)
    return (m.group(1) if m else "").lower().rstrip(".")


def item_to_engine_flags(card: dict, *, subcaps: list[str], actor: str | None = None) -> list[str]:
    """The exact `engine.cli evidence` argument list for this card's item,
    plus the cells the AGENT decided. Pure; a test asserts the parser
    accepts it."""
    item = card["item"]
    argv = ["evidence", "--source", item["source_name"], "--url", item["source_url"],
            "--tier", item["tier"], "--excerpt", item["excerpt"],
            "--claim-type", item["claim_type"], "--origin", "public"]
    if item.get("published_date"):
        argv += ["--published", item["published_date"]]
    for s in subcaps:
        argv += ["--subcap", s]
    if actor:
        argv += ["--actor", actor]
    return argv


def estimate_tokens(obj) -> int:
    """4 chars/token heuristic over compact JSON; `tiktoken` when present."""
    s = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    try:
        import tiktoken  # type: ignore
        return len(tiktoken.get_encoding("cl100k_base").encode(s))
    except Exception:  # noqa: BLE001
        return max(1, len(s) // 4)


def excerpt_word_pressure(excerpt: str) -> float:
    """0 at or under the target, rising linearly to 1 at 2× the target."""
    w = word_count(excerpt)
    if w <= EXCERPT_TARGET_WORDS:
        return 0.0
    return min(1.0, (w - EXCERPT_TARGET_WORDS) / EXCERPT_TARGET_WORDS)
