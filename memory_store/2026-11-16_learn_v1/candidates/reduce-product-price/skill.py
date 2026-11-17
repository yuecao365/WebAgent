def run(reduction_amount):
    current_price = read(role="textbox", name="[global] Price * $")
    current_cents = int(float(current_price.replace("$", "").replace(",", "").strip()) * 100)
    new_cents = current_cents - reduction_amount * 100
    dollars = str(new_cents // 100)
    cents = str(new_cents % 100)
    if len(cents) == 1:
        cents = "0" + cents
    new_price = dollars + "." + cents
    type(role="textbox", name="[global] Price * $", text=new_price)
    check(role="textbox", name="[global] Price * $")
    click(role="button", name="Save")
    check(text="You saved the product.")
