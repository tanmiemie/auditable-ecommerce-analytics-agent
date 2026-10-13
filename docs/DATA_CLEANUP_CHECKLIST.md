# Ecommerce Data Cleanup Check Coverage

This checklist applies the reusable `.agents/skills/data-cleanup/references/check-registry.md` to the current synthetic ecommerce dataset. `Pass` means the check ran with no unresolved violation; `Adjusted` means trusted data changed with audit evidence; `Unavailable` means affected metrics must abstain; `Review` means records are retained and surfaced; `Not testable` means the required source or positive fixture is absent.

| ID | Status | Current evidence / treatment |
|---|---|---|
| STR-001 | Pass | Grain documented for core tables and trusted outputs |
| STR-002 | Adjusted | Event duplicates resolved; trusted keys tested |
| STR-003 | Pass | Required event fields, timestamps, and core order validity checked |
| STR-004 | Adjusted | `cart_add` mapped with rule ID; enums checked |
| STR-005 | Review | Core joins have zero orphans; 10 experiment exposures lack assignment |
| STR-006 | Pass | Order snapshots resolve without fact-table fanout |
| EVT-001 | Adjusted | 896 duplicate event rows removed from trusted events |
| EVT-002 | Pass | Zero current content conflicts; injected conflict fixture verifies retain-and-flag behavior |
| EVT-003 | Adjusted | Android 6.2.0 cart migration canonicalized with raw name retained |
| EVT-004 | Pass | Negative ingestion lag checked; visit event ordering tested |
| EVT-005 | Unavailable | Four iOS 6.1.0 checkout days fail client/server reconciliation |
| EVT-006 | Unavailable | Four iOS 6.2.1 experiment-property days fail completeness threshold |
| SES-001 | Adjusted | Canonical visits rebuilt with 30-minute inactivity rule |
| SES-002 | Partial | 284 empty sessions identified; referral-loop source fields/positive fixture absent |
| IDN-001 | Adjusted | App retroactive and Web effective-time stitching implemented |
| IDN-002 | Pass | Pending links excluded; no current multi-user identity conflict |
| IDN-003 | Monitored | Anonymous IDs per matched user profiled; no approved reset threshold |
| ORD-001 | Pass | Keys, currency, payment status, and cent-level amount reconciliation checked |
| ORD-002 | Adjusted | 22,032 snapshots resolve to 5,508 latest completed statuses |
| ORD-003 | Adjusted | Sessionless orders retained; visit attribution coverage disclosed |
| ORD-004 | Adjusted | 85 confirmed fraud orders excluded; shared payment/device signals audited |
| ORD-005 | Adjusted | Four employee orders retained with flag |
| REF-001 | Adjusted | Refunds recognized at request; 30-day maturity implemented |
| REF-002 | Pass | No late requests or refund totals above order value |
| TIM-001 | Pass | Event/order/refund lag profiles published |
| TIM-002 | Provisional | As-of required; metric-specific maturity exists for Net Revenue, not yet for every event metric |
| TIM-003 | Review | Rebuild is reproducible; external backfill version feed is absent |
| TIM-004 | Review | Fraud label timestamps absent; outputs marked latest-state restatements |
| TIM-005 | Pass | Negative/future ingestion ordering checked for events |
| BOT-001 | Adjusted | 375 suspected-bot visits filtered from headline with raw comparison retained |
| FRD-001 | Review | Shared payment/device signals retained for risk review; only confirmed fraud is excluded |
| EXP-001 | Pass | Assignment uniqueness checked |
| EXP-002 | Review | Ten exposures without assignment; variant mismatch checked |
| EXP-003 | Unavailable | Affected iOS 6.2.1 experiment slices cannot support conclusions |
| BIZ-001 | Preserved | 4,904 eligible Paid Social campaign visits remain |
| BIZ-002 | Preserved | 358 legitimate Spring promotion orders remain |
| BIZ-003 | Not testable | Behavior window preserved, but no dated inventory-history source exists |
| BIZ-004 | Preserved | 9,047 non-bot Android 6.3.0 events remain after cleanup |
| GOV-001 | Pass | Raw-to-trusted reconciliation report exists |
| GOV-002 | Pass | Audit tables, raw IDs, mapping rules, and rule versions retained |
| GOV-003 | Pass in data layer | Tracking and experiment slices emit unavailable status; Agent enforcement is Step 4 |
| GOV-004 | Pass | 17 automated tests include anomaly and normal-business fixtures |
| GOV-005 | Pass | Decisions and commands are recorded in the development log |

## Items that cannot be “cleaned away”

- Tracking and experiment gaps remain unavailable because missing facts cannot be reconstructed safely.
- Fraud history is a latest-state restatement until label-effective timestamps exist.
- Stockout causality cannot be proven without dated inventory history.
- Referral loops cannot be directly detected without referrer/navigation fields.
- Recent event maturity needs a metric-owner threshold; lag is measured but not silently converted into a universal cutoff.

