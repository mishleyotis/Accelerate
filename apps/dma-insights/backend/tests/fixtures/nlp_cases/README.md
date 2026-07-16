# NLP regression cases — the fixture-learning convention

This directory is where the NLP platform permanently learns each report quirk.
Whenever `app/services/nlp/quality.rubric_score` (or a review agent running it
during convergence) fails a derived surface — a mis-resolved date, a negation
rendered as an event, a template phrase, a spurious year-series — the failure
is captured here as a small case file pairing the offending **input excerpt**
with the **expected extraction** (for example a JSON file with `{"input": …,
"expect": {"module": "dates", "call": "resolve_event_date", "result":
["2025-08-01", "quarter"]}}`), and `tests/test_nlp_platform.py` (or a dedicated
case-runner test) asserts it forever. The rule from the remediation plan
(Part 2): every rubric failure becomes BOTH a deterministic rule/pattern in the
toolkit AND a regression fixture in this directory — so no report shape ever
regresses twice.
