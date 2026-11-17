def run(name, message):
    goto("/sales/order/")
    check(url="^/sales/order/$")
    check(role="table", name="")
    order_id = ""
    for page in range(2):
        rows = read(role="table", name="")
        headers = rows[0]
        id_index = -1
        bill_index = -1
        ship_index = -1
        status_index = -1
        for i, header in enumerate(headers):
            if header == "ID":
                id_index = i
            if header == "Bill-to Name":
                bill_index = i
            if header == "Ship-to Name":
                ship_index = i
            if header == "Status":
                status_index = i
        for row in rows[1:]:
            if row[status_index] == "Pending" and (row[bill_index] == name or row[ship_index] == name):
                order_id = row[id_index]
                break
        if order_id != "":
            break
        if page == 0:
            click(role="button", name="")
            check(role="table", name="")
    check(role="link", name="View", row=order_id)
    click(role="link", name="View", row=order_id)
    check(url="^/sales/order/view/order_id/")
    check(text=name)
    check(text="Pending")
    type(role="textbox", name="Comment", text=message)
    check(role="textbox", name="Comment")
    click(role="checkbox", name="Notify Customer by Email")
    check(role="checkbox", name="Notify Customer by Email")
    click(role="button", name="Submit Comment")
    check(text="Customer Notified")
    check(text=message)