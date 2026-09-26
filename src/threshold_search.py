"""Grid search over tunable (non price/size) investment criteria
thresholds.

Given an already deep-scraped set of Listing objects and a base criteria
dict (loaded from criteria.yaml), tries combinations of a small parameter
grid and returns whichever combination maximizes mean Calculator score
across the passing shortlist, subject to a minimum shortlist-size floor.

purchase_price and living_space are fixed per Vincent's explicit
instruction -- callers must not put them in param_grid; this module
refuses to tune them.
"""
from __future__ import annotations

import copy
import itertools
from typing import Any

from calculator import calculate_batch, filter_passed

FIXED_PREFIXES = ("purchase_price", "living_space")


def _set_nested(d: dict, dotted_key: str, value: Any) -> None:
    if dotted_key.startswith(FIXED_PREFIXES):
        raise ValueError(f"{dotted_key} is a fixed criterion and cannot be tuned")
    parts = dotted_key.split(".")
    node = d
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def evaluate_criteria(listings: list, criteria: dict) -> tuple[float, int]:
    """Return (mean_score_of_passing, shortlist_size) for one criteria dict."""
    results = calculate_batch(listings, criteria)
    passed = filter_passed(results)
    if not passed:
        return 0.0, 0
    mean_score = sum(r.score for r in passed) / len(passed)
    return mean_score, len(passed)


def search_best_criteria(
    listings: list,
    base_criteria: dict,
    param_grid: dict,
    min_shortlist_size: int = 20,
) -> tuple[dict, float, int]:
    """Grid search over param_grid (dotted-path -> list of candidate
    values). Returns (best_criteria, best_mean_score, best_shortlist_size).

    If no combination clears min_shortlist_size, returns
    (base_criteria, 0.0, 0) -- i.e. falls back to whatever the caller
    already had rather than silently picking a degenerate tiny shortlist.
    """
    keys = list(param_grid.keys())
    best_criteria = None
    best_score = -1.0
    best_size = 0
    for values in itertools.product(*(param_grid[k] for k in keys)):
        candidate = copy.deepcopy(base_criteria)
        for k, v in zip(keys, values):
            _set_nested(candidate, k, v)
        mean_score, size = evaluate_criteria(listings, candidate)
        if size < min_shortlist_size:
            continue
        if mean_score > best_score:
            best_score = mean_score
            best_size = size
            best_criteria = candidate
    if best_criteria is None:
        return base_criteria, 0.0, 0
    return best_criteria, best_score, best_size
