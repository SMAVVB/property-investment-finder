#!/usr/bin/env python3
"""Import scraped ImmoScout24 listings into property-investment-finder's
data/listings.db, schema.sql-conformant (plz/city/kreis_ags/bundesland)."""
import json
import sqlite3
from datetime import datetime, timezone

DB_PATH = "/tmp/property-investment-finder/data/listings.db"

CITY_TO_KREIS = [
    ("Leipzig", "14713", "Leipzig", "Sachsen"),
    ("Halle", "15002", "Halle (Saale)", "Sachsen-Anhalt"),
    ("Magdeburg", "15003", "Magdeburg", "Sachsen-Anhalt"),
    ("Frankfurt", "12053", "Frankfurt (Oder)", "Brandenburg"),
    ("Cottbus", "12052", "Cottbus", "Brandenburg"),
    ("Brandenburg", "12051", "Brandenburg an der Havel", "Brandenburg"),
    ("Berlin", "11000", "Berlin", "Berlin"),
    ("Spandau", "11000", "Berlin", "Berlin"),  # IS24 sometimes drops the "Berlin" prefix
]


def normalize(city_raw: str) -> tuple[str, str | None, str]:
    c = city_raw.strip()
    for prefix, kreis, clean_city, bl in CITY_TO_KREIS:
        if c.startswith(prefix):
            return clean_city, kreis, bl
    return c, None, ""


def main():
    with open("is24_listings_meta.json") as f:
        meta = json.load(f)
    with open("is24_expose_texts.json") as f:
        texts = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    inserted, skipped_dup, no_text = 0, 0, 0
    unmatched_cities = set()
    now = datetime.now(timezone.utc).isoformat()

    for m in meta:
        is24_id = m["is24_id"]
        listing_id = f"is24-{is24_id}"
        cur.execute("SELECT 1 FROM listing WHERE listing_id = ?", (listing_id,))
        if cur.fetchone():
            skipped_dup += 1
            continue
        raw_text = texts.get(is24_id, "")
        if len(raw_text) < 50:
            no_text += 1
        clean_city, kreis_ags, bundesland = normalize(m["city"])
        if kreis_ags is None:
            unmatched_cities.add(m["city"])
        cur.execute("""
            INSERT INTO listing (
                listing_id, title, price, living_space, rent_monthly, rooms,
                floor, built_year, condition, plz, city, kreis_ags, bundesland,
                address, latitude, longitude,
                is_erbpacht, is_vacation, is_auction, is_care_apartment, is_social_binding,
                property_type, url, scraped_at, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            listing_id, m["title"], m["price"], m["living_space"], 0.0, m["rooms"],
            None, m["built_year"], "unknown", m["plz"], clean_city, kreis_ags, bundesland,
            m["city"], None, None,
            0, 0, 0, 0, 0,
            "apartment", m["url"], now, raw_text,
        ))
        inserted += 1

    conn.commit()

    cur.execute("SELECT COUNT(*), COUNT(DISTINCT listing_id), COUNT(DISTINCT url) FROM listing")
    total, distinct_id, distinct_url = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM listing WHERE LENGTH(raw_data) > 100")
    good_raw = cur.fetchone()[0]

    print(f"Inserted: {inserted}, skipped (dup listing_id): {skipped_dup}, no/short text: {no_text}")
    print(f"DB totals: {total} rows, {distinct_id} distinct listing_id, {distinct_url} distinct url")
    print(f"Rows with raw_data > 100 chars: {good_raw}/{total}")
    print(f"Unmatched cities (kreis_ags=NULL): {unmatched_cities}")

    conn.close()


if __name__ == "__main__":
    main()
