"""Deterministic recipe costs. Pack sizes use the ingredient's recipe unit."""
from decimal import Decimal, ROUND_HALF_UP, localcontext


def recipe_cost(content, bill=None):
    # Accumulate before rounding, including recipes near the accepted input limits.
    with localcontext() as context:
        context.prec = 60
        return _recipe_cost(content, bill)


def _recipe_cost(content, bill):
    lines, known, missing = [], Decimal('0'), 0
    rates = {(p['name'], p['unit']): p for p in bill['prices']} if bill is not None else None
    for ingredient in content['ingredients']:
        rate = rates.get((ingredient['name'], ingredient['unit']), {}) if rates is not None else ingredient
        price, pack = rate.get('pack_cost'), rate.get('pack_quantity')
        amount = None
        if price is not None and pack is not None:
            amount = Decimal(str(ingredient['quantity'])) / Decimal(str(pack)) * Decimal(str(price))
            known += amount
        else:
            missing += 1
        lines.append({'name': ingredient['name'], 'cost': money(amount) if amount is not None else None})
    servings = Decimal(str(content.get('servings', 1)))
    extras = bill.get('other_costs', []) if bill is not None else []
    other = sum((Decimal(str(c['per_serving'])) for c in extras), Decimal('0'))
    subtotal = known + other * servings
    return {'currency': bill['currency'] if bill is not None else content.get('currency', 'MYR'), 'lines': lines,
            'ingredient_subtotal': money(known), 'other_per_serving': money(other), 'other_total': money(other * servings),
            'missing_prices': missing, 'known_subtotal': money(subtotal),
            'total': money(subtotal) if missing == 0 else None,
            'per_serving': money(subtotal / servings) if missing == 0 else None}


def money(value):
    return str(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
