/* The why-now card face, and the client name that shattered it.
 *
 * Measured on the promoted T. Rowe Price run (7a6ad71c), every why-now card
 * rendered its face as a fragment of the client's own name:
 *
 *     WN-2  "T."
 *     WN-3  "On the 7 August 2026 Q2 earnings call, chief executive Rob
 *            Sharps told analysts T."
 *     WN-4  "On the same 7 August 2026 Q2 2026 earnings call, T."
 *
 * `headlineOf` cuts the trigger at the first full stop followed by whitespace
 * and a capital. That is a sentence boundary — and it is also, exactly, an
 * initial in front of a surname. The existing guard protected "$6.5 billion"
 * and "Jan. 2026" because a DIGIT follows the stop; nobody had a client whose
 * name begins with an initial, so the mirror case shipped.
 *
 * Driven through `whyNowFor`, the accessor the page actually calls, against
 * the compiled bundle — not the private helper. A test that reached past the
 * public surface would keep passing if the card stopped using it.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const win = require("./adapter-window.js");

/* The real shape: the `why_now` SECTION, whose `signals` each carry the
   contract's `trigger`. `adaptWhyNow` is what the page's accessor calls. */
function face(trigger) {
  const out = win.adaptWhyNow({ signals: [{ wn_id: "WN-1", kind: "LEADERSHIP", trigger }] });
  assert.ok(out && out.length === 1, "adaptWhyNow should adapt one signal");
  return out[0].label;
}

// ── the defect ──

test("an initial in the client name is not a sentence end", () => {
  const trigger = "T. Rowe Price consolidated two C-suite functions in "
    + "November 2025 — Technology, Data and Operations under chief technology "
    + "officer Ramon Richards on 3 November.";
  const label = face(trigger);
  assert.notStrictEqual(label, "T.", "the face rendered the client's initial");
  assert.ok(label.startsWith("T. Rowe Price consolidated"),
    `face lost the sentence: ${JSON.stringify(label)}`);
});

test("an initial mid-sentence does not cut the face short", () => {
  const trigger = "On the 7 August 2026 Q2 earnings call, chief executive Rob "
    + "Sharps told analysts T. Rowe Price has moved beyond isolated use cases.";
  const label = face(trigger);
  assert.ok(label.includes("has moved beyond isolated use cases"),
    `face cut at the initial: ${JSON.stringify(label)}`);
});

test("multi-initial names survive too", () => {
  for (const name of ["J.P. Morgan", "A.G. Edwards", "U.S. Bancorp"]) {
    const label = face(`${name} announced a core conversion in March 2026.`);
    assert.ok(label.startsWith(name),
      `${name} was cut: ${JSON.stringify(label)}`);
  }
});

test("a title abbreviation is not a sentence end", () => {
  const label = face("Dr. Alice Chen was appointed chief data officer in May 2026.");
  assert.ok(label.startsWith("Dr. Alice Chen"),
    `abbreviation cut the face: ${JSON.stringify(label)}`);
});

// ── what must not regress: the guards that were already right ──

test("a real sentence boundary still ends the face", () => {
  const label = face("The board approved the roadmap on 12 June 2026. The "
    + "conversion begins in the third quarter and runs for eighteen months.");
  assert.strictEqual(label, "The board approved the roadmap on 12 June 2026.");
});

test("a decimal is not a sentence end", () => {
  const label = face("Net outflows reached $6.5 billion in the quarter against "
    + "a record $1.89 trillion in assets.");
  assert.ok(label.includes("$6.5 billion"), `decimal split: ${JSON.stringify(label)}`);
});

test("a month abbreviation before a year is not a sentence end", () => {
  const label = face("The filing landed Jan. 2026 and named three new "
    + "technology seats.");
  assert.ok(label.includes("Jan. 2026"), `date split: ${JSON.stringify(label)}`);
});

test("the em dash still hands the elaboration to the drilldown", () => {
  const label = face("The credit union announced a leadership evolution on 1 "
    + "July 2026 — Jim Block steps into a newly created chief digital seat.");
  assert.ok(!label.includes("Jim Block"),
    `elaboration reached the face: ${JSON.stringify(label)}`);
  assert.ok(label.endsWith("1 July 2026"), JSON.stringify(label));
});

test("a short leading dash clause is kept, not cut to nothing", () => {
  // The `dash > 24` guard: cutting here would leave a stub, not a summary.
  const label = face("AI — the firm's stated priority for 2026 — now has a "
    + "named owner.");
  assert.ok(label.length > 24, `face cut to a stub: ${JSON.stringify(label)}`);
});

test("the whole trigger stands when there is no boundary at all", () => {
  const trigger = "A single clause with no terminator that simply runs on";
  assert.strictEqual(face(trigger), trigger);
});
