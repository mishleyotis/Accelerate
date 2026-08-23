# Verification discipline — what a checker may conclude from a failed lookup

Every agent that CHECKS something reads this before it writes a verdict:
finding-challenger, evidence-integrity-checker, numeric-reconciliation-checker,
exclusion-boundary-auditor, adversarial-verifier, package-vetter.

There is one rule and it is the whole file.

## "I could not look" is never reported as "it is not there"

A lookup that failed produces a verdict about YOUR SEARCH, not about the
claim. Whatever label your report uses for that — `UNTESTED`, `NOT_RUN`,
`COULD_NOT_VERIFY` — it is never the label that means the claim is wrong,
and its `basis` names the exact path, id or query you tried so the next
reader can succeed where you did not.

This is the same rule the payload contract already enforces on producers:
an absence is a documented search with a closure condition, never a blank;
`get_evidence` distinguishes `found` / `not_found` / `foreign`; a
`NOT_RUN` safeguard renders with its reason. Checkers are held to it too,
because a checker that fails open is worse than no checker — it launders a
failed search into an authoritative-looking finding.

### What it cost, measured 2026-08-23

One production session ran two challenge rounds over the same package and
they contradicted each other on every material point.

* The second round called the peer medians in `workbook_scores` FABRICATED.
  It had searched `/home/user/Accelerate` — the repository — while the
  package sat where `drive_fetch.py pull` had put it. Opening the real
  workbook showed `Pillar_Summary!C2:C5`, `Category_Detail!D2:D17` and
  `Peer_Median_Directional` matching the producer's cited values exactly,
  and the `Calculation_Chain` sheet it had dismissed as non-existent was
  there as well.
* It called the caps claims unverifiable for the same reason. The
  workbook's own cap distribution matched the payload exactly.
* Its `unknown_gate` finding on eight `SG-` ids was CORRECT and got argued
  with, because a third document defined ids of the same shape (see
  "Namespaces" below).

The cost was not the wrong verdicts. It was that a reader then had to
adjudicate between two authoritative-sounding reports by opening the files
neither had opened — and a fabrication finding, once written, impeaches a
producer and sends a page back through synthesis.

## Where things actually are

| What | Where | How to resolve it |
|---|---|---|
| The client package | `/root/.dma/packages/<slug>/` — **not** the repo checkout | `package_map.py /root/.dma/packages/<slug>` names both workbooks, every evidence store and every ambiguity |
| Anything inside the package | the same tree, shape varies | `corpus_search.py search --package /root/.dma/packages/<slug> --query '…'` — indexed, PDFs included |
| Resume state and prior artefacts | the client's Drive insights folder | `drive_fetch.py find-artifact --client <display_id> --run <run_id>` (recursive, read-only) |
| A staged or promoted payload | the connector | `get_staged_payload`, `get_report_bundle` |
| Whether an evidence id resolves | the connector | `get_evidence` → `found` / `not_found` / `foreign` |

If a path does not resolve, the slug or the pull is what is wrong. Say that,
in the `basis`, and label the claims untested — the finding is about the
package's availability, which is real and worth reporting, and it is a
different finding from the one you were about to write.

## Namespaces — a definition elsewhere is not counter-evidence

`explain_gate` is the ONLY authority on whether a `gate_id` exists.
`unknown_gate` means it does not, which is a CG-22 violation: an item shaped
like a disclosure that names no real gate belongs in `caps[]`, not `gates[]`.

Several documents in this repository define `SG-`-shaped ids of their own —
an acceptance-criteria list under `apps/web/tests/acceptance/`, synthetic
gate rows in `apps/*/tests/`, and (until 2026-08-23) the dma-research
skill's own batch checks, since renamed to `RS-`. Those are different
namespaces that happened to share a prefix. Finding one is not evidence that
a gate exists; `explain_gate` settles it and nothing else does.

The general form: before you cite a document as authority, check that it is
the authority for THAT vocabulary. The authority order is in `CLAUDE.md`;
for anything the connector evaluates, the connector's own registry wins.
