# 2026-11-17_m3_test_r1

Model: `gpt-6-luna`. Tasks: 45. Success: 29/45 (64%).

| Mean per task | Value |
|---|---:|
| Tokens | 43010 |
| USD | 0.0043 |
| Seconds | 37.7 |
| Steps | 8.4 |

Total: $0.1917, 1935428 tokens. Finish reasons: {'finished': 44, 'stuck': 1}.

## Tokens

Input: 1137 uncached, 471608 read from cache, 1451886 written to cache. Output: 10797, of which reasoning 1121. Cache hit rate: 25%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| history | 16117 | 38% |
| observation | 12081 | 28% |
| tools | 8445 | 20% |
| system | 5713 | 13% |
| notes | 192 | 0% |
| task | 188 | 0% |
| status | 34 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 345 | 248 | test | yes | 42494 | 23% | 0.0042 | 29.3 | 8 | finished |
| 346 | 248 | test | yes | 88147 | 24% | 0.0088 | 62.9 | 16 | finished |
| 347 | 248 | test | yes | 18052 | 24% | 0.0018 | 14.2 | 4 | finished |
| 214 | 249 | test | no | 134854 | 26% | 0.0130 | 92.9 | 26 | finished |
| 215 | 249 | test | no | 52463 | 30% | 0.0049 | 42.0 | 12 | finished |
| 216 | 249 | test | no | 73244 | 31% | 0.0067 | 51.5 | 17 | finished |
| 705 | 268 | test | no | 40996 | 31% | 0.0038 | 35.5 | 10 | finished |
| 706 | 268 | test | no | 23189 | 31% | 0.0022 | 22.6 | 6 | finished |
| 707 | 268 | test | yes | 27976 | 30% | 0.0026 | 25.2 | 7 | finished |
| 108 | 270 | test | no | 8212 | 17% | 0.0009 | 20.0 | 2 | finished |
| 109 | 270 | test | no | 8739 | 17% | 0.0010 | 21.5 | 2 | finished |
| 110 | 270 | test | no | 13160 | 22% | 0.0014 | 21.0 | 3 | finished |
| 710 | 271 | test | yes | 25490 | 28% | 0.0024 | 20.7 | 6 | finished |
| 711 | 271 | test | no | 22607 | 31% | 0.0021 | 20.6 | 6 | finished |
| 712 | 271 | test | yes | 23386 | 30% | 0.0022 | 21.3 | 6 | finished |
| 12 | 288 | test | yes | 33154 | 26% | 0.0032 | 25.6 | 7 | finished |
| 13 | 288 | test | yes | 42442 | 27% | 0.0041 | 29.1 | 9 | finished |
| 14 | 288 | test | yes | 81554 | 26% | 0.0080 | 63.1 | 16 | finished |
| 209 | 364 | test | yes | 19780 | 22% | 0.0020 | 15.0 | 4 | finished |
| 210 | 364 | test | yes | 19779 | 22% | 0.0020 | 13.4 | 4 | finished |
| 211 | 364 | test | yes | 19656 | 22% | 0.0020 | 12.3 | 4 | finished |
| 199 | 366 | test | yes | 16518 | 17% | 0.0018 | 15.2 | 3 | finished |
| 200 | 366 | test | yes | 98270 | 14% | 0.0108 | 54.1 | 11 | finished |
| 202 | 366 | test | yes | 52434 | 16% | 0.0056 | 39.3 | 7 | finished |
| 129 | 1002 | test | no | 39845 | 21% | 0.0041 | 33.7 | 7 | finished |
| 130 | 1002 | test | yes | 120825 | 21% | 0.0124 | 98.6 | 19 | finished |
| 131 | 1002 | test | yes | 173844 | 20% | 0.0180 | 123.1 | 26 | finished |
| 773 | 246 | test | no | 23475 | 24% | 0.0023 | 18.3 | 5 | finished |
| 774 | 246 | test | no | 85574 | 30% | 0.0081 | 63.4 | 19 | finished |
| 775 | 246 | test | no | 67513 | 29% | 0.0063 | 49.5 | 15 | stuck |
| 459 | 247 | test | yes | 15284 | 19% | 0.0016 | 17.2 | 3 | finished |
| 460 | 247 | test | yes | 15208 | 19% | 0.0016 | 17.5 | 3 | finished |
| 461 | 247 | test | no | 20382 | 21% | 0.0021 | 21.3 | 4 | finished |
| 471 | 257 | test | yes | 30430 | 23% | 0.0030 | 35.9 | 6 | finished |
| 472 | 257 | test | yes | 29827 | 24% | 0.0030 | 41.9 | 6 | finished |
| 473 | 257 | test | yes | 30469 | 23% | 0.0030 | 31.9 | 6 | finished |
| 487 | 275 | test | yes | 27730 | 31% | 0.0026 | 30.4 | 7 | finished |
| 488 | 275 | test | yes | 7225 | 20% | 0.0008 | 27.5 | 2 | finished |
| 489 | 275 | test | yes | 26266 | 32% | 0.0024 | 31.4 | 7 | finished |
| 493 | 280 | test | no | 36777 | 23% | 0.0037 | 65.0 | 7 | finished |
| 494 | 280 | test | no | 26333 | 22% | 0.0027 | 26.9 | 5 | finished |
| 495 | 280 | test | yes | 36999 | 23% | 0.0037 | 37.2 | 7 | finished |
| 497 | 284 | test | yes | 41480 | 27% | 0.0040 | 50.6 | 9 | finished |
| 498 | 284 | test | yes | 46563 | 27% | 0.0044 | 51.0 | 10 | finished |
| 499 | 284 | test | yes | 46783 | 27% | 0.0045 | 55.0 | 10 | finished |

## Fallbacks

Tasks: 45, of which 29 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Tool call failed, error returned | 3 | 3 | 3/3 | 1/3 |
| Native dialog accepted | 1 | 1 | n/a | 0/1 |
| Settle ran out of time | 1 | 1 | n/a | 0/1 |
| Page shown with a cut list or table | 50 | 18 | n/a | 14/18 |
| Cut list followed by read_page(find/section) | 5 | 2 | 2/5 | 2/2 |
| Stuck hint given | 5 | 4 | 3/5 | 0/4 |
| Task ended as stuck (forced finish) | 1 | 1 | 1/1 | 0/1 |
| Skill steps loaded (load_skill) | 11 | 11 | n/a | 8/11 |
| run_skill: gate passed, code run | 4 | 4 | 4/4 | 1/4 |
| run_skill: gate rejected, nothing run | 6 | 6 | n/a | 5/6 |
| Skill steps handed to the model to follow | 6 | 6 | 6/6 | 5/6 |
| Lesson shown on a matching page | 130 | 42 | n/a | 27/42 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Returned to the last stable URL; Clicked by script: element has no box; Long tool result cut; New tab opened by an action, closed; Page read retried: page busy; Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Skill code stopped at a step; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Browser not clean before the task, repaired; Browser restarted before the task; Harness error ended the task.
