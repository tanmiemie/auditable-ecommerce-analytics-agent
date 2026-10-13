import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from analytics_agent.trusted_layer import build
from evals.run_evals import run_suite


class EvaluationSuiteTests(unittest.TestCase):
    def test_pilot_suite_passes_after_fraud_policy_repair(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Path(temp_dir) / "trusted.sqlite"
            build(out_db=db)
            report = run_suite(ROOT / "evals" / "golden_cases.json", db)
        self.assertEqual(report["cases"], 8)
        self.assertEqual(report["passed"], 8)
        self.assertEqual(report["failed"], 0)
        failed = [result["id"] for result in report["results"] if not result["passed"]]
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
