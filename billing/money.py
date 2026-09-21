"""
Monetary math policy for the Sysnet platform (documented, applied consistently):

- All money is stored as Decimal(max_digits=14, decimal_places=2) in KES.
- All quantization uses ROUND_HALF_UP to 2 decimal places (Kenyan practice;
  matches the VAT example in the spec: 10,000 @16% -> 1,600.00).
- VAT is computed per line: line_net * rate / 100, quantized per line, then
  summed. Inclusive prices extract VAT as gross - gross / (1 + rate/100).
- Discounts are computed before VAT (VAT applies to the discounted line net).
- Totals are always computed server-side from stored line values.
"""
from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal('0.01')
ZERO = Decimal('0.00')


def q2(value) -> Decimal:
    """Quantize to 2 dp, half-up. None-safe."""
    if value is None:
        return ZERO
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def multiply(amount, quantity) -> Decimal:
    return q2(Decimal(amount) * Decimal(quantity))


def vat_of(net: Decimal, rate: Decimal) -> Decimal:
    """VAT amount on a net amount for the given percent rate."""
    return q2(Decimal(net) * Decimal(rate) / Decimal('100'))


def vat_component_of_gross(gross: Decimal, rate: Decimal) -> Decimal:
    """Extract the VAT portion from a VAT-inclusive gross amount."""
    gross = Decimal(gross)
    if rate <= 0:
        return ZERO
    return q2(gross - gross / (Decimal('1') + Decimal(rate) / Decimal('100')))
