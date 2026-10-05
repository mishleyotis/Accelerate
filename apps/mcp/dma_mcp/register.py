"""register_evidence (stage 2.3b/2.5) — mint before you cite.

The server allocates the id and computes the rank score; sending either
is ignored. Idempotent by content: the dedup key is the hash of URL,
claim type and the normalised leading excerpt, scoped to the entity —
registering the same source from six surfaces returns the same id six
times, each call accumulating that surface's cell links.

Fail-closed rules enforced here:
- excerpt is a verbatim 50-500 char span, verified against the FETCHED
  artefact at registration (rejected here, not at promotion);
- an item with no traceable source URL is accepted as INFERENCE, never
  FACT (the coercion is reported, never silent);
- a FACT on a T3-T5 source is REFUSED (`fact_tier`), every origin: it is
  ET-10's rule, run at the door instead of at the submit of every page that
  cites the row — and the claim type is never rewritten to pass it;
- ERS = 0.35·Tier + 0.25·Recency + 0.20·Specificity + 0.20·Corroboration,
  every factor 1.0-5.0 (PRD "The evidence rank score"), bounded by CHECK;
- identity_ok is asserted only when a domain check actually ran —
  computed or null, never a default that looks like a pass;
- origin='connector' (owner decision 3, 0063) records tool, query and
  retrieval time, computes the tier from the tool (Indeed T3, CFPB T1) and
  verifies the excerpt against the STORED connector response, not a URL;
- a span SPLIT from an internal row (`split_of`, RC-08 / D-10) is a verbatim
  piece of the parent's excerpt, STRICTLY SHORTER than it — or, declared with
  `whole_row: true`, the WHOLE of it (owner decision 2026-10-05: a discovery
  row that is entirely a client statement is shared whole, as a NEW row) —
  and only a span carrying `customer_attribution` may ever reach a customer.
  The attribution is written only by the INSERT that mints the span — never
  onto an existing row, by any path (0063's trigger refuses it in the
  database too), and a span's dedup identity includes its lineage (0065) so
  a whole-row span is never folded into its parent.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone

from . import shared_path, source_rules

shared_path.ensure(__file__)

import excerpt_clip as clip  # noqa: E402  packages/shared/excerpt_clip.py

_MINT_LOCK = 815001          # advisory lock key for the E-CC mint counter

_HASH_SQL = r"""encode(digest(coalesce(%s,'') || '|' || coalesce(%s,'') || '|' ||
                lower(left(regexp_replace(%s,'\s+',' ','g'),500)),
         'sha256'),'hex')"""

_TIER_FACTOR = {"T1": 5.0, "T2": 4.0, "T3": 3.0, "T4": 2.0, "T5": 1.0}
_RECENCY_FACTOR = {"CURRENT": 5.0, "RECENT": 4.0, "DATED": 3.0,
                   "STALE": 2.0, "ARCHIVAL": 1.0, "UNVERIFIED": 1.0}
_CLAIMS = ("FACT", "INFERENCE", "HYPOTHESIS", "CEILING_ESTIMATE")
_TIERS = ("T1", "T2", "T3", "T4", "T5")
#: `evidence_origin_t`, in full (migration 0002). `internal` was unreachable
#: from any code path until AUD-0028; it is the label that makes a client's
#: own material storable AS internal instead of laundered as a weak public
#: claim, and audience redaction is what reads it.
_ORIGINS = ("package", "producer", "connector", "internal")

# ── Connector-origin evidence (owner decision 3, 2026-10-04; 0063) ────────
#
# A connector reading — the Indeed connector's employer rating, an
# aggregation of the CFPB complaint API — is a TOOL RESULT, not a page, so
# the URL fetch below cannot verify it. It was therefore either dropped (the
# SWBC sentiment card shipped one bar while two auditors pulled a 3.1/5
# Indeed rating and 213 CFPB complaints) or registered URL-less and demoted
# to INFERENCE: a measured reading laundered into a weak claim.
#
# Admitted now under origin 'connector' with its provenance recorded —
# tool, query, retrieval time — and the response STORED (connector_responses,
# content-addressed): the excerpt is verified verbatim against those stored
# bytes instead of a fetch, and can be re-verified later against the same
# bytes. The tier is COMPUTED from the tool, never taken from the producer:
#
#   family  matched in the tool name         tier  why
#   indeed  "indeed"                         T3    an employer-review
#                                                  aggregator: third-party,
#                                                  self-reported by staff
#   cfpb    "cfpb", "consumerfinance",       T1    the regulator's own
#           "consumer_complaint"                   official complaint data
#
# A tool in no family is REFUSED: a tier nobody decided is not a tier.
CONNECTOR_SOURCES = (
    ("indeed", ("indeed",), "T3"),
    ("cfpb", ("cfpb", "consumerfinance", "consumer_complaint",
              "consumer-complaint"), "T1"),
    # Owner decision 2026-10-05 ("split by data type"): one Clay or Vibe
    # Prospecting call returns two kinds of reading, so the tier follows the
    # KIND the producer declares in `connector.kind`, never the tool alone.
    # A technographic detection is a machine scan (T1 — and a row resting on
    # a scan alone is still INFERRED, never CONFIRMED); a modelled
    # firmographic (revenue band, LinkedIn-observed headcount and its growth)
    # is aggregated third-party data (T3, like Indeed).
    ("clay", ("clay",), {"technographic": "T1", "firmographic": "T3"}),
    ("vibe_prospecting", ("vibe_prospecting", "vibe-prospecting",
                          "vibe prospecting", "explorium"),
     {"technographic": "T1", "firmographic": "T3"}),
)
CONNECTOR_KINDS = ("technographic", "firmographic")
#: A stored response larger than this is refused: a connector result is a
#: record or an aggregate, not a corpus.
CONNECTOR_RESPONSE_MAX = 2_000_000
#: Clock skew allowed on `retrieved_at` before it is a future reading.
_RETRIEVED_SKEW = timedelta(days=1)


def connector_family(tool, kind=None) -> tuple[str, str | None] | None:
    """(family, computed tier) for a connector tool name, or None.

    For a family whose tier depends on the kind of reading, the tier is None
    until `kind` names one of CONNECTOR_KINDS."""
    name = re.sub(r"^mcp__", "", str(tool or "").strip().lower())
    for family, needles, tier in CONNECTOR_SOURCES:
        if any(n in name for n in needles):
            if isinstance(tier, dict):
                return family, tier.get(str(kind or "").strip().lower())
            return family, tier
    return None


def _parse_instant(value) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    elif isinstance(value, str) and value.strip():
        v = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(v)
        except ValueError:
            try:
                d = date.fromisoformat(v[:10])
            except ValueError:
                return None
            dt = datetime(d.year, d.month, d.day)
    else:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def connector_provenance(item: dict, now: datetime | None = None) -> dict:
    """Validate and normalise an item's `connector` block. Pure: no DB.

    Returns {errors, adjustments, tool, query, retrieved_at, tier, family,
    body, sha256}. `body` is None when the producer referenced an already
    stored response by `response_sha256` instead of resending it.
    """
    now = now or datetime.now(timezone.utc)
    c = item.get("connector")
    errors, adjustments = [], []
    if not isinstance(c, dict):
        return {"errors": ["connector: origin='connector' requires a "
                           "`connector` object {tool, query, retrieved_at, "
                           "response} — the provenance IS the evidence's "
                           "traceability, in place of a URL"],
                "adjustments": []}
    tool = str(c.get("tool") or "").strip()
    query = c.get("query")
    query = (json.dumps(query, sort_keys=True, ensure_ascii=False)
             if isinstance(query, (dict, list)) else str(query or "").strip())
    kind = str(c.get("kind") or "").strip().lower() or None
    fam = connector_family(tool, kind) if tool else None
    if fam is not None and fam[1] is None:
        errors.append(
            f"connector.kind: a {fam[0]} reading's tier follows what it "
            f"measured — send kind one of {', '.join(CONNECTOR_KINDS)} "
            "(technographic: a machine-scan detection, T1; firmographic: a "
            "modelled revenue, headcount or growth figure, T3 — owner "
            "decision 2026-10-05)")
    if not tool:
        errors.append("connector.tool: required — name the tool that was "
                      "called (e.g. Indeed get_company_data)")
    elif fam is None:
        errors.append(
            f"connector_tool_unregistered: {tool!r} has no tier rule. The "
            "owner admitted Indeed (T3) and the CFPB complaint API (T1) on "
            "2026-10-04 and Clay and Vibe Prospecting by kind on 2026-10-05; "
            "another connector needs its own decision before "
            "it can be evidence. Register the underlying public page "
            "instead, if one exists.")
    if not query:
        errors.append("connector.query: required — what the tool was asked "
                      "(company, filter, API query), so the reading can be "
                      "reproduced")
    retrieved = _parse_instant(c.get("retrieved_at"))
    if retrieved is None:
        errors.append("connector.retrieved_at: required, ISO-8601 — a "
                      "reading without its retrieval time cannot be dated")
    elif retrieved > now + _RETRIEVED_SKEW:
        errors.append(f"connector.retrieved_at: {retrieved.isoformat()} is "
                      "in the future")
    body = c.get("response")
    if isinstance(body, (dict, list)):
        body = json.dumps(body, ensure_ascii=False)
    body = body if isinstance(body, str) and body.strip() else None
    sha = str(c.get("response_sha256") or "").strip().lower() or None
    if body is not None:
        if len(body) > CONNECTOR_RESPONSE_MAX:
            errors.append(f"connector.response: {len(body):,} chars exceeds "
                          f"{CONNECTOR_RESPONSE_MAX:,}; store the record the "
                          "excerpt comes from, not the whole result set")
        computed = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if sha and sha != computed:
            errors.append("connector.response_sha256 does not match the "
                          "response sent; the hash is computed server-side")
        sha = computed
    elif not sha:
        errors.append("excerpt_unverifiable: origin='connector' needs the "
                      "connector's response (or the response_sha256 of one "
                      "already stored) to verify the excerpt against — an "
                      "unverified excerpt is not evidence")
    sent = str(item.get("tier") or "").upper() or None
    if fam and fam[1] and sent and sent != fam[1]:
        adjustments.append(
            f"tier {sent} ignored: the tier of a {fam[0]} connector reading "
            f"is computed, and it is {fam[1]} (owner decision "
            f"{'2026-10-05' if fam[0] in ('clay', 'vibe_prospecting') else '2026-10-04'})")
    return {"errors": errors, "adjustments": adjustments, "tool": tool,
            "query": query, "retrieved_at": retrieved, "body": body,
            "sha256": sha, "family": fam[0] if fam else None,
            "tier": fam[1] if fam else None}


# ── Split discovery spans (RC-08 / D-10, owner default 2026-10-04; 0063) ──
#
# A partly sensitive internal row (the SWBC discovery write-up: a client
# statement beside seller and personal remarks) used to be withheld whole,
# taking its shareable half with it — 24 customer drawers ended arguing over
# nothing. It is now SPLIT here: each span is a verbatim piece of the parent
# row's excerpt, registered against it (`split_of`); the shareable span also
# carries `customer_attribution`, the label a client reads it under ("Client
# statement, discovery conversations, September 2026"). The serve layer
# withholds every internal-origin row without an attribution.
#
# AN ATTRIBUTION IS MINTED, NEVER ADDED (adversarial review, 2026-10-04).
# The first cut accepted a "span" equal to the whole parent and UPDATEd the
# attribution onto the PARENT, and filled one in on whatever row a
# re-registration deduplicated to. `evidence_index` is shared by every run of
# the entity and read live by the api, so either write changed what customers
# saw on runs ALREADY PROMOTED — outside promotion (invariant 3), under an
# unchanged ETag, and irreversibly. So: a split is strictly shorter than its
# parent; the attribution goes on the row this call mints and nowhere else;
# a dedup onto a row whose lineage or attribution differs is REFUSED rather
# than reconciled.
#
# WHOLE-ROW SHARING (owner decision 2026-10-05). A discovery row that is
# ENTIRELY a client statement had no honest route: the strictly-shorter rule
# had a producer publish five such rows with only the closing full stop
# trimmed — the wording met, the intent not. Such a row is now shared WHOLE,
# by the same mechanism as any span: a NEW row, split_of the parent, carrying
# the parent's full excerpt (its stored bytes, not the producer's copy) and
# the attribution. The producer DECLARES it with `whole_row: true` — the
# whole row sent without the declaration is still refused, because on a row
# that carries a seller remark it is the leak the split exists to stop. The
# parent is never touched; the dedup key includes the lineage (0065), so
# the span is its own row and a retry of it is the idempotent dedup. The api, for its part, serves the span under its label
# only on a run promoted at or after the span was minted
# (apps/api evidence.attribution_bound), so even a new span changes nothing
# a customer reads until a payload citing it is promoted.
_ATTRIBUTION_MIN, _ATTRIBUTION_MAX = 12, 200
#: An attribution is the CLIENT's voice re-attributed to the client; one that
#: names the assessing firm or our own document is the internal label again.
_ATTRIBUTION_BAD = re.compile(
    r"\binternal\b|\bprepared for\b|\bour\b|\bwrite-?up\b|\bproposal\b",
    re.I)


def attribution_problem(text) -> str | None:
    """Why `text` cannot be a customer attribution, or None."""
    t = str(text or "").strip()
    if not (_ATTRIBUTION_MIN <= len(t) <= _ATTRIBUTION_MAX):
        return (f"customer_attribution: {len(t)} chars — a label of "
                f"{_ATTRIBUTION_MIN}-{_ATTRIBUTION_MAX} naming the client as "
                "the speaker and the occasion, e.g. 'Client statement, "
                "discovery conversations, September 2026'")
    vendor = os.environ.get("ASSESSING_VENDOR_NAME", "Zennify")
    if vendor and re.search(re.escape(vendor), t, re.I):
        return ("customer_attribution names the assessing firm; the shareable "
                "span is attributed to the CLIENT")
    bad = _ATTRIBUTION_BAD.search(t)
    if bad:
        return (f"customer_attribution reads as our internal document "
                f"({bad.group(0)!r}); attribute the statement to the client "
                "who made it")
    return None


def split_problem(parent, entity_id, excerpt: str,
                  whole_row: bool = False) -> str | None:
    """Why a span cannot be split from `parent` (e_id, entity_id, origin,
    excerpt), or None. Pure. `whole_row` is the producer's declaration that
    the parent is entirely the client's statement and is shared whole."""
    if parent is None:
        return ("split_of: the parent row does not exist — split a span from "
                "a registered internal row")
    _pid, p_entity, p_origin, p_excerpt = parent[:4]
    if str(p_entity) != str(entity_id):
        return "split_of_foreign: the parent row belongs to another entity"
    if str(p_origin or "").lower() != "internal":
        return ("split_of: only an internal-origin row is split; a public row "
                "is already shareable")
    span, whole = _normalise(excerpt), _normalise(p_excerpt or "")
    if span not in whole:
        return ("split_span_not_verbatim: a span is a verbatim piece of its "
                "parent's excerpt — re-attribution changes the LABEL, never "
                "the words")
    if whole_row:
        if span != whole:
            return ("split_whole_row_mismatch: whole_row is declared but the "
                    "excerpt is not the parent's whole excerpt. Send the "
                    "parent's full excerpt to share the row whole, or drop "
                    "whole_row to register a shorter span.")
        return None
    if len(span) >= len(whole):
        return ("split_span_whole_row: this span is the parent's whole "
                "excerpt. Sent as an ordinary split it is refused — on a row "
                "that carries a seller or personal remark it would publish "
                "every word, the remarks included. If the WHOLE row is the "
                "client's own statement, resend with whole_row: true (owner "
                "decision 2026-10-05); otherwise register the client's "
                "statement as its own, shorter span. Never trim a character "
                "to pass this check.")
    return None


def _recency_band(published: date | None, reference: date | None) -> str:
    if not published or not reference:
        return "UNVERIFIED"
    months = (reference.year - published.year) * 12 + (reference.month - published.month)
    if months <= 12:
        return "CURRENT"
    if months <= 24:
        return "RECENT"
    if months <= 36:
        return "DATED"
    if months <= 48:
        return "STALE"
    return "ARCHIVAL"


# The clip rule lives in `packages/shared/excerpt_clip.py` and is imported,
# not restated. It is enforced in TWO images — here at the door, where
# `register_evidence` refuses a clipped span, and in the worker's package
# parse, where the corpus arrives in the first place. A rule held in two
# places drifts (MEM-0193's whole defect class), and this one drifted while
# it was being written: the first pass knew only the width 140, so a package
# clipped at 150 would have walked past it. `clip_signature` there works the
# width out from the corpus; `clause_truncated` here is told it, because one
# string cannot reveal a spike.
#
# MEM-0129/MEM-0143 measured the width on t-rowe-price-group-inc: every one
# of 24 package-origin ids on the techstack page had clauses of EXACTLY 140
# characters, and the served heatmap carried 4,461 clauses of exactly 140
# against 281 of 139 out of 4,906 — the next most common length was 114,
# with 23. That distribution is not prose.
CLAUSE_CLIP_WIDTH = clip.CLAUSE_CLIP_WIDTH

#: Clauses are joined with this in package-origin rows.
_CLAUSE_SPLIT = clip.CLAUSE_SPLIT

#: The single-excerpt door check. Named here so the module reads as it did
#: before the rule moved, and so its tests keep pinning one entry point.
_clause_truncated = clip.clause_truncated


def _specificity(excerpt: str, facts: list) -> int:
    """Deterministic reading of the PRD ladder (quantified with method /
    quantified / specific-qualitative / general / vague). Digits mark a
    quantified claim; structured facts stand in for a stated method."""
    has_number = bool(re.search(r"\d", excerpt))
    if has_number and facts:
        return 5
    if has_number:
        return 4
    return 3 if len(excerpt) >= 80 else 2


def _corroboration(cur, entity_id, subcap_ids, source_domain, tier) -> int:
    """Distinct ORIGINS supporting the same cells. Two documents from one
    domain are one source. Single-source falls back to the tier rungs."""
    independents = 1
    if subcap_ids:
        cur.execute(
            """SELECT count(DISTINCT e.source_domain)
                 FROM evidence_index e
                 JOIN evidence_subcap_links l ON l.e_id = e.e_id
                WHERE e.entity_id = %s AND l.subcap_id = ANY(%s)
                  AND e.source_domain IS NOT NULL
                  AND e.source_domain IS DISTINCT FROM %s""",
            (entity_id, list(subcap_ids), source_domain))
        independents += cur.fetchone()[0]
    if independents >= 3:
        return 5
    if independents == 2:
        return 4
    return {"T1": 3, "T2": 3, "T3": 2}.get(tier, 1)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def date_merge(stored: date | None, incoming: date | None) -> str:
    """What a later registration may do to an already-stored date.

    Three cases and they are not the same, which is the whole point:

      fill          stored is unknown, incoming states one. Strictly
                    additive — unknown becoming known — so take it.
      keep          they agree, or the incoming one says nothing.
      contradiction they disagree. The stored date STANDS and the conflict
                    is reported. Two sources disagreeing about when a
                    document was published is a finding; letting the later
                    write win resolves it silently in favour of whichever
                    call happened to be second, which is not a resolution.

    A separate function because every test of this behaviour otherwise needs
    a live database, and `apps/mcp/tests` skips 53 tests for want of one —
    a test that always skips is a test that never runs.
    """
    if incoming is None:
        return "keep"
    if stored is None:
        return "fill"
    return "keep" if stored == incoming else "contradiction"


def register_evidence(conn, run_id, item: dict, fetch=None,
                      known_entity_domains=None) -> dict:
    """fetch(url) -> str|None is injectable (tests; and the worker image
    may route through a proxy). known_entity_domains enables the domain
    identity check; absent, identity_ok stays NULL — unknown, not ok."""
    cur = conn.cursor()
    cur.execute("""SELECT r.entity_id, r.completed_at
                     FROM runs r WHERE r.id = %s""", (run_id,))
    row = cur.fetchone()
    if row is None:
        return {"e_id": None, "deduped": False, "ers": None,
                "errors": ["unknown_run"]}
    entity_id, completed_at = row
    reference_date = completed_at if isinstance(completed_at, date) else None

    errors, adjustments = [], []
    excerpt = str(item.get("excerpt") or "")
    source_url = item.get("source_url") or None
    claim = str(item.get("claim_type") or "").upper() or None
    tier = str(item.get("tier") or "").upper() or None
    # AUD-0028: the INSERT hardcoded 'producer', so `evidence_origin_t`'s
    # `internal` label could never be set by any code path — migration 0045
    # records that no row has ever carried it. An origin that cannot be
    # written is not an enum member, it is a comment.
    origin = str(item.get("origin") or "producer").lower()
    if origin not in _ORIGINS:
        errors.append(f"origin: {origin!r} not in {_ORIGINS}")

    # Decision 3: a connector reading's tier is COMPUTED from its tool.
    prov = None
    if origin == "connector":
        prov = connector_provenance(item)
        errors += prov["errors"]
        adjustments += prov["adjustments"]
        if prov.get("tier"):
            tier = prov["tier"]
    elif item.get("connector") is not None:
        errors.append(f"connector: provenance was sent but origin is "
                      f"{origin!r}; a connector reading registers with "
                      "origin='connector'")

    # RC-08 / D-10: a span split from an internal row.
    split_of = str(item.get("split_of") or "").strip() or None
    attribution = item.get("customer_attribution")
    attribution = (attribution.strip() if isinstance(attribution, str)
                   and attribution.strip() else None)
    whole_row = item.get("whole_row") is True
    parent = None
    if attribution and not split_of:
        errors.append("customer_attribution: only a span SPLIT from an "
                      "internal row carries one — send split_of with it")
    if whole_row and not split_of:
        errors.append("whole_row: declares a span that is its parent's whole "
                      "excerpt — send split_of=<the parent> with it")
    elif whole_row and not attribution:
        errors.append("whole_row: a whole-row span exists to be shared — "
                      "send its customer_attribution. Without one it is the "
                      "parent again under a second id, never served")
    if split_of:
        if origin != "internal":
            errors.append("split_of: a split span is internal material; "
                          "register it with origin='internal'")
        cur.execute(
            """SELECT e_id, entity_id, origin::text, excerpt,
                      claim_type::text, tier::text, published_date,
                      source_name
                 FROM evidence_index WHERE e_id = %s""", (split_of,))
        parent = cur.fetchone()
        bad = split_problem(parent, entity_id, excerpt, whole_row=whole_row)
        if bad:
            errors.append(bad)
        elif parent is not None:
            if whole_row:
                # The span IS the parent's text: store the parent's own
                # bytes, never the producer's re-spaced or re-cased copy.
                excerpt = parent[3]
            # A span inherits what the producer did not restate: it is a
            # piece of the same document.
            claim = claim or (parent[4] or None)
            tier = tier or (parent[5] or None)
            if not item.get("published_date") and parent[6] is not None:
                item = {**item, "published_date": parent[6]}
            if not item.get("source_name"):
                item = {**item, "source_name": parent[7]}
    if attribution:
        bad = attribution_problem(attribution)
        if bad:
            errors.append(bad)

    if not (50 <= len(excerpt) <= 500):
        errors.append(f"excerpt_length: {len(excerpt)} chars — a verbatim "
                      "span of 50-500 is required")
    clipped = _clause_truncated(excerpt)
    if clipped:
        errors.append(clipped)
    if claim not in _CLAIMS:
        errors.append(f"claim_type: {claim!r} not in {_CLAIMS}")
    if tier not in _TIERS:
        errors.append(f"tier: {tier!r} not in {_TIERS}")
    # W6 — what a source may be used to ESTABLISH, checked where the source
    # is named rather than left to the producer's typing. Both refusals are
    # about the source's own nature, so they belong beside the tier and
    # claim vocabulary checks and before anything is fetched or minted.
    tier_bad = source_rules.tier_violation(source_url, tier)
    if tier_bad:
        errors.append(tier_bad)
    # The same check running the other way. `tier_violation` catches a weak
    # source claimed strong; this catches a STRONG source filed weak, which
    # is the failure nobody looks for because it does not read like a defect
    # — it reads like a thin client. MEM-0087.
    scan_bad = source_rules.scan_tier_violation(
        item.get("source_name"), tier, item.get("origin"))
    if scan_bad:
        errors.append(scan_bad)
    absence_bad = source_rules.absence_as_capability(excerpt, claim)
    if absence_bad:
        errors.append(absence_bad)
    if errors:
        out = {"e_id": None, "deduped": False, "ers": None, "errors": errors}
        if adjustments:
            out["adjustments"] = adjustments
        return out

    # AUD-0029: a URL-less FACT used to be SILENTLY DEMOTED to INFERENCE,
    # whatever it was. That is right for an unsourced public claim and wrong
    # for an internal one: a client's own board pack is not weaker evidence
    # than a press release, it is evidence of a different KIND, and demoting
    # it hides the fact that internal material entered the run at all.
    #
    # So the two are separated. An internal source keeps its claim type and
    # is LABELLED; an unsourced public claim is still demoted, and now says
    # that internal registration was the alternative it did not take.
    if not source_url and claim == "FACT":
        if origin == "connector":
            # Reached only by a T1/T2 family (CFPB): a T3 reading's FACT is
            # refused below, by ET-10's own rule.
            adjustments.append(
                "connector reading with no public URL: claim_type FACT KEPT — "
                f"its trace is the stored {prov['family']} response "
                f"({prov['sha256'][:12]}…), the tool and the query, and the "
                "excerpt is verified against those bytes.")
        elif origin == "internal":
            adjustments.append(
                "internal source with no public URL: claim_type FACT KEPT "
                "and origin recorded as internal. It is redacted from every "
                "customer projection and never counts toward public "
                "corroboration.")
        else:
            claim = "INFERENCE"
            adjustments.append(
                "no traceable source URL: claim_type FACT downgraded to "
                "INFERENCE. If this IS internal material, register it with "
                "origin='internal' and it keeps its claim type and is "
                "labelled, rather than being laundered into a weak public "
                "claim.")

    # ET-10 AT THE DOOR — a FACT rests on a T1 or T2 source.
    #
    # The submit gate (validation2._check_fact_tier, gate code "ET-10")
    # refuses every cited row labelled FACT whose tier is outside FACT_TIERS,
    # whatever its origin. Registration used to keep FACT on a connector
    # reading unconditionally ("claim_type FACT KEPT" above), so every Indeed
    # reading — T3, computed from the tool — minted cleanly and then failed
    # the submit of every page that cited it: a row that can never be cited
    # is not evidence, it is a trap. So the same rule runs here, on the
    # claim and tier as they would be STORED (after the tier is computed for
    # a connector, inherited for a split span, and after the reported
    # URL-less demotion above), for EVERY origin — ET-10 reads no origin, so
    # a connector-only check would leave the same trap open for an internal
    # or producer row. The claim type is never rewritten to pass: the
    # producer decides between INFERENCE and a T1/T2 source.
    from .validation2 import FACT_TIERS
    if claim == "FACT" and tier not in FACT_TIERS:
        out = {"e_id": None, "deduped": False, "ers": None, "errors": [
            f"fact_tier: claim_type FACT on a {tier} source — ET-10 (a FACT "
            f"rests on a {' or '.join(FACT_TIERS)} source) refuses every "
            "cited FACT row on T3-T5 at submit, so it is refused here rather "
            "than minted uncitable. Register it as INFERENCE (or HYPOTHESIS "
            "/ CEILING_ESTIMATE)"
            + (f"; a {prov['family']} connector reading is {tier} by the "
               "tool, so it is never a FACT" if prov and prov.get("family")
               else ", or cite the T1/T2 source that states it")
            + ". The claim type is not rewritten for you."]}
        if adjustments:
            out["adjustments"] = adjustments
        return out

    # Verbatim verification — fail closed. A connector reading is verified
    # against its STORED response, never a URL fetch (decision 3): the tool
    # result is the artefact, and a URL beside it (the CFPB API query) may
    # answer differently tomorrow.
    if origin == "connector":
        body = prov["body"]
        if body is None:
            cur.execute("""SELECT body FROM connector_responses
                            WHERE sha256 = %s AND entity_id = %s""",
                        (prov["sha256"], entity_id))
            got = cur.fetchone()
            if got is None:
                return {"e_id": None, "deduped": False, "ers": None,
                        "errors": ["excerpt_unverifiable: no stored connector "
                                   f"response {prov['sha256']} for this "
                                   "entity — send the response itself"]}
            body = got[0]
        if _normalise(excerpt) not in _normalise(body):
            return {"e_id": None, "deduped": False, "ers": None,
                    "errors": ["excerpt_not_verbatim: the span is not in the "
                               "connector's response — quote the response "
                               "byte-for-byte; never summarise a tool result "
                               "and call it an excerpt"]}
    elif source_url:
        if fetch is None:
            return {"e_id": None, "deduped": False, "ers": None,
                    "errors": ["excerpt_unverifiable: no fetcher available; "
                               "an unverified excerpt is not evidence"]}
        fetched = fetch(source_url)
        if fetched is None:
            # SAY WHY. `url_unreachable` alone covered a DNS failure, a TLS
            # error, a 403 from a bot filter, a 404 and a timeout, and each of
            # those calls for a DIFFERENT next move — find another source,
            # correct the URL, retry. MEM-0072 stayed an open BLOCKER through
            # two clients because the one word could not distinguish "this
            # firm's site refuses robots" from "this firm has no site", and
            # the second reads as evidence about the firm while the first is
            # evidence about nothing.
            why = getattr(fetch, "last_error", None)
            return {"e_id": None, "deduped": False, "ers": None,
                    "errors": [f"url_unreachable: {source_url}"
                               + (f" — {why}" if why else "")]}
        if _normalise(excerpt) not in _normalise(fetched):
            return {"e_id": None, "deduped": False, "ers": None,
                    "errors": ["excerpt_not_verbatim: the span is not in the "
                               "fetched artefact — re-extract from the "
                               "source; never repair by hand"]}

    # Domain identity — asserted only when a check actually ran.
    domain = None
    if source_url:
        m = re.match(r"^[A-Za-z]+://(?:www\.)?([^/:?#]+)", source_url)
        domain = m.group(1).lower() if m else None
    # identity_ok=True only for the entity's OWN domains; a third-party
    # domain stays NULL here (not yet resolved against the registry the
    # identity gate holds — validation pass 2). Never asserted by default.
    identity_ok, identity_note = None, None
    if domain and known_entity_domains and domain in {d.lower() for d in known_entity_domains}:
        identity_ok = True
        identity_note = "entity's own domain"
    # A document about a RELATED entity is noted, never refused: a filing
    # saying A is wholly owned by B is the right evidence for ownership and
    # the wrong evidence for B's operational capability. The note is what
    # lets a reader see which one this is (W6).
    relation = source_rules.relation_note(excerpt)
    if relation:
        identity_note = f"{identity_note}; {relation}" if identity_note else relation
        adjustments.append(relation)
    subcaps = [s for s in (item.get("linked_subcap_ids") or []) if s]
    if split_of and parent is not None and not subcaps and not errors:
        # A span is a piece of its parent's document, so it bears on the
        # parent's cells unless the producer says otherwise. Minted bare, a
        # whole-row span was an orphan every cell-grain section refused
        # (ET-07 on insights and the roadmap, SWBC 2026-10-05, MEM-0079).
        # Sending linked_subcap_ids narrows it; sending none inherits.
        cur.execute(
            """SELECT DISTINCT subcap_id FROM evidence_subcap_links
                WHERE e_id = %s AND run_id = %s ORDER BY subcap_id""",
            (split_of, run_id))
        subcaps = [r[0] for r in cur.fetchall()]
        if subcaps:
            adjustments.append(
                f"linked_subcap_ids inherited from {split_of} "
                f"({len(subcaps)} cell(s)); send linked_subcap_ids to narrow "
                "them")

    published = item.get("published_date")
    if isinstance(published, str):
        try:
            published = date.fromisoformat(published[:10])
        except ValueError:
            published = None
            adjustments.append("published_date unparseable: stored as "
                               "undated (UNVERIFIED, never current)")
    if origin == "connector" and published is None:
        # A live aggregate (a rating, a complaint count) is AS OF the moment
        # it was read: the retrieval date is its date, not a default.
        published = prov["retrieved_at"].date()
        adjustments.append(
            f"connector reading dated by its retrieval, "
            f"{published.isoformat()}: a live aggregate is as of the read")

    band = _recency_band(published, reference_date)
    spec = _specificity(excerpt, item.get("facts") or [])
    corr = _corroboration(cur, entity_id, subcaps, domain, tier)
    ers = round(0.35 * _TIER_FACTOR[tier] + 0.25 * _RECENCY_FACTOR[band]
                + 0.20 * spec + 0.20 * corr, 2)

    # Mint under an advisory lock so concurrent sessions never race the
    # counter (svc_mcp runs on session-mode pooling).
    cur.execute("SELECT pg_advisory_xact_lock(%s)", (_MINT_LOCK,))
    cur.execute("""SELECT COALESCE(MAX(substring(e_id FROM 'E-CC-(\\d+)')::int), 0) + 1
                     FROM evidence_index WHERE e_id LIKE 'E-CC-%%'""")
    e_id = f"E-CC-{cur.fetchone()[0]:03d}"

    if prov is not None and prov["body"] is not None:
        # Content-addressed: the same response stored once, whichever span
        # of it is registered first (0063).
        cur.execute(
            """INSERT INTO connector_responses
                  (sha256, entity_id, tool, query, retrieved_at, body)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (sha256) DO NOTHING""",
            (prov["sha256"], entity_id, prov["tool"], prov["query"],
             prov["retrieved_at"], prov["body"]))

    cur.execute(
        f"""INSERT INTO evidence_index
              (e_id, entity_id, origin, source_name, source_url, excerpt,
               claim_type, tier, published_date, reference_date,
               specificity, corroboration, identity_ok, identity_note, ers,
               connector_tool, connector_query, connector_retrieved_at,
               connector_response_sha256, customer_attribution, split_of)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING RETURNING e_id""",
        (e_id, entity_id, origin, item.get("source_name"), source_url, excerpt,
         claim, tier, published, reference_date, spec, corr,
         identity_ok, identity_note, ers,
         prov["tool"] if prov else None, prov["query"] if prov else None,
         prov["retrieved_at"] if prov else None,
         prov["sha256"] if prov else None, attribution, split_of))
    minted = cur.fetchone()
    if minted:
        kept_id, deduped, ers_out = e_id, False, ers
    else:
        # the entity-scoped content hash fired: same URL+claim+span, and the
        # same lineage — 0065's key includes split_of, so a whole-row span
        # is never answered with its parent, nor the parent with the span.
        cur.execute(
            f"""SELECT e_id FROM evidence_index
                 WHERE entity_id = %s AND content_hash = {_HASH_SQL}
                   AND coalesce(split_of, '') = coalesce(%s, '')""",
            (entity_id, source_url, claim, excerpt, split_of))
        kept_id = cur.fetchone()[0]
        deduped, ers_out = True, None
        # NEVER RECONCILED BY A WRITE. The same words are already a row; if
        # that row's customer label or lineage is not the one asked for, the
        # call is refused — an attribution is never added to, changed on or
        # taken from a row that exists, because every run citing the row
        # would change with it (RC-08 review, 2026-10-04). Identical is the
        # idempotent retry and returns the row.
        cur.execute("""SELECT customer_attribution, split_of
                         FROM evidence_index WHERE e_id = %s""", (kept_id,))
        have_attr, have_split = cur.fetchone()
        have_attr = have_attr or None
        if have_attr != attribution or (
                split_of is not None and have_split != split_of):
            conn.rollback()
            have = (f"under the customer attribution {have_attr!r}"
                    if have_attr else "with no customer attribution "
                    "(never served to a customer)")
            return {"e_id": None, "deduped": False, "ers": None,
                    "errors": [
                        f"split_span_exists: these words are already "
                        f"registered as {kept_id}, {have}"
                        + (f", split from {have_split}" if have_split else "")
                        + ". An attribution is set only when a span is "
                        "minted, and is never added to, changed on or taken "
                        f"from an existing row. Cite {kept_id} as it stands, "
                        "or split a different span."]}
        cur.execute(
            f"""INSERT INTO evidence_dedup_audit
                  (e_id, content_hash, branch, matched_e_id, occurred_at)
                VALUES (NULL, {_HASH_SQL}, 'dedup_same_entity', %s, now())""",
            (source_url, claim, excerpt, kept_id))

        # A DATE THE FIRST REGISTRATION LACKED, arriving on a later one.
        #
        # Measured 2026-08-15 on the second client. A producer registered
        # three spans from a Client Agreement before it had established the
        # document's date, then re-registered them with published_date set.
        # Dedup fired, `linked_subcap_ids` MERGED — a new cell was genuinely
        # added to E-CC-178 — and `published_date` stayed null. The merge was
        # partial, on one field and not the other, which is the defect: an
        # item first registered undated could never afterwards be dated, so
        # it sat at UNVERIFIED forever and its ERS stayed suppressed (3.40
        # undated against 4.15 dated, on comparable spans from one document).
        #
        # Filling it is strictly additive — unknown becoming known. What is
        # NOT done here is overwriting a date the row already carries with a
        # different one: two sources disagreeing about when a document was
        # published is a contradiction, and the rule for a contradiction is
        # to state it, never to resolve it silently by taking the newer
        # write. So the three cases are separated and the third is reported.
        if published:
            cur.execute("SELECT published_date FROM evidence_index "
                        "WHERE e_id = %s", (kept_id,))
            stored = cur.fetchone()[0]
            verdict = date_merge(stored, published)
            if verdict == "fill":
                # Recompute ERS: recency is 25% of it, and a row left at
                # UNVERIFIED scores as though nobody had ever dated it.
                new_band = _recency_band(published, reference_date)
                cur.execute(
                    """UPDATE evidence_index
                          SET published_date = %s,
                              ers = round((0.35 * %s + 0.25 * %s
                                         + 0.20 * specificity
                                         + 0.20 * corroboration)::numeric, 2)
                        WHERE e_id = %s
                    RETURNING ers""",
                    (published, _TIER_FACTOR[tier], _RECENCY_FACTOR[new_band],
                     kept_id))
                ers_out = float(cur.fetchone()[0])
                adjustments.append(
                    f"{kept_id} was registered undated and is now dated "
                    f"{published.isoformat()}: recency {new_band}, ERS "
                    f"recomputed to {ers_out}")
            elif verdict == "contradiction":
                adjustments.append(
                    f"CONTRADICTION not resolved: {kept_id} is stored as "
                    f"published {stored.isoformat()} and this registration "
                    f"says {published.isoformat()}. The stored date stands. "
                    "One of the two readings is wrong and which one is a "
                    "finding — establish it from the document rather than "
                    "letting the later write win.")

    # The per-DOCUMENT sole-evidence cap (W6). Checked here, after the mint,
    # because the refusal is about the LINKS and not the registration: the
    # id is minted and its excerpt stored either way, so a producer never
    # loses a verified span to this rule — it loses the further cells the
    # document would have become the only voice for. A per-evidence-id cap
    # was refuted in the adversarial pass by splitting one filing into eight
    # ids sharing one URL, so the key is the canonicalised document.
    reach_bad = source_rules.sole_evidence_reach(cur, run_id, kept_id,
                                                source_url, subcaps)
    if reach_bad:
        conn.commit()                     # keep the mint; refuse the links
        return {"e_id": kept_id, "deduped": deduped, "ers": ers_out,
                "errors": [reach_bad],
                "links_written": 0,
                "adjustments": adjustments or []}
    for sid in subcaps:
        cur.execute(
            """INSERT INTO evidence_subcap_links (e_id, subcap_id, run_id, link_basis)
               VALUES (%s,%s,%s,'registered') ON CONFLICT DO NOTHING""",
            (kept_id, sid, run_id))
    conn.commit()
    out = {"e_id": kept_id, "deduped": deduped, "ers": ers_out, "errors": []}
    if adjustments:
        out["adjustments"] = adjustments
    return out
