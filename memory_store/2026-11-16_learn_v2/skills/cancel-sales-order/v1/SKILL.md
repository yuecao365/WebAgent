---
name: cancel-sales-order
description: Find an order in Magento Admin, cancel it, confirm the dialog, and verify the success message.
version: 1
params:
  order_id:
    type: integer
    description: The order number to cancel.
url_pattern: ^/
required_elements: []
preconditions: []
time_limit_s: 120.0
---

1. Open the Orders page at `/sales/order/` and check that the address is `/sales/order/`.
2. Enter `order_id` in the `Search by keyword` field and submit. Check that the Orders page remains open.
3. Read the orders table. Find the `ID` column by its header, then locate the row whose ID ends with `order_id` (the displayed IDs may be zero-padded). Check that the matching ID is present, then click that row's `View` link. Check that the order detail address is `/sales/order/view/order_id/` followed by `order_id` and a trailing slash.
4. Click `Cancel` on the order detail page. Check that the confirmation dialog shows an `OK` button.
5. Click `OK` to confirm cancellation. Check for the success message `You canceled the order.`

Pitfalls: The order list displays zero-padded IDs, so match the requested number against the `ID` column rather than assuming the displayed ID is unpadded. Clicking `Cancel` only opens a confirmation dialog; the cancellation is not complete until `OK` is clicked and the success message appears.
