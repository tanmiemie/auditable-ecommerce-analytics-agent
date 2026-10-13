#!/usr/bin/env python3
"""Build evaluator-only expected trusted tables from the synthetic raw database.

This is not an imputation engine. Facts that cannot be reconstructed are marked
unavailable in metric_health_windows instead of being invented.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DB = ROOT / "data" / "ecommerce_raw.sqlite"
OUT_DB = ROOT / "ground_truth" / "ecommerce_expected.sqlite"
SUMMARY = ROOT / "ground_truth" / "expected_reconciliation.json"


def scalar(conn: sqlite3.Connection, sql: str):
    return conn.execute(sql).fetchone()[0]


def build():
    if not RAW_DB.exists():
        raise SystemExit(f"Missing raw database: {RAW_DB}")
    if OUT_DB.exists():
        OUT_DB.unlink()

    conn = sqlite3.connect(OUT_DB)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("ATTACH DATABASE ? AS raw", (str(RAW_DB),))

        conn.executescript(
            """
            CREATE TABLE trusted_sessions AS
            WITH base AS (
              SELECT
                s.*,
                CASE
                  WHEN user_id <> '' THEN user_id
                  ELSE anonymous_id
                END AS canonical_visitor_id,
                CASE
                  WHEN user_agent LIKE '%PriceMonitor%' THEN 1 ELSE 0
                END AS suspected_bot
              FROM raw.sessions s
            ), ordered_v2 AS (
              SELECT
                base.*,
                LAG(strftime('%s', session_start)) OVER (
                  PARTITION BY canonical_visitor_id ORDER BY session_start, session_id
                ) AS previous_start_epoch
              FROM base
              WHERE platform='web' AND sessionization_version='v2_5min'
            ), grouped_v2 AS (
              SELECT
                ordered_v2.*,
                SUM(
                  CASE
                    WHEN previous_start_epoch IS NULL
                      OR strftime('%s', session_start) - previous_start_epoch > 1800
                    THEN 1 ELSE 0
                  END
                ) OVER (
                  PARTITION BY canonical_visitor_id ORDER BY session_start, session_id
                  ROWS UNBOUNDED PRECEDING
                ) AS visit_group
              FROM ordered_v2
            ), ranked_v2 AS (
              SELECT
                grouped_v2.*,
                ROW_NUMBER() OVER (
                  PARTITION BY canonical_visitor_id, visit_group ORDER BY session_start, session_id
                ) AS session_rank_in_visit
              FROM grouped_v2
            ), combined AS (
              SELECT
                base.*,
                session_id AS reconstructed_visit_id,
                1 AS session_rank_in_visit
              FROM base
              WHERE NOT (platform='web' AND sessionization_version='v2_5min')
              UNION ALL
              SELECT
                session_id, anonymous_id, user_id, session_start, ingested_at,
                platform, app_version, channel_raw, campaign_id, user_agent,
                ip_hash, is_known_bot, sessionization_version,
                canonical_visitor_id, suspected_bot,
                'CV_' || canonical_visitor_id || '_' || visit_group AS reconstructed_visit_id,
                session_rank_in_visit
              FROM ranked_v2
            )
            SELECT
              *,
              CASE
                WHEN sessionization_version = 'v2_5min' THEN reconstructed_visit_id
                ELSE session_id
              END AS canonical_visit_id,
              CASE
                WHEN suspected_bot = 1 THEN 0
                WHEN sessionization_version = 'v2_5min' AND session_rank_in_visit > 1 THEN 0
                ELSE 1
              END AS eligible_for_visit_metrics,
              CASE
                WHEN suspected_bot = 1 THEN 'suspected_bot'
                WHEN sessionization_version = 'v2_5min' AND session_rank_in_visit > 1 THEN 'merged_under_30min_rule'
                ELSE ''
              END AS visit_exclusion_reason,
              CAST((julianday(ingested_at) - julianday(session_start)) * 24.0 AS REAL) AS ingestion_lag_hours
            FROM combined;

            CREATE INDEX idx_trusted_sessions_id ON trusted_sessions(session_id);
            CREATE INDEX idx_trusted_sessions_visit ON trusted_sessions(canonical_visit_id);

            CREATE TABLE trusted_events AS
            WITH ranked AS (
              SELECT
                e.*,
                ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY ingested_at, rowid) AS duplicate_rank,
                COUNT(*) OVER (PARTITION BY event_id) AS raw_duplicate_count
              FROM raw.events e
            )
            SELECT
              r.*,
              CASE
                WHEN event_name_raw = 'cart_add' THEN 'add_to_cart'
                ELSE event_name_raw
              END AS event_name_canonical,
              CASE
                WHEN quantity_raw = '' THEN NULL
                WHEN quantity_raw NOT GLOB '*[^0-9]*' THEN CAST(quantity_raw AS INTEGER)
                ELSE NULL
              END AS quantity,
              CASE
                WHEN quantity_raw <> '' AND quantity_raw GLOB '*[^0-9]*' THEN 1 ELSE 0
              END AS invalid_quantity,
              COALESCE(s.suspected_bot, 0) AS suspected_bot,
              CASE WHEN COALESCE(s.suspected_bot, 0) = 1 THEN 0 ELSE 1 END AS eligible_for_behavior_metrics,
              CAST((julianday(r.ingested_at) - julianday(r.event_ts)) * 24.0 AS REAL) AS ingestion_lag_hours,
              CASE
                WHEN r.platform='ios' AND r.app_version='6.2.1'
                  AND r.event_ts >= '2026-04-10' AND r.event_ts < '2026-04-14'
                  AND r.event_name_raw IN ('add_to_cart','cart_add') AND r.experiment_id=''
                THEN 0 ELSE 1
              END AS eligible_for_experiment_attribution
            FROM ranked r
            LEFT JOIN trusted_sessions s USING(session_id)
            WHERE duplicate_rank = 1;

            CREATE INDEX idx_trusted_events_id ON trusted_events(event_id);
            CREATE INDEX idx_trusted_events_session ON trusted_events(session_id);

            CREATE TABLE trusted_orders AS
            WITH refund_totals AS (
              SELECT order_id, SUM(CAST(refund_amount AS REAL)) AS completed_refund_amount
              FROM raw.refunds
              WHERE completed_at <> ''
              GROUP BY order_id
            )
            SELECT
              o.*,
              COALESCE(r.completed_refund_amount, 0.0) AS completed_refund_amount,
              CAST(o.order_total AS REAL) - COALESCE(r.completed_refund_amount, 0.0) AS net_order_revenue,
              CASE
                WHEN o.is_confirmed_fraud='1' THEN 0
                WHEN COALESCE(u.is_employee,'0')='1' THEN 0
                ELSE 1
              END AS eligible_for_commercial_metrics,
              CASE
                WHEN o.is_confirmed_fraud='1' THEN 'confirmed_fraud'
                WHEN COALESCE(u.is_employee,'0')='1' THEN 'employee_order'
                ELSE ''
              END AS commercial_exclusion_reason,
              CAST((julianday(o.ingested_at) - julianday(o.order_ts)) * 24.0 AS REAL) AS ingestion_lag_hours
            FROM raw.orders o
            LEFT JOIN raw.users u USING(user_id)
            LEFT JOIN refund_totals r USING(order_id);

            CREATE INDEX idx_trusted_orders_id ON trusted_orders(order_id);

            CREATE TABLE trusted_experiment_exposures AS
            SELECT
              e.*,
              CASE WHEN a.user_id IS NULL THEN 0 ELSE 1 END AS has_valid_assignment,
              CASE
                WHEN a.user_id IS NULL THEN 'orphan_exposure'
                WHEN e.variant <> a.variant THEN 'variant_conflict'
                WHEN e.exposed_at < a.assigned_at THEN 'exposure_before_assignment'
                ELSE ''
              END AS integrity_issue,
              CASE
                WHEN a.user_id IS NULL OR e.variant <> a.variant OR e.exposed_at < a.assigned_at THEN 0
                ELSE 1
              END AS eligible_for_experiment_analysis
            FROM raw.experiment_exposures e
            LEFT JOIN raw.experiment_assignments a
              ON e.experiment_id=a.experiment_id AND e.user_id=a.user_id;

            CREATE TABLE metric_health_windows (
              metric_name TEXT,
              platform TEXT,
              app_version TEXT,
              start_date TEXT,
              end_date TEXT,
              status TEXT,
              reason TEXT,
              allowed_action TEXT
            );

            INSERT INTO metric_health_windows VALUES
              ('client_checkout_start_rate','ios','6.1.0','2026-03-15','2026-03-18','unavailable','begin_checkout tracking outage','do_not_report'),
              ('experiment_attributed_cart_actions','ios','6.2.1','2026-04-10','2026-04-13','unavailable','experiment_id property missing','do_not_use_for_experiment_effect'),
              ('raw_visits','web','all','2026-02-15','2026-02-18','superseded','sessionization timeout changed','use_canonical_visits'),
              ('raw_add_to_cart','android','6.2.0','2026-03-25','2026-04-30','superseded','event renamed to cart_add','use_event_name_canonical');

            CREATE TABLE data_quality_decisions (
              pattern_id TEXT,
              resolution_class TEXT,
              trusted_action TEXT,
              residual_uncertainty TEXT
            );

            INSERT INTO data_quality_decisions VALUES
              ('BOT-01','human_review','flag and exclude from approved visit metrics','behavior supports suspicion, not independent confirmation'),
              ('VIS-01','deterministic_fix','deduplicate exact event_id','near-duplicate logic is not generalized'),
              ('VIS-02','deterministic_fix','reconstruct visits with approved 30-minute rule','production systems should re-sessionize from events'),
              ('FRAUD-01','human_review','exclude confirmed fraud from commercial metrics','analytics system does not perform enforcement'),
              ('TRK-01','mark_unavailable','block affected client metric','missing client events are not reconstructed'),
              ('TRK-02','canonical_mapping','map cart_add to add_to_cart','mapping is version and date dependent'),
              ('FRAUD-02','human_review','exclude confirmed fraud from commercial metrics','analytics system does not perform enforcement'),
              ('TRK-03','mark_unavailable','block affected experiment attribution','experiment_id is not imputed');
            """
        )

        # Reconciliation is stored both in the database and as an easy-to-read JSON file.
        reconciliation = {
            "raw_events": scalar(conn, "SELECT COUNT(*) FROM raw.events"),
            "trusted_events": scalar(conn, "SELECT COUNT(*) FROM trusted_events"),
            "exact_duplicate_event_rows_removed": scalar(conn, "SELECT COUNT(*) FROM raw.events")
                - scalar(conn, "SELECT COUNT(*) FROM trusted_events"),
            "invalid_quantity_events_retained_with_null_typed_value": scalar(conn, "SELECT COUNT(*) FROM trusted_events WHERE invalid_quantity=1"),
            "suspected_bot_sessions": scalar(conn, "SELECT COUNT(*) FROM trusted_sessions WHERE suspected_bot=1"),
            "raw_sessions": scalar(conn, "SELECT COUNT(*) FROM raw.sessions"),
            "canonical_visits_eligible": scalar(conn, "SELECT COUNT(*) FROM trusted_sessions WHERE eligible_for_visit_metrics=1"),
            "sessions_merged_or_excluded": scalar(conn, "SELECT COUNT(*) FROM trusted_sessions WHERE eligible_for_visit_metrics=0"),
            "raw_orders": scalar(conn, "SELECT COUNT(*) FROM raw.orders"),
            "trusted_orders": scalar(conn, "SELECT COUNT(*) FROM trusted_orders"),
            "orders_excluded_from_commercial_metrics": scalar(conn, "SELECT COUNT(*) FROM trusted_orders WHERE eligible_for_commercial_metrics=0"),
            "orphan_or_invalid_exposures": scalar(conn, "SELECT COUNT(*) FROM trusted_experiment_exposures WHERE eligible_for_experiment_analysis=0"),
            "unavailable_metric_windows": scalar(conn, "SELECT COUNT(*) FROM metric_health_windows WHERE status='unavailable'"),
        }

        conn.execute("CREATE TABLE reconciliation_summary (metric TEXT PRIMARY KEY, value INTEGER)")
        conn.executemany(
            "INSERT INTO reconciliation_summary(metric,value) VALUES (?,?)",
            reconciliation.items(),
        )
        conn.commit()
        SUMMARY.write_text(json.dumps(reconciliation, indent=2), encoding="utf-8")
        print(json.dumps(reconciliation, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    build()

