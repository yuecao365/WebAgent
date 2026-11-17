---
name: find-customer-by-phone
description: Finds a customer by phone number in Magento Admin and returns their name and email.
version: 1
params:
  PhoneNum:
    type: string
    description: The phone number to search for.
url_pattern: ^/admin/dashboard/$
required_elements:
- role: link
  name:  CUSTOMERS
preconditions:
- url: ^/admin/dashboard/$
  why: The skill starts from the Magento Admin dashboard.
time_limit_s: 120.0
---

1. From the dashboard, open the CUSTOMERS menu and check that the All Customers link appears. 2. Open All Customers and check that the Customers page is open. 3. Enter the supplied phone number in Search by keyword, click Search, and check that the customer table is present. 4. Read the table, locate the Name, Email, and Phone columns by their headers, and select the row whose phone matches the supplied number (allowing a leading country code in the displayed phone). Return a list containing an object with the matching name and email. Pitfalls: The customer menu must be expanded before choosing All Customers. The Name column header may include a sort indicator, so identify it by its ending text rather than a fixed column position. Do not assume the Phone column's position.
