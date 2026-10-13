# Single-Agent Workflow

## Workflow

1. Validate and parse the question into an approved metric, reporting window, comparison window, dimension, filters, and reporting as-of time.
2. Reject ambiguous conversion questions until the user specifies visitor-level or visit-level denominator.
3. Reject Net Revenue questions without an explicit report as-of date.
4. Call only `GovernedAnalyticsTools`; the orchestrator contains no direct SQL path.
5. Calculate like-for-like comparison changes by segment when a comparison period is requested.
6. For investigation questions, retrieve metric health plus campaign/release context and synthesize a bounded classification.
7. Return the result, definition, health, evidence, sources, limitations, recommendation, and execution trace.

## Business-answer presentation

- The headline table shows only the cleaned/approved metric value;
- Raw-versus-filtered values remain available in audit evidence, not beside the headline;
- A Data Quality Flag table appears immediately below the headline when an adjustment or block applies;
- Each flag states the affected start/end dates, situation, treatment, and blocked/adjusted quantity when measurable;
- Suspected-bot traffic uses treatment `blocked_and_excluded_from_headline`.
- Confirmed fraud is excluded from commercial headlines; suspected/unconfirmed fraud stays included and appears in a separate policy flag with a Risk-review recommendation.

## Investigation classifications

| Classification | Meaning |
|---|---|
| `data_quality_unavailable` | A known source failure blocks authoritative interpretation |
| `data_quality_adjustment` | A governed adjustment was applied and its impact is disclosed |
| `business_context_candidate` | Campaign/release context overlaps, but causality is not established |
| `insufficient_evidence` | Available evidence does not support assigning a driver |

## Guardrails

- No arbitrary SQL or direct raw/evaluator access;
- No silent choice between visitor and visit conversion;
- No finalized Net Revenue without a report as-of time;
- No causal claim from temporal overlap alone;
- An unavailable metric returns `answer_status: abstained`;
- Every successful answer includes an inspectable workflow trace.

## Current interface boundary

The parser is deterministic and supports the scoped English/Chinese question patterns covered by tests. It is not presented as general natural-language understanding. Unsupported or ambiguous phrasing should fail visibly instead of being guessed.
