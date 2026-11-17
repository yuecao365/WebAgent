---
name: notify-customer-on-pending-order
description: Finds a customer's newest pending order and submits an emailed order comment.
version: 1
params:
  name:
    type: string
    description: Customer name whose most recent pending order should receive the notification.
  message:
    type: string
    description: Comment message to send to the customer.
url_pattern: ^/
required_elements: []
preconditions: []
time_limit_s: 120.0
---

1. Open the Orders page at `/sales/order/` and check that its order table is present.
2. Read the table, using its header row to identify ID, Bill-to Name, Ship-to Name, and Status. The table is shown newest-first by purchase date: choose the first row whose bill-to or ship-to name matches `name` and whose status is Pending. If no match is on the first page, go to the next page and check the table there before searching again. Check that a matching View link exists in the selected row.
3. Open that row's View link. Check that the order page belongs to `name` and shows Pending status.
4. Enter `message` in the Comment field and check the comment field is available.
5. Select Notify Customer by Email. Check that the notification control is present, then submit with Submit Comment. Check that the order history reports Customer Notified and includes `message`.

Pitfalls: Do not choose a customer's newest order without checking that its status is Pending; multiple orders can appear for the same customer. The list is paginated, so check the next page if needed. Adding a comment alone does not notify the customer: enable Notify Customer by Email before submitting. Do not use the separate Send Email order action.
