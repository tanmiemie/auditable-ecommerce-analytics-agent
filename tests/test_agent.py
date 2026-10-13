import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analytics_agent.agent import AnalyticsAgent, parse_question
from analytics_agent.trusted_layer import build


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db = Path(cls.temp_dir.name) / "trusted.sqlite"
        build(out_db=cls.db)
        cls.agent = AnalyticsAgent(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_requires_metric_and_time(self):
        with self.assertRaises(ValueError):
            parse_question("How are we doing?")

    def test_ambiguous_conversion_requires_denominator(self):
        with self.assertRaisesRegex(ValueError, "denominator"):
            parse_question("Compare March purchase conversion rate by country")

    def test_net_revenue_requires_as_of(self):
        with self.assertRaisesRegex(ValueError, "as-of"):
            parse_question("How did March net revenue compare with February?")

    def test_net_revenue_comparison_is_governed(self):
        result = self.agent.answer("As of 2026-05-11, how did March net revenue compare with February?")
        self.assertEqual(result["request"]["metric"], "net_revenue")
        self.assertTrue(result["result"])
        self.assertTrue(result["comparison"])
        self.assertTrue(result["comparison_summary"])
        self.assertIsNotNone(result["result"][0]["value"])
        self.assertGreater(result["result"][0]["mature_order_count"], 0)
        self.assertEqual(result["request"]["report_as_of_ts"], "2026-05-11T23:59:59Z")
        self.assertEqual(result["query_policy"], "read_only_parameterized_whitelist")
        self.assertIn("trusted_orders", result["executed_queries"]["current"]["sql"])
        self.assertIn("2026-05-11T23:59:59Z", result["executed_queries"]["current"]["parameters"])

    def test_january_visits_investigation_surfaces_bot_adjustment(self):
        result = self.agent.answer("Why did Web visits increase in January?")
        self.assertEqual(result["quality_status"], "adjusted")
        self.assertEqual(result["investigation"]["classification"], "data_quality_adjustment")
        self.assertTrue(result["investigation"]["evidence"]["raw_vs_filtered"])
        self.assertEqual(result["presentation"]["headline_result"], [{"segment": "all", "value": 5423}])
        flag = result["presentation"]["data_quality_flags"][0]
        self.assertEqual((flag["start_date"], flag["end_date"]), ("2026-01-10", "2026-01-12"))
        self.assertEqual(flag["treatment"], "blocked_and_excluded_from_headline")
        self.assertEqual(flag["blocked_or_adjusted_value"], 375)

    def test_both_conversion_denominators_are_supported(self):
        visitor = self.agent.answer("Compare March visitor conversion by country")
        visit = self.agent.answer("Compare March visit conversion by country")
        self.assertEqual(visitor["request"]["metric"], "visitor_purchase_conversion_rate")
        self.assertEqual(visit["request"]["metric"], "visit_purchase_conversion_rate")
        self.assertNotEqual(visitor["result"][0]["value"], visit["result"][0]["value"])

    def test_trace_contains_only_governed_workflow_steps(self):
        result = self.agent.answer("March gross revenue by shipping country")
        self.assertEqual(
            [step["step"] for step in result["trace"]],
            ["validate_and_parse", "metric_lookup", "fraud_evidence"],
        )
        self.assertEqual({row["segment"] for row in result["result"]}, {"CA", "GB", "US"})

    def test_revenue_country_uses_shipping_country(self):
        result = self.agent.answer("March gross revenue by country")
        self.assertEqual(result["request"]["dimension"], "shipping_country")
        self.assertEqual({row["segment"] for row in result["result"]}, {"CA", "GB", "US"})

    def test_explicit_range_does_not_use_as_of_as_start_date(self):
        request = parse_question("as of 2026-05-11, net revenue from 2026-03-01 to 2026-03-31")
        self.assertEqual((request.start_date, request.end_date), ("2026-03-01", "2026-03-31"))

    def test_fraud_investigation_keeps_policy_boundary(self):
        result = self.agent.answer("Why did Web gross revenue change from 2026-02-25 to 2026-02-26?")
        self.assertEqual(result["investigation"]["classification"], "security_review_candidate")
        self.assertIn("Risk review", result["investigation"]["recommended_action"])
        flag = result["presentation"]["policy_flags"][0]
        self.assertEqual(flag["confirmed_excluded_order_count"], 40)
        self.assertEqual(flag["suspected_included_order_count"], 0)

    def test_out_of_coverage_question_abstains(self):
        result = self.agent.answer("How many visits occurred in 2025?")
        self.assertEqual(result["answer_status"], "abstained")
        self.assertEqual(result["quality_status"], "unavailable")
        self.assertEqual(result["result"], [])
        self.assertIn("beyond available data coverage", result["quality_issues"][0]["reason"])

    def test_checkout_tracking_outage_is_user_visible(self):
        result = self.agent.answer("Is iOS checkout tracking available from 2026-03-15 to 2026-03-18?")
        self.assertEqual(result["answer_status"], "abstained")
        self.assertEqual(result["quality_status"], "unavailable")
        self.assertEqual(result["result"], [])
        flag = result["presentation"]["data_quality_flags"][0]
        self.assertEqual((flag["start_date"], flag["end_date"]), ("2026-03-15", "2026-03-18"))
        self.assertEqual(flag["treatment"], "authoritative_answer_blocked")


if __name__ == "__main__":
    unittest.main()
