"""Deterministic recipe costs. Pack sizes use the ingredient's recipe unit."""
from decimal import Decimal, ROUND_HALF_UP


def recipe_cost(content):
    lines, known, missing = [], Decimal('0'), 0
    for ingredient in content['ingredients']:
        price, pack = ingredient.get('pack_cost'), ingredient.get('pack_quantity')
        amount = None
        if price is not None and pack is not None:
            amount = Decimal(str(ingredient['quantity'])) / Decimal(str(pack)) * Decimal(str(price))
            known += amount
        else:
            missing += 1
        lines.append({'name': ingredient['name'], 'cost': money(amount) if amount is not None else None})
    return {'currency': content.get('currency', 'MYR'), 'lines': lines,
            'missing_prices': missing, 'known_subtotal': money(known),
            'total': money(known) if missing == 0 else None,
            'per_serving': money(known / Decimal(str(content['servings']))) if missing == 0 else None}


def money(value):
    return str(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
