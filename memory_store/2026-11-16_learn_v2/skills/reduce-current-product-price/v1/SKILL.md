---
name: reduce-current-product-price
description: Reduce the price on the currently open Magento product form by a specified amount and save the product.
version: 1
params:
  discount:
    type: number
    description: Amount to subtract from the current product price.
url_pattern: ^/catalog/product/edit/
required_elements:
- role: textbox
  name: '[global] Price * $'
- role: button
  name: Save
preconditions:
- url: ^/catalog/product/edit/
  why: The task is to change the product currently open in the catalog editor.
time_limit_s: 120.0
---

1. Read the current value in textbox "[global] Price * $" and calculate the new price by subtracting discount. Check that the calculated price is displayed in the price field after entering it.
2. Click button "Save". Check for the saved-product confirmation before finishing.

Pitfalls:
- Calculate the updated value from the current field; do not assume or hardcode the product's original or final price.
- Entering a value does not persist it; click Save and confirm the save message.
