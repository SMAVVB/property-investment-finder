"""Pure scoring math for the Scout stage of the autonomous tuning loop.

No network I/O here -- this only turns already-fetched search-result
numbers (price/sqm, rent/sqm) into an estimated kaufpreisfaktor, so a
candidate city can be ranked before spending a real detail-page fetch on
any of its listings.
"""
from __future__ import annotations

from statistics import median
from typing import Optional


def median_or_none(values: list[float]) -> Optional[float]:
    """Compute median of values, filtering out None and non-positive values.

    Filters out None and values <= 0 before computing the median. Returns None
    if no valid values remain after filtering.

    Args:
        values: List of numeric values (or None) to median.

    Returns:
        The median of valid values, or None if no valid values exist.
    """
    cleaned = [v for v in values if v is not None and v > 0]
    if not cleaned:
        return None
    return median(cleaned)


def estimate_kaufpreisfaktor(
    sale_prices_per_sqm: list[float], rent_prices_per_sqm: list[float]
) -> Optional[float]:
    """Rough kaufpreisfaktor estimate for a city, from cheap search-result
    data only (no detail-page fetch, no financing math).

    kaufpreisfaktor = Kaufpreis / Jahreskaltmiete. Since both price/sqm and
    rent/sqm are per-sqm, the sqm term cancels:
        kaufpreisfaktor ~= median(price/sqm) / (median(rent/sqm) * 12)

    Both input lists are filtered the same way (None and non-positive values
    excluded) before the median is taken. Returns None if either side has no
    usable data after filtering.

    Args:
        sale_prices_per_sqm: Per-sqm sale prices to estimate from.
        rent_prices_per_sqm: Per-sqm rent prices to estimate from.

    Returns:
        Estimated kaufpreisfaktor, or None if either input lacks valid data.
    """
    med_price = median_or_none(sale_prices_per_sqm)
    med_rent = median_or_none(rent_prices_per_sqm)
    if med_price is None or med_rent is None:
        return None
    return med_price / (med_rent * 12)
