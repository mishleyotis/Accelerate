"""Every agent states which model it runs on and why, from one owner.

Measured 28-09-2026 (QA audit F-C06-037): 58 sonnet / 15 opus / 1 haiku
and no agent said why, so a reader could not tell a deliberate tier from a
default. The reason lives in scripts/provision_agent_tools.py
(MODEL_REASONS), beside the grants; the manifest's frontmatter `model:`
and its first body line both come from it, and a generated manifest
renders the same line.
"""
import importlib.util
import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
AGENTS = PLUGIN / "agents"
FM = re.compile(r"^---\n(.*?)\n---\n", re.S)


def _prov():
    spec = importlib.util.spec_from_file_location(
        "provision_agent_tools", PLUGIN.parents[1] / "scripts" / "provision_agent_tools.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _manifests():
    for p in sorted(AGENTS.rglob("*.md")):
        if p.name == "README.md":
            continue
        text = p.read_text(encoding="utf-8")
        m = FM.match(text)
        yield p.stem, m.group(1), text[m.end():]


def test_every_agent_has_a_reason_and_the_table_has_no_stray():
    prov = _prov()
    names = {name for name, _, _ in _manifests()}
    assert names == set(prov.MODEL_REASONS), (names ^ set(prov.MODEL_REASONS))


def test_the_frontmatter_model_and_the_first_body_line_are_the_tables():
    prov = _prov()
    for name, fm, body in _manifests():
        model, why = prov.MODEL_REASONS[name]
        assert re.search(rf"^model: {model}$", fm, re.M), (name, model)
        first = next(l for l in body.splitlines() if l.strip())
        assert first == prov.model_line(name), (name, first)
        assert len(why) >= 40, name


def test_the_reason_names_the_work_not_the_price_alone():
    prov = _prov()
    for name, (model, why) in prov.MODEL_REASONS.items():
        assert not re.fullmatch(r"(cheap|fast|default|strong)[.]?", why.strip(), re.I), name


def test_the_distribution_is_the_audits_with_the_reasons_stated():
    """58 sonnet / 15 opus / 1 haiku on the day of the audit; moving one is
    a change to the table with its reason, which this test then records."""
    prov = _prov()
    counts = {}
    for model, _ in prov.MODEL_REASONS.values():
        counts[model] = counts.get(model, 0) + 1
    # +1 sonnet 2026-10-01: research-batch-producer (N-19, Northwest Bank QA),
    # the workflow's lean batch agent — its reason is in MODEL_REASONS.
    assert counts == {"sonnet": 59, "opus": 15, "haiku": 1}, counts
