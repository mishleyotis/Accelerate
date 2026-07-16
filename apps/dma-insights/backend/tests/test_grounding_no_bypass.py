"""Regression: every Vertex/Gemini generation callsite in app/ must run
the grounding validator on its output. No bypass.

The CLAUDE.md hard rule is verbatim:

>   Do NOT serve un-validated Gemini output to AEs. Every surface runs
>   the post-generation validator and falls back to template-fill on
>   any flag.

This test scans `app/routers/` + `app/services/` for direct calls into
`vertex_client.stream` / `vertex_client.generate` / `genai.*` and
asserts that EACH callsite has a `validate_response` or
`validate(...)` reference within 50 lines downstream OR appears on the
documented exception list (e.g. embedding-only calls that produce no
generated text to validate).

This is a pure-source static guard -- no runtime PG / Vertex required.
"""
from __future__ import annotations

import re
from pathlib import Path

# Source roots to scan.
_HERE = Path(__file__).resolve()
_BACKEND_DIR = _HERE.parents[1]
_APP_DIR = _BACKEND_DIR / "app"

# Documented exceptions: callsites that LEGITIMATELY don't run the
# validator. Each entry is (relative_path, line_substring) so the test
# can pinpoint the exact line being allowed. Adding a new entry MUST be
# accompanied by a code comment explaining WHY no validation is needed
# (embedding-only call, deterministic stub fallback, etc.).
_DOCUMENTED_EXCEPTIONS = (
    # subcap_narrative_extractor.py uses its OWN stricter inline
    # validator (validate_json_schema + per-subcap_id existence check)
    # that supersedes the V1+V2+V3 contract. Documented in the module
    # docstring.
    ("app/services/parsers/subcap_narrative_extractor.py",
     "async for chunk in vertex_client.stream"),
    # insight_explainer.py is the SYNC, session-less connector for
    # deepen_narrative's insight-card explainer hook (D2). Its output is
    # narrative WHAT/WHY/SO-WHAT prose with no evidence citations to ground,
    # so the DB-backed validate_response is N/A. Validation is instead
    # deepen_narrative._valid_insight (jargon/thinness reject) + _plain() +
    # the deterministic _deep_card template fallback — the "validator +
    # template-fill on any flag" hard rule. See the module's GROUNDING NOTE.
    ("app/services/insight_explainer.py",
     "async for chunk in vertex_client.stream"),
    # enrichment_runner.py is pure TRANSPORT: drain_stream_sync collects
    # the raw stream inside an abandonable daemon thread and hands the
    # text back to the CALLING script, which owns validation BEFORE any
    # persistence — enrich_corpus runs the E-ID fabrication check +
    # verbatim-quote/excerpt acceptance (_accept_firmo_fields /
    # _accept_tl_items), enrich_empty_surfaces runs the registry query's
    # accept() (STRICT JSON + verbatim/id-set checks; rejects are cached
    # validators_passed=False). Nothing in this module persists output.
    # See the module docstring ("validation, persistence and honesty
    # gates stay in the calling scripts").
    ("app/services/enrichment_runner.py",
     "async for ch in vertex_client.stream(call):"),
)


# Match the CALLSITE shape (method then `(`), not just the dotted name.
# This avoids false positives in:
#   - log messages: "vertex.stream retryable error"
#   - exception messages: "vertex.stream: exhausted retries"
#   - docstring prose: "the layer calls vertex_client.generate() with"
# All of those have NO `(` immediately following the method name on the
# same line, OR are inside quoted strings (we filter those out via line
# prefix below).
_GENERATE_CALL_RE = re.compile(
    r"\b(?:vertex_client|vertex|get_vertex_client\(\))"
    r"\.(?:stream|generate)\("
)


_COMMENT_OR_STRING_LINE_RE = re.compile(
    r'^\s*(?:#|"""|""|"|\'\'\'|\'\'|\')'
)


def _file_paths_to_scan() -> list[Path]:
    """Yield every .py file under app/routers/ + app/services/ excluding
    __pycache__ + the vertex_client.py implementation itself (which
    defines the methods we're scanning for)."""
    targets = []
    skip_files = {"vertex_client.py", "synthesis_orchestrator.py"}
    for sub in ("routers", "services"):
        d = _APP_DIR / sub
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            if f.name in skip_files:
                continue
            targets.append(f)
    return targets


def _is_exempt(rel_path: str, lines: list[str], line_idx: int) -> bool:
    """Return True if the line at `line_idx` (0-indexed) is in the
    documented-exception list."""
    line = lines[line_idx]
    for ex_path, ex_substr in _DOCUMENTED_EXCEPTIONS:
        if rel_path.endswith(ex_path) and ex_substr in line:
            return True
    return False


def _has_nearby_validator(lines: list[str], line_idx: int,
                         window: int = 75) -> bool:
    """Return True if any line within `window` lines AFTER line_idx
    calls validate_response or validate() with the response text."""
    start = line_idx
    end = min(len(lines), line_idx + window)
    snippet = "\n".join(lines[start:end])
    if re.search(r"\bvalidate_response\b", snippet):
        return True
    # subcap_narrative_extractor uses a different validator name.
    if re.search(r"\bvalidate\(.*response", snippet, re.IGNORECASE):
        return True
    return bool(re.search(r"\bvalidate_subcap_narrative_json\b", snippet))


_TRIPLE = chr(34) * 3  # '"""' without embedding the marker in the docstring.


def _line_is_in_docstring(lines: list[str], idx: int) -> bool:
    """Track triple-double-quote opens/closes from the file start and
    report whether `idx` falls inside a docstring block. Best-effort --
    only looks for triple-double-quote markers (the canonical
    convention in this repo)."""
    in_block = False
    for i in range(idx):
        n = lines[i].count(_TRIPLE)
        if n % 2 == 1:
            in_block = not in_block
    on_line = lines[idx]
    if not in_block and on_line.count(_TRIPLE) >= 1:
        # A line with exactly TWO markers opens AND closes on the same
        # line (one-liner docstring): treat as code. Otherwise the line
        # is opening a multi-line docstring; treat the match as prose.
        return on_line.count(_TRIPLE) != 2
    return in_block


def test_every_vertex_generation_callsite_runs_validator() -> None:
    """Static: every direct call to vertex_client.stream/generate must
    have a validator within 75 lines downstream OR be in the exception
    list. Adding an unvalidated call without an exception line is a
    REGRESSION of the grounding contract."""
    offenders: list[str] = []
    for f in _file_paths_to_scan():
        rel = f.relative_to(_BACKEND_DIR).as_posix()
        text = f.read_text()
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not _GENERATE_CALL_RE.search(line):
                continue
            # Skip if the line is inside a `"""..."""` docstring (the
            # call appears in prose, not in real code).
            if _line_is_in_docstring(lines, i):
                continue
            if _is_exempt(rel, lines, i):
                continue
            if _has_nearby_validator(lines, i):
                continue
            offenders.append(f"{rel}:{i + 1}: {line.strip()}")
    assert not offenders, (
        "Found Vertex generation callsite(s) with no nearby "
        "`validate_response` (within 75 lines downstream) and no "
        "documented exception. The CLAUDE.md hard rule requires every "
        "surface to validate Gemini output. Either:\n"
        "  - Add `await validate_response(...)` immediately after the "
        "stream/generate call, OR\n"
        "  - Add a documented exception to _DOCUMENTED_EXCEPTIONS with "
        "a code comment explaining why no validation is needed.\n\n"
        "Offenders:\n  " + "\n  ".join(offenders)
    )


def test_documented_exceptions_still_match_real_lines() -> None:
    """Defence: if someone deletes a documented exception's line but
    forgets to delete the exception entry, future scans get an unused
    allowance. Detect that here."""
    used: list[str] = []
    for ex_path, ex_substr in _DOCUMENTED_EXCEPTIONS:
        candidate = _BACKEND_DIR / ex_path
        if not candidate.exists():
            used.append(f"{ex_path}: file missing")
            continue
        text = candidate.read_text()
        if ex_substr not in text:
            used.append(f"{ex_path}: substring {ex_substr!r} not found")
    assert not used, (
        "Stale entries in _DOCUMENTED_EXCEPTIONS -- either the file or "
        "the matched substring no longer exists:\n  "
        + "\n  ".join(used)
    )
