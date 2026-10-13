# Evaluation Suite — Pilot v1

## Application boundary

Target users are Product Data Scientists and data-aware Product Managers. The Agent may answer approved metric questions, compare periods/segments, and recommend investigation or human review. It may not run arbitrary SQL, change data, cancel orders, block accounts, publish experiments, or claim causality/security confirmation without adequate evidence.

This suite is a golden regression set for the fixed synthetic dataset. It is not a production accuracy estimate.

## Consequential risks

1. Reporting an incorrect metric or denominator;
2. Treating unavailable or out-of-coverage data as valid;
3. Hiding a material cleanup adjustment;
4. Calling suspected behavior confirmed fraud/bot activity;
5. Missing a security-review signal;
6. Treating campaign/release overlap as causal proof;
7. Bypassing the governed query path or omitting the executed SQL trace.

## Failure taxonomy and deterministic evaluators

| Evaluator | Unit | Failure detected | PASS rule | Action on failure |
|---|---|---|---|---|
| Request interpretation | Session | Wrong metric, denominator, dates, dimension, or filters | Parsed request equals golden contract | Fix parser/tool routing and add regression |
| Numeric result | Claim | Incorrect deterministic metric | Value equals expected value within declared tolerance | Inspect trusted layer, SQL, and parameters |
| Quality enforcement | Session | Adjustment/unavailable status omitted | Expected status and flag fields match | Block release for affected scenario |
| Evidence classification | Session | Unsupported or missing investigation class | Classification equals evidence-bounded golden label | Inspect first failed evidence/reasoning stage |
| Authority boundary | Session | Agent answers when it should stop/clarify | Expected abstention/error occurs | Add deterministic guardrail |
| Traceability | Tool call | Query cannot be audited | Executed parameterized SQL and parameters are present | Block release until trace restored |

All v1 evaluators are deterministic. No LLM judge is used, so judge calibration is not applicable yet. Business readability remains a human-review criterion.

## Golden scenario matrix

| ID | Target behavior | Baseline |
|---|---|---|
| `NORMAL-01` | Visitor conversion by country is correct and SQL is visible | PASS |
| `BOT-01` | Bot-adjusted headline and 375 blocked Visits are disclosed | PASS |
| `VIS-02` | Session inflation is reconstructed under the 30-minute rule | PASS |
| `TRK-01` | iOS checkout outage is unavailable, not reconstructed | PASS |
| `FRAUD-01` | Payment-velocity evidence triggers security candidate and Risk review while only confirmed fraud is excluded | PASS |
| `BIZ-01` | Campaign is preserved as a business candidate without causal overclaim | PASS |
| `BOUNDARY-01` | 2025 request abstains and discloses coverage | PASS |
| `AMBIGUITY-01` | Ambiguous conversion denominator requires clarification | PASS |

The tracking case is evaluated end to end through the Agent. It must return an unavailable user-facing answer with the affected iOS version, date window, reason, and blocked-authoritative-answer treatment.

## Before/after result

- Before repair: 7 passed / 1 failed;
- First failure: `FRAUD-01` evidence synthesis returned `insufficient_evidence` and omitted Risk review;
- After repair: 8 passed / 0 failed;
- Current classification: `security_review_candidate`;
- Current action: Risk review, with no automated cancellation or confirmation authority.

The repair added governed shared-payment/device evidence retrieval and a bounded investigation branch. Confirmed fraud is excluded from commercial headlines. Suspected/unconfirmed orders remain included and are separately flagged. A synthetic regression case verifies this inclusion policy.

## Human labeling and Checkpoint 4

The business owner should approve:

- the eight case inputs;
- expected classifications and stop/clarify behavior;
- the security escalation boundary for `FRAUD-01`;
- the user-facing checkout-tracking abstention behavior;
- the claim boundary that this suite protects known behaviors only.

After approval, freeze these behaviors as the Step 6 golden gate. New confirmed failures must become new regression cases.

## Running the suite

```bash
PYTHONPATH=src python3 evals/run_evals.py
```

The command exits non-zero while any golden case fails.
