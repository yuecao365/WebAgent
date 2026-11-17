def run(report_type, start_date, end_date):
    selected = report_type.lower()
    if selected == "orders":
        report_name = "Orders"
    elif selected == "tax":
        report_name = "Tax"
    elif selected == "invoiced":
        report_name = "Invoiced"
    elif selected == "shipping":
        report_name = "Shipping"
    elif selected == "refunds":
        report_name = "Refunds"
    elif selected == "coupons":
        report_name = "Coupons"
    elif selected == "paypal settlement":
        report_name = "PayPal Settlement"
    elif selected == "braintree settlement":
        report_name = "Braintree Settlement"
    else:
        report_name = report_type
    click(role="link", name=" REPORTS")
    check(text=report_name)
    click(role="link", name=report_name, section="Sales")
    check(role="heading", name=report_name + " Report")
    months = {"january": "01", "february": "02", "march": "03", "april": "04", "may": "05", "june": "06", "july": "07", "august": "08", "september": "09", "october": "10", "november": "11", "december": "12"}
    start_parts = start_date.replace(",", "").split()
    start_month = months.get(start_parts[0].lower())
    start_day = start_parts[1]
    if len(start_day) == 1:
        start_day = "0" + start_day
    formatted_start = start_month + "/" + start_day + "/" + start_parts[2]
    type(role="textbox", name="From *", text=formatted_start)
    check(role="textbox", name="From *")
    end_parts = end_date.replace(",", "").split()
    end_month = months.get(end_parts[0].lower())
    end_day = end_parts[1]
    if len(end_day) == 1:
        end_day = "0" + end_day
    formatted_end = end_month + "/" + end_day + "/" + end_parts[2]
    type(role="textbox", name="To *", text=formatted_end)
    check(role="textbox", name="To *")
    click(role="button", name="Show Report")
    check(role="heading", name=report_name + " Report")
    check(text="records found")
    return_value(None)