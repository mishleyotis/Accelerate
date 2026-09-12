#!/usr/bin/env python3
"""A permission prompt appeared. Which layer let it through, and who can fix it?

    python3 scripts/why_did_it_prompt.py mcp__Tavily__tavily_search
    python3 scripts/why_did_it_prompt.py Bash --command "python3 -m engine.cli status"
    python3 scripts/why_did_it_prompt.py mcp__claude_ai_Exa__web_search_exa --json

WHY THIS EXISTS (owner, 2026-09-04: "the mcp tools eg tavily, exa etc are
what I get prompts of to approve" — on claude.ai/code, the terminal, Cowork
and claude.ai chat alike, and "when I place allow for all sessions, it
prompts again"). Four layers can each remove a prompt, and a fifth can put
one back that none of the four can remove:

  1. the plugin's PreToolUse hooks  (autoapprove_connector, autoapprove_builtins)
  2. `permissions.allow` — user scope, project scope, project-local scope
  3. the session's permission mode  (dontAsk denies instead of prompting)
  4. the plugin being INSTALLED and ENABLED where the session binds
  5. an ORGANISATION per-tool control of `ask` on a claude.ai connector —
     which, per the permissions reference, prompts on every call in every
     mode, never offers "remember this", and no allow rule skips.

From the outside those look identical: a prompt. This runs the real hooks
against the exact tool name, matches the exact name against every allow rule
the way Claude Code does (bare server, `server__*`, `server__prefix*`,
exact), reads the install record, and then says which layer failed and who
closes it — including the one this repository cannot.

It NEVER reads a tool list from the model's context (no script can) and
never guesses the org control: it names the command that reveals it (`/mcp`
in the prompting session) and the exact reason string the prompt carries
when that is the cause.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
HOOKS = HERE / "hooks"
REPO = PLUGIN.parents[1]

ORG_ASK_REASON = "Your organization requires approval for this tool"


def _load(p: Path) -> dict:
    try:
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def settings_files(repo: Path | None) -> dict[str, Path]:
    home = Path(os.environ.get("HOME") or "/root")
    out = {"user": home / ".claude" / "settings.json"}
    if repo:
        out["project"] = repo / ".claude" / "settings.json"
        out["project-local"] = repo / ".claude" / "settings.local.json"
    return out


def rule_matches(rule: str, tool: str) -> bool:
    """Claude Code's documented MCP/built-in allow-rule matching, as data."""
    if rule == tool:
        return True
    if rule.startswith("mcp__") and tool.startswith("mcp__"):
        parts = tool.split("__", 2)
        if len(parts) < 3:
            return False
        server, name = parts[1], parts[2]
        rparts = rule.split("__", 2)
        if len(rparts) == 2:                       # bare `mcp__server`
            return rparts[1] == server
        if len(rparts) == 3 and rparts[1] == server:
            return fnmatch.fnmatchcase(name, rparts[2])
        return False
    # Built-ins: `Tool` or `Tool(prefix *)` — the prefix form needs the input
    if "(" in rule:
        return False
    return rule == tool


def matching_rules(tool: str, files: dict[str, Path]) -> dict[str, list[str]]:
    out = {}
    for scope, p in files.items():
        perms = (_load(p).get("permissions") or {})
        allow = perms.get("allow") or []
        hits = [r for r in allow if isinstance(r, str) and rule_matches(r, tool)]
        if hits or p.exists():
            out[scope] = hits
    return out


def hook_decision(tool: str, tool_input: dict | None) -> dict[str, str | None]:
    """Run BOTH plugin hooks, the real scripts, with the real event shape."""
    event = {"tool_name": tool, "hook_event_name": "PreToolUse",
             "tool_input": tool_input or {}, "cwd": str(REPO)}
    out = {}
    for name in ("autoapprove_connector.py", "autoapprove_builtins.py"):
        r = subprocess.run([sys.executable, str(HOOKS / name)],
                           input=json.dumps(event), capture_output=True,
                           text=True, timeout=60)
        dec = None
        if r.returncode == 0 and r.stdout.strip():
            try:
                dec = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]
            except (ValueError, KeyError):
                dec = None
        out[name] = dec
    return out


def install_state() -> dict:
    home = Path(os.environ.get("HOME") or "/root")
    rec = _load(home / ".claude" / "plugins" / "installed_plugins.json")
    entries = (rec.get("plugins") or {}).get("dma-insights@zennify-dma") or []
    user_settings = _load(home / ".claude" / "settings.json")
    enabled = (user_settings.get("enabledPlugins") or {}).get("dma-insights@zennify-dma")
    return {"installed": [{"scope": e.get("scope"), "version": e.get("version")}
                          for e in entries if isinstance(e, dict)],
            "enabled_user_scope": enabled,
            "default_mode": (user_settings.get("permissions") or {}).get("defaultMode")}


def diagnose(tool: str, tool_input: dict | None = None,
             repo: Path | None = REPO) -> dict:
    hooks = hook_decision(tool, tool_input)
    rules = matching_rules(tool, settings_files(repo))
    inst = install_state()
    any_hook = any(v == "allow" for v in hooks.values())
    any_rule = any(rules.values())
    is_mcp = tool.startswith("mcp__")
    server = tool.split("__")[1] if is_mcp and tool.count("__") >= 2 else None
    findings: list[str] = []
    owner: list[str] = []

    if not any_hook:
        findings.append(
            f"neither plugin hook approves `{tool}` — with this name and input "
            f"the hook draws no decision, so the prompt is the hook's silence")
        if is_mcp:
            owner.append("the plugin: teach hooks/autoapprove_connector.py this "
                         "tool (read set, ENRICHMENT_TOOLS, or a verb it can read)")
        else:
            owner.append("the plugin: teach hooks/autoapprove_builtins.py this "
                         "command shape, or the manifest that asks for it")
    if not any_rule:
        findings.append(
            "no `permissions.allow` rule in user, project or project-local "
            "settings matches this exact name — a grant written for one "
            "server spelling (`mcp__Tavily__*`) does not match another "
            "(`mcp__claude_ai_Tavily__…`), and a rule saved by 'allow for all "
            "sessions' lands in `.claude/settings.local.json`, which a cloud "
            "container discards with the container")
        owner.append("bootstrap_session.sh (user scope, before session start) "
                     "and the repo's .claude/settings.json carry both spellings; "
                     "a session started from a snapshot must run the bootstrap")
    if not inst["installed"]:
        findings.append("the dma-insights plugin is NOT installed in this "
                        "container's user scope — no hook runs at all")
        owner.append("the environment: bootstrap_session.sh installs and "
                     "enables it before the session binds")
    elif inst["enabled_user_scope"] is not True:
        findings.append("the plugin is installed but not ENABLED at user scope, "
                        "so its hooks do not run")
        owner.append("`claude plugin enable dma-insights@zennify-dma`, or the "
                     "bootstrap, before session start")

    # The layer no code here can remove. Named whenever the hooks DO approve
    # and a rule DOES match — because then the prompt is coming from above.
    if any_hook and any_rule and is_mcp:
        findings.append(
            f"the hook approves `{tool}` and an allow rule matches it, so a "
            f"prompt that still appears is not decided by either. The one "
            f"control that overrides both, in every permission mode, is an "
            f"ORGANISATION per-tool setting of `ask` on the claude.ai "
            f"connector `{server}`: the prompt then carries the reason "
            f"“{ORG_ASK_REASON}”, offers no way to remember the choice, and "
            f"no allow rule skips it (permissions reference, 2026-09-04). "
            f"In `dontAsk` mode it becomes a silent denial instead. Run "
            f"`/mcp` in the prompting session: it shows which setting "
            f"applies to each tool on the connector.")
        owner.append("the organisation's claude.ai admin: connector tool "
                     "controls for the connector, `ask` → allow. The user's own "
                     "'allow unsupervised' connector setting does not override "
                     "an org `ask`")
    if is_mcp and server == "workspace":
        findings.append("this is a Cowork workspace tool: Cowork runs shell "
                        "through `mcp__workspace__bash`, and a `Bash` allow "
                        "rule never carries over to it; only the plugin's "
                        "builtins hook (matcher includes it since 1.17.0) "
                        "or an explicit `mcp__workspace__*` rule decides")
    if not findings:
        findings.append("every layer this tool can read approves it; if it "
                        "still prompts, the session is running a plugin "
                        "older than this checkout (hooks bind once, at start)")
        owner.append("`doctor.py --heal`, then a NEW session")

    return {"tool": tool, "hooks": hooks, "allow_rules_matching": rules,
            "install": inst, "findings": findings, "who_closes_it": owner,
            "surfaces": {
                "claude.ai/code web": "user + project settings, plugin hooks, "
                                      "then the auto classifier; the container "
                                      "is a snapshot, so only the bootstrap's "
                                      "writes survive to the next session",
                "Claude Code CLI": "the same layers on your own machine; a "
                                   "saved rule persists, but only for the "
                                   "spelling it was saved under",
                "Cowork desktop": "plugin hooks run; shell is "
                                  "`mcp__workspace__bash`; the org `ask` "
                                  "setting does NOT reach these sessions, so "
                                  "ordinary rules apply",
                "claude.ai chat": "no Claude Code hooks or settings at all — "
                                  "only the connector's own permission setting "
                                  "and any org control",
            }}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tool", help="the exact tool name the prompt showed, e.g. "
                                 "mcp__Tavily__tavily_search or Bash")
    ap.add_argument("--command", help="for Bash / mcp__workspace__bash: the command")
    ap.add_argument("--file-path", help="for Write/Edit: the target path")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    ti = {}
    if a.command:
        ti["command"] = a.command
    if a.file_path:
        ti["file_path"] = a.file_path
    out = diagnose(a.tool, ti)
    if a.json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"{a.tool}")
    for name, dec in out["hooks"].items():
        print(f"  hook {name:<28} {dec or 'no decision'}")
    for scope, hits in out["allow_rules_matching"].items():
        print(f"  allow rules ({scope:<13}) {', '.join(hits) if hits else 'none match'}")
    inst = out["install"]
    print(f"  plugin installed: {inst['installed'] or 'NO'}; enabled at user "
          f"scope: {inst['enabled_user_scope']}; defaultMode: {inst['default_mode']}")
    print("\nWhy it prompted:")
    for f in out["findings"]:
        print(f"  · {f}")
    print("\nWho closes it:")
    for o in out["who_closes_it"] or ["nothing left to close here"]:
        print(f"  → {o}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
