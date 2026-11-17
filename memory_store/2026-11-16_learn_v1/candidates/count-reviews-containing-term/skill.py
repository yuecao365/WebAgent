def run(term):
    click(role="link", name=" MARKETING")
    check(role="link", name="All Reviews")
    click(role="link", name="All Reviews")
    check(role="heading", name="Reviews")
    type(role="textbox", name="detail", text=term)
    check(role="textbox", name="detail")
    click(role="button", name="Search")
    check(url="^/review/product/index/filter/")
    rows = read(role="table", name="")
    check(role="table", name="")
    header = rows[0]
    id_index = -1
    for index, cell in enumerate(header):
        if cell == "ID":
            id_index = index
    total = 0
    for row in rows:
        if id_index >= 0 and len(row) > id_index and row[id_index].isdigit():
            total = total + 1
    return_value(total)
