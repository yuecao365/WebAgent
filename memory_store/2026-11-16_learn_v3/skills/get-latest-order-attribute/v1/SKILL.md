---
name: get-latest-order-attribute
description: Find the newest Magento order matching a requested status and retrieve its customer email.
version: 1
params:
  attribute:
    type: string
    description: Customer attribute to retrieve; supported attribute is customer email.
  status:
    type: string
    description: Status and recency criterion, such as most recent cancelled or most recent pending.
url_pattern: ^/
required_elements: []
preconditions: []
time_limit_s: 120.0
---

1. Open `/sales/order/` and check that the `Orders` heading is shown.
2. Read the Orders table and locate the `Status` and `ID` columns by their headers. Take the requested status (the final word of the status phrase); match it to the grid spelling, treating `cancelled` and `canceled` as equivalent. The grid is ordered newest first by Purchase Date, so select the first row with that status. Check that the matching order ID is present.
3. Click `View` in the matching order's row and check that the order-view page has opened.
4. For the `customer email` attribute, inspect the `Information` panel's Account Information and find the value on the `Email` row. Return that email.

Pitfalls: The grid spells the status `Canceled` with one “l”; the request may use “cancelled.” Use the first row matching the status because the grid is newest-first, rather than the first row of any status. Find columns by their headers, not fixed positions.
