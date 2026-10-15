"""The fit engine's estate identity (AAA WCNY, 2026-10-15): exact token-set
identity, never containment, so "Salesforce CRM" never marks CRM Analytics
as owned and "Power BI" is "Microsoft Power BI"."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from dma_mcp.fit import _estate_same, _register_products  # noqa: E402


@pytest.mark.parametrize("product,pv,platform,cv,same", [
    ("Salesforce CRM", "Salesforce", "Salesforce CRM Analytics", "Salesforce", False),
    ("Salesforce CRM", "Salesforce", "CRM Analytics (Tableau CRM)", "Tableau", False),
    ("Salesforce CRM", "Salesforce", "Salesforce Financial Services Cloud (FSC)", "Salesforce", False),
    ("Salesforce CRM", "Salesforce", "Salesforce Data Cloud (Data 360)", "Salesforce", False),
    ("Power BI", "Microsoft", "Microsoft Power BI", "Microsoft", True),
    ("Databricks Lakehouse (Azure Databricks)", "Databricks",
     "Databricks Data Intelligence Platform (Lakehouse)", "Databricks", True),
    ("Microsoft Azure", "Microsoft", "Microsoft Azure", "Microsoft Azure", True),
    ("Microsoft Azure", "Microsoft", "Azure AI Search", "Microsoft Azure", False),
    ("MuleSoft Anypoint Platform", "MuleSoft", "MuleSoft Anypoint Platform", "MuleSoft", True),
    ("Salesforce Service Cloud", "Salesforce", "Service Cloud", "Salesforce", True),
    ("Tableau", "Tableau", "Tableau Pulse", "Salesforce / Tableau", False),
])
def test_estate_identity(product, pv, platform, cv, same):
    assert _estate_same(product, pv, platform, cv) is same


class _Cur:
    def __init__(self, staged, raw=()):
        self.staged, self.raw, self._rows = staged, list(raw), []

    def execute(self, sql, args=None):
        s = " ".join(sql.split())
        if "FROM submissions" in s:
            self._rows = [(self.staged,)] if self.staged else []
        elif "FROM techstack_raw" in s:
            self._rows = [(r,) for r in self.raw]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


def test_the_register_places_products_in_the_estate_absent_never():
    staged = {"techstack": {"items": [
        {"vendor": "MuleSoft", "product": "MuleSoft Anypoint Platform", "status": "CLAIMED"},
        {"vendor": "Microsoft", "product": "Power BI", "status": "INFERRED"},
        {"vendor": "Salesforce", "product": "Data Cloud", "status": "ABSENT"}]}}
    got = _register_products(_Cur(staged), "R")
    assert ("MuleSoft", "MuleSoft Anypoint Platform", "CLAIMED") in got
    assert all(p != "Data Cloud" for _, p, _ in got)


def test_the_engine_copy_is_the_same_identity():
    sys.path.insert(0, str(ROOT / "plugins" / "dma-insights" / "skills" / "dma-research"))
    from engine import estate as E
    from dma_mcp import fit as F
    assert E.GENERIC_TOKENS == F._GENERIC_TOKENS
    assert E.GENERIC_CATEGORIES == F._GENERIC_CATEGORIES
    names = ["Salesforce CRM", "Salesforce CRM Analytics", "CRM Analytics (Tableau CRM)",
             "Power BI", "Microsoft Power BI", "Microsoft Azure", "Azure AI Search",
             "Databricks Lakehouse (Azure Databricks)",
             "Databricks Data Intelligence Platform (Lakehouse)", "MuleSoft Anypoint Platform",
             "Service Cloud", "Salesforce Service Cloud", "Tableau", "Tableau Pulse"]
    vendors = ["Salesforce", "Microsoft", "Microsoft Azure", "Databricks", "MuleSoft",
               "Tableau", "Salesforce / Tableau"]
    for a in names:
        for b in names:
            for va in vendors:
                for vb in vendors:
                    assert E.estate_same(a, va, b, vb) == F._estate_same(a, va, b, vb), (a, b, va, vb)
