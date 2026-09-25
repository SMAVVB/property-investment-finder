-- ============================================================
-- Property Investment Finder — Database Schema (Phase 1)
-- ============================================================
-- 5 Tabellen für die Pipeline: Extractor → Calculator → Judge → Ranker
-- ============================================================

-- Tabelle 1: listings — Rohdaten der Immobilien aus dem Extractor
CREATE TABLE IF NOT EXISTS listings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id      TEXT    NOT NULL UNIQUE,  -- Externe ID (z.B. von ImmoScout)
    title           TEXT,                      -- Titel der Anzeige
    price           REAL    NOT NULL,          -- Kaufpreis in Euro
    living_space    REAL    NOT NULL,          -- Wohnfläche in m²
    rent_monthly    REAL,                      -- Monatliche Kaltmiete in Euro
    rent_per_sqm    REAL,                      -- Kaltmiete pro m²
    rooms           INTEGER,                   -- Anzahl Zimmer
    floor           INTEGER,                   -- Stockwerk
    built_year      INTEGER,                   -- Baujahr
    condition       TEXT,                      -- Zustand: 'renovated', 'needs_work', 'raw'
    location_city   TEXT    NOT NULL,          -- Stadt
    location_state  TEXT,                      -- Bundesland
    location_address TEXT,                     -- Adresse (optional)
    latitude        REAL,                      -- GPS Breite
    longitude       REAL,                      -- GPS Länge
    is_erbpacht     BOOLEAN NOT NULL DEFAULT 0,-- Erbpacht?
    is_vacation     BOOLEAN NOT NULL DEFAULT 0,-- Ferienwohnsitz?
    property_type   TEXT    NOT NULL DEFAULT 'apartment',  -- 'apartment', 'house', 'studio'
    url             TEXT,                      -- Link zur Anzeige
    scraped_at      TEXT,                      -- Zeitpunkt des Scrapings (ISO 8601)
    raw_data        TEXT,                      -- Rohdaten als JSON (optional)
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Tabelle 2: criteria — Investitionskriterien (konfigurierbare Schwellenwerte)
CREATE TABLE IF NOT EXISTS criteria (
    key     TEXT PRIMARY KEY,   -- Schlüssel (z.B. 'purchase_price_min')
    value   TEXT    NOT NULL,   -- Wert als Text (wird je nach Kontext geparst)
    category TEXT,              -- Kategorie (z.B. 'price', 'space', 'yield')
    comment TEXT,               -- Beschreibung des Parameters
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Tabelle 3: calculations — Berechnete Kennzahlen pro Immobilie
CREATE TABLE IF NOT EXISTS calculations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id          TEXT    NOT NULL UNIQUE,
    purchase_costs_eur  REAL,              -- Kaufnebenkosten in Euro
    total_acquisition   REAL,              -- Gesamtakquisitionskosten (Kaufpreis + Nebenkosten)
    loan_amount         REAL,              -- Kreditbetrag in Euro
    monthly_interest    REAL,              -- Monatliche Zinszahlung
    monthly_amortization REAL,             -- Monatliche Tilgung
    total_monthly_mortgage REAL,           -- Gesamte monatliche Kreditbelastung (Zins + Tilgung)
    total_monthly_cost  REAL,              -- Gesamte monatliche Kosten (Kredit + NK)
    monthly_nk          REAL,              -- Monatliche Nebenkosten (Heizung, Wasser, etc.)
    gross_yield         REAL,              -- Brutto-Yield (%)
    net_yield           REAL,              -- Netto-Yield (%)
    monthly_surplus     REAL,              -- Monatlicher Überschuss (Miete - Kosten)
    monthly_top_up      REAL,              -- Monatliche Zuzahlung (negativ = Überschuss)
    payback_years       REAL,              -- Rücklaufzeit in Jahren
    equity_required     REAL,              -- Erforderliches Eigenkapital
    renovation_budget   REAL,              -- Sanierungsbudget
    total_investment    REAL,              -- Gesamtinvestition (Kauf + Nebenkosten + Sanierung)
    score               REAL,              -- Gesamtwertung (0-100)
    passed_filter       BOOLEAN NOT NULL,  -- Hat alle Filter bestanden?
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (listing_id) REFERENCES listings(listing_id)
);

-- Tabelle 4: locations — Geodaten und ÖPNV-Informationen
CREATE TABLE IF NOT EXISTS locations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id      TEXT    NOT NULL UNIQUE,
    city            TEXT    NOT NULL,
    state           TEXT,
    latitude        REAL,
    longitude       REAL,
    distance_to_station_minutes REAL,  -- Entfernung zur nächsten Bahn in Minuten
    station_name    TEXT,              -- Name des nächsten Bahnhofs
    transport_types TEXT,              -- Arten: 'S-Bahn', 'RE', 'U-Bahn', 'Bus'
    travel_time_to_berlin_hours REAL,  -- Reisezeit nach Berlin Hbf in Stunden
    region_label    TEXT,              -- Region: 'berlin_outer', 's_bahn_belt', 'brandenburg_town'
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (listing_id) REFERENCES listings(listing_id)
);

-- Tabelle 5: rankings — Endgültige gerankte Shortlist
CREATE TABLE IF NOT EXISTS rankings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id      TEXT    NOT NULL,
    rank            INTEGER NOT NULL,  -- Rang in der Shortlist (1 = beste)
    score           REAL    NOT NULL,  -- Gesamtwertung (0-100)
    gross_yield     REAL,              -- Brutto-Yield (%)
    net_yield       REAL,              -- Netto-Yield (%)
    monthly_surplus REAL,              -- Monatlicher Überschuss
    category        TEXT,              -- 'hot_deal', 'solid', 'mehrwert'
    notes           TEXT,              -- Anmerkungen zur Bewertung
    ranked_at       TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (listing_id) REFERENCES listings(listing_id)
);

-- Index für häufige Abfragen
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price);
CREATE INDEX IF NOT EXISTS idx_listings_city ON listings(location_city);
CREATE INDEX IF NOT EXISTS idx_listings_state ON listings(location_state);
CREATE INDEX IF NOT EXISTS idx_calculations_passed ON calculations(passed_filter);
CREATE INDEX IF NOT EXISTS idx_rankings_rank ON rankings(rank);
CREATE INDEX IF NOT EXISTS idx_rankings_score ON rankings(score DESC);
