"""The grounded answer path — lookup and retrieval, never composition.

An AE asks the intelligence panel a question. The serving path runs no model
(invariant 1), and the reason it does not is that no prose may be invented
while a client is looking at the page. Two operations survive that rule
intact, because neither writes a sentence:

  LOOKUP     the producer answered this question during synthesis, when a
             model was allowed to run. The answer promoted as prose with its
             citations; serving it is a SELECT.
  RETRIEVAL  nobody anticipated this question, so the run's own passages are
             ranked and returned VERBATIM under an honest frame. An index
             scan is not a model call.

What this module will not do, anywhere, at any tier: shorten a passage, join
two passages into a sentence, paraphrase, or fill a gap. An answer is either
prose a producer wrote, or a set of quotations with their sources named, or a
stated absence. Where several promoted fields bear on one question they are
returned as ORDERED PARTS, each keeping its own path and its own citations —
the panel renders them as separate blocks, so nothing that was two fields can
be read as one authored claim.

## Three tiers, in order, and why the order is that way

1. `serving_answers` — the producer's own answers (migration 0026). Best
   prose, written with the whole package in view. Absent until the connector
   writes it; see the module note at the bottom for what that needs.
2. SELECTION over the promoted sections — a fixed registry mapping each
   anticipated question to the promoted fields that already answer it. No
   model, no new prose, and it works on every run that ever promoted, which
   is why it ships first.
3. RETRIEVAL — rank the run's passages against the question. Served from
   `serving_passages` when the connector has built it; derived from the
   promoted sections in this process when it has not. Same corpus either way.

Anything that clears none of the three is an absence, said plainly, with the
next step named. A question the run cannot answer is not a defect to be
papered over — it is the one honest thing the panel can say.
"""
from __future__ import annotations

import re

from .pages import ApiError, build_page
from .redaction import CUSTOMER_WITHHELD

# ── What counts as a passage ─────────────────────────────────────────────
#
# One rule, stated here and mirrored in the panel (apps/web/proto/drawers.jsx,
# `ipPassages`), because the two must select the same text or a reader gets a
# different answer depending on which tier served it.
#
# A passage is a string in a promoted section that reads as PROSE: long
# enough and with enough words to be a sentence rather than a token. The
# thresholds are deliberately low — a focus area's verbatim quote is short
# ("awash in data but no strategy" is six words) and it is exactly the kind
# of sentence an AE wants back.
PROSE_MIN_CHARS = 40
PROSE_MIN_WORDS = 6

# Key names that never hold prose whatever their length: identifiers, dates,
# links, versions, enum-ish tokens. Matched on the final path segment.
_SKIP_KEY = re.compile(
    r"(^|_)(id|ids|at|on|url|uri|slug|hex|colour|color|version|path|date|"
    r"kind|type|code|status|band|tier|class|label)$")

# Subtrees that are the producer's own working record rather than anything a
# reader asked for. `r_layer` is the recorded reasoning behind a ranked
# claim, `sources_searched`/`queries_run` are the search trail behind an
# absence. Both are load-bearing for audit and both would swamp a ranked
# answer with the producer talking about its own method.
_SKIP_SEGMENTS = frozenset((
    "r_layer", "probes_run", "sources_searched", "queries_run",
    "empty_state", "internal_only", "redacted_paths",
))

# Where an object states its own citations. First one present wins; a list
# that is not a list of citation-shaped strings is ignored rather than
# guessed at (`evidence` is a list of ids on an insight card and a list of
# OBJECTS at the top of the adapted entity).
_CITE_KEYS = ("e_ids", "supporting_e_ids", "evidence_ids", "cited_e_ids",
              "evidence")

# Where an object states what it is about, so a passage can carry the anchor
# the page would drill to.
_ANCHOR_KEYS = (("subcap_id", "subcap"), ("cell_id", "subcap"),
                ("ic_id", "insight"), ("rec_id", "recommendation"),
                ("fa_id", "focus_area"), ("ts_id", "techstack"),
                ("e_id", "evidence"), ("wn_id", "why_now"))

_E_ID = re.compile(r"^E-[A-Za-z0-9][A-Za-z0-9\-]*$")


def _is_prose(value) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if len(text) < PROSE_MIN_CHARS:
        return False
    return len(text.split()) >= PROSE_MIN_WORDS


def _citations(node: dict, inherited: tuple) -> tuple:
    """This object's own citation list, or the one it inherits, plus WHICH of
    the two it is.

    Inheritance is what makes a section-level `e_ids` reach a paragraph that
    carries none of its own — the common case: `overview.scores` cites two
    ids for the whole section and its `framing` paragraph states none. It is
    never a guess; the ids are the ones promote wrote for the row this text
    came out of.

    But the two are not the same claim, and conflating them is how one
    paragraph came to display fifty-nine chips: `heatmap.evidence_age` cites
    every dated item in the run at SECTION level, and each of its rows would
    otherwise appear to cite all of them. So the scope travels with the ids
    and the reader is told which they are looking at."""
    for key in _CITE_KEYS:
        found = node.get(key)
        if isinstance(found, list) and found and all(
                isinstance(x, str) and _E_ID.match(x) for x in found):
            return list(found), "item"
    # An evidence item is its own citation: its excerpt is the most quotable
    # text in the run, and "the run cites nothing for this" would be false —
    # it cites the item the sentence came out of. The test is exact, so an
    # object whose id merely happens to be called `id` does not self-cite.
    for key in ("e_id", "id"):
        own = node.get(key)
        if isinstance(own, str) and _E_ID.match(own):
            return [own], "item"
    return inherited


def _anchor(node: dict, inherited):
    for key, kind in _ANCHOR_KEYS:
        val = node.get(key)
        if isinstance(val, str) and val:
            return kind, val
    return inherited


def walk_passages(page: str, section: str, data, section_e_ids=None) -> list:
    """Every prose string in one promoted section, with its path, its
    citations and what it is about. Order is the payload's own order, so two
    passages that tie on rank tie in a stable way."""
    out: list = []
    if not isinstance(data, (dict, list)):
        return out

    def walk(node, path, cites, anchor):
        if isinstance(node, dict):
            cites = _citations(node, cites)
            anchor = _anchor(node, anchor)
            for key, value in node.items():
                if key in _SKIP_SEGMENTS:
                    continue
                walk(value, f"{path}.{key}" if path else key, cites, anchor)
            return
        if isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]", cites, anchor)
            return
        if not _is_prose(node):
            return
        leaf = path.rsplit(".", 1)[-1].split("[")[0]
        if _SKIP_KEY.search(leaf):
            return
        kind, anchor_id = anchor if anchor else (None, None)
        ids, scope = cites
        out.append({
            "page": page, "section": section, "json_path": path,
            "text": node.strip(), "e_ids": list(ids or []),
            "cite_scope": scope if ids else None,
            "anchor_kind": kind, "anchor_id": anchor_id,
        })

    walk(data, "", (list(section_e_ids or []), "section"), None)
    return out


def passages_from_page(body: dict) -> list:
    """The passages of one already-built (and already-redacted) page.

    Built from the page response rather than from the serving rows, so the
    audience redaction that ran there governs here too — an internal-only
    path deleted for the customer audience is simply not in this corpus, and
    a withheld section contributes nothing. Default-deny survives the feature
    instead of being re-implemented beside it."""
    out = []
    page = body.get("page")
    for section, sec in (body.get("sections") or {}).items():
        data = sec.get("data")
        if not isinstance(data, (dict, list)):
            continue
        out += walk_passages(page, section, data, sec.get("e_ids"))
    return out


# ── The anticipated questions ────────────────────────────────────────────
#
# The producer knows what an AE asks, because the panel enumerates it. This
# registry is the canonical list; `apps/web/proto/drawers.jsx` carries the
# same questions for the surfaces it can resolve without a round trip, and
# `test_answers.py` asserts the two have not drifted.
#
# Each source names a promoted field by (page, section, path). `[*]` walks a
# list. A question resolves to the FIRST sources that yield prose, in the
# order written — so the order is an editorial judgement about which promoted
# field answers best, and it is the only judgement this module makes.
QUESTIONS = (
    {"q_id": "Q-ENT-01", "surface": "entity", "rank": 1,
     "question": "What is the 30-second version of this assessment?",
     "sources": (("overview", "exec_summary", "situation"),
                 ("overview", "exec_summary", "complication"),
                 ("overview", "exec_summary", "answer"))},
    {"q_id": "Q-ENT-02", "surface": "entity", "rank": 2,
     "question": "What does the run say the overall posture is, and on what basis?",
     "sources": (("overview", "scores", "framing"),
                 ("overview", "scores", "posture_basis"),
                 ("overview", "scores", "narrative_thread"))},
    {"q_id": "Q-ENT-03", "surface": "entity", "rank": 3,
     "question": "What does this cost if nothing changes?",
     "sources": (("overview", "exec_summary", "cost_of_delay"),
                 ("platform", "recommendations",
                  "recommendations[*].cost_of_inaction"))},
    {"q_id": "Q-ENT-04", "surface": "entity", "rank": 4,
     "question": "What are the top findings this run stands behind?",
     "sources": (("overview", "findings", "findings[*].body"),
                 ("overview", "findings", "findings[*].strategic_alignment"))},
    {"q_id": "Q-ENT-05", "surface": "entity", "rank": 5,
     "question": "Where is the largest opportunity, and why there?",
     "sources": (("overview", "opportunity", "tiles[*].rank_rationale"),
                 ("overview", "opportunity", "tiles[*].their_stack_context"),
                 ("insights", "insights", "cards[*].so_what_text"))},

    {"q_id": "Q-WN-01", "surface": "why_now", "rank": 1,
     "question": "What changed recently, and what closes the window?",
     "sources": (("overview", "why_now", "synthesis"),
                 ("overview", "why_now", "signals[*].trigger"))},
    {"q_id": "Q-WN-02", "surface": "why_now", "rank": 2,
     "question": "Why does the sequence have to start now?",
     "sources": (("overview", "why_now", "signals[*].why_this_sequence"),
                 ("overview", "why_now", "signals[*].consequence_of_waiting"))},
    {"q_id": "Q-WN-03", "surface": "why_now", "rank": 3,
     "question": "What happens to this account without intervention?",
     "sources": (("overview", "exec_summary", "cost_of_delay"),
                 ("platform", "roadmap", "sequencing_basis"))},

    {"q_id": "Q-PS-01", "surface": "platform_story", "rank": 1,
     "question": "What is the case for this platform?",
     "sources": (("platform", "platform_story", "platforms[*].story_md"),)},
    {"q_id": "Q-PS-02", "surface": "platform_story", "rank": 2,
     "question": "What gaps does it close, and against which peers?",
     "sources": (("platform", "platform_story",
                  "platforms[*].gaps[*].peer_note"),
                 ("platform", "recommendations",
                  "recommendations[*].root_cause"))},
    {"q_id": "Q-PS-03", "surface": "platform_story", "rank": 3,
     "question": "What has to be true before this lands?",
     "sources": (("platform", "recommendations",
                  "recommendations[*].prerequisites[*].condition"),
                 ("platform", "recommendations",
                  "recommendations[*].sequencing_reason"))},

    {"q_id": "Q-FA-01", "surface": "focus_area", "rank": 1,
     "question": "Why is this a focus area?",
     "sources": (("heatmap", "focus_areas", "focus_areas[*].verbatim_quote"),
                 ("heatmap", "focus_areas", "focus_areas[*].currency_note"))},
    {"q_id": "Q-FA-02", "surface": "focus_area", "rank": 2,
     "question": "Which capabilities sit under it, and what is holding them down?",
     "sources": (("overview", "ceilings", "rows[*].limiting_absence"),
                 ("overview", "ceilings", "rows[*].rationale"))},

    {"q_id": "Q-SC-01", "surface": "subcap_narrative", "rank": 1,
     "question": "What does the run state about this cell?",
     "sources": (("heatmap", "cell_evidence", "cells[*].synthesis"),)},
    {"q_id": "Q-SC-02", "surface": "subcap_narrative", "rank": 2,
     "question": "What pulled this score down?",
     "sources": (("overview", "ceilings", "rows[*].limiting_absence"),
                 ("heatmap", "alerts", "alerts[*].justification"))},
)


def _pluck(data, path: str) -> list:
    """Every value at a dotted path, following `[*]` across lists. Returns a
    list because a wildcard path has many answers and a plain one has at most
    one; the caller never has to know which."""
    nodes = [data]
    for seg in path.split("."):
        wildcard = seg.endswith("[*]")
        key = seg[:-3] if wildcard else seg
        nxt = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            child = node.get(key)
            if wildcard:
                if isinstance(child, list):
                    nxt += [c for c in child if c is not None]
            elif child is not None:
                nxt.append(child)
        nodes = nxt
        if not nodes:
            return []
    return nodes


def _parts_for(sources, pages: dict, limit: int = 3) -> list:
    """The promoted fields that answer one question, as ordered parts.

    Never joined: each part keeps the page, section and path it came from and
    its own citations, and the panel renders them as separate blocks. Two
    promoted paragraphs shown one after another are two quotations; the same
    two concatenated are a new sentence nobody wrote."""
    parts: list = []
    seen = set()
    for page, section, path in sources:
        body = pages.get(page)
        if not body:
            continue
        sec = (body.get("sections") or {}).get(section) or {}
        data = sec.get("data")
        if not isinstance(data, dict):
            continue
        section_e_ids = sec.get("e_ids") or []
        for value in _pluck(data, path):
            if not _is_prose(value):
                continue
            text = value.strip()
            if text in seen:
                continue
            seen.add(text)
            # The citations of the ROW this text came from, not of the page:
            # walk_passages already resolves inheritance, so re-use it rather
            # than keep a second rule for the same question.
            cites, scope = list(section_e_ids), "section"
            for p in walk_passages(page, section, data, section_e_ids):
                if p["text"] == text:
                    cites, scope = p["e_ids"], p["cite_scope"]
                    break
            parts.append({"text": text, "page": page, "section": section,
                          "path": path, "e_ids": list(cites),
                          "cite_scope": scope})
            if len(parts) >= limit:
                return parts
    return parts


# The pages an answer can be selected from. Fetched once per request and
# reused across every question, because a page read is the expensive part and
# fifteen questions share six pages.
_ANSWER_PAGES = ("overview", "heatmap", "insights", "platform")


def _load_pages(cur, display_id, audience, run, role, allow_history, names):
    """Build each page, tolerating the ones this audience or role may not
    see. A 403 on `context` is default-deny working, not a failure — the
    answer set is simply built from the pages that ARE served, which is the
    only correct behaviour: an answer assembled from a page the reader may
    not open would leak it."""
    out = {}
    for name in names:
        try:
            out[name] = build_page(cur, name, display_id, audience=audience,
                                   run=run, role=role,
                                   allow_history=allow_history)
        except ApiError:
            continue
    return out


def _run_meta_of(pages: dict):
    for body in pages.values():
        if body.get("run"):
            return body["entity"], body["run"]
    return None, None


def _table_exists(cur, name: str) -> bool:
    """Expand–migrate–contract: the endpoint answers before 0026 is applied
    and after, without a deploy order between them."""
    cur.execute("SELECT to_regclass(%s)", (name,))
    row = cur.fetchone()
    return bool(row and row[0])


def _promoted_answers(cur, run_id, audience: str, surface: str | None) -> list:
    """The producer's own answers for this run, or [] when the connector has
    not written any. Customer audience never sees a row marked internal."""
    if not _table_exists(cur, "serving_answers"):
        return []
    sql = ("SELECT q_id, surface, scope_id, question, rank, answer_md, "
           "absence_reason, source_page, source_section, source_path, e_ids "
           "FROM serving_answers WHERE run_id = %s")
    params: list = [run_id]
    if audience == "customer":
        sql += " AND internal_only = false"
    if surface:
        sql += " AND surface = %s"
        params.append(surface)
    sql += " ORDER BY surface, rank NULLS LAST, q_id"
    cur.execute(sql, tuple(params))
    out = []
    for (q_id, surf, scope_id, question, rank, answer_md, absence_reason,
         src_page, src_section, src_path, e_ids) in cur.fetchall():
        parts = []
        if answer_md:
            parts = [{"text": answer_md, "page": src_page,
                      "section": src_section, "path": src_path,
                      "e_ids": list(e_ids or []), "cite_scope": "item"}]
        out.append({
            "q_id": q_id, "surface": surf, "scope_id": scope_id,
            "question": question, "rank": rank,
            "provenance": "promoted", "parts": parts,
            "e_ids": list(e_ids or []),
            "absence": None if answer_md else {"reason": absence_reason},
        })
    return out


def build_answers(cur, display_id: str, audience: str = "internal",
                  run: str | None = None, role: str | None = None,
                  allow_history: bool = False,
                  surface: str | None = None) -> dict:
    """The pre-computed answer set for one entity: every anticipated question
    this run can answer, with the promoted prose and the citations behind it.

    `count` is len(answers) — computed here, never stored (invariant 8). A
    question that resolves to nothing is returned with an explicit absence
    rather than dropped, so the panel can offer the slow path by name instead
    of pretending the question was never asked."""
    pages = _load_pages(cur, display_id, audience, run, role, allow_history,
                        _ANSWER_PAGES)
    if not pages:
        raise ApiError(404, "entity_not_found",
                       f"no promoted pages for {display_id!r}")
    return answers_from_pages(cur, pages, audience, surface)


def answers_from_pages(cur, pages: dict, audience: str,
                       surface: str | None = None) -> dict:
    """The answer set over pages that are already built — so the search path
    reads the six pages ONCE and asks both questions of them."""
    entity, run_meta = _run_meta_of(pages)

    promoted = _promoted_answers(cur, run_meta["run_id"], audience, surface)
    by_key = {(a["surface"], a["scope_id"] or "", a["q_id"]): a
              for a in promoted}

    answers = list(promoted)
    for q in QUESTIONS:
        if surface and q["surface"] != surface:
            continue
        if (q["surface"], "", q["q_id"]) in by_key:
            continue                      # the producer answered it better
        parts = _parts_for(q["sources"], pages)
        cites, seen = [], set()
        for p in parts:
            for e in p["e_ids"]:
                if e not in seen:
                    seen.add(e)
                    cites.append(e)
        answers.append({
            "q_id": q["q_id"], "surface": q["surface"], "scope_id": None,
            "question": q["question"], "rank": q["rank"],
            "provenance": "selected" if parts else "absent",
            "parts": parts, "e_ids": cites,
            "absence": None if parts else {
                "reason": ("this run promoted no field that answers it — "
                           "the question is recorded, not answered")},
        })

    answers.sort(key=lambda a: (a["surface"], a["rank"] if a["rank"] is not None
                                else 99, a["q_id"]))
    answered = [a for a in answers if a["parts"]]
    return {
        "entity": entity, "run": run_meta, "audience": audience,
        "answers": answers,
        # Counts computed from the list that was just built, never asserted.
        "count": len(answers), "answered": len(answered),
    }


# ── Retrieval ────────────────────────────────────────────────────────────
#
# Deterministic ranking, stated once, in two places that must agree: here in
# SQL over `serving_passages`, and in Python over passages derived from the
# promoted sections when that table is empty. The panel carries the same rule
# again in JS (drawers.jsx `ipRank`) so it can answer without a round trip.
#
# The rule: a passage scores on COVERAGE — the share of the question's
# content terms it contains, both sides reduced to stems so "closes" answers
# "close" and "policies" answers "policy". Ties break on SUBSTANCE, then on
# payload order. No term weighting, no learned ranking, nothing that changes
# between two identical queries.
#
# Substance rather than density, and the difference is not academic. Density
# (matched terms ÷ the passage's own terms) rewards the shortest passage that
# matches, so "what is the merger doing to the data warehouse" came back with
# the four-word feature label "reusable APIs for merger data conversion"
# ahead of the paragraph that explains what the merger does to the
# warehouse. An AE asked a question; a fragment is not an answer to it.
# Capped, because past roughly eighty terms extra length stops being extra
# substance and starts being a reason a passage matched by accident.

_STOPWORDS = frozenset("""
a an and are as at be been but by can could did do does doing for from get
give had has have how in into is it its me my not of on or our should so
tell than that the their them then there these they this to us was we were
what when where which who whom why will with would you your show about many
much most any all more less need want
""".split())

_WORD = re.compile(r"[a-z0-9][a-z0-9'’\-]*")

# Coverage alone is not enough on a short question: two content words, one of
# them matched, is 0.5 — and "what is their dividend policy" would come back
# with every passage that says "policy". So a passage must clear the share
# AND carry at least two of the question's terms whenever the question has
# two to give. Returning a near-miss under "here is what this run states
# about that" is the same fabrication the frame exists to avoid.
MATCH_FLOOR = 0.6
MIN_TERMS_MATCHED = 2
SUBSTANCE_CAP = 80


def _stem(word: str) -> str:
    """A deterministic, four-line stemmer. Not linguistics — just enough that
    a question and a passage that use the same word in different numbers or
    tenses are recognised as using the same word. Same rule in the panel."""
    for suffix, replacement in (("ies", "y"), ("ing", ""), ("ed", ""),
                                ("es", ""), ("s", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[:-len(suffix)] + replacement
    return word


def query_terms(q: str) -> list:
    seen, out = set(), []
    for w in _WORD.findall((q or "").lower()):
        if w in _STOPWORDS or len(w) < 3:
            continue
        s = _stem(w)
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _passage_terms(p: dict) -> set:
    """Stemmed terms of one passage, cached on the passage. The corpus is
    walked once per request and questioned several times; re-tokenising the
    same 1,200 paragraphs for each one is the only part of this path that
    would ever be slow."""
    cached = p.get("_terms")
    if cached is None:
        cached = {_stem(w) for w in _WORD.findall((p.get("text") or "").lower())
                  if len(w) >= 3 and w not in _STOPWORDS}
        p["_terms"] = cached
    return cached


def rank_passages(question: str, passages: list, limit: int = 5) -> list:
    """Rank in-process, by the rule above. Returns [(score, passage)] over
    the floor, best first; an empty list means the run states nothing about
    the question, which is itself an answer."""
    terms = query_terms(question)
    if not terms:
        return []
    need = min(MIN_TERMS_MATCHED, len(terms))
    scored = []
    for i, p in enumerate(passages):
        words = _passage_terms(p)
        if not words:
            continue
        hit = sum(1 for t in terms if t in words)
        if hit < need:
            continue
        score = hit / len(terms)
        if score < MATCH_FLOOR:
            continue
        scored.append((score, min(len(words), SUBSTANCE_CAP), -i, p))
    scored.sort(key=lambda s: s[:3], reverse=True)
    return [(round(s[0], 4), s[3]) for s in scored[:limit]]


def _passages_from_table(cur, run_id, audience: str, question: str,
                         limit: int) -> list:
    """Lexical retrieval in the database: `ts_rank_cd` over the generated
    tsvector, with pg_trgm similarity for a query that shares no lexeme with
    the corpus (a typo, an abbreviation). Both are deterministic and neither
    is a model.

    Returns [] — not None — when the table has no rows for this run, which is
    the state before the connector writes it; the caller then derives the
    corpus from the promoted sections instead."""
    if not _table_exists(cur, "serving_passages"):
        return []
    where = "run_id = %s"
    params: list = [run_id]
    if audience == "customer":
        where += " AND internal_only = false"
    cur.execute(
        f"""SELECT text, page, section, json_path, e_ids, anchor_kind,
                   anchor_id,
                   ts_rank_cd(search_tsv, websearch_to_tsquery('english', %s)) AS lex,
                   similarity(text, %s) AS trg
              FROM serving_passages
             WHERE {where}
               AND (search_tsv @@ websearch_to_tsquery('english', %s)
                    OR text %% %s)
             ORDER BY lex DESC, trg DESC, json_path
             LIMIT %s""",
        (question, question, *params, question, question, limit))
    out = []
    for (text, page, section, path, e_ids, kind, anchor, lex, trg) in cur.fetchall():
        out.append({
            "text": text, "page": page, "section": section, "json_path": path,
            "e_ids": list(e_ids or []), "anchor_kind": kind,
            "anchor_id": anchor,
            "score": round(float(lex or 0.0) or float(trg or 0.0), 4),
        })
    return out


def search_answers(cur, display_id: str, q: str, audience: str = "internal",
                   run: str | None = None, role: str | None = None,
                   allow_history: bool = False, limit: int = 5) -> dict:
    """One question, answered from what is already promoted, or not at all.

    Three outcomes, and they are deliberately different shapes so the panel
    cannot render one as another:

      `answer`    the producer or the selection registry answers it — prose,
                  cited, with its surface named.
      `passages`  nobody answered it, so here is what the run STATES about
                  it: verbatim quotations, ranked, each with its citations
                  and the page it lives on.
      `no_match`  the run states nothing about it. The panel says so and
                  offers the slow path; it does not fill the space.
    """
    limit = max(1, min(int(limit or 5), 20))
    if not (q or "").strip():
        raise ApiError(400, "empty_question",
                       "a question is required to search this run")

    pages = _load_pages(cur, display_id, audience, run, role, allow_history,
                        _ANSWER_PAGES)
    if not pages:
        raise ApiError(404, "entity_not_found",
                       f"no promoted pages for {display_id!r}")
    entity, run_meta = _run_meta_of(pages)
    envelope = {"entity": entity, "run": run_meta, "audience": audience,
                "question": q}

    # 1 · the pre-computed set, matched on the normalised question. This is
    #     the path a starter question takes, and it is a dictionary lookup.
    norm = (q or "").strip().lower()
    for a in answers_from_pages(cur, pages, audience)["answers"]:
        if a["question"].strip().lower() == norm and a["parts"]:
            return {**envelope, "result": "answer", "answer": a}

    # 2 · retrieval over the run's own passages. The database corpus when the
    #     connector has built it; the promoted sections when it has not.
    ranked = _passages_from_table(cur, run_meta["run_id"], audience, q, limit)
    if not ranked:
        corpus = []
        for body in pages.values():
            corpus += passages_from_page(body)
        ranked = [{**p, "score": score}
                  for score, p in rank_passages(q, corpus, limit)]

    if ranked:
        return {**envelope, "result": "passages",
                "frame": "here is what this run states about that",
                "passages": ranked, "count": len(ranked)}

    return {**envelope, "result": "no_match",
            "reason": "this run states nothing that answers the question",
            # The slow path, named rather than hidden. The write it would
            # need is not built: queueing a question is an annotation with a
            # `question` anchor kind, and widening the API's writes past the
            # charter's two exceptions is a user decision, not an
            # implementation detail.
            "next": {"queue_for_synthesis": {
                "available": False,
                "reason": ("queueing a question for the next synthesis run "
                           "needs a `question` anchor kind on annotations, "
                           "which has not been adjudicated")}}}


# ── What apps/mcp has to add for tier 1 and the vector path ──────────────
#
# Both tables are written by the connector inside the promote transaction, in
# writer order, after the 34 section writers — so a page that fails to
# promote never leaves an answer index describing it (invariant 3).
#
#   serving_passages   decompose each promoted section payload with
#                      `walk_passages` above (the identical rule, or this
#                      module imported), embed each `text` with the bundled
#                      384-dim model already used for V4 grounding,
#                      L2-normalise, and insert with `embedding_model` set.
#                      `internal_only` is true where the passage's path is
#                      under one of the section's marked internal paths.
#   serving_answers    the producer's answered questions, validated at submit
#                      like any other content: an answer cites registered
#                      evidence or it is an absence with a reason. Embed the
#                      QUESTION at promote so its lookup is an index scan.
#
# The request path never embeds anything, which is the whole point: a query
# vector either already exists (a pre-embedded question) or the query is
# served lexically. See the report for the one case this deliberately does
# not build — a free-text question embedded at request time.
