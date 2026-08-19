-- Recall Pulse Warehouse — gold marts
-- These statements are also executed inside src/warehouse.py::_build_gold

-- Firm scorecard: rolling 3-year volume + YoY + a human flag
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
    w.initiated_year,
    w.recalls,
    w.class_i,
    ROUND(100.0 * w.class_i / w.recalls, 1) AS class_i_pct,
    w.recalls_rolling_3yr,
    CASE
        WHEN w.recalls_rolling_3yr >= 12 AND (100.0 * w.class_i / w.recalls) >= 40
            THEN 'chronic_high_severity'
        WHEN w.recalls_rolling_3yr >= 12 THEN 'chronic'
        WHEN (100.0 * w.class_i / w.recalls) >= 50 THEN 'acute_severe'
        ELSE 'watch'
    END AS firm_flag
FROM windowed w
JOIN silver_firm f ON f.firm_key = w.firm_key;

-- State-year exposures after exploding distribution_pattern
SELECT
    e.state,
    d.pop_k,
    r.initiated_year,
    COUNT(*) AS recall_exposures,
    SUM(r.is_class_i) AS class_i_exposures,
    ROUND(1000.0 * COUNT(*) / d.pop_k, 3) AS exposures_per_million
FROM silver_exposure e
JOIN silver_recall r ON r.recall_number = e.recall_number
JOIN dim_state d ON d.state = e.state
WHERE e.state IS NOT NULL AND r.initiated_year IS NOT NULL
GROUP BY e.state, d.pop_k, r.initiated_year;

-- Hazard calendar with a running Class I total
SELECT
    hazard_tag,
    initiated_year,
    initiated_month,
    COUNT(*) AS recalls,
    SUM(is_class_i) AS class_i,
    SUM(SUM(is_class_i)) OVER (
        PARTITION BY hazard_tag
        ORDER BY initiated_year, initiated_month
    ) AS class_i_cumulative
FROM silver_recall
WHERE initiated_year IS NOT NULL
GROUP BY hazard_tag, initiated_year, initiated_month;
