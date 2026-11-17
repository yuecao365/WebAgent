# 2026-11-17_probe_m2_r1

Model: `gpt-6-luna`. Tasks: 12. Success: 3/12 (25%).

| Mean per task | Value |
|---|---:|
| Tokens | 68454 |
| USD | 0.0068 |
| Seconds | 67.8 |
| Steps | 12.4 |

Total: $0.0819, 821450 tokens. Finish reasons: {'finished': 9, 'stuck': 3}.

## Tokens

Input: 447 uncached, 193444 read from cache, 623663 written to cache. Output: 3896, of which reasoning 539. Cache hit rate: 24%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| observation | 23926 | 35% |
| history | 21913 | 32% |
| tools | 12891 | 19% |
| system | 8721 | 13% |
| notes | 293 | 0% |
| task | 289 | 0% |
| status | 96 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 243 | 244 | probe | yes | 70772 | 26% | 0.0069 | 77.5 | 14 | finished |
| 244 | 244 | probe | yes | 36826 | 27% | 0.0035 | 30.0 | 8 | finished |
| 245 | 244 | probe | no | 22858 | 25% | 0.0023 | 18.6 | 5 | finished |
| 112 | 245 | probe | no | 65169 | 26% | 0.0063 | 57.1 | 13 | finished |
| 113 | 245 | probe | no | 26714 | 27% | 0.0026 | 25.5 | 6 | finished |
| 114 | 245 | probe | no | 60434 | 31% | 0.0056 | 49.9 | 14 | finished |
| 768 | 241 | probe | yes | 54681 | 23% | 0.0055 | 73.1 | 10 | finished |
| 769 | 241 | probe | no | 172283 | 22% | 0.0174 | 188.8 | 28 | finished |
| 770 | 241 | probe | no | 39721 | 21% | 0.0041 | 51.0 | 7 | finished |
| 453 | 242 | probe | no | 87465 | 21% | 0.0089 | 80.9 | 14 | stuck |
| 454 | 242 | probe | no | 104369 | 20% | 0.0107 | 86.9 | 16 | stuck |
| 455 | 242 | probe | no | 80158 | 23% | 0.0080 | 74.9 | 14 | stuck |

## Fallbacks

Tasks: 12, of which 3 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Page shown with a cut list or table | 68 | 6 | n/a | 1/6 |
| Cut list followed by read_page(find/section) | 2 | 2 | 1/2 | 0/2 |
| Stuck hint given | 9 | 5 | 3/9 | 0/5 |
| Task ended as stuck (forced finish) | 3 | 3 | 3/3 | 0/3 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Tool call failed, error returned; Returned to the last stable URL; Clicked by script: element has no box; Native dialog accepted; Long tool result cut; New tab opened by an action, closed; Page read retried: page busy; Settle ran out of time; Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Skill steps loaded (load_skill); run_skill: gate passed, code run; run_skill: gate rejected, nothing run; Skill code stopped at a step; Skill steps handed to the model to follow; Lesson shown on a matching page; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Read-only task wrote; next task reset first; Browser not clean before the task, repaired; Browser restarted before the task; Harness error ended the task.
