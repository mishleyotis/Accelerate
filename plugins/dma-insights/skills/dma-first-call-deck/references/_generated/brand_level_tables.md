<!-- DO NOT EDIT DIRECTLY.

     This file is regenerated from `references/01_brand/color_level_system.py`
     via `scripts/utils/generate_color_docs.py`. Any changes made here will be
     overwritten on the next regeneration.

     To change a color, palette, score range, or role: edit the config Python
     file, then re-run the generator and commit both. `check_docs_in_sync.py`
     will fail CI if they drift.
-->

# Brand Level Tables

_Score-to-level and level-to-palette mappings used across the deck._

These mappings are exposed by the config as `score_to_level_4tier` and
`score_to_level_5tier`; editors call them directly, and QA derives every
expected hex via the same functions.

## 4-Tier Level Function: `score_to_level_4tier(score: float) -> str`

Used by Slides 10 and 14.

Strict less-than on the raw score: the app's resolver (`apps/web/lib/bands.js`,
`engine.contract.band_of`). There is no fifth band.

```python
if score < 2.00:  return 'Activating'
if score < 3.00:  return 'Building'
if score < 4.00:  return 'Competing'
return 'Differentiating'
```

| Score Range | Level | Notes |
|---|---|---|
| [0.00, 2.00) | **Activating** | — |
| [2.00, 3.00) | **Building** | — |
| [3.00, 4.00) | **Competing** | — |
| [4.00, 5.00] | **Differentiating** | — |

## 5-Tier Level Function: `score_to_level_5tier(score: float) -> int`

Used by Slide 13 pillar indicators.

The maturity SCORE scale (`skills/dma-research/engine/rubric.py` `maturity_level`), not the display bands.

```python
if score < 1.50:  return 1  # Foundational
if score < 2.50:  return 2  # Developing
if score < 3.50:  return 3  # Established
if score < 4.50:  return 4  # Advanced
return 5                    # Leading
```

| Score Range | # | Label |
|---|---|---|
| [0.00, 1.50) | 1 | **Foundational** |
| [1.50, 2.50) | 2 | **Developing** |
| [2.50, 3.50) | 3 | **Established** |
| [3.50, 4.50) | 4 | **Advanced** |
| [4.50, 5.00] | 5 | **Leading** |

## Maturity Level ↔ Display Band Loose Mapping

Used by `cross_slide_checker.verify_cross_slide` to check Slide 13's
maturity-level indicator is consistent with Slide 10's band strips for the
same pillar. Input scores should be identical; if they differ by more
than 0.1, it's a warning (likely data pipeline inconsistency).

| Maturity level | Score range | Band(s) it can render as |
|---|---|---|
| 1 Foundational | [0.00, 1.50) | Activating |
| 2 Developing | [1.50, 2.50) | Activating / Building |
| 3 Established | [2.50, 3.50) | Building / Competing |
| 4 Advanced | [3.50, 4.50) | Competing / Differentiating |
| 5 Leading | [4.50, 5.00] | Differentiating |

