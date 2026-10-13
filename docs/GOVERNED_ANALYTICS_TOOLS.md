# Governed Analytics Tools

## Purpose

This layer gives the Agent a small, auditable analytics API instead of arbitrary SQL access. It reads only the trusted SQLite layer and exposes only approved metrics and dimensions.

## Supported operations

### `list_capabilities()`

Returns the approved metric registry, including definition, sources, and permitted dimensions.

### `metric_lookup(...)`

Returns one approved metric for a date range, with an optional approved `group_by`, approved equality filters, and—when required—a reporting as-of timestamp.

Every response contains:

- metric definition and requested time range;
- result rows and applied filters;
- data-quality status and issues;
- trusted sources and limitations;
- the query policy used.

### `segment_comparison(...)`

Uses the same governed metric path and groups the result by one approved dimension. It does not accept arbitrary columns or SQL fragments.

### `health_check(...)`

Returns `trusted`, `adjusted`, or `unavailable` for the requested metric window. An unavailable window blocks an authoritative metric result.

### `context_retrieval(...)`

Returns campaigns and app releases overlapping the requested period. Temporal overlap is supporting context, not proof of causality.

## Approved metrics

| Metric | Headline behavior |
|---|---|
| `visits` | 30-minute canonical visits; suspected bots excluded from headline and shown separately |
| `visitor_purchase_conversion_rate` | purchasing eligible visitors / eligible visitors |
| `visit_purchase_conversion_rate` | eligible visits linked to a paid order / eligible visits |
| `checkout_start_rate` | eligible visits with a canonical begin_checkout event / eligible visits; unavailable during confirmed tracking outages |
| `gross_revenue` | eligible paid order revenue before refunds |
| `net_revenue` | mature order-cohort revenue less refunds requested by the report as-of time |

## Guardrails

- Read-only trusted database access;
- Metric and dimension whitelist;
- Parameterized filter values;
- No evaluator-only `ground_truth/` access;
- Explicit `report_as_of_ts` required for Net Revenue;
- Confirmed fraud excluded; employee orders retained and exposed as a dimension/flag;
- Suspected/unconfirmed fraud remains in commercial headlines and is separately flagged with governed shared-payment/device evidence;
- Latest-state fraud-label limitation disclosed on revenue results;
- Raw and bot-filtered traffic/conversion values reported together;
- Unavailable health windows produce no authoritative result.
- Checkout tracking outages are consolidated by platform/version/date and surfaced to the Agent as a user-facing abstention flag.
- A request extending beyond source date coverage returns `unavailable` with no value and discloses the available range.

## Current limitations

- Fraud labels have no effective timestamp, so historical revenue is restated using the latest known label;
- Inventory history and referral/navigation evidence are absent;
- Context retrieval identifies overlap but cannot establish causality;
- The single-Agent reasoning and answer-composition layer is Step 5 and is not part of these tools.
