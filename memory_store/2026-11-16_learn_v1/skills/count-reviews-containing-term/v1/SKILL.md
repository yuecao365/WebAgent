---
name: count-reviews-containing-term
description: Filter Magento product reviews by a review-text term and count the matching review records.
version: 1
params:
  term:
    type: string
    description: Term to search for in review text.
url_pattern: ^/admin/dashboard/$
required_elements:
- role: heading
  name: Dashboard
- role: link
  name:  MARKETING
preconditions:
- url: /admin/dashboard/
  why: Start on the admin dashboard to open the reviews grid.
time_limit_s: 120.0
---

1. Open the Marketing menu and check that its submenu contains “All Reviews”.
2. Choose “All Reviews” and check that the Reviews page is open.
3. In the grid’s Review filter field, enter the term parameter. Check that the field contains the entered term.
4. Click Search and check that the address is the filtered reviews grid.
5. Read the reviews table. Find the “ID” column by its header, count rows with a numeric ID, and return that count. Check that only the result rows are counted, not the header or filter row.

Pitfalls: The search must be applied with Search before counting. Count IDs in the filtered table rather than trying to count occurrences in the truncated review snippets or including the filter row.
