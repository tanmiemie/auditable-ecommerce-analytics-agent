# Key decision and validation trace

This public log summarizes the decisions that materially change business meaning. The private working repository retains the full batch-by-batch development record and human approvals.

| Decision | Why it matters | Validation |
|---|---|---|
| Keep Visitor and Visit conversion separate | They answer different product questions and use different denominators. | Metric contracts and grouped-query regression tests |
| Reconstruct Web Visits with a 30-minute rule | A five-minute upstream timeout created false Visit growth. | Session-inflation golden case and trusted-layer reconciliation |
| Use platform-specific identity stitching | Retroactive App stitching is useful; Web devices may be shared and require time-bounded matching. | Identity fixtures and trusted-layer tests |
| Exclude confirmed fraud only | Suspicion is not proof and should not silently rewrite revenue. | Confirmed-fraud exclusion plus unconfirmed-signal inclusion regression fixture |
| Keep employee orders and flag them | Their business relevance depends on the analysis; deletion would hide evidence. | Policy flag assertions |
| Apply refunds at request time | This matches the selected finance definition for Net Revenue. | Metric calculation tests |
| Require a 30-day maturity window for final Net Revenue | Recent cohorts may still receive refunds and should not be presented as final. | Explicit report-as-of checks |
| Mark checkout metrics unavailable during missing telemetry | Server orders cannot reconstruct absent client checkout events. | User-visible outage golden case |
| Return SQL, parameters, sources, and trace | Reviewers must be able to reproduce and challenge an answer. | Answer-contract tests |
| Abstain outside data coverage | Zero and extrapolation would both be misleading. | Out-of-coverage golden case |
| Make the Streamlit UI an audit surface, not a separate calculation layer | The frontend must preserve the governed answer contract instead of recomputing or hiding metric logic. | Live browser checks of answered, adjusted, and unavailable states plus UI-helper tests |
| Regenerate synthetic data on first cloud launch | Generated databases stay out of Git, but a fresh deployment must remain reproducible and runnable. | Cold-start smoke test from an empty temporary data directory |

## Release evidence

- Unit and regression tests: 41/41 passing.
- Golden scenarios: 8/8 passing.
- The first evaluation run was 7/8; the fraud-investigation failure was repaired by adding governed evidence retrieval rather than changing the approved inclusion policy.
- Evaluator-only truth remains isolated from the agent-facing runtime.
- Streamlit browser verification covered the default adjusted result, the quality flag, governed SQL and parameters, the execution trace, and an out-of-coverage abstention.

These results apply to the fixed synthetic pilot and should not be interpreted as production accuracy.
