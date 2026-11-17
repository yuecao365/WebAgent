---
name: add-order-shipment-tracking
description: Create a shipment for an order with a selected carrier and tracking number.
version: 1
params:
  order:
    type: string
    description: Order ID to ship.
  service:
    type: string
    description: Carrier/service option to use for the tracking entry.
  tracking:
    type: string
    description: Tracking number to add.
url_pattern: ^/
required_elements: []
preconditions: []
time_limit_s: 120.0
---

1. Open the Sales > Orders list at /sales/order/ and check that the Orders heading is shown.
2. Read the orders table, find the ID column by its header, and locate the row whose ID matches the requested order (ignore leading zeroes). Open that row's View link and check that the order detail page is open.
3. Click Ship and check that the New Shipment page is open.
4. Click Add Tracking Number and check that a tracking entry row appears with Carrier, Title, and Number fields.
5. In the tracking entry row, select the requested service from the Carrier dropdown and check that the selected service is displayed. Enter the requested tracking value in the row's Number field and check that it appears.
6. Click Submit Shipment and check for the shipment-created confirmation.

Pitfalls: Order IDs in the list are zero-padded; match the ID column rather than relying on row position. Add the tracking row before entering carrier details, and do not submit until both the carrier and number are filled. The carrier and number controls are visually grouped in the tracking row and may have no accessible names; target the correct row rather than an unrelated textbox.
