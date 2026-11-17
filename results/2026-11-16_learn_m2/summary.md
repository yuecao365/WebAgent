# 2026-11-16_learn_m2

Model: `gpt-6-luna`. Tasks: 15. Success: 10/15 (67%).

| Mean per task | Value |
|---|---:|
| Tokens | 32379 |
| USD | 0.0032 |
| Seconds | 34.5 |
| Steps | 6.7 |

Total: $0.0480, 485682 tokens. Finish reasons: {'finished': 15}.

## Tokens

Input: 300 uncached, 120020 read from cache, 362519 written to cache. Output: 2843, of which reasoning 224. Cache hit rate: 25%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| history | 11659 | 36% |
| observation | 9031 | 28% |
| tools | 6665 | 21% |
| system | 4509 | 14% |
| task | 152 | 0% |
| notes | 152 | 0% |
| status | 21 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 344 | 248 | learn | yes | 13106 | 22% | 0.0013 | 12.3 | 3 | finished |
| 213 | 249 | learn | no | 72745 | 29% | 0.0069 | 76.9 | 16 | finished |
| 704 | 268 | learn | no | 27545 | 31% | 0.0026 | 25.2 | 7 | finished |
| 107 | 270 | learn | yes | 12914 | 22% | 0.0014 | 21.3 | 3 | finished |
| 709 | 271 | learn | yes | 25354 | 28% | 0.0024 | 22.3 | 6 | finished |
| 11 | 288 | learn | yes | 33306 | 26% | 0.0033 | 24.9 | 7 | finished |
| 208 | 364 | learn | yes | 19764 | 22% | 0.0020 | 13.3 | 4 | finished |
| 198 | 366 | learn | yes | 21479 | 20% | 0.0022 | 23.6 | 4 | finished |
| 128 | 1002 | learn | no | 82935 | 21% | 0.0085 | 91.3 | 13 | finished |
| 772 | 246 | learn | no | 16184 | 26% | 0.0016 | 13.4 | 4 | finished |
| 458 | 247 | learn | yes | 15429 | 18% | 0.0016 | 17.9 | 3 | finished |
| 470 | 257 | learn | no | 46239 | 28% | 0.0044 | 52.4 | 10 | finished |
| 486 | 275 | learn | yes | 11626 | 25% | 0.0012 | 28.3 | 3 | finished |
| 492 | 280 | learn | yes | 33975 | 25% | 0.0033 | 39.9 | 7 | finished |
| 496 | 284 | learn | yes | 53081 | 24% | 0.0053 | 54.0 | 10 | finished |

## Fallbacks

Tasks: 15, of which 10 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Page shown with a cut list or table | 13 | 6 | n/a | 4/6 |
| Skill steps loaded (load_skill) | 5 | 5 | n/a | 5/5 |
| run_skill: gate passed, code run | 2 | 2 | 2/2 | 2/2 |
| run_skill: gate rejected, nothing run | 2 | 2 | n/a | 1/2 |
| Skill steps handed to the model to follow | 2 | 2 | 2/2 | 1/2 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Tool call failed, error returned; Returned to the last stable URL; Clicked by script: element has no box; Native dialog accepted; Long tool result cut; New tab opened by an action, closed; Page read retried: page busy; Settle ran out of time; Cut list followed by read_page(find/section); Stuck hint given; Task ended as stuck (forced finish); Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Skill code stopped at a step; Lesson shown on a matching page; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Browser not clean before the task, repaired; Browser restarted before the task; Harness error ended the task.
