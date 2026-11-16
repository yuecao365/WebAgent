# Working rules

Read `DESIGN.md` before starting. Record decisions in `DECISIONS.md`.

## Environment

- Windows 11, PowerShell. Python 3.12 managed with uv (`uv sync`, `uv run`).
- C: has little free space. Docker data, images, datasets and caches go on D:.
  Before pulling any image or downloading anything over 1 GB, tell the user the
  name, source, size and destination, and wait for a yes.
- Only the local WebArena sites are used. Never sign in to or act on real websites
  or real accounts.
- Set `BH_TELEMETRY=0` for every run of browser-harness.

## Secrets and spending

- API keys live only in `.env` (git-ignored). Never print, log, commit or paste a
  key value. `.env.example` lists variable names with empty values.
- Before every commit, check the diff for anything that looks like a key
  (`sk-`, `hf_`, long tokens).
- Every script that calls a paid API logs its cost to `results/spend.jsonl` and
  `results/spend.md`, and stops before the cap in `BUDGET_USD` is exceeded.
- Do not start a paid run beyond a small smoke test (about 5 tasks) without the
  user's go-ahead. State the expected task count and cost first.

## Code

- No agent framework (no LangChain, LangGraph, CrewAI and similar). The harness is
  written here.
- Build on browser-harness (MIT). Prefer depending on it and wrapping it; copy and
  modify a module only when wrapping is not enough, and keep its license notice.
- Every context and memory component has a switch, off by default. Experiments are
  configs that turn switches on. A switch may become on by default only after a
  comparison run shows it helps; record the runs and numbers in `DECISIONS.md`.
  The switch stays, so a config can still turn it off.
- Keep modules small and typed. Docstrings and comments say why, not what.
- Model calls go through one module (`harness/llm.py`) that handles retries,
  structured output, token and cost accounting.
- Results of a run go to `results/<date>_<name>/` with the config, per-task records
  and a summary; never overwrite an earlier run.

## Tests

- `uv run pytest` runs offline: no network, no API calls, no browser. Use fixtures
  (saved accessibility trees, saved event logs, fake model responses).
- `uv run ruff check` and `uv run ruff format --check` pass before a commit.

## Git

- Commit locally when a step is finished and tests pass, with a clear message.
- Never push, open a pull request or change remotes unless the user says so.

## Writing

- Code, comments, commit messages and README in English.
- `DECISIONS.md` in Chinese: one entry per decision with the date, what was decided
  and why, and what was rejected.
- Report results as measured. If something failed or was skipped, say so.
