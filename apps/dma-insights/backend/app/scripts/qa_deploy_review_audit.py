"""Deploy-review defect-family audit — grades the RENDERED startup pack.

Born from the 2026-07-06 deploy review (build 2afda85): the operator read
the deployed pages and found defect families that "non-empty" QA never
catches — duplicated why-now signals, fragment recommendation titles,
issue registers listing filenames, score-echo card prose, cross-metric
financial outliers, mid-word sentiment fragments, one-template platform
narratives. Each check below encodes one reported family and measures it
against startup-data (the exact payloads AEs see), per client and in
aggregate, so regressions in ANY family fail loudly at build time and
the before→after of a remediation is a number, not an impression.

Usage:
  python -m app.scripts.qa_deploy_review_audit [--pack DIR] [--json OUT]
      [--strict]

  --strict  exit 1 when any family exceeds its ceiling (see FAMILIES);
            without it the script reports and exits 0 (baseline mode).

Checks read ONLY the committed pack — no DB, no network — so they run
identically in dev, CI regen, and post-deploy verification.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter

# ── shared text helpers ─────────────────────────────────────────────────

_STOP = frozenset(
    "the a an and or of to in for with on at by from as is are was were be "
    "been has have had it its this that these those their your our".split()
)


def _tokens(s: str | None) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9']+", (s or "").lower())
        if len(t) > 2 and t not in _STOP
    }


def _containment(a: str | None, b: str | None) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    small = ta if len(ta) <= len(tb) else tb
    return len(ta & tb) / len(small)


_PUNCT_DEBRIS = re.compile(r"\(\s*[,;]|\[\s*[,;]|,\s*\)|,\s*\]|\s[.,;]\s|\.\.(?!\.)|,,")
_FRAGMENT_TITLE = re.compile(r"^[\s)\],;.:'\"-]|^[a-z]")
# Brand/product names that legitimately begin lowercase — not fragments.
_BRAND_TITLE = re.compile(r"^(nCino|iOS|iPhone|iPad|eNPS|iPaaS|myBank|xG)\b")
_SCORE_TALK = re.compile(
    r"\b(scor(?:e|es|ing)|peer median|out of 5|/5\b|maturity level|benchmark)",
    re.I)
_FACT_TOKEN = re.compile(
    r"\$\s?\d|\b(19|20)\d{2}\b|\d+(?:\.\d+)?%|\b[A-Z][a-zA-Z]+ (?:Cloud|Bank"
    r"|CRM|Core|API|platform)\b")
_META_ISSUE = re.compile(
    r"run_manifest|MANIFEST|sheet[- _]?nam|citation[- _]?density|\.csv\b"
    r"|\.json\b|\.docx\b|\.xlsx\b|governance artifact|missing artifact"
    r"|naming mismatch|schema drift", re.I)
_WORD_FRAGMENT = re.compile(r"^[a-z][\w]{0,12}[,;:]?\s")

# ── exec-summary (SCQA) typo/flow family ────────────────────────────────
# Mirrors app.services.nlp.quality.proofread / proofread_flags (kept LOCAL so
# this audit stays import-free — pack-only, no app/DB). Every code below is a
# defect the composer's final proofread pass now removes; ceiling 0 means a
# redeploy whose exec summaries still carry them fails the audit.
# Matches "E-047", the connector-id variants ("E-P3C3-003", "EV-12", "INT-3")
# and the dash-less "E0001" — the same id family quality._EID_RE accepts, so a
# summary grounded on those rows is NOT falsely counted under-cited.
_EXEC_EID_RE = re.compile(
    r"\b(?:EV|INT|E)(?:-[A-Za-z0-9]{1,6})*-\d{1,4}\b|\bE\d{3,4}\b")
_EXEC_EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF]")
_EXEC_SHOUT_RE = re.compile(
    r"\b(?:NUANCE|CONFIRMED GAP|CONFIRMED|MAJOR FINDING|KEY FINDING|FINDING|"
    r"NOTE|NEGATIVE|POSITIVE|CAUTION|IMPORTANT|WARNING|OBSERVATION|CORRECTION)"
    "\\s*[:\\-\u2013\u2014]\\s+")
_EXEC_META_RE = re.compile(
    r"manifest\s*=|registry\s*=\s*\d|unique E-?ID|E-?ID citations|threshold\s*:|"
    r"NO_EVIDENCE|proof completeness|weights?\s+sum\s+to\s+100|per-row single tier|"
    r"not in registry|\bmismatch(?:es)?\b|citation density|schema drift|"
    r"run_manifest|evidence count|under-?cite|pillar sections|"
    r"\bT[123]\s+evidence\b|\(\d+\s+E-?IDs\)", re.I)
_EXEC_ARTICLE_RE = re.compile(r"\b[Aa] (?=(?:8|11|18)(?:\.\d+)?\s?%)")
_EXEC_DOUBLE_SPACE_RE = re.compile(r"(?<=\S)  +(?=\S)")
_EXEC_ORPHAN_PUNCT_RE = re.compile(r"\s[.,;:!?](?:\s|$)|([.,;:!?])\1")
_EXEC_MISSING_SPACE_RE = re.compile(r"(?<=[a-z])[.!?](?=[A-Z])")
_EXEC_ELLIPSIS_RE = re.compile("\u2026" + r"|\.\.\.")
# score-restatement vs evidence-fact sentence (the "reads like a score recap"
# family): a score-signature sentence with NO $/%/year/vendor/officer fact.
_EXEC_SCORE_RE = re.compile(r"/5\b|out of 5|peer median|maturity level", re.I)
_EXEC_FACT_RE = re.compile(
    r"\$\s?\d|\d+(?:\.\d+)?%|\b(?:19|20)\d\d\b|\b(?:Salesforce|Databricks|"
    r"Tableau|Twilio|nCino|MuleSoft|Oracle|Fiserv|Consent Order|"
    r"C(?:EO|FO|IO|TO|ISO|DO|OO|RO))\b", re.I)

_WHY_NOW_FIELDS = (
    "label", "category", "strength", "window", "confidence", "claim",
    "detail", "metric", "peer_context", "play", "risk", "evidence",
    "timeline", "impact",
)


def _unbalanced(s: str) -> bool:
    return s.count("(") != s.count(")") or s.count("[") != s.count("]")


# ── per-family checks (each returns {metric: value} + offender list) ────

def check_why_now(ov: dict) -> tuple[Counter, list[str]]:
    c: Counter = Counter()
    bad: list[str] = []
    sigs = ov.get("why_now_signals") or []
    c["signals"] += len(sigs)
    for i, a in enumerate(sigs):
        missing = [f for f in _WHY_NOW_FIELDS if not a.get(f)]
        if missing:
            c["field_gap_signals"] += 1
            c["field_gaps"] += len(missing)
        for b in sigs[i + 1:]:
            if _containment(a.get("detail") or a.get("text"),
                            b.get("detail") or b.get("text")) >= 0.5:
                c["dup_pairs"] += 1
                bad.append(f"dup: {str(a.get('label'))[:40]} ~ {str(b.get('label'))[:40]}")
    fields = [(s.get("peer_context"), s.get("risk"), s.get("impact")) for s in sigs]
    for j, f in enumerate(fields):
        if any(f == g for g in fields[j + 1:]) and any(f):
            c["cloned_drill_fields"] += 1
    return c, bad


def check_recs(pr: dict) -> tuple[Counter, list[str]]:
    c: Counter = Counter()
    bad: list[str] = []
    recs = []
    for key in ("recommendations", "recs", "items"):
        v = pr.get(key)
        if isinstance(v, list):
            recs = v
            break
    # platforms_roadmap.json shape: phases[].recommendations[] with the
    # (time, effort, metric) triple living in `outcomes`.
    for ph in (pr.get("phases") or pr.get("roadmap") or []):
        if isinstance(ph, dict):
            recs.extend(ph.get("recommendations") or [])
    c["recs"] += len(recs)
    triples = Counter()
    for r in recs:
        t = str(r.get("title") or "")
        if not t.strip() or t.strip() == "(untitled)":
            c["untitled"] += 1
            bad.append("untitled rec")
        elif _BRAND_TITLE.match(t):
            pass  # nCino/iOS-class brand title — legitimately lowercase
        elif _FRAGMENT_TITLE.search(t) or _unbalanced(t) or len(t.strip()) < 12:
            c["fragment_titles"] += 1
            bad.append(f"fragment: {t[:60]}")
        out = r.get("outcomes") if isinstance(r.get("outcomes"), dict) else {}
        triples[(str(out.get("time") or r.get("time")),
                 str(out.get("effort") or r.get("effort")),
                 str(out.get("metric") or r.get("metric")))] += 1
    c["dup_metric_triples"] += sum(n - 1 for n in triples.values() if n > 1)
    return c, bad


def check_issues(cx: dict) -> tuple[Counter, list[str]]:
    c: Counter = Counter()
    bad: list[str] = []
    issues = cx.get("issue_register") or cx.get("issues") or []
    if isinstance(issues, dict):
        issues = issues.get("items") or []
    c["issues"] += len(issues)
    for it in issues:
        title = str(it.get("title") or "")
        kind = str(it.get("kind") or "")
        if kind == "assessment_qa":
            # classified meta rows are fine as long as they are excluded
            # from the AE surface — exporter keeps them out; if present
            # in context.json they count against the ceiling.
            c["meta_rows_served"] += 1
            bad.append(f"meta served: {title[:60]}")
            continue
        if not title.strip():
            c["blank_titles"] += 1
            bad.append("blank issue title")
        elif _META_ISSUE.search(title):
            c["filename_or_meta_titles"] += 1
            bad.append(f"meta/file title: {title[:60]}")
        if it.get("linked_subcap_ids"):
            c["attributed"] += 1
    return c, bad


def check_narratives(ov: dict, ins: dict) -> tuple[Counter, list[str]]:
    c: Counter = Counter()
    bad: list[str] = []
    for f in ov.get("findings") or ov.get("top_findings") or []:
        for k in ("what", "why", "so_what"):
            t = str(f.get(k) or "")
            if not t:
                continue
            c["finding_fields"] += 1
            if _PUNCT_DEBRIS.search(t):
                c["punct_debris"] += 1
                bad.append(f"debris[{k}]: …{t[:60]}")
    cards = ins.get("cards") or ins.get("insight_cards") or []
    for card in cards:
        what, why = str(card.get("what_text") or ""), str(card.get("why_text") or "")
        c["cards"] += 1
        if _PUNCT_DEBRIS.search(what) or _PUNCT_DEBRIS.search(why):
            c["punct_debris"] += 1
        if (_SCORE_TALK.search(what) and not _FACT_TOKEN.search(what)
                and len(what) > 60):
            c["score_echo_what"] += 1
        if card.get("counter_e_ids"):
            c["counter_present"] += 1
    scqa = str((ov.get("scqa") or {}).get("body_md")
               or (ov.get("narrative") or {}).get("scqa_md")
               or ov.get("scqa_md") or "")
    if scqa:
        sents = re.split(r"(?<=[.!?])\s+", scqa)
        score_s = sum(1 for s in sents
                      if _SCORE_TALK.search(s) and not _FACT_TOKEN.search(s))
        c["scqa_sentences"] += len(sents)
        c["scqa_score_restate"] += score_s
    return c, bad


def check_financial(ov: dict, cx: dict) -> tuple[Counter, list[str]]:
    c: Counter = Counter()
    bad: list[str] = []

    def _series_outliers(traj: dict | None, where: str) -> None:
        if not isinstance(traj, dict):
            return
        for name, vals in (traj.get("series") or {}).items():
            xs = [v for v in (vals or []) if isinstance(v, int | float) and v > 0]
            if len(xs) < 3:
                continue
            med = sorted(xs)[len(xs) // 2]
            for v in xs:
                if med > 0 and not (0.2 <= v / med <= 5.0):
                    c["series_outliers"] += 1
                    bad.append(f"{where}.{name}: {v} vs median {round(med, 2)}")

    _series_outliers(ov.get("financial_trajectory"), "overview")
    _series_outliers(((cx.get("financials") or {}).get("metrics")
                      or {}).get("trajectory"), "context")
    sent = (ov.get("firmographics") or {}).get("sentiment") or {}
    for row in (sent.get("sources") or []):
        sig = str(row.get("signal") or "")
        if sig and _WORD_FRAGMENT.match(sig) and sig[:4].lower() not in (
                "ios ", "app ", "enps"):
            c["sentiment_fragments"] += 1
            bad.append(f"sentiment fragment: {sig[:50]}")
    for grp in ("customer", "employee"):
        for row in (sent.get(grp) or []) or []:
            sc, mx = row.get("score"), row.get("scale")
            if (isinstance(sc, int | float) and isinstance(mx, int | float)
                    and mx > 0 and sc == mx):
                c["score_equals_scale"] += 1
                bad.append(f"{grp} {row.get('source')}: {sc}/{mx}")
    return c, bad


def check_thought_leadership(ov: dict) -> tuple[Counter, list[str]]:
    """Thought leadership is STRICTLY a Clay-enrichment surface (operator
    mandate 2026-07-06): every item must be Clay-sourced. An item stamped
    derived_from evidence/gemini, or carrying an INTERNAL url, is a
    contamination — the Zennify-proposal-as-thought-leadership class."""
    c: Counter = Counter()
    bad: list[str] = []
    tl = (ov.get("firmographics") or {}).get("thought_leadership") or []
    for it in tl if isinstance(tl, list) else []:
        if not isinstance(it, dict):
            continue
        c["tl_items"] += 1
        df = str(it.get("derived_from") or "").lower()
        url = str(it.get("url") or "")
        if df in ("evidence_index", "gemini", "vertex") or url == "INTERNAL":
            c["tl_non_clay"] += 1
            bad.append(f"non-Clay TL: {str(it.get('title'))[:50]} ({df or url})")
    return c, bad


def check_platform(pl: dict) -> tuple[Counter, list[str]]:
    c: Counter = Counter()
    bad: list[str] = []
    cards = pl.get("cards") or pl.get("platform_cards") or []
    sigs: Counter = Counter()
    for card in cards:
        c["platform_cards"] += 1
        if not (card.get("story_md") or "").strip():
            c["story_null"] += 1
        opp = str(card.get("opportunity_md") or "")
        if opp:
            sig = re.sub(r"(?:[A-Z][a-z&']+(?:\s+[A-Z][a-z&']+)*)", "NAME", opp)
            sig = re.sub(r"\d+(?:\.\d+)?", "N", sig)[:120]
            sigs[sig] += 1
            if not _FACT_TOKEN.search(opp):
                c["opportunity_no_facts"] += 1
    if sigs:
        c["opportunity_dominant_template"] += max(sigs.values())
    return c, bad


_EXEC_FIT_NUM_RE = re.compile(r"\((\d+)\s*/\s*100\s*fit\)", re.I)


def _lead_platform_fit(platforms: dict | None) -> float | None:
    """The rank-1 platform card's fit_score (min sequence_rank, then max fit) —
    the number the exec summary's synthetic clause must agree with."""
    if not isinstance(platforms, dict):
        return None
    cards = platforms.get("cards") or platforms.get("platform_cards") or []
    scored = [c for c in cards if isinstance(c, dict) and c.get("fit_score") is not None]
    if not scored:
        return None
    lead = min(scored, key=lambda c: (
        c.get("sequence_rank") if c.get("sequence_rank") is not None else 99,
        -float(c.get("fit_score") or 0.0)))
    try:
        return float(lead.get("fit_score"))
    except (TypeError, ValueError):
        return None


def check_exec_summary(
    ov: dict, available_eids: int | None = None,
    platforms: dict | None = None,
) -> tuple[Counter, list[str]]:
    """The executive-summary (SCQA) typo/flow gate (operator report 2026-07-06:
    "Most have typos. Poor flow noted."). Grades the RENDERED
    overview.narrative.scqa_md — the single highest-visibility AE surface — for
    the defect families the composer's final proofread pass now removes, so a
    redeploy whose exec summaries still carry them fails the audit at ceiling 0:

      double_space, orphan_punct (space-before-punct / doubled ".."/",,"),
      missing_space_after_period, stray_ellipsis (clip artifact), emoji,
      article_error ("A 8.9%"), shout_label ("CONFIRMED GAP:"), meta_leak
      (QA/pipeline rows read as findings), under_cited (<2 distinct E-IDs), and
      score_recap_only (a summary that is mostly score restatement with fewer
      than two evidence-fact sentences — the "reads like a score recap" class).

    ``available_eids`` is the count of distinct E-IDs in the client's own
    evidence bundle (evidence.json). under_cited is a DEFECT only when the SCQA
    cites <2 DESPITE the client having >=2 to cite; a genuinely thin bundle
    (<2 E-IDs corpus-wide — e.g. bell-bank's single evidence row) citing all it
    has is an honest floor, not an under-citation, and fabricating a second id
    to clear the check would violate the no-invented-evidence mandate.
    """
    c: Counter = Counter()
    bad: list[str] = []
    scqa = str((ov.get("narrative") or {}).get("scqa_md")
               or (ov.get("scqa") or {}).get("body_md")
               or ov.get("scqa_md") or "")
    if not scqa.strip():
        c["missing"] += 1
        return c, bad
    c["exec_summaries"] += 1
    checks = (
        ("double_space", _EXEC_DOUBLE_SPACE_RE),
        ("orphan_punct", _EXEC_ORPHAN_PUNCT_RE),
        ("missing_space_after_period", _EXEC_MISSING_SPACE_RE),
        ("stray_ellipsis", _EXEC_ELLIPSIS_RE),
        ("emoji", _EXEC_EMOJI_RE),
        ("article_error", _EXEC_ARTICLE_RE),
        ("shout_label", _EXEC_SHOUT_RE),
        ("meta_leak", _EXEC_META_RE),
    )
    for code, rx in checks:
        if rx.search(scqa):
            c[code] += 1
            bad.append(f"{code}: …{(rx.search(scqa).group(0) or '')[:40]}")
    if len(set(_EXEC_EID_RE.findall(scqa))) < 2 and (
            available_eids is None or available_eids >= 2):
        c["under_cited"] += 1
        bad.append("under_cited: <2 distinct E-IDs")
    # score-recap-only: mostly score restatement, <2 evidence-fact sentences.
    sents = [s for s in re.split(r"(?<=[.!?])\s+", scqa) if s.strip()]
    score_s = sum(1 for s in sents
                  if _EXEC_SCORE_RE.search(s) and not _EXEC_FACT_RE.search(s))
    fact_s = sum(1 for s in sents if _EXEC_FACT_RE.search(s))
    density = score_s / max(1, len(sents))
    if density >= 0.5 and fact_s < 2:
        c["score_recap_only"] += 1
        bad.append(f"score_recap_only: {density:.0%} score sents, {fact_s} facts")
    # platform_fit_stale (quality ratchet, 2026-07-15): the exec summary's
    # synthetic clause cites "(N/100 fit)" for the lead platform. When a KEPT
    # summary froze that clause after the fit engine changed, N diverged from the
    # platform tab (Sunflower shipped "22/100" when the corrected lead fit was
    # 52). The composer now recomposes an offside clause; this gate FAILS the
    # deploy if any exec summary's cited fit still disagrees with the rank-1
    # platform card, so a regression can never ship silently.
    _lead_fit = _lead_platform_fit(platforms)
    _m_fit = _EXEC_FIT_NUM_RE.search(scqa)
    if _m_fit and _lead_fit is not None and abs(int(_m_fit.group(1)) - round(_lead_fit)) > 1:
        c["platform_fit_stale"] += 1
        bad.append(f"platform_fit_stale: cites {_m_fit.group(1)}/100, "
                   f"lead card is {round(_lead_fit)}/100")
    return c, bad


def check_evidence_surface(client_dir: pathlib.Path) -> tuple[Counter, list[str]]:
    c: Counter = Counter()
    p = client_dir / "evidence.json"
    if p.exists():
        try:
            items = json.loads(p.read_text()).get("items") or []
            c["evidence_rows"] += len(items)
            c["evidence_surface_present"] += 1
        except Exception:
            c["evidence_surface_broken"] += 1
    else:
        c["evidence_surface_missing"] += 1
    return c, []


# ── ceilings for --strict (aggregate across the whole pack) ─────────────
# Baselined 2026-07-06 pre-remediation; each remediation wave lowers its
# family's ceiling toward 0 as the fix lands + regen proves it.
CEILINGS: dict[str, int] = {
    "why_now.dup_pairs": 0,
    "recs.fragment_titles": 0,
    "recs.untitled": 0,
    "issues.blank_titles": 0,
    "issues.filename_or_meta_titles": 0,
    "issues.meta_rows_served": 0,
    "narr.punct_debris": 0,
    "fin.series_outliers": 0,
    "fin.sentiment_fragments": 0,
    "plat.story_null": 0,            # platform v3 dossier floor lands story_md on every card
    "tl.tl_non_clay": 0,             # thought leadership is Clay-only — no derived/INTERNAL items
    "evid.evidence_surface_missing": 94,  # drops to 0 with the drawer fix
    # exec-summary (SCQA) typo/flow family — every code ceiling 0. The composer's
    # final proofread pass removes them all, so a redeploy whose exec summaries
    # still carry any of these fails the audit (operator report 2026-07-06).
    "exec_summary.double_space": 0,
    "exec_summary.orphan_punct": 0,
    "exec_summary.missing_space_after_period": 0,
    "exec_summary.stray_ellipsis": 0,
    "exec_summary.emoji": 0,
    "exec_summary.article_error": 0,
    "exec_summary.shout_label": 0,
    "exec_summary.meta_leak": 0,
    "exec_summary.under_cited": 0,
    "exec_summary.score_recap_only": 0,
    # quality ratchet: the exec summary's cited platform-fit number must match
    # the rank-1 platform card — a stale KEPT clause fails the deploy.
    "exec_summary.platform_fit_stale": 0,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pack", default=None, help="startup-data dir")
    ap.add_argument("--json", default=None, help="write full JSON report")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    pack = pathlib.Path(args.pack) if args.pack else (
        pathlib.Path(__file__).resolve().parents[3] / "startup-data")
    clients_dir = pack / "clients"
    if not clients_dir.is_dir():
        print(f"ERROR: no pack at {pack}", file=sys.stderr)
        return 2

    agg: Counter = Counter()
    offenders: dict[str, list[str]] = {}
    per_client: dict[str, dict[str, int]] = {}

    def _load(d: pathlib.Path, name: str) -> dict:
        p = d / f"{name}.json"
        try:
            return json.loads(p.read_text()) if p.exists() else {}
        except Exception:
            return {}

    clients = sorted(p for p in clients_dir.iterdir() if p.is_dir())
    for cdir in clients:
        ov, ins = _load(cdir, "overview"), _load(cdir, "insights")
        cx = _load(cdir, "context")
        pl, rd = _load(cdir, "platforms"), _load(cdir, "platforms_roadmap")
        # Distinct E-IDs the client's SCQA COULD cite (its own evidence
        # bundle) — under_cited is scored against what's available, so a
        # single-evidence-row client is an honest floor, not a defect.
        ev_items = (_load(cdir, "evidence").get("items") or [])
        avail_eids = len({
            e for it in ev_items if isinstance(it, dict)
            for e in [str(it.get("e_id") or it.get("eid") or "")]
            if _EXEC_EID_RE.fullmatch(e)
        })
        rows: Counter = Counter()
        for prefix, (cnt, bad) in {
            "why_now": check_why_now(ov),
            "recs": check_recs(rd if rd else pl),
            "issues": check_issues(cx),
            "narr": check_narratives(ov, ins),
            "fin": check_financial(ov, cx),
            "plat": check_platform(pl),
            "tl": check_thought_leadership(ov),
            "exec_summary": check_exec_summary(ov, available_eids=avail_eids,
                                                platforms=pl),
            "evid": check_evidence_surface(cdir),
        }.items():
            for k, v in cnt.items():
                rows[f"{prefix}.{k}"] += v
            if bad:
                offenders.setdefault(cdir.name, []).extend(
                    f"{prefix}: {b}" for b in bad[:6])
        agg.update(rows)
        per_client[cdir.name] = dict(rows)

    print(f"# qa_deploy_review_audit: {len(clients)} clients @ {pack}")
    for k in sorted(agg):
        print(f"  {k:42s} {agg[k]}")
    failures = [
        (k, agg.get(k, 0), lim) for k, lim in CEILINGS.items()
        if agg.get(k, 0) > lim
    ]
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps({
            "aggregate": dict(agg), "per_client": per_client,
            "offenders": offenders,
            "failures": [{"metric": k, "value": v, "ceiling": c}
                         for k, v, c in failures],
        }, indent=1))
        print(f"# full report → {args.json}")
    if failures:
        print("# CEILING BREACHES:")
        for k, v, lim in failures:
            print(f"  FAIL {k}: {v} > {lim}")
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
