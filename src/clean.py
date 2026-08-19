"""Silver-layer transforms: dates, firm keys, hazard tags, state exposure."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from . import config

_LEGAL = re.compile(
    r"\b(incorporated|inc\.?|l\.?l\.?c\.?|l\.?p\.?|corp\.?|corporation|co\.?|company|ltd\.?)\b",
    flags=re.I,
)
_PUNCT = re.compile(r"[^a-z0-9\s]")
_WS = re.compile(r"\s+")

# Reason-for-recall is free text. These patterns are conservative on purpose.
HAZARD_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("listeria", re.compile(r"listeria", re.I)),
    ("salmonella", re.compile(r"salmonella", re.I)),
    ("ecoli", re.compile(r"e\.?\s*coli|o157", re.I)),
    ("botulinum", re.compile(r"botulin", re.I)),
    ("allergen_milk", re.compile(r"undeclared milk|milk allergen", re.I)),
    ("allergen_peanut", re.compile(r"undeclared peanut|peanut allergen", re.I)),
    ("allergen_egg", re.compile(r"undeclared egg", re.I)),
    ("allergen_other", re.compile(r"undeclared (soy|wheat|tree nut|sulfite|allergen)", re.I)),
    ("foreign_metal", re.compile(r"metal", re.I)),
    ("foreign_plastic", re.compile(r"plastic", re.I)),
    ("mold", re.compile(r"\bmold\b|mould", re.I)),
    ("label", re.compile(r"mislabel|net weight|expiration|color additive", re.I)),
]

NATIONWIDE_RE = re.compile(r"nation[- ]?wide|throughout the (united states|us)\b", re.I)
STATE_TOKEN_RE = re.compile(r"\b(" + "|".join(config.US_STATES) + r")\b")


def normalize_firm_name(name: str | float) -> str:
    """Collapse legal suffixes, punctuation, and case so aliases share a key."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return "UNKNOWN"
    text = str(name).strip().lower()
    text = text.replace("&", " and ")
    text = _LEGAL.sub(" ", text)
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    return text or "UNKNOWN"


def parse_fda_date(value) -> pd.Timestamp | pd.NaT:
    """openFDA dates are YYYYMMDD. Real files contain years like 0212 and 1930."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.NaT
    digits = re.sub(r"\D", "", str(value))
    if len(digits) != 8:
        return pd.NaT
    year = int(digits[:4])
    if year < 1990 or year > 2030:
        return pd.NaT
    try:
        return pd.Timestamp(year=year, month=int(digits[4:6]), day=int(digits[6:8]))
    except ValueError:
        return pd.NaT


def tag_hazard(reason: str | float) -> str:
    if reason is None or (isinstance(reason, float) and pd.isna(reason)):
        return "unspecified"
    text = str(reason)
    for label, pattern in HAZARD_PATTERNS:
        if pattern.search(text):
            return label
    return "other"


def extract_states(distribution_pattern: str | float) -> list[str]:
    """Turn free-text distribution into a list of state codes.

    Nationwide (and near-synonyms) explode to all states. That is a modeling
    choice: it over-states exposure for a single Costco-only SKU, but it is
    honest about what the text actually claims. The gold mart keeps a
    `is_nationwide` flag so per-capita maps can be recomputed without the explode.
    """
    if distribution_pattern is None or (isinstance(distribution_pattern, float) and pd.isna(distribution_pattern)):
        return []
    text = str(distribution_pattern)
    if NATIONWIDE_RE.search(text):
        return list(config.US_STATES)
    found = STATE_TOKEN_RE.findall(text.upper())
    # Preserve order, drop dupes
    seen: list[str] = []
    for st in found:
        if st not in seen:
            seen.append(st)
    return seen


@dataclass
class SilverTables:
    recalls: pd.DataFrame
    exposure: pd.DataFrame
    firms: pd.DataFrame


def to_silver(raw: pd.DataFrame) -> SilverTables:
    df = raw.copy()
    # openFDA sometimes nests; flatten any leftover dotted names
    df.columns = [c.split(".")[-1] for c in df.columns]

    rename = {
        "recall_number": "recall_number",
        "event_id": "event_id",
        "classification": "classification",
        "status": "status",
        "recalling_firm": "recalling_firm_raw",
        "state": "firm_state",
        "country": "country",
        "city": "city",
        "product_description": "product_description",
        "product_quantity": "product_quantity",
        "reason_for_recall": "reason_for_recall",
        "distribution_pattern": "distribution_pattern",
        "voluntary_mandated": "voluntary_mandated",
        "recall_initiation_date": "recall_initiation_date",
        "report_date": "report_date",
        "center_classification_date": "center_classification_date",
        "termination_date": "termination_date",
    }
    present = {k: v for k, v in rename.items() if k in df.columns}
    df = df.rename(columns=present)
    if "recalling_firm_raw" not in df.columns and "recalling_firm" in df.columns:
        df["recalling_firm_raw"] = df["recalling_firm"]

    for col in rename.values():
        if col not in df.columns:
            df[col] = pd.NA

    df["firm_key"] = df["recalling_firm_raw"].map(normalize_firm_name)
    df["initiated_on"] = df["recall_initiation_date"].map(parse_fda_date)
    df["reported_on"] = df["report_date"].map(parse_fda_date)
    df["classified_on"] = df["center_classification_date"].map(parse_fda_date)
    df["terminated_on"] = df["termination_date"].map(parse_fda_date)

    # Swap inverted dates rather than dropping the row
    inverted = df["initiated_on"].notna() & df["reported_on"].notna() & (df["initiated_on"] > df["reported_on"])
    df.loc[inverted, ["initiated_on", "reported_on"]] = df.loc[inverted, ["reported_on", "initiated_on"]].to_numpy()

    df["days_to_report"] = (df["reported_on"] - df["initiated_on"]).dt.days
    df["days_to_classify"] = (df["classified_on"] - df["reported_on"]).dt.days
    df["hazard_tag"] = df["reason_for_recall"].map(tag_hazard)
    df["class_rank"] = df["classification"].map({"Class I": 1, "Class II": 2, "Class III": 3}).astype("Int64")
    df["is_class_i"] = df["classification"].eq("Class I").astype(int)
    df["is_nationwide"] = df["distribution_pattern"].fillna("").map(lambda s: int(bool(NATIONWIDE_RE.search(str(s)))))
    df["is_stale_ongoing"] = (
        df["status"].eq("Ongoing") & df["terminated_on"].notna()
    ).astype(int)
    df["initiated_year"] = df["initiated_on"].dt.year.astype("Int64")
    df["initiated_month"] = df["initiated_on"].dt.month.astype("Int64")

    # Quantity is free text ("1200 cases"). Pull the first integer.
    df["qty_cases"] = (
        df["product_quantity"].astype(str).str.extract(r"(\d[\d,]*)", expand=False)
        .str.replace(",", "", regex=False)
        .astype(float)
    )

    recalls = df.drop_duplicates(subset=["recall_number"]).copy()

    # Bridge table: one row per (recall, exposed state)
    exploded = []
    for rec, pat, nation in zip(recalls["recall_number"], recalls["distribution_pattern"], recalls["is_nationwide"]):
        states = extract_states(pat)
        if not states:
            exploded.append({"recall_number": rec, "state": None, "exposure_basis": "unparsed"})
            continue
        basis = "nationwide" if nation else "listed"
        for st in states:
            exploded.append({"recall_number": rec, "state": st, "exposure_basis": basis})
    exposure = pd.DataFrame(exploded)

    firms = (
        recalls.groupby("firm_key", as_index=False)
        .agg(
            example_name=("recalling_firm_raw", "first"),
            n_name_variants=("recalling_firm_raw", "nunique"),
            firm_state=("firm_state", lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else pd.NA),
        )
    )
    return SilverTables(recalls=recalls, exposure=exposure, firms=firms)
