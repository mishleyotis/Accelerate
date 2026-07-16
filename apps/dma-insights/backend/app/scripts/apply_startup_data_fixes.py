"""Offline (no-DB) regenerator for the committed `startup-data` snapshot.

The canonical path is the DB reparse (`run_derive_chain` → `export_startup_pages`),
but it needs Postgres. This script applies the SAME deterministic enrichment —
via the shared pure helpers in `app/services/startup_enrich.py` — directly to the
per-client JSON files, so the committed snapshot improves and matches what the
deploy reparse will produce. Every value is derived from data already in the
snapshot (firmographics / financial_highlights / insight cards / platform cards);
nothing is fabricated, and the pass is idempotent (fill-missing / fix-broken).

Drives the `qa_startup_audit` hard-check defects toward zero; run that before and
after to verify all 94 are covered.

Usage:
  python -m app.scripts.apply_startup_data_fixes [--clients-dir DIR] [--dry-run]
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
from collections import defaultdict

try:
    from app.services import startup_enrich as se
    from app.services.text_hygiene import opportunity_reframe as _reframe
    from app.services.text_hygiene import scrub_md as _scrub_md
except ImportError:  # pragma: no cover
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from app.services import startup_enrich as se
    from app.services.text_hygiene import opportunity_reframe as _reframe
    from app.services.text_hygiene import scrub_md as _scrub_md


def _dejargon(v: object) -> object:
    """S1+S2 belt-and-braces: strip residual internal jargon / raw taxonomy
    codes (S1) AND reframe accusatory/deficit phrasing as opportunity language
    (S2) from a user-facing narrative string — citation-safe (text_hygiene
    protects [E-###] chips) and clean-posture-safe (a "no breaches" fact is
    never turned into an "opportunity"). Non-strings/empties pass through. Runs
    as the LAST deterministic pack pass so no surface ships raw codes or
    accusatory copy regardless of what the derive/deepen/enrich steps produced;
    the Stage-2 Claude overlay supplies the nuanced report-grounded rewrite."""
    if isinstance(v, str) and v.strip():
        out = _scrub_md(v)
        out = _reframe(out if out is not None else v)
        return out if out else v
    return v

# ── Evidence-chip resolvability + str(dict) prose (Cluster A) ────────────────
# The live "evidence drawer empty everywhere" symptom traces to narrative
# surfaces citing E-IDs that are NOT in the client's own evidence corpus —
# DOCX-scheme fabrications (E-500/E-607…) and scheme-mismatch clients whose
# research evidence (E-001…) was never persisted alongside the E-INT-#### rows.
# A chip that resolves to nothing is worse than no chip, so this belt (a) never
# ships a citation whose E-ID is absent from the client's evidence.json, and
# (b) renders a recommendation solution dict that leaked as `str(dict)` into a
# text field back to prose. It is the last-resort floor; the upstream corpus
# population is tracked separately.
# ONE citation grammar with deepen_narrative._SCQA_EID_RE / the exec-summary
# audit — the narrow prior form treated scheme-variant ids the corpus really
# carries ("E-P1C1-014") as dead and stripped them (2026-07-13: under_cited=5
# regression when the belt ran after the restyle pass).
_EID_TOKEN_RE = re.compile(
    r"(?:EV|INT|E)(?:-[A-Za-z0-9]{1,6})*-\d{1,4}|E\d{3,4}")
# Suffix-aware variant for EXTRACTION: matches the whole id including
# revision/variant suffixes ("E-025-REVISED", "E-012-B") so validity checks
# compare the exact corpus id, never a truncated base.
_EID_FULL_RE = re.compile(
    r"(?:E-(?:INT-)?|EV-|INT-)\d{1,4}(?:-[A-Za-z0-9]+)*")
_CITE_GROUP_RE = re.compile(r"\[([^\[\]]*?E-[^\[\]]*?)\]")
_TEXT_FIELDS = frozenset((
    "what_text", "why_text", "so_what_text", "body", "observation", "md",
    "narrative", "scqa_md", "story_md", "opportunity_md", "rationale",
    "note", "summary", "detail", "so_what", "what", "why",
))
_EID_ARRAY_KEYS = frozenset((
    "linked_e_ids", "e_ids", "evidence_ids", "cited_e_ids", "eids",
    "grounding_evidence_ids", "evidence_e_ids", "counter_evidence_ids",
))


def _valid_eids_for_client(cdir: str) -> set:
    ev = _load(os.path.join(cdir, "evidence.json")) or {}
    out = set()
    for it in (ev.get("items") or []):
        e = (it or {}).get("e_id")
        if isinstance(e, str) and e.strip():
            out.add(e.strip())
    return out


def _eid_base(e: object) -> str | None:
    if not isinstance(e, str):
        return None
    m = _EID_TOKEN_RE.match(e.strip())
    return m.group(0) if m else None


_SOL_RE = re.compile(r"['\"](?:solution|name)['\"]\s*:\s*['\"]([^'\"]+)['\"]")
_FIT_RE = re.compile(r"['\"]fit['\"]\s*:\s*['\"]([^'\"]+)")


def _tidy_prose(text: str) -> str:
    """Repair whitespace/punctuation debris left after removing a dead chip."""
    # a chip removed from inside brackets/parens leaves "[,", ", )", "[, ."
    # (2026-07-13 deploy-review punct_debris class) — strip the leftovers
    # BEFORE the empty-container repairs so "[, ]" collapses fully.
    text = re.sub(r"\[\s*[,;]+\s*\]", "", text)   # "[,]" fully emptied
    text = re.sub(r"\(\s*[,;]+\s*\)", "", text)   # "(,)"
    text = re.sub(r"\[\s*[,;]+\s*", "[", text)    # "[, xxx]" → "[xxx]"
    text = re.sub(r"\(\s*[,;]+\s*", "(", text)    # "(, xxx)" → "(xxx)"
    text = re.sub(r"\s*[,;]+\s*\]", "]", text)    # "[xxx, ]" → "[xxx]"
    text = re.sub(r"\s*[,;]+\s*\)", ")", text)    # "(xxx, )" → "(xxx)"
    text = re.sub(r"\(\s*\)", "", text)          # emptied parens
    text = re.sub(r"\[\s*\]", "", text)          # emptied brackets
    text = re.sub(r"\[\s*(?=[.,;])", "", text)    # orphan "[" before punct
    text = re.sub(r"(?<=[\w)\]])\.\.(?!\.)", ".", text)  # ".." (not "...")
    text = re.sub(r"\s+([.,;:)])", r"\1", text)  # space before punctuation
    text = re.sub(r"\(\s+", "(", text)           # space after (
    text = re.sub(r"[ \t]{2,}", " ", text)        # collapsed runs
    return text.strip()


def _render_dict_prose(v: str) -> str:
    """A recommendation solution dict str()'d into a text field —
    e.g. ``{'solution': 'MuleSoft Anypoint', 'fit': 'Excellent — …'}`` —
    rendered to prose (solution + fit). Handles a TRUNCATED repr (cut at a char
    cap, so ``literal_eval`` fails) via a regex fallback. Non-dict strings pass
    through."""
    s = v.lstrip()
    if not s.startswith(("{'", '{"')):
        return v
    sol = fit = ""
    try:
        d = ast.literal_eval(s)
        if isinstance(d, dict):
            sol = str(d.get("solution") or d.get("name") or "").strip()
            fit = str(d.get("fit") or "").strip()
    except (ValueError, SyntaxError):
        pass
    if not (sol or fit):  # truncated/malformed repr — extract by regex
        ms, mf = _SOL_RE.search(s), _FIT_RE.search(s)
        sol = ms.group(1).strip() if ms else ""
        fit = mf.group(1).strip() if mf else ""
    if sol and fit:
        prose = fit if fit.lower().startswith(sol.lower()) else f"{sol} — {fit}"
    elif sol:
        prose = sol
    else:
        return v
    # A source-truncated fit can end mid-word: trim back to the last complete
    # clause so we never ship a dangling fragment.
    if prose and prose[-1] not in ".!?":
        cut = max(prose.rfind("."), prose.rfind(";"), prose.rfind("—"))
        if cut > 40:
            prose = prose[:cut + 1].rstrip("—; ").rstrip() or prose
    return _tidy_prose(prose)


def _strip_dead_cites(text: str, valid: set) -> str:
    """Drop bracketed ``[E-…]`` citation groups whose E-IDs don't resolve in the
    client's evidence corpus; keep the resolvable ones; drop an emptied group.

    Extraction uses the FULL-id pattern (suffix-aware): ``[E-025-REVISED]``
    must be validated as "E-025-REVISED" (a real corpus row), not truncated
    to "E-025" and stripped as dead (2026-07-11 parity audit)."""
    def _repl(m: re.Match) -> str:
        inner = m.group(1)
        eids = _EID_FULL_RE.findall(inner)
        if not eids:
            return m.group(0)  # not a citation group after all
        kept = [e for e in eids if e in valid or _eid_base(e) in valid]
        if len(kept) == len(eids):
            return m.group(0)  # all resolve — leave verbatim
        if not kept:
            return ""  # all dead — drop the whole chip
        return "[" + ", ".join(kept) + "]"
    return _CITE_GROUP_RE.sub(_repl, text)


def _walk_reconcile(o: object, valid: set, stats: dict) -> bool:
    changed = False
    if isinstance(o, dict):
        for k, v in list(o.items()):
            if isinstance(v, str) and v:
                nv = v
                if k in _TEXT_FIELDS:
                    r = _render_dict_prose(nv)
                    if r != nv:
                        nv = r
                        stats["dict_prose_rendered"] += 1
                if valid and "E-" in nv:
                    s = _strip_dead_cites(nv, valid)
                    if s != nv:
                        nv = _tidy_prose(_scrub_md(s) or s)
                        stats["dead_cites_stripped"] += 1
                if k in _TEXT_FIELDS:
                    # debris left by a PRIOR run's chip removal ("[,", ", )",
                    # "]..") ships in the committed pack — repair
                    # unconditionally, not only when a chip dies this run.
                    t = _tidy_prose(nv)
                    if t != nv:
                        nv = t
                        stats["prose_debris_tidied"] += 1
                if nv != v:
                    o[k] = nv
                    changed = True
            elif k in _EID_ARRAY_KEYS and isinstance(v, list) and valid:
                # Keep when the EXACT id OR its base resolves. Exact: suffixed
                # ids are real corpus rows ("E-025-REVISED" ships verbatim in
                # Manasquan's evidence_index; the base-only lookup dropped
                # them as dead — 2026-07-11 parity audit). Base: facet
                # notation ("E-041:F2") cites a valid row's fragment. Entries
                # that don't look like E-IDs at all stay untouched.
                new = [e for e in v
                       if not (isinstance(e, str) and _eid_base(e)
                               and e.strip() not in valid
                               and _eid_base(e) not in valid)]
                if len(new) != len(v):
                    o[k] = new
                    stats["dead_eid_dropped"] += len(v) - len(new)
                    changed = True
            elif _walk_reconcile(v, valid, stats):
                changed = True
    elif isinstance(o, list):
        for x in o:
            if _walk_reconcile(x, valid, stats):
                changed = True
    return changed


def _reconcile_evidence(cdir: str, dry: bool, stats: dict) -> None:
    """Per-client belt: no narrative surface ships a citation whose E-ID is
    absent from the client's evidence.json, and no str(dict) leaks as prose."""
    valid = _valid_eids_for_client(cdir)
    for f in ("overview.json", "insights.json", "platforms.json", "heatmap.json",
              "heatmap_category.json", "focus_areas.json", "context.json",
              "health.json"):
        p = os.path.join(cdir, f)
        obj = _load(p)
        if obj is None:
            continue
        if _walk_reconcile(obj, valid, stats):
            _write(p, obj, dry)


_DEFAULT_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "startup-data", "clients"))
_TEMPLATE_RE = re.compile(r"scores [\d.]+ out of 5.*?(lowest|next-lowest) capability area", re.I | re.S)
_BROKEN_SCQA_RE = re.compile(r"strengths:\s*\(\d|starting with\s*,|\(\d\.\d\)\s*,\s*\(\d|gaps[^.]*:\s*\(\d")


def _load(p):
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        return json.load(fh)


def _write(p, obj, dry):
    if dry:
        return
    with open(p, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _enrich_firmographics(firm: dict, stats: dict, subvertical: str | None = None) -> None:
    # Sanitize fabricated/garbled values FIRST (null garbage → honest blank): the
    # audit's $103T / "$21M" AUM, regulator="Role", headcount=16, dict-repr and
    # footprint fragments. The fill-missing logic then runs on clean inputs.
    n = se.sanitize_firmographics(firm, subvertical)
    if n:
        stats["firm_sanitized"] += n
    fh = firm.get("financial_highlights") or {}
    if not firm.get("trend"):
        t = se.derive_trend(fh)
        if t:
            firm["trend"] = t
            stats["trend"] += 1
    if not firm.get("cagr"):
        c = se.derive_cagr(fh)
        if c:
            firm["cagr"] = c
            stats["cagr"] += 1
    if not firm.get("footprint"):
        fp = se.derive_footprint(firm.get("geography"))
        if fp:
            firm["footprint"] = fp
            stats["footprint"] += 1
    if not firm.get("branches"):
        b = se.derive_branches(fh)
        if b:
            firm["branches"] = b
            stats["branches"] += 1


def _enrich_leadership(firm: dict, stats: dict) -> None:
    ld = firm.get("leadership") or []
    out = []
    for p in ld:
        if not se.is_person_name(p.get("name")) and not se.leadership_flags(
                p.get("title"), p.get("tenure"), p.get("name"))["gap_flag"]:
            stats["garbage_dropped"] += 1
            continue  # drop subcap-id / junk rows (keep legitimate gap rows)
        flags = se.leadership_flags(p.get("title"), p.get("tenure"), p.get("name"))
        if "critical_role" not in p:
            p.update(flags)
            stats["leader_flags"] += 1
        out.append(p)
    firm["leadership"] = out


_POS_LABELS = sorted({
    "corporate & investment bank", "wealth & advisory firm",
    "real-estate investment trust", "insurance carrier", "insurance broker",
    "asset manager", "regional bank", "credit union", "farm-credit institution",
    "commercial lender", "mutual insurer", "brokerage", "insurance MGA",
    "payments system operator"}, key=len, reverse=True)


def _relabel_positioning(txt: str, correct: str | None) -> str:
    """Swap a mislabeled entity-type in the POSITIONING sentence (REIT shown as
    'asset manager', brokerage as 'wealth & advisory firm', etc.)."""
    if not correct:
        return txt
    for lbl in _POS_LABELS:
        if lbl.lower() == correct.lower():
            continue
        pat = re.compile(r"(\bis an?\b(?:\s+\$[\d.]+[BMT])?\s+)" + re.escape(lbl), re.I)
        if pat.search(txt):
            return pat.sub(lambda m: m.group(1) + correct, txt, count=1)
    return txt


def _enrich_signals(ov: dict, ev_map: dict, stats: dict,
                    name: str | None = None, subvertical: str | None = None) -> None:
    sigs = ov.get("why_now_signals") or []
    fin_eids = ev_map.get("__financial__", [])
    cleaned: list = []
    for s in sigs:
        before = s.get("text") or ""
        # de-double-prefix ("F-001: F-001 |"), scrub methodology boilerplate, and
        # clip without mid-word truncation.
        txt = se.scrub_placeholder_text(
            se.clip_clean(se.strip_boilerplate(se.dedupe_prefix(before)), 260))
        if s.get("kind") == "POSITIONING":
            relabeled = _relabel_positioning(txt, se.subvertical_label(name, subvertical))
            if relabeled != txt:
                txt = relabeled
                stats["wn_relabeled"] += 1
        if txt != before:
            stats["wn_cleaned"] += 1
        s["text"] = txt
        # drop signals that are pure methodology/section labels ("2 Top Findings:",
        # "…flow directly into the Handoff Package") — they are not "why now".
        if se.is_methodology_only(txt):
            stats["wn_dropped_boilerplate"] += 1
            continue
        # Ground only where a real link exists: a GAP signal's subcap, or a
        # FINANCIAL signal's financial-highlight E-IDs. Firmographic POSITIONING
        # signals carry no subcap link → left honestly without evidence chips.
        if not s.get("evidence"):
            sub = s.get("subcap_id")
            if sub:
                ev = se.eids_for([sub], ev_map)
                if ev:
                    s["evidence"] = ev
                    stats["wn_evidence"] += 1
            elif s.get("kind") == "FINANCIAL" and fin_eids:
                s["evidence"] = fin_eids[:4]
                stats["wn_evidence"] += 1
        cleaned.append(s)
    # near-identical signal texts communicate nothing distinct — differentiate
    # via each signal's own facts or suppress the weaker duplicate (the SAME
    # shared rule deepen_narrative applies, so pack and live converge).
    deduped = se.dedupe_why_now_signals(cleaned)
    if len(deduped) != len(cleaned):
        stats["wn_deduped"] += len(cleaned) - len(deduped)
    cleaned = deduped
    # the firmographic POSITIONING restatement is a description, not a trigger —
    # demote it to last when there are >=3 real signals to lead with.
    pos = [s for s in cleaned if s.get("kind") == "POSITIONING"]
    non_pos = [s for s in cleaned if s.get("kind") != "POSITIONING"]
    if pos and len(non_pos) >= 3:
        cleaned = non_pos + pos
        stats["wn_positioning_demoted"] += 1
    ov["why_now_signals"] = cleaned


# Finding composition delegates to the SHARED helpers in startup_enrich, so this
# offline patcher and the canonical deepen_narrative build findings from identical
# logic (no drifting second copy). The dict-shaped wrappers keep the call sites
# below terse.
def _norm(s: object) -> str:
    return se.norm(s)


def _score_clause(f: dict, key: object = None) -> str:
    return se.score_clause(f.get("score"), f.get("peer_median"), seed_key=key)


def _compose_finding_body(f: dict, is_gap: object, key: object = None) -> str:
    return se.compose_finding_body(f.get("name"), f.get("subcap_id"),
                                   f.get("score"), f.get("peer_median"), is_gap,
                                   client_key=key)


def _reframe_non_gap(body: str, f: dict) -> str:
    return se.reframe_non_gap(body, f.get("name"), f.get("subcap_id"),
                              f.get("score"), f.get("peer_median"))


def _enrich_findings(ov: dict, ev_map: dict, cards: list, insight_by_cat: dict, stats: dict) -> None:
    kept: list = []
    for f in ov.get("top_findings") or []:
        body = se.repair_citations(se.strip_boilerplate(f.get("body") or ""))
        cat = f.get("subcap_id")
        ins = insight_by_cat.get(se.category_of(cat) or cat)
        is_gap = se.is_true_gap(f.get("score"), f.get("peer_median"))
        # de-template: lead with the matching insight's analyst prose; else
        # compose a non-template, grounded body from the finding's own fields.
        if _TEMPLATE_RE.search(body):
            lead = se.strip_boilerplate((ins.get("what_text") or "").strip()) if ins else ""
            _ck = ((ov.get("entity") or {}).get("display_id")
                   or ov.get("entity_display_id"))
            body = ((lead + _score_clause(f, _ck)) if len(lead) >= 80
                    else _compose_finding_body(f, is_gap, _ck))
            stats["tf_detemplated"] += 1
        # COHERENCE: a clean analyst name is KEPT; only a non-finding name (a bare
        # label "F-003", a "<LABEL> | NAME | …" pipe-leak, a section header, or a
        # placeholder) is realigned to the body's capability — via the SAME robust
        # extractors the canonical pipeline uses, never the raw leading_capability
        # (which would re-capture the pipe label). Fixes the title↔body mismatch
        # without corrupting an already-correct name on reparse.
        if se.is_nonfinding_name(f.get("name")):
            proper = (se.finding_pipe_name(body) or se.finding_subject_phrase(body)
                      or se.leading_capability(body))
            if proper and not se.is_nonfinding_name(proper):
                f["name"] = proper
                stats["tf_retitled"] += 1
        # GAP-DIRECTION: never frame an at/above-peer capability as a gap.
        if is_gap is False:
            body = _reframe_non_gap(body, f)
            stats["tf_gap_reframed"] += 1
        # NON-FINDING: a finding still badly named (label/placeholder/header) → drop.
        if se.is_nonfinding_name(f.get("name")):
            stats["tf_placeholder_dropped"] += 1
            continue
        f["body"] = body[:600]
        if not f.get("evidence") and cat:
            ev = se.eids_for([cat], ev_map)
            if not ev and ins:
                ev = list(ins.get("linked_e_ids") or [])[:4]
            if ev:
                f["evidence"] = ev
                stats["tf_evidence"] += 1
        if not f.get("platforms"):
            plats, rationale = se.platforms_for_finding(cards, cat)
            if plats:
                f["platforms"] = plats
                f["platform_rationale"] = rationale
                stats["tf_platforms"] += 1
        # S1 de-jargon: final scrub of every narrative field (citation-safe).
        for _k in ("body", "what", "why", "so_what", "title", "platform_rationale"):
            if _k in f:
                _nv = _dejargon(f.get(_k))
                if _nv != f.get(_k):
                    f[_k] = _nv
                    stats["s1_finding_scrub"] += 1
        kept.append(f)
    ov["top_findings"] = kept


def _fix_scqa(ov: dict, stats: dict) -> None:
    nar = ov.get("narrative")
    if not isinstance(nar, dict):
        return
    s0 = nar.get("scqa_md") or ""
    # 1) strip leaked pre-write worksheet scaffolding + repair broken inline
    # citations ('[]', '[E--001]') BEFORE the quality gate — a long but
    # scaffolded SCQA must not pass as "fine".
    s = se.scrub_placeholder_text(se.repair_citations(se.strip_scqa_scaffolding(s0)))
    if s and s != s0:
        nar["scqa_md"] = s
        stats["scqa_descaffolded"] += 1
    paras = [p for p in re.split(r"\n\s*\n", s) if len(p.strip()) > 40]
    broken = bool(_BROKEN_SCQA_RE.search(s))
    # A compact strengths-led summary (no-true-gaps clients) is legitimately
    # ~300 chars; a cited, multi-paragraph, unbroken text must NOT be
    # flattened into the zero-citation fallback composer (2026-07-13:
    # sl-green under_cited regression).
    short = len(paras) < 2 or len(s) < 300
    if not (broken or short):
        return
    if not broken and len(s) >= 600:
        nar["scqa_md"] = se.reparagraph(s, target=3)
        stats["scqa_reparagraphed"] += 1
        return
    ent = ov.get("entity") or {}
    nar["scqa_md"] = se.compose_scqa(
        ent.get("name") or (ov.get("firmographics") or {}).get("legal_name") or "The institution",
        ov.get("firmographics") or {}, ov.get("overall_score"),
        ent.get("subvertical"), ov.get("top_findings") or [],
        client_key=ent.get("display_id") or ov.get("entity_display_id"))
    stats["scqa_recomposed"] += 1


def _enrich_platforms(pl: dict, ev_map: dict, stats: dict,
                      tech_items: list | None = None,
                      entity_name: str | None = None) -> None:
    from app.services.platform_dossier import compose_dossier
    # Pillar → E-IDs (and a flat fallback) from the offline evidence map.
    by_pillar: dict = defaultdict(list)
    flat: list = []
    for k, v in ev_map.items():
        for e in v:
            if e not in flat:
                flat.append(e)
            if len(k) >= 2 and k[0] in "Pp" and k[1].isdigit() and e not in by_pillar[k[:2]]:
                by_pillar[k[:2]].append(e)
    for c in pl.get("cards") or []:
        if not c.get("opportunity_md"):
            md = se.compose_opportunity_md(c, entity_key=entity_name)
            if md:
                c["opportunity_md"] = md
                stats["opportunity_md"] += 1
        if not c.get("evidence_ids"):
            ev = (by_pillar.get(c.get("pillar")) or flat)[:6]
            if ev:
                c["evidence_ids"] = ev
                stats["oss_evidence"] += 1
        # Deterministic dossier floor (platform v3): the always-ships,
        # evidence-rich narrative. A validated Gemini story (story_source
        # 'vertex') is never overwritten — validator-gated uplift.
        if not (c.get("story_md") or "").strip():
            dout = compose_dossier(c, techstack_items=tech_items,
                                   entity_name=entity_name)
            if dout.get("story_md"):
                c["story_md"] = dout["story_md"]
                c["story_source"] = dout["story_source"]
                c["dossier"] = dout["dossier"]
                c["narrative_provenance"] = dout["narrative_provenance"]
                stats["story_md"] += 1
        elif not c.get("dossier"):
            # Story already present (vertex) — still attach the structured
            # dossier + provenance for the D4 panel.
            dout = compose_dossier(c, techstack_items=tech_items,
                                   entity_name=entity_name)
            c["dossier"] = dout["dossier"]
            c["narrative_provenance"] = dout["narrative_provenance"]
            stats["dossier_only"] += 1


def _enrich_insights(ins: dict, stats: dict) -> None:
    for it in ins.get("items") or []:
        # S1 de-jargon: final scrub of the card's user-facing narrative fields.
        for _k in ("what_text", "why_text", "so_what_text", "title"):
            _nv = _dejargon(it.get(_k))
            if _nv != it.get(_k):
                it[_k] = _nv
                stats["s1_insight_scrub"] += 1
        if not it.get("pillar"):
            p = se.pillar_of(it.get("linked_subcap_id"))
            if p:
                it["pillar"] = p
                stats["ins_pillar"] += 1
        if not it.get("flag"):
            it["flag"] = se.flag_from_severity(it.get("severity"))
            stats["ins_flag"] += 1


def _flag_contamination(ov: dict, slug: str, stats: dict, remediation: list) -> None:
    """Detect wrong-entity (source-misattribution) contamination and apply the
    chosen handling: an 'unverified-source' data_quality BADGE (so a confidently-
    wrong assessment never renders unflagged), null the corroborated-foreign
    SCALAR field (a ticker that is the OTHER institution's symbol), and record the
    entity for the re-ingest remediation report. The wrong-company narrative is
    not recoverable offline, so it is flagged-not-deleted — the badge is the honest
    signal and re-ingest of the correct package is the real correction.

    Badge + nulling live in the SHARED twin ``se.apply_contamination_badge``
    (the live overview route runs the same function, so pack==live on the
    badge — qa_pack_parity structural contract); this wrapper keeps the
    patcher-only stats + remediation report. Idempotent on a pack whose
    route already stamped the badge (same signals ⇒ same values)."""
    firm = ov.get("firmographics") or {}
    had_ticker = bool(firm.get("ticker") or firm.get("stock_ticker"))
    tier = se.apply_contamination_badge(ov)
    if not tier:
        return
    ent = ov.get("entity") or {}
    name = ent.get("name") or firm.get("legal_name") or ""
    remediation.append({"slug": slug, "name": name, "tier": tier,
                        "markers": (ov.get("data_quality") or {})
                        .get("misattribution_markers")})
    if tier == "A":
        if had_ticker and not (firm.get("ticker") or firm.get("stock_ticker")):
            stats["contam_ticker_nulled"] += 1
        stats["contam_tier_a"] += 1
    else:
        stats["contam_tier_b"] += 1


_NO_LEAD_RE = re.compile(
    r"^\s*(?:No|Not|Lack of|Lacks|Absence of|Absent|Missing)\s+(.+)$", re.I)


def _reframe_opportunity(title: str) -> str:
    """Accusatory 'No X' / 'Lack of X' headline → neutral opportunity framing
    (plan S2/S9): 'No Enterprise Integration Platform' → 'Opportunity: Enterprise
    Integration Platform'. A trailing ': stat' / '. detail' clause is dropped so
    the headline stays a crisp key message, never accusatory."""
    m = _NO_LEAD_RE.match(title or "")
    if not m:
        return title
    subject = re.split(r"[.:]", m.group(1), maxsplit=1)[0].strip().rstrip(" -\u2013\u2014")
    return f"Opportunity: {subject}" if len(subject) > 2 else title


def _scrub_titles(cdir: str, dry: bool, stats: dict) -> None:
    """S14 issue headlines + S9 focus titles: strip residual jargon from issue
    titles (straight-to-the-point headlines — the 'Capability gap:' synth is
    dropped in derive_issues) and reframe accusatory 'No X' focus-area titles as
    opportunities. Rationale-fill + full validity land in the WAVE-2 overlay."""
    cp = os.path.join(cdir, "context.json")
    ctx = _load(cp)
    if ctx and ctx.get("issue_register"):
        changed = False
        for it in ctx["issue_register"]:
            nv = _dejargon(it.get("title"))
            if nv != it.get("title"):
                it["title"] = nv
                changed = True
                stats["s14_issue_title_scrub"] += 1
        if changed:
            _write(cp, ctx, dry)
    fp = os.path.join(cdir, "focus_areas.json")
    fa = _load(fp)
    if fa and fa.get("items"):
        changed = False
        for it in fa["items"]:
            t0 = it.get("title") or ""
            t1 = _reframe_opportunity(t0)
            t1 = _dejargon(t1) or t1
            if t1 != t0:
                it["title"] = t1
                changed = True
                stats["s9_focus_title_reframe"] += 1
            # The verbatim_quote is grounding, but a "Zero CRM …" / "No MuleSoft
            # detected" lead reads accusatory — reframe the TONE while the
            # opportunity_reframe keeps every number/name/citation verbatim.
            for qk in ("verbatim_quote", "quote"):
                q0 = it.get(qk)
                if isinstance(q0, str) and q0.strip():
                    q1 = _reframe(q0)
                    if q1 and q1 != q0:
                        it[qk] = q1
                        changed = True
                        stats["s9_focus_quote_reframe"] += 1
        if changed:
            _write(fp, fa, dry)


def process_client(cdir: str, dry: bool, stats: dict, remediation: list) -> None:
    ov_p, pl_p, in_p = (os.path.join(cdir, f) for f in ("overview.json", "platforms.json", "insights.json"))
    ov, pl, ins = _load(ov_p), _load(pl_p), _load(in_p)
    tech = _load(os.path.join(cdir, "techstack.json"))
    tech_items = (tech or {}).get("items") or []
    insight_items = (ins or {}).get("items") or []
    firm = (ov or {}).get("firmographics") or {}
    ev_map = se.subcap_evidence_map(insight_items, (firm.get("financial_highlights") or {}).get("lines"))
    cards = (pl or {}).get("cards") or []
    insight_by_cat: dict = {}
    for it in insight_items:
        cat = se.category_of(it.get("linked_subcap_id"))
        if cat and cat not in insight_by_cat and (it.get("what_text") or ""):
            insight_by_cat[cat] = it

    if ov:
        ent = ov.get("entity") or {}
        subv = ent.get("subvertical")
        name = ent.get("name") or firm.get("legal_name")
        _enrich_firmographics(firm, stats, subv)
        _enrich_leadership(firm, stats)
        _enrich_signals(ov, ev_map, stats, name, subv)
        _enrich_findings(ov, ev_map, cards, insight_by_cat, stats)
        _fix_scqa(ov, stats)
        _flag_contamination(ov, os.path.basename(cdir.rstrip("/")), stats, remediation)
        _write(ov_p, ov, dry)
    if pl:
        _ent = (ov or {}).get("entity") or {}
        _ename = _ent.get("name") or firm.get("legal_name")
        _enrich_platforms(pl, ev_map, stats, tech_items, _ename)
        _write(pl_p, pl, dry)
    if ins:
        _enrich_insights(ins, stats)
        _write(in_p, ins, dry)
    _scrub_titles(cdir, dry, stats)
    # Last pass: resolvable-chips-only + str(dict)→prose on the final surfaces.
    _reconcile_evidence(cdir, dry, stats)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients-dir", default=_DEFAULT_DIR)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dirs = sorted(d for d in (os.path.join(args.clients_dir, x) for x in os.listdir(args.clients_dir))
                  if os.path.isdir(d))
    stats: dict = defaultdict(int)
    remediation: list = []
    for cdir in dirs:
        process_client(cdir, args.dry_run, stats, remediation)
    # Re-ingest remediation report: the wrong-entity (source-misattribution)
    # entities whose correct content can only be restored by re-ingesting the
    # right source package. Tier A = corroborated + badged + ticker nulled;
    # Tier B = likely holding-company symbol, surfaced for human review only.
    if remediation and not args.dry_run:
        rp = os.path.join(os.path.dirname(args.clients_dir.rstrip("/")),
                          "contamination_remediation.json")
        with open(rp, "w") as fh:
            json.dump(sorted(remediation, key=lambda r: (r["tier"], r["slug"])), fh, indent=2)
        print(f"# wrote re-ingest remediation report → {rp}")
    print(f"# apply_startup_data_fixes — {len(dirs)} clients{' (dry-run)' if args.dry_run else ''}")
    for k in sorted(stats):
        print(f"   {k:22} {stats[k]}")
    if remediation:
        for r in sorted(remediation, key=lambda r: (r["tier"], r["slug"])):
            print(f"   CONTAMINATION[{r['tier']}] {r['slug']}: {r['markers']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
