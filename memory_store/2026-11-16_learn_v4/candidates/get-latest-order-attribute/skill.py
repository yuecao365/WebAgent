def run(attribute, status):
    goto("/sales/order/")
    check(role="heading", name="Orders")
    rows = read(role="table", name="")
    headers = rows[0]
    status_column = -1
    id_column = -1
    for i, header in enumerate(headers):
        if header == "Status":
            status_column = i
        if header == "ID":
            id_column = i
    wanted = status.lower().split()[-1]
    if wanted == "cancelled":
        wanted = "canceled"
    order_id = ""
    for i, row in enumerate(rows):
        if i == 0:
            continue
        if row[status_column].lower() == wanted:
            order_id = row[id_column]
            break
    check(text=order_id)
    click(role="link", name="View", row=order_id)
    check(url="/sales/order/view/order_id/[0-9]+/")
    if attribute.lower() == "customer email":
        panel = read(role="tabpanel", name="Information")
        parts = panel.replace("|", " ").replace(":", " ").split()
        email = ""
        for i, part in enumerate(parts):
            if part.lower() == "email":
                email = parts[i + 1]
                break
        return_value(email)