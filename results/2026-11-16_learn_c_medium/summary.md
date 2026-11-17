# 2026-11-16_learn_c_medium

Model: `gpt-6-luna`. Tasks: 15. Success: 14/15 (93%).

| Mean per task | Value |
|---|---:|
| Tokens | 21651 |
| USD | 0.0020 |
| Seconds | 34.8 |
| Steps | 6.7 |

Total: $0.0299, 324768 tokens. Finish reasons: {'finished': 15}.

## Tokens

Input: 303 uncached, 109220 read from cache, 210183 written to cache. Output: 5062, of which reasoning 2522. Cache hit rate: 34%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| observation | 8914 | 42% |
| tools | 5947 | 28% |
| system | 5062 | 24% |
| history | 1007 | 5% |
| task | 185 | 1% |
| notes | 174 | 1% |
| status | 24 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 344 | 248 | learn | yes | 8834 | 29% | 0.0008 | 10.8 | 3 | finished |
| 213 | 249 | learn | yes | 39692 | 36% | 0.0037 | 75.1 | 12 | finished |
| 704 | 268 | learn | yes | 19148 | 41% | 0.0017 | 26.9 | 7 | finished |
| 107 | 270 | learn | yes | 27669 | 42% | 0.0024 | 37.4 | 10 | finished |
| 709 | 271 | learn | yes | 16800 | 38% | 0.0014 | 21.2 | 6 | finished |
| 11 | 288 | learn | yes | 16589 | 31% | 0.0016 | 19.7 | 5 | finished |
| 208 | 364 | learn | yes | 10704 | 24% | 0.0011 | 15.1 | 3 | finished |
| 198 | 366 | learn | yes | 14921 | 26% | 0.0015 | 26.7 | 4 | finished |
| 128 | 1002 | learn | yes | 28857 | 27% | 0.0029 | 43.6 | 7 | finished |
| 772 | 246 | learn | no | 39966 | 36% | 0.0038 | 61.8 | 12 | finished |
| 458 | 247 | learn | yes | 11166 | 23% | 0.0011 | 18.0 | 3 | finished |
| 470 | 257 | learn | yes | 20802 | 31% | 0.0019 | 41.3 | 6 | finished |
| 486 | 275 | learn | yes | 16380 | 47% | 0.0012 | 37.1 | 7 | finished |
| 492 | 280 | learn | yes | 24058 | 32% | 0.0022 | 36.2 | 7 | finished |
| 496 | 284 | learn | yes | 29182 | 35% | 0.0026 | 50.6 | 9 | finished |

## Fallbacks

Tasks: 15, of which 14 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Page shown with a cut list or table | 12 | 7 | n/a | 7/7 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Tool call failed, error returned; Returned to the last stable URL; Clicked by script: element has no box; Native dialog accepted; Long tool result cut; New tab opened by an action, closed; Page read retried: page busy; Settle ran out of time; Cut list followed by read_page(find/section); Stuck hint given; Task ended as stuck (forced finish); Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Skill steps loaded (load_skill); run_skill: gate passed, code run; run_skill: gate rejected, nothing run; Skill code stopped at a step; Skill steps handed to the model to follow; Lesson shown on a matching page; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Browser not clean before the task, repaired; Browser restarted before the task; Harness error ended the task.
