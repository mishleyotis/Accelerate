"""The committed customer sentiment projection IS what redaction serves.

Owner decision 1 (2026-10-04): the customer gets a reduced sentiment card,
ratings bars and themes, with no cell codes, internal sources, cap
vocabulary or r_layer. Round 1 changed the card and the projection in two
separate streams. The card's tests rendered a hand-built imitation of the
customer body (`customerCopy` in the web fixture), so nothing tied the card
to what `redact_section` actually returns.

`fixtures/projections/sentiment_customer.json` holds synthetic sentiment
inputs together with the customer body that this module's redaction serves
for each. The web suite renders those bodies
(apps/web/tests/sentiment-customer-projection.test.js). This test fails the
moment the projection drifts from the committed bodies, so the card is
always tested against the real wire shape.

Regenerate after an intended projection change, then re-run the web suite:
    python tests/test_sentiment_projection_fixture.py --write
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_api.redaction import redact_section

FIXTURE = (Path(__file__).resolve().parents[3] / "fixtures" / "projections"
           / "sentiment_customer.json")


def _project(case: dict) -> dict:
    data = copy.deepcopy(case["input"])
    out, _ = redact_section("overview", "sentiment", data,
                            data.get("internal_only") or [], "customer",
                            case.get("evidence_scope"))
    return out


def _load() -> dict:
    return json.loads(FIXTURE.read_text())


def test_the_committed_customer_body_is_what_redaction_serves():
    for name, case in sorted(_load()["cases"].items()):
        _same(name, case)


def _same(name, case):
    assert _project(case) == case["customer"], (
        f"{name}: the customer sentiment projection drifted from the body the "
        "web card is tested against. Regenerate with "
        "`python tests/test_sentiment_projection_fixture.py --write` and "
        "re-run apps/web tests/sentiment-customer-projection.test.js")


def test_the_projection_is_the_reduced_card():
    """Decision 1, read off the committed bodies: bars and themes reach the
    customer, and the analyst's half does not."""
    for name, case in _load()["cases"].items():
        cust = case["customer"]
        assert cust is not None, f"{name}: sentiment withheld whole"
        assert cust.get("themes"), f"{name}: no themes reached the customer"
        for gone in ("r_layer", "gap_analysis", "narrative_thread"):
            assert gone not in cust, f"{name}: {gone} reached the customer"
        for t in cust["themes"]:
            assert "cap_statement" not in t and "mapped_subcap_ids" not in t


if __name__ == "__main__" and "--write" in sys.argv:
    doc = _load()
    for case in doc["cases"].values():
        case["customer"] = _project(case)
    FIXTURE.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {FIXTURE}")
