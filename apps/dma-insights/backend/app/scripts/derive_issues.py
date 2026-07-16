"""Issue-register derive — grounded, no empty states (2026-06).

The D5 Context "Issue register" renders empty for any ACTIVE entity whose
package shipped no parseable ``issue_register`` artifact. 30/94 entities were
empty: some packages ship the register under a name/location the ingest missed
(CamelCase ``*IssueRegister*.csv``, ``issue_register_L2.csv``,
``A5_Issues_Register.csv`` in 01_evidence); others genuinely recorded no
governance issues.

This pass fills every empty-or-junk register WITHOUT fabricating:

  0. QUARANTINE (2026-07-06 production fix) — some packages' registers are
     the DMA bot's OWN pipeline-QA log, not client issues: rows keyed on
     artifact FILE NAMES ("caps_applied_log.csv absent as standalone CSV
     file…", "contradiction_log.csv absent…", schema-contract drift). The
     Context page rendered those file names as the client's issue register
     (entity interactive-brokers-grou-0001). ``_META_TITLE_RE`` and
     ``is_pipeline_artifact_issue`` classify them; persisted pipeline/meta
     rows are RECLASSIFIED to kind='assessment_qa' (preserved as
     Health-page material — the context router excludes assessment_qa),
     never deleted, so the register carries issues with a digital-maturity
     impact instead of build artifacts.

  1. MINE — sweep the entity's package for any issue-register artifact, parse
     it with the canonical ``parse_issue_register_csv`` (case-insensitive,
     plural-tolerant, header-classified, alias-aware for the BOK
     ``ISS_ID``/``Finding`` and Chemung ``description`` headers). Real
     analyst-recorded CLIENT issues win (written kind='client'); rows are
     filtered PER ROW by ``is_pipeline_artifact_issue`` — finer than the
     header-level kind alone, it drops pipeline-QA rows that leak into a
     client-classified file AND rescues genuine client issues that ship
     inside a governance-classified checklist.

  2. HONESTLY EMPTY (plan S14 / user directive, 2026-07-08) — capability
     gaps are NOT issues. The register lists only REAL report-noted issues
     (litigation, enforcement actions, incidents, concentration events,
     self-disclosed risks); capability gaps belong on the heatmap / focus
     surfaces. A client with no mined real issues keeps an honestly-empty
     register (the frontend renders a clean-posture empty state), and any
     "Capability gap: …" rows a prior derive synthesized are purged.

  3. ENFORCEMENT DETAIL (2026-07-06 production fix) — the D5 "Regulatory
     standing" card drills an OPEN regulatory issue into IssueDetail; the
     audit found those drilldowns carrying a bare title with the rationale
     duplicating it and no evidence anchor. For every regulatory/compliance
     issue row whose rationale carries no evidence citation, this pass finds
     the entity's OWN enforcement evidence (excerpt naming the same action)
     and appends the VERBATIM excerpt + its E-ID; empty ``linked_subcap_ids``
     inherit the evidence row's subcaps so the drilldown links pillar
     attribution too. Quotes are verbatim (``nlp.segment.clip_quote``):
     truncation lands on a sentence/word boundary with an ellipsis, never
     mid-claim. Skips rows already citing evidence → idempotent.

  4. CE-VERIFY LINKS (2026-07-09 NLP hardening) — cross-encoder-verify every
     client issue's ``linked_subcap_ids`` against the issue's own text and
     prune semantically-unsupported links (``_verify_subcap_links``).

Quality gate (2026-07-06, replaces the zero-rows gate): a run re-derives when
it has NO quality client row — i.e. every existing row is blank-titled,
kind='assessment_qa', or title-classified as assessment-QA meta ("Missing
governance artifact: caps_applied_log.csv"). Junk kind='client' rows (blank
or meta-titled) are DELETED before the mined rows land, so the very rows that
used to block this backfill (Wescom's 3 governance filename rows, Bank of
Utah's 4 blank titles) now trigger it. Rows properly kinded 'assessment_qa'
by ingest are kept (Health-page material). Idempotent: a run with ≥1 quality
client row is never touched.

Usage: DATABASE_URL=... [DMA_SEED_CORPUS_DIR=...] python -m app.scripts.derive_issues
"""
from __future__ import annotations

import asyncio
import glob
import os
import re
import sys

from sqlalchemy import text

from app.database import get_sessionmaker

_CORPUS = (os.environ.get("DMA_ISSUES_CORPUS_DIR")
           or os.environ.get("DMA_SEED_CORPUS_DIR")
           or "tests/fixtures/dma_packages_batches")

_CANON = ("01_evidence", "00_entity_profile", "01_Research", "07_governance")

# Verbatim port of qa_deploy_review_audit._META_ISSUE (2026-07-06 deploy
# review, family issues.filename_or_meta_titles). ASSESSMENT_QA_TITLE_SQL_RE
# is intentionally NARROWER (it drives the re-derive gate); it misses the
# "schema drift" / bare "manifest" / ".docx" / "absent from workbook" phrasings
# that 12 governance rows (WSFS, texas-capital, regions, compeer, cathay,
# bell-bank, alma-bank) carry as kind='client', so they leaked onto the AE
# context register. Rows matching THIS pattern are QA-meta about the workbook,
# never a client issue — reclassify them to 'assessment_qa' (Health-page
# material; the context router already excludes assessment_qa). Kept in
# lock-step with the audit's _META_ISSUE — if that regex changes, change this.
_META_TITLE_RE = re.compile(
    r"run_manifest|MANIFEST|sheet[- _]?nam|citation[- _]?density|\.csv\b"
    r"|\.json\b|\.docx\b|\.xlsx\b|governance artifact|missing artifact"
    r"|naming mismatch|schema drift"
    # scoring-methodology notes mined into client registers (2026-07-12):
    # cap/ceiling mechanics, REC echoes, coverage flags — Health-page
    # material (assessment_qa), never AE-facing client issues
    r"|^REC-\d+ \(|XPIL-\d+|caps? P[1-4]C|cap RAISED M|NO_EVIDENCE flag"
    r"|URF-\d|documented as N/A|score \(\d(\.\d)?\) based on", re.I)


def _norm_name(s: str) -> str:
    """Folder/entity name → comparable token string (lowercased alnum)."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# ── pipeline-QA row detection (quarantine pass) ────────────────────────────
# Grounded on the real IBKR governance register: rows keyed on artifact
# file names, pipeline schema-contract drift, and E-ID bookkeeping — the
# DMA bot auditing ITSELF, which is never a client's digital-maturity issue.
_ARTIFACT_FILE_RE = re.compile(
    r"\b[\w-]+\.(?:csv|json|xlsx?|docx?|md|txt|png|zip)\b", re.IGNORECASE,
)
_PIPELINE_CATEGORY_RE = re.compile(
    r"\b(?:INPUT_VALIDATION|ARTIFACT_PROVENANCE|EVIDENCE_TRACEABILITY|"
    r"SCHEMA_(?:DRIFT|CONTRACT)|FORMAT_COMPLIANCE|GOVERNANCE_PROCESS)\b",
)
_PIPELINE_PHRASE_RE = re.compile(
    r"schema\s+(?:contract|drift|mismatch)|interface\s+contract|"
    r"governance\s+audit\s+expects|absent\s+as\s+(?:a\s+)?standalone|"
    r"standalone\s+\w+\s+column\s+absent|"
    r"orphan\s+citation|range-style\s+(?:e-?id|referenc)|"
    r"v\d+(?:\.\d+)?\s+governance|"
    r"assessment\s+skill|scoring[_\s]scratchpad|evidence[_\s]index\.(?:json|csv)|"
    r"cited\s+in\s+subcap\s+rationales|report\s+section\s+\d+|"
    r"layer\s+[0-3]\s+(?:qa|pass)|"
    # the bot's own QA-check bookkeeping: pattern/threshold counters over
    # its rationales, subcap-citation ratios, workbook schema drift.
    r"pattern\s+detected\s+in\s+rationales|subcaps?\s+capped|"
    r"\(threshold\s*[>≥<]|cited\s+in\s+\d+\s+of\s+\d+\s+subcaps|"
    r"workbook\s+schema|reference\s+count:\s*\d|"
    r"check\s+found\s+\d+\s+e-?ids?|"
    # report-audit metric rows (EWB GOV register class, live 2026-07-06):
    # "Citations: total=31 (≥30: True), exec=3 (≥5: False)", "Source
    # attribution: 237/642 (37%) have NO_EVIDENCE", "Critic log: No formal
    # critic worksheet generated", "Report citations: 31 unique E-IDs
    # (target ≥50)", "Anti-generic: forbidden=0, generic_exec=38%".
    r"\bNO_EVIDENCE\b|unique\s+e-?ids|critic\s+(?:log|worksheet)|"
    r"missing\s+urls|generic_exec|\bforbidden=\d|\bexec=\d|"
    r"citations?:\s*total=|\bpeer\s+refs\b|"
    r"e-?ids?\s+to\s+(?:the\s+)?executive\s+summary",
    re.IGNORECASE,
)
# Audit-metric LEAD labels — the row is the report auditing itself
# ("URL validity: 237/642 (37%)…", "Peer integration: 0 total peer
# refs…", "Proof completeness 54.3% (target >=95%)").
_AUDIT_LEAD_RE = re.compile(
    r"^\s*(?:citations?|url\s+validity|source\s+attribution|critic\s+log|"
    r"report\s+citations?|peer\s+integration|anti-generic|"
    r"proof\s+completeness|evidence\s+coverage|scoring\s+coverage|"
    r"range-style\s+references?)\b\s*(?:[:=]|\d)",
    re.IGNORECASE,
)
# Two-letter governance check codes ("IV-05", "ET-01", "RC-14", "SI-06",
# "DC-06", "PV-03", "AP-04") — the register's own audit-rule ids; a client
# issue never leads with one.
_PIPELINE_CHECK_CODE_RE = re.compile(r"\b(?:IV|ET|AP|PV|RC|DC|SI)-\d{1,2}\b")


def is_pipeline_artifact_issue(
    *,
    title: str | None = None,
    description: str | None = None,
    category: str | None = None,
    affected_id: str | None = None,
) -> bool:
    """True when an issue row records the DMA pipeline auditing its own
    artifacts (file-name-shaped subjects, schema-contract drift, E-ID
    bookkeeping) rather than a client issue with a maturity impact."""
    if affected_id and _ARTIFACT_FILE_RE.fullmatch(affected_id.strip()):
        return True
    if category and _PIPELINE_CATEGORY_RE.search(category.upper()):
        return True
    blob = f"{title or ''} {description or ''}"
    lead = (title or description or "").strip().split(" ", 1)[0]
    if _ARTIFACT_FILE_RE.fullmatch(lead):
        return True  # "caps_applied_log.csv absent as standalone CSV file…"
    if _PIPELINE_CHECK_CODE_RE.search(blob):
        return True  # "RC-14 check found 0 E-IDs…" / "This triggers SI-06"
    if _AUDIT_LEAD_RE.match(title or "") or _AUDIT_LEAD_RE.match(description or ""):
        return True  # "URL validity: 237/642 (37%)…" — report self-audit
    return bool(_PIPELINE_PHRASE_RE.search(blob))


# ── enforcement-detail composition (pass 3) ────────────────────────────────
# Row shapes that qualify as regulatory/compliance issues. SUPERSET of
# `context_extras._REG_ISSUE_RE` / the frontend RegulatoryStandingCard
# REG_ISSUE_RE (which pick the callout row): named-regulator actions
# ("FINRA AWC…", "CFTC penalty…") are enforcement content even when the
# title never says "regulatory" — those drilldowns need the detail too.
_REG_ISSUE_RE = re.compile(
    r"regulat|complian|enforc|consent|licen[cs]|\bbsa\b|\baml\b|cfpb|sanction|"
    r"finra|\bawc\b|\bcftc\b|\bocc\b|\bfdic\b|\bncua\b|\bosfi\b|\bfintrac\b|"
    r"\bsec\b|penalt|cease and desist|restitution|disgorgement",
    re.IGNORECASE,
)
# Evidence excerpts that describe a concrete enforcement action.
_ENFORCEMENT_EV_RE = re.compile(
    r"enforcement|consent order|penalt|cease and desist|sanction|"
    r"\bAWC\b|censur|settle(?:d|ment)|\bfined?\b|restitution|"
    r"disgorgement|civil money penalty",
    re.IGNORECASE,
)
# Bracketed citation (single- or multi-id: "[E-047]", "[E-020,E-042]") —
# a row carrying one is already evidence-anchored.
_INLINE_EID_RE = re.compile(r"\[(?:E-\d{2,4}[,;\s]*)+\]")
_TOKEN_RE = re.compile(r"[a-z0-9$%.]{3,}")
_STOP_TOKENS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "issue", "open",
    "within", "days", "due", "action", "actions", "regulatory", "compliance",
})


def _issue_tokens(text_: str) -> set[str]:
    return {
        t for t in _TOKEN_RE.findall((text_ or "").lower())
        if t not in _STOP_TOKENS
    }


# Workbook scratch columns that ride the subcap rationale cell ("… |
# Evidence ceiling: 5.0 | Diagnostic: Does the organization have …") —
# scoring-rubric bookkeeping, never AE-facing prose (live 2026-07-06).
_RUBRIC_SEGMENT_RE = re.compile(
    r"^\s*(?:evidence\s+ceiling|diagnostic|rubric|confidence|"
    r"cap(?:ped)?(?:\s+at)?|scoring\s+note)\b\s*[:=]?",
    re.IGNORECASE,
)
# Inline (non-pipe) scratch markers observed in the IBKR workbook cells:
# "… via proxy. [E-020] Evidence: E-042, E-023 Q: Does the organization
# have … Final: M1.4 from raw M1.4, ceil level 5.0". Case-sensitive —
# these are the workbook's own column labels, always capitalised.
_INLINE_SCRATCH_RE = re.compile(
    r"\s(?:Q|Final|Evidence|Diagnostic|Ceiling|Rubric|Raw)\s*:",
)
# A catalogue "name" that is itself taxonomy jargon (seed stubs, code
# echoes) — composing a title from it would print "capability area this
# capability" after the jargon scrub.
_JARGONY_NAME_RE = re.compile(r"\bsub-?cap\b|\bP[1-4]C\d", re.IGNORECASE)


def clean_subcap_rationale(raw: str | None, max_chars: int = 700) -> str:
    """The analyst's own rationale prose: pipe-separated workbook rubric
    columns dropped, inline scratch markers ("Q:", "Final:", "Evidence:")
    cut, and the tail clipped at a sentence boundary (never the mid-word
    "…criteria an" cut the audit found)."""
    from app.services.nlp.segment import clip_sentences

    kept = [
        seg.strip() for seg in (raw or "").split("|")
        if seg.strip() and not _RUBRIC_SEGMENT_RE.match(seg)
    ]
    joined = " ".join(kept)
    cut = _INLINE_SCRATCH_RE.search(joined)
    if cut:
        joined = joined[: cut.start()].rstrip(" ,;:")
    return clip_sentences(joined, max_chars)


def gap_display_name(cap_name: str | None, rationale: str | None,
                     subcap_id: str) -> str:
    """What the capability-gap issue title names. The real catalogue name
    when it exists and is not itself taxonomy jargon; else the lead
    clause of the analyst's own rationale ("No CRM/MAP confirmed") —
    grounded and descriptive; else the bare subcap id (last resort)."""
    name = (cap_name or "").strip()
    if name and not _JARGONY_NAME_RE.search(name):
        return name
    lead = clean_subcap_rationale(rationale, 90)
    lead = lead.split(". ", 1)[0].strip(" .")
    return lead or subcap_id


def compose_enforcement_detail(
    *,
    title: str | None,
    rationale: str | None,
    linked_subcap_ids: list[str] | None,
    evidence: list,
) -> tuple[str, list[str]] | None:
    """(new_rationale, linked_subcap_ids) for a regulatory issue row, or
    None when nothing grounded can be added.

    ``evidence`` rows need ``e_id`` / ``excerpt`` / ``linked_subcap_ids``
    attributes (already tier-ordered by the caller). The best row is the
    first whose excerpt names an enforcement action AND shares ≥2 content
    tokens with the issue's own text — same-event grounding, never a
    generic regulatory paragraph. The excerpt is appended VERBATIM
    (``clip_quote``: sentence-boundary truncation + ellipsis, never
    mid-claim) with its E-ID; subcaps fill only when the row had none.
    """
    from app.services.nlp.segment import clip_quote

    blob = f"{title or ''} {rationale or ''}"
    if not _REG_ISSUE_RE.search(blob):
        return None
    if _INLINE_EID_RE.search(rationale or ""):
        return None  # already evidence-anchored — idempotent no-op
    toks = _issue_tokens(blob)
    best = None
    for ev in evidence:
        excerpt = (getattr(ev, "excerpt", None) or "").strip()
        if len(excerpt) < 40 or not _ENFORCEMENT_EV_RE.search(excerpt):
            continue
        shared = len(toks & _issue_tokens(excerpt))
        if shared < 2:
            continue
        if best is None or shared > best[0]:
            best = (shared, ev)
    if best is None:
        return None
    ev = best[1]
    quote = clip_quote((ev.excerpt or "").strip(), 420)
    if not quote:
        return None
    base = (rationale or "").strip()
    # A rationale that merely duplicates the title adds nothing — the
    # evidence quote becomes the drilldown's descriptive detail.
    if base and _norm_name(base) == _norm_name(title or ""):
        base = ""
    detail = f'Research evidence [{ev.e_id}]: "{quote}"'
    new_rationale = (f"{base} {detail}".strip())[:2000]
    subs = list(linked_subcap_ids or [])
    if not subs:
        subs = list(getattr(ev, "linked_subcap_ids", None) or [])[:6]
    return new_rationale, subs


def _package_index() -> dict[str, str]:
    """{normalized client-dir name → package root} over the corpus."""
    idx: dict[str, str] = {}
    if not os.path.isdir(_CORPUS):
        return idx
    for batch in sorted(glob.glob(os.path.join(_CORPUS, "*"))):
        if not os.path.isdir(batch):
            continue
        for client in sorted(glob.glob(os.path.join(batch, "*"))):
            if not os.path.isdir(client):
                continue
            root = client
            for sub in [client, *[d for d in glob.glob(os.path.join(client, "*"))
                                  if os.path.isdir(d)]]:
                if any(os.path.isdir(os.path.join(sub, c)) for c in _CANON):
                    root = sub
                    break
            idx.setdefault(_norm_name(os.path.basename(client)), root)
    return idx


def _mine_issue_rows(root: str) -> list:
    """Every issue-register artifact under a package root, broadest discovery
    (case-insensitive, any name containing issue+register / issues_register),
    parsed via the canonical CSV parser. Returns the richest file's
    CLIENT-classified IssueRow list — QA governance checklists (kind=
    'assessment_qa') never refill an AE register from here."""
    from app.services.parsers.package_csvs import parse_issue_register_csv

    cands: list[str] = []
    for sub in ("07_governance", "08_appendices", "03_scoring_workbook",
                "02_research_workbook", "01_evidence"):
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for f in glob.glob(os.path.join(d, "**", "*.csv"), recursive=True):
            base = os.path.basename(f).lower()
            if ("issue" in base and ("register" in base or "log" in base)) \
                    or "issues_register" in base:
                cands.append(f)
    best: list = []
    for f in sorted(set(cands)):
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                rows = parse_issue_register_csv(fh.read())
        except OSError:
            continue
        # keep rows that carry a real title/finding (skip header-only or
        # rows the parser couldn't title) AND that are CLIENT issues by
        # CONTENT — the per-row classifier is finer than the parser's
        # header-level kind: pipeline-QA rows ("caps_applied_log.csv
        # absent…") never surface on the client register even from a
        # client-classified file, while a genuine client issue riding a
        # governance-classified checklist (complaint backlog next to a
        # check_id column) is still rescued.
        rows = [
            r for r in rows
            if (getattr(r, "description", "") or "").strip()
            and not is_pipeline_artifact_issue(
                description=getattr(r, "description", None),
                category=getattr(r, "type", None),
            )
        ]
        if len(rows) > len(best):
            best = rows
    return best


# issue_register.severity is VARCHAR(16), lowercase-canonical in the DB.
_SEV_MAP = {"CRITICAL": "critical", "HIGH": "high", "MATERIAL": "high",
            "SEVERE": "high", "MED": "medium", "MEDIUM": "medium",
            "MODERATE": "medium", "LOW": "low", "MINOR": "low", "INFO": "low"}


def _norm_sev(raw: object) -> str:
    """Free-text severity → canonical lowercase ∈ {critical,high,medium,low}."""
    s = str(raw or "").strip().upper()
    for k, v in _SEV_MAP.items():
        if s.startswith(k):
            return v
    return "medium"


def _sev_for(score: float) -> str:
    if score < 2.0:
        return "high"
    if score < 2.75:
        return "medium"
    return "low"


async def _amain() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    from app.services.parsers.package_csvs import ASSESSMENT_QA_TITLE_SQL_RE

    sm = get_sessionmaker()
    pkg_idx = _package_index()
    mined = synthesized = rows_written = junk_deleted = reclassified = 0
    async with sm() as session:
        # ── Reclassify meta-titled kind='client' rows → 'assessment_qa' ──
        # UNCONDITIONAL over every ACTIVE run (not the empty-register gate):
        # a client with both real issues AND mis-kinded governance rows was
        # never re-derived, so its "schema drift"/"manifest mismatch" rows
        # rendered on the AE register. Match the AUDIT's exact meta pattern
        # (broader than the gate's) in Python for a verbatim criterion, PLUS
        # `is_pipeline_artifact_issue` over title+rationale (the quarantine
        # classifier: check-code leads, artifact-file subjects, report
        # self-audit metrics the title regex alone misses), then move
        # matches to assessment_qa — preserved for Health, dropped from
        # context.json (router excludes assessment_qa). Never deletes; never
        # touches a real client issue.
        client_rows = (await session.execute(text(
            """
            SELECT ir.id::text id, ir.title, ir.rationale
            FROM issue_register ir
            JOIN runs r ON r.id = ir.run_id AND r.status = 'ACTIVE'
            JOIN entities e ON e.id = r.entity_id AND e.status = 'ACTIVE'
            WHERE COALESCE(ir.kind, 'client') = 'client'
              AND BTRIM(COALESCE(ir.title, '')) <> ''
            """))).all()
        meta_ids = [row.id for row in client_rows
                    if _META_TITLE_RE.search(row.title or "")
                    or is_pipeline_artifact_issue(
                        title=row.title, description=row.rationale)]
        if meta_ids:
            async with session.begin_nested():
                res = await session.execute(text(
                    "UPDATE issue_register SET kind = 'assessment_qa' "
                    "WHERE id = ANY(CAST(:ids AS uuid[]))"),
                    {"ids": meta_ids})
                reclassified = res.rowcount or 0

        # Quality gate: a run qualifies when it has NO quality client
        # row — every existing row is blank-titled, assessment-QA
        # kinded, or meta-titled. (The old zero-rows gate let 3 junk
        # governance rows block the backfill for exactly the clients
        # whose registers the user flagged.)
        empties = (await session.execute(text(
            """
            SELECT e.id::text eid, e.name, e.drive_folder_id dfid,
                   e.subvertical sv, r.id::text rid, r.assessment_date asd
            FROM entities e
            JOIN runs r ON r.entity_id = e.id AND r.status = 'ACTIVE'
            WHERE e.status = 'ACTIVE'
              AND NOT EXISTS (
                  SELECT 1 FROM issue_register ir
                  WHERE ir.run_id = r.id
                    AND COALESCE(ir.kind, 'client') = 'client'
                    AND BTRIM(COALESCE(ir.title, '')) <> ''
                    AND ir.title !~* :qa_re
              )
            ORDER BY e.display_id
            """), {"qa_re": ASSESSMENT_QA_TITLE_SQL_RE})).all()

        for ent in empties:
            # ── 1. MINE real issue artifacts the ingest missed ──────────
            root = None
            dfid = ent.dfid or ""
            key = _norm_name(dfid.split("local:", 1)[-1] if "local:" in dfid
                             else ent.name)
            if key in pkg_idx:
                root = pkg_idx[key]
            else:  # token-subset fallback
                kt = set(key.split())
                for k, v in pkg_idx.items():
                    if kt and (kt <= set(k.split()) or set(k.split()) <= kt):
                        root = v
                        break
            issue_rows = _mine_issue_rows(root) if root else []

            # Junk kind='client' rows (blank / meta-titled) are what
            # blocked this backfill AND what the AE sees — delete them
            # for every gated run (an honestly-empty register beats
            # "Missing governance artifact: caps_applied_log.csv").
            # Properly kinded assessment_qa rows are kept (Health page).
            async with session.begin_nested():
                junk = await session.execute(text(
                    """
                    DELETE FROM issue_register
                    WHERE run_id = CAST(:r AS uuid)
                      AND COALESCE(kind, 'client') = 'client'
                      AND (BTRIM(COALESCE(title, '')) = ''
                           OR title ~* :qa_re)
                    """),
                    {"r": ent.rid, "qa_re": ASSESSMENT_QA_TITLE_SQL_RE})
                junk_deleted += junk.rowcount or 0

            if issue_rows:
                import json as _json

                from app.services.parsers.package_csvs import (
                    canonical_issue_status,
                )
                async with session.begin_nested():
                    from datetime import date as _date

                    def _as_date(iso: str | None):
                        try:
                            return _date.fromisoformat(iso) if iso else None
                        except ValueError:
                            return None

                    for ir in issue_rows[:25]:
                        st = canonical_issue_status(ir.status)
                        await session.execute(text(
                            """
                            INSERT INTO issue_register (run_id, entity_id,
                                issue_id, title, severity, rationale, opened_on,
                                resolved_on, status, kind, dma_impact, caps,
                                linked_subcap_ids, source_path)
                            VALUES (CAST(:r AS uuid), CAST(:e AS uuid), :iid,
                                :ti, :sev, :rat, :od, :rd, :st,
                                'client', :impact, CAST(:caps AS JSONB),
                                :subs, :sp)
                            ON CONFLICT DO NOTHING
                            """),
                            {"r": ent.rid, "e": ent.eid,
                             "iid": (ir.issue_id or "ISS")[:16],
                             "ti": (ir.description or "Governance issue")[:500],
                             "sev": _norm_sev(ir.severity),
                             "rat": (ir.cap_formula or ir.description or "")[:2000],
                             "od": _as_date(ir.opened_on) or ent.asd,
                             "rd": _as_date(ir.resolved_on),
                             "st": st,
                             "impact": ir.dma_impact,
                             "caps": _json.dumps(ir.caps) if ir.caps else None,
                             "subs": [
                                 a for a in (ir.affected_categories or [])
                                 if re.match(r"^P[1-4]C", a)
                             ],
                             "sp": "mined:client-register"})
                        rows_written += 1
                mined += 1
                continue

            # ── 2. Capability gaps are NOT issues (plan S14 / user directive) ──
            # The issue register lists only REAL report-noted issues (litigation,
            # enforcement actions, incidents, concentration events, self-disclosed
            # risks). Capability gaps belong on the heatmap / focus surfaces, so a
            # client with no mined real issues keeps an honestly-empty register
            # rather than shipping "Capability gap: …" headlines that read as
            # fabricated issues (the frontend renders a clean-posture empty
            # state). Purge any synthesized gap rows a prior run left, so the
            # regen is idempotent and the stale committed pack is corrected.
            async with session.begin_nested():
                purged = await session.execute(text(
                    "DELETE FROM issue_register WHERE run_id = CAST(:r AS uuid) "
                    "AND source_path = 'derived:capability-gap'"), {"r": ent.rid})
                junk_deleted += purged.rowcount or 0

        # ── 3. ENFORCEMENT DETAIL — descriptive drilldown + evidence ────
        # Every regulatory/compliance row in an ACTIVE run whose rationale
        # is not yet evidence-anchored gains the entity's OWN enforcement
        # excerpt (verbatim + E-ID) and, when it had none, the evidence
        # row's subcap links. Skips already-cited rows → idempotent.
        reg_rows = (await session.execute(text(
            """
            SELECT ir.id::text iid_pk, ir.entity_id::text eid, ir.title,
                   ir.rationale, ir.linked_subcap_ids
            FROM issue_register ir
            JOIN runs r ON r.id = ir.run_id AND r.status = 'ACTIVE'
            ORDER BY ir.created_at
            """))).all()
        detailed = 0
        ev_cache: dict[str, list] = {}
        for row in reg_rows:
            blob = f"{row.title or ''} {row.rationale or ''}"
            if not _REG_ISSUE_RE.search(blob) or _INLINE_EID_RE.search(
                    row.rationale or ""):
                continue
            if row.eid not in ev_cache:
                ev_cache[row.eid] = (await session.execute(text(
                    """
                    SELECT e_id, excerpt, linked_subcap_ids
                    FROM evidence_index
                    WHERE entity_id = CAST(:e AS uuid)
                      AND excerpt ~* '(enforcement|consent order|penalt|cease and desist|sanction|AWC|censur|settle|fined|restitution)'
                    ORDER BY tier ASC, e_id ASC
                    LIMIT 200
                    """), {"e": row.eid})).all()
            composed = compose_enforcement_detail(
                title=row.title, rationale=row.rationale,
                linked_subcap_ids=list(row.linked_subcap_ids or []),
                evidence=ev_cache[row.eid],
            )
            if composed is None:
                continue
            new_rat, subs = composed
            await session.execute(text(
                """
                UPDATE issue_register
                SET rationale = :rat, linked_subcap_ids = :subs
                WHERE id = CAST(:i AS uuid)
                """), {"rat": new_rat, "subs": subs, "i": row.iid_pk})
            detailed += 1

        # ── 4. CE-verify issue→subcap links (2026-07-09 NLP hardening) ──
        # Runs over ALL persisted client rows (existing + just-mined), so a
        # single derive pass heals the whole corpus. Idempotent.
        links_checked, links_pruned = await _verify_subcap_links(session)

        # ── 4. Ground blank rationales in the analyst's own words (S14) ──
        rat_filled, rat_blank = await _backfill_blank_rationales(session)
        await session.commit()
    print(f"# derive_issues: filled={mined + synthesized} "
          f"(mined={mined} synthesized={synthesized}) rows_written={rows_written} "
          f"junk_deleted={junk_deleted} reclassified={reclassified} "
          f"enforcement_rows_detailed={detailed} "
          f"link_rows_checked={links_checked} links_pruned={links_pruned} "
          f"rationales_backfilled={rat_filled} rationales_still_blank={rat_blank} "
          f"(grounded; idempotent)", flush=True)
    return 0


_LINK_SUPPORT_FLOOR = 0.30


async def _verify_subcap_links(session) -> tuple[int, int]:
    """CE-verify every client issue's ``linked_subcap_ids`` against the issue's
    own text and PRUNE the links the cross-encoder cannot support (fused
    support < 0.30). 40.5% of persisted links were semantically unrelated to
    their issue (2026-07-09 corpus audit) because a regex over the CSV's
    affected_categories was the only gate — and cross_entity_patterns
    ``issue_theme`` rows inherit whatever survives here. A category-grain id
    (``P1C2``) counts as supported when ANY leaf under it clears the floor;
    an id the catalogue can't resolve is KEPT (we can't honestly judge it).
    The issue row itself is never deleted — only its bad links. No-op when
    the NLP tier is cold. Returns (rows_checked, links_pruned)."""
    from app.services.nlp import rerank
    from app.services.nlp.semantic import SemanticIndex, model_available
    if not model_available():
        return 0, 0
    rows = (await session.execute(text(
        """
        SELECT ir.id, ir.title, ir.rationale, ir.linked_subcap_ids,
               r.ccg_catalog_version AS cv
        FROM issue_register ir
        JOIN runs r ON r.id = ir.run_id
        JOIN entities e ON e.id = r.entity_id
        WHERE e.status = 'ACTIVE'
          AND COALESCE(ir.kind, 'client') = 'client'
          AND array_length(ir.linked_subcap_ids, 1) > 0
        """))).all()
    if not rows:
        return 0, 0
    # Catalogue names per version, loaded once (a few hundred rows each).
    names: dict[tuple[str, str], str] = {}
    for cv in sorted({r.cv for r in rows if r.cv}):
        for c in (await session.execute(text(
            "SELECT subcap_id, name, COALESCE(description, '') AS d "
            "FROM ccg_subcaps WHERE version = :v"), {"v": cv})).all():
            names[(cv, c.subcap_id)] = f"{c.name}. {c.d}"[:240]
    idx = SemanticIndex()
    checked = pruned = 0
    for r in rows:
        issue_txt = f"{r.title or ''}. {(r.rationale or '')[:280]}".strip(". ")
        if len(issue_txt) < 12 or not r.cv:
            continue
        checked += 1
        kept: list[str] = []
        for sid in r.linked_subcap_ids:
            cands = ([names[(r.cv, sid)]] if (r.cv, sid) in names else
                     [t for (v, s), t in names.items()
                      if v == r.cv and s.startswith(sid + ".")][:12])
            if not cands:
                kept.append(sid)
                continue
            sups = rerank.support_scores(
                issue_txt, [(c, idx.relevance(issue_txt, c)) for c in cands])
            if max(sups) >= _LINK_SUPPORT_FLOOR:
                kept.append(sid)
        if len(kept) != len(r.linked_subcap_ids):
            pruned += len(r.linked_subcap_ids) - len(kept)
            await session.execute(text(
                "UPDATE issue_register SET linked_subcap_ids = :k "
                "WHERE id = :i"), {"k": kept, "i": r.id})
    return checked, pruned


_TAG_MARKER_RE = re.compile(r"\s*\[([A-Z][A-Z /_-]{1,18})\]:?\s*")
_EID_DUMP_RE = re.compile(
    r"(?:(?<=^)|(?<=[.!?:]\s))"
    r"((?:E-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*,\s*)+"
    r"E-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\s+(supports?)\b")
_NUM_WORDS = ("zero", "one", "two", "three", "four", "five", "six",
              "seven", "eight", "nine", "ten")


def _prose_ify_rationale(t: str) -> str:
    """Workbook notation -> prose, deterministically and idempotently.

    "[MATURITY]: Maps to M3" reads as a section marker from the scoring
    tool; served prose gets a sentence-lead label ("Maturity: maps to
    M3"). "E-005, E-006, E-007 support the assessment" leads with an
    ID dump; the counted claim keeps every citation but reads as a
    sentence ("Three evidence items [E-005, E-006, E-007] support...").
    """
    t = (t or "").strip()

    def _tag(m: re.Match[str]) -> str:
        label = m.group(1).title().replace("_", " ").strip()
        return f". {label}: "

    t = _TAG_MARKER_RE.sub(_tag, t)
    t = re.sub(r"^\.\s+", "", t)
    t = re.sub(r"\.\s*\.", ".", t)

    def _dump(m: re.Match[str]) -> str:
        ids = [x.strip() for x in m.group(1).split(",") if x.strip()]
        n = (_NUM_WORDS[len(ids)] if len(ids) < len(_NUM_WORDS)
             else str(len(ids)))
        return (f"{n.capitalize()} evidence items "
                f"[{', '.join(ids)}] {m.group(2)}")

    return _EID_DUMP_RE.sub(_dump, t).strip()


async def _backfill_blank_rationales(session) -> tuple[int, int]:
    """Fill blank client-issue rationales from the run's own material (S14).

    Source order per row: the linked subcap's ``subcap_scores.rationale``
    (the assessment's per-capability prose, cited with its real score),
    else the row's own ``dma_impact`` — labelled, because the context and
    heatmap routes render dma_impact as its own field and a verbatim copy
    would read as duplicated text. Rows with neither source stay blank:
    an honest gap beats an invented sentence. Idempotent — only blank
    rows are touched. Returns (filled, still_blank)."""
    # scrub workbook markers out of rationales a PRIOR backfill composed
    # (idempotent; only rows this pass wrote, identified by their prefix)
    await session.execute(text(
        r"""
        UPDATE issue_register
        SET rationale = BTRIM(regexp_replace(
                rationale, '\[(NO\s+)?EVIDENCE\]:?\s*|🚨\s*', '', 'gi'))
        WHERE rationale LIKE 'Linked capability %'
          AND (rationale ~* '\[(NO\s+)?EVIDENCE\]' OR rationale LIKE '%🚨%')
        """))
    # prose-ify rationales already persisted with workbook notation —
    # [TAG]: section markers and E-ID-dump subjects (idempotent: the
    # transform is a no-op on already-converted text)
    tagged = (await session.execute(text(
        r"""
        SELECT id, rationale FROM issue_register
        WHERE rationale ~ '\[[A-Z][A-Z /_-]{1,18}\]'
           OR rationale ~ 'E-[A-Za-z0-9-]+,\s*E-[A-Za-z0-9-]+[^.]*\ssupports?\s'
        """))).all()
    for tr in tagged:
        fixed = _prose_ify_rationale(tr.rationale or "")
        if fixed and fixed != tr.rationale:
            await session.execute(text(
                "UPDATE issue_register SET rationale = :ra WHERE id = :i"),
                {"ra": fixed[:2000], "i": tr.id})
    rows = (await session.execute(text(
        """
        SELECT ir.id, ir.run_id, ir.linked_subcap_ids, ir.dma_impact
        FROM issue_register ir
        JOIN runs r ON r.id = ir.run_id AND r.status = 'ACTIVE'
        WHERE COALESCE(ir.kind, 'client') = 'client'
          AND BTRIM(COALESCE(ir.rationale, '')) = ''
        """))).all()
    if not rows:
        return 0, 0
    filled = 0
    for r in rows:
        rationale = None
        for sid in (r.linked_subcap_ids or []):
            # exact leaf first; else the weakest leaf under a category-grain
            # id — the score that makes the issue load-bearing.
            sub = (await session.execute(text(
                """
                SELECT subcap_id, score, rationale
                FROM subcap_scores
                WHERE run_id = :rid
                  AND (subcap_id = :sid OR subcap_id LIKE :pre)
                  AND BTRIM(COALESCE(rationale, '')) <> ''
                ORDER BY (subcap_id = :sid) DESC, score ASC NULLS LAST
                LIMIT 1
                """), {"rid": r.run_id, "sid": sid,
                       "pre": f"{sid}.%"})).first()
            if sub is not None:
                score_bit = (f" (scores {format(round(float(sub.score), 2), 'g')}/5 "
                             f"on this run)" if sub.score is not None else "")
                # strip raw workbook markers before quoting — "[EVIDENCE]:",
                # "[NO EVIDENCE]", shout-flag emoji — they are analyst-tool
                # notation, not AE prose (cohesion sweep: fragment class)
                prose = re.sub(r"^\s*(?:\[(?:NO\s+)?EVIDENCE\]:?\s*|🚨\s*)+",
                               "", sub.rationale.strip())
                prose = re.sub(r"\[(?:NO\s+)?EVIDENCE\]:?\s*", "", prose)
                prose = _prose_ify_rationale(prose)
                if len(prose) < 20:
                    continue
                rationale = (f"Linked capability {sub.subcap_id}{score_bit}: "
                             f"{prose}")[:2000]
                break
        if rationale is None:
            impact = (r.dma_impact or "").strip()
            if impact:
                rationale = f"Raised for its assessed impact: {impact}"[:2000]
        if rationale:
            await session.execute(text(
                "UPDATE issue_register SET rationale = :ra WHERE id = :i"),
                {"ra": rationale, "i": r.id})
            filled += 1
    return filled, len(rows) - filled


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
