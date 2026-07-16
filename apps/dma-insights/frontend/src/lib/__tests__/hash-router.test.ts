/**
 * Hash router round-trip tests — gate G03.HASH.ROUTER.
 */
import { describe, expect, it } from "vitest";
import { buildHash, parseHash } from "../hash-router";

describe("parseHash", () => {
  it("returns root for empty hash", () => {
    expect(parseHash("")).toEqual({ path: "/", query: {}, hash: "/" });
  });

  it("strips the leading #", () => {
    const r = parseHash("#/clients");
    expect(r.path).toBe("/clients");
    expect(r.query).toEqual({});
  });

  it("parses a query string", () => {
    const r = parseHash("#/clients/fce-001/overview?card=IC-003&drawer=evidence");
    expect(r.path).toBe("/clients/fce-001/overview");
    expect(r.query).toEqual({ card: "IC-003", drawer: "evidence" });
  });

  it("handles a bare query (no path)", () => {
    const r = parseHash("#/?owner=me");
    expect(r.path).toBe("/");
    expect(r.query).toEqual({ owner: "me" });
  });
});

describe("buildHash", () => {
  it("returns just the path when no query", () => {
    expect(buildHash("/clients")).toBe("/clients");
  });

  it("appends a query string", () => {
    expect(buildHash("/clients/fce-001/heatmap", { hm: "value_chain", peer: "true" }))
      .toBe("/clients/fce-001/heatmap?hm=value_chain&peer=true");
  });

  it("drops undefined / empty values", () => {
    expect(buildHash("/x", { a: "1", b: undefined, c: "" })).toBe("/x?a=1");
  });
});

describe("round-trip", () => {
  it("parse → build is stable for typical routes", () => {
    const routes = [
      "/",
      "/clients",
      "/clients/fce-001/overview",
      "/clients/fce-001/heatmap?hm=value_chain",
      "/clients/fce-001/insights?card=IC-003&drawer=evidence",
      "/alerts?status=open",
    ];
    for (const r of routes) {
      const parsed = parseHash("#" + r);
      expect(buildHash(parsed.path, parsed.query)).toBe(r);
    }
  });
});
