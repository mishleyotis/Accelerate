"""The DMA research engine: the workbook is the substrate, not an export.

AUD-0001 measured the root defect this package answers: zero research steps
touched a sheet, and the workbook had exactly one producer that built a fresh
`Workbook()` and saved it once at the end, from a parallel JSON plane. Every
mid-run mechanism the architecture assumes — agents recording as they go,
chain integrity reconciling live, a resume anchored on the workbook,
governance auditing the same object the agents wrote — is impossible while
that is true.

So here the workbook IS the record. `workbook.py` is the only writer; every
other module goes through it. A JSON file may be a cache or a report, never
an interface.

Module map
    contract.py   the shape and the counts, computed from the catalogue
    workbook.py   the substrate: open, append, read, atomic save
    runstate.py   $RUN, the checkpoint, and what survives a dead container
    ledger.py     append records; `stats` (which used to raise NameError)
    orient.py     the session opener: state, do_first, next card
    floors_gate.py the gate — and it writes where orient reads
    validator.py  the seven contract rules, each with a test that fires it
    handoff.py    the research -> assessment handoff, from the workbook
    reports.py    the two client-facing reports, curated from the workbook
    watchdog.py   a research run that has stopped says so
"""
