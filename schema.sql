-- ============================================================
-- Property Investment Finder — Database Schema (Phase 1)
-- ============================================================
-- 5 Tabellen exakt nach Build-Plan-Spezifikation:
-- listing, financials, judgments, location, labels
-- ============================================================

-- Tabelle 1: listing — Rohdaten der Immobilien aus dem Extractor
-- Pro-Listing-Geodaten + Geo-Detail-Felder (ÖPNV etc.)
CREATE TABLE IF NOT EXISTS listing (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id                  TEXT    NOT NULL UNIQUE,  -- Externe ID (z.B. von ImmoScout)
    title                       TEXT,                      -- Titel der Anzeige
    price                       REAL    NOT NULL,          -- Kaufpreis in Euro
    living_space                REAL    NOT NULL,          -- Wohnfläche in m²
    rent_monthly                REAL,                      -- Monatliche Kaltmiete in Euro
    rent_per_sqm                REAL,                      -- Kaltmiete pro m²
    rooms                       INTEGER,                   -- Anzahl Zimmer
    floor                       INTEGER,                   -- Stockwerk
    built_year                  INTEGER,                   -- Baujahr
    condition                   TEXT,                      -- Zustand: 'renovated', 'needs_work', 'raw'
    plz                         TEXT,                      -- Postleitzahl
    city                        TEXT    NOT NULL,          -- Stadt
    kreis_ags                   TEXT,                      -- Kreis-AGS (FK zu location.kreis_ags)
    bundesland                  TEXT,                      -- Bundesland
    address                     TEXT,                      -- Adresse (optional)
    latitude                    REAL,                      -- GPS Breite
    longitude                   REAL,                      -- GPS Länge
    is_erbpacht                 BOOLEAN NOT NULL DEFAULT 0,-- Erbpacht (Erbbaurecht)
    is_vacation                 BOOLEAN NOT NULL DEFAULT 0,-- Ferienwohnung
    is_auction                  BOOLEAN NOT NULL DEFAULT 0,-- Zwangsversteigerung
    is_care_apartment           BOOLEAN NOT NULL DEFAULT 0,-- Betreutes Wohnen
    is_social_binding           BOOLEAN NOT NULL DEFAULT 0,-- Sozialbindung
    property_type               TEXT    NOT NULL DEFAULT 'apartment',
    url                         TEXT,                      -- Link zur Anzeige
    scraped_at                  TEXT,                      -- Zeitpunkt des Scrapings (ISO 8601)
    raw_data                    TEXT,                      -- Rohdaten als JSON (optional)
    -- Geo-Detail-Felder pro Listing (ÖPNV, Reisezeit etc.)
    distance_to_station_minutes REAL,                      -- Entfernung zur nächsten Bahn in Minuten
    station_name                TEXT,                      -- Name des nächsten Bahnhofs
    transport_types             TEXT,                      -- Arten: 'S-Bahn', 'RE', 'U-Bahn', 'Bus'
    travel_time_to_berlin_hours REAL,                      -- Reisezeit nach Berlin Hbf in Stunden
    region_label                TEXT,                      -- Region: 'berlin_outer', 's_bahn_belt', 'brandenburg_town'
    created_at                  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Tabelle 2: financials — Berechnete Finanzkennzahlen pro Immobilie
-- Enthält auch Calculator-Ausgabe (outlier_tier, stress_test, score, etc.)
CREATE TABLE IF NOT EXISTS financials (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id                  TEXT    NOT NULL UNIQUE,
    purchase_costs_eur          REAL,              -- Kaufnebenkosten in Euro
    all_in_costs                REAL,              -- All-in-Kosten K = price + purchase_costs + renovation
    annual_rent                 REAL,              -- Jahreskaltmiete R_year
    gross_yield                 REAL,              -- Brutto-Yield (%) = R_year / price * 100
    net_yield                   REAL,              -- Netto-Yield (%) = (R_year*(1-v) - 12*H_non_alloc - M) / K
    kaufpreisfaktor             REAL,              -- Kaufpreisfaktor k = P / R_year
    loan_amount                 REAL,              -- Kreditbetrag
    monthly_interest            REAL,              -- Monatliche Zinszahlung
    monthly_amortization        REAL,              -- Monatliche Tilgung
    total_monthly_mortgage      REAL,              -- Zins + Tilgung
    monthly_nk                  REAL,              -- Monatliches Hausgeld (total)
    monthly_nk_non_alloc        REAL,              -- Monatliches Hausgeld (nicht umlagefähig)
    annual_loan_costs           REAL,              -- Jährliche Kreditkosten M
    monthly_surplus             REAL,              -- Kaltmiete - Gesamtkosten
    monthly_top_up              REAL,              -- Monatliche Zuzahlung
    equity_required             REAL,              -- Erforderliches Eigenkapital
    renovation_budget           REAL,              -- Sanierungsbudget
    -- Calculator-Ausgabe (kein Judge-Ergebnis)
    outlier_tier                TEXT,              -- 'phenomenal', 'very_good', 'acceptable', 'market'
    stress_test_passed          BOOLEAN,           -- Cashflow unter Stress (2% mehr Zins, 6 Monate Leerstand)
    stress_monthly_surplus      REAL,              -- Monatlicher Überschuss unter Stress
    stress_6month_loss          REAL,              -- Gesamtverlust über 6 Monate unter Stress
    score                       REAL,              -- Gesamtwertung (0-100)
    passed_filter               BOOLEAN,           -- Hat alle Filter bestanden?
    rejection_reasons           TEXT,              -- JSON-Array mit Ablehnungsgründen
    created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (listing_id) REFERENCES listing(listing_id)
);

-- Tabelle 3: judgments — ONE ROW PER (listing, question)
-- Der Judge (THE-511, Laya mit 14 Fragen) schreibt eine Zeile pro Frage.
-- Calculator-Ausgabe gehört NICHT hierhin.
CREATE TABLE IF NOT EXISTS judgments (
    listing_id    TEXT NOT NULL,
    question_id   TEXT NOT NULL,
    model_version TEXT,
    answer        TEXT,
    probability   REAL,
    confidence    REAL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (listing_id, question_id),
    FOREIGN KEY (listing_id) REFERENCES listing(listing_id)
);

-- Tabelle 4: location — REFERENZTABELLE, EINE ZEILE PRO KREIS/REGION
-- Verknüpfung über kreis_ags mit listing.kreis_ags.
-- THE-509 liefert data/location_data.csv + scripts/load_location_data.py.
CREATE TABLE IF NOT EXISTS location (
    kreis_ags           TEXT PRIMARY KEY,
    city                TEXT,
    pop_trend_10y       REAL,
    vacancy_rate        REAL,
    rent_index_eur_m2   REAL,
    rent_growth_5y      REAL,
    price_eur_m2        REAL,
    grunderwerbsteuer_pct REAL,
    updated             TEXT,
    data_quality        TEXT
);

-- Tabelle 5: labels — Manuelle Korrekturen der Judge-Antworten
-- (Trainingsdaten für späteres Laya-Finetuning)
CREATE TABLE IF NOT EXISTS labels (
    listing_id   TEXT NOT NULL,
    question_id  TEXT NOT NULL,
    your_answer  TEXT,
    note         TEXT,
    labeled_at   TEXT,
    PRIMARY KEY (listing_id, question_id),
    FOREIGN KEY (listing_id) REFERENCES listing(listing_id)
);

-- Indizes für häufige Abfragen
CREATE INDEX IF NOT EXISTS idx_listing_price ON listing(price);
CREATE INDEX IF NOT EXISTS idx_listing_city ON listing(city);
CREATE INDEX IF NOT EXISTS idx_listing_state ON listing(bundesland);
CREATE INDEX IF NOT EXISTS idx_listing_kreis ON listing(kreis_ags);
CREATE INDEX IF NOT EXISTS idx_financials_kaufpreisfaktor ON financials(kaufpreisfaktor);
CREATE INDEX IF NOT EXISTS idx_financials_net_yield ON financials(net_yield);
CREATE INDEX IF NOT EXISTS idx_financials_outlier_tier ON financials(outlier_tier);
CREATE INDEX IF NOT EXISTS idx_financials_passed ON financials(passed_filter);
CREATE INDEX IF NOT EXISTS idx_judgments_question ON judgments(question_id);
CREATE INDEX IF NOT EXISTS idx_judgments_model ON judgments(model_version);
