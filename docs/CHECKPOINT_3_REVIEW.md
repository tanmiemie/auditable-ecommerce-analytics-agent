# Checkpoint 3 — Single-Agent Experience Review

## What to review

Please judge whether each response:

- answers the business question clearly;
- uses the intended metric definition and denominator;
- distinguishes computed facts from possible explanations;
- exposes material data-quality adjustments and limitations;
- avoids claiming causality without evidence;
- gives a useful next action;
- includes enough trace to review what the Agent did.

Approved presentation rule: the business headline/table shows cleaned metrics only. Any adjustment or block appears in a separate Data Quality Flag table immediately below it with dates, situation, treatment, and affected quantity. Raw-versus-filtered values remain audit evidence.

## Five trial questions

1. `1月 Web visits 为什么上涨？`
   - Expected behavior: expose suspected-bot adjustment, raw versus filtered impact, and campaign context without treating overlap as causal proof.
2. `按国家比较3月访客转化率`
   - Expected behavior: use the visitor denominator and return country segments.
3. `按国家比较3月访问转化率`
   - Expected behavior: use the visit denominator and produce a result distinct from visitor conversion.
4. `截至2026-05-11，3月净收入与2月相比如何？`
   - Expected behavior: apply refund-request timing and refund-window maturity, then disclose latest-state fraud-label limitations.
5. `3月 gross revenue 按国家`
   - Expected behavior: interpret revenue country as shipping country and preserve employee orders under the approved policy.

## Intentional rejection checks

- `按国家比较3月购买转化率`
  - Must ask for visitor or visit denominator rather than silently choosing one.
- `3月净收入是多少？`
  - Must require a report as-of date.
- `2025年 visits 是多少？`
  - Must return `unavailable`, disclose the available `2026-01-01` to `2026-04-30` coverage, and return no fabricated or partial value.

## Approval decision

- [x] Approved to proceed to Step 6 Evaluation Suite — confirmed by business owner on 2026-10-13
- [ ] Approved with revisions listed below
- [ ] Not approved

Notes:
