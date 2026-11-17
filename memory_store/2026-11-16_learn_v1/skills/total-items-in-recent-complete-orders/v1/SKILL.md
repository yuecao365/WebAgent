---
name: total-items-in-recent-complete-orders
description: Find the item quantity total across the most recent requested number of complete orders.
version: 1
params:
  order_count:
    type: integer
    description: How many of the most recent complete orders to include.
url_pattern: ^/
required_elements: []
preconditions: []
time_limit_s: 120.0
---

1. Open the Orders grid at `/sales/order/`. Check that the Orders heading and order table are visible, and that Purchase Date is sorted newest first; if it is not, sort it descending.
2. Scan the rows in date order, continuing to later grid pages if needed. Keep only rows whose Status is Complete, stopping once you have found `order_count` such rows. Check each selected row's date and status so the chosen orders are the newest complete ones, not simply the newest orders of any status.
3. Open each selected order with its row's View link. Check the order heading/number and that the order status is Complete. In the Items Ordered table, find the Qty column by its header and add the ordered quantity for every product line in that order. Check all product rows have been included before moving to the next selected order.
4. Add the quantities from the selected orders and return that total as the answer. Check that the answer is a count of items, not a count of orders or a sum of prices.

Pitfalls: Newer rows may be Pending, Processing, or Canceled and must be skipped. An order can contain multiple product lines; sum each line's quantity. Do not assume the order number indicates recency; use Purchase Date.
