# Browser agent: harness, context and memory, evaluation

A browser agent that completes web tasks in a real Chrome, built on
[browser-harness](https://github.com/browser-use/browser-harness) (MIT). The work is
in three parts:

1. **Harness**: the agent loop, tools, budgets, recovery and execution.
2. **Context and memory**: short-term context inside one task, and long-term memory
   carried across tasks.
3. **Evaluation**: WebArena Verified tasks that show what each part changes in
   success rate, tokens, cost and time, measured against the run-to-run noise.

## 1. Harness

- **Tools**: `click`, `type`, `goto`, `scroll`, `read_page`, `write_note`, `finish`.
  Tool calling with strict schemas. `load_skill` and `run_skill` exist only while the
  skills switch is on.
- **Loop control**: budgets on steps, tokens, wall time and dollars. When a budget
  runs out, the run is forced to finish. Stuck detection (the same action repeated,
  or the page unchanged for several steps) triggers a change of strategy.
- **Recovery**: a failed tool call returns its error to the model to retry. After
  repeated failures the agent goes back to the last stable page.
- **Environment check**: before every task the browser is checked and repaired (one
  tab, visible, no stored site data, at the start URL); a tab an action opens is
  closed and reported to the model.
- **Verifier**: a model call with its own context that sees only a skill's
  SKILL.md, the parameters, the returned value and the final page, and judges
  whether a replay of the skill's code did what the skill says.
- **Sandboxed execution**: model-written skill code is checked against an allow-list
  of syntax and runs in a namespace that holds only seven browser calls.
- **Event log**: every step is appended to a log; any task can be replayed from it.
  Fallbacks are counted from the log (the fallback ledger).

## 2. Context and memory

### Short-term (inside one task)

| Problem | Approach |
|---|---|
| The accessibility tree is long | Keep interactive elements and visible text, truncate long lists; between steps send only what changed |
| History grows | The history keeps each call and a one-line result, never a page; only the current page is shown, at the end of the prompt; long tool output is cut and says so |
| The model loses track | A working note (goal, done, next) the model maintains, kept in a fixed place in the prompt |
| Cost | Stable prefix, changing tail, so prompt caching applies |

### Long-term (across tasks)

| Kind | What it stores | How it is written | How it is used |
|---|---|---|---|
| Procedural: skills | A folder per skill: `SKILL.md` (frontmatter and numbered steps in plain language) and, only if verified, `skill.py` (the same steps as code) | Induced from the shortest successful learn episode of a template; the code is replayed with the original and with other parameters and judged by the verifier; code that fails any replay is dropped and the skill stays as guidance | Listed in the stable prefix by name, description and URL pattern. `load_skill` returns the steps; `run_skill` runs the code if the gate passes, else returns the steps |
| Semantic: site facts | Short facts such as where a page is, which report or filter gives what, how a form behaves, each with a URL pattern and its source | Extracted from successful learn episodes, merged when they repeat | In the stable prefix, capped at about 800 tokens |
| Episodic: lessons | What went wrong on a page, each with a URL pattern | A reflection call on a failed learn episode that sees only the trace and the binary outcome | Shown in the tail of the prompt only while the current URL matches |

**Skills address elements by locator, never by ref**: role and accessible name,
optionally inside a table row that shows a text or inside a named section. A locator
that matches no element or several is an error.

**Skill code** may call only `goto`, `click`, `type`, `select`, `read`, `check` and
`return_value`. Every call that changes the page is followed by a `check`. Code makes
no model calls and never finishes the task; the model finishes as usual.

**The gate.** `run_skill` executes code only if all of these hold: `skill.py` exists;
the current URL matches the skill's `url_pattern`; every required element resolves to
exactly one element; every precondition holds. Otherwise nothing runs: the result
names the failed check and returns the steps of `SKILL.md`, and the model follows them
itself (guided). Guided is the default path.

**Fallback.** If a step of the code or its check fails, execution stops. The model
gets the failing step, the error, the steps of `SKILL.md` and the current page, and
continues guided. If that fails too, it continues as without memory.

**Where memory comes from.** Only the 15 learn tasks. Skills and site facts come only
from learn episodes the official evaluator scored successful; lessons from failed
ones. Only the success or failure label is used: no expected answer and no evaluator
detail enters memory. Nothing from test or probe tasks enters memory or changes the
harness, prompts, gates or defaults.

**Versioning.** Memory is append-only. An update adds a version; nothing is
overwritten or deleted; a retired version is marked, not removed. Each build lives in
`memory_store/<date>_<name>/` with its provenance (source runs and tasks, models, code
commit) and a manifest of every item's version; metadata (source, version, created,
use count, success count) is in SQLite. A run config names the build it uses. During
test and probe runs memory is frozen and read-only.

**Switches**: `skills`, `site_facts`, `lessons`, all off by default. With all three
off, the requests sent to the model are byte-identical to the baseline's (a test pins
this).

## 3. Evaluation

- **Data**: WebArena Verified, shopping-admin site. 15 templates with 4 tasks each:
  the first task of each template is for learning (15 learn tasks), the other three
  for testing (45 test tasks, held out). A probe set of 4 further templates with 3
  tasks each (12 tasks, held out) shows what memory does on templates it never
  learned from.
- **Metrics**: success, steps, model calls, seconds, tokens and dollars per task.
  Every arm is run 3 times; results are given with their mean and spread.
- **Noise**: the baseline varies by about 5 of 45 tasks between runs. A difference
  is called an improvement only when it is larger than the run-to-run spread.

| Arm | Switches | Task set |
|---|---|---|
| none | memory off (the baseline) | 45 test |
| M1 | skills | 45 test |
| M2 | skills + site facts | 45 test |
| C | no memory, budget-matched: more steps and reasoning effort, chosen on learn tasks so that its cost per task is close to M2's | 45 test |
| M3 | skills + site facts + lessons; 2 runs, if the budget allows | 45 test |
| probe | none and M2 | 12 probe |

The question is not whether memory raises the success rate, but what holds up against
the noise: whether memory is reliable (no wrong replays), where it helps, where it
does not, where it hurts, and whether it beats the budget-matched agent without
memory. Reported per arm, paired per task against none (fixed, broken, stabilized,
unchanged), as paired efficiency differences with bootstrap intervals, and for skills
by gate passes, rejections, code-run success, fallbacks and wrong replays.

Every task produces a trace. Tasks that fail in at least 2 of 3 runs are classified
(wrong page or filter, misread or miscounted, action not done, gave up, not on the
page, over budget, evaluator mismatch, harness error).

Every context and memory component has a switch, off by default. An experiment is a
config that turns switches on, so one codebase produces every arm. A switch becomes on
by default only after a comparison run shows it helps, with the evidence in
`DECISIONS.md`; observation pruning and list truncation are on by default for this
reason (learn-task arms, 2026-11-16).

## 4. Stack

| Layer | Choice |
|---|---|
| Language, env | Python 3.12, uv |
| Browser | browser-harness, Chrome DevTools Protocol |
| Model | Official provider SDK; tool calling, structured output, prompt caching. Model set in `.env` |
| Harness | Written in this repo, no agent framework |
| Memory store | Skill folders (`SKILL.md`, optional `skill.py`); site facts, lessons and item metadata in SQLite; one directory per build |
| Selection | Skills by the model from the list in the prefix; lessons by URL pattern |
| Eval environment | WebArena Verified in Docker (Docker Desktop + WSL2, data on D:), official evaluator |
| Quality | pytest, ruff |

## 5. Layout

```
src/browser_agent/
  browser/     session, observation, actions, environment (wraps browser-harness)
  harness/     loop.py, tools.py, llm.py (calls, retries, token/cost accounting),
               sandbox.py, events.py (event log)
  context/     observe.py (pruning, truncation, diff)
  memory/      locators.py, skill.py (format), skill_api.py (the seven calls),
               building, verification, store and the gate
  eval/        webarena.py (tasks, reset, evaluator), runner.py, fallbacks.py,
               failures.py, aggregate.py, tabscan.py
memory_store/  one directory per memory build
scripts/       setup notes, run_eval.py, report scripts
configs/       task subset, probe set, experiment configs
results/       run outputs, spend log
tests/         offline tests
```

## 6. Milestones

1. WebArena Verified shopping-admin running locally; harness loop, tools and
   accounting; cost controls; defaults chosen on the learn tasks. Done.
2. Fallback ledger, failure classes, new-tab fix, environment check; the baseline on
   the 45 test tasks over 3 runs. Done.
3. Long-term memory: skill format and sandbox, building from learn episodes,
   verification of skill code, the gate and the guided fallback in the loop.
4. Measurement: the arms above on the test and probe tasks; tables from a script.

## 7. Not planned

Outside this project's scope; ideas that come up are added here, not built:

- E3 drift: injected page changes and step repair of skills
- tracing UI (OpenTelemetry, Phoenix)
- dashboard
- MCP server
- screenshots or a vision model
- extra tools
- variants of the check before finishing
- multi-agent setups
- harness self-optimization
- reinforcement learning
- comparisons between models
- history compaction and the E1 context experiment as first drafted (the defaults
  were chosen on the learn-task arms instead)
- a "not present" form of `check` in skill code
- showing the induction call the accessibility tree's own element names, so that
  more skill code passes verification (found in B3: several candidates named
  elements as the pruned page text shows them, which the locators could not resolve)
- repairing skill code that fails a replay
- keeping skill code only when a replay with other parameters passes too (found in
  B7: code kept on the original replay alone returned counts with a filter left unset)

## 8. Open items

- Model and budget cap: the user chooses.

## References

- browser-harness: https://github.com/browser-use/browser-harness
- WebArena Verified: https://github.com/ServiceNow/webarena-verified
- Related work: AWM https://arxiv.org/abs/2409.07429 ; ASI
  https://arxiv.org/abs/2504.06821 ; WebXSkill https://arxiv.org/abs/2604.13318
