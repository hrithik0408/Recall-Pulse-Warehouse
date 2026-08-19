"""Bronze → silver → gold → quality gates → figures → briefing memo."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config
from .clean import to_silver
from .ingest import load_or_fetch
from .quality import as_frame, evaluate
from .visualize import (
    plot_classify_lag,
    plot_firm_flags,
    plot_hazard_calendar,
    plot_quality,
    plot_state_burden,
)
from .warehouse import RecallWarehouse


@dataclass
class PipelineResult:
    source: str
    silver_recalls: int
    figure_paths: list[Path] = field(default_factory=list)
    report_path: Path | None = None
    headline: dict = field(default_factory=dict)
    quality_passed: bool = True


class RecallPulsePipeline:
    def __init__(self, raw_json: Path | None = None, warehouse_path: Path | None = None) -> None:
        self.raw_json = raw_json
        self.warehouse = RecallWarehouse(warehouse_path)

    def run(self) -> PipelineResult:
        raw, source = load_or_fetch(self.raw_json)
        silver = to_silver(raw)
        stats = self.warehouse.rebuild(raw, silver)

        firms = self.warehouse.latest_firm_flags()
        state_year = self.warehouse.state_year()
        hazard = self.warehouse.hazard_month()
        snap = self.warehouse.quality_snapshot()
        checks = evaluate(snap, stats["silver_recalls"])
        quality = as_frame(checks)

        config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
        firms.to_csv(config.REPORT_DIR / "firm_watchlist.csv", index=False)
        state_year.to_csv(config.REPORT_DIR / "state_year.csv", index=False)
        hazard.to_csv(config.REPORT_DIR / "hazard_month.csv", index=False)
        quality.to_csv(config.REPORT_DIR / "quality_gates.csv", index=False)
        self.warehouse.firm_scorecard().to_csv(config.REPORT_DIR / "firm_scorecard_full.csv", index=False)

        figures = [
            plot_firm_flags(firms),
            plot_state_burden(state_year),
            plot_hazard_calendar(hazard),
            plot_classify_lag(hazard),
            plot_quality(quality),
        ]
        headline = self._headline(firms, state_year, snap, stats)
        report = self._write_memo(source, stats, headline, firms, quality)
        return PipelineResult(
            source=source,
            silver_recalls=stats["silver_recalls"],
            figure_paths=figures,
            report_path=report,
            headline=headline,
            quality_passed=bool(quality["passed"].all()),
        )

    @staticmethod
    def _headline(firms: pd.DataFrame, state_year: pd.DataFrame,
                  snap: pd.DataFrame, stats: dict) -> dict:
        row = snap.iloc[0]
        top = firms.iloc[0] if len(firms) else None
        latest = int(state_year["initiated_year"].max())
        worst_state = (
            state_year[state_year["initiated_year"] == latest]
            .sort_values("class_i_per_million", ascending=False)
            .iloc[0]
        )
        return {
            "silver_recalls": int(stats["silver_recalls"]),
            "distinct_firms": int(row["distinct_firms"]),
            "class_i": int(row["class_i"]),
            "stale_ongoing": int(row["stale_ongoing"]),
            "avg_name_variants": round(float(row["avg_name_variants"]), 2),
            "top_firm": None if top is None else str(top["example_name"]),
            "top_firm_flag": None if top is None else str(top["firm_flag"]),
            "top_firm_3yr": None if top is None else int(top["recalls_rolling_3yr"]),
            "worst_state": str(worst_state["state"]),
            "worst_state_year": latest,
            "worst_state_class_i_per_m": float(worst_state["class_i_per_million"]),
        }

    def _write_memo(self, source: str, stats: dict, headline: dict,
                    firms: pd.DataFrame, quality: pd.DataFrame) -> Path:
        path = config.REPORT_DIR / "briefing_memo.md"
        lines = [
            "# Recall Pulse Warehouse — briefing memo",
            "",
            f"- Source: `{source}`",
            f"- Silver recalls: **{stats['silver_recalls']:,}** across "
            f"**{headline['distinct_firms']}** collapsed firms",
            f"- Class I: **{headline['class_i']:,}**  |  stale Ongoing flags: **{headline['stale_ongoing']:,}**",
            f"- Average name variants per firm key: **{headline['avg_name_variants']}**",
            "",
            "## The one-slide finding",
            "",
            (
                f"**{headline['top_firm']}** is the current watchlist head "
                f"(`{headline['top_firm_flag']}`, {headline['top_firm_3yr']} recalls in a 3-year window). "
                f"On a per-capita Class I basis, **{headline['worst_state']}** led in "
                f"{headline['worst_state_year']} at {headline['worst_state_class_i_per_m']:.2f} exposures per million."
            ),
            "",
            "Nationwide text was exploded to every state. Recompute the map with "
            "`listed_exposures` only before you take that ranking to a press briefing.",
            "",
            "## Quality gates",
            "",
            "| Check | Value | Threshold | Result |",
            "|---|---:|---:|---|",
        ]
        for _, r in quality.iterrows():
            mark = "PASS" if r["passed"] else "FAIL"
            lines.append(f"| {r['name']} | {r['value']:.2f} | {r['comparator']} {r['threshold']} | {mark} |")
        lines += [
            "",
            "## Watchlist (latest year per firm)",
            "",
            "| Firm | Flag | 3yr recalls | Class I % | Name variants |",
            "|---|---|---:|---:|---:|",
        ]
        for _, r in firms.head(8).iterrows():
            lines.append(
                f"| {r['example_name']} | {r['firm_flag']} | {int(r['recalls_rolling_3yr'])} "
                f"| {r['class_i_pct']:.0f}% | {int(r['n_name_variants'])} |"
            )
        lines += [
            "",
            "## How to read this (and how not to)",
            "",
            "- `status = Ongoing` is not a live SLA. Cross it with `termination_date`.",
            "- Firm names are not keys. The watchlist is only as good as `normalize_firm_name`.",
            "- Per-capita state ranks include nationwide explosions unless you filter them out.",
            "- This warehouse answers 'who, what, where, how fast.' It does not estimate illnesses.",
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
