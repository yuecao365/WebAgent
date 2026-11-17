# 2026-11-16_c_test_r1

Model: `gpt-6-luna`. Tasks: 45. Success: 37/45 (82%).

| Mean per task | Value |
|---|---:|
| Tokens | 38931 |
| USD | 0.0040 |
| Seconds | 52.2 |
| Steps | 9.7 |

Total: $0.1792, 1751898 tokens. Finish reasons: {'finished': 45}.

## Tokens

Input: 1305 uncached, 495300 read from cache, 1209499 written to cache. Output: 45794, of which reasoning 34324. Cache hit rate: 29%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| observation | 15609 | 41% |
| tools | 9567 | 25% |
| system | 8143 | 21% |
| history | 3900 | 10% |
| notes | 358 | 1% |
| task | 295 | 1% |
| status | 40 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 345 | 248 | test | yes | 47733 | 30% | 0.0050 | 62.1 | 12 | finished |
| 346 | 248 | test | yes | 65165 | 27% | 0.0074 | 85.8 | 14 | finished |
| 347 | 248 | test | yes | 9218 | 28% | 0.0009 | 10.7 | 3 | finished |
| 214 | 249 | test | no | 119412 | 26% | 0.0139 | 158.4 | 24 | finished |
| 215 | 249 | test | yes | 114769 | 27% | 0.0127 | 156.3 | 24 | finished |
| 216 | 249 | test | yes | 51632 | 33% | 0.0053 | 84.7 | 14 | finished |
| 705 | 268 | test | no | 16773 | 39% | 0.0015 | 24.5 | 6 | finished |
| 706 | 268 | test | no | 24145 | 39% | 0.0024 | 37.2 | 8 | finished |
| 707 | 268 | test | yes | 21395 | 43% | 0.0018 | 30.0 | 8 | finished |
| 108 | 270 | test | yes | 31396 | 41% | 0.0027 | 40.4 | 11 | finished |
| 109 | 270 | test | yes | 31623 | 41% | 0.0028 | 40.4 | 11 | finished |
| 110 | 270 | test | yes | 34872 | 41% | 0.0030 | 42.7 | 12 | finished |
| 710 | 271 | test | yes | 17590 | 37% | 0.0016 | 24.4 | 6 | finished |
| 711 | 271 | test | no | 14554 | 45% | 0.0012 | 22.3 | 6 | finished |
| 712 | 271 | test | yes | 15439 | 42% | 0.0013 | 22.4 | 6 | finished |
| 12 | 288 | test | yes | 16323 | 32% | 0.0016 | 19.3 | 5 | finished |
| 13 | 288 | test | yes | 16377 | 32% | 0.0016 | 20.7 | 5 | finished |
| 14 | 288 | test | yes | 149789 | 22% | 0.0168 | 144.3 | 26 | finished |
| 209 | 364 | test | yes | 10767 | 24% | 0.0011 | 12.0 | 3 | finished |
| 210 | 364 | test | yes | 10766 | 24% | 0.0011 | 11.3 | 3 | finished |
| 211 | 364 | test | yes | 12395 | 31% | 0.0012 | 15.6 | 4 | finished |
| 199 | 366 | test | yes | 12291 | 21% | 0.0013 | 14.5 | 3 | finished |
| 200 | 366 | test | yes | 19761 | 20% | 0.0022 | 22.5 | 4 | finished |
| 202 | 366 | test | yes | 12326 | 21% | 0.0013 | 14.1 | 3 | finished |
| 129 | 1002 | test | yes | 58119 | 27% | 0.0058 | 74.6 | 13 | finished |
| 130 | 1002 | test | yes | 103277 | 22% | 0.0107 | 114.9 | 19 | finished |
| 131 | 1002 | test | yes | 114153 | 24% | 0.0117 | 109.7 | 22 | finished |
| 773 | 246 | test | no | 65967 | 30% | 0.0066 | 72.5 | 16 | finished |
| 774 | 246 | test | no | 129127 | 22% | 0.0144 | 129.7 | 23 | finished |
| 775 | 246 | test | no | 30536 | 38% | 0.0026 | 37.8 | 10 | finished |
| 459 | 247 | test | yes | 11303 | 23% | 0.0012 | 25.8 | 3 | finished |
| 460 | 247 | test | yes | 11114 | 23% | 0.0011 | 17.0 | 3 | finished |
| 461 | 247 | test | yes | 11168 | 23% | 0.0012 | 24.8 | 3 | finished |
| 471 | 257 | test | yes | 20427 | 31% | 0.0019 | 39.0 | 6 | finished |
| 472 | 257 | test | yes | 24307 | 32% | 0.0023 | 46.5 | 7 | finished |
| 473 | 257 | test | yes | 20492 | 31% | 0.0019 | 34.7 | 6 | finished |
| 487 | 275 | test | yes | 16317 | 47% | 0.0012 | 34.3 | 7 | finished |
| 488 | 275 | test | yes | 16405 | 47% | 0.0013 | 33.9 | 7 | finished |
| 489 | 275 | test | yes | 16297 | 47% | 0.0012 | 39.8 | 7 | finished |
| 493 | 280 | test | no | 50277 | 32% | 0.0054 | 100.8 | 13 | finished |
| 494 | 280 | test | yes | 34943 | 26% | 0.0038 | 56.6 | 8 | finished |
| 495 | 280 | test | yes | 33425 | 27% | 0.0033 | 48.7 | 8 | finished |
| 497 | 284 | test | yes | 35498 | 36% | 0.0032 | 61.5 | 11 | finished |
| 498 | 284 | test | yes | 35835 | 36% | 0.0032 | 63.1 | 11 | finished |
| 499 | 284 | test | yes | 36400 | 35% | 0.0033 | 64.5 | 11 | finished |

## Fallbacks

Tasks: 45, of which 37 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Tool call failed, error returned | 1 | 1 | 1/1 | 0/1 |
| Native dialog accepted | 1 | 1 | n/a | 0/1 |
| New tab opened by an action, closed | 1 | 1 | 1/1 | 1/1 |
| Settle ran out of time | 1 | 1 | n/a | 0/1 |
| Page shown with a cut list or table | 54 | 21 | n/a | 20/21 |
| Cut list followed by read_page(find/section) | 2 | 2 | 2/2 | 2/2 |
| Model API call retried (429, 5xx, timeout) | 3 | 2 | 3/3 | 2/2 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Returned to the last stable URL; Clicked by script: element has no box; Long tool result cut; Page read retried: page busy; Stuck hint given; Task ended as stuck (forced finish); Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Skill steps loaded (load_skill); run_skill: gate passed, code run; run_skill: gate rejected, nothing run; Skill code stopped at a step; Skill steps handed to the model to follow; Lesson shown on a matching page; Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Browser not clean before the task, repaired; Browser restarted before the task; Harness error ended the task.
