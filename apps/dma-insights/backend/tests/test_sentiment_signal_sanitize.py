"""Sentiment signal sanitizer — the fin.sentiment_fragments family (2026-07-06).

The deploy-review audit (qa_deploy_review_audit.check_financial) flags any
firmographics.sentiment.sources[].signal that reads as a mid-sentence fragment:
its _WORD_FRAGMENT re matches a signal STARTING with a lowercase word (<=13
word-chars) + optional punctuation + space, unless it begins ios/app/enps. The
build carried 35 such rows across two classes:

  (A) raw Clay/CSV "key: value, key: value" dumps that survived because
      derive_sentiment's fill-if-empty gate skipped entities that already had a
      parsed sentiment blob (the raw sources passed straight into the pack);
  (B) prose clips the extractor grabbed mid-clause or off-topic (tech-stack
      lists, leadership bios, QA-meta).

These pin the sanitizer (derive_sentiment._sanitize / _sanitize_sources, run over
EVERY blob by normalize_sentiment's Pass 2): a kv-dump is reformatted into a
readable, source-named sentence when its keys are genuine sentiment ratings (else
dropped); a prose fragment is re-clipped to a capitalised sentence boundary when
it truly concerns sentiment (else dropped); a real rating is never discarded, a
number never invented.
"""
from __future__ import annotations

import re

from app.scripts.derive_sentiment import (
    _KV_HEAD,
    _sanitize,
    _sanitize_sources,
    normalize_sentiment,
)

# EXACT copy of the audit's fragment gate — keep in lockstep with
# qa_deploy_review_audit._WORD_FRAGMENT so the assertion is the real ceiling.
_WORD_FRAGMENT = re.compile(r"^[a-z][\w]{0,12}[,;:]?\s")
_AUDIT_OK = ("ios ", "app ", "enps")


def _is_fragment(sig: str) -> bool:
    return bool(sig and _WORD_FRAGMENT.match(sig)
               and sig[:4].lower() not in _AUDIT_OK)


# ── class (A): raw "key: value" dumps ────────────────────────────────────────
# (source, signal) exactly as they shipped in the committed pack.
_CLASS_A = [
    ("Glassdoor", "overall: 2.5/5 (250 reviews), work_life_balance: 2.6/5, culture_values: 2.2/5"),
    ("App Ratings", "ios: 4.3 stars, android: 3.9 stars, mixed_rating_source: 3.3/5 (53 reviews)"),
    ("Glassdoor", "overall: 3.5, reviews: 56, culture_values: 3.9"),
    ("Indeed", "overall: 5.0, ceo_approval: 0.5381, recommend_friend: 0.566"),
    ("Facebook", "recommend: 0.82, reviews: 27"),
    (None, "rating: 4.79, reviews: 31000, note: Strong but UX complaints on new app transition"),
    ("Employee Indeed", "overall: 5.0, culture: 5.0, management: 5.0"),
    ("Glassdoor", "reviews: 1, note: 1 review only"),
    ("Exa Ratings", "work_life: 2.5, compensation: 3.8, culture: 2.9"),
]
# non-sentiment kv-dumps → dropped wholesale (financial snapshot / tally / noise)
_CLASS_A_DROP = [
    "market_cap_B: 14.26, 1yr_high: 122.6, 1yr_low: 71.0",
    "yes: 6, no: 0, pct: 100%",
    "yes: 2, no: 4, pct: 33%",
    "difficulty: MEDIUM, experience: EXCELLENT, length: TWO_WEEKS",
    "lunarcrush: Limited data — institutional banking topic, low social volume",
]

# ── class (B): mid-clause / off-topic prose clips ────────────────────────────
# salvageable (genuine sentiment, just clipped mid-clause) → cleaned, kept.
_CLASS_B_KEEP = [
    "best financial institutions in the state — something only 2.8% of banks can "
    "claim; recognition comes directly from customers — customer satisfaction",
    "show complaints about online banking reliability, long customer service hold "
    "times, IBTX conversion data loss issues",
    "include M&A announcements + Direct VestGen Glassdoor search returned NO results "
    "for the parent VestGen Wealth Partners brand",
]
# genuinely off-topic (tech-stack / bio / QA-meta / product list) → dropped.
_CLASS_B_DROP = [
    "detected including Salesforce CRM, Microsoft Dynamics CRM, Temenos Transact, Fiserv",
    "with Coppin State, Johns Hopkins, Towson, Loyola, UMB, Morgan State",
    "income $140.9M, EPS $2.22; NIM expanded 11bps to 2.91% Period end loans $24.9B",
    "actions against Fisher Investments found in 2024-2025 No FINRA disciplinary actions",
    "maintains Business Continuity Plan, Disaster Recovery, BIA No NCUA enforcement actions",
    "to M1FCU 2024 from State Employees CU NC where she was Associate EVP",
    "works with CIO on strategy, model portfolios, risk management Wellington-Altus",
    "case advisory materials, client-provided documents, meeting notes, 44 T3 items",
    "category is entirely NULL (empty), and the tech_customer_management category",
    "offers PayAnyone, Sound-to-Sound transfers instead Indicates possible pivot away from Zelle",
    "community FIs offering text, video, secure chat, co-browsing, screen sharing — Eltropy",
    "philosophy IMA Finance Group confirmed Applied Systems customer; gained accessibility",
]


def test_sentiment_class_a_kv_dumps_become_clean_sentences() -> None:
    for source, sig in _CLASS_A:
        assert _is_fragment(sig), f"fixture drifted — not a fragment: {sig!r}"
        clean = _sanitize(sig, source)
        assert clean, f"sentiment kv-dump wrongly dropped: {sig!r}"
        assert not _is_fragment(clean), f"still a fragment: {clean!r}"
        # no raw "key: value" head survives (colons removed on reformat)
        assert not _KV_HEAD.match(clean), f"kv head survived: {clean!r}"
        assert ": " not in re.split(r"[.;]", clean)[0] or clean[0].isupper()


def test_sentiment_non_sentiment_kv_dumps_are_dropped() -> None:
    # financial snapshots, yes/no tallies, interview noise, coverage caveats:
    # the signal is not sentiment → dropped (no fabricated rating substituted).
    for sig in _CLASS_A_DROP:
        assert _sanitize(sig, "Some Source") is None, f"should drop: {sig!r}"


def test_sentiment_class_b_salvageable_clips_are_reclipped() -> None:
    for sig in _CLASS_B_KEEP:
        assert _is_fragment(sig), f"fixture drifted — not a fragment: {sig!r}"
        clean = _sanitize(sig, "Glassdoor")
        assert clean, f"genuine sentiment clip wrongly dropped: {sig!r}"
        assert not _is_fragment(clean), f"still a fragment: {clean!r}"
        assert clean[0].isupper() or clean[0].isdigit()


def test_sentiment_class_b_offtopic_clips_are_dropped() -> None:
    for sig in _CLASS_B_DROP:
        assert _sanitize(sig, "Glassdoor") is None, f"off-topic should drop: {sig!r}"


def test_sentiment_sanitize_sources_drops_signal_but_keeps_real_rating() -> None:
    # class-B off-topic clip on a row WITH a real rating → keep row, drop signal
    # (a real number is never discarded); no real rating → drop the whole row.
    rows = _sanitize_sources([
        {"source": "Employee reviews", "rating": "3.8/5",
         "signal": "detected including Salesforce CRM, Temenos Transact, Fiserv"},
        {"source": "Better Business Bureau",
         "signal": "with Coppin State, Johns Hopkins, Towson, Loyola"},
        {"source": "Net Promoter Score", "rating": "6/5",   # impossible → not real
         "signal": "offers PayAnyone, Sound-to-Sound transfers instead Zelle pivot"},
    ])
    by = {r["source"]: r for r in rows}
    assert by["Employee reviews"]["rating"] == "3.8/5"
    assert "signal" not in by["Employee reviews"]          # off-topic signal dropped
    assert "Better Business Bureau" not in by              # no rating → row removed
    assert "Net Promoter Score" not in by                  # 6/5 out of scale → removed


def test_sentiment_normalize_pass2_yields_zero_fragments() -> None:
    """The Pass-2 choke point: normalize_sentiment sanitizes EVERY blob's
    sources[] — including the raw derived_from=None kv-dumps derive_sentiment
    skipped. Feed representative class-A and class-B blobs and assert the emitted
    sources carry zero audit fragments and no kv-dump heads."""
    blob = {"derived_from": None, "sources": [
        {"source": "Glassdoor", "rating": "0.55",
         "signal": "overall: 3.5, reviews: 56, culture_values: 3.9"},
        {"source": "Mobile App", "rating": None,
         "signal": "market_cap_B: 14.26, 1yr_high: 122.6, 1yr_low: 71.0"},
        {"source": "Net Promoter Score",
         "signal": "with Coppin State, Johns Hopkins, Towson, Loyola"},
        {"source": "Trustpilot",
         "signal": "show complaints about online banking reliability, long hold times"},
    ]}
    out = normalize_sentiment(blob)
    assert out is not None
    emitted = out.get("sources") or []
    for row in emitted:
        sig = str(row.get("signal") or "")
        assert not _is_fragment(sig), f"fragment survived Pass 2: {sig!r}"
        assert not _KV_HEAD.match(sig), f"kv head survived Pass 2: {sig!r}"
    labels = {r["source"] for r in emitted}
    assert "Glassdoor" in labels                # sentiment kv reformatted, kept
    assert "Trustpilot" in labels               # sentiment clip re-clipped, kept
    assert "Mobile App" not in labels           # non-sentiment kv, no rating → dropped
    assert "Net Promoter Score" not in labels   # off-topic clip, no rating → dropped
