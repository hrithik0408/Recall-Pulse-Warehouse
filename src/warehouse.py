"""Medallion-lite warehouse: bronze (raw JSON rows) → silver → gold marts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from . import config
from .clean import SilverTables


SCHEMA_SQL = """
DROP TABLE IF EXISTS gold_state_year;
DROP TABLE IF EXISTS gold_firm_scorecard;
DROP TABLE IF EXISTS gold_hazard_month;
DROP TABLE IF EXISTS silver_exposure;
DROP TABLE IF EXISTS silver_firm;
DROP TABLE IF EXISTS silver_recall;
DROP TABLE IF EXISTS dim_state;
DROP TABLE IF EXISTS bronze_enforcement;

CREATE TABLE bronze_enforcement (
    recall_number TEXT,
    payload_json  TEXT NOT NULL
);

CREATE TABLE dim_state (
    state     TEXT PRIMARY KEY,
    pop_k     INTEGER NOT NULL
);

CREATE TABLE silver_recall (
    recall_number      TEXT PRIMARY KEY,
    event_id           TEXT,
    classification     TEXT,
    class_rank         INTEGER,
    is_class_i         INTEGER,
    status             TEXT,
    is_stale_ongoing   INTEGER,
    firm_key           TEXT,
    recalling_firm_raw TEXT,
    firm_state         TEXT,
    hazard_tag         TEXT,
    reason_for_recall  TEXT,
    product_description TEXT,
    qty_cases          REAL,
    is_nationwide      INTEGER,
    initiated_on       TEXT,
    reported_on        TEXT,
    classified_on      TEXT,
    terminated_on      TEXT,
    days_to_report     INTEGER,
    days_to_classify   INTEGER,
    initiated_year     INTEGER,
    initiated_month    INTEGER,
    voluntary_mandated TEXT
);

CREATE TABLE silver_firm (
    firm_key          TEXT PRIMARY KEY,
    example_name      TEXT,
    n_name_variants   INTEGER,
    firm_state        TEXT
);

CREATE TABLE silver_exposure (
    recall_number   TEXT,
    state           TEXT,
    exposure_basis  TEXT
);

CREATE INDEX idx_recall_firm_year ON silver_recall(firm_key, initiated_year);
CREATE INDEX idx_exposure_state ON silver_exposure(state);
"""


class RecallWarehouse:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or config.WAREHOUSE_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.execute("PRAGMA journal_mode=WAL;")
        return con

    def rebuild(self, raw: pd.DataFrame, silver: SilverTables) -> dict:
        state_dim = pd.DataFrame(
            [{"state": st, "pop_k": pop} for st, pop in config.STATE_POP_K.items()]
        )
        public_cols = [c for c in raw.columns if not str(c).startswith("_")]
        bronze_rows = [
            (str(row.get("recall_number", "")), json.dumps(row.to_dict(), default=str))
            for _, row in raw[public_cols].iterrows()
        ]

        rec = silver.recalls.copy()
        for col in ("initiated_on", "reported_on", "classified_on", "terminated_on"):
            rec[col] = pd.to_datetime(rec[col], errors="coerce").dt.strftime("%Y-%m-%d")

        keep = [
            "recall_number", "event_id", "classification", "class_rank", "is_class_i",
            "status", "is_stale_ongoing", "firm_key", "recalling_firm_raw", "firm_state",
            "hazard_tag", "reason_for_recall", "product_description", "qty_cases",
            "is_nationwide", "initiated_on", "reported_on", "classified_on",
            "terminated_on", "days_to_report", "days_to_classify", "initiated_year",
            "initiated_month", "voluntary_mandated",
        ]
        rec = rec[keep]

        with self.connect() as con:
            con.executescript(SCHEMA_SQL)
            con.executemany(
                "INSERT INTO bronze_enforcement(recall_number, payload_json) VALUES (?, ?)",
                bronze_rows,
            )
            state_dim.to_sql("dim_state", con, if_exists="append", index=False)
            rec.to_sql("silver_recall", con, if_exists="append", index=False)
            silver.firms.to_sql("silver_firm", con, if_exists="append", index=False)
            silver.exposure.to_sql("silver_exposure", con, if_exists="append", index=False)
            self._build_gold(con)
            n = con.execute("SELECT COUNT(*) FROM silver_recall").fetchone()[0]
        return {"silver_recalls": int(n), "bronze_rows": len(bronze_rows)}

    @staticmethod
    def _build_gold(con: sqlite3.Connection) -> None:
        con.executescript(
            """
            CREATE TABLE gold_firm_scorecard AS
            WITH yearly AS (
                SELECT
                    firm_key,
                    initiated_year,
                    COUNT(*) AS recalls,
                    SUM(is_class_i) AS class_i,
                    AVG(days_to_report) AS avg_days_to_report
                FROM silver_recall
                WHERE initiated_year IS NOT NULL
                GROUP BY firm_key, initiated_year
            ),
            windowed AS (
                SELECT
                    firm_key,
                    initiated_year,
                    recalls,
                    class_i,
                    avg_days_to_report,
                    SUM(recalls) OVER (
                        PARTITION BY firm_key
                        ORDER BY initiated_year
                        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                    ) AS recalls_rolling_3yr,
                    LAG(recalls) OVER (
                        PARTITION BY firm_key ORDER BY initiated_year
                    ) AS prev_year_recalls
                FROM yearly
            )
            SELECT
                f.firm_key,
                f.example_name,
                f.n_name_variants,
                f.firm_state,
                w.initiated_year,
                w.recalls,
                w.class_i,
                ROUND(100.0 * w.class_i / w.recalls, 1) AS class_i_pct,
                ROUND(w.avg_days_to_report, 1) AS avg_days_to_report,
                w.recalls_rolling_3yr,
                w.prev_year_recalls,
                CASE
                    WHEN w.recalls_rolling_3yr >= 12 AND (100.0 * w.class_i / w.recalls) >= 40
                        THEN 'chronic_high_severity'
                    WHEN w.recalls_rolling_3yr >= 12 THEN 'chronic'
                    WHEN (100.0 * w.class_i / w.recalls) >= 50 THEN 'acute_severe'
                    ELSE 'watch'
                END AS firm_flag
            FROM windowed w
            JOIN silver_firm f ON f.firm_key = w.firm_key;

            CREATE TABLE gold_state_year AS
            WITH exploded AS (
                SELECT
                    e.state,
                    r.initiated_year,
                    r.recall_number,
                    r.is_class_i,
                    r.is_nationwide
                FROM silver_exposure e
                JOIN silver_recall r ON r.recall_number = e.recall_number
                WHERE e.state IS NOT NULL AND r.initiated_year IS NOT NULL
            )
            SELECT
                x.state,
                d.pop_k,
                x.initiated_year,
                COUNT(*) AS recall_exposures,
                SUM(x.is_class_i) AS class_i_exposures,
                SUM(CASE WHEN x.is_nationwide = 0 THEN 1 ELSE 0 END) AS listed_exposures,
                ROUND(1000.0 * COUNT(*) / d.pop_k, 3) AS exposures_per_million,
                ROUND(1000.0 * SUM(x.is_class_i) / d.pop_k, 3) AS class_i_per_million
            FROM exploded x
            JOIN dim_state d ON d.state = x.state
            GROUP BY x.state, d.pop_k, x.initiated_year;

            CREATE TABLE gold_hazard_month AS
            SELECT
                COALESCE(hazard_tag, 'unspecified') AS hazard_tag,
                initiated_year,
                initiated_month,
                COUNT(*) AS recalls,
                SUM(is_class_i) AS class_i,
                ROUND(AVG(days_to_classify), 1) AS avg_days_to_classify,
                SUM(SUM(is_class_i)) OVER (
                    PARTITION BY COALESCE(hazard_tag, 'unspecified')
                    ORDER BY initiated_year, initiated_month
                ) AS class_i_cumulative
            FROM silver_recall
            WHERE initiated_year IS NOT NULL AND initiated_month IS NOT NULL
            GROUP BY hazard_tag, initiated_year, initiated_month;
            """
        )

    def query(self, sql: str) -> pd.DataFrame:
        with self.connect() as con:
            return pd.read_sql_query(sql, con)

    def firm_scorecard(self) -> pd.DataFrame:
        return self.query(
            """
            SELECT *
            FROM gold_firm_scorecard
            ORDER BY initiated_year DESC, recalls_rolling_3yr DESC
            """
        )

    def latest_firm_flags(self) -> pd.DataFrame:
        return self.query(
            """
            WITH latest AS (
                SELECT
                    firm_key,
                    MAX(initiated_year) AS latest_year
                FROM gold_firm_scorecard
                GROUP BY firm_key
            )
            SELECT s.*
            FROM gold_firm_scorecard s
            JOIN latest l
              ON l.firm_key = s.firm_key AND l.latest_year = s.initiated_year
            ORDER BY
                CASE s.firm_flag
                    WHEN 'chronic_high_severity' THEN 1
                    WHEN 'chronic' THEN 2
                    WHEN 'acute_severe' THEN 3
                    ELSE 4
                END,
                s.recalls_rolling_3yr DESC
            """
        )

    def state_year(self) -> pd.DataFrame:
        return self.query("SELECT * FROM gold_state_year ORDER BY initiated_year, class_i_per_million DESC")

    def hazard_month(self) -> pd.DataFrame:
        return self.query("SELECT * FROM gold_hazard_month ORDER BY initiated_year, initiated_month")

    def quality_snapshot(self) -> pd.DataFrame:
        return self.query(
            """
            SELECT
                COUNT(*) AS recalls,
                SUM(CASE WHEN initiated_on IS NULL THEN 1 ELSE 0 END) AS missing_init_date,
                SUM(CASE WHEN days_to_report IS NULL THEN 1 ELSE 0 END) AS missing_report_lag,
                SUM(is_stale_ongoing) AS stale_ongoing,
                SUM(is_nationwide) AS nationwide,
                SUM(is_class_i) AS class_i,
                COUNT(DISTINCT firm_key) AS distinct_firms,
                (SELECT COUNT(*) FROM silver_exposure WHERE state IS NULL) AS unparsed_exposure,
                (SELECT AVG(n_name_variants) FROM silver_firm) AS avg_name_variants
            FROM silver_recall
            """
        )
