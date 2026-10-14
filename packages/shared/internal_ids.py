"""What may not appear in a sentence a client reads.

ONE PATTERN, TWO IMAGES. The connector refuses it at submit (CG-49) and the
api withholds it at serve (MEM-0137). Those are different jobs on the same
rule, and a rule held in two places drifts — MEM-0193's whole defect class,
and this build has paid for it more than once.

WHY BOTH ENDS ARE NEEDED, since either alone looks sufficient:

CG-49 refuses a MEM id inside a client-visible `empty_state.reason` at
submit. It protects everything submitted after it existed. It does nothing
for the three clients promoted before it, whose bodies carry the ids today.

MEM-0137's serve-side fix protects those. It cannot replace CG-49, because
the right repair for a bad sentence is a better sentence from the producer,
not a hole punched in a live page.

WHAT THIS IS NOT FOR. Ordinary English is not machinery: "no regulatory gate
applies", "the connector between the two systems", "staged for the next
cycle" are sentences a client may legitimately read, and a rule that refuses
them teaches producers to fight the gate rather than read it. So this matches
IDENTIFIERS and CALL SYNTAX — `MEM-0081`, `SG-V4`, `get_evidence(` — never
the words gate, connector or staged on their own.
"""
from __future__ import annotations

import re

#: An id or call that names this system's own machinery.
#:
#: Measured in production 2026-08-24 across three promoted clients: ten
#: customer-visible fields matched, including
#: `platform.starters.empty_state.sources_searched` carrying
#: `get_page_contract('platform')`, `r_layer` and the literal
#: `CUSTOMER_WITHHELD`, and `heatmap.safeguard_gates.empty_state
#: .sources_searched` carrying SG-01 and SG-V4.
INTERNAL_ID = re.compile(
    r"\b(?:MEM|REF)-\d{3,4}\b"                   # findings-memory ids
    r"|\b(?:CG|AG|ET)-\d{2,3}\b"                 # gate ids (SG below)
    r"|\bSG-[A-Z0-9]{1,3}\d?\b"                  # SG-01, SG-V4, SG-AC1
    r"|\bCUSTOMER_WITHHELD\b"                    # the redaction constant
    r"|\bno_staged_submission\b"
    r"|\b(?:get|list|submit|promote|register|record|resolve|report)_[a-z_]+\("
    , re.I)


def names_machinery(text) -> str | None:
    """The first internal identifier in `text`, or None.

    Returns the MATCH rather than a boolean so a caller can say what it
    found: a verdict that names the string is one a producer can act on, and
    a verdict that says "something in here" is one they have to hunt for.
    """
    if not isinstance(text, str):
        return None
    m = INTERNAL_ID.search(text)
    return m.group(0) if m else None


def scan(node, path: str = "") -> list:
    """[(path, matched_string)] over every string in a nested structure.

    A key filter cannot see this. `reason` is an allowed key and its VALUE is
    where the id sits, which is why the serve allowlist — correct as far as it
    goes — let ten fields through.
    """
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            out += scan(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += scan(v, f"{path}[{i}]")
    else:
        hit = names_machinery(node)
        if hit:
            out.append((path, hit))
    return out


# ── Pipeline vocabulary (moved from apps/api/dma_api/redaction.py) ──────
# Our PIPELINE's vocabulary in a sentence a client reads — a third net beside
# the vendor and seller nets, and like them a backstop: producers are fixing
# the prose (SWBC, 2026-10-02, measured on the withdrawn run), and this is
# what still stands if one does not.
#
#   NOT_RUN            a gate status, inside PROSE. A safeguard gate's
#                      `status: "NOT_RUN"` is designed to render (invariant
#                      12) — so a value that IS the bare token is never
#                      matched, and heatmap.safeguard_gates is exempt from
#                      this one term: its reason text explains a NOT_RUN by
#                      design.
#   connector credit   the enrichment budget.
#   Clay · Explorium · Exa · Tavily · Firecrawl
#                      the enrichment and search tools. CASE-SENSITIVE and
#                      bounded, so "clay", "exactly", "example" never match;
#                      "Clay" followed by a capitalised word ("Clay Thompson,
#                      CFO") is a person, not the tool, and is left alone.
#   RRF · k=60 · engine v2 · hot band
#                      retrieval-fusion and ranking internals.
#
# Same convention as the other nets: the FIELD holding the sentence goes
# (a list element is blanked), never half a sentence, and every path is
# recorded in the receipt.
PIPELINE_TERMS = (
    ("NOT_RUN", re.compile(r"\bNOT_RUN\b")),
    ("connector credit", re.compile(r"\bconnector[- ]credits?\b", re.I)),
    ("Clay", re.compile(r"\bClay(?:\.com|'s)?\b(?!\s+[A-Z][a-z])")),
    ("Explorium", re.compile(r"\bExplorium\b", re.I)),
    ("Exa", re.compile(r"\bExa(?:\.ai)?\b")),
    ("Tavily", re.compile(r"\bTavily\b", re.I)),
    ("Firecrawl", re.compile(r"\bFire[- ]?crawl\b", re.I)),
    ("RRF", re.compile(r"\bRRF\b")),
    ("k=60", re.compile(r"\bk\s*=\s*60\b")),
    ("engine v2", re.compile(r"\bengine[- ]v2\b", re.I)),
    ("hot band", re.compile(r"\bhot[- ]bands?\b", re.I)),
)
# A value that is nothing but an enum token is a STATUS, not prose.
BARE_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]*$")
# Keys that hold a person's or an organisation's NAME: a client whose CFO is
# called Clay is not leaking a tool.
NAME_KEYS = frozenset({"name", "full_name", "person", "person_name",
                                "display_name", "e_id", "gate_id", "gate"})



def names_pipeline_term(text, exempt=()) -> str | None:
    """The first pipeline term `text` names, or None. A value that is only an
    enum token (`NOT_RUN` as a status) is a status, not prose."""
    if not isinstance(text, str) or BARE_TOKEN.match(text.strip()):
        return None
    for term, rx in PIPELINE_TERMS:
        if term not in exempt and rx.search(text):
            return term
    return None


# ── What a customer is served at all (moved from redaction.py) ──────────
# (page, section) withheld entirely from the customer audience.
CUSTOMER_WITHHELD = frozenset((
    ("overview", "ceilings"),            # O1b — TRD §11 rung table
    # O9 `overview.sentiment` LEFT this set on 2026-10-04 by OWNER DECISION 1
    # (SWBC gold audit, D-34): the customer receives a REDUCED card — bars
    # and themes, without cell codes, internal sources, cap vocabulary or
    # r_layer — built by `_project_sentiment` below. This supersedes TRD
    # §11's withholding for that one section; thought_leadership stays.
    ("overview", "thought_leadership"),   # O12 — TRD §11 rung table
    # O10. The evidence CENSUS, not the evidence: tier histogram, item and
    # fact counts, the self-sourced share and the gate line. It is how well
    # WE evidenced the assessment, which is our method showing through, and
    # it belongs beside the ceilings it explains rather than in front of the
    # client. It sat outside this set until 2026-08-18 and was reaching the
    # customer body in full; nothing rendered it only because the web
    # adapter happens to drop those keys (live-adapter.jsx adaptCoverage),
    # so a wire leak was standing behind a UI accident. Both promoted
    # clients were affected, not one.
    ("overview", "evidence_coverage"),    # O10 — the census, not the scores
    ("heatmap", "alerts"),                # D7 Health, operational
    ("heatmap", "evidence_age"),          # D7 Health, operational
    ("heatmap", "cohort_patterns"),       # D7 Health + cross-entity
    # P-starters: conversation openers WRITTEN FOR THE SELLER ("ask them
    # which system…", "follow-up question"). MEM-0081 / T-2: key-stripping
    # it left a customer card list whose every remaining field was a line
    # of our talk track, so it is withheld whole — a section that is our
    # preparation for the room has no redacted form.
    ("platform", "starters"),
))

# Whole pages withheld from the customer audience: a locked state, not a
# partial page. Requested with audience=customer -> 403 audience_forbidden.
CUSTOMER_WITHHELD_PAGES = frozenset(("context",))

# ── The surface-contract allowlist ─────────────────────────────────────
#
# Sections that are OUR RECORD OF OUR OWN METHOD rather than the client's
# assessment, and therefore reach no audience at all. Owner instruction,
# 2026-08-19, third round on the same material: "internal artifacts
# (reasoning traces, capability ceiling, evidence coverage, tiers, counts,
# uncertainty) are dropped at the payload boundary and render nowhere."
#
# Withholding them from the CUSTOMER audience was the previous rule, and it
# was measured insufficient twice: the audience is a toggle in the browser,
# so anybody who moved it met the capability-ceiling table, the evidence
# census and a reasoning trace on the same screen as the client's own
# scores. "Nowhere" is a different rule from "not by default", and it is
# the one that was asked for.
#
# The sections are not deleted from the database or from the producer's
# contract — they are still promoted, still validated, still auditable
# through the connector. They are removed at the point where bytes leave
# for a browser, which is the only boundary that decides what renders.
NEVER_SERVED = frozenset((
    ("overview", "ceilings"),            # O1b — the capability ceiling and
                                         #       uncertainty table
    ("overview", "evidence_coverage"),   # O10 — the census: tiers, counts,
                                         #       the gate line, the share
))



# ── Keys no customer is served, at any depth (CG-52's skip list) ──────────
#
# The serve layer drops these for the customer audience wherever they sit:
# the probe / method / cap classes of packages/shared/serve_classes.json
# (pinned equal by packages/shared/tests/test_customer_scope.py), the
# reasoning trace, the storyline volleys and the enrichment stamps. Prose
# under one of them never reaches a customer, so the submit gate does not
# ask a producer to rewrite it.
CUSTOMER_EXCLUDED_KEYS = frozenset({
    # serve_classes.json · probe_keys
    "sources_searched", "queries_run", "searched_on",
    # serve_classes.json · method_keys
    "tier", "ers", "recency_band", "discovered_by", "provenance", "link_basis",
    # serve_classes.json · cap_keys
    "cap_level", "ceiling", "uncertainty_band", "urf_modifiers",
    # redaction.NEVER_SERVED_KEYS / CUSTOMER_STRIP_KEYS
    "r_layer", "storyline_challenge", "enrichment_basis", "enriched_at",
    # bookkeeping, not prose
    "internal_only",
})


def _path_pattern(path: str) -> str:
    """`cells[12].items[3].tier` -> `cells[*].items[*].tier`."""
    return re.sub(r"\[\d+\]", "[*]", path)


#: A registered source's IDENTITY — the evidence store's name for the row,
#: not a sentence a producer wrote. CG-52 does not ask a producer to rewrite
#: it (the store owns it); the serve layer's net still decides what a
#: customer is shown of it.
SOURCE_IDENTITY_KEYS = frozenset({"source_name", "source_title", "publisher",
                                  "source_domain"})

#: A VERBATIM span of an artefact or a person — the evidence store or the
#: source holds it as written and nobody may rewrite it. The set is
#: packages/shared/abbreviations.EXCERPT_FIELDS (excerpts, quotes, urls,
#: names, headlines, source filenames…), read from the module that owns it
#: rather than restated. Measured on Golden 1 (2026-10-07, nine rows): a
#: registered technographic reading whose own text says "Clay + Vibe scan" —
#: asking a producer to rewrite it would ask them to falsify a quote. The
#: serve layer still decides what a customer sees of it.
_VERBATIM = None


def verbatim_keys() -> frozenset:
    """abbreviations.EXCERPT_FIELDS, loaded from beside this file (both
    images stage the two modules together; the engine's packaged copy never
    calls this)."""
    global _VERBATIM
    if _VERBATIM is None:
        import importlib.util
        from pathlib import Path
        path = Path(__file__).with_name("abbreviations.py")
        spec = importlib.util.spec_from_file_location("_dma_abbreviations", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _VERBATIM = frozenset(mod.EXCERPT_FIELDS)
    return _VERBATIM


def customer_prose_hits(page: str, section: str, body, internal_only=(),
                        keys=None) -> list:
    """[(path, term)] for every string a CUSTOMER would be served in this
    section that names a pipeline term — the prose the serve layer would
    otherwise delete for that audience.

    `keys` limits the walk to those top-level keys (None = the whole body).
    Skips sections and pages withheld from the customer, the excluded key
    classes above, NAME_KEYS, and every path the producer marked
    internal_only (exact or `[*]` form)."""
    if (page, section) in CUSTOMER_WITHHELD or (page, section) in NEVER_SERVED \
            or page in CUSTOMER_WITHHELD_PAGES or not isinstance(body, dict):
        return []
    # A `[*]` marking covers every row; a concrete-index marking covers that
    # row only. Widening `cells[0].synthesis` to every cell would let one
    # marked row hide the prose of all the others from this gate.
    exact, wild = set(), set()
    for m in internal_only or ():
        p = m.get("path") if isinstance(m, dict) else m
        if isinstance(p, str) and p:
            p = p.strip()
            (wild if "[*]" in p else exact).add(p)
    exempt = ("NOT_RUN",) if (page, section) == ("heatmap", "safeguard_gates") else ()
    verbatim = verbatim_keys()
    out = []

    def walk(node, path):
        if path and (path in exact or _path_pattern(path) in wild):
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if k in CUSTOMER_EXCLUDED_KEYS:
                    continue
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str):
            leaf = path.rsplit(".", 1)[-1].split("[", 1)[0]
            if leaf in NAME_KEYS or leaf in SOURCE_IDENTITY_KEYS or leaf in verbatim:
                return
            hit = names_pipeline_term(node, exempt)
            if hit:
                out.append((path, hit))

    for k, v in body.items():
        if keys is not None and k not in keys:
            continue
        if k in CUSTOMER_EXCLUDED_KEYS:
            continue
        walk(v, k)
    return out


# ── Rewriting a research note into prose a customer may read ─────────────
#
# The research engine projects each DECLARED absence into the heatmap cell
# drawer (engine.surface_export.absence_rows) from the lane's own notes, and
# those notes are a search log: "three Exa queries returned…", "Tavily
# returned HTTP 432 and was unusable", "Counter-reading: NOT_RUN: web_search
# budget exhausted". Served to a customer, the pipeline net above deletes the
# whole synthesis (63 of 619 drawers on First Tech, 2026-10-07); submitted,
# CG-52 refuses it. This keeps what the search ESTABLISHED and drops which
# tool ran it and how much budget it had — the client's terms, not ours.
#
# The guarantee is checked, not assumed: `neutralise_pipeline_terms(t)` never
# returns a string `names_pipeline_term` would flag (pinned by
# packages/shared/tests/test_customer_scope.py over the measured corpus).

#: Clauses about OUR search capacity rather than about the client: dropped.
#: The CLAUSE goes, not the sentence: bounded by commas as well as full stops,
#: so "three queries returned only the 2024 report, and Tavily returned HTTP
#: 432 and was unusable" keeps the finding and loses the outage.
_CAPACITY_CLAUSE = re.compile(
    r"(?:,\s*(?:and|but)\s+|,\s*)?[^.;,]*\b(?:budget|plan limit|HTTP \d{3}"
    r"|rate[- ]limit|credits? (?:ran out|exhausted)|unusable)\b[^.;,]*", re.I)

_TOOLS = r"(?:Exa|Tavily|Firecrawl|Explorium)(?:\.ai)?"
_NEUTRAL = (
    (re.compile(r"\bNOT_RUN\b:?\s*"), "not run "),
    (re.compile(rf"\b{_TOOLS} (?:connector )?(?:queries|searches|volleys)\b", re.I),
     "web searches"),
    (re.compile(rf"\b{_TOOLS} (?:connector )?(?:query|search|volley)\b", re.I),
     "a web search"),
    (re.compile(r"\bweb_search\b|\bWebSearch\b"), "web search"),
    (re.compile(rf"\s*\((?:{_TOOLS}|Clay)\)", re.I), ""),
    (re.compile(rf"\bvia (?:{_TOOLS}|Clay)\b", re.I), "via web search"),
    (re.compile(rf"\b(?:plus|and) {_TOOLS}\b", re.I), "and web search"),
    (re.compile(rf"\b{_TOOLS}\b(?=\s*['\"“])", re.I), "a web search for"),
    (re.compile(rf"\bonly {_TOOLS} volleys ran\b", re.I), "only a partial search ran"),
    (re.compile(r"\bClay(?:\.com|'s)? (?:Tech Stack |technographic )?scan\b"),
     "technographic scan"),
    (re.compile(rf"\b{_TOOLS}\b", re.I), "web search"),
    (re.compile(r"\bClay(?:\.com|'s)?\b(?!\s+[A-Z][a-z])"), "a data provider"),
    (re.compile(r"\bconnector[- ]credits?\b", re.I), "search capacity"),
    (re.compile(r"\bRRF\b|\bk\s*=\s*60\b|\bengine[- ]v2\b", re.I), "the ranking"),
    (re.compile(r"\bhot[- ]bands?\b", re.I), "the top band"),
    (re.compile(r"\b(web search)(?: and web search)+\b"), r"\1"),
)


def neutralise_pipeline_terms(text):
    """`text` with every pipeline term rewritten into what the search
    established; a non-string is returned unchanged."""
    if not isinstance(text, str):
        return text
    if names_pipeline_term(text) is None and not _CAPACITY_CLAUSE.search(text):
        return text                        # nothing of ours in it: untouched
    t = _CAPACITY_CLAUSE.sub(" ", text)
    for rx, rep in _NEUTRAL:
        t = rx.sub(rep, t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"(^|[.;:]\s*)[;,]\s*", r"\1", t)          # a clause left headless
    t = re.sub(r"\s+([.,;:])", r"\1", t)
    t = re.sub(r";\s*\.", ".", t)
    t = re.sub(r"\.(?:\s*\.)+", ".", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    # A sentence whose opening clause was the outage starts lower-case now.
    return re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)
