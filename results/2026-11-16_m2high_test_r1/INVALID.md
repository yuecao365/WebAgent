# m2high_test_r1: 42 of 45 tasks did not run

Three tasks ran (345, 346, 347; all successful). In the fourth (214) the machine ran out
of memory: the browser-harness daemon logged `MemoryError: Unable to allocate output
buffer` while receiving a page (D:\browser-agent-data\arm2\bh\tmp\bu-default.log), its
connection to the browser died ("sent 1011 (internal error)"), and the page could not be
read. The harness does not restart the browser when the reset between two tasks fails, so
the 41 tasks after it were recorded as harness errors without running.

The raw record is kept as it is: 3 of 45, 42 harness errors. The 42 tasks are run once
more as `m2high_test_r1_retry` and reported separately.

Later note: that plan was replaced. After the harness learned to restart a lost browser
(commit 5dd6148), all 45 tasks were run again as `2026-11-16_m2high_test_r1b`; that run is
the one in the tables. This directory is in no table. Two site containers and two
browsers were running at the time, with about 1 GB of memory free.
