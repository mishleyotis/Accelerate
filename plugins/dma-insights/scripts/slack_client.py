#!/usr/bin/env python3
"""Slack, reachable from any session — connector attached or not.

WHY THIS EXISTS. Until 2026-08-30 the only way this system could read
#deal-desk was the claude.ai Slack CONNECTOR, attached per Routine on its own
edit screen in the routines UI. That is not portable in three separate ways,
and every one of them was measured rather than feared:

  1. `dma-assessment-intake` carries no connector of any kind, so the queue
     that decides which client to assess could not read its own channel
     (AUD-0190). `update_trigger` cannot attach one; only a human can.
  2. A SCRIPT can never call a connector tool. So the triage rule could be
     tested over recorded fixtures and never over the live channel, and the
     two halves — read and decide — could drift with nothing to catch it.
  3. Every new Routine, every fresh container, every teammate's session
     starts with no Slack until somebody clicks through a UI.

A bot token in Secret Manager has none of those properties. It is read by the
same three-rung ladder as the connector path token (gcp_token.path_token),
works in any process that carries the service-account key, and is rotated
without touching a line of code.

WHAT THIS DELIBERATELY DOES NOT DO. It never opens a listening endpoint. The
intake POLLS on a schedule, so there is no Slack Events subscription, no
request-signing to verify, no public URL to defend, and no signing secret to
store. A design that needs no inbound endpoint needs no OAuth redirect either
— see docs/CONNECTORS.md § Slack.

THE RENDERED FORMAT IS THE CONTRACT. slack_intake.py parses the CONNECTOR's
rendered text, and the fixtures under scripts/tests/slack/ are real
recordings of it. So this client renders the Slack API's JSON into that exact
shape rather than inventing its own: one parser, one set of fixtures, and a
transcript that reads identically whichever route fetched it. Changing the
rendering here without changing the fixtures is a defect the round-trip tests
in test_slack_client.py will catch.

THE TOKEN IS NEVER ECHOED. Not to stdout, not into an error message, not into
a log line. Every failure path names the RUNG that failed and the variable or
secret that fixes it, never the value it was looking for.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

API = "https://slack.com/api/"
PROJECT = os.environ.get("DMA_GCP_PROJECT", "digital-maturity-assessor")

#: The ladder, cheapest first, exactly as gcp_token.path_token does it. The
#: env var costs nothing, the file costs a stat, Secret Manager costs a token
#: exchange and an HTTPS call but always answers where the service account is
#: provisioned — which is the rung that makes a scheduled firing survivable.
TOKEN_ENV = ("DMA_SLACK_BOT_TOKEN", "SLACK_BOT_TOKEN")
TOKEN_FILE = "/root/.dma/slack_token"
TOKEN_SECRET = "dmai-slack-bot-token"

#: Rendered by the connector as a local wall-clock time with a zone
#: abbreviation. We render UTC and say so; the parser reads the TS, never the
#: pretty time, so this is for humans reading a saved transcript.
_TIMEFMT = "%Y-%m-%d %H:%M:%S"


class SlackError(RuntimeError):
    """A Slack API call that answered, and said no."""


# ── the token ────────────────────────────────────────────────────────────

def _secret_via_rest(name: str, project: str) -> str:
    """Secret Manager over plain HTTPS, with no gcloud anywhere.

    gcloud is ABSENT from the routine image — measured 2026-08-30,
    `command -v gcloud` finds nothing — so a ladder whose last rung shells
    out to it has no last rung at all in the place it matters most. The
    service-account key mints an access token in pure Python
    (gcp_token.mint_assertion + exchange) and this reads the secret with it.
    """
    import gcp_token                                          # noqa: PLC0415
    key, source = gcp_token.load_key()
    if key is None:
        raise SlackError(f"no service-account key: {source}")
    tok = gcp_token.exchange(
        gcp_token.mint_assertion(key, {"scope": gcp_token.DEFAULT_SCOPE}))
    access = tok.get("access_token")
    if not access:
        raise SlackError("the service account minted no access token")
    url = (f"https://secretmanager.googleapis.com/v1/projects/{project}"
           f"/secrets/{urllib.parse.quote(name)}/versions/latest:access")
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {access}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
    data = (body.get("payload") or {}).get("data") or ""
    return base64.b64decode(data).decode("utf-8").strip()


def bot_token(project: str = PROJECT) -> str:
    """The bot token, or SystemExit naming every route that was tried.

    Never returns an empty string and never prints the value.
    """
    tried = []
    for var in TOKEN_ENV:
        v = (os.environ.get(var) or "").strip()
        if v:
            return v
        tried.append(f"${var} unset")
    f = Path(TOKEN_FILE)
    try:
        if f.is_file():
            v = f.read_text(encoding="utf-8").strip()
            if v:
                return v
            tried.append(f"{TOKEN_FILE} is empty")
        else:
            tried.append(f"{TOKEN_FILE} absent")
    except OSError:
        tried.append(f"{TOKEN_FILE} unreadable")
    try:
        v = _secret_via_rest(TOKEN_SECRET, project)
        if v:
            return v
        tried.append(f"Secret Manager {TOKEN_SECRET} is empty")
    except Exception as e:                                    # noqa: BLE001
        tried.append(f"Secret Manager {TOKEN_SECRET}: {e}")
    # A gcloud rung, last and optional, for a workstation that has one.
    try:
        r = subprocess.run(
            ["gcloud", "secrets", "versions", "access", "latest",
             f"--secret={TOKEN_SECRET}", f"--project={project}"],
            capture_output=True, text=True, timeout=60)
        v = (r.stdout or "").strip()
        if v:
            return v
    except Exception:                                         # noqa: BLE001
        pass
    raise SystemExit(
        "no Slack bot token. Tried, in order: " + "; ".join(tried) + ". "
        f"Set one of {', '.join(TOKEN_ENV)}, or land {TOKEN_FILE}, or grant "
        f"this service account secretmanager.secretAccessor on "
        f"{TOKEN_SECRET}. The value is never printed by this script.")


# ── the API ──────────────────────────────────────────────────────────────

def call(method: str, params: dict, *, token: str | None = None,
         post: bool = False) -> dict:
    """One Slack Web API call. Raises SlackError on `ok: false`.

    Slack answers 200 with `{"ok": false, "error": "..."}` for most refusals,
    so a caller checking only the HTTP status believes an empty result — the
    exact shape of failure this project keeps meeting elsewhere (a queue read
    from the wrong key looked like a quiet queue for days). This raises.
    """
    tok = token or bot_token()
    url = API + method
    if post:
        body = json.dumps(params).encode()
        req = urllib.request.Request(url, data=body, headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json; charset=utf-8"})
    else:
        req = urllib.request.Request(
            url + "?" + urllib.parse.urlencode(params),
            headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            out = json.loads(resp.read())
    except urllib.error.HTTPError as e:                       # noqa: PERF203
        raise SlackError(f"{method}: HTTP {e.code}") from None
    if not out.get("ok"):
        err = out.get("error", "unknown")
        hint = {
            "not_in_channel": "the bot is not in this channel — invite it "
                              "with /invite @<app> in #deal-desk",
            "missing_scope": f"the token lacks a scope this call needs "
                             f"(needed: {out.get('needed')}, "
                             f"provided: {out.get('provided')})",
            "invalid_auth": "the token is not valid — it may have been "
                            "rotated; re-read it from Secret Manager",
            "channel_not_found": "wrong channel id, or the bot cannot see "
                                 "this channel",
        }.get(err, "")
        raise SlackError(f"{method}: {err}" + (f" — {hint}" if hint else ""))
    return out


def _users(ids: set, token: str) -> dict:
    """Display names for user ids, best effort.

    A name that cannot be resolved renders as the bare id rather than
    failing the fetch: the parser decides on IDS, and a missing display name
    costs a human some readability and costs the triage nothing.
    """
    out = {}
    for uid in sorted(i for i in ids if i):
        try:
            info = call("users.info", {"user": uid}, token=token)
            u = info.get("user") or {}
            prof = u.get("profile") or {}
            out[uid] = (prof.get("real_name") or u.get("real_name")
                        or u.get("name") or uid)
        except SlackError:
            out[uid] = uid
    return out


def _when(ts: str) -> str:
    try:
        return datetime.fromtimestamp(
            float(ts), tz=timezone.utc).strftime(_TIMEFMT)
    except (TypeError, ValueError):
        return "1970-01-01 00:00:00"


def _author(msg: dict, names: dict) -> tuple:
    """(display, id) for a message's author, bot or human."""
    if msg.get("bot_id"):
        who = (msg.get("username")
               or ((msg.get("bot_profile") or {}).get("name"))
               or "bot")
        return who, msg["bot_id"]
    uid = msg.get("user") or ""
    return names.get(uid, uid), uid


#: mrkdwn markers for the styles a `rich_text` run can carry. `bold` is the
#: load-bearing one: every field label the parser finds is a bold run, and
#: `_field` looks for the LINE `*Label*`.
_STYLE_MARK = (("bold", "*"), ("italic", "_"), ("strike", "~"))

_MENTION_RE = re.compile(r"<@(U[A-Z0-9]+)")


def _mentions(msg: dict) -> set:
    """User ids this message MENTIONS, so their names can be resolved too.

    `_users` was fed message AUTHORS only. But the two mentions that decide
    a request — the Submitter field's value and the workflow's assignee
    footer — are mentions, not authors, so they rendered as bare `<@Uxxx>`
    while the connector renders `<@Uxxx|Display Name>`. Two renderings of
    one channel is exactly the drift this client exists to prevent, and the
    footer boundary in `slack_intake._FOOTER` reads that form.
    """
    out = set(_MENTION_RE.findall(msg.get("text") or ""))
    for b in msg.get("blocks") or []:
        if b.get("type") == "section":
            for t in ([(b.get("text") or {}).get("text")]
                      + [f.get("text") for f in b.get("fields") or []]):
                out |= set(_MENTION_RE.findall(t or ""))
        for el in b.get("elements") or []:
            for sub in [el] + list(el.get("elements") or []):
                for deep in [sub] + list(sub.get("elements") or []):
                    if deep.get("type") == "user" and deep.get("user_id"):
                        out.add(deep["user_id"])
    return out


def _run(sub: dict, names: dict) -> str:
    """One inline run of a `rich_text` element, back in mrkdwn."""
    kind = sub.get("type")
    if kind == "text":
        s = sub.get("text") or ""
        core, style = s.strip(), sub.get("style") or {}
        if core:
            for key, mark in _STYLE_MARK:
                if style.get(key):
                    core = f"{mark}{core}{mark}"
            # markers go INSIDE the surrounding whitespace, so a bold label
            # still starts its own line and `^\*Label\*$` still matches.
            s = s[:len(s) - len(s.lstrip())] + core + s[len(s.rstrip()):]
        return s
    if kind == "user" and sub.get("user_id"):
        uid = sub["user_id"]
        nm = names.get(uid)
        return f"<@{uid}|{nm}>" if nm and nm != uid else f"<@{uid}>"
    if kind == "link" and sub.get("url"):
        label = sub.get("text")
        return f"<{sub['url']}|{label}>" if label else f"<{sub['url']}>"
    if kind == "emoji" and sub.get("name"):
        return f":{sub['name']}:"
    if kind == "channel" and sub.get("channel_id"):
        return f"<#{sub['channel_id']}>"
    if kind == "usergroup" and sub.get("usergroup_id"):
        return f"<!subteam^{sub['usergroup_id']}>"
    return sub.get("text") or ""


def _inline(el: dict, names: dict) -> str:
    """A `rich_text` element as ONE line — its runs CONCATENATED.

    Concatenated, not newline-joined. The runs are inline spans of a single
    line and Slack already emits explicit "\n" text runs wherever the line
    really breaks, so joining them with newlines put a blank line between
    every field label and its value: `*Account Full Name*` stopped being a
    line by itself, `_field` matched nothing, and EVERY request parsed with
    account, website, submitter and priority empty — measured 2026-08-30
    against the live #deal-desk, where all six requests read UNDECIDABLE
    with "carries no *Account Full Name*" while every one of them had one.

    A list element nests sections; those are separate lines.
    """
    subs = el.get("elements") or []
    if any(x.get("elements") for x in subs):
        return "\n".join(_inline(x, names) for x in subs)
    return "".join(_run(x, names) for x in subs)


def _body(msg: dict, names: dict | None = None) -> str:
    """The message text, with the workflow's field blocks preserved.

    A Slack workflow posts its fields as BLOCKS, and `text` on such a message
    is usually a fallback string or empty — so rendering `text` alone loses
    every `*Account Full Name*` the parser reads. The block walk below is
    what makes an API-fetched transcript parse the same as a connector one.
    """
    names = names or {}
    parts = []
    for b in msg.get("blocks") or []:
        if b.get("type") == "section":
            t = (b.get("text") or {}).get("text")
            if t:
                parts.append(t)
            for f in b.get("fields") or []:
                if f.get("text"):
                    parts.append(f["text"])
        elif b.get("type") == "rich_text":
            for el in b.get("elements") or []:
                rendered = _inline(el, names)
                if rendered.strip():
                    parts.append(rendered)
    if not parts and msg.get("text"):
        parts.append(msg["text"])
    return "\n".join(p.rstrip() for p in parts).strip()


# ── rendering: the connector's own shape ─────────────────────────────────

def render_channel(channel_id: str, channel_name: str, messages: list,
                   names: dict) -> str:
    """The channel transcript, in the format slack_intake.py parses."""
    out = [f"Channel: #{channel_name} ({channel_id})", ""]
    for m in messages:
        who, wid = _author(m, names)
        out.append(f"=== Message from {who} ({wid}) at {_when(m.get('ts'))} "
                   f"UTC ===")
        out.append(f"Message TS: {m.get('ts')}")
        body = _body(m, names)
        if body:
            out.append(body)
        n = int(m.get("reply_count") or 0)
        if n:
            latest = _when(m.get("latest_reply") or m.get("ts"))
            out.append(f"Thread: {n} replies (latest: {latest} UTC)")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_thread(parent: dict, replies: list, names: dict) -> str:
    """One thread, in the format slack_intake.py parses."""
    who, wid = _author(parent, names)
    out = ["=== THREAD PARENT MESSAGE ===",
           f"From: {who} ({wid})",
           f"Time: {_when(parent.get('ts'))} UTC",
           f"Message TS: {parent.get('ts')}"]
    body = _body(parent, names)
    if body:
        out.append(body)
    out.append("")
    out.append(f"=== THREAD REPLIES ({len(replies)} total) ===")
    for i, r in enumerate(replies, 1):
        rwho, rid = _author(r, names)
        out += ["", f"--- Reply {i} of {len(replies)} ---",
                f"From: {rwho} ({rid})",
                f"Time: {_when(r.get('ts'))} UTC",
                f"Message TS: {r.get('ts')}"]
        rbody = _body(r, names)
        if rbody:
            out.append(rbody)
        reacts = ", ".join(
            f"{x.get('name')} ({x.get('count')})" for x in r.get("reactions")
            or [] if x.get("name"))
        if reacts:
            out.append(f"Reactions: {reacts}")
    return "\n".join(out).rstrip() + "\n"


# ── the three things the intake needs ────────────────────────────────────

def fetch_channel(channel_id: str, limit: int = 50,
                  token: str | None = None) -> str:
    tok = token or bot_token()
    # THE CHANNEL'S NAME IS A LABEL. It goes in the transcript's header line
    # and nothing parses it — `render_channel` already falls back to the id,
    # and slack_intake reads message rows, never the header.
    #
    # But it is fetched with `conversations.info`, which requires
    # `channels:read`, while the messages come from `conversations.history`,
    # which requires `channels:history`. Measured 2026-08-30 on a live
    # intake firing: the bot token carried `channels:history` and NOT
    # `channels:read`, so `call()` raised on the label and the firing ended
    # having read nothing — reporting the channel unreadable when every
    # message in it was reachable with the scopes already granted.
    #
    # A cosmetic lookup may not decide whether the substantive one runs. The
    # id is a perfectly good header, so a refused name degrades to it and
    # the read proceeds.
    try:
        info = call("conversations.info", {"channel": channel_id}, token=tok)
        name = ((info.get("channel") or {}).get("name")) or channel_id
    except SlackError as e:
        print(f"note: channel name unavailable ({e}); using the id as the "
              f"header. Add `channels:read` for a friendlier transcript — "
              f"the messages below need only `channels:history`.",
              file=sys.stderr)
        name = channel_id
    hist = call("conversations.history",
                {"channel": channel_id, "limit": limit}, token=tok)
    msgs = hist.get("messages") or []
    # AUTHORS *and* MENTIONS. The connector renders a mention as
    # `<@Uxxx|Display Name>`, and `slack_intake._FOOTER` reads that
    # form to find where the workflow's assignee footer starts. Ids
    # repeat heavily across a channel, so `_users` dedupes this to a
    # handful of lookups.
    names = _users({m.get("user") for m in msgs}
                   | {u for m in msgs for u in _mentions(m)}, tok)
    return render_channel(channel_id, name, msgs, names)


def fetch_thread(channel_id: str, ts: str, token: str | None = None) -> str:
    tok = token or bot_token()
    out = call("conversations.replies",
               {"channel": channel_id, "ts": ts, "limit": 200}, token=tok)
    msgs = out.get("messages") or []
    if not msgs:
        raise SlackError(f"conversations.replies returned no parent for {ts}")
    parent, replies = msgs[0], msgs[1:]
    # AUTHORS *and* MENTIONS. The connector renders a mention as
    # `<@Uxxx|Display Name>`, and `slack_intake._FOOTER` reads that
    # form to find where the workflow's assignee footer starts. Ids
    # repeat heavily across a channel, so `_users` dedupes this to a
    # handful of lookups.
    names = _users({m.get("user") for m in msgs}
                   | {u for m in msgs for u in _mentions(m)}, tok)
    return render_thread(parent, replies, names)


def post_reply(channel_id: str, thread_ts: str, text: str,
               token: str | None = None) -> dict:
    """Post into a thread. The CALLER decides what may be said.

    This deliberately carries no judgment about folder links: that rule
    lives in slack_intake.completion_reply, which refuses to render one
    without --served, and putting a second copy of it here would be a second
    place to forget it.
    """
    if not thread_ts:
        raise SlackError(
            "refusing to post without a thread_ts: a completion reply "
            "belongs in the request's own thread, and a top-level message "
            "answers nobody")
    return call("chat.postMessage",
                {"channel": channel_id, "thread_ts": thread_ts, "text": text},
                token=token, post=True)


# ── CLI ──────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("whoami", help="prove the token works, print no secret")
    w.add_argument("--project", default=PROJECT)

    c = sub.add_parser("channel", help="fetch a channel as a transcript")
    c.add_argument("--channel", required=True)
    c.add_argument("--limit", type=int, default=50)
    c.add_argument("--out", default="")

    t = sub.add_parser("thread", help="fetch one thread as a transcript")
    t.add_argument("--channel", required=True)
    t.add_argument("--ts", required=True)
    t.add_argument("--out", default="")

    p = sub.add_parser("post", help="post a reply into a thread")
    p.add_argument("--channel", required=True)
    p.add_argument("--thread-ts", required=True)
    p.add_argument("--text", required=True)

    a = ap.parse_args(argv)

    if a.cmd == "whoami":
        out = call("auth.test", {}, token=bot_token(a.project))
        print(json.dumps({"ok": True, "team": out.get("team"),
                          "user": out.get("user"), "bot_id": out.get("bot_id"),
                          "url": out.get("url")}, indent=1))
        return 0

    if a.cmd == "channel":
        text = fetch_channel(a.channel, a.limit)
    elif a.cmd == "thread":
        text = fetch_thread(a.channel, a.ts)
    else:
        r = post_reply(a.channel, a.thread_ts, a.text)
        print(json.dumps({"ok": True, "ts": r.get("ts"),
                          "channel": r.get("channel")}, indent=1))
        return 0

    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"wrote {a.out} ({len(text)} chars)")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SlackError as e:
        print(f"slack: {e}", file=sys.stderr)
        raise SystemExit(2) from None
