#!/usr/bin/env python3
"""Prove a test can fail. A test green under mutation asserts nothing.

Every gate and every check added during this build was hand-checked by breaking
the thing it guards and watching it go red — the em-dash ratchet, Gate C, Gate
D, Gate F's negative control, AG-09, the entity-search rule. That worked and it
does not scale: it is a habit, not a property, and habits lapse exactly when a
suite grows fastest.

This is the property. For a (test, target) pair it mutates the TARGET one token
at a time and re-runs the TEST. A mutation the test does not notice SURVIVED. A
pair whose mutations all survive is VACUOUS — the test passes whatever the code
says — and that is the failure this blocks.

WHAT IT MUTATES, and why these. Each corresponds to a defect this build actually
shipped rather than to a textbook operator list:

    a numeric literal      the alert ceiling was off by one; the corpus ratchet
                           and the em-dash counts are all pinned integers
    a comparison           `<` versus `<=` is invariant 6's four band
                           boundaries, and `>=` versus `>` was the ceiling bug
    a boolean literal      `is_thin_evidence`, `below_threshold`, `deployed`
                           tri-state — flags that decide what renders
    a `not`                the redaction walker and every default-deny path
    and/or                 `_empty_declared or may_be_empty` decides whether a
                           producer is told to fill a field
    a string literal       enum values and gate ids; a guessed `'ACTIVE'` that
                           was not in `run_status_t` killed the enrichment job

WHAT IT DELIBERATELY DOES NOT DO. It does not mutate comments, docstrings, or
the test file itself, and it stops at the first N surviving mutants per pair so
a large target cannot make a run take an hour. Coverage of mutants is not the
point; the point is that at least one mutation of the code under test makes the
test go red.

    mutation_check.py --pairs                 run the committed pair list
    mutation_check.py <test> <target> [...]   run one pair
    mutation_check.py --pairs --max 8         cap mutants per pair
"""
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAIRS = REPO / "apps" / "web" / "tests" / "acceptance" / "mutation_pairs.json"

# (pattern, replacement-fn). Applied to one match at a time.
MUTATORS = [
    (re.compile(r"(?<![\w.])(\d+)(?![\w.])"), lambda m: str(int(m.group(1)) + 1)),
    (re.compile(r"(?<=[\s(])<=(?=[\s(])"), lambda m: "<"),
    (re.compile(r"(?<=[\s(])>=(?=[\s(])"), lambda m: ">"),
    (re.compile(r"(?<=[\s(])<(?=[\s(])"), lambda m: "<="),
    (re.compile(r"(?<=[\s(])>(?=[\s(])"), lambda m: ">="),
    (re.compile(r"(?<=[\s(])==(?=[\s(])"), lambda m: "!="),
    (re.compile(r"(?<=[\s(])!=(?=[\s(])"), lambda m: "=="),
    (re.compile(r"\bTrue\b"), lambda m: "False"),
    (re.compile(r"\bFalse\b"), lambda m: "True"),
    (re.compile(r"\bnot\s+"), lambda m: ""),
    (re.compile(r"(?<=[\s)])\band\b(?=\s)"), lambda m: "or"),
    (re.compile(r"(?<=[\s)])\bor\b(?=\s)"), lambda m: "and"),
]

_COMMENT = re.compile(r"^\s*#")


def prose_spans(src: str, path: str) -> list:
    """Character spans of comments and string literals — not code.

    This build's modules carry long docstrings that quote line numbers,
    migration ids and thresholds. Mutating `'0047'` inside a paragraph
    explaining migration 0047 changes nothing that runs, so the mutant survives
    for a reason that has nothing to do with the test, and the pair gets
    reported as vacuous. The first run of this tool did exactly that.

    Python is parsed rather than pattern-matched, because a regex for triple
    quotes gets nested quotes and f-strings wrong and would silently protect
    real code from mutation — a false PASS, which is worse than a false fail.
    """
    spans = []
    pos = 0
    for line in src.splitlines(keepends=True):
        if _COMMENT.match(line):
            spans.append((pos, pos + len(line)))
        pos += len(line)
    if not path.endswith(".py"):
        return spans
    try:
        import ast
        tree = ast.parse(src)
    except SyntaxError:
        return spans
    offsets = [0]
    for line in src.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))

    def at(row, col):
        return offsets[row - 1] + col

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.end_lineno is None:
                continue
            spans.append((at(node.lineno, node.col_offset),
                          at(node.end_lineno, node.end_col_offset)))
    return spans


def region(src: str, symbol: str | None):
    """The character span a pair is actually about.

    Without this the tool is unfair to exactly the tests worth keeping.
    `validation2.py` is over 1,500 lines; AG-09 is sixty of them. Mutating a
    random integer eight hundred lines away and then reporting that
    `test_rank_against_score.py` "asserts nothing about that file" is a false
    accusation, and a gate that makes false accusations gets switched off.

    So a pair may name the SYMBOL it covers, and mutation is confined to that
    definition's body — which is also what the plan means by mutating the
    asserted field rather than the file. No symbol means the whole file, which
    is right for a JSON contract a test reads end to end.
    """
    if not symbol:
        return 0, len(src)
    # `[ \t]*` and not `\s*`: with re.M, `^` matches at a line start and `\s*`
    # then happily eats BACKWARDS across blank lines, so the match began two
    # lines above the def and the body span collapsed to 32 characters. Every
    # pair reported zero mutants and therefore "vacuous" — the tool accusing
    # every test in its own list of asserting nothing.
    m = re.search(rf"^([ \t]*)(?:async\s+)?def\s+{re.escape(symbol)}\s*\(",
                  src, re.M)
    if m is None:
        m = re.search(rf"^([ \t]*)class\s+{re.escape(symbol)}\b", src, re.M)
    if m is None:
        raise LookupError(f"symbol {symbol!r} is not defined in this file")
    indent = len(m.group(1))
    start = m.start()
    # Scan from the end of the definition's own LINE. Scanning from `m.end()`
    # — just after the opening paren — put the scan's origin mid-line, where
    # re.M's `^` also matches position 0 of the slice, so the very first
    # "line start" found was the remainder of the signature at indent 0 and
    # every body span came out thirty characters long.
    nl = src.find("\n", m.end())
    if nl == -1:
        return start, len(src)
    for line_m in re.finditer(r"\n([ \t]*)(\S)", src[nl:]):
        if len(line_m.group(1)) <= indent:
            return start, nl + line_m.start()
    return start, len(src)


def mutants(src: str, limit: int, symbol: str | None = None, seed: int = 11,
            path: str = ".py"):
    """(description, mutated_source) pairs, sampled deterministically.

    Deterministic on purpose: a mutation run that samples differently every
    time reports a different verdict every time, and nobody can tell a fixed
    test from a lucky one.
    """
    lo, hi = region(src, symbol)
    skip = prose_spans(src, path)

    def is_prose(i):
        return any(a <= i < b for a, b in skip)

    found = []
    for pattern, repl in MUTATORS:
        for m in pattern.finditer(src):
            if not (lo <= m.start() < hi) or is_prose(m.start()):
                continue
            new = repl(m)
            if new == m.group(0):
                continue
            line_no = src.count("\n", 0, m.start()) + 1
            found.append((f"line {line_no}: {m.group(0)!r} -> {new!r}",
                          src[:m.start()] + new + src[m.end():]))
    random.Random(seed).shuffle(found)
    return found[:limit]


def invalidate(target: Path) -> None:
    """Drop compiled bytecode for the mutated file.

    CPython keys a `.pyc` on the source's mtime AND SIZE. Every interesting
    mutator here is length-preserving — `==` to `!=`, `<` to `>`, `and` to
    `or` — and a write landing in the same mtime second is therefore
    indistinguishable from the original to the cache. The subprocess imports
    the STALE bytecode, the test passes, and the mutant is reported as having
    survived.

    Measured while building this: `attempts_for_run`'s `status == "RESOLVED"`
    was reported as a survivor, and flipping the same operator by hand failed
    five tests. A mutation tool that under-reports kills accuses working tests
    of asserting nothing, and the first thing anyone does with a gate that
    cries wolf is switch it off.
    """
    for pyc in target.parent.glob("__pycache__/*.pyc"):
        pyc.unlink(missing_ok=True)


def run(test: str) -> bool:
    """True when the test PASSES."""
    if test.endswith(".js"):
        cmd = ["node", "--test", test]
        cwd = REPO / "apps" / "web"
        rel = Path(test)
        if rel.is_absolute():
            try:
                cmd = ["node", "--test", str(rel.relative_to(cwd))]
            except ValueError:
                cwd = REPO
    else:
        cmd = [sys.executable, "-m", "pytest", test, "-q", "-x"]
        cwd = REPO
    import os
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       timeout=600, env=env)
    return p.returncode == 0


def check_pair(test: str, target: str, limit: int,
               symbol: str | None = None) -> dict:
    tpath = REPO / target
    if not tpath.exists():
        return {"test": test, "target": target, "error": "target not found"}
    original = tpath.read_text()
    try:
        region(original, symbol)
    except LookupError as e:
        return {"test": test, "target": target, "error": str(e)}

    # Also before the baseline run: an interrupted earlier run can leave
    # bytecode compiled from a MUTATED source behind, and the pair then reports
    # "does not pass before any mutation" about a file that is clean on disk.
    invalidate(tpath)
    if not run(test):
        return {"test": test, "target": target,
                "error": "the test does not pass before any mutation — fix it "
                         "first; a red test kills every mutant for free"}

    survived, killed = [], 0
    backup = tempfile.NamedTemporaryFile("w", delete=False, suffix=".bak")
    backup.write(original)
    backup.close()
    try:
        for desc, mutated in mutants(original, limit, symbol, path=target):
            tpath.write_text(mutated)
            invalidate(tpath)
            try:
                still_green = run(test)
            except subprocess.TimeoutExpired:
                still_green = False   # a hang is a detection, not a survival
            if still_green:
                survived.append(desc)
            else:
                killed += 1
    finally:
        shutil.copyfile(backup.name, tpath)
        invalidate(tpath)
        Path(backup.name).unlink(missing_ok=True)
        assert tpath.read_text() == original, (
            f"FAILED TO RESTORE {target} — restore it from git before doing "
            "anything else")

    return {"test": test, "target": target, "killed": killed,
            "survived": survived, "mutants": killed + len(survived)}


def main(argv) -> int:
    limit = 6
    if "--max" in argv:
        i = argv.index("--max")
        limit = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]

    if "--pairs" in argv:
        if not PAIRS.exists():
            print(f"no pair list at {PAIRS.relative_to(REPO)}", file=sys.stderr)
            return 2
        pairs = [(p["test"], p["target"], p.get("symbol")) for p in
                 json.loads(PAIRS.read_text())["pairs"]]
    elif len(argv) >= 2:
        pairs = [(argv[0], argv[1], argv[2] if len(argv) > 2 else None)]
    else:
        print(__doc__.strip().splitlines()[-3].strip(), file=sys.stderr)
        return 2

    vacuous, errored = [], []
    for test, target, symbol in pairs:
        r = check_pair(test, target, limit, symbol)
        if r.get("error"):
            errored.append(r)
            print(f"  ERROR   {test} × {target}: {r['error']}")
            continue
        # The bar is ONE. A test that notices a single mutation of the code it
        # covers is not vacuous, and demanding a kill RATIO here would turn a
        # correctness gate into a coverage target nobody can hit honestly.
        mark = "VACUOUS" if r["killed"] == 0 else "ok"
        where = f"{target}::{symbol}" if symbol else target
        print(f"  {mark:8}{test} × {where}: "
              f"{r['killed']}/{r['mutants']} mutants killed")
        for s in r["survived"][:3]:
            print(f"             survived: {s}")
        if r["killed"] == 0:
            vacuous.append(r)

    if vacuous or errored:
        print(f"\nmutation check FAILED: {len(vacuous)} vacuous, "
              f"{len(errored)} could not run.", file=sys.stderr)
        for r in vacuous:
            print(f"  {r['test']} passes with {r['target']} mutated "
                  f"{r['mutants']} different ways — it asserts nothing about "
                  "the code it names", file=sys.stderr)
        return 1
    print(f"\nmutation check passed: {len(pairs)} pair(s), none vacuous.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
