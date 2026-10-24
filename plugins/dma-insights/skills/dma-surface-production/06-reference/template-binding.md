# Bind to the template, and to the copy the agent wrote last

Moved out of `SKILL.md` on 28-09-2026 (QA audit F-B04-027: the skill file was over 500 lines, and a file nobody can read in one sitting is a file nobody reads). The SKILL.md reading manifest says which phase reads this.

## Bind to the template, and to the copy the agent wrote last

`${CLAUDE_PLUGIN_ROOT}/references/canonical_sources.json` (at the plugin root; `engine.template` reads the template id from it) names the scoring-workbook template, the
Golden 1 CU package as the measured reference, and the shapes known to be
wrong. It is checked in so the answer to "which template?" survives between
sessions and is reviewable in a diff rather than remembered.

```bash
python scripts/check_template.py <workbook.xlsx>    # BEFORE synthesis
python ../../scripts/inspect_client_folders.py --client "<name>"
```

`check_template.py` measures a workbook against the worker's own
`_TAB_TARGET` — 29 tabs, each bound to the surface it feeds — and prints
which are missing or empty **and what starves as a result**. It imports that
map rather than copying it: a second copy of the list here would be wrong the
first time the app changed.

A template is not correct because it is named "template". Measured 2026-09-03:

| Workbook | tabs | read-tabs with data |
|---|---|---|
| Golden 1 CU (the reference) | 43 | **28 of 29** |
| Bank of Travelers Rest — assessment | 20 | 11 of 29 |
| Bank of Travelers Rest — scoring (research v5) | 23 | 13 of 29 |

BOTR's two workbooks are COMPLEMENTARY — one holds `Firmographics`,
`Focus_Areas`, `Issue_Register`, `Subcap_Scores`; the other holds
`Entity_Timeline`, `Tech_Register`, `Report_Narrative`, `Provenance`.
Together ~26 of 29; separately 11 and 13. That is what binding to a split,
older template produces, and it is why eighteen of that entity's nineteen
runs landed with zero scored cells while the scores sat in a sibling file.

### One workbook and one report per client folder

`inspect_client_folders.py` reports VERSIONS, STALE PICK, DUPLICATES and
EMPTY PICK from the live tree. On BOTR it found four workbooks at three
depths in one folder, three byte-identical, with the scan reading neither the
newest nor the one with scores.

The scan now defends itself — copy directories (`memory-backup/`, `archive/`,
`old/` and siblings) are excluded, equal-ranked candidates break the tie on
**modified time** rather than filename, and a ranked workbook stating no
scored cell falls through to a sibling that has them. None of that makes the
copies harmless: a producer should still leave exactly one workbook and one
report in the client folder, and put working copies outside the intake tree.
