---
name: cancel-sales-order
description: Find a Magento order by ID and cancel it, confirming the cancellation on the order page.
version: 1
params:
  order_id:
    type: integer
    description: The numeric ID of the order to cancel.
url_pattern: ^/
required_elements: []
preconditions: []
time_limit_s: 120.0
---

1. Open the Orders page at `/sales/order/` and check that the Orders page is open.
2. Search for the requested order ID in “Search by keyword” and submit. Check that the Orders list remains open, then read its table and identify the ID column from the header. Find the row whose ID ends with the requested numeric ID and check that the matching ID is shown.
3. In that row, click “View”. Check that the order detail URL contains the requested order ID and that the “Cancel” button is available.
4. Click “Cancel” and check that the confirmation dialog offers “OK”. Click “OK” and check for the success message “You canceled the order.”

Pitfalls: Magento displays order IDs with leading zeroes, so match the table ID by its ending digits rather than assuming the displayed ID is unpadded. The cancellation requires confirming the dialog with “OK”; clicking “Cancel” only opens that dialog.
