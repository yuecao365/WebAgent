---
name: notify-customer-pending-order
description: Find a customer's newest pending order and submit an email-notified order comment.
version: 1
params:
  customer_name:
    type: string
    description: The customer's full name.
  message:
    type: string
    description: The comment to send to the customer.
url_pattern: ^/admin/dashboard/$
required_elements:
- role: heading
  name: Dashboard
preconditions:
- role: heading
  name: Dashboard
  why: The workflow starts on the Magento admin dashboard.
time_limit_s: 120.0
---

1. Open the Sales menu, then choose Orders. Check that the Orders page appears.
2. Search the orders for the customer by entering their name in Search by keyword and clicking Search. Check that the filtered results show the customer.
3. Read the orders table and identify the ID, Bill-to Name, Ship-to Name, and Status columns by their headers. Starting at the first result (newest purchase date first), find the first row where the customer is the bill-to or ship-to name and the status is Pending. Open View for that row and check that the heading identifies that order.
4. Enter the message in Comment and check that it is present. Enable Notify Customer by Email and check that it is enabled.
5. Click Submit Comment. Check that the message appears in the order's comment history.

Pitfalls: Select the newest matching pending order, not merely the first pending order overall. Confirm the customer matches either the bill-to or ship-to name. Enable Notify Customer by Email before submitting; submitting without it will not notify the customer.
