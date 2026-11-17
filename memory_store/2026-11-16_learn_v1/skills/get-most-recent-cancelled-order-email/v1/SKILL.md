---
name: get-most-recent-cancelled-order-email
description: Find the newest cancelled order in Magento’s orders grid and return the customer email.
version: 1
params: {}
url_pattern: ^/admin/dashboard/$
required_elements:
- role: link
  name:  SALES
preconditions: []
time_limit_s: 120.0
---

1. Open the SALES menu and check that its Orders link appears.
2. Open Orders and check that the orders grid is at /sales/order/.
3. Read the orders table. Locate the ID and Status columns by their header names. The Purchase Date column is ordered newest first; choose the first row whose Status is Canceled. Check that a cancelled-order ID was found.
4. Click View in the row identified by that order ID, then check that the order page shows the ID.
5. Read the Information panel, find the email value in its Email row, and return it.

Pitfalls: The newest order may not be cancelled, so check statuses while scanning. Do not use a cancelled order from a later/older part of the grid when a newer cancelled row is shown. Match the table columns by header, not fixed positions.
