"""Every command a routine prompt names must exist, with the flags it names.

A prompt is not code. Nothing type-checks it, nothing imports it, and the
first thing that evaluates it is a fresh trigger-fired session at 06:23 with
nobody reading. So a wrong flag is not a typo — it is a firing that dies at
its first step and reports nothing anyone sees until someone asks why the
routine went quiet.

There WAS a guard for this (test_synthesis_watchdog.py, added 2026-08-23
after `pull-ledgers --into` was written where the parser defines `--dest`).
It checked the watchdog prompt against two named subcommands. Four other
prompts, and every other command in them, went unchecked — which is how
`run_gate.py pick --count 2` survived in the synthesis prompt after `--count`
had changed meaning, and how `--stress` would have survived its removal. A
guard scoped to one prompt is a guard that reports green about the four it
never opened.

This walks EVERY prompt in ROUTINES.md and checks EVERY command in it. The
floor assertion at the bottom is the part that matters most: it fails when
the walk stops finding things to check, so this can never quietly cover
nothing the way its predecessor did.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "plugins" / "dma-insights" / "docs" / "ROUTINES.md"

#: `python3 <script> [subcommand] [--flags ...]`, up to a backtick or newline.
#: Both path shapes the prompts use, and both are resolved against the repo.
INVOCATION = re.compile(
    r"python3?\s+((?:plugins/dma-insights/)?scripts/[a-z_0-9]+\.py)([^`\n]*)")
FLAG = re.compile(r"(--[a-z][a-z0-9-]*)")

#: Commands whose --help cannot run in a bare checkout. Kept EXPLICIT and
#: empty until something earns a place here: a silent skip list is how a
#: guard stops guarding.
UNRUNNABLE: dict = {}


def prompts() -> dict:
    """Every fenced block under a `### 2x` heading, keyed by its heading.

    Section 2 is the session routines; section 1 is Cloud Scheduler and its
    fences are gcloud, not prompts.
    """
    if not DOC.is_file():
        return {}
    text = DOC.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"^### (2[a-z-]*(?:-[a-z]+)?) · (.+)$", text, re.M):
        start = m.end()
        nxt = text.find("\n### ", start)
        body = text[start:nxt if nxt > 0 else len(text)]
        blocks = re.findall(r"\n```\n(.*?)\n```", body, re.S)
        if blocks:
            out[f"{m.group(1)} {m.group(2)[:40]}"] = "\n".join(blocks)
    return out


def defined_flags(script: str, sub: str | None) -> set | None:
    """The flags a script's parser actually defines, read from the parser.

    None when --help could not run at all — reported by the caller rather
    than swallowed, so an unrunnable script is visible instead of skipped.
    """
    argv = [sys.executable, str(ROOT / script)]
    if sub:
        argv.append(sub)
    argv.append("--help")
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=90,
                           cwd=ROOT)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (r.stdout or "") + (r.stderr or "")
    if not text.strip():
        return None
    # argparse prints usage even on a bad subcommand; a real help page names
    # at least --help itself.
    return set(FLAG.findall(text)) if "--help" in text else None


def commands() -> list:
    """(section, script, subcommand, flags) for every invocation in every
    prompt, deduplicated."""
    seen, out = set(), []
    for section, prompt in prompts().items():
        for script, tail in INVOCATION.findall(prompt):
            tokens = tail.split()
            sub = (tokens[0] if tokens and not tokens[0].startswith("-")
                   and re.fullmatch(r"[a-z][a-z0-9-]*", tokens[0]) else None)
            flags = tuple(sorted(set(FLAG.findall(tail))))
            key = (script, sub, flags)
            if key in seen:
                continue
            seen.add(key)
            out.append((section, script, sub, flags))
    return out


ALL = commands()


def test_the_doc_carries_prompts_to_check():
    """The predecessor's failure mode, asserted directly: a guard that finds
    no prompts passes every test in this file while checking nothing."""
    found = prompts()
    assert len(found) >= 4, (
        f"only {len(found)} routine prompts found in {DOC} — section 2 "
        f"declares five live routines and each keeps its prompt verbatim. "
        f"Found: {sorted(found)}")


def test_enough_commands_are_actually_checked():
    """The floor. The prompts name upwards of twenty distinct invocations;
    a walk that suddenly finds three has stopped parsing, not stopped
    needing to."""
    assert len(ALL) >= 15, (
        f"only {len(ALL)} commands extracted from the routine prompts — the "
        f"extraction has broken, and every assertion below it is vacuous. "
        f"Extracted: {[(c[1], c[2]) for c in ALL]}")


@pytest.mark.parametrize(
    "section,script,sub,flags",
    [c for c in ALL if c[3]],
    ids=[f"{c[1].rsplit('/', 1)[-1]}:{c[2] or '-'}" for c in ALL if c[3]])
def test_every_flag_a_routine_prompt_names_exists(section, script, sub, flags):
    path = ROOT / script
    assert path.is_file(), (
        f"{section} tells a routine to run `{script}`, which does not exist")
    if (script, sub) in UNRUNNABLE:
        pytest.skip(UNRUNNABLE[(script, sub)])
    defined = defined_flags(script, sub)
    assert defined is not None, (
        f"`{script} {sub or ''} --help` produced no readable help, so the "
        f"flags {section} names cannot be checked. A prompt naming a command "
        f"nothing can introspect is not verifiable — fix the script or add "
        f"it to UNRUNNABLE with a reason")
    missing = [f for f in flags if f not in defined]
    assert not missing, (
        f"{section} tells a routine to run `{script} {sub or ''} "
        f"{' '.join(missing)}` and {'that flag does' if len(missing) == 1 else 'those flags do'} "
        f"not exist. Defined for this subcommand: {sorted(defined)}")


@pytest.mark.parametrize(
    "section,script,sub,flags", ALL,
    ids=[f"{c[1].rsplit('/', 1)[-1]}:{c[2] or '-'}" for c in ALL])
def test_every_subcommand_a_routine_prompt_names_exists(section, script, sub,
                                                        flags):
    """A wrong SUBCOMMAND fails the same way a wrong flag does, and reads
    even more like the script being broken."""
    path = ROOT / script
    assert path.is_file(), f"{section} names {script}, which does not exist"
    if sub is None or (script, sub) in UNRUNNABLE:
        pytest.skip("no subcommand to check")
    r = subprocess.run([sys.executable, str(path), sub, "--help"],
                       capture_output=True, text=True, timeout=90, cwd=ROOT)
    combined = (r.stdout or "") + (r.stderr or "")
    assert "invalid choice" not in combined, (
        f"{section} tells a routine to run `{script} {sub}`, and argparse "
        f"calls that an invalid choice: {combined.strip()[:300]}")


def live_prompts() -> dict:
    """The prompts a firing will actually execute.

    § 2a-ii is a deleted routine's archived record. It was pinned to one
    client and carried a version floor, and both are part of why it is
    deleted — rewriting it would erase the lesson it exists to carry.
    """
    return {k: v for k, v in prompts().items() if not k.startswith("2a-ii")}


def test_no_prompt_carries_a_version_literal():
    """Owner, 2026-08-23. A floor written as prose is never evaluated: the
    prompts said ">= 0.6.0" and ">= 0.8.0" while a container ran 0.2.0 with
    five of forty-seven agents, and nothing compared the two. The check is
    `plugin_version.py`; a number here is the defect coming back."""
    offenders = []
    for section, prompt in live_prompts().items():
        for m in re.finditer(r"[>=]=\s*\d+\.\d+\.\d+|version\s+\d+\.\d+\.\d+",
                             prompt, re.I):
            # The measured incident is quoted in several prompts ON PURPOSE,
            # as the reason the rule exists. A quoted floor is inside quotes.
            span = prompt[max(0, m.start() - 60):m.end() + 10]
            if '"' in span or "never evaluated" in span or "cleared every floor" in span:
                continue
            offenders.append((section, m.group(0)))
    assert not offenders, (
        f"a version floor is written into a routine prompt: {offenders}. "
        f"Run plugins/dma-insights/scripts/plugin_version.py instead — it "
        f"compares the installed plugin against what the checkout publishes")


def test_no_prompt_names_a_client_to_produce():
    """Owner, 2026-08-23: "Ensure no client hardcoding. This is a routine
    meant to run and ingest DMAs."

    Scoped to the LIVE routines, per `live_prompts`.
    """
    live = live_prompts()
    named = re.compile(
        r"houlihan|t\.? ?rowe|baxter|logix|shore[- ]united|hughes[- ]federal|"
        r"propartners|bok[- ]financial", re.I)
    offenders = [(section, m.group(0))
                 for section, prompt in live.items()
                 for m in named.finditer(prompt)]
    assert not offenders, (
        f"a live routine prompt names a client: {offenders}. The gate walks "
        f"the pending queue in the queue's own order; the gold exemplar is "
        f"read from fixtures/gold_manifest.json; the held-out control lives "
        f"in run_gate.HELD_OUT and subtracts")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
