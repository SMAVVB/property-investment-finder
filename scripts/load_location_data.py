"""
Property Investment Finder — Phase 3 location data loader.

Loads data/location_data.csv into the `location` table (exact build-plan
schema: kreis_ags TEXT PRIMARY KEY, pop_trend_10y, vacancy_rate,
rent_index_eur_m2, rent_growth_5y, price_eur_m2, grunderwerbsteuer_pct,
updated). `city` and `data_quality` in the CSV are documentation-only and
are not inserted -- they are not part of the schema.

PLACEHOLDER cells are stored as NULL, never as a fabricated number.
"""
import csv
import sqlite3
import sys

LOCATION_COLUMNS = [
    "kreis_ags",
    "pop_trend_10y",
    "vacancy_rate",
    "rent_index_eur_m2",
    "rent_growth_5y",
    "price_eur_m2",
    "grunderwerbsteuer_pct",
    "updated",
]


def _parse_value(raw: str):
    if raw is None or raw.strip().upper() == "PLACEHOLDER" or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return raw


def load(csv_path: str, db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS location (
          kreis_ags TEXT PRIMARY KEY,
          pop_trend_10y REAL,
          vacancy_rate REAL,
          rent_index_eur_m2 REAL,
          rent_growth_5y REAL,
          price_eur_m2 REAL,
          grunderwerbsteuer_pct REAL,
          updated TEXT
        )
        """
    )

    count = 0
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            values = [_parse_value(row[col]) if col != "kreis_ags" and col != "updated"
                      else row[col] for col in LOCATION_COLUMNS]
            placeholders = ", ".join("?" for _ in LOCATION_COLUMNS)
            cur.execute(
                f"INSERT OR REPLACE INTO location ({', '.join(LOCATION_COLUMNS)}) "
                f"VALUES ({placeholders})",
                values,
            )
            count += 1
    conn.commit()
    conn.close()
    return count


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "data/location_data.csv"
    db_path = sys.argv[2] if len(sys.argv) > 2 else "location_test.sqlite"
    n = load(csv_path, db_path)
    print(f"Loaded {n} rows into {db_path} (location table)")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT kreis_ags, price_eur_m2, grunderwerbsteuer_pct FROM location ORDER BY kreis_ags")
    for row in cur.fetchall():
        print(row)
    conn.close()
