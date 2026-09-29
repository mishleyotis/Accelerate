"""The assessment report's band swatches are the app's (QA audit F-L11-042
pair 38, 29-09-2026): the skill listed `#D32F2F / #FBC02D / #388E3C` beside
a deck aligned to `apps/web/lib/bands.js` in W1 — a third palette for the
same four words. Invariant 7: score→band→hex in exactly one module."""
import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
REPO = PLUGIN.parents[1]
BANDS_JS = REPO / "apps" / "web" / "lib" / "bands.js"
SKILL = PLUGIN / "skills" / "dma-assessment" / "SKILL.md"


def _app_fills():
    return dict(re.findall(r'(\w+): \{ fill: "#([0-9A-F]{6})"', BANDS_JS.read_text()))


def test_the_assessment_skill_names_exactly_the_apps_fills():
    fills = _app_fills()
    assert list(fills) == ["Activating", "Building", "Competing", "Differentiating"]
    text = SKILL.read_text(encoding="utf-8")
    block = text.split("Maturity BANDS", 1)[1].split("fifth band", 1)[0]
    for band, hexv in fills.items():
        assert f"{band}=`#{hexv}`" in block, (band, hexv)
    stray = set(re.findall(r"#([0-9A-Fa-f]{6})", block)) - set(fills.values())
    assert stray == set(), stray
    assert "bands.js" in block
