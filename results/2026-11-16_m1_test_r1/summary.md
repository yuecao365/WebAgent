# 2026-11-16_m1_test_r1

Model: `gpt-6-luna`. Tasks: 45. Success: 32/45 (71%).

| Mean per task | Value |
|---|---:|
| Tokens | 34215 |
| USD | 0.0033 |
| Seconds | 33.9 |
| Steps | 7.5 |

Total: $0.1490, 1539665 tokens. Finish reasons: {'finished': 44, 'stuck': 1}.

## Tokens

Input: 1008 uncached, 410892 read from cache, 1117672 written to cache. Output: 10093, of which reasoning 1291. Cache hit rate: 27%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| observation | 12329 | 36% |
| history | 8313 | 24% |
| tools | 7737 | 23% |
| system | 5234 | 15% |
| notes | 178 | 1% |
| task | 168 | 0% |
| status | 31 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 345 | 248 | test | yes | 30714 | 28% | 0.0029 | 22.8 | 7 | finished |
| 346 | 248 | test | yes | 62890 | 27% | 0.0062 | 51.2 | 13 | finished |
| 347 | 248 | test | yes | 15225 | 28% | 0.0015 | 10.7 | 4 | finished |
| 214 | 249 | test | no | 49534 | 35% | 0.0045 | 49.5 | 13 | finished |
| 215 | 249 | test | no | 52848 | 32% | 0.0048 | 47.8 | 13 | finished |
| 216 | 249 | test | no | 70210 | 36% | 0.0060 | 58.5 | 19 | finished |
| 705 | 268 | test | no | 10787 | 26% | 0.0011 | 18.7 | 3 | finished |
| 706 | 268 | test | yes | 24387 | 35% | 0.0021 | 23.8 | 7 | finished |
| 707 | 268 | test | yes | 15567 | 18% | 0.0017 | 18.6 | 3 | finished |
| 108 | 270 | test | no | 6898 | 21% | 0.0007 | 17.1 | 2 | finished |
| 109 | 270 | test | no | 11231 | 26% | 0.0012 | 21.3 | 3 | finished |
| 110 | 270 | test | no | 11162 | 26% | 0.0011 | 19.4 | 3 | finished |
| 710 | 271 | test | yes | 26751 | 32% | 0.0024 | 21.0 | 7 | finished |
| 711 | 271 | test | no | 20996 | 34% | 0.0019 | 22.2 | 6 | finished |
| 712 | 271 | test | yes | 10261 | 28% | 0.0010 | 16.1 | 3 | finished |
| 12 | 288 | test | yes | 28012 | 30% | 0.0026 | 21.1 | 7 | finished |
| 13 | 288 | test | yes | 27976 | 30% | 0.0026 | 21.4 | 7 | finished |
| 14 | 288 | test | yes | 27622 | 31% | 0.0026 | 21.2 | 7 | finished |
| 209 | 364 | test | yes | 16974 | 25% | 0.0017 | 12.6 | 4 | finished |
| 210 | 364 | test | yes | 17097 | 25% | 0.0017 | 11.1 | 4 | finished |
| 211 | 364 | test | yes | 16974 | 25% | 0.0017 | 10.9 | 4 | finished |
| 199 | 366 | test | yes | 14390 | 20% | 0.0015 | 11.6 | 3 | finished |
| 200 | 366 | test | no | 156795 | 15% | 0.0170 | 60.5 | 18 | stuck |
| 202 | 366 | test | yes | 40743 | 17% | 0.0043 | 25.8 | 6 | finished |
| 129 | 1002 | test | yes | 74034 | 25% | 0.0073 | 69.8 | 14 | finished |
| 130 | 1002 | test | no | 22543 | 25% | 0.0022 | 23.3 | 5 | finished |
| 131 | 1002 | test | yes | 154026 | 23% | 0.0155 | 154.8 | 26 | finished |
| 773 | 246 | test | yes | 66413 | 32% | 0.0061 | 66.6 | 16 | finished |
| 774 | 246 | test | no | 22583 | 38% | 0.0019 | 19.1 | 7 | finished |
| 775 | 246 | test | no | 52157 | 35% | 0.0045 | 44.5 | 14 | finished |
| 459 | 247 | test | yes | 13399 | 21% | 0.0014 | 15.9 | 3 | finished |
| 460 | 247 | test | yes | 13329 | 21% | 0.0014 | 14.5 | 3 | finished |
| 461 | 247 | test | yes | 13330 | 21% | 0.0014 | 18.3 | 3 | finished |
| 471 | 257 | test | yes | 26004 | 27% | 0.0025 | 33.4 | 6 | finished |
| 472 | 257 | test | yes | 26637 | 27% | 0.0026 | 34.1 | 6 | finished |
| 473 | 257 | test | yes | 26043 | 27% | 0.0025 | 42.6 | 6 | finished |
| 487 | 275 | test | yes | 9625 | 30% | 0.0009 | 29.7 | 3 | finished |
| 488 | 275 | test | yes | 9649 | 30% | 0.0009 | 27.1 | 3 | finished |
| 489 | 275 | test | yes | 5954 | 24% | 0.0006 | 28.6 | 2 | finished |
| 493 | 280 | test | no | 35358 | 28% | 0.0034 | 64.4 | 8 | finished |
| 494 | 280 | test | yes | 48936 | 23% | 0.0049 | 44.5 | 9 | finished |
| 495 | 280 | test | yes | 31407 | 27% | 0.0030 | 34.6 | 7 | finished |
| 497 | 284 | test | yes | 41474 | 31% | 0.0038 | 49.5 | 10 | finished |
| 498 | 284 | test | yes | 42104 | 30% | 0.0039 | 50.2 | 10 | finished |
| 499 | 284 | test | yes | 38616 | 29% | 0.0036 | 47.1 | 9 | finished |

## Fallbacks

Tasks: 45, of which 32 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Tool call failed, error returned | 2 | 2 | 2/2 | 1/2 |
| Native dialog accepted | 1 | 1 | n/a | 0/1 |
| Settle ran out of time | 1 | 1 | n/a | 0/1 |
| Page shown with a cut list or table | 54 | 18 | n/a | 15/18 |
| Cut list followed by read_page(find/section) | 15 | 3 | 10/15 | 2/3 |
| Stuck hint given | 4 | 3 | 2/4 | 0/3 |
| Task ended as stuck (forced finish) | 1 | 1 | 1/1 | 0/1 |
| Skill steps loaded (load_skill) | 28 | 28 | n/a | 23/28 |
| run_skill: gate passed, code run | 10 | 10 | 9/10 | 5/10 |
| run_skill: gate rejected, nothing run | 3 | 3 | n/a | 2/3 |
| Skill code stopped at a step | 1 | 1 | n/a | 0/1 |
| Skill steps handed to the model to follow | 4 | 4 | 4/4 | 2/4 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Returned to the last stable URL; Clicked by script: element has no box; Long tool result cut; New tab opened by an action, closed; Page read retried: page busy; Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Lesson shown on a matching page; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Browser not clean before the task, repaired; Browser restarted before the task; Harness error ended the task.
