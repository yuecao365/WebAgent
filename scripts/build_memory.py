"""Build long-term memory from the traces of learn runs.

    uv run python scripts/build_memory.py --config configs/memory_learn_v1.json --stage induce
    uv run python scripts/build_memory.py --config configs/memory_learn_v1.json --stage verify

"induce" makes the model calls (paid) and writes memory_store/<date>_<name>/. "verify"
replays the candidate skill code on the local site and keeps code only where every
replay passes; it needs the site running and makes one small model call per replay.
Both log their spend to results/spend.jsonl and stop before BUDGET_USD is exceeded.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from browser_agent.harness.llm import LLMClient, Pricing, client_from_env
from browser_agent.memory.pipeline import (
    LOG_FILE,
    BuildConfig,
    BuildLog,
    build_dir,
    derive_build,
    git_commit,
    induce,
    remerge_facts,
)


def client(config: BuildConfig, root: Path) -> LLMClient:
    pricing = None
    if config.price_input_per_mtok is not None and config.price_output_per_mtok is not None:
        pricing = Pricing(input=config.price_input_per_mtok, output=config.price_output_per_mtok)
    llm = client_from_env(
        root / "results",
        api="responses",
        effort=config.reasoning_effort,
        model=config.model,
        pricing=pricing,
        max_output_tokens=config.max_output_tokens,
    )
    return llm.labelled(run=f"memory_build_{config.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--stage", choices=["induce", "verify", "remerge-facts"], required=True)
    parser.add_argument(
        "--build",
        type=Path,
        help="verify: the build to continue; remerge-facts: the build to derive from",
    )
    args = parser.parse_args(argv)
    root = Path.cwd()
    load_dotenv(root / ".env")
    config = BuildConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    llm = client(config, root)
    if args.stage == "induce":
        store = induce(config, root, llm, build_dir(root, config.name))
        print(f"build: {store.root}")
    elif args.stage == "remerge-facts":
        if args.build is None:
            parser.error("--stage remerge-facts needs --build, the build to derive from")
        target = build_dir(root, config.name)
        store = derive_build(
            args.build,
            target,
            "site facts merged again so that all of them fit under the prefix cap",
            git_commit(root),
        )
        fits = remerge_facts(store, llm, BuildLog(target / LOG_FILE))
        store.close()
        print(f"build: {target}; all site facts fit under the cap: {fits}")
    else:
        from browser_agent.memory.verify import verify_build

        if args.build is None:
            parser.error("--stage verify needs --build")
        verify_build(config, root, llm, args.build)
    llm.ledger.write_summary()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
