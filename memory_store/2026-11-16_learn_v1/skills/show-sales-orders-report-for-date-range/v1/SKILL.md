---
name: show-sales-orders-report-for-date-range
description: Open Magento's Orders Report, set the requested date range, and display the report.
version: 1
params:
  from_date:
    type: string
    description: Start date for the report, in MM/DD/YYYY format.
  to_date:
    type: string
    description: End date for the report, in MM/DD/YYYY format.
url_pattern: ^/admin/dashboard/$
required_elements:
- role: link
  name:  REPORTS
preconditions:
- url: ^/admin/dashboard/$
  why: Start on the Magento Admin dashboard.
time_limit_s: 120.0
---

1. On the dashboard, click link " REPORTS". Check that link "Orders" appears in the Reports menu.
2. Click link "Orders". Check that heading "Orders Report" appears.
3. In the Filter group, enter {from_date} in textbox "From *". Check that the field is present and the report page remains open.
4. Enter {to_date} in textbox "To *". Check that the field is present and the report page remains open.
5. Leave the other filters at their defaults, then click button "Show Report". Check that the address is under /reports/report_sales/sales/filter/ and the Orders Report is displayed.

Pitfalls:
- Use the requested date range, including the correct first and last day; for a previous calendar month, include the full month.
- The Period filter defaults to Day. Leave it unchanged when the requested report is the episode's date-range report; changing it alters the report grouping.
- Click Orders in the expanded Reports menu (the Sales report), not another report category.
