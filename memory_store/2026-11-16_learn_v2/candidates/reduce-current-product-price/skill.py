def run(discount):
    current_price = read(role="textbox", name="[global] Price * $")
    new_price = str(float(current_price.replace("$", "").replace(",", "").strip()) - discount)
    type(role="textbox", name="[global] Price * $", text=new_price)
    check(text=new_price)
    click(role="button", name="Save")
    check(text="You saved the product.")