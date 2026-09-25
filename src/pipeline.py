#!/usr/bin/env python3
"""
Property Investment Finder — Pipeline Runner (Phase 2)

Orchestrates the full Navigator + Extractor + DB storage pipeline.

Usage:
  python -m src.pipeline --city "Leipzig" --min-price 80000 --max-price 150000 \\
      --min-area 30 --max-area 55 --max-pages 3 --db property.db
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.navigator import KleinanzeigenNavigator, SearchConfig, ListingURL, asdict
from src.extractor import KleinanzeigenExtractor, ExtractedListing

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def init_db(db_path: str, schema_path: str = None) -> sqlite3.Connection:
    """Initialize SQLite database with schema."""
    if schema_path is None:
        schema_path = str(PROJECT_ROOT / "schema.sql")
    conn = sqlite3.connect(db_path)
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    return conn


def store_listing(conn: sqlite3.Connection, listing: ExtractedListing) -> None:
    """Store an extracted listing in the database."""
    conn.execute("""
        INSERT OR REPLACE INTO listing (
            listing_id, title, price, living_space, rent_monthly, rooms,
            floor, built_year, condition, location_city, location_state,
            location_address, latitude, longitude,
            is_erbpacht, is_vacation, is_auction, is_care_apartment, is_social_binding,
            property_type, url, scraped_at, raw_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        listing.listing_id,
        listing.title,
        listing.price,
        listing.living_space,
        listing.rent_monthly,
        listing.rooms,
        listing.floor,
        listing.built_year,
        listing.condition,
        listing.location_city,
        listing.location_state,
        listing.location_address,
        listing.latitude,
        listing.longitude,
        1 if listing.is_erbpacht else 0,
        1 if listing.is_vacation else 0,
        1 if listing.is_auction else 0,
        1 if listing.is_care_apartment else 0,
        1 if listing.is_social_binding else 0,
        listing.property_type,
        listing.url,
        listing.scraped_at,
        listing.raw_data[:2000] if listing.raw_data else None,
    ))
    conn.commit()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(args) -> dict:
    """
    Run the full Navigator -> Extractor -> DB pipeline.

    Returns summary dict.
    """
    # --- Step 1: Navigate ---
    logger.info("=" * 60)
    logger.info("STEP 1: Navigator — searching for listings")
    logger.info("=" * 60)

    config = SearchConfig(
        city=args.city,
        min_price=args.min_price,
        max_price=args.max_price,
        min_area=args.min_area,
        max_area=args.max_area,
    )

    nav = KleinanzeigenNavigator()
    found_listings = nav.search(config, max_pages=args.max_pages)

    logger.info("Navigator found %d unique listings", len(found_listings))

    if not found_listings:
        logger.warning("No listings found! Check search parameters or portal availability.")
        return {"found": 0, "extracted": 0, "stored": 0, "errors": ["No listings found"]}

    # Save raw navigator output
    raw_output = [asdict(l) for l in found_listings]
    raw_path = str(PROJECT_ROOT / "output" / "navigator_output.json")
    os.makedirs(str(PROJECT_ROOT / "output"), exist_ok=True)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_output, f, ensure_ascii=False, indent=2)
    logger.info("Navigator output saved to %s", raw_path)

    # --- Step 2: Extract ---
    logger.info("=" * 60)
    logger.info("STEP 2: Extractor — extracting listing details")
    logger.info("=" * 60)

    urls = []
    source_info = None
    for listing in found_listings:
        urls.append(listing.url)
        if listing.search_config and not source_info:
            source_info = listing.search_config

    if not source_info:
        source_info = {"city": args.city}

    extractor = KleinanzeigenExtractor()
    extracted_listings = extractor.extract_batch(urls, source_info=source_info)

    success_count = sum(1 for l in extracted_listings if l.extraction_success)
    logger.info("Extractor succeeded on %d/%d listings", success_count, len(extracted_listings))

    # Save raw extractor output
    extracted_output = [asdict(l) for l in extracted_listings]
    extracted_path = str(PROJECT_ROOT / "output" / "extracted_output.json")
    with open(extracted_path, "w", encoding="utf-8") as f:
        json.dump(extracted_output, f, ensure_ascii=False, indent=2)
    logger.info("Extractor output saved to %s", extracted_path)

    # --- Step 3: Store in DB ---
    logger.info("=" * 60)
    logger.info("STEP 3: Database — storing listings")
    logger.info("=" * 60)

    db_path = args.db if args.db else str(PROJECT_ROOT / "data" / "listings.db")
    os.makedirs(str(PROJECT_ROOT / "data"), exist_ok=True)
    conn = init_db(db_path)

    stored = 0
    for listing in extracted_listings:
        if listing.extraction_success:
            store_listing(conn, listing)
            stored += 1

    cursor = conn.execute("SELECT COUNT(*) FROM listing")
    total_rows = cursor.fetchone()[0]
    conn.close()

    logger.info("Stored %d listings in database (%d total rows)", stored, total_rows)

    return {
        "found": len(found_listings),
        "extracted": len(extracted_listings),
        "success": success_count,
        "stored": stored,
        "total_db_rows": total_rows,
        "db_path": db_path,
        "errors": [
            l.extraction_notes
            for l in extracted_listings
            if not l.extraction_success
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Property Investment Finder — Pipeline")
    parser.add_argument("--city", default="Leipzig")
    parser.add_argument("--min-price", type=int, default=80000)
    parser.add_argument("--max-price", type=int, default=150000)
    parser.add_argument("--min-area", type=float, default=30.0)
    parser.add_argument("--max-area", type=float, default=55.0)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--db", help="Path to SQLite database")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    logger.info("Pipeline starting for city=%s, price=%d-%d, area=%.0f-%.0f",
                args.city, args.min_price, args.max_price,
                args.min_area, args.max_area)

    result = run_pipeline(args)

    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)
    print(f"  Listings found (navigator):  {result['found']}")
    print(f"  Listings extracted:          {result['extracted']}")
    print(f"  Extraction success rate:     {result['success']}/{result['extracted']} "
          f"({result['success']/max(result['extracted'],1)*100:.0f}%)")
    print(f"  Listings stored in DB:       {result['stored']}")
    print(f"  Total DB rows:               {result['total_db_rows']}")
    print(f"  Database path:               {result['db_path']}")

    if result.get('errors'):
        print(f"\n  Errors ({len(result['errors'])}):")
        for err in result['errors'][:10]:
            print(f"    - {err}")

    return result


if __name__ == "__main__":
    main()
