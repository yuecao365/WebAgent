def run(order_id):
    goto("/sales/order/")
    check(url="/sales/order/")
    type(role="textbox", name="Search by keyword", text=str(order_id), submit=True)
    check(url="/sales/order/")
    table = read(role="table", name="")
    id_index = -1
    for i in range(len(table[0])):
        if table[0][i] == "ID":
            id_index = i
            break
    order_row = ""
    for row in table[1:]:
        if row[id_index].endswith(str(order_id)):
            order_row = row[id_index]
            break
    check(text=order_row)
    click(role="link", name="View", row=order_row)
    check(url="/sales/order/view/order_id/" + str(order_id) + "/")
    click(role="button", name="Cancel")
    check(role="button", name="OK")
    click(role="button", name="OK")
    check(text="You canceled the order.")