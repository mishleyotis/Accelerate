"""CG-38 — a financial figure is quoted from a filing, never computed.

Owner, 2026-08-22: "Have a clear prohibition against derived figures, figures
should verbatim come from 10-K filings or company financials."

The case that produced the rule is worth keeping, because it is the one that
would have got through. Building the T. Rowe Price five-year trajectory,
FY2023 was reachable two ways:

    the FY2023 Form 10-K     "At December 31, 2023, we had $1,444.5 billion
                              in assets under management…"
    the FY2024 Form 10-K     "At December 31, 2024, we had $1,606.6 billion…
                              an increase of $162.1 billion from the end of
                              2023."   ->  1606.6 - 162.1 = 1444.5

Both give 1444.5. Only one is a disclosure.

WHY NOTHING ELSE CATCHES IT. The derived figure is the RIGHT number. It
carries a real evidence id; the id resolves; the row belongs to this entity
and run; its excerpt is a genuine verbatim span, 50-500 chars, from a genuine
filing that really does mention 2023. ET-01, ET-02, ET-04, the dating checks
and the fetcher's own verbatim verification all pass. The only false thing is
the relationship between the number and the sentence.

SCALE IS NOT ARITHMETIC. Writing a stated $1.89 trillion as 1890 USD billions
is a representation change — the digits are still the filer's — and the
series must hold one unit or the adapter renders four of six points off by a
factor of 1000. Subtracting one stated figure from another produces digits
that appear in no sentence anywhere. The gate compares mantissas, which is
exactly the line between those two.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp.gates import GATES                                      # noqa: E402
from dma_mcp.validation2 import (_mantissa,                          # noqa: E402
                                 _check_financial_figures_are_quoted as quoted)

FY2023 = ("At December 31, 2023, we had $1,444.5 billion in assets under "
          "management, an increase of $169.8 billion from 2022.")
FY2024 = ("At December 31, 2024, we had $1,606.6 billion in assets under "
          "management, an increase of $162.1 billion from the end of 2023.")
Q2_26 = ("Assets under management ended the second quarter of 2026 at $1.89 "
         "trillion, with $6.5 billion in net outflows during the quarter.")


def _row(e_id, excerpt):
    return {"e_id": e_id, "excerpt": excerpt}


def _series(*points):
    return {"financial_series": {"series": [
        {"value": v, "source_e_id": e, "unit": "USD billions"}
        for v, e in points]}}


# ── the defect ──


def test_a_figure_reached_by_subtraction_is_refused():
    """1606.6 - 162.1 = 1444.5, cited to the filing that states neither."""
    out = quoted([_row("E-CC-400", FY2024)], {}, _series((1444.5, "E-CC-400")))
    assert len(out) == 1
    assert out[0]["path"] == "financial_series.series[0].value"
    assert "does not appear in the span" in out[0]["message"]
    assert "E-CC-400" in out[0]["message"]


def test_the_refusal_names_the_comparative_route():
    """A producer told only "wrong" re-cites the same filing. Told how the
    number got there, it goes and finds the year's own filing."""
    out = quoted([_row("E-CC-400", FY2024)], {}, _series((1444.5, "E-CC-400")))
    assert "comparative" in out[0]["message"]
    assert "subtraction" in out[0]["message"]


def test_the_same_figure_cited_to_its_own_filing_passes():
    """The pair. The number is identical; only the citation differs, and that
    is the whole of what this gate measures."""
    assert quoted([_row("E-CC-401", FY2023)], {},
                  _series((1444.5, "E-CC-401"))) == []


def test_every_point_is_checked_not_just_the_first():
    out = quoted([_row("E-CC-401", FY2023), _row("E-CC-400", FY2024)], {},
                 _series((1444.5, "E-CC-401"), (9999.9, "E-CC-400")))
    assert len(out) == 1
    assert out[0]["path"] == "financial_series.series[1].value"


# ── scale is a representation, not a derivation ──


def test_a_stated_trillion_carried_in_billions_passes():
    """1.89 trillion -> 1890 USD billions. The digits are the filer's, and
    the series must hold one unit or the adapter mis-scales it."""
    assert quoted([_row("E-CC-347", Q2_26)], {},
                  _series((1890, "E-CC-347"))) == []


def test_thousand_separators_and_currency_marks_do_not_matter():
    assert quoted([_row("E-CC-402", "…we had $1,687.8 billion in assets…")],
                  {}, _series((1687.8, "E-CC-402"))) == []


def test_mantissa_strips_scale_and_separators_but_keeps_the_digits():
    assert _mantissa(1687.8) == _mantissa("$1,687.8 billion") == "16878"
    assert _mantissa(1890) == _mantissa("1.89 trillion") == "189"
    assert _mantissa(1444.5) != _mantissa(1606.6)


def test_a_near_miss_is_still_a_miss():
    """1,444.5 and 1,444.6 have different digits. A gate that compared
    magnitudes would let a transcription slip through."""
    assert len(quoted([_row("E-CC-401", FY2023)], {},
                      _series((1444.6, "E-CC-401")))) == 1


# ── what must NOT be refused ──


def test_an_unresolvable_id_is_left_to_the_identity_gates():
    """ET-01 and ET-02 own a fabricated id, and two gates refusing one defect
    make a producer chase the wrong one."""
    assert quoted([], {}, _series((1444.5, "E-CC-999"))) == []


def test_a_point_with_no_figure_is_not_this_gate_s_business():
    payload = {"financial_series": {"series": [
        {"value": None, "source_e_id": "E-CC-401"},
        {"source_e_id": "E-CC-401"}]}}
    assert quoted([_row("E-CC-401", FY2023)], {}, payload) == []


def test_maturity_scores_are_not_financial_disclosures():
    """A score is produced BY the assessment; requiring it to appear in a
    source would refuse every score this product exists to compute."""
    payload = {"workbook_scores": {"series": [
        {"value": 2.21, "source_e_id": "E-CC-401"}]}}
    assert quoted([_row("E-CC-401", FY2023)], {}, payload) == []


def test_non_dict_payloads_are_ignored():
    assert quoted([], {}, None) == [] and quoted([], {}, []) == []


def test_a_boolean_is_not_a_figure():
    payload = {"financial_series": {"series": [
        {"value": True, "source_e_id": "E-CC-401"}]}}
    assert quoted([_row("E-CC-401", FY2023)], {}, payload) == []


# ── the real five-year series ──


REAL = [
    (1687.8, "At December 31, 2021, we had $1,687.8 billion in assets under "
             "management, including $871.4 billion in U.S. mutual funds."),
    (1274.7, "At December 31, 2022, we had $1,274.7 billion in assets under "
             "management, including $627.8 billion in U.S. mutual funds."),
    (1444.5, FY2023),
    (1606.6, FY2024),
    (1775.6, "At December 31, 2025, we had $1,775.6 billion in assets under "
             "management, an increase of $169.0 billion from the end of 2024."),
]


def test_the_whole_promoted_trajectory_passes():
    rows = [_row(f"E-CC-{410 + i}", ex) for i, (_, ex) in enumerate(REAL)]
    payload = _series(*[(v, f"E-CC-{410 + i}") for i, (v, _) in enumerate(REAL)])
    assert quoted(rows, {}, payload) == []


def test_shifting_any_one_point_to_its_neighbour_s_filing_is_caught():
    """The concrete slip: cite the year you have open rather than the year you
    are stating. Every one of the five is caught."""
    rows = [_row(f"E-CC-{410 + i}", ex) for i, (_, ex) in enumerate(REAL)]
    for i, (v, _) in enumerate(REAL):
        other = f"E-CC-{410 + (i + 1) % len(REAL)}"
        out = quoted(rows, {}, _series((v, other)))
        assert len(out) == 1, f"point {i} ({v}) cited to {other} was not caught"


# ── registered and wired ──


def test_the_gate_is_registered_and_blocks():
    assert "CG-38" in GATES
    assert GATES["CG-38"][-1] == "block"


def test_the_check_is_wired_into_pass_two():
    import ast
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "validation2.py").read_text(encoding="utf-8")
    called = {getattr(n.func, "id", None) for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.Call)}
    assert "_check_financial_figures_are_quoted" in called
