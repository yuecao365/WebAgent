---
name: show-sales-report-date-range
description: Display the selected Sales report for a requested start and end date.
version: 1
params:
  report_type:
    type: string
    description: Sales report type, such as orders, tax, invoiced, shipping, refunds, or coupons.
  start_date:
    type: string
    description: Start date for the report, written as a month name, day, and year.
  end_date:
    type: string
    description: End date for the report, written as a month name, day, and year.
url_pattern: ^/admin/dashboard/$
required_elements:
- role: link
  name:  REPORTS
preconditions:
- url: /admin/dashboard/
  why: The dashboard has the Reports navigation link.
time_limit_s: 120.0
---

1. Open the Reports navigation menu. Check that the Sales report link matching the requested report type appears.
2. In the Sales section of the menu, select the corresponding report link (for example, orders selects “Orders”). Check that its report heading appears.
3. Convert the requested start and end dates to the date field's month/day/year format, and enter them in “From *” and “To *”. Check that each date field is present after entry.
4. Click “Show Report”. Check that the report results appear under the expected report heading.

Pitfalls: Choose the report link under Sales, not an identically themed report in another menu category. The report is not updated until “Show Report” is clicked. After submission, Magento may display dates in a shortened format; that does not mean the entered date was lost.
