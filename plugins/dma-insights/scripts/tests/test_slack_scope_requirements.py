"""What the doc calls REQUIRED must be what the code actually cannot survive.

MEASURED 2026-08-30, on a live `dma-assessment-intake` firing: the bot token
held `channels:history` and not `channels:read`, and the routine reported the
whole channel unreadable. Every message in it was reachable. The intake died
because `fetch_channel` asked `conversations.info` — which needs
`channels:read` — for the channel's DISPLAY NAME before it asked
`conversations.history` for the messages, and nothing anywhere parses that
name. A cosmetic lookup decided whether the substantive one ran.

The fix is in `fetch_channel`: the name lookup degrades to the channel id.
But the doc had listed all four scopes in one undifferentiated table, so an
operator provisioning the app had no way to know which two were load-bearing
— and once the code degrades a call, a doc that still calls it required sends
the next person chasing a scope they do not need.

SO THIS DERIVES IT. A Slack method whose call site is wrapped in
`except SlackError` is one this client survives losing; one that is not is
one it cannot. That property is read out of the SOURCE with `ast`, never
from a list typed here, and checked against the required column of
CONNECTORS.md § Scopes the bot needs. Add a degradation without relaxing the
doc, or tighten the doc without degrading the call, and this fails.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
CLIENT = SCRIPTS / "slack_client.py"
DOC = SCRIPTS.parents[0] / "docs" / "CONNECTORS.md"

#: Slack scope -> the API method this client spends it on. Only the join is
#: hand-written; whether that method is survivable is derived below. The
#: floor assertion beneath keeps a new scope row from going unchecked.
METHOD_OF = {
    "channels:history": "conversations.history",
    "channels:read": "conversations.info",
    "chat:write": "chat.postMessage",
    "users:read": "users.info",
}


def doc_table() -> dict:
    """scope -> required?, from the table in CONNECTORS.md."""
    out = {}
    for line in DOC.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*`([a-z]+:[a-z]+)`\s*\|(.*)\|\s*([^|]*)\|\s*$",
                     line)
        if m:
            out[m.group(1)] = "yes" in m.group(3).lower()
    return out


def degraded_methods() -> set:
    """Methods whose call site sits under an `except SlackError` handler.

    Walked outward from each call rather than inward from each try, so a
    handler three frames up still counts — it is the same property: this
    client keeps going without that method.
    """
    tree = ast.parse(CLIENT.read_text(encoding="utf-8"))
    parents = {}
    for node in ast.walk(tree):
        for kid in ast.iter_child_nodes(node):
            parents[kid] = node

    def catches_slackerror(handler: ast.ExceptHandler) -> bool:
        t = handler.type
        names = ([t] if isinstance(t, ast.Name) else
                 list(t.elts) if isinstance(t, ast.Tuple) else [])
        return any(getattr(n, "id", "") in ("SlackError", "Exception")
                   for n in names)

    out = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "call"
                and node.args
                and isinstance(node.args[0], ast.Constant)):
            continue
        method, cur, child = node.args[0].value, parents.get(node), node
        while cur is not None:
            if (isinstance(cur, ast.Try) and child in cur.body
                    and any(catches_slackerror(h) for h in cur.handlers)):
                out.add(method)
                break
            child, cur = cur, parents.get(cur)
    return out


def test_the_scope_table_is_still_parseable():
    """Floor: an unparsed table makes every check below vacuous."""
    got = doc_table()
    assert set(got) == set(METHOD_OF), (
        f"CONNECTORS.md lists {sorted(got)} and this test knows "
        f"{sorted(METHOD_OF)} — map the new scope to the method it buys "
        f"before it can go unchecked")
    assert any(got.values()) and not all(got.values()), (
        "a table where every scope is required, or none is, is the "
        "undifferentiated list this test exists to replace")


def test_a_scope_is_required_exactly_when_losing_it_stops_the_client():
    disagree = {}
    deg = degraded_methods()
    for scope, required in doc_table().items():
        method = METHOD_OF[scope]
        if required is (method in deg):
            disagree[scope] = (
                f"doc says required={required}, but {method} is "
                f"{'degraded in' if method in deg else 'fatal in'} "
                f"slack_client.py")
    assert not disagree, (
        "the doc and the code disagree about what this client can survive "
        f"losing: {disagree}")


def test_the_channel_read_itself_is_never_degraded():
    """The one that must never join the degraded set. A transcript with no
    messages and no error is the queue defect this whole client exists to
    prevent — 'nobody asked' and 'we could not look' must stay different."""
    assert "conversations.history" not in degraded_methods()


def test_the_cosmetic_lookups_are_degraded():
    """The other direction, so nobody 'fixes' this by re-raising."""
    deg = degraded_methods()
    for method in ("conversations.info", "users.info"):
        assert method in deg, (
            f"{method} is a label lookup that decides nothing the parser "
            f"reads; letting it raise makes a missing scope look like an "
            f"empty channel")
