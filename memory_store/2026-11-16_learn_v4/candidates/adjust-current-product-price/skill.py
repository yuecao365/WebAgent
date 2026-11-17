def run(action, amount):
    price_text = read(role="textbox", name="[global] Price * $").replace("$", "").strip()
    price_parts = price_text.split(".")
    price_whole = int(price_parts[0])
    price_fraction = 0
    if len(price_parts) > 1:
        price_fraction_text = price_parts[1]
        if len(price_fraction_text) == 1:
            price_fraction_text = price_fraction_text + "0"
        if len(price_fraction_text) > 2:
            price_fraction_text = price_fraction_text[:2]
        price_fraction = int(price_fraction_text)
    amount_text = amount.replace("$", "").strip()
    amount_parts = amount_text.split(".")
    amount_whole = int(amount_parts[0])
    amount_fraction = 0
    if len(amount_parts) > 1:
        amount_fraction_text = amount_parts[1]
        if len(amount_fraction_text) == 1:
            amount_fraction_text = amount_fraction_text + "0"
        if len(amount_fraction_text) > 2:
            amount_fraction_text = amount_fraction_text[:2]
        amount_fraction = int(amount_fraction_text)
    total_cents = price_whole * 100 + price_fraction
    amount_cents = amount_whole * 100 + amount_fraction
    if action.lower() == "reduce":
        total_cents = total_cents - amount_cents
    else:
        total_cents = total_cents + amount_cents
    new_price = str(total_cents // 100)
    fraction_text = str(total_cents % 100)
    if len(fraction_text) < 2:
        fraction_text = "0" + fraction_text
    new_price = new_price + "." + fraction_text
    type(role="textbox", name="[global] Price * $", text=new_price)
    check(role="textbox", name="[global] Price * $")
    click(role="button", name="Save")
    check(text="You saved the product.")