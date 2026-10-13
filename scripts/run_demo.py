from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analytics_agent.agent import AnalyticsAgent
from analytics_agent.trusted_layer import TRUSTED_DB, build


QUESTIONS = [
    "Why did Web visits increase in January?",
    "Compare March visitor conversion by country",
    "As of 2026-05-11, how did March net revenue compare with February?",
    "Is iOS checkout tracking available from 2026-03-15 to 2026-03-18?",
    "How many visits occurred in 2025?",
]


def main() -> None:
    build(out_db=TRUSTED_DB)
    agent = AnalyticsAgent(TRUSTED_DB)
    outputs = []
    for question in QUESTIONS:
        answer = agent.answer(question)
        outputs.append({
            "question": question,
            "answer_status": answer["answer_status"],
            "metric": answer["request"]["metric"],
            "quality_status": answer["quality_status"],
            "headline": answer["presentation"]["headline_result"],
            "data_quality_flags": answer["presentation"]["data_quality_flags"],
            "policy_flags": answer["presentation"]["policy_flags"],
            "investigation": answer["investigation"],
            "limitations": answer["limitations"],
            "executed_queries": answer["executed_queries"],
            "trace": answer["trace"],
        })
    print(json.dumps(outputs, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
