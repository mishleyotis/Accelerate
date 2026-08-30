"""A small real run, built through the engine's own write path.

Small on purpose: 686 seeded rows is the production shape and a slow test.
The scope-mode and catalogue behaviour is covered in test_contract.py; what
these fixtures exercise is the loop."""
from __future__ import annotations

from engine import contract as C
from engine import ledger as L
from engine import runstate

CAT = "P1C1"


def small_selection(n: int = 6) -> list[str]:
    tax = C.taxonomy()
    return list(tax.cells_in(CAT))[:n]


def new_run(tmp_path, *, n: int = 6, run_id: str = "R-TEST-1",
            prelim: bool = True, folder: bool = True):
    """A started run with its PRELIM phase closed and its client folder open.

    Both default ON because both are what a real run has: `orient` withholds
    every category card while PRELIM is open, and a run with no client
    folder is one nobody can find. Pass `prelim=False` / `folder=False` to
    test those gates themselves."""
    run = runstate.start(
        run_id=run_id, entity_name="Acme Credit Union", entity_id="acme-cu",
        sub_vertical="CU", scope_mode="T1_CORE", reference_date="2026-08-29",
        root=tmp_path / "run", selected=small_selection(n))
    if folder:
        from engine import assemble
        assemble.open_folder(run, tmp_path / "client", push=False)
    if prelim:
        close_prelim(run)
    return run


def bank_evidence(wb, subcap, n=3, *, tier="T2", published="2025-06-01"):
    """Rows from TWO source identities, because the syntheses built on them
    claim 'two independent sources agree' — and since single_source_fact
    became a blocking gate term, a FACT resting on one host is refused. The
    third row is the independent second (the NCUA call report the fixture
    synthesis already cites in prose)."""
    # EVIDENCE THAT NEVER CAME FROM A SEARCH IS EVIDENCE FROM NOWHERE.
    # Until `category_never_searched` became a gate term (2026-08-30, from a
    # live report that agents were closing subcaps without deep searches),
    # this fixture banked rows and synthesised on them with an empty
    # Search_Log — so every test workbook modelled the exact shape the gate
    # now refuses, and one lifecycle test asserted PASS over it. A fixture
    # that cannot pass an honest gate is a fixture teaching the wrong thing.
    L.append_search(wb, subcap=subcap, facet="works",
                    query=f"{subcap} capability evidence — fixture bank",
                    tool="web_search", hits=n + 1, kept=n,
                    outcome=f"kept {n}")
    out = []
    for i in range(n):
        second = i == n - 1 and n > 1
        out.append(L.append_evidence(
            wb,
            source_name=("NCUA Call Report 2025 — digital channel volumes"
                         if second else f"Annual Report 2025 p{i+1}"),
            source_url=(f"https://ncua.example/callreport/2025#{subcap}"
                        if second else f"https://acme.example/ar25#p{i+1}"),
            tier=tier,
            excerpt=("Alkami digital banking went live in Q3 2024 and reached "
                     f"47 percent member adoption within ninety days, restated "
                     f"at {50+i} percent in the 2025 report."),
            subcaps=[subcap], published=published))
    return out


def good_synthesis(subcap: str, eids: list[str]) -> dict:
    cite = " ".join(f"[{e}:F1]" for e in eids[:2])
    return {
        "Dominant_Claim": ("Acme Credit Union runs digital banking on Alkami "
                           "with measured member adoption."),
        "Claim_Label": "FACT",
        "What_We_Found": (
            f"Alkami digital banking went live in Q3 2024 {cite} and the 2025 "
            "annual report restates member adoption at 52 percent, up from 47 "
            "percent at ninety days. The board pack names a quarterly review "
            "cadence owned by the Chief Digital Officer."),
        "Facet_Coverage": "works, value, corroborates",
        "DQ_Works": ("Alkami went live Q3 2024; adoption 47 percent at ninety "
                     "days, 52 percent in 2025."),
        "DQ_Fails": ("NOT_RUN: no delayed or descoped programme surfaced in "
                     "four adversarial queries across 2023-2026."),
        "DQ_Value": ("Adoption is reported to the board quarterly and is tied "
                     "to the 2025 cost-to-serve target."),
        "DQ_Corroborates": ("The 2025 NCUA call report names the same "
                            "digital channel volumes."),
        "DQ_Contradicts": ("NOT_RUN: no enforcement action, complaint or "
                           "abandoned programme found for Acme in 2023-2026."),
        "Triangulation": (f"Two independent sources agree on the launch date "
                          f"and the adoption figure {cite}."),
        "Ceiling_Reasoning": ("Deployment plus measured utilisation supports a "
                             "Competing ceiling, not Differentiating."),
        "Why_It_Matters": ("Adoption at this level changes which channel the "
                           "cost-to-serve programme can lean on in 2026."),
        "DMA_Impact": ("Lifts the digital-channel capability from Building to "
                       "Competing on measured utilisation, not on deployment."),
        "Ceiling_Band": "Competing",
        "Uncertainty": 0.3,
        "Challenge_Verdict": "PASS",
    }


#: A full, independent challenge. `CHALLENGE_DIMENSIONS` is required by name
#: (AUD-0102) and the challenger may not be the synthesis's author
#: (AUD-0018 / AUD-0024).
def challenge(wb, subcap, *, verdict="PASS", actor="finding-challenger"):
    from engine import contract as CC
    return L.record_challenge(
        wb, subcap, verdict=verdict, actor=actor,
        dimensions={d: "PASS" for d in CC.CHALLENGE_DIMENSIONS},
        rationale=("Two independent sources carry the launch date and the "
                   "adoption figure; the ceiling reasoning stops at Competing "
                   "and the contradicts probe returned nothing."),
        ceiling_band_delta="0")


def synthesise(wb, subcap, record, *, author="surface-producer",
               challenger="finding-challenger", verdict="PASS"):
    """Write a synthesis and have a DIFFERENT actor challenge it."""
    out = L.append_synthesis(wb, subcap, record, actor=author)
    challenge(wb, subcap, verdict=verdict, actor=challenger)
    return out


# ── the phases a category-loop test needs closed behind it ───────────────
#
# PRELIM and the completeness gate landed after most of these tests were
# written, and they are RIGHT to fire: a run with no institution profile and
# a workbook with six empty tabs are exactly the Golden 1 shape. So the
# fixtures close them through the ENGINE'S OWN write path rather than by
# bypassing the gate — which makes every loop test also a standing proof
# that both gates are satisfiable from a clean start.

def preflight_doc(*, entity="Acme Credit Union", entity_id="acme-cu") -> dict:
    """A preflight that passes `check` — financial review, census, answers."""
    from engine import preflight as P
    d = P.skeleton(entity=entity, entity_id=entity_id)
    d["financials"]["statements"] = [{
        "source_name": "NCUA Call Report — 2025 Q4",
        "url": "https://ncua.example/callreport/2025",
        "kind": "call_report", "period": "FY2025", "tier": "T1",
        "period_end": "2025-12-31",
        "retrieved_at": "2026-08-29T09:00:00Z"}]
    d["financials"]["revenue_lines"] = [{
        "line": "Interest income — consumer loans", "amount": 612000000,
        "currency": "USD", "period": "FY2025", "share_pct": 100.0,
        "implies_lob": "retail consumer lending", "source": "call report"}]
    d["lob_census"]["lines_of_business"] = [{
        "lob": "retail consumer lending", "revenue_share_pct": 100.0,
        "material": True,
        "basis": "the only call-report revenue line, 100% of FY2025 income"}]
    d["lob_census"]["candidates"] = [
        {"sub_vertical": "CU", "verdict": "ACCEPT",
         "reason": "state-chartered NCUA-insured credit union; the sole "
                   "material revenue line is member retail business"},
        {"sub_vertical": "RB", "verdict": "REJECT",
         "reason": "no OCC or FDIC bank charter exists for this entity"}]
    d["binding_question"] = {
        "asked": True, "tool": "AskUserQuestion",
        "question": "One material retail revenue line and no commercial "
                    "book — bind to which sub-vertical?",
        "options": ["CU", "RB"], "answer": "CU — retail lending in scope",
        "answer_sub_vertical": "CU", "answered_by": "engagement owner",
        "answered_at": "2026-08-29T09:12:00Z"}
    d["mode_question"] = {
        "asked": True, "tool": "AskUserQuestion",
        "question": "What evidence access does this engagement carry?",
        "options": ["PUBLIC", "HYBRID", "INTERNAL"],
        "answer": "PUBLIC — no internal documents provided",
        "answer_mode": "PUBLIC", "answered_by": "engagement owner",
        "answered_at": "2026-08-29T09:12:00Z"}
    d["binding"] = {"sub_vertical": "CU", "evidence_mode": "PUBLIC",
                    "scope_mode": "T1_CORE"}
    return d


def preflight_file(tmp_path, **kw):
    import json as _json
    p = tmp_path / "preflight.json"
    p.write_text(_json.dumps(preflight_doc(**kw), indent=2))
    return p


def close_prelim(run, *, entity="Acme Credit Union"):
    """Do the preliminary research, for real, through the real refusals."""
    from engine import prelim, preflight, techscan
    # The financial review is PRELIM's `financials` section, and it is
    # written by the binding preflight rather than by hand — so a fixture
    # that closes PRELIM records the preflight, exactly as `cli start` does.
    doc = preflight_doc(entity=entity)
    preflight.record(run, doc)
    wb = run.open()
    eid = L.append_evidence(
        wb, source_name="NCUA Call Report — 2025 Q4",
        source_url="https://ncua.example/callreport/2025", tier="T1",
        excerpt=(f"{entity} is a state-chartered, federally insured credit "
                 f"union serving 1.1 million members across 72 branches, "
                 f"with 1,850 full-time employees as at 31 December 2025."),
        subcaps=[], published="2025-12-31")
    prelim.narrate(
        wb, "firmographics", heading=None, evidence=[eid],
        body=(f"{entity} is a state-chartered, federally insured credit union "
              f"serving 1.1 million members through 72 branches and 1,850 "
              f"full-time employees. Its field of membership is geographic "
              f"rather than employer-based, and its balance sheet is "
              f"dominated by consumer lending."))
    prelim.narrate(
        wb, "leadership", heading=None, evidence=[eid],
        body=("Digital ownership sits with a named Chief Digital Officer "
              "reporting to the CEO, alongside a CIO who owns the core "
              "platform. Both roles predate the current programme, so the "
              "institution is not standing up digital ownership for the "
              "first time."))
    # Signal is the DIRECTION, kind is the CLASS — the two questions the C1
    # surface asks separately and the tab used to answer with one column.
    for d, ev, sig, kind, effect in (
            ("2024-06-06", "Core digital banking platform selected",
             "POSITIVE", "PLATFORM",
             "ADVANCED — the core stops being the constraint on channel work"),
            ("2025-03-12", "AI credit decisioning went live",
             "POSITIVE", "DATA",
             "ADVANCED — decisioning moves from manual to modelled"),
            ("2025-09-08", "Credit-offer engine centralised",
             "NEUTRAL", "STRATEGY",
             "UNCHANGED — a consolidation with no stated capability effect")):
        prelim.timeline(wb, date=d, event=ev, signal=sig, kind=kind,
                        body=f"{ev}, as reported in the run's register.",
                        maturity_effect=effect, evidence=[eid])
    prelim.peers(wb, ["Peer Alpha CU", "Peer Beta CU", "Peer Gamma CU"],
                 basis="inferred",
                 rule=("US credit unions in the 15-25bn asset band with a "
                       "geographic field of membership and a public core "
                       "platform decision since 2022"))
    techscan.record(wb, product="Alkami Digital Banking", vendor="Alkami",
                    layer="CUST", status="CONFIRMED",
                    method="public_document",
                    basis="named as the digital banking platform in the 2025 "
                          "call report",
                    providers=["clay", "web"],
                    subcaps=[], evidence_ids=[eid],
                    source_urls=["https://ncua.example/callreport/2025"],
                    as_of="2025-12-31")
    prelim.complete(wb)
    return eid


def make_shippable(wb):
    """Close the completeness gate the honest way — by FILLING, not declaring.

    Every sheet it touches is one a real run fills, so this doubles as proof
    that the gate is satisfiable from a clean start rather than only
    satisfiable by disclosure."""
    from engine import completeness
    if not [r for r in wb.rows("Search_Log") if any(r.values())]:
        L.append_search(wb, subcap=None, facet="works",
                        query="fixture: the search the banked evidence came from",
                        tool="web_search", hits=4, kept=1, outcome="kept 1")
    if not [r for r in wb.rows("DQ_Bank") if any(r.values())]:
        # A minimal bank. `kg build` seeds the real one from the pillar
        # toolkits; a fixture that has no toolkits still needs the sheet to
        # carry the questions the loop is answering, because a run with an
        # empty DQ bank is a run researching from memory.
        for i, subcap in enumerate(small_selection(2)):
            for order, facet in enumerate(("primary", "works", "contradicts")):
                wb.append("DQ_Bank", {
                    "SubCap_ID": subcap, "Order": order, "Facet": facet,
                    "Probe_Tier": "direct",
                    "Question": (f"What does the public record show about "
                                 f"{subcap} — {facet}?"),
                    "Mode_Fit": "BOTH", "Internal_Sources": "",
                    "Public_Sources": "annual report; regulator filing",
                    "Weight_Pct": ""})
    if not [r for r in wb.rows("Tech_Peer_Deployments") if any(r.values())]:
        # T3's peer card. Fill it where there is a product to compare, and
        # DECLARE it where there is not — "no register rows, so no peer
        # deployment to examine" is a true sentence, and the gate exists to
        # make a run say one or the other rather than ship a blank card.
        from engine import techscan
        tech = [r for r in wb.rows("Tech_Register") if r.get("TS_ID")]
        if tech:
            techscan.peer_record(
                wb, ts_id=str(tech[0]["TS_ID"]), peer="Peer Alpha CU",
                deployed=True,
                basis="the peer's own newsroom names the platform live",
                source_url="https://peer-alpha.example/news/core-live")
        else:
            completeness.declare(
                wb, "Tech_Peer_Deployments",
                "the technology register carries no rows, so there is no "
                "product whose peer deployment could be examined")
    return completeness.check(wb)


def sign_off_sections(wb, actor="report-validator"):
    """Give every WRITTEN report section an independent verdict.

    The renderer refuses an unreviewed section (AUD-0153: it refused a
    MISSING one and accepted an unread one, so a report could ship on prose
    nobody had adversarially read). Tests that exercise the RENDERER still
    need real verdicts, so this runs the real review path — a different
    actor, every dimension by name, a note over the rubber-stamp floor —
    rather than writing the column directly.
    """
    from engine import narrative as N
    signed = 0
    for row in wb.rows("Report_Narrative"):
        report = str(row.get("Report") or "").strip()
        sid = str(row.get("Section_ID") or "").strip()
        if report not in N.RS.SPECS or not str(row.get("Body") or "").strip():
            continue
        if str(row.get("Author") or "").strip().lower() == actor.lower():
            continue                       # cannot review its own work
        try:
            N.review(wb, report, sid, verdict="PASS", actor=actor,
                     dimensions={d: "PASS" for d in N.REVIEW_DIMENSIONS},
                     note=("Fixture sign-off: citations resolve, the weighing "
                           "names a rejected reading, and any absence carries "
                           "its ladder."))
            signed += 1
        except N.NarrativeRefusal:
            continue                       # not a spec section; leave it
    return signed
