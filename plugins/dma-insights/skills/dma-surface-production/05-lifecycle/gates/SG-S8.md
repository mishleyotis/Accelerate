# SG-S8 · sentiment rests on more than one line

One gate's deep dive, moved out of `../1-gates.md` so a producer reads it when its reading order names `SG-S8` or a verdict does — not the whole book up front (QA audit F-E01-026, 28-09-2026). The family table, the citation stack and *Reading a verdict* stay in `../1-gates.md`; the registry's own wording is `explain_gate("SG-S8")`.

### SG-S8 · sentiment rests on more than one line

**Discloses — it does not block.** A failing SG-S8 still promotes and renders to the client
with its plain label: *"Sentiment rests on a single source, so treat it as indicative only"*.
That is the point. The common misreading of this surface runs the other way — a thin reading
taken as a finding about the institution — so the thinness is stated on the card rather than
hidden by a block.

The count is computed at submit from the rating rows and is **never read from a declared
`displayed_lines`**. A producer stating its own line count is the one input this gate cannot
trust; `displayed_lines` exists for the renderer, not for the gate.

What counts, and what does not:

- Counted: `overview.sentiment.bars[]` and `context.context_sentiment.context_tiles[].rows[]`
  — the same dataset at two depths, counted identically whichever page is submitted.
- **A row with no `rating` is not a line of sentiment.** It is a source you searched, and it
  belongs in the ladder (`sources_searched`), not in the count.
- Three results: `PASS` at two or more rated rows · `FAIL` at one · `NOT_RUN` with the reason
  `no rated rows` when nothing rated was emitted at all.
- **A self-published NPS standing alone is thin whatever the count.** Where every rated row's
  source names NPS, the gate fails regardless of how many there are — one voice about itself,
  repeated, is still one voice.
