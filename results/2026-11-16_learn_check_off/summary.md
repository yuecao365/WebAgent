# 2026-11-16_learn_check_off

Model: `gpt-6-luna`. Tasks: 15. Success: 10/15 (67%).

| Mean per task | Value |
|---|---:|
| Tokens | 32165 |
| USD | 0.0031 |
| Seconds | 39.9 |
| Steps | 7.9 |

Total: $0.0462, 482481 tokens. Finish reasons: {'finished': 14, 'stuck': 1}.

## Tokens

Input: 357 uncached, 132080 read from cache, 347131 written to cache. Output: 2913, of which reasoning 187. Cache hit rate: 28%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| observation | 17166 | 54% |
| tools | 7010 | 22% |
| system | 5966 | 19% |
| history | 1346 | 4% |
| task | 238 | 1% |
| notes | 200 | 1% |
| status | 44 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 344 | 248 | learn | yes | 8834 | 29% | 0.0008 | 26.4 | 3 | finished |
| 213 | 249 | learn | no | 43162 | 39% | 0.0036 | 88.6 | 14 | finished |
| 704 | 268 | learn | yes | 17502 | 44% | 0.0014 | 35.5 | 7 | finished |
| 107 | 270 | learn | no | 157848 | 15% | 0.0173 | 80.4 | 19 | stuck |
| 709 | 271 | learn | yes | 16810 | 38% | 0.0014 | 25.2 | 6 | finished |
| 11 | 288 | learn | yes | 16145 | 32% | 0.0015 | 18.4 | 5 | finished |
| 208 | 364 | learn | yes | 10704 | 24% | 0.0011 | 13.0 | 3 | finished |
| 198 | 366 | learn | yes | 14921 | 26% | 0.0015 | 20.4 | 4 | finished |
| 128 | 1002 | learn | no | 47423 | 24% | 0.0047 | 71.7 | 10 | finished |
| 772 | 246 | learn | no | 44920 | 40% | 0.0037 | 49.5 | 15 | finished |
| 458 | 247 | learn | yes | 11162 | 23% | 0.0011 | 17.1 | 3 | finished |
| 470 | 257 | learn | no | 23754 | 32% | 0.0021 | 31.5 | 7 | finished |
| 486 | 275 | learn | yes | 16107 | 48% | 0.0012 | 35.9 | 7 | finished |
| 492 | 280 | learn | yes | 24007 | 32% | 0.0022 | 35.7 | 7 | finished |
| 496 | 284 | learn | yes | 29182 | 35% | 0.0026 | 48.6 | 9 | finished |

## Fallbacks

Tasks: 15, of which 10 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Clicked by script: element has no box | 1 | 1 | n/a | 0/1 |
| Page shown with a cut list or table | 28 | 7 | n/a | 4/7 |
| Cut list followed by read_page(find/section) | 12 | 1 | 9/12 | 0/1 |
| Stuck hint given | 3 | 2 | 1/3 | 0/2 |
| Task ended as stuck (forced finish) | 1 | 1 | 1/1 | 0/1 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Tool call failed, error returned; Returned to the last stable URL; Native dialog accepted; Long tool result cut; Page read retried: page busy; Settle ran out of time; Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Harness error ended the task.
