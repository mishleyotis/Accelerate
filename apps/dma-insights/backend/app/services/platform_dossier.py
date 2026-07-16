"""Deterministic platform DOSSIER — the evidence-rich narrative floor that
can never be cold (plan Part-platform v3).

The 2026-07 platform audit found the two narrative surfaces on D4 either
architecturally allowed to be null (``story_md`` — cache-read-only, 470/470
null in the shipped pack) or collapsed to a single score-talk skeleton
(``opportunity_md`` — 0/467 named a current-stack system, carried a $-figure,
or a year). Every input for a real dossier already exists per card
(``fit_breakdown.top_subcaps`` with E-IDs, prereqs with scores+thresholds,
``absent_families``) and per entity (``techstack`` rows with
CONFIRMED/INFERRED/CLAIMED/ABSENT status, ``evidence_e_ids`` and
``peer_coverage``) — v3 is an assembly/reasoning problem, not data collection.

This module assembles, per card, a three-section dossier grounded ONLY in
those inputs (nothing fabricated — an absent input yields a shorter, honest
narrative, never a guess):

  1. **Where they are today** — the entity's CONFIRMED/INFERRED current
     systems in the platform's pillar (named, E-ID-cited, with peer_coverage)
     and whether the pitched family is confirmed ABSENT (greenfield) or
     already partly present (displacement).
  2. **Why this platform** — the fit engine's TOP-OPPORTUNITY subcaps
     (opportunity-ranked, never sorted[0]) with score-vs-peer-median, the
     factor points from ``fit_breakdown``, and the E-IDs behind them.
  3. **Path to ready** — the readiness light, the OPEN prerequisites with
     current-vs-threshold numbers (the QA challenge: a 'met' prereq is only
     stated met when its score actually clears the threshold), and the
     prerequisite-DAG sequence argument.

Every composed sentence is paired with a ``narrative_provenance`` entry
``{claim, source_kind, e_ids}`` so the whole story is auditable. Bracketed
E-ID citations (``[E-040]``) survive ``text_hygiene.scrub_md`` (bare tokens
and raw ``P#C#`` codes are stripped) — the story never leaks a taxonomy
code and never drops a real citation.

Pure-logic: reads plain dicts (a serialized ``PlatformCard`` + the pack
``techstack.json`` item shape), no SQLAlchemy, no FastAPI. The router twin
(``routers/platforms.py``) and the offline patcher twin
(``scripts/apply_startup_data_fixes.py``) both call :func:`compose_dossier`
with the SAME shapes so pack==live (the qa_pack_parity contract).
"""
from __future__ import annotations

import re

from app.services.platform_incumbents import (
    CATEGORY_INCUMBENT_PATTERNS,
    PLATFORM_CATEGORY,
)
from app.services.text_hygiene import scrub_md

# Server-side twin of platform_fit_data.PLATFORM_FAMILY_PATTERNS (kept a
# dependency-free copy here so the pure composer never imports the DB
# assembly module). Matches a techstack row to the pitched platform family.
_FAMILY_PATTERNS: dict[str, re.Pattern[str]] = {
    "salesforce": re.compile(
        r"salesforce|mulesoft|tableau crm|marketing cloud|data cloud|agentforce"
        r"|financial services cloud|\bfsc\b", re.I),
    "databricks": re.compile(r"databricks|lakehouse|mosaic", re.I),
    "tableau": re.compile(r"tableau|pulse", re.I),
    "twilio": re.compile(r"twilio|segment", re.I),
    "ncino": re.compile(r"ncino", re.I),
}

_PLATFORM_NAME: dict[str, str] = {
    "salesforce": "Salesforce", "databricks": "Databricks", "tableau": "Tableau",
    "twilio": "Twilio", "ncino": "nCino",
}


def _pname(pid: str) -> str:
    return _PLATFORM_NAME.get(str(pid), str(pid)[:1].upper() + str(pid)[1:])


_PILLAR_LABEL: dict[str, str] = {
    "P1": "strategy & data-foundation",
    "P2": "customer-experience",
    "P3": "operations",
    "P4": "data & analytics",
}

_OPEN_STATUSES = frozenset({"UNMET", "MISSING", "BLOCKED", "FAIL", "PARTIAL"})
_STORY_MAX = 1400


def _num(v: object) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    return None


def _cite(e_ids: object, limit: int = 2) -> tuple[str, list[str]]:
    """Bracketed citation string ('[E-040, E-045]') + the id list it used.
    Bracketed form is deliberate — text_hygiene preserves it verbatim."""
    ids = [str(e) for e in (e_ids or []) if e][:limit]
    return (f" [{', '.join(ids)}]" if ids else ""), ids


def _fam_status_label(status: str) -> str:
    return {
        "CONFIRMED": "confirmed in the current stack",
        "INFERRED": "inferred from adjacent signals",
        "CLAIMED": "claimed but unverified",
        "ABSENT": "confirmed absent",
    }.get(status, status.lower())


def _relevant_stack(
    card: dict, techstack_items: list[dict] | None,
) -> tuple[list[dict], list[dict]]:
    """Split the entity's techstack into (pitched-family rows, other current
    systems in the card's pillar). 'Current systems' are CONFIRMED/INFERRED
    named products the AE can reference — the mandate's 'current
    organizational capabilities'."""
    pillar = card.get("pillar")
    pid = card.get("platform_id")
    fam_rx = _FAMILY_PATTERNS.get(str(pid))
    same_family: list[dict] = []
    current: list[dict] = []
    seen: set[str] = set()
    for it in techstack_items or []:
        if not isinstance(it, dict):
            continue
        name = it.get("product_name") or it.get("product") or it.get("vendor")
        if not name:
            continue
        status = str(it.get("status") or "").upper()
        hay = f"{it.get('vendor', '')} {it.get('product', '')} {name}"
        if fam_rx and fam_rx.search(hay):
            same_family.append(it)
        elif status in ("CONFIRMED", "INFERRED") and it.get("dma_pillar") == pillar:
            key = str(name).lower()
            if key not in seen:
                seen.add(key)
                current.append(it)
    # Best-evidenced current systems first (peer_coverage as the tiebreak so
    # a widely-deployed peer tool leads the sentence).
    current.sort(key=lambda it: (
        -len(it.get("evidence_e_ids") or []),
        -(_num(it.get("peer_coverage")) or 0.0),
    ))
    return same_family, current


def _open_prereqs(card: dict) -> tuple[list[dict], int]:
    """OPEN prerequisites (challenged against their threshold) + total count.

    The QA mandate: never conclude a prereq is met before challenging it.
    We re-derive open/met from current_score vs threshold when both exist,
    so a stale ``status`` string can't assert 'met' on a failing score."""
    prereqs = card.get("prereq_checks") or card.get("prereqs") or []
    if isinstance(prereqs, dict):  # fit_breakdown.prereqs shape
        prereqs = [
            {"required_subcap_id": k, **(v if isinstance(v, dict) else {})}
            for k, v in prereqs.items()
        ]
    total = 0
    open_list: list[dict] = []
    for p in prereqs:
        if not isinstance(p, dict):
            continue
        total += 1
        status = str(p.get("status", "")).upper()
        cur = _num(p.get("current_score"))
        if cur is None:
            cur = _num(p.get("current"))
        thr = _num(p.get("threshold"))
        # Challenge the status: a numeric score below threshold is OPEN even
        # if the row says MET; a MET-labelled row clearing threshold is met.
        challenged_open = (
            (cur is not None and thr is not None and cur < thr)
            or status in _OPEN_STATUSES
        )
        if challenged_open:
            open_list.append({
                "name": p.get("name") or p.get("label") or "a foundational prerequisite",
                "required_subcap_id": p.get("required_subcap_id"),
                "current": cur,
                "threshold": thr,
                "status": status or "UNMET",
            })
    return open_list, total


def _top_subcaps(card: dict) -> list[dict]:
    bd = card.get("fit_breakdown") if isinstance(card.get("fit_breakdown"), dict) else {}
    return [t for t in (bd.get("top_subcaps") or []) if isinstance(t, dict)]


def _subcap_name_index(top_subcaps: list[dict]):
    """Lexical index over the card's contributing subcap names — the offline
    NLP tier used to match an issue's TEXT to related subcaps. Returns None
    when the similarity tier is unavailable (sklearn absent) or there is
    nothing to index; callers treat None as 'no similarity matches'."""
    docs = [
        (str(t.get("subcap_id")), f"{t.get('name') or ''} {t.get('subcap_id') or ''}")
        for t in top_subcaps
        if t.get("subcap_id")
    ]
    if not docs:
        return None
    # Route platform-dossier subcap matching through the MiniLM tier (2026-07-14
    # audit: this was TF-IDF-only). preferred_index() is a drop-in — same
    # fit/top_k — that lifts to semantic when the model is baked and degrades
    # to the exact lexical index when it is cold (never raises).
    try:
        from app.services.nlp.semantic import preferred_index
    except Exception:
        return None
    idx = preferred_index()
    idx.fit(docs)
    return idx


def _resolve_related_subcaps(
    prereq: dict,
    top_subcaps: list[dict],
    addressable_ids: list[str],
    name_index=None,
) -> list[dict]:
    """Related subcaps for one prerequisite/issue — the readiness card's
    'backing subcaps'.

    The 2026-07 operator report: prerequisites (the 'missing issues') rendered
    with zero related subcaps because the ONLY matcher was the frontend's
    ``top_subcaps.startsWith(required[:4])`` prefix filter — the platform's
    top-OPPORTUNITY subcaps rarely fall in the prereq's gated category, so
    911/1222 prereqs across all 94 clients surfaced nothing. This resolves the
    related subcaps server-side via the shared matching ladder so an issue that
    carries a ``linked_subcap_id`` (its ``required_subcap_id``) can NEVER show
    zero related subcaps:

      1. the gate subcap itself (``required_subcap_id`` — the linked_subcap_id
         the issue register carries) — always related, always emitted;
      2. same-category then same-pillar contributing subcaps from the fit
         breakdown (the addressable gaps the platform closes nearby);
      3. nlp lexical similarity between the issue TEXT (prereq name) and the
         contributing subcap names (``nlp.similarity``);
      4. same-category addressable-gap ids when nothing but the gate matched.
    """
    required = str(prereq.get("required_subcap_id") or "")
    text_ = str(prereq.get("name") or "")
    by_id: dict[str, dict] = {}
    for t in top_subcaps:
        sid = str(t.get("subcap_id") or "")
        if sid:
            by_id.setdefault(sid, t)

    out: list[dict] = []
    seen: set[str] = set()

    def _emit(sid: str, label: object, score: object, e_ids: object) -> None:
        sid = str(sid or "")
        if not sid or sid in seen:
            return
        seen.add(sid)
        out.append({
            "subcap_id": sid,
            "name": str(label) if label else None,
            "score": _num(score),
            "e_ids": [str(e) for e in (e_ids or []) if e][:3],
        })

    # 1. the gate subcap itself — the issue's own linked_subcap_id.
    if required:
        info = by_id.get(required) or {}
        _emit(
            required,
            info.get("name") or text_ or None,
            info.get("score", prereq.get("current")),
            info.get("e_ids"),
        )

    # 2. same-category, then same-pillar contributing subcaps.
    cat, pil = required[:4], required[:2]
    for pref in (cat, pil):
        if not pref:
            continue
        for t in top_subcaps:
            sid = str(t.get("subcap_id") or "")
            if sid.startswith(pref):
                _emit(sid, t.get("name"), t.get("score"), t.get("e_ids"))
        if len(out) >= 6:
            return out[:6]

    # 3. nlp lexical similarity: the issue text → contributing subcap names.
    #    A firmer floor than the module default keeps a single shared common
    #    token (e.g. "Management") from fabricating a weak "related" link.
    if text_ and name_index is not None:
        for sid, _s in name_index.top_k(text_, k=4, min_score=0.15):
            t = by_id.get(str(sid)) or {}
            _emit(sid, t.get("name"), t.get("score"), t.get("e_ids"))
            if len(out) >= 6:
                break

    # 4. same-category addressable gap ids when only the gate matched.
    if len(out) <= 1 and cat:
        for sid in addressable_ids:
            sid = str(sid)
            if sid[:4] == cat and sid != required:
                _emit(sid, None, None, None)

    return out[:6]


def _opportunity_points(card: dict) -> float | None:
    bd = card.get("fit_breakdown") if isinstance(card.get("fit_breakdown"), dict) else {}
    fac = (bd.get("factors") or {}).get("opportunity") or {}
    return _num(fac.get("points"))


def build_readiness_now(card: dict, techstack_items: list[dict] | None) -> dict:
    """Section 1+3 structured payload: current systems, greenfield/displacement
    posture, readiness light, open prerequisites."""
    same_family, current = _relevant_stack(card, techstack_items)
    open_prereqs, total_prereqs = _open_prereqs(card)
    # Attach the related subcaps to every open prerequisite so the readiness
    # card never renders an issue with zero related subcaps (2026-07 fix).
    tops = _top_subcaps(card)
    addr = [str(s) for s in (card.get("addressable_subcap_ids") or [])]
    name_index = _subcap_name_index(tops)
    for p in open_prereqs:
        p["related_subcaps"] = _resolve_related_subcaps(p, tops, addr, name_index)
    absent_families = []
    bd = card.get("fit_breakdown") if isinstance(card.get("fit_breakdown"), dict) else {}
    absent_families = [str(f) for f in (bd.get("absent_families") or []) if f]
    fam_absent = any(
        str(it.get("status", "")).upper() == "ABSENT" for it in same_family
    ) or bool(absent_families)
    fam_present = [
        it for it in same_family
        if str(it.get("status", "")).upper() in ("CONFIRMED", "INFERRED")
    ]
    lens, incumbents = _card_stack_lens(
        card, techstack_items,
        fam_absent=bool(fam_absent) and not fam_present,
    )
    return {
        "light": card.get("readiness_index"),
        "confirmed_systems": [
            {
                "name": it.get("product_name") or it.get("product") or it.get("vendor"),
                "status": str(it.get("status", "")).upper(),
                "e_ids": [str(e) for e in (it.get("evidence_e_ids") or [])][:2],
                "peer_coverage": _num(it.get("peer_coverage")),
            }
            for it in current[:3]
        ],
        "family_present": [
            {
                "name": it.get("product_name") or it.get("product") or it.get("vendor"),
                "status": str(it.get("status", "")).upper(),
            }
            for it in fam_present[:3]
        ],
        # `greenfield` stays boolean for older readers; the three-way frame
        # (greenfield | integrate | expand) + the named category incumbents
        # are the 2026-07-14 additive fields.
        "greenfield": lens == "greenfield",
        "lens": lens,
        "category_incumbents": incumbents,
        "absent_families": absent_families,
        "open_prereqs": open_prereqs,
        "total_prereqs": total_prereqs,
    }


def _card_stack_lens(
    card: dict,
    techstack_items: list[dict] | None,
    *,
    fam_absent: bool,
) -> tuple[str, list[str]]:
    """(lens, category incumbents) for the card — breakdown-first (the fit
    engine persisted the reasoned lens), techstack-scan fallback for cards
    computed before the lens existed."""
    bd = card.get("fit_breakdown") if isinstance(card.get("fit_breakdown"), dict) else {}
    sl = ((bd.get("factors") or {}).get("absent_boost") or {}).get("stack_lens")
    if isinstance(sl, dict) and sl.get("lens"):
        return str(sl["lens"]), [
            str(x) for x in (sl.get("category_incumbents") or []) if x
        ]
    if not fam_absent:
        return "expand", []
    category = PLATFORM_CATEGORY.get(str(card.get("platform_id") or ""))
    hay = " ".join(
        f"{it.get('vendor') or ''} "
        f"{it.get('product_name') or it.get('product') or ''}"
        for it in (techstack_items or [])
        if str(it.get("status", "")).upper() in ("CONFIRMED", "INFERRED")
    ).lower()
    incumbents = [
        name for name, rx in CATEGORY_INCUMBENT_PATTERNS.get(category or "", [])
        if rx.search(hay)
    ]
    return ("integrate", incumbents) if incumbents else ("greenfield", [])


def _integration_vehicle(card: dict) -> str | None:
    """The Zennify integration-layer L3 the v7 catalogue maps onto this
    card's gap drivers (persisted by compute_v2_rows as
    breakdown.l3_solution.integration_vehicle). None when the L4 layer
    isn't loaded — the prose simply omits the vehicle sentence."""
    bd = card.get("fit_breakdown") if isinstance(card.get("fit_breakdown"), dict) else {}
    sol = bd.get("l3_solution") or {}
    veh = sol.get("integration_vehicle")
    if isinstance(veh, dict) and veh.get("platform_name"):
        return str(veh["platform_name"])
    return None


def compose_dossier(
    card: dict,
    *,
    techstack_items: list[dict] | None = None,
    entity_name: str | None = None,
    metric_phrases: list[str] | None = None,
) -> dict:
    """Assemble the full dossier for one platform card.

    Returns ``{story_md, story_source, dossier, narrative_provenance}``.
    ``story_md`` is the scrubbed 3-6 sentence narrative — non-null for any
    card with a ``display_name`` (an INSUFFICIENT_EVIDENCE card still gets an
    honest current-state floor, never a hole). ``story_source`` is
    ``'deterministic'`` for this floor; a validated Gemini story replaces it
    upstream (validator-gated uplift)."""
    name = str(card.get("display_name") or card.get("platform_id") or "This platform")
    if not (card.get("display_name") or card.get("platform_id")):
        return {"story_md": None, "story_source": None, "dossier": None,
                "narrative_provenance": []}

    ent = str(entity_name or card.get("entity_name") or "the client")
    pillar = str(card.get("pillar") or "")
    pillar_label = _PILLAR_LABEL.get(pillar, pillar or "digital")
    addr = card.get("addressable_subcap_ids") or []

    # Anti-template engine (2026-07-13 stress-test): the shipped pack carried
    # 260 masked six-word frames shared across >=10 clients on this surface —
    # many on all 94 ("— a greenfield entry rather than", "nothing gates it").
    # Every emitted sentence now draws its realization from a seeded pool
    # keyed by (entity, platform): same card → same prose forever, different
    # clients → different frames. Facts, numbers and citations are invariant.
    from app.services.nlp.stylebook import pick, seeded
    rng = seeded(ent, str(card.get("platform_id") or name), "dossier")

    rn = build_readiness_now(card, techstack_items)
    tops = _top_subcaps(card)
    opp_pts = _opportunity_points(card)

    sentences: list[str] = []
    provenance: list[dict] = []

    def emit(text: str, source_kind: str, e_ids: list[str] | None = None) -> None:
        text = text.strip()
        if not text:
            return
        sentences.append(text)
        provenance.append({
            "claim": text,
            "source_kind": source_kind,
            "e_ids": [str(e) for e in (e_ids or []) if e],
        })

    # ── 1. Where they are today ────────────────────────────────────────────
    stack_eids: list[str] = []
    current = rn["confirmed_systems"]
    if current:
        for sys in current[:2]:
            stack_eids.extend(sys.get("e_ids") or [])
        names = [str(s["name"]) for s in current[:2] if s.get("name")]
        joined = " and ".join(names)
        cov = current[0].get("peer_coverage")
        cov_txt = (pick(rng, (
            " ({c}% of peers run comparable tooling)",
            " — tooling {c}% of peers also run",
            " (peer adoption of comparable tools: {c}%)",
            " ({c}% peer coverage on comparable tools)",
            " — {c}% of the peer set runs something comparable",
            " (comparable tooling shows up at {c}% of peers)",
        ), c=round(cov * 100)) if isinstance(cov, float) and cov > 0 else "")
        cite, used = _cite(stack_eids)
        emit(pick(rng, (
            "{joined} anchor {ent}'s {pl} stack today{cov}{cite}.",
            "{ent} runs its {pl} estate on {joined} today{cov}{cite}.",
            "Today's {pl} stack at {ent} is built around {joined}{cov}{cite}.",
            "{joined} carry {ent}'s {pl} workload today{cov}{cite}.",
        ), joined=joined, ent=ent, pl=pillar_label, cov=cov_txt, cite=cite),
            "techstack", used)
    if rn.get("lens") == "integrate" and rn.get("category_incumbents"):
        inc = str(rn["category_incumbents"][0])
        emit(pick(rng, (
            "The {name} family is absent, but {inc} already anchors that "
            "layer — the case here is integration with {inc}, not a "
            "greenfield install.",
            "With {inc} in place, {name} enters as a complement to the "
            "installed platform: the conversation is coexistence and "
            "data-flow, not displacement.",
            "{inc} already carries this workload, so the {name} argument "
            "runs through integration with {inc} rather than a net-new "
            "platform build.",
            "That stack is not open ground — {inc} occupies the layer — so "
            "any {name} motion starts from interoperating with {inc}, not "
            "from a blank slate.",
        ), name=name, inc=inc), "techstack")
        # 2026-07-14 solutioning: NAME the Zennify integration vehicle the
        # v7 catalogue maps onto this card's gaps (MuleSoft Anypoint / Data
        # Cloud / Twilio Segment), not just the incumbent — the stakeholder's
        # "we have MuleSoft" gap.
        veh = _integration_vehicle(card)
        if veh:
            emit(pick(rng, (
                "The connective tissue is {veh}: it lands {name}'s value on "
                "top of {inc} without unwinding it.",
                "Zennify runs that integration through {veh}, wiring {name} "
                "into the {inc} estate rather than replacing it.",
                "{veh} is the vehicle — it bridges {name} to the installed "
                "{inc} layer so the two operate as one.",
            ), veh=veh, name=name, inc=inc), "catalogue")
    elif rn["greenfield"]:
        fam_txt = f" ({', '.join(rn['absent_families'][:2])})" if rn["absent_families"] else ""
        emit(pick(rng, (
            "The {name} platform family is confirmed absent from that stack"
            "{fam} — a greenfield entry rather than a rip-and-replace.",
            "That stack shows no confirmed {name} footprint{fam}, which makes "
            "this a greenfield entry, not a displacement fight.",
            "Nothing in the confirmed stack overlaps the {name} family{fam} — "
            "{name} would land on open ground rather than displace an "
            "incumbent.",
            "The techstack review confirms the {name} family is not in place"
            "{fam}; the entry is greenfield, with no incumbent to unwind.",
        ), name=name, fam=fam_txt), "techstack")
    elif rn["family_present"]:
        fp = rn["family_present"][0]
        emit(pick(rng, (
            "The {name} platform is already {status} ({fp}), so this is an "
            "expansion, not a net-new introduction.",
            "{name} is not starting cold here — {fp} is {status} — so the "
            "motion is expansion on an existing foothold.",
            "With {fp} {status}, the {name} conversation is about widening "
            "an existing footprint rather than introducing a new vendor.",
        ), name=name, status=_fam_status_label(fp["status"]), fp=fp["name"]),
            "techstack")

    # ── 1b. Analyst-report reconciliation (W4) ─────────────────────────────
    _backing = ((card.get("fit_breakdown") or {}).get("analyst_backing")
                if isinstance(card.get("fit_breakdown"), dict) else None) or {}
    _recs = _backing.get("recs") or []
    if _recs:
        _r0 = _recs[0]
        _ph = f" (Phase {_r0['phase']})" if _r0.get("phase") else ""
        _rtitle = str(_r0.get("title") or "").strip().rstrip(".")
        if _rtitle:
            emit(pick(rng, (
                "The analyst report backs this{ph}: “{t}.”",
                "This aligns with the assessment's own recommendation{ph} to "
                "{t_low}.",
                "The report already calls for it{ph} — “{t}.”",
            ), ph=_ph, t=_rtitle, t_low=_rtitle[:1].lower() + _rtitle[1:]),
                "recommendation")
    elif _backing.get("note") and (_num(card.get("fit_score")) or 0) >= 60:
        # Honest flag: a hot card the analyst never explicitly recommended.
        emit(pick(rng, (
            "This is an engine read of the capability data, not one of the "
            "report's explicit recommendations — position it as a data-driven "
            "addition.",
            "The analyst report does not name this platform directly; the case "
            "here rests on the capability scores, not a written recommendation.",
        )), "assessment")

    # ── 2. Why this platform ───────────────────────────────────────────────
    if tops:
        lead = tops[0]
        lead_name = lead.get("name") or "the top capability"
        lead_eids = [str(e) for e in (lead.get("e_ids") or [])]
        score = _num(lead.get("score"))
        peer = _num(lead.get("peer_median"))
        # Lead with the OPPORTUNITY + evidence — not "widest gap: X sits at
        # Y/5 … N addressable gaps … fit points" (plan S13; user: not interested
        # in the subcaps). The current maturity stays as a compact trailing stat.
        head_txt = ""
        if score is not None and peer is not None:
            head_txt = pick(rng, (
                " (currently {s:.1f}/5 against a {p:.1f} peer benchmark)",
                " (now {s:.1f}/5, peer median {p:.1f})",
                " — today it reads {s:.1f}/5 against peers at {p:.1f}",
                " ({s:.1f}/5 where peers hold {p:.1f})",
                " (assessed {s:.1f}/5; the peer line is {p:.1f})",
                " — {s:.1f}/5 today versus {p:.1f} across the peer set",
            ), s=score, p=peer)
        elif score is not None:
            head_txt = pick(rng, (
                " (currently {s:.1f}/5)", " (now {s:.1f}/5)",
                " — today it reads {s:.1f}/5",
            ), s=score)
        cite, used = _cite(lead_eids)
        # variants keep their 6-gram windows disjoint — no shared stub like
        # "the capability with the" across two variants (census-measured).
        emit(pick(rng, (
            "The clearest opportunity {name} unlocks for {ent} is {lead}"
            "{cite} — the capability with the most headroom to advance"
            "{head}.",
            "For {ent}, {name} pays off first on {lead}{cite} — the "
            "widest-open surface on its board{head}.",
            "{lead} is where {name} earns its place at {ent}{cite}: no "
            "other addressable area carries as much upside{head}.",
            "Start the {name} case at {lead}{cite}, the ground where "
            "{ent} has the most to gain{head}.",
            "{name}'s first dividend at {ent} comes from {lead}{cite}"
            "{head}.",
            "If {ent} deploys {name}, {lead} moves first{cite} — nothing "
            "else it addresses has as far to run{head}.",
        ), name=name, ent=ent, lead=lead_name, cite=cite, head=head_txt),
            "subcap_score", used)
        # Next surface (second-ranked opportunity), if named + distinct.
        if len(tops) > 1 and tops[1].get("name") and tops[1]["name"] != lead_name:
            nxt = tops[1]
            nxt_eids = [str(e) for e in (nxt.get("e_ids") or [])]
            ns, nu = _num(nxt.get("score")), _num(nxt.get("peer_median"))
            nxt_gap = (
                f" ({ns:.1f}/5 vs {nu:.1f})" if ns is not None and nu is not None
                else ""
            )
            cite2, used2 = _cite(nxt_eids)
            emit(pick(rng, (
                "{nxt}{gap} is the adjacent surface it lifts next{cite}.",
                "Behind it, {nxt}{gap} is the next capability the same "
                "deployment reaches{cite}.",
                "The same footprint then extends to {nxt}{gap}{cite}.",
                "{nxt}{gap} follows as the second surface the platform "
                "improves{cite}.",
                "Next in line: {nxt}{gap}{cite}.",
                "One deployment, two capabilities — {nxt}{gap} rides the "
                "same rollout{cite}.",
            ), nxt=str(nxt["name"]), gap=nxt_gap, cite=cite2),
                "subcap_score", used2)
    elif not addr:
        emit(
            f"No capability gaps are currently mapped to the {name} platform "
            f"for {ent} this run — the fit card is honest about that.",
            "state",
        )

    # A quantified entity metric mined from the entity's own evidence, when
    # available (real fact, non-fabricated) — strengthens the story.
    if metric_phrases:
        mp = str(metric_phrases[0]).strip()
        if mp:
            emit(pick(rng, (
                "{ent}'s own evidence quantifies the stakes: {mp}.",
                "The stakes carry a number from {ent}'s own file: {mp}.",
                "{ent}'s evidence puts a figure on it — {mp}.",
            ), ent=ent, mp=mp), "evidence")

    # ── 3. Path to ready ───────────────────────────────────────────────────
    light = str(rn["light"] or "").lower()
    open_p = rn["open_prereqs"]
    total_p = rn["total_prereqs"]
    if light == "green" or (total_p and not open_p):
        if total_p:
            emit(pick(rng, (
                "Readiness is green — all {tot} prerequisites clear their "
                "thresholds, so {name} can land now.",
                "Every one of the {tot} prerequisites clears its threshold: "
                "{name} is deployable as-is.",
                "{name} is ready today — the {tot} mapped prerequisites all "
                "clear.",
            ), tot=total_p, name=name), "prereq")
        else:
            # No prereq spec mapped for this platform — assert readiness
            # without inventing a count ("the mapped mapped prerequisites").
            emit(pick(rng, (
                "Readiness is green — nothing gates {name}; it can land now.",
                "{name} carries no open prerequisites: it is deployable as-is.",
            ), name=name), "prereq")
    elif open_p:
        ex = open_p[0]
        cur, thr = ex.get("current"), ex.get("threshold")
        detail = (pick(rng, (
            ", led by {n} at {c:.1f} versus the {t:.1f} threshold",
            " — first among them {n}, at {c:.1f} against a {t:.1f} bar",
            ", starting with {n} ({c:.1f} today, {t:.1f} required)",
        ), n=ex["name"], c=cur, t=thr)
            if isinstance(cur, float) and isinstance(thr, float)
            else f", led by {ex['name']}")
        band = "near-ready" if light == "amber" else (
            "blocked on prerequisites" if light == "red" else "in evaluation")
        emit(pick(rng, (
            "Readiness is {light} ({band}): {n} of {tot} prerequisite{pl} "
            "still open{detail}.",
            "The readiness light is {light} — {band} — with {n} of {tot} "
            "prerequisite{pl} open{detail}.",
            "{n} of {tot} prerequisite{pl} remain open{detail}, which keeps "
            "the readiness light {light} ({band}).",
        ), light=light or "unrated", band=band, n=len(open_p), tot=total_p,
            pl="s" if total_p != 1 else "", detail=detail), "prereq")

    # Sequence argument from the prerequisite DAG.
    seq = {}
    bd = card.get("fit_breakdown") if isinstance(card.get("fit_breakdown"), dict) else {}
    seq = bd.get("sequence") or {}
    rank = seq.get("rank") if isinstance(seq, dict) else card.get("sequence_rank")
    after = [str(a) for a in (seq.get("after") or [])] if isinstance(seq, dict) else []
    # W5 (2026-07-14): name the CONCRETE prerequisite the card waits on, not
    # a bare "its prerequisites" — the AE-followable causal link ("hold
    # Databricks until the data foundation clears"). Sourced from the
    # persisted prereq spec (first unmet/partial check).
    gating = None
    _prq = bd.get("prereqs") if isinstance(bd.get("prereqs"), dict) else {}
    for _sid, _spec in _prq.items():
        if isinstance(_spec, dict) and str(_spec.get("status", "")).upper() in (
                "UNMET", "PARTIAL", "MISSING"):
            gating = str(_spec.get("name") or "").strip()
            if gating:
                break
    if after:
        aft = " and ".join(_pname(a) for a in after[:2])
        # Number agreement: a SINGLE prerequisite platform takes singular
        # verbs ("Databricks goes first: it clears …"); 2+ take plural. The
        # 2026-07-14 verbatim vet found "Databricks go first: they clear" on
        # 31 clients — a single platform welded to plural verbs.
        _one = len(after[:2]) == 1
        v_deliver = "delivers" if _one else "deliver"
        v_clear = "clears" if _one else "clear"
        v_land = "lands" if _one else "land"
        v_go = "goes" if _one else "go"
        v_lead = "leads" if _one else "lead"
        v_open = "opens" if _one else "open"
        pron = "it" if _one else "they"
        obj = "it" if _one else "them"
        dep = "that deployment" if _one else "those deployments"
        if gating:
            emit(pick(rng, (
                f"Sequence {{name}} after {{after}}: it needs {{gate}} in place "
                f"first, and that is what {{after}} {v_deliver}.",
                f"Hold {{name}} until {{after}} {v_land} — {{gate}} is the "
                f"prerequisite it inherits from {obj}.",
                f"{{name}} waits on {{gate}}; {{after}} {v_clear} that foundation "
                f"first, so {pron} {v_lead} and {{name}} follows.",
            ), name=name, after=aft, gate=gating), "sequence")
        else:
            emit(pick(rng, (
                f"Sequence {{name}} after {{after}}, which {v_clear} its "
                f"prerequisites first.",
                f"{{name}} belongs later in the sequence — {{after}} {v_clear} "
                f"its prerequisites first.",
                f"Stage {{name}} behind {{after}}; {dep} {v_open} its "
                f"prerequisites.",
                f"{{after}} {v_go} first: {pron} {v_clear} the prerequisites "
                f"{{name}} needs.",
            ), name=name, after=aft), "sequence")
    elif rank == 1:
        emit(pick(rng, (
            "{name} leads the platform sequence — nothing gates it.",
            "{name} goes first in the sequence: no prerequisite stands "
            "ahead of it.",
            "Nothing upstream gates {name}, so it opens the platform "
            "sequence.",
        ), name=name), "sequence")

    story_raw = " ".join(sentences).strip()
    story_md = scrub_md(story_raw)
    if story_md and len(story_md) > _STORY_MAX:
        story_md = story_md[:_STORY_MAX].rsplit(".", 1)[0] + "."

    dossier = {
        "readiness_now": rn,
        "opportunity": {
            "gap_count": len(addr),
            "opportunity_points": opp_pts,
            "lead_subcap": (
                {
                    "name": tops[0].get("name"),
                    "score": _num(tops[0].get("score")),
                    "peer_median": _num(tops[0].get("peer_median")),
                    "e_ids": [str(e) for e in (tops[0].get("e_ids") or [])][:3],
                }
                if tops else None
            ),
            "next_subcaps": [
                {"name": t.get("name"), "score": _num(t.get("score"))}
                for t in tops[1:4] if t.get("name")
            ],
        },
        "why_sequence": {
            "rank": rank,
            "after": after,
        },
    }
    return {
        "story_md": story_md or None,
        "story_source": "deterministic" if story_md else None,
        "dossier": dossier,
        "narrative_provenance": provenance,
    }


def story_facts_ok(story_md: object) -> bool:
    """QA acceptance: a real dossier story carries ≥1 bracketed E-ID citation
    AND ≥1 concrete fact (a named-system 'X platform/Cloud/Core', a score
    against a peer median, a percentage, a $-figure, or a year)."""
    t = str(story_md or "")
    if not t:
        return False
    has_cite = bool(re.search(r"\[[^\]]*E-[A-Za-z0-9]", t))
    has_fact = bool(re.search(
        r"\$\s?\d|\b(?:19|20)\d{2}\b|\d+(?:\.\d+)?\s*%"
        r"|\d+(?:\.\d+)?/5|peer median"
        r"|\b[A-Z][A-Za-z]+ (?:platform|Cloud|Core|CRM|API)\b",
        t))
    return has_cite and has_fact
