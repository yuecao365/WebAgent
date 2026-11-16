# baseline_test_r3: stopped, not a valid run

This run was stopped by hand after 13 of 45 tasks because it exposed a harness bug.
It has no summary and is not part of any table. It was not rerun.

## What happened

In task 216 the model clicked the product link "Electra Bra Top" on the review edit
page (`events.jsonl` of task 216, 21:37:29 UTC). The site opens that link in a new
browser tab. The harness stayed attached to its own tab, which was now in the
background, and nothing closes the new tab between tasks.

From the next task on (705, 706, 707, 108, 109, 110, 710) no click on a top-level menu
opened its submenu: the link shows as focused and the page text does not change. In
the first six tasks of this run, and in every task of runs 1 and 2, the menus open.
When the run was stopped the browser had two tabs: the agent's, and
`/admin/catalog/product/edit/id/1604/` (Electra Bra Top).

## Raw record

`records.jsonl` holds the 13 tasks that ended: 3 successes (345, 346, 347), 10
failures. Tasks 214, 215 and 216 failed before the new tab had any effect. The seven
after them ran with the agent's tab in the background and say nothing about the
agent. Task 711 was in progress when the run was stopped and has no record.

Spend of this run: $0.0454.
