#!/usr/bin/env python3
"""Run the Recall Pulse Warehouse.

    python run.py
    python run.py --json data/raw/openfda_food_enforcement_sample.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.pipeline import RecallPulsePipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Recall Pulse Warehouse")
    parser.add_argument("--json", type=Path, default=None, help="Optional openFDA JSON array")
    args = parser.parse_args()

    result = RecallPulsePipeline(raw_json=args.json).run()
    print(f"source          : {result.source}")
    print(f"silver recalls  : {result.silver_recalls:,}")
    print(f"quality gates   : {'PASS' if result.quality_passed else 'FAIL'}")
    print(f"briefing memo   : {result.report_path}")
    print("figures:")
    for p in result.figure_paths:
        print(f"  - {p}")
    print("headline findings:")
    for k, v in result.headline.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
