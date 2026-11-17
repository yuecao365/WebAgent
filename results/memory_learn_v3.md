# Memory build 2026-11-16_learn_v3

Model `gpt-6-luna`, code 641e469, from runs 2026-11-16_learn_b2, 2026-11-16_learn_c2, 2026-11-16_learn_check_off, 2026-11-16_learn_check_on.

Model calls for this build: 53, $0.0835.

## Skills

| Skill | Template | Source task | Parameters (slot) | Code | Verdict |
|---|---:|---:|---|---|---|
| adjust-current-product-price v1 | 247 | 458 | action (action), amount (amount) | none | the original replay failed: the verifier: The product page shows a saved confirmation, but its price is still $27.00 instead of the required reduced price of $22.00. |
| count-all-reviews v1 | 248 | 344 | time (time) | none | no candidate code: the model wrote no code |
| cancel-admin-order v1 | 257 | 470 | id (id) | none | the original replay failed: line 14: IndexError: list index out of range |
| show-sales-report-date-range v1 | 271 | 709 | report_type (type), start_date (start_date), end_date (end_date) | none | the original replay failed: step 3 click(role='link', name='Orders', section='Sales'): no element matches link "Orders" in the section "Sales"; link "Orders" exists, but not in that row or section |
| notify-customer-on-pending-order v1 | 280 | 492 | name (name), message (message) | none | the original replay failed: step 15 check(text='Customer Notified'): check failed: the page does not show "Customer Notified" |
| add-order-shipment-tracking v1 | 284 | 496 | order (order), service (service), tracking (tracking) | none | no candidate code: the model wrote no code; other_args {"order": "65", "service": "DHL", "tracking": "8974568499"} not used: a held-out task uses 65; first attempt refused: the code carries literal values of the task: Federal Express |
| count-reviews-by-term v1 | 288 | 11 | term (term) | none | the original replay failed: step 5 type(role='textbox', name='detail', text='disappointed'): no element matches textbox "detail"; elements with role textbox are named "From", "To", "of 18", "" |
| find-customer-by-phone v1 | 364 | 208 | PhoneNum (PhoneNum) | none | the original replay failed: the gate rejects it on the task's start page: 2 elements match link " CUSTOMERS", where exactly one is needed |
| get-latest-order-attribute v1 | 366 | 198 | attribute (attribute), status (status) | none | the original replay failed: it did not reproduce the episode's outcome (returned "was"; the agent had answered ["harrypotterfan1@gmail.com"]) |
| total-items-in-recent-complete-orders v1 | 1002 | 128 | k (k) | none | no candidate code: the model wrote no code |
| change-cms-page-title v2 | 275 | 486 | old_heading (old_heading), heading (heading) | kept | all 3 replays passed |
| monthly-orders-report v2 | 270 | 107 | start_date (period), end_date (period) | kept | all 1 replays passed |
| show-sales-report v2 | 268 | 704 | report (report), start_date (time_span), end_date (time_span) | kept | all 1 replays passed |

Templates without a successful learn episode (no skill): [246, 249]

## Site facts

26 active, 18 retired versions.

- `fact-001@v1` on `/catalog/product/edit/` (tasks 458): A product's edit page is under Catalog and includes a global Price field and a Save button; saving displays a confirmation while remaining on the product editor.
- `fact-003@v1` on `/review/product/index/` (tasks 344): The All Reviews grid displays a total record count above the table and supports filtering reviews by status, title, nickname, product, and other columns.
- `fact-006@v1` on `/sales/order/view/` (tasks 470): An order detail page exposes action buttons such as Cancel and shows order information, item and total tables, and tabs for invoices, credit memos, shipments, and comment history.
- `fact-007@v1` on `/reports/report_sales/sales/` (tasks 704): The Sales Orders report is available under Reports > Sales > Orders.
- `fact-008@v1` on `/reports/report_sales/sales/` (tasks 704): The Orders Report filter includes Order Created or Order Updated date selection, Day/Month/Year periods, date range fields, order status, and empty-row and actual-value options.
- `fact-009@v1` on `/reports/report_sales/sales(/filter/.*)?` (tasks 704): Use Show Report to apply the Orders Report filters; the results table includes interval, order and sales totals, invoiced/refunded amounts, tax, shipping, discount, and canceled values.
- `fact-011@v1` on `/reports/report_sales/sales/` (tasks 107): The Orders Report is at the Sales reports route and provides Date Used, Period, date range, Order Status, Empty Rows, and Show Actual Values filters with a Show Report button.
- `fact-012@v1` on `/reports/report_sales/sales(/filter/.*)?` (tasks 107): In the Orders Report, choosing Period=Month and submitting a date range displays one row per month; the Orders column gives the order count.
- `fact-014@v1` on `/reports/report_sales/sales/` (tasks 709): The Orders report is at Reports > Sales > Orders and provides date-used, period, date-range, order-status, empty-row, and actual-value filters.
- `fact-015@v1` on `/reports/report_sales/sales(/filter/.*)?` (tasks 709): The Orders report defaults to Order Created, Day, Any status, and hides empty rows and actual values; use Show Report to apply filters.
- `fact-016@v1` on `/reports/report_sales/sales(/filter/.*)?` (tasks 709): The Orders report table summarizes orders and sales metrics by the selected interval and includes a Total row; it also offers CSV or Excel XML export.
- `fact-017@v1` on `/cms/page/` (tasks 486): CMS pages are managed under Content > Pages, where a table lists page titles and each row's Select menu exposes Edit.
- `fact-022@v1` on `/sales/order/view/order_id/[^/]+/` (tasks 492): An order detail page shows order and customer information, and its Information view includes a Status selector, Comment field, Notify Customer by Email checkbox, and Submit Comment button.
- `fact-023@v1` on `/sales/order/view/order_id/[^/]+/` (tasks 492): Submitting an order comment adds it to the order history, and checking Notify Customer by Email records that the customer was notified.
- `fact-026@v1` on `/sales/order/view/order_id/[^/]+/` (tasks 496): An order detail page provides a Ship action that opens the new shipment form.
- `fact-027@v1` on `/admin/order_shipment/new/order_id/[^/]+/` (tasks 496): On the new shipment form, Add Tracking Number adds a carrier, title, and tracking-number row; choosing a known carrier auto-fills its title.
- `fact-029@v1` on `/review/product/index/` (tasks 11): The All Reviews table has a Review text filter; applying it with Search returns matching review records and displays the total records found.
- `fact-030@v1` on `/review/product/index/` (tasks 11): Review rows show status and review text, and the grid can include both approved and pending reviews in search results.
- `fact-035@v1` on `^/sales/order/view/order_id/[^/]+/$` (tasks 198): An order's View page shows its status and the customer's email in the Account Information section.
- `fact-038@v1` on `^/sales/order/view/order_id/[^/]+/$` (tasks 128): An order detail page's Information tab includes an Items Ordered table with a Qty column for each product, which can be used to total items in the order.
- `fact-002@v2` on `/review/product/index/` (tasks 11, 344): The Marketing menu's User Content section contains an All Reviews page.
- `fact-004@v2` on `/admin/dashboard/` (tasks 128, 198, 470, 492, 496): The Sales navigation menu contains an Orders link that opens the orders grid.
- `fact-005@v2` on `/sales/order/` (tasks 128, 198, 470, 492, 496): The Orders grid supports keyword search, configurable columns, filters, and pagination; it lists information such as customer, purchase date, and status, can be sorted by Purchase Date, and each row has a View link to order details.
- `fact-010@v2` on `/admin/dashboard/` (tasks 107, 709): The Reports navigation menu groups Sales reports, including Orders, Tax, Invoiced, Shipping, Refunds, and Coupons; the Orders link opens the Orders Report.
- `fact-018@v2` on `/cms/page/edit/page_id/[^/]+` (tasks 486): Editing a CMS page opens its form at a page-specific /cms/page/edit/page_id/.../ address, where the Page Title can be changed and saved with Save. Saving displays a success confirmation and updates the form heading and Page Title field to the saved title.
- `fact-031@v2` on `^/customer/index/` (tasks 208): The Customers menu contains an All Customers page at /customer/index/. The customer grid has a Search by keyword field and Filters control, and displays customer name, email, and phone columns.

## Lessons

12 active, 6 retired versions.

- `lesson-003@v1` on `/cms/page/` (tasks 486): On the CMS Pages listing, after opening a row’s action menu, use its Edit link and, if navigation times out, wait and check whether the edit form loaded before retrying or stopping.
- `lesson-004@v1` on `^/admin/dashboard/$|^/catalog/product/$` (tasks 213): On the Magento admin dashboard or product catalog, use Marketing → User Content → Reviews (or Pending Reviews) to find and filter reviews; do not open the product editor when the goal is to read review data.
- `lesson-005@v1` on `/review/product/pending/` (tasks 772): On /review/product/pending/, filter the grid by product and apply the search before selecting rows; identify negative reviews from their titles and review text, select every matching negative review, then choose Delete in the mass-action control and confirm the deletion.
- `lesson-008@v1` on `/sales/order/` (tasks 128): On the Sales > Orders grid, treat “complete orders” as orders whose Status is Complete, not merely the newest orders regardless of status; filter or scan by status and date before opening the two newest qualifying orders.
- `lesson-009@v1` on `/review/product/` (tasks 772): On pending-review grids, inspect each matching review’s content and rating/status to distinguish negative from positive reviews, and select only the negative ones before using Delete; do not delete every review for a product indiscriminately.
- `lesson-010@v1` on `/review/product/` (tasks 772): On review grids, after entering filter values, click Search and verify the resulting rows before taking a mass action; typing into a filter alone does not apply it.
- `lesson-011@v1` on `/sales/order/view/` (tasks 470): On an order detail page, after clicking the order-level Cancel action, treat the confirmation dialog as a separate step and click its OK button to confirm; the dialog's Cancel button only dismisses it and leaves the order unchanged.
- `lesson-014@v1` on `/sales/order/` (tasks 107): On the orders grid, count every row in the fully filtered result set by purchase-date month; do not estimate from a truncated page excerpt, and verify the monthly counts sum to the grid's total record count before reporting.
- `lesson-015@v1` on `/review/product/pending/` (tasks 772): On pending-review grids, verify both the product and the review’s sentiment before using mass delete; select only reviews that meet the requested sentiment, not every result matching the product name.
- `lesson-016@v1` on `/admin/order_shipment/new/.*` (tasks 496): On /admin/order_shipment/new/, after activating Add Tracking Number, inspect the page again for dynamically inserted carrier, title, and number controls; if the row click appears ineffective, target the actual button and wait or refresh the page state rather than repeatedly clicking the row.
- `lesson-001@v2` on `/review/product/edit/` (tasks 213): On review edit pages, determine each review’s rating from the Detailed Rating controls and their selected state or accessible value; do not infer it from the generic five-star label, review text, or a row of stars that does not expose its selection.
- `lesson-002@v2` on `/review/product/` (tasks 213): On filtered review-list pages, apply the filters with Search and inspect every matching record. Take titles from the table’s Title column, not the Review body snippet; where ratings are not shown in the list, open each review and collect its rating, using review navigation controls where available.
