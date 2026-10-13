# Architecture and extension path

## Design goal

The system is designed around a narrow promise: answer approved ecommerce metric questions with inspectable evidence, and stop when the required data is unavailable or unreliable.

## Request path

1. **Semantic contracts** define metric meaning, grain, joins, identity rules, dimensions, quality requirements, and policy boundaries.
2. **Data-quality checks** detect known integrity failures and preserve repair evidence.
3. **Trusted-layer transformations** deterministically deduplicate, canonicalize, reconstruct Visits, and apply eligibility rules without overwriting raw data.
4. **Governed tools** expose only approved metrics, filters, and evidence queries through parameterized read-only SQL.
5. **The orchestrator** parses the bounded request, checks coverage and health, runs the governed operation, adds flags, and returns SQL plus an execution trace.
6. **Evaluation** tests both numeric outputs and policy behavior against isolated golden expectations.

## Trust boundaries

```text
Agent-visible                         Evaluator-only
-------------                         --------------
semantic contracts                    injected incident truth
trusted analytical tables             expected reconciliation
governed metric tools                 golden assertions
approved business context
```

The agent never reads evaluator-only truth. This prevents a passing evaluation from merely reflecting access to the answer key.

## How the design extends

A new metric should be added through the same sequence:

1. define its business meaning and owner;
2. declare grain, numerator, denominator, time basis, dimensions, and exclusions;
3. register health dependencies and unavailable conditions;
4. implement a parameterized governed query;
5. add normal, failure, ambiguity, and out-of-coverage tests;
6. review the answer format and policy flags with the metric owner.

This is reusable application structure, not a claim of production infrastructure scalability. A production pilot would still require a warehouse adapter, authentication and row-level access, orchestration, observability, concurrency testing, freshness SLAs, and a larger human-labeled evaluation set.

## Where an LLM could be added

The deterministic MVP is the safety baseline. An LLM could later assist with broader intent parsing, evidence summarization, and follow-up questions while the metric computation, access policy, availability checks, and SQL execution remain governed. Any such change should be evaluated against the deterministic baseline before release.
