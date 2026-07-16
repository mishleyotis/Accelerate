"""Why-now template + dedup contracts (2026-07-06 fix family).

Diagnosed symptoms (pack audit a4fe52a6): duplicate tiles for one real-world
trigger (asymmetric _push guard), the same event sentence printed twice
inside one tile (title-echo details), one client-level peer_context/risk/
impact/play stamped on every tile, template gaps (no WN-n ids, window/
timeline/metric nulls, confidence never HIGH), and a legacy 5-key producer.

These tests pin the fixes with the diagnosis's five VERBATIM duplicate
examples from the shipped pack — all must dedup — plus the per-signal
differentiation and 14-field completeness contracts. Pure logic, no DB.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from app.scripts.deepen_narrative import (
    _assign_peer_context,
    _dedupe_plays,
    _dedupe_sentences,
    _ensure_deep_fields,
    _event_detail,
    _peer_line,
    _push_signal,
    _sig,
    finalize_why_now,
)
from app.services import startup_enrich as se
from app.services.wn_dedup import near_duplicate, token_containment

_TODAY = dt.date(2026, 7, 6)

# The 14 prototype content fields _sig must populate (proto 3d9fd6c1 WHY_NOW);
# the 15th key, `id` (WN-n), is stamped by finalize_why_now.
_TEMPLATE_FIELDS = (
    "label", "category", "strength", "window", "confidence", "claim",
    "detail", "metric", "peer_context", "play", "risk", "evidence",
    "timeline", "impact",
)

# ── The diagnosis's 5 verbatim duplicate examples (shipped pack) ────────────
# 1) sound-credit-union-0001 — one acquisition mined twice
_WBB_A = ("Completed acquisition of Washington Business Bank June 2025 "
          "(Jun 2025).")
_WBB_B = ("WBB ACQUISITION: completed acquisition of Washington Business "
          "Bank, increased Thurston County branch footprint, gained ~800 "
          "business clients, expanding business segment support (May 2025).")
# 2) tristate-capital-holding-0001 — one CTO hire titled two ways
_CTO_A = ("Andrew Caudill appointed CTO. Andrew Caudill appointed CTO at "
          "TriState Capital Bank, Jan 2026")
_CTO_B = ("TSC has a CTO: Andrew M. Caudill, appointed Jan 2026. Previously "
          "Head of Technology Strategy and Architecture")
# 3) loandepot-inc-0001 — the same Q4-2025-earnings AI deployment
_AI_A = ("AI capabilities deployed for lead acquisition and conversion "
         "(confirmed in Q4 2025 earnings) (Nov 2025)")
_AI_B = ("AI lead acquisition/conversion deployed per Q4 2025 earnings — "
         "implies some level of customer scoring/targeting (Nov 2025)")
# 4) chemung-canal-trust-comp-0001 — two token-identical 'priority focus' pads
_PAD_A = ("Cross-Sell & Deepening at 1.64/5 is one of Chemung Canal Trust "
          "Company's lower-scoring capability areas and a priority focus for "
          "the next phase of the digital-maturity roadmap.")
_PAD_B = ("Data Stewardship Program at 1.64/5 is one of Chemung Canal Trust "
          "Company's lower-scoring capability areas and a priority focus for "
          "the next phase of the digital-maturity roadmap.")
# 5) 1st-security-bank-of-was-0001 — one tile printing the hire twice
_ECHO = ("VP Marketing (Camberly G.) hired Dec 2025 - new marketing…. "
         "VP Marketing (Camberly G.) hired Dec 2025 - new marketing "
         "leadership. Window: closes ~Q4 2026.")


class TestSymmetricDedupGuard:
    def test_diagnosis_pair_examples_all_dedup(self):
        for a, b in ((_WBB_A, _WBB_B), (_CTO_A, _CTO_B),
                     (_AI_A, _AI_B), (_PAD_A, _PAD_B)):
            assert near_duplicate(a, b), f"escaped: {a[:60]!r} vs {b[:60]!r}"
            assert near_duplicate(b, a), "guard must be symmetric"

    def test_distinct_triggers_are_not_deduped(self):
        assert not near_duplicate(
            _WBB_A,
            "Ralph Haberli appointed CEO Nov 2025 after PE owners halted "
            "sale efforts")
        assert not near_duplicate(
            _PAD_A,
            "An open FRB consent order requires remediation of "
            "transaction-monitoring controls within 18 months.")

    def test_push_keeps_the_deeper_write_up_of_a_duplicate_pair(self):
        sigs: list[dict] = []
        counts: dict[str, int] = {}
        short = {"kind": "M&A", "category": "market", "strength": "STRONG",
                 "detail": _WBB_A, "subcap_id": None}
        rich = {"kind": "M&A", "category": "market", "strength": "STRONG",
                "detail": _WBB_B, "subcap_id": None}
        assert _push_signal(short, sigs, counts) is True
        # duplicate → no NET-new signal, but the deeper write-up wins in place
        assert _push_signal(rich, sigs, counts) is False
        assert len(sigs) == 1
        assert sigs[0]["detail"] == _WBB_B
        assert counts["market"] == 1

    def test_push_prefers_higher_strength_over_length(self):
        sigs: list[dict] = []
        counts: dict[str, int] = {}
        weak_long = {"kind": "M&A", "category": "market",
                     "strength": "SUPPORTING", "detail": _WBB_B}
        strong_short = {"kind": "M&A", "category": "market",
                        "strength": "STRONG", "detail": _WBB_A}
        _push_signal(weak_long, sigs, counts)
        assert _push_signal(strong_short, sigs, counts) is False
        assert sigs[0]["detail"] == _WBB_A

    def test_same_subcap_same_category_dedups_even_with_disjoint_prose(self):
        sigs: list[dict] = []
        counts: dict[str, int] = {}
        _push_signal({"kind": "GAP", "category": "market", "strength": "SUPPORTING",
                      "detail": "Data Warehouse & Data Lake scores 1.56/5.",
                      "subcap_id": "P4C2"}, sigs, counts)
        added = _push_signal(
            {"kind": "GAP", "category": "market", "strength": "SUPPORTING",
             "detail": "Entirely different wording about analytics maturity "
                       "trailing the cohort.",
             "subcap_id": "P4C2"}, sigs, counts)
        assert added is False
        assert len(sigs) == 1

    def test_category_cap_still_enforced_for_non_market(self):
        sigs: list[dict] = []
        counts: dict[str, int] = {}
        _push_signal({"kind": "LEADERSHIP", "category": "leadership",
                      "detail": "New CTO Anna Smith joined in March 2026."},
                     sigs, counts)
        _push_signal({"kind": "LEADERSHIP", "category": "leadership",
                      "detail": "A CDO seat was created for Bob Jones with a "
                                "governed-data mandate."}, sigs, counts)
        assert _push_signal(
            {"kind": "LEADERSHIP", "category": "leadership",
             "detail": "VP Engineering hire posted for the platform team."},
            sigs, counts) is False
        assert len(sigs) == 2


class TestTitleEchoSuppression:
    def test_intra_signal_echo_collapses_keeping_the_richer_sentence(self):
        out = _dedupe_sentences(_ECHO)
        assert out.count("VP Marketing (Camberly G.) hired Dec 2025") == 1
        assert "new marketing leadership" in out          # richer variant kept
        assert "Window: closes ~Q4 2026." in out          # distinct tail kept

    def test_event_detail_prefers_body_when_it_restates_the_title(self):
        detail = _event_detail(
            "VP Marketing (Camberly G.) hired Dec 2025 - new marketing…",
            "VP Marketing (Camberly G.) hired Dec 2025 - new marketing leadership",
            "Dec 2025")
        assert detail.count("hired Dec 2025") == 1
        assert "leadership" in detail

    def test_event_detail_body_equal_to_title_prints_once_with_date(self):
        detail = _event_detail("Named Forbes America's Best Employers 2026",
                               "Named Forbes America's Best Employers 2026",
                               "Jul 2026")
        assert detail == "Named Forbes America's Best Employers 2026 (Jul 2026)."

    def test_event_detail_short_body_with_new_content_keeps_the_title(self):
        detail = _event_detail("Core migration announced",
                               "Target go-live is Q2 2027.", "Sep 2025")
        assert "Core migration announced" in detail
        assert "Target go-live is Q2 2027" in detail

    def test_event_detail_no_body_falls_back_to_title(self):
        assert _event_detail("Acquired Beacon Insurance Agency", "", "Feb 2026") \
            == "Acquired Beacon Insurance Agency (Feb 2026)."


class TestSigTemplateCompleteness:
    def test_sig_emits_all_14_template_fields(self):
        s = _sig("M&A", "market",
                 "Completed acquisition of Washington Business Bank, adding "
                 "roughly 800 business clients", ["E-001", "E-002"],
                 window="closes ~Q2 2027", claim="FACT", best_tier=1,
                 timeline={"date": "2025-06-15", "event": "WBB acquisition"},
                 derived_from="timeline_events")
        for f in _TEMPLATE_FIELDS:
            assert f in s, f"missing template field {f}"
        for f in ("label", "category", "strength", "confidence", "claim",
                  "detail", "risk", "impact"):
            assert s[f], f"empty required field {f}"
        # tier-1 evidence x2 behind a dated FACT → HIGH is reachable again
        assert s["confidence"] == "HIGH"
        assert s["strength"] == "STRONG"

    def test_risk_and_impact_are_signal_specific_not_category_constants(self):
        a = _sig("M&A", "market", _WBB_B, ["E-1"], window="closes ~Q2 2027")
        b = _sig("GAP", "market",
                 "Cross-Sell & Deepening scores 1.64/5 vs a typical 2.4 at "
                 "similar institutions — the deepest open gap.", ["E-2"],
                 metric="Cross-Sell & Deepening 1.64/5 vs peer 2.4")
        assert a["risk"] != b["risk"]
        assert a["impact"] != b["impact"]

    def test_degenerate_labels_are_replaced(self):
        s = _sig("MILESTONE", "market",
                 "Rate-Betterment Partnership: mortgage rate incentives for "
                 "Betterment users with $100K+ AUM. Through Dec 2026.", [])
        assert len(s["label"]) >= 8
        s2 = _sig("MILESTONE", "market",
                  "2026: Kathleen Alicks named to the Elite Women of "
                  "Insurance 2026 list.", [])
        assert len(s2["label"]) >= 8

    def test_ensure_deep_fields_passes_tier_through_to_confidence(self):
        legacy = [{"kind": "M&A", "text": _WBB_B, "evidence": ["E-1", "E-2"],
                   "derived_from": "timeline_events",
                   "timeline": {"date": "2025-06-15", "event": "WBB"}}]
        out = _ensure_deep_fields(legacy, None, tier_of=lambda eids: 1)
        assert out[0]["confidence"] in ("HIGH", "MEDIUM")
        # tier-1 + 2 evidence ids → HIGH under wn_confidence
        assert out[0]["confidence"] == "HIGH"
        no_tier = _ensure_deep_fields(
            [dict(legacy[0], confidence="MEDIUM")], None)
        assert no_tier[0]["confidence"] == "MEDIUM"   # caller value preserved


class TestFinalizeWhyNow:
    def _mk(self):
        strong = _sig("LEADERSHIP", "leadership",
                      "Andrew Caudill appointed CTO at TriState Capital Bank",
                      ["E-1", "E-2"], window="closes ~Q1 2027", claim="FACT",
                      best_tier=1,
                      timeline={"date": "2026-01-15", "event": "CTO appointed"},
                      derived_from="timeline_events")
        gap = {"kind": "GAP", "category": "market", "strength": "SUPPORTING",
               "derived_from": "subcap_scores", "detail": "gap detail",
               "metric": "X 1.5/5", "window": None, "timeline": None}
        lead_no_window = {"kind": "LEADERSHIP", "category": "leadership",
                          "strength": "LEADING", "derived_from": "timeline_events",
                          "detail": "old hire", "metric": None, "window": None,
                          "timeline": {"date": "2025-01-15", "event": "hire"}}
        return [gap, strong, lead_no_window]

    def test_ids_are_sequential_strongest_first(self):
        out = finalize_why_now(self._mk(), today=_TODAY,
                               assessment_date=dt.date(2026, 6, 30))
        assert [s["id"] for s in out] == ["WN-1", "WN-2", "WN-3"]
        assert out[0]["strength"] == "STRONG"

    def test_window_fallbacks_by_producer_class(self):
        out = finalize_why_now(self._mk(), today=_TODAY)
        by_kind = {s["kind"]: s for s in out}
        # undated score-derived signal → honest structural vocabulary
        assert by_kind["GAP"]["window"] == "structural"
        # dated trigger whose category clock ran out → its REAL date is the
        # bounded anchor (never the synthetic assessment stamp, which is
        # only applied after the window pass)
        lead2 = next(s for s in out if s.get("detail") == "old hire")
        assert lead2["window"] == "trigger dated Jan 2025"

    def test_window_anchor_never_uses_assessment_stamp(self):
        # a signal with NO real timeline must not get a dated window even
        # when an assessment date is supplied — the stamp lands in the
        # timeline fallback only, after windows are decided
        out = finalize_why_now(self._mk(), today=_TODAY,
                               assessment_date=dt.date(2026, 6, 30))
        gap = next(s for s in out if s["kind"] == "GAP")
        assert gap["window"] == "structural"
        assert gap["timeline"] == {"date": "2026-06-30",
                                   "event": "Latest DMA run"}

    def test_timeline_fallback_uses_assessment_date(self):
        out = finalize_why_now(self._mk(), today=_TODAY,
                               assessment_date=dt.date(2026, 6, 30))
        gap = next(s for s in out if s["kind"] == "GAP")
        assert gap["timeline"] == {"date": "2026-06-30",
                                   "event": "Latest DMA run"}

    def test_metric_fallback_only_quotes_the_real_trigger_date(self):
        out = finalize_why_now(self._mk(), today=_TODAY)
        lead2 = next(s for s in out if s.get("detail") == "old hire")
        assert "months in seat" in lead2["metric"]
        gap = next(s for s in out if s["kind"] == "GAP")
        assert gap["metric"] == "X 1.5/5"     # compose-time metric untouched


class TestPerSignalDrillDifferentiation:
    def _rows(self):
        return [
            SimpleNamespace(cat="P4C2", sc=1.56, peer=2.50,
                            worst_name="Data Warehouse & Data Lake"),
            SimpleNamespace(cat="P2C1", sc=1.64, peer=2.40,
                            worst_name="Content Marketing & Thought Leadership"),
            SimpleNamespace(cat="P3C1", sc=2.10, peer=2.30,
                            worst_name="Loan Origination"),
        ]

    def test_peer_context_distinct_per_signal_and_own_row_wins(self):
        signals = [
            {"kind": "GAP", "subcap_id": "P4C2", "label": "Data gap",
             "detail": "Data Warehouse & Data Lake scores 1.56/5."},
            {"kind": "LEADERSHIP", "subcap_id": None, "label": "VP Marketing hired",
             "detail": "VP Marketing hired Dec 2025 — new marketing leadership."},
            {"kind": "M&A", "subcap_id": None, "label": "WBB acquisition",
             "detail": "Completed acquisition of Washington Business Bank."},
        ]
        _assign_peer_context(signals, self._rows(), overall=2.4)
        ctxs = [s["peer_context"] for s in signals]
        # v3: peer context only where a REAL category row sharpens the
        # signal — no overall-score filler; unmatched signals carry None
        real = [c for c in ctxs if c]
        assert len(set(real)) == len(real), f"repeated peer_context: {ctxs}"
        assert "Data Warehouse & Data Lake" in ctxs[0]      # own subcap row
        assert "Content Marketing" in ctxs[1]               # topical match

    def test_peer_context_no_overall_filler(self):
        # v3 doctrine: an overall-score restatement is filler, not peer
        # context — with no matching category rows every signal carries
        # None rather than "Overall digital maturity stands at ..."
        signals = [{"kind": "A", "label": "x", "detail": "x"},
                   {"kind": "B", "label": "y", "detail": "y"}]
        _assign_peer_context(signals, [], overall=2.8)
        assert signals[0]["peer_context"] is None
        assert signals[1]["peer_context"] is None

    def test_dedupe_plays_breaks_the_verbatim_repeat(self):
        signals = [
            {"category": "market", "label": "WBB acquisition",
             "play": "Prioritize the Salesforce conversation."},
            {"category": "leadership", "label": "New CTO",
             "play": "Prioritize the Salesforce conversation."},
            {"category": "market", "label": "Deepest data gap",
             "play": "Prioritize the Salesforce conversation."},
        ]
        _dedupe_plays(signals)
        plays = [s["play"] for s in signals]
        assert len(set(plays)) == 3, f"repeated play survived: {plays}"
        assert plays[0] == "Prioritize the Salesforce conversation."


class TestDepthFloorPads:
    def test_pads_rotate_frames_and_never_near_duplicate(self):
        cats = [("P4C1", "Data Foundation", 1.64, ["E-1"]),
                ("P2C1", "Cross-Sell & Deepening", 1.64, []),
                ("P3C1", "Ops Automation", 2.0, [])]
        out = se.ensure_why_now_depth([], cats, 2.8, "Chemung Canal Trust Company")
        texts = [s["text"] for s in out if s["kind"] == "PRIORITY"]
        assert len(texts) >= 2
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                assert not near_duplicate(texts[i], texts[j]), \
                    f"pads still read as duplicates: {texts[i]!r} / {texts[j]!r}"
                assert token_containment(texts[i], texts[j]) < 0.5

    def test_pads_capped_at_one_per_parent_pillar(self):
        cats = [("P4C1", "Data Foundation", 1.6, []),
                ("P4C2", "Analytics", 1.7, []),
                ("P4C3", "Integration", 1.8, [])]
        out = se.ensure_why_now_depth([], cats, 2.8, "Royal Business Bank")
        pads = [s for s in out if s["kind"] == "PRIORITY"]
        assert len(pads) == 1
        assert any(s["kind"] == "TRAJECTORY" for s in out)

    def test_pads_carry_a_metric(self):
        cats = [("P4C1", "Data Foundation", 1.64, [])]
        out = se.ensure_why_now_depth([], cats, 2.8, "Amarillo National Bank")
        for s in out:
            assert s.get("metric")


class TestW6Humanization:
    """W6 (2026-07-14): why-now labels read as AE-followable headlines — no
    score-quoting, no mid-thought clip — and each play carries a real action.
    Every case below is a defect the 94-client stress test surfaced AFTER the
    unit suite was green, so each is pinned here to prevent recurrence."""

    def test_w6_play_pools_each_carry_an_action_token(self):
        # The W6-added pools (market/gap/financial) replaced default_play
        # ("Prioritize the … conversation") for GAP/milestone/fundamentals
        # signals. default_play carried the recognized directive the
        # actionability gate greps the set for; the replacements must too, or
        # a client whose only action verb rode that play scores no_action
        # (the exact 94-client stress-test regression). The pre-existing pools
        # (core_migration/hiring/regulatory) never carried one and rely on
        # another signal in the set — unchanged by W6, so not asserted here.
        from app.scripts.deepen_narrative import _PLAY_VARIANTS
        from app.services.nlp.quality import _ACTION_RE, _IMPERATIVE_LEAD_RE
        for cat in ("market", "gap", "financial"):
            for v in _PLAY_VARIANTS[cat]:
                assert _ACTION_RE.search(v) or _IMPERATIVE_LEAD_RE.match(v), \
                    f"{cat} play carries no recognized action token: {v!r}"

    def test_sig_prefers_composed_label_over_detail_clip(self):
        detail = ("Azure cloud usage indicated by LinkedIn job postings and "
                  "CDO roadmap references across three business units.")
        s = _sig("HIRING", "hiring", detail, ["E-1"],
                 label="3 live data & tech roles open at Demo Bank",
                 play="Prioritize the platform conversation now.")
        assert s["label"] == "3 live data & tech roles open at Demo Bank"

    def test_ensure_deep_fields_preserves_composed_label(self):
        # the deep-field rebuild used to drop the composed label (play was
        # threaded, label was not) — _sig then clipped the detail mid-thought.
        sig = _sig("GAP", "market",
                   "Data Foundation is the widest gap on this run.", ["E-1"],
                   label="Data Foundation trails the Data & Technology peer set",
                   play="Close this gap first — it should lead the roadmap.")
        out = _ensure_deep_fields([sig], default_play="X.")
        assert out[0]["label"] == \
            "Data Foundation trails the Data & Technology peer set"

    def test_headline_strips_source_ellipsis_and_dangling_connective(self):
        from app.scripts.deepen_narrative import _headline
        # source timeline titles are ingest-truncated at a connective + "…"
        assert _headline(
            "Phillips named 2025 Auto Finance Executive of the Year by…", 72) \
            == "Phillips named 2025 Auto Finance Executive of the Year"
        assert _headline(
            "AmeriCU named 2025 American Banker Best Credit Unions to…", 72) \
            == "AmeriCU named 2025 American Banker Best Credit Unions"
        # a clean title is returned intact (no over-strip)
        assert _headline("Core banking migration completed", 72) \
            == "Core banking migration completed"

    def test_peer_line_strips_leaked_subcap_number_prefix(self):
        # W8 vet (2026-07-14): a leaked source-column numeric prefix
        # ("1033/Open Banking API Compliance") must not reach the peer chip.
        line = _peer_line("1033/Open Banking API Compliance", 2.77, 2.75)
        assert "1033/" not in line
        assert line.startswith("Open Banking API Compliance")
