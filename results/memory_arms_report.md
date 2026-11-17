# Test tasks

## 1. Per arm

| Arm | Runs | Success per run | Mean | Std dev | All-of-n | Any-of-n | Steps | Model calls | Seconds | Tokens | USD per task | USD per successful task |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 3 | 34, 29, 28 of 45 | 30.3 | 3.2 | 26 | 36 | 8.2 ± 0.4 | 8.2 ± 0.4 | 38.6 ± 1.4 | 30,739 ± 2,690 | 0.0029 ± 0.0003 | 0.0043 |
| M1 | 1 | 32 of 45 | 32.0 | n/a | 32 | 32 | 7.5 | 7.5 | 33.9 | 34,215 | 0.0033 | 0.0047 |
| M2 | 1 | 32 of 45 | 32.0 | n/a | 32 | 32 | 7.9 | 7.9 | 35.6 | 41,045 | 0.0041 | 0.0058 |
| M3 | 1 | 29 of 45 | 29.0 | n/a | 29 | 29 | 8.4 | 8.4 | 37.7 | 43,010 | 0.0043 | 0.0066 |
| C | 1 | 37 of 45 | 37.0 | n/a | 37 | 37 | 9.7 | 9.7 | 52.2 | 38,931 | 0.0040 | 0.0048 |
| M2-high | 1 | 39 of 45 | 39.0 | n/a | 39 | 39 | 10.1 | 10.1 | 56.2 | 57,295 | 0.0060 | 0.0070 |

> One run each: M1, M2, M3, C, M2-high. Several runs: none (3). The 3 runs of none alone range from 28 to 34 of 45 tasks, a difference of 6. A difference of that size between two arms is within noise and is not an improvement or a loss.

## 2. Paired per task against none

| Arm vs baseline | Runs | Tasks | Fixed | Broken | Stabilized | Baseline mixed | Unchanged |
|---|---|---:|---:|---:|---:|---:|---:|
| M1 vs none | 1 vs 3 | 45 | 1 | 0 | n/a | 10 | 34 |
| M2 vs none | 1 vs 3 | 45 | 0 | 1 | n/a | 10 | 34 |
| M3 vs none | 1 vs 3 | 45 | 1 | 1 | n/a | 10 | 33 |
| C vs none | 1 vs 3 | 45 | 3 | 0 | n/a | 10 | 32 |
| M2-high vs none | 1 vs 3 | 45 | 6 | 0 | n/a | 10 | 29 |

**M1 vs none**
- fixed: 773 (0/3 → 1/1)
- broken: none
- baseline mixed (no conclusion from one run): 109 (1/3 → 0/1), 110 (1/3 → 0/1), 129 (1/3 → 1/1), 130 (1/3 → 0/1), 131 (1/3 → 1/1), 215 (1/3 → 0/1), 345 (2/3 → 1/1), 461 (2/3 → 1/1), 706 (1/3 → 1/1), 774 (2/3 → 0/1)

**M2 vs none**
- fixed: none
- broken: 346 (3/3 → 0/1)
- baseline mixed (no conclusion from one run): 109 (1/3 → 0/1), 110 (1/3 → 0/1), 129 (1/3 → 1/1), 130 (1/3 → 1/1), 131 (1/3 → 1/1), 215 (1/3 → 1/1), 345 (2/3 → 1/1), 461 (2/3 → 0/1), 706 (1/3 → 1/1), 774 (2/3 → 1/1)
  - broken 346: loaded count-all-reviews (steps only), filtered the reviews to 2022 once, reset the filter, typed the dates again, then clicked New Review instead of Search and finished with UNKNOWN_ERROR; the expected answer is 0

**M3 vs none**
- fixed: 200 (0/3 → 1/1)
- broken: 494 (3/3 → 0/1)
- baseline mixed (no conclusion from one run): 109 (1/3 → 0/1), 110 (1/3 → 0/1), 129 (1/3 → 0/1), 130 (1/3 → 1/1), 131 (1/3 → 1/1), 215 (1/3 → 0/1), 345 (2/3 → 1/1), 461 (2/3 → 0/1), 706 (1/3 → 0/1), 774 (2/3 → 0/1)
  - broken 494: opened the right order (304) and finished with NOT_FOUND_ERROR because the order names Alexander Thomas and the task says Alex Thomas; no comment was sent. Four lessons were shown on the way

**C vs none**
- fixed: 108 (0/3 → 1/1), 200 (0/3 → 1/1), 216 (0/3 → 1/1)
- broken: none
- baseline mixed (no conclusion from one run): 109 (1/3 → 1/1), 110 (1/3 → 1/1), 129 (1/3 → 1/1), 130 (1/3 → 1/1), 131 (1/3 → 1/1), 215 (1/3 → 1/1), 345 (2/3 → 1/1), 461 (2/3 → 1/1), 706 (1/3 → 0/1), 774 (2/3 → 0/1)

**M2-high vs none**
- fixed: 108 (0/3 → 1/1), 200 (0/3 → 1/1), 214 (0/3 → 1/1), 216 (0/3 → 1/1), 705 (0/3 → 1/1), 773 (0/3 → 1/1)
- broken: none
- baseline mixed (no conclusion from one run): 109 (1/3 → 1/1), 110 (1/3 → 1/1), 129 (1/3 → 1/1), 130 (1/3 → 1/1), 131 (1/3 → 1/1), 215 (1/3 → 1/1), 345 (2/3 → 1/1), 461 (2/3 → 0/1), 706 (1/3 → 0/1), 774 (2/3 → 0/1)

> One run each: M1, M2, M3, C, M2-high. Several runs: none (3). The 3 runs of none alone range from 28 to 34 of 45 tasks, a difference of 6. A difference of that size between two arms is within noise and is not an improvement or a loss.

## 3. Paired efficiency

Per-task difference from none (arm minus none); the interval is a 95% bootstrap interval of the mean over tasks.

| Arm | Steps: mean | median | 95% interval | Model calls: mean | median | 95% interval | Seconds: mean | median | 95% interval |
|---|---:|---:|---|---:|---:|---|---:|---:|---|
| M1 | -0.76 | -0.33 | -1.83 to +0.30 | -0.76 | -0.33 | -1.83 to +0.30 | -4.71 | -3.91 | -9.50 to +0.54 |
| M2 | -0.31 | -0.33 | -1.31 to +0.77 | -0.31 | -0.33 | -1.31 to +0.77 | -3.03 | -2.27 | -6.80 to +1.03 |
| M3 | +0.20 | +0.00 | -0.93 to +1.36 | +0.20 | +0.00 | -0.93 to +1.36 | -0.97 | -0.93 | -4.74 to +2.95 |
| C | +1.44 | +0.00 | +0.22 to +2.73 | +1.44 | +0.00 | +0.22 to +2.73 | +13.51 | +4.94 | +5.46 to +22.51 |
| M2-high | +1.87 | +0.67 | +0.44 to +3.49 | +1.87 | +0.67 | +0.44 to +3.49 | +17.53 | +3.40 | +8.48 to +28.02 |

> One run each: M1, M2, M3, C, M2-high. Several runs: none (3). The 3 runs of none alone range from 28 to 34 of 45 tasks, a difference of 6. A difference of that size between two arms is within noise and is not an improvement or a loss.

## 4. Skills

| Arm | Task runs | Called load_skill | Called run_skill | Gate passed | Gate rejected | Code ran through | Code stopped | Handed to model | Successful after hand-over | Code ran through, task failed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 45 | 28 | 13 | 10 | 3 | 9 | 1 | 4 | 2/4 | 4 |
| M2 | 45 | 15 | 6 | 4 | 2 | 4 | 0 | 2 | 2/2 | 3 |
| M3 | 45 | 11 | 10 | 4 | 6 | 4 | 0 | 6 | 5/6 | 3 |
| M2-high | 45 | 20 | 10 | 5 | 5 | 5 | 0 | 5 | 5/5 | 1 |

- M1: gate rejections by check: no_code 3.
  Code ran through but the task failed: m1_test_r1/108, m1_test_r1/109, m1_test_r1/110, m1_test_r1/705.
- M2: gate rejections by check: no_code 2.
  Code ran through but the task failed: m2_test_r1/108, m2_test_r1/109, m2_test_r1/110.
- M3: gate rejections by check: no_code 6.
  Code ran through but the task failed: m3_test_r1/108, m3_test_r1/109, m3_test_r1/110.
- M2-high: gate rejections by check: no_code 5.
  Code ran through but the task failed: m2high_test_r1b/706.

Skill code ran through and the task failed, from the traces:

- M1 task 108: in the skill: monthly-orders-report code ran through and returned the counts of the Orders report with Order Status left at Any; the answer was passed on unchanged
- M1 task 109: in the skill: monthly-orders-report code ran through and returned the counts of the Orders report with Order Status left at Any; the answer was passed on unchanged
- M1 task 110: in the skill: monthly-orders-report code ran through and returned the counts of the Orders report with Order Status left at Any; the answer was passed on unchanged
- M1 task 705: before the skill: show-sales-report did what it was told; the model passed start date 01/30 where 01/29 is expected
- M2 task 108: in the skill: monthly-orders-report code ran through and returned the counts of the Orders report with Order Status left at Any; the answer was passed on unchanged
- M2 task 109: in the skill: monthly-orders-report code ran through and returned the counts of the Orders report with Order Status left at Any; the answer was passed on unchanged
- M2 task 110: in the skill: monthly-orders-report code ran through and returned the counts of the Orders report with Order Status left at Any; the answer was passed on unchanged
- M3 task 108: in the skill: monthly-orders-report code ran through and returned the counts of the Orders report with Order Status left at Any; the answer was passed on unchanged
- M3 task 109: in the skill: monthly-orders-report code ran through and returned the counts of the Orders report with Order Status left at Any; the answer was passed on unchanged
- M3 task 110: in the skill: monthly-orders-report code ran through and returned the counts of the Orders report with Order Status left at Any; the answer was passed on unchanged
- M2-high task 706: before the skill: show-sales-report did what it was told; the model passed end date 03/15 (today) where Q1 ends 03/31

> One run each: M1, M2, M3, C, M2-high. Several runs: none (3). The 3 runs of none alone range from 28 to 34 of 45 tasks, a difference of 6. A difference of that size between two arms is within noise and is not an improvement or a loss.

## 5. Memory by effort

| | effort low | effort high |
|---|---|---|
| memory off | none: 30.3 ± 3.2 of 45 (3 run(s)); $0.0043 per successful task | C: 37 of 45 (1 run(s)); $0.0048 per successful task |
| memory on | M2: 32 of 45 (1 run(s)); $0.0058 per successful task | M2-high: 39 of 45 (1 run(s)); $0.0070 per successful task |

> One run each: M1, M2, M3, C, M2-high. Several runs: none (3). The 3 runs of none alone range from 28 to 34 of 45 tasks, a difference of 6. A difference of that size between two arms is within noise and is not an improvement or a loss.

| Arm vs baseline | Runs | Tasks | Fixed | Broken | Stabilized | Baseline mixed | Unchanged |
|---|---|---:|---:|---:|---:|---:|---:|
| M2-high vs C | 1 vs 1 | 45 | 3 | 1 | n/a | 0 | 41 |
| M2-high vs M2 | 1 vs 1 | 45 | 9 | 2 | n/a | 0 | 34 |
| C vs M2 | 1 vs 1 | 45 | 7 | 2 | n/a | 0 | 36 |

**M2-high vs C**
- fixed: 214 (0/1 → 1/1), 705 (0/1 → 1/1), 773 (0/1 → 1/1)
- broken: 461 (1/1 → 0/1)
- baseline mixed (no conclusion from one run): none
  - broken 461: loaded adjust-current-product-price (steps only), typed 29.50 and then 41.00, and saved 41.00: the increase was applied twice

**M2-high vs M2**
- fixed: 108 (0/1 → 1/1), 109 (0/1 → 1/1), 110 (0/1 → 1/1), 200 (0/1 → 1/1), 214 (0/1 → 1/1), 216 (0/1 → 1/1), 346 (0/1 → 1/1), 705 (0/1 → 1/1), 773 (0/1 → 1/1)
- broken: 706 (1/1 → 0/1), 774 (1/1 → 0/1)
- baseline mixed (no conclusion from one run): none
  - broken 706: show-sales-report code ran through with the arguments the model passed: end date 03/15 (today) where Q1 ends 03/31
  - broken 774: deleted reviews 353, 351 and 349 with the mass action after opening 353 five times; the evaluator accepts only the single-review delete requests

**C vs M2**
- fixed: 108 (0/1 → 1/1), 109 (0/1 → 1/1), 110 (0/1 → 1/1), 200 (0/1 → 1/1), 216 (0/1 → 1/1), 346 (0/1 → 1/1), 461 (0/1 → 1/1)
- broken: 706 (1/1 → 0/1), 774 (1/1 → 0/1)
- baseline mixed (no conclusion from one run): none
  - broken 706: right report and dates (01/01 to 03/31), but Date Used was changed to Last Credit Memo Created Date and Period to Month; the evaluator expects the order-created report type
  - broken 774: deleted reviews 353, 351 and 349 with the mass action; the evaluator accepts only the single-review delete requests

## 7. Failure classes

| Failure class | none (3 runs) | M2 (1 runs) |
|---|---:|---:|
| Action not done or done wrongly | 11 | 4 |
| Done as asked, but the evaluator cannot accept it | 3 | 1 |
| Gave up or reported not found | 7 | 1 |
| Ran out of budget, stuck, or the model call failed | 3 | 1 |
| The page does not show the information | 8 | 2 |
| Wrong page or filter | 12 | 4 |
| All failed task runs | 44 | 13 |

> One run each: M1, M2, M3, C, M2-high. Several runs: none (3). The 3 runs of none alone range from 28 to 34 of 45 tasks, a difference of 6. A difference of that size between two arms is within noise and is not an improvement or a loss.

# Probe tasks

## 1. Per arm

| Arm | Runs | Success per run | Mean | Std dev | All-of-n | Any-of-n | Steps | Model calls | Seconds | Tokens | USD per task | USD per successful task |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 1 | 8 of 12 | 8.0 | n/a | 8 | 8 | 13.2 | 13.2 | 75.9 | 52,204 | 0.0049 | 0.0073 |
| M2 | 1 | 3 of 12 | 3.0 | n/a | 3 | 3 | 12.4 | 12.4 | 67.8 | 68,454 | 0.0068 | 0.0273 |

> One run each: none, M2. none was run once on these 12 tasks too, so the run-to-run spread on them was not measured; no difference here can be told from noise.

## 2. Paired per task against none

| Arm vs baseline | Runs | Tasks | Fixed | Broken | Stabilized | Baseline mixed | Unchanged |
|---|---|---:|---:|---:|---:|---:|---:|
| M2 vs none | 1 vs 1 | 12 | 0 | 5 | n/a | 0 | 7 |

**M2 vs none**
- fixed: none
- broken: 112 (1/1 → 0/1), 245 (1/1 → 0/1), 453 (1/1 → 0/1), 769 (1/1 → 0/1), 770 (1/1 → 0/1)
- baseline mixed (no conclusion from one run): none
  - broken 112: filtered the reviews to the product, found two, and finished with UNKNOWN_ERROR because the grid shows no star rating, without opening a review; no skill was loaded
  - broken 245: answered Merrie from the filtered grid after 5 steps without opening the reviews (Shaunte expected); no skill was loaded
  - broken 453: opened the product and clicked the Enable Product switch again and again (the same call three times in a row, three times) without saving; ended stuck
  - broken 769: updated four of the five sizes (M, XS, L, S), never opened XL, and finished with SUCCESS after 28 steps
  - broken 770: opened the configurable parent product instead of the two simple products and finished with UNKNOWN_ERROR after 7 steps

> One run each: none, M2. none was run once on these 12 tasks too, so the run-to-run spread on them was not measured; no difference here can be told from noise.

## 3. Paired efficiency

Per-task difference from none (arm minus none); the interval is a 95% bootstrap interval of the mean over tasks.

| Arm | Steps: mean | median | 95% interval | Model calls: mean | median | 95% interval | Seconds: mean | median | 95% interval |
|---|---:|---:|---|---:|---:|---|---:|---:|---|
| M2 | -0.75 | -0.50 | -2.58 to +1.00 | -0.75 | -0.50 | -2.58 to +1.00 | -8.06 | -0.48 | -22.17 to +4.88 |

> One run each: none, M2. none was run once on these 12 tasks too, so the run-to-run spread on them was not measured; no difference here can be told from noise.

# 8. One-time cost of building memory

| Build | Calls | USD | By kind of call |
|---|---:|---:|---|
| learn_v1 | 31 | 0.0472 | induce 17 ($0.0333), facts 13 ($0.0123), merge 1 ($0.0016) |
| learn_v2 | 4 | 0.0067 | induce 4 ($0.0067) |
| learn_v3 | 53 | 0.0835 | induce 17 ($0.0376), facts 13 ($0.0122), merge 2 ($0.0021), reflect 15 ($0.0302), verify 6 ($0.0013) |
| learn_v4 | 5 | 0.0057 | remerge 5 ($0.0057) |
| All builds | 93 | 0.1431 | |

