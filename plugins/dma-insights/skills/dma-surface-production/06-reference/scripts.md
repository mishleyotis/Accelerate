# Scripts

Moved out of `SKILL.md` on 28-09-2026 (QA audit F-B04-027: the skill file was over 500 lines, and a file nobody can read in one sitting is a file nobody reads). The SKILL.md reading manifest says which phase reads this.

## Scripts

Run these rather than eyeballing — they are faster and they do not get tired.

```bash
python scripts/ship_page.py <run> <page|all> --sections DIR [--promote]
                                                    # assemble, plan, submit from DISK.
                                                    # The only supported way to move a
                                                    # payload — see the section above for
                                                    # what retyping one cost and what it
                                                    # invented
python scripts/self_heal.py --sections DIR --page <page> --entity "<legal name>"
                                                    # the gates that cost a cycle on a real
                                                    # run, replayed locally for free:
                                                    # ET-09 (case-insensitive), CG-12 face
                                                    # budgets, CG-44 empty bars, unmarked
                                                    # r_layer. Blocking vs advisory
python scripts/preflight.py --run-id <uuid>        # where the run stands, what is blocking
python scripts/check_payload.py <payload.json> --page <page> \
       --subvertical <CODE> --cells <bundle.json>
                                                    # local checks before you submit:
                                                    # required fields, budgets, id patterns,
                                                    # internal_only marking, empty states.
                                                    # --subvertical turns ET-05 ON and
                                                    # --cells turns CG-14 ON; without them
                                                    # those two print "not run", which is
                                                    # not a pass
python scripts/check_repetition.py <drafts.json> --page <page> --at-scale 708
                                                    # BEFORE you write the 21st item of a
                                                    # large array, not before submit:
                                                    # CG-15's template rule compares items
                                                    # against each other, so no per-item
                                                    # check can see it, and the shape that
                                                    # refuses 708 cells is visible in 20
python scripts/score_prompt.py <prompt.txt>        # score a prompt you have written
                                                    # against the 14-attribute standard
python scripts/check_language.py <payload.json>    # accusatory framing, fields that OPEN on
                                                    # an absence, gap statements with no
                                                    # adjacent asset, lost capitals
python scripts/check_evidence.py <get_evidence.json> --review
                                                    # the evidence register, not a page:
                                                    # one excerpt under two hosts, a
                                                    # source_url that is not a document,
                                                    # a search page, a tool cited as a source
python scripts/clay_plan.py --domain <domain>      # the enrichment call sequence and the
                                                    # tier each data point registers at
python scripts/check_consistency.py <rundir>/     # <rundir> holds <page>.json plus
                                                    # bundle.json (get_report_bundle),
                                                    # catalogue.json, fit.json; the
                                                    # sub-vertical binding is READ from the
                                                    # bundle (MEM-0559), never typed.
                                                    # cross-page reconciliation before
                                                    # promotion — the check no per-page
                                                    # gate can make: foreign variant cells,
                                                    # silent drawers, coverage denominators,
                                                    # the run's one constraint, and the
                                                    # RC-10/RC-12 invariants (factor sums,
                                                    # O5 = P1 = engine, tile states, area
                                                    # tabs, candidate set, stair-step order,
                                                    # one thin definition, H6 completeness,
                                                    # O6/O7 counts, the identified peer set)
python scripts/precheck_gates.py <payload.json> --page <page> \
       --evidence <get_evidence.json> --bundle <get_report_bundle.json>
                                                    # the connector's own blocking gates,
                                                    # run locally: ET-01/ET-04 citations,
                                                    # CG-10 dating, ET-05 sub-vertical
                                                    # scope, CG-14 cell linkage
```

`check_payload.py` catches the cheap failures locally so your submissions spend their
round trips on the expensive ones — grain, identity and grounding, which only the server
can check.

`check_repetition.py` runs at a different moment from all the others: **while you are
still deciding how to write, not after you have written**. CG-15 refuses three or more
items of one field that share both their phrasing and their content words, so it is a
property of the ARRAY and invisible inside any single item — on 2026-08-08 two producers
met it at submit, one of them having already built all 708 heatmap cells. Twenty drafts
are enough to see it. The promoted Baxter run's 706 cell syntheses score 0.179 against a
line of 0.40, so a 700-cell page is demonstrably writable; if yours is refused, the shape
is the problem and not the scale. `03-pages/heatmap/H2.md` says what to change.

`precheck_gates.py` sits between the two, and it exists because a submission is not
free. Submitting supersedes the staged row, so a FAIL on a page that was passing costs
you the pass until you repair it — and inside a promotion window, that blocks the
promote for every other page too. The gates it runs need the run's own facts (which
evidence rows exist and what they carry, which cells the run serves) but not a database,
so two tool calls you have already made are enough: `get_evidence` for every id the page
cites — `--list-cited` prints them so one call covers the page — and `get_report_bundle`.

It imports the connector's gate modules rather than restating them. A second copy of a
gate is a second answer to the same question, and the answer that matters is the
server's.

Run it on a page you did not write, too. The heatmap promoted on the run this was
written for returned **120 blocking reasons** when first checked this way: 79 foreign
sub-vertical cells sitting inside focus-area cell lists, 11 alerts naming cells the run
does not carry, 28 evidence rows whose stored excerpt cannot be cited, 2 lowercase
openings. A page that passed under an older gate set is not a page that passes now, and
finding that out from this costs nothing.
