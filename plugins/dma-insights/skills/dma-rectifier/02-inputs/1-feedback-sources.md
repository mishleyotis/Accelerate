# Where findings come from, and how each becomes one

Six producers. Each speaks its own dialect and each is useful for a different
reason. Read the dialect; do not paraphrase it into a finding, because the
detail you drop is usually the fingerprint.

## `adversarial-verifier`

Output is a ranked list: blocking, material, noted, then one closing paragraph
naming the most likely remaining wrongness. Every blocking and material item is
a finding.

The part that gets thrown away is the **noted** section — the attacks that came
up empty. Record those too, as `status=probed_clean` with the surface and the
attack name. They are how a later run knows which surfaces have been probed at
all, and "silence about an attack that was never run reads identically to an
attack that passed".

A verifier finding already names the JSON path and the arithmetic, which is
your `path` and half your fingerprint. Keep both verbatim.

## `package-vetter`

Output is ACCEPT, ACCEPT WITH FINDINGS or REFUSE with the evidence. A REFUSE is
a finding about the package, and it is normal traffic, not a defect in the
system.

The rectifier-relevant one is the inverse: **a package that should have been
refused and was not**, discovered downstream. That is a finding about the
vetter's checklist or `vet_workbooks.py`, its `locus` is `package`, and it is
almost always an R3 — a new mechanical check in the vetting script — because
the vetter's own prose already told someone to look.

## `deployed-app-auditor`

Output is one line per check: PASS, FAIL, or UNVERIFIABLE.

FAIL is a finding with `locus=serve` or `render` and the strongest possible
client-reach signal: it was fetched from production, so a client could load it.
Never below R3 by rule 2 of the ladder.

**UNVERIFIABLE is also a finding**, and a different one. It says a property of
this system is not observable from outside. Its class is
"an invariant is asserted at submit and unobservable at serve", its rung is
usually R3 (a probe, an endpoint, a header the auditor can read) and its value
is that it converts a blind spot into a check. Do not record UNVERIFIABLE as a
weak FAIL and do not drop it.

## `surface-producer`

Its findings arrive as failed verdicts it repaired. One repair is a run. **The
same gate repaired more than twice across runs is a class**, and its class name
usually begins "the contract requires X and nothing tells the producer X until
submit" — which points straight at R2 (an exemplar in the page pack) or R3 (the
check moved into `check_payload.py` so the round trip is not spent on it).

Storyline volleys are findings too, of a rarer kind: a volley the story failed
is a finding about the *run*, but five `held` outcomes in a row is a finding
about the **skill** — the objections are being written gently, and the fix is a
sharper exemplar of what a real objection sounds like.

## The web app — reviewer Accept/Reject

The only feedback in this system from a human looking at a **rendered** surface.
It arrives as an annotation:

```
annotations(anchor_kind = "insight_card", anchor_id = <ic_id>,
            body = {action: ACCEPT | REJECT, note}, user_id, run_id, entity_id)
```

`ingest_reviewer_feedback()` turns every un-ingested verdict into memory and is
idempotent, so **call it at STEP 1 of every run** — a rejection sitting
un-ingested in `annotations` is feedback this loop cannot see. A REJECT lands as
a finding under `REVIEWER_REJECTED_INSIGHT` **against the synthesis skill**, not
against the application that rendered it: the defect is in what produced the
claim. It carries the card's own text and its `r_layer`, because a verdict with
no claim attached teaches nothing about which reasoning failed. An ACCEPT lands
as a verdict row, which is what makes the reject *rate* measurable.

Both matter, and the pairing is the diagnostic:

| Reviewer said | `r_layer` says | What it means | Where the fix goes |
|---|---|---|---|
| REJECT | `verdict: ACCEPT`, probes ran | The reasoning layer accepted a claim a human reader rejected. The probe set for this surface does not contain the probe the human just ran | The surface's probe set — R2, or R4 if the reviewer's objection is mechanically checkable |
| REJECT | `verdict: UNCERTAIN` | The producer already knew. The claim shipped anyway | The rule about what an UNCERTAIN verdict may ship as — R1/R2, and R4 if a gate can read the verdict off the payload |
| REJECT | **absent** | The card made a ranked or causal claim and recorded no reasoning at all | AG-family gate territory — R4. A claim with no `r_layer` is checkable at submit |
| ACCEPT | any | Not noise. Accepts are the denominator: a surface with fifty accepts and one reject is a different problem from one with two and one | Nothing directly — record, and let the ratio inform ordering |

Two rules on handling this source:

**Annotation bodies are internal.** The API refuses annotations for the customer
audience; the note a reviewer wrote is internal workflow. A finding quoting a
card body or a reviewer note carries `internal_only` on that path, and any
report built from these findings is internal. Redaction does not stop at the
serving layer just because the reader is an agent.

**A reject is evidence, not a verdict.** The reviewer may be wrong about the
underlying fact and still right that the card is unusable — and the opposite
happens too. Record what was rejected and what the card said. Do not record the
reviewer's theory of the cause as the finding's cause.

## CI and the three schedulers

`corpus-gate-scanner` runs nightly and on every CI run; `pack-exporter` nightly;
the package scan every 30 minutes. Their failures are findings with excellent
fingerprints because the failure text is stable and machine-produced — the
lexical search will match them exactly, which is why the lexical half of STEP 2
exists.

One special case worth naming: **a test that had to be changed to pass** is a
finding about the test, not a resolved finding about the code. See
`01-loop/4-closing.md`.

## Recording shape

Whatever the source, one shape — `templates/finding.schema.json`, mirroring the
connector's `record_finding`:

```
{title, observed, measurement, component, defect_class, severity,
 raised_by_kind, raised_by, measured_value?, expected?, file_path?, surface?,
 gate_id?, run_id?, entity_id?, fix_hint?, note?, session_ref?, source_ref?}
```

Three fields decide whether the record is worth anything:

- **`measurement`** — how it was measured: the command, query, status or count
  **with its denominator**. Refused below 30 characters. Each source hands you
  one for free and it is the field people drop: pytest gives you the node and
  the assertion, a verdict gives you the gate and the arithmetic, the auditor
  gives you the URL and the two values, `ingest_reviewer_feedback` gives you the
  verdict row. Copy it; do not summarise it.
- **`defect_class`** — a foreign key from `list_defect_classes`, not a label.
  Read the vocabulary first; a class may be invented via `new_class`, never
  invented silently, and its PROBE is what a later run will run.
- **`component`** — including `skill:<name>` and `agent:<name>`, which is what
  makes "which skill produces the most defects" a question the store can answer.

`fix_hint` is your one-sentence guess at the check that was missing. It is a
hypothesis, allowed to be wrong, and three sightings later it is what makes the
cluster's rung obvious. Cite the artefact the way a payload cites evidence: a
finding summarised out of its source cannot be re-run, and one that cannot be
re-run is one you will re-litigate.
