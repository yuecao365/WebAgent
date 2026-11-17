---
name: get-total-review-count
description: Find the total number of reviews from the Magento Admin reviews listing.
version: 1
params: {}
url_pattern: ^/admin/dashboard/$
required_elements:
- role: link
  name:  MARKETING
preconditions:
- url: ^/admin/dashboard/$
  why: Start from the Magento Admin dashboard.
time_limit_s: 120.0
---

1. Click the link " MARKETING" and check that the menu now shows the link "All Reviews".
2. Click the link "All Reviews" and check that the page heading is "Reviews".
3. Read the total shown in the listing's records-found summary, rather than counting the currently visible table rows; return that number.

Pitfalls: The listing is paginated, so the visible rows are only a page of reviews, not the total. The dashboard itself does not show the review count.
