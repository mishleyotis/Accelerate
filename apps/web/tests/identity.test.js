/* The acting-as clamp. "Acting as" is a preview, so it must only ever NARROW:
   an ADMIN previewing the AE view should get the server's AE answer (the same
   403 on D5 a real AE gets), and an AE that asks for ADMIN must still be
   answered as an AE. Enforcing that here — not by declining to render a control
   — is what makes it hold when the DOM is edited. */
const test = require("node:test");
const assert = require("node:assert");
const { effectiveRole, mayActAs } = require("../lib/identity.js");

test("an AE cannot act as anything, whatever it asks for", () => {
  for (const asked of ["ADMIN", "ANALYST", "admin", "AE", null, undefined, ""]) {
    assert.equal(effectiveRole("AE", asked), "AE");
  }
  assert.equal(mayActAs("AE"), false);
});

test("an admin previewing a narrower view gets that view", () => {
  assert.equal(effectiveRole("ADMIN", "AE"), "AE");
  assert.equal(effectiveRole("ADMIN", "ANALYST"), "ANALYST");
  assert.equal(effectiveRole("ANALYST", "AE"), "AE");
});

test("a request can never widen", () => {
  assert.equal(effectiveRole("ANALYST", "ADMIN"), "ANALYST");
});

test("an unknown or absent request falls back to the granted role", () => {
  for (const asked of [null, undefined, "", "SUPERUSER", "ae ", 7, {}]) {
    assert.equal(effectiveRole("ANALYST", asked), "ANALYST");
  }
});

test("case is normalised on both sides", () => {
  assert.equal(effectiveRole("admin", "ae"), "AE");
  assert.equal(mayActAs("analyst"), true);
});

test("a missing granted role defaults to the least privilege", () => {
  assert.equal(effectiveRole(null, "ADMIN"), "AE");
  assert.equal(effectiveRole(undefined, "ANALYST"), "AE");
});
