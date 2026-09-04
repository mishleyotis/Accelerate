#!/usr/bin/env python3
"""The routing brief — for every session start, every subagent, every compaction.

WHY THIS FILE CHANGED.

  AUD-0004  Claude Code delivers SessionStart hooks to TOP-LEVEL sessions only.
      Measured over the project's transcripts: the parent carried 4
      `SessionStart:startup` attachments; 3 of 3 subagent transcripts carried
      0. And the synthesis Routine orders the top session to "dispatch every
      routed stage DIRECTLY via the Agent tool", so the ENTIRE routed producer
      population — 30 producers, 3 checkers, the consolidator, the vetter —
      started without "route before you produce", without "read
      get_memory_digest first", without "only the surface-producer submits",
      and without the routing.md pointer. The harness offers `SubagentStart`
      with `additionalContexts`; hooks.json declared 3 event types and not
      that one.

  AUD-0054  the source filter admitted `startup` and `clear` only. The CLI's
      SessionStart enum is five values, so the brief was silent on `resume`,
      `compact` and `fork` — and the docstring's justification ("resumes and
      compaction continuations already carry the brief in context") was
      asserted, never tested. A synthesis firing that produces six pages WILL
      compact, and after it does, the routing rule is whatever the summariser
      chose to keep.

So: all five sources print, subagents get their own brief through
SubagentStart, and the compaction case gets the one thing it never had — a
destination to route to (`05-lifecycle/routing.md § After a compaction`).

Contract: reads the hook event as JSON on stdin, prints to stdout. No
network, no state, fails OPEN — a brief that cannot decide prints, because
failing closed costs the brief on exactly the session that needed it.
"""
import json
import sys
from pathlib import Path

ROUTING = "skills/dma-surface-production/05-lifecycle/routing.md"

CORE = (
    "dma-insights: route before you produce. Entry fork first — an entity + "
    "evidence mode with NO package yet is a RESEARCH engagement "
    "(research-conductor produces the package; it is not Drive ingestion) "
    "and it opens with the binding preflight — a financial-statement review, "
    "an LOB census and an AskUserQuestion the engagement owner ANSWERED, "
    "never a sub-vertical you inferred; then PRELIM, which gates every "
    "category card. "
    "A finished '<Client> - DMA' folder goes to package-vetter, then "
    "production; a repair naming a surface or page routes by the table. In "
    "production: one surface -> that page's per-surface producer, then "
    "finding-challenger, then page-consolidator; only the surface-producer "
    "submits or promotes. Read get_memory_digest before authoring anything, "
    "and end every production with the qa-overseer so the findings memory "
    f"learns. Routing table: {ROUTING}"
)

#: The research children work a different substrate (the scoring workbook,
#: not the connector), so the production brief is wrong for them — telling a
#: category researcher "produce only the surface you were dispatched for"
#: is exactly the kind of half-applicable rule a compacted child obeys into
#: a mess. They get their own.
RESEARCH_BRIEF = (
    "dma-insights research tier: the workbook is the substrate — what you do "
    "not write there did not happen. First command (and after ANY "
    "interruption or compaction): engine.brief dispatch --run <R> --root "
    "<ROOT> --category <YOURS> — one bounded packet carrying what the run "
    "already knows, the evidence ALREADY registered for your open cells "
    "(read it before searching; the run paid for it), the volleys each "
    "cell still owes, and your own notebook compacted, so a lost context "
    "costs a read and not a re-search. Then engine.cli orient --run <R> "
    "--root <ROOT> --category <YOURS> for the work card; obey its do_first "
    "literally. Report with engine.brief handback --category <YOURS>. "
    "Protocol: "
    "skills/dma-research/references/RESEARCH-PROTOCOL.md — the five volleys "
    "in order (works, fails, value, contradicts, corroborates; every one "
    "FIRED and logged per cell — the floors gate counts them, and an empty "
    "cell closes only as a declared absence via `engine.cli absence`), the "
    "memory notebook, the refusals. The templates are pinned in "
    "references/templates/ and bound into the run at start; read "
    "gold_reference.json before you author anything. "
    "PRELIM ran before you: the institution profile, timeline, peer set and "
    "technology baseline are already in the workbook (Report_Narrative "
    "PRELIM-* rows, Entity_Timeline, Peer_Benchmarks, Tech_Register) — read "
    "them before your first search rather than re-researching them, and if "
    "orient says PRELIM is open, say so and stop instead of working a card "
    "the phase gate is holding. "
    "Work only your own category; never score, never submit, never promote."
)

#: The SCORING tier (scoring-p1..p4-producer, scoring-critic). Measured
#: 2026-09-03: these agents received CORE + SUBAGENT — the production
#: submit-boundary rule — and no word about the assessment stage they run.
SCORING_BRIEF = (
    "dma-insights scoring tier: the workbook is the substrate and column D is "
    "yours alone. First command (and after ANY interruption or compaction): "
    "engine.assessment state --run <R> --root <ROOT>. `engine.assessment "
    "open` has NO --force: it refuses until every category's floors gate is a "
    "PASS recorded with --require-synthesis, PRELIM is closed, the five-year "
    "financial trajectory is banked and the run's evidence density meets the "
    "Golden 1 floors — if it refuses, the research is not finished and you "
    "say so rather than scoring around it. Score only through "
    "`engine.assessment score` (it refuses an unsynthesised or unchallenged "
    "row, a score above its evidence ceiling, a rationale under 150 chars or "
    "one citing nothing the row carries, a blank AI-and-data overlay); the "
    "critic is a DIFFERENT actor from every scorer; `engine.assessment gate` "
    "must record PASS before any report section may be written. Read "
    "references/templates/gold_reference.json (the Golden 1 shape) and "
    "skills/dma-assessment/references/scoring_methodology.md before the "
    "first score. Score only your own pillar; never write a report section, "
    "never submit, never promote."
)

#: The REPORT tier (report-research-producer, report-assessment-producer,
#: report-validator). Measured 2026-09-03: `report-research-producer` matched
#: the substring "research-" and received the CATEGORY RESEARCHER's brief —
#: "fire five volleys, engine.brief dispatch --category <YOURS>" — while the
#: other two received no template or precondition pointer at all.
REPORT_BRIEF = (
    "dma-insights report tier: the run is finished before you start, and the "
    "report is written INTO a pinned Doc, not a remembered shape. First "
    "command (and after ANY interruption or compaction): engine.cli "
    "narrative preconditions --run <R> --root <ROOT> --report "
    "<client_research|assessment> — it must print ready; if it does not, STOP "
    "and report what it names (PRELIM open, a category gate not PASS, the "
    "templates unbound, the SCORING gate not PASS, the workbook incomplete, "
    "the five-year financial trajectory missing). Owner, 2026-09-03: 'report "
    "writing starts without scoring happening' — this is the check that stops "
    "it, and `engine.cli narrative write` runs it again on every write. Then "
    "engine.template binding --run <R> --root <ROOT>, and read the Doc you "
    "write to — references/templates/client_profile_template.md or "
    "assessment_report_template.md — and references/templates/"
    "gold_reference.json (the Golden 1 depth) before you open a section. "
    "Write only through `engine.cli narrative write` (blocks in the Doc's "
    "order, the card floors, the countable minimum data); render only through "
    "`engine.cli report`, which authors into the branded shell; run `python3 "
    "-m engine.gold_standard report <docx> --kind <k>` on your own output "
    "before you hand back. The validator writes no section and passes none "
    "whose citations it did not open. Never score, never submit, never "
    "promote."
)

#: The install states on which research, scoring and report work is REFUSED
#: rather than warned about. UPDATED_MID_SESSION is not one: the disk is
#: fixed and child processes bind the healed install.
REFUSING_INSTALL_STATES = ("STALE", "MISSING", "INCOMPLETE", "DIVERGED",
                           "DISABLED", "MANIFEST_SPLIT")

#: What each start source needs ON TOP of the core rule. `resume`, `compact`
#: and `fork` used to print nothing at all.
BY_SOURCE = {
    "startup": "",
    "clear": "",
    "resume": (" This session RESUMED: re-read the routing table before "
               "acting — a resumed turn carries whatever context survived, "
               "not necessarily this rule."),
    "compact": (" This session was COMPACTED: the routing rule, the memory "
                f"rule and the submit boundary are NOT guaranteed to have "
                f"survived the summary. Re-read {ROUTING} § After a "
                f"compaction before your next tool call."),
    "fork": (" This session is a FORK: it inherits a transcript it did not "
             "write. Confirm which run and which surface you own before "
             "producing anything."),
}

SUBAGENT = (
    " You are a SUBAGENT. You do not inherit the parent's brief — this is it. "
    "Produce only the surface you were dispatched for; do not re-produce a "
    "page to repair a field, and do not submit or promote: that boundary "
    "belongs to the surface-producer alone."
)


def install_warning() -> str:
    """One sentence when this container's plugin is not what the repo ships.

    WHY THE HOOK CARRIES IT (owner, 2026-08-31: "Does the plugin have similar
    routine ingrained?"). Until now the staleness check lived only in a
    Routine prompt: the intake Routine ran it, and every other session — an
    interactive one, a synthesis lane, a watchdog firing — started on
    whatever the container's snapshot happened to hold and found out only
    when something behaved oddly. A firing had already died on
    `STALE: installed 0.9.12 (47 agents) vs published 1.13.0 (68 agents)`,
    and nothing outside that one prompt would ever have said so.

    IT REPORTS AND DOES NOT REPAIR, deliberately. The repair uninstalls and
    reinstalls the plugin cache — the very directory the session is binding
    its agents from as this hook runs — and it takes far longer than the
    hook's 10-second budget. Mutating an install underneath a binding session
    would turn a stale roster into no roster. So the hook names the state and
    the one command that fixes it, and the session decides.

    Fails OPEN, like the rest of this file: a version check that cannot run
    must never cost the routing brief.
    """
    zip_text = ""
    try:
        # The install judging ITSELF (the Cowork zip path): manifest version
        # vs the plugin version the pinned templates were pinned for.
        eng = Path(__file__).resolve().parent.parent.parent / "skills" / "dma-research"
        sys.path.insert(0, str(eng))
        from engine import template as _T                      # noqa: PLC0415
        g = _T.zip_guard()
        if not g.get("ok"):
            zip_text = (f" INSTALL CHECK (zip guard): this install's manifest is "
                        f"{g.get('installed')} but its pinned templates require plugin "
                        f"{g.get('required')} — the upload PREDATES ITS OWN TEMPLATES. "
                        f"RESEARCH, SCORING AND REPORT WORK IS REFUSED ON THIS INSTALL: "
                        f"`engine.cli start` refuses it too. {g.get('fix')}")
    except Exception:            # noqa: BLE001 — fail OPEN, on purpose
        zip_text = ""
    try:
        here = Path(__file__).resolve().parent.parent          # scripts/
        sys.path.insert(0, str(here))
        import plugin_version                                  # noqa: PLC0415
        v = plugin_version.compare()
        if v["ok"]:
            return zip_text
        status = str(v.get("status") or "")
        refusing = status in REFUSING_INSTALL_STATES
        return (f" INSTALL CHECK, from this container rather than from "
                f"expectation: {plugin_version.summary(v)}. This session is "
                f"NOT running what the checkout publishes."
                + (f" RESEARCH, SCORING AND REPORT WORK IS REFUSED ON THIS "
                   f"INSTALL: do not run /dma-insights:run-assessment, "
                   f"`engine.pipeline run` or `engine.cli start`, and do not "
                   f"dispatch any research, scoring or report agent, until "
                   f"`python3 plugins/dma-insights/scripts/doctor.py --heal` "
                   f"reports OK — the engine's own `start` refuses on this "
                   f"state too (measured 2026-09-03: a 0.9.12 install ran "
                   f"none of the gates the checkout publishes)."
                   if refusing else
                   f" Before you rely on an agent, a skill or a hook, run "
                   f"`python3 plugins/dma-insights/scripts/doctor.py --heal` "
                   f"— it applies the repair this status needs and re-checks "
                   f"in one command.")
                + f" If it comes back UPDATED_MID_SESSION the disk is fixed and "
                f"THIS session still holds the old roster (they bind once, at "
                f"start): keep working, but dispatch stages as fresh child "
                f"processes via `agent_run.py` / `engine.pipeline run`, which "
                f"bind the repaired install.") + zip_text
    except Exception:            # noqa: BLE001 — fail OPEN, on purpose
        return zip_text


def brief(event: dict) -> str:
    hook = str(event.get("hook_event_name") or event.get("hookEventName") or "")
    agent = str(event.get("agent_type") or event.get("agentType") or "")
    if hook == "SubagentStart" or agent:
        # Route by the agent's TIER, on its name after the plugin prefix.
        # A substring test on "research-" sent report-research-producer the
        # category researcher's brief (measured 2026-09-03).
        name = agent.split(":", 1)[-1]
        if name.startswith("report-"):
            return REPORT_BRIEF
        if name.startswith("scoring-"):
            return SCORING_BRIEF
        if name.startswith("research-") or name == "technographic-scanner":
            return RESEARCH_BRIEF
        return CORE + SUBAGENT
    source = str(event.get("source") or "startup")
    # Top-level sessions only. A subagent runs inside a parent that already
    # saw this and cannot act on it — its parent is mid-flight — so telling
    # each of 68 of them turns a warning into wallpaper.
    return CORE + BY_SOURCE.get(source, BY_SOURCE["resume"]) + install_warning()


def main() -> int:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            event = {}
    except Exception:            # noqa: BLE001 — fail OPEN, on purpose
        event = {}
    text = brief(event)
    # SubagentStart takes `additionalContexts`; SessionStart takes plain
    # stdout. Emitting the JSON form for a subagent is what actually puts the
    # brief in the child's context — printing to stdout there would be
    # swallowed, which is the AUD-0004 failure wearing a fix.
    if event.get("hook_event_name") == "SubagentStart" or \
            event.get("hookEventName") == "SubagentStart":
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContexts": [text],
            }
        }))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
