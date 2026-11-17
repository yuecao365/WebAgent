---
name: add-order-shipment-tracking
description: Create a shipment for an order with a selected carrier and tracking number, then verify shipment creation.
version: 1
params:
  order_id:
    type: string
    description: The order ID without display padding.
  carrier:
    type: string
    description: The carrier to assign to the shipment.
  tracking_number:
    type: string
    description: The carrier's tracking number.
url_pattern: ^/
required_elements: []
preconditions: []
time_limit_s: 120.0
---

1. Open the order detail page at `/sales/order/view/order_id/{order_id}/`. Check that the order detail page for the requested order is open.
2. Click **Ship**. Check that the **New Shipment** heading is shown.
3. Click **Add Tracking Number**. Check that the carrier selector is present.
4. Choose the requested carrier in **Carrier**. Check the carrier selection step has completed on the shipment form.
5. Enter the requested tracking number in **Number**. Check the number field is present with the form still open.
6. Click **Submit Shipment**. Check for the success message **The shipment has been created.**

Pitfalls: Submitting this form creates a shipment and fulfills the listed quantities; it is not merely an edit to tracking metadata. Confirm that creating a shipment is intended. Select the carrier before entering the number, since choosing a carrier may populate its title automatically. Verify the order ID before submitting.
