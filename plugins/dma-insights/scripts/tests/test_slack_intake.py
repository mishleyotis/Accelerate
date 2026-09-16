"""The queue comes out of #deal-desk, and the expensive mistake is a false
PENDING.

WHY THESE EXIST. The intake Routine fired hourly and scanned Google Drive —
the wrong flow, at the wrong cadence, for a queue that arrives in Slack. The
owner's rule has one subtle edge and these tests are mostly about it:

    DELIVERED is a reply FROM THE OWNER that CARRIES A DRIVE FOLDER LINK.

Not "the owner replied" — the real Richwood thread has a reply from the owner
saying "Let me retrieve it from my desktop", which is not a delivery. Not
"somebody replied" — the real REV thread's only reply is a colleague's FYI.
Not "there is a drive.google.com link" — the Hubbl workflow posts one in its
own request, in the same channel, for a different person's queue.

Every fixture under tests/slack/ is a RECORDING of what the connector
returned on 2026-08-30, not a construction, because the connector returns a
rendered text format of its own and a fixture written from the API docs would
be a fixture of a shape nobody sends.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = HERE / "slack_intake.py"
FIX = pathlib.Path(__file__).resolve().parent / "slack"
sys.path.insert(0, str(HERE))
import slack_intake as SI                                    # noqa: E402

NOW = SI.datetime(2026, 8, 30, tzinfo=SI.timezone.utc)


def _channel() -> str:
    return (FIX / "channel.txt").read_text()


def _threads() -> dict:
    return SI._load_threads(str(FIX))


def _by_account(out, name):
    return next(r for r in out["requests"] if r["account"] == name)


# ── the rule, over the real recordings ───────────────────────────────────

def test_the_owners_reply_with_a_folder_link_is_delivery():
    out = SI.triage(_channel(), _threads(), since_days=30, now=NOW)
    row = _by_account(out, "Richwood Bank")
    assert row["state"] == SI.DELIVERED, row
    assert row["folder_id"] == "1V5aG3cvov1lgBkA3yL4wGwBs8UgedgWq"


def test_a_reply_from_somebody_else_is_not_delivery():
    """REV FCU's only reply is a colleague's 'FYI @Andrew'. A request with a
    reply is not a request that was answered."""
    out = SI.triage(_channel(), _threads(), since_days=30, now=NOW)
    row = _by_account(out, "REV Federal Credit Union")
    assert row["state"] == SI.PENDING, row
    assert "folder link" in row["why"]


def test_the_owner_replying_without_a_link_is_not_delivery():
    """The real Richwood thread carries one: 'Let me retrieve it from my
    desktop.' Presence is not delivery."""
    thread = SI.parse_thread((FIX / "thread_richwood_delivered.txt").read_text())
    only_prose = {"parent_ts": thread["parent_ts"],
                  "replies": [r for r in thread["replies"]
                              if not SI.FOLDER_LINK.search(r["text"])]}
    assert any(r["author_id"] == SI.DELIVERY_USER_ID
               for r in only_prose["replies"]), "the fixture must still " \
                                                "carry an owner reply"
    got = SI.verdict({"account": "Richwood Bank", "reply_count": 2},
                     only_prose)
    assert got["state"] == SI.PENDING
    assert "never with a Drive FOLDER link" in got["why"]


def test_a_file_link_is_not_a_folder_link():
    for text in ("https://drive.google.com/file/d/1AAAAAAAAAAAAAAA/view",
                 "https://docs.google.com/document/d/1AAAAAAAAAAAAAAA/edit",
                 "https://drive.google.com/drive/my-drive"):
        assert not SI.FOLDER_LINK.search(text), text
    for text in ("https://drive.google.com/drive/folders/1V5aG3cvov1lgBkA3yL4",
                 "<https://drive.google.com/drive/u/0/folders/1V5aG3cvov1lgBk|x>"):
        assert SI.FOLDER_LINK.search(text), text


def test_an_unfetched_thread_is_undecidable_and_never_pending():
    """The expensive mistake. A request whose thread was not read looks
    exactly like one nobody answered, and starting it assesses a client who
    was already delivered."""
    out = SI.triage(_channel(), threads={}, since_days=30, now=NOW)
    row = _by_account(out, "Richwood Bank")
    assert row["state"] == SI.UNDECIDABLE, row
    assert row not in out["pending"]


def test_no_replies_at_all_is_pending_not_undecidable():
    """The connector omits the `Thread:` line when a message has no replies,
    and no replies means nobody answered — including the owner."""
    out = SI.triage(_channel(), _threads(), since_days=30, now=NOW)
    row = _by_account(out, "GoEasy")
    assert row["state"] == SI.PENDING and row["reply_count"] is None


# ── the other workflow in the same channel ───────────────────────────────

def test_the_hubbl_workflow_is_never_picked_up():
    """Same channel, same shape — *Submitter*, *Priority*, and a Drive folder
    link right there in the request — assigned to a different person."""
    out = SI.triage(_channel(), _threads(), since_days=90, now=NOW)
    accounts = {r["account"] for r in out["requests"]}
    for theirs in ("MidFirst Bank", "CalPrivate Bank", "Penderfund"):
        assert theirs not in accounts, theirs
    assert len(out["not_this_flow"]) == 3


def test_the_flow_is_identified_by_bot_not_by_shape():
    """Shape-only matching is what would admit the Hubbl queue. The bot id
    decides; the bot NAME is the fallback; the fields decide nothing."""
    shaped_like_ours = {
        "author_id": SI.NOT_THIS_FLOW_BOT_ID,
        "author_name": SI.NOT_THIS_FLOW_BOT_NAME,
        "body": "*Account Full Name*\nSomebody Else\n*Priority*\nUrgent",
        "ts": "1.1", "posted_at": "", "reply_count": None}
    assert SI._is_dma_request(shaped_like_ours) is False
    assert SI._is_dma_request({**shaped_like_ours,
                               "author_id": SI.DMA_REQUEST_BOT_ID}) is True
    renamed = {**shaped_like_ours, "author_id": "BNEWID000",
               "author_name": SI.DMA_REQUEST_BOT_NAME}
    assert SI._is_dma_request(renamed) is True, "the name is the fallback"
    assert SI._is_dma_request({**shaped_like_ours, "author_id": "BOTHER",
                               "author_name": "Something Else"}) is False


# ── one client, one run ──────────────────────────────────────────────────

def test_a_resubmitted_request_does_not_start_two_runs():
    """It happens: Gulf Coast Business Credit says 'Resubmitting as my
    initial request error'd out.'"""
    text = _channel()
    twice = text + text.split("Channel:")[0]      # no-op; build explicitly
    first = """
=== Message from Assessment and Research Request (B0ACUPDCMGF) at 2026-08-29 08:00:00 EAT ===
Message TS: 1788000000.111111
*Account Full Name*
Twice Requested Bank
*Website*
<https://twice.test/>
*Priority*
High (need in 48 hours)

<@U09TL2S4LLS|Mishley Otiende> Please run the maturity assessment
"""
    second = first.replace("1788000000.111111", "1788009999.222222").replace(
        "2026-08-29 08:00:00", "2026-08-29 18:00:00")
    out = SI.triage(text + first + second, _threads(), since_days=30, now=NOW)
    rows = [r for r in out["requests"]
            if r["account"] == "Twice Requested Bank"]
    assert len(rows) == 2
    states = sorted(r["state"] for r in rows)
    assert states == ["PENDING", "SUPERSEDED"], states
    live = next(r for r in rows if r["state"] == SI.PENDING)
    assert live["ts"] == "1788009999.222222", "the NEWEST is the live one"
    assert sum(1 for r in out["pending"]
               if r["account"] == "Twice Requested Bank") == 1


def test_a_delivered_request_is_never_superseded_away():
    """Supersession is about two OPEN requests. A delivered one is history
    and must keep its verdict, or a re-request would erase the record that
    the first was answered."""
    out = SI.triage(_channel(), _threads(), since_days=90, now=NOW)
    assert _by_account(out, "Richwood Bank")["state"] == SI.DELIVERED


# ── the identifiers this file mints ──────────────────────────────────────

def test_the_entity_slug_agrees_with_the_engine():
    """A copy that is CHECKED beats an import that is not: a scripts/ file
    reaching into the engine binds the queue to that import working."""
    sys.path.insert(0, str(HERE.parent / "skills" / "dma-research"))
    from engine import runstate

    for name in ("REV Federal Credit Union", "Bank of Travelers Rest",
                 "GoEasy", "Gulf Coast Business Credit", "TGS Insurance",
                 "", "   ", "Ünïcode & Co."):
        assert SI._slug(name) == runstate._slug(name), name


def test_every_minted_run_id_is_one_the_engine_will_accept():
    sys.path.insert(0, str(HERE.parent / "skills" / "dma-research"))
    from engine import runstate

    out = SI.triage(_channel(), _threads(), since_days=90, now=NOW)
    assert out["requests"]
    for r in out["requests"]:
        assert runstate._RUN_ID_RE.match(r["run_id"]), r["run_id"]
    manual = SI.manual_request("Acme Credit Union", now=NOW)
    assert runstate._RUN_ID_RE.match(manual["run_id"]), manual["run_id"]


def test_the_reference_date_is_the_requests_not_todays():
    """An assessment answers the question as it was ASKED. Dating it today
    would silently re-age every piece of evidence against the wrong ruler."""
    out = SI.triage(_channel(), _threads(), since_days=90, now=NOW)
    assert _by_account(out, "Richwood Bank")["reference_date"] == "2026-08-13"


# ── the window, and the fields ───────────────────────────────────────────

def test_the_default_window_is_the_last_five_days():
    out = SI.triage(_channel(), _threads(), now=NOW)
    assert out["since_days"] == 5
    accounts = {r["account"] for r in out["requests"]}
    assert "GoEasy" in accounts                      # 2026-08-28
    assert "Richwood Bank" not in accounts           # 2026-08-13


def test_the_priority_does_not_swallow_the_workflow_footer():
    """`*Priority*` is the last field, so an unbounded read ran on into the
    '@owner Please run the maturity assessment…' footer and the priority
    printed as a paragraph."""
    out = SI.triage(_channel(), _threads(), since_days=90, now=NOW)
    for r in out["requests"]:
        assert "\n" not in r["priority"], r["priority"]
        assert "Please run" not in r["priority"], r["priority"]


def test_urgent_outranks_high_and_ties_break_oldest_first():
    rank = SI._rank
    assert rank({"priority": "Urgent (need in 24 hours)", "ts": "9"}) < \
        rank({"priority": "High (need in 48 hours)", "ts": "1"})
    assert rank({"priority": "High", "ts": "1"}) < \
        rank({"priority": "High", "ts": "2"})
    assert rank({"priority": "Whatever", "ts": "1"}) > \
        rank({"priority": "High", "ts": "9"}), "an unknown word sorts last"


def test_a_request_with_no_account_name_is_undecidable():
    got = SI.verdict({"account": "", "reply_count": None}, None)
    assert got["state"] == SI.UNDECIDABLE
    assert "Account Full Name" in got["why"]


# ── refusals ─────────────────────────────────────────────────────────────

def test_a_transcript_it_does_not_recognise_is_refused_whole():
    with pytest.raises(SystemExit) as e:
        SI.parse_channel("just some text\nwith no headers\n")
    assert "slack_read_channel transcript" in str(e.value)


def test_the_manual_path_refuses_an_empty_client():
    with pytest.raises(SystemExit):
        SI.manual_request("   ")


def test_the_manual_request_is_the_same_shape_as_a_slack_one():
    """A manual run that took a different code path would be a second
    pipeline nobody tests."""
    out = SI.triage(_channel(), _threads(), since_days=90, now=NOW)
    slack_row = out["pending"][0]
    manual = SI.manual_request("Acme Credit Union", now=NOW)
    assert set(slack_row) - set(manual) == set(), \
        sorted(set(slack_row) - set(manual))
    assert manual["source"] == "manual"


# ── it must not reach the network ────────────────────────────────────────

def test_triage_makes_no_network_call(monkeypatch):
    """A script cannot call Slack — there is no credential in this
    repository — and pretending otherwise is how a queue starts guessing."""
    import socket

    def refuse(*a, **k):
        raise AssertionError("triage tried to open a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    out = SI.triage(_channel(), _threads(), since_days=90, now=NOW)
    assert out["requests"]


def test_the_source_carries_no_import_of_a_network_library():
    src = SCRIPT.read_text()
    for bad in ("import requests", "urllib.request", "http.client",
                "import socket"):
        assert bad not in src, bad


# ── the CLI ──────────────────────────────────────────────────────────────

def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=120)


def test_threads_emits_the_pairs_the_session_must_read():
    """So a message_ts is never typed by hand into a tool call."""
    r = _run("threads", "--transcript", str(FIX / "channel.txt"),
             "--since-days", "30", "--now", "2026-08-30")
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    assert rows and all(x["channel_id"] == SI.DEAL_DESK_CHANNEL_ID
                        for x in rows)
    assert all(re.fullmatch(r"\d+\.\d+", x["message_ts"]) for x in rows)
    assert not any(x["account"] == "GoEasy" for x in rows), \
        "a request with no replies needs no thread read"


def test_the_exit_codes_separate_none_pending_from_could_not_tell():
    """'Nothing to do' and 'I could not tell' must never share a code: one
    ends a firing cleanly and the other is a firing that must go look."""
    full = _run("triage", "--transcript", str(FIX / "channel.txt"),
                "--threads", str(FIX), "--since-days", "30",
                "--now", "2026-08-30")
    assert full.returncode == 2, full.stdout       # undecidables remain

    narrow = _run("triage", "--transcript", str(FIX / "channel.txt"),
                  "--threads", str(FIX), "--since-days", "5",
                  "--now", "2026-08-30", "--json")
    doc = json.loads(narrow.stdout)
    assert {r["account"] for r in doc["pending"]} >= {"GoEasy"}


def test_json_carries_every_bucket():
    r = _run("triage", "--transcript", str(FIX / "channel.txt"),
             "--threads", str(FIX), "--since-days", "90",
             "--now", "2026-08-30", "--json")
    doc = json.loads(r.stdout)
    assert {"requests", "pending", "delivered", "undecidable",
            "not_this_flow", "channel", "since_days"} <= set(doc)
    assert doc["channel"] == SI.DEAL_DESK_CHANNEL_ID


def test_the_script_answers_help():
    assert _run("--help").returncode == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# ── the reply that closes the thread, and the trap under it ─────────────
#
# The connector sends AS THE OWNER, so this reply is itself what makes the
# request read DELIVERED to the next triage. And `engine.cli start` opens
# `<Entity> - DMA` in the intake Drive at minute one with status IN_PROGRESS,
# so a folder link is postable long before there is anything in the folder.

FOLDER = "https://drive.google.com/drive/folders/1V5aG3cvov1lgBkA3yL4wGwBs8U"


def test_the_folder_link_is_refused_until_the_run_is_served():
    """Posting early marks the request answered, takes it out of every future
    queue, and hands the requester an empty folder."""
    with pytest.raises(SystemExit) as e:
        SI.completion_reply("Richwood Bank", FOLDER, served=False)
    assert "until the assessment is SERVED" in str(e.value)


def test_a_file_link_is_refused_as_a_completion():
    with pytest.raises(SystemExit) as e:
        SI.completion_reply("Richwood Bank",
                            "https://drive.google.com/file/d/1AAAAAAAAAAA/view",
                            served=True)
    assert "not a Drive FOLDER link" in str(e.value)


def test_the_reply_would_read_as_delivered_on_the_next_pass():
    """The loop has to close: the message this renders must be the message
    the triage recognises, or a delivered client stays in the queue forever."""
    out = SI.completion_reply("Richwood Bank", FOLDER, served=True)
    assert out["reads_as_delivered"]
    verdict = SI.verdict(
        {"account": "Richwood Bank", "reply_count": 1},
        {"parent_ts": "1.1",
         "replies": [{"author_id": SI.DELIVERY_USER_ID,
                      "author_name": "Mishley Otiende",
                      "text": out["text"]}]})
    assert verdict["state"] == SI.DELIVERED, verdict


def test_the_reply_goes_to_the_deal_desk_channel():
    out = SI.completion_reply("Acme", FOLDER, served=True)
    assert out["channel_id"] == SI.DEAL_DESK_CHANNEL_ID


def test_the_reply_names_the_account_or_refuses():
    with pytest.raises(SystemExit):
        SI.completion_reply("  ", FOLDER, served=True)


def test_the_cli_reply_refuses_without_served():
    r = _run("reply", "--client", "Acme", "--folder-url", FOLDER)
    assert r.returncode != 0
    assert "SERVED" in (r.stderr + r.stdout)
    ok = _run("reply", "--client", "Acme", "--folder-url", FOLDER, "--served")
    assert ok.returncode == 0 and FOLDER in ok.stdout


# ── the thread travels with the run ─────────────────────────────────────

def test_the_workbook_can_record_the_thread_it_answers():
    """The run that answers a request is started by one firing and finished
    by another, days later and in another container. Without the thread on
    the run, the completion reply has nowhere to go."""
    sys.path.insert(0, str(HERE.parent / "skills" / "dma-research"))
    from engine import contract as C

    for key in ("slack_channel", "slack_thread_ts", "requested_by"):
        assert key in C.RUN_METADATA_KEYS, key


# ── thread-of: the thread comes off the run, never off a prompt ──────────
#
# The firing that promotes a run is not the firing that started it. Whatever
# the promoting session knows about the request, it read out of the workbook
# — so this is the join between the two halves of the queue, and the place a
# retyped ts would send the owner's own account a message to a stranger.

def _started_run(tmp_path, run_id, **request):
    import subprocess
    import sys
    skill = HERE.parent / "skills" / "dma-research"
    sys.path.insert(0, str(skill))
    from engine import runstate                              # noqa: PLC0415
    run = runstate.start(
        run_id=run_id, entity_name="Acme CU", entity_id="acme-cu",
        sub_vertical="CU", scope_mode="T1_CORE",
        reference_date="2026-08-29", root=tmp_path / "runs",
        evidence_mode="PUBLIC",
        sv_basis="NCUA-chartered federal credit union per charter 24680",
        mode_basis="engagement letter 2026-08-01 grants public-only review")
    if request:
        wb = run.open()
        for k, v in request.items():
            wb.set_metadata(k, v)
    return run


def test_thread_of_reads_the_request_off_the_run(tmp_path):
    _started_run(tmp_path, "R-THREAD-1",
                 slack_channel=SI.DEAL_DESK_CHANNEL_ID,
                 slack_thread_ts="1756400000.123456",
                 requested_by="U0EXAMPLE")
    got = SI.thread_of("R-THREAD-1", str(tmp_path / "runs"))
    assert got["answerable"] is True
    assert got["slack_thread_ts"] == "1756400000.123456"
    assert got["slack_channel"] == SI.DEAL_DESK_CHANNEL_ID
    assert got["requested_by"] == "U0EXAMPLE"


def test_a_run_with_no_thread_is_answerable_false_and_says_so(tmp_path):
    """A manual run answers no request. The routine must be able to tell
    that apart from a thread it failed to read — the first is nothing to do,
    the second is a request left open forever."""
    _started_run(tmp_path, "R-THREAD-2")
    got = SI.thread_of("R-THREAD-2", str(tmp_path / "runs"))
    assert got["answerable"] is False
    assert "Post nothing" in got["why"]


def test_thread_of_never_invents_a_channel(tmp_path):
    """The channel is the run's, not the module's constant. A run recorded
    against another channel must not be answered in #deal-desk."""
    _started_run(tmp_path, "R-THREAD-3", slack_channel="C0OTHER",
                 slack_thread_ts="1756400000.999999")
    got = SI.thread_of("R-THREAD-3", str(tmp_path / "runs"))
    assert got["slack_channel"] == "C0OTHER"


# ── two boundaries the queue was crossing wrong ─────────────────────────

def test_the_submitter_is_read_and_not_eaten_by_the_footer():
    """MEASURED 2026-08-30, on the RECORDED fixtures — so this was wrong on
    the connector route too, for as long as the route has existed.

    `*Submitter*`'s value is a line-initial @-mention. So is the workflow's
    assignee footer, and `_FOOTER` was searched from position 0 — so it
    matched the VALUE, ended the field before it began, and `submitter` came
    back "" on every request ever parsed. STEP 6 of the intake Routine hands
    that straight to `engine.cli start --requested-by`, so every run that
    ever started from this queue lost the person who asked for it.
    """
    got = SI.triage((FIX / "channel.txt").read_text(),
                    SI._load_threads(str(FIX)), since_days=99999,
                    now=SI.datetime(2026, 8, 30, tzinfo=SI.timezone.utc))
    subs = [r["submitter"] for r in got["requests"]]
    assert all(subs), (
        f"a request parsed with no submitter: {subs} — the footer boundary "
        f"is eating the field's own value again")
    assert any("Kevin Murray" in s for s in subs), subs


def test_the_footer_still_bounds_priority_after_that():
    """The other half. Widening the boundary to find the submitter must not
    let the assignee sentence leak into the last field."""
    got = SI.triage((FIX / "channel.txt").read_text(),
                    SI._load_threads(str(FIX)), since_days=99999,
                    now=SI.datetime(2026, 8, 30, tzinfo=SI.timezone.utc))
    for r in got["requests"]:
        assert "Please run the maturity" not in r["priority"], r["priority"]
        assert len(r["priority"]) < 60, r["priority"]


def test_a_bare_mention_footer_also_bounds_the_field():
    """The API route renders `<@Uxxx>` when the display name cannot be
    resolved — `users:read` is a degradable scope. The boundary must hold
    without the `|Name` half, or a token missing one optional scope puts the
    assignee sentence in the priority field."""
    body = ("*Account Full Name*\nAcme Bank\n*Priority*\nHigh (48 hours)\n\n"
            "<@U09TL2S4LLS> Please run the maturity assessment and reply")
    assert SI._field(body, "Priority") == "High (48 hours)"
    assert SI._field(body, "Account Full Name") == "Acme Bank"


def test_fetch_asks_for_the_thread_key_that_threads_to_read_emits(tmp_path,
                                                                  monkeypatch):
    """`threads_to_read` emits `message_ts`; the `fetch` subcommand read
    `ts`. So the bot-token route died with KeyError on the FIRST request
    carrying a reply — which is to say on every real channel. Nothing caught
    it because the connector route reads that JSON itself and the token
    route had never got this far: `fetch_channel` was failing above it on a
    missing scope.

    This drives the REAL subcommand, so the two halves are joined by the
    code path rather than by a list of key names typed here.
    """
    import types
    chan = (FIX / "channel.txt").read_text()
    fake = types.SimpleNamespace(
        SlackError=RuntimeError,
        bot_token=lambda *a, **k: "xoxb-test",
        fetch_channel=lambda *a, **k: chan,
        fetch_thread=lambda c, ts, **k: f"=== THREAD PARENT MESSAGE ===\n"
                                        f"Message TS: {ts}\n",
    )
    monkeypatch.setitem(sys.modules, "slack_client", fake)
    out = tmp_path / "deal_desk.txt"
    threads = tmp_path / "threads"
    rc = SI.main(["fetch", "--transcript", str(out), "--threads",
                  str(threads), "--since-days", "99999"])
    assert rc == 0, rc
    named = SI.threads_to_read(chan, since_days=99999)
    assert named, "the fixture channel names no threads — nothing was proved"
    for row in named:
        assert (threads / f"thread_{row['message_ts']}.txt").exists(), (
            f"no file for {row['message_ts']}; fetch and threads_to_read "
            f"disagree about the key that names a thread")
