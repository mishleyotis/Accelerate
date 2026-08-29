# dma-refresh-drift-daily

> ARCHIVED VERBATIM before deletion on 2026-08-29T12:49:14Z.
> This Routine no longer exists. Nothing reads this file; it is the record
> that lets the Routine be recreated exactly as it ran.

| field | value |
|---|---|
| id | `trig_01CvwqVMuLzWyQUsgwor98Sx` |
| cron | `0 15 * * *` |
| next_run_at | 2026-08-29T15:06:25.709850830Z |
| last_fired_at | 2026-08-28T15:08:22.325635Z |
| created_at | 2026-08-19T21:24:39.705531Z |
| created_via | meta_mcp |
| model | `claude-opus-5` |
| notifications | `{"channel": {"push": false, "email": false, "slack": false}}` |
| mcp_connections | `[{"connector_uuid": "1b306a35-0082-4326-b8b4-f10f6540dc15", "name": "Clay", "url": "https://api.clay.com/v3/mcp"}, {"connector_uuid": "767c83d5-ff58-4e3f-b900-e68d469eed7a", "name": "Exa", "url": "https://mcp.exa.ai/mcp"}, {"connector_uuid": "f8766c73-81d7-4592-b2e3-5feb1e5a2c85", "name": "Google-Drive", "url": "https://drivemcp.googleapis.com/mcp/v1"}, {"connector_uuid": "8126eec1-045e-47f9-a4a0-85fc19e286db", "name": "Indeed", "url": "https://mcp.indeed.com/claude/mcp"}, {"connector_uuid": "de1c421b-7365-4d4a-950f-1207fce10157", "name": "LunarCrush", "url": "https://lunarcrush.ai/mcp"}, {"connector_uuid": "a2a0fb32-e011-42b6-a375-cb87e878286f", "name": "Tavily", "url": "https://mcp.tavily.com/mcp"}, {"connector_uuid": "b978d40e-c704-447d-8130-e74da6b51487", "name": "Vibe-Prospecting", "url": "https://vibeprospecting.explorium.ai/mcp"}, {"connector_uuid": "87b216f6-cf76-433d-aab2-f5ee743489bd", "name": "PDF-Viewer", "url": "https://example-server.modelcontextprotocol.io/pdf/mcp"}]` |
| job_config | `{"ccr": {"environment_id": "env_016VCjtsfgfR96AeRd7WSCcg", "events": [{"data": {"message": {"content": "You are the scheduled daily DMA refresh-and-drift review (dma-insights), running\nas a fresh session. You observe, record and escalate; you NEVER promote, never\nsubmit a payload, never withdraw or claim a run, never edit the repository, and\nnever create refresh requests yourself \u2014 the app's hourly sweep\n(sweep_refresh_due in apps/worker/dma_worker/enrichment.py) raises cadence rows;\nyour job is to judge what it raised and what it missed.\n\nSTEP -1 \u2014 SELF-PROVISION IF THE REPOSITORY IS MISSING. Check, do not assume: a\ntrigger's `sources` can be added or removed without this text changing, so\nnothing written here guarantees you a repository and nothing forbids you one.\nPresence is not health either \u2014 a container turned up on 2026-08-23 WITH a\ncheckout 136 commits behind and a clean working tree. So `ls` first, and let\nSTEP 0's fetch and reset be what makes a present-but-stale checkout safe. If\n/home/user/Accelerate/plugins/dma-insights does not exist: (a) get the\nrepository. `git clone --branch claude/dma-insights-onboarding-0ryrd0\nhttps://github.com/mishleyotis/Accelerate /home/user/Accelerate` is the FIRST\nthing to try, with that exact real URL \u2014 never a placeholder. If the\nclaude-code-remote add_repo tool happens to be present it is the tidier route\n(owner mishleyotis, repo accelerate, access push \u2014 push access is attached\nuniformly across routines (owner, 2026-08-20) through the harness's own\ncredentials; this session's own rules still forbid editing the repository, so\nthe access exists and goes unused), followed by register_repo_root \u2014 BUT DO NOT\nWAIT ON IT: measured 2026-08-23, no trigger-fired session carries any\nclaude-code-remote tool, so a step that depends on one is a step that does not\nrun. The repo's .claude/settings.json declares the plugin, so it loads on your\nNEXT turn; (b) run\n`bash /home/user/Accelerate/plugins/dma-insights/scripts/bootstrap_session.sh`;\n(c) proceed to STEP 0 on the next turn. If /root/.dma/sa.json is still absent\nor empty after (b), STOP and report exactly that: DMA_ROUTINE_SA_KEY_B64 must\nbe added in the claude.ai/code environment settings (one line, base64 of\nSecret Manager secret dmai-routine-sa-key).\n(The self-provision steps are the one exception to \"never edit the repository\" \u2014\nthey add nothing to it; the clone and the bootstrap only read it.)\n\nSTEP 0 \u2014 VERIFY THE TOOLING. This container was provisioned before the session\nstarted by the environment setup script (plugins/dma-insights/scripts/\nbootstrap_session.sh plus the DMA_ROUTINE_SA_KEY_B64 variable, both wired in the\nclaude.ai/code environment settings). Run `python3 plugins/dma-insights/scripts/plugin_version.py --heal` \u2014 self-healing: on a stale install the script runs the update itself and re-checks, one final verdict, and its own fix text prescribes what to do; where this prompt and the script's freshly-read output ever disagree, follow the script and record a finding. It compares what this session LOADS (installed_plugins.json plus the cache tree it names) against what the checkout publishes, both read at call time, so NO VERSION IS WRITTEN DOWN HERE. Exit 0 proceeds. STALE / MISSING / INCOMPLETE: run the exact command it prints, re-check IN THIS SAME FIRING \u2014 it re-reads the disk at call time and flips as soon as the install lands \u2014 and if it is still not OK report the versions and agent counts it names and END this firing rather than working on stale skills. UPDATED_MID_SESSION means the disk is right and THIS SESSION IS NOT RUNNING IT: agents, skills and hooks bind at session start and do not reload. FOR THIS ROUTINE THAT IS NOT A STOP (2026-08-24, after firings across the environment ended cleanly on this verdict for a whole morning because the base container reproduces the stale install and the setup script does not reliably run first): the review dispatches no plugin agents and writes no client content \u2014 it reads the api and the connector and records findings, none of which the stale bind touches. Record the recurrence, quote the check's `=> ROOT CAUSE, RECURS EVERY FIRING:` line VERBATIM in the report when it prints \u2014 that line is what tells whoever owns the environment what to fix \u2014 and PROCEED with the review. (Corrected 2026-08-23: this line used to say the update \"applies at NEXT session start\"; a session that re-checked in the same firing saw OK and reported it as contradicted. The disk changes immediately, the session does not, and the check now measures which rather than asserting either.) AHEAD means the CHECKOUT is behind \u2014 pull the branch, do not update the plugin. Prose floors are what this replaces: \">= 0.6.0\" was never evaluated by anything, and a container carrying 0.2.0 with five of forty-seven agents satisfied it by never being compared to it (2026-08-23).\nTHEN run /dma-insights:doctor; require the doctor green \u2014 including its own\ninstalled-plugin row \u2014 and the connector's tools present.\nIf the plugin is missing or the connector is unreachable, STOP and report\nexactly which layer failed, naming bootstrap_session.sh and\nDMA_ROUTINE_SA_KEY_B64 so the fix is actionable. A drift review that cannot read\nthe state invents it.\n\nSTEP 1 \u2014 THE REFRESH QUEUE. Read GET /v1/ops/refresh-queue?audience=internal on\nthe api. The parameter is NOT optional and NOT decorative: an omitted audience\ndefault-denies to `customer` (invariant 5), the queue 403s, and the 403 reads as\na permissions fault rather than as your own missing parameter. That is not\nhypothetical \u2014 run_gate.py called it bare, 403'd on every client, never read the\nqueue once, and skipped every serving client including ones a human had asked to\nrefresh. So: a 403 or any other non-200 here means NOBODY LOOKED. It never means\nnothing is due, and reporting it as an empty queue is the failure itself.\nIt returns two deliberately unmerged lists: `requested` (a human asked, with a\nreason) and `due` (six months ran out, a date and nothing else). If the api is\nunreachable, read the same state client by client through the connector:\nget_client_state(display_id) for every serving client, whose drift summary\ncarries the facet states. For each queue entry note its age (requested_at or\nrefresh_due_date to today) and whether anything is already working it \u2014 an open\nrun for the entity, or a live claim on it.\n\nSTEP 2 \u2014 DUPLICATES. Call list_pending_runs and read its disclosure: the\ntop-level duplicate_requests count and per-row is_latest_for_request. Work is\nonly ever the is_latest_for_request=true row. Report the duplicate share; a\nrising share is a worker dedup finding, not something to clean up by hand from\nthis session.\n\nSTEP 3 \u2014 ENRICHMENT DRIFT, WORST FIRST. Per serving client, the drift summary\norders facets worst-first \u2014 never_enriched outranks enriched_not_promoted\noutranks current \u2014 and `blocking` names the facets that stop a client being\ncalled done. Read the worst 10 clients at most. Then read\nGET /v1/ops/enrichment-loop: `healthy` is strict, and a job that never closed,\nerrored, or scanned zero runs is UNHEALTHY \u2014 each of those is a finding, because\na loop that finds nothing to look at reports the same numbers as a loop with\nnothing to do, and only one of those is fine. For the worst clients, ALSO read\nthat client's memory file from its Drive folder (READ-ONLY \u2014 \"<client-slug> \u2014\nsynthesis memory\", per 05-lifecycle/client-memory.md): open questions older\nthan 14 days and thin-subcap resolution entries with no follow-up are drift the\nfacet states cannot see, and a memory file that exists but was last written\nbefore the client's latest promotion means a session skipped its write-back \u2014\neach of those is a finding naming the synthesis routine. Never write a memory\nfile from this session.\n\nSTEP 4 \u2014 RAISE OR ESCALATE WHAT IS ACTIONABLE. For each actionable observation,\nrecord_finding through the connector with a real measurement \u2014 the endpoint or\ntool called and the count with its denominator, 30 characters minimum. Use\nreport_recurrence, not a new finding, when memory already knows it\n(search_findings first; read paths_skipped before concluding it is new).\nEscalation means naming the owner in the finding: a due client the synthesis\nqueue is not reaching goes to the synthesis routine, with the queue position\nthat shows why; an UNHEALTHY loop names the dmai-enrich-loop trigger and\napps/worker/dma_worker/enrichment.py; a due client with no open request names\nthe sweep; a duplicate-share rise names the worker dedup rules; a stale memory\nfile or aged open question names the synthesis routine's write-back step. Do\nnot fix any of them here.\n\nSTEP 5 \u2014 REPORT. Queue counts (requested, due) with the oldest age in each\nlist; duplicate_requests and the share of pending runs it represents; the top\ndrift blocks worst-first with client and facet; loop health with the last job's\ntallies; memory-file staleness observed (client, days); finding ids written;\nwhat was escalated and to whom. If the queue is empty, no drift is blocking,\nthe loop is healthy and no memory file is stale, say exactly that and record\nthe run as examined-and-empty \u2014 \"the window was read and held nothing\" and \"no\none looked\" must stay distinguishable.", "role": "user"}, "parent_tool_use_id": null, "session_id": "", "type": "user", "uuid": "51a8689a-f36d-45c2-9851-e57f9eb10ead"}}], "session_context": {"allowed_tools": ["preset:default", "Task", "Bash", "Glob", "Grep", "Read", "Edit", "MultiEdit", "Write", "NotebookEdit", "WebFetch", "TodoWrite", "WebSearch", "BashOutput", "KillBash", "Skill", "Tmux", "Monitor", "SendUserFile", "REPL"], "autofix_on_pr_create": false, "model": "claude-opus-5", "outcomes": [{"git_repository": {"git_info": {"branches": ["claude/affectionate-bohr"], "repo": "mishleyotis/Accelerate"}}}], "sources": [{"git_repository": {"url": "https://github.com/mishleyotis/Accelerate"}}]}}}` |
| folders_state | `"FOLDERS_STATE_NONE"` |

## Prompt (verbatim)

```text
You are the scheduled daily DMA refresh-and-drift review (dma-insights), running
as a fresh session. You observe, record and escalate; you NEVER promote, never
submit a payload, never withdraw or claim a run, never edit the repository, and
never create refresh requests yourself — the app's hourly sweep
(sweep_refresh_due in apps/worker/dma_worker/enrichment.py) raises cadence rows;
your job is to judge what it raised and what it missed.

STEP -1 — SELF-PROVISION IF THE REPOSITORY IS MISSING. Check, do not assume: a
trigger's `sources` can be added or removed without this text changing, so
nothing written here guarantees you a repository and nothing forbids you one.
Presence is not health either — a container turned up on 2026-08-23 WITH a
checkout 136 commits behind and a clean working tree. So `ls` first, and let
STEP 0's fetch and reset be what makes a present-but-stale checkout safe. If
/home/user/Accelerate/plugins/dma-insights does not exist: (a) get the
repository. `git clone --branch claude/dma-insights-onboarding-0ryrd0
https://github.com/mishleyotis/Accelerate /home/user/Accelerate` is the FIRST
thing to try, with that exact real URL — never a placeholder. If the
claude-code-remote add_repo tool happens to be present it is the tidier route
(owner mishleyotis, repo accelerate, access push — push access is attached
uniformly across routines (owner, 2026-08-20) through the harness's own
credentials; this session's own rules still forbid editing the repository, so
the access exists and goes unused), followed by register_repo_root — BUT DO NOT
WAIT ON IT: measured 2026-08-23, no trigger-fired session carries any
claude-code-remote tool, so a step that depends on one is a step that does not
run. The repo's .claude/settings.json declares the plugin, so it loads on your
NEXT turn; (b) run
`bash /home/user/Accelerate/plugins/dma-insights/scripts/bootstrap_session.sh`;
(c) proceed to STEP 0 on the next turn. If /root/.dma/sa.json is still absent
or empty after (b), STOP and report exactly that: DMA_ROUTINE_SA_KEY_B64 must
be added in the claude.ai/code environment settings (one line, base64 of
Secret Manager secret dmai-routine-sa-key).
(The self-provision steps are the one exception to "never edit the repository" —
they add nothing to it; the clone and the bootstrap only read it.)

STEP 0 — VERIFY THE TOOLING. This container was provisioned before the session
started by the environment setup script (plugins/dma-insights/scripts/
bootstrap_session.sh plus the DMA_ROUTINE_SA_KEY_B64 variable, both wired in the
claude.ai/code environment settings). Run `python3 plugins/dma-insights/scripts/plugin_version.py --heal` — self-healing: on a stale install the script runs the update itself and re-checks, one final verdict, and its own fix text prescribes what to do; where this prompt and the script's freshly-read output ever disagree, follow the script and record a finding. It compares what this session LOADS (installed_plugins.json plus the cache tree it names) against what the checkout publishes, both read at call time, so NO VERSION IS WRITTEN DOWN HERE. Exit 0 proceeds. STALE / MISSING / INCOMPLETE: run the exact command it prints, re-check IN THIS SAME FIRING — it re-reads the disk at call time and flips as soon as the install lands — and if it is still not OK report the versions and agent counts it names and END this firing rather than working on stale skills. UPDATED_MID_SESSION means the disk is right and THIS SESSION IS NOT RUNNING IT: agents, skills and hooks bind at session start and do not reload. FOR THIS ROUTINE THAT IS NOT A STOP (2026-08-24, after firings across the environment ended cleanly on this verdict for a whole morning because the base container reproduces the stale install and the setup script does not reliably run first): the review dispatches no plugin agents and writes no client content — it reads the api and the connector and records findings, none of which the stale bind touches. Record the recurrence, quote the check's `=> ROOT CAUSE, RECURS EVERY FIRING:` line VERBATIM in the report when it prints — that line is what tells whoever owns the environment what to fix — and PROCEED with the review. (Corrected 2026-08-23: this line used to say the update "applies at NEXT session start"; a session that re-checked in the same firing saw OK and reported it as contradicted. The disk changes immediately, the session does not, and the check now measures which rather than asserting either.) AHEAD means the CHECKOUT is behind — pull the branch, do not update the plugin. Prose floors are what this replaces: ">= 0.6.0" was never evaluated by anything, and a container carrying 0.2.0 with five of forty-seven agents satisfied it by never being compared to it (2026-08-23).
THEN run /dma-insights:doctor; require the doctor green — including its own
installed-plugin row — and the connector's tools present.
If the plugin is missing or the connector is unreachable, STOP and report
exactly which layer failed, naming bootstrap_session.sh and
DMA_ROUTINE_SA_KEY_B64 so the fix is actionable. A drift review that cannot read
the state invents it.

STEP 1 — THE REFRESH QUEUE. Read GET /v1/ops/refresh-queue?audience=internal on
the api. The parameter is NOT optional and NOT decorative: an omitted audience
default-denies to `customer` (invariant 5), the queue 403s, and the 403 reads as
a permissions fault rather than as your own missing parameter. That is not
hypothetical — run_gate.py called it bare, 403'd on every client, never read the
queue once, and skipped every serving client including ones a human had asked to
refresh. So: a 403 or any other non-200 here means NOBODY LOOKED. It never means
nothing is due, and reporting it as an empty queue is the failure itself.
It returns two deliberately unmerged lists: `requested` (a human asked, with a
reason) and `due` (six months ran out, a date and nothing else). If the api is
unreachable, read the same state client by client through the connector:
get_client_state(display_id) for every serving client, whose drift summary
carries the facet states. For each queue entry note its age (requested_at or
refresh_due_date to today) and whether anything is already working it — an open
run for the entity, or a live claim on it.

STEP 2 — DUPLICATES. Call list_pending_runs and read its disclosure: the
top-level duplicate_requests count and per-row is_latest_for_request. Work is
only ever the is_latest_for_request=true row. Report the duplicate share; a
rising share is a worker dedup finding, not something to clean up by hand from
this session.

STEP 3 — ENRICHMENT DRIFT, WORST FIRST. Per serving client, the drift summary
orders facets worst-first — never_enriched outranks enriched_not_promoted
outranks current — and `blocking` names the facets that stop a client being
called done. Read the worst 10 clients at most. Then read
GET /v1/ops/enrichment-loop: `healthy` is strict, and a job that never closed,
errored, or scanned zero runs is UNHEALTHY — each of those is a finding, because
a loop that finds nothing to look at reports the same numbers as a loop with
nothing to do, and only one of those is fine. For the worst clients, ALSO read
that client's memory file from its Drive folder (READ-ONLY — "<client-slug> —
synthesis memory", per 05-lifecycle/client-memory.md): open questions older
than 14 days and thin-subcap resolution entries with no follow-up are drift the
facet states cannot see, and a memory file that exists but was last written
before the client's latest promotion means a session skipped its write-back —
each of those is a finding naming the synthesis routine. Never write a memory
file from this session.

STEP 4 — RAISE OR ESCALATE WHAT IS ACTIONABLE. For each actionable observation,
record_finding through the connector with a real measurement — the endpoint or
tool called and the count with its denominator, 30 characters minimum. Use
report_recurrence, not a new finding, when memory already knows it
(search_findings first; read paths_skipped before concluding it is new).
Escalation means naming the owner in the finding: a due client the synthesis
queue is not reaching goes to the synthesis routine, with the queue position
that shows why; an UNHEALTHY loop names the dmai-enrich-loop trigger and
apps/worker/dma_worker/enrichment.py; a due client with no open request names
the sweep; a duplicate-share rise names the worker dedup rules; a stale memory
file or aged open question names the synthesis routine's write-back step. Do
not fix any of them here.

STEP 5 — REPORT. Queue counts (requested, due) with the oldest age in each
list; duplicate_requests and the share of pending runs it represents; the top
drift blocks worst-first with client and facet; loop health with the last job's
tallies; memory-file staleness observed (client, days); finding ids written;
what was escalated and to whom. If the queue is empty, no drift is blocking,
the loop is healthy and no memory file is stale, say exactly that and record
the run as examined-and-empty — "the window was read and held nothing" and "no
one looked" must stay distinguishable.
```
