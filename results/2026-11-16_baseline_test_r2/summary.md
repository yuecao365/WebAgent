# 2026-11-16_baseline_test_r2

Model: `gpt-6-luna`. Tasks: 45. Success: 29/45 (64%).

| Mean per task | Value |
|---|---:|
| Tokens | 31350 |
| USD | 0.0029 |
| Seconds | 39.7 |
| Steps | 8.4 |

Total: $0.1315, 1410737 tokens. Finish reasons: {'finished': 44, 'stuck': 1}.

## Tokens

Input: 1131 uncached, 421640 read from cache, 978057 written to cache. Output: 9909, of which reasoning 956. Cache hit rate: 30%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| observation | 15503 | 50% |
| tools | 7328 | 24% |
| system | 6237 | 20% |
| history | 1602 | 5% |
| task | 214 | 1% |
| notes | 209 | 1% |
| status | 36 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 345 | 248 | test | yes | 45670 | 34% | 0.0041 | 57.0 | 13 | finished |
| 346 | 248 | test | yes | 61525 | 31% | 0.0058 | 70.0 | 16 | finished |
| 347 | 248 | test | yes | 9001 | 28% | 0.0009 | 10.4 | 3 | finished |
| 214 | 249 | test | no | 66648 | 36% | 0.0058 | 84.4 | 20 | finished |
| 215 | 249 | test | no | 40821 | 25% | 0.0040 | 47.4 | 9 | finished |
| 216 | 249 | test | no | 28086 | 41% | 0.0023 | 43.7 | 10 | finished |
| 705 | 268 | test | no | 15421 | 42% | 0.0013 | 22.4 | 6 | finished |
| 706 | 268 | test | no | 16925 | 46% | 0.0013 | 24.4 | 7 | finished |
| 707 | 268 | test | yes | 17500 | 44% | 0.0014 | 25.8 | 7 | finished |
| 108 | 270 | test | no | 32926 | 31% | 0.0030 | 43.8 | 9 | finished |
| 109 | 270 | test | yes | 42029 | 34% | 0.0038 | 49.8 | 12 | finished |
| 110 | 270 | test | no | 99012 | 14% | 0.0109 | 70.1 | 12 | finished |
| 710 | 271 | test | yes | 19746 | 39% | 0.0017 | 23.4 | 7 | finished |
| 711 | 271 | test | no | 14135 | 45% | 0.0011 | 21.7 | 6 | finished |
| 712 | 271 | test | yes | 14914 | 43% | 0.0012 | 23.5 | 6 | finished |
| 12 | 288 | test | yes | 18442 | 35% | 0.0016 | 21.9 | 6 | finished |
| 13 | 288 | test | yes | 15793 | 32% | 0.0014 | 17.6 | 5 | finished |
| 14 | 288 | test | yes | 29746 | 34% | 0.0026 | 34.0 | 9 | finished |
| 209 | 364 | test | yes | 10698 | 24% | 0.0011 | 12.0 | 3 | finished |
| 210 | 364 | test | yes | 10697 | 24% | 0.0011 | 11.7 | 3 | finished |
| 211 | 364 | test | yes | 10698 | 24% | 0.0011 | 12.4 | 3 | finished |
| 199 | 366 | test | yes | 12098 | 21% | 0.0012 | 14.4 | 3 | finished |
| 200 | 366 | test | no | 146950 | 16% | 0.0159 | 95.6 | 19 | stuck |
| 202 | 366 | test | yes | 34674 | 18% | 0.0037 | 31.8 | 6 | finished |
| 129 | 1002 | test | no | 24881 | 26% | 0.0024 | 45.2 | 6 | finished |
| 130 | 1002 | test | no | 24886 | 26% | 0.0024 | 31.4 | 6 | finished |
| 131 | 1002 | test | no | 63975 | 26% | 0.0062 | 74.1 | 14 | finished |
| 773 | 246 | test | no | 30380 | 42% | 0.0024 | 37.3 | 11 | finished |
| 774 | 246 | test | yes | 53803 | 36% | 0.0048 | 66.7 | 16 | finished |
| 775 | 246 | test | no | 58206 | 33% | 0.0052 | 66.1 | 16 | finished |
| 459 | 247 | test | yes | 11109 | 23% | 0.0011 | 18.2 | 3 | finished |
| 460 | 247 | test | yes | 11034 | 23% | 0.0011 | 16.7 | 3 | finished |
| 461 | 247 | test | no | 14807 | 26% | 0.0015 | 20.0 | 4 | finished |
| 471 | 257 | test | yes | 20184 | 32% | 0.0018 | 35.0 | 6 | finished |
| 472 | 257 | test | yes | 23929 | 32% | 0.0022 | 38.2 | 7 | finished |
| 473 | 257 | test | yes | 20223 | 32% | 0.0018 | 32.5 | 6 | finished |
| 487 | 275 | test | yes | 16053 | 48% | 0.0012 | 38.5 | 7 | finished |
| 488 | 275 | test | yes | 16153 | 48% | 0.0012 | 36.8 | 7 | finished |
| 489 | 275 | test | yes | 16145 | 48% | 0.0012 | 35.7 | 7 | finished |
| 493 | 280 | test | no | 23771 | 32% | 0.0022 | 64.6 | 7 | finished |
| 494 | 280 | test | yes | 23955 | 32% | 0.0022 | 36.5 | 7 | finished |
| 495 | 280 | test | yes | 31863 | 28% | 0.0030 | 47.5 | 8 | finished |
| 497 | 284 | test | yes | 41758 | 40% | 0.0034 | 61.5 | 14 | finished |
| 498 | 284 | test | yes | 37454 | 38% | 0.0032 | 63.2 | 12 | finished |
| 499 | 284 | test | yes | 32013 | 36% | 0.0028 | 53.6 | 10 | finished |

## Fallbacks

Tasks: 45, of which 29 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Native dialog accepted | 1 | 1 | n/a | 0/1 |
| Settle ran out of time | 1 | 1 | n/a | 0/1 |
| Page shown with a cut list or table | 72 | 22 | n/a | 13/22 |
| Cut list followed by read_page(find/section) | 18 | 3 | 8/18 | 1/3 |
| Stuck hint given | 4 | 3 | 2/4 | 1/3 |
| Task ended as stuck (forced finish) | 1 | 1 | 1/1 | 0/1 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Tool call failed, error returned; Returned to the last stable URL; Clicked by script: element has no box; Long tool result cut; Page read retried: page busy; Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Harness error ended the task.
