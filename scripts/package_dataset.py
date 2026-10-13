#!/usr/bin/env python3
"""Build a versioned, collaborator-ready synthetic dataset archive."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "synthetic-ecommerce-v1.zip"
RAW_DIR = ROOT / "data" / "raw"
RAW_DB = ROOT / "data" / "ecommerce_raw.sqlite"
SUMMARY = ROOT / "ground_truth" / "generation_summary.json"


def main() -> None:
    required = [RAW_DB, SUMMARY, *sorted(RAW_DIR.glob("*.csv"))]
    if not RAW_DB.exists() or not SUMMARY.exists() or len(required) <= 2:
        raise SystemExit("Generate the dataset first with: python3 generator/generate_data.py")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    readme = """Synthetic Ecommerce Dataset v1

This bundle contains entirely synthetic data generated with seed 42.
It contains no customer or company data.

Regenerate from source:
  python3 generator/generate_data.py

Repository:
  https://github.com/tanmiemie/auditable-ecommerce-analytics-agent
"""
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in required:
            archive.write(path, path.relative_to(ROOT))
        archive.writestr("DATASET_README.txt", readme)

    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(f"Created {OUT}")
    print(f"SHA-256 {digest}")


if __name__ == "__main__":
    main()
