---
name: monthly-orders-report
description: Retrieve monthly order counts for an inclusive date range from Magento's Orders Report.
version: 1
params:
  start_date:
    type: string
    description: Inclusive start date in the report's MM/DD/YYYY format.
  end_date:
    type: string
    description: Inclusive end date in the report's MM/DD/YYYY format.
url_pattern: ^/admin/dashboard/$
required_elements:
- role: heading
  name: Dashboard
- role: link
  name:  REPORTS
preconditions:
- url: ^/admin/dashboard/$
  why: The task starts on the Magento Admin dashboard.
- role: heading
  name: Dashboard
  why: Confirms the current page is the dashboard.
time_limit_s: 120.0
---

1. On the Magento Admin dashboard, open the Reports menu and choose Sales > Orders. Check that the Orders Report page appears.
2. Set Period to Month. Enter the requested inclusive start and end dates in the From * and To * fields, respectively, using the report's MM/DD/YYYY format. Check each field remains present after entry.
3. Click Show Report and check that the report results page loads.
4. Read the results table. Find the Interval and Orders columns by their header text. For each monthly row, return an object with the month name and the integer in Orders; omit the Total row. Return only this list.

Pitfalls: Use the Orders column, not Sales Items or the aggregate Total. Set the interval to Month before running the report, and enter both inclusive date bounds before clicking Show Report. Do not mistake the initial empty table for the filtered results.
