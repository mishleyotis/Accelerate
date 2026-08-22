/* G6 — a documented absence must be legible, and must never take the page down.
 *
 * Two defects, one root: a payload field that is legitimately absent.
 *
 * THE CRASH. `pages-d5-d6-tech-runs.jsx` rendered an evidence excerpt as
 * `e.excerpt.slice(0, 140)` with no guard. An ingested evidence row can carry
 * no excerpt at all — measured on Logix run d7ed1d90, 36 of 62 rows — so this
 * threw a TypeError and the tech-stack evidence card rendered nothing. Every
 * other excerpt site in proto/ already states the absence instead; this one
 * was the outlier, and it is a large part of what "no confirmed tech stack"
 * looked like on a screen. A guard on one line does not stop the next one, so
 * the rule is linted over the whole tree.
 *
 * THE SILENCE. `EnrichmentGap` returned null unconditionally. That was right
 * for the 61 call sites that pass only a field label — they have nothing to
 * say but our own workflow vocabulary, and "queued for enrichment" names a
 * backlog the reader is not party to. It was wrong for the two that pass a
 * producer-authored reason: the ladder ran, it returned nothing, and why is a
 * finding. That sentence renders now, with no status word in front of it.
 */
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const PROTO = path.join(__dirname, "..", "proto");

// Payload fields that are nullable by contract — an absence is a legal value
// for every one of them, so `x.FIELD.method()` is a crash waiting for the
// client whose run happens not to carry it.
const NULLABLE_TEXT = [
  "excerpt", "quarantine_reason", "closure_condition", "narrative_thread",
  "detection_basis", "dma_impact", "rationale", "limiting_absence",
  "plain_label", "framing_sentence", "source_url",
];

// `pages-live-client.jsx` is 2,693 lines that app/route.js ships to every
// browser and nothing mounts — recorded as H3 in tests/acceptance/ACCEPTANCE.md
// ("defined, exported and mounted nowhere"). Its two hits here are `.length`
// and `.map` on a `dma_impact` it treats as an array, which is a different
// shape from the prose field the live payload carries, so linting it would be
// measuring a module that does not run. Excluded by name rather than by a
// looser rule, so that deleting the module deletes this line too.
const UNMOUNTED = new Set(["pages-live-client.jsx"]);

function protoSources() {
  return fs.readdirSync(PROTO)
    .filter((f) => f.endsWith(".jsx") && !UNMOUNTED.has(f))
    .map((f) => [f, fs.readFileSync(path.join(PROTO, f), "utf8")]);
}

test("no nullable payload field is dereferenced without a guard", () => {
  const offenders = [];
  for (const [file, src] of protoSources()) {
    const lines = src.split("\n");
    for (const field of NULLABLE_TEXT) {
      // `.field.` — a member access straight off the nullable value. The
      // guarded forms in this codebase all go through a coercer first
      // (dwText/asText/pfText) or test the value before reaching for it.
      const re = new RegExp(`\\.${field}\\.\\s*[a-zA-Z]`);
      lines.forEach((line, i) => {
        if (re.test(line)) offenders.push(`${file}:${i + 1}  ${line.trim().slice(0, 110)}`);
      });
    }
  }
  assert.deepStrictEqual(offenders, [],
    "a nullable payload field is dereferenced directly. Route it through "
    + "dwText/asText/pfText, or test it first — a run that does not carry it "
    + "takes the whole card down with a TypeError:\n" + offenders.join("\n"));
});

test("EnrichmentGap renders a producer-authored reason", () => {
  const src = fs.readFileSync(path.join(PROTO, "utils.jsx"), "utf8");
  const body = src.slice(src.indexOf("function EnrichmentGap"));
  const end = body.indexOf("\n}\n");
  const fn = body.slice(0, end);

  assert.ok(/const why = /.test(fn) && /if \(!why\) return null;/.test(fn),
    "EnrichmentGap must render a passed `reason` and nothing without one. An "
    + "unconditional `return null` discards the only real information the "
    + "component is ever handed.");
  assert.ok(/data-gap="reason"/.test(fn),
    "the rendered reason needs its own marker so a render test can find it");
  // Not asserting the old vocabulary is absent from the file. It survives
  // twice on purpose — in the owner's adjudication, quoted verbatim, and in
  // the dead branch kept below the return so the policy and its history live
  // in one place. A test that grepped for the words would be asserting
  // against the documentation, which is how a rule loses the reason it
  // exists. What matters is the early return, and that is asserted above.
});

test("a section's declared absence renders its reason, closure and ladder", () => {
  const src = fs.readFileSync(path.join(PROTO, "utils.jsx"), "utf8");
  const fn = src.slice(src.indexOf("function SectionEmpty("),
                       src.indexOf("function SectionEmptyFoot"));
  for (const owed of ["es.reason", "closure_condition", "sources_searched"]) {
    assert.ok(fn.includes(owed),
      `SectionEmpty stopped rendering ${owed}. The producer runs a documented `
      + "ladder before it is allowed to state an absence; dropping the record "
      + "turns a finding back into a blank space.");
  }
});

test("the client view defaults to the body a client may read", () => {
  /* Audience is a UI toggle, not a role-derived value, so whatever this says
     is what every reader gets on first paint.

     IT HAS BEEN BOTH VALUES, and this case has asserted both. "internal" put
     the reasoning traces, the capability ceilings and the evidence census in
     front of anyone who opened a client, and it was reported three times. It
     was reversed to "customer" on 2026-08-18 — which treated the symptom:
     what was on screen was internal MACHINERY rendered into a client surface,
     and rounds 3 and 4 removed that at the source.

     Owner instruction 2026-08-19: "the default view for all clients is the
     internal view." So it is "internal" again, on a surface that no longer
     leaks the machinery, and this case exists to make the value deliberate
     rather than drifted — the redaction posture it used to stand in for is
     asserted on the API, where it belongs and where it never moved. */
  const src = fs.readFileSync(path.join(PROTO, "app-root.jsx"), "utf8");
  const m = src.match(/"audience_default":\s*"([a-z]+)"/);
  assert.ok(m, "TWEAK_DEFAULTS no longer declares audience_default");
  assert.strictEqual(m[1], "internal",
    "the app lands on the internal body by owner instruction (2026-08-19). "
    + "Changing this changes what every reader sees on first paint, so it is "
    + "a decision, not a default to be tidied.");

  // and the compiled bundle agrees, because that is what ships
  const built = fs.readFileSync(
    path.join(PROTO, "..", "public", "proto", "js", "app-root.js"), "utf8");
  const b = built.match(/audience_default":\s*"([a-z]+)"/);
  assert.ok(b && b[1] === "internal",
    "the source says internal and the compiled bundle does not — run build:proto");
});
