---
name: show-sales-report
description: Open a Magento Sales report, apply the requested date span, and display its results.
version: 2
params:
  report:
    type: string
    description: The requested report; choose the matching Sales report menu item.
  start_date:
    type: string
    description: Start boundary of the requested time span, formatted MM/DD/YYYY.
  end_date:
    type: string
    description: End boundary of the requested time span, formatted MM/DD/YYYY.
url_pattern: ^/admin/dashboard/$
required_elements:
- role: link
  name:  REPORTS
preconditions:
- url: /admin/dashboard/
  why: The episode starts on the admin dashboard, where the Reports menu is available.
time_limit_s: 120.0
---

1. From the admin dashboard, open the Reports menu. Check that the Sales report links, including Orders, are visible.
2. Use the requested report to choose its matching Sales menu link. For example, the sales order report corresponds to Orders; other Sales report requests correspond to the matching menu entry such as Tax, Invoiced, Shipping, Refunds, or Coupons. Check that the report filter page has loaded.
3. In the filter, leave Date Used as Order Created and Period as Day unless the requested report requires otherwise. Enter the supplied start and end boundaries in From and To, respectively, in MM/DD/YYYY format. Check the date fields show those values.
4. Click Show Report. Check that the report results page is displayed and review its results table.

Pitfalls: The date interval is controlled by From and To; Period is the aggregation interval, not the date range. Keep the boundaries inclusive and in the expected date format. Do not confuse the Orders report with the separate Sales menu or the Customers reports.
