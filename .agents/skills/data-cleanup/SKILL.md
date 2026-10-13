---
name: data-cleanup
description: Audit and clean analytical datasets into a reproducible trusted layer with immutable raw data, explicit contracts, issue-by-issue checks, reconciliation evidence, and regression tests. Use for data cleanup, trusted-layer builds, reusable quality gates, or adding a newly discovered data issue to an existing cleanup workflow.
---

# Data Cleanup

Build a trusted analytical layer without hiding data loss or rewriting raw evidence.

## Non-negotiable invariants

- Keep raw inputs immutable. Apply removals, mappings, exclusions, and repairs only in staging/trusted outputs.
- Never expose evaluator-only or ground-truth artifacts to the system being evaluated.
- Confirm table grain, keys, event time, ingestion time, and downstream metric use before cleaning.
- Separate five outcomes: deterministic repair, governed mapping, provisional data, metric unavailable, and human review.
- Do not convert a suspected condition into a confirmed claim.
- Preserve legitimate business changes; cleanup must not flatten campaigns, promotions, stockouts, releases, or UX effects.
- Every adjustment needs an audit count, lineage back to raw rows, and a deterministic regression test.

## Workflow

1. Inventory sources and contracts. Record row counts, columns, types, candidate keys, grains, timestamps, enums, and relationships.
2. Read [the check registry](references/check-registry.md) completely. Mark every applicable check as pass, adjusted, unavailable, provisional, review, or not applicable with evidence.
3. Profile before transforming. Measure duplicates, nulls, enum drift, orphans, fanout, time lag, volume shifts, and affected segments.
4. Build the trusted layer atomically. Prefer a temporary output followed by replacement only after successful completion.
5. Reconcile raw to trusted. Report retained, adjusted, excluded, unattributed, unavailable, provisional, and review counts plus metric impact.
6. Test observable behavior, including at least one positive failure fixture for fragile rules. A test that only checks a field exists is insufficient when a realistic anomaly can be injected.
7. Preserve a trace containing inputs, decisions, files, commands, actual test results, limitations, and the human checkpoint.

## Adding a new checking issue

When a new data problem appears, the cleanup is not complete after a one-off fix. In the same change:

1. add a stable check ID and procedure to `references/check-registry.md`;
2. define detection evidence and severity;
3. define whether to repair, map, exclude, mark provisional/unavailable, preserve, or review;
4. add audit output and lineage;
5. add a deterministic regression test or explain why one cannot be built;
6. update reconciliation and development trace.

Do not automatically make a dataset-specific anomaly universal. Generalize only the invariant; keep dataset-specific thresholds, mappings, and dates in that project's contracts.

## Delivery gate

Do not call cleanup complete until:

- every applicable registry item has a recorded status;
- critical/high contract violations are either resolved or explicitly accepted;
- metric health prevents answers from unavailable data;
- recent/provisional periods expose an as-of timestamp;
- normal-business negative controls remain present;
- tests pass from a clean rebuild;
- reconciliation is ready for owner review.

