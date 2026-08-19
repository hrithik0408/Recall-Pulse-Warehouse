# Recall Pulse Warehouse — briefing memo

- Source: `json:D:\recall-pulse-warehouse\data\raw\openfda_food_enforcement_sample.json`
- Silver recalls: **500** across **376** collapsed firms
- Class I: **231**  |  stale Ongoing flags: **0**
- Average name variants per firm key: **1.02**

## The one-slide finding

**Garden-Fresh Foods, Inc.** is the current watchlist head (`acute_severe`, 10 recalls in a 3-year window). On a per-capita Class I basis, **WY** led in 2026 at 3.45 exposures per million.

Nationwide text was exploded to every state. Recompute the map with `listed_exposures` only before you take that ranking to a press briefing.

## Quality gates

| Check | Value | Threshold | Result |
|---|---:|---:|---|
| pct_missing_init_date | 0.00 | <= 8.0 | PASS |
| pct_stale_ongoing | 0.00 | <= 15.0 | PASS |
| pct_unparsed_exposure | 14.20 | <= 20.0 | PASS |
| avg_name_variants | 1.02 | >= 1.05 | FAIL |
| class_i_share | 46.20 | >= 5.0 | PASS |

## Watchlist (latest year per firm)

| Firm | Flag | 3yr recalls | Class I % | Name variants |
|---|---|---:|---:|---:|
| Garden-Fresh Foods, Inc. | acute_severe | 10 | 100% | 1 |
| Newly Weds Foods Inc | acute_severe | 8 | 100% | 2 |
| Reser's Fine Foods, Inc. | acute_severe | 7 | 100% | 1 |
| FRESH IDEATION FOOD GROUP, LLC dba Fresh Creative Cuisine | acute_severe | 6 | 100% | 1 |
| Blue Bell Creameries, L.P. | acute_severe | 5 | 100% | 1 |
| Sunland, Incorporated | acute_severe | 4 | 100% | 1 |
| CHETAK NEW YORK LLC | acute_severe | 3 | 100% | 1 |
| Dierbergs Markets, Inc Corporate Office | acute_severe | 3 | 100% | 1 |

## How to read this (and how not to)

- `status = Ongoing` is not a live SLA. Cross it with `termination_date`.
- Firm names are not keys. The watchlist is only as good as `normalize_firm_name`.
- Per-capita state ranks include nationwide explosions unless you filter them out.
- This warehouse answers 'who, what, where, how fast.' It does not estimate illnesses.
