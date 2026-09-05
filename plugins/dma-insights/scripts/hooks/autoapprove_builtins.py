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
         unquoted newlines) is one of:
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
           * git, without a push and without a configuration that runs a
             command: status, log, diff, show, fetch, checkout, branch,
             rev-parse, add, commit, stash, remote -v, `config --get`.
             `git push` is NOT here: the synthesis Routines are forbidden
             to push and the rectifier's push rides the harness's own
             credential path, so a push stays a decision a person (or the
             harness) makes. Neither is `git config <key> <value>` beyond
             `user.*`: sshCommand, pager, fsmonitor, hooksPath and alias
             each run a program on the next innocent-looking git call.
           * inline python (`python3 -c`, `python3 - <<'PY'`) ONLY when
             every module it imports is in INLINE_MODULES (json, re, csv,
             datetime, openpyxl …) and the code names nothing in
             INLINE_BANNED — an interpreter is a shell, and an allow-list
             of modules is what keeps "python3 -c" from being a hole in the
             wall. `import os as o` is refused by the import, not by a
             regex that has to guess the alias.
         Redirections (`>`, `>>`) are allowed only INTO a write root (below).
         Anything this parser cannot read — `eval`, `exec`, `sudo`, `xargs`,
         `source`, backgrounding with `&`, a pipe INTO an interpreter, an
         unresolved `$VAR` or `$(…)` inside a path — draws NO decision and
         falls through exactly as before. So the blast radius of this file
         being wrong is "the routine still asks", never "the routine did
         something nobody sanctioned".

  Write / Edit / MultiEdit / NotebookEdit
         a target under one of the WRITE ROOTS: the run root
         (`$DMA_RUN_ROOT`, `/home/claude/dma_output`, `~/dma_output`),
         `/root/.dma` (packages, bundles, ledgers, agent logs), the scratch
         dirs, and — inside the repository — ONLY the plugin tree, `fixtures/`,
         `scripts/`, `tests/` and `docs/`: the rectifier's writer scope. The
         deployables (`apps/`, `infra/`, `migrations/`, `packages/`), every
         settings or credential file (`.claude/`, `sa.json`, `pathtok`,
         `slack_token`, `.env`) and the plugin's own trust boundary
         (`.mcp.json`, `hooks/hooks.json`) draw no decision from here, ever.

THE SECRET LEVEL. The service-account key and the connector path token live
at the TOP of `/root/.dma`, beside the run roots the agents legitimately read
underneath it. So the top level of that directory — and of `~/.claude`, and
the ancestors `/root`, `/home`, `/etc`, `/` — is a level no shell verb here
may name: not by its literal path, not through a glob whose literal prefix
lands there (`/root/.dma/*.json`), not through `..` (`/root/.dma/runs/..`),
not through a variable or a `$(…)` assembled inside a path, and not by
archiving or recursing the directory itself. Deeper paths
(`/root/.dma/runs/R/07_qa/*.json`) are the pipeline's and stay approved.

THE DENY HOOKS STILL WIN. `deny_credential_ops.py` and `deny_bulk_read.py`
run beside this one and the harness resolves deny over allow — but this file
does not lean on that: it imports both and asks them FIRST, and says nothing
when either would refuse. Two hooks with opposite opinions on one call is a
resolution order nobody should have to bet a firing on.

FAIL-OPEN AND SILENT. Unreadable input, a tool this file does not know, a
command it cannot parse: no output, no decision, exit 0. The hook must never
crash and must never deny — denial is the two guards' job.

STRESSED, NOT ASSUMED. `tests/test_autoapprove_adversarial.py` holds the
corpus that found the first version of this file approving 58 shapes it
should not have (2026-09-04): newline-smuggled second commands, globs and
variables reaching the key directory, `git config core.sshCommand`, `import
os as o`, `rm -rf` on a write root itself, a write to `.mcp.json`. Every
one of them is refused now and the corpus is the regression gate.
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
PLUGIN_DIR = HERE.parents[1]

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
    cwd = Path(_CWD)
    for c in (cwd, *cwd.parents):
        if (c / "plugins" / "dma-insights").is_dir():
            return c
    return None


#: Repository subtrees a routine may write. The rectifier edits the plugin
#: tree and its tests; the synthesis lanes write the two learning ledgers in
#: fixtures/ (subcap_match.py learn, source_yield.py log) — through python,
#: but the Write tool is the same boundary. The deployables are not here.
#: `docs/` is ABSENT on purpose: the charter calls the six design docs
#: read-only, and `plugins/dma-insights/docs` (the plugin's own notes, which
#: the rectifier does write) is reached through the plugin entry above.
REPO_WRITABLE = ("plugins/dma-insights", "fixtures", "scripts", "tests",
                 ".qa")

#: Files that carry a credential, the session's own permission posture, or
#: the plugin's trust boundary (its MCP server URL and its hooks). Never
#: approved from here whatever root they sit under.
NEVER_WRITE = re.compile(
    r"(^|/)(\.claude(\.json)?|settings(\.local)?\.json|sa\.json|pathtok|"
    r"slack_token|\.env[^/]*|id_rsa[^/]*|\.netrc|\.git/config|\.mcp\.json|"
    r"hooks/hooks\.json)(/|$)"
    # The guards themselves. A hook that approves a rewrite of the hooks
    # that judge the next call has approved everything exactly once.
    r"|(^|/)scripts/hooks/[^/]+\.py$")

#: The event's cwd — the harness sends it; relative paths resolve against it.
_CWD = os.getcwd()


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


def _under(path: Path, root: Path, strict: bool = False) -> bool:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return not (strict and str(rel) == ".")


def _abs(raw: str) -> Path:
    p = Path(os.path.expanduser(raw.strip()))
    if not p.is_absolute():
        p = Path(_CWD) / p
    return p


def path_is_writable(raw: str, strict: bool = False,
                     cwd: str | None = None) -> bool:
    """`strict` — the path must lie INSIDE a root, never be the root itself
    (an `rm -rf` on `/root/.dma` is not a write into it)."""
    if not isinstance(raw, str) or not raw.strip():
        return False
    if "$" in raw or "__SUBST__" in raw:
        return False                        # an unresolved name is no path
    p = Path(os.path.expanduser(raw.strip()))
    if not p.is_absolute():
        p = Path(cwd or _CWD) / p
    if NEVER_WRITE.search(str(p)):
        return False
    try:
        if NEVER_WRITE.search(str(p.resolve())):
            return False
    except OSError:
        return False
    return any(_under(p, r, strict) for r in write_roots())


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
    # tar / gzip / gunzip / unzip are ABSENT: `tar --to-command` runs a
    # program, `-C` writes anywhere, `gzip <file>` replaces its argument in
    # place, `unzip -d` chooses its own destination. Each was approved on
    # 2026-09-04 because the verb "only reads".
    "zipinfo", "sleep", "timeout",
    "python3", "python", "bash", "sh", "git", "pytest", "claude", "export",
    "unset", "rm",
})

#: Verbs whose arguments are not file paths the SHELL opens, so an
#: unresolved `$VAR` or a lifted `$(…)` among them is data, not a path this
#: grammar failed to see. Every other verb refuses such a token.
#: `echo` and `printf` are ABSENT: an unresolved `$VAR` among their
#: arguments prints the environment the service-account key lives in — the
#: exposure `env` / `printenv` are blocked for (`echo "$SA_KEY" > /tmp/k`
#: was approved, 2026-09-04). A literal `echo '{"probe": 1}'` still passes,
#: because it carries no `$`.
VAR_TOLERANT = frozenset({
    "test", "[", "true", "false", "cd", "export", "unset",
    "date", "sleep", "python3", "python", "git", "claude", "pytest", "bash",
    "sh", "mkdir", "basename", "dirname", "which", "command", "type",
})

#: Git subcommands that read, or write only the LOCAL clone. No push.
GIT_OK = frozenset({
    "status", "log", "diff", "show", "fetch", "checkout", "switch", "branch",
    "rev-parse", "remote", "add", "commit", "stash", "restore", "ls-files",
    "describe", "tag", "blame", "grep", "config", "merge-base", "reset",
    "clone", "pull", "worktree",
})

#: A git token that makes the NEXT git call run a program, or reaches a
#: credential. Any one of them and the segment draws no decision.
GIT_BAD = re.compile(
    r"^(-c|--config(-env)?|-C)$|^--config=|sshCommand|core\.pager|"
    r"core\.fsmonitor|core\.editor|core\.hooksPath|hooksPath|^alias\.|"
    r"--upload-pack|--receive-pack|--exec|credential|sequence\.editor|"
    r"diff\.external|\.textconv|filter\..*\.(clean|smudge)|^!|"
    r"url\..*insteadof|http\.proxy|core\.askpass|GIT_SSH", re.I)

#: `git config` forms that only read. A set is allowed for `user.*` alone.
GIT_CONFIG_READ = frozenset({"--get", "--get-all", "--get-regexp", "--list",
                             "-l", "--show-origin", "--show-scope"})

#: Modules inline python may import. Anything else — os, subprocess, shutil,
#: socket, glob, importlib, ctypes … — and the program draws no decision.
INLINE_MODULES = frozenset({
    "json", "re", "sys", "math", "csv", "datetime", "collections",
    "itertools", "functools", "statistics", "textwrap", "string", "decimal",
    "fractions", "hashlib", "pathlib", "typing", "dataclasses", "enum",
    "copy", "operator", "pprint", "time", "uuid", "random", "io", "base64",
    "difflib", "unicodedata", "html", "argparse", "heapq", "bisect",
    "openpyxl", "docx", "pypdf",
})

#: Tokens that make an inline python program a shell in disguise, whatever
#: it imported. Any one of them and the program draws no decision.
INLINE_BANNED = re.compile(
    r"\b(subprocess|os\.system|os\.popen|os\.exec\w*|os\.spawn\w*|os\.remove|"
    r"os\.unlink|os\.rmdir|os\.rename|shutil|socket|http\.client|urllib|"
    r"requests|httpx|aiohttp|ftplib|smtplib|pty|ctypes|importlib|__import__|"
    r"eval|exec|compile|rmtree|chmod|chown|setattr|getattr|builtins|"
    r"__dict__|__class__|__subclasses__|sys\.modules|sys\.path|environ)\b"
    r"|open\([^)]*['\"][wax]"           # open(…, 'w'|'a'|'x')
    r"|open\(\s*[^'\"\s)]"              # open(<not a literal>) — a built path
    r"|\.write_(text|bytes)\(|\.unlink\(|\.rmdir\(|\.save\(|\.touch\(|"
    r"\.mkdir\(|\.rename\(|\.replace\(|globals\(|vars\(|locals\(")

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

#: A blocked word that is a SCRIPT'S OWN SUBCOMMAND, not a verb.
#:
#: Measured 2026-09-04: `agent_run.py watch --log-dir …` — the live-status
#: table the conductor and the run-assessment command both tell a session to
#: open — drew no decision, because `watch` is banned wherever it appears
#: (`watch(1)` re-runs a command forever). Immediately after a `.py` path it
#: cannot be that: the executable is python, the script is resolved on disk by
#: `_script_ok`, and this token is an argument python hands it. Kept to that
#: one shape — the token directly after a `.py` — so `timeout 5 watch ls`
#: still draws no decision.
_SUBCOMMANDABLE = frozenset({"watch", "set", "env"})


def _subcommand_of_a_script(tok: str, cur: list) -> bool:
    return (tok in _SUBCOMMANDABLE and bool(cur)
            and cur[-1].endswith(".py"))


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
    r"sa\.json|pathtok|slack_token|/\.claude(\.json|/(?!plugins/)|$)|"
    r"\.netrc|id_rsa|\.env\b|/etc/(passwd|shadow|sudoers)", re.I)

#: Inline python naming the TOP of the key directory — `'/root/.dma/' +
#: 'sa.json'`, `'/root/.dma/x.json'` — as opposed to a run root beneath it.
INLINE_SECRET_LEVEL = re.compile(r"/root/\.dma(?!/[\w.-]+/)")

#: The sed sentences this grammar reads: line addresses with `p`/`d`, and
#: `s///` with printing flags. `w`/`W` write a file, `e` EXECUTES the
#: pattern space, `r`/`R` read one in — all four were approved while sed sat
#: in READ_VERBS (`sed -n 's/.*/git push/e' README.md`, 2026-09-04).
_SED_OK = re.compile(
    r"^(?:\s*(?:[0-9]+|\$|/(?:\\.|[^/])*/|\d+,\d+|\d+,\$)?\s*"
    r"(?:[pdq=]|s(.)(?:\\.|(?!\1).)*\1(?:\\.|(?!\1).)*\1[gipIm0-9]*)"
    r"\s*;?\s*)+$")


def _sed_ok(tokens: list[str], cwd: str) -> bool:
    args = tokens[1:]
    inplace = [a for a in args if a == "--in-place" or a.startswith("--in-place=")
               or (a.startswith("-") and not a.startswith("--") and "i" in a[1:])]
    scripts, files, i = [], [], 0
    while i < len(args):
        a = args[i]
        if a in ("-e", "--expression", "-f", "--file"):
            if a in ("-f", "--file"):
                return False                 # a script this grammar cannot see
            i += 1
            if i < len(args):
                scripts.append(args[i])
        elif a.startswith("--expression="):
            scripts.append(a.split("=", 1)[1])
        elif a.startswith("-"):
            pass
        elif not scripts:
            scripts.append(a)
        else:
            files.append(a)
        i += 1
    if not scripts or not all(_SED_OK.match(x) for x in scripts):
        return False
    if inplace:
        return bool(files) and all(path_is_writable(f, cwd=cwd) for f in files)
    return True


#: Environment names a command may reference and this grammar will resolve.
#: Anything else stays a `$` and is refused where a path is expected.
SAFE_ENV = ("HOME", "DMA_RUN_ROOT", "DMA_ARTIFACT_ROOT", "DMA_BUNDLE_CACHE",
            "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR", "TMPDIR", "PWD")

_GLOB = frozenset("*?[{")
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _secret_dirs() -> set[str]:
    """The levels a shell verb may not name: the key directory, the settings
    directories, and their ancestors. The repository root is NOT here — its
    `.claude/` is, and NEVER_WRITE / SECRET_PATHS cover the file itself."""
    home = str(Path.home())
    dirs = {"/", "/root", "/home", "/etc", "/root/.dma", "/root/.claude",
            home, os.path.join(home, ".dma"), os.path.join(home, ".claude")}
    repo = _repo_root()
    if repo:
        dirs.add(str(repo / ".claude"))
    return dirs


def _reaches_secret_level(tok: str, cwd: str) -> bool:
    """A token that names the secret level itself: the directory, an
    ancestor of it, or a glob / `..` whose literal part lands there. A
    relative token resolves against the cwd the command has `cd`-ed to."""
    if not tok or tok.startswith("-"):
        return False
    t = os.path.expanduser(tok)
    has_glob = any(c in _GLOB for c in t)
    if not t.startswith("/"):
        t = os.path.join(cwd, t)             # `cd /root; grep -r x .dma`
    dirs = _secret_dirs()
    if has_glob:
        i = min(t.index(c) for c in _GLOB if c in t)
        lit = t[:i]
        if not lit or "/" not in lit:
            return False                    # `[EVIDENCE] …`, `*.xlsx`
        d = lit if lit.endswith("/") else os.path.dirname(lit)
        return os.path.normpath(d) in dirs
    return os.path.normpath(t) in dirs


def _expand(tok: str, assigns: dict) -> str:
    def sub(m):
        name = m.group(1) or m.group(2)
        if name in assigns:
            return assigns[name]
        if name in SAFE_ENV and os.environ.get(name):
            return os.environ[name]
        return m.group(0)
    return _VAR.sub(sub, tok)


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


def _newlines_are_separators(s: str) -> str | None:
    """An unquoted newline ends a command as surely as `;` — `ls\\ngit push`
    is two commands. Quoted newlines are data. A backslash-newline
    continuation is whitespace."""
    out, q, i = [], None, 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s) and q != "'":
            if s[i + 1] == "\n":
                out.append(" ")
            else:
                out.append(s[i:i + 2])
            i += 2
            continue
        if q:
            if c == q:
                q = None
            out.append(c)
        elif c in ("'", '"'):
            q = c
            out.append(c)
        elif c == "\n":
            out.append(" ; ")
        elif c == "&":
            # `&` is not in shlex's punctuation_chars (so `2>&1` survives as
            # one token), which means an UNSPACED `x&&git push` was absorbed
            # into the previous argument and the second command was never
            # read. Measured 2026-09-04: `echo x&&git push` was approved.
            # Redirections keep their `&`; everything else is an operator.
            prev = "".join(out).rstrip()
            if prev.endswith(">") or re.search(r"\d?>$", prev):
                out.append(c)                # 2>&1, &>, 1>&2
            elif s[i:i + 2] == "&&":
                out.append(" ; ")
                i += 1
            elif s[i:i + 2] == "&>":
                out.append(c)                # &> file
            else:
                return None                  # backgrounding, or `a &b`
        else:
            out.append(c)
        i += 1
    if q:
        return None                          # unterminated quote
    return "".join(out)


def _split_segments(command: str) -> tuple[list[str], list[str]] | None:
    """(segments, heredoc bodies), or None when the command has a construct
    the grammar does not reason about.

    Quote-aware: a `;` or `|` INSIDE a quoted argument is data, and the
    engine's own `--excerpt "…; …"` and `--rationale "[EVIDENCE] …; …"` are
    exactly that shape. `$(…)` substitutions are lifted OUT and checked as
    their own segments — `W=$(python3 -m engine.cli …)` is a shape the
    conductor's own manifest uses — and the place they were lifted from
    carries a `__SUBST__` marker so a path built around one is refused."""
    lifted = _lift_heredocs(command)
    if lifted is None:
        return None
    flat, bodies = lifted
    flat = _newlines_are_separators(flat)
    if flat is None:
        return None
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
        if tok in BLOCKED_TOKENS and not _subcommand_of_a_script(tok, cur):
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


def _split_env_prefix(tokens: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    pre: list[tuple[str, str]] = []
    while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
        name, _, value = tokens[0].partition("=")
        pre.append((name, value))
        tokens = tokens[1:]
    return pre, tokens


def _imports_ok(code: str) -> bool:
    for m in re.finditer(r"\b(?:import|from)\s+([\w.]+(?:\s*,\s*[\w.]+)*)", code):
        for name in re.split(r"\s*,\s*", m.group(1)):
            if name.split(".")[0] not in INLINE_MODULES:
                return False
    return True


def _inline_ok(code: str) -> bool:
    if not code.strip():
        return False
    if INLINE_BANNED.search(code) or SECRET_PATHS.search(code):
        return False
    if INLINE_SECRET_LEVEL.search(code):
        return False
    return _imports_ok(code)


def _python_ok(argv: list[str], heredoc: str) -> bool:
    """`python3 …`: the engine, a plugin or repo script, pytest, or inline
    code that imports only INLINE_MODULES and names nothing in INLINE_BANNED."""
    args = argv[1:]
    if not args:
        return False
    if args[0] in ("--version", "-V", "-VV"):
        return len(args) == 1
    if args[0] == "-m":
        if len(args) < 2:
            return False
        mod = args[1]
        if ENGINE_MOD.match(mod):
            return True
        if mod == "pytest":
            rest = args[2:]
            for i, a in enumerate(rest):
                if a in ("-p", "--plugin") or a.startswith("-p"):
                    val = a[2:] if len(a) > 2 else (rest[i + 1] if i + 1 < len(rest) else "")
                    if not val.startswith("no:"):
                        return False
                if a.startswith("--rootdir") or a.startswith("-c") and a != "-c":
                    return False
            return True
        return mod == "json.tool"
    if args[0] == "-c":
        return _inline_ok(" ".join(args[1:]))
    if args[0] == "-":
        return _inline_ok(heredoc)
    if args[0].startswith("-"):
        # -u, -B, -W … then the script; never -c/-m hidden behind a flag
        if any(a in ("-c", "-m") for a in args):
            return False
        rest = [a for a in args if not a.startswith("-")]
        return bool(rest) and _script_ok(rest[0])
    return _script_ok(args[0])


#: The directories a script may be run from, resolved on disk. The regexes
#: above are the fast path for the spellings prompts use; this is for a
#: RELATIVE path (`python ../../scripts/inspect_client_folders.py` from a
#: skill directory, `python scripts/ship_page.py` from the surface-production
#: skill) that the regexes cannot see the target of. Resolved against the
#: event's cwd, then checked against the same roots.


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


def _script_ok(path: str) -> bool:
    """Executable only from the REAL plugin tree or the real repo `scripts/`.

    The regexes above used to be a fast path that ACCEPTED on shape alone,
    and shape is forgeable: `/tmp/scripts/evil.py` matches REPO_SCRIPT and
    `/tmp/x/plugins/dma-insights/scripts/evil.py` matches PLUGIN_PATH, while
    `/tmp` is a write root — so two approved steps (Write then Bash) ran
    arbitrary code and every module, token and push rule in this file was
    moot. Measured 2026-09-04. The path is now always resolved on disk and
    checked against the directories that actually exist; the regexes only
    expand `$CLAUDE_PLUGIN_ROOT`, which a resolver cannot see through."""
    if not path.endswith(".py"):
        return False
    raw = path
    if "$" in raw:
        expanded = re.sub(r"\$\{?(CLAUDE_PLUGIN_ROOT|PLUGIN)\}?",
                          str(PLUGIN_DIR), raw)
        if "$" in expanded:
            return False                     # a name this grammar cannot see
        raw = expanded
    try:
        rp = _abs(raw).resolve()
    except OSError:
        return False
    return rp.is_file() and any(_under(rp, r) for r in _script_roots())


def _wrapped(tokens: list[str]) -> list[str] | None:
    """Peel `timeout [-k N] [-s SIG] DURATION cmd…` and `command [-p] cmd…`
    down to the command they run. `command -v x` / `type x` / `which x`
    are queries and stay as they are. None when the wrapper is malformed."""
    while tokens:
        v = tokens[0]
        if v == "timeout":
            i = 1
            while i < len(tokens) and tokens[i].startswith("-"):
                i += 2 if tokens[i] in ("-k", "-s", "--kill-after", "--signal") else 1
            if i + 1 >= len(tokens):
                return None
            tokens = tokens[i + 1:]
            _, tokens = _split_env_prefix(tokens)
            continue
        if v == "command":
            rest = tokens[1:]
            if rest and rest[0] in ("-v", "-V"):
                return tokens                  # a query: `command -v claude`
            # ONLY `command`'s own leading flags are peeled. Stripping every
            # flag turned `command sed -i …` into a plain `sed` read and
            # `command git push` into a bare `git` (2026-09-04).
            while rest and rest[0] in ("-p", "--"):
                rest = rest[1:]
            tokens = rest
            continue
        break
    return tokens


def _segment_ok(segment: str, bodies: list[str], ctx: dict) -> bool:
    """`ctx` carries what earlier segments of the same command established:
    `assigns` (NAME=value) and `cwd` (after a `cd`), so a later segment's
    `$NAME` and relative paths are judged where the shell would put them."""
    assigns, cwd = ctx["assigns"], ctx["cwd"]
    line, heredoc = _strip_heredoc(segment, bodies)
    if SECRET_PATHS.search(line) or SECRET_PATHS.search(heredoc):
        return False
    try:
        tokens = shlex.split(line, posix=True)
    except ValueError:
        return False
    pre, tokens = _split_env_prefix(tokens)
    for name, value in pre:
        assigns[name] = _expand(value, assigns)
    tokens = [_expand(t, assigns) for t in tokens]
    if SECRET_PATHS.search(" ".join(tokens)):
        return False                      # assembled from pieces or a $VAR
    tokens, targets = _redirect_targets(tokens)
    for t in targets:
        if not path_is_writable(t, strict=True, cwd=cwd):
            return False
    if not tokens:
        return True                                 # a bare assignment
    tokens = _wrapped(tokens)
    if not tokens:
        return False
    verb = tokens[0]
    if verb not in READ_VERBS:
        return False
    args = tokens[1:]
    if verb not in VAR_TOLERANT:
        for a in args:
            if "$" in a:
                return False                # a path the grammar cannot see
            # `__SUBST__` is the output of a `$(…)` this grammar ALREADY
            # checked as its own segment, so printing it exposes nothing the
            # command could not print directly. It is still not a path.
            if "__SUBST__" in a and verb not in ("echo", "printf"):
                return False
    if any(_reaches_secret_level(a, cwd) for a in args):
        return False
    if verb == "cd":
        target = next((a for a in args if not a.startswith("-")), "")
        if not target or "$" in target or "__SUBST__" in target:
            return False                    # a cwd the grammar cannot follow
        ctx["cwd"] = os.path.normpath(os.path.join(
            cwd, os.path.expanduser(target)))
        return True
    if verb in ("python3", "python"):
        return _python_ok(tokens, heredoc)
    if verb in ("bash", "sh"):
        rest = [a for a in args if not a.startswith("-")]
        return bool(rest) and bool(PLUGIN_PATH.match(rest[0])) \
            and rest[0].endswith(".sh")
    if verb == "git":
        if any(GIT_BAD.search(a) for a in args):
            return False
        sub = next((a for a in args if not a.startswith("-")), "")
        if sub not in GIT_OK:
            return False
        if sub == "config":
            rest = [a for a in args[args.index("config") + 1:]]
            if any(a in GIT_CONFIG_READ for a in rest):
                return True
            keys = [a for a in rest if not a.startswith("-")]
            return bool(keys) and keys[0].startswith("user.")
        return True
    if verb == "claude":
        # The argv `agent_run.py` emits, and no wider. Approving any
        # `claude -p … dma-insights:x` approved
        # `--dangerously-skip-permissions` too, which is this hook waving
        # through a child that answers to nothing (2026-09-04).
        if not ("-p" in args or "--print" in args):
            return False
        if not any(a.startswith("dma-insights:") for a in args):
            return False
        if any("dangerously" in a or "bypassPermissions" in a
               or a.startswith("--permission-prompt-tool") for a in args):
            return False
        for i, a in enumerate(args):
            if a == "--permission-mode" and i + 1 < len(args):
                if args[i + 1] not in ("dontAsk", "default", "plan",
                                       "acceptEdits"):
                    return False
        return True
    if verb == "export":
        return bool(args) and all(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", a)
                                  for a in args)
    if verb == "rm":
        # only strictly inside a write root, never a root itself
        paths = [a for a in args if not a.startswith("-")]
        return bool(paths) and all(path_is_writable(p, strict=True, cwd=cwd) and
                                   Path(p).name not in ("", ".", "..", "*")
                                   for p in paths)
    if verb in ("cp", "mv", "tee", "touch", "mkdir"):
        # the destination must be writable; a read from anywhere below the
        # secret level is fine. `-t DIR` puts the destination FIRST, which
        # read as a source while the last argument read as the destination
        # (`cp -t apps /tmp/evil.py` was approved, 2026-09-04).
        target = None
        for i, a in enumerate(args):
            if a in ("-t", "--target-directory") and i + 1 < len(args):
                target = args[i + 1]
            elif a.startswith("--target-directory="):
                target = a.split("=", 1)[1]
        paths = [a for a in args if not a.startswith("-")]
        if target is not None:
            return path_is_writable(target, cwd=cwd)
        if not paths:
            return False
        dests = paths[-1:] if verb in ("cp", "mv") else paths
        return all(path_is_writable(d, cwd=cwd) for d in dests)
    if verb == "sed":
        return _sed_ok(tokens, cwd)
    if verb == "sort":
        return not any(a in ("-o", "--output") or a.startswith("--output=")
                       or (a.startswith("-o") and len(a) > 2) for a in args)
    if verb in ("command", "type", "which"):
        return all("/" not in a for a in args)
    return True


def bash_ok(command: str) -> bool:
    if not isinstance(command, str) or not command.strip():
        return False
    split = _split_segments(command)
    if split is None:
        return False
    segs, bodies = split
    ctx: dict = {"assigns": {}, "cwd": _CWD}
    return bool(segs) and all(_segment_ok(s, bodies, ctx) for s in segs)


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
    # COWORK (Claude Desktop) runs shell commands through its own
    # `mcp__workspace__bash` tool and web reads through
    # `mcp__workspace__web_fetch`, not the built-in Bash/WebFetch — and the
    # permissions reference is explicit that a `Bash` allow rule never
    # carries over to it. Measured 2026-09-04: the owner sees prompts in
    # Cowork too, and there the connector hook's verb heuristic reads "bash"
    # as unknown and says nothing. Same grammar, same guards, same roots.
    if tool == "mcp__workspace__bash":
        tool = "Bash"
        if "command" not in ti:
            for key in ("cmd", "script", "input"):
                if isinstance(ti.get(key), str):
                    ti = {"command": ti[key]}
                    break
    elif tool == "mcp__workspace__web_fetch":
        return _allow("read-only web fetch through Cowork's workspace tool — "
                      "the same read the built-in WebFetch is approved for")
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
