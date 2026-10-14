You are a headless permission probe for the dma-insights plugin. Do exactly the
steps below, in order, using the named tools, and do not ask any question.
If a tool call is refused or asks for permission, do NOT retry it another way:
record the refusal text verbatim and continue to the next step.

1. Bash: `cd /home/user/Accelerate/plugins/dma-insights/skills/dma-research && python3 -m engine.cli counts`
2. Bash: `mkdir -p /root/.dma/probe/run && cd /home/user/Accelerate/plugins/dma-insights/skills/dma-research && python3 -m engine.preflight init --entity "Probe Credit Union" --entity-id probe-cu --out /root/.dma/probe/run/preflight.json`
3. Bash: `python3 /home/user/Accelerate/plugins/dma-insights/scripts/audit_builtin_approvals.py --strict | head -3`
4. Bash: `grep -c '"' /root/.dma/probe/run/preflight.json`
5. Write: create the file /root/.dma/probe/run/note.json with the content {"probe": "write-ok"}
6. Edit: in /root/.dma/probe/run/note.json replace `write-ok` with `edit-ok`
7. Read: read /root/.dma/probe/run/note.json back
8. Call the MCP tool mcp__plugin_dma-insights_connector__get_memory_digest with no arguments and note whether it returned.
9. Call the MCP tool mcp__plugin_dma-insights_connector__list_pending_runs with no arguments and note only how many rows it returned.
10. Bash: `python3 -c "import json; print(json.dumps({'probe': 'inline-ok'}))"`

Then print exactly one final line: PROBE COMPLETE: <n> of 10 steps ran, refused: <comma-separated step numbers or none>.
