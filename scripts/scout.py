#!/usr/bin/env python3
"""Scout stage of the autonomous tuning loop -- cheap, search-JSON-only
city ranking. No detail-page (expose) fetches: only the same
resultListModel JSON the search-results scraper already parses, hit once
for sale listings (wohnung-kaufen, fixed price/size band) and once for
rental listings (wohnung-mieten, size band only) per candidate city, to
get a real median rent/sqm instead of a hardcoded guess.

Run: /home/vincent/multica-lab/venv-scrape/bin/python scripts/scout.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, "src")

from scrapling.fetchers import StealthyFetcher

from immoscout_scraper import extract_result_json, parse_entries
from regions import load_candidate_batch, mark_scouted
from scout_scoring import estimate_kaufpreisfaktor, median_or_none

DB_PATH = "/tmp/property-investment-finder/data/listings.db"
PRICE_MIN, PRICE_MAX = 80000, 150000
SPACE_MIN, SPACE_MAX = 30, 55


def _fetch_hits(bl_slug: str, city_slug: str, city_name: str, bl_name: str, kind: str):
    """kind: 'kaufen' or 'mieten'. Returns (entries, num_hits); ([], 0) on failure."""
    if kind == "kaufen":
        url = (
            f"https://www.immobilienscout24.de/Suche/de/{bl_slug}/{city_slug}/wohnung-kaufen"
            f"?price={PRICE_MIN}-{PRICE_MAX}&livingspace={SPACE_MIN}-{SPACE_MAX}"
        )
    else:
        url = (
            f"https://www.immobilienscout24.de/Suche/de/{bl_slug}/{city_slug}/wohnung-mieten"
            f"?livingspace={SPACE_MIN}-{SPACE_MAX}"
        )
    try:
        r = StealthyFetcher.fetch(
            url, headless=True, disable_resources=True, network_idle=True, timeout=30000
        )
    except Exception as e:
        print(f"  [{city_name}/{kind}] FETCH ERROR: {e}", file=sys.stderr)
        return [], 0
    if r.status != 200:
        print(f"  [{city_name}/{kind}] status={r.status}")
        return [], 0
    data = extract_result_json(r.html_content)
    if data is None:
        print(f"  [{city_name}/{kind}] no resultListModel found")
        return [], 0
    return parse_entries(data, city_name, bl_name)


def scout_city(bl_slug: str, city_slug: str, city_name: str, bl_name: str) -> dict:
    sale_entries, n_sale = _fetch_hits(bl_slug, city_slug, city_name, bl_name, "kaufen")
    rent_entries, n_rent = _fetch_hits(bl_slug, city_slug, city_name, bl_name, "mieten")

    sale_price_per_sqm = [
        e.price / e.living_space for e in sale_entries if e.price and e.living_space
    ]
    rent_price_per_sqm = [
        e.price / e.living_space for e in rent_entries if e.price and e.living_space
    ]

    if n_sale == 0 and n_rent == 0:
        status = "no_slug"
    elif not sale_price_per_sqm:
        status = "failed"
    else:
        status = "ok"

    return {
        "city": city_name,
        "bundesland": bl_name,
        "n_sale_hits": n_sale,
        "median_price_per_sqm": median_or_none(sale_price_per_sqm),
        "median_rent_per_sqm": median_or_none(rent_price_per_sqm),
        "est_kaufpreisfaktor": estimate_kaufpreisfaktor(sale_price_per_sqm, rent_price_per_sqm),
        "status": status,
    }


def store_scout_result(
    conn: sqlite3.Connection, bl_slug: str, city_slug: str, result: dict
) -> None:
    conn.execute(
        """
        INSERT INTO region_scouting
            (city, kreis_ags, scouted_at, n_sale_hits, median_price_per_sqm,
             median_rent_per_sqm, est_kaufpreisfaktor, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result["city"],
            f"{bl_slug}/{city_slug}",
            datetime.now(timezone.utc).isoformat(),
            result["n_sale_hits"],
            result["median_price_per_sqm"],
            result["median_rent_per_sqm"],
            result["est_kaufpreisfaktor"],
            result["status"],
        ),
    )
    conn.commit()


def main(batch_size: int = 20) -> None:
    candidates = load_candidate_batch(batch_size=batch_size)
    if not candidates:
        print("No un-scouted candidates left in regions.yaml.")
        return
    conn = sqlite3.connect(DB_PATH)
    for bl_slug, city_slug, city_name, bl_name in candidates:
        print(f"Scouting {city_name} ({bl_name})...")
        result = scout_city(bl_slug, city_slug, city_name, bl_name)
        store_scout_result(conn, bl_slug, city_slug, result)
        print(f"  -> {result}")
    conn.close()
    mark_scouted(candidates)


if __name__ == "__main__":
    main()
