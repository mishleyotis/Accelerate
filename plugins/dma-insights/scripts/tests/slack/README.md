# Recorded #deal-desk responses

Real `mcp__Slack__slack_read_channel` and `slack_read_thread` output, captured
2026-08-30, with nothing rewritten.

WHY RECORDED RATHER THAN SYNTHESISED. The Slack connector does not return
Slack's JSON; it returns a RENDERED TEXT format of its own, and the intake
parser has to read that. A fixture written from the API docs would be a
fixture of a format nobody sends. These are what the tool actually returned.

They carry, on purpose, every case the queue has to get right:

| case | where |
|---|---|
| a DMA request with no replies at all | GoEasy |
| a DMA request whose only reply is a colleague's FYI | REV FCU, Bank of Travelers Rest |
| a DELIVERED request — the owner replied with a Drive FOLDER link | Richwood Bank |
| the owner replying with NO link, in the same thread | Richwood Bank, reply 3 |
| a different workflow in the same channel, for a different person | Hubbl Readout Request (B0ANFBBJ5D3) |
| a request resubmitted after the first errored | Gulf Coast Business Credit |

`channel.txt` is one page of history (the tool paginates); `thread_*.txt` are
the threads named in the table.
