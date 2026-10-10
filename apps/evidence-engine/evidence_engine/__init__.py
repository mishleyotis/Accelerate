"""DMA Insights evidence engine — gold-standard evidence cards, not pages.

The mechanical half of research (search fan-out, crawl, extraction, dating,
dedupe, ranking, verbatim excerpt selection, liveness, provenance) runs
here, deterministically and without a model; the reasoning half (subcap
linkage, claim labels, final tier, contradiction disposition) stays with the
plugin's agents. See docs/CARD-CONTRACT.md and docs/DISCOVERY.md.

No client-specific string may appear anywhere in this package
(`tests/test_no_client_strings.py` greps for it in CI).
"""
__version__ = "0.1.0"
