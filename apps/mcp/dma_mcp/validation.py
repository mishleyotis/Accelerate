"""Validation pass 1 (stage 2.4) — structural and editorial.

Format sweeps against the contract registry: required sections and
fields, types, invented fields, the universal envelope, empty-state
ladders, and id-pattern discipline. Every reason names the gate, the
JSON path and the concrete conflict — a verdict an agent cannot act on
produces another failed submission.

Pass 2 (evidence resolution, grain locks, band words, V4) runs
separately: checking extractions against database rows is different
work from format sweeps, and the split keeps both legible.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .contracts import ENVELOPE, PAGES, sections
from .dates import ACCEPTED as DATE_SHAPES, resolve as resolve_date
from .identifiers import EID_TOKEN_RE, agent_id_class
from .shared_path import ensure as _ensure_shared
from .vacuity import check_vacuity

_ensure_shared(__file__)
from abbreviations import (  # noqa: E402  packages/shared/abbreviations.py
    EXCERPT_FIELDS as _ABBREV_VERBATIM,
    EXPANSION as _ABBREV_EXPANSION,
    PATTERN as _ABBREV,
    unexplained as _unexplained_abbrevs,
)

_AGENT_ID_KEYS = ("ic_id", "f_id", "fa_id", "ts_id", "wn_id", "rec_id")

_TYPE_CHECK = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "list": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def _norm_member(s) -> str:
    """One normaliser for both sides of the membership test, so `founded_year`,
    `Founded Year` and `founded-year` are one member and not three."""
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")


def _check_must_present(section, fname, spec, val, empty_declared) -> list:
    """CG-18 — the members a list field must contain, not just that it exists.

    THE ROOT CAUSE THIS CLOSES, measured 2026-08-14.

    Every "must-present set" in this product lived only as prose inside a
    contract's `doc` string. `required: true` applies to the CONTAINER — that
    `firmographics.fields` is a list — and CG-02 fires on
    `body.get(fname) is None`. So a payload carrying a list with ONE member
    satisfied every gate the connector has, and which members it carried was
    documentation.

    The consequence was reported by the build owner as "changes do not get
    promoted": `website` was added to the firmographics contract, no gate
    asked for it, and the next run would have omitted it exactly as the last
    one did. Measured on the live reference: 12 firmographics fields served,
    no website among them, while the producer's own absence ladder on that
    same section named the firm's domain twice. Nothing was broken. Nothing
    had been asked.

    WHAT COUNTS AS PRESENT — and this is the whole design:

      * a member carrying a value                                 -> passes
      * a member explicitly quarantined WITH a reason             -> passes
      * a member absent from the list entirely                    -> BLOCKS
      * a member present but null with no quarantine reason       -> BLOCKS

    The second line is what keeps the absence protocol legal: a field the
    ladder could not close is a finding, and it renders as a documented em
    dash. The third and fourth are the ones that were invisible — silence,
    and silence dressed as a value.

    The set is read from the contract, so a section that gains a member gains
    its enforcement in the same edit and this function never changes.
    """
    members = spec.get("must_present") or []
    any_of = spec.get("must_present_any") or []
    if not members and not any_of:
        return []
    # A section that declares an empty state and sends nothing has said so
    # honestly; CG-02 already governs whether that is allowed.
    if not val and empty_declared:
        return []
    key = spec.get("must_present_key", "field")

    stated, held, empty = set(), set(), set()
    for item in val or []:
        if not isinstance(item, dict):
            continue
        member = _norm_member(item.get(key))
        if not member:
            continue
        value = item.get("value")
        if value not in (None, "", []):
            stated.add(member)
        elif item.get("quarantined") and str(item.get("quarantine_reason") or "").strip():
            held.add(member)
        else:
            empty.add(member)

    out, accounted = [], stated | held
    for want in members:
        # A member may be a STRING or a LIST OF ALIASES for one fact. The
        # spec writes "founded year"; the corpus writes `founded`; the
        # normaliser folds case and punctuation but not synonyms, so the gate
        # refused the gold-standard payload for a field it plainly stated.
        # A gate that refuses correct content teaches producers to route
        # around it, which is worse than the gap it was guarding.
        aliases = want if isinstance(want, (list, tuple)) else [want]
        norms = [_norm_member(a) for a in aliases]
        want = aliases[0]                      # the canonical name, for prose
        norm = norms[0]
        if any(n in accounted for n in norms):
            continue
        if any(n in empty for n in norms):
            out.append(_reason(
                "CG-18", section, f"{section}.{fname}[{want}]",
                f"must-present member {want!r} is present with no value and "
                "no quarantine reason — an unexplained blank is the one state "
                "this set exists to refuse. Either state the value with its "
                "provenance, or run the ladder and mark the field "
                "`quarantined` with `quarantine_reason`; a documented em dash "
                "is a finding, a silent one is an omission"))
        else:
            out.append(_reason(
                "CG-18", section, f"{section}.{fname}",
                f"must-present member {want!r} is absent from "
                f"{section}.{fname} entirely. The contract's must-present set "
                "is not a suggestion: every member is stated with its "
                "provenance, or held with `quarantined` and a "
                "`quarantine_reason` naming the ladder that failed. Absent "
                "beats wrong, but absent-and-unmentioned is neither"))
    for group in any_of:
        if any(_norm_member(g) in accounted for g in group):
            continue
        out.append(_reason(
            "CG-18", section, f"{section}.{fname}",
            f"none of {', '.join(map(repr, group))} is stated or held — the "
            "set requires one of them, and a sub-vertical that genuinely "
            "reports none of them still has to say which ladder established "
            "that"))
    return out


# ── CG-20 · a vendor is a company, not a category ─────────────────────
#
# The contract has always said it: "A PRODUCT, not a service and not a
# category — 'Salesforce Financial Services Cloud' is a product; 'CRM',
# 'Analytics/BI', 'Django' are not; vendor and product are separate fields."
# Nothing checked it, so rows reading `vendor: "Integration platform"` and
# `vendor: "e-signature vendor (unnamed)"` promoted onto a client's technology
# register beside Salesforce and Fortinet. The build owner called them noise
# entries, which is exactly what they are: a placeholder for research that did
# not finish, rendered with the same weight as a confirmed deployment.
#
# Measured over both promoted registers, 2026-08-14: 39 distinct vendors, of
# which exactly 3 are categories and 36 are real companies. Both rules below
# separate them with no false positives — "Early Warning Services" keeps its
# generic third word and passes, because it also carries two words that are
# not generic.
_CG20_PLACEHOLDER = ("unnamed", "unknown", "tbd", "n/a", "not named",
                     "to be confirmed", "unspecified")
_CG20_GENERIC = frozenset((
    "platform", "platforms", "vendor", "vendors", "tool", "tools", "tooling",
    "solution", "solutions", "software", "provider", "providers", "system",
    "systems", "suite", "service", "services", "integration", "portal",
    "application", "applications", "app", "apps", "product", "products",
    "the", "a", "an", "and", "or", "of", "unnamed", "unknown", "tbd",
))


def _card_key(text) -> str:
    """The comparison both sides of a duplicate get reduced to.

    Words, lowercased, in order. Punctuation, capitalisation and whitespace
    are formatting; two cards that differ only in those are one argument
    written twice, and a byte comparison would let a stray comma pass a
    duplicate through.
    """
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _check_cards_unique(section, body) -> list:
    """CG-25 — one card per argument.

    Nothing deduplicates insight cards anywhere: `adaptInsights` is a
    straight `.map`, so a card written twice renders twice and counts twice
    toward the headline count the reader takes on trust. The issue register
    carries a dedup rule for precisely this failure; the cards, which are
    the page's whole argument, carried none.

    Checked on three keys because they fail differently. A repeated `ic_id`
    is a minting slip and the second row overwrites the first at promotion.
    A repeated title or claim is the same argument written twice, which no
    id check would ever see.
    """
    if section != "insights" or not isinstance(body, dict):
        return []
    cards = body.get("cards")
    if not isinstance(cards, list):
        return []
    out = []
    for field, label in (("ic_id", "identifier"),
                         ("title", "title"),
                         ("what_text", "claim")):
        seen = {}
        for i, c in enumerate(cards):
            if not isinstance(c, dict):
                continue
            key = _card_key(c.get(field))
            if not key:
                continue
            if key in seen:
                first = seen[key]
                out.append(_reason(
                    "CG-25", section, f"{section}.cards[{i}].{field}",
                    f"this card's {label} is the one card {first} already "
                    f"carries. Two cards saying the same thing render twice "
                    f"and count twice toward the headline the reader trusts, "
                    f"so merge them into the argument you meant to make, or "
                    f"make the second one a different argument. Compared on "
                    f"words, so reformatting one copy does not separate them."))
            else:
                seen[key] = f"cards[{i}]"
    return out


# ── round-4 gates: four ways a payload passed every check and still read
#    wrong on the page ────────────────────────────────────────────────────

# `\d+\.\d+`, not `\d\.\d`: the first version of this pattern could not
# match "2.52" — the trailing word boundary failed against the second decimal
# — so it read the very sentence it was written for as clean. And the
# separator class covers a typographic apostrophe, because prose written for a
# client surface uses one.
_NUM = r"\d+\.\d+"
_RUN = r"this run['’]?s?"
_SCORE_RECAP = re.compile(
    r"(?:\b(?:pillar|category|composite|subcap|cell)s?\b[^.\n]{0,80}?" + _NUM
    + r"|" + _NUM + r"[^\n]{0,60}?\bagainst\s+" + _RUN
    + r"|\b" + _RUN + r"[^\n]{0,60}?" + _NUM
    + r"|\bcohort\b[^\n]{0,80}?" + _NUM + r")", re.I)


def _check_why_now_is_an_event(section, body) -> list:
    """AG-11 — a why-now signal is a DATED EXTERNAL EVENT, never a score recap.

    Measured on the reference client: WN-4's trigger read "a five-member
    same-sub-vertical cohort read on 19 August 2026 sits at 2.52, 2.70, 2.50
    and 2.36 across the four pillars against this run's 1.60, 1.52, 1.75 and
    1.43". Every figure in it is this assessment's own output. It passed every
    gate, because nothing in the contract said a trigger has to be about the
    world.

    The distinction is not stylistic. Why-now answers "what changed outside
    this institution that makes now the moment"; a score recap answers "what
    did we score", which the heatmap already answers and the reader has
    already seen. A signal that recaps is a signal the page did not need, and
    it displaces one it did.
    """
    if section != "why_now" or not isinstance(body, dict):
        return []
    out = []
    for i, sig in enumerate(body.get("signals") or []):
        if not isinstance(sig, dict):
            continue
        for field in ("trigger", "headline", "so_what", "metric"):
            text = sig.get(field)
            if not isinstance(text, str) or not text.strip():
                continue
            if _SCORE_RECAP.search(text):
                out.append(_reason(
                    "AG-11", "why_now", f"why_now.signals[{i}].{field}",
                    f"{sig.get('wn_id') or f'signal {i}'} states this "
                    "assessment's own scores where a dated external event "
                    "belongs. Why-now answers what changed OUTSIDE the "
                    "institution to make now the moment; the scores are the "
                    "heatmap's answer to a different question and the reader "
                    "has already seen them. Replace it with an event that has "
                    "a date and a source, or drop the signal — a recap "
                    "displaces a signal the page needed."))
                break
    return out


def _check_thought_leadership_unique(section, body) -> list:
    """CG-26 — one entry per SOURCE DOCUMENT.

    Reported as "thought leadership signals at 3 with 2 duplicates". Two of
    the three carried the same `url` — one congressional testimony quoted
    twice, with different quotes, different e_ids and different alignments.
    Not duplicates by any field check, and duplicates to every reader: same
    headline stem, same author, same date, same link.

    A second quote from a document already cited belongs IN that entry, and
    the freed slot belongs to a document the ladder has not reached.
    """
    if section != "thought_leadership" or not isinstance(body, dict):
        return []
    out, seen = [], {}
    for i, e in enumerate(body.get("entries") or []):
        if not isinstance(e, dict):
            continue
        url = str(e.get("url") or "").strip().rstrip("/").lower()
        if not url:
            continue
        if url in seen:
            out.append(_reason(
                "CG-26", "thought_leadership",
                f"thought_leadership.entries[{i}].url",
                f"entry {i} cites the same document as entry {seen[url]}. To a "
                "reader that is the same item listed twice — same link, same "
                "author, same date — however different the quotes are. Merge "
                "the second quote into the first entry, citing both evidence "
                "ids, and give the slot to a document this ladder has not "
                "reached."))
        else:
            seen[url] = i
    return out



# VERBATIM BY CONTRACT, and therefore never rewritten: an excerpt is a
# byte-for-byte span of a fetched artefact (invariant 4), and a quote or a
# person's own words are what someone actually said. Expanding an abbreviation
# inside one would misquote a source and break the verifier that compares an
# excerpt against the bytes it was taken from. Measured: a focus area's
# `verbatim_quote` was rewritten from "greater CFPB scrutiny" to the full
# phrase — a chief executive's congressional testimony, misquoted by a tidy-up.
#
# `source_name`, `source_title` and `author_role` USED TO BE IN THIS SET and
# are not any more. They are labels this application writes about an artefact,
# not spans of it: the package author typed "…Logix FCU" and a producer typed
# "…Logix Federal Credit Union" for the same document at the same URL, and
# neither is its filed title. The artefact's identity is its URL, which the
# drawer shows beside the label. See packages/shared/abbreviations.py.
_VERBATIM_FIELDS = _ABBREV_VERBATIM

#: How many CG-27 paths a verdict spells out before it switches to a count.
#: Enough that a small section is fully enumerated and a producer can work
#: straight down the list; past it, the total plus the per-abbreviation
#: breakdown is what makes the repair converge.
_CG27_LISTED = 24


def _check_no_bare_abbreviations(page, section, body) -> list:
    """CG-27 — a client surface spells it out the first time.

    Fifty occurrences of FCU, forty-eight of NCUA, and CU itself reached
    promoted prose. A reader outside this industry does not know them, and a
    reader inside it does not need them shortened; either way the abbreviation
    costs comprehension and buys nothing on a page that is not short of room.

    Only AUTHORED prose and the labels this application writes. A quote or an
    excerpt is a verbatim span, and rewriting one would misquote the source and
    break the evidence verifier that compares an excerpt against the bytes it
    was taken from — those are exempt. A source NAME is not a span: see
    packages/shared/abbreviations.py for where that line now falls and why it
    moved.
    """
    if not isinstance(body, dict):
        return []
    out = []

    def walk(node, path, key=None):
        # NO EARLY RETURN. This used to stop at six reasons — "name a handful,
        # not a wall" — and the handful read as the whole job. Measured
        # 2026-08-23 (MEM-0195): one heatmap verdict listed 13 CG-27 paths;
        # walking the identical tree with the same PATTERN and EXPANSION
        # found 102, a factor of 7.8. A producer repairs what the verdict
        # names, resubmits, and is handed the next six — so the repair never
        # converges and the run burns a round trip per handful.
        #
        # The wall was a real concern, so the fix is not to print 102 reasons:
        # it is to walk the whole section, list a readable prefix, and say
        # HOW MANY there are and where, so one sweep can finish the section.
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}", k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]", key)
        elif isinstance(node, str) and key not in _VERBATIM_FIELDS and node.strip():
            # NO LENGTH FLOOR. It was 12 characters, on the reasoning that a
            # short string is a label rather than prose — and a unit is the
            # shortest string on any page. "FTE" is three characters and
            # rendered on the overview footer of every client, invisible to
            # this gate and to the expander beside it, through four rounds of
            # abbreviation sweeps.
            for m in _ABBREV.finditer(node):
                short = m.group(1)
                # Spelled out in the same field is a second reference and
                # reads correctly as one — but only ITS OWN expansion counts.
                if re.search(re.escape(_ABBREV_EXPANSION[short]), node, re.I):
                    continue
                out.append(_reason(
                    "CG-27", section, f"{page}.{path}",
                    f"'{short}' reaches a client surface unexplained. "
                    "Spell it out on first use in the field; the short "
                    "form is fine afterwards. Quotes and excerpts are "
                    "verbatim spans and are never rewritten — a source "
                    "NAME is a label this application writes, so it is "
                    "spelled out like any other."))
                break            # one reason per field: it is one edit

    walk(body, section)
    if len(out) <= _CG27_LISTED:
        return out
    # More than a reader can act on one at a time. List a prefix, then say
    # exactly how many there are and which abbreviations account for them, so
    # the producer sweeps the section ONCE instead of discovering the size of
    # the job six reasons at a time.
    tally = Counter()
    for r in out:
        m = re.search(r"'([A-Za-z0-9]+)' reaches", r.get("message", ""))
        if m:
            tally[m.group(1)] += 1
    spread = ", ".join(f"{k} {v}" for k, v in tally.most_common(8))
    listed = out[:_CG27_LISTED]
    listed.append(_reason(
        "CG-27", section, f"{page}.{section}",
        f"{len(out)} unexplained abbreviations in this section, of which "
        f"{_CG27_LISTED} are listed above. By abbreviation: {spread}. "
        f"REPAIR THE WHOLE SECTION IN ONE PASS — the listed paths are a "
        f"sample, not the job. Repairing only what is named here resubmits "
        f"into the same gate with {len(out) - _CG27_LISTED} still there. "
        f"Every expansion this gate knows is in "
        f"packages/shared/abbreviations.py; a sibling section often already "
        f"carries the clean label for the same id, which is the cheapest "
        f"repair available."))
    return listed


# Words that make a finding read as an accusation. Each was measured in a
# promoted starter or is the same move in different words.
_ACCUSATORY = (
    (r"\bdo(?:es)? not (?:quite )?line up\b",
     "says the client contradicted itself"),
    (r"\bwhat it cannot do\b", "opens on an incapacity"),
    (r"\byou (?:have )?(?:failed|neglected|ignored|missed)\b",
     "assigns fault"),
    (r"\b(?:do|does|did)?\s*you\s+(?:do not|don'?t|not)\s+"
     r"(?:have|know|track|measure|hold|report)\b",
     "opens on an absence in the second person"),
    (r"\bwhy (?:do|does|did)n'?t? you\b|\bwhy do you not\b",
     "asks the client to account for an absence"),
    (r"\byour (?:problem|weakness|deficienc)\w*\b", "names a deficiency"),
    (r"\bfall(?:s|ing)? (?:short|behind)\b", "ranks the client down"),
    (r"\blag(?:s|ging)? (?:behind|the)\b", "ranks the client down"),
    (r"\bno (?:real|actual) \w+ (?:exists|in place)\b",
     "states a bare absence where an opening belongs"),
)


# Every section whose prose a CLIENT reads. Restricting this to `starters` was
# the first version's mistake: the phrase that reached the live page —
# "What it cannot do is answer a question" — was on a platform-story tile, one
# card away from the starters and read by exactly the same person.
_CLIENT_FACING = frozenset((
    "starters", "platform_story", "recommendations", "roadmap", "stairstep",
    "opportunity", "findings", "exec_summary", "why_now",
))


def _check_starter_tone(section, body) -> list:
    """AG-12 — a starter opens on an opportunity, never on an accusation.

    A conversation starter is read by the client. "Two things you have told
    the market do not quite line up" is an accusation of inconsistency, and
    "what it cannot do is answer a question" opens on an incapacity — both
    were promoted. The same fact stated as an opening ("the app does the
    transactional work well, and the next thing it could do is answer a
    question") costs nothing and lands better.

    The gate refuses the MOVE, not a word list: each pattern is a way of
    making the client the subject of a failure.
    """
    if section not in _CLIENT_FACING or not isinstance(body, dict):
        return []
    out = []

    def walk(node, path, key=None):
        if len(out) >= 8:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}", k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]", key)
        elif isinstance(node, str) and len(node) > 30 and key not in _VERBATIM_FIELDS:
            for pat, why in _ACCUSATORY:
                if re.search(pat, node, re.I):
                    out.append(_reason(
                        "AG-12", section, path,
                        f"this {why}, and the client reads it. State the same "
                        "fact as the opening it is: what is in place, and the "
                        "next thing it makes possible. A gap presented as an "
                        "opportunity is the same information and a different "
                        "conversation."))
                    break

    walk(body, section)
    return out


_OFFICER_TITLE = re.compile(
    r"\bchief\s+(executive|information security|information|operating|"
    r"technology|financial|data|risk|legal|marketing|administrative|"
    r"lending|experience|digital)\s+officer\b", re.I)


def _check_roster_keeps_uncontactable(section, body) -> list:
    """CG-28 — an executive is not dropped for want of a contact route.

    The roster is the accountability set for the assessment; contact
    enrichment is a convenience on top of it. A seat that owns a finding
    belongs on the page whether or not a work address came back — dropping it
    silently makes the institution look smaller than it is and hides the owner
    of the gap being discussed. Reported directly: "I do not see the CTO. Do
    not exclude executives whose contacts cannot be retrieved."

    ENFORCED AGAINST THE PAYLOAD'S OWN STATEMENT of who is accountable. The
    section's `r_layer.domain_test` names the accountability set in prose —
    on the reference client, "chief executive, chief information officer,
    chief operating officer and chief information security officer" — and the
    roster served three of those four. Titles are matched, never names: a
    title is a small closed vocabulary and a name is not.

    What this CANNOT see, and says so rather than pretending: a seat nobody
    named anywhere. That half lives in the producer skill's antipatterns and
    in a render test that a roster row with no email still draws.
    """
    if section != "leadership" or not isinstance(body, dict):
        return []
    roster = body.get("roster")
    if not isinstance(roster, list):
        return []
    out = []

    served = {m.group(0).lower()
              for r in roster if isinstance(r, dict)
              for m in _OFFICER_TITLE.finditer(str(r.get("title") or ""))}

    rl = body.get("r_layer")
    accountable = []
    if isinstance(rl, dict):
        for key in ("domain_test", "hypothesis", "counter"):
            text = rl.get(key)
            if isinstance(text, str):
                accountable.extend(m.group(0).lower()
                                   for m in _OFFICER_TITLE.finditer(text))
    missing = sorted({t for t in accountable if t not in served})
    if missing:
        out.append(_reason(
            "CG-28", "leadership", "leadership.roster",
            "this section names " + ", ".join(missing) + " as accountable and "
            "serves no such seat. An executive is not dropped because contact "
            "enrichment returned nothing: the roster IS the accountability "
            "set, and a missing seat hides the owner of a gap this run is "
            "discussing. Serve the seat with the fields that are known and "
            "let the contact route be the thing that is absent."))

    known = body.get("seats_identified")
    if isinstance(known, int) and known > len(roster):
        out.append(_reason(
            "CG-28", "leadership", "leadership.roster",
            f"{known} seats were identified and {len(roster)} are served."))
    for i, m in enumerate(roster):
        if isinstance(m, dict) and m.get("dropped_for_no_contact"):
            out.append(_reason(
                "CG-28", "leadership", f"leadership.roster[{i}]",
                "a seat is marked dropped for want of a contact route. Serve "
                "it; the absence belongs on the contact field, not on the "
                "person."))
    return out


#: "20 C-suite contacts resolved", "resolved 20 contacts", "returned 14
#: contact records". A COUNT next to a resolution verb, in the section's own
#: account of what it searched. Zero is matched too and is harmless: the gate
#: only fires on a positive count.
_RESOLVED_CONTACTS = re.compile(
    r"(?:(\d+)\s+(?:[\w-]+\s+){0,3}contacts?\s+(?:were\s+)?(?:resolved|returned|found)"
    r"|(?:resolved|returned)\s+(\d+)\s+(?:[\w-]+\s+){0,3}contacts?)", re.I)

#: The fields migration 0018 binds 1:1 per person. Any one of them present is
#: a route the reader can act on.
_CONTACT_ROUTE_FIELDS = ("email", "linkedin_url", "phone")


def _check_resolved_contacts_are_served(section, body) -> list:
    """CG-32 — an enrichment that resolved is an enrichment that serves.

    On the promoted T. Rowe Price run the leadership section served six seats
    with every contact route null, and said why in its own `sources_searched`:

        "Clay contact enrichment task mcp-task_0tk3p6ia8ykw5sfVpVR — RAN and
         COMPLETED this session, 20 C-suite contacts resolved; per-contact
         output not delivered to this producer invocation, so 0 of 6"

    Twenty contacts were fetched and lost between the tool and the producer.
    Every gate passed, because each half is individually legal: a null contact
    route is a permitted absence (CG-28 exists precisely to keep the person on
    the page when the route does not come back), and naming what was searched
    is what the contract asks for. Only the COMBINATION is a defect, and
    nothing read both halves of the sentence.

    So this gate reads both. It fires ONLY on the contradiction — a positive
    resolved count beside zero served routes. A section that says the tool was
    not attached, or ran and resolved nothing, is honestly thin and passes:
    thin content is an assessment result, and a gate that refused it would
    push producers toward inventing contact details.
    """
    if section != "leadership" or not isinstance(body, dict):
        return []
    roster = body.get("roster")
    if not isinstance(roster, list) or not roster:
        return []

    served = sum(1 for r in roster if isinstance(r, dict)
                 and any(str(r.get(f) or "").strip() for f in _CONTACT_ROUTE_FIELDS))
    if served:
        return []

    es = body.get("empty_state")
    texts = []
    if isinstance(es, dict):
        for v in es.values():
            if isinstance(v, str):
                texts.append(v)
            elif isinstance(v, list):
                texts.extend(x for x in v if isinstance(x, str))
    for text in texts:
        m = _RESOLVED_CONTACTS.search(text)
        if not m:
            continue
        count = int(m.group(1) or m.group(2) or 0)
        if count <= 0:
            continue
        return [_reason(
            "CG-32", "leadership", "leadership.roster",
            f"this section's own disclosure says {count} contacts were "
            f"resolved, and it serves a contact route on none of its "
            f"{len(roster)} seats. That is a dropped result, not an absence: "
            f"the enrichment ran, the values exist, and they did not reach "
            f"the payload. Hand the per-contact output to the producer and "
            f"re-emit, or — if the values genuinely cannot be recovered — say "
            f"that the delivery failed rather than reporting a count that "
            f"never reached a reader.")]
    return []


#: The Surface Specification's own floor was 2 ("Fewer than 2 entries after
#: searching all seven source families -> emit what you have, set thin=true").
#: Raised to 3 by the owner on 2026-08-22 after the T. Rowe Price page served
#: one. Held here as a named constant so the number has one home.
THOUGHT_LEADERSHIP_FLOOR = 3

#: How far back a financial trajectory must reach. The Surface Specification's
#: Context page header states it in as many words — "8 of 8 events · 4 issues ·
#: 5-year financials".
FINANCIAL_SERIES_YEARS = 5

_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def _years_in(*values) -> set:
    out = set()
    for v in values:
        for m in _YEAR.finditer(str(v or "")):
            out.add(int(m.group(0)))
    return out


def _check_thought_leadership_depth(section, body) -> list:
    """CG-33 — the card carries three executives speaking, or says why not.

    The T. Rowe Price page served ONE entry. The section was honest about it —
    thin=true, and a `sources_searched` naming per-executive searches across
    earnings transcripts, PR Newswire, DEF 14A and investor relations — so
    nothing refused it: the spec's floor was 2 and the disclosure was real.

    The owner raised the floor to 3 (2026-08-22). What makes that reachable
    rather than a wall is the second half of the same decision: the run's own
    reason said the evidence store carries executive coverage for five of six
    roster members as researcher paraphrases and quoted fragments UNDER THE
    80-CHARACTER FLOOR or truncated mid-word — the chief technology officer
    seat alone had five publications with no admissible quote among them. The
    speech exists; the registration was not capturing quotable spans. So this
    message names that route, because a producer told only "find one more" will
    go looking for a sixth publication rather than re-registering the five it
    already has.
    """
    if section != "thought_leadership" or not isinstance(body, dict):
        return []
    entries = body.get("entries")
    if not isinstance(entries, list) or len(entries) >= THOUGHT_LEADERSHIP_FLOOR:
        return []
    return [_reason(
        "CG-33", "thought_leadership", "thought_leadership.entries",
        f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'} served and "
        f"{THOUGHT_LEADERSHIP_FLOOR} are required. Before searching for another "
        f"publication, check the ones already registered: an entry is "
        f"admissible only on a VERBATIM quote of 80-260 characters, and the "
        f"commonest cause of a thin card is evidence registered with a "
        f"paraphrase, a fragment under the floor, or a span truncated "
        f"mid-word. Re-register those sources with a continuous quoted span "
        f"and the entries follow. thin=true records the shortfall; it does not "
        f"excuse it.")]


def _check_financial_series_reach(section, body) -> list:
    """CG-34 — a trajectory reaches back five years, or the search did.

    The T. Rowe Price page served two points — FY2025 year-end and Q2 2026 —
    and its own `reading` called it "a snapshot, not a trajectory". The section
    set verified_sparse and named what it searched, so every gate passed; the
    Surface Specification nonetheless states the intent plainly, in the Context
    page header: "8 of 8 events · 4 issues · 5-year financials".

    The producer resolved the latest results release and stopped. For a public
    filer, prior-year assets under management sit in the same investor-relations
    page and the same annual report it had already opened.

    So the test is on REACH, not on luck: either five distinct years are
    served, or the disclosure shows the ladder actually looked at a period at
    least four years older than the newest point. That is checked by reading
    the YEARS named in the search account, not by matching the words "10-K" or
    "annual report" — a producer that searched a 2021 filing says 2021, in
    whatever form of words it likes, and an entity with genuinely no published
    history can still satisfy it by showing where it looked.
    """
    if section != "financial_series" or not isinstance(body, dict):
        return []
    series = body.get("series")
    if not isinstance(series, list) or not series:
        return []                       # an empty series is CG's empty-state job

    served = set()
    for p in series:
        if isinstance(p, dict):
            served |= _years_in(p.get("as_of"), p.get("period"))
    if len(served) >= FINANCIAL_SERIES_YEARS:
        return []

    newest = max(served) if served else None
    if newest is None:
        return []                       # undated points are the date gates' job

    reach = newest - (FINANCIAL_SERIES_YEARS - 1)
    es = body.get("empty_state")
    searched = set()
    if isinstance(es, dict):
        for v in es.values():
            if isinstance(v, str):
                searched |= _years_in(v)
            elif isinstance(v, list):
                searched |= _years_in(*[x for x in v if isinstance(x, str)])
    if any(y <= reach for y in searched):
        return []

    return [_reason(
        "CG-34", "financial_series", "financial_series.series",
        f"{len(served)} distinct year{'' if len(served) == 1 else 's'} served "
        f"({', '.join(str(y) for y in sorted(served))}) against the "
        f"{FINANCIAL_SERIES_YEARS}-year trajectory the surface is specified to "
        f"carry, and the search account names no period at or before {reach}. "
        f"A trajectory is the point of this card — two dated points are a "
        f"snapshot. For a public filer the earlier figures are in the "
        f"investor-relations page and the annual report already cited for the "
        f"latest one, so walk back to {reach} in the entity's OWN filings. If the "
        f"history genuinely is not published, say where you looked and name "
        f"the years, and this passes on the search rather than on the result.")]


#: Characters that never belong in anything a client reads.
#:
#: DELIBERATELY NARROW. `§` is NOT here — a regulatory citation ("12 CFR
#: § 1026.36") is real and common in this corpus, and a gate that refused it
#: would be refusing correct work. What is listed either marks up a manuscript
#: rather than a sentence (pilcrow, dagger, double dagger), is invisible and
#: therefore un-auditable (zero-width, soft hyphen, byte-order mark), or is
#: already the evidence of a decoding failure (the replacement character).
_BAD_CHARS = {
    "¶": "PILCROW SIGN",
    "†": "DAGGER",
    "‡": "DOUBLE DAGGER",
    "­": "SOFT HYPHEN (invisible)",
    "​": "ZERO WIDTH SPACE",
    "‌": "ZERO WIDTH NON-JOINER",
    "‍": "ZERO WIDTH JOINER",
    "﻿": "BYTE ORDER MARK",
    "�": "REPLACEMENT CHARACTER (a decode already failed)",
}


def _walk_strings(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def _check_no_typesetting_marks(section, body) -> list:
    """CG-35 — a manuscript mark is not a sentence.

    Reported 2026-08-22 from the focus-area drilldown: "Invalid characters".
    Four pilcrows had reached the served page, inside `source_document`:

        "T. Rowe Price press release — T. Rowe Price Announces Creation of
         Global Strategy Function (¶4 of the release (Sharps quote),
         immediately after ¶3's introduction of Andrew Reich)"

    The provenance was true and the placement was useful to whoever wrote it.
    It is still not a document title, and `¶` is a mark most readers cannot
    name. It arrived because the same annotation had first been written into
    `source_page` — an INTEGER column — and was moved to the nearest string
    field rather than dropped, so this gate is the second half of that repair.

    Also catches the invisible ones. A zero-width space or a soft hyphen
    changes nothing on screen and silently breaks every search, comparison and
    dedup that touches the field; the replacement character means a decode
    already failed upstream and the run is serving the damage.
    """
    if not isinstance(body, dict):
        return []
    out = []
    for path, text in _walk_strings(body):
        hits = {ch for ch in text if ch in _BAD_CHARS}
        if not hits:
            continue
        named = ", ".join(f"{ch!r} ({_BAD_CHARS[ch]})" for ch in sorted(hits))
        where = text
        for ch in hits:
            i = where.find(ch)
            if i >= 0:
                where = where[max(0, i - 40):i + 40]
                break
        out.append(_reason(
            "CG-35", section, f"{section}.{path}" if path else section,
            f"served text carries {named}. Around it: …{where.strip()}… "
            f"A pilcrow or a dagger marks up a manuscript rather than saying "
            f"anything to a reader, and the invisible ones break every search "
            f"and comparison that touches the field without changing what is "
            f"on screen. If the detail is worth keeping, say it in words; if "
            f"it is a placement note for the producer, it does not belong in "
            f"a field the client reads."))
    return out


#: How long a citation LABEL runs. Measured 2026-08-22 across the two
#: promoted clients: Baxter's four focus areas cite in 37, 46, 47 and 52
#: characters — `Publisher — subject (YYYY-MM)`. T. Rowe Price's four ran
#: 178, 211, 236 and 266. The ceiling sits at more than twice Baxter's
#: longest, so a genuinely long publication title passes and a paragraph
#: does not.
SOURCE_LABEL_MAX = 120

#: The words a locator note uses. Present INSIDE a parenthetical, they are
#: what separates "where in the document" from a subtitle that is part of the
#: document's actual name.
_LOCATOR_WORDS = re.compile(
    r"(?i)\b(?:paragraph|para\.?|immediately\s+(?:after|before|above|below)|"
    r"directly\s+(?:above|below|after|before)|"
    r"(?:sub)?heading\s+(?:beneath|above|below)|"
    r"opening\s+statement|prepared\s+remarks|"
    r"(?:after|before)\s+the\s+\w+[\w /-]*\s+(?:discussion|section|block))\b")

_PARENTHETICAL = re.compile(r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)")


def _check_source_label_is_a_citation(section, body) -> list:
    """CG-36 — `source_document` names a document; it does not locate a quote.

    Reported 2026-08-22 as "the focus area heatmap drilldown has very
    different shapes as required by the golden standards", with a screenshot
    of a SOURCE line running three wrapped lines under a clipped title.

    The shapes, measured rather than eyeballed:

        Baxter          37  46  47  52   'PYMNTS — BCU Data Culture & AI panel (2025-08)'
        T. Rowe Price  178 211 236 266   '... Global Strategy Function (¶4 of the
                                          release (Sharps quote), immediately
                                          after ¶3's introduction of Andrew Reich)'

    Same contract, same field set, same section keys — every gate passed. What
    differs is that one is a citation and the other is a citation with a
    locator note welded onto it.

    IT GOT THERE BY A REPAIR. The locator was first written into `source_page`,
    an INTEGER column, where it broke promotion with a Postgres type error.
    Moving it to the nearest string field made the promote succeed, put a
    pilcrow on a client's page (CG-35), and made the chip overflow its own box
    (the SOURCE row fix in `pages-d3-heatmap.jsx`). Three defects, one cause,
    and the field has no home for that note because a document's name is not
    where a quote sits inside it. `verbatim_quote` already says which span was
    used; that IS the locator.

    Length alone would be a blunt rule, so the refusal names whichever of the
    two it found — a locator parenthetical, or a label past the ceiling — and
    a long title with no locator note is refused on length only, which is the
    honest reason.
    """
    if not isinstance(body, dict):
        return []
    out = []
    for path, text in _walk_strings(body):
        if not path.endswith("source_document"):
            continue
        label = text.strip()
        locators = [p for p in _PARENTHETICAL.findall(label)
                    if _LOCATOR_WORDS.search(p) or "¶" in p]
        if not locators and len(label) <= SOURCE_LABEL_MAX:
            continue
        if locators:
            why = (f"it carries a locator note — \"({locators[0][:90]}…)\" — "
                   f"which says where in the document the quote sits, not what "
                   f"the document is called")
        else:
            why = (f"it runs {len(label)} characters against a "
                   f"{SOURCE_LABEL_MAX}-character ceiling for a citation label")
        out.append(_reason(
            "CG-36", section, f"{section}.{path}" if path else section,
            f"this source label is not a citation: {why}. A reader sees this "
            f"string in a one-line SOURCE row beside the document link, so a "
            f"paragraph here wraps over its neighbour instead of naming the "
            f"source. Cite it the way the rest of the corpus does — publisher, "
            f"subject, and the period in brackets, e.g. "
            f"\"PR Newswire — Global Strategy function (2025-11)\" — and let "
            f"`verbatim_quote` carry which span was used, which is what a "
            f"locator note was standing in for."))
    return out


def _check_contact_routes_are_marked(section, body) -> list:
    """CG-37 — a way to reach a named person is marked, or it reaches the client.

    Invariant 5 is default-deny and server-side, but the DENY LIST IS THE
    PRODUCER'S: `redaction.py` strips the paths a section marks in
    `internal_only`, and a path nobody marks is served. The contract says as
    much in as many words — "Marking is the producer's duty: a path you do not
    mark reaches the client" — and until now nothing checked that the duty was
    discharged. The contract requires the FIELD, never its contents.

    That was survivable while the field was always null. It stopped being
    survivable on 2026-08-22, when a re-polled Clay task put five named
    executives' work addresses and LinkedIn profiles onto a promoted roster:
    real personal contact data for real people at a real firm, one forgotten
    list entry away from the customer-facing body.

    Scoped to a route beside a NAME, which is what makes it personal. A
    switchboard number on a firmographics card is a company's published
    contact and not this gate's business; the same column beside "Rob Sharps"
    is. So the trigger is a dict that carries both a person's name and a way
    to reach them.

    Every unmarked path is named individually. A producer told only "something
    is unmarked" on a six-seat roster has fifteen fields to check by hand,
    which is how a marking gets missed in the first place.
    """
    if not isinstance(body, dict):
        return []
    marked = {str(p) for p in (body.get("internal_only") or [])
              if isinstance(p, str)}
    unmarked = []

    def walk(node, path):
        if isinstance(node, dict):
            name = str(node.get("name") or "").strip()
            if name and name not in ("-", "—"):
                for f in _CONTACT_ROUTE_FIELDS:
                    if str(node.get(f) or "").strip():
                        p = f"{path}.{f}" if path else f
                        if p not in marked:
                            unmarked.append((p, name))
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(body, "")
    if not unmarked:
        return []
    shown = ", ".join(f"{p} ({who})" for p, who in unmarked[:6])
    more = f" and {len(unmarked) - 6} more" if len(unmarked) > 6 else ""
    return [_reason(
        "CG-37", section, f"{section}.internal_only",
        f"{len(unmarked)} contact route{'' if len(unmarked) == 1 else 's'} for "
        f"a named individual {'is' if len(unmarked) == 1 else 'are'} not in "
        f"this section's internal_only list: {shown}{more}. The serve layer "
        f"strips what a section marks and serves what it does not, so an "
        f"unmarked work address is published to the customer audience — not "
        f"hidden by a default, not caught downstream. Add each path exactly as "
        f"written above; marking is per-field and per-person, because a roster "
        f"that gains a seat gains five paths nobody re-checks.")]


def _check_page_thread(page, section, fields, body) -> list:
    """CG-23 — a section whose writer stores a thread carries one.

    The contract registry merges `narrative_thread` into a section's fields
    only where that section's WRITER binds the column (contracts.py,
    `_section_meta_for`), so the presence of the key in `fields` is exactly
    the question "does this section have somewhere to put a thread". Six of
    the thirty-four writers bind it at item grain instead and are silently
    exempt here, which is why the field itself stays `required: false` and
    this check reads the writer rather than the flag.

    Measured 2026-08-18: the third client promoted 16 of 34 sections with a
    null thread; the reference client had 32 of 33 written. Nothing refused
    either, because `required: false` is a statement about the FIELD and the
    obligation is about the PAGE.
    """
    if "narrative_thread" not in (fields or {}):
        return []
    if not isinstance(body, dict):
        return []
    thread = body.get("narrative_thread")
    if isinstance(thread, str) and thread.strip():
        return []
    return [_reason(
        "CG-23", section, f"{section}.narrative_thread",
        "this section's writer stores a page thread and none was sent. "
        "45-75 words tracing the line through this page's surfaces in "
        "render order, written last from what was actually produced. A "
        "page is not a container for surfaces; if the thread cannot be "
        "written, the surfaces are not yet a page.")]


#: What `detected` counts, and it is defined by SUBTRACTION for a reason.
#:
#: ABSENT is the one status that means "a slot was searched here and nothing
#: was found". Every other status — CONFIRMED, INFERRED, CLAIMED — is a slot
#: with something in it at a stated confidence, and the confidence is what the
#: row's own badge says. So detected = rows - absent.
#:
#: The first cut of this gate counted CONFIRMED and INFERRED only, which reads
#: defensibly and was still wrong: the frontend computes the same figure by
#: subtraction (live-adapter.jsx techLayersOf) and the frontend is what a
#: reader sees. Two definitions of one word on one page is the defect this
#: gate exists to refuse, so the gate takes the renderer's.
_UNDETECTED_STATUSES = frozenset({"ABSENT"})


def _check_rollup_agrees(section, body) -> list:
    """CG-24 — `layers[].detected` equals what items[] actually holds.

    Invariant 8: counts are computed, never stored where a source of truth
    exists, and `items` is the source of truth for `detected`. Measured
    2026-08-18: a register serving six named OPS products beside
    `detected: 0` on the OPS card, because four rows were appended after the
    rollup was written and nothing recomputed it. Both numbers passed every
    other gate; the page reads as an empty estate.

    The refusal states the arithmetic, per charter invariant 12: the layer,
    the figure sent, the figure computed, and which rows were counted.
    """
    if section != "techstack" or not isinstance(body, dict):
        return []
    layers, items = body.get("layers"), body.get("items")
    if not isinstance(layers, list) or not isinstance(items, list):
        return []
    counted = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        lay = str(it.get("layer") or "").strip().upper()
        if str(it.get("status") or "").strip().upper() not in _UNDETECTED_STATUSES:
            counted[lay] = counted.get(lay, 0) + 1
    out = []
    for i, lay in enumerate(layers):
        if not isinstance(lay, dict):
            continue
        name = str(lay.get("layer") or "").strip().upper()
        sent = lay.get("detected")
        if not isinstance(sent, int) or isinstance(sent, bool):
            continue
        got = counted.get(name, 0)
        if sent != got:
            rows = sum(1 for it in items
                       if isinstance(it, dict)
                       and str(it.get("layer") or "").strip().upper() == name)
            out.append(_reason(
                "CG-24", section, f"{section}.layers[{i}].detected",
                f"layer {name} sends detected={sent} and its own items[] "
                f"hold {got}: of the {rows} rows on this layer, {rows - got} "
                f"are ABSENT and the other {got} place something at a stated "
                f"confidence. Compute this figure from items[] at build time "
                f"rather than asserting it, or the two numbers on the card "
                f"drift apart the moment a row is added. `expected` is not "
                f"checked here: it is a judgement about the reference class, "
                f"not a count of these rows."))
    return out


def _check_vendor_is_a_company(section, fname, spec, val) -> list:
    if fname != "items" or section != "techstack":
        return []
    out = []
    for i, item in enumerate(val or []):
        if not isinstance(item, dict):
            continue
        vendor = str(item.get("vendor") or "").strip()
        product = str(item.get("product") or "").strip()
        if not vendor:
            continue
        low = vendor.lower()
        words = [w for w in re.split(r"[^a-z0-9]+", low) if w]
        if any(p in low for p in _CG20_PLACEHOLDER):
            out.append(_reason(
                "CG-20", section, f"{section}.{fname}[{i}].vendor",
                f"vendor {vendor!r} says it is a placeholder. A row whose "
                "vendor is not named is research that did not finish, and it "
                "renders on the client's register with the same weight as a "
                "confirmed deployment. Name the company, or drop the row and "
                "let the section's reach counters carry the gap"))
        elif words and all(w in _CG20_GENERIC for w in words):
            out.append(_reason(
                "CG-20", section, f"{section}.{fname}[{i}].vendor",
                f"vendor {vendor!r} is a CATEGORY, not a company. The "
                "contract is explicit — vendor and product are separate "
                "fields, and 'CRM' or 'Analytics/BI' is neither. Name the "
                "company that supplies it; if the run could not establish "
                "one, the row is not a register entry"))
        elif product and product.lower() == low:
            out.append(_reason(
                "CG-20", section, f"{section}.{fname}[{i}].product",
                f"product and vendor are both {vendor!r}. One of the two is "
                "unstated: a register row names a company AND the thing it "
                "supplies, and repeating the company in both fields renders "
                "as a product nobody sells"))
    return out


def _reason(gate, section, path, message):
    return {"gate_id": gate, "section": section, "path": path,
            "message": message, "severity": "block"}


# CG-21 — a serialisation that escaped into a payload leaf.
#
# Measured 2026-08-14: a promoted run carried
# `stairstep.ladder.steps[*].blocking_findings` as JSON-ENCODED STRINGS —
# `'{"f_id": "F-1", "e_ids": ["E-CC-139"]}'` where the contract says finding
# ids. The frontend printed each item straight into a chip, so the ladder
# showed literal JSON to the AE.
#
# CG-03 cannot see this and never will: it asks whether a list's items are
# the declared type, and a JSON-encoded object IS a valid string. The
# encoding is invisible to every type check in this module, which is exactly
# why it needs its own gate rather than a widening of an existing one.
#
# The predicate is deliberately narrow — a leaf that PARSES as a JSON object
# or array. Prose that merely mentions a brace does not parse; a stringified
# object always does. Anything that parses to a scalar (a bare number, a
# quoted word) is not a serialisation of a structure and is left alone.
def _looks_like_serialised_json(text: str) -> bool:
    s = text.strip()
    if len(s) < 2 or s[0] not in "{[":
        return False
    try:
        return isinstance(json.loads(s), (dict, list))
    except Exception:
        return False


def _check_serialised_leaves(section: str, node, path=None) -> list:
    """Walk every leaf of a section and refuse the ones that are JSON."""
    out = []
    path = path or section
    if isinstance(node, dict):
        for k, v in node.items():
            out.extend(_check_serialised_leaves(section, v, f"{path}.{k}"))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(_check_serialised_leaves(section, item, f"{path}[{i}]"))
    elif isinstance(node, str) and _looks_like_serialised_json(node):
        shape = "object" if node.strip()[0] == "{" else "array"
        out.append(_reason(
            "CG-21", section, path,
            f"this leaf is a JSON {shape} that has been SERIALISED into a "
            f"string: {node.strip()[:80]!r}. Send the value, not a "
            "serialisation of it — the serving path stores what it is given "
            "and the page renders it verbatim, so an encoded object reaches "
            "the client as literal JSON. If the contract asks for ids, send "
            "the ids; if it asks for objects, send objects and let CG-03 "
            "check their type"))
    return out


def _valid_empty_state(es) -> bool:
    return (isinstance(es, dict) and bool(es.get("reason"))
            and isinstance(es.get("sources_searched"), list)
            and len(es["sources_searched"]) > 0)


def _check_narrative_thread_is_per_section(page, payload) -> list:
    """CG-29 — the thread has to say what THIS section adds.

    MEASURED on the promoted overview of run d7ed1d90: ten of twelve sections
    carried the same `narrative_thread`, word for word. The field was present
    everywhere, so every presence check passed, and a reader moving between
    cards read the same paragraph ten times.

    That is the difference between a page thread PASTED and a story WOVEN, and
    it is invisible to any per-section gate: a duplicate is a relation BETWEEN
    sections, so it can only be seen once, over the whole page.

    Two sections may legitimately connect to the story in the same way. They
    may not say so in the same words: the field exists to tell a reader what
    the section in front of them adds, and a sentence that is true of ten
    sections tells them nothing about any.
    """
    if not isinstance(payload, dict):
        return []
    seen, out = {}, []
    for name in payload:
        body = payload.get(name)
        if not isinstance(body, dict):
            continue
        thread = body.get("narrative_thread")
        if not isinstance(thread, str) or not thread.strip():
            continue
        key = re.sub(r"\s+", " ", thread.strip().lower())
        first = seen.get(key)
        if first is None:
            seen[key] = name
            continue
        out.append(_reason(
            "CG-29", name, f"{page}.{name}.narrative_thread",
            f"the thread on {name!r} is word for word the thread on "
            f"{first!r}. A reader moving between these two cards reads the "
            "same paragraph twice, so neither one tells them what the "
            "section in front of them adds. Write what THIS section "
            "contributes to the argument; the page-level story belongs in "
            "the summary once."))
        if len(out) >= 6:
            break
    return out


def validate_pass1(page: str, payload: dict) -> list:
    if page not in PAGES:
        return [_reason("CG-01", None, page, f"unknown page {page!r}; pages are {list(PAGES)}")]
    if not isinstance(payload, dict):
        return [_reason("CG-03", None, page, "payload must be an object of sections")]

    reasons = []
    contract = sections(page)

    for name in payload:
        if name not in contract:
            reasons.append(_reason(
                "CG-04", name, name,
                f"section {name!r} is not in the {page} contract — payload "
                "shapes are law; call get_page_contract and re-shape"))

    for name, sec in contract.items():
        body = payload.get(name)
        if body is None:
            if sec.get("required", True):
                reasons.append(_reason(
                    "CG-01", name, name,
                    f"required section {name!r} missing — promotion requires "
                    "a passing submission on every required section"))
            continue
        if not isinstance(body, dict):
            reasons.append(_reason("CG-03", name, name,
                                   f"section {name!r} must be an object"))
            continue

        fields = sec["fields"]
        empty = body.get("empty_state")
        empty_declared = empty is not None
        if empty_declared and not _valid_empty_state(empty):
            reasons.append(_reason(
                "CG-06", name, f"{name}.empty_state",
                "an explicit empty state must name its reason and the "
                "sources_searched — an absence with no ladder is rejected"))

        for fname in body:
            if fname not in fields:
                reasons.append(_reason(
                    "CG-04", name, f"{name}.{fname}",
                    f"field {fname!r} is not in the {page}.{name} contract"))

        for fname, spec in fields.items():
            val = body.get(fname)
            if val is None:
                if spec["required"] and fname in ENVELOPE:
                    reasons.append(_reason(
                        "CG-05", name, f"{name}.{fname}",
                        f"envelope field {fname!r} is required on every "
                        "section, empty states included"))
                elif spec["required"] and not empty_declared:
                    reasons.append(_reason(
                        "CG-02", name, f"{name}.{fname}",
                        f"required field {fname!r} missing and no explicit "
                        "empty state declared"))
                continue
            # CG-19 — `required: true` was satisfied by an EMPTY list.
            #
            # `val = []` is not None, so the branch above never ran, and a
            # list type-checks fine. The empty list then wrote zero rows at
            # promotion, and the read path omits a key with no rows — so the
            # surface DISAPPEARED from the served page with no empty_state to
            # explain it, and every gate was green. Measured 2026-08-14 across
            # both promoted clients: exactly one content field each is empty
            # or absent without an empty state, and on the second client it is
            # `platform.starters.starters` — the conversation starters the
            # build owner reported as "disappeared".
            #
            # An empty list is a claim ("there are none") and it has to be
            # made deliberately: declare the section's empty_state with the
            # ladder, or mark the field `may_be_empty` in the contract where
            # emptiness is the ordinary case rather than a finding
            # (`techstack.dropped` — nothing was dropped — is the one such
            # field in the registry today).
            if (spec["type"] == "list" and spec["required"] and not val
                    and fname not in ENVELOPE and not empty_declared
                    and not spec.get("may_be_empty")):
                reasons.append(_reason(
                    "CG-19", name, f"{name}.{fname}",
                    f"required list {fname!r} is EMPTY and the section "
                    "declares no empty state. An empty list is not a quiet "
                    "pass: promotion writes no rows for it and the surface "
                    "vanishes from the page with nothing saying why. Either "
                    "send the items, or declare the section's empty_state "
                    "with the ladder that established the absence"))
                continue
            check = _TYPE_CHECK.get(spec["type"])
            if check and not check(val):
                reasons.append(_reason(
                    "CG-03", name, f"{name}.{fname}",
                    f"{fname!r} must be {spec['type']}, got "
                    f"{type(val).__name__}"))
                continue
            if spec["type"] == "list" and spec.get("item_type") in ("object", "string"):
                want = dict if spec["item_type"] == "object" else str
                for i, item in enumerate(val):
                    if not isinstance(item, want):
                        reasons.append(_reason(
                            "CG-03", name, f"{name}.{fname}[{i}]",
                            f"items of {fname!r} must be "
                            f"{spec['item_type']}s (the item schema is in "
                            "the field's doc text)"))
                        break
            reasons.extend(_check_must_present(name, fname, spec, val,
                                               empty_declared))
            reasons.extend(_check_vendor_is_a_company(name, fname, spec, val))

        reasons.extend(_check_page_thread(page, name, fields, body))
        reasons.extend(_check_rollup_agrees(name, body))
        reasons.extend(_check_cards_unique(name, body))
        reasons.extend(_check_why_now_is_an_event(name, body))
        reasons.extend(_check_thought_leadership_unique(name, body))
        reasons.extend(_check_no_bare_abbreviations(page, name, body))
        reasons.extend(_check_starter_tone(name, body))
        reasons.extend(_check_roster_keeps_uncontactable(name, body))
        reasons.extend(_check_resolved_contacts_are_served(name, body))
        reasons.extend(_check_thought_leadership_depth(name, body))
        reasons.extend(_check_financial_series_reach(name, body))
        reasons.extend(_check_no_typesetting_marks(name, body))
        reasons.extend(_check_source_label_is_a_citation(name, body))
        reasons.extend(_check_contact_routes_are_marked(name, body))

        # id-pattern discipline
        for i, e in enumerate(body.get("e_ids") or []):
            if isinstance(e, str) and not EID_TOKEN_RE.fullmatch(e.split(":")[0]):
                reasons.append(_reason(
                    "ET-03", name, f"{name}.e_ids[{i}]",
                    f"{e!r} is not an evidence id the recogniser accepts"))
        reasons.extend(_check_agent_ids(name, body))
        reasons.extend(_check_enum_fields(page, name, body))
        reasons.extend(_check_contract_vocabularies(page, name, body))
        reasons.extend(_check_date_fields(page, name, body))
        reasons.extend(_check_date_absence(page, name, body))
        reasons.extend(_check_sentence_case(name, body))
        reasons.extend(_check_face_budgets(page, name, body))
        reasons.extend(_check_payload_excerpts(name, body))
        reasons.extend(_check_serialised_leaves(name, body))

    # CG-15 runs once over the whole page: template repetition is a
    # relation BETWEEN a field's items, not a property of one value, so it
    # cannot be answered inside the per-section loop above.
    reasons.extend(check_vacuity(page, payload))
    # CG-29 for the same reason: a repeated thread is a relation BETWEEN
    # sections and cannot be seen from inside one.
    reasons.extend(_check_narrative_thread_is_per_section(page, payload))

    return reasons


# Payload fields whose promoted column is a Postgres enum. Generated from
# the live schema and the writer spec (scripts/gen_enum_fields.py), because
# a value the enum rejects is not a JSON-type error — it type-checks as a
# string and then aborts the promote transaction, which is the one place a
# failure must never surface. The first production promote of this
# connector died exactly there: prose written into an EVIDENCE│HYBRID│
# INFERRED chip.
_ENUM_FIELDS = None


def _enum_fields() -> dict:
    global _ENUM_FIELDS
    if _ENUM_FIELDS is None:
        try:
            _ENUM_FIELDS = json.loads(
                Path(__file__).with_name("enum_fields.json").read_text())["enum_fields"]
        except Exception:
            _ENUM_FIELDS = {}
    return _ENUM_FIELDS


def _at_path(body, path):
    """Yield (json_path, value) for a spec path, following `[*]` lists.

    Handles repeated `[*].` levels and dotted leaves, so a nested face
    field (`tiles[*].addressable_cells[*].feature_that_addresses_it`) and
    a nested object leaf (`validation_gate.grain_note`) are both
    addressable — a registry that could only reach one level deep would
    silently police nothing on the surfaces that nest.
    """
    head, sep, rest = path.partition("[*].")
    if not sep:
        node = body
        for part in head.split("."):
            if not isinstance(node, dict) or part not in node:
                return
            node = node[part]
        yield head, node
        return
    node = body
    for part in head.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    if isinstance(node, list):
        for i, item in enumerate(node):
            for sub, value in _at_path(item, rest):
                yield f"{head}[{i}].{sub}", value


def _check_date_fields(page: str, section: str, body) -> list:
    """A field promoted into a DATE column must resolve to one. Month and
    quarter precision are legitimate (the prompts ask for them) and resolve;
    anything else is rejected here rather than aborting the promote."""
    out = []
    spec = None
    try:
        spec = json.loads(
            Path(__file__).with_name("enum_fields.json").read_text()).get("date_fields", {})
    except Exception:
        return out
    for path in spec.get(f"{page}.{section}", ()):
        for jpath, value in _at_path(body, path):
            if resolve_date(value) is False:
                out.append(_reason(
                    "CG-09", section, f"{section}.{jpath}",
                    f"{str(value)[:40]!r} does not resolve to a date — this field is "
                    f"promoted into a DATE column and accepts {DATE_SHAPES}"))
    return out


# Fields whose promoted column is plain TEXT but whose CONTRACT states a closed
# vocabulary. The generated `enum_fields` registry only knows Postgres enums, so
# these were policed by nothing: a producer wrote a consequence SENTENCE into
# `context.timeline.events[*].signal`, the TEXT column accepted it, promotion
# succeeded, and the Positive/Neutral/Negative filters on D5 then matched zero
# events on a page with ten of them. A filter that silently matches nothing is
# worse than a failed submission, so the vocabulary is enforced here.
#
# Add a field only where the contract names the values. This is not a place to
# invent vocabulary — the contract's `doc` text is the source.
_CONTRACT_VOCABULARIES = {
    "context.timeline": {
        "events[*].signal": {
            "name": "signal",
            "values": ("POSITIVE", "NEUTRAL", "NEGATIVE"),
            "note": ("the event's direction for maturity, which the D5 timeline "
                     "clusters on. The consequence sentence belongs in "
                     "`maturity_effect`, not here"),
        },
        # Measured on a served run: 4 of 11 events carried a kind outside the
        # eight — TECHNOLOGY (x3) and CAPABILITY (x1). The column is plain TEXT
        # and nothing else looked, so those four events matched no D5 filter
        # and were invisible on a page that rendered them.
        "events[*].kind": {
            "name": "kind",
            "values": ("PLATFORM", "LEADERSHIP", "M&A", "REGULATORY",
                       "CHANNEL", "DATA", "SECURITY", "STRATEGY"),
            "note": ("the event's class, which D5 filters on. A near-miss "
                     "('TECHNOLOGY' for PLATFORM, 'CAPABILITY' for DATA) is "
                     "not a synonym — it is an event no filter can reach"),
        },
        # LEADING: the contract asks for the word "with one clause of
        # reasoning", so the served value is 'ADVANCED — the core is no longer
        # the constraint…'. An exact match here would have refused all eleven
        # events of a run that is doing exactly what it was asked.
        "events[*].maturity_effect": {
            "name": "maturity_effect",
            "values": ("ADVANCED", "CONSTRAINED", "NEUTRAL"),
            "leading": True,
            "note": ("the effect on today's assessed position, leading the "
                     "field; the clause of reasoning follows it"),
        },
        # Served value: 'strategy-first, substrate-later' — prose against a
        # five-word vocabulary, on a TEXT column with no enum behind it.
        "arc_shape": {
            "name": "arc_shape",
            "values": ("STEADY_INVESTMENT", "STOP_START", "POST_EVENT_CATCHUP",
                       "LEGACY_ANCHORED", "RECENT_ACCELERATION"),
            # leading, because the contract states the five "with one sentence
            # of evidence" — the badge must be one of them, what follows it is
            # the producer's own prose
            "leading": True,
            "note": ("the shape of the sequence, one of five, leading the "
                     "field. A coined phrase renders as an unrecognised badge; "
                     "the sentence of evidence follows the word"),
        },
    },
    # Per-item provenance, now that it HAS a column (0027). The vocabularies
    # differ per surface because the contract states different ones, which is
    # why the column is TEXT — so CG-09 is the only thing standing between a
    # coined value and a badge nobody can read.
    "platform.recommendations": {
        "recommendations[*].provenance": {
            "name": "provenance",
            "values": ("ANALYST", "DERIVED"),
            "note": ("how THIS recommendation was arrived at — required, never "
                     "blank. Distinct from the section envelope's provenance, "
                     "which says who produced the section"),
        },
    },
    "platform.starters": {
        "starters[*].provenance": {
            "name": "provenance",
            "values": ("TEMPLATE_FILL", "ANALYST"),
            "note": ("and RENDER it — a rule-composed starter labelled as "
                     "analyst work misrepresents how it was written"),
        },
    },
    "platform.roadmap": {
        "phases[*].provenance": {
            "name": "provenance",
            "values": ("analyst", "derived"),
            "note": ("if the package states the phasing use it and label it "
                     "analyst; derive only where it does not"),
        },
    },
    "techstack.techstack": {
        "items[*].status": {
            "name": "status",
            "values": ("CONFIRMED", "INFERRED", "CLAIMED", "ABSENT"),
            "note": "required per row; the register renders each state distinctly",
        },
    },
}


_LEADING_TOKEN = re.compile(r"^[A-Z][A-Z_]*")


# Vocabularies the CONTRACT declares in its own `doc` text, derived rather
# than copied. `_CONTRACT_VOCABULARIES` above is hand-written, and hand-
# written is how `context.timeline.arc_shape` — whose doc opens
# "STEADY_INVESTMENT|STOP_START|POST_EVENT_CATCHUP|LEGACY_ANCHORED|
# RECENT_ACCELERATION" — was never added to it. A promoted run served
# `'strategy-first, substrate-later'` there: a coined phrase in a
# five-value field, which is MEM-0010's exact class on the exact page
# CG-09 was built for, one field along.
#
# So the hand-written entries stay (they carry near-miss guidance and the
# `leading` rule, which no derivation can infer) and anything the contract
# declares and they do not is derived and policed automatically. A
# vocabulary added to the contract tomorrow is enforced tomorrow.
# Case-INSENSITIVE, because a vocabulary is not always shouted: the
# contract states `platform.roadmap.sequencing_basis` as
# "prerequisites|undetermined", and an uppercase-only expression let a
# 90-word paragraph sit in it on a promoted run. Found by the producer
# repairing that run, not by this gate.
_DOC_VOCAB = re.compile(
    r"^([A-Za-z][A-Za-z0-9_&/-]{1,30}(?:\|[A-Za-z][A-Za-z0-9_&/-]{1,30}){1,12})")
# …and a TYPE description is not a vocabulary. `context.regulatory_standing
# .charter_date` opens "date|null", which reads as a two-value enum to the
# expression above and would refuse every real date. Measured before
# landing the widening: it was the only false positive in the corpus, and
# it is the reason this list exists rather than a case fold alone.
_TYPE_WORDS = frozenset((
    "date", "datetime", "time", "null", "none", "string", "str", "text",
    "number", "numeric", "int", "integer", "float", "decimal", "bool",
    "boolean", "true", "false", "object", "dict", "list", "array", "any",
))
_DERIVED_VOCABULARIES = None


def _derived_vocabularies() -> dict:
    """{"page.section": {field: spec}} from the contract's own doc text."""
    global _DERIVED_VOCABULARIES
    if _DERIVED_VOCABULARIES is not None:
        return _DERIVED_VOCABULARIES
    out: dict = {}
    try:
        for page in PAGES:
            for sname, sec in sections(page).items():
                key = f"{page}.{sname}"
                hand = _CONTRACT_VOCABULARIES.get(key, {})
                for fname, spec in (sec.get("fields") or {}).items():
                    if fname in hand:
                        continue          # the hand-written entry wins
                    m = _DOC_VOCAB.match((spec.get("doc") or "").strip())
                    if not m:
                        continue
                    values = tuple(m.group(1).split("|"))
                    if any(v.lower() in _TYPE_WORDS for v in values):
                        continue          # a type description, not a vocabulary
                    out.setdefault(key, {})[fname] = {
                        "name": fname,
                        "values": values,
                        "note": ("the vocabulary is stated in this field's "
                                 "own contract doc, first line. A coined "
                                 "phrase in a fixed-vocabulary field renders, "
                                 "matches no filter, and is invisible to "
                                 "every surface that groups on it"),
                        # A vocabulary the contract states as a bare pipe list
                        # is exact: where a field legitimately takes the WORD
                        # then a clause, its hand-written entry says so.
                        "leading": False,
                    }
    except Exception:                     # noqa: BLE001 — derived, never fatal
        out = {}
    _DERIVED_VOCABULARIES = out
    return out


def _vocabularies(page: str, section: str) -> dict:
    key = f"{page}.{section}"
    return {**_derived_vocabularies().get(key, {}),
            **_CONTRACT_VOCABULARIES.get(key, {})}


def _check_contract_vocabularies(page: str, section: str, body) -> list:
    out = []
    for path, spec in _vocabularies(page, section).items():
        for jpath, value in _at_path(body, path):
            if value is None or value in spec["values"]:
                continue
            if spec.get("leading") and isinstance(value, str):
                # The contract asks for the WORD and then a clause. The badge
                # is the leading run of capitals; everything after it is the
                # producer's prose and none of this gate's business.
                m = _LEADING_TOKEN.match(value)
                if m and m.group(0) in spec["values"]:
                    continue
            shown = (value if isinstance(value, str) and len(value) <= 60
                     else f"{str(value)[:57]}…")
            out.append(_reason(
                "CG-09", section, f"{section}.{jpath}",
                f"{shown!r} is not a value of {spec['name']} — the contract "
                f"states {' │ '.join(spec['values'])}. {spec['note']}"))
    return out


def _check_enum_fields(page: str, section: str, body) -> list:
    out = []
    for path, spec in _enum_fields().get(f"{page}.{section}", {}).items():
        for jpath, value in _at_path(body, path):
            if value is None or value in spec["values"]:
                continue
            shown = value if isinstance(value, str) and len(value) <= 60 else f"{str(value)[:57]}…"
            out.append(_reason(
                "CG-09", section, f"{section}.{jpath}",
                f"{shown!r} is not a value of {spec['enum']} — this field is promoted "
                f"into an enum column and takes one of {' │ '.join(spec['values'])}"))
    return out


def _check_agent_ids(section, node, path=None) -> list:
    """Agent-created ids (five classes + authored rec_id) must match
    their patterns wherever they appear in the section tree."""
    out = []
    path = path or section
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}"
            if k in _AGENT_ID_KEYS and isinstance(v, str):
                if agent_id_class(v) != k:
                    out.append(_reason(
                        "ET-03", section, p,
                        f"{v!r} does not match the {k} pattern — the agent "
                        "creates exactly five id classes plus authored rec_id"))
            else:
                out.extend(_check_agent_ids(section, v, p))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(_check_agent_ids(section, item, f"{path}[{i}]"))
    return out


# ── CG-10 · a date that could not be established says so ──────────────
#
# The date that DATES an item on a surface: the timeline's x-position, the
# issue register's Gantt start, the signal's event date, the firmographic
# row's recency dot. A bare null in one of these does not render as "no
# date" — it renders as an EMPTY SLOT beside a populated row, which reads
# as undated when nobody looked and as undated when somebody looked and
# found nothing. Those are different facts and the surface cannot tell
# them apart, so the payload has to (invariant 9: undated evidence is
# UNVERIFIED, never current; a derived value is computed or null, never a
# default that looks like data).
#
# Registered here are the item-dating fields only. A SECOND date on the
# same item — `resolved_on` on an ACTIVE matter, `closed_on` on an
# ANNOUNCED merger, `appointed_on` where the source gives no start date —
# is legitimately null: the event has not happened, which is a fact about
# the world rather than a gap in the research. Refusing those would be
# refusing the truth.
_ITEM_DATING = {
    "context.timeline": ("events[*].event_date", "the timeline places the "
                         "event on an axis; an undated event has no position"),
    "context.issue_register": ("issues[*].opened_on", "the register orders on "
                               "opened_on and the Gantt draws from it"),
    "overview.why_now": ("signals[*].dated_on", "a why-now is an EVENT; the "
                         "contract drops an undated signal rather than "
                         "rendering one"),
    "overview.thought_leadership": ("entries[*].published_on", "the card "
                                    "prints the publication date beside the "
                                    "quote"),
    "overview.firmographics": ("fields[*].as_of", "the recency dot is computed "
                               "from as_of"),
    "overview.leadership": ("roster[*].as_of", "a name with no verification "
                            "date does not render — a stale executive is "
                            "worse than a gap"),
    "heatmap.evidence_age": ("rows[*].published_or_asof", "age_months and band "
                             "are computed from this date"),
}

# Values that RECORD non-establishment rather than assert a date. The
# ladder's own words, plus the evidence tier's UNVERIFIED and the
# evidence-age contract's own `undated` band.
_ABSENCE_RUNGS = frozenset((
    "UNVERIFIED", "UNWORKED", "WORKED_ABSENT", "NOT_RUN", "undated",
    "verified_absent", "verified_sparse", "cannot_estimate", "empty_state",
))
# Keys whose value may carry one of those rungs (an enum) or, for the
# `_reason`/`_note`/`_basis` forms, any non-empty sentence.
_RUNG_KEYS = ("recency_band", "recency_tag", "band", "date_basis",
              "dating_basis", "undated_reason", "date_absence")


def _records_absence(item: dict, field: str) -> bool:
    """True when the item states that the date was searched for and not
    established, rather than leaving a hole."""
    if not isinstance(item, dict):
        return False
    if item.get("quarantined") and item.get("quarantine_reason"):
        return True
    for key in (f"{field}_basis", f"{field}_absence", f"{field}_note",
                f"{field}_reason"):
        if str(item.get(key) or "").strip():
            return True
    for key in _RUNG_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip() in _ABSENCE_RUNGS:
            return True
    # the absence protocol's own record: what was searched, and with what
    for key in ("sources_searched", "queries_run"):
        if isinstance(item.get(key), list) and item[key]:
            return True
    return False


def _check_date_absence(page: str, section: str, body) -> list:
    out = []
    entry = _ITEM_DATING.get(f"{page}.{section}")
    if not entry or not isinstance(body, dict):
        return out
    path, why = entry
    container, _, field = path.partition("[*].")
    items = body.get(container)
    for i, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict):
            continue
        if item.get(field) is not None:
            continue
        if _records_absence(item, field):
            continue
        out.append(_reason(
            "CG-10", section, f"{section}.{container}[{i}].{field}",
            f"{field} is a bare null — {why}. A date nobody could establish "
            "is a finding and is recorded as one: carry the rung that says "
            f"so ({' │ '.join(sorted(_ABSENCE_RUNGS))} on {', '.join(_RUNG_KEYS)}, "
            "or the sources_searched ladder that established the absence), "
            "or state the date, or drop the row. What must not happen is an "
            "empty slot beside a populated one — the surface cannot tell "
            "'not looked for' from 'looked for and not found', so the "
            "payload has to"))
    return out


# ── CG-11 · prose begins as a sentence ────────────────────────────────
#
# Mechanical, and asked for by name: a field that renders as a line of
# prose on a client surface starts with a capital. The exception is a
# first word that carries an uppercase letter after its first character —
# nCino, iOS, eBay, iPhone — which is the vendor's own orthography and
# must survive untouched. Everything else that starts lowercase is a
# sentence that lost its opening capital somewhere between the draft and
# the payload.
#
# Scope is deliberately narrow enough to be right every time: a value is
# policed when its KEY is a prose key, or when the value ENDS in terminal
# punctuation (the producer wrote a sentence, so it is one). A noun-phrase
# fragment that renders inline after a label — a unit, a system reference,
# an id, a hostname, an enum — is none of those and is left alone, because
# capitalising a fragment mid-sentence is the same defect pointing the
# other way.
_PROSE_KEYS = frozenset((
    "body", "rationale", "story", "story_md", "text", "framing", "synthesis",
    "summary", "narrative", "narrative_thread", "consequence",
    "consequence_of_waiting", "cost_of_acting_now", "why_this_sequence",
    "trigger", "window", "detection_basis", "dma_impact", "so_what", "what",
    "why", "reason", "not_run_reason", "note", "grain_note", "currency_note",
    "reach_note", "detail", "statement", "pattern_statement", "headline",
    "relevance_note", "effect_note", "mix_implication", "strategic_alignment",
    "plain_label", "rejected_alternative", "implication", "clause",
    "limiting_absence", "description", "justification", "closure_condition",
    "quarantine_reason", "sequencing_basis", "sequencing_reason",
    "denominator_definition", "target_basis", "enrichment_basis",
    "proxy_disclosure", "maturity_effect", "empty_reason",
))
# Never touched: a verbatim span is a copy of what a document says, and
# editing its first letter to look tidier is the one thing evidence may
# never have done to it. Identifiers, hostnames and URLs are not prose.
_NEVER_SENTENCE = frozenset((
    "excerpt", "quote", "verbatim", "snippet", "url", "source_url",
    "linkedin_url", "producer_version", "source_domain", "domain", "email",
    "phone", "e_id", "source_name", "vendor", "product", "name", "field",
    "unit", "value", "kind", "layer", "status", "tier", "id",
))
_MIN_SENTENCE = 25
# nCino, iOS, eBay: an uppercase letter anywhere after the first character
# of the FIRST word. Their lowercase opener is the spelling, not a slip.
_CAMEL_FIRST_WORD = re.compile(r"^[a-z]+[A-Z]")


def _sentence_case_reason(path_key: str, value: str):
    """→ the offending first word, or None when the value is fine."""
    if not isinstance(value, str) or len(value) < _MIN_SENTENCE:
        return None
    if path_key in _NEVER_SENTENCE:
        return None
    if not re.search(r"\s", value):
        return None                      # a token, not a sentence
    text = value.strip().lstrip("\"'“‘([{")
    if not text or not text[0].isalpha() or not text[0].islower():
        return None
    ends_as_sentence = value.strip()[-1] in ".?!"
    if path_key not in _PROSE_KEYS and not ends_as_sentence:
        return None
    word = text.split()[0].strip(".,;:")
    if _CAMEL_FIRST_WORD.match(word):
        return None                      # nCino, iOS, eBay — the vendor's own
    return word


def _check_sentence_case(section: str, node, path=None, key=None) -> list:
    out = []
    path = path or section
    if isinstance(node, dict):
        for k, v in node.items():
            out.extend(_check_sentence_case(section, v, f"{path}.{k}", k))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(_check_sentence_case(section, item, f"{path}[{i}]", key))
    elif isinstance(node, str) and key:
        word = _sentence_case_reason(key, node)
        if word:
            out.append(_reason(
                "CG-11", section, path,
                f"begins {word!r} — a prose field on a client surface begins "
                f"with a capital. Write {word.capitalize()!r}. (A first word "
                "carrying an uppercase letter after its first character — "
                "nCino, iOS, eBay — is the vendor's own spelling and is "
                "exempt; this one is not.)"))
    return out


# ── CG-12 · a face field is a label, not a paragraph ──────────────────
#
# Two measured failures, one class. A 20-40-word `window` clause was
# rendered as a chip on the why-now card FACE and destroyed the strip's
# layout; a 150-character `detection_basis` was rendered as a badge in the
# tech register's right rail and overflowed every row. The renderer has
# since moved both to where prose belongs, and this is the other half of
# that repair: the payload keeps the face field inside the budget its own
# contract states, so the next surface that puts it on a face has a
# bounded string to put there.
#
# Each entry names the slot and where the long form lives, because the
# repair is never "cut words" — it is "move the argument to the field
# that renders it".
_FACE_BUDGETS = {
    "overview.why_now": (
        ("signals[*].window", {"max_words": 40, "min_words": 20},
         "the drilldown's Window row",
         "the closing EVENT and its date; the argument for acting belongs "
         "in consequence_of_waiting"),
        ("signals[*].trigger", {"max_words": 45, "min_words": 25},
         "the card face, cut at its first clause",
         "what changed, dated and cited; the reasoning belongs in "
         "why_this_sequence"),
    ),
    "techstack.techstack": (
        ("items[*].detection_basis", {"max_chars": 160, "max_sentences": 1},
         "the register row and the T3 detail header",
         "ONE CLAUSE saying how the product was placed in this estate; the "
         "explanation of what it bears on belongs in dma_impact (40-90 words)"),
    ),
    "insights.landscape": (
        ("tiles[*].detail", {"max_chars": 90},
         "the landscape tile's one-line detail",
         "the count's meaning in one line"),
    ),
    "heatmap.safeguard_gates": (
        ("gates[*].plain_label", {"min_words": 6, "max_words": 24},
         "the client-visible gate card",
         "a human sentence of 8-18 words; the mechanism belongs in "
         "what_it_checks"),
    ),
    "overview.opportunity": (
        ("tiles[*].addressable_cells[*].feature_that_addresses_it",
         {"max_chars": 80}, "the addressable-cell chip",
         "the feature's name, not its case"),
    ),
}


def _sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def _check_face_budgets(page: str, section: str, body) -> list:
    out = []
    for path, budget, slot, belongs in _FACE_BUDGETS.get(f"{page}.{section}", ()):
        for jpath, value in _at_path(body, path):
            if not isinstance(value, str) or not value.strip():
                continue
            words, chars = len(value.split()), len(value)
            over = None
            if "max_chars" in budget and chars > budget["max_chars"]:
                over = (f"{chars} characters against a budget of "
                        f"{budget['max_chars']}")
            elif "max_words" in budget and words > budget["max_words"]:
                over = f"{words} words against a budget of {budget['max_words']}"
            elif "max_sentences" in budget and \
                    _sentences(value) > budget["max_sentences"]:
                over = (f"{_sentences(value)} sentences where the contract "
                        f"states {budget['max_sentences']}")
            elif "min_words" in budget and words < budget["min_words"]:
                over = f"{words} words, under the stated floor of {budget['min_words']}"
            if over is None:
                continue
            out.append(_reason(
                "CG-12", section, f"{section}.{jpath}",
                f"renders in {slot} and carries {over}. This field holds "
                f"{belongs}. The repair is to MOVE the prose, not to trim it: "
                "a paragraph in a face slot overflows its container, and a "
                "20-40-word window clause put in a chip is what broke the "
                "why-now strip"))
    return out


# ── ET-04 (payload half) · an excerpt is a 50-500 char verbatim span ───
#
# The store enforces this at registration, but a payload may carry the
# excerpt itself (the run's evidence index renders it under every chip),
# and an empty or clipped one reaches the client as a citation with
# nothing behind it. Same floor either side of the boundary: 50 characters
# is the fail-closed minimum for a grounded excerpt, 500 the ceiling.
def _check_payload_excerpts(section: str, node, path=None, key=None) -> list:
    out = []
    path = path or section
    if isinstance(node, dict):
        for k, v in node.items():
            out.extend(_check_payload_excerpts(section, v, f"{path}.{k}", k))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(_check_payload_excerpts(section, item, f"{path}[{i}]", key))
    elif key == "excerpt":
        text = node if isinstance(node, str) else ""
        n = len(text.strip())
        if n == 0:
            out.append(_reason(
                "ET-04", section, path,
                "empty excerpt — a citation with no verbatim span is a "
                "reference, not evidence. Re-extract the 50-500 character "
                "span from the source; never compose one"))
        elif not (50 <= n <= 500):
            out.append(_reason(
                "ET-04", section, path,
                f"excerpt is {n} characters — a verbatim span is 50-500 "
                "(50 is the fail-closed floor for a grounded excerpt, above "
                "the 40-character linkable minimum). Widen the span in the "
                "source or cite a different passage; never pad it"))
    return out
