"""A small real run, built through the engine's own write path.

Small on purpose: 686 seeded rows is the production shape and a slow test.
The scope-mode and catalogue behaviour is covered in test_contract.py; what
these fixtures exercise is the loop."""
from __future__ import annotations

from engine import contract as C
from engine import ledger as L
from engine import report_spec as RS
from engine import runstate

CAT = "P1C1"


def small_selection(n: int = 6) -> list[str]:
    tax = C.taxonomy()
    return list(tax.cells_in(CAT))[:n]


def two_category_selection(n: int = 4) -> list[str]:
    """Cells from TWO categories — what a run that can exercise
    cross-lane behaviour needs, and what `small_selection` (P1C1 only)
    deliberately is not."""
    tax = C.taxonomy()
    cats = list(tax.categories)[:2]
    out = []
    for cat in cats:
        out += list(tax.cells_in(cat))[:n]
    return out


def new_run(tmp_path, *, n: int = 6, run_id: str = "R-TEST-1",
            prelim: bool = True, folder: bool = True, selected=None):
    """A started run with its PRELIM phase closed and its client folder open.

    Both default ON because both are what a real run has: `orient` withholds
    every category card while PRELIM is open, and a run with no client
    folder is one nobody can find. Pass `prelim=False` / `folder=False` to
    test those gates themselves."""
    run = runstate.start(
        run_id=run_id, entity_name="Acme Credit Union", entity_id="acme-cu",
        sub_vertical="CU", scope_mode="T1_CORE", reference_date="2026-08-29",
        root=tmp_path / "run",
        selected=list(selected) if selected else small_selection(n))
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
    fire_volleys(wb, subcap, n=n)
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


def fire_volleys(wb, subcap, *, n=3, tool="web_search"):
    """Log one search per volley facet for a subcap — the five angles the
    protocol has always required and the floors gate now COUNTS per cell
    (`volleys_incomplete`, 2026-09-03). The `contradicts` query carries two
    adversarial operators so `quality.probes_contradicts` recognises it."""
    queries = {
        # The toolkit's own diagnostic question comes first: the five
        # volleys answer it, and `primary_unfired` blocks a category whose
        # cell never asked it (2026-09-03).
        "primary": f'"Acme Credit Union" {subcap} digital capability statement',
        "works": f'"Acme Credit Union" {subcap} rollout OR "went live"',
        "fails": f'"Acme Credit Union" {subcap} delayed OR descoped OR outage',
        "value": f'"Acme Credit Union" {subcap} adoption OR "reduced by" OR results',
        "contradicts": (f'"Acme Credit Union" {subcap} enforcement OR lawsuit '
                        f'OR criticism OR abandoned'),
        "corroborates": f'"Acme Credit Union" {subcap} regulator OR analyst OR rating',
    }
    for facet, q in queries.items():
        hits = n + 1 if facet in ("works", "value", "corroborates") else 0
        if L._ops_since_checkpoint(wb) >= L.SEARCH_OP_CEILING:
            # The wall is per CONVERSATION and the fixture is one long one:
            # checkpoint and continue, which is exactly what the ceiling
            # exists to force a live run to do (test_search_op_ceiling).
            runstate.checkpoint(wb, f"fixture: volleys up to {subcap}/{facet}")
        L.append_search(wb, subcap=subcap, facet=facet, query=q, tool=tool,
                        hits=hits, kept=n if hits else 0,
                        outcome=(f"kept {n}" if hits else "no hits"))


def declare_absent(wb, subcap, *, actor="research-p1c1-producer"):
    """Fire every volley on an EMPTY cell and close it as a declared absence
    — the only honest way a cell ends a run with NO_EVIDENCE."""
    fire_volleys(wb, subcap, n=0)
    proxy_q = (f'"Acme Credit Union" {subcap} proxy: "chief digital officer" '
               f'OR "head of digital"')
    L.append_search(wb, subcap=subcap, facet="works", query=proxy_q,
                    tool="exa", hits=0, kept=0, outcome="no hits")
    return L.declare_absence(
        wb, subcap, actor=actor,
        ladder=[{"rung": "direct",
                 "query": f'"Acme Credit Union" {subcap} rollout OR "went live"'},
                {"rung": "proxy", "query": proxy_q}],
        proxy_log=("hunted the leadership_title proxy class — a named owner for "
                   "the capability — across the site, LinkedIn and the annual "
                   "report; nothing names one"),
        what_was_hunted=(f"a public artefact naming {subcap} at Acme Credit Union "
                         f"across five volleys and two ladder rungs; the searches "
                         f"returned generic vendor pages and nothing about Acme"))


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
    # The Firmographics TAB — every must-present field STATED or ABSENT with
    # a route (Client Profile §1.1/§1.2; the app's O2 strip).
    from engine import profile
    for field, value, unit in (("website", "acme.example", "n/a"),
                               ("employees", "1850", "headcount"),
                               ("assets_or_aum_or_revenue", "18.4bn", "USD assets"),
                               ("branches", "72", "count"),
                               ("headquarters", "Sacramento, CA", "n/a"),
                               ("founded", "1933", "year"),
                               ("primary_regulator", "NCUA", "n/a"),
                               ("charter", "state-chartered credit union", "n/a"),
                               ("ownership", "member-owned cooperative", "n/a")):
        profile.firmographic(wb, field=field, value=value, unit=unit,
                             as_of="2025-12-31", evidence=eid, confidence="High")
    profile.firmographic(
        wb, field="cagr", state="ABSENT",
        reason=("a credit union publishes no revenue CAGR; the call report "
                "carries assets and shares by quarter, not a growth series"),
        route="NCUA 5300 call reports FY2021-FY2025, searched 2026-08-29")
    prelim.narrate(
        wb, "leadership", heading=None, evidence=[eid],
        body=("Maria Alvarez has been Chief Digital Officer since 2022, "
              "reporting to chief executive Devon Whitfield, alongside a "
              "CIO who owns the core platform. Both roles predate the "
              "current programme, so the institution is not standing up "
              "digital ownership for the first time."))
    # PRELIM now carries what these leaders say in public, not only who they
    # are: the category researchers read a finding against stated direction.
    prelim.narrate(
        wb, "thought_leadership", heading=None, evidence=[eid],
        body=("Maria Alvarez has spoken twice at industry conferences on "
              "moving decisioning off the core, and the institution's own "
              "2025 report repeats that framing. The stated direction is "
              "consistent across both, so a category finding that "
              "contradicts it is worth a second source rather than a "
              "restatement."))
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
    bank_financials(wb, eid)
    prelim.peers(wb, ["Peer Alpha CU", "Peer Beta CU", "Peer Gamma CU"],
                 basis="inferred",
                 rule=("US credit unions in the 15-25bn asset band with a "
                       "geographic field of membership and a public core "
                       "platform decision since 2022"))
    # ALL FOUR LAYERS, in PRELIM. A layer nothing was found in is an
    # ABSENT row carrying the ladder — never a layer left out, which reads
    # to every later surface as a clean estate.
    for product, vendor, layer, status, basis in (
            ("Alkami Digital Banking", "Alkami", "CUST", "CONFIRMED",
             "named as the digital banking platform in the 2025 call report"),
            ("Fiserv DNA", "Fiserv", "OPS", "CONFIRMED",
             "named as the core processor in the 2025 call report"),
            ("Snowflake", "Snowflake", "DATA", "INFERRED",
             "two 2025 engineering postings require production Snowflake"),
            ("public cloud hosting", "none named", "INFRA", "ABSENT",
             "searched the call report, the careers site and three vendor "
             "case-study indexes for a named hosting or datacentre "
             "platform; none is stated anywhere public"),):
        techscan.record(wb, product=product, vendor=vendor,
                        layer=layer, status=status,
                        method="public_document",
                        basis=basis,
                        providers=["clay", "web"],
                        subcaps=[], evidence_ids=[eid],
                        source_urls=["https://ncua.example/callreport/2025"],
                        as_of="2025-12-31")
    prelim.complete(wb)
    return eid


def bank_financials(wb, eid, *, years=5, metrics=("total_assets", "net_income",
                                                  "total_loans")):
    """The five-year trajectory Golden 1 carries (GSY-18): `years` fiscal
    years × `metrics` series, every point resolving to the call report."""
    from engine import profile
    for m_i, metric in enumerate(metrics):
        for y_i in range(years):
            fy = 2021 + y_i
            profile.financial(
                wb, metric=metric, fiscal_year=f"FY{fy}",
                value=round(1000 * (1.08 ** y_i) * (1 + m_i), 1),
                unit="USD m", evidence=eid,
                source_url=f"https://ncua.example/callreport/{fy}",
                basis="NCUA 5300 call report, year-end")


def make_shippable(wb):
    """Close the completeness gate the honest way — by FILLING, not declaring.

    Every sheet it touches is one a real run fills, so this doubles as proof
    that the gate is satisfiable from a clean start rather than only
    satisfiable by disclosure."""
    from engine import completeness
    if not [r for r in wb.rows("Search_Log") if any(r.values())]:
        L.append_search(wb, subcap=None, facet="works",
                        query="fixture: the search the banked evidence came from",
                        tool="web_search", hits=4, kept=1, outcome="kept 1",
                        prelim=True)
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
    # The client's own facts (2026-09-03): filled where the register has a
    # cell to hang a priority on, declared where the run honestly has none.
    ev = {}
    for e in wb.rows("Evidence_Detail"):
        for sc in str(e.get("SubCap_IDs") or e.get("SubCaps") or "").replace(";", ",").split(","):
            sc = sc.strip()
            if sc and sc in wb.selected_subcaps():
                ev.setdefault(sc, []).append(e["E_ID"])
    client_facts(wb, wb.selected_subcaps(), ev)
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


def section_record(section: str, eids, report="client_research", **over) -> dict:
    """A report section record shaped to the PINNED template: every block
    heading in order, body scaled to the section's own word floor, every
    block cited in the prose, and the four argument fields filled."""
    sec = RS.SPECS[report].section(section)
    para = (
            "The public record for this institution is read here against the "
            "question the block asks, and the reading is stated so a reader "
            "can disagree with it rather than accept it. Nothing in this "
            "paragraph rests on a source that is not in the run's own "
            "register, and every figure it carries can be reopened from the "
            "excerpt that supplied it rather than recalled from anywhere "
            "else in the record of the engagement. Where the record is "
            "silent the silence is reported as silence, with the ladder "
            "that establishes it, rather than being read as an answer in "
            "either direction; and where two sources disagree the "
            "disagreement is carried forward rather than resolved by "
            "preference. That is the standard the whole section is written "
            "to, and it is the standard a reader should hold it to when "
            "deciding whether any single sentence here has earned its "
            "place in an argument about this institution.")
    # Scale the filler to the section's own floor: these tests are about the
    # refusals, and a body that trips the word floor first proves nothing
    # about the anatomy the test is aiming at.
    floor = sec.card_min_words or sec.min_words
    nblocks = len(sec.blocks) or 1
    w = len(para.split())
    per = max(1, -(-floor // (nblocks * w)) + 1)
    control = control_block(sec, eids)
    body = []
    for b in sec.blocks or ("",):
        if b:
            body.append(f"## {b}")
        if control:
            # The Doc's MINIMUM DATA, in the countable form `Check` reads —
            # once, in the first block; the whole body is what is counted.
            body.append(control)
            control = ""
        body.extend([para] * per)
        # The renderer reads citations out of the BODY (`reports.CITE_RE`),
        # not out of Evidence_IDs, so a section that cites in the column and
        # not in the prose reads as uncited to the artefact a client opens.
        body.append("Sources for this block: "
                    + " ".join(f"[{e}]" for e in eids) + ".")
        body.append("")
    rec = {
        "Body": "\n".join(body).strip(),
        "Evidence_IDs": ", ".join(eids),
        "Weighing": (
            "The reading above was weighed against the opposite one — that "
            "the silence in the public record reflects an absence of "
            "practice rather than an absence of disclosure — and the "
            "conservative reading was preferred because the institution is "
            "member-owned and publishes little of either kind."),
        "Assumptions": (
            "Assumed that what a member-owned institution publishes "
            "understates what it does; that cuts toward under-reading it."),
        "Bias_Notes": (
            "A public-evidence run over-reads what a client publishes and "
            "under-reads what it does not; this section leans that way."),
        "Inference_Tags": "",
        "Absence_Basis": "",
    }
    rec.update(over)
    return rec


# ── the Doc's countable MINIMUM DATA, satisfied per check ─────────────────
#
# Every section of the pinned templates carries `checks` — a regex, a floor,
# sometimes a ceiling — for the part of its control block a reviewer should
# never count by hand (findings F-NNN, five fiscal years, the four layers).
# The fixture body has to CLEAR those to test anything downstream of the
# write, so each check label maps to the smallest text that satisfies it.
# Keyed by LABEL on purpose: a spec change that adds a check the fixture has
# never met fails loudly here (KeyError) rather than silently in a test that
# was about something else.

def _ids(prefix, n, width):
    return " ".join(f"{prefix}{i:0{width}d}" for i in range(1, n + 1))


def _years(n):
    return " ".join(str(2018 + i) for i in range(n))


def _cite(eids, n):
    return " ".join(f"[{e}]" for e in list(eids)[:max(n, len(eids))])


_CHECK_TEXT = {
    "the website field": lambda c, e: "the website field is stated as acme.example and resolves",
    "findings F-NNN": lambda c, e: _ids("F-", c.min, 3),
    "why-now signals WN-NN": lambda c, e: _ids("WN-", c.min, 2),
    "critical gaps G-NNN": lambda c, e: _ids("G-", c.min, 3),
    "fiscal years": lambda c, e: _years(c.min),
    "fiscal years in the trajectory": lambda c, e: _years(c.min),
    "a computed CAGR": lambda c, e: "a computed CAGR over the trajectory",
    "the peer set lock statement": lambda c, e: "the peer set is locked at the research phase",
    "insight cards IC-NNN": lambda c, e: _ids("IC-", c.min, 3),
    "technology register rows TS-NN": lambda c, e: _ids("TS-", c.min, 2),
    "the four technology layers": lambda c, e: "OPS CUST DATA INFRA",
    "stated priorities FA-NN": lambda c, e: _ids("FA-", c.min, 2),
    "a currency status": lambda c, e: "CONFIRMED_CURRENT",
    "assumptions A-NNN": lambda c, e: _ids("A-", c.min, 3),
    "a recorded negative-search result": lambda c, e: "NONE_FOUND",
    "the handoff status": lambda c, e: "READY",
    "unique E-IDs": _cite,
    "unique E-IDs per pillar": _cite,
    "E-IDs per recommendation": _cite,
    "REC cross-references": lambda c, e: _ids("REC-", c.min, 2),
    "a REC cross-reference per pillar": lambda c, e: _ids("REC-", c.min, 2),
    "REC ids on the root causes": lambda c, e: _ids("REC-", c.min, 2),
    "every recommendation placed in a phase": lambda c, e: _ids("REC-", c.min, 2),
    "the four pillar rows": lambda c, e: "P1 P2 P3 P4",
    "gaps listed per pillar": lambda c, e: "P1 P2 P3 P4",
    "the catalogue version": lambda c, e: "catalogue version v7.0",
    "a Cap_Triggers rule id": lambda c, e: "CAP-R01",
    "all sixteen category rows": lambda c, e: " ".join(
        f"P{p}C{q}" for p in range(1, 5) for q in range(1, 5)),
    "the weights-sum check": lambda c, e: "weights sum to 1.00",
    "the AI and data overlay": lambda c, e: (
        "AI and data overlay: the data foundation rests on the member master "
        "and transaction domains, governed under a catalogue that went live "
        f"this year [{(str(e[0]).split(':')[0] if e else 'E-1')}]; data readiness "
        "is AMBER because lineage is only partial. Applicability is ASSISTIVE, a "
        "model assists the workflow rather than deciding it, and the blocker is "
        "the absence of a feature store. Peer AI posture is inferred from public "
        "signals, not audited. Closing the governance gap lifts readiness to "
        "GREEN and unlocks the autonomous tier the roadmap sequences after it"),
    "the six factor weights": lambda c, e: "0.25 0.20 0.15 0.10 0.10 0.20",
    "three or more phases": lambda c, e: "phase one, phase two, phase three",
    "the provenance label": lambda c, e: "ANALYST",
}


def control_block(sec, eids) -> str:
    """One paragraph that clears every countable check of `sec`."""
    parts = []
    for chk in sec.checks:
        try:
            fn = _CHECK_TEXT[chk.label]
        except KeyError:
            raise KeyError(
                f"the pinned template added check {chk.label!r} to §{sec.id}; "
                f"teach fixtures._CHECK_TEXT the smallest text that clears it")
        text = fn(chk, eids) if fn is not _cite else _cite(eids, chk.min)
        parts.append(text)
    if not parts:
        return ""
    return "Control block, per the Doc: " + "; ".join(parts) + "."


def write_report(wb, report, eids, *, actor=None, run=None):
    """Write EVERY section of one report through `narrative.write`, the
    sanctioned path — one card per pillar in scope for the deep dives, the
    Doc's minimum of cards for every other list section, one passage
    otherwise. Returns the number of rows written."""
    from engine import narrative as N
    spec = RS.SPECS[report]
    actor = actor or ("report-research-producer" if report == "client_research"
                      else "report-assessment-producer")
    n = 0
    for sec in spec.sections:
        if sec.kind == "pillar":
            for p in sorted({c[:2] for c in wb.selected_subcaps()}):
                N.write(wb, report, sec.id, section_record(sec.id, eids, report),
                        actor=actor, card=p, run=run)
                n += 1
        elif sec.is_card:
            for i in range(N.card_floor_for(wb, sec)):
                N.write(wb, report, sec.id, section_record(sec.id, eids, report),
                        actor=actor, card=f"{sec.card_prefix}{i + 1:02d}", run=run)
                n += 1
        else:
            N.write(wb, report, sec.id, section_record(sec.id, eids, report),
                    actor=actor, run=run)
            n += 1
    return n


# ── a researched run, and a scored one ───────────────────────────────────
#
# `researched_run` is the smallest run every category gate PASSES on: five
# worked cells (five items each clears the >=20 per category floor) and one
# declared absence. `scored_run` takes it through the SCORING stage — open,
# score every row, an independent critic, the rollup — to a PASS on the
# SCORING gate, which is the precondition the assessment report writes under.

RATIONALE = ("[EVIDENCE] {e0} shows Alkami digital banking live since Q3 2024 with 47 "
             "percent adoption; {e1} confirms the 2025 restatement at 52 percent. "
             "[MATURITY MATCH] Maps to M3 'standardized, documented' because the "
             "platform is live and measured quarterly. [GAP TO NEXT] No evidence of "
             "optimisation loops or data-driven targeting. [COUNTER] None identified. "
             "[CEILING] Two T2 sources allow 5.0; single-source cap not triggered. "
             "[SO WHAT] For Acme Credit Union this means the channel can carry the "
             "cost-to-serve programme.")


def researched_run(tmp_path, n=6, absent=1):
    run = new_run(tmp_path, n=n)
    wb = run.open()
    cells = wb.selected_subcaps()
    ev = {}
    for cell in cells[:n - absent]:
        ev[cell] = bank_evidence(wb, cell, n=5)
        synthesise(wb, cell, good_synthesis(cell, ev[cell]))
    for cell in cells[n - absent:]:
        declare_absent(wb, cell)
    client_facts(wb, cells, ev)
    from engine import floors_gate
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]
    return run, wb, cells, ev


def client_facts(wb, cells, ev):
    """The research-stage client tabs the Client Profile §6/§7 read — filled
    through `engine.profile` where the fixture has the material (a stated
    priority with its verbatim quote) and DECLARED through `engine.completeness`
    where the run honestly has none (no live matter, nothing outstanding)."""
    from engine import completeness, profile
    first = next((c for c in cells if c in ev), None)
    have_focus = [r for r in wb.rows("Focus_Areas") if r.get("ID")]
    if not first and not have_focus \
            and "Focus_Areas" not in completeness.reasons(wb):
        completeness.declare(
            wb, "Focus_Areas",
            "no client-authored document naming a stated priority was located "
            "in this run's evidence; the priorities section is written as an "
            "honest absence rather than from inference")
    elif first and not have_focus:
        profile.focus(
            wb, fa_id="FA-01", title="Grow digital member adoption",
            quote=("Our members increasingly expect to open accounts, apply for "
                   "loans and manage their money from their phones, and we intend "
                   "to meet them there."),
            document="Annual Report 2025", page="4", cells=[first],
            evidence=ev[first][0], currency="CONFIRMED_CURRENT",
            note="the 2025 report is the latest the client has published")
    if not [r for r in wb.rows("Issue_Register") if any(r.values())]:
        completeness.declare(
            wb, "Issue_Register",
            "the regulator, court and news ladders were walked for open "
            "enforcement, litigation and outage matters and each returned "
            "NONE_FOUND for the assessment window")
    if not [r for r in wb.rows("Enrichment_Needed") if any(r.values())]:
        completeness.declare(
            wb, "Enrichment_Needed",
            "every must-present firmographic is stated or quarantined with a "
            "reason and no category closed with an open enrichment request")


def score_cell(wb, cell, eids, score=2.5, actor="scoring-p1-producer", **over):
    kw = dict(score=score, confidence="MEDIUM",
              rationale=RATIONALE.format(e0=eids[0], e1=eids[1]) if eids else
              ("No evidence located after five volleys and a two-rung ladder "
               "(direct, proxy); the leadership_title proxy was hunted across the "
               "site, LinkedIn and the annual report and nothing names an owner. "
               "Scored at the no-evidence cap and disclosed as an Unknown; an "
               "internal artefact would lift it."),
              actor=actor, ai_applicability="ASSISTIVE",
              data_dependency="member master, transactions",
              data_readiness="AMBER")
    kw.update(over)
    # A claimed AI posture cites the evidence for it — the overlay is
    # evidence-tied now, so an evidenced cell scored ASSISTIVE / AUGMENTED /
    # AUTONOMOUS carries an ai_evidence id. Default to the cell's own first.
    if eids and str(kw.get("ai_applicability", "")).upper() != "NONE" \
            and "ai_evidence" not in kw:
        kw["ai_evidence"] = eids[0]
    from engine import assessment as A
    return A.score(wb, cell, **kw)


def score_all(wb, cells, ev):
    for i, cell in enumerate(cells):
        if cell in ev:
            score_cell(wb, cell, ev[cell], score=2.0 + 0.25 * (i % 3))
        else:
            score_cell(wb, cell, [], score=1.5, confidence="LOW")


def score_stage(run, wb, cells, ev):
    """Take a researched run through the SCORING stage to a PASS on the
    SCORING gate: open, score every row, an independent critic, the rollup,
    then the stage's own catalogue tabs (filled where there is a platform to
    name, declared where the fixture's estate has no peers)."""
    from engine import assessment as A
    from engine import completeness
    A.open_stage(wb, run.qa_dir)
    score_all(wb, cells, ev)
    for pillar in sorted({c[:2] for c in cells}):
        A.critique(wb, pillar=pillar, verdict="PASS", actor="scoring-critic",
                   note="Re-derived 4 of 6 rows across the capabilities; ceilings hold; "
                        "differentiation present; would move nothing.")
    A.rollup(wb, headline="Modern rails, unbuilt member-relationship layer: "
                          "sits a band below digital-leader peers")
    v = A.gate(wb, run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]
    A.solution(wb, sol_id="SOL-01", name="Digital onboarding and account opening",
               platform="Alkami", categories=["P1C1"])
    if not [r for r in wb.rows("Platform_Peer_Adoption") if any(r.values())]:
        completeness.declare(
            wb, "Platform_Peer_Adoption",
            "no peer institution's deployment of the named products could be "
            "examined in this fixture run, so no adoption verdict is recorded")
    return v


def report_ready_run(tmp_path, n=6, absent=1):
    """A run a REPORT SECTION may be written on — researched, gated, scored,
    the SCORING gate PASS — returned as the Run alone, so a test that used to
    open with `new_run(tmp_path)` and write a section can swap one call.

    Since 2026-09-03 `narrative.write` runs the stage preconditions on every
    call (a library write with no run landed a section on an unscored
    workbook — the owner's issue 2 in miniature), so a section can only be
    written on a run in this state. The scored cells' evidence ids are on
    `run.ev`, keyed by cell, and the cells on `run.cells`."""
    run, wb, cells, ev = scored_run(tmp_path, n=n, absent=absent)
    run.cells = cells
    run.ev = ev
    return run


def scored_run(tmp_path, n=6, absent=1):
    """A scored run is also a SHIPPABLE one: the report preconditions read
    `completeness.check`, so a run whose DQ_Bank or Tech_Peer_Deployments is
    empty with no reason recorded cannot take a report section. Filled here
    the honest way (`make_shippable`), so every test that scores a run can
    write on it without re-deriving that list."""
    run, wb, cells, ev = researched_run(tmp_path, n=n, absent=absent)
    score_stage(run, wb, cells, ev)
    make_shippable(wb)
    return run, wb, cells, ev


def write_both_reports(run, wb, cells, ev, *, render=True):
    """Every section of both reports through the sanctioned writer, on a
    scored run, under the stage preconditions; signed off by a different
    actor; rendered. The whole real path, not `wb.append`."""
    from engine import report_spec as RS
    from engine import reports
    make_shippable(wb)
    eids = []
    for c in cells:
        eids += ev.get(c, [])
    eids = eids[:10]
    for key in RS.SPECS:
        write_report(wb, key, eids, run=run)
    sign_off_sections(wb)
    # the REC cards project into the tab the app reads
    from engine import grains
    grains.recommendations(wb)
    out = {}
    if render:
        for key, spec in RS.SPECS.items():
            out[key] = reports.render(wb, spec, run.deliverables)
    return out


def bank_peer_medians(wb, *, median=3.0, p25=2.5, p75=3.5):
    """Record a peer median per category in scope — the research-stage input
    the assessment's Gap_to_Peer is computed from. PRELIM has already frozen
    the peer set (close_prelim); if a bare run has not, freeze one first."""
    from engine import prelim
    if not [r for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID")]:
        prelim.peers(wb, ["Peer Alpha CU", "Peer Beta CU", "Peer Gamma CU"],
                     rule=("federally chartered credit unions in the same asset "
                           "band with a comparable member base and digital posture"),
                     basis="table")
    cats = sorted({c.split(".")[0] for c in wb.selected_subcaps()})
    for cid in cats:
        prelim.peer_median(wb, category=cid, median=median, p25=p25, p75=p75,
                           basis="table",
                           source="peer scores read from the published peer table",
                           peer_scores="2.5, 3.0, 3.5")
    return cats
