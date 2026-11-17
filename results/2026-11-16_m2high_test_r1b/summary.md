# 2026-11-16_m2high_test_r1b

Model: `gpt-6-luna`. Tasks: 45. Success: 39/45 (87%).

| Mean per task | Value |
|---|---:|
| Tokens | 57295 |
| USD | 0.0060 |
| Seconds | 56.2 |
| Steps | 10.1 |

Total: $0.2713, 2578269 tokens. Finish reasons: {'finished': 45}.

## Tokens

Input: 1362 uncached, 577508 read from cache, 1958033 written to cache. Output: 41366, of which reasoning 29012. Cache hit rate: 23%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| history | 21897 | 39% |
| observation | 15021 | 27% |
| tools | 11244 | 20% |
| system | 7606 | 13% |
| notes | 292 | 1% |
| task | 277 | 0% |
| status | 37 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 345 | 248 | test | yes | 31300 | 23% | 0.0035 | 33.0 | 6 | finished |
| 346 | 248 | test | yes | 77773 | 22% | 0.0084 | 69.1 | 13 | finished |
| 347 | 248 | test | yes | 17833 | 24% | 0.0018 | 11.8 | 4 | finished |
| 214 | 249 | test | yes | 142199 | 23% | 0.0152 | 158.2 | 24 | finished |
| 215 | 249 | test | yes | 153742 | 23% | 0.0168 | 143.0 | 25 | finished |
| 216 | 249 | test | yes | 248295 | 20% | 0.0275 | 207.6 | 36 | finished |
| 705 | 268 | test | yes | 40640 | 25% | 0.0043 | 31.4 | 8 | finished |
| 706 | 268 | test | no | 12447 | 23% | 0.0014 | 19.7 | 3 | finished |
| 707 | 268 | test | yes | 27569 | 21% | 0.0031 | 41.6 | 5 | finished |
| 108 | 270 | test | yes | 28249 | 25% | 0.0029 | 36.7 | 6 | finished |
| 109 | 270 | test | yes | 45705 | 28% | 0.0045 | 38.7 | 10 | finished |
| 110 | 270 | test | yes | 49551 | 29% | 0.0048 | 39.5 | 11 | finished |
| 710 | 271 | test | yes | 31882 | 27% | 0.0031 | 25.4 | 7 | finished |
| 711 | 271 | test | no | 23333 | 31% | 0.0023 | 24.4 | 6 | finished |
| 712 | 271 | test | yes | 23872 | 30% | 0.0023 | 24.4 | 6 | finished |
| 12 | 288 | test | yes | 32899 | 26% | 0.0032 | 27.3 | 7 | finished |
| 13 | 288 | test | yes | 32781 | 26% | 0.0032 | 28.1 | 7 | finished |
| 14 | 288 | test | yes | 72505 | 26% | 0.0075 | 68.2 | 14 | finished |
| 209 | 364 | test | yes | 19785 | 22% | 0.0021 | 15.5 | 4 | finished |
| 210 | 364 | test | yes | 19855 | 22% | 0.0021 | 15.8 | 4 | finished |
| 211 | 364 | test | yes | 14888 | 19% | 0.0016 | 12.3 | 3 | finished |
| 199 | 366 | test | yes | 16504 | 17% | 0.0018 | 15.7 | 3 | finished |
| 200 | 366 | test | yes | 86924 | 15% | 0.0097 | 61.9 | 10 | finished |
| 202 | 366 | test | yes | 25646 | 17% | 0.0028 | 22.0 | 4 | finished |
| 129 | 1002 | test | yes | 96440 | 21% | 0.0101 | 95.8 | 15 | finished |
| 130 | 1002 | test | yes | 115906 | 21% | 0.0120 | 103.6 | 18 | finished |
| 131 | 1002 | test | yes | 164148 | 20% | 0.0172 | 152.3 | 24 | finished |
| 773 | 246 | test | yes | 100527 | 26% | 0.0104 | 103.4 | 19 | finished |
| 774 | 246 | test | no | 205920 | 21% | 0.0224 | 162.4 | 31 | finished |
| 775 | 246 | test | no | 40500 | 28% | 0.0039 | 33.8 | 9 | finished |
| 459 | 247 | test | yes | 15392 | 18% | 0.0016 | 16.4 | 3 | finished |
| 460 | 247 | test | yes | 15304 | 19% | 0.0016 | 18.7 | 3 | finished |
| 461 | 247 | test | no | 26959 | 21% | 0.0028 | 24.9 | 5 | finished |
| 471 | 257 | test | yes | 30143 | 24% | 0.0030 | 37.9 | 6 | finished |
| 472 | 257 | test | yes | 29476 | 24% | 0.0029 | 42.7 | 6 | finished |
| 473 | 257 | test | yes | 29899 | 24% | 0.0030 | 40.1 | 6 | finished |
| 487 | 275 | test | yes | 7185 | 20% | 0.0008 | 27.3 | 2 | finished |
| 488 | 275 | test | yes | 31736 | 31% | 0.0029 | 33.5 | 8 | finished |
| 489 | 275 | test | yes | 11634 | 24% | 0.0012 | 26.7 | 3 | finished |
| 493 | 280 | test | no | 83594 | 24% | 0.0092 | 115.0 | 15 | finished |
| 494 | 280 | test | yes | 86382 | 18% | 0.0095 | 84.7 | 12 | finished |
| 495 | 280 | test | yes | 60942 | 23% | 0.0062 | 57.7 | 11 | finished |
| 497 | 284 | test | yes | 49617 | 29% | 0.0047 | 63.7 | 11 | finished |
| 498 | 284 | test | yes | 49053 | 26% | 0.0048 | 52.9 | 10 | finished |
| 499 | 284 | test | yes | 51335 | 28% | 0.0050 | 63.0 | 11 | finished |

## Fallbacks

Tasks: 45, of which 39 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Tool call failed, error returned | 1 | 1 | 1/1 | 0/1 |
| Native dialog accepted | 1 | 1 | n/a | 0/1 |
| New tab opened by an action, closed | 2 | 2 | 2/2 | 2/2 |
| Settle ran out of time | 1 | 1 | n/a | 0/1 |
| Page shown with a cut list or table | 67 | 23 | n/a | 21/23 |
| Cut list followed by read_page(find/section) | 6 | 3 | 4/6 | 3/3 |
| Skill steps loaded (load_skill) | 20 | 20 | n/a | 17/20 |
| run_skill: gate passed, code run | 5 | 5 | 5/5 | 4/5 |
| run_skill: gate rejected, nothing run | 5 | 5 | n/a | 5/5 |
| Skill steps handed to the model to follow | 5 | 5 | 5/5 | 5/5 |
| Model API call retried (429, 5xx, timeout) | 3 | 3 | 3/3 | 3/3 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Returned to the last stable URL; Clicked by script: element has no box; Long tool result cut; Page read retried: page busy; Stuck hint given; Task ended as stuck (forced finish); Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Skill code stopped at a step; Lesson shown on a matching page; Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Browser not clean before the task, repaired; Browser restarted before the task; Harness error ended the task.
