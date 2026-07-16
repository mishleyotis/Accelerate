"""Normalize the annotation-wrapped evidence the ingest layer persisted.

Roughly a third of ``evidence_index`` rows in the corpus carry ingest artifacts
that the gold-standard read path must never surface to an AE:

  * multi-E-ID ``e_id`` cells truncated to the column's 16 chars
    (``"E-031,E-032,E-03"``, ``"E-072:F2, E-072:"``) — several ids crammed into
    one row and cut mid-token;
  * ``:F<n>`` fragment-index suffixes on the ids (``"E-041:F1"``);
  * excerpts wrapped in an annotation header, e.g.
    ``"[CEILING: L3.5 ±0.3] [E-006:F1, E-007:F1] Net Zero Pathway: <text> [PRESENCE ≠ UTILIZATION]"``
    or ``"[ERS: 4.60] [FACT] [E-041:F1] Source — Title (T2, CURRENT): <text>"``.

These two helpers recover the *citable* E-ID and the *human* sentence so the
composer/grader read clean data. This is the source fix — every consumer of the
L1 ``EntityState`` benefits, and nothing needs the malformed rows re-ingested.
"""
from __future__ import annotations

import re

# A complete E-ID token. The FIRST match in a comma cell is always intact — only
# the trailing token is cut by the 16-char column — so ``primary_eid`` is safe.
_EID_RE = re.compile(r"E-\d+")
# One or more leading "[...]" annotation groups ("[CEILING: …] [E-…:F#] ").
_LEAD_BRACKETS_RE = re.compile(r"^\s*(?:\[[^\]]*\]\s*)+")
# A tier/status marker — the real evidence text follows it ("(T2, CURRENT): …").
_TIER_MARKER_RE = re.compile(r"\(T\d[^)]*\):\s*")
# Trailing "[...]" markers ("[PRESENCE ≠ UTILIZATION]").
_TRAIL_BRACKETS_RE = re.compile(r"(?:\s*\[[^\]]*\])+\s*$")
# A leading analyst-correction annotation ("Invalidated E-055/F4:", "Validated
# E-012:") — the corrected human fact follows the colon.
_LEAD_VALIDATION_RE = re.compile(r"^\s*(?:in)?validated\b[^:]{0,48}:\s*", re.I)
# Any "[...]" annotation group ANYWHERE — inline "[ERS:4.65] [FACT] [E-016:F2]"
# markers ride mid-string inside pipe-delimited multi-fact rows.
_ANY_BRACKET_RE = re.compile(r"\[[^\]]*\]")


def _clean_fact_segment(seg: str) -> str:
    """Strip inline annotation from ONE fact fragment (a pipe-row cell)."""
    seg = _LEAD_VALIDATION_RE.sub("", seg.strip())
    seg = _ANY_BRACKET_RE.sub(" ", seg)          # drop [ERS:] [FACT] [E-:F] etc.
    m = _TIER_MARKER_RE.search(seg[:160])
    if m and not re.search(r"[.!?]", seg[:m.start()]):
        seg = seg[m.end():]
    return re.sub(r"\s+", " ", seg).strip(" .;")


def primary_eid(cell: str | None, excerpt: str | None = None) -> str | None:
    """The first COMPLETE E-ID for a (possibly mangled, multi-E-ID) e_id cell.

    The first token in a comma-joined cell is never truncated (only the trailing
    one is cut by the column width), so the first ``E-\\d+`` match is the safe,
    citable id. Falls back to the excerpt's leading citation block when the cell
    yields nothing. Returns ``None`` when no E-ID can be recovered.
    """
    for src in (cell or "", excerpt or ""):
        m = _EID_RE.search(src)
        if m:
            return m.group(0)
    return None


_CANON_EID_RE = re.compile(r"^E-[A-Z0-9-]+$")
# A NOISE annotation bracket group anywhere in a finding's prose — a scoring
# ceiling / ERS / FACT / PRESENCE marker or a ":F<n>" evidence fragment id. Clean
# "E-021" citation lists are left alone (they belong to the evidence drawer).
_NOISE_BRACKET_RE = re.compile(r"\[[^\]]*(?:ERS[:=]|FACT|CEILING|PRESENCE|:F\d|±)[^\]]*\]")
# An inline tier/ceiling parenthetical ("(T1, LEGACY):", "(L3.5 ±0.3)").
_INLINE_TIER_RE = re.compile(r"\((?:T\d|L\d)[^)]*\)\s*:?")
# A leaked prompt-scaffold fragment persisted AS a finding ("Each includes the
# evidence basis, maturity implication, and Salesforce solution alignment.").
_FINDING_META_RE = re.compile(
    r"\beach (?:includes|finding|item)\b"
    r"|evidence basis,\s*maturity implication"
    r"|maturity implication,?\s*and salesforce"
    r"|salesforce solution alignment\.?\s*$", re.I)
_FINDING_TEXT_KEYS = ("title", "name", "what", "why", "so_what", "body")


def clean_finding_text(raw: str | None) -> str:
    """Strip ingest annotation from a finding's prose so the D1 story reads
    cleanly: NOISE bracket groups ([ERS:…]/[FACT]/[CEILING…]/[E-…:F#]) and inline
    tier/ceiling parentheticals anywhere in the string. Clean prose (and plain
    E-ID citation lists) is left untouched."""
    s = (raw or "").strip()
    if not s:
        return ""
    s = _NOISE_BRACKET_RE.sub(" ", s)
    s = _INLINE_TIER_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip(" .;:—-")


def clean_finding_items(items: list) -> list:
    """Read-time hygiene for persisted ``top_findings``: drop a leaked
    prompt-scaffold fragment (a meta 'Each includes …' pseudo-finding) and strip
    ingest annotation from every text field of the rest. Order preserved;
    non-dict entries pass through untouched."""
    out: list = []
    for it in items or []:
        if not isinstance(it, dict):
            out.append(it)
            continue
        title = str(it.get("title") or it.get("name") or "")
        body = str(it.get("body") or it.get("what") or "")
        if _FINDING_META_RE.search(title) or _FINDING_META_RE.search(body[:140]):
            continue                        # a scaffold leak, not a real finding
        cleaned = dict(it)
        for k in _FINDING_TEXT_KEYS:
            v = it.get(k)
            if isinstance(v, str) and v.strip():
                c = clean_finding_text(v)
                if c:
                    cleaned[k] = c
        out.append(cleaned)
    return out


def clean_and_dedupe_evidence(
    rows: list[dict], *, limit: int = 8, min_excerpt: int = 24,
) -> list[dict]:
    """Prepare raw ``evidence_index`` rows for an AE-facing evidence drawer.

    Each ``row`` is a dict carrying at least ``e_id`` + ``excerpt`` (plus any
    passthrough display fields). For every row we recover the citable id
    (``primary_eid``; for a non-"E-<digit>" scheme like ``E-INT-0201`` we fall
    back to the first clean token so a whole legitimate drawer is never dropped)
    and the human sentence (``clean_excerpt``). A row that cleans to fewer than
    ``min_excerpt`` chars is an annotation-only / placeholder stub ("(no
    excerpt)", "NEGATIVE PROXY:", a bare "[CEILING …]") and is dropped. Rows are
    deduped by cleaned id, preferring the canonical ``E-###`` row over a column-
    cut fragment and, within the same kind, the longer sentence. Order follows
    the input (already tier/recency-sorted by the caller). Read-only — the
    persisted rows are never mutated.
    """
    by_eid: dict[str, dict] = {}
    for row in rows:
        raw_eid = str(row.get("e_id") or "").strip()
        raw_exc = row.get("excerpt")
        eid = primary_eid(raw_eid, raw_exc)
        if not eid:
            eid = raw_eid.split(",")[0].split(":")[0].strip() or None
        if not eid:
            continue
        exc = clean_excerpt(raw_exc)
        if len(exc) < min_excerpt:
            continue
        is_canon = bool(_CANON_EID_RE.match(raw_eid))
        prev = by_eid.get(eid)
        better = prev is None or (is_canon and not prev["_canon"]) or (
            is_canon == prev["_canon"] and len(exc) > len(prev["excerpt"]))
        if better:
            out = dict(row)
            out["e_id"] = eid
            out["excerpt"] = exc
            out["_canon"] = is_canon
            by_eid[eid] = out
    result = []
    for d in list(by_eid.values())[:limit]:
        d.pop("_canon", None)
        result.append(d)
    return result


def clean_excerpt(raw: str | None) -> str:
    """Strip ingest annotation so the human sentence(s) remain.

    Two shapes occur in the corpus. A single-fact row carries a leading ``[...]``
    header + optional ``(T#, STATUS):`` tier marker + trailing ``[...]`` markers.
    A ``|``-delimited row packs several facts, each with INLINE ``[ERS:…] [FACT]
    [E-…:F#]`` annotation — those are split into separate clean sentences so the
    composer can pick a lead from any of them. A row that is only annotation
    reduces to ``""``.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    if "|" in s:
        facts = [f for f in (_clean_fact_segment(seg) for seg in s.split("|"))
                 if len(f) >= 12]
        return " ".join(f + "." for f in facts).strip()
    s = _LEAD_BRACKETS_RE.sub("", s)
    s = _LEAD_VALIDATION_RE.sub("", s)   # "Invalidated E-055/F4: <corrected fact>"
    # The real text follows a tier/status marker when it terminates a HEADER —
    # bounded near the start AND with no sentence break before it, so a genuine
    # sentence that merely precedes a "(T3, PLANNED):" parenthetical is kept.
    m = _TIER_MARKER_RE.search(s[:160])
    if m and not re.search(r"[.!?]", s[:m.start()]):
        s = s[m.end():]
    s = _TRAIL_BRACKETS_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()
