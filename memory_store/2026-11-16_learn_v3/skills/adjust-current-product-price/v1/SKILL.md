---
name: adjust-current-product-price
description: Adjusts the current product's price by a specified dollar amount, then saves the product.
version: 1
params:
  action:
    type: string
    description: Whether to reduce or increase the current product price.
  amount:
    type: string
    description: Dollar amount to add or subtract, such as a dollar sign followed by a number.
url_pattern: ^/catalog/product/edit/id/[^/]+/
required_elements:
- role: textbox
  name: '[global] Price * $'
- role: button
  name: Save
preconditions:
- url: ^/catalog/product/edit/id/[^/]+/
  why: The skill applies to the product edit page currently open.
time_limit_s: 120.0
---

1. Read the value in textbox "[global] Price * $" and parse it as a dollar amount. Remove the dollar sign from {{amount}} and parse that amount too. Check that the price field is available and its current value can be read.
2. If {{action}} is Reduce, subtract {{amount}} from the current price; if it is Increase, add {{amount}}. Enter the computed price into textbox "[global] Price * $". Check that the price field is still present and shows the computed value.
3. Click button "Save". Check for the confirmation text "You saved the product.".

Pitfalls: Calculate from the current price instead of assuming a fixed starting price or fixed result. Save after changing the field, and wait for the saved confirmation before treating the change as complete.
