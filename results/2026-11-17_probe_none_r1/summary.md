# 2026-11-17_probe_none_r1

Model: `gpt-6-luna`. Tasks: 12. Success: 8/12 (67%).

| Mean per task | Value |
|---|---:|
| Tokens | 52204 |
| USD | 0.0049 |
| Seconds | 75.9 |
| Steps | 13.2 |

Total: $0.0585, 626453 tokens. Finish reasons: {'finished': 11, 'stuck': 1}.

## Tokens

Input: 474 uncached, 185420 read from cache, 436410 written to cache. Output: 4149, of which reasoning 737. Cache hit rate: 30%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| observation | 25380 | 49% |
| tools | 11779 | 23% |
| system | 10026 | 19% |
| history | 3926 | 8% |
| notes | 337 | 1% |
| task | 337 | 1% |
| status | 74 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 243 | 244 | probe | yes | 62758 | 31% | 0.0058 | 75.0 | 16 | finished |
| 244 | 244 | probe | yes | 11178 | 34% | 0.0010 | 15.2 | 4 | finished |
| 245 | 244 | probe | yes | 26428 | 34% | 0.0024 | 37.6 | 8 | finished |
| 112 | 245 | probe | yes | 50730 | 35% | 0.0044 | 55.7 | 15 | finished |
| 113 | 245 | probe | no | 39113 | 33% | 0.0035 | 52.3 | 11 | finished |
| 114 | 245 | probe | no | 58461 | 33% | 0.0054 | 101.7 | 16 | finished |
| 768 | 241 | probe | yes | 30800 | 29% | 0.0029 | 55.6 | 8 | finished |
| 769 | 241 | probe | yes | 123255 | 27% | 0.0119 | 191.1 | 27 | finished |
| 770 | 241 | probe | yes | 55702 | 30% | 0.0052 | 101.4 | 14 | finished |
| 453 | 242 | probe | yes | 62256 | 25% | 0.0061 | 99.8 | 13 | finished |
| 454 | 242 | probe | no | 64833 | 24% | 0.0064 | 70.3 | 13 | stuck |
| 455 | 242 | probe | no | 40939 | 37% | 0.0035 | 55.1 | 13 | finished |

## Fallbacks

Tasks: 12, of which 8 scored successful.

| Fallback | Triggers | Tasks | Recovered | Tasks successful |
|---|---:|---:|---:|---:|
| Page shown with a cut list or table | 58 | 8 | n/a | 4/8 |
| Stuck hint given | 4 | 3 | 2/4 | 1/3 |
| Task ended as stuck (forced finish) | 1 | 1 | 1/1 | 0/1 |
| Read-only task wrote; next task reset first | 1 | 1 | n/a | 0/1 |

Recovered counts triggers that were followed by what the fallback was for; it is given only where that applies. Tasks successful is a correlation, not a rescue rate: a fallback can fire in a task that succeeds for other reasons.

Did not fire: Tool arguments not JSON, error returned; Arguments rejected by the schema, or unknown tool; Invalid finish returned to the model; Reply without a tool call, nudged; Extra call skipped: one call per step; Call skipped after a failed call; Call skipped after a new page; Tool call failed, error returned; Returned to the last stable URL; Clicked by script: element has no box; Native dialog accepted; Long tool result cut; New tab opened by an action, closed; Page read retried: page busy; Settle ran out of time; Cut list followed by read_page(find/section); Forced finish on a budget; Task ended without an answer; Finish intercepted for a check; Skill steps loaded (load_skill); run_skill: gate passed, code run; run_skill: gate rejected, nothing run; Skill code stopped at a step; Skill steps handed to the model to follow; Lesson shown on a matching page; Model API call retried (429, 5xx, timeout); Reasoning effort rejected, downgraded; Switched to minimal request mode; Task ended by a model error; Task ended by a model refusal; Task ended by the spend cap; Browser not clean before the task, repaired; Browser restarted before the task; Harness error ended the task.
