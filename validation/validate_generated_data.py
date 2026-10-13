#!/usr/bin/env python3
"""High-signal validation checks for the generated v1 dataset."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "ecommerce_raw.sqlite"


CHECKS = {
    "BOT-01 scraper sessions exist": """
        SELECT COUNT(*) FROM sessions
        WHERE session_start >= '2026-01-10' AND session_start < '2026-01-13'
          AND user_agent LIKE '%PriceMonitor%'
    """,
    "VIS-01 exact duplicate event IDs exist": """
        SELECT COUNT(*) FROM (
          SELECT event_id FROM events GROUP BY event_id HAVING COUNT(*) > 1
        )
    """,
    "VIS-02 split-session version exists": """
        SELECT COUNT(*) FROM sessions WHERE sessionization_version = 'v2_5min'
    """,
    "FRAUD-01 shared payment-token orders exist": """
        SELECT COUNT(*) FROM orders WHERE payment_token_hash = 'SHARED_TOKEN_VELOCITY'
    """,
    "TRK-01 iOS orders remain during checkout outage": """
        SELECT COUNT(*) FROM orders o JOIN sessions s ON o.session_id = s.session_id
        WHERE o.order_ts >= '2026-03-15' AND o.order_ts < '2026-03-19'
          AND s.platform = 'ios' AND s.app_version = '6.1.0'
    """,
    "TRK-02 renamed cart events exist": """
        SELECT COUNT(*) FROM events
        WHERE event_name_raw = 'cart_add' AND platform = 'android' AND app_version = '6.2.0'
    """,
    "FRAUD-02 WELCOME20 abuse orders exist": """
        SELECT COUNT(*) FROM orders WHERE coupon_code = 'WELCOME20' AND is_confirmed_fraud = '1'
    """,
    "TRK-03 missing experiment property exists": """
        SELECT COUNT(*) FROM events
        WHERE event_ts >= '2026-04-10' AND event_ts < '2026-04-14'
          AND platform = 'ios' AND app_version = '6.2.1'
          AND event_name_raw = 'add_to_cart' AND experiment_id = ''
    """,
    "experiment exposures without assignment exist": """
        SELECT COUNT(*) FROM experiment_exposures e
        LEFT JOIN experiment_assignments a
          ON e.experiment_id = a.experiment_id AND e.user_id = a.user_id
        WHERE a.user_id IS NULL
    """,
}


SIGNAL_CHECKS = [
    {
        "check": "BOT-01 affected dates have elevated web sessions",
        "query": """
          SELECT
            (SELECT COUNT(*) / 3.0 FROM sessions WHERE session_start >= '2026-01-10' AND session_start < '2026-01-13' AND platform='web') /
            (SELECT COUNT(*) / 6.0 FROM sessions WHERE session_start >= '2026-01-04' AND session_start < '2026-01-10' AND platform='web')
        """,
        "operator": ">", "threshold": 1.25,
    },
    {
        "check": "VIS-01 Android 5.4.0 has material duplicate rate",
        "query": """
          SELECT 1.0 * SUM(CASE WHEN n > 1 THEN n - 1 ELSE 0 END) / SUM(n)
          FROM (SELECT event_id, COUNT(*) n FROM events WHERE platform='android' AND app_version='5.4.0' GROUP BY event_id)
        """,
        "operator": ">", "threshold": 0.05,
    },
    {
        "check": "TRK-01 iOS checkout-to-purchase telemetry ratio collapses",
        "query": """
          SELECT
            (SELECT 1.0 * COUNT(*) FROM events WHERE event_ts >= '2026-03-15' AND event_ts < '2026-03-19' AND platform='ios' AND event_name_raw='begin_checkout') /
            (SELECT COUNT(*) FROM events WHERE event_ts >= '2026-03-15' AND event_ts < '2026-03-19' AND platform='ios' AND event_name_raw='purchase')
        """,
        "operator": "<", "threshold": 0.25,
    },
    {
        "check": "TRK-02 renamed cart event dominates Android 6.2.0",
        "query": """
          SELECT 1.0 * SUM(CASE WHEN event_name_raw='cart_add' THEN 1 ELSE 0 END) /
                       SUM(CASE WHEN event_name_raw IN ('cart_add','add_to_cart') THEN 1 ELSE 0 END)
          FROM events WHERE platform='android' AND app_version='6.2.0'
        """,
        "operator": ">", "threshold": 0.90,
    },
    {
        "check": "TRK-03 experiment-property missing rate is material",
        "query": """
          SELECT 1.0 * SUM(CASE WHEN experiment_id='' THEN 1 ELSE 0 END) / COUNT(*)
          FROM events WHERE event_ts >= '2026-04-10' AND event_ts < '2026-04-14'
            AND platform='ios' AND app_version='6.2.1' AND event_name_raw='add_to_cart'
        """,
        "operator": ">", "threshold": 0.90,
    },
    {
        "check": "BIZ-01 campaign traffic has explicit campaign evidence",
        "query": """
          SELECT 1.0 * SUM(CASE WHEN campaign_id='CAMP_SOCIAL_JAN' THEN 1 ELSE 0 END) / COUNT(*)
          FROM sessions WHERE session_start >= '2026-01-20' AND session_start < '2026-01-27'
        """,
        "operator": ">", "threshold": 0.40,
    },
    {
        "check": "BIZ-02 promotion produces legitimate SPRING20 orders",
        "query": """
          SELECT COUNT(*) FROM orders
          WHERE order_ts >= '2026-03-05' AND order_ts < '2026-03-11'
            AND coupon_code='SPRING20' AND is_confirmed_fraud='0'
        """,
        "operator": ">", "threshold": 50,
    },
]


def main():
    if not DB.exists():
        raise SystemExit(f"Missing database: {DB}. Run generator/generate_data.py first.")
    conn = sqlite3.connect(DB)
    results = []
    failed = False
    try:
        for name, query in CHECKS.items():
            count = conn.execute(query).fetchone()[0]
            passed = count > 0
            failed |= not passed
            results.append({"check": name, "passed": passed, "evidence_count": count})
        for item in SIGNAL_CHECKS:
            value = conn.execute(item["query"]).fetchone()[0]
            passed = value is not None and (
                value > item["threshold"] if item["operator"] == ">" else value < item["threshold"]
            )
            failed |= not passed
            results.append({
                "check": item["check"], "passed": passed,
                "observed_value": None if value is None else round(value, 4),
                "expectation": f'{item["operator"]} {item["threshold"]}',
            })
    finally:
        conn.close()
    print(json.dumps(results, indent=2))
    if failed:
        raise SystemExit("One or more generated-data checks failed")


if __name__ == "__main__":
    main()

