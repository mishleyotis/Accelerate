"""The value-chain arrangement a client actually reads.

`ccg_value_chains` is DERIVED, not authored: the loader walks the
`21_VC_Mapping_PerSubcap` tab, takes the distinct stage labels a
sub-vertical's column names across ~850 cells, and mints one stage row
per label. That derivation is faithful and it is unreadable. Measured on
the shipped v7.0 workbooks:

    RB  49 raw labels     CU  48     IB  50     RIA 50
    AM  54               CIB 53     CL  52     IC  54     FC  45

and Baxter Credit Union's heatmap served 30 of CU's 48 after the API's
two marker filters. Thirty is not a value chain. Worse, what survived
read as the workbook talking to itself rather than as a credit union
describing its own business:

    MEMBER SERVICING & BRANCH/DIGITAL        136 cells   (pillar 2)
    MEMBER SERVICE & DIGITAL ENGAGEMENT       96 cells   (pillar 4)
    MEMBER SUPPORT & HARDSHIP CARE            76 cells   (pillar 2)

— three labels for one process, in three cases, because three different
pillar workbooks each named the servicing column in their own words. Set
beside the prototype's standard ("Digital Account Opening", "Loan
Origination", "Member Servicing"), the catalogue was shipping a taxonomy
where a client expects a business.

## What this module is, and what it deliberately is not

It is a SELECTION and a RENAMING, per sub-vertical, and nothing else.

  · Every curated stage's cell membership is the UNION of the workbook
    labels folded into it. No cell is assigned by hand, no cell is
    invented, no cell is dropped from a label that is kept. Merging three
    servicing labels yields exactly the cells those three labels named.
  · No score is touched. Scores live in the serving tier and this module
    cannot reach them.
  · The markers are dropped, and dropping them costs nothing measurable.
    A label like "- (N/A)", "Not applicable — credit unions follow NCUA
    framework", "(applicable via CIB pattern)", "(SV-Specific: P3C1.3.CU1)"
    or "Indirect: credit unions also cooperative" is the workbook author
    annotating a cell that maps NOWHERE for this sub-vertical — it is not
    a stage of anyone's value chain. Measured across all nine
    sub-verticals, the cells reachable ONLY through a marker are, without
    exception, another sub-vertical's T2 variant cells (`P1C1.3.IC1`,
    `P2C1.1.FC1`, …) — precisely the cells `subverticals.serves()`
    already keeps off the grid. For CU: 22 such cells, all foreign.
    So the arrangement below covers every cell a run for that
    sub-vertical can serve.

The API kept the marker filters (`value_chain.py::_real`) and should keep
them: a catalogue version loaded before this module existed still carries
raw labels, and the filter is what stops those rendering as columns.

## Why eight, and why the arrangements differ

Eight is the cap the user set, and it is also about the number of stages
that fit the prototype's three-across tile grid without the page becoming
a list. Sub-verticals differ because their businesses do — a credit
union's chain runs field-of-membership → acquisition → onboarding →
servicing, an insurance carrier's runs product design → underwriting →
issuance → claims — and the workbook already carries that difference in
its per-sub-vertical columns. What this module does NOT do is impose one
skeleton on nine businesses: where a sub-vertical's own labels name a
process the others have no equivalent of (CIB's clearing and settlement,
FC's seasonal cash management, IB's account rounding), it keeps it.

Names are sentence case on purpose. The workbook shouts (`MEMBER
SERVICING & BRANCH/DIGITAL`); a page a client reads does not. That also
guarantees no curated name collides with a raw label, which is what makes
applying this map twice a no-op.

## The join is by NAME, so both tables move together

`ccg_vc_mapping.value_chain_stages` names, per cell, the stages that cell
belongs to, and `ccg_value_chains.name` is what it joins to. Renaming one
side alone would silently empty every stage. `curate_row` and
`arrangement` are the two halves of one rename and are applied in the
same transaction — by the loader when a version loads, and by migration
0024 for versions already in the database.
"""
from __future__ import annotations

import re

# A workbook marker: the author saying "this cell maps nowhere here",
# never a stage. Four shapes, all observed in the shipped v7.0 tabs.
_MARKERS = (
    # "- (N/A)"  ·  "Not applicable — credit unions follow NCUA framework"
    re.compile(r"^[-–—\s]*(\(?\s*n/?a\s*\)?|not applicable)\b", re.IGNORECASE),
    # "(applicable via CIB pattern)" — a cross-reference to another
    # sub-vertical's arrangement, not a stage of this one
    re.compile(r"^\(applicable via .+\)$", re.IGNORECASE),
    # "(SV-Specific: P3C1.3.CU1)" — a cell id in the stage column
    re.compile(r"^\(\s*sv-specific\s*:.*\)$", re.IGNORECASE),
    # "Indirect: crop insurance brokers overlap with Farm Credit servicing"
    re.compile(r"^indirect\s*:", re.IGNORECASE),
)


def is_marker(name) -> bool:
    """True when a stage label is the workbook annotating, not naming."""
    text = str(name or "").strip()
    return not text or any(p.match(text) for p in _MARKERS)


# sub-vertical -> the arrangement, in process order: (curated name, the
# workbook labels it folds). Every non-marker label of that sub-vertical
# appears exactly once; `test_value_chain_arrangements` asserts both
# halves of that against the loaded catalogue.
ARRANGEMENTS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {

    # ── Credit unions ────────────────────────────────────────────────
    "CU": (
        ("Field of membership & market strategy", (
            "MARKET & FIELD-OF-MEMBERSHIP STRATEGY",
        )),
        ("Member acquisition & marketing", (
            "PROSPECT & MEMBER ACQUISITION",
            "MEMBER ACQUISITION & FOM MARKETING",
        )),
        ("Member onboarding & account opening", (
            "KYC, MEMBER ONBOARD & SHARE ACCOUNT FUNDING",
            "MEMBER ONBOARDING & ELIGIBILITY",
        )),
        ("Member servicing & digital engagement", (
            "MEMBER SERVICING & BRANCH/DIGITAL",
            "MEMBER SERVICE & DIGITAL ENGAGEMENT",
            "MEMBER SUPPORT & HARDSHIP CARE",
        )),
        # P4C1.9's CU label is "MEMBER LENDING (Auto, Cards, Mortgage)" and
        # every cell under it is another sub-vertical's variant, so it can
        # never carry a CU score on its own. It rides with the growth stage
        # (auto, cards and mortgage ARE the credit union's cross-sell)
        # rather than standing as a stage that renders permanently empty.
        ("Member growth, cross-sell & lending", (
            "MEMBER LIFECYCLE & LOYALTY",
            "MEMBER LENDING (Auto, Cards, Mortgage)",
        )),
        ("Payments & card operations", (
            "PAYMENTS / CARD PROCESSOR",
        )),
        ("Back office, CUSO & shared services", (
            "BACK OFFICE, CUSO & SHARED SERVICES",
            "BACK OFFICE & SHARED SERVICES",
            "AUTOMATION CoE / CUSO",
            "CUSO IT RESILIENCE & BCP",
            "CUSO VENDOR / TPRM",
        )),
        ("Risk, fraud & NCUA compliance", (
            "RISK MGMT / BOARD RISK COMMITTEE",
            "SUPERVISORY COMMITTEE / AUDIT",
            "MEMBER FRAUD / FINANCIAL CRIMES",
            "CYBER & INFOSEC (CUSO)",
            "COMPLIANCE / NCUA REGULATORY",
            "NCUA / CALL REPORT OPS",
            "AML / BSA / OFAC",
            "MEMBER ADVOCACY & CFPB",
            "POLICY & MEMBER ED",
        )),
    ),

    # ── Retail banking ───────────────────────────────────────────────
    "RB": (
        ("Market & customer segment strategy", (
            "MARKET",
        )),
        ("Marketing & lead generation", (
            "PROSPECT & LEAD CAPTURE",
            "MARKETING & LEAD GENERATION",
        )),
        ("Account opening & onboarding", (
            "KYC, ONBOARD & ACTIVATE",
            "ACCOUNT OPENING & ACTIVATION",
            "KYC, ACCOUNT OPENING & FUNDING",
        )),
        ("Everyday servicing & digital support", (
            "CROSS-CHANNEL SERVICING & ENGAGEMENT",
            "DAILY SERVICING & DIGITAL ENGAGEMENT",
            "ISSUE RESOLUTION & DIGITAL SUPPORT",
        )),
        ("Deposits, payments & consumer lending", (
            "PAYMENTS OPS",
            "DEPOSITS, PAYMENTS & TREASURY",
            "CONSUMER LENDING (Cards, Auto, HELOC, Mortgage)",
        )),
        ("Cross-sell, loyalty & retention", (
            "CROSS-SELL, LOYALTY & RETENTION",
        )),
        ("Back office operations & technology platform", (
            "BACK OFFICE OPS, COMPLIANCE & PLATFORM",
            "BACK OFFICE OPS",
            "AUTOMATION COE",
            "TECH RESILIENCE & BCP",
            "VENDOR / TPRM",
        )),
        ("Risk, fraud & regulatory compliance", (
            "OPERATIONAL RISK MGMT",
            "INTERNAL AUDIT",
            "FRAUD OPS / FINANCIAL CRIMES UNIT",
            "CYBER & INFOSEC",
            "COMPLIANCE & REGULATORY AFFAIRS",
            "REGULATORY REPORTING",
            "AML / BSA OPS",
            "CONSUMER PROTECTION OPS",
            "POLICY & TRAINING",
        )),
    ),

    # ── Commercial lending ───────────────────────────────────────────
    "CL": (
        ("Market intelligence & vertical targeting", (
            "MARKET INTELLIGENCE & VERTICAL TARGETING",
        )),
        ("Business development & RM prospecting", (
            "BUSINESS DEVELOPMENT & RM PROSPECTING",
        )),
        ("Client onboarding & credit investigation", (
            "KYC/KYB, BENEFICIAL OWNERSHIP, CREDIT INVESTIGATION",
        )),
        ("Deal origination & underwriting", (
            "LOAN APPLICATION & UNDERWRITING",
            "DEAL ORIGINATION, UNDERWRITING & DOC PREP",
            "CREDIT ANALYSIS, SPREADING & UNDERWRITING",
        )),
        ("Loan servicing & covenant monitoring", (
            "BORROWER SERVICING & COVENANT MGMT",
            "PORTFOLIO MGMT, COVENANT MONITORING & SERVICING",
            "LOAN OPS & SERVICING",
            "COMMERCIAL PAYMENT OPS",
        )),
        ("Portfolio management & relationship review", (
            "BANKER RELATIONSHIP & PORTFOLIO REVIEW",
            "PORTFOLIO ANALYTICS & PROVISIONING",
            "CROSS-SELL & PORTFOLIO EXPANSION",
        )),
        ("Lending operations & technology platform", (
            "BACK OFFICE & REGULATORY OPS",
            "AUTOMATION CoE",
            "PORTFOLIO RESILIENCE & DR",
            "VENDOR / DOC PROVIDER MGMT",
        )),
        ("Credit risk, compliance & regulatory reporting", (
            "CREDIT POLICY & PORTFOLIO RISK",
            "CREDIT AUDIT & QA",
            "CREDIT FRAUD / BORROWER VERIFICATION",
            "CYBER & SECURE LENDING PORTAL",
            "REG COMPLIANCE (HMDA/CRA/FDIC)",
            "REGULATORY & CREDIT ADMIN COMPLIANCE",
            "CALL REPORT & HMDA REPORTING",
            "AML / BSA / KYB",
            "CONSUMER PROTECTION (where applicable)",
            "CREDIT POLICY TRAINING",
        )),
    ),

    # ── Corporate & investment banking ───────────────────────────────
    "CIB": (
        ("Sector research & client intelligence", (
            "SECTOR/CLIENT INTELLIGENCE & RESEARCH",
        )),
        ("Coverage & relationship management", (
            "COVERAGE & RELATIONSHIP MGMT",
            "RM COVERAGE & STRATEGIC ENGAGEMENT",
        )),
        ("Client onboarding & facility setup", (
            "CLIENT ONBOARDING (KYC, EDD)",
            "CLIENT KYC, FACILITY SETUP & ACCESS",
        )),
        ("Trade execution & securities services", (
            "TRADE SERVICES & SECURITIES SERVICES",
        )),
        ("Clearing, settlement & trade operations", (
            "SETTLEMENT / CLEARING OPS",
            "TRADE OPS (MIDDLE/BACK)",
        )),
        ("Wallet share & relationship deepening", (
            "WALLET SHARE & RELATIONSHIP DEEPENING",
        )),
        ("Trading platform & operational technology", (
            "TECHNOLOGY PLATFORM (Front/Middle/Back)",
            "AUTOMATION CoE",
            "TRADING RESILIENCE & BCP",
            "COUNTERPARTY / VENDOR MGMT",
        )),
        ("Market risk, surveillance & compliance", (
            "MARKET & COUNTERPARTY RISK",
            "INTERNAL AUDIT (CIB)",
            "TRADING FRAUD / MARKET ABUSE",
            "TRADE SURVEILLANCE",
            "CYBER & TRADING SECURITY",
            "COMPLIANCE (Reg, MiFID, Volcker)",
            "REGULATORY & OPERATIONAL COMPLIANCE",
            "REGULATORY REPORTING (CFTC/SEC)",
            "AML / KYC / KYB (Institutional)",
            "INSTITUTIONAL CONDUCT OVERSIGHT",
            "COMPLIANCE TRAINING & POLICY",
        )),
    ),

    # ── Farm Credit / ag lending ─────────────────────────────────────
    "FC": (
        ("Ag market intelligence & seasonal forecasting", (
            "AG MARKET INTELLIGENCE & SEASONAL FORECASTING",
            "MARKET",
            "STRATEGY & PORTFOLIO",
        )),
        ("Producer outreach & prospecting", (
            "PRODUCER & AGRIBUSINESS PROSPECTING",
            "AG MARKET INTELLIGENCE & PRODUCER OUTREACH",
            "MARKETING & ACQUISITION",
            "ENGAGE",
        )),
        ("Borrower onboarding & farm due diligence", (
            "KYC, FARM OPERATION DUE DILIGENCE",
            "ELIGIBILITY & ONBOARDING",
        )),
        ("Loan origination & seasonal underwriting", (
            "LOAN APPLICATION & FCA UNDERWRITING",
            "FARM/AG LOAN ORIGINATION & SEASONAL UNDERWRITING",
            "CREDIT ANALYSIS (Cash Flow, Crop Yield, Livestock Cycle)",
        )),
        ("Borrower servicing & seasonal cash management", (
            "BORROWER SERVICING & SEASONAL CASH MGMT",
            "COOPERATIVE MEMBER SERVICING & PATRONAGE",
            "AG LOAN OPS & SERVICING",
            "AG PAYMENT / DISBURSEMENT OPS",
        )),
        ("Patron relationship & portfolio review", (
            "PATRON RELATIONSHIP & SEASONAL PORTFOLIO REVIEW",
            "CROSS-SELL & AG PRODUCT EXPANSION",
            "PORTFOLIO MGMT & FCA REGULATORY OPS",
        )),
        ("Lending platform & operations", (
            "AUTOMATION CoE",
            "BACK OFFICE OPS, COMPLIANCE & PLATFORM",
            "PORTFOLIO RESILIENCE / FCA REPORTING",
            "VENDOR / FARM SERVICE PARTNERS",
        )),
        ("Credit risk, fraud & FCA compliance", (
            "AG PORTFOLIO RISK & WEATHER",
            "FCA AUDIT & QA",
            "AG FRAUD / BORROWER VERIFICATION",
            "CYBER & DIGITAL LENDING SECURITY",
            "COMPLIANCE / FCA REGULATORY",
            "FCA REGULATORY & SCORECARD COMPLIANCE",
            "FCA REPORTING",
            "AML / BSA / KYB (Ag)",
            "BORROWER PROTECTION",
            "AG POLICY & MEMBER ED",
        )),
    ),

    # ── Asset & wealth management ────────────────────────────────────
    "AM": (
        ("Product strategy & investment proposition", (
            "PRODUCT STRATEGY & DEVELOPMENT",
        )),
        ("Brand, marketing & distribution", (
            "BRAND, MARKETING & THOUGHT LEADERSHIP",
            "WHOLESALE & DIRECT DISTRIBUTION",
            "INSTITUTIONAL DISTRIBUTION & RFP RESPONSE",
        )),
        ("Prospecting & relationship conversion", (
            "PROSPECT GENERATION & REFERRAL CULTIVATION",
            "PROSPECT TO RELATIONSHIP CONVERSION",
        )),
        ("Client onboarding & account transfer", (
            "CLIENT ONBOARDING (KYC, Suitability, Account Opening, ACAT)",
            "CLIENT ONBOARDING (Institutional KYC, IMA Negotiation)",
            "INSTITUTIONAL/INTERMEDIARY ONBOARDING",
        )),
        ("Financial planning & portfolio construction", (
            "FINANCIAL PLANNING & PORTFOLIO CONSTRUCTION",
            "PERFORMANCE ANALYTICS & ATTRIBUTION",
            "CROSS-FUND SALES & PERFORMANCE ATTRIBUTION",
        )),
        ("Client service & reporting", (
            "CLIENT SERVICE (INST + RETAIL)",
        )),
        ("Investment operations, custody & advisor platform", (
            "INVESTMENT OPS / MIDDLE OFFICE",
            "HOME OFFICE / MIDDLE OFFICE OPS",
            "CUSTODY & SETTLEMENT",
            "ADVISOR PLATFORM & DATA",
            "TECHNOLOGY PLATFORM & DATA",
            "AUTOMATION CoE",
            "INVESTMENT PLATFORM RESILIENCE",
            "CUSTODIAN / VENDOR MGMT",
        )),
        ("Fiduciary risk, surveillance & compliance", (
            "INVESTMENT & FIDUCIARY RISK",
            "INTERNAL AUDIT (WM)",
            "INVESTMENT FRAUD / SUITABILITY",
            "COMMUNICATIONS SURVEILLANCE",
            "CYBER & ADVISOR PORTAL SECURITY",
            "COMPLIANCE / SUITABILITY OPS",
            "COMPLIANCE & SUITABILITY OPS",
            "COMPLIANCE & RISK MGMT",
            "COMPLIANCE & REGULATORY (Reg BI, Fiduciary, Custody)",
            "SEC / FORM ADV REPORTING",
            "AML / KYC (Wealth)",
            "CLIENT FIDUCIARY OVERSIGHT",
            "ADVISOR COMPLIANCE TRAINING",
        )),
    ),

    # ── RIAs & broker-dealers ────────────────────────────────────────
    "RIA": (
        ("Brand, niche marketing & lead generation", (
            "BRAND, NICHE & CONTENT MARKETING",
            "BRAND & NICHE CONTENT MARKETING",
            "ATTRACT & MANAGE LEADS",
        )),
        ("Client onboarding & account transfer", (
            "ONBOARD & ACAT TRANSFER",
            "ACCOUNT OPENING & CUSTODIAN SETUP",
        )),
        ("Financial planning & portfolio management", (
            "PLANNING, IPS, PORTFOLIO MGMT",
        )),
        ("Client service & performance reporting", (
            "CLIENT SERVICE & PERFORMANCE REPORTING",
        )),
        ("Wallet share & referral growth", (
            "WALLET SHARE & REFERRAL ENGINE",
        )),
        ("Custody, client funds & advisory operations", (
            "CLIENT FUNDS / CUSTODY",
            "RIA/BD OPS",
            "CUSTODIAN / TECH VENDOR MGMT",
        )),
        ("Advisor technology platform & data", (
            "TECHNOLOGY (CRM, Performance, Planning)",
            "ADVISOR PLATFORM & DATA",
            "AUTOMATION & TECHNOLOGY",
            "TECHNOLOGY RESILIENCE",
        )),
        ("Investor protection, surveillance & compliance", (
            "INVESTOR & ADVISORY RISK",
            "INTERNAL AUDIT & FINRA EXAM PREP",
            "INVESTOR FRAUD / SURVEILLANCE",
            "COMMS / SOCIAL SURVEILLANCE",
            "CYBER & CLIENT DATA SECURITY",
            "COMPLIANCE (Reg BI, Form ADV, Custody Rule)",
            "COMPLIANCE (Reg BI, Form ADV)",
            "SEC / FINRA REPORTING",
            "AML / KYC (Investor)",
            "INVESTOR PROTECTION & OVERSIGHT",
            "ADVISOR / RR TRAINING",
        )),
    ),

    # ── Insurance carriers ───────────────────────────────────────────
    "IC": (
        ("Product design & actuarial pricing", (
            "PRODUCT DESIGN & ACTUARIAL PRICING",
        )),
        ("Distribution & agent management", (
            "BROKER/AGENT MGMT & APPOINTMENT",
        )),
        ("Quote, underwriting & risk selection", (
            "QUOTE, BIND & SALES",
            "UNDERWRITING & RISK SELECTION",
            "UNDERWRITING OPS",
        )),
        ("Policy issuance & administration", (
            "POLICY ISSUANCE & ACTIVATION",
            "BIND, ISSUE & POLICY ADMINISTRATION",
            "CLAIMS / POLICY ADMIN OPS",
        )),
        ("Claims handling & settlement", (
            "CLAIMS, ENDORSEMENTS, SERVICE CENTER",
            "FNOL, CLAIMS ADJUDICATION & SETTLEMENT",
            "CLAIMS PAYMENT / BILLING OPS",
        )),
        ("Policyholder engagement & renewal", (
            "POLICYHOLDER ENGAGEMENT & COMMUNICATIONS",
            "RENEWAL, CROSS-SELL, RETENTION",
        )),
        ("Core insurance platform & operations", (
            "TECHNOLOGY (PAS, CMS, Billing, Data)",
            "AUTOMATION CoE",
            "TECH RESILIENCE (PAS/CMS)",
            "REINSURER / VENDOR MGMT",
        )),
        ("Actuarial risk, fraud & statutory compliance", (
            "UNDERWRITING & ACTUARIAL RISK",
            "INTERNAL AUDIT & STATUTORY EXAM",
            "CLAIMS FRAUD / SIU",
            "CYBER & POLICYHOLDER DATA",
            "COMPLIANCE / ACTUARIAL OVERSIGHT",
            "REGULATORY, ACTUARIAL & FINANCIAL OPS",
            "NAIC / STATUTORY REPORTING",
            "AML / KYC (Insurance)",
            "POLICYHOLDER PROTECTION",
            "AGENT / ADJUSTER TRAINING",
        )),
    ),

    # ── Insurance brokerages ─────────────────────────────────────────
    "IB": (
        ("Niche & market strategy", (
            "NICHE & MARKET STRATEGY",
        )),
        ("Lead generation & pipeline management", (
            "PRODUCER LEAD GEN & NICHE MARKETING",
            "CAMPAIGNS, LEADS & OPPORTUNITY MGMT",
        )),
        ("Multi-carrier quoting & binding", (
            "MULTI-CARRIER QUOTING & BINDING",
            "BIND & POLICY DELIVERY",
        )),
        ("Policy servicing & renewal", (
            "POLICY SERVICING, RENEWAL & CROSS-SELL",
            "BROKER OPS / SERVICING",
        )),
        ("Client service & claims advocacy", (
            "CLIENT SERVICE & CLAIMS ADVOCACY",
            "CLIENT REVIEW & ADVOCACY",
            "CLIENT ADVOCACY",
        )),
        ("Account rounding, referrals & book growth", (
            "ACCOUNT ROUNDING & REFERRALS",
            "PERPETUATION & M&A (Book Transfer)",
        )),
        ("Agency platform, premium & commission operations", (
            "AGENCY MGMT SYSTEM & DATA",
            "PREMIUM PROCESSING / COMMISSIONS",
            "PRODUCER COMPENSATION & COMMISSION TRACKING",
            "AUTOMATION & DIGITAL TOOLS",
            "AGENCY MGMT SYSTEM RESILIENCE",
            "CARRIER / VENDOR MGMT",
        )),
        ("E&O risk, fraud & regulatory compliance", (
            "E&O / PROFESSIONAL RISK",
            "INTERNAL AUDIT",
            "BROKER FRAUD / E&O CLAIMS",
            "CYBER & CLIENT DATA SECURITY",
            "COMPLIANCE / E&O OVERSIGHT",
            "STATE INS DEPT REPORTING",
            "AML / KYC (Insurance)",
            "BROKER / AGENT TRAINING",
        )),
    ),
}

# (sub-vertical, workbook label) -> curated stage name. Built once; the
# pair is the key because labels repeat across sub-verticals with
# different meanings ("MARKET" is RB's whole market-strategy stage and
# three stray FC cells; "INTERNAL AUDIT" belongs to RB and to IB).
_INDEX: dict[tuple[str, str], str] = {
    (sv, raw): name
    for sv, stages in ARRANGEMENTS.items()
    for name, raws in stages
    for raw in raws
}


def has_arrangement(sub_vertical) -> bool:
    """Whether a curated arrangement exists for this sub-vertical code.

    A code with none — a vocabulary this module has not been taught —
    passes through untouched rather than being curated into nothing.
    """
    return sub_vertical in ARRANGEMENTS


def arrangement(sub_vertical) -> list[dict]:
    """[{stage_order, name, source_stages}] in process order, or []."""
    return [{"stage_order": i, "name": name, "source_stages": list(raws)}
            for i, (name, raws) in
            enumerate(ARRANGEMENTS.get(sub_vertical, ()), 1)]


def curate_row(sub_vertical, stages) -> list[str]:
    """One cell's `value_chain_stages`, curated.

    Workbook labels map to their curated stage, markers drop out, and the
    result is de-duplicated with first-appearance order preserved (three
    servicing labels on one cell become one servicing stage, once). A
    sub-vertical with no arrangement is returned unchanged: not knowing
    the business is not grounds for erasing what the workbook said.

    A label the arrangement does not name and that is not a marker is
    KEPT. That cannot happen for a loaded version — the test asserts
    total coverage — and if the workbook grows a label tomorrow, keeping
    it renders an ugly stage, while dropping it would silently lose the
    cells. Visible beats invisible.
    """
    raw = [str(s).strip() for s in (stages or ()) if str(s or "").strip()]
    if not has_arrangement(sub_vertical):
        return raw
    out: list[str] = []
    for label in raw:
        if is_marker(label):
            continue
        name = _INDEX.get((sub_vertical, label), label)
        if name not in out:
            out.append(name)
    return out
