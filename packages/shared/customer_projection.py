"""The customer projection, checked against the internal one (RC-08).

WHY THIS EXISTS. Every gate this build runs validates the INTERNAL payload,
and the redaction tests guard only against LEAKS. Nothing compared what a
customer is served with what the analyst is served, so the opposite failure —
a hole — was invisible. Measured 2026-10-04 on SWBC (gold audit, HM-03,
INS-TS-07, PL-04): 24 customer drawers kept an argued synthesis over zero
served items (six of them thin:false), and platform estate_reach vanished
from every customer tile, while every gate and every redaction test was
green.

One function, three readers:
  · apps/api tests run it over redact_section output (CI);
  · scripts/audit_promoted_client.py runs it over the two served bodies of
    every promoted page (nightly corpus-gate-scanner, and --from-dir);
  · anything else that holds an internal and a customer body of one page.

It reads page BODIES as the API serves them — `{"sections": {name:
{"data": ..., "data_source": ..., "empty_state": ...}}}` — or the bare
sections mapping. It never imports the API: packages/shared is the contract
layer both sides read.

Findings are dicts {level, code, page, section, path, message}. BLOCKER means
the customer projection says something it cannot back, or silently serves
nothing where the analyst sees content.
"""
from __future__ import annotations

#: List fields a customer may legitimately receive EMPTY while the internal
#: body has rows, each with the decision that makes it so. Anything not named
#: here and emptied for the customer is a hole, not a policy.
DOCUMENTED_EMPTY = {
    ("techstack", "techstack", "items"):
        "DECISIONS D4 — customer register rows are CONFIRMED or ABSENT only",
    ("overview", "sentiment", "bars"):
        "owner decision 1 (2026-10-04) — internal-source bars are withheld "
        "from the reduced customer card",
    ("overview", "sentiment", "themes"):
        "owner decision 1 (2026-10-04) — themes naming cell codes, cap "
        "vocabulary or resting only on internal sources are withheld",
    ("heatmap", "safeguard_gates", "gates"):
        "a gate row about a section withheld from this audience is dropped",
}

#: Envelope keys that are not content: a body holding only these is empty.
_ENVELOPE = frozenset({"produced_at", "producer_version", "e_ids",
                       "empty_state", "enrichment_status", "internal_only",
                       "computed_error", "unresolved_citations"})

#: Keys whose list values are citation chips.
CITATION_KEYS = frozenset({"e_ids", "supporting_e_ids", "evidence_ids"})


def _f(level, code, page, section, path, message):
    return {"level": level, "code": code, "page": page, "section": section,
            "path": path, "message": message}


def _sections(body) -> dict:
    if not isinstance(body, dict):
        return {}
    s = body.get("sections")
    return s if isinstance(s, dict) else body


def _data(entry):
    if isinstance(entry, dict) and ("data" in entry or "data_source" in entry):
        return entry.get("data")
    return entry


def _has_content(node, top=True) -> bool:
    if isinstance(node, dict):
        return any(_has_content(v, False) for k, v in node.items()
                   if not (top and k in _ENVELOPE))
    if isinstance(node, list):
        return any(_has_content(v, False) for v in node)
    if isinstance(node, str):
        return bool(node.strip())
    return node is not None and node is not False


def _documented_withholding(entry) -> bool:
    """The serve layer's own stub for a section withheld from this audience
    (pages.withheld_entry) — the withholding is stated, so it is not a hole."""
    if not isinstance(entry, dict):
        return False
    es = entry.get("empty_state") or {}
    return (entry.get("data_source") == "withheld"
            or (isinstance(es, dict)
                and es.get("kind") == "withheld_for_audience"))


def _cells(data) -> list:
    cells = data.get("cells") if isinstance(data, dict) else None
    return [c for c in cells if isinstance(c, dict)] if isinstance(cells, list) else []


def _drawers(page, section, internal, customer) -> list:
    """A drawer the customer can open must hold what its prose argues from."""
    out = []
    by_id = {c.get("subcap_id"): c for c in _cells(internal)}
    for i, c in enumerate(_cells(customer)):
        items = c.get("items")
        n = len(items) if isinstance(items, list) else 0
        chips = [e for e in (c.get("e_ids") or []) if isinstance(e, str)]
        prose = str(c.get("synthesis") or "").strip()
        before = by_id.get(c.get("subcap_id")) or {}
        had = before.get("items")
        had = len(had) if isinstance(had, list) else len(before.get("e_ids") or [])
        where = f"cells[{i}]"
        if chips and n == 0:
            out.append(_f("BLOCKER", "CP-CHIPS-OVER-NOTHING", page, section,
                          where, f"{c.get('subcap_id')}: {len(chips)} citation "
                          "chip(s) open onto zero served items."))
        elif prose and n == 0 and had:
            out.append(_f("BLOCKER", "CP-ARGUED-DRAWER-EMPTY", page, section,
                          where, f"{c.get('subcap_id')}: the customer drawer "
                          f"argues a synthesis over 0 served items (the "
                          f"internal drawer holds {had}"
                          + ("; thin:false" if c.get("thin") is False else "")
                          + "). Re-ground it on a shareable span, or withhold "
                          "the synthesis with the evidence."))
    return out


def _dangling(page, section, data, served_ids) -> list:
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                here = f"{path}.{k}" if path else k
                if k in CITATION_KEYS and isinstance(v, list):
                    missing = [e for e in v if isinstance(e, str)
                               and e not in served_ids]
                    if missing:
                        out.append(_f("BLOCKER", "CP-DANGLING-CHIP", page,
                                      section, here,
                                      f"{len(missing)} chip(s) cite evidence "
                                      f"the customer is not served: "
                                      f"{', '.join(sorted(missing)[:5])}"))
                elif k == "e_id" and isinstance(v, str) and v not in served_ids:
                    out.append(_f("BLOCKER", "CP-DANGLING-CHIP", page, section,
                                  here, f"{v} is not in the customer evidence "
                                  "index"))
                else:
                    walk(v, here)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(data, "")
    return out


def check_page(page: str, internal_body, customer_body,
               served_evidence_ids=None, documented=None) -> list:
    """Every finding for one page's customer projection.

    `served_evidence_ids`, when given, is the set of evidence ids a customer
    can open (the customer evidence route, or the customer heatmap.evidence
    rows): every chip outside it is a dangling chip. Without it the chip
    check is confined to the drawers, which resolve their own items.
    """
    documented = DOCUMENTED_EMPTY if documented is None else documented
    internal, customer = _sections(internal_body), _sections(customer_body)
    if not customer:
        # A page the customer is refused whole (context: 403, a locked state)
        # is a stated withholding at the page grain.
        return []
    out = []
    for section, ientry in internal.items():
        idata = _data(ientry)
        if not _has_content(idata):
            continue
        centry = customer.get(section)
        cdata = _data(centry)
        if centry is None or cdata is None:
            if centry is not None and _documented_withholding(centry):
                continue
            out.append(_f("BLOCKER", "CP-SECTION-EMPTIED", page, section, "",
                          "the internal body serves content here and the "
                          "customer body serves nothing, with no stated "
                          "withholding."))
            continue
        if not _has_content(cdata):
            out.append(_f("BLOCKER", "CP-SECTION-EMPTIED", page, section, "",
                          "the customer body serves this section empty while "
                          "the internal body serves content, with no stated "
                          "withholding."))
            continue
        if isinstance(idata, dict) and isinstance(cdata, dict):
            for key, ival in idata.items():
                cval = cdata.get(key)
                if (isinstance(ival, list) and ival and isinstance(cval, list)
                        and not cval
                        and (page, section, key) not in documented):
                    out.append(_f("BLOCKER", "CP-LIST-EMPTIED", page, section,
                                  key, f"{len(ival)} row(s) for the analyst, "
                                  "0 for the customer, and no documented "
                                  "withholding names this field."))
        out += _drawers(page, section, idata, cdata)
        if served_evidence_ids is not None and section != "evidence":
            out += _dangling(page, section, cdata, set(served_evidence_ids))
    return out


def blockers(findings) -> list:
    return [f for f in findings if f.get("level") == "BLOCKER"]
