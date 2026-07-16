# ADR 0009 — User-facing naming for catalogue layers

**Status**: Accepted (2026-05-20)

## Context

The Capability Catalogue v7 ships with internal terminology that's
useful for the data layer but jargon-heavy for AEs and customers:

| Catalogue layer | DB / schema name | Internal use |
|---|---|---|
| Sub-capability | `ccg_subcaps`, `subcap_id` | "Subcap" |
| Capability | `ccg_l1_capabilities`, `l1_id` | "L1 Capability" |
| Platform area | `ccg_l3_platforms`, `l3_id` | "L3 Platform" |
| Feature | `ccg_l4_features` | "L4 Feature" |

The User Brief is explicit: the AE-facing UI must not show "L1", "L3",
"L4" jargon. AEs talk about *capabilities*, *platform areas*, and
*features*. Operators do likewise.

## Decision

1. **DB / schema names stay as-is** (`ccg_l1_capabilities`,
   `ccg_l3_platforms`, `ccg_l4_features`, `l1_id`, `l3_id`). They are
   the canonical join keys and renaming them would force a
   migration-heavy ripple. Backend code may reference these names
   directly.

2. **Pydantic schemas + frontend types use the user-facing names**:
   - `l1_id` → `capability_id` + `capability_name`
   - `l3_id` → `platform_area_id` + `platform_area_name`
   - `l4_features` → `features` (when surfaced as a user-facing list)
   - Sub-capabilities keep "sub-cap" / "sub-capability" (still used in
     the brief).

3. **value_chain.py + similar services** expose only the user-facing
   names in their dataclasses (e.g. `SubcapForCluster.capability_id`,
   not `l1_id`) so the UI never has to translate.

4. **UI labels** never say "L1", "L3", "L4". They say "Capability",
   "Platform area", "Feature". The HeatmapPage capability-zoom heading
   says "Capability"; the platform-area cluster heading says
   "Platform area".

5. **Audit**: a grep at PR review must turn up zero occurrences of the
   strings `"L1"`, `"L3"`, `"L4"` in the **frontend** under
   `src/` (excluding the read-only `_prototype/` reference dir). The
   backend is allowed to use the DB-level names internally.

## Consequences

- Maintains schema stability while shielding AEs from jargon.
- All future surfaces (FeatureExplorer, PlatformAreaDrill, etc.) use
  the canonical names from day 1.
- `value_chain.cluster_by_capability` + `cluster_by_platform_area`
  embody the naming contract; their tests lock it in.

## Tests

`backend/tests/test_value_chain.py` exercises the clustering with the
user-facing names. Future tests for routers that surface these
clusters should assert the response JSON uses `capability_*` /
`platform_area_*` keys (not `l1_*` / `l3_*`).
