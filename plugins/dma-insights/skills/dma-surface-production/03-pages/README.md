# Page packs

One file per submission page, numbered in production order. Each carries, per surface: the contract, what must be presented, the information-sources table naming the source of truth per field, and the synthesis prompt.

Produce the heatmap first — its cell linkage is what every other page cites, and the coverage denominators the Overview reports are computed over the cells linked there.

These are reference material rather than a read-through. Open the pack for the page being produced.

`rulebooks/` holds one rulebook per page slug, opened with the page pack and applied by default. Each rulebook (schema D2) is versioned in its title line and carries, per surface anchor:
the Baxter positive pattern (quoted exemplars plus shape notes), the anti-patterns keyed MEM-#### / gate-id, and the surface's exclusion set — the internal-only keys and paths.
The rectifier is the only writer; producers read and never edit; user-flagged entries are marked **PERMANENT — never retire** and outlive every other retirement.

Since W3-4 (QA audit F-E01-026) each `<n>-<page>.md` is the page's index and every
surface lives in `<page>/<ID>.md`; a producer reads its own surface file, the page
index and the gate files its reading order names — about a tenth of the window
instead of a quarter.
