---
name: cancel-admin-order
description: Find an order by ID in Magento Admin, open it, cancel it, and confirm the cancellation.
version: 1
params:
  id:
    type: string
    description: The order ID to cancel.
url_pattern: ^/
required_elements: []
preconditions: []
time_limit_s: 120.0
---

1. Open `/sales/order/` and check that the Orders page is displayed.
2. Enter the requested order ID in `textbox "Search by keyword"`, submit with Enter, and check that the ID appears in the filtered results.
3. Read the results table, locate the `ID` column by its header, and identify the row whose displayed ID ends with the requested ID (the grid may show leading zeroes). Click that row's `link "View"`; check that the order heading matches the displayed ID.
4. Click `button "Cancel"` and check that the confirmation dialog offers `button "OK"`.
5. Click `button "OK"` and check for the cancellation confirmation message.

Pitfalls: The grid formats order IDs with leading zeroes, so match the requested ID against the displayed ID rather than assuming identical formatting. Cancellation requires confirming the dialog; check for the success message after confirmation, even if the interface briefly appears to stall.
