# 2026-11-16_learn_check_on

Model: `gpt-6-luna`. Tasks: 15. Success: 11/15 (73%).

| Mean per task | Value |
|---|---:|
| Tokens | 32179 |
| USD | 0.0030 |
| Seconds | 42.7 |
| Steps | 8.9 |

Total: $0.0446, 482683 tokens. Finish reasons: {'finished': 14, 'stuck': 1}.

## Tokens

Input: 399 uncached, 149860 read from cache, 328503 written to cache. Output: 3921, of which reasoning 469. Cache hit rate: 31%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| observation | 15063 | 47% |
| tools | 7802 | 24% |
| system | 6639 | 21% |
| history | 1904 | 6% |
| task | 239 | 1% |
| notes | 227 | 1% |
| status | 43 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 344 | 248 | learn | yes | 13035 | 30% | 0.0012 | 37.0 | 4 | finished |
| 213 | 249 | learn | no | 76728 | 33% | 0.0070 | 127.5 | 21 | finished |
| 704 | 268 | learn | yes | 20575 | 44% | 0.0016 | 37.2 | 8 | finished |
| 107 | 270 | learn | no | 57268 | 18% | 0.0061 | 43.8 | 9 | finished |
| 709 | 271 | learn | yes | 21595 | 36% | 0.0019 | 22.6 | 7 | finished |
| 11 | 288 | learn | yes | 19413 | 33% | 0.0018 | 20.7 | 6 | finished |
| 208 | 364 | learn | yes | 16633 | 23% | 0.0017 | 11.9 | 4 | finished |
| 198 | 366 | learn | yes | 38532 | 17% | 0.0041 | 32.1 | 6 | finished |
| 128 | 1002 | learn | yes | 42615 | 27% | 0.0042 | 64.9 | 10 | finished |
| 772 | 246 | learn | no | 42864 | 42% | 0.0034 | 49.6 | 15 | finished |
| 458 | 247 | learn | yes | 15139 | 25% | 0.0015 | 18.3 | 4 | finished |
| 470 | 257 | learn | yes | 23918 | 32% | 0.0022 | 40.3 | 7 | finished |
| 486 | 275 | learn | yes | 18454 | 49% | 0.0014 | 35.4 | 8 | finished |
| 492 | 280 | learn | yes | 27220 | 33% | 0.0025 | 36.8 | 8 | finished |
| 496 | 284 | learn | no | 48694 | 39% | 0.0040 | 62.6 | 16 | stuck |

## Fallbacks

Tasks: 15, of which 11 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Page shown with a cut list or table | 20 | 8 | n/a | 5/8 |
| Cut list followed by read_page(find/section) | 1 | 1 | 1/1 | 1/1 |
| Stuck hint given | 2 | 1 | 0/2 | 0/1 |
| Task ended as stuck (forced finish) | 1 | 1 | 1/1 | 0/1 |
| Finish intercepted for a check | 14 | 14 | 0/14 | 11/14 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Check before finishing: triggered in 14 tasks, answer changed in 0, 16 extra steps, 11 of those tasks scored successful.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Tool call failed, error returned; Returned to the last stable URL; Clicked by script: element has no box; Native dialog accepted; Long tool result cut; Page read retried: page busy; Settle ran out of time; Forced finish on a budget; Task ended without an answer; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Harness error ended the task.
