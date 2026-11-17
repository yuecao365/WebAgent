def run():
    goto("/review/product/index/")
    check(url="^/review/product/index/")
    select(role="combobox", name="per page", option="200")
    check(role="textbox", name="of 2")
    rows = read(role="table", name="")
    headers = rows[0]
    id_index = 0
    for index, header in enumerate(headers):
        if header == "ID":
            id_index = index
    total = 0
    for row in rows:
        if len(row) > id_index and row[id_index].isdigit():
            total = total + 1
    click(role="button", name="")
    check(url="^/review/product/index/")
    rows = read(role="table", name="")
    headers = rows[0]
    id_index = 0
    for index, header in enumerate(headers):
        if header == "ID":
            id_index = index
    for row in rows:
        if len(row) > id_index and row[id_index].isdigit():
            total = total + 1
    return_value(total)
