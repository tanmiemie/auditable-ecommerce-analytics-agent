# Data Cleanup Reconciliation — Checkpoint 2 Draft

## Scope

This report reconciles the raw ecommerce dataset to the trusted layer built from the Checkpoint 1 semantic contracts. Raw tables remain unchanged. The generated trusted database is `data/ecommerce_trusted.sqlite`; its reproducible builder is `src/analytics_agent/trusted_layer.py`.

Report as-of timestamp for refund maturity examples: `2026-05-11T08:36:30Z`, the latest ingestion timestamp across the relevant raw sources.

## Reconciliation summary

| Area | Raw / before | Trusted / after | Treatment and impact |
|---|---:|---:|---|
| Events | 320,986 rows | 320,090 unique events | 896 retry rows removed deterministically; zero content conflicts; raw rows retained |
| Identity links | 10,000 links | 9,743 eligible, 257 ineligible | Pending links are not stitched; no ambiguous/conflicting links observed |
| Raw sessions → canonical visits | 71,279 sessions | 70,895 visits | 284 sessions had no events; event-based 30-minute reconstruction also merged adjacent raw sessions |
| Suspected-bot visits | 70,895 raw visits | 70,520 filtered visits | 375 visits (0.529%) excluded from traffic headline; raw impact retained |
| Orders | 5,593 orders | 5,508 commercially eligible | 85 confirmed-fraud orders excluded; their gross value is $8,273.50 |
| Employee orders | 4 orders | 4 included with flag | $560.59 retained and exposed through `is_employee_order` |
| Refunds | 185 requests | 185 eligible requests | $25,899.74 recognized at `requested_at`; zero requests were outside 30 days |
| Order-to-visit attribution | 5,593 orders | 5,508 eligible orders attributed | 85 unattributed orders are exactly the 85 confirmed-fraud orders; 45 were sessionless and 40 had sessions without usable events |
| Order status history | 22,032 snapshots | 5,508 current statuses | Latest status selected without revenue fanout; zero snapshot amount mismatches |
| Tracking health | Daily platform/version slices | 4 unavailable slices | iOS 6.1.0 checkout metric unavailable on Mar 15–18 because server orders remained while checkout events were absent |
| Experiment instrumentation | Assigned-user cart events | 4 unavailable slices | iOS 6.2.1 experiment analysis unavailable on Apr 10–13; 10 exposures without assignment remain review items |

## Metric impact

| Metric view | Raw | Governed headline | Difference |
|---|---:|---:|---:|
| Visits | 70,895 | 70,520 | −375 suspected-bot visits |
| Visit Purchase Conversion | 7.7664% | 7.8077% | +0.0413 percentage points after bot filtering |
| Visitor Purchase Conversion | 40.7407% | 42.2696% | +1.5289 percentage points after bot filtering |

At the report as-of timestamp, 4,773 commercially eligible orders have completed the 30-day refund window. Their mature Gross Revenue is $664,877.83 and finalized Net Revenue is $642,876.16. Another 735 eligible orders representing $105,874.47 remain inside the refund window and are disclosed as immature revenue rather than included in finalized Net Revenue.

## Trusted objects

- `trusted_identity_map`: identity eligibility and review reason;
- `trusted_events`: deterministic event deduplication, canonical event name, governed identity, visit assignment, and bot evidence;
- `canonical_visits`: approved 30-minute visit fact and raw/filtered eligibility;
- `trusted_sessions`: raw-session lineage plus identity and bot annotations;
- `trusted_orders`: fraud eligibility, employee flag, canonical-visit attribution, refund totals, and refund-window end;
- `trusted_refunds`: request-time recognition and late-request review flag;
- `trusted_order_status_history` and `trusted_order_current_status`: history-preserving current-state resolution;
- `tracking_health_daily`: independent client/server tracking availability;
- `experiment_instrumentation_health`: required-property coverage and abstention status;
- `data_freshness_audit`: source-time versus ingestion-time lag;
- `contract_check_results`, `event_dedup_audit`, and `data_quality_audit`: inspectable contract and adjustment evidence;
- `dim_campaigns`, `dim_app_releases`, and `dim_products`: preserved business context.

## Validation results

- 320,090 trusted event rows have 320,090 distinct `event_id` values;
- conflicting duplicates retain the earliest-ingested record, continue the build, and emit `content_conflict = 1` for review;
- no event gap greater than 30 minutes exists inside a canonical visit;
- app identity retro-stitching and web `effective_from` boundary have zero detected rule violations;
- bot classifications include rule version and reason fields;
- all confirmed-fraud orders are ineligible, while all employee orders remain eligible;
- requested refund totals reconcile to raw refunds, and all refund-window flags are valid;
- four iOS 6.1.0 tracking-outage days are marked unavailable rather than repaired from orders;
- four iOS 6.2.1 experiment-property failure days are marked unavailable;
- latest order snapshots resolve to 5,508 completed orders without fact-table fanout;
- 4,904 eligible campaign visits, 358 legitimate Spring promotion orders, and 9,047 Android 6.3.0 events remain preserved;
- all 17 automated tests pass, including thirteen trusted-layer contract tests and four legacy prototype regression tests.

## Residual risks and boundaries

- The synthetic data contains no anonymous web event before its mapping `effective_from` that is both eligible and lacks a direct user ID. The web boundary is implemented and tested for violations, but this exact positive edge case is not exercised by current data.
- `bot_rule_v1` uses the available source bot flag or a `PriceMonitor` user-agent signal. It is a reproducible suspected-bot rule, not independent confirmation.
- Confirmed-fraud labels lack an effective timestamp. Fraud-filtered history is therefore explicitly a latest-state restatement, not a reconstruction of what was known at the original report time.
- Event lag reaches 48 hours, order lag 1.5 hours, and refund ingestion lag 185 hours. Freshness is now measured, but each future metric still needs an owner-approved maturity threshold before recent periods can be declared final.
- Ten experiment exposures have no matching assignment and remain review items.
- The dataset has no dated inventory-history source, so the stockout scenario can be preserved but not independently validated as causal from inventory data.
- Cookie-reset and referral-loop checks are in the reusable registry, but the current dataset has no confirmed positive fixture for either pattern.
- Recent Net Revenue is intentionally incomplete until orders pass the 30-day refund window; every query must expose its report as-of timestamp and immature revenue.
- The existing Agent query layer is still experimental. This cleanup approves the trusted data, not the final Agent behavior.

## Checkpoint 2 review

Owner confirmation is required before moving to governed analytics tools. Please review whether the adjustments, metric impact, and residual limitations are acceptable.
