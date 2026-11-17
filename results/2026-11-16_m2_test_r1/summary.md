# 2026-11-16_m2_test_r1

Model: `gpt-6-luna`. Tasks: 45. Success: 32/45 (71%).

| Mean per task | Value |
|---|---:|
| Tokens | 41045 |
| USD | 0.0041 |
| Seconds | 35.6 |
| Steps | 7.9 |

Total: $0.1842, 1847003 tokens. Finish reasons: {'finished': 44, 'stuck': 1}.

## Tokens

Input: 1068 uncached, 439132 read from cache, 1396526 written to cache. Output: 10277, of which reasoning 1259. Cache hit rate: 24%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| history | 13970 | 34% |
| observation | 13048 | 32% |
| tools | 8001 | 20% |
| system | 5413 | 13% |
| notes | 181 | 0% |
| task | 173 | 0% |
| status | 30 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 345 | 248 | test | yes | 29785 | 24% | 0.0030 | 22.5 | 6 | finished |
| 346 | 248 | test | no | 57952 | 25% | 0.0058 | 41.2 | 11 | finished |
| 347 | 248 | test | yes | 17745 | 24% | 0.0018 | 10.1 | 4 | finished |
| 214 | 249 | test | no | 69544 | 29% | 0.0066 | 54.5 | 15 | finished |
| 215 | 249 | test | yes | 62043 | 30% | 0.0059 | 56.8 | 14 | finished |
| 216 | 249 | test | no | 52796 | 30% | 0.0049 | 48.4 | 12 | finished |
| 705 | 268 | test | no | 27722 | 31% | 0.0026 | 24.2 | 7 | finished |
| 706 | 268 | test | yes | 22914 | 31% | 0.0021 | 22.7 | 6 | finished |
| 707 | 268 | test | yes | 28580 | 25% | 0.0028 | 21.3 | 6 | finished |
| 108 | 270 | test | no | 12597 | 23% | 0.0013 | 17.9 | 3 | finished |
| 109 | 270 | test | no | 13121 | 22% | 0.0014 | 19.6 | 3 | finished |
| 110 | 270 | test | no | 13052 | 22% | 0.0014 | 18.3 | 3 | finished |
| 710 | 271 | test | yes | 25382 | 28% | 0.0024 | 19.3 | 6 | finished |
| 711 | 271 | test | no | 22499 | 32% | 0.0021 | 19.2 | 6 | finished |
| 712 | 271 | test | yes | 23278 | 31% | 0.0022 | 19.0 | 6 | finished |
| 12 | 288 | test | yes | 32581 | 26% | 0.0032 | 22.2 | 7 | finished |
| 13 | 288 | test | yes | 32577 | 26% | 0.0032 | 22.2 | 7 | finished |
| 14 | 288 | test | yes | 27647 | 26% | 0.0027 | 17.6 | 6 | finished |
| 209 | 364 | test | yes | 19494 | 22% | 0.0020 | 12.4 | 4 | finished |
| 210 | 364 | test | yes | 19493 | 22% | 0.0020 | 11.8 | 4 | finished |
| 211 | 364 | test | yes | 14880 | 19% | 0.0016 | 9.6 | 3 | finished |
| 199 | 366 | test | yes | 16280 | 17% | 0.0017 | 12.4 | 3 | finished |
| 200 | 366 | test | no | 237719 | 15% | 0.0257 | 98.2 | 27 | stuck |
| 202 | 366 | test | yes | 38053 | 11% | 0.0043 | 13.3 | 4 | finished |
| 129 | 1002 | test | yes | 82614 | 22% | 0.0084 | 70.0 | 14 | finished |
| 130 | 1002 | test | yes | 103860 | 22% | 0.0106 | 96.0 | 17 | finished |
| 131 | 1002 | test | yes | 151807 | 21% | 0.0155 | 131.7 | 24 | finished |
| 773 | 246 | test | no | 42824 | 30% | 0.0040 | 34.6 | 10 | finished |
| 774 | 246 | test | yes | 63037 | 29% | 0.0060 | 60.0 | 14 | finished |
| 775 | 246 | test | no | 30928 | 28% | 0.0030 | 23.3 | 7 | finished |
| 459 | 247 | test | yes | 15290 | 19% | 0.0016 | 14.8 | 3 | finished |
| 460 | 247 | test | yes | 15213 | 19% | 0.0016 | 13.5 | 3 | finished |
| 461 | 247 | test | no | 20373 | 21% | 0.0021 | 21.9 | 4 | finished |
| 471 | 257 | test | yes | 28548 | 25% | 0.0028 | 33.0 | 6 | finished |
| 472 | 257 | test | yes | 29181 | 24% | 0.0029 | 35.1 | 6 | finished |
| 473 | 257 | test | yes | 29823 | 24% | 0.0030 | 34.4 | 6 | finished |
| 487 | 275 | test | yes | 7099 | 20% | 0.0008 | 30.0 | 2 | finished |
| 488 | 275 | test | yes | 25911 | 33% | 0.0023 | 33.9 | 7 | finished |
| 489 | 275 | test | yes | 25903 | 33% | 0.0023 | 37.7 | 7 | finished |
| 493 | 280 | test | no | 39555 | 25% | 0.0039 | 64.7 | 8 | finished |
| 494 | 280 | test | yes | 45425 | 22% | 0.0046 | 36.8 | 8 | finished |
| 495 | 280 | test | yes | 35817 | 24% | 0.0036 | 37.2 | 7 | finished |
| 497 | 284 | test | yes | 48987 | 29% | 0.0046 | 58.4 | 11 | finished |
| 498 | 284 | test | yes | 41433 | 27% | 0.0040 | 50.0 | 9 | finished |
| 499 | 284 | test | yes | 45641 | 28% | 0.0043 | 50.9 | 10 | finished |

## Fallbacks

Tasks: 45, of which 32 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Native dialog accepted | 1 | 1 | n/a | 0/1 |
| Settle ran out of time | 1 | 1 | n/a | 0/1 |
| Page shown with a cut list or table | 64 | 18 | n/a | 15/18 |
| Cut list followed by read_page(find/section) | 19 | 3 | 5/19 | 2/3 |
| Stuck hint given | 2 | 1 | 0/2 | 0/1 |
| Task ended as stuck (forced finish) | 1 | 1 | 1/1 | 0/1 |
| Skill steps loaded (load_skill) | 15 | 15 | n/a | 10/15 |
| run_skill: gate passed, code run | 4 | 4 | 4/4 | 1/4 |
| run_skill: gate rejected, nothing run | 2 | 2 | n/a | 2/2 |
| Skill steps handed to the model to follow | 2 | 2 | 2/2 | 2/2 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Tool call failed, error returned; Returned to the last stable URL; Clicked by script: element has no box; Long tool result cut; New tab opened by an action, closed; Page read retried: page busy; Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Skill code stopped at a step; Lesson shown on a matching page; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Browser not clean before the task, repaired; Browser restarted before the task; Harness error ended the task.
