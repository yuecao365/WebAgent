---
name: reduce-product-price
description: Reduce the current Magento product's price by a specified amount and save the product.
version: 1
params:
  reduction_amount:
    type: integer
    description: Amount to subtract from the current price, in dollars.
url_pattern: ^/catalog/product/edit/id/[0-9]+/$
required_elements:
- role: textbox
  name: '[global] Price * $'
preconditions:
- url: ^/catalog/product/edit/id/[0-9]+/$
  why: Start on the product edit page whose price should be changed.
- role: textbox
  name: '[global] Price * $'
  why: The product price field must be available.
time_limit_s: 120.0
---

1. Read the current value of textbox "[global] Price * $". Remove any currency symbol or thousands separators, parse the amount, and subtract reduction_amount dollars. Check that the resulting price is the intended current price minus reduction_amount.
2. Replace the contents of textbox "[global] Price * $" with the resulting amount formatted to two decimal places. Check that the price field is still present.
3. Click button "Save". Check that the page displays "You saved the product." 

Pitfalls: Subtract from the price currently shown on this product rather than entering a fixed target price. Save the edited value; typing alone does not persist the change.
