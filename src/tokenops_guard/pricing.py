from decimal import ROUND_CEILING, Decimal

from .config import ModelPrice
from .models import MAX_MONEY, Usage


def cost_microdollars(price: ModelPrice, usage: Usage, *, worst_case: bool = False) -> int:
    # USD / million tokens * token count == microdollars. Round UP once per call.
    if worst_case:
        input_cost = (
            Decimal(usage.input_tokens)
            * price.input_usd_per_million
            * price.input_billing_multiplier
        )
    else:
        cached_rate = (
            price.cached_input_usd_per_million
            if price.cached_input_usd_per_million is not None
            else price.input_usd_per_million
        )
        write_rate = (
            price.cache_write_usd_per_million
            if price.cache_write_usd_per_million is not None
            else price.input_usd_per_million * price.input_billing_multiplier
        )
        ordinary = usage.input_tokens - usage.cached_input_tokens - usage.cache_write_input_tokens
        input_cost = (
            Decimal(ordinary) * price.input_usd_per_million
            + Decimal(usage.cached_input_tokens) * cached_rate
            + Decimal(usage.cache_write_input_tokens) * write_rate
        )
    value = input_cost + Decimal(usage.output_tokens) * price.output_usd_per_million
    result = int(value.to_integral_value(rounding=ROUND_CEILING))
    if not 0 <= result <= MAX_MONEY:
        raise ValueError("Calculated cost is outside the ledger's safe integer range")
    return result
