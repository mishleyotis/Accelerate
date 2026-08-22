"""The contract's own prose must be true, client-neutral, and held once.

`get_page_contract` returns each field's `doc` text and the skill treats it as
part of the contract, not as documentation ("The `doc` text on each field is
part of the contract — for a list-of-object field it is the only place the item
keys are stated"). Every word in it is read by the producer as fact and
calibrates what it writes. That makes the prose an input to synthesis, and it
has to hold to the same standard as anything else this system asserts.

Measured 2026-08-15, auditing the contract against the design docs it was
authored from. Six clauses in the shipped `doc` text carried claims that cannot
be true of this system:

    "32 clients shipped derived rows presented as analyst recommendations"
    "17 clients shipped a sequence contradicting their own roadmap"
    "17 clients did"
    "absent for 138 clients until the exporter was fixed"
    "16 clients had two or fewer events"
    "SunStrong shipped 13 rows for one matter"

This system has TWO promoted clients. The denominators — 138, 93, 32, 17, 16 —
came from the design docs, which carry them throughout, and were copied into
the contract when the fields were authored. In the docs they are inert; in the
contract they are handed to the producer as measurement. Each clause was
removed and its RULE kept, because the rule never needed the number: "provenance
required, never blank" stands on its own and stood on its own before.

The sixth is a different failure. A named third party in a shared contract is
wrong whichever way it resolves — if the name is real it is client information
in a file that ships to every producer, and if it is invented it is a false
measurement wearing a client's name. The dedup rule it illustrated
(`issue_dedup.collapse_issue_rows`) is real and is what remains.

Two assertions here, because the removal alone does not stop the next one:

  1. No contract `doc` text asserts a corpus-scale measurement. A count of
     things this system has never had cannot be evidence for a rule; if a rule
     needs justification it gets the rule, not a denominator.

  2. The two COMMITTED copies of the contract agree byte for byte.
     `apps/mcp/dma_mcp/contracts_data.json` is what `contracts.py` and
     `submit.py` read at runtime; `packages/shared/contracts_data.json` is what
     `infra/deploy.sh` stages into the mcp and worker images and what CI checks.
     Both are committed, neither is generated, and nothing asserted they match
     — so a fix applied to one would validate against one shape and promote
     against another. That is the rule-held-in-two-places class at the highest-
     authority artefact in the connector.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

# The two COMMITTED copies. Both are in git and both are read.
COMMITTED = [
    REPO / "packages" / "shared" / "contracts_data.json",
    REPO / "apps" / "mcp" / "dma_mcp" / "contracts_data.json",
]

# The deploy-staging copies. `apps/*/shared/.gitignore` excludes `*.json` on
# purpose: infra/deploy.sh writes these from packages/shared into each build
# context, so they are build artefacts and are ABSENT in a fresh clone. The
# first version of this test required them and passed locally — where a deploy
# had run — while failing in CI, which is the repo-versus-runtime gap in the
# other direction and precisely what Gate D exists to catch one layer up.
#
# Checked when present, never required: a stale staged copy left behind by an
# interrupted deploy is a real hazard on a developer's machine, and an absent
# one is the normal state everywhere else.
STAGED = [
    REPO / "apps" / "mcp" / "shared" / "contracts_data.json",
    REPO / "apps" / "worker" / "shared" / "contracts_data.json",
]

# The runtime read path (contracts.py: `_HERE / "contracts_data.json"`) and the
# deploy source. If these two disagree, validation and promotion disagree.
RUNTIME = REPO / "apps" / "mcp" / "dma_mcp" / "contracts_data.json"
SOURCE = REPO / "packages" / "shared" / "contracts_data.json"


def _doc_strings(node, path="$"):
    """Every `doc` and `_notes` string in the contract, with its JSON path."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("doc", "_notes") and isinstance(v, str):
                yield f"{path}.{k}", v
            elif k in ("doc", "_notes") and isinstance(v, list):
                for i, s in enumerate(v):
                    if isinstance(s, str):
                        yield f"{path}.{k}[{i}]", s
            else:
                yield from _doc_strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _doc_strings(v, f"{path}[{i}]")


# "<number> clients", "<number> runs", "<number> client packages" — a count of
# entities this system has processed. Bounded to small integers on purpose:
# "851 cells" and "34 sections" are facts about the CATALOGUE and the writer
# registry, not about a corpus of clients, and must keep passing.
_CORPUS_CLAIM = re.compile(
    r"\b\d{1,4}\s+(?:committed\s+)?(?:clients?|runs?|client\s+packages?|"
    r"assessments?|institutions?)\b", re.I)


def test_no_contract_doc_asserts_a_corpus_measurement():
    data = json.loads(SOURCE.read_text())
    offenders = []
    for path, text in _doc_strings(data):
        for m in _CORPUS_CLAIM.finditer(text):
            lo = max(0, m.start() - 60)
            offenders.append(f"{path}: …{text[lo:m.end() + 60].strip()}…")
    assert offenders == [], (
        "contract `doc` text asserts a measurement over a client corpus that "
        "does not exist. The producer reads this as fact and calibrates on it. "
        "Keep the rule, drop the denominator:\n  " + "\n  ".join(offenders))


def test_contract_prose_names_no_client():
    """A third party's name in a shared contract is either confidential or
    fabricated. Both are removals; neither is a rule."""
    data = json.loads(SOURCE.read_text())
    # Names that reached the contract from the design docs' invented corpus.
    # This is a denylist rather than a detector because "no proper noun" would
    # forbid Salesforce, Jack Henry and every vendor the contract must name.
    banned = ["SunStrong", "Zota", "Synovus"]
    offenders = []
    for path, text in _doc_strings(data):
        for name in banned:
            if re.search(rf"\b{re.escape(name)}\b", text, re.I):
                offenders.append(f"{path}: {name}")
    assert offenders == [], (
        "a client name appears in contract text that ships to every "
        "producer:\n  " + "\n  ".join(offenders))


def test_the_runtime_contract_and_the_deploy_source_are_the_same_bytes():
    """What validates a submission and what ships in the image must be one
    file's worth of content, or a repair lands on one side only."""
    assert RUNTIME.exists(), f"{RUNTIME} is the runtime read path and is missing"
    assert SOURCE.exists(), f"{SOURCE} is what deploy.sh stages and is missing"
    if RUNTIME.read_bytes() != SOURCE.read_bytes():
        a, b = json.loads(RUNTIME.read_text()), json.loads(SOURCE.read_text())
        detail = "the JSON parses to different content" if a != b else (
            "the JSON is equivalent but the bytes differ (formatting drift)")
        pytest.fail(
            f"{RUNTIME.relative_to(REPO)} (read by contracts.py at runtime) "
            f"and {SOURCE.relative_to(REPO)} (staged into the image by "
            f"infra/deploy.sh) disagree — {detail}. A contract fix applied to "
            "one validates against one shape and promotes against another.")


@pytest.mark.parametrize("copy", COMMITTED,
                         ids=lambda p: str(p).split("Accelerate/")[-1])
def test_every_committed_copy_agrees(copy):
    assert copy.exists(), f"{copy} is committed and missing"
    assert copy.read_bytes() == SOURCE.read_bytes(), (
        f"{copy.relative_to(REPO)} has drifted from the source at "
        f"{SOURCE.relative_to(REPO)}. Apply the edit to packages/shared and "
        "copy it across, or the connector validates and promotes against "
        "different shapes.")


@pytest.mark.parametrize("copy", STAGED,
                         ids=lambda p: str(p).split("Accelerate/")[-1])
def test_a_staged_copy_left_in_the_tree_is_not_stale(copy):
    if not copy.exists():
        pytest.skip(f"{copy.relative_to(REPO)} is a deploy artefact and is "
                    "absent, which is the normal state outside a deploy")
    assert copy.read_bytes() == SOURCE.read_bytes(), (
        f"{copy.relative_to(REPO)} is a staged copy left over from an earlier "
        f"deploy and no longer matches {SOURCE.relative_to(REPO)}. Re-run "
        "infra/deploy.sh, or delete it — a stale one is what the next local "
        "build would package.")
