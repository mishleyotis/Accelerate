"""The API route must produce a transcript the connector's parser accepts.

THE WHOLE RISK OF THIS CHANGE IN ONE SENTENCE: slack_intake.py parses the
CONNECTOR's rendered text, and slack_client.py fetches JSON from Slack — so
if the renderer's shape drifts by one character the triage silently stops
seeing requests, which is indistinguishable from a quiet channel.

So these tests do not check the renderer against a description of the format.
They render, then run the REAL parser over the result and assert the same
facts the recorded-connector fixtures assert. A format change that breaks the
parser fails here; a format change that does not, does not matter.

No test in this file touches the network or reads a token.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import slack_client as SC                                     # noqa: E402
import slack_intake as SI                                     # noqa: E402

FIX = pathlib.Path(__file__).resolve().parent / "slack"

WORKFLOW_BOT = "B0ACUPDCMGF"
OWNER = "U09TL2S4LLS"


def _request_msg(ts, account, website, context, submitter, priority,
                 replies=0, latest=None):
    """A workflow request as Slack actually delivers it: fields in BLOCKS.

    `text` is a fallback string on these messages — the fields the parser
    reads exist only in the blocks, which is exactly why _body walks them.
    """
    lines = (f"*Account Full Name*\n{account}\n*Website*\n<{website}>\n"
             f"*Additional Context*\n{context}\n*Submitter*\n{submitter}\n"
             f"*Priority*\n{priority}")
    msg = {
        "ts": ts, "bot_id": WORKFLOW_BOT,
        "username": "Assessment and Research Request",
        "text": "",
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": lines}},
            {"type": "section", "text": {"type": "mrkdwn", "text":
                f"<@{OWNER}|Mishley Otiende> Please run the maturity "
                f"assessment and account research, place in the account "
                f"folder, and reply to this thread with a link to the folder"}},
        ],
    }
    if replies:
        msg["reply_count"] = replies
        msg["latest_reply"] = latest or ts
    return msg


def test_a_rendered_channel_parses_as_a_dma_request():
    text = SC.render_channel("C0AD83KJ4DU", "deal-desk", [
        _request_msg("1787950217.210239", "REV Federal Credit Union",
                     "https://www.revfcu.com/", "Marketing cloud, no CRM",
                     "<@U061X1XFD5F|Kevin Murray>",
                     "High (need in 48 hours)", replies=1)], {})
    got = SI.triage(text, {}, since_days=99999,
                    now=SI.datetime(2026, 8, 30, tzinfo=SI.timezone.utc))
    assert len(got["requests"]) == 1, (
        "the renderer produced a transcript the parser found no request in — "
        "the two halves have drifted")
    r = got["requests"][0]
    assert r["account"] == "REV Federal Credit Union"
    assert r["ts"] == "1787950217.210239"
    assert r["priority"].startswith("High")
    assert r["entity_id"] == "rev-federal-credit-union"


def test_the_footer_still_bounds_the_last_field():
    """The defect the recorded fixtures caught once already: without a
    boundary, `*Priority*` swallows the workflow's @-mention footer."""
    text = SC.render_channel("C0AD83KJ4DU", "deal-desk", [
        _request_msg("1787950217.210239", "GoEasy", "https://www.goeasy.com/",
                     "ctx", "<@U061X1XFD5F|Kevin Murray>",
                     "Urgent (need in 24 hours)")], {})
    r = SI.triage(text, {}, since_days=99999,
                  now=SI.datetime(2026, 8, 30, tzinfo=SI.timezone.utc)
                  )["requests"][0]
    assert "Please run the maturity" not in r["priority"], (
        f"the footer leaked into the priority: {r['priority']!r}")


def test_a_rendered_thread_reads_delivered_when_the_owner_posts_a_folder():
    parent = _request_msg("1786644275.998269", "Richwood Bank",
                          "https://richwoodbank.com/", "RFP response",
                          "<@U0AGL0TD0C8|Melissa Hanning>",
                          "High (need in 48 hours)", replies=1)
    replies = [{"ts": "1787011311.370559", "user": OWNER,
                "text": "Hi team, the DMA for Richwood Bank has been "
                        "finalized. Please find the folder here: "
                        "<https://drive.google.com/drive/folders/"
                        "1V5aG3cvov1lgBkA3yL4wGwBs8UgedgWq|Drive Link>"}]
    thread = SC.render_thread(parent, replies, {OWNER: "Mishley Otiende"})
    parsed = SI.parse_thread(thread)
    v = SI.verdict(SI.parse_request(SI.parse_channel(
        SC.render_channel("C0AD83KJ4DU", "deal-desk", [parent], {})
    )["messages"][0]), parsed)
    assert v["state"] == SI.DELIVERED, v


def test_a_reply_from_someone_else_is_not_delivery():
    """The REV thread's real shape: a colleague replied, the owner did not."""
    parent = _request_msg("1787950217.210239", "REV Federal Credit Union",
                          "https://www.revfcu.com/", "ctx",
                          "<@U061X1XFD5F|Kevin Murray>", "High", replies=1)
    replies = [{"ts": "1787950224.1", "user": "U061X1XFD5F",
                "text": "FYI <@U0ANDREW|Andrew>"}]
    thread = SC.render_thread(parent, replies, {"U061X1XFD5F": "Kevin Murray"})
    v = SI.verdict(SI.parse_request(SI.parse_channel(
        SC.render_channel("C0AD83KJ4DU", "deal-desk", [parent], {})
    )["messages"][0]), SI.parse_thread(thread))
    assert v["state"] == SI.PENDING, v


def test_an_owner_reply_without_a_folder_link_is_not_delivery():
    """Also real: "Let me retrieve it from my desktop" is not a delivery."""
    parent = _request_msg("1786644275.998269", "Richwood Bank",
                          "https://richwoodbank.com/", "ctx",
                          "<@U0AGL0TD0C8|Melissa Hanning>", "High", replies=1)
    replies = [{"ts": "1787329417.175349", "user": OWNER,
                "text": "Let me retrieve it from my desktop."}]
    thread = SC.render_thread(parent, replies, {OWNER: "Mishley Otiende"})
    v = SI.verdict(SI.parse_request(SI.parse_channel(
        SC.render_channel("C0AD83KJ4DU", "deal-desk", [parent], {})
    )["messages"][0]), SI.parse_thread(thread))
    assert v["state"] == SI.PENDING, v


def test_rich_text_blocks_render_their_mentions_and_links():
    """A human reply arrives as rich_text, not as a section — and the
    delivery rule reads a Drive link out of exactly those replies."""
    msg = {"ts": "1.1", "user": OWNER, "blocks": [{
        "type": "rich_text", "elements": [{"type": "rich_text_section",
        "elements": [
            {"type": "text", "text": "done: "},
            {"type": "link",
             "url": "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMn"},
        ]}]}]}
    assert "drive.google.com/drive/folders/1AbCdEfGhIjKlMn" in SC._body(msg)


def test_the_renderer_never_emits_a_reply_header_the_parser_cannot_see():
    parent = _request_msg("1.0", "X Bank", "https://x.test/", "c",
                          "<@U1|A>", "Low", replies=2)
    replies = [{"ts": "1.1", "user": "U1", "text": "one"},
               {"ts": "1.2", "user": OWNER, "text": "two"}]
    text = SC.render_thread(parent, replies, {})
    assert len(SI._REPLY.findall(text)) == 2
    assert SI.parse_thread(text)["replies"] and \
        len(SI.parse_thread(text)["replies"]) == 2


# ── the token ladder: order, and silence about values ────────────────────

def test_the_token_ladder_prefers_the_environment(monkeypatch):
    monkeypatch.setenv("DMA_SLACK_BOT_TOKEN", "xoxb-from-env")
    assert SC.bot_token() == "xoxb-from-env"


def test_the_token_ladder_falls_through_to_the_file(monkeypatch, tmp_path):
    for v in SC.TOKEN_ENV:
        monkeypatch.delenv(v, raising=False)
    f = tmp_path / "slack_token"
    f.write_text("xoxb-from-file\n")
    monkeypatch.setattr(SC, "TOKEN_FILE", str(f))
    assert SC.bot_token() == "xoxb-from-file"


def test_a_failure_names_every_rung_and_prints_no_value(monkeypatch,
                                                        tmp_path):
    """The refusal has to be actionable without ever being a leak."""
    for v in SC.TOKEN_ENV:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(SC, "TOKEN_FILE", str(tmp_path / "nope"))
    monkeypatch.setattr(SC, "_secret_via_rest",
                        lambda *a, **k: (_ for _ in ()).throw(
                            SC.SlackError("no key")))
    monkeypatch.setattr(SC.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError()))
    with pytest.raises(SystemExit) as e:
        SC.bot_token()
    msg = str(e.value)
    for rung in ("DMA_SLACK_BOT_TOKEN", "nope", SC.TOKEN_SECRET):
        assert rung in msg, f"the refusal does not name the {rung} rung"
    assert "xoxb" not in msg


def test_no_source_file_carries_a_literal_credential():
    """The permanent one. A credential in the repository is a credential to
    rotate, and this is the check that says so before a commit does.

    Widened 2026-08-30 beyond Slack: the project also handles a Google OAuth
    client (GOCSPX-…) wired into the MCP gate as dmai-oauth-client-secret,
    and a scanner that only knew one vendor's prefix would have watched the
    wrong door. Shapes, not values — nothing secret is written here.
    """
    import re
    root = HERE.parents[2]
    # Slack only. The repository-wide scanner (scripts/scan_secrets.py) owns
    # every other vendor's shape AND the exclusions that keep the legacy
    # snapshot's deliberate FAKE fixtures from reading as leaks — a second
    # scanner without those exclusions reports the same placeholders forever
    # and teaches everyone to ignore it.
    pat = re.compile(r"xox[baprs]-[0-9]{6,}-[0-9]{6,}-")
    bad = []
    for p in root.rglob("*"):
        if not p.is_file() or ".git/" in str(p):
            continue
        if p.suffix not in {".py", ".sh", ".md", ".json", ".yml", ".yaml",
                            ".txt", ".toml"}:
            continue
        try:
            if pat.search(p.read_text(encoding="utf-8", errors="ignore")):
                bad.append(str(p.relative_to(root)))
        except OSError:
            continue
    assert not bad, f"a literal Slack token is committed in: {bad}"


# ── the API refuses loudly ───────────────────────────────────────────────

def test_an_ok_false_answer_raises_rather_than_reading_as_empty(monkeypatch):
    """Slack answers HTTP 200 with ok:false. A caller checking only the
    status believes an empty channel — the exact shape of the queue defect
    this project already met once."""
    class _Resp:
        def read(self): return json.dumps(
            {"ok": False, "error": "not_in_channel"}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(SC.urllib.request, "urlopen", lambda *a, **k: _Resp())
    with pytest.raises(SC.SlackError) as e:
        SC.call("conversations.history", {"channel": "C1"}, token="x")
    assert "not_in_channel" in str(e.value)
    assert "/invite" in str(e.value), "the refusal should name the remedy"


def test_posting_without_a_thread_ts_is_refused(monkeypatch):
    monkeypatch.setattr(SC, "call", lambda *a, **k: {"ok": True})
    with pytest.raises(SC.SlackError) as e:
        SC.post_reply("C0AD83KJ4DU", "", "hello", token="x")
    assert "thread" in str(e.value)


def test_the_recorded_fixtures_still_parse():
    """The connector route has not been removed and must keep working: the
    same parser, over the real recordings, unchanged."""
    got = SI.triage((FIX / "channel.txt").read_text(),
                    SI._load_threads(str(FIX)), since_days=99999,
                    now=SI.datetime(2026, 8, 30, tzinfo=SI.timezone.utc))
    assert got["requests"], "the recorded channel stopped parsing"


# ── a cosmetic lookup may not decide whether the read happens ────────────
#
# Measured 2026-08-30 on a live `dma-assessment-intake` firing: the bot token
# carried `channels:history` and not `channels:read`, and the whole intake
# ended having read NOTHING — "Slack unreadable" — because `fetch_channel`
# asked `conversations.info` for the channel's DISPLAY NAME first, and that
# call needs the scope the token lacked. Every message in the channel was
# reachable with the scopes already granted.
#
# The name goes in one header line that nothing parses. So it degrades to the
# id, and the substantive call proceeds. These tests pin both halves of that:
# the label may degrade, the messages may not.

def _slack_granting(*scopes):
    """A fake Slack that grants exactly `scopes` and refuses the rest the way
    Slack really does — ok:false, which `call` turns into a SlackError."""
    granted, needs = set(scopes), {
        "conversations.info": "channels:read",
        "conversations.history": "channels:history",
        "users.info": "users:read",
    }

    def _call(method, params, *, token=None, **kw):
        need = needs[method]
        if need not in granted:
            raise SC.SlackError(
                f"{method}: missing_scope — needed: {need}, provided: "
                f"{', '.join(sorted(granted)) or 'none'}")
        if method == "conversations.info":
            return {"ok": True, "channel": {"name": "deal-desk"}}
        if method == "conversations.history":
            return {"ok": True, "messages": [_request_msg(
                "1787950217.210239", "REV Federal Credit Union",
                "https://www.revfcu.com/", "Marketing cloud, no CRM",
                "<@U061X1XFD5F|Kevin Murray>", "High (need in 48 hours)")]}
        return {"ok": True, "user": {"real_name": "Kevin Murray"}}
    return _call


def _requests_in(text):
    return SI.triage(text, {}, since_days=99999,
                     now=SI.datetime(2026, 8, 30,
                                     tzinfo=SI.timezone.utc))["requests"]


def test_a_refused_channel_name_does_not_stop_the_read(monkeypatch):
    """THE DEFECT. With only `channels:history`, the queue still reads."""
    monkeypatch.setattr(SC, "call", _slack_granting("channels:history"))
    got = _requests_in(SC.fetch_channel("C0AD83KJ4DU", token="x"))
    assert len(got) == 1, (
        "a token holding channels:history read no requests — the cosmetic "
        "name lookup is deciding whether the substantive one runs again")
    assert got[0]["account"] == "REV Federal Credit Union"


def test_the_id_stands_in_for_the_refused_name(monkeypatch):
    monkeypatch.setattr(SC, "call", _slack_granting("channels:history"))
    head = SC.fetch_channel("C0AD83KJ4DU", token="x").splitlines()[0]
    assert "C0AD83KJ4DU" in head, head


def test_the_real_name_is_used_when_the_scope_is_there(monkeypatch):
    """The degradation must not become the only behaviour: a token that CAN
    read the name still gets the friendlier header."""
    monkeypatch.setattr(SC, "call",
                        _slack_granting("channels:read", "channels:history"))
    head = SC.fetch_channel("C0AD83KJ4DU", token="x").splitlines()[0]
    assert "#deal-desk" in head, head


#: A value that is NOT credential-shaped, assembled rather than written.
#: The first version of this test passed a literal `xoxb-`-prefixed string,
#: which is what a real Slack token looks like — and `scripts/scan_secrets.py`
#: rightly failed CI on it twice over, as a Slack token and as a hardcoded
#: credential assignment. The scanner was correct: a fake credential
#: committed to the tree is how people learn to wave its failures through.
#:
#: The shape was never load-bearing. `fetch_channel` does not parse the
#: token, it passes it to `call`, which these tests monkeypatch — so the
#: property under test ("whatever was handed in must not reach stderr") is
#: proved by any distinctive value, and better by one nobody can mistake for
#: real. Split so the joined form appears nowhere in the source.
_NEVER_ECHOED = "not-a-real-value-" + "canary" + "-do-not-print"


def test_the_note_names_the_scope_and_never_the_token(monkeypatch, capsys):
    """An operator reading the log must learn what to grant, and the value
    handed in as the token must not appear in the note — the file's standing
    rule, stated in its own docstring: the token is never echoed."""
    monkeypatch.setattr(SC, "call", _slack_granting("channels:history"))
    SC.fetch_channel("C0AD83KJ4DU", token=_NEVER_ECHOED)
    err = capsys.readouterr().err
    assert "channels:read" in err and "channels:history" in err, err
    assert _NEVER_ECHOED not in err, "the note echoed the token"
    assert "canary" not in err, (
        "no fragment of the token reached the note either")


def test_a_refused_history_is_still_a_failure(monkeypatch):
    """Only the LABEL degrades. If the messages cannot be read, saying so is
    the whole job — a transcript with no messages and no error is the queue
    defect this client exists to prevent."""
    monkeypatch.setattr(SC, "call", _slack_granting("channels:read"))
    with pytest.raises(SC.SlackError) as e:
        SC.fetch_channel("C0AD83KJ4DU", token="x")
    assert "conversations.history" in str(e.value)


# ── the workflow really posts rich_text, and rich_text carries STYLE ─────
#
# `tests/slack/rich_text_request.json` is a VERBATIM recording of a real
# Assessment and Research Request message, pulled from `conversations.history`
# on 2026-08-30. It is here because the hand-built `_request_msg` above is a
# `section` block with mrkdwn already in its `text` — which is what the
# CONNECTOR hands over, and is not what the API returns. The workflow posts
# ONE `rich_text` block whose field labels are bold RUNS, and the renderer
# was dropping both the bold markers and the run boundaries.
#
# The result, measured against the live #deal-desk the same day: every
# request came back with account, website, submitter and priority empty and
# a verdict of UNDECIDABLE — "the request carries no *Account Full Name*" —
# on messages that plainly carried one. The queue read as unanswerable
# noise. Fixtures built by hand could not catch it because they were built
# in the shape that already worked.

RICH = json.loads((FIX / "rich_text_request.json").read_text())


def test_the_recorded_rich_text_request_parses():
    """THE DEFECT, against the bytes Slack actually returned."""
    text = SC.render_channel("C0AD83KJ4DU", "deal-desk", [RICH],
                             {"U09TL2S4LLS": "Mishley Otiende",
                              "U061X1XFD5F": "Kevin Murray"})
    got = SI.triage(text, {}, since_days=99999,
                    now=SI.datetime(2026, 8, 30, tzinfo=SI.timezone.utc))
    assert len(got["requests"]) == 1, (
        "a real workflow message rendered into something the parser finds no "
        "request in — the API route and the connector route have drifted")
    r = got["requests"][0]
    assert r["account"] == "REV Federal Credit Union"
    assert r["website"] == "https://www.revfcu.com/"
    assert r["priority"].startswith("High")
    assert "marketing cloud" in r["context"]


def test_a_bold_run_becomes_a_label_on_its_own_line():
    """The mechanism, stated so a future edit cannot quietly undo it:
    `_field` looks for the LINE `*Label*`, and a bold run is how the API
    says that."""
    body = SC._body(RICH, {})
    for label in ("Account Full Name", "Website", "Additional Context",
                  "Submitter", "Priority"):
        assert f"\n*{label}*\n" in f"\n{body}\n", (
            f"*{label}* is not a line by itself in the rendered body")


def test_inline_runs_are_not_split_across_lines():
    """Slack emits explicit "\\n" runs where a line really breaks. Joining
    the runs with newlines instead put a blank line between every label and
    its value, which is what broke the parse."""
    body = SC._body(RICH, {})
    assert "*Account Full Name*\nREV Federal Credit Union" in body, body


def test_a_mention_renders_with_its_display_name_when_known():
    """The footer boundary in slack_intake reads `<@Uxxx|Name>`, so the two
    routes must agree on that form."""
    body = SC._body(RICH, {"U09TL2S4LLS": "Mishley Otiende"})
    assert "<@U09TL2S4LLS|Mishley Otiende>" in body
    assert "<@U061X1XFD5F>" in body, "an unknown id stays a bare mention"


def test_the_mentions_are_collected_for_name_resolution():
    """`_users` was fed authors only, so the two ids that decide a request —
    the submitter and the assignee — were never resolved."""
    assert SC._mentions(RICH) >= {"U09TL2S4LLS", "U061X1XFD5F"}


def test_the_assignee_footer_survives_the_round_trip():
    """It must still be there and still be recognisable, or `_field` loses
    the boundary that stops Priority swallowing it."""
    body = SC._body(RICH, {"U09TL2S4LLS": "Mishley Otiende"})
    assert "Please run the maturity assessment" in body
    assert "<@U09TL2S4LLS|Mishley Otiende> Please run" in body, (
        "the mention and the sentence after it are one line in Slack")
