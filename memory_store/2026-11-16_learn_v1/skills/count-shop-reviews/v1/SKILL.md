---
name: count-shop-reviews
description: Count all reviews in Magento Admin by reading review IDs across the paginated review grid.
version: 1
params: {}
url_pattern: ^/
required_elements: []
preconditions: []
time_limit_s: 120.0
---

1. Open the Reviews grid at `/review/product/index/` and check that the address is the review-index page.
2. Set the “per page” dropdown to 200. Check that the grid pagination shows two pages.
3. Read the table and count rows with a numeric value in the column headed “ID”; ignore the header and filter rows.
4. Go to the next page and check that the review page is still open. Read the table again and count numeric IDs using the “ID” header.
5. Add the two page counts and return the total.

Pitfalls: The grid initially shows only 20 of the reviews, so do not report the number of visible rows. The table also contains a header and filter row; count rows by numeric IDs and locate the ID column by its header rather than assuming a column position.
