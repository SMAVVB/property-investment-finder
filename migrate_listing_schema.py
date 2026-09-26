#!/usr/bin/env python3
"""
Migrate listing table from old schema (location_city/location_state/location_address)
to new schema (plz/city/kreis_ags/bundesland/address).

Old columns: location_city, location_state, location_address
New columns: plz, city, kreis_ags, bundesland, address

Strategy:
- city ← extract city name from location_city (clean up full listing titles)
- bundesland ← derive from city name (Sachsen for all known cities)
- kreis_ags ← match city name against location_data.csv
- plz ← NULL (not available in scraped data)
- address ← NULL (not available in scraped data)
"""

import csv
import html
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DB_PATH = str(PROJECT_ROOT / "data" / "listings.db")
LOCATION_CSV = str(PROJECT_ROOT / "data" / "location_data.csv")


def load_location_map(csv_path: str) -> dict[str, str]:
    """Load city → kreis_ags mapping from location_data.csv."""
    mapping = {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            city = row["city"].strip()
            kreis_ags = row["kreis_ags"].strip()
            mapping[city] = kreis_ags
    return mapping


def extract_city_name(raw_location_city: str) -> str:
    """Extract clean city name from location_city field.
    
    Handles two formats:
    1. Clean: "Leipzig" → "Leipzig"
    2. Full title: "Leipzig &#8211; Attraktive Eigentumswohnung..." → "Leipzig"
    3. HTML entities: "Eilenburg &#8211; Nachhaltig investieren..." → "Eilenburg"
    """
    # Clean HTML entities
    cleaned = html.unescape(raw_location_city)
    
    # Split on en-dash (— or --) to get the city prefix
    # Pattern: "City -- ..." or "City &#8211; ..."
    parts = re.split(r'\s*[\u2014\u2013]\s*|\s*--\s*', cleaned)
    city = parts[0].strip()
    
    # Clean up trailing punctuation/parentheses from city name
    city = re.sub(r'[,;:]+$', '', city).strip()
    
    return city if city else raw_location_city


def derive_bundesland(city: str) -> str:
    """Derive bundesland from city name.
    
    All known cities in the dataset are in Sachsen.
    Returns None for unknown cities.
    """
    # Known Sachsen cities
    sachsen_cities = {
        'leipzig', 'eilenburg', 'frohburg', 'grimma', 'taucha', 'machern',
        'halle', 'magdeburg', 'dresden', 'leipzig', 'chemnitz',
        'südliches anhalt', 'suedliches anhalt'
    }
    
    city_lower = city.lower().strip()
    
    # Check if city is in known Sachsen list
    if city_lower in sachsen_cities:
        return 'Sachsen'
    
    # Check if city name contains known Sachsen city
    for known in sachsen_cities:
        if known in city_lower or city_lower in known:
            return 'Sachsen'
    
    return None


def match_kreis_ags(city: str, location_map: dict[str, str]) -> str | None:
    """Match city name to kreis_ags from location_data.csv.
    
    Returns None if no match found (documented in output).
    """
    city_clean = city.strip()
    
    # Direct match
    if city_clean in location_map:
        return location_map[city_clean]
    
    # Case-insensitive match
    city_lower = city_clean.lower()
    for csv_city, kreis_ags in location_map.items():
        if csv_city.lower() == city_lower:
            return kreis_ags
    
    # Partial match: check if city name is contained in CSV city name
    for csv_city, kreis_ags in location_map.items():
        csv_name = csv_city.split('(')[0].strip()  # Remove parentheticals
        if city_clean.lower() == csv_name.lower():
            return kreis_ags
    
    return None


def migrate():
    """Perform the schema migration."""
    print("=" * 60)
    print("SCHEMA MIGRATION: listing table")
    print("=" * 60)
    
    # Load location mapping
    location_map = load_location_map(LOCATION_CSV)
    print(f"\nLoaded {len(location_map)} city → kreis_ags mappings from CSV")
    
    # Connect to DB
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Step 0: Record raw_data lengths before migration
    cur.execute("SELECT id, LENGTH(raw_data) FROM listing")
    raw_data_before = dict(cur.fetchall())
    print(f"\nPre-migration: {len(raw_data_before)} listings with raw_data")
    total_raw_before = sum(raw_data_before.values())
    print(f"Total raw_data bytes: {total_raw_before}")
    
    # Step 1: Add new columns (SQLite allows ADD COLUMN on existing table)
    print("\n--- Step 1: Adding new columns ---")
    for col in ['plz', 'city', 'kreis_ags', 'bundesland', 'address']:
        try:
            cur.execute(f"ALTER TABLE listing ADD COLUMN {col} TEXT")
            print(f"  Added column: {col}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"  Column {col} already exists, skipping")
            else:
                raise
    
    # Step 2: Migrate data
    print("\n--- Step 2: Migrating data ---")
    
    unmatched_cities = {}
    migrated = 0
    
    cur.execute("SELECT id, location_city, location_state FROM listing")
    rows = cur.fetchall()
    
    for row_id, location_city, location_state in rows:
        # Extract city name
        city = extract_city_name(location_city)
        
        # Derive bundesland
        bundesland = derive_bundesland(city)
        if bundesland is None and location_state:
            bundesland = location_state  # Fallback to location_state
        
        # Match kreis_ags
        kreis_ags = match_kreis_ags(city, location_map)
        
        # Track unmatched cities
        if kreis_ags is None:
            if city not in unmatched_cities:
                unmatched_cities[city] = []
            unmatched_cities[city].append(row_id)
        
        # Update the row
        cur.execute("""
            UPDATE listing SET city = ?, bundesland = ?, kreis_ags = ? WHERE id = ?
        """, (city, bundesland, kreis_ags, row_id))
        migrated += 1
    
    conn.commit()
    print(f"  Migrated {migrated} rows")
    print(f"  Unmatched cities (kreis_ags = NULL): {len(unmatched_cities)}")
    for city, ids in unmatched_cities.items():
        print(f"    - \"{city}\": {len(ids)} listings (IDs: {ids})")
    
    # Step 3: Drop old columns
    print("\n--- Step 3: Dropping old columns ---")
    for col in ['location_city', 'location_state', 'location_address']:
        try:
            cur.execute(f"ALTER TABLE listing DROP COLUMN {col}")
            print(f"  Dropped column: {col}")
        except sqlite3.OperationalError as e:
            if "no such column" in str(e).lower():
                print(f"  Column {col} already dropped, skipping")
            else:
                raise
    
    conn.commit()
    
    # Step 4: Verify
    print("\n--- Step 4: Verification ---")
    
    # Check new columns exist
    cur.execute("PRAGMA table_info(listing)")
    columns = [col[1] for col in cur.fetchall()]
    print(f"  Columns: {columns}")
    
    # Check NULL counts
    for col in ['city', 'kreis_ags', 'bundesland']:
        cur.execute(f"SELECT COUNT(*) FROM listing WHERE {col} IS NULL")
        null_count = cur.fetchone()[0]
        print(f"  NULL {col}: {null_count}/{len(rows)}")
    
    # Check non-NULL counts
    for col in ['city', 'kreis_ags', 'bundesland']:
        cur.execute(f"SELECT COUNT(*) FROM listing WHERE {col} IS NOT NULL")
        non_null = cur.fetchone()[0]
        print(f"  Non-NULL {col}: {non_null}/{len(rows)}")
    
    # Verify raw_data preserved
    cur.execute("SELECT id, LENGTH(raw_data) FROM listing")
    raw_data_after = dict(cur.fetchall())
    total_raw_after = sum(raw_data_after.values())
    print(f"\n  Post-migration raw_data: {len(raw_data_after)} listings")
    print(f"  Total raw_data bytes: {total_raw_after}")
    
    if raw_data_before == raw_data_after:
        print("  ✓ raw_data integrity: PERFECT MATCH")
    else:
        print("  ✗ raw_data integrity: MISMATCH!")
        for id_key in set(list(raw_data_before.keys()) + list(raw_data_after.keys())):
            if raw_data_before.get(id_key) != raw_data_after.get(id_key):
                print(f"    ID {id_key}: before={raw_data_before.get(id_key)}, after={raw_data_after.get(id_key)}")
    
    # Show sample data
    print("\n--- Sample migrated data ---")
    cur.execute("""
        SELECT id, listing_id, city, kreis_ags, bundesland, price, living_space
        FROM listing LIMIT 5
    """)
    for row in cur.fetchall():
        print(f"  id={row[0]}, listing_id={row[1]}, city={row[2]}, "
              f"kreis_ags={row[3]}, bundesland={row[4]}, "
              f"price={row[5]}, area={row[6]}m²")
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    
    return {
        'migrated': migrated,
        'unmatched_cities': unmatched_cities,
        'raw_data_preserved': raw_data_before == raw_data_after,
    }


if __name__ == "__main__":
    result = migrate()
    sys.exit(0 if result['raw_data_preserved'] else 1)
