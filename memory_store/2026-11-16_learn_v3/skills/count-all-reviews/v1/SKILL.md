---
name: count-all-reviews
description: Find the total number of reviews recorded in the Magento Admin reviews grid.
version: 1
params:
  time:
    type: string
    description: The time period the question asks about; use the all-time review total for an all-time request.
url_pattern: ^/admin/dashboard/$
required_elements:
- role: link
  name:  MARKETING
preconditions:
- url: /admin/dashboard/
  why: Start from the admin dashboard so the Marketing menu can be opened.
time_limit_s: 120.0
---

1. On the dashboard, click the “ MARKETING” link. Check that the expanded menu contains “All Reviews” under User Content.
2. Click “All Reviews”. Check that the Reviews page is open (the page address is /review/product/index/ and its heading is “Reviews”).
3. For an all-time request, read the total-records-found indicator above the reviews table and report its number as the number of reviews received. This grid total, rather than the visible first-page row count, is the answer.

Pitfalls: The grid is paginated, so do not count only the rows currently displayed. Do not confuse the separate Pending Reviews view with All Reviews.
