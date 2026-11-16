# 2026-11-16_smoke_optimized

Model: `gpt-6-luna`. Tasks: 5. Success: 3/5 (60%).

| Mean per task | Value |
|---|---:|
| Tokens | 16373 |
| USD | 0.0014 |
| Seconds | 25.0 |
| Steps | 6.4 |

Total: $0.0069, 81866 tokens. Finish reasons: {'finished': 5}.

## Tokens

Input: 96 uncached, 31725 read from cache, 49301 written to cache. Output: 744. Cache hit rate: 39%.

| Prompt section | Mean tokens per task (estimate) | Share |
|---|---:|---:|
| observation | 6228 | 38% |
| tools | 5024 | 31% |
| system | 4334 | 27% |
| history | 452 | 3% |
| task | 129 | 1% |
| notes | 36 | 0% |
| status | 21 | 0% |

## Tasks

| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |
|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| 344 | 248 | learn | yes | 8187 | 29% | 0.0008 | 10.1 | 3 | finished |
| 470 | 257 | learn | no | 15054 | 39% | 0.0013 | 27.2 | 6 | finished |
| 704 | 268 | learn | yes | 16641 | 43% | 0.0013 | 23.6 | 7 | finished |
| 496 | 284 | learn | yes | 23434 | 40% | 0.0019 | 43.8 | 9 | finished |
| 208 | 364 | learn | no | 18550 | 38% | 0.0016 | 20.0 | 7 | finished |
