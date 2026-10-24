"""What a production agent reads before its first tool call, measured.

Measured 28-09-2026 (QA audit F-E01-026): on the audit's basis — SKILL.md,
the page pack, 1-gates.md and routing.md — a heatmap production session
read ≈47k tokens (23 % of a 200k window) before its first tool call, the
overview 56k (28 %); the threshold is 15 %. Measured on the agents' FULL
reading orders (which also name the rulebook, the doctrine files and the
input maps) the load was 41–55 % per per-surface producer.

W3-4 split the page packs, the rulebooks and the gate book one file per
surface or gate, and every reading order names the files its surface
needs. These tests hold the two figures: the audit's basis under 15 %,
and the full reading order under a ceiling that only ratchets down.
Tokens are bytes/4, the audit's own method.
"""
import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2]
SP = PLUGIN / "skills" / "dma-surface-production"
REF = re.compile(r"`\$\{CLAUDE_PLUGIN_ROOT\}/([^`\s]+)`")
WINDOW = 200_000
#: the audit's threshold, on the audit's basis
BASIS_CEILING = int(0.15 * WINDOW)
#: the full reading order: 32 % today (platform-fit 30.9 % measured after
#: W3-5 trimmed SKILL.md to 7.5k tokens, from 32.8 % after W3-4 and 43.4 %
#: before); lower it as the doctrine files and routing.md shrink, never
#: raise it
FULL_CEILING = int(0.32 * WINDOW)


def _tok(p: Path) -> int:
    return len(p.read_bytes()) // 4


def _producers():
    return sorted(p for p in (PLUGIN / "agents" / "production").rglob("*-producer.md")
                  if not p.name.endswith("-surface-producer.md"))


def _reading_order(md: Path):
    seen = []
    for rel in REF.findall(md.read_text(encoding="utf-8")):
        f = PLUGIN / rel
        if f.is_file() and rel not in seen:
            seen.append(rel)
    return seen


@pytest.mark.parametrize("md", _producers(), ids=lambda p: p.stem)
def test_the_audits_basis_is_under_fifteen_percent(md):
    """SKILL.md + the surface's own pack file(s) + the gate files named +
    routing.md — what the audit counted, now per surface rather than per
    page and per gate rather than per book."""
    order = _reading_order(md)
    packs = [r for r in order if "/03-pages/" in r and "/rulebooks/" not in r]
    gates = [r for r in order if "/05-lifecycle/gates/" in r]
    assert packs, f"{md.name} names no per-surface pack file"
    assert not any(r.endswith("/05-lifecycle/1-gates.md") for r in order), (
        f"{md.name} still reads the whole gate book up front")
    assert not any(re.search(r"/03-pages/\d-\w+\.md$", r) for r in order), (
        f"{md.name} still reads a whole page pack up front")
    total = (_tok(SP / "SKILL.md") + _tok(SP / "05-lifecycle" / "routing.md")
             + sum(_tok(PLUGIN / r) for r in packs + gates))
    assert total <= BASIS_CEILING, f"{md.name}: {total} tokens on the audit's basis"


@pytest.mark.parametrize("md", _producers(), ids=lambda p: p.stem)
def test_the_full_reading_order_stays_under_the_ratchet(md):
    order = _reading_order(md)
    total = (_tok(SP / "SKILL.md") + _tok(SP / "05-lifecycle" / "routing.md")
             + sum(_tok(PLUGIN / r) for r in order))
    assert total <= FULL_CEILING, f"{md.name}: {total} tokens on the full reading order"


def test_every_surface_has_its_own_pack_and_rulebook_file():
    for page in ("heatmap", "overview", "insights", "platform", "context", "techstack"):
        packs = {p.stem for p in (SP / "03-pages" / page).glob("*.md")}
        books = {p.stem for p in (SP / "03-pages" / "rulebooks" / page).glob("*.md")}
        assert packs and books, page
        # C6 renders O8's section: its rulebook lives under context, its
        # pack block under overview
        assert books - {"C6"} <= packs | {"C6"}, (page, books - packs)


def test_a_page_pack_and_a_rulebook_index_name_every_surface_file():
    for page, fname in (("heatmap", "1-heatmap.md"), ("overview", "2-overview.md"),
                        ("insights", "3-insights.md"), ("platform", "4-platform.md"),
                        ("context", "5-context.md"), ("techstack", "6-techstack.md")):
        idx = (SP / "03-pages" / fname).read_text(encoding="utf-8")
        for f in (SP / "03-pages" / page).glob("*.md"):
            assert f"`{page}/{f.name}`" in idx, (fname, f.name)
        ridx = (SP / "03-pages" / "rulebooks" / f"{page}.md").read_text(encoding="utf-8")
        for f in (SP / "03-pages" / "rulebooks" / page).glob("*.md"):
            assert f"`{page}/{f.name}`" in ridx, (page, f.name)


def test_the_gate_book_indexes_every_gate_file():
    book = (SP / "05-lifecycle" / "1-gates.md").read_text(encoding="utf-8")
    files = sorted((SP / "05-lifecycle" / "gates").glob("*.md"))
    assert len(files) >= 30
    for f in files:
        assert f"`gates/{f.name}`" in book, f.name
