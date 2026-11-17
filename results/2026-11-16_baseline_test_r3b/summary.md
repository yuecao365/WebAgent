# 2026-11-16_baseline_test_r3b

Model: `gpt-6-luna`. Tasks: 45. Success: 28/45 (62%).

| Mean per task | Value |
|---|---:|
| Tokens | 33071 |
| USD | 0.0031 |
| Seconds | 39.1 |
| Steps | 8.5 |

Total: $0.1407, 1488184 tokens. Finish reasons: {'finished': 44, 'stuck': 1}.

## Tokens

Input: 1146 uncached, 427990 read from cache, 1048559 written to cache. Output: 10489, of which reasoning 1383. Cache hit rate: 29%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| observation | 16791 | 51% |
| tools | 7452 | 23% |
| system | 6342 | 19% |
| history | 1775 | 5% |
| task | 228 | 1% |
| notes | 213 | 1% |
| status | 35 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 345 | 248 | test | no | 21259 | 42% | 0.0017 | 35.6 | 8 | finished |
| 346 | 248 | test | yes | 54466 | 35% | 0.0049 | 69.1 | 16 | finished |
| 347 | 248 | test | yes | 11721 | 33% | 0.0011 | 13.9 | 4 | finished |
| 214 | 249 | test | no | 89102 | 32% | 0.0081 | 89.3 | 23 | finished |
| 215 | 249 | test | no | 38995 | 40% | 0.0033 | 53.0 | 13 | finished |
| 216 | 249 | test | no | 46976 | 41% | 0.0039 | 61.4 | 16 | finished |
| 705 | 268 | test | no | 17964 | 43% | 0.0014 | 23.8 | 7 | finished |
| 706 | 268 | test | no | 14552 | 44% | 0.0011 | 20.6 | 6 | finished |
| 707 | 268 | test | yes | 20216 | 32% | 0.0019 | 21.7 | 6 | finished |
| 108 | 270 | test | no | 99007 | 15% | 0.0108 | 59.3 | 13 | finished |
| 109 | 270 | test | no | 112553 | 15% | 0.0123 | 71.3 | 14 | finished |
| 110 | 270 | test | no | 33308 | 31% | 0.0031 | 37.8 | 9 | finished |
| 710 | 271 | test | yes | 17018 | 38% | 0.0015 | 20.8 | 6 | finished |
| 711 | 271 | test | no | 14135 | 45% | 0.0011 | 21.2 | 6 | finished |
| 712 | 271 | test | yes | 14914 | 43% | 0.0012 | 22.3 | 6 | finished |
| 12 | 288 | test | yes | 18446 | 35% | 0.0016 | 21.4 | 6 | finished |
| 13 | 288 | test | yes | 15791 | 32% | 0.0014 | 16.9 | 5 | finished |
| 14 | 288 | test | yes | 42232 | 33% | 0.0038 | 45.8 | 12 | finished |
| 209 | 364 | test | yes | 10698 | 24% | 0.0011 | 11.9 | 3 | finished |
| 210 | 364 | test | yes | 10697 | 24% | 0.0011 | 12.3 | 3 | finished |
| 211 | 364 | test | yes | 12300 | 31% | 0.0011 | 15.9 | 4 | finished |
| 199 | 366 | test | yes | 14655 | 26% | 0.0014 | 15.5 | 4 | finished |
| 200 | 366 | test | no | 130184 | 14% | 0.0144 | 70.7 | 15 | stuck |
| 202 | 366 | test | yes | 32477 | 12% | 0.0037 | 17.8 | 4 | finished |
| 129 | 1002 | test | yes | 67056 | 25% | 0.0067 | 77.8 | 14 | finished |
| 130 | 1002 | test | no | 24885 | 26% | 0.0024 | 43.3 | 6 | finished |
| 131 | 1002 | test | no | 57291 | 24% | 0.0057 | 83.5 | 12 | finished |
| 773 | 246 | test | no | 67591 | 32% | 0.0062 | 68.1 | 18 | finished |
| 774 | 246 | test | no | 28951 | 44% | 0.0023 | 37.2 | 11 | finished |
| 775 | 246 | test | no | 33944 | 38% | 0.0029 | 40.3 | 11 | finished |
| 459 | 247 | test | yes | 11108 | 23% | 0.0011 | 15.9 | 3 | finished |
| 460 | 247 | test | yes | 11039 | 23% | 0.0011 | 18.4 | 3 | finished |
| 461 | 247 | test | yes | 11039 | 23% | 0.0011 | 17.3 | 3 | finished |
| 471 | 257 | test | yes | 20184 | 32% | 0.0018 | 38.8 | 6 | finished |
| 472 | 257 | test | yes | 23929 | 32% | 0.0022 | 42.1 | 7 | finished |
| 473 | 257 | test | yes | 20223 | 32% | 0.0018 | 35.2 | 6 | finished |
| 487 | 275 | test | yes | 16053 | 48% | 0.0012 | 37.6 | 7 | finished |
| 488 | 275 | test | yes | 16153 | 48% | 0.0012 | 34.3 | 7 | finished |
| 489 | 275 | test | yes | 16145 | 48% | 0.0012 | 34.1 | 7 | finished |
| 493 | 280 | test | no | 23772 | 32% | 0.0022 | 61.4 | 7 | finished |
| 494 | 280 | test | yes | 23955 | 32% | 0.0022 | 34.8 | 7 | finished |
| 495 | 280 | test | yes | 24008 | 32% | 0.0022 | 34.5 | 7 | finished |
| 497 | 284 | test | yes | 36253 | 39% | 0.0030 | 54.7 | 12 | finished |
| 498 | 284 | test | yes | 31793 | 36% | 0.0027 | 52.8 | 10 | finished |
| 499 | 284 | test | yes | 29146 | 35% | 0.0025 | 48.8 | 9 | finished |

## Fallbacks

Tasks: 45, of which 28 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Tool call failed, error returned | 1 | 1 | 1/1 | 0/1 |
| Native dialog accepted | 1 | 1 | n/a | 0/1 |
| Settle ran out of time | 1 | 1 | n/a | 0/1 |
| Page shown with a cut list or table | 71 | 21 | n/a | 14/21 |
| Cut list followed by read_page(find/section) | 21 | 5 | 18/21 | 2/5 |
| Stuck hint given | 3 | 2 | 1/3 | 0/2 |
| Task ended as stuck (forced finish) | 1 | 1 | 1/1 | 0/1 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Returned to the last stable URL; Clicked by script: element has no box; Long tool result cut; New tab opened by an action, closed; Page read retried: page busy; Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Browser not clean before the task, repaired; Browser restarted before the task; Harness error ended the task.
