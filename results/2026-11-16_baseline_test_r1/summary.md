# 2026-11-16_baseline_test_r1

Model: `gpt-6-luna`. Tasks: 45. Success: 34/45 (76%).

| Mean per task | Value |
|---|---:|
| Tokens | 27796 |
| USD | 0.0026 |
| Seconds | 37.1 |
| Steps | 7.8 |

Total: $0.1155, 1250806 tokens. Finish reasons: {'finished': 44, 'stuck': 1}.

## Tokens

Input: 1053 uncached, 388620 read from cache, 850803 written to cache. Output: 10330, of which reasoning 1784. Cache hit rate: 31%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| observation | 12856 | 47% |
| tools | 6829 | 25% |
| system | 5813 | 21% |
| history | 1644 | 6% |
| task | 199 | 1% |
| notes | 191 | 1% |
| status | 31 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 345 | 248 | test | yes | 21421 | 30% | 0.0020 | 24.8 | 6 | finished |
| 346 | 248 | test | yes | 28655 | 36% | 0.0025 | 37.6 | 9 | finished |
| 347 | 248 | test | yes | 9001 | 28% | 0.0009 | 9.5 | 3 | finished |
| 214 | 249 | test | no | 30277 | 34% | 0.0027 | 50.5 | 9 | finished |
| 215 | 249 | test | yes | 38560 | 40% | 0.0033 | 54.7 | 13 | finished |
| 216 | 249 | test | no | 63650 | 38% | 0.0054 | 91.0 | 20 | finished |
| 705 | 268 | test | no | 20731 | 43% | 0.0016 | 27.8 | 8 | finished |
| 706 | 268 | test | yes | 14550 | 44% | 0.0011 | 21.3 | 6 | finished |
| 707 | 268 | test | yes | 17500 | 44% | 0.0014 | 23.7 | 7 | finished |
| 108 | 270 | test | no | 17972 | 43% | 0.0015 | 28.2 | 7 | finished |
| 109 | 270 | test | no | 21190 | 43% | 0.0017 | 30.1 | 8 | finished |
| 110 | 270 | test | yes | 26938 | 43% | 0.0022 | 37.7 | 10 | finished |
| 710 | 271 | test | yes | 17018 | 38% | 0.0015 | 22.1 | 6 | finished |
| 711 | 271 | test | no | 14135 | 45% | 0.0011 | 21.5 | 6 | finished |
| 712 | 271 | test | yes | 14914 | 43% | 0.0012 | 20.9 | 6 | finished |
| 12 | 288 | test | yes | 15804 | 32% | 0.0014 | 19.6 | 5 | finished |
| 13 | 288 | test | yes | 15789 | 32% | 0.0014 | 19.1 | 5 | finished |
| 14 | 288 | test | yes | 15592 | 33% | 0.0014 | 17.7 | 5 | finished |
| 209 | 364 | test | yes | 10698 | 24% | 0.0011 | 12.4 | 3 | finished |
| 210 | 364 | test | yes | 13310 | 29% | 0.0013 | 16.0 | 4 | finished |
| 211 | 364 | test | yes | 10698 | 24% | 0.0011 | 11.9 | 3 | finished |
| 199 | 366 | test | yes | 12098 | 21% | 0.0012 | 13.5 | 3 | finished |
| 200 | 366 | test | no | 127241 | 14% | 0.0140 | 64.1 | 15 | stuck |
| 202 | 366 | test | yes | 22092 | 17% | 0.0024 | 21.3 | 4 | finished |
| 129 | 1002 | test | no | 25332 | 25% | 0.0025 | 41.6 | 6 | finished |
| 130 | 1002 | test | yes | 83142 | 23% | 0.0084 | 133.1 | 16 | finished |
| 131 | 1002 | test | yes | 106744 | 25% | 0.0106 | 116.4 | 22 | finished |
| 773 | 246 | test | no | 10499 | 37% | 0.0009 | 10.7 | 4 | finished |
| 774 | 246 | test | yes | 85524 | 33% | 0.0079 | 100.4 | 23 | finished |
| 775 | 246 | test | no | 29566 | 39% | 0.0025 | 36.8 | 10 | finished |
| 459 | 247 | test | yes | 14900 | 26% | 0.0015 | 20.2 | 4 | finished |
| 460 | 247 | test | yes | 11027 | 23% | 0.0011 | 16.3 | 3 | finished |
| 461 | 247 | test | yes | 11043 | 23% | 0.0011 | 15.4 | 3 | finished |
| 471 | 257 | test | yes | 20184 | 32% | 0.0018 | 38.2 | 6 | finished |
| 472 | 257 | test | yes | 20817 | 31% | 0.0019 | 36.1 | 6 | finished |
| 473 | 257 | test | yes | 20223 | 32% | 0.0018 | 37.0 | 6 | finished |
| 487 | 275 | test | yes | 16053 | 48% | 0.0012 | 34.7 | 7 | finished |
| 488 | 275 | test | yes | 16153 | 48% | 0.0012 | 34.9 | 7 | finished |
| 489 | 275 | test | yes | 16145 | 48% | 0.0012 | 34.7 | 7 | finished |
| 493 | 280 | test | no | 23814 | 32% | 0.0022 | 40.3 | 7 | finished |
| 494 | 280 | test | yes | 23955 | 32% | 0.0022 | 35.7 | 7 | finished |
| 495 | 280 | test | yes | 24008 | 32% | 0.0022 | 35.5 | 7 | finished |
| 497 | 284 | test | yes | 30974 | 37% | 0.0026 | 52.2 | 10 | finished |
| 498 | 284 | test | yes | 31723 | 36% | 0.0027 | 52.2 | 10 | finished |
| 499 | 284 | test | yes | 29146 | 35% | 0.0025 | 49.6 | 9 | finished |

## Fallbacks

Tasks: 45, of which 34 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Tool call failed, error returned | 2 | 2 | 2/2 | 2/2 |
| Page shown with a cut list or table | 57 | 20 | n/a | 16/20 |
| Cut list followed by read_page(find/section) | 14 | 3 | 13/14 | 2/3 |
| Stuck hint given | 2 | 1 | 0/2 | 0/1 |
| Task ended as stuck (forced finish) | 1 | 1 | 1/1 | 0/1 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Returned to the last stable URL; Clicked by script: element has no box; Native dialog accepted; Long tool result cut; Page read retried: page busy; Settle ran out of time; Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Harness error ended the task.
