"""PreToolUse guard: the scoring workbook and the two reports have ONE writer.

WHY THIS EXISTS. Every goeasy finding (docs/goeasy-findings-register.md)
shares one root: "the work went around the pipeline" — the workbook was
hand-scored with openpyxl, the reports were built as a blank `Document()`.
The engine's refusals only fire when an agent calls the engine, and until
2026-09-03 nothing stopped an agent from opening openpyxl or python-docx
directly on a deliverable (measured: no hook denied
`openpyxl.Workbook().save("DMA_Scoring_Workbook_x.xlsx")`). This is the
interception the plugin already uses for credentials and bulk reads, pointed
at the deliverables.

WHAT IT DENIES. On Bash: an inline/one-off Python that constructs a workbook
or document and saves it to a deliverable-shaped path, or that RUNS a
retired writer (`populate_workbook.py`, `validate_workbook.py`,
`assessment_runner.py` — running one, not reading it). On
Write/Edit/MultiEdit/NotebookEdit: a target path ending in .xlsx/.xlsm/.docx.

WHAT IT ALLOWS, deliberately. Anything that runs the engine (`-m engine.` or
`engine/`), the test suites (`pytest`, paths under `tests/`), the stress walks
(`stress_`), the plugin's own scripts (`scripts/…py`), and every read.
Fail-open on malformed input, like its siblings: a guard that bricks every
call when the harness changes its stdin shape is worse than the gap it closes.
Allow = exit 0 with no output.
"""
import json
import re
import sys

REASON = (
    "dma-insights: the scoring workbook and the two reports have ONE writer — "
    "the engine — and this call writes {what} around it. Register evidence "
    "with `engine.cli evidence`, close a cell with `engine.cli synthesise` / "
    "`engine.cli absence`, score with `engine.assessment score`, write a "
    "section with `engine.cli narrative write`, render with `engine.cli "
    "report`, build the client folder with `engine.assemble package`. A file "
    "written any other way is not gated and is not a deliverable (goeasy "
    "GSY-05/GSY-15: the whole register shares this one root)."
)

#: A command that goes THROUGH the engine or the suites is the sanctioned
#: path, whatever library it imports along the way.
ALLOW = re.compile(
    r"(-m\s+engine\.|/engine/|\bengine/[a-z_]+\.py|\bpytest\b|(^|[\s/])tests/|"
    r"\bstress_[a-z_]+\.py|plugins/dma-insights/scripts/[a-z_]+\.py|"
    r"\bgold_standard\b|\bpatch_validator\b)")

#: Constructing or saving a workbook / document outside the engine.
CONSTRUCT = re.compile(
    r"(openpyxl\.Workbook\s*\(|\bWorkbook\s*\(\s*\)|load_workbook\s*\(.*\)\s*\.save\s*\(|"
    r"\bdocx\.Document\s*\(|\bDocument\s*\(\s*\)|\.save\s*\(\s*[\"'][^\"']*\.(xlsx|xlsm|docx)[\"']|"
    r"\bDocument\s*\(\s*[\"'][^\"']*\.docx[\"']\s*\))")

#: The deliverable shapes, so a scratch spreadsheet in /tmp is not a denial.
DELIVERABLE = re.compile(
    r"(DMA_Scoring_Workbook|Scoring_Workbook|DMA_Assessment_Report|Assessment_Report|"
    r"Client_Profile_Research|Research_Report|Technographic_Scan|09_deliverables|"
    r"\s-\sDMA[/\"']|dma_output|DMA_RUN_ROOT|\.xlsx|\.docx)", re.I)

#: RUNNING a retired writer — an interpreter (or a shebang path) immediately
#: before it. Measured 2026-09-04: matching the bare filename denied `sed -n`
#: and `grep` on the file too, so the guard blocked reading the very script
#: whose refusal it exists to enforce. A guard that stops a reader has stopped
#: being a guard.
RETIRED = re.compile(
    r"(python3?|py|uv\s+run|\./|bash|sh)\s*\S*"
    r"(populate_workbook|validate_workbook|assessment_runner)\.py")

FILE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
FILE_EXT = re.compile(r"\.(xlsx|xlsm|docx)$", re.I)


def decide(payload: dict) -> str | None:
    """The denial reason, or None to allow."""
    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        return None
    if tool in FILE_TOOLS:
        path = str(ti.get("file_path") or ti.get("path") or ti.get("notebook_path") or "")
        if FILE_EXT.search(path):
            return REASON.format(what=f"`{path.rsplit('/', 1)[-1]}` directly")
        return None
    if tool != "Bash":
        return None
    cmd = ti.get("command") or ""
    if not isinstance(cmd, str) or not cmd.strip():
        return None
    if ALLOW.search(cmd):
        return None
    if CONSTRUCT.search(cmd) and DELIVERABLE.search(cmd):
        return REASON.format(what="a workbook or document")
    if RETIRED.search(cmd):
        return REASON.format(what="through a retired writer")
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
    except Exception:            # noqa: BLE001 — fail OPEN, on purpose
        return 0
    reason = decide(payload)
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
