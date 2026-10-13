import sqlite3
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analytics_agent.trusted_layer import RAW_DB, build


class TrustedLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "trusted.sqlite"
        build(out_db=cls.db_path)
        cls.con = sqlite3.connect(cls.db_path)
        cls.con.execute("ATTACH DATABASE ? AS raw", (str(RAW_DB),))

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.temp_dir.cleanup()

    def scalar(self, sql):
        return self.con.execute(sql).fetchone()[0]

    def test_events_are_deduplicated_deterministically(self):
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM trusted_events"), 320090)
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM trusted_events"),
            self.scalar("SELECT COUNT(DISTINCT event_id) FROM trusted_events"),
        )
        self.assertEqual(
            self.scalar("SELECT SUM(removed_row_count) FROM event_dedup_audit"), 896
        )
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM event_dedup_audit WHERE content_conflict=1"),
            0,
        )

    def test_conflicting_duplicate_retains_earliest_and_is_flagged(self):
        raw_copy = Path(self.temp_dir.name) / "raw_with_conflict.sqlite"
        trusted_copy = Path(self.temp_dir.name) / "trusted_with_conflict.sqlite"
        shutil.copy2(RAW_DB, raw_copy)

        fixture = sqlite3.connect(raw_copy)
        try:
            cursor = fixture.execute("SELECT * FROM events ORDER BY rowid LIMIT 1")
            columns = [item[0] for item in cursor.description]
            original = list(cursor.fetchone())
            event_id = original[columns.index("event_id")]
            original_event_name = original[columns.index("event_name_raw")]
            original[columns.index("event_name_raw")] = "conflicting_test_event"
            original[columns.index("ingested_at")] = "2099-01-01T00:00:00Z"
            placeholders = ",".join("?" for _ in columns)
            fixture.execute(
                f"INSERT INTO events ({','.join(columns)}) VALUES ({placeholders})",
                original,
            )
            fixture.commit()
        finally:
            fixture.close()

        build(raw_db=raw_copy, out_db=trusted_copy)
        result = sqlite3.connect(trusted_copy)
        try:
            retained_name = result.execute(
                "SELECT event_name_raw FROM trusted_events WHERE event_id=?", (event_id,)
            ).fetchone()[0]
            conflict = result.execute(
                "SELECT content_conflict FROM event_dedup_audit WHERE event_id=?",
                (event_id,),
            ).fetchone()[0]
        finally:
            result.close()

        self.assertEqual(retained_name, original_event_name)
        self.assertEqual(conflict, 1)

    def test_canonical_visits_obey_thirty_minute_rule(self):
        violations = self.scalar(
            """
            WITH gaps AS (
              SELECT canonical_visit_id,event_ts,
                     LAG(strftime('%s',event_ts)) OVER (
                       PARTITION BY canonical_visit_id ORDER BY event_ts,event_id
                     ) previous_epoch
              FROM trusted_events
            )
            SELECT COUNT(*) FROM gaps
            WHERE previous_epoch IS NOT NULL
              AND strftime('%s',event_ts)-previous_epoch>1800
            """
        )
        self.assertEqual(violations, 0)
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM canonical_visits"),
            self.scalar("SELECT COUNT(DISTINCT canonical_visit_id) FROM canonical_visits"),
        )

    def test_platform_specific_identity_stitching(self):
        app_violations = self.scalar(
            """
            SELECT COUNT(*)
            FROM trusted_events e
            JOIN trusted_identity_map i USING(anonymous_id)
            JOIN raw.sessions s USING(session_id)
            WHERE e.platform IN ('ios','android') AND i.identity_eligible=1
              AND NULLIF(e.user_id,'') IS NULL AND NULLIF(s.user_id,'') IS NULL
              AND e.canonical_visitor_id<>i.user_id
            """
        )
        web_violations = self.scalar(
            """
            SELECT COUNT(*)
            FROM trusted_events e
            JOIN trusted_identity_map i USING(anonymous_id)
            JOIN raw.sessions s USING(session_id)
            WHERE e.platform='web' AND i.identity_eligible=1
              AND NULLIF(e.user_id,'') IS NULL AND NULLIF(s.user_id,'') IS NULL
              AND ((e.event_ts<i.effective_from AND e.canonical_visitor_id<>e.anonymous_id)
                OR (e.event_ts>=i.effective_from AND e.canonical_visitor_id<>i.user_id))
            """
        )
        self.assertEqual(app_violations, 0)
        self.assertEqual(web_violations, 0)

    def test_bot_filter_is_auditable(self):
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM canonical_visits "
                "WHERE bot_rule_version IS NULL OR bot_reason IS NULL"
            ),
            0,
        )
        self.assertGreater(
            self.scalar("SELECT COUNT(*) FROM canonical_visits WHERE suspected_bot=1"), 0
        )

    def test_order_eligibility_matches_approved_policy(self):
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM trusted_orders "
                "WHERE is_confirmed_fraud='1' AND eligible_for_commercial_metrics<>0"
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM trusted_orders "
                "WHERE is_employee_order=1 AND eligible_for_commercial_metrics<>1"
            ),
            0,
        )
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM trusted_orders WHERE is_employee_order=1"), 4
        )

    def test_refunds_use_request_time_and_thirty_day_window(self):
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM trusted_refunds WHERE within_refund_window=0"),
            0,
        )
        self.assertAlmostEqual(
            self.scalar("SELECT SUM(requested_refund_amount) FROM trusted_orders"),
            self.scalar("SELECT SUM(CAST(refund_amount AS REAL)) FROM raw.refunds"),
            places=2,
        )
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM trusted_orders "
                "WHERE refund_window_end<>datetime(order_ts,'+30 days')"
            ),
            0,
        )

    def test_order_snapshots_resolve_without_fanout(self):
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM trusted_order_current_status"), 5508
        )
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM trusted_order_current_status "
                "WHERE current_status<>'completed' OR snapshot_amount_valid<>1"
            ),
            0,
        )
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM trusted_orders"), 5593)

    def test_tracking_outage_is_marked_unavailable(self):
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM tracking_health_daily "
                "WHERE platform='ios' AND app_version='6.1.0' "
                "AND metric_date BETWEEN '2026-03-15' AND '2026-03-18' "
                "AND checkout_metric_status='unavailable'"
            ),
            4,
        )

    def test_experiment_property_failure_is_marked_unavailable(self):
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM experiment_instrumentation_health "
                "WHERE platform='ios' AND app_version='6.2.1' "
                "AND metric_date BETWEEN '2026-04-10' AND '2026-04-13' "
                "AND experiment_metric_status='unavailable'"
            ),
            4,
        )

    def test_latest_fraud_labels_are_disclosed_as_restatements(self):
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM trusted_orders "
                "WHERE is_confirmed_fraud='1' "
                "AND fraud_as_of_status='restated_with_latest_fraud_label_timestamp_unavailable'"
            ),
            85,
        )

    def test_contract_checks_surface_known_exposure_orphans_only(self):
        violations = dict(
            self.con.execute(
                "SELECT check_name,violation_count FROM contract_check_results "
                "WHERE violation_count<>0"
            ).fetchall()
        )
        self.assertEqual(violations, {"experiment_exposure_without_assignment": 10})

    def test_normal_business_changes_are_preserved(self):
        campaign_visits = self.scalar(
            "SELECT COUNT(*) FROM canonical_visits "
            "WHERE campaign_id='CAMP_SOCIAL_JAN' AND eligible_for_traffic_metrics=1"
        )
        promotion_orders = self.scalar(
            "SELECT COUNT(*) FROM trusted_orders "
            "WHERE coupon_code='SPRING20' AND eligible_for_commercial_metrics=1"
        )
        android_redesign_events = self.scalar(
            "SELECT COUNT(*) FROM trusted_events "
            "WHERE platform='android' AND app_version='6.3.0' AND suspected_bot=0"
        )
        self.assertGreater(campaign_visits, 0)
        self.assertGreater(promotion_orders, 50)
        self.assertGreater(android_redesign_events, 0)


if __name__ == "__main__":
    unittest.main()
