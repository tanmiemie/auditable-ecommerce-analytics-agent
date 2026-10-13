# Data Cleanup Check Registry

For each applicable check, record: status, evidence count/rate, affected segment and time, action, output object, test, and residual risk.

## Structure and contracts

| ID | Check | Default treatment |
|---|---|---|
| STR-001 | Declared grain matches observed grain | Stop metric publication on unresolved mixed grain |
| STR-002 | Primary/composite keys are unique and non-null | Quarantine or deterministically resolve; never hide fanout |
| STR-003 | Required columns, types, and timestamp formats | Mark invalid rows and affected metrics |
| STR-004 | Stable enums and schema drift | Version mappings; quarantine unknown values when semantics are unsafe |
| STR-005 | Foreign keys and join coverage | Report orphans and pre/post-join row counts |
| STR-006 | Join fanout | Block calculations that multiply fact rows |

## Events and behavioral data

| ID | Check | Default treatment |
|---|---|---|
| EVT-001 | Duplicate event IDs / retry rows | Keep raw; retain earliest ingestion deterministically in trusted data |
| EVT-002 | Conflicting duplicate content | Continue with earliest row, set conflict flag, quantify and review |
| EVT-003 | Event-name or property migration | Apply platform/version/effective-date mapping and preserve raw fields |
| EVT-004 | Event ordering and impossible timestamps | Flag; do not silently reorder business time |
| EVT-005 | Client/server divergence or tracking outage | Mark affected client metric unavailable; never fabricate events from orders |
| EVT-006 | Required event-property completeness | Mark affected analysis unavailable when coverage is insufficient |

## Sessions and identity

| ID | Check | Default treatment |
|---|---|---|
| SES-001 | Sessionization-version drift | Rebuild canonical visits from approved inactivity rule |
| SES-002 | Empty sessions and referral loops | Preserve raw; exclude empty visits and flag loop patterns |
| IDN-001 | Identity status and effective time | Stitch only eligible links under platform policy |
| IDN-002 | One identity mapping to multiple users / reassignment | Do not stitch conflicted periods; review |
| IDN-003 | Cookie/device resets and identity proliferation | Quantify by version and time; do not assume user growth |

## Transactions and revenue

| ID | Check | Default treatment |
|---|---|---|
| ORD-001 | Order key, amount formula, currency, and payment validity | Exclude invalid commercial facts or mark review per contract |
| ORD-002 | Order status snapshots | Select latest valid status at as-of time; never sum snapshots |
| ORD-003 | Missing session attribution | Preserve server order; exclude only from metrics requiring visit attribution |
| ORD-004 | Confirmed fraud and suspected fraud | Apply approved status policy; preserve evidence and label timing |
| ORD-005 | Employee/internal orders | Apply approved inclusion policy and expose a flag |
| REF-001 | Refund request, completion, and window timing | Apply approved recognition time and maturity flag |
| REF-002 | Refund amount exceeds order or late policy exception | Flag and review; never silently over-deduct |

## Time, freshness, and leakage

| ID | Check | Default treatment |
|---|---|---|
| TIM-001 | Event-to-ingestion lag by source and partition | Publish lag profile and data as-of timestamp |
| TIM-002 | Recent incomplete partitions | Mark provisional until the approved maturity threshold |
| TIM-003 | Backfills and historical rewrites | Version results and disclose restatement |
| TIM-004 | Delayed labels used before availability | Require label-effective time; otherwise label output as latest-state restatement |
| TIM-005 | Future data / time travel | Block or quarantine affected calculation |

## Automation, fraud, and experiments

| ID | Check | Default treatment |
|---|---|---|
| BOT-001 | Known and behaviorally suspected automation | Keep raw/filtered values and rule version; do not overclaim confirmation |
| FRD-001 | Shared device/payment/IP velocity patterns | Quantify, flag suspected fraud, and route for review |
| EXP-001 | Assignment uniqueness and balance | Mark invalid experiments unavailable |
| EXP-002 | Exposure without assignment or variant mismatch | Quantify and prevent unsupported experiment conclusions |
| EXP-003 | Required experiment property missing | Mark affected segment/window unavailable |

## Business-preservation controls

| ID | Check | Default treatment |
|---|---|---|
| BIZ-001 | Campaign traffic and spend context | Preserve and surface as possible real-business explanation |
| BIZ-002 | Legitimate promotion orders | Preserve non-fraud demand and quantify separately from abuse |
| BIZ-003 | Inventory/stockout context | Preserve conversion impact; do not classify as tracking failure without evidence |
| BIZ-004 | Release/UX behavior change with intact telemetry | Preserve as product effect and distinguish from missing instrumentation |

## Output and governance

| ID | Check | Default treatment |
|---|---|---|
| GOV-001 | Raw-to-trusted reconciliation | Required counts and metric deltas |
| GOV-002 | Audit lineage and rule versions | Required for every adjustment |
| GOV-003 | Metric health / abstention | Unavailable metrics must not return authoritative values |
| GOV-004 | Normal and anomaly regression fixtures | Required before checkpoint approval |
| GOV-005 | Human decision trace | Record business choices separately from implementation details |

