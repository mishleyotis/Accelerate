"""B-6 — customer-safe prospecting scorecard renderer.

Pure render layer (jinja2) so it unit-tests without a DB or a browser.
The prospecting router feeds live values in; the result is a self-contained
HTML document (inline CSS) suitable for download or for PDF conversion.

Customer-safe by construction: only the overall score, the four pillar
scores, and the top platform-fit values are rendered — never ERS, alert
counts, evidence, or internal notes.

PDF is produced by WeasyPrint when the optional `export` extra is
installed; the router degrades gracefully (501) when it is not, rather
than fabricating a file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Color authority mirrors frontend/src/lib/maturity.ts bands (ADR 0008).
# Kept in sync deliberately; the scorecard is a static export so it cannot
# import the TS module.
_BANDS = [
    (4.5, "#139F94", "Differentiating"),
    (3.5, "#27BBAF", "Competing"),
    (2.5, "#62D7B8", "Building"),
    (0.0, "#FFCB99", "Activating"),
]


def maturity_hex(score: float | None) -> str:
    if score is None:
        return "#E5E7EB"
    for threshold, hex_, _ in _BANDS:
        if score >= threshold:
            return hex_
    return "#FFCB99"


def maturity_label(score: float | None) -> str:
    if score is None:
        return "Not assessed"
    for threshold, _, label in _BANDS:
        if score >= threshold:
            return label
    return "Activating"


@dataclass
class PillarScore:
    pillar_id: str
    name: str
    score: float | None


@dataclass
class PlatformFit:
    name: str
    fit_score: float  # 0..100


@dataclass
class ScorecardData:
    entity_name: str
    subvertical: str | None
    display_id: str
    overall: float | None
    assessment_date: str | None
    pillars: list[PillarScore] = field(default_factory=list)
    top_platforms: list[PlatformFit] = field(default_factory=list)


_TEMPLATE_SRC = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{{ d.entity_name }} — DMA Scorecard</title>
<style>
  :root { --teal:#27BBAF; --ink:#1C4A4D; --muted:#6B7280; --sep:#E5E7EB; }
  * { box-sizing:border-box; }
  body { font-family:'DM Sans',-apple-system,Segoe UI,Roboto,sans-serif;
         color:#111827; margin:0; padding:40px; background:#fff; }
  .head { display:flex; justify-content:space-between; align-items:flex-start;
          border-bottom:2px solid var(--ink); padding-bottom:16px; }
  .eyebrow { font-size:11px; letter-spacing:.08em; text-transform:uppercase;
             color:var(--muted); }
  h1 { font-size:24px; margin:4px 0 2px; color:var(--ink); }
  .meta { font-size:12px; color:var(--muted); }
  .ring { text-align:center; }
  .ring .val { font-size:34px; font-weight:700; line-height:1; }
  .ring .lbl { font-size:11px; color:var(--muted); }
  .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px;
          margin:24px 0; }
  .pillar { border:1px solid var(--sep); border-radius:8px; padding:12px; }
  .pillar .pid { font-size:10px; color:var(--muted); }
  .pillar .pname { font-size:12px; font-weight:600; margin:2px 0 8px; }
  .bar { height:6px; border-radius:3px; background:var(--sep); overflow:hidden; }
  .bar > span { display:block; height:100%; }
  .pillar .pscore { font-size:18px; font-weight:700; margin-top:6px; }
  .sec { font-size:13px; font-weight:700; color:var(--ink);
         margin:24px 0 8px; }
  .plats { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
  .plat { border:1px solid var(--sep); border-radius:8px; padding:12px;
          text-align:center; }
  .plat .pn { font-size:12px; font-weight:600; }
  .plat .pf { font-size:22px; font-weight:700; color:var(--teal); }
  .foot { margin-top:32px; font-size:10px; color:var(--muted);
          border-top:1px solid var(--sep); padding-top:8px; }
</style></head><body>
  <div class="head">
    <div>
      <div class="eyebrow">DMA scorecard · share-safe</div>
      <h1>{{ d.entity_name }}</h1>
      <div class="meta">
        {{ d.subvertical or "—" }}{% if d.assessment_date %} ·
        Assessed {{ d.assessment_date }}{% endif %}
      </div>
    </div>
    <div class="ring">
      <div class="val" style="color:{{ hexf(d.overall) }}">
        {{ "%.1f"|format(d.overall) if d.overall is not none else "—" }}
      </div>
      <div class="lbl">{{ labelf(d.overall) }}</div>
    </div>
  </div>

  <div class="grid">
    {% for p in d.pillars %}
    <div class="pillar">
      <div class="pid">{{ p.pillar_id }}</div>
      <div class="pname">{{ p.name }}</div>
      <div class="bar"><span style="width:{{ pct(p.score) }}%;
           background:{{ hexf(p.score) }}"></span></div>
      <div class="pscore" style="color:{{ hexf(p.score) }}">
        {{ "%.1f"|format(p.score) if p.score is not none else "—" }}
      </div>
    </div>
    {% endfor %}
  </div>

  {% if d.top_platforms %}
  <div class="sec">Top platform opportunities</div>
  <div class="plats">
    {% for pl in d.top_platforms %}
    <div class="plat">
      <div class="pn">{{ pl.name }}</div>
      <div class="pf">{{ "%.0f"|format(pl.fit_score) }}</div>
      <div class="lbl" style="font-size:10px;color:var(--muted)">fit score</div>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <div class="foot">
    Generated by DMA Insights · share-safe presentation mode ·
    {{ d.display_id }}
  </div>
</body></html>
"""

# Compiled lazily on first render so a missing `jinja2` degrades to a clean
# per-request RuntimeError (→ 500) rather than crashing the whole app on
# import. jinja2 IS a core dependency (backend/pyproject.toml + the
# backend.Dockerfile pip list); the lazy guard is belt-and-suspenders for
# image-build drift.
_TEMPLATE: Any = None


def _get_template() -> Any:
    global _TEMPLATE
    if _TEMPLATE is None:
        try:
            import jinja2
        except ImportError as exc:  # pragma: no cover - import-drift guard
            raise RuntimeError(
                "HTML scorecard export requires jinja2 (a core dependency). "
                "The backend image is missing it — add jinja2 to "
                "infra/docker/backend.Dockerfile."
            ) from exc
        _TEMPLATE = jinja2.Template(_TEMPLATE_SRC)
    return _TEMPLATE


def _pct(score: float | None) -> float:
    if score is None:
        return 0.0
    return max(0.0, min(100.0, (score / 5.0) * 100.0))


def render_scorecard_html(d: ScorecardData) -> str:
    return _get_template().render(
        d=d, hexf=maturity_hex, labelf=maturity_label, pct=_pct,
    )


def render_scorecard_pdf(d: ScorecardData) -> bytes:
    """Render to PDF via WeasyPrint. Raises RuntimeError when the optional
    `export` extra (weasyprint) is not installed so the router can return a
    clean 501 instead of a fabricated file."""
    try:
        import weasyprint  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "PDF export requires the 'export' extra (weasyprint). "
            "Install with: pip install '.[export]'"
        ) from exc
    html = render_scorecard_html(d)
    return weasyprint.HTML(string=html).write_pdf()  # pragma: no cover
