#!/usr/bin/env python3
"""The assessment queue, read out of #deal-desk instead of scanned off Drive.

    slack_intake.py threads  --transcript <channel.txt>
    slack_intake.py triage   --transcript <channel.txt> [--threads <dir|file>]
                             [--since-days 5] [--now 2026-08-30] [--json]
    slack_intake.py request  --client "Acme Credit Union" [--website URL]
                             [--requested-by "@name"] [--json]

WHY THIS EXISTS. The intake Routine fired hourly and scanned Google Drive for
folders — the wrong flow, at the wrong cadence, spending a session per hour on
a tree that only changes when somebody has already done the work by hand. The
requests do not arrive in Drive. They arrive in Slack, from a workflow, in a
channel, addressed to a person, and they are finished when that person replies
with the folder link.

    owner, 2026-08-30: "The current routine is spending tokens on the wrong
    flow."

WHY IT DOES NOT CALL SLACK. There is no Slack credential in this repository —
no token, no key file, nothing to mint one from; `drive_fetch.py` works only
because a service-account key IS provisioned. So this file does the half a
script can do honestly: it DECIDES, offline, over a transcript the session
fetched with the connector tools it already carries. That split is what makes
the rule testable over recorded fixtures in CI and live in a firing, with the
same code deciding both — the technique `routine_health.py` documents.

THE RULE, in one line:

    A request is DELIVERED when the OWNER replied in its thread with a Google
    Drive FOLDER link. Anything else is PENDING. Anything that cannot be
    evaluated is UNDECIDABLE — never PENDING, because starting a run that was
    already delivered is the expensive mistake.

Three states, not two, for the reason that runs through this whole codebase:
a check that cannot tell must say so rather than pick the cheerful answer.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── the identities, declared once ────────────────────────────────────────
#
# None of these appeared anywhere in this repository before 2026-08-30. This
# file is their home; a prompt that re-types one of them is a second source of
# truth, which is how the pinned-client defect happened (docs/CLIENT-SELECTION).

#: #deal-desk — where the requests arrive.
DEAL_DESK_CHANNEL_ID = "C0AD83KJ4DU"

#: The Slack workflow that posts DMA requests: "Assessment and Research
#: Request". The shortcut is what a human sees; the bot id is what the API
#: returns, and both are recorded because neither alone survives a rename.
DMA_REQUEST_BOT_ID = "B0ACUPDCMGF"
DMA_REQUEST_BOT_NAME = "Assessment and Research Request"
DMA_REQUEST_SHORTCUT = "Ft0ADDPFSHK6"

#: "Hubbl Readout Request" posts in the SAME channel, in a similar shape, and
#: is assigned to a different person. It is not this flow and must never be
#: picked up. Named rather than merely unmatched: a bot that is simply absent
#: from a list cannot be told apart from one nobody thought about.
NOT_THIS_FLOW_BOT_ID = "B0ANFBBJ5D3"
NOT_THIS_FLOW_BOT_NAME = "Hubbl Readout Request"

#: The owner. A reply from them CARRYING A FOLDER LINK is delivery.
DELIVERY_USER_ID = "U09TL2S4LLS"

#: The delivery marker. `/drive/folders/` and not merely `drive.google.com`:
#: a link to a FILE, a Doc or a Sheet is not the folder the request asked for.
FOLDER_LINK = re.compile(
    r"https?://drive\.google\.com/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]{10,})")

PENDING, DELIVERED, UNDECIDABLE = "PENDING", "DELIVERED", "UNDECIDABLE"

#: Ordering. The workflow offers exactly these; an unrecognised one sorts
#: last rather than being renamed into a bucket it did not choose.
PRIORITY_ORDER = {"urgent": 0, "high": 1}


# ── parsing the transcript the connector actually returns ────────────────
#
# The Slack connector does not return Slack's JSON. It returns a rendered
# text format of its own, and this parser reads THAT — a parser written from
# the API docs would be a parser for a shape nobody sends. The fixtures under
# tests/slack/ are recordings, not constructions, for the same reason.

_MSG = re.compile(
    r"^=== Message from (?P<who>.+?) \((?P<bot>[A-Z0-9]+)\) at "
    r"(?P<when>[\d\-: ]+?) \w+ ===\s*$", re.M)
_TS = re.compile(r"^Message TS: (?P<ts>\d+\.\d+)\s*$", re.M)
_REPLY = re.compile(r"^--- Reply \d+ of \d+ ---\s*$", re.M)
_FROM = re.compile(r"^From: (?P<name>.*?)\s*\((?P<uid>[A-Z0-9]+)\)\s*$", re.M)


#: The workflow's fixed footer: the line that @-mentions the assignee and
#: states the ask. It ends the LAST field, which is otherwise unbounded —
#: without it `*Priority*` swallowed the footer and the priority read
#: "High (need in 48 hours)\n\n<@U09TL2S4LLS|…> Please run the maturity…",
#: which sorts and prints as nonsense.
_FOOTER = re.compile(r"^<@U[A-Z0-9]+\|", re.M)


def _field(body: str, label: str) -> str:
    """A `*Label*` block: the lines under it, up to the next `*Label*` — or
    the assignee footer, whichever comes first."""
    m = re.search(rf"^\*{re.escape(label)}\*\s*$", body, re.M)
    if not m:
        return ""
    rest = body[m.end():]
    ends = [x.start() for x in
            (re.search(r"^\*[A-Z][^*\n]*\*\s*$", rest, re.M),
             _FOOTER.search(rest)) if x]
    chunk = rest[:min(ends)] if ends else rest
    return "\n".join(ln.strip() for ln in chunk.strip().splitlines()).strip()


def _slug(s: str) -> str:
    """`runstate._slug`, reproduced rather than imported.

    The engine lives under a skill and is imported by path; a scripts/ file
    that reached into it would bind this queue to that import working. The
    expression is four tokens long and pinned by a test that asserts the two
    agree — a copy that is CHECKED is safer here than an import that is not.
    """
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "entity"


def parse_channel(text: str) -> dict:
    """Every message in a channel transcript, DMA requests marked."""
    starts = list(_MSG.finditer(text or ""))
    if not starts:
        raise SystemExit(
            "REFUSED: this does not look like a slack_read_channel "
            "transcript — no '=== Message from … ===' header anywhere. Save "
            "the tool's output verbatim; a reformatted transcript is a "
            "transcript of something else.")
    out = []
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        block = text[m.end():end]
        ts = _TS.search(block)
        row = {
            "author_name": m.group("who").strip(),
            "author_id": m.group("bot"),
            "posted_at": m.group("when").strip(),
            "ts": ts.group("ts") if ts else "",
            "body": block[ts.end():] if ts else block,
            "reply_count": _reply_count(block),
        }
        row["is_dma_request"] = _is_dma_request(row)
        out.append(row)
    return {"messages": out}


def _reply_count(block: str) -> int | None:
    """`Thread: N replies`. None when the line is absent, which the connector
    means as ZERO — but None is carried rather than 0 so a caller can tell
    'the transcript said none' from 'the transcript did not say'."""
    m = re.search(r"^Thread: (\d+) replies", block, re.M)
    return int(m.group(1)) if m else None


def _is_dma_request(row: dict) -> bool:
    """The bot id first, its name second, and the shape LAST.

    Never shape-only. The Hubbl workflow posts in the same channel with
    *Submitter*, *Priority* and a Drive link, and admitting it would start
    assessments for another person's queue.
    """
    if row["author_id"] == NOT_THIS_FLOW_BOT_ID:
        return False
    if row["author_id"] == DMA_REQUEST_BOT_ID:
        return True
    if row["author_name"] == DMA_REQUEST_BOT_NAME:
        return True
    return False


def parse_request(row: dict) -> dict:
    """One DMA request, as the fields the workflow posts."""
    body = row["body"]
    account = _field(body, "Account Full Name")
    website = _field(body, "Website")
    out = {
        "ts": row["ts"],
        "posted_at": row["posted_at"],
        "account": account,
        "website": _unwrap(website),
        "context": _field(body, "Additional Context"),
        "submitter": _field(body, "Submitter"),
        "priority": _field(body, "Priority"),
        "reply_count": row["reply_count"],
    }
    out["entity_id"] = _slug(account)
    # The RUN id, minted deterministically so two firings that see the same
    # request agree on it rather than starting the client twice.
    out["run_id"] = f"{out['entity_id']}-{row['ts'].replace('.', '')}"[:64]
    # The reference date is the REQUEST's, never today's: an assessment
    # answers the question as it was asked.
    out["reference_date"] = (row["posted_at"] or "")[:10]
    return out


def _unwrap(v: str) -> str:
    """Slack wraps links in angle brackets and may carry a `|label`."""
    v = (v or "").strip()
    m = re.match(r"^<([^|>]+)(?:\|[^>]*)?>$", v)
    return m.group(1) if m else v


def parse_thread(text: str) -> dict:
    """A thread transcript: the parent ts, and one row per reply."""
    ts = _TS.search(text or "")
    marks = list(_REPLY.finditer(text or ""))
    replies = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        block = text[m.end():end]
        who = _FROM.search(block)
        body = block[who.end():] if who else block
        replies.append({
            "author_id": who.group("uid") if who else "",
            "author_name": who.group("name").strip() if who else "",
            "text": body.strip(),
        })
    return {"parent_ts": ts.group("ts") if ts else "", "replies": replies}


# ── the decision ─────────────────────────────────────────────────────────

def verdict(request: dict, thread: dict | None) -> dict:
    """PENDING · DELIVERED · UNDECIDABLE, with the reason."""
    if not request.get("account"):
        return _v(UNDECIDABLE, "the request carries no *Account Full Name*, "
                               "and the account is not derivable from the "
                               "website without guessing which legal entity "
                               "a domain belongs to")
    n = request.get("reply_count")
    if thread is None:
        if not n:
            # The connector omits the Thread: line when there are no replies,
            # so no replies means nobody has answered — including the owner.
            return _v(PENDING, "no replies at all, so no delivery")
        return _v(UNDECIDABLE,
                  f"{n} repl(y|ies) the transcript does not contain — read "
                  f"the thread before deciding. A request whose thread was "
                  f"not fetched must never read as pending: that is how a "
                  f"delivered client gets assessed twice")
    for r in thread.get("replies", []):
        if r.get("author_id") != DELIVERY_USER_ID:
            continue
        m = FOLDER_LINK.search(r.get("text") or "")
        if m:
            return _v(DELIVERED, "the owner replied with the folder link",
                      folder_id=m.group(1))
    owner_replies = sum(1 for r in thread.get("replies", [])
                        if r.get("author_id") == DELIVERY_USER_ID)
    if owner_replies:
        return _v(PENDING,
                  f"the owner replied {owner_replies} time(s) but never with "
                  f"a Drive FOLDER link, so the assessment has not been "
                  f"handed over")
    return _v(PENDING, "nobody has replied with the folder link")


def _v(state: str, why: str, **kw) -> dict:
    return {"state": state, "why": why, **kw}


def _within(request: dict, since_days: int, now: datetime) -> bool:
    try:
        when = datetime.strptime(request["reference_date"], "%Y-%m-%d")
    except (KeyError, ValueError):
        return True                    # undatable: let the verdict decide
    return when.replace(tzinfo=timezone.utc) >= now - timedelta(
        days=since_days)


def _rank(request: dict) -> tuple:
    word = (request.get("priority") or "").strip().lower().split(" ")[0]
    return (PRIORITY_ORDER.get(word, 9), request.get("ts") or "")


def triage(channel_text: str, threads: dict[str, dict] | None = None,
           since_days: int = 5, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    threads = threads or {}
    doc = parse_channel(channel_text)
    rows, skipped = [], []
    for msg in doc["messages"]:
        if not msg["is_dma_request"]:
            skipped.append({"ts": msg["ts"], "author": msg["author_name"],
                            "why": ("a different workflow in the same channel"
                                    if msg["author_id"] == NOT_THIS_FLOW_BOT_ID
                                    else "not the DMA request workflow")})
            continue
        req = parse_request(msg)
        if not _within(req, since_days, now):
            continue
        req.update(verdict(req, threads.get(req["ts"])))
        rows.append(req)

    # A request RE-POSTED for the same account (it happens: "Resubmitting as
    # my initial request error'd out") must not start two runs. The newest
    # undelivered one is the live request; older undelivered ones are
    # superseded by it, and a DELIVERED one is never touched.
    newest: dict[str, str] = {}
    for r in sorted(rows, key=lambda x: x["ts"]):
        if r["state"] == PENDING:
            newest[r["entity_id"]] = r["ts"]
    for r in rows:
        if r["state"] == PENDING and newest.get(r["entity_id"]) != r["ts"]:
            r.update(_v("SUPERSEDED",
                        f"a newer request for {r['account']} is pending "
                        f"(ts {newest[r['entity_id']]}); one client, one run"))

    pending = sorted([r for r in rows if r["state"] == PENDING], key=_rank)
    return {
        "channel": DEAL_DESK_CHANNEL_ID,
        "since_days": since_days,
        "requests": rows,
        "pending": pending,
        "delivered": [r for r in rows if r["state"] == DELIVERED],
        "undecidable": [r for r in rows if r["state"] == UNDECIDABLE],
        "not_this_flow": skipped,
    }


def threads_to_read(channel_text: str, since_days: int = 5,
                    now: datetime | None = None) -> list[dict]:
    """The (channel_id, message_ts) pairs the session must read next.

    Emitted rather than left to the session to work out, so a `ts` is never
    typed by hand into a tool call. Only requests that HAVE replies need a
    thread; one with none is already decidable.
    """
    out = []
    for r in triage(channel_text, since_days=since_days, now=now)["requests"]:
        if r.get("reply_count"):
            out.append({"channel_id": DEAL_DESK_CHANNEL_ID,
                        "message_ts": r["ts"], "account": r["account"]})
    return out


def manual_request(client: str, website: str = "", requested_by: str = "",
                   now: datetime | None = None) -> dict:
    """The owner names a client and it starts.

    Identical in shape to a Slack-borne request so the downstream path cannot
    tell them apart — a manual run that took a different code path would be a
    second pipeline nobody tests.
    """
    if not (client or "").strip():
        raise SystemExit("REFUSED: --client is the whole input; there is "
                         "nothing to assess without it")
    now = now or datetime.now(timezone.utc)
    eid = _slug(client)
    return {
        "ts": "", "posted_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "account": client.strip(), "website": website.strip(),
        "context": "", "submitter": requested_by.strip() or "the owner",
        "priority": "Manual", "reply_count": None,
        "entity_id": eid,
        "run_id": f"{eid}-{now.strftime('%Y%m%d%H%M%S')}"[:64],
        "reference_date": now.strftime("%Y-%m-%d"),
        "state": PENDING, "why": "named by the owner",
        "source": "manual",
    }


# ── the answer that closes the thread ────────────────────────────────────

def completion_reply(account: str, folder_url: str, *, served: bool,
                     run_id: str = "") -> dict:
    """The text that answers the request, and the refusal that guards it.

    THE TRAP THIS CLOSES. The connector sends AS THE OWNER, so this reply is
    itself what makes the request read DELIVERED to the next triage. And
    `engine.cli start` opens `<Entity> - DMA` in the intake Drive at minute
    one with `status: IN_PROGRESS` — so a folder link is postable long before
    there is anything in the folder. Posting one early would mark the request
    answered, take it out of every future queue, and leave the requester with
    a link to an empty folder.

    So the link is refused until the package is COMPLETE and the run is
    SERVED. There is no flag to override it: a caller who wants to say
    something before then can say it without a folder link, and a message
    without a folder link does not close the thread.
    """
    if not (account or "").strip():
        raise SystemExit("REFUSED: the reply must name the account it answers")
    if not served:
        raise SystemExit(
            "REFUSED: no folder link until the assessment is SERVED. The "
            "client folder exists from run start with status IN_PROGRESS, "
            "and this reply is what marks the request delivered — posting it "
            "early takes the request out of the queue and hands the "
            "requester an empty folder. Say something without a link, or "
            "wait.")
    if not FOLDER_LINK.search(folder_url or ""):
        raise SystemExit(
            f"REFUSED: {folder_url!r} is not a Drive FOLDER link. A file, a "
            f"Doc or a Sheet is not what the request asked for, and would "
            f"not read as delivered on the next pass either.")
    text = (f"Hi team, the DMA for {account.strip()} has been finalized and "
            f"is live on the app. Please find the folder here: {folder_url}")
    return {"text": text, "account": account.strip(), "run_id": run_id,
            "channel_id": DEAL_DESK_CHANNEL_ID,
            "reads_as_delivered": bool(
                FOLDER_LINK.search(text)) }


# ── CLI ──────────────────────────────────────────────────────────────────

def _read(p: str) -> str:
    return Path(p).read_text(encoding="utf-8", errors="ignore")


def _load_threads(path: str | None) -> dict[str, dict]:
    if not path:
        return {}
    p = Path(path)
    files = sorted(p.glob("thread_*.txt")) if p.is_dir() else [p]
    out = {}
    for f in files:
        t = parse_thread(_read(str(f)))
        if t["parent_ts"]:
            out[t["parent_ts"]] = t
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("threads", help="the (channel, ts) pairs to read next")
    t.add_argument("--transcript", required=True)
    t.add_argument("--since-days", type=int, default=5)
    t.add_argument("--now")

    g = sub.add_parser("triage", help="the queue: pending, delivered, "
                                      "undecidable")
    g.add_argument("--transcript", required=True)
    g.add_argument("--threads", help="a thread transcript, or a directory of "
                                     "them")
    g.add_argument("--since-days", type=int, default=5)
    g.add_argument("--now")
    g.add_argument("--json", action="store_true")

    r = sub.add_parser("request", help="the manual path: name a client")
    r.add_argument("--client", required=True)
    r.add_argument("--website", default="")
    r.add_argument("--requested-by", default="")
    r.add_argument("--json", action="store_true")

    y = sub.add_parser("reply", help="the completion text for the thread")
    y.add_argument("--client", required=True)
    y.add_argument("--folder-url", required=True)
    y.add_argument("--run", default="")
    y.add_argument("--served", action="store_true",
                   help="the run is PROMOTED and the app serves it. Without "
                        "this the folder link is refused: the reply is what "
                        "marks the request delivered")
    y.add_argument("--json", action="store_true")

    a = ap.parse_args(argv)
    now = (datetime.strptime(a.now, "%Y-%m-%d").replace(tzinfo=timezone.utc)
           if getattr(a, "now", None) else None)

    if a.cmd == "threads":
        rows = threads_to_read(_read(a.transcript), a.since_days, now)
        print(json.dumps(rows, indent=1))
        return 0

    if a.cmd == "request":
        one = manual_request(a.client, a.website, a.requested_by)
        print(json.dumps(one, indent=1) if a.json
              else f"INTAKE: PENDING {one['entity_id']} "
                   f"run={one['run_id']} \"{one['account']}\" (manual)")
        return 0

    if a.cmd == "reply":
        one = completion_reply(a.client, a.folder_url, served=a.served,
                               run_id=a.run)
        print(json.dumps(one, indent=1) if a.json else one["text"])
        return 0

    out = triage(_read(a.transcript), _load_threads(a.threads),
                 a.since_days, now)
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        print(f"#deal-desk, last {out['since_days']} day(s): "
              f"{len(out['pending'])} pending · {len(out['delivered'])} "
              f"delivered · {len(out['undecidable'])} undecidable · "
              f"{len(out['not_this_flow'])} not this flow\n")
        for r in out["pending"]:
            print(f"  PENDING     {r['entity_id']:34s} ts={r['ts']} "
                  f"[{r['priority']}]\n              \"{r['account']}\" — "
                  f"{r['why']}")
        for r in out["undecidable"]:
            print(f"  UNDECIDABLE {r['entity_id']:34s} ts={r['ts']}\n"
                  f"              {r['why']}")
        for r in out["delivered"]:
            print(f"  delivered   {r['entity_id']:34s} "
                  f"folder={r.get('folder_id', '?')}")
    if out["undecidable"]:
        return 2                    # "I could not tell" is not "none pending"
    return 0 if out["pending"] else 1


if __name__ == "__main__":
    sys.exit(main())
