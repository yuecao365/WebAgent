# Browser agent: harness, context and memory, evaluation

A browser agent that completes web tasks in a real Chrome, built on
[browser-harness](https://github.com/browser-use/browser-harness) (MIT). The work is
in three parts:

1. **Harness**: the agent loop, tools, budgets, recovery and execution.
2. **Context and memory**: short-term context inside one task, and long-term memory
   carried across tasks.
3. **Evaluation**: WebArena Verified tasks that show what each part changes in
   success rate, tokens, cost and time.

Retrieval is a small component of memory, not a focus.

## 1. Harness

- **Tools**: `click`, `type`, `goto`, `scroll`, `read_page`, `run_skill`,
  `write_note`, `finish`. Tool calling with strict schemas.
- **Loop control**: budgets on steps, tokens, wall time and dollars. When a budget
  runs out, the run is forced to finish. Stuck detection (the same action repeated,
  or the page unchanged for several steps) triggers a change of strategy.
- **Recovery**: a failed tool call returns its error to the model to retry. After
  repeated failures the agent goes back to the last stable page.
- **Verifier sub-agent**: separate context from the main agent; it sees only the
  outcome and decides whether a candidate skill holds.
- **Sandboxed execution**: model-written skill code runs in a restricted namespace
  that exposes only the browser primitives.
- **Event log**: every step is appended to a log; any task can be replayed from it.

## 2. Context and memory

### Short-term (inside one task)

| Problem | Approach |
|---|---|
| The accessibility tree is long | Keep interactive elements and visible text, truncate long lists; between steps send only what changed |
| History grows | Keep the last N steps in full, summarize older ones; truncate long tool output and say so |
| The model loses track | A working note (goal, done, next) the model maintains, kept in a fixed place in the prompt |
| Cost | Stable prefix, changing tail, so prompt caching applies |

### Long-term (across tasks)

| Kind | What it stores | How it is written | How it is used |
|---|---|---|---|
| Procedural: skills | Parameterized Python functions, each step with a check | Induced from a successful episode, rerun by the verifier with other parameters, stored only if it passes | On a match, replayed with no model calls |
| Semantic: site facts | Facts such as where a page is or how a form behaves | Extracted after a task, deduplicated and merged | Injected when the agent enters the site |
| Episodic: lessons | What went wrong on a page before | Written after reflecting on a failed episode | Shown when the agent reaches that page again |

**Maintenance**: version, use count and success rate per item. Skills with a low
success rate are retired. When a page changes and a step's check fails, only that
step is re-explored and the skill is patched.

## 3. Evaluation

- **Data**: WebArena Verified, shopping-admin site, 15–20 templates with 3–5 tasks
  each, about 60 tasks. The first task of each template is used for learning, the
  rest for testing.
- **Metrics**: success rate, tokens per task, dollars per task, seconds per task,
  steps per task. One run per arm.

| Experiment | Arms | Question |
|---|---|---|
| E1 context | full history / history compaction / compaction + observation pruning + working note | How many tokens context management saves, and whether success drops |
| E2 memory | none / skills only / skills + site facts + lessons | How much memory speeds up and cheapens tasks from a seen template |
| E3 drift | page changed by injected CSS/JS (button text or position): no repair / step repair | Whether memory keeps working when the site changes |

Every task produces a trace. Failed tasks are classified (element not found, wrong
page, finished early, over budget).

Every context and memory component has a switch, off by default. An experiment is a
config that turns switches on, so one codebase produces E1–E3.

## 4. Stack

| Layer | Choice |
|---|---|
| Language, env | Python 3.12, uv |
| Browser | browser-harness, Chrome DevTools Protocol |
| Model | Official provider SDK; tool calling, structured output, prompt caching. Model set in `.env` |
| Harness | Written in this repo, no agent framework |
| Memory store | Skills as Python files; metadata, site facts and lessons in SQLite |
| Retrieval | BM25 over task text |
| Eval environment | WebArena Verified in Docker (Docker Desktop + WSL2, data on D:), official evaluator |
| Drift injection | CDP `Page.addScriptToEvaluateOnNewDocument` |
| Tracing | OpenTelemetry, viewed in Phoenix |
| Dashboard | Streamlit |
| MCP (optional) | Official MCP Python SDK, exposing the skill library as tools |
| Quality | pytest, ruff |

## 5. Layout

```
src/browser_agent/
  browser/     session, observation, actions (wraps browser-harness)
  harness/     loop.py, tools.py, llm.py (calls, retries, token/cost accounting),
               sandbox.py, events.py (event log, replay)
  context/     observe.py (pruning, diff), history.py (compaction), notes.py,
               layout.py (cache-friendly prompt order)
  memory/      skills/ (capture, induce, verify, store, replay, repair),
               site_facts.py, lessons.py, retrieve.py
  eval/        webarena.py (tasks, reset, evaluator), runner.py, drift.py,
               failures.py
  tracing.py
  mcp_server.py
memory_store/  learned skills and facts
dashboard/     app.py
scripts/       setup notes, run_eval.py, demo_drift.py
configs/       task subset, experiment configs
results/       run outputs, spend log
tests/         offline tests
```

## 6. Milestones

1. WebArena Verified shopping-admin running locally; harness loop, tools and
   accounting; a baseline run.
2. Short-term context: pruning, diff, compaction, working note, prompt layout; E1.
3. Long-term memory: skills (induce, verify, replay), site facts, lessons; E2.
4. Drift injection and step repair; E3; traces, failure classes, dashboard. MCP if
   time allows.

## 7. Open items

- Model and budget cap: the user chooses.
- Running WebArena under Windows + WSL2 is unproven. Check it first; if it fails,
  run Docker natively inside WSL2.

## References

- browser-harness: https://github.com/browser-use/browser-harness
- WebArena Verified: https://github.com/ServiceNow/webarena-verified
- Related work: AWM https://arxiv.org/abs/2409.07429 ; ASI
  https://arxiv.org/abs/2504.06821 ; WebXSkill https://arxiv.org/abs/2604.13318
