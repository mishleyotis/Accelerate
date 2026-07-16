"""Language sanitization audit against the UI/UX brief voice guide.

Per the 2026-06-07 operator mandate: "check on whether the language
used to communicate findings has been sanitized to fit the language
guidelines in the different design documents eg UIUX brief."

Source-of-truth: ``docs/reference/DMA Insights - UI_UX Design Brief.html``
voice rules:

  1. Confident, specific, active. No hedging.
     - Avoid: "may be some", "there are a number of", "potentially",
       "appears to", "it seems".
  2. Opportunity framing. No deficit language in customer-facing copy.
     - Avoid: "pain point", "weakness", "lags", "failure", "deficient",
       "lacking".
     - Use:   "area of focus", "room to grow", "positioned to accelerate",
              "opportunity".
  3. Word economy. Numbers beat adjectives.
     - Avoid: "a number of", "several", "many", "various", "significant".
  4. No jargon in user-facing copy.
     - Avoid: "JWT", "403 Forbidden", "stack trace", "API error 500",
       "null pointer", "HTTP 500", "ECONNREFUSED", "OOM".
  5. No apologies in error / fallback states.
     - Avoid: "Sorry", "Oops", "Apologies", "Unfortunately".
  6. Active voice. (Statistical proxy: passive markers like
     "was posted by", "is being processed by".)
  7. Specifics beat generics. (Cannot mechanically check; the audit
     flags generic placeholders like "the company", "the firm",
     "the entity" when an entity_name was available.)

The audit scans the live-DB rendered narratives:

  - ``runs.scqa`` JSONB (situation / complication / question / answer)
  - ``runs.top_findings`` JSONB
  - ``runs.why_now_signals`` JSONB
  - ``subcap_scores.rationale`` (one row per subcap)
  - ``document_sections.body`` (parsed DOCX section content)
  - ``focus_areas.verbatim_quote`` + .name + .summary
  - ``recommendations.headline`` + .scqa + .root_cause

Output: TSV with one row per (entity, surface, rule_violated, snippet).
Plus an aggregate per-entity + per-rule count summary.

Two additional modes (QA-gates workstream 2026-07-02, plan Parts 2/3.5/R.4):

  --nlp-coverage   STATIC gate, no DB. Scans `app/scripts/` +
                   `app/services/parsers/` for modules that EMIT user-facing
                   prose (string/f-string assignments into *_md / text /
                   title / body / label fields, or long f-strings built for
                   persistence) WITHOUT importing `app.services.nlp`. The
                   Part 3.5 matrix is binding: no derive/parse script ships
                   prose without the toolkit. Violations in modules NOT on
                   the explicit `NLP_COVERAGE_GRANDFATHER` burn-down list
                   exit nonzero. Grandfathered modules print as warnings;
                   grandfathered modules that came clean print a reminder to
                   shrink the list.

  --pattern-gaps   DB report. Aggregates the structured `PATTERN_GAP`
                   warnings (`nlp.patterns.record_pattern_gap`) across
                   `runs.parser_warnings` — the registry's zero-day list of
                   artifact shapes that fell through to generic mining.
                   Report-only (exit 0): each gap is a learning item for the
                   pattern registry, not a build defect.

Usage:
  export DATABASE_URL=postgresql+asyncpg://...
  python -m app.scripts.qa_language_audit
  python -m app.scripts.qa_language_audit --output docs/qa/qa_language_audit.tsv
  python -m app.scripts.qa_language_audit --limit 20  # smoke test
  python -m app.scripts.qa_language_audit --nlp-coverage   # static, no DB
  python -m app.scripts.qa_language_audit --pattern-gaps   # DB report

Exit code: 0 if no violations, 1 otherwise.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from app.database import get_sessionmaker

# Each rule has a list of compiled regex patterns matched case-insensitively
# against the narrative text. A match logs the surrounding context + the
# rule id + a suggested replacement when one exists.
#
# Format: rule_id -> {description, patterns: [(regex, suggestion)]}
RULES = {
    "R1_no_hedging": {
        "description": "Confident / active — no hedging.",
        "patterns": [
            (r"\bmay\s+be\s+some\b", '"is" + a specific count'),
            (r"\bthere\s+are\s+a\s+number\s+of\b", "specific number"),
            (r"\bpotentially\b", "stronger claim or omit"),
            (r"\bit\s+(?:seems|appears)\b", '"is" + evidence'),
            (r"\bmight\s+(?:be|have)\b", '"is" / "has" with evidence'),
        ],
    },
    "R2_opportunity_framing": {
        "description": "Opportunity framing — no deficit language.",
        "patterns": [
            (r"\bpain\s+points?\b", '"areas of focus"'),
            (r"\bweakness(?:es)?\b", '"opportunity" or "area of focus"'),
            (r"\blags\b", '"trails" + concrete delta'),
            (r"\bfailure(?:s)?\b", '"gap" / "opportunity"'),
            (r"\bdeficient\b", '"opportunity"'),
            (r"\blacking\b", '"missing" + specific'),
            (r"\bpoor(?:ly)?\b", '"limited" + delta'),
        ],
    },
    "R3_word_economy": {
        "description": "Word economy — numbers beat adjectives.",
        "patterns": [
            (r"\ba\s+number\s+of\b", "exact count"),
            (r"\bseveral\b", "exact count"),
            (r"\bmany\b", "exact count"),
            (r"\bvarious\b", "exact list"),
            (r"\bsignificant(?:ly)?\b", "delta in numbers"),
        ],
    },
    "R4_no_jargon": {
        "description": "No jargon / stack-trace leakage in user-facing copy.",
        "patterns": [
            (r"\bJWT(?:\s+(?:expired|invalidated|verification))?\b", '"session" terms'),
            (r"\bHTTP\s+\d{3}\b", "plain-English state"),
            (r"\b\d{3}\s+(?:Forbidden|Unauthorized|Internal Server Error)\b",
             "plain-English state"),
            (r"\bstack\s+trace\b", "remove"),
            (r"\bnull\s+pointer\b", "remove"),
            (r"\bECONNREFUSED\b", '"connection failed"'),
            (r"\bOOM\b", '"out of memory"'),
            (r"\bAPI\s+error\b", "plain-English"),
        ],
    },
    "R5_no_apologies": {
        "description": "No apologies — state situation + recovery.",
        "patterns": [
            (r"\bsorry\b", "remove"),
            (r"\boops\b", "remove"),
            (r"\bapologies\b", "remove"),
            (r"\bunfortunately\b", '"the current state is" + recovery'),
        ],
    },
    "R6_active_voice": {
        "description": "Active voice — flag common passive markers.",
        "patterns": [
            (r"\bwas\s+(?:posted|created|updated|computed|generated)\s+by\b",
             '"X did Y"'),
            (r"\bis\s+being\s+(?:processed|analyzed|generated)\s+by\b",
             "active phrasing"),
            (r"\bhas\s+been\s+(?:flagged|noted|identified)\s+by\b",
             "active phrasing"),
        ],
    },
}


@dataclass
class Violation:
    entity_display_id: str
    entity_name: str
    surface: str          # 'scqa.situation', 'subcap_rationale', etc.
    surface_key: str      # row_id / subcap_id for traceability
    rule_id: str
    snippet: str
    matched_phrase: str
    suggestion: str

    def line(self) -> str:
        # Sanitize control chars (newlines, tabs) for TSV.
        clean_snippet = re.sub(r"\s+", " ", self.snippet)[:240]
        return "\t".join([
            self.entity_display_id, self.entity_name, self.surface,
            self.surface_key, self.rule_id, self.matched_phrase,
            self.suggestion, clean_snippet,
        ])


def _scan_text(
    text_in: str,
    *,
    entity_display_id: str,
    entity_name: str,
    surface: str,
    surface_key: str,
) -> list[Violation]:
    if not text_in or not isinstance(text_in, str):
        return []
    out: list[Violation] = []
    for rule_id, rule in RULES.items():
        for pat, sug in rule["patterns"]:
            for m in re.finditer(pat, text_in, re.IGNORECASE):
                start = max(0, m.start() - 60)
                end = min(len(text_in), m.end() + 60)
                snippet = text_in[start:end]
                out.append(Violation(
                    entity_display_id=entity_display_id,
                    entity_name=entity_name,
                    surface=surface,
                    surface_key=surface_key,
                    rule_id=rule_id,
                    snippet=snippet,
                    matched_phrase=m.group(0),
                    suggestion=sug,
                ))
    return out


def _flatten_json_text(blob) -> list[str]:
    """Walk a JSON value, return every string leaf."""
    if blob is None:
        return []
    if isinstance(blob, str):
        return [blob]
    if isinstance(blob, list):
        out: list[str] = []
        for v in blob:
            out.extend(_flatten_json_text(v))
        return out
    if isinstance(blob, dict):
        out: list[str] = []
        for v in blob.values():
            out.extend(_flatten_json_text(v))
        return out
    return []


async def audit_entity(
    session, display_id: str, name: str
) -> list[Violation]:
    out: list[Violation] = []
    # ── runs.scqa, runs.top_findings, runs.why_now_signals ─────────────
    rows = (await session.execute(
        text(
            "SELECT r.id::text, r.scqa, r.top_findings, r.why_now_signals "
            "FROM runs r JOIN entities e ON e.id = r.entity_id "
            "WHERE e.display_id = :did AND r.status = 'ACTIVE'"
        ),
        {"did": display_id},
    )).all()
    for r in rows:
        rid = r[0]
        for field, value in (
            ("scqa", r[1]),
            ("top_findings", r[2]),
            ("why_now_signals", r[3]),
        ):
            for s in _flatten_json_text(value):
                out.extend(_scan_text(
                    s,
                    entity_display_id=display_id, entity_name=name,
                    surface=f"runs.{field}", surface_key=rid,
                ))
    # ── subcap_scores.rationale ────────────────────────────────────────
    rows = (await session.execute(
        text(
            "SELECT ss.subcap_id, ss.rationale "
            "FROM subcap_scores ss JOIN runs r ON r.id = ss.run_id "
            "JOIN entities e ON e.id = r.entity_id "
            "WHERE e.display_id = :did AND r.status='ACTIVE' "
            "  AND ss.rationale IS NOT NULL AND length(ss.rationale) > 0"
        ),
        {"did": display_id},
    )).all()
    for r in rows:
        out.extend(_scan_text(
            r[1],
            entity_display_id=display_id, entity_name=name,
            surface="subcap_scores.rationale", surface_key=r[0] or "",
        ))
    # ── document_sections.body ─────────────────────────────────────────
    rows = (await session.execute(
        text(
            "SELECT ds.section_kind, ds.body "
            "FROM document_sections ds JOIN runs r ON r.id = ds.run_id "
            "JOIN entities e ON e.id = r.entity_id "
            "WHERE e.display_id = :did AND r.status='ACTIVE' "
            "  AND ds.body IS NOT NULL AND length(ds.body) > 0"
        ),
        {"did": display_id},
    )).all()
    for r in rows:
        out.extend(_scan_text(
            r[1],
            entity_display_id=display_id, entity_name=name,
            surface="document_sections.body", surface_key=r[0] or "",
        ))
    # ── focus_areas (title + verbatim_quote) ───────────────────────────
    rows = (await session.execute(
        text(
            "SELECT fa.title, fa.verbatim_quote "
            "FROM focus_areas fa JOIN runs r ON r.id = fa.run_id "
            "JOIN entities e ON e.id = r.entity_id "
            "WHERE e.display_id = :did AND r.status='ACTIVE'"
        ),
        {"did": display_id},
    )).all()
    for r in rows:
        for field, value in (
            ("title", r[0]),
            ("verbatim_quote", r[1]),
        ):
            out.extend(_scan_text(
                value or "",
                entity_display_id=display_id, entity_name=name,
                surface=f"focus_areas.{field}",
                surface_key=(r[0] or "")[:32],
            ))
    # ── recommendations.title + .description ───────────────────────────
    rows = (await session.execute(
        text(
            "SELECT rec.rec_id, rec.title, rec.description "
            "FROM recommendations rec JOIN runs r ON r.id = rec.run_id "
            "JOIN entities e ON e.id = r.entity_id "
            "WHERE e.display_id = :did AND r.status='ACTIVE'"
        ),
        {"did": display_id},
    )).all()
    for r in rows:
        out.extend(_scan_text(
            r[1] or "",
            entity_display_id=display_id, entity_name=name,
            surface="recommendations.title", surface_key=r[0] or "",
        ))
        out.extend(_scan_text(
            r[2] or "",
            entity_display_id=display_id, entity_name=name,
            surface="recommendations.description", surface_key=r[0] or "",
        ))
    return out


async def main_async(args: argparse.Namespace) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        sql = (
            "SELECT display_id, name FROM entities WHERE status='ACTIVE' "
            "AND display_id IS NOT NULL ORDER BY display_id"
        )
        if args.limit:
            sql += f" LIMIT {int(args.limit)}"
        ents = (await session.execute(text(sql))).all()

    print(f"# {len(ents)} active entities to audit", flush=True)
    rows: list[str] = [
        "display_id\tname\tsurface\tsurface_key\trule_id\t"
        "matched_phrase\tsuggestion\tsnippet"
    ]
    total_violations = 0
    rule_counts: dict[str, int] = {}
    entity_counts: dict[str, int] = {}
    surface_counts: dict[str, int] = {}

    for i, (did, name) in enumerate(ents, 1):
        # Fresh session per entity: a failed query (e.g. a column
        # missing on a partially-migrated schema) on entity N can't
        # corrupt the audit for entity N+1.
        try:
            async with sm() as session:
                violations = await audit_entity(session, did, name)
        except Exception as e:
            print(
                f"# AUDIT ERROR for {did}: {type(e).__name__}: {e}",
                flush=True,
            )
            continue
        for v in violations:
            rows.append(v.line())
            rule_counts[v.rule_id] = rule_counts.get(v.rule_id, 0) + 1
            entity_counts[did] = entity_counts.get(did, 0) + 1
            surface_counts[v.surface] = surface_counts.get(v.surface, 0) + 1
        total_violations += len(violations)
        if i % 20 == 0:
            print(
                f"  ... {i}/{len(ents)} audited "
                f"({total_violations} violations so far)",
                flush=True,
            )

    output = "\n".join(rows) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output, encoding="utf-8")
        print(f"# wrote audit to {out}", flush=True)
    else:
        print(output)

    print(
        f"\n# LANGUAGE SANITIZATION SUMMARY: {total_violations} violations "
        f"across {len(entity_counts)}/{len(ents)} entities",
        flush=True,
    )
    if rule_counts:
        print("\n# Violations by rule:", flush=True)
        for rid, n in sorted(rule_counts.items(), key=lambda x: -x[1]):
            desc = RULES[rid]["description"]
            print(f"  {n:5} {rid} -- {desc}", flush=True)
    if surface_counts:
        print("\n# Violations by surface:", flush=True)
        for s, n in sorted(surface_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {n:5} {s}", flush=True)
    if entity_counts:
        print("\n# Top 10 worst-offender entities:", flush=True)
        for did, n in sorted(entity_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {n:5} {did}", flush=True)

    return 0 if total_violations == 0 else 1


# ═════════════════════════════════════════════════════════════════════════════
# --nlp-coverage — the Part 3.5 static gate (QA-gates workstream 2026-07-02)
#
# "No derive/parse script ships prose or classifications without going through
# services/nlp/" is BINDING (plan R.4). This scanner is the enforcement: a
# module under app/scripts/ or app/services/parsers/ that composes user-facing
# prose without importing the toolkit fails the build unless it is on the
# explicit grandfather burn-down list below.
# ═════════════════════════════════════════════════════════════════════════════

# Explicit burn-down list: modules that PRE-DATE the toolkit and still compose
# prose with ad-hoc string building. Every entry here is debt owed to the
# Part 3.5 matrix — REMOVE entries as their owners route prose through
# app.services.nlp; NEVER add a new module. Target: empty by pack-regen time
# (plan R.4 "grandfathered files listed explicitly and burned down to zero").
NLP_COVERAGE_GRANDFATHER: frozenset[str] = frozenset({
    # scripts still composing prose ad hoc (measured 2026-07-02; burned down
    # same day: deepen_narrative + section_analysis came clean via D1/D2;
    # 2026-07-04: derive_financials + derive_insights + derive_sentiment came
    # clean; scan widened to ALL of app/services + signal/note/summary/
    # narrative/rationale fields — the pre-existing services below are
    # grandfathered AS-MEASURED so the gate catches FUTURE modules. Several
    # are false-positive-shaped (LLM prompt templates, SQL f-strings, regex
    # literals, operator log summaries) — annotate on burn-down, don't churn.
    "app/scripts/apply_startup_data_fixes.py",
    "app/scripts/derive_recommendations.py",
    "app/scripts/derive_subcap_narratives.py",
    "app/scripts/export_startup_data.py",     # partial-assessment note string
    "app/scripts/historical_backfill.py",
    "app/scripts/derive_issues.py",           # rationale one-liner
    "app/scripts/derive_peers.py",            # note one-liner
    # services (widened scan 2026-07-04)
    "app/services/alerts_producer.py",
    "app/services/catalogue_alias_bridge.py",
    "app/services/completeness_contract.py",
    "app/services/customer_intelligence.py",  # LLM prompt template
    "app/services/drive_comment_materiality.py",
    "app/services/drive_feedback.py",
    "app/services/enrichment.py",             # LLM prompt template
    "app/services/entity_healing.py",
    "app/services/evidence_dedup.py",         # audit reason strings
    "app/services/insight_explainer.py",      # pillar label map
    "app/services/intelligence_builder.py",   # LLM prompt templates
    "app/services/job_executions.py",         # operator log summaries
    "app/services/job_executions_db.py",      # SQL f-string
    "app/services/pattern_recognition.py",
    "app/services/platform_story.py",
    "app/services/prompt_quality.py",
    "app/services/rag_answer.py",             # LLM prompt template
    "app/services/readiness_index.py",        # note one-liner
    "app/services/run_resolver.py",           # SQL f-string
    "app/services/synthesis_cache_db.py",     # SQL f-string
    # parsers still composing prose ad hoc
    "app/services/parsers/dma_package.py",
    "app/services/parsers/package_persist.py",
    "app/services/parsers/r_rules.py",        # rendered parser-warning strings
    "app/services/parsers/report_recommendations.py",  # title w/o nlp.titlecraft
    "app/services/parsers/report_synthesis.py",
    "app/services/parsers/section_miner.py",  # section body w/o nlp.segment
    "app/services/parsers/subcap_narrative_extractor.py",
})

# QA reporters print operator-facing audit tables; they never persist
# user-facing prose. Everything else under the scanned roots is in scope.
_SCAN_EXEMPT_PREFIXES = ("qa_",)
# Operator-report / CI tooling: their composed strings are console reports or
# ops markdown artifacts, never AE-rendered surfaces. Explicit so a NEW script
# must justify itself here (or import the toolkit) rather than slip through.
_REPORT_ONLY_EXEMPT: frozenset[str] = frozenset({
    "app/scripts/diagnose_extraction.py",
    "app/scripts/inspect_dma_samples.py",
    "app/scripts/ledger_walker.py",
    "app/scripts/parse_audit_local.py",
    "app/scripts/parse_coverage.py",
    "app/scripts/parser_observations_promoter.py",
    "app/scripts/seed_ci.py",
})
_SCAN_ROOTS = ("app/scripts", "app/services")

# fields that carry user-facing prose (plan heuristic: *_md / text / title /
# body / label — matched on the tail of the assigned name/key)
_PROSE_FIELD_RE = re.compile(
    r"(?:_md|(?:^|_)text|(?:^|_)title|(?:^|_)body|(?:^|_)label|(?:^|_)signal"
    r"|(?:^|_)note|(?:^|_)summary|(?:^|_)narrative|(?:^|_)rationale"
    r"|(?:^|_)observation)$")
_FSTRING_PROSE_MIN = 80  # approx rendered length that counts as composed prose
_PRINT_LIKE = frozenset({"print", "debug", "info", "warning", "error",
                         "exception", "critical", "log", "write"})


@dataclass
class ProseSite:
    line: int
    kind: str      # "field_assign" | "long_fstring"
    detail: str    # field name or preview


def _imports_nlp_toolkit(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.startswith("app.services.nlp") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith("app.services.nlp"):
                return True
            if mod == "app.services" and any(a.name == "nlp" for a in node.names):
                return True
    return False


def _approx_fstring_len(node: ast.JoinedStr) -> int:
    n = 0
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            n += len(part.value)
        else:
            n += 12  # a formatted value ≈ one prose token
    return n


def _has_prose_literal(node: ast.AST) -> bool:
    """True when the value subtree composes prose: any f-string, or a string
    literal with a space and ≥12 chars (classification constants like
    'engineering_signal' don't count)."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.JoinedStr):
            return True
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                and len(sub.value) >= 12 and " " in sub.value:
            return True
    return False


def _target_field_name(target: ast.AST) -> str | None:
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) \
            and isinstance(target.slice.value, str):
        return target.slice.value
    return None


class _ProseScanner(ast.NodeVisitor):
    """Collects prose-emission sites, suppressing operator-output contexts
    (print/log calls, raised exceptions) — those are not user-facing prose."""

    def __init__(self) -> None:
        self.sites: list[ProseSite] = []
        self._suppress = 0

    # -- suppression contexts ------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else (
            fn.attr if isinstance(fn, ast.Attribute) else "")
        if name in _PRINT_LIKE:
            self._suppress += 1
            self.generic_visit(node)
            self._suppress -= 1
            return
        for kw in node.keywords:
            if kw.arg and _PROSE_FIELD_RE.search(kw.arg) and _has_prose_literal(kw.value) \
                    and not self._suppress:
                self.sites.append(ProseSite(node.lineno, "field_assign", kw.arg))
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        self._suppress += 1
        self.generic_visit(node)
        self._suppress -= 1

    # -- prose sites ----------------------------------------------------------
    def _check_assign(self, targets: list[ast.AST], value: ast.AST | None,
                      lineno: int) -> None:
        if self._suppress or value is None:
            return
        for t in targets:
            name = _target_field_name(t)
            if name and _PROSE_FIELD_RE.search(name) and _has_prose_literal(value):
                self.sites.append(ProseSite(lineno, "field_assign", name))
                return

    def visit_Assign(self, node: ast.Assign) -> None:
        self._check_assign(node.targets, node.value, node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_assign([node.target], node.value, node.lineno)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        if not self._suppress:
            for k, v in zip(node.keys, node.values, strict=False):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) \
                        and _PROSE_FIELD_RE.search(k.value) and _has_prose_literal(v):
                    self.sites.append(ProseSite(node.lineno, "field_assign", k.value))
                    break
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        if not self._suppress and _approx_fstring_len(node) > _FSTRING_PROSE_MIN:
            preview = "".join(p.value for p in node.values
                              if isinstance(p, ast.Constant) and isinstance(p.value, str))
            self.sites.append(ProseSite(node.lineno, "long_fstring", preview[:60]))
        self.generic_visit(node)


def scan_module_source(src: str, rel_path: str = "<mem>") -> dict:
    """Pure scanner: {imports_nlp, sites[]} for one module's source."""
    tree = ast.parse(src, filename=rel_path)
    scanner = _ProseScanner()
    scanner.visit(tree)
    return {"imports_nlp": _imports_nlp_toolkit(tree), "sites": scanner.sites}


def run_nlp_coverage(backend_root: Path | None = None, show: int = 3) -> int:
    root = backend_root or Path(__file__).resolve().parents[2]
    hard_violations: list[str] = []
    grandfathered_dirty: list[str] = []
    grandfathered_clean: list[str] = []
    scanned = 0
    for scan_root in _SCAN_ROOTS:
        for path in sorted((root / scan_root).glob("*.py")):
            rel = f"{scan_root}/{path.name}"
            if path.name == "__init__.py" or path.name.startswith(_SCAN_EXEMPT_PREFIXES) \
                    or rel in _REPORT_ONLY_EXEMPT:
                continue
            scanned += 1
            try:
                result = scan_module_source(path.read_text(), rel)
            except SyntaxError as e:  # pragma: no cover - unparseable module
                hard_violations.append(f"{rel}: unparseable ({e})")
                continue
            emits = bool(result["sites"])
            grandfathered = rel in NLP_COVERAGE_GRANDFATHER
            if grandfathered:
                (grandfathered_dirty if emits and not result["imports_nlp"]
                 else grandfathered_clean).append(rel)
                continue
            if emits and not result["imports_nlp"]:
                sites = ", ".join(f"L{s.line}:{s.kind}:{s.detail}"
                                  for s in result["sites"][:show])
                hard_violations.append(f"{rel}: {sites}")
    print(f"\n# qa_language_audit --nlp-coverage — {scanned} modules scanned "
          f"({len(NLP_COVERAGE_GRANDFATHER)} grandfathered)")
    if hard_violations:
        print(f"\n✗ {len(hard_violations)} NON-grandfathered module(s) emit prose "
              "without app.services.nlp (Part 3.5 matrix violation):")
        for v in hard_violations:
            print(f"   {v}")
    if grandfathered_dirty:
        print(f"\n⚠ {len(grandfathered_dirty)} grandfathered module(s) still dirty "
              "(burn-down debt):")
        for v in sorted(grandfathered_dirty):
            print(f"   {v}")
    stale = sorted(set(grandfathered_clean))
    if stale:
        print(f"\n→ {len(stale)} grandfathered module(s) now clean — remove from "
              "NLP_COVERAGE_GRANDFATHER:")
        for v in stale:
            print(f"   {v}")
    missing = sorted(m for m in NLP_COVERAGE_GRANDFATHER
                     if not (root / m).exists())
    if missing:
        print(f"\n→ {len(missing)} grandfathered path(s) no longer exist — remove:")
        for v in missing:
            print(f"   {v}")
    print(f"\n# RESULT: {'FAIL' if hard_violations else 'PASS'} "
          f"— {len(hard_violations)} hard violation(s)")
    return 1 if hard_violations else 0


# ═════════════════════════════════════════════════════════════════════════════
# --pattern-gaps — the registry's zero-day report (plan Part 2 / 12.3)
# ═════════════════════════════════════════════════════════════════════════════

def _iter_pattern_gaps(parser_warnings: object):
    """Yield (path, reason) from a runs.parser_warnings JSONB value.

    Three entry shapes across the corpus:
      * `nlp.patterns.record_pattern_gap` dicts — code == "PATTERN_GAP"
        with first-class path/reason keys;
      * the ingestion re-architecture's structured envelopes —
        {code, severity, detail} where detail is "path — reason";
      * legacy strings ("INFO/pattern_gap: path — reason")."""
    if not isinstance(parser_warnings, list):
        return
    for entry in parser_warnings:
        if isinstance(entry, dict) and str(entry.get("code") or "").upper() == "PATTERN_GAP":
            if entry.get("path") or entry.get("reason"):
                yield str(entry.get("path") or "?"), str(entry.get("reason") or "?")
            else:  # envelope form: {code, severity, detail}
                path, _, reason = str(entry.get("detail") or "").partition("—")
                yield path.strip() or "?", reason.strip() or "?"
        elif isinstance(entry, str) and "pattern_gap" in entry.lower():
            body = entry.split(":", 1)[1].strip() if ":" in entry else entry
            path, _, reason = body.partition("—")
            yield path.strip() or "?", reason.strip() or "?"


async def pattern_gaps_report() -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        rows = (await session.execute(text(
            "SELECT e.display_id, r.request_id, r.parser_warnings "
            "FROM runs r JOIN entities e ON e.id = r.entity_id "
            "WHERE r.parser_warnings IS NOT NULL"
        ))).all()
    by_shape: dict[tuple[str, str], int] = {}
    by_entity: dict[str, int] = {}
    total = 0
    for did, _rid, warnings in rows:
        for path, reason in _iter_pattern_gaps(warnings):
            shape = (Path(path).name, reason)
            by_shape[shape] = by_shape.get(shape, 0) + 1
            by_entity[did] = by_entity.get(did, 0) + 1
            total += 1
    print(f"\n# qa_language_audit --pattern-gaps — {total} PATTERN_GAP warning(s) "
          f"across {len(by_entity)} entities ({len(rows)} runs scanned)")
    if by_shape:
        print("\n# Gaps by artifact shape (registry learning queue):")
        for (name, reason), n in sorted(by_shape.items(), key=lambda x: -x[1])[:25]:
            print(f"  {n:5}  {name} — {reason}")
        print("\n# Top entities:")
        for did, n in sorted(by_entity.items(), key=lambda x: -x[1])[:10]:
            print(f"  {n:5}  {did}")
    else:
        print("  (none — every artifact matched a registered pattern)")
    return 0  # report-only: gaps are learning items, not build defects


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--output", help="Write TSV to this path (default stdout)")
    p.add_argument("--limit", type=int, help="Audit only first N entities")
    p.add_argument("--nlp-coverage", action="store_true",
                   help="static Part-3.5 gate: prose emission without app.services.nlp")
    p.add_argument("--pattern-gaps", action="store_true",
                   help="report PATTERN_GAP warnings across runs.parser_warnings")
    args = p.parse_args()
    if args.nlp_coverage:
        return run_nlp_coverage()
    if args.pattern_gaps:
        return asyncio.run(pattern_gaps_report())
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
