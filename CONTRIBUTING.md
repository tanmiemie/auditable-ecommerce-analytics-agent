# Contributing

Contributions are welcome when they preserve the project's core guarantees: explicit semantics, deterministic metric computation, inspectable evidence, and safe abstention.

Before opening a pull request:

1. document any business-semantic change in the relevant contract;
2. add or update regression coverage;
3. run the synthetic-data validation, unit tests, and golden evaluation;
4. state whether the change affects metric meaning, data eligibility, or answer behavior;
5. do not expose evaluator-only truth to agent-facing code.

```bash
python3 generator/generate_data.py
python3 validation/validate_generated_data.py
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 evals/run_evals.py
```
