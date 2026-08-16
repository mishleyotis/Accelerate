---
description: Check that this DMA Insights install can actually reach the connector — plugin, Google identity, token audience — and say which part is missing.
---

Run the install doctor and report its findings plainly.

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --base-url "${DMA_MCP_HOST:-https://dmai-mcp-dukrne5v4a-uc.a.run.app}"
```

Then, whatever it printed:

1. If every check passed, confirm the connector is reachable by calling
   `list_pending_runs` and reporting the count. A doctor that passes while the
   tools are absent has checked the wrong thing.
2. If a check failed, state which layer it is — plugin, Google credentials,
   token audience, or path token — and give the one command that fixes it. Do
   not guess past the first failure: they cascade, and the second message is
   usually a consequence of the first.

Never print, echo or paste a token, header value or secret. Report only whether
a credential could be obtained.
