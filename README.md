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

## Layout

```
src/browser_agent/
  browser/   session (browser-harness), observation, actions, network (HAR)
  harness/   loop, tools, llm (the only module that calls a model), events
  eval/      webarena (tasks, reset, evaluator, subset), runner
configs/     subset.json (60 tasks), smoke.json, baseline.json
scripts/     setup notes, check_env.py, build_subset.py, run_eval.py
tests/       offline tests with saved fixtures
```
