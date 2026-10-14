import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analytics_agent.ui_helpers import chart_rows, format_delta, format_metric_value, quality_label


class UIHelperTests(unittest.TestCase):
    def test_metric_formatting(self):
        self.assertEqual(format_metric_value("visits", 5423), "5,423")
        self.assertEqual(format_metric_value("visitor_purchase_conversion_rate", 0.151737), "15.17%")
        self.assertEqual(format_metric_value("net_revenue", 188654.1), "$188,654.10")
        self.assertEqual(format_metric_value("visits", None), "Unavailable")

    def test_delta_formatting(self):
        row = {"absolute_change": 19434.65, "percent_change": 0.114849}
        self.assertEqual(format_delta("net_revenue", row), "+$19,434.65 (+11.5%)")

    def test_chart_rows_include_comparison(self):
        answer = {
            "request": {"metric": "visits"},
            "result": [{"segment": "web", "value": 120}],
            "comparison_summary": [{"segment": "web", "comparison": 100}],
        }
        self.assertEqual(
            chart_rows(answer),
            [{"segment": "web", "current": 120, "metric": "visits", "comparison": 100}],
        )

    def test_quality_labels(self):
        self.assertEqual(quality_label("trusted"), "Trusted")
        self.assertEqual(quality_label("unavailable"), "Unavailable")


if __name__ == "__main__":
    unittest.main()
