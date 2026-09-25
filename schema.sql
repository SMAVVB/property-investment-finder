-- ============================================================
-- Property Investment Finder — Database Schema (Phase 1)
-- ============================================================
-- 5 Tabellen exakt nach Build-Plan-Spezifikation:
-- listing, financials, judgments, location, labels
-- ============================================================

-- Tabelle 1: listing — Rohdaten der Immobilien aus dem Extractor
CREATE TABLE IF NOT EXISTS listing (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id          TEXT    NOT NULL UNIQUE,  -- Externe ID (z.B. von ImmoScout)
    title               TEXT,                      -- Titel der Anzeige
    price               REAL    NOT NULL,          -- Kaufpreis in Euro
    living_space        REAL    NOT NULL,          -- Wohnfläche in m²
    rent_monthly        REAL,                      -- Monatliche Kaltmiete in Euro
    rent_per_sqm        REAL,                      -- Kaltmiete pro m²
    rooms               INTEGER,                   -- Anzahl Zimmer
    floor               INTEGER,                   -- Stockwerk
    built_year          INTEGER,                   -- Baujahr
    condition           TEXT,                      -- Zustand: 'renovated', 'needs_work', 'raw'
    location_city       TEXT    NOT NULL,          -- Stadt
    location_state      TEXT,                      -- Bundesland
    location_address    TEXT,                      -- Adresse (optional)
    latitude            REAL,                      -- GPS Breite
    longitude           REAL,                      -- GPS Länge
    is_erbpacht         BOOLEAN NOT NULL DEFAULT 0,-- Erbpacht (Erbbaurecht)
    is_vacation         BOOLEAN NOT NULL DEFAULT 0,-- Ferienwohnung
    is_auction          BOOLEAN NOT NULL DEFAULT 0,-- Zwangsversteigerung
    is_care_apartment   BOOLEAN NOT NULL DEFAULT 0,-- Betreutes Wohnen
    is_social_binding   BOOLEAN NOT NULL DEFAULT 0,-- Sozialbindung
    property_type       TEXT    NOT NULL DEFAULT 'apartment',
    url                 TEXT,                      -- Link zur Anzeige
    scraped_at          TEXT,                      -- Zeitpunkt des Scrapings (ISO 8601)
    raw_data            TEXT,                      -- Rohdaten als JSON (optional)
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Tabelle 2: financials — Berechnete Finanzkennzahlen pro Immobilie
CREATE TABLE IF NOT EXISTS financials (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id              TEXT    NOT NULL UNIQUE,
    purchase_costs_eur      REAL,              -- Kaufnebenkosten in Euro
    all_in_costs            REAL,              -- All-in-Kosten K = price + purchase_costs + renovation
    annual_rent             REAL,              -- Jahreskaltmiete R_year
    gross_yield             REAL,              -- Brutto-Yield (%) = R_year / price * 100
    net_yield               REAL,              -- Netto-Yield (%) = (R_year*(1-v) - 12*H_non_alloc - M) / K
    kaufpreisfaktor         REAL,              -- Kaufpreisfaktor k = P / R_year
    loan_amount             REAL,              -- Kreditbetrag
    monthly_interest        REAL,              -- Monatliche Zinszahlung
    monthly_amortization    REAL,              -- Monatliche Tilgung
    total_monthly_mortgage  REAL,              -- Zins + Tilgung
    monthly_nk              REAL,              -- Monatliches Hausgeld (total)
    monthly_nk_non_alloc    REAL,              -- Monatliches Hausgeld (nicht umlagefähig)
    annual_loan_costs       REAL,              -- Jährliche Kreditkosten M
    monthly_surplus         REAL,              -- Kaltmiete - Gesamtkosten
    monthly_top_up          REAL,              -- Monatliche Zuzahlung
    equity_required         REAL,              -- Erforderliches Eigenkapital
    renovation_budget       REAL,              -- Sanierungsbudget
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (listing_id) REFERENCES listing(listing_id)
);

-- Tabelle 3: judgments — Bewertungen und Filter-Entscheidungen
CREATE TABLE IF NOT EXISTS judgments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id          TEXT    NOT NULL UNIQUE,
    passed_filter       BOOLEAN NOT NULL,      -- Hat alle Filter bestanden?
    outlier_tier        TEXT,                  -- 'phenomenal', 'very_good', 'acceptable', 'market'
    stress_test_passed  BOOLEAN,               -- Cashflow unter Stress (2% mehr Zins, 6 Monate Leerstand)
    stress_monthly_surplus REAL,               -- Monatlicher Überschuss unter Stress
    stress_6month_loss  REAL,                  -- Gesamtverlust über 6 Monate unter Stress
    rejection_reasons   TEXT,                  -- JSON-Array mit Ablehnungsgründen
    score               REAL,                  -- Gesamtwertung (0-100)
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (listing_id) REFERENCES listing(listing_id)
);

-- Tabelle 4: location — Geodaten und ÖPNV-Informationen
CREATE TABLE IF NOT EXISTS location (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id          TEXT    NOT NULL UNIQUE,
    city                TEXT    NOT NULL,
    state               TEXT,
    kreis_ags           TEXT,                  -- Kreis-AGS (PK für Verknüpfung mit Phase-3-Daten)
    latitude            REAL,
    longitude           REAL,
    distance_to_station_minutes REAL,          -- Entfernung zur nächsten Bahn in Minuten
    station_name        TEXT,                  -- Name des nächsten Bahnhofs
    transport_types     TEXT,                  -- Arten: 'S-Bahn', 'RE', 'U-Bahn', 'Bus'
    travel_time_to_berlin_hours REAL,          -- Reisezeit nach Berlin Hbf in Stunden
    region_label        TEXT,                  -- Region: 'berlin_outer', 's_bahn_belt', 'brandenburg_town'
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (listing_id) REFERENCES listing(listing_id)
);

-- Tabelle 5: labels — Kategorisierung und Labels
CREATE TABLE IF NOT EXISTS labels (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id          TEXT    NOT NULL,
    label_key           TEXT    NOT NULL,      -- z.B. 'region', 'tier', 'city_class'
    label_value         TEXT    NOT NULL,      -- z.B. 'berlin_outer', 'phenomenal', 'A'
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (listing_id) REFERENCES listing(listing_id)
);

-- Indizes für häufige Abfragen
CREATE INDEX IF NOT EXISTS idx_listing_price ON listing(price);
CREATE INDEX IF NOT EXISTS idx_listing_city ON listing(location_city);
CREATE INDEX IF NOT EXISTS idx_listing_state ON listing(location_state);
CREATE INDEX IF NOT EXISTS idx_financials_kaufpreisfaktor ON financials(kaufpreisfaktor);
CREATE INDEX IF NOT EXISTS idx_financials_net_yield ON financials(net_yield);
CREATE INDEX IF NOT EXISTS idx_judgments_passed ON judgments(passed_filter);
CREATE INDEX IF NOT EXISTS idx_judgments_tier ON judgments(outlier_tier);
CREATE INDEX IF NOT EXISTS idx_location_kreis ON location(kreis_ags);
