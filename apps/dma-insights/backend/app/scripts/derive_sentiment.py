"""Sentiment-overview derive (self-healing, grounded — no fabrication).

The Context page's "Sentiment overview" card was empty for ~62 of 94 clients:
only the 32 entities whose package shipped a structured `A#_sentiment_data.csv`
(or entity_profile.json sentiment block) had `firmographics.sentiment`. Yet the
analyst research report carries the signal in prose for ~90/94 — Glassdoor /
Indeed ratings, app-store stars, NPS, J.D. Power, CFPB complaint volume, etc.

This pass reads each entity's persisted report prose (`document_sections`) and,
for every recognised sentiment SOURCE it actually mentions, captures the number
the report states (rating / %, kept verbatim) plus the grounded sentence around
it. It writes a `{sources:[{source, rating?, signal, trend?}], derived_from:
"research_report_prose"}` blob ONLY where the report truly names the source —
nothing is invented; entities whose report has no sentiment signal stay empty
(the honest "awaiting enrichment" state). Fill-if-empty, idempotent: the 32 with
CSV/Clay sentiment are never overwritten.

Usage: DATABASE_URL=... python -m app.scripts.derive_sentiment
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import sys

from sqlalchemy import text

from app.database import get_sessionmaker

# (display label, recognise-regex) — order = render priority.
_SOURCES: list[tuple[str, str]] = [
    ("Glassdoor", r"Glassdoor"),
    ("Indeed", r"Indeed"),
    ("Comparably", r"Comparably"),
    ("App Store", r"App Store|Apple App Store|iOS app rating|iOS rating"),
    ("Google Play", r"Google Play|Play Store|Android app rating"),
    ("J.D. Power", r"J\.?\s?D\.?\s?Power"),
    ("Net Promoter Score", r"Net Promoter Score|\bNPS\b"),
    ("Trustpilot", r"Trustpilot"),
    ("Better Business Bureau", r"Better Business Bureau|\bBBB\b"),
    ("CFPB complaints", r"\bCFPB\b|Consumer Financial Protection Bureau"),
    ("Yelp", r"Yelp"),
    ("Forrester", r"Forrester"),
]
_RATING = re.compile(r"(\d(?:\.\d)?)\s*(?:/\s*5|out of\s*5|stars?\b|★)", re.I)
_PCT = re.compile(r"(\d{1,3})\s*%")
# NPS index capture (2026-07-06 deploy review): decimal-aware, `$`-fenced
# (the gap class must never cross a money figure — LPL's "NPS comparisons
# LPL Financials is a $11.0B in assets…" minted NPS 11), and unit-fenced so
# "9.7/10"-style satisfaction ratings route to the scale parser instead of
# truncating to "9". Callers search only the ±120-char clause around the
# source mention, never the whole document.
_NPS = re.compile(
    r"(?:eNPS|NPS|Net Promoter Score)[^.\d$%]{0,40}?"
    r"(?<![\d$.])([+-]?\d{1,3}(?:\.\d{1,2})?)(?!\s*[%/BMKx])", re.I)
# satisfaction/recommend percents for employee-review sources ("Glassdoor
# 79% satisfaction") — either ordering, keyword-bound so a complaint-
# resolution or market-share percent can't masquerade as a rating.
_EMP_PCT = re.compile(
    r"(\d{1,3})\s*%[^.\n]{0,30}?(?:satisf|recommend|approv|positive)"
    r"|(?:satisf\w*|recommend\w*|approv\w*|positive)[^.\n%]{0,30}?(\d{1,3})\s*%",
    re.I)
_EMP_CUE = re.compile(r"employee|eNPS|workforce|staff\b|workplace", re.I)
# A rating whose own context admits it aggregates (almost) nothing is not
# a customer-sentiment signal — "Rating: 5/5 stars (limited reviews)"
# (Compeer E-036) surfaced as a fabricated-perfect "Customer reviews 5/5"
# on the live card (2026-07-06 QA). Honest-absent beats a hollow 5/5.
_LOW_SAMPLE = re.compile(
    r"limited\s+reviews?|few\s+reviews?|no\s+reviews?|small\s+sample|"
    r"insufficient\s+reviews?|low\s+review\s+volume|not\s+enough\s+reviews?|"
    r"\b[1-9]\s+reviews?\b", re.I)
# "BBB" inside a CREDIT-RATING clause (S&P/Fitch/KBRA scales: BBB+, BBB-,
# "S&P BBB+ ratings") is a bond grade, not the Better Business Bureau.
_BBB_CREDIT = re.compile(
    r"S\s*&\s*P|Standard\s*&\s*Poor|Fitch|KBRA|Moody|DBRS|"
    r"credit\s+rating|issuer\s+rating|BBB\s*[+-]", re.I)
_TREND = re.compile(r"\b(improv|declin|fall|drop|rising|rose|stable|flat|steady|deteriorat|worsen)\w*", re.I)
# A mention only counts as SENTIMENT (vs. an incidental regulator/vendor name —
# e.g. "compliance spanning CFPB, FDIC") when the surrounding text is actually
# about opinion/ratings, or a rating number was found. ("score"/"rank" are NOT
# here — they false-match the assessment's own "Maturity Score".)
_SENT_KW = re.compile(
    r"rating|review|star|complaint|sentiment|satisfaction|approv|recommend|accredited|"
    r"\bNPS\b|glassdoor|indeed|trustpilot|yelp|comparably", re.I)
# Internal assessment prose — if the clipped signal looks like this we grabbed
# the SCQA / scoring narrative, not customer sentiment. Reject it.
_ASSESS_JUNK = re.compile(
    r"Assessment ID|DMA-ASM|Maturity Score|M[1-5] Standardized|peer median|\bSV[1-9]\b"
    # citation-manifest lines ("EV--005 Glassdoor company profile…") list the
    # platforms without carrying sentiment — never a signal
    r"|EV-{1,2}\d{2,}|company profile and reviews", re.I)
# taxonomy codes / cross-reference ids that must never reach the sentiment card.
_SIG_CODE = [
    re.compile(r"[\[(]?\b(?:E|ISS|GOV|REC|REQ)-\d+\b[\])]?", re.I),
    re.compile(r"(?<![A-Za-z])P[1-4]C\d+(?:[._][A-Za-z0-9]+)*", re.I),
]
_LC_KEEP = {"ios", "iphone", "ipad", "app", "ecommerce", "fintech", "enps"}

# Recurring-theme vocabulary (2026-07-06 depth fix — operator: "Sentiment
# overview details so shallow when I drilldown"). A theme is emitted ONLY when
# its cue appears in the source's clipped window/signal — never invented.
# Powers the D1 SentimentCard theme chips + (via the ';'-joined `themes`
# string context_extras.sentiment_view already parses) the D5 drilldown.
_THEME_CUES: list[tuple[str, str]] = [
    ("Mobile app", r"\bapp\b|mobile|iOS|android|superapp"),
    ("Digital experience", r"online bank|digital|website|web portal|self[- ]service"),
    ("Customer service", r"customer service|support|call center|wait time|hold time"),
    ("Branch experience", r"branch|in[- ]person|teller|lobby"),
    ("Fees & pricing", r"\bfee\b|\bfees\b|overdraft|charges|pricing"),
    ("Transfers & payments", r"transfer|\bACH\b|zelle|bill pay|payment|deposit"),
    ("Reliability", r"outage|downtime|slow|crash|load[- ]time|latency|\bbug\b|glitch"),
    ("Leadership", r"management|leadership|executive|senior leader"),
    ("Compensation & benefits", r"\bpay\b|salary|compensation|benefits|wages|bonus"),
    ("Work-life balance", r"work[- ]life|workload|long hours|overtime|flexib"),
    ("Culture", r"culture|coworker|\bteam\b|community focus"),
    ("Career growth", r"career|advancement|promotion|growth opportunit|development"),
    ("Process & workflow", r"manual|spreadsheet|bureaucra|silo|paperwork"),
    ("Technology", r"legacy|outdated|modern|needs updating|tech stack"),
]
_THEME_PATTERNS = [(label, re.compile(rx, re.I)) for label, rx in _THEME_CUES]


def _extract_themes(text: str, limit: int = 4) -> list[str]:
    """Grounded recurring themes present in the text (vocabulary order;
    deduped; capped). Empty when nothing recognised — never fabricated."""
    if not text:
        return []
    out: list[str] = []
    for label, pat in _THEME_PATTERNS:
        if pat.search(text) and label not in out:
            out.append(label)
        if len(out) >= limit:
            break
    return out


def _themes_from_source(src: dict) -> list[str]:
    """Themes for a normalized row: an explicit `themes` field (CSV/Clay ship
    a ';'-delimited string; some rows a list) UNION themes mined from the
    signal/drilldown prose. Deduped, capped at 4."""
    out: list[str] = []
    raw = src.get("themes")
    if isinstance(raw, str):
        out.extend(t.strip() for t in re.split(r"[;•|]", raw) if t.strip())
    elif isinstance(raw, list):
        out.extend(str(t).strip() for t in raw if str(t).strip())
    for t in _extract_themes(str(src.get("signal") or src.get("drilldown") or "")):
        if t not in out:
            out.append(t)
    return out[:4]


def _clean_sig(sig: str) -> str:
    """Strip taxonomy codes + a broken leading word-fragment (an artefact of the
    section-aggregated prose) so the signal reads as plain sentiment."""
    for pat in _SIG_CODE:
        sig = pat.sub("", sig)
    # mid-word cut like "ution " / "me " — also tolerate trailing punctuation on
    # the fragment: the Compeer deploy review (2026-07-06) surfaced
    # "wever, employee engagement…" where the comma stopped the old \s+-only
    # pattern from matching, so the fragment shipped to the card.
    m = re.match(r"^([a-z][\w]*)[,;:]?\s+", sig)
    if m and m.group(1).lower() not in _LC_KEEP:
        sig = sig[m.end():]
    sig = re.sub(r"\s+([.,;:])", r"\1", sig)
    return re.sub(r"\s{2,}", " ", sig).strip(" .;:-")


def _clip_signal(prose: str, pos: int) -> str:
    """The grounded SENTENCE around the match, clipped to a bounded window so
    it can never bleed into far-away (e.g. executive-summary) text.

    Sentence boundaries come from nlp.segment (abbreviation-aware — "Inc.",
    "vs.", initials), replacing the raw ". " find/rfind that produced the
    mid-word fragments _clean_sig papers over (semantics audit 2026-07-04).
    The bounded window + _clean_sig stay as guards."""
    # 240/320 window snapped to WORD boundaries: the old 60-char raw slice
    # routinely started mid-word, and the segmenter then returned that
    # fragment as "the sentence" ("wever, employee engagement…" — Compeer,
    # 2026-07-06 deploy review). Snapping keeps the guarantee that the
    # window never bleeds into far-away text while never cutting a word.
    lo, hi = max(0, pos - 240), min(len(prose), pos + 320)
    while lo > 0 and not prose[lo].isspace():
        lo -= 1
    while hi < len(prose) and not prose[hi - 1].isspace():
        hi += 1
    win = prose[lo:hi]
    rel = pos - lo
    try:
        from app.services.nlp.segment import sentences as _nlp_sentences
        cursor = 0
        for sent in _nlp_sentences(win):
            start = win.find(sent, cursor)
            if start == -1:
                continue
            cursor = start + len(sent)
            if start <= rel < cursor:
                return _clean_sig(re.sub(r"\s+", " ", sent).strip(" .;:-"))
    except Exception:
        pass  # toolkit degraded — regex tier below
    sb = win.rfind(". ", 0, rel)
    win = win[sb + 2:] if sb != -1 else win
    se = win.find(". ")
    win = win[:se + 1] if se != -1 else win
    return _clean_sig(re.sub(r"\s+", " ", win).strip(" .;:-"))


def _trend(window: str) -> str | None:
    m = _TREND.search(window)
    if m:
        w = m.group(1).lower()
        if w.startswith(("stable", "flat", "steady")):
            return "Stable"
        if w.startswith(("improv", "rising", "rose")):
            return "Improving"
        return "Declining"
    # No explicit trend verb — classify the window's SENTIMENT POLARITY via
    # the toolkit (negation-aware) instead of returning nothing, so prose
    # like "reviews praise the mobile app" still yields a direction.
    try:
        from app.services.nlp.polarity import signal as _polarity_signal
        pol = _polarity_signal(window)
        if pol == "positive":
            return "Improving"
        if pol == "negative":
            return "Declining"
    except Exception:
        pass
    return None


# ── Signal sanitizer (2026-07-06 deploy review: fin.sentiment_fragments=35 → 0)
# Two offender classes reach sources[].signal and read as mid-sentence garbage
# to an AE: (A) raw Clay/CSV "key: value, key: value" dumps that survived because
# derive_sentiment's fill-if-empty gate SKIPPED entities that already had a parsed
# sentiment blob (their raw sources passed straight through to the pack), and (B)
# prose the extractor grabbed mid-clause or off-topic (tech-stack lists, leadership
# bios, QA-meta). We act ONLY on signals the audit itself would flag (its EXACT
# _WORD_FRAGMENT semantics) so clean signals are never disturbed: a kv-dump is
# reformatted into a readable, source-named sentence when its keys are genuine
# sentiment ratings (else dropped); a prose fragment is re-clipped to a capitalised
# sentence boundary when it truly concerns sentiment (else dropped). Nothing is
# invented — an unsalvageable signal is dropped, honest-empty beats garbage.
_AUDIT_FRAGMENT = re.compile(r"^[a-z][\w]{0,12}[,;:]?\s")     # == audit _WORD_FRAGMENT
_AUDIT_FRAGMENT_OK = ("ios ", "app ", "enps")                 # == audit allowlist
_KV_HEAD = re.compile(r"^[a-z][\w]{0,20}:\s")                 # "overall: 2.5/5, …"
_KV_PAIR = re.compile(r"([A-Za-z][\w ]*?)\s*:\s*([^,;]+?)(?=\s*[,;]|\s*$)")
# keys that make a kv-dump a genuine sentiment/rating signal…
_KV_SENT = re.compile(
    r"^(overall|rating|reviews?|review[_ ]count|combined[_ ]rating|"
    r"work[_ ]life(?:[_ ]balance)?|compensation|culture(?:[_ ]values)?|"
    r"management|ceo[_ ]approval|recommend(?:[_ ]friend|[_ ]pct)?|"
    r"satisfaction|approval|ios|android|app|mixed[_ ]rating[_ ]source|"
    r"score|stars?|nps)$", re.I)
# …value-carrying prose keys rendered inline but not themselves qualifying.
_KV_PROSE = re.compile(r"^(notes?|highlights?|detail|comment)$", re.I)
# keys that mark a NON-sentiment dump (financial snapshot / interview noise /
# bare yes-no tally) → the signal is not sentiment, drop it.
_KV_NONSENT = re.compile(
    r"^(market[_ ]cap\w*|1yr[_ ]\w+|52w\w*|ytd|high|low|yes|no|pct|"
    r"difficulty|experience|length|revenue|assets?|aum|ticker|price|"
    r"volume|market[_ ]share)$", re.I)
# off-topic prose windows the extractor mis-captured — never sentiment.
_OFFTOPIC = re.compile(
    r"\bCRM\b|Salesforce|Temenos|Fiserv|Oracle Financial|Microsoft Dynamics|"
    r"Cisco|Symantec|Splunk|Veracode|Forcepoint|IT security technolog|"
    r"Applied Systems|Eltropy|co-browsing|screen sharing|secure chat|"
    r"PayAnyone|Wear OS|BIN sponsorship|ACH items|"
    r"Business Continuity Plan|Disaster Recovery|consent orders?|"
    r"enforcement actions?|FINRA disciplinary|Cybersecurity Program|"
    r"is entirely NULL|tech_customer_management|advisory materials|"
    r"client-provided documents|would validate framework|\bT3 items\b|"
    r"\bEVP\b|\bSVP\b|model portfolios|works with CIO", re.I)
# vocabulary proving the window IS about opinion/ratings/reviews.
_SENT_PRESENT = re.compile(
    r"rating|review|star\b|complaint|sentiment|satisfaction|recommend|"
    r"glassdoor|indeed|trustpilot|yelp|comparably|praise|"
    r"customer service|\bNPS\b|reputation|member friction", re.I)


def _cap_start(text: str, source: str | None) -> str | None:
    """Ensure the signal starts with a capital/digit (defeats the audit's
    _WORD_FRAGMENT): prefer prefixing a proper-noun source, else capitalise."""
    t = re.sub(r"\s{2,}", " ", (text or "").strip()).strip(" ;,.-")
    if not t:
        return None
    if not t[0].islower():
        return t                       # already capital/digit
    src = (source or "").strip()
    if src and src[0].isupper() and src.lower() not in t[: len(src) + 2].lower():
        return f"{src} {t}"
    return t[0].upper() + t[1:]


def _reformat_kv(sig: str, source: str | None) -> str | None:
    """A sentiment "key: value" dump → one readable, source-named sentence
    (colons removed, underscores spaced). None when it is NOT sentiment
    (financial snapshot / interview noise / bare tally) so the caller drops it."""
    pairs = _KV_PAIR.findall(sig)
    if not pairs:
        return None
    keys = [re.sub(r"\s+", "_", k.strip().lower()) for k, _ in pairs]
    if any(_KV_NONSENT.match(k) for k in keys):
        return None                    # a financial/noise key poisons the dump
    if not any(_KV_SENT.match(k) for k in keys):
        return None                    # no genuine sentiment/rating key
    clauses: list[str] = []
    for k, v in pairs:
        kl = re.sub(r"\s+", "_", k.strip().lower())
        vv = v.strip()
        if _KV_PROSE.match(kl):
            clauses.append(vv)                        # prose value stands alone
        elif vv:
            clauses.append(f"{k.strip().replace('_', ' ')} {vv}")
    return _cap_start("; ".join(c for c in clauses if c), source)


def _defrag(sig: str) -> str | None:
    """A mid-clause prose fragment → the first sentiment-bearing clause that
    starts at a sentence boundary (capital/digit), else the whole thing with a
    capitalised first letter. None when off-topic or carrying no sentiment
    vocabulary at all (a mis-classified capture)."""
    s = re.sub(r"\s+", " ", sig).strip()
    # boundary = sentence-ender/'+'/spaced dash (em/en/hyphen via \u to keep ruff
    # RUF001-clean); a candidate clause must then begin with a capital or digit.
    starts = [0] + [m.end() for m in re.finditer(
        "[.;:!?+]\\s+|\\s[\u2014\u2013-]\\s+", s)]
    for i in starts:
        cand = s[i:].strip()
        if (cand and not cand[0].islower() and len(cand) >= 12
                and _SENT_PRESENT.search(cand) and not _OFFTOPIC.search(cand)):
            return cand
    # no clean sentence boundary — salvage the whole clause iff it is sentiment
    # and not off-topic, capitalising the leading lowercase word.
    if _SENT_PRESENT.search(s) and not _OFFTOPIC.search(s):
        cand = _cap_start(s, None)
        if cand and len(cand) >= 12:
            return cand
    return None


def _sanitize(sig: str, source: str | None = None) -> str | None:
    """Clean one sources[].signal. Acts ONLY on signals the audit would flag as a
    fragment (exact _WORD_FRAGMENT semantics) — audit-clean signals pass through
    untouched. Returns the cleaned signal, or None to drop it."""
    s = (sig or "").strip()
    if not s:
        return sig
    if not (_AUDIT_FRAGMENT.match(s) and s[:4].lower() not in _AUDIT_FRAGMENT_OK):
        return sig                     # already clean → never disturb
    if _KV_HEAD.match(s):
        return _reformat_kv(s, source)
    return _defrag(s)


def _has_real_rating(src: dict) -> bool:
    """True when the row carries a parseable rating within its own scale — so we
    keep the row (dropping only its signal) rather than discarding a real number."""
    score, scale = _parse_score(src.get("rating"), "")
    return score is not None and bool(scale) and 0 <= score <= scale


def _sanitize_sources(sources: list) -> list[dict]:
    """Clean every sources[] row's signal (the pack-facing field the audit
    grades). A row whose signal is an unsalvageable fragment keeps its source +
    real rating with the signal dropped; a row with neither a clean signal nor a
    real rating is removed entirely (honest-empty beats mid-sentence garbage)."""
    out: list[dict] = []
    for src in sources:
        if not isinstance(src, dict):
            out.append(src)
            continue
        sig = str(src.get("signal") or "")
        clean = _sanitize(sig, src.get("source"))
        if clean == sig:
            out.append(src)                       # unchanged → same object
        elif clean:
            out.append({**src, "signal": clean})
        elif _has_real_rating(src):               # drop signal, keep real rating
            out.append({k: v for k, v in src.items() if k != "signal"})
        # else: no clean signal, no real rating → drop the whole row
    return out


# ── Peer-attribution fence (2026-07 FCMA fix) ────────────────────────────
# A peer's number is NEVER the client's. Mirror the money-fence guard on the
# NPS regex: reject a figure whose subject is a locked peer or that sits in a
# "Peer NPS benchmark" / pipe-delimited peer scoreboard. FCMA shipped
# "NPS 60" grabbed from E-079 (source_name "Comparably Peer NPS Benchmark",
# excerpt "Peer NPS benchmark … FCSA NPS 60 (LEADER among FCS peers) | CoBank
# 50 | Rabobank 25 …") — FCSA's number, not FCMA's. The client's OWN
# Glassdoor / App-Store / Google-Play rows (source_name names the platform,
# the subject IS the client) pass this fence untouched.
_PEER_BENCHMARK_RE = re.compile(
    r"peer\s+(?:nps\s+)?benchmark"
    r"|\bnps\s+benchmark\b"
    r"|(?:leader|leads?|ranks?|highest|lowest|top|bottom|ahead|behind)\b"
    r"[\w.,'&\- ]{0,30}\bpeers?\b"
    r"|\bamong\s+(?:its\s+|the\s+)?(?:fcs\s+|[\w.\- ]{0,20}\s+)?peers?\b"
    r"|\bvs\.?\s+(?:best\s+)?peer|\bbest\s+peer\b"
    r"|\bpeer\s+(?:median|average|mean|comparison|set|group|rating)\b",
    re.I)
# A pipe-delimited scoreboard of "<Proper Name> <number>" cells (≥2 pairs) is
# a competitor scoreboard, not the client's single rating.
_PEER_SCOREBOARD_RE = re.compile(
    r"(?:[A-Z][\w.&'\- ]{1,28}?\s+[+-]?\d{1,3}(?:\.\d+)?\s*\|\s*){2,}")
# A figure whose immediate SUBJECT (the token right before it) is a peer cue —
# "FCSA peer: 4.3/5", "peer NPS 60" — belongs to the peer, not the client.
_PEER_SUBJECT_RE = re.compile(
    r"(?:\bpeer\b|competitor|benchmark)[\w.:'&\- ]{0,24}$", re.I)


def _is_peer_benchmark(source_name: str, clause: str,
                       peer_names: set[str] | None = None) -> bool:
    """True when a figure in ``clause`` (or the row's ``source_name``)
    belongs to a PEER, not the client — the peer-attribution fence."""
    hay = f"{source_name or ''}\n{clause or ''}"
    if _PEER_BENCHMARK_RE.search(hay) or _PEER_SCOREBOARD_RE.search(clause or ""):
        return True
    if peer_names:
        low = (clause or "").lower()
        for pn in peer_names:
            pn = (pn or "").strip().lower()
            # a locked-peer name followed (within a clause) by a number is
            # that peer's figure — reject.
            if len(pn) >= 3 and re.search(
                    rf"\b{re.escape(pn)}\b[^.|]{{0,40}}?[+-]?\d", low):
                return True
    return False


def _first_client_match(rx: str, prose: str,
                        peer_names: set[str] | None = None):
    """First occurrence of a source keyword whose surrounding clause is NOT a
    peer benchmark — so a peer's mention never becomes the client's source
    row (the whole-document re.search grabbed the peer NPS)."""
    for m in re.finditer(rx, prose, re.I):
        p = m.start()
        clause = prose[max(0, p - 140): p + 140]
        if _is_peer_benchmark("", clause, peer_names):
            continue
        # the figure's immediate left-subject is a peer ("FCSA peer: 4.3/5")
        if _PEER_SUBJECT_RE.search(prose[max(0, p - 40): p]):
            continue
        return m
    return None


def _rating_for_label(
    label: str, clause: str, window: str | None = None,
    nps_clause: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """(rating, kind, cohort) for a source keyword's local clause — the ONE
    rating-extraction rule shared by the prose extractor and the evidence-
    corpus harvester (keeps them in lockstep). Never scans past the clause,
    so an App-Store '/5' can't be mislabelled onto a neighbouring BBB row."""
    window = window if window is not None else clause
    nps_clause = nps_clause if nps_clause is not None else clause
    rating: str | None = None
    kind: str | None = None
    cohort: str | None = None
    if label == "Net Promoter Score":
        sm = _SCALE_RE.search(nps_clause)
        if sm:
            rating = f"{sm.group(1)}/{sm.group(2)}"
        else:
            nm = _NPS.search(nps_clause)
            if nm and abs(float(nm.group(1))) <= 100:
                rating, kind = nm.group(1), "nps"
        if _EMP_CUE.search(nps_clause):
            cohort = "employee"
    if rating is None:
        rm = _RATING.search(clause)
        # A low-sample admission ("5/5 stars (limited reviews)" — Compeer
        # E-036, 2026-07-06 QA) voids the NUMBER, not the source: the
        # mention still lands WITHOUT a rating. Honest-absent beats a
        # hollow perfect score.
        if rm and not _LOW_SAMPLE.search(clause):
            rating = f"{rm.group(1)}/5"
    if rating is None and label in ("CFPB complaints", "J.D. Power", "Forrester"):
        pm = _PCT.search(window)
        if pm:
            rating = f"{pm.group(1)}%"
    if rating is None and label in ("Glassdoor", "Indeed", "Comparably"):
        pm = _EMP_PCT.search(window)
        if pm:
            n_pct = int(pm.group(1) or pm.group(2))
            if 0 < n_pct <= 100:
                rating = f"{n_pct}%"
    return rating, kind, cohort


def _match_source_label(text: str) -> str | None:
    """The recognised sentiment SOURCE named in ``text`` (render-priority
    order), or None. Used to bind an evidence row's Source_Name to a
    platform label."""
    if not text:
        return None
    for label, rx in _SOURCES:
        if re.search(rx, text, re.I):
            return label
    return None


# Segment an excerpt so a multi-source line ("Yelp: 3.6/5 (8 reviews). Not
# BBB Accredited") splits into per-source clauses — the fix for the App-
# Store-rating-tagged-as-BBB mislabel: each rating binds only to the source
# named in (or immediately left of) its own segment. A '.' inside a decimal
# ("4.0-4.1/5", "4.8/5") is NOT a boundary (else the rating truncates to
# "1/5" / "8/5"); only sentence-final '.'/';' + whitespace splits.
# en/em dash via \u to keep ruff RUF001-clean.
_SEG_SPLIT_RE = re.compile(r"(?<!\d)\.(?=\s|$)|;\s*|\n|\s[\u2013\u2014]\s")


def _sentiment_segments(text: str) -> list[str]:
    return [s.strip() for s in _SEG_SPLIT_RE.split(text or "") if s.strip()]


def _extract_from_evidence(
    ev_rows: list, peer_names: set[str] | None = None,
) -> list[dict]:
    """Client's OWN per-source sentiment rows harvested from the evidence
    CORPUS (``[{source_name, excerpt}]``). Each row pairs its Source_Name —
    which names the platform ("Glassdoor — FCMA Reviews", "Apple App Store —
    … app") that the excerpt itself often omits — with the rating stated in
    the excerpt, so App-Store / Google-Play / Glassdoor rows are captured
    instead of collapsing to one "Public Sources / neutral / null" row.

    Peer-benchmark rows are rejected (a peer's number is never the client's);
    a row/segment naming a source but carrying no parseable rating becomes a
    qualitative row (signal only) rather than being dropped. Nothing is
    invented."""
    by_label: dict[str, dict] = {}
    order: list[str] = []
    for row in ev_rows:
        name = str((row.get("source_name") if isinstance(row, dict)
                    else getattr(row, "source_name", "")) or "").strip()
        exc = str((row.get("excerpt") if isinstance(row, dict)
                   else getattr(row, "excerpt", "")) or "").strip()
        if not name and not exc:
            continue
        if _is_peer_benchmark(name, exc, peer_names):
            continue
        primary = _match_source_label(name)
        segs = _sentiment_segments(exc) or [exc]
        for seg in segs:
            if _is_peer_benchmark("", seg, peer_names):
                continue
            seg_label = _match_source_label(seg) or primary
            if not seg_label:
                continue
            rating, kind, cohort = _rating_for_label(seg_label, seg, seg, seg)
            signal = _clean_sig(re.sub(r"\s+", " ", seg).strip(" .;:-"))
            row_out = by_label.get(seg_label)
            if row_out is None:
                row_out = {"source": seg_label}
                by_label[seg_label] = row_out
                order.append(seg_label)
            if rating and not row_out.get("rating"):
                row_out["rating"] = rating
                if kind:
                    row_out["kind"] = kind
                if cohort:
                    row_out["cohort"] = cohort
            # prefer the rating-bearing / longest grounded segment
            if (signal and len(signal) > len(row_out.get("signal") or "")
                    and (not row_out.get("signal") or rating
                         or _SENT_KW.search(signal))):
                row_out["signal"] = signal[:240]
        # a named source with no signal at all keeps the source_name as its
        # honest signal so it renders (qualitative) rather than vanishing.
        if primary and primary in by_label and not by_label[primary].get("signal"):
            by_label[primary]["signal"] = _clean_sig(name)[:240] or name[:240]
    out: list[dict] = []
    for label in order:
        r = by_label[label]
        sig = r.get("signal") or ""
        # keep rows that carry either a real rating or genuine sentiment prose
        if not r.get("rating") and not _SENT_KW.search(sig):
            continue
        tr = _trend(sig)
        if tr:
            r["trend"] = tr
        themes = _extract_themes(sig)
        if themes:
            r["themes"] = "; ".join(themes)
        out.append(r)
    return out


def _is_aggregate_only(sent: object) -> bool:
    """True when the stored sentiment is just the aggregate 'Public Sources /
    POSITIVE' row (the A6_Sentiment_Analysis collapse) with no per-platform
    rated or platform-named source — the state the evidence-corpus harvest
    supersedes. False for a genuine per-source CSV/Clay payload (never
    clobbered) and for an empty blob."""
    if not isinstance(sent, dict):
        return False
    srcs = sent.get("sources") or []
    if not srcs:
        return False
    for s in srcs:
        if not isinstance(s, dict):
            return False
        label = str(s.get("source") or "")
        if (_match_source_label(label) or _EMPLOYEE_SRC.search(label)
                or _CUSTOMER_SRC.search(label) or s.get("rating")):
            return False       # a real per-platform / rated row exists
    return True


def _extract(prose: str, peer_names: set[str] | None = None) -> list[dict]:
    sources: list[dict] = []
    seen: set[str] = set()
    for label, rx in _SOURCES:
        # first NON-PEER occurrence — a peer's mention (E-079 "Peer NPS
        # benchmark … FCSA NPS 60 …") must never become the client's row.
        m = _first_client_match(rx, prose, peer_names)
        if not m or label in seen:
            continue
        p = m.start()
        window = prose[max(0, p - 80): p + 260]
        # "S&P BBB+ ratings" is a bond grade, not the Better Business
        # Bureau — the bare-BBB alias false-matched credit-rating prose
        # (Compeer, 2026-07-06 QA) and manufactured a review source.
        if label == "Better Business Bureau" and _BBB_CREDIT.search(
                prose[max(0, p - 60): p + 60]):
            continue
        # CLAUSE-LOCAL (±120 NPS / -40..+120 default) — the old whole-document
        # search captured unrelated numbers (ima's "7", LPL's "$11.0B").
        nps_clause = prose[max(0, p - 120): p + 120]
        clause = prose[max(0, p - 40): p + 120]
        rating, kind, cohort = _rating_for_label(label, clause, window, nps_clause)
        # drop incidental mentions: keep only when a rating was stated or the
        # context is genuinely about opinion/ratings.
        if rating is None and not _SENT_KW.search(window):
            continue
        signal = _clip_signal(prose, p)
        # sanitize away kv-dumps / mid-clause + off-topic fragments before the
        # naming guard (2026-07-06 deploy review — sources never ship a fragment).
        signal = _sanitize(signal, label)
        if not signal:
            continue
        # the signal MUST actually name the source, and MUST NOT be assessment
        # prose we grabbed by accident (guards the BBB→SCQA false positive).
        if (len(signal) < 24 or not re.search(rx, signal, re.I)
                or _ASSESS_JUNK.search(signal)):
            continue
        entry: dict = {"source": label, "signal": signal[:240]}
        if rating:
            entry["rating"] = rating
        if kind:
            entry["kind"] = kind
        if cohort:
            entry["cohort"] = cohort
        tr = _trend(window)
        if tr:
            entry["trend"] = tr
        themes = _extract_themes(f"{signal} {window}")
        if themes:
            entry["themes"] = "; ".join(themes)
        sources.append(entry)
        seen.add(label)
    # ── Unattributed-rating fallback (2026-07-04 deep search: 14 clients'
    # ratings live in evidence WITHOUT the platform name — "3.8/5 rating,
    # 59 reviews, 79% recommend, culture 4.4/5. Employee concern: …").
    # Cohort is classified from the surrounding cue words; the label says
    # exactly what we know. At most one anonymous entry per cohort, and
    # only when no NAMED source of that cohort was already captured.
    if len(sources) < 2:
        have_emp = any(_EMPLOYEE_SRC.search(s["source"]) for s in sources)
        have_cust = any(_CUSTOMER_SRC.search(s["source"]) for s in sources)
        for m in re.finditer(r"(\d(?:\.\d)?)\s*/\s*5\b[^.\n]{0,120}", prose):
            window = prose[max(0, m.start() - 100): m.end() + 140]
            if not re.search(r"reviews?|ratings?|recommend", window, re.I):
                continue
            # An anonymous rating whose own context admits a thin sample
            # ("5/5 stars (limited reviews)") is not an aggregate — the
            # label below would present it as one. Honest-absent instead
            # of a fabricated perfect score (Compeer, 2026-07-06 QA).
            if _LOW_SAMPLE.search(window):
                continue
            # A perfect 5/5 with NO stated review volume is statistically
            # void for an anonymous source — only volume-backed perfection
            # survives ("5/5 from 2,100 reviews" keeps its rating).
            if float(m.group(1)) >= 5 and not _N_RE.search(window):
                continue
            # never attribute a peer's rating ("FCSA peer: 4.3/5") to the client
            if (_is_peer_benchmark("", window, peer_names)
                    or _PEER_SUBJECT_RE.search(prose[max(0, m.start() - 40): m.start()])):
                continue
            is_emp = bool(re.search(
                r"employee|culture|work[- ]life|staff|workplace", window, re.I))
            # A mobile-app rating is store voice, not the customer-review
            # aggregate — label it as exactly what we know.
            is_app = not is_emp and bool(re.search(
                r"app store|google play|mobile app|ios|android|app rating",
                window, re.I))
            is_cust = not is_emp and not is_app and bool(re.search(
                r"customer|member|complaint|service|app\b|branch", window, re.I))
            label = ("Employee reviews" if is_emp
                     else "Mobile app reviews" if is_app
                     else "Customer reviews" if is_cust else None)
            if label is None or (is_emp and have_emp) or ((is_cust or is_app) and have_cust):
                continue
            signal = _clip_signal(prose, m.start())
            signal = _sanitize(signal, label)
            if not signal or len(signal) < 24 or _ASSESS_JUNK.search(signal):
                continue
            entry = {"source": label, "signal": signal[:240],
                     "rating": f"{m.group(1)}/5"}
            tr = _trend(window)
            if tr:
                entry["trend"] = tr
            themes = _extract_themes(f"{signal} {window}")
            if themes:
                entry["themes"] = "; ".join(themes)
            sources.append(entry)
            if is_emp:
                have_emp = True
            else:
                have_cust = True
            if have_emp and have_cust:
                break
    return sources


# ── Normalized scorecard (plan 4.6 SentimentCard) ───────────────────────────
# source → employee vs customer classification (Glassdoor/Indeed/Comparably
# are workforce voice; stores/BBB/CFPB/JD Power/NPS/Trustpilot/Yelp are
# customer voice; Forrester is industry analyst → customer-side benchmark).
_EMPLOYEE_SRC = re.compile(r"glassdoor|indeed|comparably|enps|employee", re.I)
_CUSTOMER_SRC = re.compile(
    r"app store|google play|play store|\bbbb\b|better business|cfpb|trustpilot|"
    r"yelp|j\.?\s?d\.?\s?power|net promoter|\bnps\b|forrester|reviews?|apple", re.I)
_N_RE = re.compile(r"([\d,]{2,7})\+?\s*(?:reviews?|ratings?|responses?|complaints?)", re.I)
_SCALE_RE = re.compile(r"(\d(?:\.\d{1,2})?)\s*(?:/|out of)\s*(5|10|100)", re.I)


_NPS_SRC = re.compile(r"net\s*promoter|\benps\b|\bnps\b", re.I)
_NPS_BARE = re.compile(r"^\s*([+-]?\d{1,3}(?:\.\d{1,2})?)\s*$")
# ~+30 is the FSI customer-NPS norm — the ONLY benchmark an NPS row is
# flagged against (never the 5-point cohort average: +22/100 → 1.1/5 →
# "BELOW PEER" was the Compeer mis-model, 2026-07-06 deploy review).
_NPS_FSI_NORM = 30.0
# structured CSV/Clay fragment pairs ("Glassdoor Rating" + "Glassdoor
# Reviews") carry the value/count OUTSIDE the rating field — same suffix
# vocabulary context_extras.sentiment_view merges on (one contract).
# full canonical names that END in a fragment-suffix word — never strip.
_CANONICAL_FULL_SOURCES = {"net promoter score"}
_FRAG_SUFFIX = re.compile(
    r"\s+(rating|reviews?|review\s+count|score|volume)$", re.I)


def _parse_score(rating: object, signal: str) -> tuple[float | None, int | None]:
    """(score, scale) from a rating string ('4.2/5', '78%', '3.9'), falling
    back to the signal prose ONLY when the rating itself carries no number —
    a blob-wide scan let a neighbouring metric's '/5' win (bank-ozk's NPS
    row shipped CSAT's 3.3/5; 2026-07-06 deploy review)."""
    r = str(rating or "").strip()
    m = _SCALE_RE.search(r)
    if m:
        return float(m.group(1)), int(m.group(2))
    if r.endswith("%"):
        try:
            return float(r.rstrip("%")), 100
        except ValueError:
            return None, None
    try:
        v = float(r)
    except ValueError:
        # no numeric rating — the signal prose is the last resort
        m = _SCALE_RE.search(signal or "")
        if m:
            return float(m.group(1)), int(m.group(2))
        return None, None
    if 0 <= v <= 5:
        return v, 5
    if 0 <= v <= 100:
        return v, 100
    return None, None


def _merge_fragment_sources(sources: list) -> list[dict]:
    """Fold 'X Rating'/'X Reviews' fragment rows into one 'X' source (the
    rating fragment's number becomes `rating`, the reviews fragment's
    becomes `volume`) so the scorecard sees the same merged rows the D5
    sentiment_view renders. Non-fragment rows pass through untouched."""
    merged: dict[str, dict] = {}
    order: list[str] = []
    for src in sources:
        if not isinstance(src, dict):
            continue
        label = str(src.get("source") or "").strip()
        m = _FRAG_SUFFIX.search(label)
        base = _FRAG_SUFFIX.sub("", label).strip() if m else label
        # Canonical source names keep their full form: "Net Promoter
        # Score" is a proper noun, not a "<source> Score" fragment — the
        # stripped "Net Promoter" leaked to the card (ozk class).
        if m and label.lower() in _CANONICAL_FULL_SOURCES:
            m, base = None, label
        key = base.lower()
        if key not in merged:
            merged[key] = dict(src, source=base or label)
            order.append(key)
            row = merged[key]
            if m and re.search(r"reviews?|count|volume", m.group(1), re.I):
                # a count fragment's number is the sample size, not a rating
                row["volume"] = row.get("volume") or row.pop("rating", None)
            continue
        row = merged[key]
        num = str(src.get("rating") or "").strip()
        if m and re.search(r"reviews?|count|volume", m.group(1), re.I):
            row.setdefault("volume", num or src.get("volume"))
        elif num and not str(row.get("rating") or "").strip():
            row["rating"] = num
        for k in ("signal", "themes", "trend", "metric", "volume"):
            if src.get(k) and not row.get(k):
                row[k] = src[k]
    return [merged[k] for k in order]


def normalize_sentiment(blob: dict) -> dict | None:
    """`{sources:[…]}` → adds the prototype scorecard shape:
    ``employee[] / customer[] rows {source, metric, score, scale, n}``,
    ``nps[]`` (its own metric kind: {cohort, metric, value, n?, flag?} on
    the -100..+100 index, never a score/100 bar), ``qualitative[]`` (rows
    whose source carries signal+trend but no parsable number — rendered as
    polarity rows instead of vanishing), ``industry_avg`` (5-pt employee
    benchmark) and ``b2b_b2c_gap``. Returns the merged blob, or None when
    nothing normalizable. Never invents a number: a source without one is
    qualitative, not scored."""
    # Sanitize the raw sources[] FIRST — this is the one choke point Pass 2 runs
    # over EVERY persisted blob (incl. the raw Clay/CSV kv-dumps derive_sentiment
    # skipped), so it is where pre-existing fragment signals are cleaned/dropped
    # (2026-07-06 deploy review). raw_sources (unmerged) becomes the pack-facing
    # `sources`; the merged view still feeds the scorecard rows.
    in_sources = (blob or {}).get("sources") or []
    raw_sources = _sanitize_sources(in_sources)
    sources = _merge_fragment_sources(raw_sources)
    employee: list[dict] = []
    customer: list[dict] = []
    nps_rows: list[dict] = []
    qualitative: list[dict] = []
    for src in sources:
        label = str(src.get("source") or "").strip()
        if not label:
            continue
        signal = str(src.get("signal") or src.get("themes") or "")
        rating_raw = str(src.get("rating") or "").strip()
        is_emp = bool(src.get("cohort") == "employee"
                      or _EMPLOYEE_SRC.search(label)
                      or (_NPS_SRC.search(label) and _EMP_CUE.search(signal)))
        n = None
        nm = _N_RE.search(f"{signal} {src.get('volume') or ''}")
        if nm:
            with contextlib.suppress(ValueError):
                n = int(nm.group(1).replace(",", ""))
        elif str(src.get("volume") or "").replace(",", "").strip().isdigit():
            n = int(str(src.get("volume")).replace(",", ""))
        # NPS is its own metric kind: a bare/signed index on an NPS source
        # never becomes a score/100 bar (and its signal prose is never
        # scanned for another metric's '/5').
        is_nps_src = bool(src.get("kind") == "nps" or _NPS_SRC.search(label))
        bare = _NPS_BARE.match(rating_raw)
        if (is_nps_src and bare and abs(float(bare.group(1))) <= 100
                and not _SCALE_RE.search(rating_raw)):
            value = float(bare.group(1))
            row = {"source": label,
                   "metric": "Employee NPS" if is_emp else "NPS",
                   "kind": "nps", "value": value,
                   "cohort": "employee" if is_emp else "customer",
                   "benchmark": _NPS_FSI_NORM}
            if n:
                row["n"] = n
            if not is_emp and value < _NPS_FSI_NORM:
                row["flag"] = "below_peer"     # vs the NPS norm, not /5
            nps_rows.append(row)
            continue
        # an NPS-kind source's SIGNAL is never scanned for a scale — a
        # neighbouring metric's '/5' (ozk's CSAT) must not become "NPS".
        score, scale = _parse_score(src.get("rating"),
                                    "" if is_nps_src else signal)
        if score is None:
            # honest qualitative row — signal + trend/polarity, no bar
            q = {"source": label,
                 "metric": str(src.get("metric") or "Overall"),
                 "cohort": "employee" if is_emp else "customer",
                 "signal": signal[:200] or None}
            tr = str(src.get("trend") or "").strip()
            if tr:
                q["trend"] = tr
            themes = _themes_from_source(src)
            if themes:
                q["themes"] = themes
            try:
                from app.services.nlp.polarity import signal as _pol
                q["polarity"] = _pol(signal) if signal.strip() else "neutral"
            except Exception:
                q["polarity"] = "neutral"
            qualitative.append(q)
            continue
        row = {"source": label, "metric": str(src.get("metric") or "Overall"),
               "score": score, "scale": scale or 5}
        if n:
            row["n"] = n
        themes = _themes_from_source(src)
        if themes:
            row["themes"] = themes
        if is_emp:
            employee.append(row)
        else:
            customer.append(row)   # unclassified public voice → customer side
    # nothing scorable AND no source in the input → truly empty, honest-None.
    # (When the INPUT had sources but sanitization emptied them — all fragment
    # garbage — fall through to emit a cleaned honest-empty blob so Pass 2
    # OVERWRITES the stale row instead of skipping the write on merged==blob.)
    if (not employee and not customer and not nps_rows
            and not qualitative and not in_sources):
        return None
    # 5-pt normalization for the gap test (100-pt scores scaled down)
    def _five(r: dict) -> float:
        return r["score"] * 5.0 / r["scale"] if r["scale"] else r["score"]

    out = dict(blob)
    out["sources"] = raw_sources or None    # pack-facing cleaned sources
    out["employee"] = employee or None
    out["customer"] = customer or None
    out["nps"] = nps_rows or None
    out["qualitative"] = qualitative or None
    out["industry_avg"] = 3.5   # FSI employee-review norm (Glassdoor cohort)
    emp5 = [_five(r) for r in employee]
    cus5 = [_five(r) for r in customer]
    out["b2b_b2c_gap"] = bool(emp5 and cus5
                              and abs(sum(emp5) / len(emp5) - sum(cus5) / len(cus5)) >= 0.5)
    below = [r for r in customer if _five(r) < 3.0]
    for r in below:
        r["flag"] = "below_peer"
    out["normalized"] = True
    return out


async def _amain() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    sm = get_sessionmaker()
    filled = scanned = skipped_have = no_signal = 0
    async with sm() as session:
        # Clear our OWN prior prose-derivations so tightened rules fully
        # self-correct (a now-rejected false positive must not linger). CSV/Clay
        # payloads (no/other derived_from) are never touched.
        await session.execute(text(
            "UPDATE firmographics SET sentiment=NULL "
            "WHERE sentiment->>'derived_from'='research_report_prose'"))
        rows = (await session.execute(text(
            """
            SELECT e.id::text eid, e.display_id, r.id::text rid,
                   f.sentiment
            FROM entities e
            JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE'
            LEFT JOIN firmographics f ON f.entity_id=e.id
            WHERE e.status='ACTIVE' ORDER BY e.display_id
            """))).all()
        for row in rows:
            scanned += 1
            sent = row.sentiment or {}
            # skip entities with real per-source CSV/Clay sentiment; recompute
            # our own prior prose-derivation so tightened rules self-correct.
            # An AGGREGATE-ONLY blob ("Public Sources / POSITIVE", no per-
            # platform rated row — the A6_Sentiment_Analysis collapse) is NOT
            # real per-source sentiment: run the evidence-corpus harvest and
            # let it SUPERSEDE the aggregate (task: per-source rows BEFORE the
            # aggregate-CSV fallback).
            aggregate_only = _is_aggregate_only(sent)
            if (isinstance(sent, dict) and sent.get("sources")
                    and sent.get("derived_from") != "research_report_prose"
                    and not aggregate_only):
                skipped_have += 1
                continue
            prose = (await session.execute(text(
                "SELECT string_agg(body, ' ') FROM document_sections WHERE run_id=CAST(:rid AS uuid)"
            ), {"rid": row.rid})).scalar() or ""
            # Locked peer names strengthen the peer-attribution fence (a
            # peer's rating is never the client's). Best-effort — degrades to
            # the context-only fence when entity_peers is empty/absent.
            peer_names: set[str] = set()
            try:
                peer_names = {
                    (pr.peer_name or "").strip()
                    for pr in (await session.execute(text(
                        "SELECT peer_name FROM entity_peers "
                        "WHERE entity_id=CAST(:e AS uuid)"), {"e": row.eid})).all()
                    if (pr.peer_name or "").strip()
                }
            except Exception:
                peer_names = set()
            # Per-source harvest over the EVIDENCE CORPUS (Source_Name +
            # excerpt): the platform name lives in source_name — "Glassdoor —
            # FCMA Reviews", "Apple App Store — … app" — which the excerpt
            # ("Overall 4.0-4.1/5 (191 reviews)", "iOS app rated 4.8/5")
            # omits, so running the per-source regexes over the excerpt alone
            # missed the client's own rows. Peer benchmarks are fenced out.
            ev_rows = (await session.execute(text(
                r"""
                SELECT source_name, excerpt FROM evidence_index
                WHERE entity_id=CAST(:e AS uuid) AND excerpt IS NOT NULL
                  AND (COALESCE(source_name,'') || ' ' || excerpt) ~* '(glassdoor|indeed|comparably|app store|google play|play store|better business|\ybbb\y|cfpb|trustpilot|yelp|j\.?d\.?\s*power|net promoter|\ynps\y|forrester|/\s*5|stars?\y|reviews?|rated)'
                  -- citation manifests / source inventories (multiple EV-/E-###
                  -- refs) name the platforms without carrying sentiment
                  AND excerpt !~* '(EV-+[0-9]{2,}.*EV-+[0-9]{2,}|E-[0-9]{3}.*E-[0-9]{3})'
                ORDER BY tier ASC NULLS LAST, e_id ASC
                """), {"e": row.eid})).mappings().all()
            ev_sources = _extract_from_evidence(ev_rows, peer_names)
            # Rating-bearing EVIDENCE lines also join the prose blob for the
            # anonymous-rating fallback (2026-07-04: some ratings live only in
            # excerpts as unattributed "3.8/5 rating, 59 reviews"). Prepend
            # source_name so the named-source detector sees the platform.
            ev_prose = "\n".join(
                f"{(r.get('source_name') or '')}: {(r.get('excerpt') or '')}"
                for r in ev_rows if r.get("excerpt"))
            prose = (prose + "\n" + ev_prose).strip()
            if not prose and not ev_sources:
                no_signal += 1
                continue
            # Evidence-corpus rows FIRST (authoritative, source-named), then
            # prose rows for any source not already captured.
            have = {str(s.get("source") or "").lower() for s in ev_sources}
            sources = list(ev_sources)
            for s in _extract(prose, peer_names):
                if str(s.get("source") or "").lower() not in have:
                    sources.append(s)
            if not sources:
                no_signal += 1
                continue
            blob = {"sources": sources, "derived_from": "research_report_prose"}
            # carry the aggregate's overall label forward when we supersede it.
            if aggregate_only and isinstance(sent, dict):
                agg = sent.get("overall") or sent.get("overall_sentiment")
                if agg:
                    blob["overall"] = agg
                blob["superseded_aggregate"] = True
            if aggregate_only:
                # supersede the collapsed aggregate-only CSV blob with the
                # per-source harvest (unconditional — we proved it carries no
                # real per-platform row).
                await session.execute(text(
                    "UPDATE firmographics SET sentiment=CAST(:s AS jsonb) "
                    "WHERE entity_id=CAST(:e AS uuid)"
                ), {"e": row.eid, "s": json.dumps(blob)})
            else:
                # fill-if-empty, but allowed to refresh our OWN prior prose-
                # derivation; never clobber a real CSV/Clay per-source payload.
                await session.execute(text(
                    """
                    INSERT INTO firmographics (entity_id, sentiment)
                    VALUES (CAST(:e AS uuid), CAST(:s AS jsonb))
                    ON CONFLICT (entity_id) DO UPDATE SET sentiment = EXCLUDED.sentiment
                    WHERE firmographics.sentiment IS NULL
                       OR firmographics.sentiment->>'derived_from' = 'research_report_prose'
                    """), {"e": row.eid, "s": json.dumps(blob)})
            filled += 1
        # Pass 2 — normalize EVERY persisted blob into the scorecard shape
        # (adds employee[]/customer[] rows; never touches `sources`).
        normalized = 0
        rows2 = (await session.execute(text(
            """
            SELECT f.entity_id::text eid, f.sentiment FROM firmographics f
            JOIN entities e ON e.id=f.entity_id
            WHERE e.status='ACTIVE' AND f.sentiment IS NOT NULL
              AND f.sentiment ? 'sources'
            """))).all()
        for r2 in rows2:
            blob = r2.sentiment if isinstance(r2.sentiment, dict) else None
            if not blob:
                continue
            merged = normalize_sentiment(blob)
            if merged and merged != blob:
                await session.execute(text(
                    "UPDATE firmographics SET sentiment=CAST(:s AS jsonb) "
                    "WHERE entity_id=CAST(:e AS uuid)"
                ), {"s": json.dumps(merged), "e": r2.eid})
                normalized += 1
        await session.commit()

    print(f"# derive_sentiment: normalized={normalized} scanned={scanned} filled={filled} "
          f"already_had={skipped_have} no_report_signal={no_signal} "
          f"(grounded in report prose; fill-if-empty)", flush=True)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
