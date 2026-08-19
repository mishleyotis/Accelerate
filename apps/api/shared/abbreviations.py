"""One list of abbreviations, and one rule about where they may be rewritten.

Four rounds of sweeps removed abbreviations from promoted prose and a reader
still found `CU` and `Logix FCU` on the page, because the list lived inside the
gate that refuses PAYLOADS and half the abbreviations on screen never travel
through a payload field. They come from:

  · the app's own chrome — a role label, a unit in a footer. Fixed at the
    source, and caught now by a render test rather than by any payload gate.
  · the evidence register — `source_name` on a row the package supplied. The
    connector never sees it as prose and cannot refuse it: the row was written
    by whoever assembled the assessment, and by charter the ingested tier is
    read-only once scanned.

So the list moved here, where the connector's gate, the api's evidence
projection and the tests can all read the same copy.

THE BOUNDARY, and it is the only interesting thing in this file.

A VERBATIM span is what someone actually wrote or said: an excerpt, a quote, a
person's words. Expanding an abbreviation inside one misquotes the source and
breaks the verifier that compares an excerpt against the bytes it came from.
Those are never rewritten, and `EXCERPT_FIELDS` names them.

A LABEL is what this application calls a thing on screen. `source_name` is a
label: it is typed by whoever assembled the package, it is not the artefact's
filed title, and the artefact's identity is its URL — which the drawer shows
beside it. Two rows in this corpus cite the SAME congressional testimony at the
same URL, one labelled "…Logix FCU" by the package and one "…Logix Federal
Credit Union" by a producer. Neither is the filed title. Expanding a label
quotes nobody.

That distinction reverses an earlier reading in this repo, which put
`source_name` and `source_title` in the verbatim set on the grounds that a
source's title is what someone said. It is not: the excerpt is. Owner
instruction, 2026-08-19 — "I still see abbreviations eg CU. Kindly ensure this
is communicated in full ie Credit Unions."
"""
from __future__ import annotations

import re

# Abbreviation -> the expansion that licenses it. Each abbreviation is paired
# with ITS OWN expansion, not with a pool of them: the first version checked
# whether ANY expansion appeared in the field, so "The NCUA call report shows
# the credit union above nine billion" read as clean — "credit union" was
# present, so NCUA was treated as already spelled out. The same containment
# slip bit the expander written beside the gate.
#
# Kept short and specific: an aggressive list would fire on ticker symbols and
# product names, and a gate that cries wolf gets switched off.
EXPANSION = {
    "NCUA": r"National Credit Union Administration",
    "FCU": r"Federal Credit Union",
    "CFPB": r"Consumer Financial Protection Bureau",
    "CU": r"credit union",
    "CUs": r"credit unions",
    "CEO": r"chief executive",
    "CIO": r"chief information officer",
    "COO": r"chief operating officer",
    "CTO": r"chief technology officer",
    "CISO": r"chief information security officer",
    "CFO": r"chief financial officer",
    "CDO": r"chief data officer",
    "KPI": r"key performance indicator",
    "KPIs": r"key performance indicators",
    "ROI": r"return on investment",
    "SLA": r"service level agreement",
    "SLAs": r"service level agreements",
    "NPS": r"Net Promoter Score",
    "FTE": r"full-time employee",
    "FTEs": r"full-time employees",
    "YoY": r"year on year",
    "QoQ": r"quarter on quarter",
    "AE": r"account executive",
    "AEs": r"account executives",
    "API": r"application programming interface",
    "APIs": r"application programming interfaces",
    "UX": r"user experience",
    "UI": r"user interface",
    "B2B": r"business-to-business",
    "B2C": r"business-to-consumer",
}

# Longest first, so `CUs` cannot be consumed as `CU` with a stray `s` left
# behind and `FTEs` cannot become "full-time employees" spelled "full-time
# employee" + "s".
PATTERN = re.compile(r"\b(" + "|".join(
    sorted(EXPANSION, key=len, reverse=True)) + r")\b")

# A verbatim span of an artefact or a person. NEVER rewritten, and never
# gated: see the boundary note above.
EXCERPT_FIELDS = frozenset((
    "excerpt", "quote", "their_words", "verbatim_quote",
    "url", "source_url", "linkedin_url", "email",
    "name", "legal_name", "author_name", "peer_name",
    # An artefact's own filename, its published headline, and the label a
    # trigger was filed under.
    "source_document", "source_filename", "trigger_label",
    "headline", "title_verbatim",
    # Catalogue-controlled vocabulary: these are identifiers with a label
    # route of their own, and expanding one would stop it resolving.
    # `sub_vertical` is the same shape and was the last thing a served-page
    # scan flagged: the token is `CU` and the frontend resolves it through
    # SUBVERTICAL_LABEL to "Credit Union", so the string a reader sees is
    # already spelled out and rewriting the token would break the lookup.
    "platform", "vendor", "l3_area", "l4_feature",
    "sub_vertical", "subvertical",
))

# In a LABEL, a role is part of a title and takes title case: "President &
# Chief Executive, Logix Federal Credit Union", not "President & chief
# executive". In prose the lower-case form is right — "the chief executive
# said" — so the two styles are held apart rather than one being bent to
# serve both.
TITLE_EXPANSION = {
    "CU": "Credit Union",
    "CUs": "Credit Unions",
    "CEO": "Chief Executive",
    "CIO": "Chief Information Officer",
    "COO": "Chief Operating Officer",
    "CTO": "Chief Technology Officer",
    "CISO": "Chief Information Security Officer",
    "CFO": "Chief Financial Officer",
    "CDO": "Chief Data Officer",
    "AE": "Account Executive",
    "AEs": "Account Executives",
}

# Display labels this application writes about an artefact. Expanded on the
# way out, because nothing here is a quotation.
LABEL_FIELDS = frozenset(("source_name", "source_title", "author_role"))


# An IDENTIFIER, not prose. `VC-CU-01` is a catalogue value-chain id and the
# `CU` in it names the chain, not the phrase "credit union" — expanding it
# would break the id, and flagging it sends a producer to fix something that is
# already right. Sixteen of these were counted as abbreviations on a served
# page before the shape was excluded. A token is an identifier when it is a
# hyphen- or underscore-joined run of upper-case letters and digits with at
# least one digit-bearing or multi-part segment: `VC-CU-01`, `TS-14`,
# `P1C1.1.1`, `E-CC-188`.
_IDENT = re.compile(r"[A-Z][A-Z0-9]*(?:[-_.][A-Z0-9]+)+")


def _identifier_spans(text: str):
    return [(m.start(), m.end()) for m in _IDENT.finditer(text)]


def unexplained(text: str):
    """Abbreviations present in `text` without their own expansion beside them.

    Yields each short form once, in the order it appears. A field that already
    spells it out is a second reference and reads correctly as one — but only
    ITS OWN expansion counts. A match inside an identifier is not an
    abbreviation at all and is skipped.
    """
    if not isinstance(text, str) or not text.strip():
        return
    idents = _identifier_spans(text)
    seen = set()
    for m in PATTERN.finditer(text):
        short = m.group(1)
        if short in seen:
            continue
        if any(a <= m.start() and m.end() <= b for a, b in idents):
            continue
        if re.search(re.escape(EXPANSION[short]), text, re.I):
            continue
        seen.add(short)
        yield short


def expand(text, style="prose"):
    """Spell out every abbreviation, keeping the sentence reading naturally.

    `style="label"` is for a display label — a source name, a person's role in
    a byline — where a role reads as part of a title and takes title case.

    Sentence case is preserved. An earlier expander wrote "credit union" at the
    head of a sentence that had begun "CU members…", and three cells were
    refused for a lower-case sentence opening — a tidy-up that broke the thing
    it was tidying. Non-strings pass through unchanged so a caller can map this
    over a projection without type-checking every field.
    """
    if not isinstance(text, str) or not text:
        return text

    table = {**EXPANSION, **TITLE_EXPANSION} if style == "label" else EXPANSION

    idents = _identifier_spans(text)

    def sub(m):
        short = m.group(1)
        # An identifier is not prose: expanding the CU in `VC-CU-01` breaks
        # the id and resolves nothing.
        if any(a <= m.start() and m.end() <= b for a, b in idents):
            return m.group(0)
        full = table[short]
        start = m.start()
        # At the start of the string, or after a sentence end, the expansion
        # opens a sentence and takes a capital.
        head = text[:start].rstrip()
        if not head or head[-1] in ".!?:;" or head.endswith("—"):
            return full[0].upper() + full[1:]
        return full

    out = PATTERN.sub(sub, text)
    # An expansion already present verbatim beside its short form leaves
    # "Federal Credit Union (Federal Credit Union)" behind. Collapse the
    # parenthetical restatement rather than shipping the stutter.
    for full in set(table.values()):
        out = re.sub(re.escape(full) + r"\s*\(" + re.escape(full) + r"\)",
                     full, out, flags=re.I)
    return out
