# Building an Analytics Agent That Knows When Not to Answer

## The problem

An ecommerce metric can move because customer behavior changed, a campaign launched, tracking failed, sessions were counted differently, automated traffic arrived, or fraudulent orders entered the system. A SQL query can be syntactically correct and still produce a misleading business conclusion.

I built this project to test a narrower and more useful product promise: within approved metric definitions and data boundaries, can an analytics agent produce an auditable answer and stop when the evidence is unreliable?

## My role

I defined the MVP boundary, made the business-policy decisions with explicit human checkpoints, implemented the trusted data and governed query layers, built the deterministic Agent workflow, and created the evaluation loop. Every batch records its sources, decisions, tests, limitations, and commit in the development log.

## The environment

The project uses a reproducible 120-day synthetic ecommerce dataset with 10,000 users, 71,279 raw sessions, 320,986 raw events, and 5,593 orders. The generator injects known data incidents and legitimate business changes so the Agent must distinguish cleanup from business truth.

Representative scenarios include scraper traffic, duplicated SDK events, a five-minute session timeout, missing iOS checkout events, an Android event rename, payment-velocity fraud, a real Paid Social campaign, and a real promotion.

Evaluator-only incident definitions stay under `ground_truth/` and are never available to the Agent.

## Product decisions before code

The most consequential work was defining what each number means:

- Visits use a canonical 30-minute inactivity rule;
- Visitor and Visit conversion remain separate metrics;
- App identity may stitch pre-login behavior retroactively, while Web identity respects `effective_from`;
- Confirmed fraud is excluded, but suspected/unconfirmed fraud remains in commercial metrics and receives a Risk-review flag;
- Employee orders remain included and are separately flagged;
- Refunds reduce Net Revenue when requested;
- Net Revenue is finalized only after the 30-day refund window closes;
- Missing client checkout events make the dependent metric unavailable; server orders cannot be used to invent those events.

These decisions are versioned in semantic and data-quality contracts rather than hidden inside prompts.

## System design

The trusted layer deterministically deduplicates events, preserves conflicting-duplicate evidence, reconstructs canonical Visits, applies identity policy, resolves order snapshots, standardizes event names, and creates health windows. Raw rows remain available for audit.

The Agent never receives arbitrary database access. Governed tools whitelist metrics and dimensions, parameterize filters, enforce data coverage and health status, and return the exact executed SQL. The orchestrator validates the question, selects a governed operation, compares periods, retrieves bounded context, and produces a cleaned headline plus flags and limitations.

The system separates three ideas that are often mixed together:

1. a cleaned business metric;
2. audit evidence showing what was adjusted;
3. investigation context that may suggest, but not prove, a cause.

## A failure that improved the product

The first golden evaluation passed seven of eight cases. The Agent correctly excluded confirmed fraud from Revenue but classified a payment-velocity window as “insufficient evidence” and failed to recommend Risk review.

I kept the failure visible, added a governed shared-device/payment-token evidence tool, and introduced a bounded `security_review_candidate` path. A separate regression fixture proves that an unconfirmed signaled order remains in Gross Revenue while receiving a Fraud Policy Flag. The Agent still cannot confirm fraud or take action against an account.

The golden suite then improved from 7/8 to 8/8 without changing the approved inclusion policy.

## Results

- 37 unit and regression tests pass;
- 8/8 golden scenarios pass;
- 896 duplicate event rows are deterministically removed;
- 375 suspected-bot Visits are excluded from the Jan 10–12 Web headline;
- Four iOS 6.1.0 checkout-outage days produce a user-facing unavailable answer;
- Out-of-coverage requests abstain rather than return zero or extrapolated data;
- Every metric response includes its executed parameterized SQL and trace.

These are results on a fixed synthetic environment. They establish regression behavior, not production accuracy.

## What I would do next

Before a production pilot, I would connect a real warehouse with role-based access, define freshness thresholds with metric owners, add production trace sampling, expand human-labeled scenarios, and calibrate any semantic evaluator before using it as a release gate. I would also add fraud-label effective timestamps, inventory history, and referral/navigation data to close current evidence gaps.

The current MVP is intentionally deterministic and narrow. That constraint is part of the design: it makes the Agent's claims inspectable and gives the team a concrete foundation for deciding where additional model flexibility is worth the risk.
