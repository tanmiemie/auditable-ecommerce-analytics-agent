from __future__ import annotations

from typing import Any


RATE_METRICS = {
    "visitor_purchase_conversion_rate",
    "visit_purchase_conversion_rate",
    "checkout_start_rate",
}
REVENUE_METRICS = {"gross_revenue", "net_revenue"}


def metric_label(metric: str) -> str:
    return metric.replace("_", " ").title()


def format_metric_value(metric: str, value: Any) -> str:
    if value is None:
        return "Unavailable"
    if metric in RATE_METRICS:
        return f"{float(value):.2%}"
    if metric in REVENUE_METRICS:
        return f"${float(value):,.2f}"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{int(value):,}"


def format_delta(metric: str, row: dict[str, Any]) -> str | None:
    absolute = row.get("absolute_change")
    percent = row.get("percent_change")
    if absolute is None:
        return None
    absolute_text = format_metric_value(metric, abs(absolute))
    sign = "+" if absolute >= 0 else "−"
    if percent is None:
        return f"{sign}{absolute_text}"
    return f"{sign}{absolute_text} ({percent:+.1%})"


def chart_rows(answer: dict[str, Any]) -> list[dict[str, Any]]:
    metric = answer["request"]["metric"]
    comparison = {
        row["segment"]: row.get("comparison")
        for row in answer.get("comparison_summary") or []
    }
    rows = []
    for row in answer.get("result") or []:
        item = {
            "segment": str(row["segment"]),
            "current": row.get("value"),
            "metric": metric,
        }
        if row["segment"] in comparison:
            item["comparison"] = comparison[row["segment"]]
        rows.append(item)
    return rows


def quality_label(status: str) -> str:
    return {
        "trusted": "Trusted",
        "adjusted": "Adjusted",
        "unavailable": "Unavailable",
    }.get(status, status.title())
