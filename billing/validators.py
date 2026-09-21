"""Server-side financial input validation."""
from decimal import Decimal, InvalidOperation

from .money import q2, ZERO


def validate_line_data(lines_data):
    """Return a list of error strings (empty when valid)."""
    errors = []
    for i, ln in enumerate(lines_data, start=1):
        label = f'Line {i}'
        if not (ln.get('description') or '').strip():
            errors.append(f'{label}: description is required.')
        try:
            qty = Decimal(str(ln.get('quantity') or '0'))
        except (InvalidOperation, ValueError):
            errors.append(f'{label}: quantity is not a valid number.')
            continue
        if qty <= 0:
            errors.append(f'{label}: quantity must be greater than zero.')
        try:
            price = Decimal(str(ln.get('unit_price') or '0'))
        except (InvalidOperation, ValueError):
            errors.append(f'{label}: unit price is not a valid number.')
            continue
        if price < 0:
            errors.append(f'{label}: unit price cannot be negative.')
        try:
            disc = Decimal(str(ln.get('discount_percent') or '0'))
        except (InvalidOperation, ValueError):
            disc = ZERO
        if disc < 0 or disc > 100:
            errors.append(f'{label}: discount must be between 0 and 100 percent.')
        if ln.get('pricing_mode') not in ('exclusive', 'inclusive', None, ''):
            errors.append(f'{label}: invalid pricing mode.')
    return errors
