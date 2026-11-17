def run(report, start_date, end_date):
    report_name = report.lower()
    if report_name.count("order") > 0:
        menu_item = "Orders"
    elif report_name.count("tax") > 0:
        menu_item = "Tax"
    elif report_name.count("invoic") > 0:
        menu_item = "Invoiced"
    elif report_name.count("shipp") > 0:
        menu_item = "Shipping"
    elif report_name.count("refund") > 0:
        menu_item = "Refunds"
    elif report_name.count("coupon") > 0:
        menu_item = "Coupons"
    elif report_name.count("paypal") > 0:
        menu_item = "PayPal Settlement"
    elif report_name.count("braintree") > 0:
        menu_item = "Braintree Settlement"
    else:
        menu_item = report
    click(role="link", name=" REPORTS")
    check(role="link", name="Orders")
    check(role="link", name=menu_item)
    click(role="link", name=menu_item)
    check(role="button", name="Show Report")
    type(role="textbox", name="From *", text=start_date)
    type(role="textbox", name="To *", text=end_date)
    click(role="button", name="Show Report")
    check(url="^/reports/.*")