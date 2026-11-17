def run(start_date, end_date):
    click(role="link", name=" REPORTS")
    check(role="link", name="Orders")
    click(role="link", name="Orders")
    check(role="heading", name="Orders Report")
    select(role="combobox", name="Period", option="Month")
    check(role="combobox", name="Period")
    type(role="textbox", name="From *", text=start_date)
    check(role="textbox", name="From *")
    type(role="textbox", name="To *", text=end_date)
    check(role="textbox", name="To *")
    click(role="button", name="Show Report")
    check(url="^/reports/report_sales/sales/filter/")
    rows = read(role="table", name="")
    header = rows[0]
    interval_column = 0
    orders_column = 0
    for i in range(len(header)):
        if header[i] == "Interval":
            interval_column = i
        if header[i] == "Orders":
            orders_column = i
    result = []
    for i in range(1, len(rows)):
        row = rows[i]
        interval = row[interval_column]
        if interval.lower() == "total" or interval.lower().startswith("we couldn"):
            continue
        month_number = int(interval.split("/")[0])
        month_name = ""
        if month_number == 1:
            month_name = "January"
        if month_number == 2:
            month_name = "February"
        if month_number == 3:
            month_name = "March"
        if month_number == 4:
            month_name = "April"
        if month_number == 5:
            month_name = "May"
        if month_number == 6:
            month_name = "June"
        if month_number == 7:
            month_name = "July"
        if month_number == 8:
            month_name = "August"
        if month_number == 9:
            month_name = "September"
        if month_number == 10:
            month_name = "October"
        if month_number == 11:
            month_name = "November"
        if month_number == 12:
            month_name = "December"
        result.append({"month": month_name, "count": int(row[orders_column].replace(",", "").strip())})
    return_value(result)