# Demo Guide

## One-command demo

From the repository root:

```bash
PYTHONPATH=src python3 scripts/run_demo.py
```

The script rebuilds the trusted database and runs five fixed questions. Each output retains the cleaned headline, flags, limitations, SQL, parameters, and trace.

## Demo story

### 1. A metric can be numerically valid but operationally misleading

Ask `1月 Web visits 为什么上涨？`. The Agent removes 375 suspected-automation Visits from the headline, discloses the affected dates, and preserves the raw evidence for audit. It also finds an overlapping Paid Social campaign but does not claim causality.

### 2. Metric definitions require explicit business choices

Compare `按国家比较3月访客转化率` with `按国家比较3月访问转化率`. The values differ because the denominators differ. Asking only for “购买转化率” triggers clarification rather than a silent default.

### 3. Revenue needs an as-of date

Ask `截至2026-05-11，3月净收入与2月相比如何？`. The Agent recognizes refunds at request time and finalizes only order cohorts whose 30-day refund window has closed.

### 4. Missing telemetry must block the dependent metric

Ask `2026-03-15 to 2026-03-18 iOS checkout tracking 数据可以用吗？`. The Agent reports that iOS 6.1.0 checkout events are missing while server orders continue, returns `unavailable`, and refuses to fabricate the client metric.

### 5. Missing coverage is not zero

Ask `2025年 visits 是多少？`. The Agent returns no value and states that the available coverage is 2026-01-01 through 2026-04-30.

## Evidence to show during review

- Exact parameterized SQL under `executed_queries`;
- Agent execution stages under `trace`;
- Cleanup reconciliation in `docs/DATA_CLEANUP_RECONCILIATION.md`;
- Golden before/after history in `docs/EVALUATION_SUITE.md`;
- Business and technical decisions in `docs/DEVELOPMENT_LOG.md`.

## Demo claim boundary

This is a deterministic synthetic MVP demonstrating governed analytics behavior. Do not describe it as a production deployment, a general Text-to-SQL system, or evidence that it replaces Data Scientists.
