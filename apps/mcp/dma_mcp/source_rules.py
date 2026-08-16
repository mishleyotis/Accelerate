"""What a source may be used to establish (W6, stage 2.5c).

Every rule here was written from one promoted run that reached a regulated
client's dashboard. None of them is a judgement call the connector is
making on the producer's behalf; each is a rule the assessment method
already states in prose and nothing enforced.

## The four rules

**Tier discipline at registration.** The tier table makes vendor
collateral T5 with an L2 ceiling. A `fortinet.com/customers/<client>`
marketing page was registered T1 with ERS 4.20 and became the sole
evidence for five cells in the run's only Differentiating category. A
tier is a property of the SOURCE, so it is checkable where the source is
named — a self-published customer story, a press release, a vendor
product page cannot be T1 whatever the producer types.

**A relation is not a capability.** Thirty of that run's fifty-two
top-band cells rested on one Form ADV officer list for *Odlum Brown USA*
— a 29-person RIA with US$160M AUM — used to score a parent with CAD
$28B+ and 370+ staff. The plan's first proposal was an entity-SIZE gate;
the stress test refuted it (no field in `evidence_index`, the payload or
the catalogue carries entity size, and parent and subsidiary share a
name, so the domain check passes). What IS checkable is the CLAIM: a
filing about a related entity may evidence ownership, structure and group
policy, and never the other entity's operational capability.

**An absence is not a capability.** `E-112` turned "a search returned NO
disciplinary actions" into a 4.0-4.5 capability score. A clean record is
the absence of a finding, not the presence of a control, and no amount of
it evidences that the control exists.

**One document may not be the sole voice of an assessment.** `E-046`
reached 186 subcaps and `E-016` 184 in one run; the governance layer
flagged it as `DC-06` and shipped anyway. Two things had to be right
here and the first draft got one of them wrong. The cap is per DOCUMENT,
not per evidence id — a filing split into eight registered ids with eight
verbatim spans and one URL defeated a per-id cap entirely in the
adversarial pass, so the canonicalised URL is the key. And it counts SOLE
evidence, not reach: capping total reach at 30% refuses the reference
client's call report (411 of 765 cells, legitimately) while passing the
run this rule exists for (186 of 709). Breadth is not the defect;
monopoly is.

## What these rules deliberately do not do

They do not refuse a source. Vendor collateral is legitimate evidence of
what a vendor claims, and a subsidiary filing is legitimate evidence of
group structure. Each rule constrains what the source may be used to
ESTABLISH, and says so in the words a producer needs to act on it.
"""
from __future__ import annotations

import re

# ── Tier discipline ────────────────────────────────────────────────────
#
# Path and host shapes that make a page the vendor's own marketing about a
# customer. T5, ceiling L2, corroboration required — the tier table's own
# rule, applied where the source is named rather than left to be typed.
_VENDOR_COLLATERAL = (
    (re.compile(r"/customers?/", re.I), "a vendor's customer-story page"),
    (re.compile(r"/case-stud(y|ies)/", re.I), "a vendor case study"),
    (re.compile(r"/success-stor(y|ies)/", re.I), "a vendor success story"),
    (re.compile(r"/testimonial", re.I), "a vendor testimonial page"),
    (re.compile(r"/(press|news)-releases?/", re.I), "a press release"),
    (re.compile(r"/newsroom/", re.I), "a newsroom item"),
    (re.compile(r"/(products?|solutions?|platform)/", re.I),
     "a vendor product or solution page"),
    (re.compile(r"/(blog|resources?|white-?papers?|ebooks?)/", re.I),
     "vendor-published marketing content"),
)
# The tier this evidence class may reach, and the evidence LEVEL its
# ceiling implies — both stated in the refusal so the producer does not
# have to look them up.
VENDOR_MAX_TIER = "T5"
VENDOR_CEILING = "L2"
_TIER_ORDER = {"T1": 1, "T2": 2, "T3": 3, "T4": 4, "T5": 5}


# ── Who is publishing, which the path cannot tell you ──────────────────
#
# THE RULE ABOVE READS THE PATH AND THROWS THE HOST AWAY, and for vendors
# that is right: the corpus's vendors are not enumerable. But `/newsroom/`
# and `/press-release/` are exactly how a REGULATOR publishes too, and a
# regulator is not a vendor — it is the T1 source the evidence tier table
# names first.
#
# Measured 2026-08-16: `ncua.gov/newsroom/press-release/2025/…` — the
# prudential regulator of the credit union being assessed — was refused at
# T1 and again at T2 with "a vendor's own page is evidence of what the
# VENDOR says". The only way past it was to register a T1 regulator at T5,
# which understates the tier and depresses the rank score: the same
# silently-suppresses-the-score failure the tier rules exist to prevent,
# running in the opposite direction.
#
# An ALLOWLIST is wrong for vendors and right here, and the asymmetry is
# the point: vendors are an open set, prudential regulators are a closed
# and small one. Matching is on the registrable suffix, so a lookalike
# host (`ncua.gov.example.com`) does not qualify.
_REGULATORY_SUFFIX = (
    ".gov",            # US federal and state: NCUA, FDIC, OCC, FRB, SEC, CFPB
    ".mil",
    ".gc.ca",          # Canada: OSFI, FCAC
    ".gov.uk",
    ".europa.eu",
    ".gov.au",
    ".govt.nz",
)
#: Prudential regulators, SROs and central banks that do not sit under one
#: of the suffixes above. Short by construction — add only a body that
#: supervises the institutions being assessed.
_REGULATORY_HOST = frozenset({
    "fca.org.uk", "bankofengland.co.uk", "prarulebook.co.uk",
    "osfi-bsif.gc.ca", "bank-banque-canada.ca", "cdic.ca",
    "finra.org", "sipc.org", "ffiec.gov", "bis.org", "iosco.org",
    "ecb.europa.eu", "eba.europa.eu", "esma.europa.eu",
})


def _host(source_url: str | None) -> str:
    m = re.match(r"^[a-z]+://([^/:?#]+)", source_url or "", flags=re.I)
    return (m.group(1) if m else "").lower().rstrip(".")


def regulatory_publisher(source_url: str | None) -> bool:
    """Is this URL published by a regulator or a government body?

    Such a page is a third-party regulatory source, never the assessed
    institution's own marketing, so the vendor-collateral shapes must not
    reach it whatever its path says.
    """
    host = _host(source_url)
    if not host:
        return False
    # Subdomains qualify (`www.fca.org.uk`, `data.fdic.gov`) but a lookalike
    # must not: match the registrable suffix, never a substring.
    if any(host == known or host.endswith("." + known)
           for known in _REGULATORY_HOST):
        return True
    return any(host == suffix.lstrip(".") or host.endswith(suffix)
               for suffix in _REGULATORY_SUFFIX)


def vendor_collateral(source_url: str | None) -> str | None:
    """What KIND of vendor collateral this URL is, or None.

    Deliberately shape-based rather than a vendor allowlist: the corpus's
    vendors are not enumerable, and a rule that needs a list is a rule
    that is wrong about every vendor not on it. The one exception is the
    publisher class the path genuinely cannot express — see
    `regulatory_publisher`.
    """
    if not source_url:
        return None
    if regulatory_publisher(source_url):
        return None
    try:
        path = re.sub(r"^[a-z]+://[^/]+", "", source_url, flags=re.I) or "/"
    except (TypeError, ValueError):
        return None
    for pattern, what in _VENDOR_COLLATERAL:
        if pattern.search(path):
            return what
    return None


def tier_violation(source_url: str | None, tier: str | None) -> str | None:
    """The reason this tier cannot be claimed for this source, or None."""
    what = vendor_collateral(source_url)
    if not what or not tier:
        return None
    if _TIER_ORDER.get(tier, 9) >= _TIER_ORDER[VENDOR_MAX_TIER]:
        return None
    return (
        f"tier_too_high: {source_url} is {what}, which the tier table makes "
        f"{VENDOR_MAX_TIER} with a {VENDOR_CEILING} evidence ceiling and "
        f"corroboration required — it was registered {tier}. A vendor's own "
        "page is evidence of what the VENDOR says, at the vendor's tier; it "
        "is not the institution stating its capability. Register it at "
        f"{VENDOR_MAX_TIER}, or cite the institution's own artefact if one "
        "exists. Five cells in one promoted run took their only evidence "
        "from a page like this, registered T1 at ERS 4.20.")


# ── An absence is not a capability ─────────────────────────────────────
#
# Both spellings, because the adversarial pass found that the negation
# rule was defeated by rephrasing the same span positively: "records a
# clean supervisory history" is "no disciplinary actions" with the
# negation moved into a noun.
_ABSENCE_SPAN = (
    re.compile(r"\bno\s+(?:disciplinary|enforcement|regulatory|adverse|"
               r"material)\s+\w*\s*(?:actions?|findings?|events?|"
               r"proceedings?|history)\b", re.I),
    # "A review OF FILINGS disclosed nothing" — the verb is not adjacent to
    # the noun, and requiring adjacency missed the corpus's own phrasing.
    re.compile(r"\b(?:search|review|check|screen)\w*\b[^.]{0,60}?\b"
               r"(?:returned|found|disclosed|revealed|identified|located)\s+"
               r"(?:no|none|nothing|zero)\b", re.I),
    re.compile(r"\bnot?\s+(?:records?|reports?|filings?|complaints?)\s+"
               r"(?:were\s+)?(?:found|located|identified)\b", re.I),
    re.compile(r"\bclean\s+(?:supervisory|regulatory|disciplinary|"
               r"compliance)\s+(?:history|record|standing)\b", re.I),
    re.compile(r"\b(?:no|zero)\s+(?:records?|results?|matches)\s+"
               r"(?:found|returned|located)\b", re.I),
)


def absence_span(excerpt: str | None) -> bool:
    """True when the excerpt establishes that something was NOT found."""
    if not excerpt:
        return False
    return any(p.search(excerpt) for p in _ABSENCE_SPAN)


def absence_as_capability(excerpt: str | None, claim_type: str | None) -> str | None:
    """The reason this excerpt cannot carry this claim class, or None.

    An absence is a real finding and registers happily as one. What it
    cannot be is a FACT about a capability — which is how a search that
    returned no disciplinary actions became a 4.0-4.5 control score.
    """
    if not absence_span(excerpt) or (claim_type or "").upper() != "FACT":
        return None
    return (
        "absence_is_not_capability: this excerpt records that something was "
        "NOT found — a clean record, an empty search, no filings located. "
        "That is the absence of a finding, not the presence of a control, "
        "and it cannot be registered as a FACT about a capability. Register "
        "it as the absence it is (claim_type INFERENCE, and state in the "
        "cell what the ladder established), or cite the artefact that "
        "DESCRIBES the control. One promoted run scored four cells 4.0-4.5 "
        "on a span of exactly this shape.")


# ── One document as the SOLE voice ─────────────────────────────────────
#
# Two decisions here, and the first was wrong until it was measured.
#
# PER DOCUMENT, not per evidence id: the adversarial pass defeated a
# per-id cap in a few lines by splitting one filing into eight registered
# ids with eight verbatim spans and one URL.
#
# SOLE evidence, not reach. The first version capped a document's total
# reach at 30%, which the corpus refutes in both directions: the reference
# client's broadest document reaches 411 of 765 cells (53.7%) and is
# legitimate — a call report bears on half an assessment — while the run
# this rule was written for peaks at 186 of 709 (26.2%) and would have
# passed. The plan said it plainly and the first implementation did not
# follow: "one 10-K legitimately evidences 180 cells; what is illegitimate
# is 180 cells evidenced by ONLY that one."
#
# Measured on the production corpus, cells for which a document is the only
# citable source:
#
#     Baxter (reference)      49 of 765    6.4%
#     Odlum Brown             74 of 709   10.4%
#     corpus p50 / p95 / p99   0.6 / 6.2 / 13.3%
#     corpus worst                        85.0%
#
# 20% sits above p99 and well clear of both clients, and catches the
# adversarial payload where one Form ADV was the sole voice for 82% of
# cells. It refuses under 1% of the corpus's documents.
SOLE_EVIDENCE_PCT = 20.0


def canonical_document(source_url: str | None) -> str | None:
    """The document key: scheme, `www.`, query, fragment and trailing
    slash dropped. Two ids quoting two spans of one filing share it."""
    if not source_url:
        return None
    u = str(source_url).strip()
    u = re.sub(r"^[a-z]+://", "", u, flags=re.I)
    u = re.sub(r"^www\.", "", u, flags=re.I)
    u = u.split("#", 1)[0].split("?", 1)[0]
    return u.rstrip("/").lower() or None


# The canonical-document expression, in SQL, identical to
# `canonical_document` above. Written once and interpolated, because two
# spellings of one rule is the class this build keeps producing.
_DOC_SQL = (r"rtrim(lower(regexp_replace(regexp_replace("
            r"split_part(split_part(e.source_url,'#',1),'?',1),"
            r"'^[a-z]+://','','i'),'^www\.','','i')),'/')")


def sole_evidence_reach(cur, run_id, e_id: str, source_url: str | None,
                        adding: list) -> str | None:
    """The reason this document may not become the sole voice for these
    further cells, or None.

    A cell counts against the document only where the document would be
    its ONLY citable source. Breadth is legitimate; monopoly is not.
    """
    doc = canonical_document(source_url)
    if not doc or not adding:
        return None
    cur.execute("""SELECT count(DISTINCT subcap_id) FROM subcap_scores
                    WHERE run_id = %s""", (run_id,))
    scored = cur.fetchone()[0]
    if not scored:
        return None                        # 0 of 0 is not 100% (invariant 9)

    # Cells this document links on this run, INCLUDING the ones about to be
    # added, minus every cell some OTHER citable document also links. An
    # excerpt shorter than the contract's floor is not a citable source, so
    # a cell "corroborated" only by an unciteable row is still sole-sourced.
    cur.execute(
        f"""WITH mine AS (
              SELECT DISTINCT l.subcap_id
                FROM evidence_subcap_links l
                JOIN evidence_index e ON e.e_id = l.e_id
               WHERE l.run_id = %s AND {_DOC_SQL} = %s
              UNION
              SELECT unnest(%s::text[])
            )
            SELECT count(*) FROM mine
             WHERE NOT EXISTS (
               SELECT 1 FROM evidence_subcap_links o
                 JOIN evidence_index oe ON oe.e_id = o.e_id
                WHERE o.run_id = %s AND o.subcap_id = mine.subcap_id
                  AND length(oe.excerpt) >= 50
                  AND rtrim(lower(regexp_replace(regexp_replace(
                        split_part(split_part(oe.source_url,'#',1),'?',1),
                        '^[a-z]+://','','i'),'^www\\.','','i')),'/')
                      IS DISTINCT FROM %s)""",
        (run_id, doc, list(dict.fromkeys(adding)), run_id, doc))
    sole = cur.fetchone()[0]
    pct = 100.0 * sole / scored
    if pct <= SOLE_EVIDENCE_PCT:
        return None
    return (
        f"sole_evidence_reach: {doc} would be the ONLY citable source for "
        f"{sole} of {scored} scored cells ({pct:.1f}%), over the "
        f"{SOLE_EVIDENCE_PCT:g}% line. Breadth is not the problem — the "
        "reference client's broadest document bears on 53.7% of its cells "
        "and is legitimate. What this refuses is a document that is the "
        "whole basis for a fifth of an assessment, which is one source "
        "wearing a run's clothes. The cap is per DOCUMENT, not per "
        "evidence id: splitting one filing into several ids does not "
        "divide its voice. Corroborate these cells with a second source, "
        "or cite this one only where it speaks to the capability "
        "specifically. (The registration stands — the id is minted and its "
        "excerpt stored; it is the further cell links that are refused.)")


# ── A relation is not a capability ─────────────────────────────────────
#
# The claim classes a document about a RELATED entity may carry. Ownership
# and structure travel across the relation; capability does not.
RELATION_CLAIMS = ("ownership", "structure", "group policy", "regulatory "
                   "registration", "corporate history")
_RELATION_MARKERS = (
    re.compile(r"\bwholly[- ]owned\b", re.I),
    re.compile(r"\b(?:a\s+)?subsidiar(?:y|ies)\b", re.I),
    re.compile(r"\baffiliat(?:e|ed)\b", re.I),
    re.compile(r"\bparent\s+(?:company|firm|corporation)\b", re.I),
    re.compile(r"\bunder\s+common\s+(?:control|ownership)\b", re.I),
)


def relation_span(excerpt: str | None) -> bool:
    """True when the excerpt is about a related entity rather than this one."""
    if not excerpt:
        return False
    return any(p.search(excerpt) for p in _RELATION_MARKERS)


def relation_note(excerpt: str | None) -> str | None:
    """An identity NOTE, never a refusal.

    Refusing would be wrong: a filing stating that A is wholly owned by B
    is exactly the right evidence for ownership. What it cannot do is
    carry B's operational capability, and the note is what makes a reader
    — and the identity gate — able to see the difference.
    """
    if not relation_span(excerpt):
        return None
    return ("relation_scope: this excerpt describes a RELATED entity "
            "(parent, subsidiary or affiliate). It may evidence "
            + ", ".join(RELATION_CLAIMS) + " — and never the assessed "
            "entity's operational capability. Thirty top-band cells in one "
            "promoted run rested on a subsidiary's officer list, telling a "
            "regulated dealer its surveillance and best-execution "
            "monitoring were Differentiating.")
