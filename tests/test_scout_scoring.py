import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from scout_scoring import median_or_none, estimate_kaufpreisfaktor


def test_median_or_none_filters_invalid_values():
    assert median_or_none([2000, 2200, 0, None, 2100]) == 2100


def test_median_or_none_empty_or_all_invalid():
    assert median_or_none([]) is None
    assert median_or_none([0, None]) is None


def test_estimate_kaufpreisfaktor_known_values():
    # median price/sqm = 2100, median rent/sqm = 8.5
    # kaufpreisfaktor = 2100 / (8.5 * 12)
    sale = [2000.0, 2200.0, 2100.0]
    rent = [8.0, 9.0, 8.5]
    result = estimate_kaufpreisfaktor(sale, rent)
    assert result == pytest.approx(2100 / (8.5 * 12), rel=1e-6)


def test_estimate_kaufpreisfaktor_missing_data_returns_none():
    assert estimate_kaufpreisfaktor([], [8.0]) is None
    assert estimate_kaufpreisfaktor([2000.0], []) is None
