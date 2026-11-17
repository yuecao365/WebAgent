def run(order_id):
    goto("/sales/order/")
    check(url="^/sales/order/$")
    type(role="textbox", name="Search by keyword", text=str(order_id), submit=True)
    check(url="^/sales/order/")
    rows = read(role="table", name="")
    header = rows[0]
    id_column = -1
    for column, label in enumerate(header):
        if label == "ID":
            id_column = column
    target_id = ""
    for row in rows[1:]:
        if id_column >= 0 and row[id_column].endswith(str(order_id)):
            target_id = row[id_column]
    if target_id == "":
        check(text=str(order_id))
    else:
        check(text=target_id)
    click(role="link", name="View", row=target_id)
    check(url="^/sales/order/view/order_id/" + str(order_id) + "/$")
    check(role="button", name="Cancel")
    click(role="button", name="Cancel")
    check(role="button", name="OK")
    click(role="button", name="OK")
    check(text="You canceled the order.")
