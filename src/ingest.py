"""Ingest openFDA food enforcement records, or synthesize the same schema.

Official source (no API key):
  https://api.fda.gov/food/enforcement.json
  bulk: https://open.fda.gov/apis/food/enforcement/download/
  last confirmed current in 2026.

Dates arrive as YYYYMMDD strings. Status is unreliable for "Ongoing" on old
recalls. Firm names are not a unique key. distribution_pattern is free text.
Those three facts are the reason this is a data-engineering project.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from . import config


# Canonical firm, then the dirty aliases we expect to see in the wild.
FIRM_ALIASES: list[tuple[str, list[str]]] = [
    ("Acme Frozen Foods Inc", ["Acme Frozen Foods Inc", "ACME FROZEN FOODS, INC.", "Acme Frozen Foods Incorporated", "Acme Frozen Foods"]),
    ("Northwind Dairy LLC", ["Northwind Dairy LLC", "NORTHWIND DAIRY L.L.C.", "Northwind Dairy, LLC", "Northwind Dairy"]),
    ("Pacific Catch Seafood Co", ["Pacific Catch Seafood Co", "PACIFIC CATCH SEAFOOD CO.", "Pacific Catch Seafood Company", "Pacific Catch"]),
    ("Heartland Grain Mills", ["Heartland Grain Mills", "HEARTLAND GRAIN MILLS INC", "Heartland Grain Mills, Inc."]),
    ("Sunrise Produce Packers", ["Sunrise Produce Packers", "SUNRISE PRODUCE PACKERS LLC", "Sunrise Produce"]),
    ("Blue Ridge Smokehouse", ["Blue Ridge Smokehouse", "BLUE RIDGE SMOKEHOUSE INC.", "Blue Ridge Smoke House"]),
    ("Metro Meal Kits Inc", ["Metro Meal Kits Inc", "METRO MEAL KITS, INC", "Metro Meal Kits"]),
    ("Gulf Coast Shellfish", ["Gulf Coast Shellfish", "GULF COAST SHELLFISH CO", "Gulf Coast Shellfish Company"]),
    ("Great Lakes Cheese Co", ["Great Lakes Cheese Co", "GREAT LAKES CHEESE CO.", "Great Lakes Cheese Company"]),
    ("Canyon Spice Traders", ["Canyon Spice Traders", "CANYON SPICE TRADERS LLC", "Canyon Spice"]),
    ("Evergreen Nut Roasters", ["Evergreen Nut Roasters", "EVERGREEN NUT ROASTERS INC", "Evergreen Nut Roasters, Inc."]),
    ("Capitol Bakery Group", ["Capitol Bakery Group", "CAPITOL BAKERY GROUP LLC", "Capitol Bakery"]),
    ("Rio Grande Tortilla", ["Rio Grande Tortilla", "RIO GRANDE TORTILLA CO", "Rio Grande Tortilla Company"]),
    ("Hudson Valley Juice Co", ["Hudson Valley Juice Co", "HUDSON VALLEY JUICE CO.", "Hudson Valley Juice"]),
    ("Prairie Pet Treats", ["Prairie Pet Treats", "PRAIRIE PET TREATS INC", "Prairie Pet Treats, Inc."]),
    ("Bayou Frozen Entrees", ["Bayou Frozen Entrees", "BAYOU FROZEN ENTREES LLC", "Bayou Frozen Entrées"]),
    ("Sierra Ready Meals", ["Sierra Ready Meals", "SIERRA READY MEALS INC.", "Sierra Ready Meals, Inc"]),
    ("Atlantic Smoked Fish", ["Atlantic Smoked Fish", "ATLANTIC SMOKED FISH CORP", "Atlantic Smoked Fish Corp."]),
    ("Midwest Sprout Farms", ["Midwest Sprout Farms", "MIDWEST SPROUT FARMS LLC", "Midwest Sprout"]),
    ("Desert Date Company", ["Desert Date Company", "DESERT DATE CO", "Desert Date Co."]),
]

HAZARDS = [
    ("Listeria monocytogenes", "pathogen", 0.18, "Class I"),
    ("Salmonella", "pathogen", 0.16, "Class I"),
    ("Undeclared milk", "allergen", 0.10, "Class I"),
    ("Undeclared peanut", "allergen", 0.07, "Class I"),
    ("Undeclared egg", "allergen", 0.05, "Class I"),
    ("E. coli O157:H7", "pathogen", 0.06, "Class I"),
    ("Clostridium botulinum", "pathogen", 0.03, "Class I"),
    ("Foreign material - metal", "foreign", 0.08, "Class II"),
    ("Foreign material - plastic", "foreign", 0.06, "Class II"),
    ("Undeclared sulfites", "allergen", 0.04, "Class II"),
    ("Mold", "quality", 0.05, "Class II"),
    ("Mislabeling - net weight", "label", 0.04, "Class III"),
    ("Incorrect expiration date", "label", 0.04, "Class III"),
    ("Undeclared color additive", "label", 0.04, "Class II"),
]

PRODUCTS = [
    "frozen ready-to-eat meal", "ice cream pint", "sliced deli turkey",
    "raw milk cheese", "smoked salmon fillet", "bagged spinach",
    "sprouts", "peanut butter jar", "flour 5-lb bag", "spice blend",
    "pet jerky treats", "fresh salsa", "tortilla chips", "apple juice",
    "frozen shrimp", "protein bar", "infant cereal", "hummus cup",
]

FIRM_STATES = ["CA", "TX", "WI", "NY", "WA", "FL", "IL", "PA", "GA", "OH",
               "OR", "NJ", "MN", "MI", "NC", "MA", "CO", "AZ", "LA", "ME"]


def _openfda_page(skip: int, limit: int, timeout: int = 20) -> list[dict]:
    url = f"{config.OPENFDA_FOOD_ENFORCEMENT}?limit={limit}&skip={skip}"
    req = urllib.request.Request(url, headers={"User-Agent": "recall-pulse-warehouse/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("results", [])


def try_fetch_openfda() -> pd.DataFrame | None:
    """Best-effort live pull. Returns None on any network / schema failure."""
    records: list[dict] = []
    try:
        for i in range(config.OPENFDA_PAGES):
            chunk = _openfda_page(skip=i * config.OPENFDA_LIMIT, limit=config.OPENFDA_LIMIT)
            if not chunk:
                break
            records.extend(chunk)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return None
    if not records:
        return None
    return pd.json_normalize(records)


def _distribution_text(rng: np.random.Generator, states: list[str], nationwide: bool) -> str:
    if nationwide:
        return rng.choice(
            [
                "Nationwide",
                "Nationwide in the US",
                "Distributed nationwide and to Canada",
                "US nationwide via retail and e-commerce",
            ]
        )
    sample = list(rng.choice(config.US_STATES, size=min(len(states), len(states)), replace=False))
    # Use the intended states, not a random redraw — keep the passed-in list
    sample = states
    style = int(rng.integers(0, 4))
    if style == 0:
        return ", ".join(sample)
    if style == 1:
        return "Distributed to the following states: " + ", ".join(sample)
    if style == 2:
        return " & ".join(sample) + " only"
    return "Product was shipped to " + "; ".join(sample) + "."


def generate_synthetic_recalls(n: int | None = None, seed: int | None = None) -> pd.DataFrame:
    """openFDA-shaped food enforcement rows, including dirty firm names."""
    n = n or config.N_SYNTHETIC_RECALLS
    rng = np.random.default_rng(seed if seed is not None else config.RANDOM_SEED)

    hazard_p = np.array([h[2] for h in HAZARDS], dtype=float)
    hazard_p /= hazard_p.sum()

    # A few firms are serial offenders
    firm_w = np.array([3.5 if i < 4 else 1.0 for i in range(len(FIRM_ALIASES))], dtype=float)
    firm_w /= firm_w.sum()

    rows = []
    for i in range(n):
        year = int(rng.integers(config.SYNTHETIC_YEAR_START, config.SYNTHETIC_YEAR_END + 1))
        # Listeria / produce slightly more common in warmer months
        month_w = np.array([0.07, 0.07, 0.08, 0.09, 0.10, 0.11, 0.11, 0.10, 0.08, 0.07, 0.06, 0.06])
        month_w /= month_w.sum()
        month = int(rng.choice(np.arange(1, 13), p=month_w))
        day = int(rng.integers(1, 28))
        init = pd.Timestamp(year=year, month=month, day=day)

        lag_report = int(rng.integers(2, 40))
        lag_class = int(max(0, rng.normal(18, 10)))
        report = init + pd.Timedelta(days=lag_report)
        classified = report + pd.Timedelta(days=lag_class)

        # ~8% garbage / swapped dates, matching real openFDA pain
        init_str = init.strftime("%Y%m%d")
        report_str = report.strftime("%Y%m%d")
        class_str = classified.strftime("%Y%m%d")
        if rng.random() < 0.03:
            init_str = "02121207"  # documented real-world garbage year
        elif rng.random() < 0.05:
            init_str, report_str = report_str, init_str

        firm_idx = int(rng.choice(len(FIRM_ALIASES), p=firm_w))
        canonical, aliases = FIRM_ALIASES[firm_idx]
        dirty_name = str(rng.choice(aliases))
        firm_state = FIRM_STATES[firm_idx]

        hazard, hazard_family, _p, default_class = HAZARDS[int(rng.choice(len(HAZARDS), p=hazard_p))]
        # Serial offenders more likely Class I
        if firm_idx < 4 and rng.random() < 0.25:
            default_class = "Class I"
        classification = default_class
        if rng.random() < 0.02:
            classification = "Not Yet Classified"

        nationwide = bool(rng.random() < 0.22)
        if nationwide:
            dist_states = list(config.US_STATES)
        else:
            k = int(rng.integers(2, 12))
            # regional bias around the firm
            dist_states = list(rng.choice(config.US_STATES, size=k, replace=False))
            if firm_state not in dist_states:
                dist_states[0] = firm_state

        status_draw = rng.random()
        if (pd.Timestamp.today() - classified).days < 180:
            status = "Ongoing" if status_draw < 0.7 else "Completed"
            term = None
        elif status_draw < 0.08:
            # Stale "Ongoing" — a known openFDA footgun
            status = "Ongoing"
            term = (classified + pd.Timedelta(days=int(rng.integers(60, 400)))).strftime("%Y%m%d")
        else:
            status = rng.choice(["Completed", "Terminated"], p=[0.45, 0.55])
            term = (classified + pd.Timedelta(days=int(rng.integers(30, 400)))).strftime("%Y%m%d")

        product = str(rng.choice(PRODUCTS))
        qty = int(rng.choice([200, 500, 1200, 5000, 18000, 75000, 250000],
                             p=[0.12, 0.18, 0.22, 0.2, 0.15, 0.09, 0.04]))

        rows.append(
            {
                "recall_number": f"F-{1000 + i}-{(year % 100):02d}",
                "event_id": f"{40000 + firm_idx * 17 + int(i / 3)}",
                "classification": classification,
                "status": status,
                "recalling_firm": dirty_name,
                "city": "Unknown",
                "state": firm_state,
                "country": "United States",
                "product_description": f"{product}; lot {rng.integers(10000, 99999)}",
                "product_quantity": f"{qty} cases",
                "reason_for_recall": f"Potential contamination with {hazard}" if hazard_family == "pathogen"
                else f"{hazard} — product does not declare allergen" if hazard_family == "allergen"
                else f"{hazard} found in finished product" if hazard_family == "foreign"
                else hazard,
                "distribution_pattern": _distribution_text(rng, dist_states, nationwide),
                "voluntary_mandated": rng.choice(
                    ["Voluntary: Firm Initiated", "FDA Mandated"], p=[0.93, 0.07]
                ),
                "recall_initiation_date": init_str,
                "report_date": report_str,
                "center_classification_date": class_str,
                "termination_date": term,
                "code_info": f"Lot {rng.integers(1000, 9999)}",
                "product_type": "Food",
                # hidden helper used only by the synthesizer tests; stripped before bronze
                "_canonical_firm": canonical,
                "_hazard_family": hazard_family,
                "_nationwide": nationwide,
            }
        )

    return pd.DataFrame(rows)


def load_or_fetch(raw_json: Path | None = None) -> tuple[pd.DataFrame, str]:
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)

    if raw_json and Path(raw_json).exists():
        df = pd.read_json(raw_json)
        return df, f"json:{raw_json}"

    existing = sorted(config.RAW_DIR.glob("*.json")) + sorted(config.RAW_DIR.glob("*.csv"))
    for path in existing:
        if path.stat().st_size == 0:
            continue
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path), f"csv:{path}"
        return pd.read_json(path), f"json:{path}"

    live = try_fetch_openfda()
    if live is not None and len(live) >= 50:
        out = config.RAW_DIR / "openfda_food_enforcement_sample.json"
        live.to_json(out, orient="records", indent=2)
        return live, f"openfda:{out}"

    df = generate_synthetic_recalls()
    out = config.RAW_DIR / "synthetic_food_enforcement.json"
    # Persist the public schema only
    public = df.drop(columns=[c for c in df.columns if c.startswith("_")])
    public.to_json(out, orient="records", indent=2)
    return df, f"synthetic:{out}"
