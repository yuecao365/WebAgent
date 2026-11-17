---
name: show-orders-report-by-date-range
description: Open Magento's Orders Report, apply a date range, and display the report results.
version: 1
params:
  from_date:
    type: string
    description: Beginning date for the report, formatted as MM/DD/YYYY.
  to_date:
    type: string
    description: Ending date for the report, formatted as MM/DD/YYYY.
url_pattern: ^/
required_elements: []
preconditions: []
time_limit_s: 120.0
---

1. Open `/reports/report_sales/sales/` and check that the page shows the **Orders Report** heading.
2. Enter `from_date` in the **From \*** field and check that the field is present. Enter `to_date` in the **To \*** field and check that the field is present.
3. Click **Show Report** and check that the results include a **Total** row.

Pitfalls: Enter dates in the report's expected month/day/year format. Changing the date fields alone does not refresh the report; click **Show Report**.
