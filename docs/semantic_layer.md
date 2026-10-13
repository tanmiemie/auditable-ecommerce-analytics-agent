# Semantic Layer

## Purpose

The same raw data can support multiple technically correct but business-incompatible answers. This semantic layer defines what each table represents, its grain and keys, approved joins, metric rules, and the conditions under which a result is usable.

Machine-readable contracts live in:

- `config/semantic_layer.yml`
- `config/metrics.yml`
- `config/data_quality_contracts.yml`

## Core entities

| Table | Row meaning | Primary or candidate key | Role |
|---|---|---|---|
| `users` | One registered account | `user_id` | Country, initial platform, employee status |
| `identity_map` | One anonymous-to-registered identity link | `anonymous_id` | Pre-login and post-login stitching |
| `sessions` | One source-system raw session | `session_id` | Raw traffic and platform context |
| `events` | One client event sent to collection | `event_id` candidate key | Behavior time, event taxonomy, duplicate detection |
| `orders` | One server-side order | `order_id` | Revenue and conversion numerator |
| `refunds` | One refund request | `refund_id` | Net Revenue adjustment |
| `campaigns` | One marketing campaign | `campaign_id` | Investigation context |
| `app_releases` | One platform release | `platform + app_version` | Tracking and behavior context |

## Verified dataset facts

- 10,000 users with unique, non-null `user_id` values.
- 10,000 identity records: 9,743 matched and 257 pending.
- 71,279 source sessions, including 822 records created under a five-minute timeout.
- 320,986 event rows, including 896 duplicate `event_id` rows.
- 5,593 orders, including 85 confirmed-fraud orders, four employee orders, and 45 orders without a session.
- 185 refunds, all linked to an order and requested within 30 days in this fixed dataset.
- Order arithmetic reconciles to `subtotal - discount + shipping_fee + tax = order_total`.

## Approved semantic boundaries

### Raw session is not a Visit

A source session reflects upstream instrumentation. The governed Visits metric reconstructs canonical Visits using a 30-minute inactivity rule and keeps raw identifiers for audit.

### Anonymous identity is not automatically a known user

Only matched, non-conflicting identities may be stitched. App behavior may be stitched retroactively because the approved pilot assumes a primarily single-user device. Web behavior is stitched only at or after `effective_from` because browsers may be shared. Pending or ambiguous mappings remain unresolved.

### Visitor conversion is not Visit conversion

Visitor Purchase Conversion uses unique canonical visitors as the denominator. Visit Purchase Conversion uses canonical Visits. An unqualified conversion question must trigger clarification.

### Client events are not server transactions

Events describe client behavior; Orders are server-side commercial facts. When they disagree, the system investigates tracking health. It does not use Orders to invent missing client events.

### Context is not causal proof

Campaigns and releases can strengthen an investigation hypothesis, but temporal overlap alone does not establish causality.

## Approved metric policies

1. Gross Revenue uses eligible paid orders and `order_total`, including shipping and tax after discounts and before refunds.
2. Net Revenue subtracts refunds at `requested_at` and reports only order cohorts whose 30-day refund window is complete as final.
3. Confirmed-fraud orders are excluded from Revenue and conversion numerators.
4. Suspected or unconfirmed fraud remains included and receives a Risk-review flag.
5. Employee orders remain included and receive an employee flag.
6. Traffic-derived headlines use bot-filtered values and disclose raw values, excluded counts, and excluded shares.
7. Traffic and conversion use `users.country`; Revenue uses `orders.shipping_country`.
8. Missing telemetry makes dependent metrics unavailable when the missing fact cannot be reconstructed reliably.

These rules were approved before cleanup and are enforced in the trusted layer, governed tools, regression tests, and golden evaluation suite.
