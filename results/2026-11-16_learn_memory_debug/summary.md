# 2026-11-16_learn_memory_debug

Model: `gpt-6-luna`. Tasks: 15. Success: 11/15 (73%).

| Mean per task | Value |
|---|---:|
| Tokens | 37236 |
| USD | 0.0037 |
| Seconds | 36.4 |
| Steps | 7.5 |

Total: $0.0552, 558544 tokens. Finish reasons: {'finished': 15}.

## Tokens

Input: 339 uncached, 138376 read from cache, 416468 written to cache. Output: 3361, of which reasoning 422. Cache hit rate: 25%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| history | 13791 | 37% |
| observation | 10169 | 27% |
| tools | 7573 | 20% |
| system | 5123 | 14% |
| notes | 173 | 0% |
| task | 159 | 0% |
| status | 25 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 344 | 248 | learn | yes | 21680 | 26% | 0.0021 | 16.6 | 5 | finished |
| 213 | 249 | learn | no | 40546 | 28% | 0.0039 | 29.1 | 9 | finished |
| 704 | 268 | learn | yes | 12490 | 23% | 0.0013 | 18.2 | 3 | finished |
| 107 | 270 | learn | yes | 12399 | 23% | 0.0013 | 21.3 | 3 | finished |
| 709 | 271 | learn | yes | 24964 | 28% | 0.0024 | 20.3 | 6 | finished |
| 11 | 288 | learn | yes | 38115 | 26% | 0.0037 | 27.3 | 8 | finished |
| 208 | 364 | learn | yes | 14835 | 19% | 0.0016 | 23.4 | 3 | finished |
| 198 | 366 | learn | yes | 25664 | 22% | 0.0026 | 33.7 | 5 | finished |
| 128 | 1002 | learn | yes | 53602 | 21% | 0.0055 | 60.9 | 9 | finished |
| 772 | 246 | learn | no | 137365 | 27% | 0.0133 | 92.7 | 27 | finished |
| 458 | 247 | learn | no | 25534 | 22% | 0.0026 | 24.6 | 5 | finished |
| 470 | 257 | learn | no | 11469 | 25% | 0.0011 | 12.4 | 3 | finished |
| 486 | 275 | learn | yes | 11238 | 25% | 0.0011 | 32.9 | 3 | finished |
| 492 | 280 | learn | yes | 55545 | 23% | 0.0056 | 47.1 | 10 | finished |
| 496 | 284 | learn | yes | 73098 | 25% | 0.0071 | 85.9 | 14 | finished |

## Fallbacks

Tasks: 15, of which 11 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Arguments rejected by the schema, or unknown tool | 4 | 4 | 4/4 | 4/4 |
| Tool call failed, error returned | 1 | 1 | 1/1 | 0/1 |
| Page shown with a cut list or table | 15 | 5 | n/a | 4/5 |
| Cut list followed by read_page(find/section) | 1 | 1 | 1/1 | 1/1 |
| Skill steps loaded (load_skill) | 5 | 5 | n/a | 4/5 |
| run_skill: gate passed, code run | 3 | 3 | 3/3 | 3/3 |
| run_skill: gate rejected, nothing run | 2 | 2 | n/a | 2/2 |
| Skill steps handed to the model to follow | 2 | 2 | 2/2 | 2/2 |
| Lesson shown on a matching page | 44 | 14 | n/a | 11/14 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Returned to the last stable URL; Clicked by script: element has no box; Native dialog accepted; Long tool result cut; New tab opened by an action, closed; Page read retried: page busy; Settle ran out of time; Stuck hint given; Task ended as stuck (forced finish); Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Skill code stopped at a step; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Browser not clean before the task, repaired; Browser restarted before the task; Harness error ended the task.
