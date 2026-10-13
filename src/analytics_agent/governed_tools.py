from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .trusted_layer import TRUSTED_DB, build


@dataclass(frozen=True)
class MetricSpec:
    label: str
    definition: str
    sources: tuple[str, ...]
    dimensions: tuple[str, ...]


METRICS = {
    "visits": MetricSpec(
        "Visits",
        "Distinct 30-minute canonical visits; headline excludes suspected-bot visits.",
        ("canonical_visits",),
        ("date", "platform", "app_version", "channel", "country", "campaign_id"),
    ),
    "visitor_purchase_conversion_rate": MetricSpec(
        "Visitor Purchase Conversion Rate",
        "Eligible visitors with at least one eligible paid order divided by visitors with a canonical visit in the same reporting window.",
        ("canonical_visits", "trusted_orders", "dim_users"),
        ("date", "platform", "channel", "country", "campaign_id"),
    ),
    "visit_purchase_conversion_rate": MetricSpec(
        "Visit Purchase Conversion Rate",
        "Canonical visits linked through session lineage to at least one eligible paid order divided by canonical visits.",
        ("canonical_visits", "trusted_orders"),
        ("date", "platform", "app_version", "channel", "country", "campaign_id"),
    ),
    "checkout_start_rate": MetricSpec(
        "Checkout Start Rate",
        "Eligible canonical visits containing at least one canonical begin_checkout event divided by eligible canonical visits.",
        ("canonical_visits", "trusted_events", "tracking_health_daily"),
        ("date", "platform", "app_version", "channel", "country", "campaign_id"),
    ),
    "gross_revenue": MetricSpec(
        "Gross Revenue",
        "Sum of eligible paid order_total before refunds; confirmed fraud excluded and employee orders included with a flag.",
        ("trusted_orders", "trusted_sessions"),
        ("date", "platform", "channel", "shipping_country", "campaign_id", "is_employee_order"),
    ),
    "net_revenue": MetricSpec(
        "Net Revenue",
        "Mature eligible order-cohort revenue less refunds recognized at requested_at as of the supplied report timestamp.",
        ("trusted_orders", "trusted_refunds", "trusted_sessions"),
        ("date", "platform", "channel", "shipping_country", "campaign_id", "is_employee_order"),
    ),
}


VISIT_DIMENSIONS = {
    "date": "date(v.canonical_visit_start)",
    "platform": "v.platform",
    "app_version": "v.app_version",
    "channel": "v.channel",
    "country": "COALESCE(u.country,'unknown')",
    "campaign_id": "COALESCE(v.campaign_id,'none')",
}

ORDER_DIMENSIONS = {
    "date": "date(o.order_ts)",
    "platform": "COALESCE(s.platform,'unknown')",
    "channel": "COALESCE(s.channel_raw,'unknown')",
    "shipping_country": "o.shipping_country",
    "campaign_id": "COALESCE(s.campaign_id,'none')",
    "is_employee_order": "o.is_employee_order",
}


class GovernedAnalyticsTools:
    def __init__(self, db: Path = TRUSTED_DB):
        self.db = db
        if not db.exists():
            build(out_db=db)

    def list_capabilities(self) -> dict[str, Any]:
        return {
            name: {
                "label": spec.label,
                "definition": spec.definition,
                "sources": list(spec.sources),
                "dimensions": list(spec.dimensions),
            }
            for name, spec in METRICS.items()
        }

    def metric_lookup(
        self,
        metric: str,
        start_date: str,
        end_date: str,
        group_by: str | None = None,
        filters: dict[str, Any] | None = None,
        report_as_of_ts: str | None = None,
    ) -> dict[str, Any]:
        spec = self._validate_request(metric, group_by, filters)
        if metric == "net_revenue" and not report_as_of_ts:
            raise ValueError("net_revenue requires report_as_of_ts")

        coverage = self.data_coverage(metric)
        if start_date < coverage["start_date"] or end_date > coverage["end_date"]:
            issue = {
                "metric_name": metric,
                "status": "unavailable",
                "reason": "requested period extends beyond available data coverage",
                "available_start_date": coverage["start_date"],
                "available_end_date": coverage["end_date"],
            }
            return self._response(
                metric, spec, start_date, end_date, group_by, filters, report_as_of_ts,
                [], {"status": "unavailable", "issues": [issue]},
                limitations=["No value is returned when any part of the requested period is outside source coverage."], query=None,
            )

        health = self.health_check(metric, start_date, end_date)
        if health["status"] == "unavailable":
            return self._response(
                metric, spec, start_date, end_date, group_by, filters, report_as_of_ts,
                [], health, limitations=["Metric is unavailable for at least one requested slice."], query=None,
            )

        if metric == "visits":
            rows, query = self._visits(start_date, end_date, group_by, filters)
        elif metric == "visitor_purchase_conversion_rate":
            rows, query = self._visitor_conversion(start_date, end_date, group_by, filters)
        elif metric == "visit_purchase_conversion_rate":
            rows, query = self._visit_conversion(start_date, end_date, group_by, filters)
        elif metric == "checkout_start_rate":
            rows, query = self._checkout_start_rate(start_date, end_date, group_by, filters)
        elif metric == "gross_revenue":
            rows, query = self._gross_revenue(start_date, end_date, group_by, filters)
        else:
            rows, query = self._net_revenue(
                start_date, end_date, group_by, filters, report_as_of_ts
            )

        limitations = []
        if metric in {"visits", "visitor_purchase_conversion_rate", "visit_purchase_conversion_rate", "checkout_start_rate"}:
            limitations.append("Headline is bot-filtered; raw value and excluded share are included.")
        if metric in {"gross_revenue", "net_revenue"}:
            limitations.append("Fraud filtering uses latest known labels because label-effective timestamps are unavailable.")
        if metric == "net_revenue":
            limitations.append("Only orders whose 30-day refund window closed by report_as_of_ts are finalized.")
        return self._response(
            metric, spec, start_date, end_date, group_by, filters, report_as_of_ts,
            rows, health, limitations, query,
        )

    def segment_comparison(
        self,
        metric: str,
        start_date: str,
        end_date: str,
        dimension: str,
        filters: dict[str, Any] | None = None,
        report_as_of_ts: str | None = None,
    ) -> dict[str, Any]:
        return self.metric_lookup(
            metric, start_date, end_date, dimension, filters, report_as_of_ts
        )

    def health_check(self, metric: str, start_date: str, end_date: str) -> dict[str, Any]:
        allowed_health_metrics = set(METRICS) | {"checkout_start_rate", "experiment_metrics"}
        if metric not in allowed_health_metrics:
            raise ValueError(f"Unsupported health metric: {metric}")
        con = self._connect()
        try:
            if metric == "checkout_start_rate":
                rows = con.execute(
                    """
                    SELECT 'checkout_start_rate' metric_name,platform,app_version,
                           MIN(metric_date) start_date,MAX(metric_date) end_date,
                           checkout_metric_status status,health_reason reason
                    FROM tracking_health_daily
                    WHERE metric_date BETWEEN ? AND ? AND checkout_metric_status<>'available'
                    GROUP BY platform,app_version,checkout_metric_status,health_reason
                    ORDER BY start_date,platform
                    """,
                    (start_date, end_date),
                ).fetchall()
            else:
                rows = con.execute(
                    """
                    SELECT metric_name,platform,start_date,end_date,status,reason
                    FROM metric_health_windows
                    WHERE metric_name=? AND start_date<=? AND end_date>=?
                    ORDER BY start_date,platform
                    """,
                    (metric, end_date, start_date),
                ).fetchall()
        finally:
            con.close()
        issues = [dict(row) for row in rows]
        statuses = {row["status"] for row in issues}
        status = "unavailable" if "unavailable" in statuses else "adjusted" if statuses else "trusted"
        return {"status": status, "issues": issues}

    def context_retrieval(self, start_date: str, end_date: str) -> dict[str, Any]:
        con = self._connect()
        try:
            campaigns = [
                dict(row) for row in con.execute(
                    "SELECT * FROM dim_campaigns WHERE start_date<=? AND end_date>=? ORDER BY start_date",
                    (end_date, start_date),
                )
            ]
            releases = [
                dict(row) for row in con.execute(
                    "SELECT * FROM dim_app_releases WHERE date(released_at) BETWEEN ? AND ? ORDER BY released_at",
                    (start_date, end_date),
                )
            ]
        finally:
            con.close()
        return {
            "time_range": {"start_date": start_date, "end_date": end_date},
            "campaigns": campaigns,
            "app_releases": releases,
            "causality_guardrail": "Temporal overlap is context, not proof of causality.",
        }

    def data_coverage(self, metric: str) -> dict[str, str]:
        if metric not in METRICS:
            raise ValueError(f"Unsupported metric: {metric}")
        if metric in {"visits", "visitor_purchase_conversion_rate", "visit_purchase_conversion_rate", "checkout_start_rate"}:
            sql = "SELECT MIN(date(canonical_visit_start)),MAX(date(canonical_visit_start)) FROM canonical_visits"
        else:
            sql = "SELECT MIN(date(order_ts)),MAX(date(order_ts)) FROM trusted_orders"
        con = self._connect()
        try:
            start_date, end_date = con.execute(sql).fetchone()
        finally:
            con.close()
        if not start_date or not end_date:
            raise ValueError(f"No source coverage is available for {metric}")
        return {"start_date": start_date, "end_date": end_date}

    def fraud_evidence(
        self, start_date: str, end_date: str, platform: str | None = None
    ) -> dict[str, Any]:
        platform_clause = " AND s.platform=?" if platform else ""
        params: list[Any] = [start_date, end_date]
        if platform:
            params.append(platform)
        sql = f"""
            WITH signaled_orders AS (
              SELECT DISTINCT o.order_id,o.is_confirmed_fraud,o.gross_order_revenue
              FROM trusted_orders o
              LEFT JOIN trusted_sessions s USING(session_id)
              JOIN fraud_signal_audit f
                ON (f.signal_type='shared_device' AND f.signal_value=o.device_id)
                OR (f.signal_type='shared_payment_token' AND f.signal_value=o.payment_token_hash)
              WHERE date(o.order_ts) BETWEEN ? AND ?{platform_clause}
            )
            SELECT
              SUM(CASE WHEN is_confirmed_fraud='1' THEN 1 ELSE 0 END) confirmed_excluded_order_count,
              ROUND(SUM(CASE WHEN is_confirmed_fraud='1' THEN gross_order_revenue ELSE 0 END),2) confirmed_excluded_gross_revenue,
              SUM(CASE WHEN is_confirmed_fraud!='1' THEN 1 ELSE 0 END) suspected_included_order_count,
              ROUND(SUM(CASE WHEN is_confirmed_fraud!='1' THEN gross_order_revenue ELSE 0 END),2) suspected_included_gross_revenue
            FROM signaled_orders
        """
        rows, query = self._query(sql, params)
        summary = rows[0]
        for key in ("confirmed_excluded_order_count", "suspected_included_order_count"):
            summary[key] = summary[key] or 0
        for key in ("confirmed_excluded_gross_revenue", "suspected_included_gross_revenue"):
            summary[key] = summary[key] or 0.0
        return {
            "summary": summary,
            "policy": {
                "confirmed": "excluded_from_commercial_headline",
                "suspected_unconfirmed": "included_in_commercial_headline_and_flagged_for_risk_review",
                "authority_boundary": "Analytics Agent cannot confirm fraud, cancel orders, or block accounts.",
            },
            "executed_query": query,
        }

    def _validate_request(self, metric, group_by, filters):
        if metric not in METRICS:
            raise ValueError(f"Unsupported metric: {metric}")
        spec = METRICS[metric]
        if group_by and group_by not in spec.dimensions:
            raise ValueError(f"Unsupported dimension {group_by} for {metric}")
        for key in (filters or {}):
            if key not in spec.dimensions:
                raise ValueError(f"Unsupported filter {key} for {metric}")
        return spec

    def _connect(self):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _filters(mapping, filters, alias_expression=True):
        clauses, values = [], []
        for key, value in (filters or {}).items():
            expression = mapping[key] if alias_expression else key
            clauses.append(f"{expression}=?")
            values.append(value)
        return clauses, values

    def _visits(self, start, end, group_by, filters):
        segment = VISIT_DIMENSIONS[group_by] if group_by else "'all'"
        clauses, values = self._filters(VISIT_DIMENSIONS, filters)
        where = " AND ".join(["date(v.canonical_visit_start) BETWEEN ? AND ?", *clauses])
        sql = f"""
            SELECT {segment} segment,COUNT(*) raw_value,
                   SUM(v.eligible_for_traffic_metrics) value,
                   COUNT(*)-SUM(v.eligible_for_traffic_metrics) suspected_bot_excluded_value,
                   ROUND(1.0*(COUNT(*)-SUM(v.eligible_for_traffic_metrics))/COUNT(*),6)
                     suspected_bot_excluded_share
            FROM canonical_visits v LEFT JOIN dim_users u ON u.user_id=v.canonical_user_id
            WHERE {where} GROUP BY 1 ORDER BY 1
        """
        return self._query(sql, [start, end, *values])

    def _visitor_conversion(self, start, end, group_by, filters):
        segment = VISIT_DIMENSIONS[group_by] if group_by else "'all'"
        clauses, values = self._filters(VISIT_DIMENSIONS, filters)
        where = " AND ".join(["date(v.canonical_visit_start) BETWEEN ? AND ?", *clauses])
        sql = f"""
            WITH visitor_segments AS (
              SELECT {segment} segment,v.canonical_visitor_id,
                     MAX(v.eligible_for_traffic_metrics) eligible
              FROM canonical_visits v LEFT JOIN dim_users u ON u.user_id=v.canonical_user_id
              WHERE {where} GROUP BY 1,2
            ), buyers AS (
              SELECT DISTINCT user_id visitor_id FROM trusted_orders
              WHERE eligible_for_commercial_metrics=1 AND payment_status='paid'
                AND date(order_ts) BETWEEN ? AND ?
            )
            SELECT s.segment,
                   ROUND(1.0*COUNT(DISTINCT CASE WHEN b.visitor_id IS NOT NULL THEN s.canonical_visitor_id END)/COUNT(DISTINCT s.canonical_visitor_id),6) raw_value,
                   ROUND(1.0*COUNT(DISTINCT CASE WHEN s.eligible=1 AND b.visitor_id IS NOT NULL THEN s.canonical_visitor_id END)/NULLIF(COUNT(DISTINCT CASE WHEN s.eligible=1 THEN s.canonical_visitor_id END),0),6) value,
                   COUNT(DISTINCT s.canonical_visitor_id)-COUNT(DISTINCT CASE WHEN s.eligible=1 THEN s.canonical_visitor_id END) suspected_bot_excluded_denominator,
                   ROUND(1.0*(COUNT(DISTINCT s.canonical_visitor_id)-COUNT(DISTINCT CASE WHEN s.eligible=1 THEN s.canonical_visitor_id END))/COUNT(DISTINCT s.canonical_visitor_id),6) suspected_bot_excluded_share
            FROM visitor_segments s LEFT JOIN buyers b ON b.visitor_id=s.canonical_visitor_id
            GROUP BY 1 ORDER BY 1
        """
        return self._query(sql, [start, end, *values, start, end])

    def _visit_conversion(self, start, end, group_by, filters):
        segment = VISIT_DIMENSIONS[group_by] if group_by else "'all'"
        clauses, values = self._filters(VISIT_DIMENSIONS, filters)
        where = " AND ".join(["date(v.canonical_visit_start) BETWEEN ? AND ?", *clauses])
        sql = f"""
            WITH visits AS (
              SELECT {segment} segment,v.canonical_visit_id,v.eligible_for_traffic_metrics
              FROM canonical_visits v LEFT JOIN dim_users u ON u.user_id=v.canonical_user_id
              WHERE {where}
            ), buyers AS (
              SELECT DISTINCT canonical_visit_id FROM trusted_orders
              WHERE eligible_for_commercial_metrics=1 AND payment_status='paid'
                AND canonical_visit_id IS NOT NULL AND date(order_ts) BETWEEN ? AND ?
            )
            SELECT v.segment,
                   ROUND(1.0*COUNT(DISTINCT CASE WHEN b.canonical_visit_id IS NOT NULL THEN v.canonical_visit_id END)/COUNT(DISTINCT v.canonical_visit_id),6) raw_value,
                   ROUND(1.0*COUNT(DISTINCT CASE WHEN v.eligible_for_traffic_metrics=1 AND b.canonical_visit_id IS NOT NULL THEN v.canonical_visit_id END)/NULLIF(COUNT(DISTINCT CASE WHEN v.eligible_for_traffic_metrics=1 THEN v.canonical_visit_id END),0),6) value,
                   COUNT(DISTINCT v.canonical_visit_id)-COUNT(DISTINCT CASE WHEN v.eligible_for_traffic_metrics=1 THEN v.canonical_visit_id END) suspected_bot_excluded_denominator,
                   ROUND(1.0*(COUNT(DISTINCT v.canonical_visit_id)-COUNT(DISTINCT CASE WHEN v.eligible_for_traffic_metrics=1 THEN v.canonical_visit_id END))/COUNT(DISTINCT v.canonical_visit_id),6) suspected_bot_excluded_share
            FROM visits v LEFT JOIN buyers b USING(canonical_visit_id)
            GROUP BY 1 ORDER BY 1
        """
        return self._query(sql, [start, end, *values, start, end])

    def _checkout_start_rate(self, start, end, group_by, filters):
        segment = VISIT_DIMENSIONS[group_by] if group_by else "'all'"
        clauses, values = self._filters(VISIT_DIMENSIONS, filters)
        where = " AND ".join(["date(v.canonical_visit_start) BETWEEN ? AND ?", *clauses])
        sql = f"""
            WITH visits AS (
              SELECT {segment} segment,v.canonical_visit_id,v.eligible_for_traffic_metrics
              FROM canonical_visits v LEFT JOIN dim_users u ON u.user_id=v.canonical_user_id
              WHERE {where}
            ), checkout_visits AS (
              SELECT DISTINCT canonical_visit_id FROM trusted_events
              WHERE event_name='begin_checkout' AND canonical_visit_id IS NOT NULL
                AND date(event_ts) BETWEEN ? AND ?
            )
            SELECT v.segment,
                   ROUND(1.0*COUNT(DISTINCT CASE WHEN c.canonical_visit_id IS NOT NULL THEN v.canonical_visit_id END)/COUNT(DISTINCT v.canonical_visit_id),6) raw_value,
                   ROUND(1.0*COUNT(DISTINCT CASE WHEN v.eligible_for_traffic_metrics=1 AND c.canonical_visit_id IS NOT NULL THEN v.canonical_visit_id END)/NULLIF(COUNT(DISTINCT CASE WHEN v.eligible_for_traffic_metrics=1 THEN v.canonical_visit_id END),0),6) value,
                   COUNT(DISTINCT v.canonical_visit_id)-COUNT(DISTINCT CASE WHEN v.eligible_for_traffic_metrics=1 THEN v.canonical_visit_id END) suspected_bot_excluded_denominator
            FROM visits v LEFT JOIN checkout_visits c USING(canonical_visit_id)
            GROUP BY 1 ORDER BY 1
        """
        return self._query(sql, [start, end, *values, start, end])

    def _gross_revenue(self, start, end, group_by, filters):
        segment = ORDER_DIMENSIONS[group_by] if group_by else "'all'"
        clauses, values = self._filters(ORDER_DIMENSIONS, filters)
        where = " AND ".join([
            "date(o.order_ts) BETWEEN ? AND ?", "o.payment_status='paid'",
            "o.eligible_for_commercial_metrics=1", *clauses,
        ])
        sql = f"""
            SELECT {segment} segment,ROUND(SUM(o.gross_order_revenue),2) value,
                   COUNT(*) eligible_order_count,SUM(o.is_employee_order) employee_order_count,
                   ROUND(SUM(CASE WHEN o.is_employee_order=1 THEN o.gross_order_revenue ELSE 0 END),2) employee_order_revenue
            FROM trusted_orders o LEFT JOIN trusted_sessions s USING(session_id)
            WHERE {where} GROUP BY 1 ORDER BY 1
        """
        return self._query(sql, [start, end, *values])

    def _net_revenue(self, start, end, group_by, filters, as_of):
        segment = ORDER_DIMENSIONS[group_by] if group_by else "'all'"
        clauses, values = self._filters(ORDER_DIMENSIONS, filters)
        where = " AND ".join([
            "date(o.order_ts) BETWEEN ? AND ?", "o.payment_status='paid'",
            "o.eligible_for_commercial_metrics=1", *clauses,
        ])
        sql = f"""
            WITH refund_as_of AS (
              SELECT order_id,SUM(CAST(refund_amount AS REAL)) refund_amount
              FROM trusted_refunds
              WHERE within_refund_window=1 AND datetime(requested_at)<=datetime(?)
              GROUP BY order_id
            )
            SELECT {segment} segment,
                   ROUND(SUM(CASE WHEN datetime(o.refund_window_end)<=datetime(?)
                                  THEN o.gross_order_revenue-COALESCE(r.refund_amount,0) END),2) value,
                   SUM(CASE WHEN datetime(o.refund_window_end)<=datetime(?) THEN 1 ELSE 0 END) mature_order_count,
                   SUM(CASE WHEN datetime(o.refund_window_end)>datetime(?) THEN 1 ELSE 0 END) immature_order_count,
                   ROUND(SUM(CASE WHEN datetime(o.refund_window_end)>datetime(?)
                                  THEN o.gross_order_revenue ELSE 0 END),2) immature_revenue
            FROM trusted_orders o LEFT JOIN trusted_sessions s USING(session_id)
            LEFT JOIN refund_as_of r USING(order_id)
            WHERE {where} GROUP BY 1 ORDER BY 1
        """
        return self._query(sql, [as_of, as_of, as_of, as_of, as_of, start, end, *values])

    def _query(self, sql, params):
        con = self._connect()
        try:
            rows = [dict(row) for row in con.execute(sql, params)]
        finally:
            con.close()
        return rows, {"sql": "\n".join(line.rstrip() for line in sql.strip().splitlines()), "parameters": list(params)}

    @staticmethod
    def _response(metric, spec, start, end, group_by, filters, as_of, rows, health, limitations, query):
        return {
            "metric": metric,
            "label": spec.label,
            "definition": spec.definition,
            "time_range": {"start_date": start, "end_date": end},
            "group_by": group_by,
            "filters": filters or {},
            "report_as_of_ts": as_of,
            "result": rows,
            "quality_status": health["status"],
            "quality_issues": health["issues"],
            "sources": list(spec.sources),
            "limitations": limitations,
            "executed_query": query,
            "query_policy": "read_only_parameterized_whitelist",
        }
