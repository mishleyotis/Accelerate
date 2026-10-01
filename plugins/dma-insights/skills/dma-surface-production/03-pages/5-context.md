# Page: context

Five sections. INTERNAL ONLY — the whole dashboard is withheld from the customer audience, but that does not relax the identity gate or citation.

**5 sections · 6 surfaces.** Submit with `submit_page_payload(run_id, page='context', payload={...})`.

Read `01-start-here/1-standing-clauses.md` before writing any section on this page. The standing clauses apply to every section and are not repeated below.

## Sections on this page

| Section | Required | Surfaces | Renders on |
|---|---|---|---|
| `timeline` | yes | C1 | D5 |
| `issue_register` | yes | C2 | D5 |
| `regulatory_standing` | yes | C3 | D5 |
| `context_sentiment` | yes | C4 | D5 |
| `acquisitions` | yes | C5 | D5 |
| — | — | C6 | D5 (renders `overview.financial_series`) |

**C6 is not a section of this page.** The financial trajectory card on D5 renders
`overview.financial_series` — the same section, the same row, the same
`reading`. You do not produce it twice and you cannot make the two cards
disagree, because there is only one. Write it on the overview page.

### C6 · five points is the floor, and it is a research floor

The card is a bar chart with a CAGR under it. Three bars is not a trajectory — it is a
line through two gaps, and it reads as thin research to the one audience that opens this
page. Ship **at least five dated points on one metric definition**, and take the deceleration
with them: a series that grows 13% · 13% · 2.5% · 2.1% · 5.3% tells a story a single CAGR
flattens away, and that story is usually the point.

Three failures produced the three-point cards already shipped, all of them repairable
before submission:

- **Points sourced from whatever press release mentioned a number.** The figures then carry
  the release date rather than a reporting period, round to the nearest billion, and lag the
  filing by two quarters. `01-start-here/2-evidence.md` has the regulator route per
  institution type — for a credit union, one NCUA quarterly file per December.
- **`source_e_id` pointing at a row that says something else.** Measured on a promoted run:
  the FY2023 asset point cited an annual-report row whose excerpt was about NPS, and the
  2025-Q3 point cited an Indeed employee rating. The id resolved, the chip opened, and it
  answered a different question. A financial point cites the source **of that figure, for
  that period**, or it does not ship.
- **Reading the newest number as the newest year-end.** Quarterly filers publish a cycle
  above the last December. Keep each figure on its own stated date: an institution can be
  $6.34B at 2025-12-31, $6.50B at 2026-03-31 and $6.40B at 2026-06-30 without any of them
  being wrong, and averaging them or picking the flattering one is the defect. Where a
  quarter falls, say so in `reading` rather than letting a rising chart imply it did not.

`trend` is COMPUTED from the emitted points and stays inside the contract's four words —
`GROWING │ STABLE │ DECLINING │ VOLATILE`. The prototype's "ACCELERATING" badge is not one
of them; render the contract's word.

## Internal only, and what that does not excuse

Withheld from the customer audience does not mean unmarked. Audience redaction
is server-side and **default-deny**: a path you do not mark is a path that
reaches whoever can see the page. Two things still apply on every section here:

- Mark the internal rungs in `internal_only[]` — the redaction walker strips the
  paths you name, and only those.
- The identity gate, citation and the recency ladder are unchanged. An internal
  reader acts on this page; a wrong regulator or an unresolvable evidence chip
  costs the same credibility it would cost in front of the client.

## Surfaces on this page — one file each

The per-surface files carry the contract, the must-present list, the information sources and the synthesis prompt for one surface. A producer reads the file for the surface it owns, never the whole page; the page-wide rules above apply to every one of them.

- `context/C1.md` — C1 · Digital evolution timeline
- `context/C2.md` — C2 · Issue register &amp; Gantt
- `context/C3.md` — C3 · Regulatory standing
- `context/C4.md` — C4 · Sentiment overview
- `context/C5.md` — C5 · Acquisition history
