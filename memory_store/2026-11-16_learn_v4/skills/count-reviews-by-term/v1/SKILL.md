---
name: count-reviews-by-term
description: Search Magento customer reviews for a supplied term and return the number of matching review records.
version: 1
params:
  term:
    type: string
    description: Term to search for in review text.
url_pattern: ^/admin/dashboard/$
required_elements:
- role: link
  name:  MARKETING
preconditions:
- url: /admin/dashboard/
  why: Start on the admin dashboard to open the customer reviews list.
time_limit_s: 120.0
---

1. Open Marketing, then choose All Reviews under User Content. Check that the Reviews page and its review filters are displayed.
2. Enter the supplied term in the Review filter (not the Title or Nickname filter), then click Search. Check that the filtered Reviews page reports its matching records.
3. Set the per-page option to 200 and check that the review table is still displayed. Read the table and return the number of data rows (the table's first row is its header) as the matching-review count.

Pitfalls: Typing in the filter does not apply it; click Search. The term belongs in the Review filter. Do not mistake a visible row on the unfiltered list for a matching result; count rows only after applying the filter.
