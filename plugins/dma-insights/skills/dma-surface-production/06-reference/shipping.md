# Shipping a page: write files, run one command

Moved out of `SKILL.md` on 28-09-2026 (QA audit F-B04-027: the skill file was over 500 lines, and a file nobody can read in one sitting is a file nobody reads). The SKILL.md reading manifest says which phase reads this.

## Shipping a page: write files, run one command

**Never retype a payload into `append_payload_part`.** Write each section to
`sections/<page>.<section>.json` and ship the directory:

```bash
python scripts/self_heal.py --sections sections/ --page overview \
       --entity "<the entity's legal name>"      # blocking vs advisory
python scripts/ship_page.py <run_id> overview --sections sections/ --dry-run
python scripts/ship_page.py <run_id> overview --sections sections/
python scripts/ship_page.py <run_id> all --sections sections/ --promote
```

`ship_page.py` assembles the sections, plans the parts, opens the upload,
sends every part **from disk** through `plugins/dma-insights/scripts/mcp_raw.py`,
submits with the `expect` counts, and prints the verdict's status and blocking
reasons — nothing else.

### Why this is not optional

Golden 1 CU (2026-09-02) shipped its six pages by printing the payload in
4000-character chunks and having subagents retype them into
`append_payload_part`, comparing byte receipts to catch drift. That cost about
**330,000 subagent tokens for one page, done twice**, and it was never
necessary: `mcp_raw.py` has spoken JSON-RPC to the connector from a file on
disk since 2026-08-20.

The cost is the smaller half. Retyping is the ONLY step in this pipeline that
can invent content, and on that run it did — an agent paraphrased
`P4C3.5.6.reach_note` from "Both spans establish" to "Two spans establishing".
A two-byte receipt delta was the only thing that caught it, and the substituted
phrasing genuinely exists on a sibling cell, so a reviewer would have read it
as ordinary variation. **A file on disk cannot paraphrase itself.** Every byte
receipt, chunk-boundary check and `emit_part --check` step this skill used to
require exists to detect a failure mode the file path removes.

Measured on the same six pages: the planner produces byte-identical parts
(overview: 39,639 / 39,624 / 34,197 / 14,622 / 23,431) in under a second.

### The order that saves the most

1. `self_heal.py` first — it restates the gates that cost a cycle, over the
   section files, for free. **A submission SUPERSEDES the staged row**, so a
   FAIL on a page that was passing costs that pass and blocks the promote for
   the other five.
2. `--dry-run` next, to see the part plan and the `expect` counts.
3. Submit. On a FAIL, fix the SECTION FILE and resubmit — never loop
   resubmitting until the wording happens to pass.
4. `--promote` only when all six report PASS; promotion is atomic across all
   six and refuses rather than half-succeeding.

### What self_heal.py blocks on, and what it only advises

**Blocking** — each restates a connector gate: `ET-09` (the entity's own name
with a leading article, matched CASE-INSENSITIVELY, which is how three manual
sweeps missed the same twelve strings), `CG-12` face budgets (path-keyed:
`basis` is a chip only under `prerequisites`), `CG-44` (a `peer_median` and a
`delta` with a null `score` — it names the recoverable figure), and unmarked
`r_layer` (redaction is default-deny).

**Advisory** — the sibling-null rule: a field populated on some rows of a list
and null on others. That is how a producer drops a field mid-list, and also how
the contract expresses a tri-state (`deployed` is null on purpose; a peer with
no public filing has no `source_url`). A heuristic never holds a gate it cannot
justify, so a human reads these.
