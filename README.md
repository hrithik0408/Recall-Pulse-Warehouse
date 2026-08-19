# Recall Pulse Warehouse

**Level 1 — Foundations.** A food-recall data warehouse that treats openFDA enforcement reports as a dirty operational system, not a tidy CSV.

The public-health question is simple: **which firms keep showing up, which hazards are moving, and which states are exposed — after you fix the names, the dates, and the free-text distribution field?**

## Why this is not another tutorial project

"Netflix EDA" and "clean a CSV" do not survive a 2026 AI-engineer screen. This project does, because the hard parts are the ones production teams actually fight:

- `recalling_firm` is not a unique key (`ACME FROZEN FOODS, INC.` vs `Acme Frozen Foods Inc`)
- dates are `YYYYMMDD` strings, and some of them are garbage years
- `status = Ongoing` can sit on a record that already has a `termination_date` (documented openFDA behavior into 2026)
- `distribution_pattern` is prose ("Distributed to the following states: NY, NJ and CT" vs "Nationwide")

Those become a bronze / silver / gold SQLite warehouse, a firm watchlist with window functions, and a per-capita state mart.

## Quick start

```bash
python -m pip install -r requirements.txt
python run.py
```

The runner tries the live openFDA endpoint first (`https://api.fda.gov/food/enforcement.json`, no key). If the sandbox cannot reach it, it falls back to a synthesizer that preserves the official field names and the messy aliases.

To force official data later:

```bash
curl "https://api.fda.gov/food/enforcement.json?limit=100" -o data/raw/openfda.json
python run.py --json data/raw/openfda.json
```

Full bulk files: [openFDA food enforcement download](https://open.fda.gov/apis/food/enforcement/download/) (zipped JSON, updated through 2026).

## Architecture

```
openFDA JSON  or  synthesizer
        │
        ▼
 bronze_enforcement   (raw payload_json, untouched)
        │
        ▼
 silver_recall  +  silver_firm  +  silver_exposure
   dates gated     name key         state explode
        │
        ▼
 gold_firm_scorecard   gold_state_year   gold_hazard_month
   LAG + rolling 3yr    ⋈ census pop      cumulative Class I
        │
        ▼
 quality gates → figures → briefing memo
```

## Layout

```
run.py
src/ingest.py       # live API + official-schema generator
src/clean.py        # firm key, date gate, state parser
src/warehouse.py    # medallion SQLite
src/quality.py      # pass/fail gates
src/visualize.py
src/pipeline.py
sql/gold_marts.sql
```
