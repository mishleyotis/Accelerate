# Where you record, and when your page can ship

Moved out of `SKILL.md` on 28-09-2026 (QA audit F-B04-027: the skill file was over 500 lines, and a file nobody can read in one sitting is a file nobody reads). The SKILL.md reading manifest says which phase reads this.

## Where you record, and when your page can ship

Two vocabularies meet here. An assessment agent writes into workbook **tabs**;
the connector accepts page **sections**. Nothing joined them, so an agent
filling `Entity_Timeline` had no way to know it was the only input to the
context page's timeline, and no way to know that finishing it made a page
submittable. That is why ingestion was an afterthought: you cannot submit as
you go if you cannot tell what "done" means for one page.

`${CLAUDE_PLUGIN_ROOT}/references/tab_recording_map.json` is that join, GENERATED from the worker's
own `_TAB_TARGET` and the live page contracts — never hand-written, because a
hand-written map is one refactor away from being confidently wrong.

| Workbook tab | Page section it feeds | Binding |
|---|---|---|
| `Issue_Register` | `platform.stairstep` | proposed |
| `Recommendations` | `platform.recommendations` | verified |
| `Solution_Catalogue` | `platform.platform_story` | proposed |
| `Platform_Peer_Adoption` | `techstack.techstack` | verified |
| `Tech_Peer_Deployments` | `techstack.techstack` | verified |
| `Tech_Register` | `techstack.techstack` | verified |
| `Technographic_Scan` | `techstack.techstack` | verified |

29 tabs are read in all: 13 feed a
page, and the remaining 10 are run config, provenance and gate
logs that feed no client surface — the parser marks those
`not_client_facing`, so their absence from the table is not a gap.

**Read the Binding column literally.** Only 5 of the 29 mappings are
marked `verified` — checked field by field against `get_page_contract`.
14 are `proposed`: read off the tab's shape and not
yet confirmed. A `proposed` binding is a good guess about where your work
lands, not a promise, and it is worth confirming against the contract
before you rely on it.

### Ship as you go

```bash
python scripts/ship_page.py <run_id> all --sections sections/ --incremental
```

Run it after every producer returns. It asks the contract which sections each
page REQUIRES, ships every page that has them, and names what the rest are
waiting on. A page already passing is simply resubmitted with the same
content, so re-running is free.

The connector RETAINS staged rows, so five pages can sit staged and passing
while the sixth is still being produced. **Promotion stays atomic across all
six** — staging is not serving, and no client sees a half-built run. What
moves earlier is validation, gate refusals and the byte cost of transport, to
where a producer can still act on them cheaply. When the last producer
returns, the sixth page ships and the run promotes: the client page is live as
the assessment ends, not as a separate exercise afterwards.
