from __future__ import annotations

import calendar
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .governed_tools import GovernedAnalyticsTools
from .trusted_layer import TRUSTED_DB


METRIC_ALIASES = (
    ("visitor_purchase_conversion_rate", ("visitor conversion", "visitor-level conversion", "访客转化率", "用户转化率")),
    ("visit_purchase_conversion_rate", ("visit conversion", "visit-level conversion", "访问转化率", "session conversion")),
    ("checkout_start_rate", ("checkout start rate", "checkout rate", "结账开始率", "checkout tracking")),
    ("gross_revenue", ("gross revenue", "毛收入")),
    ("net_revenue", ("net revenue", "净收入")),
    ("visits", ("visits", "visit count", "访问量", "访问次数", "流量")),
)
AMBIGUOUS_CONVERSION = ("purchase conversion", "conversion rate", "购买转化率", "转化率")
DIMENSION_ALIASES = {
    "platform": ("platform", "平台"),
    "app_version": ("app version", "app_version", "版本"),
    "channel": ("channel", "渠道"),
    "country": ("country", "国家"),
    "shipping_country": ("shipping country", "收货国家"),
    "campaign_id": ("campaign", "活动"),
    "is_employee_order": ("employee", "员工"),
    "date": ("daily", "by day", "每天", "按日", "日期"),
}
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "1月": 1, "2月": 2, "3月": 3, "4月": 4,
}
PLATFORMS = {"web": "web", "ios": "ios", "android": "android"}


@dataclass(frozen=True)
class Request:
    intent: str
    metric: str
    start_date: str
    end_date: str
    dimension: str | None = None
    filters: dict[str, Any] | None = None
    compare_start: str | None = None
    compare_end: str | None = None
    report_as_of_ts: str | None = None


def _month_window(year: int, month: int) -> tuple[str, str]:
    last = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last:02d}"


def _extract_months(q: str) -> list[int]:
    matches = sorted((q.find(word), number) for word, number in MONTHS.items() if word in q)
    return list(dict.fromkeys(number for _, number in matches))


def _extract_as_of(q: str) -> str | None:
    iso = re.search(r"(?:as of|截至)\s*((?:19|20)\d{2}-\d{2}-\d{2})(?:[t\s](\d{2}:\d{2}(?::\d{2})?z?))?", q)
    if iso:
        time_part = iso.group(2) or "23:59:59Z"
        if len(time_part) == 5:
            time_part += ":00"
        if not time_part.lower().endswith("z"):
            time_part += "Z"
        return f"{iso.group(1)}T{time_part.upper()}"
    zh = re.search(r"截至\s*(\d{1,2})月(\d{1,2})日", q)
    if zh:
        return f"2026-{int(zh.group(1)):02d}-{int(zh.group(2)):02d}T23:59:59Z"
    return None


def parse_question(question: str) -> Request:
    q = question.lower().strip()
    metric = next((name for name, aliases in METRIC_ALIASES if any(alias in q for alias in aliases)), None)
    if metric is None and any(alias in q for alias in AMBIGUOUS_CONVERSION):
        raise ValueError("Conversion denominator is ambiguous. Specify visitor conversion or visit conversion.")
    if metric is None:
        raise ValueError("Specify one supported metric: visits, visitor/visit conversion, gross revenue, or net revenue.")

    as_of = _extract_as_of(q)
    months = _extract_months(q)
    years = [int(year) for year in re.findall(r"(?:19|20)\d{2}", q)]
    report_year = years[-1] if years else 2026
    explicit_dates = re.findall(r"(?:19|20)\d{2}-\d{2}-\d{2}", q)
    if as_of and as_of[:10] in explicit_dates:
        explicit_dates.remove(as_of[:10])
    if len(explicit_dates) >= 2:
        start, end = explicit_dates[0], explicit_dates[1]
    elif months:
        start, end = _month_window(report_year, months[0])
    elif years:
        start, end = f"{report_year}-01-01", f"{report_year}-12-31"
    else:
        raise ValueError("Specify a reporting period in January-April 2026.")

    compare_start = compare_end = None
    if len(months) > 1:
        compare_start, compare_end = _month_window(report_year, months[1])

    dimension_matches = [
        (len(alias), name)
        for name, aliases in DIMENSION_ALIASES.items()
        for alias in aliases
        if alias in q
    ]
    dimension = max(dimension_matches)[1] if dimension_matches else None
    if metric in {"gross_revenue", "net_revenue"} and dimension == "country":
        dimension = "shipping_country"
    elif metric not in {"gross_revenue", "net_revenue"} and dimension == "shipping_country":
        dimension = "country"
    filters: dict[str, Any] = {}
    for token, canonical in PLATFORMS.items():
        if re.search(rf"\b{token}\b", q):
            filters["platform"] = canonical
            break

    intent = "investigation" if any(word in q for word in ("why", "investigate", "原因", "为什么", "上涨", "下降", "变化")) else "metric_lookup"
    if metric == "net_revenue" and not as_of:
        raise ValueError("Net Revenue requires an explicit report as-of date, for example: 截至2026-05-11.")

    return Request(intent, metric, start, end, dimension, filters, compare_start, compare_end, as_of)


class AnalyticsAgent:
    """Deterministic single-agent orchestrator over governed analytics tools."""

    def __init__(self, db: Path = TRUSTED_DB):
        self.db = db
        self.tools = GovernedAnalyticsTools(db)

    def answer(self, question: str) -> dict[str, Any]:
        request = parse_question(question)
        trace: list[dict[str, Any]] = [{"step": "validate_and_parse", "status": "completed"}]
        current = self.tools.metric_lookup(
            request.metric, request.start_date, request.end_date,
            request.dimension, request.filters, request.report_as_of_ts,
        )
        trace.append({"step": "metric_lookup", "status": "completed", "quality_status": current["quality_status"]})

        comparison = None
        if request.compare_start:
            comparison = self.tools.metric_lookup(
                request.metric, request.compare_start, request.compare_end,
                request.dimension, request.filters, request.report_as_of_ts,
            )
            trace.append({"step": "comparison_lookup", "status": "completed", "quality_status": comparison["quality_status"]})

        comparison_summary = self._compare(current, comparison) if comparison else None
        fraud_evidence = None
        if request.metric in {"gross_revenue", "net_revenue"}:
            fraud_evidence = self.tools.fraud_evidence(
                request.start_date, request.end_date, request.filters.get("platform")
            )
            trace.append({"step": "fraud_evidence", "status": "completed"})
        presentation = self._presentation(current, fraud_evidence)
        investigation = None
        if request.intent == "investigation":
            context = self.tools.context_retrieval(request.start_date, request.end_date)
            investigation = self._investigate(current, comparison, context, fraud_evidence)
            trace.append({"step": "evidence_synthesis", "status": "completed", "classification": investigation["classification"]})

        return {
            "question": question,
            "request": asdict(request),
            "answer_status": "abstained" if current["quality_status"] == "unavailable" else "answered",
            "metric_definition": current["definition"],
            "presentation": presentation,
            "result": current["result"],
            "comparison": comparison["result"] if comparison else None,
            "comparison_summary": comparison_summary,
            "quality_status": self._combined_quality(current, comparison),
            "quality_issues": current["quality_issues"] + (comparison["quality_issues"] if comparison else []),
            "sources": sorted(set(current["sources"] + (comparison["sources"] if comparison else []))),
            "limitations": list(dict.fromkeys(current["limitations"] + (comparison["limitations"] if comparison else []))),
            "executed_queries": {
                "current": current["executed_query"],
                "comparison": comparison["executed_query"] if comparison else None,
            },
            "investigation": investigation,
            "trace": trace,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "query_policy": current["query_policy"],
        }

    @staticmethod
    def _presentation(metric_result: dict, fraud_evidence: dict | None = None) -> dict[str, Any]:
        headline = [
            {"segment": row["segment"], "value": row.get("value")}
            for row in metric_result["result"]
        ]
        excluded_value = sum(
            row.get("suspected_bot_excluded_value", 0) or 0
            for row in metric_result["result"]
        )
        flags = []
        for issue in metric_result["quality_issues"]:
            reason = issue.get("reason", "")
            if "automation excluded" in reason:
                treatment = "blocked_and_excluded_from_headline"
                affected_value = excluded_value
            elif "canonical visits rebuilt" in reason:
                treatment = "reconstructed_with_approved_30_minute_rule"
                affected_value = None
            else:
                treatment = "authoritative_answer_blocked" if issue.get("status") == "unavailable" else "adjusted"
                affected_value = None
            flags.append({
                "start_date": issue.get("start_date", issue.get("available_start_date")),
                "end_date": issue.get("end_date", issue.get("available_end_date")),
                "situation": reason,
                "treatment": treatment,
                "blocked_or_adjusted_value": affected_value,
            })
        policy_flags = []
        if fraud_evidence:
            fraud = fraud_evidence["summary"]
            if fraud["confirmed_excluded_order_count"] or fraud["suspected_included_order_count"]:
                policy_flags.append({
                    "type": "fraud_policy",
                    "confirmed_excluded_order_count": fraud["confirmed_excluded_order_count"],
                    "confirmed_excluded_gross_revenue": fraud["confirmed_excluded_gross_revenue"],
                    "suspected_included_order_count": fraud["suspected_included_order_count"],
                    "suspected_included_gross_revenue": fraud["suspected_included_gross_revenue"],
                    "treatment": "confirmed excluded; suspected/unconfirmed retained and flagged",
                })
        return {
            "headline_policy": "cleaned_metric_only",
            "headline_result": headline,
            "data_quality_flags": flags,
            "policy_flags": policy_flags,
            "audit_note": "Raw-versus-filtered values remain in result/evidence for review, not in the business headline.",
        }

    @staticmethod
    def _combined_quality(current: dict, comparison: dict | None) -> str:
        statuses = {current["quality_status"]}
        if comparison:
            statuses.add(comparison["quality_status"])
        if "unavailable" in statuses:
            return "unavailable"
        if "adjusted" in statuses:
            return "adjusted"
        return "trusted"

    @staticmethod
    def _compare(current: dict, comparison: dict) -> list[dict[str, Any]]:
        prior = {row["segment"]: row.get("value") for row in comparison["result"]}
        output = []
        for row in current["result"]:
            value, baseline = row.get("value"), prior.get(row["segment"])
            absolute = None if value is None or baseline is None else round(value - baseline, 6)
            percent = None if absolute is None or baseline == 0 else round(absolute / baseline, 6)
            output.append({"segment": row["segment"], "current": value, "comparison": baseline,
                           "absolute_change": absolute, "percent_change": percent})
        return output

    @staticmethod
    def _investigate(current: dict, comparison: dict | None, context: dict, fraud_evidence: dict | None = None) -> dict[str, Any]:
        fraud = fraud_evidence["summary"] if fraud_evidence else None
        has_fraud_signal = fraud and (
            fraud["confirmed_excluded_order_count"] or fraud["suspected_included_order_count"]
        )
        if current["quality_status"] == "unavailable":
            classification, confidence = "data_quality_unavailable", "high"
            action = "Repair or backfill the affected source before interpreting the metric."
        elif has_fraud_signal:
            classification, confidence = "security_review_candidate", "high"
            action = "Route the flagged shared-payment/device pattern to Risk review; do not auto-cancel orders or label unconfirmed orders as confirmed fraud."
        elif current["quality_status"] == "adjusted":
            classification, confidence = "data_quality_adjustment", "high"
            action = "Use the adjusted headline and monitor the raw-versus-filtered impact."
        elif context["campaigns"] or context["app_releases"]:
            classification, confidence = "business_context_candidate", "low"
            action = "Validate the overlapping campaign or release with a controlled segment/time comparison."
        else:
            classification, confidence = "insufficient_evidence", "low"
            action = "Collect additional causal evidence before assigning a driver."

        bot_evidence = [
            {key: row[key] for key in row if key.startswith("suspected_bot") or key in {"segment", "raw_value", "value"}}
            for row in current["result"] if "suspected_bot_excluded_share" in row
        ]
        return {
            "classification": classification,
            "affected_segment": current.get("filters") or "all requested segments",
            "evidence": {
                "metric_health": current["quality_issues"],
                "raw_vs_filtered": bot_evidence,
                "comparison_available": comparison is not None,
                "campaigns": context["campaigns"],
                "app_releases": context["app_releases"],
                "fraud": fraud_evidence,
            },
            "confidence": confidence,
            "limitations": list(dict.fromkeys(current["limitations"] + [context["causality_guardrail"]])),
            "recommended_action": action,
        }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    args = parser.parse_args()
    print(json.dumps(AnalyticsAgent().answer(args.question), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
