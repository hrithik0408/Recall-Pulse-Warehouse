"""Explicit data-quality gates. These are the interview, not the charts."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class QualityCheck:
    name: str
    value: float
    threshold: float
    comparator: str
    passed: bool
    note: str


def evaluate(snapshot: pd.DataFrame, n_recalls: int) -> list[QualityCheck]:
    row = snapshot.iloc[0]
    checks = []

    def add(name, value, threshold, comparator, note):
        if comparator == "<=":
            passed = value <= threshold
        else:
            passed = value >= threshold
        checks.append(QualityCheck(name, float(value), float(threshold), comparator, passed, note))

    add(
        "pct_missing_init_date",
        100 * row["missing_init_date"] / max(n_recalls, 1),
        8.0,
        "<=",
        "Garbage YYYYMMDD values should be rare after the 1990–2030 gate.",
    )
    add(
        "pct_stale_ongoing",
        100 * row["stale_ongoing"] / max(n_recalls, 1),
        15.0,
        "<=",
        "openFDA leaves old recalls marked Ongoing. Flag, do not trust status.",
    )
    add(
        "pct_unparsed_exposure",
        100 * row["unparsed_exposure"] / max(n_recalls, 1),
        20.0,
        "<=",
        "distribution_pattern with no state token and no nationwide phrase.",
    )
    add(
        "avg_name_variants",
        row["avg_name_variants"],
        1.05,
        ">=",
        "If this is ~1.0 on real data, firm matching is probably under-collapsing.",
    )
    add(
        "class_i_share",
        100 * row["class_i"] / max(n_recalls, 1),
        5.0,
        ">=",
        "A pull with almost no Class I is usually a filter bug, not a miracle year.",
    )
    return checks


def as_frame(checks: list[QualityCheck]) -> pd.DataFrame:
    return pd.DataFrame([c.__dict__ for c in checks])
