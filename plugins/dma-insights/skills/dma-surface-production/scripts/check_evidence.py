#!/usr/bin/env python3
"""Check the run's evidence register for pairings that cannot both be true.

    python scripts/check_evidence.py get_evidence.json
    python scripts/check_evidence.py get_evidence.json --review

Input is a `get_evidence(run_id, e_ids=[...])` response, or the API's
`/v1/entities/<id>/evidence` body, or a bare list of rows. Ask for every id
the run carries, not only the cited ones — an uncited row is still a row a
later page will reach for.

WHAT THIS IS FOR. An excerpt is a verbatim span of the document at
`source_url`. The pairing is the claim: it says "open this and you will find
these words". Registering a TRUE claim under a URL that does not contain it is
fabrication by construction, and the truth of the claim is no defence — a
reader who clicks the chip lands on a page that does not say what the card
says it says.

The defect does not look like a fabricated quote. It looks like two documents
read in one sitting and four rows minted afterwards, with the pairing crossed
over. On the run this was written against, `E-CC-001` carried BCU's own
newsroom prose under a third-party directory URL and was cited nine times on
the heatmap, while `E-CC-003` carried the same span under the newsroom page
that actually holds it.

WHAT IT CAN CHECK, without fetching anything:

  DUP-HOST   one excerpt registered under two different hosts. No verbatim
             span is a verbatim span of two different documents unless you
             say it is syndicated, and this is the check that catches the
             crossed pairing without any name heuristic.
  NOT-A-URL  a `source_url` that is not an http(s) document — the literal
             string "multiple", a bare path, a tool endpoint.
  SEARCH     a search-results page. It contains no span you can quote. A
             negative search result is a rung in the absence ladder, recorded
             as sources_searched, never an evidence row.
  BARE       an excerpt with no URL, or a row with no publisher name.

WHAT IT CANNOT CHECK. A single row whose excerpt simply is not on its page.
Nothing short of fetching the URL can, and `register_evidence` does exactly
that — which is why registering from the artefact in the same step you fetch
it is the real control, and this script is only the net underneath.

`--review` prints the publisher named in `source_name` beside the URL's host
where they share no token. That list is for READING, not refusing: a wire
service carrying a vendor's release, an archive, a regulator's own domain and
a publisher that has rebranded all land in it legitimately, and on the run
measured here 25 of the 31 rows it questioned were one of those four.

Exit 0 = no blocking pairings, 1 = at least one.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.parse import urlparse

SEARCH_HOSTS = ("google.", "bing.", "duckduckgo.", "search.yahoo.", "baidu.")
# Endpoints that FIND a source and are never the source. "Cite the source, not
# the tool" — a value with no traceable document behind it is an inference.
TOOL_HOSTS = ("explorium.ai", "clay.com", "clay.run", "builtwith.com",
              "wappalyzer.com", "hubbl.io", "zoominfo.com", "apollo.io")
# Publisher-name tokens that carry no identifying signal against a hostname.
STOP = {"the", "and", "for", "inc", "llc", "report", "annual", "news", "press",
        "release", "releases", "profile", "page", "pages", "data", "review",
        "reviews", "rating", "ratings", "company", "official", "site",
        "website", "com", "org", "net", "gov", "www", "about", "events",
        "list", "index", "home", "credit", "union", "bank", "corp",
        "corporation", "group", "holdings", "of", "at", "in", "on", "to",
        "a", "an", "from", "with", "by", "case", "study", "consolidation",
        "carry", "forward", "summary", "confirmation", "results"}


def rows(doc):
    """Every evidence row in whatever shape the caller had to hand."""
    if isinstance(doc, list):
        return [r for r in doc if isinstance(r, dict)]
    out = []
    for key in ("found", "items", "evidence", "rows"):
        val = doc.get(key)
        if isinstance(val, list):
            out.extend(r for r in val if isinstance(r, dict))
    return out


def host(url):
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    h = parsed.hostname.lower()
    return h[4:] if h.startswith("www.") else h


def is_search(url):
    h = host(url) or ""
    if any(h.startswith(s) or f".{s}" in f".{h}" for s in SEARCH_HOSTS):
        return "?q=" in url or "/search" in url
    return False


def publisher_tokens(name):
    """(tokens, acronym) of the publisher prefix of a source name."""
    prefix = re.split(r"\s+[—–|:·-]\s+", name or "", 1)[0]
    words = re.findall(r"[A-Za-z0-9]+", prefix)
    toks = [w.lower() for w in words if len(w) >= 3 and w.lower() not in STOP]
    acronym = "".join(w[0] for w in words if w[0].isalpha()).lower()
    return toks, acronym


def name_matches_host(name, h):
    if not name or not h:
        return True
    flat = h.replace(".", "")
    toks, acronym = publisher_tokens(name)
    if any(t in flat for t in toks):
        return True
    # "Baxter Credit Union Annual Report" against bcu.org: the initials of the
    # LEADING words are the acronym a host is registered under, and the words
    # after it are the document, not the publisher.
    if any(acronym[:n] in flat for n in range(len(acronym), 1, -1)):
        return True
    every = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", name)
             if len(w) >= 4 and w.lower() not in STOP]
    return any(t in flat for t in every)


def check(evidence):
    blocking, review = [], []
    by_excerpt: dict[str, list[dict]] = {}

    for r in evidence:
        eid = r.get("e_id") or r.get("stored_id") or "<no id>"
        url = r.get("source_url")
        name = (r.get("source_name") or "").strip()
        excerpt = (r.get("excerpt") or "").strip()
        h = host(url)

        if excerpt and not url:
            blocking.append((eid, "BARE",
                             "carries an excerpt and no source_url — an "
                             "excerpt is a span OF a document; without the "
                             "address it is an unattributable quotation"))
        elif url and h is None:
            blocking.append((eid, "NOT-A-URL",
                             f"source_url is {str(url)[:60]!r}, which is not "
                             "an http(s) document. A reader cannot open it and "
                             "register_evidence cannot verify the span "
                             "against it"))
        elif is_search(url):
            blocking.append((eid, "SEARCH",
                             f"source_url is a search-results page ({h}). It "
                             "holds no span you can quote. A negative search "
                             "is a rung in the absence ladder — record it in "
                             "sources_searched, not as an evidence row"))
        elif h and any(h.endswith(t) for t in TOOL_HOSTS):
            blocking.append((eid, "TOOL",
                             f"source_url is the enrichment tool ({h}), not "
                             "the source. Cite the filing, listing or page the "
                             "tool surfaced — a value with no traceable "
                             "document is an inference, and is labelled one"))
        if excerpt and not name:
            blocking.append((eid, "BARE",
                             "no source_name — the drawer prints the "
                             "publisher above the quote, and a quote with no "
                             "publisher is unattributed"))
        if len(excerpt) >= 50:
            by_excerpt.setdefault(excerpt, []).append(r)
        if h and name and not name_matches_host(name, h):
            review.append((eid, name, h))

    for excerpt, group in by_excerpt.items():
        if len(group) < 2:
            continue
        hosts = {host(r.get("source_url")) for r in group}
        ids = sorted(r.get("e_id") or "?" for r in group)
        urls = sorted({str(r.get("source_url")) for r in group})
        if len(hosts) > 1:
            blocking.append((", ".join(ids), "DUP-HOST",
                             "one excerpt registered under "
                             f"{len(hosts)} different hosts — {' vs '.join(urls)}"
                             ". At most one of these documents contains this "
                             "span. Keep the row whose URL you actually "
                             "fetched it from and drop the other; if the piece "
                             "is genuinely syndicated, register the one you "
                             "read and say so. Excerpt: "
                             f"{excerpt[:90]}…"))
        else:
            review.append((", ".join(ids), "same excerpt, same host",
                           "two rows the content dedup did not merge"))
    return blocking, review


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("evidence", help="get_evidence output, as JSON")
    ap.add_argument("--review", action="store_true",
                    help="also print the publisher-vs-host reading list")
    a = ap.parse_args(argv)

    try:
        doc = json.load(open(a.evidence, encoding="utf-8"))
    except Exception as exc:                                   # noqa: BLE001
        print(f"could not read {a.evidence}: {exc}")
        return 1

    evidence = rows(doc)
    if not evidence:
        print("no evidence rows in that file — pass a get_evidence response, "
              "the API's /evidence body, or a bare list of rows")
        return 1

    blocking, review = check(evidence)
    print(f"\n  evidence rows read: {len(evidence)}")
    print(f"  pairings that cannot both be true: {len(blocking)}")
    print(f"  publisher/host rows to read: {len(review)}\n")

    if blocking:
        print("  REFUSE — the excerpt and the URL are one claim\n")
        for eid, kind, msg in blocking:
            print(f"    [{kind}] {eid}\n            {msg}\n")
    if a.review and review:
        print("  REVIEW — the publisher named and the host do not share a "
              "token.\n  A wire service, an archive, a regulator's own domain "
              "and a rebrand all\n  land here legitimately. Read, do not "
              "refuse.\n")
        for row in review:
            print("    " + " · ".join(str(x) for x in row))
        print()
    if not blocking:
        print("  no impossible pairings. The one thing this cannot check is "
              "whether a\n  single excerpt is actually on its own page — only "
              "fetching it can, and\n  register_evidence does that at "
              "registration.\n")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
