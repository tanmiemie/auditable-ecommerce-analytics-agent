from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analytics_agent.agent import AnalyticsAgent
from analytics_agent.governed_tools import GovernedAnalyticsTools
from analytics_agent.trusted_layer import build


def get_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def evaluate_check(output: Any, check: dict[str, Any]) -> tuple[bool, str]:
    try:
        actual = get_path(output, check["path"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return False, f"missing path {check['path']}: {exc}"
    op, expected = check["op"], check["expected"]
    if op == "equals":
        passed = actual == expected
    elif op == "approx":
        passed = abs(actual - expected) <= check.get("tolerance", 1e-6)
    elif op == "contains":
        passed = expected in actual
    elif op == "length":
        passed = len(actual) == expected
    else:
        return False, f"unsupported operation {op}"
    return passed, f"{check['path']} {op} {expected!r}; actual={actual!r}"


def run_suite(cases_path: Path, db: Path) -> dict[str, Any]:
    cases = json.loads(cases_path.read_text())
    agent = AnalyticsAgent(db)
    tools = GovernedAnalyticsTools(db)
    results = []

    for case in cases:
        error = None
        output = None
        try:
            if case["target"] == "agent_answer":
                output = agent.answer(**case["input"])
            elif case["target"] == "health_check":
                output = tools.health_check(**case["input"])
            else:
                raise ValueError(f"Unsupported target {case['target']}")
        except Exception as exc:  # evaluator records application errors as evidence
            error = f"{type(exc).__name__}: {exc}"

        checks = []
        if "expected_error" in case:
            passed = error is not None and case["expected_error"] in error
            checks.append({"passed": passed, "detail": f"expected error containing {case['expected_error']!r}; actual={error!r}"})
        elif error:
            checks.append({"passed": False, "detail": f"unexpected application error: {error}"})
        else:
            for check in case["checks"]:
                passed, detail = evaluate_check(output, check)
                checks.append({"passed": passed, "detail": detail})

        results.append({
            "id": case["id"],
            "name": case["name"],
            "passed": all(check["passed"] for check in checks),
            "checks": checks,
            "error": error,
        })

    passed = sum(result["passed"] for result in results)
    return {
        "suite": "ecommerce_analytics_agent_pilot_v1",
        "cases": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
        "claim_boundary": "Golden regression behavior for this synthetic dataset; not a production accuracy estimate.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=ROOT / "evals" / "golden_cases.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temp_dir:
        db = Path(temp_dir) / "trusted.sqlite"
        build(out_db=db)
        report = run_suite(args.cases, db)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)
    raise SystemExit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
