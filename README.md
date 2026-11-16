# browser-agent

A browser agent that completes web tasks in a real Chromium browser, built on
[browser-harness](https://github.com/browser-use/browser-harness) and evaluated on
[WebArena Verified](https://github.com/ServiceNow/webarena-verified) (shopping-admin).

See `DESIGN.md` for the design, `AGENTS.md` for the working rules and
`scripts/setup_webarena.md` for the local environment.

## Quick start

```powershell
# uv caches and the managed Python go on D: (C: is short on space)
$env:UV_CACHE_DIR = "D:\uv-cache"; $env:UV_PYTHON_INSTALL_DIR = "D:\uv-python"
uv sync
uv run pytest            # offline: no network, API or browser
uv run ruff check; uv run ruff format --check
```

## Running against the local site

1. Set up and start the shopping-admin container: `scripts/setup_webarena.md`.
2. Check the environment without calling a model:
   `uv run python scripts/check_env.py`
3. Copy `.env.example` to `.env` and fill in the model, key, prices and `BUDGET_USD`.
4. Run a config:

   ```powershell
   uv run python scripts/run_eval.py --config configs/smoke.json
   ```

   Results go to `results/<date>_<name>/`; every model call is logged in
   `results/spend.jsonl`. A run of more than 5 tasks needs `--confirm-paid`.
   `--dev-cache` replays stored model replies for unchanged requests, so repeating a
   task while developing costs nothing; do not use it for results that count.

## Switches

A config turns components on under `"switches"`; all are off by default.

| Switch | Effect |
|---|---|
| `prune_observation` | Show only what can be acted on and what can be read; one line per table row |
| `truncate_lists` | Show the first rows/options of a long run and count the rest |
| `diff_observation` | While the page stays the same document, show only the changed lines |
| `multi_action` | Run every tool call of a reply, stopping at a failure or a new page |

`configs/smoke.json` runs with every switch off; `configs/smoke_optimized.json` turns
on pruning, truncation and multi-action. The prompt layout itself (task, append-only
history of calls with one-line results, then a tail with the current page, the
working note and the step count) is not a switch.

## Layout

```
src/browser_agent/
  browser/   session (browser-harness), observation, actions, network (HAR)
  harness/   loop, tools, llm (the only module that calls a model), events
  context/   observe (pruned, truncated and diff views of a page)
  eval/      webarena (tasks, reset, evaluator, subset), runner
configs/     subset.json (60 tasks), smoke.json, smoke_optimized.json, baseline.json
scripts/     setup notes, check_env.py, build_subset.py, run_eval.py
tests/       offline tests with saved fixtures
```
