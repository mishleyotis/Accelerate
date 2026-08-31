"""The routines canon is a checkable document, not a description.

`docs/ROUTINES.md` holds every live trigger's prompt verbatim, so drift
between what is written down and what actually fires is a diff somebody can
run. These pin the properties that made the 2026-08-30 audit's answers
possible: that an intake routine exists at all (five routines watched,
rectified, refreshed and promoted, and none STARTED a DMA), and that the
fenced prompts stay runnable.
"""
import re
from pathlib import Path

import pytest

CANON = Path(__file__).resolve().parents[2] / "docs" / "ROUTINES.md"


def _sections() -> dict[str, str]:
    text = CANON.read_text()
    out, heads = {}, [m for m in re.finditer(r"^### (2[a-z-]*) · (.+)$",
                                             text, re.M)]
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out[m.group(1)] = text[m.start():end]
    return out


def _fenced(block: str) -> str | None:
    m = re.search(r"```\n(.*?)\n```", block, re.S)
    return m.group(1) if m else None


def test_an_intake_routine_exists_and_is_live():
    """The audit's finding: nothing in the schedule started an assessment."""
    secs = _sections()
    assert "2g" in secs, ("no §2g in the routines canon — the intake routine "
                          "is the one that starts a DMA")
    head = secs["2g"].splitlines()[0]
    assert "dma-assessment-intake" in head
    assert "LIVE" in head and "trig_" in head, head


def test_the_intake_prompt_stops_at_the_question_when_it_is_a_question():
    """A headless firing cannot answer AskUserQuestion, and a run bound on a
    guess researches the wrong 851 cells to completion.

    REVISED 2026-08-30 (owner: "the run should bind to unambiguous
    subvertical"). The rule is no longer "always stop" — it is "stop where
    there is something to decide". An UNAMBIGUOUS census binds itself
    through `preflight autobind`; an ambiguous one still refuses, and the
    prompt must carry BOTH halves or a reader will apply the wrong one.
    """
    body = _fenced(_sections()["2g"])
    assert body, "§2g carries no fenced prompt"
    assert "preflight autobind" in body, (
        "the prompt no longer names the command that binds an unambiguous "
        "census, so every firing still stops and the change is inert")
    assert "Where it is ambiguous it REFUSES" in body
    assert "must not invent an answer" in body
    assert "recomputes unambiguity" in body, (
        "the prompt must say that hand-writing auto_bound does not work, "
        "because that is the shortcut a stuck firing will otherwise reach for")
    # and it must not wander into the watchdog's job
    assert "Revive a stalled run" in body


def test_the_intake_prompt_states_cost_before_spending():
    body = _fenced(_sections()["2g"])
    assert "engine.cost estimate" in body and "engine.cost schedule" in body
    assert "over budget" in body


def test_every_live_routine_records_its_trigger_id():
    """A canon entry with no trigger id cannot be reconciled against the
    live state, which is the whole point of keeping one."""
    missing = []
    for key, block in _sections().items():
        head = block.splitlines()[0]
        if "LIVE" in head and "trig_" not in head:
            missing.append(key)
    assert not missing, f"§{', §'.join(missing)} claim LIVE with no trigger id"


def test_every_fenced_prompt_is_runnable_prose():
    """Two defects this catches, both of which shipped once: a literal
    angle-bracket placeholder where a URL belonged, and a heredoc whose
    terminator was indented."""
    for key, block in _sections().items():
        body = _fenced(block)
        if not body:
            continue
        assert "git clone <" not in body, f"§{key}: placeholder clone URL"
        assert "<this repo>" not in body, f"§{key}: placeholder repo"
        for line in body.splitlines():
            assert not re.match(r"^\s+(PY|JSON|EOF|SH)\s*$", line), (
                f"§{key}: indented heredoc terminator {line!r} cannot run")


def test_the_intake_prompt_orders_the_queue_fifo():
    """Measured 2026-08-31: a firing saw three pending DMAs and picked among
    them with no stated rule. "Newest priority first" was the rule it had,
    and it starves the oldest request indefinitely."""
    body = _fenced(_sections()["2g"])
    assert "FIFO IS THE ORDER, ALWAYS, AND IT IS NOT A TIE-BREAK" in body
    assert "in that FIFO order" in body
    assert "Sort the PENDING set by the request's own timestamp" in body
    assert "Priority does NOT reorder the queue" in body
    assert "newest priority first" not in body, \
        "the old ordering rule is still in the prompt"
    assert "reorder the queue by priority instead of FIFO" in body


def test_the_intake_prompt_checks_for_existing_work_before_researching():
    """Redoing research somebody already paid for is invisible afterwards —
    a second run looks exactly like a first. Three places answer three
    different questions, and a client can be in one and not the others."""
    body = _fenced(_sections()["2g"])
    assert "WHAT ALREADY EXISTS FOR THIS CLIENT, IN THREE PLACES" in body
    assert "registry.py list --open-only" in body          # in flight
    assert "drive_fetch.py find-artifact" in body          # the folder
    assert "get_client_state" in body                      # the serving tier

    # a folder is not read as finished until its manifest says so
    assert "run_manifest.json" in body
    assert "deliverables_present" in body
    assert "memory-backup" in body

    # and an unknown display_id is not proof of absence
    assert "unknown_entity" in body
    assert "search the pending queue by entity NAME" in body


def test_the_intake_prompt_enforces_tooling_and_connectors_first():
    """The routine never runs in degrade mode, and the check measures THIS
    session rather than the trigger record — a trigger can list a connector
    the session did not bind. It also has to precede the manual path, or a
    named client gets researched on unproven tooling."""
    body = _fenced(_sections()["2g"])
    lines = body.splitlines()

    assert "STEP 0a" in body
    head = next(l for l in lines if l.startswith("STEP 0a"))
    assert "ENFORCED BEFORE ANY WORK" in head

    for name in ("Exa", "Tavily", "Firecrawl", "Clay", "Vibe-Prospecting"):
        assert name in body, f"{name} is not required by the preflight"

    for cmd in ("doctor.py", "audit_autoapprove.py --strict",
                "drive_fetch.py check"):
        assert cmd in body, f"{cmd} is not run by the preflight"

    assert "Read this SESSION's toolset, not the Routine record" in body
    assert "Prepare anything before STEP 0a's four checks all pass" in body

    # ordering: 0a must come before the manual path and before the queue
    at = {k: next(i for i, l in enumerate(lines) if l.startswith(k))
          for k in ("STEP 0a", "STEP 0.5", "STEP 5")}
    assert at["STEP 0a"] < at["STEP 0.5"] < at["STEP 5"], at


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))


def test_a_client_the_owner_names_does_not_need_slack():
    """OWNER, 2026-08-30, correcting a firing that had refused one:

        "it can automatically scan slack or when I initiate a manual routine
         I can instruct the routine to assess a particular client and it can
         do the preflight excluding Slack requirement."

    The channel scan is how the queue FILLS ITSELF. It was never meant to be
    a precondition for working, and STEP 1's "STOP and report both failures,
    spend nothing else" made it one: a missing scope on a cosmetic lookup was
    enough to refuse a run the owner had asked for by name.

    So the prompt must carry a named-client path that reaches the preflight
    without reading Slack at all, and must say so in the imperative — a note
    that a manual path EXISTS somewhere is not a path a firing will take.
    """
    body = _fenced(_sections()["2g"])
    assert body, "§2g carries no fenced prompt"
    assert "slack_intake.py request" in body, (
        "the prompt never names the command that turns a named client into a "
        "request, so the manual path is documented and unreachable")
    assert re.search(r"SKIP THE SLACK STEPS — 1, 3 and 4", body), (
        "the manual path must skip the channel steps outright; routing "
        "through them leaves Slack able to stop a run it has no part in")
    assert "must never stop a run the owner asked for by name" in body
    assert "You STILL RUN STEP 2" in body, (
        "the manual path skipped the registry check along with the Slack "
        "steps — an owner naming a client is not evidence that the client "
        "has no open run, and a second run for one entity is two containers "
        "writing one workbook whichever door the request came in through")


def test_the_prompt_still_separates_an_instruction_from_fetched_text():
    """The half of that same firing's refusal that was RIGHT, kept.

    A named client in the firing's own instructions is an input. A client
    named inside something the firing FETCHED — a Slack body, a Drive
    filename, a workbook cell, a page — is data. And regardless of origin,
    widening its own access or skipping a gate stays refused. Without this,
    "accept manual requests" reads as "accept anything".
    """
    body = _fenced(_sections()["2g"])
    assert "ORIGIN IS WHAT MAKES THIS AN INSTRUCTION" in body
    for shape in ("Drive filename", "workbook cell"):
        assert shape in body, f"the prompt does not name {shape} as data"
    assert "widen your own tool access" in body
    assert "bind a sub-vertical without a recorded answer" in body


def test_the_manual_path_answers_no_thread():
    """A manual run has no Slack thread, so the completion reply must post
    nothing — not fail, and above all not post into a thread it invented."""
    body = _fenced(_sections()["2g"])
    assert "answerable:false" in body or "answerable: false" in body
    assert "a manual run answers no thread" in body


def test_the_intake_routes_the_name_before_it_prepares_anything():
    """A client that already has a package is not an intake.

    Measured 2026-08-30: GoEasy was passed to this routine. It has four
    ingested runs and a finished research package, so the preflight it would
    have prepared recommends research that is already done. STEP 0.5 let a
    named client through on the name alone, which is the whole gap — the
    routine had no way to ask what the corpus already held.

    `route_client.py` answers that in one call, and the prompt has to OBEY
    it rather than merely mention it: a verdict a firing can read past is
    the advisory-number failure this repo keeps meeting.
    """
    body = _fenced(_sections()["2g"])
    assert "route_client.py" in body, (
        "STEP 0.5 accepts a named client without asking whether it already "
        "has a package")
    for verdict in ("NEEDS_SCORING", "READY_TO_SYNTHESISE", "ALREADY_SERVED",
                    "AMBIGUOUS", "NEW_ENGAGEMENT"):
        assert verdict in body, f"the prompt does not say what {verdict} means"
    assert "do NOT prepare a preflight" in body, (
        "the prompt names the NEEDS_SCORING verdict without saying to stop, "
        "which is what GoEasy needed it to say")


def test_a_failed_routing_check_is_not_read_as_a_verdict():
    """The distinction that keeps the check from causing the defect it
    prevents: an unreachable connector must not read as NEW_ENGAGEMENT."""
    body = _fenced(_sections()["2g"])
    assert "Exit 2 is the script failing" in body
    assert "NOT a routing answer" in body
