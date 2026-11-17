---
name: sales-orders-report-last-month
description: Open Magento's Orders Report for a supplied last-month date range and display the results.
version: 1
params:
  from_date:
    type: string
    description: Start date of the last-month reporting range, in the format shown by the report filter.
  to_date:
    type: string
    description: End date of the last-month reporting range, in the format shown by the report filter.
url_pattern: ^/
required_elements: []
preconditions: []
time_limit_s: 120.0
---

1. Open `/reports/report_sales/sales/` and check that the Orders Report page is displayed.
2. In the Filter group, enter `from_date` in the textbox named "From *" and `to_date` in the textbox named "To *". Check that both date fields are present.
3. Leave Date Used as Order Created and Period as Day, then click the "Show Report" button. Check that the address changes to the report's filter URL and the results are displayed.

Pitfalls:
- Enter both dates; the report will not run with either required date missing.
- Keep Period set to Day to show the daily intervals, as in the episode. The filter defaults to Day.
