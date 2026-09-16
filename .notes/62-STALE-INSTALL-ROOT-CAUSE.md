# Why every new session reported a stale plugin install (2026-09-16)

Read-only diagnosis of the container that opened session
`session_01WRC9vC7myKkQRyg25qPGGw`, followed by the code change that ends
the recurrence. Every line below is a measurement from that container or a
sentence from the Claude Code documentation, not an inference.

## The symptom

The SessionStart hook reported, on every new session:

```
STALE: installed 1.19.0 (73 agents) vs published 1.20.0 (74 agents).
This session is NOT running what the checkout publishes.
RESEARCH, SCORING AND REPORT WORK IS REFUSED ON THIS INSTALL …
```

Sessions then ran `doctor.py --heal`, got `UPDATED_MID_SESSION`, worked in
"recovery mode", and the next session reported the same thing.

## What the container actually held

| Fact | Value | How measured |
|---|---|---|
| Install record | `1.19.0`, `installPath=~/.claude/plugins/cache/zennify-dma/dma-insights/1.19.0`, written `2026-09-11T03:56:48Z` | `~/.claude/plugins/installed_plugins.json` |
| Cache copy | 73 agents, no `agents/research/research-challenger.md` | `diff -rq` against the checkout |
| Provisioning record | `bootstrap_ran_at 2026-09-11T03:56:50Z`, installed `1.19.0`, expected `1.19.0`, checkout at `bfd1971` | `/root/.dma/provisioning.json` |
| Checkout | `1.20.0`, 74 agents, HEAD `507e79e` on `claude/tender-gauss-e1alh7` | `git log`, `plugin.json` |
| Checkout refreshed at | `02:34:47.75` to `.80` | `stat` on `conftest.py`, `.git/HEAD`, `.git/FETCH_HEAD`; `git reflog` |
| CLI process started at | `02:34:47.82` | ctime of `/proc/$CLAUDE_PID` |
| Connector process root | `CLAUDE_PLUGIN_ROOT=/home/user/Accelerate/plugins/dma-insights` | `/proc/1207/environ` of `mcp_proxy.py` |
| PreToolUse hook root | `CLAUDE_PLUGIN_ROOT=/home/user/Accelerate/plugins/dma-insights` | sampled `/proc/*/environ` of `autoapprove_builtins.py` during a tool call |
| Agent roster this session | 74 agents including `dma-insights:research-challenger` | the Agent tool's roster |
| `claude plugin details dma-insights@zennify-dma` | `1.20.0`, the 74-agent description | CLI |
| Startup reconcile | `headless_marketplace_reconcile_completed installed 0 updated 0` | `$CLAUDE_CODE_DIAGNOSTICS_FILE` |

So the session was running **1.20.0 from the checkout, in place**. The
record said 1.19.0 because the record was never what the CLI loads from.

## Why the record was frozen

From the cloud-environments documentation (`code.claude.com/docs/en/cloud-environments`,
section *Environment caching*):

> The setup script runs the first time you start a session in an environment.
> After it completes, Anthropic snapshots the filesystem and reuses that
> snapshot as the starting point for later sessions. New sessions start with
> your dependencies, tools, and Docker images already on disk, and skip the
> setup script step.

> The setup script runs again to rebuild the cache when you change the
> environment's setup script or allowed network hosts, and when the cache
> reaches its expiry after roughly seven days. Resuming an existing session
> never re-runs the setup script.

`bootstrap_session.sh` is that setup script. It ran once, on 2026-09-11 at
03:56, installed the plugin that was current then (1.19.0), and wrote the
install record and the provisioning record. Every session since started from
that snapshot. The harness refreshed the checkout to the branch tip before
the CLI started; the record stayed at 1.19.0. There is no per-session mode
for setup scripts, so "run bootstrap at session start", which the old
`stale_snapshot` fix text prescribed, was not something the environment can
do.

## Why the check called it stale anyway

`plugins/dma-insights/scripts/plugin_version.py` took "what this session
loads" from `installed_plugins.json` plus the cache directory it points at.
For a plugin whose marketplace is a `directory` source with a relative plugin
path (`.claude/settings.json` registers the checkout as `zennify-dma`;
`marketplace.json` points at `./plugins/dma-insights`), Claude Code 2.1.273
resolves the plugin against the marketplace directory and runs it in place.
The hook, the engine's `refuse_on_stale_install`, `guard_dispatch`, the
doctor and `readiness.py` all read the same wrong tree, so they agreed with
each other and were all wrong together.

Each `--heal` then updated a copy nothing loads from, on a disk that is
discarded when the session ends. The next session restored the snapshot and
paid again. That is the whole loop.

## The change

* `plugin_version.loaded_root()` measures the root the session runs from,
  in order of directness: `CLAUDE_PLUGIN_ROOT` (a hook or the connector, or
  a child of either), then the record the SessionStart hook now writes to
  `~/.claude/plugins/data/dma-insights-zennify-dma/loaded_root.json` keyed by
  session id, then the live connector process's environment. Only with no
  measurement at all does the install record decide, as before.
* `compare()` reports `OK … loaded in place from the checkout` when the
  loaded tree **is** the checkout's plugin directory, and names the record
  beside it as bookkeeping. Version arithmetic, DIVERGED, DISABLED and the
  heal plan apply unchanged when the loaded root is a real copy.
* `session_brief.py` records the loaded root on SessionStart, SubagentStart
  and PostCompact, fail-open.
* The `stale_snapshot` provisioning verdict, its fix text,
  `bootstrap_session.sh`'s header and the readiness standing item now state
  the documented snapshot behaviour and prescribe the only action that
  exists (rebuild the cache), and only for a session whose loaded root is the
  copy.

Verified on this container after the change:

```
OK: installed 1.20.0 (74 agents) vs published 1.20.0 (74 agents) — loaded in place from the checkout
  - loaded IN PLACE from the checkout (/home/user/Accelerate/plugins/dma-insights), measured from …
    the install record says 1.19.0 at /root/.claude/plugins/cache/…/1.19.0, which is the CLI's
    bookkeeping and not what it loads from — nothing to heal
```

`doctor.py --no-probe`: `installed plugin` row green with the same line.

## What this does not claim

* It does not claim the CLI will load in place on every machine or every
  CLI version. That is why the root is measured rather than assumed; a
  session that really loads the snapshot's copy is still reported STALE,
  against the tree it runs, with the cache-rebuild fix.
* It does not change `bootstrap_session.sh`'s install step. Registration
  (marketplace, `enabledPlugins`, `userConfig`) is still what makes the CLI
  load the plugin at all; the snapshot carries it.
* The checkout refresh landed 70 ms before the CLI started on this
  container. A refresh that landed after the CLI started would be a
  different defect (agents read at start, hooks read per call), and this
  check would not see it. Nothing measured suggests it happens.
