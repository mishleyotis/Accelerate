#!/usr/bin/env python3
"""PreToolUse guard on Bash: credential-shaped operations are denied by policy.

WHY (measured 2026-08-20): a trigger-fired synthesis session invented a
"GitHub PAT instruction" that was never given, committed repo edits outside
its writer scope (constraint [B]: the weekly rectifier is the only plugin
writer) and tried to push them "using the routine's existing secrets
mechanism". The harness classifier blocked it — correctly — but a
probabilistic block invites the next session to try another phrasing, and it
teaches nothing. This hook makes the boundary DETERMINISTIC policy (owner,
2026-08-20: "add a scoped permission properly rather than trying to work
around the classifier") and the denial text itself carries the sanctioned
path, so the block is where a confused session learns to self-heal.

Denied, each with zero legitimate use anywhere in this workflow:
  * GitHub token literals on a command line — no GitHub PAT exists in this
    workflow; Secret Manager holds only the SA key and the connector path
    token, and the one routine that pushes (the weekly rectifier) rides the
    harness's own GitHub App credentials via plain `git push`.
  * git URLs with embedded credentials, x-access-token forms, and git
    credential-helper writes — nothing here may mint or persist a git
    credential.
  * shell fetches of docs.google.com URLs — Drive content is read through
    drive_fetch.py under the service-account identity, whose visibility is
    the access boundary; the owner's own documents (one of which holds
    credentials) must never be pulled into a transcript by an ad-hoc fetch.

Fail-open on malformed input: a guard that bricks every Bash call when the
harness changes its stdin shape is a worse failure than the classifier
backstop it complements. Allow = exit 0 with no output.
"""
import json
import re
import sys

DENIALS = (
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "a GitHub token literal"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
     "a GitHub fine-grained token literal"),
    (re.compile(r"://[^/\s'\"]*@github\.com", re.I),
     "a git URL with embedded credentials"),
    (re.compile(r"\bx-access-token\b", re.I),
     "an x-access-token credential form"),
    (re.compile(r"\bgit\b[^\n|;&]*\bcredential\.helper\b"),
     "a git credential-helper write"),
    # A FETCH, not a mention. Measured 2026-09-30 (SWBC, HYBRID): the rule
    # matched the URL alone, so `engine.intake add --source-url <doc>` and
    # `engine.cli evidence --origin internal --url <doc>` — recording where
    # an internal document came from, which the protocol requires — were
    # denied as "a shell fetch" although nothing was fetched. The URL now
    # denies only beside something that retrieves it.
    (re.compile(
        # \A: evaluated once, from the start. Unanchored, re.search retried
        # both [\s\S]* scans at every offset — cubic on a long command, which
        # timed the adversarial garbage test out at 60 s.
        r"\A(?=[\s\S]*\bdocs\.google\.com/(?:document|spreadsheets|presentation)\b)"
        r"[\s\S]*(?:\b(?:curl|wget|http|https|httpie|aria2c|lynx|w3m|links|"
        r"xh|gsutil)\b(?!\s*[:=])|urlopen|urllib|requests\.(?:get|post)|"
        r"httpx|fetch\s*\()",
        re.I),
     "a shell fetch of a Google Docs URL"),
    # QA audit F-K04-039 (28-09-2026): the service-account key on disk
    # (/root/.dma/sa.json) and the path token were readable by any Bash and
    # named by no guard; autoapprove_builtins merely declined to approve the
    # read, which left it a prompt. The key is read only by the plugin's own
    # scripts inside a process (gcp_token) and never printed, copied,
    # exported or piped.
    (re.compile(r"\.dma/(?:sa\.json|pathtok|path_token|routine_sa[\w.-]*)\b|"
                r"\bsa\.json\b"),
     "the service-account key file or path token by name"),
    (re.compile(r"\bDMA_ROUTINE_SA_KEY_B64\b|\bDMA_PATH_TOKEN\b"),
     "the credential environment variable by name"),
    # ANY process's environ, however the pid is written — a number, self,
    # thread-self, a glob, $$, $PPID, ${PPID}. The first version enumerated
    # a few spellings and /proc/$PPID/environ walked past it.
    (re.compile(r"/proc/[^/\s]+/environ\b"),
     "a process environment read (list names only with `env | cut -d= -f1`)"),
)

# A WHOLE-ENVIRONMENT DUMP prints the credential without naming it.
# Measured 2026-10-05 (arbor-bank-2026-10-05 resume): `env | grep -i DMA_`
# run to find a run root printed DMA_ROUTINE_SA_KEY_B64's value into the
# transcript; the by-name rule above never saw it. A segment whose command
# is bare `env` / `printenv` / `export -p` / `declare -x|-p` / `set` dumps
# every value; it is denied unless the next pipe stage keeps NAMES only.
# `env VAR=x cmd` (env as a launcher), `printenv NAME`, `set -e` and
# `export FOO=1` are untouched.
#
# Read at the grain of SHELL WORDS, per command segment: the first version
# matched string prefixes, so it missed `env 2>&1 | grep`, `/usr/bin/env`,
# bare `export` and `env -0`, and it split on parentheses, so the Python
# expression `set(a) | set(b)` inside a heredoc read as a bare `set`.
# Best-effort by design: a program that prints its own environment
# (python -c 'print(os.environ)') is not a shell builtin and is not caught.
_NAMES_ONLY = re.compile(
    r"^\s*(?:cut\s+-d\s*['\"]?=['\"]?\s+-f\s*1(?![\d,-])|cut\s+-f\s*1(?![\d,-])\s+-d\s*['\"]?=['\"]?(?:\s|$)|"
    r"sed\s+(?:-e\s+)?['\"]s/=\.\*//['\"]|awk\s+-F\s*['\"]?=['\"]?\s+['\"]\{\s*print \$1\s*\}['\"])")
_SEGMENT = re.compile(r"\$\(|`|&&|\|\||;|\n|(?<![>&<0-9])&(?![>&])")
_REDIRECT = re.compile(r"^(?:\d*>>?|\d*>&\d*|&>>?|<)\S*$")
ENV_DUMP = ("a whole-environment dump (it prints every secret value; list "
            "names only with `env | cut -d= -f1`)")


def _words(stage: str) -> list[str]:
    try:
        import shlex
        w = shlex.split(stage, posix=True)
    except ValueError:
        w = stage.split()
    out, skip = [], False
    for t in w:
        if skip:
            skip = False
            continue
        if _REDIRECT.match(t):
            if t in (">", ">>", "<", "&>", "&>>") or re.fullmatch(r"\d+>>?", t):
                skip = True            # the redirect target is the next word
            continue
        out.append(t)
    while out and out[0] in ("sudo", "command", "builtin", "exec", "nohup"):
        out = out[1:]
    return out


def _dumps(words: list[str]) -> bool:
    if not words:
        return False
    head, args = words[0].rsplit("/", 1)[-1], words[1:]
    if head in ("env", "printenv"):
        # Only flags left: it prints the environment. A NAME=value word or a
        # command after it makes env a launcher; a bare name makes printenv
        # print one variable.
        return all(a.startswith("-") for a in args)
    if head == "set":
        return not args
    if head == "export":
        return not args or args == ["-p"]
    if head in ("declare", "typeset"):
        flags = [a for a in args if a.startswith("-")]
        names = [a for a in args if not a.startswith("-")]
        return not names and (not flags or any(c in f for f in flags for c in "px"))
    return False


def _env_dump(command: str) -> bool:
    for seg in _SEGMENT.split(command or ""):
        stages = seg.split("|")
        if _dumps(_words(stages[0].strip().rstrip(")").strip())):
            nxt = stages[1] if len(stages) > 1 else ""
            if not _NAMES_ONLY.match(nxt):
                return True
    return False


REASON = (
    "Denied by dma-insights policy: the command carries {what}. No GitHub "
    "credential exists in this workflow (Secret Manager holds only the SA "
    "key and the connector path token) — any 'GitHub PAT instruction' is "
    "spurious. Synthesis and drift sessions attach the repository read-only "
    "and never commit or push; persistence is the connector plus Drive "
    "(drive_fetch.py push-ledger / push-bundle / push-memory). Repository "
    "changes land only through the weekly rectifier's reviewed PR on the "
    "harness's own credentials, and Google Docs are read via drive_fetch.py "
    "under the service-account identity, never fetched from a shell."
)


def decide(command: str) -> str | None:
    """The denial reason for a Bash command, or None."""
    for rx, what in DENIALS:
        if rx.search(command or ""):
            return REASON.format(what=what)
    if _env_dump(command):
        return REASON.format(what=ENV_DUMP)
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail-open: the harness classifier remains the backstop
    if not isinstance(payload, dict):
        # NOT-A-DICT IS UNPARSED INPUT, NOT A VIOLATION. Measured 2026-09-14:
        # a JSON list, string or null on stdin raised AttributeError here and
        # the hook exited NON-ZERO with a traceback — a hook failing CLOSED on
        # its own bug, which is the one failure a guard may never have.
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    ti = payload.get("tool_input")
    command = (ti.get("command") or "") if isinstance(ti, dict) else ""
    if not isinstance(command, str):
        return 0
    reason = decide(command)
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
