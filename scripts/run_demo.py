from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analytics_agent.agent import AnalyticsAgent
from analytics_agent.trusted_layer import TRUSTED_DB, build


QUESTIONS = [
    "1月 Web visits 为什么上涨？",
    "按国家比较3月访客转化率",
    "截至2026-05-11，3月净收入与2月相比如何？",
    "2026-03-15 to 2026-03-18 iOS checkout tracking 数据可以用吗？",
    "2025年 visits 是多少？",
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
