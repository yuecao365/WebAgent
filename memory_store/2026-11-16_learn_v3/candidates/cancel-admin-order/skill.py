def run(id):
    goto("/sales/order/")
    check(url="/sales/order/")
    type(role="textbox", name="Search by keyword", text=id, submit=True)
    check(text=id)
    rows = read(role="table", name="")
    header = rows[0]
    id_column = -1
    for index in range(len(header)):
        if header[index] == "ID":
            id_column = index
    target = ""
    for row in rows[1:]:
        if row[id_column].endswith(id):
            target = row[id_column]
    click(role="link", name="View", row=target)
    check(role="heading", name="#" + target)
    click(role="button", name="Cancel")
    check(role="button", name="OK")
    click(role="button", name="OK")
    check(text="You canceled the order.")