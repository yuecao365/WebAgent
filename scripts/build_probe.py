"""Write configs/probe.json: templates the memory never learned from.

    uv run python scripts/build_probe.py

Four shopping-admin templates that are not in configs/subset.json, three tasks each,
chosen by the same rules as the subset (browser_agent.eval.webarena.build_subset) with
a fixed seed. A template worded nearly like one in the subset is skipped, so that the
probe really is of unseen kinds of task. All twelve tasks are held out: they show what
memory does on templates it has no skill for, and nothing is tuned on them.
"""

from __future__ import annotations

import json
from pathlib import Path

from browser_agent.eval.webarena import build_subset, dataset_tasks

# Two of each type that is available. Outside the subset the only navigate template
# with three tasks is 253, which the evaluator cannot pass, so there is none here.
QUOTAS = {"retrieve": 2, "mutate": 2}
PER_TEMPLATE = 3
SEED = 1


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    subset = json.loads((root / "configs" / "subset.json").read_text(encoding="utf-8"))
    probe = build_subset(
        dataset_tasks(),
        QUOTAS,
        per_template=PER_TEMPLATE,
        seed=SEED,
        exclude_templates=[template["template_id"] for template in subset["templates"]],
        avoid_wording=[template["intent_template"] for template in subset["templates"]],
        splits=("probe", "probe"),
    )
    path = root / "configs" / "probe.json"
    path.write_text(json.dumps(probe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{path}: {len(probe['templates'])} templates, {len(probe['tasks'])} tasks")
    for template in probe["templates"]:
        print(
            f"  {template['template_id']} ({template['task_type']}): {template['intent_template']}"
        )


if __name__ == "__main__":
    main()
