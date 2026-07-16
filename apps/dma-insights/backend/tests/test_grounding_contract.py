"""Grounding-contract contract: should_refuse branches, refusal wording,
probe builder classes, prompt inclusion."""
import json
import os

os.environ.setdefault("DMA_DISABLE_SEMANTIC", "1")

from app.services.grounding_contract import (
    REFUSAL_SENTINEL,
    refusal_answer,
    should_refuse,
)


def test_refuses_empty_bundle():
    refuse, reason = should_refuse("What is Alma Bank's revenue?", [])
    assert refuse and reason == "empty_bundle"


def test_refuses_irrelevant_bundle():
    bundle = [{"text": "Migratory songbirds cross the Gulf of Mexico in "
                       "spring at altitudes above two thousand feet."}]
    refuse, reason = should_refuse(
        "What is the institution's annual revenue?", bundle)
    assert refuse and reason in ("no_relevant_evidence",
                                 "quantity_without_numbers")


def test_refuses_quantity_without_numbers():
    bundle = [{"text": "The bank's revenue outlook was described by "
                       "management as stable, with revenue diversification "
                       "a stated priority."}]
    refuse, reason = should_refuse("What is the bank's annual revenue?", bundle)
    assert refuse and reason in ("quantity_without_numbers",
                                 "fact_not_established")


def test_answers_when_relevant_numeric_evidence_exists():
    bundle = [{"text": "Annual report: the bank recorded revenue of $412M "
                       "for fiscal 2025, up 6% year over year."}]
    refuse, _ = should_refuse("What is the bank's annual revenue?", bundle)
    assert not refuse


def test_answers_non_quantity_relevant_question():
    bundle = [{"text": "The bank is headquartered in Buffalo, New York, "
                       "with regional offices across the Northeast."}]
    refuse, _ = should_refuse("Where is the bank headquartered?", bundle)
    assert not refuse


def test_refusal_answer_contains_sentinel_and_g9_offer():
    text = refusal_answer("quantity_without_numbers")
    assert REFUSAL_SENTINEL in text
    assert "G9" in text
    assert "validator" not in text.lower()


def test_contract_block_in_prompt():
    from app.services.rag_answer import GroundingBundle, build_answer_prompt
    prompt = build_answer_prompt(
        question="What changed?", bundle=GroundingBundle(items=[]),
        style="concise", max_paragraphs=2)
    assert REFUSAL_SENTINEL in prompt
    assert "INFERENCE" in prompt


def test_probe_builder_emits_both_classes(tmp_path):
    clients = tmp_path / "clients"
    a = clients / "null-bank-0001"
    a.mkdir(parents=True)
    (a / "overview.json").write_text(json.dumps({
        "entity": {"name": "Null Bank"},
        "firmographics": {"revenue_usd": None, "founded": None,
                          "hq": "Springfield, IL"},
    }))
    (a / "techstack.json").write_text(json.dumps({"items": []}))
    (a / "evidence.json").write_text(json.dumps({"items": [
        {"e_id": "E-001",
         "excerpt": "Null Bank is headquartered in Springfield and serves "
                    "central Illinois."}]}))
    from app.ml.gold.build_refusal_probes import build
    rows = build(str(clients))
    expects = {r["expect"] for r in rows}
    assert "refuse" in expects and "answer" in expects
    styles = {r["style"] for r in rows if r["expect"] == "refuse"}
    assert "adversarial" in styles
    controls = [r for r in rows if r["expect"] == "answer"]
    assert all(r.get("expected_substring") for r in controls)
