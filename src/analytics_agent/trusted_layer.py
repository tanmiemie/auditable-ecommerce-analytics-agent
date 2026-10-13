from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DB = ROOT / "data" / "ecommerce_raw.sqlite"
TRUSTED_DB = ROOT / "data" / "ecommerce_trusted.sqlite"

BOT_RULE_VERSION = "bot_rule_v1"


def build(raw_db: Path = RAW_DB, out_db: Path = TRUSTED_DB) -> Path:
    """Build the governed trusted layer without modifying the raw database."""
    out_db.parent.mkdir(parents=True, exist_ok=True)
    temporary_db = out_db.with_suffix(f"{out_db.suffix}.tmp")
    if temporary_db.exists():
        temporary_db.unlink()

    con = sqlite3.connect(temporary_db)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("ATTACH DATABASE ? AS raw", (str(raw_db),))
        con.executescript(
            f"""
            CREATE TABLE dim_users AS SELECT * FROM raw.users;
            CREATE TABLE dim_products AS SELECT * FROM raw.products;
            CREATE TABLE dim_campaigns AS SELECT * FROM raw.campaigns;
            CREATE TABLE dim_app_releases AS SELECT * FROM raw.app_releases;
            CREATE TABLE trusted_experiment_assignments AS SELECT * FROM raw.experiment_assignments;
            CREATE TABLE trusted_experiment_exposures AS SELECT * FROM raw.experiment_exposures;

            CREATE TABLE trusted_identity_map AS
            WITH identity_counts AS (
              SELECT anonymous_id,
                     COUNT(DISTINCT CASE WHEN match_status='matched' THEN user_id END) matched_user_count,
                     COUNT(DISTINCT user_id) all_user_count
              FROM raw.identity_map GROUP BY anonymous_id
            )
            SELECT m.*,
                   CASE WHEN m.match_status='matched' AND c.matched_user_count=1
                              AND c.all_user_count=1 THEN 1 ELSE 0 END identity_eligible,
                   CASE WHEN m.match_status<>'matched' THEN m.match_status
                        WHEN c.matched_user_count<>1 OR c.all_user_count<>1 THEN 'identity_conflict'
                        ELSE '' END identity_review_reason
            FROM raw.identity_map m JOIN identity_counts c USING(anonymous_id);

            CREATE TABLE event_dedup_audit AS
            SELECT event_id,COUNT(*) raw_row_count,COUNT(*)-1 removed_row_count,
                   MIN(ingested_at) first_ingested_at,MAX(ingested_at) last_ingested_at,
                   COUNT(DISTINCT
                     COALESCE(session_id,'') || char(31) ||
                     COALESCE(anonymous_id,'') || char(31) || COALESCE(user_id,'') || char(31) ||
                     COALESCE(event_ts,'') || char(31) || COALESCE(event_name_raw,'') || char(31) ||
                     COALESCE(platform,'') || char(31) || COALESCE(app_version,'') || char(31) ||
                     COALESCE(product_id,'') || char(31) || COALESCE(quantity_raw,'') || char(31) ||
                     COALESCE(cart_value_raw,'') || char(31) || COALESCE(experiment_id,'') || char(31) ||
                     COALESCE(source_event_id,'')
                   ) business_variant_count,
                   CASE WHEN COUNT(DISTINCT
                     COALESCE(session_id,'') || char(31) ||
                     COALESCE(anonymous_id,'') || char(31) || COALESCE(user_id,'') || char(31) ||
                     COALESCE(event_ts,'') || char(31) || COALESCE(event_name_raw,'') || char(31) ||
                     COALESCE(platform,'') || char(31) || COALESCE(app_version,'') || char(31) ||
                     COALESCE(product_id,'') || char(31) || COALESCE(quantity_raw,'') || char(31) ||
                     COALESCE(cart_value_raw,'') || char(31) || COALESCE(experiment_id,'') || char(31) ||
                     COALESCE(source_event_id,'')
                   )>1 THEN 1 ELSE 0 END content_conflict
            FROM raw.events GROUP BY event_id HAVING COUNT(*)>1;

            CREATE TABLE trusted_events AS
            WITH ranked AS (
              SELECT e.rowid raw_event_rowid,e.*,
                     ROW_NUMBER() OVER (
                       PARTITION BY e.event_id
                       ORDER BY e.ingested_at,e.event_ts,e.source_event_id,e.rowid
                     ) dedupe_rank
              FROM raw.events e
            ), canonicalized AS (
              SELECT r.*,
                     CASE WHEN r.event_name_raw='cart_add' THEN 'add_to_cart'
                          ELSE r.event_name_raw END event_name,
                     CASE WHEN r.event_name_raw='cart_add' AND r.platform='android'
                               AND r.app_version='6.2.0'
                          THEN 'android_6_2_cart_migration'
                          WHEN r.event_name_raw='cart_add' THEN 'generic_cart_alias'
                          ELSE 'identity' END event_mapping_rule,
                     ROUND((julianday(r.ingested_at)-julianday(r.event_ts))*24,3)
                       ingestion_lag_hours,
                     s.channel_raw,s.campaign_id,s.user_agent,s.ip_hash,s.is_known_bot,
                     CASE
                       WHEN COALESCE(NULLIF(r.user_id,''),NULLIF(s.user_id,'')) IS NOT NULL
                         THEN COALESCE(NULLIF(r.user_id,''),NULLIF(s.user_id,''))
                       WHEN COALESCE(i.identity_eligible,0)=1 AND r.platform IN ('ios','android')
                         THEN i.user_id
                       WHEN COALESCE(i.identity_eligible,0)=1 AND r.platform='web'
                            AND r.event_ts>=i.effective_from THEN i.user_id
                       ELSE r.anonymous_id END canonical_visitor_id,
                     CASE
                       WHEN COALESCE(NULLIF(r.user_id,''),NULLIF(s.user_id,'')) IS NOT NULL
                         THEN COALESCE(NULLIF(r.user_id,''),NULLIF(s.user_id,''))
                       WHEN COALESCE(i.identity_eligible,0)=1
                            AND (r.platform IN ('ios','android')
                                 OR (r.platform='web' AND r.event_ts>=i.effective_from))
                         THEN i.user_id
                       ELSE NULL END canonical_user_id,
                     CASE WHEN s.is_known_bot='1' OR s.user_agent LIKE '%PriceMonitor%'
                          THEN 1 ELSE 0 END suspected_bot,
                     CASE WHEN s.is_known_bot='1' THEN 'source_known_bot_flag'
                          WHEN s.user_agent LIKE '%PriceMonitor%' THEN 'price_monitor_user_agent'
                          ELSE '' END bot_reason,
                     '{BOT_RULE_VERSION}' bot_rule_version
              FROM ranked r
              JOIN raw.sessions s USING(session_id)
              LEFT JOIN trusted_identity_map i ON i.anonymous_id=r.anonymous_id
              WHERE r.dedupe_rank=1
            ), sequenced AS (
              SELECT c.*,
                     LAG(strftime('%s',event_ts)) OVER (
                       PARTITION BY canonical_visitor_id ORDER BY event_ts,event_id
                     ) previous_event_epoch
              FROM canonicalized c
            ), numbered AS (
              SELECT s.*,
                     SUM(CASE WHEN previous_event_epoch IS NULL
                                   OR strftime('%s',event_ts)-previous_event_epoch>1800
                              THEN 1 ELSE 0 END) OVER (
                       PARTITION BY canonical_visitor_id ORDER BY event_ts,event_id
                       ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                     ) canonical_visit_number
              FROM sequenced s
            )
            SELECT n.*,
                   'CV_' || canonical_visitor_id || '_' || printf('%06d',canonical_visit_number)
                     canonical_visit_id
            FROM numbered n;

            CREATE TABLE canonical_visits AS
            WITH visit_rows AS (
              SELECT e.*,
                     ROW_NUMBER() OVER (
                       PARTITION BY canonical_visit_id ORDER BY event_ts,event_id
                     ) visit_event_rank
              FROM trusted_events e
            )
            SELECT canonical_visit_id,canonical_visitor_id,
                   MAX(canonical_user_id) canonical_user_id,
                   MIN(event_ts) canonical_visit_start,MAX(event_ts) canonical_visit_end,
                   COUNT(*) event_count,MAX(suspected_bot) suspected_bot,
                   COALESCE(GROUP_CONCAT(DISTINCT NULLIF(bot_reason,'')),'') bot_reason,
                   MAX(bot_rule_version) bot_rule_version,
                   MAX(CASE WHEN visit_event_rank=1 THEN platform END) platform,
                   MAX(CASE WHEN visit_event_rank=1 THEN app_version END) app_version,
                   MAX(CASE WHEN visit_event_rank=1 THEN channel_raw END) channel,
                   MAX(CASE WHEN visit_event_rank=1 THEN campaign_id END) campaign_id,
                   MAX(CASE WHEN visit_event_rank=1 THEN session_id END) first_session_id,
                   CASE WHEN MAX(suspected_bot)=0 THEN 1 ELSE 0 END eligible_for_traffic_metrics
            FROM visit_rows GROUP BY canonical_visit_id,canonical_visitor_id;

            CREATE TABLE trusted_sessions AS
            WITH session_visit AS (
              SELECT session_id,MIN(canonical_visit_id) canonical_visit_id,
                     COUNT(DISTINCT canonical_visit_id) canonical_visit_count
              FROM trusted_events GROUP BY session_id
            )
            SELECT s.*,
                   CASE WHEN NULLIF(s.user_id,'') IS NOT NULL THEN s.user_id
                        WHEN COALESCE(i.identity_eligible,0)=1 AND s.platform IN ('ios','android')
                          THEN i.user_id
                        WHEN COALESCE(i.identity_eligible,0)=1 AND s.platform='web'
                             AND s.session_start>=i.effective_from THEN i.user_id
                        ELSE s.anonymous_id END visitor_id,
                   CASE WHEN s.is_known_bot='1' OR s.user_agent LIKE '%PriceMonitor%'
                        THEN 1 ELSE 0 END suspected_bot,
                   CASE WHEN s.is_known_bot='1' THEN 'source_known_bot_flag'
                        WHEN s.user_agent LIKE '%PriceMonitor%' THEN 'price_monitor_user_agent'
                        ELSE '' END bot_reason,
                   '{BOT_RULE_VERSION}' bot_rule_version,
                   sv.canonical_visit_id,COALESCE(sv.canonical_visit_count,0) canonical_visit_count,
                   CASE WHEN s.is_known_bot='1' OR s.user_agent LIKE '%PriceMonitor%'
                        THEN 0 ELSE 1 END eligible_for_visit_metrics,
                   CASE WHEN s.is_known_bot='1' OR s.user_agent LIKE '%PriceMonitor%'
                        THEN 'suspected_bot' ELSE '' END exclusion_reason,
                   1 visit_rank
            FROM raw.sessions s
            LEFT JOIN trusted_identity_map i USING(anonymous_id)
            LEFT JOIN session_visit sv USING(session_id);

            CREATE TABLE trusted_refunds AS
            SELECT r.*,
                   ROUND((julianday(r.ingested_at)-julianday(r.requested_at))*24,3)
                     ingestion_lag_hours,
                   CASE WHEN r.requested_at<=datetime(o.order_ts,'+30 days')
                        THEN 1 ELSE 0 END within_refund_window,
                   CASE WHEN r.requested_at>datetime(o.order_ts,'+30 days')
                        THEN 'late_refund_request' ELSE '' END review_reason
            FROM raw.refunds r JOIN raw.orders o USING(order_id);

            CREATE TABLE trusted_order_status_history AS
            SELECT h.*,
                   CASE WHEN ABS(CAST(h.order_total_snapshot AS REAL)-CAST(o.order_total AS REAL))<=0.01
                        THEN 1 ELSE 0 END snapshot_amount_valid,
                   ROW_NUMBER() OVER (
                     PARTITION BY h.order_id
                     ORDER BY h.status_ts DESC,h.ingested_at DESC,h.rowid DESC
                   ) current_status_rank
            FROM raw.order_status_history h
            JOIN raw.orders o USING(order_id);

            CREATE TABLE trusted_order_current_status AS
            SELECT order_id,status current_status,status_ts current_status_ts,
                   ingested_at current_status_ingested_at,order_total_snapshot,
                   snapshot_amount_valid
            FROM trusted_order_status_history
            WHERE current_status_rank=1;

            CREATE TABLE trusted_orders AS
            WITH refund_totals AS (
              SELECT order_id,
                     SUM(CASE WHEN within_refund_window=1
                              THEN CAST(refund_amount AS REAL) ELSE 0 END) requested_refund_amount,
                     MIN(requested_at) first_refund_requested_at,
                     MAX(requested_at) last_refund_requested_at,
                     SUM(CASE WHEN within_refund_window=0 THEN 1 ELSE 0 END) late_refund_count
              FROM trusted_refunds GROUP BY order_id
            ), order_visit_candidates AS (
              SELECT o.order_id,o.order_ts,e.canonical_visit_id,e.event_ts,e.event_id
              FROM raw.orders o
              JOIN trusted_events e ON e.session_id=o.session_id
              WHERE NULLIF(o.session_id,'') IS NOT NULL
            ), order_visit_ranked AS (
              SELECT c.*,
                     ROW_NUMBER() OVER (
                       PARTITION BY order_id
                       ORDER BY CASE WHEN event_ts<=order_ts THEN 0 ELSE 1 END,
                                CASE WHEN event_ts<=order_ts THEN event_ts END DESC,
                                event_ts ASC,event_id
                     ) attribution_rank
              FROM order_visit_candidates c
            ), order_visit AS (
              SELECT order_id,canonical_visit_id
              FROM order_visit_ranked WHERE attribution_rank=1
            )
            SELECT o.*,ov.canonical_visit_id,
                   cs.current_status,cs.current_status_ts,cs.current_status_ingested_at,
                   cs.snapshot_amount_valid,
                   ROUND((julianday(o.ingested_at)-julianday(o.order_ts))*24,3)
                     ingestion_lag_hours,
                   CAST(o.order_total AS REAL) gross_order_revenue,
                   COALESCE(r.requested_refund_amount,0.0) requested_refund_amount,
                   CAST(o.order_total AS REAL)-COALESCE(r.requested_refund_amount,0.0)
                     net_order_revenue,
                   datetime(o.order_ts,'+30 days') refund_window_end,
                   r.first_refund_requested_at,r.last_refund_requested_at,
                   COALESCE(r.late_refund_count,0) late_refund_count,
                   CASE WHEN o.is_confirmed_fraud='1' THEN 0 ELSE 1 END
                     eligible_for_commercial_metrics,
                   CASE WHEN o.is_confirmed_fraud='1' THEN 1 ELSE 0 END
                     fraud_label_uses_latest_known_state,
                   CASE WHEN o.is_confirmed_fraud='1'
                        THEN 'restated_with_latest_fraud_label_timestamp_unavailable'
                        ELSE 'not_confirmed_fraud' END fraud_as_of_status,
                   CASE WHEN COALESCE(u.is_employee,'0')='1' THEN 1 ELSE 0 END is_employee_order,
                   CASE WHEN o.is_confirmed_fraud='1' THEN 'confirmed_fraud'
                        ELSE '' END exclusion_reason
            FROM raw.orders o
            LEFT JOIN dim_users u USING(user_id)
            LEFT JOIN refund_totals r USING(order_id)
            LEFT JOIN order_visit ov USING(order_id)
            LEFT JOIN trusted_order_current_status cs USING(order_id);

            CREATE TABLE tracking_health_daily AS
            WITH checkout AS (
              SELECT platform,app_version,date(event_ts) metric_date,
                     COUNT(*) checkout_events
              FROM trusted_events WHERE event_name='begin_checkout'
              GROUP BY 1,2,3
            ), order_counts AS (
              SELECT s.platform,s.app_version,date(o.order_ts) metric_date,
                     COUNT(*) paid_orders
              FROM trusted_orders o
              JOIN trusted_sessions s USING(session_id)
              WHERE o.payment_status='paid' AND o.eligible_for_commercial_metrics=1
              GROUP BY 1,2,3
            )
            SELECT o.platform,o.app_version,o.metric_date,
                   COALESCE(c.checkout_events,0) checkout_events,o.paid_orders,
                   ROUND(1.0*COALESCE(c.checkout_events,0)/o.paid_orders,4)
                     checkout_events_per_order,
                   CASE WHEN o.paid_orders>=5 AND COALESCE(c.checkout_events,0)=0
                        THEN 'unavailable'
                        WHEN o.paid_orders>=5 AND 1.0*COALESCE(c.checkout_events,0)/o.paid_orders<0.25
                        THEN 'degraded'
                        ELSE 'available' END checkout_metric_status,
                   CASE WHEN o.paid_orders>=5 AND COALESCE(c.checkout_events,0)=0
                        THEN 'server_orders_present_but_checkout_events_missing'
                        WHEN o.paid_orders>=5 AND 1.0*COALESCE(c.checkout_events,0)/o.paid_orders<0.25
                        THEN 'checkout_events_low_relative_to_server_orders'
                        ELSE '' END health_reason
            FROM order_counts o LEFT JOIN checkout c USING(platform,app_version,metric_date);

            CREATE TABLE experiment_instrumentation_health AS
            WITH assigned_events AS (
              SELECT e.platform,e.app_version,date(e.event_ts) metric_date,e.event_name,
                     COUNT(*) event_count,
                     SUM(CASE WHEN NULLIF(e.experiment_id,'') IS NULL THEN 1 ELSE 0 END)
                       missing_experiment_id_count
              FROM trusted_events e
              JOIN trusted_experiment_assignments a
                ON a.user_id=e.canonical_user_id
              WHERE e.event_name='add_to_cart'
              GROUP BY 1,2,3,4
            )
            SELECT *,ROUND(1.0*missing_experiment_id_count/event_count,4) missing_rate,
                   CASE WHEN event_count>=10
                              AND 1.0*missing_experiment_id_count/event_count>0.10
                        THEN 'unavailable' ELSE 'available' END experiment_metric_status
            FROM assigned_events;

            CREATE TABLE data_freshness_audit AS
            SELECT 'events' source_name,MIN(event_ts) min_source_ts,MAX(event_ts) max_source_ts,
                   MAX(ingested_at) max_ingested_at,
                   ROUND(AVG(ingestion_lag_hours),3) avg_ingestion_lag_hours,
                   ROUND(MAX(ingestion_lag_hours),3) max_ingestion_lag_hours
            FROM trusted_events
            UNION ALL
            SELECT 'orders',MIN(order_ts),MAX(order_ts),MAX(ingested_at),
                   ROUND(AVG(ingestion_lag_hours),3),ROUND(MAX(ingestion_lag_hours),3)
            FROM trusted_orders
            UNION ALL
            SELECT 'refunds',MIN(requested_at),MAX(requested_at),MAX(ingested_at),
                   ROUND(AVG(ingestion_lag_hours),3),ROUND(MAX(ingestion_lag_hours),3)
            FROM trusted_refunds;

            CREATE TABLE identity_health_audit AS
            SELECT 'anonymous_ids_per_user' check_name,
                   COUNT(*) entities,
                   ROUND(AVG(anonymous_id_count),3) average_value,
                   MAX(anonymous_id_count) maximum_value
            FROM (
              SELECT user_id,COUNT(DISTINCT anonymous_id) anonymous_id_count
              FROM trusted_identity_map WHERE identity_eligible=1 GROUP BY user_id
            );

            CREATE TABLE fraud_signal_audit AS
            SELECT 'shared_payment_token' signal_type,payment_token_hash signal_value,
                   COUNT(DISTINCT user_id) user_count,COUNT(*) order_count,
                   MAX(CASE WHEN is_confirmed_fraud='1' THEN 1 ELSE 0 END) has_confirmed_fraud
            FROM trusted_orders
            GROUP BY payment_token_hash
            HAVING COUNT(DISTINCT user_id)>1
            UNION ALL
            SELECT 'shared_device',device_id,COUNT(DISTINCT user_id),COUNT(*),
                   MAX(CASE WHEN is_confirmed_fraud='1' THEN 1 ELSE 0 END)
            FROM trusted_orders
            GROUP BY device_id
            HAVING COUNT(DISTINCT user_id)>1;

            CREATE TABLE contract_check_results AS
            SELECT 'users_primary_key' check_name,
                   (SELECT COUNT(*)-COUNT(DISTINCT user_id) FROM dim_users) violation_count,
                   'critical' severity
            UNION ALL SELECT 'sessions_primary_key',
                   (SELECT COUNT(*)-COUNT(DISTINCT session_id) FROM trusted_sessions),'critical'
            UNION ALL SELECT 'orders_primary_key',
                   (SELECT COUNT(*)-COUNT(DISTINCT order_id) FROM trusted_orders),'critical'
            UNION ALL SELECT 'refunds_primary_key',
                   (SELECT COUNT(*)-COUNT(DISTINCT refund_id) FROM trusted_refunds),'critical'
            UNION ALL SELECT 'event_session_orphans',
                   (SELECT COUNT(*) FROM raw.events e LEFT JOIN raw.sessions s USING(session_id)
                    WHERE s.session_id IS NULL),'high'
            UNION ALL SELECT 'required_event_fields_missing',
                   (SELECT COUNT(*) FROM raw.events
                    WHERE NULLIF(event_id,'') IS NULL OR NULLIF(session_id,'') IS NULL
                       OR NULLIF(anonymous_id,'') IS NULL OR NULLIF(event_ts,'') IS NULL
                       OR NULLIF(ingested_at,'') IS NULL OR NULLIF(event_name_raw,'') IS NULL),'critical'
            UNION ALL SELECT 'event_ingestion_before_event_time',
                   (SELECT COUNT(*) FROM trusted_events WHERE ingestion_lag_hours<0),'high'
            UNION ALL SELECT 'order_user_orphans',
                   (SELECT COUNT(*) FROM raw.orders o LEFT JOIN raw.users u USING(user_id)
                    WHERE u.user_id IS NULL),'high'
            UNION ALL SELECT 'refund_order_orphans',
                   (SELECT COUNT(*) FROM raw.refunds r LEFT JOIN raw.orders o USING(order_id)
                    WHERE o.order_id IS NULL),'high'
            UNION ALL SELECT 'invalid_order_totals',
                   (SELECT COUNT(*) FROM trusted_orders
                    WHERE ROUND(ABS(CAST(subtotal AS REAL)-CAST(discount AS REAL)+CAST(shipping_fee AS REAL)+CAST(tax AS REAL)-CAST(order_total AS REAL)),2)>0.01),'high'
            UNION ALL SELECT 'invalid_order_status_snapshots',
                   (SELECT COUNT(*) FROM trusted_order_status_history WHERE snapshot_amount_valid=0),'high'
            UNION ALL SELECT 'refund_amount_exceeds_order_total',
                   (SELECT COUNT(*) FROM trusted_orders WHERE requested_refund_amount>gross_order_revenue+0.01),'high'
            UNION ALL SELECT 'unexpected_session_platform',
                   (SELECT COUNT(*) FROM trusted_sessions WHERE platform NOT IN ('web','ios','android')),'high'
            UNION ALL SELECT 'unexpected_event_name',
                   (SELECT COUNT(*) FROM trusted_events
                    WHERE event_name_raw NOT IN ('app_open','page_view','view_item','add_to_cart','cart_add','begin_checkout','purchase')),'high'
            UNION ALL SELECT 'unexpected_order_currency_or_status',
                   (SELECT COUNT(*) FROM trusted_orders WHERE currency<>'USD' OR payment_status<>'paid'),'high'
            UNION ALL SELECT 'unexpected_identity_status',
                   (SELECT COUNT(*) FROM trusted_identity_map WHERE match_status NOT IN ('matched','pending','ambiguous')),'high'
            UNION ALL SELECT 'duplicate_experiment_assignment',
                   (SELECT COUNT(*)-COUNT(DISTINCT experiment_id || char(31) || user_id)
                    FROM trusted_experiment_assignments),'critical'
            UNION ALL SELECT 'experiment_exposure_without_assignment',
                   (SELECT COUNT(*) FROM trusted_experiment_exposures e
                    LEFT JOIN trusted_experiment_assignments a
                      ON a.experiment_id=e.experiment_id AND a.user_id=e.user_id
                    WHERE a.user_id IS NULL),'high'
            UNION ALL SELECT 'experiment_variant_mismatch',
                   (SELECT COUNT(*) FROM trusted_experiment_exposures e
                    JOIN trusted_experiment_assignments a
                      ON a.experiment_id=e.experiment_id AND a.user_id=e.user_id
                    WHERE e.variant<>a.variant),'critical';

            CREATE TABLE metric_health_windows(
              metric_name TEXT,platform TEXT,start_date TEXT,end_date TEXT,status TEXT,reason TEXT
            );
            INSERT INTO metric_health_windows VALUES
              ('visits','web','2026-01-10','2026-01-12','adjusted','suspected automation excluded; raw and filtered values required'),
              ('visits','web','2026-02-15','2026-02-18','adjusted','canonical visits rebuilt with approved 30-minute rule'),
              ('visitor_purchase_conversion_rate','web','2026-01-10','2026-01-12','adjusted','suspected automation excluded; raw and filtered values required'),
              ('visit_purchase_conversion_rate','web','2026-01-10','2026-01-12','adjusted','suspected automation excluded; raw and filtered values required');
            INSERT INTO metric_health_windows
            SELECT 'checkout_start_rate',platform,metric_date,metric_date,
                   checkout_metric_status,health_reason
            FROM tracking_health_daily
            WHERE checkout_metric_status<>'available';
            INSERT INTO metric_health_windows
            SELECT 'experiment_metrics',platform,metric_date,metric_date,
                   experiment_metric_status,'experiment_id missing for assigned-user events'
            FROM experiment_instrumentation_health
            WHERE experiment_metric_status<>'available';

            CREATE TABLE data_quality_audit AS
            SELECT 'events' object_name,'duplicate_rows_removed' check_name,
                   (SELECT SUM(removed_row_count) FROM event_dedup_audit) observed_value,
                   'adjusted' status
            UNION ALL SELECT 'events','conflicting_duplicate_event_ids',
                   (SELECT COUNT(*) FROM event_dedup_audit WHERE content_conflict=1),
                   'retained_earliest_and_flagged'
            UNION ALL SELECT 'identity_map','ineligible_links',
                   (SELECT COUNT(*) FROM trusted_identity_map WHERE identity_eligible=0),'excluded'
            UNION ALL SELECT 'canonical_visits','suspected_bot_visits',
                   (SELECT COUNT(*) FROM canonical_visits WHERE suspected_bot=1),'excluded_from_headline'
            UNION ALL SELECT 'orders','confirmed_fraud_orders',
                   (SELECT COUNT(*) FROM trusted_orders WHERE is_confirmed_fraud='1'),'excluded'
            UNION ALL SELECT 'orders','employee_orders',
                   (SELECT COUNT(*) FROM trusted_orders WHERE is_employee_order=1),'included_with_flag'
            UNION ALL SELECT 'orders','orders_without_canonical_visit',
                   (SELECT COUNT(*) FROM trusted_orders WHERE canonical_visit_id IS NULL),'unattributed'
            UNION ALL SELECT 'order_status_history','invalid_snapshots',
                   (SELECT COUNT(*) FROM trusted_order_status_history WHERE snapshot_amount_valid=0),'review'
            UNION ALL SELECT 'refunds','late_refund_requests',
                   (SELECT COUNT(*) FROM trusted_refunds WHERE within_refund_window=0),'review'
            UNION ALL SELECT 'tracking','unavailable_checkout_metric_days',
                   (SELECT COUNT(*) FROM tracking_health_daily WHERE checkout_metric_status='unavailable'),'unavailable'
            UNION ALL SELECT 'experiments','unavailable_instrumentation_rows',
                   (SELECT COUNT(*) FROM experiment_instrumentation_health WHERE experiment_metric_status='unavailable'),'unavailable'
            UNION ALL SELECT 'contracts','total_contract_violations',
                   (SELECT SUM(violation_count) FROM contract_check_results),'review';

            CREATE INDEX idx_te_event_ts ON trusted_events(event_ts);
            CREATE INDEX idx_te_visit ON trusted_events(canonical_visit_id);
            CREATE INDEX idx_cv_start ON canonical_visits(canonical_visit_start);
            CREATE INDEX idx_cv_visitor ON canonical_visits(canonical_visitor_id);
            CREATE INDEX idx_ts_start ON trusted_sessions(session_start);
            CREATE INDEX idx_to_order_ts ON trusted_orders(order_ts);
            CREATE INDEX idx_to_visit ON trusted_orders(canonical_visit_id);
            CREATE INDEX idx_thd_date ON tracking_health_daily(metric_date);
            CREATE INDEX idx_eih_date ON experiment_instrumentation_health(metric_date);
            CREATE UNIQUE INDEX idx_to_order_id ON trusted_orders(order_id);
            CREATE UNIQUE INDEX idx_tr_refund_id ON trusted_refunds(refund_id);
            """
        )
        con.commit()
    except Exception:
        con.close()
        if temporary_db.exists():
            temporary_db.unlink()
        raise
    else:
        con.close()
        os.replace(temporary_db, out_db)
    return out_db


if __name__ == "__main__":
    print(build())
