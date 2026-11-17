def run(customer_name, message):
    click(role="link", name=" SALES")
    check(role="link", name="Orders")
    click(role="link", name="Orders")
    check(role="heading", name="Orders")
    type(role="textbox", name="Search by keyword", text=customer_name)
    check(role="textbox", name="Search by keyword")
    click(role="button", name="Search")
    check(text=customer_name)
    orders = read(role="table", name="")
    headers = orders[0]
    id_col = -1
    bill_col = -1
    ship_col = -1
    status_col = -1
    for index, header in enumerate(headers):
        if header == "ID":
            id_col = index
        if header == "Bill-to Name":
            bill_col = index
        if header == "Ship-to Name":
            ship_col = index
        if header == "Status":
            status_col = index
    order_id = ""
    for row in orders[1:]:
        if (
            order_id == ""
            and row[status_col] == "Pending"
            and (row[bill_col] == customer_name or row[ship_col] == customer_name)
        ):
            order_id = row[id_col]
    if order_id != "":
        click(role="link", name="View", row=order_id)
        check(role="heading", name="#" + order_id)
        type(role="textbox", name="Comment", text=message)
        check(text=message)
        click(role="checkbox", name="Notify Customer by Email")
        check(role="checkbox", name=" Notify Customer by Email")
        click(role="button", name="Submit Comment")
        check(text=message)
