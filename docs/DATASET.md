# Synthetic Ecommerce Dataset

## Recommended distribution model

The repository stores the generator, contracts, and validation code. A versioned GitHub Release stores a ready-to-use compressed dataset. This design keeps Git history small while supporting both reproducibility and fast onboarding.

## Dataset contents

The `synthetic-ecommerce-v1.zip` release asset contains:

- `data/raw/*.csv`: source-style tables for users, identity, sessions, events, orders, refunds, campaigns, releases, and experiments;
- `data/ecommerce_raw.sqlite`: the same raw tables in a query-ready SQLite database;
- `ground_truth/generation_summary.json`: seed, coverage, and row counts;
- `DATASET_README.txt`: provenance and regeneration instructions.

Evaluator-only incident truth and expected answers are intentionally omitted from the download bundle. They are generated locally for testing but should not be used as Agent input.

## Provenance

- Entirely synthetic; no customer or company data is included.
- Deterministic seed: `42`.
- Coverage: 2026-01-01 through 2026-04-30.
- Scale: 10,000 users, 71,279 sessions, 320,986 events, and 5,593 orders.
- Purpose: analytics engineering, data-quality testing, agent evaluation, and portfolio demonstration.

## Rebuild locally

```bash
python3 generator/generate_data.py
python3 validation/validate_generated_data.py
```

## Build the release asset

After generation:

```bash
python3 scripts/package_dataset.py
```

The command writes `dist/synthetic-ecommerce-v1.zip` and prints its SHA-256 checksum.

## Usage boundary

The dataset deliberately contains quality failures, suspected automation, confirmed-fraud labels, and legitimate business changes. It should not be treated as representative of real-world prevalence, model performance, or commercial outcomes.
