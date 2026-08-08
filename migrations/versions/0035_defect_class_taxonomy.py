"""0035 — the defect-class taxonomy, seeded from what this build already paid for.

`memory_findings.defect_class` is a foreign key (0034) so that three agents
filing the same defect cannot file it under three synonyms. A foreign key with
an empty parent table refuses everything, so the vocabulary has to exist before
the first tool call — and it is a vocabulary, not a schema, which is why it is
its own revision rather than a block at the bottom of 0034.

Every class below was extracted from a defect this build actually shipped and
then had to find again. That is the point: the classes are not a taxonomy
someone designed, they are the shapes this system keeps producing.

Each class carries a `tell` and a `probe`, and both are load-bearing:

  * the TELL is what a reader sees when the defect is live. It is the only part
    of a class an agent can match against a symptom it is currently holding —
    "the page is empty but every gate passed" is findable; "field mapping error"
    is not.
  * the PROBE is the command or query that detects it. A class with no probe can
    only ever be rediscovered by accident, which is how most of these were found
    the first time.

Seeded `ON CONFLICT DO NOTHING`: re-running the migration never overwrites a
description someone sharpened, and a class the connector added at runtime (via
`record_finding`'s `new_class`, the only way to invent one) survives untouched.

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-08
"""
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

# (class_id, title, description, tell, probe)
CLASSES = [
    (
        "CONTRACT_FIELD_DISCARDED_AT_PROMOTION",
        "A required contract field is validated at submit and dropped at promotion",
        "The page contract declares a field. Validation checks it and passes. "
        "Promotion has no column to put it in, so the writer drops it on the "
        "floor. Every gate is green and the client sees an empty surface. The "
        "item grain is the usual hiding place: CG-13 only ever swept "
        "SECTION-level fields, so keys declared by an item shape "
        "(`Per issue: {...}`) went unchecked for the whole build.",
        "A surface renders blank, or a chip renders with no figure, on a run "
        "whose submission verdict is a clean pass. No error anywhere; the "
        "verdict names no failing gate.",
        "For each writer binding, resolve the contract's declared keys "
        "(section AND item grain) against the serving table's columns: "
        "`python3 -m pytest apps/mcp/tests/test_field_census.py`. In SQL: "
        "compare information_schema.columns for the serving table against "
        "get_page_contract(page)'s field tuples and item doc text.",
    ),
    (
        "STALE_BUILD_ARTEFACT_SERVED",
        "The server serves a compiled bundle, not the source that was edited",
        "The app serves `apps/web/public/proto/js/*.js`, which are COMPILED "
        "from `apps/web/proto/*.jsx`. Editing the .jsx and reloading changes "
        "nothing, so a fix verified against an unrebuilt bundle is verified "
        "against nothing — and the verification is what makes it dangerous: "
        "the defect is now recorded as fixed.",
        "A change that is definitely in the source has no effect in the "
        "browser, or a bug that was definitely fixed reproduces exactly. "
        "Hard-refresh does not help. The bundle's mtime predates the edit.",
        "Compare mtimes before trusting any browser check: "
        "`ls -l apps/web/proto/<name>.jsx apps/web/public/proto/js/<name>.js`. "
        "If the .js is older than the .jsx, rebuild first; every observation "
        "made before the rebuild is void.",
    ),
    (
        "SILENT_HEADER_ALIAS_DROP",
        "A parser meets a header spelling it does not know and drops the column",
        "The workbook parser matches headers against an alias list. An "
        "unlisted spelling matches nothing, the column is skipped, and the row "
        "count is unchanged — so every count-based check stays green while a "
        "column's worth of meaning is gone. Four separate occurrences in this "
        "build, each found on a rendered page rather than at parse time.",
        "Right row count, green VERIFY lines, and one field empty across every "
        "row. `platform_mapped=0` beside `cells=836` is this class saying so "
        "out loud.",
        "Assert per-column non-null counts after a parse, not just row counts. "
        "`python3 -m pytest apps/worker/tests/test_silent_drop_classes.py`; in "
        "prod read the migrate Job's `VERIFY catalogue ... platform_mapped=` "
        "line and treat 0 as a failure, not a value.",
    ),
    (
        "MATCHER_NORMALISATION_DRIFT",
        "A matcher is rewritten to look for a normalised form and stops matching",
        "A comparison is 'improved' to search for a canonical form — "
        "`headlineOf`'s em-dash `indexOf` is the instance here — while the "
        "data still carries the original. The function keeps returning a "
        "value, so nothing raises; it just returns the wrong one. Behaviour "
        "changes silently and the diff looks like a tidy-up.",
        "A filter, split or lookup that used to match now returns the whole "
        "string, an empty list, or the fallback branch — for every input, not "
        "for edge cases.",
        "Pin the matcher with a test over REAL strings from the corpus before "
        "changing it, including the un-normalised forms. Grep the corpus for "
        "both forms and count: if the normalised form's count is 0, the "
        "matcher can never fire.",
    ),
    (
        "CREDENTIAL_SUBSTITUTION_PROBE",
        "The probe measures the intermediary, not the system under test",
        "Outbound HTTPS in this environment goes through an agent proxy that "
        "substitutes its own credential. `GET /user` answers 200 for an "
        "INVALID token, so a PAT-expiry check run here measures the proxy's "
        "credential and reports the user's as healthy. Two separate agents "
        "reached the same wrong conclusion from it, which is the tell that "
        "this is environmental and not a mistake either of them made.",
        "An auth check passes with a token that should not work — including a "
        "deliberately corrupted one. The response identity does not match the "
        "credential that was sent.",
        "Negative control first: send a deliberately invalid credential. If it "
        "also returns 200, the probe is measuring the proxy and every result "
        "from it is void. Check `curl -sS \"$HTTPS_PROXY/__agentproxy/status\"` "
        "for what the proxy substitutes.",
    ),
    (
        "UNRECOGNISED_INPUT_READS_AS_EMPTY",
        "A reader that does not recognise its input carries on as if it were empty",
        "The distinction between 'this document contains nothing' and 'I could "
        "not read this document' is not made, so an unreadable input becomes "
        "an empty result and flows onward as data. The workbook parser had "
        "twelve of these classes; a whole workbook parsed to nothing with no "
        "line naming which tab.",
        "A zero, an empty list or a null that is indistinguishable from a "
        "legitimate absence. Downstream surfaces render an honest-looking "
        "empty state for material that exists.",
        "Make the reader emit a NAMED refusal per unit it could not read (tab, "
        "sheet, section) and assert the count of refusals is reported, not "
        "just the count of successes. Compare parsed unit count against the "
        "source's unit count and fail on any gap.",
    ),
    (
        "ENUM_FIELD_CARRIES_PROSE",
        "A field the contract types as an enum is written with a sentence",
        "`arc_shape` and the timeline's `kind` were populated with prose. The "
        "value stores fine — the column is TEXT — and then matches no filter, "
        "no legend and no colour rule, so the surface that reads it renders "
        "nothing for that row while the payload looks fully populated.",
        "A filter or legend shows zero of a category that clearly exists in "
        "the data. The stored value is a phrase where the vocabulary lists "
        "single tokens.",
        "Police enum-shaped payload fields at SUBMIT against the contract "
        "vocabulary registry (CG-09), not at read: "
        "`python3 -m pytest apps/mcp/tests/test_contract_vocabularies.py`. In "
        "SQL: `SELECT DISTINCT <col> FROM <table>` and eyeball for anything "
        "with a space in it.",
    ),
    (
        "PROVENANCE_NAMES_THE_TOOL",
        "Evidence records the tool that found it instead of the document",
        "19 evidence rows named the search tool as their source rather than "
        "the artefact the excerpt came from. The row still cites, still has an "
        "excerpt, still passes the fail-closed evidence check — and is "
        "untraceable to anything a client could be shown.",
        "`source_name` or `source_url` reads as a tool, a query or a search "
        "result page rather than a document. Two rows from genuinely different "
        "documents share one source.",
        "`SELECT source_name, count(*) FROM evidence_index GROUP BY 1 ORDER BY "
        "2 DESC` — a source name with an implausible row count is a tool. "
        "Assert source_url resolves to a document, not a search endpoint.",
    ),
    (
        "WRITE_PATH_WITH_NO_READ_PATH",
        "Something is written that nothing can read back",
        "A control exists, a table exists, a grant exists — and no code path "
        "selects from it. The reviewer Accept/Reject pair rendered on every "
        "insight card for the whole build while `annotations` had no reader "
        "anywhere: no API endpoint, no MCP tool, no worker job, and the web "
        "adapter hardcoded `annotation: null`.",
        "A UI control that appears to work and whose effect is never visible "
        "again. A table with an INSERT grant and no query referencing it.",
        "Grep every service for the table name; if the only hits are the "
        "migration and the writer, there is no reader. "
        "`SELECT count(*)` on the table is the second half — a table that is "
        "both unread and empty has never worked at all.",
    ),
    (
        "REVIEWER_REJECTED_INSIGHT",
        "A reviewer rejected a produced claim on its reasoning trace",
        "An analyst pressed Reject on an insight card. The defect is in what "
        "produced the claim — the synthesis skill and the reasoning it "
        "recorded — not in the application that rendered it. The finding "
        "carries the card's own text and its `r_layer`, because a verdict with "
        "no claim attached teaches nothing about which reasoning failed.",
        "A REJECT verdict in `memory_reviewer_verdicts`. Several rejects "
        "sharing a pillar, a claim_label or a shape of r_layer are one skill "
        "problem, not several bad cards.",
        "`SELECT action, count(*) FROM memory_reviewer_verdicts GROUP BY 1` "
        "for the rate, then `list_open_findings(defect_class="
        "'REVIEWER_REJECTED_INSIGHT')` for what was rejected and why.",
    ),
    (
        "UNPROVISIONED_IDENTITY",
        "An authenticated actor has no durable row, so attributable writes refuse",
        "Authentication succeeds and authorisation is held in deploy-time "
        "allowlists, but nothing ever writes the `users` row those grants "
        "imply. Any write that must be attributable then refuses a real, "
        "signed-in person — correctly, which is why it survives so long: the "
        "refusal looks like a working safety check rather than a gap.",
        "A 403 naming the actor rather than the permission — `unknown_actor`, "
        "`no such user` — for someone who is definitely signed in. The user "
        "table has zero rows for people who use the product daily.",
        "`SELECT count(*) FROM users` against the allowlist's length. If the "
        "table is empty and the allowlist is not, every attributable write "
        "path is dead.",
    ),
]


def upgrade() -> None:
    conn = op.get_bind()
    for class_id, title, description, tell, probe in CLASSES:
        conn.exec_driver_sql(
            """INSERT INTO memory_defect_classes
                 (class_id, title, description, tell, probe, created_by)
               VALUES (%s, %s, %s, %s, %s, 'migration:0035')
               ON CONFLICT (class_id) DO NOTHING""",
            (class_id, title, description, tell, probe))
    rows = conn.exec_driver_sql(
        "SELECT class_id FROM memory_defect_classes ORDER BY class_id").fetchall()
    print(f"VERIFY 0035 defect classes={len(rows)}", flush=True)
    for (cid,) in rows:
        print(f"VERIFY 0035 class {cid}", flush=True)


def downgrade() -> None:
    ids = ", ".join(f"'{c[0]}'" for c in CLASSES)
    op.execute(f"DELETE FROM memory_defect_classes WHERE class_id IN ({ids})")
