import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from calculator import Listing, load_criteria
from threshold_search import evaluate_criteria, search_best_criteria


def _criteria():
    """Load criteria.yaml the same way tests/test_calculator.py does --
    load_criteria() with no path argument resolves relative to src/, but
    criteria.yaml lives at the repo root."""
    criteria_path = os.path.join(os.path.dirname(__file__), "..", "criteria.yaml")
    return load_criteria(criteria_path)


def _make_listings():
    """5 synthetic listings, fixed price/size (already within the 80-150k /
    30-55m2 band so purchase_price/living_space filters never reject any
    of them -- only built_year and yield should differentiate them)."""
    listings = []
    # 3 "new, good yield" listings built 2005, rent high enough for >=4.5% yield
    for i in range(3):
        listings.append(Listing(
            listing_id=f"new-{i}", price=100000, living_space=40,
            rent_monthly=450, built_year=2005, city="Leipzig", bundesland="Sachsen",
        ))
    # 2 "old, poor yield" listings built 1960, low rent (but still >=3.5%
    # gross yield so they only get excluded by the built_year cutoff, not
    # by the yield filter itself)
    for i in range(2):
        listings.append(Listing(
            listing_id=f"old-{i}", price=100000, living_space=40,
            rent_monthly=300, built_year=1960, city="Leipzig", bundesland="Sachsen",
        ))
    return listings


def test_evaluate_criteria_returns_mean_score_and_size():
    listings = _make_listings()
    criteria = _criteria()
    mean_score, size = evaluate_criteria(listings, criteria)
    assert size >= 1
    assert mean_score >= 0.0


def test_search_best_criteria_prefers_built_year_cutoff_that_excludes_bad_listings():
    listings = _make_listings()
    base_criteria = _criteria()
    param_grid = {"built_year.min": [0, 1990]}
    best_criteria, best_score, best_size = search_best_criteria(
        listings, base_criteria, param_grid, min_shortlist_size=2
    )
    # With min_shortlist_size=2, both cutoffs leave enough listings; the
    # 1990 cutoff drops the 2 low-yield 1960-built listings, raising the
    # mean score of what remains.
    assert best_criteria["built_year"]["min"] == 1990
    assert best_size == 3


def test_search_best_criteria_falls_back_when_floor_never_met():
    listings = _make_listings()
    base_criteria = _criteria()
    param_grid = {"built_year.min": [0, 1990]}
    best_criteria, best_score, best_size = search_best_criteria(
        listings, base_criteria, param_grid, min_shortlist_size=999
    )
    assert best_size == 0
    assert best_score == 0.0
    assert best_criteria == base_criteria


def test_fixed_keys_cannot_be_tuned():
    listings = _make_listings()
    base_criteria = _criteria()
    import pytest
    with pytest.raises(ValueError):
        search_best_criteria(
            listings, base_criteria, {"purchase_price.min": [0]}, min_shortlist_size=1
        )
