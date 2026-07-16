"""Regression: every `exit N` in an infra script must be documented in
infra/EXIT_CODES.md.

Without this gate, a contributor adding a new failure mode (e.g.
`exit 42` for a brand-new resource-provisioning subscript) can land
the change without updating the central key, and operators get an
opaque exit code with no recovery hint. The test fails loud and
the fix is one line in EXIT_CODES.md.

Scope: scripts directly under `apps/dma-insights/infra/*.sh`.
Vendored libraries (e.g. `setup-pg-extensions.sh` calling out to
external tooling) are still in scope -- their exit codes propagate.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

INFRA_DIR = Path(__file__).parent.parent.parent / "infra"
EXIT_CODES_MD = INFRA_DIR / "EXIT_CODES.md"


# Exits that don't need a per-script row in the key:
#   - 0 is success and is convention-documented at the top of the file
SKIP_CODES: set[str] = {"0"}


def _enumerate_exits() -> dict[str, set[str]]:
    """Map basename → set of `exit N` codes used in that script."""
    out: dict[str, set[str]] = {}
    for sh in sorted(INFRA_DIR.glob("*.sh")):
        codes: set[str] = set()
        for line in sh.read_text().splitlines():
            m = re.match(r"^\s*exit\s+(\d+)\b", line)
            if m:
                codes.add(m.group(1))
        if codes:
            out[sh.name] = codes
    return out


@pytest.fixture(scope="module")
def exits() -> dict[str, set[str]]:
    return _enumerate_exits()


@pytest.fixture(scope="module")
def doc_text() -> str:
    if not EXIT_CODES_MD.exists():
        pytest.skip(f"{EXIT_CODES_MD} not present in this checkout")
    return EXIT_CODES_MD.read_text()


def test_at_least_one_script_uses_exit_codes(exits: dict[str, set[str]]) -> None:
    """Defence: if the scan returns nothing, the regex is broken."""
    assert exits, (
        "No `exit N` literals found in infra/*.sh -- either every script "
        "stopped using explicit exits OR the scan regex broke. Either "
        "way, manual inspection required."
    )


def test_every_script_with_exits_has_a_section_in_key(
    doc_text: str, exits: dict[str, set[str]],
) -> None:
    """Each script that uses `exit N` (with N != 0) must have its
    own `### <script>` header in EXIT_CODES.md."""
    missing: list[str] = []
    for script, codes in exits.items():
        meaningful = codes - SKIP_CODES
        if not meaningful:
            continue
        # Look for the script's section header (either `### script.sh`
        # or `### \`script.sh\``).
        if not re.search(rf"^###\s+`?{re.escape(script)}`?", doc_text, re.MULTILINE):
            missing.append(f"{script} (exits: {sorted(meaningful)})")
    assert not missing, (
        "Scripts with `exit N` literals (N != 0) missing a section in "
        "EXIT_CODES.md:\n  " + "\n  ".join(missing)
        + "\n\nAdd a `### <script>.sh` section to "
        f"{EXIT_CODES_MD.relative_to(INFRA_DIR.parent.parent.parent)} "
        f"with a per-code recovery hint, then re-run."
    )


def test_every_non_zero_exit_code_appears_in_doc(
    doc_text: str, exits: dict[str, set[str]],
) -> None:
    """For each script's section, every non-zero `exit N` literal in
    the script must appear as a literal `N` somewhere in that
    section's table (a `| 1 |` or `| 2..5 |` range row)."""
    # Split doc into per-script sections by ### headers
    sections: dict[str, str] = {}
    current_name: str | None = None
    buf: list[str] = []
    for line in doc_text.splitlines():
        m = re.match(r"^###\s+`?([^\s`]+\.sh)`?", line)
        if m:
            if current_name is not None:
                sections[current_name] = "\n".join(buf)
            current_name = m.group(1)
            buf = []
        else:
            buf.append(line)
    if current_name is not None:
        sections[current_name] = "\n".join(buf)

    undocumented: list[str] = []
    for script, codes in exits.items():
        section = sections.get(script, "")
        if not section:
            # Section absence is caught by the previous test; don't
            # double-report here.
            continue
        for code in sorted(codes - SKIP_CODES):
            # Accept a bare `N` (table cell), a `\`N\`` formatted code,
            # or an `N..M` range that brackets the value.
            if re.search(rf"`{re.escape(code)}`", section):
                continue
            if re.search(rf"\b{re.escape(code)}\b", section):
                continue
            # Range form: e.g. `2..5` documents 2, 3, 4, 5
            range_match = re.findall(r"(\d+)\.\.(\d+)", section)
            in_range = any(
                int(lo) <= int(code) <= int(hi)
                for lo, hi in range_match
            )
            if in_range:
                continue
            undocumented.append(f"{script}: exit {code}")
    assert not undocumented, (
        "Exit codes used in scripts but NOT documented in their "
        "EXIT_CODES.md section:\n  " + "\n  ".join(undocumented)
        + "\n\nAdd a row to the script's table with a recovery hint."
    )
