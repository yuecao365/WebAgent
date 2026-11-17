# 2026-11-16_learn_c_high

Model: `gpt-6-luna`. Tasks: 15. Success: 14/15 (93%).

| Mean per task | Value |
|---|---:|
| Tokens | 23545 |
| USD | 0.0023 |
| Seconds | 36.2 |
| Steps | 6.9 |

Total: $0.0340, 353181 tokens. Finish reasons: {'finished': 15}.

## Tokens

Input: 312 uncached, 113030 read from cache, 232109 written to cache. Output: 7730, of which reasoning 4937. Cache hit rate: 33%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| observation | 9915 | 43% |
| tools | 6286 | 27% |
| system | 5350 | 23% |
| history | 1047 | 5% |
| notes | 211 | 1% |
| task | 195 | 1% |
| status | 26 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 344 | 248 | learn | yes | 9050 | 29% | 0.0009 | 12.3 | 3 | finished |
| 213 | 249 | learn | yes | 47326 | 31% | 0.0051 | 80.3 | 12 | finished |
| 704 | 268 | learn | yes | 19455 | 40% | 0.0018 | 29.3 | 7 | finished |
| 107 | 270 | learn | yes | 25175 | 41% | 0.0022 | 33.6 | 9 | finished |
| 709 | 271 | learn | yes | 17609 | 37% | 0.0016 | 23.7 | 6 | finished |
| 11 | 288 | learn | yes | 27291 | 34% | 0.0027 | 36.9 | 8 | finished |
| 208 | 364 | learn | yes | 10775 | 24% | 0.0011 | 12.3 | 3 | finished |
| 198 | 366 | learn | yes | 22631 | 23% | 0.0023 | 27.8 | 5 | finished |
| 128 | 1002 | learn | yes | 28868 | 27% | 0.0029 | 44.1 | 7 | finished |
| 772 | 246 | learn | no | 19749 | 40% | 0.0018 | 31.6 | 7 | finished |
| 458 | 247 | learn | yes | 11282 | 23% | 0.0012 | 19.3 | 3 | finished |
| 470 | 257 | learn | yes | 23777 | 32% | 0.0022 | 41.9 | 7 | finished |
| 486 | 275 | learn | yes | 16832 | 46% | 0.0013 | 36.3 | 7 | finished |
| 492 | 280 | learn | yes | 33274 | 27% | 0.0033 | 47.1 | 8 | finished |
| 496 | 284 | learn | yes | 40087 | 35% | 0.0036 | 66.4 | 12 | finished |

## Fallbacks

Tasks: 15, of which 14 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| New tab opened by an action, closed | 1 | 1 | 1/1 | 1/1 |
| Page shown with a cut list or table | 15 | 8 | n/a | 8/8 |
| Cut list followed by read_page(find/section) | 1 | 1 | 1/1 | 1/1 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Tool call failed, error returned; Returned to the last stable URL; Clicked by script: element has no box; Native dialog accepted; Long tool result cut; Page read retried: page busy; Settle ran out of time; Stuck hint given; Task ended as stuck (forced finish); Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Skill steps loaded (load_skill); run_skill: gate passed, code run; run_skill: gate rejected, nothing run; Skill code stopped at a step; Skill steps handed to the model to follow; Lesson shown on a matching page; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Browser not clean before the task, repaired; Browser restarted before the task; Harness error ended the task.
