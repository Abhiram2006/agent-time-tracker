# Food library (example)

Reusable macros for recurring meals, so the agent logs a repeat as a one-liner instead
of re-estimating. Copy this to `foods.md` and grow it with the user's actual foods.
Corrections overwrite the entry (optionally bump a version note).

| Food | kcal | P (g) | notes |
|---|---:|---:|---|
| Chicken rice bowl | ~700 | ~45 | ~150g chicken + rice + veg |
| Oatmeal + 2 eggs | ~450 | ~25 | standard breakfast |
| Protein shake (1 scoop) | ~120 | ~30 | |
| Salmon + potatoes | ~650 | ~40 | dinner portion |
| Chicken burrito | ~900 | ~45 | big, with rice/beans/cheese |

**Conventions**
- Estimate with `~` / round numbers — no fake precision.
- Flag the biggest uncertainty (oil, portion size, "big plate" guesses).
- The calendar meal event carries the macro tag `[700kcal 45P]`; this library is the
  lookup, the day log's Diet section is the human-readable record.
