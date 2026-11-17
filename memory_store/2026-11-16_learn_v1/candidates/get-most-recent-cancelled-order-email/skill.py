def run():
    click(role="link", name=" SALES")
    check(role="link", name="Orders")
    click(role="link", name="Orders")
    check(url="/sales/order/")
    rows = read(role="table", name="")
    headers = rows[0]
    id_index = -1
    status_index = -1
    for index, header in enumerate(headers):
        if header == "ID":
            id_index = index
        if header == "Status":
            status_index = index
    order_id = ""
    for row in rows[1:]:
        if row[status_index] == "Canceled" and order_id == "":
            order_id = row[id_index]
    check(text=order_id)
    click(role="link", name="View", row=order_id)
    check(text=order_id)
    info = read(role="tabpanel", name="Information")
    email = info.split("Email")[1].split("|")[1].split()[0]
    return_value(email)
