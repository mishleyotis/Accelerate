"""Focus-area display sanitation (2026-06-10 final-tests census).

The Client Profile parser captures focus areas liberally — which is
right for recall, but the corpus shows three junk shapes leaking to the
D3 focus view (506 rows: 75 meta-headers, dozens of bare IDs):

  1. META-HEADER rows — the DOCX section heading itself captured as a
     focus area: "2 Top Findings (with Zennify Relevance)",
     "3 Critical Gaps", "All findings aligned to 6 strategic
     objectives…". These are document scaffolding, not priorities.
  2. BARE-ID titles — "F-004" / "G-002" with the real statement hiding
     in the pipe-delimited verbatim quote
     ("F-004 | Teradata to Databricks modernization in flight | …").
     Salvageable: the second pipe segment IS the title.
  3. SENTENCE-BLOB titles — a full paragraph truncated at the column's
     128 chars. Kept, but the display title is clipped at a clause
     boundary so cards don't render mid-word.

This module is the READ-path filter (the sanitizing layer before
anything reaches the frontend — same philosophy as
entity_name_sanity). The rows stay in the table untouched for audit;
only the rendering changes.
"""
from __future__ import annotations

import re

_META_TITLE_RES = (
    # "2 Top Findings", "7 Key Findings (with Zennify Relevance)" …
    re.compile(r"^\d+\s+(top|key|headline)?\s*finding", re.I),
    # "2 Critical Gaps", "2 Critical Gaps1.2 Critical Gaps" …
    re.compile(r"^\d+\s+critical\s+gaps?", re.I),
    re.compile(r"with\s+zennify\s+relevance", re.I),
    re.compile(r"^all\s+findings\s+aligned", re.I),
    # bare section headings captured verbatim
    re.compile(r"^(near|long)[- ]term\s+objectives?\b", re.I),
    re.compile(r"^(strategic\s+)?(objectives?|priorities|focus\s+areas)\s*(\(\d{4}\))?$", re.I),
    # 2026-06-11 QA audit — preamble/scaffolding shapes still leaking:
    #   "The following strategic objectives are extracted directly…"
    #   "The following 10 strategic objectives, ordered by recency…"
    re.compile(r"^the\s+following\b", re.I),
    #   "These eight objectives…" / "This section summarizes…"
    re.compile(r"^(these\s+\w+\s+(objectives?|findings?|priorities)|this\s+section)\b", re.I),
    #   "Implications for Zennify Engagement Timing: SO-01 …" — analyst
    #   commentary about us, not a client priority.
    re.compile(r"^implications\s+for\s+zennify\b", re.I),
    #   "Gap Priority 1 items are required for accurate scoring" — a
    #   scoring-pipeline instruction shipped as BOTH a focus-area title and
    #   a top-finding title (2026-07-13 corpus QA, access-cu).
    re.compile(r"gap\s+priority\s+\d|required\s+for\s+accurate\s+scoring|"
               r"items?\s+are\s+required\s+for\b", re.I),
    #   "Zennify Relevance: Salesforce FSC enables …" — the SO-WHAT-for-us
    #   line the research report threads under each strategic priority. It
    #   is Zennify commentary, never the client's stated priority (2026-07
    #   TowneBank screenshot: these were leaking as focus cards).
    re.compile(r"^zennify\s+relevance\b", re.I),
    #   "Guiding Principles (CSR Report): Soundness, Profitability…" —
    #   corporate-values scaffolding.
    re.compile(r"^guiding\s+principles\b", re.I),
    #   Notebook / code-fence artifacts that survive a DOCX round-trip
    #   ("- if in Colab: `from goog…", fenced blocks). Never a priority.
    re.compile(r"(```|^[-•]\s*if\s+in\s+colab|\bfrom\s+google\.colab\b)", re.I),
)

_META_QUOTE_RES = (
    re.compile(r"^each\s+finding\s+includes", re.I),
    re.compile(r"^seven\s+headline\s+findings", re.I),
)

_BARE_ID_RE = re.compile(r"^[FG]-\d{1,4}$")
# A leading finding-ID token in a pipe-delimited cell ("F-003 | …", "G-17: …").
_FINDING_ID_PREFIX_RE = re.compile(r"^\s*[FG]-?\d{1,4}\b\s*[|:.\u2014\u2013-]*\s*", re.I)
# Emoji / pictographs that a table-row cell carries as visual markers.
_EMOJI_STRIP_RE = re.compile("[\U0001f000-\U0001faff☀-➿\U0001f1e6-\U0001f1ff]+")
# A bare row-index cell ("7", "12") — a finding table-row lead, never a title.
_BARE_INDEX_RE = re.compile(r"^\d{1,3}$")


def title_from_finding_row(cell: str) -> tuple[str, str | None]:
    """(title, body) from a pipe-delimited finding cell.

    Strips a leading ``F-0NN`` / ``G-0NN`` finding-ID (or bare row-index)
    token + emoji, then takes the FIRST non-empty pipe segment as the title
    and the NEXT non-empty segment as the body. This is the fix for the
    ``| Rosie`` bug: naively splitting "F-003 | ROSIE-Salesforce NBA | ROSIE
    = 22 ML models" on ``|`` and grabbing a fragment yielded a broken
    ``| Rosie`` title; here it yields ``("ROSIE-Salesforce NBA", "ROSIE = 22
    ML models")``. Never returns a ``|``-leading fragment or a raw table-row
    dump. When the cell has no pipes it is returned as-is (body None)."""
    raw = _FINDING_ID_PREFIX_RE.sub("", cell or "").strip()
    if "|" not in raw:
        return _EMOJI_STRIP_RE.sub("", raw).strip(), None
    segs: list[str] = []
    for part in raw.split("|"):
        part = _EMOJI_STRIP_RE.sub("", part).strip()
        if not part or _BARE_ID_RE.match(part) or _BARE_INDEX_RE.match(part):
            continue
        segs.append(part)
    if not segs:
        return "", None
    return segs[0], (segs[1] if len(segs) >= 2 else None)


# ── Subvertical scope (2026-07 FCMA fix: "AI Claims Estimation" leaked) ─────
# A focus/priority must map to an IN-SCOPE, evidenced capability for THIS
# entity's subvertical. The A5 Subvertical-NA log is authoritative ("AI Claims
# Estimation is an INSURANCE CARRIER subvertical subcap. FCMA is Commercial
# Lending — sub-vertical mismatch"). Two DB-reachable signals stand in for the
# log when its ids aren't threaded through: the subcap's LOB-overlay LEAF
# suffix, and carrier-only capability NAMES.
#
# LOB-family leaf suffix. The v7.0 catalogue's actual LOB-overlay leaf codes are
# CIB / IC / RIA / CL / CU / AM / IB / FC / RB (a subcap ending ".XX1" is the
# overlay of subvertical XX). Longer codes (CIB/RIA) precede shorter ones; the
# trailing "\d*$" anchor makes ordering safe regardless.
_LOB_LEAF_RE = re.compile(r"\.(CIB|RIA|IC|IB|CU|RB|CL|AM|FC|WM|CB|PB)\d*$", re.I)
# Entity subvertical is stored as a 2-3 letter CODE (RB/CU/CL/AM/RIA/IB/FC/IC/CIB
# — confirmed in the DB), so map the code DIRECTLY to the LOB families in scope
# for it (the leaf code == the subvertical code for the entity's own LOB, plus a
# conservative adjacency where an entity genuinely spans LOBs). A subcap whose
# leaf code is NOT in this set is a different-industry overlay (the NA-1.0 cell).
_SUBVERTICAL_CODE_LOB: dict[str, frozenset[str]] = {
    "RB": frozenset({"RB"}), "CU": frozenset({"CU"}), "CL": frozenset({"CL"}),
    "AM": frozenset({"AM", "RIA"}), "RIA": frozenset({"RIA", "AM"}),
    "IB": frozenset({"IB"}), "FC": frozenset({"FC", "CL"}), "IC": frozenset({"IC"}),
    "CIB": frozenset({"CIB", "CL"}),
    # coded aliases that may appear (commercial/wealth/private bank)
    "CB": frozenset({"CL", "CIB"}), "WM": frozenset({"AM", "RIA"}),
    "PB": frozenset({"AM", "RIA"}),
}
# subvertical keyword → the LOB code(s) IN SCOPE for it (fallback when a full
# subvertical NAME is stored instead of a code; first match wins-union).
_SUBVERTICAL_LOB: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = (
    (re.compile(r"insurance\s+carrier|\bcarrier\b|underwrit", re.I), frozenset({"IC"})),
    (re.compile(r"insurance\s+brok|broker(?:age)?|\bagency\b", re.I), frozenset({"IB"})),
    (re.compile(r"credit\s+union", re.I), frozenset({"CU"})),
    (re.compile(r"registered\s+investment|\bRIA\b", re.I), frozenset({"RIA", "AM"})),
    (re.compile(r"wealth|asset\s+manage|advisor", re.I), frozenset({"AM", "RIA"})),
    (re.compile(r"farm\s+credit|cooperative\s+lend", re.I), frozenset({"FC", "CL"})),
    (re.compile(r"corporate\s+(?:&|and)\s+investment|investment\s+bank", re.I), frozenset({"CIB", "CL"})),
    (re.compile(r"retail\s+bank|consumer\s+bank", re.I), frozenset({"RB"})),
    (re.compile(r"commercial\s+(?:bank|lend)|business\s+bank|\bGSE\b|lending", re.I), frozenset({"CL", "CIB"})),
)
# Insurance-CARRIER-scope capability NAMES that never apply to a lending /
# credit / banking entity (grounded in the A5 NA-log language).
_CARRIER_ONLY_CAP_RE = re.compile(
    r"\bclaims?\s+(?:estimation|adjudication|processing|handling|settlement|fnol)\b"
    r"|\bunderwriting\s+(?:workbench|automation|desk)\b"
    r"|\bpolicy\s+admin(?:istration)?\b"
    r"|\bactuar(?:ial|y)\b|\bcatastrophe\s+model", re.I)


def _lob_code(subcap_id: str) -> str | None:
    m = _LOB_LEAF_RE.search(subcap_id or "")
    return m.group(1).upper() if m else None


def _subvertical_lob_families(subvertical: str | None) -> frozenset[str] | None:
    """LOB codes in scope for ``subvertical``; None when it is unknown (then
    nothing is judged out-of-scope — the honest floor). Exact 2-3 letter CODE
    (how the entity stores it) is resolved first, then a full-NAME keyword
    fallback."""
    if not subvertical:
        return None
    code = subvertical.strip().upper()
    if code in _SUBVERTICAL_CODE_LOB:
        return _SUBVERTICAL_CODE_LOB[code]
    fams: set[str] = set()
    for rx, codes in _SUBVERTICAL_LOB:
        if rx.search(subvertical):
            fams |= codes
    return frozenset(fams) if fams else None


def subcap_out_of_scope(
    subcap_id: str, *, subvertical: str | None = None,
    na_subcap_ids: set[str] | frozenset[str] | None = None,
) -> bool:
    """True when a subcap is NOT in scope for the entity's subvertical: it is
    in the authoritative A5 NA set, or its LOB-overlay leaf suffix belongs to
    a different industry than the subvertical."""
    if na_subcap_ids and subcap_id in na_subcap_ids:
        return True
    code = _lob_code(subcap_id)
    if code:
        fams = _subvertical_lob_families(subvertical)
        if fams is not None and code not in fams:
            return True
    return False


def focus_area_out_of_scope(
    title: str, quote: str, involved_subcap_ids: list[str] | None = None, *,
    subvertical: str | None = None,
    na_subcap_ids: set[str] | frozenset[str] | None = None,
) -> bool:
    """True when a focus area maps to an OUT-OF-SCOPE (subvertical-NA)
    capability and must be dropped — the A5-NA / LOB-mismatch subcap check,
    plus a carrier-only capability NAME named in the title/quote on a
    non-carrier entity ("AI Claims Estimation" on Farm-Credit FCMA). Honest by
    construction: an unknown subvertical with no NA list judges nothing."""
    ids = list(involved_subcap_ids or [])
    na = {str(s).strip() for s in (na_subcap_ids or ()) if str(s).strip()}
    if na and any(i in na for i in ids):
        return True
    fams = _subvertical_lob_families(subvertical)
    if fams is not None and any(
            (c := _lob_code(i)) and c not in fams for i in ids):
        return True
    return bool(
        subvertical
        and not re.search(r"insurance|carrier|underwrit", subvertical, re.I)
        and _CARRIER_ONLY_CAP_RE.search(f"{title or ''} {quote or ''}"))


# A Zennify-DERIVED maturity/gap finding dumped verbatim as a table row —
# "7 | 55% headcount growth … | Growth stress on operations … | …". The
# leading bare index + pipe is the tell (the salvageable "F-004 | …" rows
# keep their finding-ID prefix and are handled separately). These are
# findings, NOT the entity's strategic priorities, so they never render as
# focus cards (operator 2026-07: "focus areas … seems like findings …
# eg Bank of Utah"). Dropping them lets the synthesizer's heuristic fill
# the entity's priority-framed focus areas instead. A 4-digit lead (a year)
# is deliberately NOT matched.
_FINDING_TABLE_ROW_RE = re.compile(r"^\s*\d{1,2}\s*\|\s")

_DISPLAY_MAX = 96

# A strategic-priority TITLE is a concise noun-phrase headline. A raw
# sentence fragment — one that starts mid-word/mid-sentence, runs longer
# than a headline, or ends in a truncated "…" tail — is prose, and prose
# belongs in the quote/description, never in the title (operator 2026-07
# TowneBank screenshot: "Applied is uniquely positioned to deliver
# practical, powerful…" leaked as a card title). Such titles are
# compressed to a headline via nlp.titlecraft (SVO) at render time.
_MAX_HEADLINE_WORDS = 10
_MIN_HEADLINE_LEN = 12


def is_fragment_title(title: str) -> bool:
    """True when ``title`` reads as a prose sentence fragment rather than a
    concise strategic-priority headline: it starts lowercase (cut mid-
    sentence), ends in a "…"/"..." truncation tail, or is longer than a
    headline (> ~10 words). Pure + deterministic — the shared predicate
    used by both this read-path filter and the synthesizer's title-repair
    pass. A finite verb alone does NOT make a fragment (a valid short
    headline like "AI governance is in place; activation surface is
    missing" must survive verbatim)."""
    t = (title or "").strip()
    if not t:
        return False
    if t[0].islower():
        return True
    if t.endswith(("…", "...")):
        return True
    return len(t.split()) > _MAX_HEADLINE_WORDS


def _humanize_fragment(title: str, body: str) -> str:
    """Compress a sentence-fragment title into a headline via nlp.titlecraft
    (SVO). Tries the title text first, then the body/quote; falls back to a
    clause-boundary clip of the original when titlecraft is unavailable or
    yields nothing better. The prose stays in the quote — this only picks a
    cleaner TITLE to render."""
    try:
        from app.services.nlp.titlecraft import make_title
    except Exception:  # pragma: no cover - nlp platform absent
        return _clip(title)
    for source in (title, body):
        if not source:
            continue
        try:
            headline = make_title(source, max_chars=72)
        except Exception:
            headline = ""
        if (headline and len(headline) >= _MIN_HEADLINE_LEN
                and not is_fragment_title(headline)):
            return headline[:_DISPLAY_MAX]
    return _clip(title)


def _title_headline(title: str, body: str) -> str:
    """Display title for a KEPT focus row: a concise strategic-priority
    headline. Clean noun-phrase titles clip through unchanged; sentence
    fragments are humanized (nlp.titlecraft SVO)."""
    t = (title or "").strip()
    if is_fragment_title(t):
        return _humanize_fragment(t, body)
    return _clip(t)


_MACHINE_SUFFIX_RE = re.compile(
    r"\s*\(\s*(?:→|->)?\s*OBJ[- ]?\d+\s*,?\s*(?:HIGH|MEDIUM|LOW)?\s*\)\s*$",
    re.I,
)


def _strip_machine_tokens(text: str) -> str:
    """2026-06-11 live-corpus QA (operator screenshots): the newer
    handoff generation ships focus-area titles as full analyst lines —
    pipe-delimited segments with a trailing "(→OBJ-1, HIGH)" routing
    suffix and wrapping quotes. Display title = the FIRST segment,
    machine suffix + quotes stripped."""
    t = text.strip().strip('"\u201c\u201d').strip()
    t = t.split("|", 1)[0].strip()
    t = _MACHINE_SUFFIX_RE.sub("", t).strip(" -—·")
    return t


def clean_focus_area(
    title: str, quote: str, involved_subcap_ids: list[str] | None = None, *,
    subvertical: str | None = None,
    na_subcap_ids: set[str] | frozenset[str] | None = None,
) -> tuple[bool, str]:
    """(keep, display_title) for one focus_areas row.

    keep=False → the row is document scaffolding OR out-of-scope for this
    entity's subvertical (an A5 subvertical-NA capability); never render it.
    display_title — the title to render when kept (salvaged from the quote for
    bare-ID rows via ``title_from_finding_row``; clause-clipped for blobs).

    The optional ``involved_subcap_ids`` / ``subvertical`` / ``na_subcap_ids``
    are backward-compatible: 2-arg callers keep the prior behaviour; the
    synthesizer passes them so subvertical-NA rows ("AI Claims Estimation" on a
    Farm-Credit entity) are dropped, not shipped."""
    t = (title or "").strip()
    q = (quote or "").strip()
    if not t:
        return False, t

    # subvertical-NA / out-of-scope capability → drop (never render).
    if focus_area_out_of_scope(t, q, involved_subcap_ids,
                               subvertical=subvertical,
                               na_subcap_ids=na_subcap_ids):
        return False, t

    for rx in _META_TITLE_RES:
        if rx.search(t):
            return False, t
    for rx in _META_QUOTE_RES:
        if rx.search(q):
            return False, t

    # A verbatim Zennify maturity-findings table row ("7 | <finding> |
    # <implication> | …") is a derived finding, not a stated strategic
    # priority — never render it as a focus card (Bank of Utah shipped 7
    # of these and nothing else; dropping them lets the synthesizer fill
    # priority-framed focus areas).
    if _FINDING_TABLE_ROW_RE.match(q):
        return False, t

    t = _strip_machine_tokens(t) or t

    # A finding-row TITLE ("F-004 | Teradata to Databricks modernization …",
    # or the full pipe row) — strip the F-0NN token, take the first non-empty
    # pipe segment as the title (defeats the "| Rosie" fragment bug).
    if _BARE_ID_RE.match(t) or ("|" in t and _FINDING_ID_PREFIX_RE.match(t)):
        head, body = title_from_finding_row(q if "|" in q else t)
        if head:
            return True, _title_headline(head, body or head)
        return False, t
    if _BARE_ID_RE.match(t):
        return False, t

    return True, _title_headline(t, q)


def _clip(text: str) -> str:
    if len(text) <= _DISPLAY_MAX:
        return text
    cut = text[:_DISPLAY_MAX]
    # prefer a clause boundary, else the last whole word
    for sep in (". ", "; ", " — ", ", "):
        idx = cut.rfind(sep)
        if idx >= 40:
            return cut[:idx].rstrip() + "…"
    sp = cut.rfind(" ")
    return (cut[:sp] if sp >= 40 else cut).rstrip() + "…"
