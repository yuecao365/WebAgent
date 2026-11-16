"""Run an experiment config.

uv run python scripts/run_eval.py --config configs/smoke.json
"""

from __future__ import annotations

import sys

from browser_agent.eval.runner import main

if __name__ == "__main__":
    sys.exit(main())
