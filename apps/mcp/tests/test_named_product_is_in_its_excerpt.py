"""CG-50 — the product a techstack row names appears in the span it cites.

MEM-0129, BLOCKER. A producer read a truncated excerpt, reached past the cut
into the scan summary it remembered, and named nine products the citable
spans do not contain. Substring-testing all fourteen against their own cited
excerpts: NINE present in zero of them, five confirmed. Repairing the
register against that test took it from 41 rows to 27, CONFIRMED from 9 to 3,
and removed the run's entire security-tooling incumbency story — a story that
had never been there.

The finding's own fix_hint made this a PRODUCER HABIT: *"substring-test every
product name against its own stored excerpt before citing it, and never rely
on source_name or on recollection of what the scan found."* A habit is not a
control. It was written on 2026-08-21 and a run promoted the next day with
95% of its client-facing evidence clipped, because nothing checked.

The fourteen products below are the measured population, and the split
between them is the fixture: they are what this gate has to get right.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dma_mcp.validation2 as V2                        # noqa: E402
from dma_mcp.validation2 import _distinctive_tokens     # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3]
                       / "packages" / "shared"))
from excerpt_clip import CLAUSE_CLIP_WIDTH              # noqa: E402

W = CLAUSE_CLIP_WIDTH

#: MEM-0129's measurement. Nine present in zero of their own cited excerpts.
NAMED_BUT_UNSUPPORTED = ["Splunk", "Cortex XSOAR", "Ping Identity",
                         "Azure MFA", "ServiceNow", "Proofpoint", "GCP",
                         "Snowflake", "Prometheus"]
#: Five that survived the same test.
NAMED_AND_SUPPORTED = ["CrowdStrike Falcon", "Palo Alto NGFW",
                       "SailPoint IdentityIQ", "Financial Services Cloud",
                       "Marketing Cloud"]


# ── a conn that answers only what the gate asks of it ─────────────────

class FakeCur:
    def __init__(self, store):
        self.store = store

    def execute(self, sql, params=None):
        self._last = (sql, params)

    def fetchone(self):
        return None


class FakeConn:
    """The gate resolves ids through evidence_tools; the tests substitute the
    resolver rather than a database, so what is exercised is the GATE and not
    a stub of Postgres."""
    def cursor(self):
        return FakeCur({})


@pytest.fixture
def store(monkeypatch):
    """{e_id: excerpt or None}. None means 'the row resolves and carries no
    excerpt' — a different outcome from 'does not resolve', which is the
    distinction this gate exists to keep."""
    data: dict = {}
    monkeypatch.setattr(V2, "clip", V2.clip)

    import dma_mcp.evidence_tools as ev
    monkeypatch.setattr(ev, "_run_scope",
                        lambda conn, run_id: {"entity_id": "ent-1",
                                              "token": "X", "run_seq": 1})

    def fake_resolve(cur, cited, scope):
        key = str(cited).split(":")[0]
        if key not in data:
            return None, True                    # does not resolve at all
        return ("e", "ent-1", "src", "u", data[key],
                "FACT", "T1", None, "CURRENT", 4.0, "AGENT"), True

    monkeypatch.setattr(ev, "_resolve", fake_resolve)
    return data


def run(items, **_):
    return V2._check_named_product_is_in_its_excerpt(
        FakeConn(), "run-1", "techstack", {"techstack": {"items": items}})


def row(product, e_ids, vendor=None, status="CONFIRMED", **extra):
    return {"ts_id": "TS-001", "product": product, "vendor": vendor,
            "status": status, "e_ids": list(e_ids), **extra}


def cut(name: str) -> str:
    """A clause hard-clipped at the measured width, with `name` falling PAST
    the cut — which is the whole mechanism of MEM-0129. The producer saw the
    scan summary, the store kept only the first 140 characters, and the name
    the row asserts is in the part that was thrown away."""
    lead = ("The technographic scan of the estate returned a long inventory "
            "covering identity, monitoring, orchestration and mail security "
            "across every operating region of the business, and it named ")
    body = (lead * 3)[:W - 6] + "identi"
    assert len(body) == W and body[-1].isalnum()
    assert name.lower() not in body.lower(), \
        "the fixture must put the name past the cut, or it proves nothing"
    return body


# ── the measured population ───────────────────────────────────────────

@pytest.mark.parametrize("product", NAMED_BUT_UNSUPPORTED)
def test_a_product_absent_from_its_own_excerpt_is_refused(store, product):
    store["E-1"] = ("The firm operates a security operations centre staffed "
                    "around the clock and reports no material incidents in "
                    "the period under review.")
    out = run([row(product, ["E-1"])])
    assert [r["gate_id"] for r in out] == ["CG-50"], product
    assert "appears in none of the 1 excerpt(s)" in out[0]["message"]


@pytest.mark.parametrize("product", NAMED_AND_SUPPORTED)
def test_a_product_its_excerpt_names_passes(store, product):
    """A LIMITATION STATED RATHER THAN HIDDEN: "Financial Services Cloud" and
    "Marketing Cloud" are entirely generic words, so they carry no
    distinctive token of their own and cannot be corroborated BY NAME. Only
    the vendor can corroborate them, which is why the excerpt here names it.
    That is the honest reach of a token test and the reason the vendor is
    part of the match rather than an afterthought."""
    store["E-1"] = (f"The 2026 filing states the firm deployed Salesforce "
                    f"{product} across its operating regions this year.")
    assert run([row(product, ["E-1"], vendor="Salesforce")]) == [], product


def test_the_split_reproduces_mem_0129s_measurement(store):
    """Fourteen rows, one excerpt each, built so that exactly the nine
    measured as unsupported are unsupported. The gate must find nine — not
    fourteen, which would mean it refuses everything, and not zero."""
    items = []
    for i, product in enumerate(NAMED_BUT_UNSUPPORTED):
        store[f"E-U{i}"] = ("A quarterly report describing headcount and "
                            "branch footprint, naming no technology.")
        items.append(row(product, [f"E-U{i}"]))
    for i, product in enumerate(NAMED_AND_SUPPORTED):
        store[f"E-S{i}"] = (f"The report names Salesforce {product} in "
                            f"production use.")
        items.append(row(product, [f"E-S{i}"], vendor="Salesforce"))
    out = run(items)
    assert len(out) == len(NAMED_BUT_UNSUPPORTED) == 9, [r["message"][:60]
                                                         for r in out]


# ── a clipped store and a wrong row need different fixes ──────────────

def test_a_clipped_excerpt_sends_you_to_the_store_not_the_row(store):
    """The whole causal chain in one test. If the name is missing AND the
    excerpt is a hard clip, rewriting the row is the WRONG fix — it would
    drop a product the client may really run."""
    store["E-1"] = cut("Splunk")
    out = run([row("Splunk", ["E-1"])])
    assert len(out) == 1
    r = out[0]["message"]
    assert "HARD CLIP" in r
    assert "re-ingest" in r
    assert "Fix the STORE, not the row" in r


def test_an_untruncated_excerpt_sends_you_to_the_row(store):
    store["E-1"] = ("A complete sentence, ending properly, that does not "
                    "mention the product in question at all.")
    out = run([row("Splunk", ["E-1"])])
    assert "none of those excerpts is truncated" in out[0]["message"]
    assert "dropped[]" in out[0]["message"]
    assert "HARD CLIP" not in out[0]["message"]


def test_the_two_fixes_are_never_offered_at_once(store):
    for excerpt in (cut("Splunk"), "A clean sentence about staff."):
        store["E-1"] = excerpt
        r = run([row("Splunk", ["E-1"])])[0]["message"]
        assert ("HARD CLIP" in r) != ("none of those excerpts is truncated" in r)


# ── "could not look" is its own outcome ───────────────────────────────

def test_a_row_whose_ids_resolve_with_no_excerpt_is_refused_distinctly(store):
    """Not passed. MEM-0129's nine looked exactly like rows that had passed,
    and that is the whole reason this is a refusal and not a shrug."""
    store["E-1"] = None
    out = run([row("Splunk", ["E-1"])])
    assert len(out) == 1
    assert "carrying NO excerpt" in out[0]["message"]
    assert "could not be checked at all" in out[0]["message"]
    assert "appears in none of" not in out[0]["message"]


def test_an_id_that_does_not_resolve_is_left_to_et_04(store):
    """Two gates reporting one absence makes a verdict list nobody reads."""
    assert run([row("Splunk", ["E-NOPE"])]) == []


def test_a_row_with_no_citations_is_not_this_gates_business(store):
    """The contract routes an uncitable item to dropped[]; CG-02 and the
    contract own that, not this gate."""
    assert run([row("Splunk", [])]) == []
    assert run([{"product": "Splunk", "status": "CONFIRMED"}]) == []


# ── matching that does not cry wolf on correct work ───────────────────

def test_a_partial_product_name_in_the_excerpt_corroborates_it(store):
    """A real excerpt says "Financial Services Cloud" where the row says
    "Salesforce Financial Services Cloud". Refusing that would be a false
    positive on correct work, which is how a gate teaches people to fight
    it."""
    store["E-1"] = ("The bank's 2026 investor day names Financial Services "
                    "Cloud as the system of record for advice.")
    assert run([row("Salesforce Financial Services Cloud", ["E-1"],
                    vendor="Salesforce")]) == []


def test_the_vendor_corroborates_a_product_whose_name_is_all_generic(store):
    """"Core Banking Platform" has no distinctive token of its own. The
    vendor is what identifies it."""
    store["E-1"] = "A press release states the firm runs Fiserv for deposits."
    assert run([row("Core Banking Platform", ["E-1"], vendor="Fiserv")]) == []


def test_a_generic_word_alone_never_corroborates(store):
    """The gate would be decorative if "Cloud" counted — it appears in every
    second vendor's catalogue."""
    store["E-1"] = "The firm is pursuing a cloud platform strategy this year."
    out = run([row("Snowflake Data Cloud", ["E-1"], vendor="Snowflake")])
    assert [r["gate_id"] for r in out] == ["CG-50"]


def test_any_one_of_several_cited_excerpts_is_enough(store):
    store["E-1"] = "A filing about branch closures."
    store["E-2"] = "A job posting seeking a Snowflake platform engineer."
    assert run([row("Snowflake", ["E-1", "E-2"])]) == []


def test_matching_is_case_insensitive(store):
    store["E-1"] = "the vendor SERVICENOW was selected after a review."
    assert run([row("ServiceNow", ["E-1"])]) == []


# ── ABSENT rows are exempt, deliberately ──────────────────────────────

def test_an_absent_row_is_exempt(store):
    """Evidence of absence rarely names the absent product, and refusing
    these rows would push a producer to DELETE honest ABSENT rows rather than
    record them — trading a documented gap for a silent one."""
    store["E-1"] = ("A review of the firm's published architecture finds no "
                    "reference to any orchestration tooling.")
    assert run([row("Cortex XSOAR", ["E-1"], status="ABSENT")]) == []


@pytest.mark.parametrize("status", ["CONFIRMED", "INFERRED", "CLAIMED"])
def test_every_other_status_is_checked(store, status):
    store["E-1"] = "A filing that names no technology whatsoever."
    assert [r["gate_id"] for r in run([row("Splunk", ["E-1"], status=status)])] \
        == ["CG-50"], status


# ── the tokeniser ─────────────────────────────────────────────────────

@pytest.mark.parametrize("name,expect", [
    ("Salesforce Financial Services Cloud", ["Salesforce"]),
    ("Core Banking Platform", []),
    ("Marketing Cloud", []),
    ("Cortex XSOAR", ["Cortex", "XSOAR"]),
    ("GCP", ["GCP"]),
    ("Palo Alto NGFW", ["Palo", "Alto", "NGFW"]),
    ("", []),
    (None, []),
])
def test_distinctive_tokens(name, expect):
    assert _distinctive_tokens(name) == expect


def test_a_two_character_fragment_cannot_carry_identity():
    """It would match almost any prose."""
    assert _distinctive_tokens("AI") == []
    assert _distinctive_tokens("SAP") == ["SAP"]


# ── the verdict earns its keep ────────────────────────────────────────

def test_the_verdict_names_the_path_the_tokens_and_the_ids(store):
    """Invariant 12: a verdict names the gate, the JSON path and the
    arithmetic. Here the arithmetic is what was searched for and where."""
    store["E-1"] = "A filing about staffing."
    store["E-2"] = "Another about premises."
    r = run([row("Splunk", ["E-1", "E-2"])])[0]
    assert r["gate_id"] == "CG-50"
    assert r["path"] == "techstack.techstack.items[0]"
    assert "Splunk" in r["message"]
    assert "E-1" in r["message"] and "E-2" in r["message"]
    assert "2 excerpt(s)" in r["message"]


def test_the_verdict_says_why_a_generic_word_was_ignored(store):
    store["E-1"] = "A cloud platform strategy, named as such."
    r = run([row("Snowflake Data Cloud", ["E-1"], vendor="Snowflake")])[0]
    assert "generic words that identify nothing" in r["message"]


# ── scope ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("page", ["overview", "platform", "heatmap",
                                  "context", "insights"])
def test_only_the_techstack_page_is_checked(store, page):
    store["E-1"] = "Names nothing."
    assert V2._check_named_product_is_in_its_excerpt(
        FakeConn(), "run-1", page,
        {"techstack": {"items": [row("Splunk", ["E-1"])]}}) == []


def test_a_malformed_payload_is_not_this_gates_problem(store):
    for bad in (None, [], "x", {"techstack": None}, {"techstack": {}},
                {"techstack": {"items": "x"}}, {"techstack": {"items": [1]}}):
        assert V2._check_named_product_is_in_its_excerpt(
            FakeConn(), "run-1", "techstack", bad) == []


def test_the_gate_is_wired_into_the_submit_path():
    import inspect
    src = inspect.getsource(V2)
    assert "_check_named_product_is_in_its_excerpt(\n        conn, run_id, " \
           "page, payload)" in src, "the gate exists but nothing calls it"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
