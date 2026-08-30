"""ET-09 — another client's name in this client's prose.

ET-01 halts a citation that resolves to another institution's row. It sees
nothing when the contamination never cites, and that is the route that
actually occurred: MEM-0023, two concurrent sessions sharing one scratchpad
path, a producer analysing another client's bundle for twenty-two minutes.
Every id it cited would have been the other client's — but the sentences it
wrote from the same read are invisible to every gate in this connector.

The distinctiveness floor is not a guess. Measured over the 113 distinct
entity names in the intake tree on 2026-08-14: 111 carry two or more words,
exactly one is under eight characters, and ZERO are composed entirely of
generic banking tokens. The false-positive tests below are that measurement
turned into assertions — they are the half that decides whether a BLOCKING
gate can be trusted to run unattended at 03:00.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import _check_foreign_entity_prose, _norm_name

THIS_RUN = "11111111-1111-1111-1111-111111111111"


class _Cur:
    """Answers the two statements the gate issues, and refuses anything else
    so a third source added later is a test error, not a silent wrong pass."""

    def __init__(self, others, peers):
        self.others, self.peers, self._out = others, peers, []

    def execute(self, sql, params=None):
        if "FROM entities" in sql:
            self._out = [(n, None) for n in self.others]
        elif "peer_scores" in sql:
            self._out = [(p,) for p in self.peers]
        else:
            raise AssertionError("unmodelled statement:\n" + sql)

    def fetchall(self):
        return self._out


class _Conn:
    def __init__(self, others=(), peers=()):
        self._c = _Cur(list(others), list(peers))

    def cursor(self):
        return self._c


def _run(payload, others=("Odlum Brown Limited", "Baxter Credit Union"),
         peers=()):
    return _check_foreign_entity_prose(_Conn(others, peers), THIS_RUN, payload)


# ── the defect ────────────────────────────────────────────────────────
def test_another_clients_name_in_prose_is_refused():
    out = _run({"overview": {"exec_summary": {
        "body": "The institution trails Odlum Brown Limited on data maturity."}}})
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "ET-09" and r["severity"] == "block"
    assert r["section"] == "overview"
    assert "Odlum Brown Limited" in r["message"]
    assert "contamination" in r["message"]


def test_it_fires_with_nothing_cited_at_all():
    """The whole point: this contamination carries no e_ids, so a gate that
    only runs when something was cited would never see it."""
    out = _run({"context": {"sentiment": {"note": "Baxter Credit Union's "
                                                  "members report delays."}}})
    assert [x["gate_id"] for x in out] == ["ET-09"]


def test_it_reads_nested_items_not_only_top_level_strings():
    out = _run({"techstack": {"techstack": {"items": [
        {"name": "Core", "dma_impact": "Deployed the same year as "
                                       "Odlum Brown Limited."}]}}})
    assert len(out) == 1
    assert "items[0].dma_impact" in out[0]["path"]


def test_punctuation_and_case_do_not_hide_the_name():
    out = _run({"overview": {"s": {"t": "odlum   brown\nlimited settled it."}}})
    assert len(out) == 1


def test_one_reason_per_section_and_name_not_one_per_sentence():
    """A producer that read the wrong bundle writes the name everywhere. The
    verdict has to be readable, and the repair is the same one either way."""
    body = {f"k{i}": "Odlum Brown Limited did." for i in range(20)}
    out = _run({"overview": {"s": body}})
    assert len(out) == 1


# ── the false-positive controls, which decide whether it may block ────
def test_a_peer_recorded_for_this_run_is_not_contamination():
    """Peers are named legitimately, all over the payload. The exclusion is
    read from `peer_scores` — server-side truth — never from the payload's
    own claims, because a payload naming its own exculpation is not
    evidence."""
    out = _run({"overview": {"s": {"t": "Ahead of Odlum Brown Limited."}}},
               peers=["Odlum Brown Limited"])
    assert out == []


def test_a_peer_match_survives_punctuation_differences():
    out = _run({"overview": {"s": {"t": "Behind Odlum Brown, Limited."}}},
               peers=["odlum brown limited"])
    assert out == []


def test_generic_banking_phrases_never_match():
    """Zero of the corpus's 113 names are composed entirely of generic
    tokens, so no real name is lost by refusing to match on them — and the
    phrases below appear in ordinary prose on every single run."""
    prose = ("The first national bank in the state, a community credit union "
             "and a mutual insurance company all trust the same core.")
    for name in ("First National Bank", "Community Credit Union",
                 "Mutual Insurance Company", "The Trust Company"):
        assert _run({"overview": {"s": {"t": prose}}}, others=[name]) == [], name


def test_a_short_or_single_word_name_is_not_matched():
    """AAFCU (5 chars) is the one corpus name under the floor. Matching it
    would fire on any acronym in any sentence; the gap is deliberate and
    stated rather than silently absent."""
    assert _run({"overview": {"s": {"t": "AAFCU and ACME reported."}}},
                others=["AAFCU"]) == []


def test_a_distinctive_single_word_name_IS_matched():
    """Bridgecrest — one word, eleven characters. The floor admits it, which
    is why the single-word rule is a length rule and not an exclusion."""
    out = _run({"overview": {"s": {"t": "Bridgecrest runs the same stack."}}},
               others=["Bridgecrest"])
    assert len(out) == 1


def test_a_substring_of_a_longer_word_is_not_a_match():
    """Word boundaries: `Mercury` must not match `Mercurial`."""
    assert _run({"overview": {"s": {"t": "A mercurial rollout."}}},
                others=["Mercury Financial"]) == []


def test_the_runs_own_entity_is_never_flagged():
    """The query excludes it in SQL; this pins that the payload naming its
    OWN client — which every payload does, constantly — is silent."""
    assert _run({"overview": {"s": {"t": "Acme Bank of Nowhere grew."}}},
                others=[]) == []


def test_a_corpus_read_that_fails_does_not_block_the_run():
    """A gate that cannot read its corpus must not pass silently OR block a
    run on a transient read. It returns nothing and ET-01 still covers the
    cited route — stated in the code, pinned here."""
    class _Boom:
        def cursor(self):
            raise RuntimeError("connection reset")
    assert _check_foreign_entity_prose(_Boom(), THIS_RUN, {"overview": {}}) == []


def test_non_string_and_tiny_values_are_skipped_without_error():
    out = _run({"overview": {"s": {"n": 4, "b": True, "z": None, "t": "ok",
                                   "l": [1, 2], "d": {"x": "Odlum Brown "
                                                           "Limited"}}}})
    assert len(out) == 1


def test_norm_name_is_the_one_normaliser_both_sides_use():
    """Peer exclusion and name matching must normalise identically, or a
    peer written with a comma stops excluding and the gate blocks a correct
    run. One function, asserted on both shapes."""
    assert _norm_name("Odlum Brown, Limited.") == _norm_name("odlum brown limited")
