#!/usr/bin/env python3
"""PreToolUse on Bash / Write / Edit — approve the pipeline's OWN commands and
the run's OWN files, nothing else.

WHY THIS EXISTS (measured 2026-09-03, the headless-workflow audit, after the
owner's fifth report of approval prompts in a scheduled firing).

Every earlier fix in this directory ruled on MCP tools: the connector by
prefix, the enrichment connectors by suffix, the stable-segment servers by
exact name, WebSearch/WebFetch by name. `audit_autoapprove.py --strict`
passes: 124 of 184 MCP tools approved and every other one refused ON THE
RECORD. And the owner was still being asked to approve tool calls — because
the prompts were not MCP calls at all.

Every agent in this plugin does its work through `Bash`. The sixteen category
researchers, the four pillar scorers, the two report writers, the conductor,
the vetter: each one runs `python3 -m engine.<module> …` for every write it
makes, because the workbook's refusals ARE the write control. The producers
write section JSON to disk with `Write` so `ship_page.py` can submit it
without a byte passing through a model. None of those three tools had a
PreToolUse decision, none is in `permissions.allow`, and neither the
`default` nor the `auto` mode auto-approves an arbitrary shell command — so
every one fell through to a prompt, and a trigger-fired container has nobody
to answer it. The MCP surface was 100 percent ruled on and the workflow still
could not run headless.

WHAT IT APPROVES, and the reason each line is as narrow as it is:

  Bash   a command whose EVERY segment (split on `&&`, `||`, `;`, `|`, and
         newlines) is one of:
           * the research engine:      python3 -m engine.<module> …
           * a plugin script:          python3 <plugin>/scripts/*.py …
                                       python3 <plugin>/skills/*/scripts/*.py …
                                       python3 <plugin>/skills/*/engine/*.py …
           * a repo-root script:       python3 scripts/*.py …
           * the plugin's shell:       bash <plugin>/scripts/*.sh
           * pytest, the doctor's own checks, `claude -p --agent dma-insights:…`
           * a read-only shell verb: ls, find, grep, rg, sed -n, head, tail,
             wc, cut, sort, uniq, tr, jq, cat, stat, du, date, echo, printf,
             test, true, cd, mkdir -p, cp, mv, touch, diff, basename …
           * git, without a push: status, log, diff, show, fetch, checkout,
             branch, rev-parse, add, commit, stash, remote -v. `git push` is
             NOT here: the synthesis Routines are forbidden to push and the
             rectifier's push rides the harness's own credential path, so a
             push stays a decision a person (or the harness) makes.
           * inline python (`python3 -c`, `python3 - <<'PY'`) ONLY when the
             code names none of the process-, network- or filesystem-mutating
             modules in INLINE_BANNED — an interpreter is a shell, and this
             list is what keeps "python3 -c" from being a hole in the wall.
         Redirections (`>`, `>>`) are allowed only INTO a write root (below).
         Anything this parser cannot read — `eval`, `exec`, `sudo`, `xargs`,
         `source`, backgrounding with `&`, a pipe INTO an interpreter — draws
         NO decision and falls through exactly as before. So the blast radius
         of this file being wrong is "the routine still asks", never "the
         routine did something nobody sanctioned".

  Write / Edit / MultiEdit / NotebookEdit
         a target under one of the WRITE ROOTS: the run root
         (`$DMA_RUN_ROOT`, `/home/claude/dma_output`, `~/dma_output`),
         `/root/.dma` (packages, bundles, ledgers, agent logs), the scratch
         dirs, and — inside the repository — ONLY the plugin tree, `fixtures/`,
         `scripts/`, `tests/` and `docs/`: the rectifier's writer scope. The
         deployables (`apps/`, `infra/`, `migrations/`, `packages/`) and every
         settings or credential file (`.claude/`, `sa.json`, `pathtok`,
         `slack_token`, `.env`) draw no decision from here, ever.

THE DENY HOOKS STILL WIN. `deny_credential_ops.py` and `deny_bulk_read.py`
run beside this one and the harness resolves deny over allow — but this file
does not lean on that: it imports both and asks them FIRST, and says nothing
when either would refuse. Two hooks with opposite opinions on one call is a
resolution order nobody should have to bet a firing on.

FAIL-OPEN AND SILENT. Unreadable input, a tool this file does not know, a
command it cannot parse: no output, no decision, exit 0. The hook must never
crash and must never deny — denial is the two guards' job.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:                                               # the two guards, asked first
    import deny_bulk_read as _bulk                 # noqa: E402
    import deny_credential_ops as _cred            # noqa: E402
except Exception:                                  # noqa: BLE001
    _bulk = _cred = None

EDIT_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

# ── where a run may write ────────────────────────────────────────────────


def _repo_root() -> Path | None:
    """The checkout this plugin lives in, when it runs from one.

    `<repo>/plugins/dma-insights/scripts/hooks/<this>` → four up. From an
    installed plugin cache there is no repo above it, so the repository
    write roots are derived from CLAUDE_PROJECT_DIR / cwd instead."""
    p = HERE.parents[3] if len(HERE.parents) > 3 else None
    if p and (p / "plugins" / "dma-insights").is_dir():
        return p
    for env in ("CLAUDE_PROJECT_DIR",):
        v = os.environ.get(env)
        if v and (Path(v) / "plugins" / "dma-insights").is_dir():
            return Path(v)
    cwd = Path(os.getcwd())
    for c in (cwd, *cwd.parents):
        if (c / "plugins" / "dma-insights").is_dir():
            return c
    return None


#: Repository subtrees a routine may write. The rectifier edits the plugin
#: tree and its tests; the synthesis lanes write the two learning ledgers in
#: fixtures/ (subcap_match.py learn, source_yield.py log) — through python,
#: but the Write tool is the same boundary. The deployables are not here.
REPO_WRITABLE = ("plugins/dma-insights", "fixtures", "scripts", "tests",
                 "docs", ".qa")

#: Files that carry a credential or the session's own permission posture.
#: Never approved from here whatever root they sit under.
NEVER_WRITE = re.compile(
    r"(^|/)(\.claude(\.json)?|settings(\.local)?\.json|sa\.json|pathtok|"
    r"slack_token|\.env[^/]*|id_rsa[^/]*|\.netrc|\.git/config)(/|$)")


def write_roots() -> list[Path]:
    roots = []
    for env in ("DMA_RUN_ROOT", "DMA_ARTIFACT_ROOT", "DMA_BUNDLE_CACHE",
                "TMPDIR", "CLAUDE_SCRATCHPAD_DIR"):
        v = os.environ.get(env)
        if v:
            roots.append(Path(v))
    roots += [Path("/home/claude/dma_output"), Path("/root/.dma"),
              Path.home() / "dma_output", Path("/tmp")]
    repo = _repo_root()
    if repo:
        roots += [repo / sub for sub in REPO_WRITABLE]
    return roots


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def path_is_writable(raw: str) -> bool:
    if not isinstance(raw, str) or not raw.strip():
        return False
    p = Path(os.path.expanduser(raw.strip()))
    if not p.is_absolute():
        p = Path(os.getcwd()) / p
    if NEVER_WRITE.search(str(p)):
        return False
    return any(_under(p, r) for r in write_roots())


# ── the shell grammar ────────────────────────────────────────────────────

#: Verbs that only read, print, or move within the tree. `awk` is absent on
#: purpose (it has system()); so are `env`/`printenv`/`set` (they print the
#: environment, where the service-account key lives) and `curl` (a fetch is a
#: fetch, but `| bash` is a supply chain, and the connector already speaks
#: over mcp_raw.py).
READ_VERBS = frozenset({
    "ls", "find", "grep", "egrep", "fgrep", "rg", "sed", "head", "tail",
    "wc", "cut", "sort", "uniq", "tr", "jq", "cat", "stat", "du", "df",
    "date", "echo", "printf", "test", "[", "true", "false", "cd", "pwd",
    "mkdir", "cp", "mv", "touch", "diff", "cmp", "basename", "dirname",
    "realpath", "readlink", "which", "command", "type", "file", "md5sum",
    "sha256sum", "tee", "column", "nl", "tac", "rev", "paste", "comm",
    "unzip", "zipinfo", "tar", "gzip", "gunzip", "sleep", "timeout",
    "python3", "python", "bash", "sh", "git", "pytest", "claude", "export",
    "unset", "rm",
})

#: Git subcommands that read, or write only the LOCAL clone. No push.
GIT_OK = frozenset({
    "status", "log", "diff", "show", "fetch", "checkout", "switch", "branch",
    "rev-parse", "remote", "add", "commit", "stash", "restore", "ls-files",
    "describe", "tag", "blame", "grep", "config", "merge-base", "reset",
    "clone", "pull", "worktree",
})

#: Tokens that make an inline python program a shell in disguise. Any one of
#: them and the program draws no decision.
INLINE_BANNED = re.compile(
    r"\b(subprocess|os\.system|os\.popen|os\.exec\w*|os\.spawn\w*|os\.remove|"
    r"os\.unlink|os\.rmdir|os\.rename|shutil|socket|http\.client|urllib|"
    r"requests|httpx|aiohttp|ftplib|smtplib|pty|ctypes|importlib|__import__|"
    r"eval|exec|compile|open\([^)]*['\"][wax]|pathlib[^\n]*write_|"
    r"\.write_text|\.write_bytes|\.unlink\(|\.rmdir\(|rmtree|chmod|chown|"
    r"setattr|globals\(\)|builtins)\b")

#: Words this parser will not reason about, wherever they appear as a token
#: (a verb, an argument to `timeout`, a `find -exec`). Their presence means
#: no decision — not a deny. A quoted excerpt that merely CONTAINS one of
#: these words is a single token and does not match.
BLOCKED_TOKENS = frozenset({
    "eval", "exec", "sudo", "su", "xargs", "source", ".", "nohup", "setsid",
    "watch", "screen", "tmux", "ssh", "scp", "rsync", "nc", "ncat", "telnet",
    "wget", "curl", "pip", "pip3", "npm", "npx", "node", "gcloud", "gsutil",
    "docker", "kubectl", "crontab", "chmod", "chown", "dd", "mkfs", "shred",
    "killall", "pkill", "kill", "reboot", "shutdown", "apt", "apt-get", "yum",
    "brew", "awk", "gawk", "perl", "ruby", "php", "env", "printenv", "set",
    "-exec", "-execdir", "-delete", "-ok",
})

#: The plugin's own tree, in every spelling a prompt uses for it.
PLUGIN_PATH = re.compile(
    r"^(?:\$\{?CLAUDE_PLUGIN_ROOT\}?|\$PLUGIN|"
    r"(?:/[^\s]*/)?plugins/dma-insights|"
    r"/[^\s]*/\.claude/plugins/[^\s]*dma-insights[^\s]*)"
    r"/(scripts/[A-Za-z0-9_.-]+\.(?:py|sh)|"
    r"skills/[A-Za-z0-9_-]+/(?:scripts|engine)/[A-Za-z0-9_./-]+\.py)$")
REPO_SCRIPT = re.compile(r"^(?:\./|/[^\s]*/)?scripts/[A-Za-z0-9_.-]+\.py$")
ENGINE_MOD = re.compile(r"^engine(\.[A-Za-z_][A-Za-z0-9_]*)+$")


#: Files that hold a credential or the session's permission posture. A
#: command that so much as NAMES one draws no decision — reading a key with
#: `cat` or `open()` is not a read this hook will ever wave through.
SECRET_PATHS = re.compile(
    r"sa\.json|pathtok|slack_token|/\.claude(\.json|/)|\.netrc|id_rsa|"
    r"\.env\b|/etc/(passwd|shadow|sudoers)", re.I)

_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[ \t]*\n")


def _lift_heredocs(command: str) -> tuple[str, list[str]] | None:
    """Replace each `<<'TAG' … TAG` body with a placeholder token and return
    the bodies, so the splitter never sees a body's semicolons or pipes as
    shell. None when a heredoc has no terminator."""
    bodies: list[str] = []
    out, i = [], 0
    while True:
        m = _HEREDOC.search(command, i)
        if not m:
            out.append(command[i:])
            break
        tag = m.group(2)
        end = re.compile(rf"^[ \t]*{re.escape(tag)}[ \t]*$", re.M)
        e = end.search(command, m.end())
        if not e:
            return None
        bodies.append(command[m.end():e.start()])
        out.append(command[i:m.start()] + f" __HEREDOC_{len(bodies) - 1}__")
        i = e.end()
    return "".join(out), bodies


def _split_segments(command: str) -> tuple[list[str], list[str]] | None:
    """(segments, heredoc bodies), or None when the command has a construct
    the grammar does not reason about.

    Quote-aware: a `;` or `|` INSIDE a quoted argument is data, and the
    engine's own `--excerpt "…; …"` and `--rationale "[EVIDENCE] …; …"` are
    exactly that shape. `$(…)` substitutions are lifted OUT and checked as
    their own segments — `W=$(python3 -m engine.cli …)` is a shape the
    conductor's own manifest uses."""
    lifted = _lift_heredocs(command)
    if lifted is None:
        return None
    flat, bodies = lifted
    segs: list[str] = []

    def _lift_subst(s: str) -> str | None:
        out, i = [], 0
        while True:
            j = s.find("$(", i)
            if j < 0:
                out.append(s[i:])
                break
            out.append(s[i:j])
            depth, k = 0, j + 1
            while k < len(s):
                if s[k] == "(":
                    depth += 1
                elif s[k] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            if k >= len(s):
                return None
            inner = s[j + 2:k]
            if "$(" in inner:
                return None
            segs.append(inner)
            out.append("__SUBST__")
            i = k + 1
        return "".join(out)

    flat = _lift_subst(flat)
    if flat is None:
        return None
    # Quote-aware split on the list/pipe operators, one shell line at a time.
    # `&` is deliberately NOT a punctuation char: `2>&1` and `&>` are
    # redirections the grammar reads, so `&&` and a bare `&` are recognised
    # as whole tokens below instead.
    try:
        lex = shlex.shlex(flat, posix=True, punctuation_chars=";|")
        lex.whitespace_split = True
        lex.commenters = ""
        tokens = list(lex)
    except ValueError:
        return None
    cur: list[str] = []
    for tok in tokens:
        if tok in (";", "|", "||", "&&"):
            if cur:
                segs.append(shlex.join(cur))
                cur = []
            continue
        if tok in (";;", "|&", "&") or (
                tok.endswith("&") and not tok.endswith("&&")
                and not re.search(r"\d?>&$", tok)):
            return None                      # backgrounding, case, stderr pipe
        if "`" in tok or "$((" in tok or tok.startswith(("<(", ">(")):
            return None                      # substitutions the grammar skips
        if tok in BLOCKED_TOKENS:
            return None
        cur.append(tok)
    if cur:
        segs.append(shlex.join(cur))
    return segs, bodies


def _strip_heredoc(segment: str, bodies: list[str]) -> tuple[str, str]:
    """(command line, heredoc body) — the body was lifted by the splitter and
    rides here as a placeholder token."""
    m = re.search(r"__HEREDOC_(\d+)__", segment)
    if not m:
        return segment, ""
    idx = int(m.group(1))
    body = bodies[idx] if idx < len(bodies) else ""
    return segment.replace(m.group(0), "").strip(), body


def _redirect_targets(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Split `> file` / `>> file` / `2> file` out of a token list.
    `2>&1`, `>/dev/null` and `1>&2` are not writes."""
    keep, targets = [], []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        m = re.match(r"^(\d?>>?|&>)(.*)$", t)
        if m and not re.match(r"^\d?>&\d$", t):
            target = m.group(2)
            if not target:
                i += 1
                target = tokens[i] if i < len(tokens) else ""
            if target and target != "/dev/null" and not target.startswith("&"):
                targets.append(target)
            i += 1
            continue
        if t in ("<", "<<", "<<<") and i + 1 < len(tokens):
            i += 2
            continue
        keep.append(t)
        i += 1
    return keep, targets


def _drop_env_prefix(tokens: list[str]) -> list[str]:
    while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
        tokens = tokens[1:]
    return tokens


def _python_ok(argv: list[str], heredoc: str) -> bool:
    """`python3 …`: the engine, a plugin or repo script, pytest, or inline
    code that names nothing in INLINE_BANNED."""
    args = argv[1:]
    if not args:
        return False
    if args[0] == "-m":
        if len(args) < 2:
            return False
        mod = args[1]
        return bool(ENGINE_MOD.match(mod)) or mod in ("pytest", "json.tool")
    if args[0] == "-c":
        code = " ".join(args[1:])
        return bool(code.strip()) and not INLINE_BANNED.search(code)
    if args[0] == "-":
        return bool(heredoc.strip()) and not INLINE_BANNED.search(heredoc)
    if args[0].startswith("-"):
        # -u, -B, -W … then the script
        rest = [a for a in args if not a.startswith("-")]
        return bool(rest) and _script_ok(rest[0])
    return _script_ok(args[0])


#: The directories a script may be run from, resolved on disk. The regexes
#: above are the fast path for the spellings prompts use; this is for a
#: RELATIVE path (`python ../../scripts/inspect_client_folders.py` from a
#: skill directory, `python scripts/ship_page.py` from the surface-production
#: skill) that the regexes cannot see the target of. Resolved against the
#: event's cwd, then checked against the same roots.
_CWD = os.getcwd()


def _script_roots() -> list[Path]:
    roots = [PLUGIN_DIR / "scripts"]
    skills = PLUGIN_DIR / "skills"
    if skills.is_dir():
        for s in skills.iterdir():
            roots += [s / "scripts", s / "engine"]
    repo = _repo_root()
    if repo:
        roots.append(repo / "scripts")
    return roots


PLUGIN_DIR = HERE.parents[1]


def _script_ok(path: str) -> bool:
    if PLUGIN_PATH.match(path) or REPO_SCRIPT.match(path):
        return True
    if not path.endswith(".py") or "$" in path:
        return False
    p = Path(os.path.expanduser(path))
    if not p.is_absolute():
        p = Path(_CWD) / p
    try:
        rp = p.resolve()
    except OSError:
        return False
    return rp.is_file() and any(_under(rp, r) for r in _script_roots())


def _segment_ok(segment: str, bodies: list[str]) -> bool:
    line, heredoc = _strip_heredoc(segment, bodies)
    if SECRET_PATHS.search(line) or SECRET_PATHS.search(heredoc):
        return False
    line = line.replace("__SUBST__", "SUBST")
    try:
        tokens = shlex.split(line, posix=True)
    except ValueError:
        return False
    tokens, targets = _redirect_targets(tokens)
    for t in targets:
        if not path_is_writable(t.replace("SUBST", "")):
            return False
    tokens = _drop_env_prefix(tokens)
    if not tokens:
        return True                                 # a bare assignment
    # `timeout 600 cmd …` — check the wrapped command
    if tokens[0] == "timeout" and len(tokens) > 2:
        tokens = tokens[2:]
        tokens = _drop_env_prefix(tokens)
    verb = tokens[0]
    if verb not in READ_VERBS:
        return False
    if verb in ("python3", "python"):
        return _python_ok(tokens, heredoc)
    if verb in ("bash", "sh"):
        rest = [a for a in tokens[1:] if not a.startswith("-")]
        return bool(rest) and bool(PLUGIN_PATH.match(rest[0])) \
            and rest[0].endswith(".sh")
    if verb == "git":
        sub = next((a for a in tokens[1:] if not a.startswith("-")), "")
        return sub in GIT_OK
    if verb == "claude":
        return "-p" in tokens and any(a.startswith("dma-insights:")
                                      for a in tokens)
    if verb == "rm":
        # only inside a write root, never recursive-force on a root itself
        paths = [a for a in tokens[1:] if not a.startswith("-")]
        return bool(paths) and all(path_is_writable(p) and
                                   Path(p).name not in ("", ".", "..", "*")
                                   for p in paths)
    if verb in ("cp", "mv", "tee", "touch", "mkdir"):
        # the destination (last non-flag arg) must be writable; a read from
        # anywhere is fine
        paths = [a for a in tokens[1:] if not a.startswith("-")]
        if not paths:
            return False
        dests = paths[-1:] if verb in ("cp", "mv") else paths
        return all(path_is_writable(d) for d in dests)
    if verb == "sed":
        # in-place editing is a write; require a writable target
        if any(a.startswith("-i") for a in tokens[1:]):
            files = [a for a in tokens[2:] if not a.startswith("-")][1:]
            return bool(files) and all(path_is_writable(f) for f in files)
        return True
    if verb == "cd":
        return True
    return True


def bash_ok(command: str) -> bool:
    if not isinstance(command, str) or not command.strip():
        return False
    split = _split_segments(command)
    if split is None:
        return False
    segs, bodies = split
    return bool(segs) and all(_segment_ok(s, bodies) for s in segs)


# ── the two guards, asked first ──────────────────────────────────────────

def guards_would_deny(command: str) -> bool:
    try:
        if _cred is not None and any(rx.search(command) for rx, _ in _cred.DENIALS):
            return True
        if _bulk is not None and _bulk.decide(command):
            return True
    except Exception:                               # noqa: BLE001
        return True                                 # unsure → say nothing
    return False


BASH_REASON = (
    "dma-insights pipeline command, auto-approved by the plugin's own hook: "
    "every segment is the research engine, a plugin or repo script, pytest, "
    "a local git operation or a read-only shell verb, and any redirection "
    "lands inside a run root. The credential and bulk-read guards were asked "
    "first and did not object. A scheduled session has nobody to answer a "
    "prompt, and every agent in this plugin writes through these commands.")
EDIT_REASON = (
    "write inside a DMA run root or the plugin's own writer scope, "
    "auto-approved by the dma-insights hook: producers write section JSON to "
    "disk so ship_page.py can submit it without a byte passing through a "
    "model, and a scheduled session has nobody to answer a prompt. Settings, "
    "credentials and the deployables are never approved from here.")


def decide(event: dict) -> dict | None:
    global _CWD
    tool = event.get("tool_name")
    ti = event.get("tool_input") or {}
    if not isinstance(ti, dict):
        return None
    cwd = event.get("cwd")
    if isinstance(cwd, str) and cwd:
        _CWD = cwd
    if tool == "Bash":
        cmd = ti.get("command")
        if not isinstance(cmd, str) or guards_would_deny(cmd) or not bash_ok(cmd):
            return None
        return _allow(BASH_REASON)
    if tool in EDIT_TOOLS:
        path = ti.get("file_path") or ti.get("notebook_path") or ""
        if path_is_writable(path):
            return _allow(EDIT_REASON)
        return None
    return None


def _allow(reason: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": reason,
    }}


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:                               # noqa: BLE001
        return 0
    if not isinstance(event, dict):
        return 0
    out = decide(event)
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                               # noqa: BLE001
        sys.exit(0)                                 # never crash, never deny
