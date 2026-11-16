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

Copy `.env.example` to `.env` and fill it in before any paid run.
