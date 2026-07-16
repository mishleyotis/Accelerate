"""facts_extractor — evidence facts[] → D5 timeline events (NLP pipeline).

Pins the date normaliser against the real messy publish_date formats,
the conservative event classifier (precision over recall), the Part 8.2
pipeline contracts (negation suppression, real-event-date precision
flags, titlecraft titles, native signal, cross-source dedup) and the
end-to-end derivation against the real Haventree fixture. The fixture
strings in the negation/description tests are the audit's VERBATIM worst
offenders (aafcu / access-credit / sunflower classes).
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from app.schemas.package import EvidenceRow
from app.services.nlp import polarity
from app.services.parsers.facts_extractor import (
    classify_fact_kind,
    dedup_events,
    extract_regulatory_standing,
    extract_timeline_events,
    parse_event_date,
)

_TODAY = date(2026, 6, 9)


def test_parse_event_date_formats() -> None:
    assert parse_event_date("2025-02-14", today=_TODAY) == date(2025, 2, 14)
    assert parse_event_date("2025-02", today=_TODAY) == date(2025, 2, 1)  # most common
    assert parse_event_date("2019", today=_TODAY) == date(2019, 1, 1)
    assert parse_event_date("2020-2022", today=_TODAY) == date(2020, 1, 1)  # range start
    assert parse_event_date("2021-current", today=_TODAY) == date(2021, 1, 1)
    assert parse_event_date("2024-Q3", today=_TODAY) == date(2024, 7, 1)
    assert parse_event_date("2024-q1", today=_TODAY) == date(2024, 1, 1)
    # sentinels / junk / out-of-range
    for bad in ("N/A", "", "current", "unknown", None, "1700", "2099", "not a date"):
        assert parse_event_date(bad, today=_TODAY) is None


def test_classify_fact_kind_precision() -> None:
    # true positives
    assert classify_fact_kind("Acquired FinTechCo for $400M in 2023") == "acquisition"
    assert classify_fact_kind("Merged with RegionalCo in 2021") == "acquisition"
    assert classify_fact_kind("Fern Glowinsky appointed President and CEO") == "leadership"
    assert classify_fact_kind("Joel Cote joined as COO in March 2026") == "leadership"
    assert classify_fact_kind("Fined $2M by the regulator for AML lapses") == "regulatory"

    # FALSE-POSITIVE guards — the real noise that polluted Haventree:
    assert classify_fact_kind("CHRO background: talent acquisition and people development") is None
    assert classify_fact_kind("Propensity models for DTC acquisition") is None
    assert classify_fact_kind("Values listed: Empathy, Innovation, Collaboration") is None
    assert classify_fact_kind("NEGATIVE EVIDENCE: NOT listed in FINTRAC penalty registry") is None
    assert classify_fact_kind("Growing retained earnings base confirms capacity to self-fund") is None
    assert classify_fact_kind("") is None


def _ev(e_id: str, publish_date: str | None, facts: list[dict],
        excerpt: str = "x") -> EvidenceRow:
    return EvidenceRow(
        e_id=e_id, source_name="src", tier=2, excerpt=excerpt,
        publish_date=publish_date, facts=facts,
    )


# ── Part 8.2 step 3 — negation/absence suppression (audit verbatim) ────────


AUDIT_NEGATIONS = [
    # aafcu rows that rendered as timeline 'acquisition'/'regulatory' events:
    "INTERNAL ALTERNATIVE — 'No M&A activity' (P1C1.8.1-8.4): NEGATIVE SEARCH "
    "confirmed AAFCU not party to any 2024 or 2025 merger transaction",
    "NEGATIVE SEARCH: AAFCU NOT named in any 2024 or 2025 NCUA merger "
    "approvals, bank acquisitions, or merger-of-equals announcements",
    "NEGATIVE SEARCH RESULT: No formal enforcement orders, consent orders, "
    "or monetary penalties identified against the institution in 2024",
    "No evidence of a consent order or cease and desist action was found "
    "in the OCC enforcement database for 2023-2025",
    "NOT named in any FINTRAC administrative monetary penalty registry "
    "entries reviewed in 2025",
]


def test_negated_absences_never_become_events() -> None:
    rows = [_ev(f"E{i}", "2026-04", [{"text": t, "claim_label": "FACT"}])
            for i, t in enumerate(AUDIT_NEGATIONS)]
    assert extract_timeline_events(rows, today=_TODAY) == []


def test_regulatory_standing_signal_from_suppressed_absence() -> None:
    rows = [
        _ev("E-037", "2025-12", [{
            "text": AUDIT_NEGATIONS[2], "claim_label": "FACT",
        }]),
    ]
    standing = extract_regulatory_standing(rows)
    assert standing is not None
    assert standing["label"] == "Clean regulatory standing"
    assert standing["e_id"] == "E-037"
    assert "No formal enforcement" in standing["note"]


def test_regulatory_standing_none_when_no_absence() -> None:
    rows = [_ev("E1", "2025-01", [{"text": "Fined $2M by the OCC in March 2024"}])]
    assert extract_regulatory_standing(rows) is None


# ── Part 8.2 step 2 — event-vs-description gate ─────────────────────────────


def test_descriptions_obligations_hypotheticals_dropped() -> None:
    rows = [
        _ev("E1", "2026-04", [
            # baseline/obligation (audit: "MUST maintain BSA/AML")
            {"text": "The institution MUST maintain BSA/AML transaction "
                     "monitoring controls under its charter obligations"},
            # strategy intent (audit acquisition FP class)
            {"text": "Management is actively seeking acquisition opportunities "
                     "across the Midwest region"},
            # analyst inference
            {"text": "The spending pattern appears to reflect an ongoing core "
                     "modernization program at the bank"},
            # resume/oversight description with an M&A noun but no event verb
            # or in-text date (access-credit audit FP):
            {"text": "Darcy oversaw complex integration process following the "
                     "merger of six credit unions over the past three years"},
        ]),
    ]
    assert extract_timeline_events(rows, today=_TODAY) == []


def test_noun_frame_with_in_text_date_is_promoted() -> None:
    rows = [_ev("E-003", "2026-02", [{
        "text": "July 1, 2022: legal merger of Access + Noventis + Sunova CUs "
                "(member vote Jan 27, 2022)",
    }])]
    events = extract_timeline_events(rows, today=_TODAY)
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "acquisition"
    assert ev.event_date == date(2022, 7, 1)
    assert ev.date_precision == "day"  # in-text date, NOT the publish month


# ── Part 8.2 steps 4-6 — dates, titles, signal, refs ────────────────────────


def test_in_text_date_beats_publish_date_with_precision_flag() -> None:
    rows = [
        _ev("E1", "2026-04", [{"text": "Sunflower Bank launched its rebuilt "
                                       "mobile app in March 2024"}]),
        _ev("E2", "2026-04", [{"text": "Jane Smith was appointed Chief "
                                       "Financial Officer"}]),
    ]
    events = {e.e_id: e for e in extract_timeline_events(rows, today=_TODAY)}
    dated = events["E1"]
    assert dated.event_date == date(2024, 3, 1)
    assert dated.date_precision == "month"
    fallback = events["E2"]
    assert fallback.event_date == date(2026, 4, 1)
    assert fallback.date_precision == "publish_fallback"


def test_titles_are_clean_and_excerpt_moves_to_body() -> None:
    # Audit garbage-title classes: subcap prefix + ALL-CAPS header + 200-char
    # wall. The pipeline must emit a ≤60-char human title and keep the
    # verbatim claim in body.
    text = (
        "P3C2.1.4 CORE BANKING MODERNIZATION UPDATE: The bank completed its "
        "core banking migration to Jack Henry in June 2024, consolidating "
        "three legacy deposit systems onto a single platform across all "
        "branches and back-office operations [E-214]"
    )
    rows = [_ev("E-100", "2026-01", [{"text": text}])]
    events = extract_timeline_events(rows, today=_TODAY)
    assert len(events) == 1
    ev = events[0]
    assert len(ev.title) <= 60
    assert not ev.title.startswith("P3C2")            # subcap prefix stripped
    assert "CORE BANKING MODERNIZATION" not in ev.title  # ALL-CAPS header gone
    assert ev.body == text                            # verbatim claim kept
    assert ev.event_date == date(2024, 6, 1)
    assert ev.date_precision == "month"
    assert ev.subcap_ids == ["P3C2.1.4"]
    assert "E-100" in ev.evidence_e_ids and "E-214" in ev.evidence_e_ids


def test_signal_is_native_polarity_not_kind() -> None:
    rows = [
        _ev("E1", "2024-12", [{"text": "Fined $4.5M under an AML consent "
                                       "order announced December 2024"}]),
        _ev("E2", "2025-06", [{"text": "Acquired FinTechCo in June 2025 to "
                                       "expand digital lending momentum"}]),
    ]
    events = {e.e_id: e for e in extract_timeline_events(rows, today=_TODAY)}
    assert events["E1"].signal == "negative"
    assert events["E2"].signal == "positive"


# 2026-07-02 depth stress-test regressions — two artifacts sampled from
# LIVE rows (verbatim): trailing '=' debris and a markdown-bullet date
# fragment emitted as a TITLE. Titles must never carry either class.
_TITLE_TRAIL_DEBRIS = re.compile(r"[=*_#|]\s*$")
_TITLE_LEAD_MARKER = re.compile(r"^\s*[(\[]?[a-z]?[)\]]\s|^\*\*|^[-•*] ", re.IGNORECASE)


def test_stress_probe_trailing_equals_debris() -> None:
    # exchange-bank E-033 (verbatim): emitted title was "Promoted to SVP 2025 ="
    rows = [_ev("E-033", "2025-06", [{
        "text": "Promoted to SVP 2025 = expanding scope and recognition of "
                "risk function",
    }])]
    events = extract_timeline_events(rows, today=_TODAY)
    assert len(events) == 1
    title = events[0].title
    assert not _TITLE_TRAIL_DEBRIS.search(title), title
    assert title.startswith("Promoted to SVP 2025")


def test_stress_probe_markdown_bullet_date_title() -> None:
    # beacon-bank E-058 (verbatim class): emitted title was
    # "(e) **September 10, 2025" — a list-marker + emphasis + bare date.
    rows = [_ev("E-058", "2026-01", [{
        "text": "Marshall case timeline: (a) April 20, 2023 — Marshall filed "
                "Chapter 11 (debts $92.7M, $90.5M unsecured promissory notes "
                "to 990 investors); (e) **September 10, 2025 — reorganization "
                "plan announced by the court",
    }])]
    events = extract_timeline_events(rows, today=_TODAY)
    assert events, "dated occurrences must still be promoted"
    for ev in events:
        assert not _TITLE_LEAD_MARKER.search(ev.title), ev.title
        assert not _TITLE_TRAIL_DEBRIS.search(ev.title), ev.title
        assert "**" not in ev.title, ev.title
        # a bare date is never a title
        assert not re.fullmatch(
            r"(?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+\d{1,2},?\s+\d{4}", ev.title,
        ), ev.title


# ── Part 8.2 step 7 — cross-source dedup ────────────────────────────────────


def test_cross_source_near_duplicates_merge() -> None:
    rows = [
        _ev("E1", "2024-08", [{"text": "Acquired Hudson Valley CU branches "
                                       "in August 2024 adding 32 locations"}]),
        _ev("E2", "2024-08", [{"text": "Hudson Valley CU branches acquired "
                                       "August 2024 — 32 locations added"}]),
    ]
    events = extract_timeline_events(rows, today=_TODAY)
    assert len(events) == 1
    # evidence anchors unioned across the merged sources
    assert {"E1", "E2"} <= set(events[0].evidence_e_ids)


def test_dedup_events_keeps_more_precise_date() -> None:
    from app.schemas.package import TimelineEventCandidate

    a = TimelineEventCandidate(
        event_date=date(2024, 6, 15), kind="product",
        title="Bank launched rebuilt mobile app", body="launch A",
        e_id="E1", date_precision="day", evidence_e_ids=["E1"],
    )
    b = TimelineEventCandidate(
        event_date=date(2024, 6, 1), kind="product",
        title="Bank launched rebuilt mobile app", body="launch A",
        e_id="E2", date_precision="publish_fallback", evidence_e_ids=["E2"],
    )
    kept = dedup_events([a, b])
    assert len(kept) == 1
    assert kept[0].date_precision == "day"
    assert set(kept[0].evidence_e_ids) == {"E1", "E2"}


def test_extract_selects_dedupes_and_caps() -> None:
    rows = [
        _ev("E1", "2023-05", [
            {"text": "Acquired FinTechCo to expand digital lending", "claim_label": "FACT"},
            {"text": "Is a Schedule I bank regulated by OSFI", "claim_label": "FACT"},  # static → skip
        ]),
        _ev("E2", "2024-Q2", [
            {"text": "Jane Smith was appointed Chief Financial Officer"},
        ]),
        _ev("E3", None, [  # no date anywhere → skipped entirely
            {"text": "Acquired AnotherCo in a major deal"},
        ]),
        _ev("E4", "2022-01", [
            {"text": "REMOVED: original breach claim retracted", "claim_label": "REMOVED"},  # anti-fact
        ]),
    ]
    events = extract_timeline_events(rows, today=_TODAY)
    kinds = {e.kind for e in events}
    assert kinds == {"acquisition", "leadership"}
    assert all(e.event_date is not None for e in events)
    # most-recent first
    assert events[0].event_date >= events[-1].event_date
    # provenance threaded
    acq = next(e for e in events if e.kind == "acquisition")
    assert acq.e_id == "E1" and acq.event_date == date(2023, 5, 1)
    assert acq.date_precision == "publish_fallback"

    # cap respected (distinct titles so dedup doesn't collapse them)
    many = [
        _ev(f"E{i}", "2023-05",
            [{"text": f"Acquired {n} Holdings in a definitive deal"}])
        for i, n in enumerate((
            "Aspen", "Birch", "Cedar", "Dogwood", "Elm", "Fir", "Ginkgo",
            "Hazel", "Juniper", "Katsura", "Linden", "Magnolia",
        ))
    ]
    assert len(extract_timeline_events(many, today=_TODAY, cap=10)) == 10


# ── 2026-07 pack audit — kind/signal contradiction regressions ─────────────
# The a08f0c5c diagnosis measured 141 kind/signal-vs-text contradictions
# across the 1,266 committed-pack timeline events. Each case below is a
# VERBATIM title/body from startup-data/clients/*/context.json (the worst
# offender per class) pinned to the expected kind+signal.

# (client, verbatim pack text, expected kind, expected signal)
PACK_AUDIT_CASES = [
    # A: regulatory RESOLUTIONS rendered signal='negative' (12 events/8 clients)
    ("fulton-bank-national-ass-8001",
     "5-YEAR BSA/AML REMEDIATION COMPLETED MAY 2019 (Lancaster Online): "
     "'Federal Reserve System has terminated a consent order requiring it "
     "and its subsidiary Lafayette Ambassador Bank in Lehigh Valley to fix "
     "deficiencies in their compliance with the U.S. Bank Secrecy Act and "
     "anti-money laundering regulations'",
     "regulatory", "positive"),
    ("everbank-n-a-0001",
     "OCC consent order for mortgage servicing remediated — 91/95 items "
     "completed, order terminated, $1.6M borrower payments made",
     "regulatory", "positive"),
    ("regions-bank-0001",
     "Regions Bank fully resolved 2022 CFPB Consent Order on overdraft fees "
     "(July 2025 termination, $50M penalty paid, consumer redress complete). "
     "Resolution demonstrates active regulatory compliance remediation "
     "capability and exam readiness process.",
     "regulatory", "positive"),
    ("regions-bank-0001",
     "CFPB Consent Order FULLY RESOLVED July 2025 per E-001: The most recent "
     "consent order was resolved — strongest positive compliance signal.",
     "regulatory", "positive"),
    # C: enforcement/legal texts classified kind='milestone'
    ("beacon-bank-0001",
     "June 2025 — NY AG Letitia James announced 49-count criminal indictment "
     "against Marshall (securities fraud + grand larceny)",
     "regulatory", "negative"),
    ("cornerstone-capital-bank-0001",
     "Service provider data breach → AG notifications + Experian monitoring "
     "(RESOLVED) [E-051]. Salesforce Shield / security posture opportunity",
     "regulatory", "neutral"),
    # D: compliance/risk HIRES classified kind='regulatory' signal='negative'
    ("bank-of-utah-30v2",
     "VP Compliance Manager (Sept 2025) hired AFTER consent order (Feb 2024) "
     "— likely remediation-driven hire to strengthen compliance function",
     "leadership", "positive"),
    ("bank-of-utah-30v2",
     "SVP Strategic Risk Officer (July 2024) hired 5 months after consent "
     "order — risk governance response to enforcement action",
     "leadership", "positive"),
    # E: leadership hires dumped into kind='milestone' (112 events)
    ("1st-security-bank-of-was-0001",
     "VP Marketing (Camberly G.) hired Dec 2025 - new marketing leadership",
     "leadership", "positive"),
    ("1st-security-bank-of-was-0001",
     "Compliance Testing & Monitoring Manager hired Aug 2024 to strengthen "
     "second-line testing",
     "leadership", "positive"),
]


def test_pack_audit_kind_signal_contradictions() -> None:
    for client, text, want_kind, want_signal in PACK_AUDIT_CASES:
        assert classify_fact_kind(text) == want_kind, (client, text[:60])
        assert polarity.signal(text) == want_signal, (client, text[:60])


def test_pack_audit_clean_standing_absence_never_a_negative_event() -> None:
    # apg-federal-credit-union-0001 (verbatim): promoted as kind='regulatory'
    # signal='negative' — the exact opposite of a clean regulatory record.
    text = (
        "NCUA Enforcement Actions database search: NO actions, consent "
        "orders, or prohibitions found against APG Federal Credit Union or "
        "any APGFCU-named individual in current or recent enforcement "
        "records — clean regulatory record"
    )
    assert polarity.is_negated_absence(text) is True
    assert polarity.signal(text) == "positive"  # absence of a bad thing
    assert classify_fact_kind(text) is None
    rows = [_ev("E-90", "2026-02", [{"text": text}])]
    assert extract_timeline_events(rows, today=_TODAY) == []  # suppressed from the timeline
    standing = extract_regulatory_standing(rows)  # …but drives clean standing
    assert standing is not None
    assert standing["label"] == "Clean regulatory standing"
    # derive_context's residual title gate must also catch this phrasing.
    from app.scripts.derive_context import _is_negation_title
    assert _is_negation_title(
        "NCUA Enforcement Actions database search: NO actions…") is True


def test_pack_audit_peer_precedent_never_lands_on_entity_timeline() -> None:
    # alma-bank-0001 (verbatim): 'Gemini Trust fined $37M' — a NYDFS
    # precedent about ANOTHER institution — sat on Alma Bank's timeline
    # as its own kind='regulatory' signal='negative' event.
    text = (
        "NYDFS enforcement precedent: Gemini Trust fined $37M (2024) for "
        "inadequate TPSP oversight; Block Inc. fined $40M (2025) for lack "
        "of board-reviewed third-party cybersecurity policies — enforcement "
        "risk elevates Alma Bank's TPRM compliance incentive"
    )
    rows = [_ev("E-91", "2025-07", [{"text": text}])]
    assert extract_timeline_events(rows, today=_TODAY) == []


def test_pack_audit_departure_stays_negative_and_becomes_leadership() -> None:
    # access-credit-union-limi-0001 (verbatim): a CMO departure was
    # kind='milestone'; polarity (negative) was already right — the kind
    # fix must NOT flip legitimately negative leadership news.
    text = (
        "Adam Monteith: DEPARTED as CMO November 2025 (per Exa signal) — "
        "transitioned to Chief Corporate Affairs Officer"
    )
    events = extract_timeline_events([_ev("E-92", "2025-11", [{"text": text}])], today=_TODAY)
    assert len(events) == 1
    assert events[0].kind == "leadership"
    assert events[0].signal == "negative"


def test_pack_audit_open_consent_order_stays_negative() -> None:
    # Guard from the fix plan: lexicon widening must not flip genuinely
    # negative rows — an ISSUED order with an open remediation obligation
    # has no completed-resolution verb.
    issued = ("OCC issued a consent order in February 2024 requiring "
              "remediation within 18 months")
    assert polarity.signal(issued) == "negative"
    assert classify_fact_kind(issued) == "regulatory"
    fined = "Fined $4.5M under an AML consent order announced December 2024"
    assert polarity.signal(fined) == "negative"


def test_real_haventree_fixture() -> None:
    fix = Path(__file__).resolve().parents[1] / (
        "tests/fixtures/dma_packages_batches/batch_01/"
        "Haventree Bank DMA - DMA/01_evidence/evidence_index.json"
    )
    if not fix.exists():
        import pytest
        pytest.skip(f"fixture moved: {fix}")
    data = json.loads(fix.read_text())
    raw_rows = data if isinstance(data, list) else data.get("items") or data.get("evidence") or []
    rows = [
        EvidenceRow(
            e_id=str(r.get("evidence_id") or r.get("e_id") or "E?")[:16],
            source_name=str(r.get("source_name") or "src"),
            source_url=r.get("url") or r.get("source_url"),
            tier=int(r.get("tier") or 5) if str(r.get("tier") or "5").isdigit() else 5,
            excerpt=str(r.get("excerpt") or ""),
            publish_date=str(r.get("publish_date") or "") or None,
            facts=r.get("facts") if isinstance(r.get("facts"), list) else [],
        )
        for r in raw_rows
        if isinstance(r, dict)
    ]
    events = extract_timeline_events(rows, today=_TODAY)
    # The fixture carries dated, event-shaped facts → a non-empty timeline.
    assert len(events) > 0
    for e in events:
        assert e.kind
        assert e.title and len(e.title) <= 61  # 60 + ellipsis glyph
        assert e.title == e.title.strip()
        assert e.date_precision in {"day", "month", "quarter", "year",
                                    "publish_fallback"}
        assert e.signal in {"positive", "neutral", "negative"}
        assert e.body  # verbatim claim preserved


# ── 2026-07-06 classifier tightening (production D5 timeline audit) ─────────
# Verbatim event shapes from the IBKR + Haventree fixtures that the
# classifier was mis-labelling: regulator-actor launches chipped as the
# entity's "tech launch", executive VP/EVP hires demoted to milestones,
# and individual staff job-starts promoted as company events.


def test_regulator_actor_launch_is_regulatory_not_product() -> None:
    rows = [
        # IBKR E-corpus verbatim: FINRA launched ITS OWN platform.
        _ev("E1", "2026-07", [{"text": "Finra 2026 Annual Report: 'FINRA CORE "
                                       "launched in 2025' for member firms"}]),
        # Haventree verbatim: OSFI launched a supervisory framework.
        _ev("E2", "2024-04", [{"text": "OSFI launched new Supervisory "
                                       "Framework February 2024"}]),
    ]
    events = {e.e_id: e for e in extract_timeline_events(rows, today=_TODAY)}
    assert events["E1"].kind == "regulatory"
    assert events["E2"].kind == "regulatory"


def test_entity_launch_stays_product_even_when_regulator_mentioned_after() -> None:
    rows = [_ev("E1", "2025-10", [{
        "text": "Ask IBKR launched Oct 15, 2025: AI-powered NLP tool for "
                "account holders, reviewed by FINRA guidance",
    }])]
    events = extract_timeline_events(rows, today=_TODAY)
    assert len(events) == 1
    assert events[0].kind == "product"  # entity acted; regulator named after


def test_vp_and_evp_hires_classify_leadership() -> None:
    # IBKR's critical inflection point — previously a bare 'milestone'.
    assert classify_fact_kind(
        "EVP Technology: Somayajulu (Soma) Bulusu, joined Feb 2024"
    ) == "leadership"
    assert classify_fact_kind(
        "Vikrant Verma VP Software Engineering joined April 2024"
    ) == "leadership"


def test_non_executive_staff_hires_are_suppressed() -> None:
    rows = [
        _ev("E1", "2024-12", [{"text": "Sara Azadeh Business Data Analyst "
                                       "joined Dec 2024"}]),
        _ev("E2", "2025-07", [{"text": "Tarun Sanagapalli Senior Cyber "
                                       "Security Engineer joined July 2025"}]),
    ]
    assert extract_timeline_events(rows, today=_TODAY) == []


def test_real_ibkr_cpr_fixture_kinds() -> None:
    fix = Path(__file__).resolve().parents[1] / (
        "tests/fixtures/dma_packages_batches/batch_15/"
        "Interactive Brokers - DMA/02_research_workbook/"
        "IBKR_CPR_Evidence_Source.json"
    )
    if not fix.exists():
        import pytest
        pytest.skip(f"fixture moved: {fix}")
    data = json.loads(fix.read_text())
    rows = [
        EvidenceRow(
            e_id=str(r.get("evidence_id"))[:16], source_name=str(r.get("source_name")),
            source_url=r.get("url"), tier=2, excerpt="",
            publish_date=str(r.get("publish_date") or "") or None,
            facts=r.get("facts") if isinstance(r.get("facts"), list) else [],
        )
        for r in data.get("items", [])
    ]
    by_title = {e.title: e for e in extract_timeline_events(rows, today=_TODAY)}

    def _kind_of(fragment: str) -> str | None:
        for title, ev in by_title.items():
            if fragment.lower() in title.lower():
                return ev.kind
        return None

    assert _kind_of("FINRA CORE") == "regulatory"       # regulator actor
    assert _kind_of("Soma") == "leadership"             # EVP hire
    assert _kind_of("CFTC") == "regulatory"             # $20M penalty
    assert _kind_of("LedgerX") == "acquisition"
    assert _kind_of("Ask IBKR") == "product"            # entity's own launch
