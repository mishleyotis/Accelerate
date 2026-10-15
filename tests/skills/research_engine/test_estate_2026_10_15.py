"""engine/estate.py — the engine's copy of the connector's estate identity
(AAA WCNY, 2026-10-15). The connector test (apps/mcp/tests/test_fit_estate.py)
holds the two equal; this one pins what `annotate` adds to fit rows."""
from engine import estate as E

CAT = [
    {"l3_id": "L3-MS-ANYPOINT", "vendor": "MuleSoft", "platform_name": "MuleSoft Anypoint Platform",
     "category": "iPaaS"},
    {"l3_id": "L3-SF-FSC", "vendor": "Salesforce",
     "platform_name": "Salesforce Financial Services Cloud (FSC)", "category": "Industry Cloud"},
    {"l3_id": "L3-SF-CRMA", "vendor": "Salesforce", "platform_name": "Salesforce CRM Analytics",
     "category": "Analytics"},
    {"l3_id": "L3-SF-TABLEAU", "vendor": "Salesforce / Tableau",
     "platform_name": "Tableau (Cloud + Server)", "category": "Analytics & BI"},
    {"l3_id": "L3-POWER-BI", "vendor": "Microsoft", "platform_name": "Microsoft Power BI",
     "category": "Analytics & BI"},
]
REG = [
    {"TS_ID": "TS-1", "Vendor": "Salesforce", "Product": "Salesforce CRM", "Status": "INFERRED"},
    {"TS_ID": "TS-2", "Vendor": "Microsoft", "Product": "Power BI", "Status": "INFERRED"},
    {"TS_ID": "TS-3", "Vendor": "MuleSoft", "Product": "MuleSoft Anypoint Platform",
     "Status": "CLAIMED"},
    {"TS_ID": "TS-4", "Vendor": "Salesforce", "Product": "Salesforce Data Cloud",
     "Status": "ABSENT"},
]


def _rows():
    return E.annotate([{"platform": c["platform_name"]} for c in CAT], REG, CAT)


def test_owned_extension_and_replacement_are_read_from_the_register():
    by = {r["platform"]: r for r in _rows()}
    assert by["MuleSoft Anypoint Platform"]["in_estate"] == "CLAIMED"
    assert by["Microsoft Power BI"]["in_estate"] == "INFERRED"
    fsc = by["Salesforce Financial Services Cloud (FSC)"]
    assert fsc["in_estate"] is None and fsc["vendor_in_estate"] == "INFERRED"
    assert by["Salesforce CRM Analytics"]["in_estate"] is None       # never "CRM" ~ "CRM Analytics"
    assert by["Tableau (Cloud + Server)"]["replaces_in_estate"] == ["Power BI"]


def test_an_absent_row_owns_nothing_and_connector_fields_are_kept():
    rows = E.annotate([{"platform": "Salesforce Data Cloud", "in_estate": "X"}], REG, CAT)
    assert rows[0]["in_estate"] == "X"
    assert not E.estate_same("Salesforce CRM", "Salesforce", "CRM Analytics (Tableau CRM)", "Tableau")
