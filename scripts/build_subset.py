"""Write configs/subset.json from the installed WebArena Verified dataset.

    uv run python scripts/build_subset.py

The selection rules live in browser_agent.eval.webarena.build_subset; this script
only fixes their parameters, so the file can be rebuilt and compared at any time.
"""

from __future__ import annotations

import json
from pathlib import Path

from browser_agent.eval.webarena import build_subset, dataset_tasks

# About the mix of the 176 solvable shopping-admin tasks: 47% retrieve, 43% mutate,
# 10% navigate. 15 templates of 4 tasks give 15 learn and 45 test tasks.
QUOTAS = {"retrieve": 7, "mutate": 6, "navigate": 2}
PER_TEMPLATE = 4
SEED = 0


def main() -> None:
    subset = build_subset(dataset_tasks(), QUOTAS, per_template=PER_TEMPLATE, seed=SEED)
    path = Path(__file__).resolve().parents[1] / "configs" / "subset.json"
    path.write_text(json.dumps(subset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    splits = [task["split"] for task in subset["tasks"]]
    print(
        f"{path}: {len(subset['templates'])} templates, {len(splits)} tasks "
        f"({splits.count('learn')} learn, {splits.count('test')} test)"
    )


if __name__ == "__main__":
    main()
