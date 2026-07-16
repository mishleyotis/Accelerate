/**
 * Rec drilldown ID contract (2026-07-06 fix).
 *
 * Live bug: opening a recommendation from the platform page failed to
 * load. The stairstep curve and roadmap chevrons only hold the
 * human-readable REC-NN display code; the detail endpoint was
 * UUID-only, so the fetch 500'd and the modal showed "Couldn't load
 * recommendation".
 *
 * Contract pinned here:
 *   1. recommendationDetailPath — a UUID goes to the bare detail path;
 *      a REC-NN code carries the ?display_id= scope the backend needs
 *      to resolve it within the entity's ACTIVE run.
 *   2. DrawerHost.asRecPayload — the displayId the openers put on the
 *      drawer payload must survive the host → modal hand-off (it was
 *      previously dropped, so even a scoped opener lost its scope).
 */
import { describe, expect, it } from "vitest";

import { asRecPayload } from "../DrawerHost";
import { recommendationDetailPath } from "@/lib/recommendations";

const UUID = "6f9619ff-8b86-d011-b42d-00c04fc964ff";

describe("recommendationDetailPath", () => {
  it("uses the bare path for a UUID pk (scope irrelevant)", () => {
    expect(recommendationDetailPath(UUID, "alma-bank")).toBe(
      `/api/v1/recommendations/${UUID}`,
    );
  });

  it("scopes a REC-NN display code with ?display_id=", () => {
    expect(recommendationDetailPath("REC-08", "alma-bank")).toBe(
      "/api/v1/recommendations/REC-08?display_id=alma-bank",
    );
  });

  it("leaves an unscoped code bare (backend resolves when unambiguous)", () => {
    expect(recommendationDetailPath("REC-08", null)).toBe(
      "/api/v1/recommendations/REC-08",
    );
  });

  it("URI-encodes both segments", () => {
    expect(recommendationDetailPath("REC 08", "a/b")).toBe(
      "/api/v1/recommendations/REC%2008?display_id=a%2Fb",
    );
  });
});

describe("DrawerHost.asRecPayload (displayId spine)", () => {
  it("carries recommendationId AND displayId through the hand-off", () => {
    expect(
      asRecPayload({ recommendationId: "REC-08", displayId: "alma-bank" }),
    ).toEqual({ recommendationId: "REC-08", displayId: "alma-bank" });
  });

  it("defaults both to null on junk payloads", () => {
    expect(asRecPayload(undefined)).toEqual({
      recommendationId: null,
      displayId: null,
    });
    expect(asRecPayload({ recommendationId: 42 })).toEqual({
      recommendationId: null,
      displayId: null,
    });
  });
});
