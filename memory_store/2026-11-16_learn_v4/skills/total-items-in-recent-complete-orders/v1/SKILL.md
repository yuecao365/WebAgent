---
name: total-items-in-recent-complete-orders
description: Finds the newest complete orders and totals their ordered item quantities.
version: 1
params:
  k:
    type: integer
    description: How many of the most recent complete orders to include.
url_pattern: ^/admin/dashboard/$
required_elements:
- role: link
  name:  SALES
preconditions:
- url: /admin/dashboard/
  why: Begin on the admin dashboard before opening Sales > Orders.
time_limit_s: 120.0
---

1. Open the SALES menu and check that its menu includes the Orders link. Open Orders and check that the Orders page and order grid are shown.
2. Read the orders grid. Identify the Status, ID, and Purchase Date columns by their headers. In the grid's displayed newest-first order, select the first {{k}} rows whose Status is Complete. Skip orders in other statuses; if necessary, continue to the next grid page until {{k}} complete orders have been selected.
3. Open each selected order using its row's View link. Check that the order detail page is open, verify its status is Complete, and inspect the Items Ordered table. For every item row, add the ordered quantity shown in the Qty column. Return to the Orders grid and check it is shown before opening the next selected order.
4. Return the sum of the item quantities across those {{k}} orders.

Pitfalls:
- Do not take the first {{k}} orders overall; filter for Complete first, preserving newest-first ordering.
- Sum the quantities in the Qty column for each product row, not order totals, prices, or the number of product rows.
- Do not count canceled, pending, or processing orders.
