#!/usr/bin/env python3
"""Import Immowelt listings into the database."""

import json
import sqlite3
import hashlib
import os
import re
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "listings.db")
SCHEMA_PATH = os.path.join(PROJECT_ROOT, "schema.sql")
INPUT_PATH = os.path.join(PROJECT_ROOT, "data", "all_listings.json")


def extract_bundesland(city: str) -> str:
    """Determine Bundesland from city name."""
    if not city:
        return ""
    city_lower = city.lower()
    
    # Berlin
    if city_lower == "berlin":
        return "Berlin"
    
    # Brandenburg towns
    brandenburg_cities = [
        "leipzig", "cottbus", "frankfurt", "potsdam", "dessau",
        "wittenberg", "senftenberg", "brandenburg", "königs",
        "falkensee", "eberswalde", "bernau", "schwedt", "oranienburg",
        "kleinmachnow", "stahnsdorf", "ketzin", "wandlitz", "hennigsdorf",
        "teltow", "zossen", "ludwigsfelde", "rathenow", "halberstadt",
        "magdeburg", "bautzen", "görlitz", "chemnitz", "dresden",
        "meißen", "riesa", "delitzsch", "nauen", "prenzlau",
        "angermünde", "neuruppin", "falkenberg", "bad belzig",
        "jüterbog", "schönefeld", "lichterfeld", "haunstetten"
    ]
    
    for bc in brandenburg_cities:
        if bc in city_lower:
            return "Brandenburg"
    
    # Saxony
    saxony_cities = ["leipzig", "dresden", "chemnitz", "hall", "bielefeld", "magdeburg"]
    for sc in saxony_cities:
        if sc in city_lower:
            return "Sachsen"
    
    return ""


def import_listings():
    """Import listings from JSON into SQLite database."""
    # Read input
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        listings = json.load(f)
    
    print(f"Reading {len(listings)} listings from {INPUT_PATH}")
    
    # Initialize database (don't re-execute schema - it may conflict with existing tables)
    conn = sqlite3.connect(DB_PATH)
    # Check if listing table exists
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='listing'").fetchall()
    if not tables:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
    
    # Track what we're importing
    imported = 0
    skipped = 0
    errors = 0
    
    for listing in listings:
        try:
            # Generate listing_id
            listing_id = listing.get("listing_id", f"iw-{hashlib.md5(listing['url'].encode()).hexdigest()[:12]}")
            
            # Extract bundesland
            bundesland = extract_bundesland(listing.get("city", ""))
            
            # Extract PLZ from address if not present
            plz = listing.get("plz", "")
            address = listing.get("address", "")
            if not plz and address:
                plz_match = re.search(r'\((\d{5})\)', address)
                if plz_match:
                    plz = plz_match.group(1)
            
            # Store raw_data (the card text)
            raw_data = listing.get("title", "")
            
            # Insert or replace
            conn.execute("""
                INSERT OR REPLACE INTO listing (
                    listing_id, title, price, living_space, rent_monthly, rooms,
                    floor, built_year, condition, plz, city, bundesland, address,
                    is_erbpacht, is_vacation, is_auction, is_care_apartment, is_social_binding,
                    property_type, url, scraped_at, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                listing_id,
                listing.get("title", "")[:500],
                listing.get("price", 0),
                listing.get("living_space", 0),
                listing.get("rent_monthly", 0),
                listing.get("rooms", 0),
                listing.get("floor", ""),
                0,  # built_year
                "unknown",  # condition
                plz,
                listing.get("city", ""),
                bundesland,
                address[:200] if address else "",
                0, 0, 0, 0, 0,  # exclusion flags
                "apartment",
                listing.get("url", ""),
                listing.get("scraped_at", datetime.now(timezone.utc).isoformat()),
                raw_data[:2000] if raw_data else None,
            ))
            imported += 1
            
        except Exception as e:
            errors += 1
            print(f"  Error importing {listing.get('listing_id', 'unknown')}: {e}")
    
    conn.commit()
    
    # Count total
    total = conn.execute("SELECT COUNT(*) FROM listing").fetchone()[0]
    conn.close()
    
    print(f"\nImport complete:")
    print(f"  Imported: {imported}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    print(f"  Total in DB: {total}")
    
    # Show source breakdown
    conn = sqlite3.connect(DB_PATH)
    sources = conn.execute("""
        SELECT source, COUNT(*) FROM (
            SELECT CASE 
                WHEN listing_id LIKE 'klz-%' THEN 'kleinanzeigen'
                WHEN listing_id LIKE 'iw-%' THEN 'immowelt'
                WHEN listing_id LIKE 'is24-%' THEN 'immoscout24'
                WHEN listing_id LIKE 'pos-%' THEN 'poschmann'
                ELSE 'unknown'
            END as source
            FROM listing
        ) GROUP BY source
    """).fetchall()
    print(f"\nBy source:")
    for s, c in sources:
        print(f"  {s}: {c}")
    conn.close()


if __name__ == "__main__":
    import_listings()
