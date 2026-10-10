"""gold://web-app-requirements says who sees each section — RC-01e / D-35.

SWBC gold audit, 2026-10-04: the resource listed `overview.sentiment` as
served with no audience qualifier, while the customer body withheld it whole.
A producer reading "served" wrote for a customer who never saw the card.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_mcp import resources  # noqa: E402


def test_every_section_carries_its_audience_disposition():
    from dma_api import redaction as R
    disp = resources.web_app_requirements()["audience_disposition"]
    for page, section in R.CUSTOMER_WITHHELD - R.NEVER_SERVED:
        assert disp[f"{page}.{section}"]["customer"] == "withheld", section
    for page, section in R.NEVER_SERVED:
        assert disp[f"{page}.{section}"] == {"internal": "never_served",
                                             "customer": "never_served"}
    for page in R.CUSTOMER_WITHHELD_PAGES:
        rows = [v for k, v in disp.items() if k.startswith(page + ".")]
        assert rows and all(v["customer"] == "page_withheld" for v in rows)


def test_the_resource_names_the_gold_shape():
    assert "surface_gold.json" in resources.web_app_requirements()["gold_shape"]
