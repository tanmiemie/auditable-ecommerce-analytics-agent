import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analytics_agent.governed_tools import GovernedAnalyticsTools
from analytics_agent.trusted_layer import build


class GovernedToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db = Path(cls.temp_dir.name) / "trusted.sqlite"
        build(out_db=cls.db)
        cls.tools = GovernedAnalyticsTools(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_capabilities_are_limited_to_approved_metrics(self):
        self.assertEqual(
            set(self.tools.list_capabilities()),
            {"visits", "visitor_purchase_conversion_rate", "visit_purchase_conversion_rate", "checkout_start_rate", "gross_revenue", "net_revenue"},
        )

    def test_rejects_unsupported_metric_and_dimension(self):
        with self.assertRaises(ValueError):
            self.tools.metric_lookup("arbitrary_sql", "2026-01-01", "2026-01-31")
        with self.assertRaises(ValueError):
            self.tools.metric_lookup("visits", "2026-01-01", "2026-01-31", group_by="payment_token_hash")

    def test_visits_exposes_raw_and_filtered_values(self):
        result = self.tools.metric_lookup("visits", "2026-01-01", "2026-01-31")
        row = result["result"][0]
        self.assertGreater(row["raw_value"], row["value"])
        self.assertGreater(row["suspected_bot_excluded_value"], 0)
        self.assertEqual(result["query_policy"], "read_only_parameterized_whitelist")
        self.assertIn("canonical_visits", result["executed_query"]["sql"])
        self.assertEqual(result["executed_query"]["parameters"][:2], ["2026-01-01", "2026-01-31"])

    def test_conversion_metrics_are_distinct(self):
        visitor = self.tools.metric_lookup("visitor_purchase_conversion_rate", "2026-03-01", "2026-03-31")
        visit = self.tools.metric_lookup("visit_purchase_conversion_rate", "2026-03-01", "2026-03-31")
        self.assertNotEqual(visitor["result"][0]["value"], visit["result"][0]["value"])

    def test_net_revenue_requires_as_of_and_discloses_immature_revenue(self):
        with self.assertRaises(ValueError):
            self.tools.metric_lookup("net_revenue", "2026-04-01", "2026-04-30")
        result = self.tools.metric_lookup(
            "net_revenue", "2026-04-01", "2026-04-30",
            report_as_of_ts="2026-05-11T08:36:30Z",
        )
        self.assertGreater(result["result"][0]["immature_order_count"], 0)
        self.assertGreater(result["result"][0]["immature_revenue"], 0)

    def test_segment_filter_is_parameterized_and_scoped(self):
        result = self.tools.segment_comparison(
            "gross_revenue", "2026-03-01", "2026-03-31", "shipping_country",
            filters={"is_employee_order": 0},
        )
        self.assertEqual({row["segment"] for row in result["result"]}, {"CA", "GB", "US"})

    def test_unavailable_health_blocks_authoritative_result(self):
        health = self.tools.health_check("checkout_start_rate", "2026-03-15", "2026-03-18")
        self.assertEqual(health["status"], "unavailable")
        self.assertEqual(len(health["issues"]), 1)
        self.assertEqual(health["issues"][0]["app_version"], "6.1.0")

        result = self.tools.metric_lookup("checkout_start_rate", "2026-03-15", "2026-03-18", filters={"platform": "ios"})
        self.assertEqual(result["quality_status"], "unavailable")
        self.assertEqual(result["result"], [])

    def test_context_retrieval_returns_campaigns_and_releases(self):
        context = self.tools.context_retrieval("2026-03-01", "2026-03-31")
        self.assertTrue(context["campaigns"])
        self.assertTrue(context["app_releases"])
        self.assertIn("not proof", context["causality_guardrail"])

    def test_out_of_coverage_period_is_unavailable(self):
        result = self.tools.metric_lookup("visits", "2025-01-01", "2025-12-31")
        self.assertEqual(result["quality_status"], "unavailable")
        self.assertEqual(result["result"], [])
        self.assertEqual(result["quality_issues"][0]["available_start_date"], "2026-01-01")
        self.assertEqual(result["quality_issues"][0]["available_end_date"], "2026-04-30")

    def test_fraud_evidence_separates_confirmed_from_suspected_policy(self):
        result = self.tools.fraud_evidence("2026-02-25", "2026-02-26", "web")
        self.assertEqual(result["summary"]["confirmed_excluded_order_count"], 40)
        self.assertEqual(result["summary"]["suspected_included_order_count"], 0)
        self.assertIn("included", result["policy"]["suspected_unconfirmed"])
        self.assertIn("fraud_signal_audit", result["executed_query"]["sql"])

    def test_unconfirmed_signaled_order_remains_included_and_flagged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Path(temp_dir) / "trusted.sqlite"
            build(out_db=db)
            con = sqlite3.connect(db)
            try:
                con.execute(
                    """INSERT INTO trusted_orders(
                         order_id,order_ts,gross_order_revenue,is_confirmed_fraud,
                         payment_token_hash,eligible_for_commercial_metrics,payment_status
                       ) VALUES(?,?,?,?,?,?,?)""",
                    ("TEST_SUSPECTED", "2026-02-25T12:00:00Z", 50.0, "0",
                     "SHARED_TOKEN_VELOCITY", 1, "paid"),
                )
                con.commit()
            finally:
                con.close()
            tools = GovernedAnalyticsTools(db)
            evidence = tools.fraud_evidence("2026-02-25", "2026-02-26")
            metric = tools.metric_lookup("gross_revenue", "2026-02-25", "2026-02-26")
        self.assertEqual(evidence["summary"]["suspected_included_order_count"], 1)
        self.assertEqual(evidence["summary"]["suspected_included_gross_revenue"], 50.0)
        self.assertEqual(metric["result"][0]["eligible_order_count"], 87)


if __name__ == "__main__":
    unittest.main()
