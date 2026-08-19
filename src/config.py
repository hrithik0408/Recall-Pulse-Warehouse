"""Paths and constants for the Recall Pulse Warehouse."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
WAREHOUSE_PATH = DATA_DIR / "recall_pulse.sqlite"
FIGURE_DIR = ROOT / "outputs" / "figures"
REPORT_DIR = ROOT / "outputs" / "reports"

OPENFDA_FOOD_ENFORCEMENT = "https://api.fda.gov/food/enforcement.json"
# Unauthenticated openFDA: 240 req/min, 1,000 req/day. We only need a page or two.
OPENFDA_LIMIT = 100
OPENFDA_PAGES = 5  # 500 records if the API is reachable

RANDOM_SEED = 7
N_SYNTHETIC_RECALLS = 4_800
SYNTHETIC_YEAR_START = 2018
SYNTHETIC_YEAR_END = 2025

US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR",
]

# 2023 Census vintage-style populations (thousands) — enough for per-capita rates.
STATE_POP_K = {
    "CA": 38900, "TX": 30500, "FL": 22600, "NY": 19500, "PA": 12900,
    "IL": 12500, "OH": 11700, "GA": 11000, "NC": 10800, "MI": 10000,
    "NJ": 9300, "VA": 8700, "WA": 7800, "AZ": 7400, "TN": 7100,
    "MA": 7000, "IN": 6800, "MO": 6200, "MD": 6200, "WI": 5900,
    "CO": 5900, "MN": 5700, "SC": 5300, "AL": 5100, "LA": 4600,
    "KY": 4500, "OR": 4200, "OK": 4000, "CT": 3600, "UT": 3400,
    "IA": 3200, "NV": 3200, "AR": 3000, "MS": 2900, "KS": 2900,
    "NM": 2100, "NE": 2000, "ID": 1900, "WV": 1800, "HI": 1400,
    "NH": 1400, "ME": 1400, "MT": 1100, "RI": 1100, "DE": 1000,
    "SD": 900, "ND": 780, "AK": 730, "DC": 680, "VT": 650,
    "WY": 580, "PR": 3200,
}
