def run(PhoneNum):
    click(role="link", name=" CUSTOMERS")
    check(role="link", name="All Customers")
    click(role="link", name="All Customers")
    check(url="^/customer/index/$")
    type(role="textbox", name="Search by keyword", text=PhoneNum)
    click(role="button", name="Search")
    check(role="table", name="")
    rows = read(role="table", name="")
    headers = rows[0]
    name_index = -1
    email_index = -1
    phone_index = -1
    for index, header in enumerate(headers):
        if header.endswith("Name"):
            name_index = index
        if header == "Email":
            email_index = index
        if header == "Phone":
            phone_index = index
    target_phone = PhoneNum.replace("+1 ", "")
    result = []
    for row in rows[1:]:
        if row[phone_index] == target_phone or row[phone_index].endswith(target_phone):
            result.append({"name": row[name_index], "email": row[email_index]})
    return_value(result)