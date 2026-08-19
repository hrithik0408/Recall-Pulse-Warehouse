"""Warehouse outputs → figures a compliance lead would actually open."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from . import config

sns.set_theme(style="whitegrid", context="talk")


def _save(fig: plt.Figure, name: str) -> Path:
    config.FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.FIGURE_DIR / name
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_firm_flags(latest: pd.DataFrame, top_n: int = 12) -> Path:
    df = latest.head(top_n).iloc[::-1]
    palette = {
        "chronic_high_severity": "#B2182B",
        "chronic": "#EF8A62",
        "acute_severe": "#FDDBC7",
        "watch": "#67A9CF",
    }
    colors = [palette.get(f, "#999999") for f in df["firm_flag"]]
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.barh(df["example_name"], df["recalls_rolling_3yr"], color=colors)
    ax.set_xlabel("Recalls in rolling 3-year window")
    ax.set_title("Firm watchlist — aliases already collapsed")
    return _save(fig, "01_firm_watchlist.png")


def plot_state_burden(state_year: pd.DataFrame) -> Path:
    latest_year = int(state_year["initiated_year"].max())
    df = state_year[state_year["initiated_year"] == latest_year].nlargest(15, "class_i_per_million")
    fig, ax = plt.subplots(figsize=(11, 6))
    sns.barplot(data=df, x="state", y="class_i_per_million", color="#B2182B", ax=ax)
    ax.set_ylabel("Class I exposures per million people")
    ax.set_xlabel("")
    ax.set_title(f"Class I geographic burden ({latest_year}) — nationwide recalls included")
    return _save(fig, "02_state_class_i_burden.png")


def plot_hazard_calendar(hazard_month: pd.DataFrame) -> Path:
    df = hazard_month.copy()
    keep = df.groupby("hazard_tag")["recalls"].sum().nlargest(6).index
    df = df[df["hazard_tag"].isin(keep)]
    df["period"] = pd.to_datetime(
        dict(year=df["initiated_year"], month=df["initiated_month"], day=1)
    )
    fig, ax = plt.subplots(figsize=(12, 6))
    sns.lineplot(data=df, x="period", y="recalls", hue="hazard_tag", ax=ax)
    ax.set_xlabel("")
    ax.set_ylabel("Recalls initiated")
    ax.set_title("Hazard mix over time (top 6 tags)")
    ax.legend(title="", fontsize=9)
    return _save(fig, "03_hazard_calendar.png")


def plot_classify_lag(hazard_month: pd.DataFrame) -> Path:
    df = (
        hazard_month.groupby("hazard_tag", as_index=False)["avg_days_to_classify"]
        .mean()
        .sort_values("avg_days_to_classify", ascending=False)
        .head(10)
    )
    fig, ax = plt.subplots(figsize=(11, 6))
    sns.barplot(data=df, y="hazard_tag", x="avg_days_to_classify", color="#2166AC", ax=ax)
    ax.set_xlabel("Average days from report to classification")
    ax.set_ylabel("")
    ax.set_title("Classification lag is a process metric, not a pathogen metric")
    return _save(fig, "04_classify_lag.png")


def plot_quality(quality: pd.DataFrame) -> Path:
    df = quality.copy()
    df["label"] = df.apply(lambda r: "PASS" if r["passed"] else "FAIL", axis=1)
    fig, ax = plt.subplots(figsize=(11, 5))
    colors = ["#1A9850" if p else "#D73027" for p in df["passed"]]
    ax.barh(df["name"], df["value"], color=colors)
    ax.set_xlabel("Observed value")
    ax.set_title("Warehouse quality gates")
    for i, row in df.reset_index(drop=True).iterrows():
        ax.text(row["value"], i, f"  {row['label']} (≤/≥ {row['threshold']})", va="center", fontsize=9)
    return _save(fig, "05_quality_gates.png")
