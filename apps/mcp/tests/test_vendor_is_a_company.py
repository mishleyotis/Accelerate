"""CG-20 — a vendor is a company, not a category.

The contract has always said it: "A PRODUCT, not a service and not a category
— 'Salesforce Financial Services Cloud' is a product; 'CRM', 'Analytics/BI',
'Django' are not; vendor and product are separate fields." Nothing checked it,
so rows reading `vendor: "Integration platform"` and `vendor: "e-signature
vendor (unnamed)"` promoted onto a client's technology register beside
Salesforce and Fortinet. The build owner called them noise entries: a
placeholder for research that did not finish, rendered with the same weight as
a confirmed deployment.

THE MEASUREMENT that makes this safe to block, taken over both promoted
registers on 2026-08-14: 39 distinct vendors, of which exactly 3 are
categories and 36 are real companies. The false-positive tests below carry the
36 — including the one that would break a naive rule.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation import _check_vendor_is_a_company


def _run(rows):
    return _check_vendor_is_a_company("techstack", "items", {}, rows)


def _row(vendor, product="Some Product"):
    return {"vendor": vendor, "product": product}


# ── the three the corpus actually carried ─────────────────────────────
def test_the_three_real_placeholder_rows_are_refused():
    """Verbatim from the promoted register."""
    for v in ("Integration platform", "Portal platform (unnamed)",
              "e-signature vendor (unnamed)"):
        out = _run([_row(v)])
        assert len(out) == 1, v
        assert out[0]["gate_id"] == "CG-20" and out[0]["severity"] == "block"


def test_a_placeholder_is_named_as_unfinished_research():
    out = _run([_row("Portal platform (unnamed)")])
    assert "placeholder" in out[0]["message"]
    assert "did not finish" in out[0]["message"]


def test_a_bare_category_is_named_as_a_category():
    out = _run([_row("Integration platform")])
    assert "CATEGORY" in out[0]["message"]


# ── the 36 that must keep passing ─────────────────────────────────────
def test_every_real_vendor_in_the_corpus_passes():
    """The full distinct-vendor list from both promoted registers, minus the
    three. If a future word is added to the generic set and one of these
    starts failing, this test is the one that says so."""
    real = ["Adobe", "Alloy", "Amazon Web Services", "Apple", "Astra",
            "AviaryAI", "BioCatch", "Blend", "Blue Prism", "Bonzo",
            "Broadridge", "Citrix", "Creovai", "Early Warning Services",
            "Fortinet", "Genesys", "Glia", "Google", "IBM", "Jack Henry",
            "LogicGate", "Lumin Digital", "Medallia", "Microsoft", "MuleSoft",
            "Odlum Brown", "Salesforce", "SavvyMoney", "SnapEngage",
            "Tealium", "Temenos", "UiPath", "Workday", "Zendesk", "Zoho",
            "Zscaler"]
    assert len(real) == 36
    out = _run([_row(v) for v in real])
    assert out == [], [r["path"] for r in out]


def test_a_real_vendor_carrying_a_generic_word_still_passes():
    """"Early Warning Services" is the row that breaks a naive rule: its third
    word IS generic. The test is all-words-generic, not any-word-generic."""
    assert _run([_row("Early Warning Services")]) == []
    assert _run([_row("Lumin Digital")]) == []


# ── product must not repeat its vendor ────────────────────────────────
def test_product_equal_to_vendor_is_refused():
    out = _run([{"vendor": "Salesforce", "product": "Salesforce"}])
    assert len(out) == 1
    assert "both" in out[0]["message"]
    assert out[0]["path"].endswith(".product")


def test_a_product_that_merely_starts_with_its_vendor_is_fine():
    """"Salesforce Marketing Cloud" is a real product name and the commonest
    shape in the corpus."""
    assert _run([{"vendor": "Salesforce",
                  "product": "Salesforce Marketing Cloud"}]) == []


# ── shape and scope ───────────────────────────────────────────────────
def test_the_reason_names_the_offending_row_by_index():
    out = _run([_row("Fortinet"), _row("Integration platform")])
    assert out[0]["path"] == "techstack.items[1].vendor"


def test_a_missing_vendor_is_not_this_gate_s_business():
    """CG-02 and the item-evidence sweep own an absent field; this gate only
    judges a vendor that IS stated."""
    assert _run([{"product": "Something"}]) == []
    assert _run([{"vendor": "   ", "product": "Something"}]) == []


def test_it_only_runs_on_the_techstack_register():
    rows = [_row("Integration platform")]
    assert _check_vendor_is_a_company("firmographics", "items", {}, rows) == []
    assert _check_vendor_is_a_company("techstack", "dropped", {}, rows) == []


def test_non_dict_rows_do_not_raise():
    assert _run(["nonsense", None, 42]) == []


def test_it_is_registered_so_a_verdict_can_be_explained():
    from dma_mcp.gates import GATES
    assert "CG-20" in GATES and GATES["CG-20"][-1] == "block"
