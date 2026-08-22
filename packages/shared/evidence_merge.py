"""Two rows, one artefact: the duplicate that made a drawer unreadable.

MEASURED on run d7ed1d90 (Logix Federal Credit Union, 104 evidence rows):

  · 20 source urls carry more than one row.
  · 36 rows carry NO excerpt. Every one is package-ingested — the workbook's
    own evidence ledger, written before the ingest path stored spans.
  · 10 of those 36 sit on a url where ANOTHER row already carries a verbatim
    span of the same document.

That last number is the interesting one. `E-LOGIXFED-003` and `E-CC-188` are
the same congressional testimony at the same url. The package row carries the
CELL LINKS — 21 of them, including P1C1.1.1 — and no quotable span. The
producer row carries the span and different links. So the cell that a reader
opened showed a citation with no quote, while a quote from the very same
document sat one row away, attached to a different cell.

THE RULE, and its two halves are not symmetric:

  · A row with an excerpt is a SPAN of the artefact. Several spans of one
    document are several citations — E-CC-188 and E-CC-199 quote different
    paragraphs of the same testimony — and merging them would delete a
    citation the producer made. They all survive.
  · A row with no excerpt is a REFERENCE to the artefact. It carries nothing a
    span-carrying sibling does not, except its cell links. It is absorbed, its
    links join the survivors, and its id is recorded on them.

Where no row on a url carries a span, one survives and the rest are absorbed:
to a reader they are the same unquotable reference listed twice.

NOTHING IS LOST AND NOTHING IS HIDDEN. `also_filed_as` names every absorbed
id, the caller is told how many were absorbed, and every id still RESOLVES on
its own: this rewrites a LISTING, never a resolution. Invariant 4 is a
per-id contract and a merged listing does not touch it.
"""
from __future__ import annotations

import re

_SCHEME = re.compile(r"^https?://", re.I)


def source_key(url) -> str:
    """The identity of an artefact for this purpose: its url, scheme-blind.

    http and https of one page are one document. `www.` is NOT stripped — a
    host that answers on both is one server's choice and not something to
    assume — and neither is a query string: `itunes.apple.com/lookup?id=…` is
    a different response per id, and collapsing those would merge unrelated
    artefacts. An archive.org wrapper stays distinct from the page it wraps,
    because a retrieval that succeeded and one that had to go to an archive are
    different retrievals.
    """
    u = str(url or "").strip()
    if not u:
        return ""
    return _SCHEME.sub("", u).rstrip("/").lower()


def _has_excerpt(item) -> bool:
    return bool(str(item.get("excerpt") or "").strip())


def merge_same_source(items: list[dict]) -> tuple[list[dict], dict]:
    """Collapse rows that reference an artefact already quoted by a sibling.

    Returns `(items, report)`. `report` carries `absorbed` (how many rows were
    merged away), `groups` (how many urls had more than one row) and
    `excerpts_recovered` (how many absorbed rows had no span and whose cells
    therefore gained one). Counted rather than summarised: a merge that
    silently shrinks a list is indistinguishable from a query that lost rows.
    """
    order = {id(it): i for i, it in enumerate(items)}
    groups: dict[str, list[dict]] = {}
    loose: list[dict] = []
    for it in items:
        k = source_key(it.get("source_url"))
        (groups.setdefault(k, []) if k else loose).append(it)

    out: list[dict] = list(loose)
    absorbed_n = recovered = multi = 0
    for k, rows in groups.items():
        if len(rows) > 1:
            multi += 1
        with_span = [r for r in rows if _has_excerpt(r)]
        if with_span:
            survivors, absorbed = with_span, [r for r in rows if not _has_excerpt(r)]
            recovered += len(absorbed)
        else:
            # No span anywhere on this url. Keep the strongest tier, then the
            # lowest id, so the choice is stable across processes and runs.
            rows_sorted = sorted(rows, key=lambda r: (str(r.get("tier") or "T9"),
                                                      str(r.get("e_id") or "")))
            survivors, absorbed = rows_sorted[:1], rows_sorted[1:]
        absorbed_n += len(absorbed)

        if absorbed:
            extra_links: set = set()
            for a in absorbed:
                extra_links.update(a.get("linked_subcap_ids") or [])
            also = sorted(str(a.get("e_id")) for a in absorbed if a.get("e_id"))
            for s in survivors:
                s["linked_subcap_ids"] = sorted(
                    set(s.get("linked_subcap_ids") or []) | extra_links)
                s["also_filed_as"] = sorted(set(s.get("also_filed_as") or []) | set(also))
        out.extend(survivors)

    out.sort(key=lambda it: order.get(id(it), 0))
    return out, {"absorbed": absorbed_n, "groups": multi,
                 "excerpts_recovered": recovered}
