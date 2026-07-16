"""Headline-gate contract: builder classes, spec exemplars, flags, fallback."""
import os

import pytest

from app.ml.gold.build_headline_gold import (
    SPEC_GOLD,
    SPEC_REJECT,
    build,
    threat_tone,
    vendor_first,
)
from app.ml.headline_gate import gate_headline, load_gate

_CLIENTS = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "startup-data", "clients"))


@pytest.mark.skipif(not os.path.isdir(_CLIENTS), reason="pack not present")
def test_builder_produces_balanced_labelled_rows():
    rows = build()
    # The reject pool shrinks as the pack's template/accusatory defects are
    # fixed (the enhancement's success), and the 3x balance cap tracks the
    # smaller class — assert structure, not volume; the shipped artifact
    # trains on the committed 450-row fixture, not this live mine.
    assert len(rows) >= 30
    gold = [r for r in rows if r["label"] == "gold"]
    reject = [r for r in rows if r["label"] == "reject"]
    assert gold and reject
    assert len(reject) <= 3 * len(gold) + 1
    texts = [r["text"] for r in rows]
    assert len(texts) == len({" ".join(t.casefold().split()) for t in texts})
    spec_texts = {r["text"] for r in rows if r["source"] == "spec"}
    assert any(t in spec_texts for t in SPEC_GOLD)
    assert any(t in spec_texts for t in SPEC_REJECT)


def test_vendor_first_flag():
    assert vendor_first("Salesforce Data Cloud is a leading CDP that unifies "
                        "customer data") is True
    assert vendor_first("Databricks offers a unified lakehouse platform") is True
    for gold in SPEC_GOLD:
        assert vendor_first(gold) is False, gold


def test_threat_tone_flag():
    assert threat_tone("Modernize now or risk falling behind competitors") is True
    assert threat_tone("Competitors will eat this book of business") is True
    for gold in SPEC_GOLD:
        assert threat_tone(gold) is False, gold


@pytest.mark.skipif(load_gate() is None, reason="artifact not trained")
def test_spec_exemplars_classify_correctly():
    wrong = []
    for t in SPEC_REJECT:
        r = gate_headline(t)
        if r["verdict"] != "reject":
            wrong.append(("reject", t, r))
    for t in SPEC_GOLD:
        r = gate_headline(t)
        if r["verdict"] != "gold":
            wrong.append(("gold", t, r))
    # the trained gate must clear the spec's own exemplars near-perfectly
    assert len(wrong) <= 1, wrong


def test_fallback_without_artifact(monkeypatch):
    load_gate.cache_clear()
    monkeypatch.setattr("app.ml.headline_gate._MODELS_DIR", "/nonexistent")
    try:
        r = gate_headline("Salesforce Data Cloud is a leading CDP that "
                          "unifies customer data")
        assert r["verdict"] == "reject" and r["vendor_first"] is True
        r2 = gate_headline("")
        assert r2["verdict"] == "reject"
    finally:
        load_gate.cache_clear()
