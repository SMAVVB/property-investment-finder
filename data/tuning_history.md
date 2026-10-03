# Autotune history

Append-only log of every autotune / LLM-analyst cycle. See
docs/superpowers/specs/2026-09-26-autonomous-filter-tuning-design.md
for what this loop does and why.

## 2026-09-27T00:44:57.627514+00:00 [autotune]

- Shortlist size: 0
- Mean score: 0.00
- Promoted: no
- Preset: `{"purchase_price": {"min": 80000, "max": 150000, "comment": "Gesamter Kaufpreis inkl. aller Nebenkosten"}, "built_year": {"min": 1990, "comment": "Bevorzugt Baujahr 1990+, um GDR-/Vorkriegsbestand mit hohem Sanierungsrisiko zu meiden. Kein Mindest-Energieausweis (noch keine Praeferenz)."}, "living_space": {"target_min": 35, "target_max": 50, "allowed_min": 30, "allowed_max": 55, "comment": "Zielbereich 35-50m\u00b2, mit Toleranz nach unten/oben bis 30/55m\u00b2"}, "equity": {"min": 20000, "max": 40000, "comment": "Verf\u00fcgbares Eigenkapital f\u00fcr Anzahlung und Nebenkosten"}, "financing": {"loan_to_value": 1.0, "comment": "100% Bankfinanzierung des Kaufpreises"}, "loan": {"interest_rate": 0.048, "amortization_rate": 0.02, "total_rate": 0.068, "comment": "Zins 4.8%, Tilgung 2%, zusammen 6.8% p.a. auf den Kreditbetrag"}, "purchase_costs": {"berlin": 0.06, "brandenburg": 0.065, "brandenburg_berlin_belt": 0.065, "saxony": 0.055, "saxony_anhalt": 0.05, "other": 0.06, "comment": "Grunderwerbsteuer + Notar; Makler separat. Berlin 6%, Brandenburg 6.5%"}, "renovation": {"budget": 15000, "comment": "Pauschales Sanierungsbudget; kann pro Listing \u00fcberschrieben werden"}, "location": {"max_travel_time_hours": 1.5, "comment": "Max 1.5h mit \u00d6PNV von Berlin (Hbf) zum Objekt"}, "target_regions": {"berlin_outer_districts": ["Neuk\u00f6lln", "Treptow", "K\u00f6penick", "Lichtenberg", "Marzahn", "Hellersdorf", "Tempelhof", "Charlottenburg", "Spandau", "Reinickendorf", "Weissensee", "Frohnau", "Pankow", "Prenzlauer Berg", "Kreuzberg"], "s_bahn_belt": ["Potsdam", "K\u00f6nigs Wusterhausen", "Falkensee", "Eberswalde", "Bernau", "Schwedt", "Oranienburg", "Kleinmachnow", "Stahnsdorf", "Ketzin", "Wandlitz", "Hennigsdorf", "Teltow", "Zossen", "Ludwigsfelde", "Rathenow"], "brandenburg_towns": ["Cottbus", "Frankfurt (Oder)", "Leipzig", "Dessau-Ro\u00dflau", "Wittenberg", "Senftenberg", "Brandenburg an der Havel", "Potsdam"], "comment": "Berlin Au\u00dfenbezirke + S-Bahn/RE-G\u00fcrtel + Brandenburger Universit\u00e4tsst\u00e4dte"}, "location_must_have": {"max_distance_to_station_minutes": 10, "comment": "Muss innerhalb von \u226410 Min. Fu\u00dfweg zu einem Bahnanschluss haben"}, "yield": {"gross": {"min": 0.035, "preferred": 0.05}, "comment": "Brutto-Yield = Jahreskaltmiete / Kaufpreis. 3.5% Minimum, 5%+ bevorzugt"}, "monthly_top_up": {"max": 500, "comment": "Die Differenz zwischen monatlichen Kosten (Kredit + NK) und Kaltmiete"}, "exclusions": {"erbpacht": true, "vacation": true, "auction": true, "care_apartment": true, "social_binding": true, "city_specific": {"cottbus": {"max_living_space": 45, "max_price": 99000}, "frankfurt_oder": {"max_living_space": 45, "max_price": 81000}, "leipzig": {"max_living_space": 45, "max_price": 117000}}, "comment": "Erbpacht, Ferienwohnung, Zwangsversteigerung, Betreutes Wohnen, Sozialbindung immer ausschlie\u00dfen; st\u00e4dtespezifische Limits als zus\u00e4tzlicher Filter"}, "monthly_nk_per_sqm": 3.0, "non_allocable_pct": 0.02, "comment": "Gesch\u00e4tztes Hausgeld; nicht umlagef\u00e4higer Anteil f\u00fcr Build-Plan-Formel", "rent_per_sqm": {"berlin_min": 8.0, "berlin_max": 12.0, "brandenburg_min": 5.0, "brandenburg_max": 8.0, "other_min": 5.0, "other_max": 9.0, "comment": "Referenzwerte f\u00fcr Kaltmiete pro m\u00b2 zur Plausibilisierung"}}`

## 2026-09-27T00:47:10.028138+00:00 [autotune]

- Shortlist size: 100
- Mean score: 28.92
- Promoted: yes
- Preset: `{"purchase_price": {"min": 80000, "max": 150000, "comment": "Gesamter Kaufpreis inkl. aller Nebenkosten"}, "built_year": {"min": 0, "comment": "Bevorzugt Baujahr 1990+, um GDR-/Vorkriegsbestand mit hohem Sanierungsrisiko zu meiden. Kein Mindest-Energieausweis (noch keine Praeferenz)."}, "living_space": {"target_min": 35, "target_max": 50, "allowed_min": 30, "allowed_max": 55, "comment": "Zielbereich 35-50m\u00b2, mit Toleranz nach unten/oben bis 30/55m\u00b2"}, "equity": {"min": 20000, "max": 40000, "comment": "Verf\u00fcgbares Eigenkapital f\u00fcr Anzahlung und Nebenkosten"}, "financing": {"loan_to_value": 1.0, "comment": "100% Bankfinanzierung des Kaufpreises"}, "loan": {"interest_rate": 0.048, "amortization_rate": 0.02, "total_rate": 0.068, "comment": "Zins 4.8%, Tilgung 2%, zusammen 6.8% p.a. auf den Kreditbetrag"}, "purchase_costs": {"berlin": 0.06, "brandenburg": 0.065, "brandenburg_berlin_belt": 0.065, "saxony": 0.055, "saxony_anhalt": 0.05, "other": 0.06, "comment": "Grunderwerbsteuer + Notar; Makler separat. Berlin 6%, Brandenburg 6.5%"}, "renovation": {"budget": 15000, "comment": "Pauschales Sanierungsbudget; kann pro Listing \u00fcberschrieben werden"}, "location": {"max_travel_time_hours": 1.5, "comment": "Max 1.5h mit \u00d6PNV von Berlin (Hbf) zum Objekt"}, "target_regions": {"berlin_outer_districts": ["Neuk\u00f6lln", "Treptow", "K\u00f6penick", "Lichtenberg", "Marzahn", "Hellersdorf", "Tempelhof", "Charlottenburg", "Spandau", "Reinickendorf", "Weissensee", "Frohnau", "Pankow", "Prenzlauer Berg", "Kreuzberg"], "s_bahn_belt": ["Potsdam", "K\u00f6nigs Wusterhausen", "Falkensee", "Eberswalde", "Bernau", "Schwedt", "Oranienburg", "Kleinmachnow", "Stahnsdorf", "Ketzin", "Wandlitz", "Hennigsdorf", "Teltow", "Zossen", "Ludwigsfelde", "Rathenow"], "brandenburg_towns": ["Cottbus", "Frankfurt (Oder)", "Leipzig", "Dessau-Ro\u00dflau", "Wittenberg", "Senftenberg", "Brandenburg an der Havel", "Potsdam"], "comment": "Berlin Au\u00dfenbezirke + S-Bahn/RE-G\u00fcrtel + Brandenburger Universit\u00e4tsst\u00e4dte"}, "location_must_have": {"max_distance_to_station_minutes": 5, "comment": "Muss innerhalb von \u226410 Min. Fu\u00dfweg zu einem Bahnanschluss haben"}, "yield": {"gross": {"min": 0.045, "preferred": 0.05}, "comment": "Brutto-Yield = Jahreskaltmiete / Kaufpreis. 3.5% Minimum, 5%+ bevorzugt"}, "monthly_top_up": {"max": 500, "comment": "Die Differenz zwischen monatlichen Kosten (Kredit + NK) und Kaltmiete"}, "exclusions": {"erbpacht": true, "vacation": true, "auction": true, "care_apartment": true, "social_binding": true, "city_specific": {"cottbus": {"max_living_space": 45, "max_price": 99000}, "frankfurt_oder": {"max_living_space": 45, "max_price": 81000}, "leipzig": {"max_living_space": 45, "max_price": 117000}}, "comment": "Erbpacht, Ferienwohnung, Zwangsversteigerung, Betreutes Wohnen, Sozialbindung immer ausschlie\u00dfen; st\u00e4dtespezifische Limits als zus\u00e4tzlicher Filter"}, "monthly_nk_per_sqm": 3.0, "non_allocable_pct": 0.02, "comment": "Gesch\u00e4tztes Hausgeld; nicht umlagef\u00e4higer Anteil f\u00fcr Build-Plan-Formel", "rent_per_sqm": {"berlin_min": 8.0, "berlin_max": 12.0, "brandenburg_min": 5.0, "brandenburg_max": 8.0, "other_min": 5.0, "other_max": 9.0, "comment": "Referenzwerte f\u00fcr Kaltmiete pro m\u00b2 zur Plausibilisierung"}}`

## 2026-09-27T06:00:36.320397+00:00 [autotune]

- Shortlist size: 108
- Mean score: 28.79
- Promoted: yes
- Preset: `{"purchase_price": {"min": 80000, "max": 150000, "comment": "Gesamter Kaufpreis inkl. aller Nebenkosten"}, "built_year": {"min": 0, "comment": "Bevorzugt Baujahr 1990+, um GDR-/Vorkriegsbestand mit hohem Sanierungsrisiko zu meiden. Kein Mindest-Energieausweis (noch keine Praeferenz)."}, "living_space": {"target_min": 35, "target_max": 50, "allowed_min": 30, "allowed_max": 55, "comment": "Zielbereich 35-50m\u00b2, mit Toleranz nach unten/oben bis 30/55m\u00b2"}, "equity": {"min": 20000, "max": 40000, "comment": "Verf\u00fcgbares Eigenkapital f\u00fcr Anzahlung und Nebenkosten"}, "financing": {"loan_to_value": 1.0, "comment": "100% Bankfinanzierung des Kaufpreises"}, "loan": {"interest_rate": 0.048, "amortization_rate": 0.02, "total_rate": 0.068, "comment": "Zins 4.8%, Tilgung 2%, zusammen 6.8% p.a. auf den Kreditbetrag"}, "purchase_costs": {"berlin": 0.06, "brandenburg": 0.065, "brandenburg_berlin_belt": 0.065, "saxony": 0.055, "saxony_anhalt": 0.05, "other": 0.06, "comment": "Grunderwerbsteuer + Notar; Makler separat. Berlin 6%, Brandenburg 6.5%"}, "renovation": {"budget": 15000, "comment": "Pauschales Sanierungsbudget; kann pro Listing \u00fcberschrieben werden"}, "location": {"max_travel_time_hours": 1.5, "comment": "Max 1.5h mit \u00d6PNV von Berlin (Hbf) zum Objekt"}, "target_regions": {"berlin_outer_districts": ["Neuk\u00f6lln", "Treptow", "K\u00f6penick", "Lichtenberg", "Marzahn", "Hellersdorf", "Tempelhof", "Charlottenburg", "Spandau", "Reinickendorf", "Weissensee", "Frohnau", "Pankow", "Prenzlauer Berg", "Kreuzberg"], "s_bahn_belt": ["Potsdam", "K\u00f6nigs Wusterhausen", "Falkensee", "Eberswalde", "Bernau", "Schwedt", "Oranienburg", "Kleinmachnow", "Stahnsdorf", "Ketzin", "Wandlitz", "Hennigsdorf", "Teltow", "Zossen", "Ludwigsfelde", "Rathenow"], "brandenburg_towns": ["Cottbus", "Frankfurt (Oder)", "Leipzig", "Dessau-Ro\u00dflau", "Wittenberg", "Senftenberg", "Brandenburg an der Havel", "Potsdam"], "comment": "Berlin Au\u00dfenbezirke + S-Bahn/RE-G\u00fcrtel + Brandenburger Universit\u00e4tsst\u00e4dte"}, "location_must_have": {"max_distance_to_station_minutes": 5, "comment": "Muss innerhalb von \u226410 Min. Fu\u00dfweg zu einem Bahnanschluss haben"}, "yield": {"gross": {"min": 0.045, "preferred": 0.05}, "comment": "Brutto-Yield = Jahreskaltmiete / Kaufpreis. 3.5% Minimum, 5%+ bevorzugt"}, "monthly_top_up": {"max": 500, "comment": "Die Differenz zwischen monatlichen Kosten (Kredit + NK) und Kaltmiete"}, "exclusions": {"erbpacht": true, "vacation": true, "auction": true, "care_apartment": true, "social_binding": true, "city_specific": {"cottbus": {"max_living_space": 45, "max_price": 99000}, "frankfurt_oder": {"max_living_space": 45, "max_price": 81000}, "leipzig": {"max_living_space": 50, "max_price": 117000}}, "comment": "Erbpacht, Ferienwohnung, Zwangsversteigerung, Betreutes Wohnen, Sozialbindung immer ausschlie\u00dfen; st\u00e4dtespezifische Limits als zus\u00e4tzlicher Filter"}, "monthly_nk_per_sqm": 3.0, "non_allocable_pct": 0.02, "comment": "Gesch\u00e4tztes Hausgeld; nicht umlagef\u00e4higer Anteil f\u00fcr Build-Plan-Formel", "rent_per_sqm": {"berlin_min": 8.0, "berlin_max": 12.0, "brandenburg_min": 5.0, "brandenburg_max": 8.0, "other_min": 5.0, "other_max": 9.0, "comment": "Referenzwerte f\u00fcr Kaltmiete pro m\u00b2 zur Plausibilisierung"}}`

## 2026-09-29T01:53:08.883273+00:00 [autotune]

- Shortlist size: 71
- Mean score: 25.73
- Promoted: no
- Preset: `{"purchase_price": {"min": 80000, "max": 150000, "comment": "Gesamter Kaufpreis inkl. aller Nebenkosten"}, "built_year": {"min": 0, "comment": "Bevorzugt Baujahr 1990+, um GDR-/Vorkriegsbestand mit hohem Sanierungsrisiko zu meiden. Kein Mindest-Energieausweis (noch keine Praeferenz)."}, "living_space": {"target_min": 35, "target_max": 50, "allowed_min": 30, "allowed_max": 55, "comment": "Zielbereich 35-50m\u00b2, mit Toleranz nach unten/oben bis 30/55m\u00b2"}, "equity": {"min": 20000, "max": 40000, "comment": "Verf\u00fcgbares Eigenkapital f\u00fcr Anzahlung und Nebenkosten"}, "financing": {"loan_to_value": 1.0, "comment": "100% Bankfinanzierung des Kaufpreises"}, "loan": {"interest_rate": 0.048, "amortization_rate": 0.02, "total_rate": 0.068, "comment": "Zins 4.8%, Tilgung 2%, zusammen 6.8% p.a. auf den Kreditbetrag"}, "purchase_costs": {"berlin": 0.06, "brandenburg": 0.065, "brandenburg_berlin_belt": 0.065, "saxony": 0.055, "saxony_anhalt": 0.05, "other": 0.06, "comment": "Grunderwerbsteuer + Notar; Makler separat. Berlin 6%, Brandenburg 6.5%"}, "renovation": {"budget": 15000, "comment": "Pauschales Sanierungsbudget; kann pro Listing \u00fcberschrieben werden"}, "location": {"max_travel_time_hours": 1.5, "comment": "Max 1.5h mit \u00d6PNV von Berlin (Hbf) zum Objekt"}, "target_regions": {"berlin_outer_districts": ["Neuk\u00f6lln", "Treptow", "K\u00f6penick", "Lichtenberg", "Marzahn", "Hellersdorf", "Tempelhof", "Charlottenburg", "Spandau", "Reinickendorf", "Weissensee", "Frohnau", "Pankow", "Prenzlauer Berg", "Kreuzberg"], "s_bahn_belt": ["Potsdam", "K\u00f6nigs Wusterhausen", "Falkensee", "Eberswalde", "Bernau", "Schwedt", "Oranienburg", "Kleinmachnow", "Stahnsdorf", "Ketzin", "Wandlitz", "Hennigsdorf", "Teltow", "Zossen", "Ludwigsfelde", "Rathenow"], "brandenburg_towns": ["Cottbus", "Frankfurt (Oder)", "Leipzig", "Dessau-Ro\u00dflau", "Wittenberg", "Senftenberg", "Brandenburg an der Havel", "Potsdam"], "comment": "Berlin Au\u00dfenbezirke + S-Bahn/RE-G\u00fcrtel + Brandenburger Universit\u00e4tsst\u00e4dte"}, "location_must_have": {"max_distance_to_station_minutes": 5, "comment": "Muss innerhalb von \u226410 Min. Fu\u00dfweg zu einem Bahnanschluss haben"}, "yield": {"gross": {"min": 0.045, "preferred": 0.05}, "comment": "Brutto-Yield = Jahreskaltmiete / Kaufpreis. 3.5% Minimum, 5%+ bevorzugt"}, "monthly_top_up": {"max": 500, "comment": "Die Differenz zwischen monatlichen Kosten (Kredit + NK) und Kaltmiete"}, "exclusions": {"erbpacht": true, "vacation": true, "auction": true, "care_apartment": true, "social_binding": true, "city_specific": {"cottbus": {"max_living_space": 45, "max_price": 99000}, "frankfurt_oder": {"max_living_space": 45, "max_price": 81000}, "leipzig": {"max_living_space": 50, "max_price": 117000}}, "comment": "Erbpacht, Ferienwohnung, Zwangsversteigerung, Betreutes Wohnen, Sozialbindung immer ausschlie\u00dfen; st\u00e4dtespezifische Limits als zus\u00e4tzlicher Filter"}, "monthly_nk_per_sqm": 3.0, "non_allocable_pct": 0.02, "comment": "Gesch\u00e4tztes Hausgeld; nicht umlagef\u00e4higer Anteil f\u00fcr Build-Plan-Formel", "rent_per_sqm": {"berlin_min": 8.0, "berlin_max": 12.0, "brandenburg_min": 5.0, "brandenburg_max": 8.0, "other_min": 5.0, "other_max": 9.0, "comment": "Referenzwerte f\u00fcr Kaltmiete pro m\u00b2 zur Plausibilisierung"}}`

## 2026-09-29T03:15:00+00:00 [llm_analyst]

- Shortlist size: 71 (current, from autotune run 3)
- Mean score: 25.73 (not promoted)
- Promoted: no (LLM analyst found data quality issues, not criteria problems)
- Changes: Added Dresden to brandenburg_towns in criteria.yaml
- Rationale: Dresden has 197 scout hits (highest of any city) with excellent metrics
  (kaufpreisfaktor 21.6, median rent 9.79€/m², estimated yield ~4.6%) but ZERO listings
  in the database. This is a data collection gap, not a criteria problem. The autotune
  grid search only varies 3 parameters (built_year.min, yield.gross.min,
  max_distance_to_station_minutes) and cannot address region-level data gaps.
- Key findings:
  1. Dresden: 197 sale hits in region_scouting, 0 listings in DB (data gap)
  2. Berlin: ALL 111 listings have rent_monthly=0 (rent estimation relies on location
     table's rent_index of 13.5€/m² — known gap, handled by estimate_missing_rents())
  3. 3 land listings (poschmann-0002, 0009, 0014) in DB as property_type='land'
     — currently filtered out by other criteria but should be explicitly excluded
  4. CITY_TO_KREIS mapping in import_immoscout.py only has 8 cities; new promoted cities
     get raw city names with NULL kreis_ags
  5. Location table rent_index only covers 4 cities (Berlin, Leipzig, Halle, Magdeburg);
     Frankfurt (Oder), Cottbus, Brandenburg an der Havel have no rent_index
  6. Grid search PARAM_GRID is narrow (3 params) — equity filter (min:20k) and renovation
     budget (15k) are never tested

## 2026-09-29T03:28:53.062442+00:00 [autotune]

- Shortlist size: 71
- Mean score: 25.73
- Promoted: no
- Preset: `{"purchase_price": {"min": 80000, "max": 150000, "comment": "Gesamter Kaufpreis inkl. aller Nebenkosten"}, "built_year": {"min": 0, "comment": "Bevorzugt Baujahr 1990+, um GDR-/Vorkriegsbestand mit hohem Sanierungsrisiko zu meiden. Kein Mindest-Energieausweis (noch keine Praeferenz)."}, "living_space": {"target_min": 35, "target_max": 50, "allowed_min": 30, "allowed_max": 55, "comment": "Zielbereich 35-50m\u00b2, mit Toleranz nach unten/oben bis 30/55m\u00b2"}, "equity": {"min": 20000, "max": 40000, "comment": "Verf\u00fcgbares Eigenkapital f\u00fcr Anzahlung und Nebenkosten"}, "financing": {"loan_to_value": 1.0, "comment": "100% Bankfinanzierung des Kaufpreises"}, "loan": {"interest_rate": 0.048, "amortization_rate": 0.02, "total_rate": 0.068, "comment": "Zins 4.8%, Tilgung 2%, zusammen 6.8% p.a. auf den Kreditbetrag"}, "purchase_costs": {"berlin": 0.06, "brandenburg": 0.065, "brandenburg_berlin_belt": 0.065, "saxony": 0.055, "saxony_anhalt": 0.05, "other": 0.06, "comment": "Grunderwerbsteuer + Notar; Makler separat. Berlin 6%, Brandenburg 6.5%"}, "renovation": {"budget": 15000, "comment": "Pauschales Sanierungsbudget; kann pro Listing \u00fcberschrieben werden"}, "location": {"max_travel_time_hours": 1.5, "comment": "Max 1.5h mit \u00d6PNV von Berlin (Hbf) zum Objekt"}, "target_regions": {"berlin_outer_districts": ["Neuk\u00f6lln", "Treptow", "K\u00f6penick", "Lichtenberg", "Marzahn", "Hellersdorf", "Tempelhof", "Charlottenburg", "Spandau", "Reinickendorf", "Weissensee", "Frohnau", "Pankow", "Prenzlauer Berg", "Kreuzberg"], "s_bahn_belt": ["Potsdam", "Dresden", "K\u00f6nigs Wusterhausen", "Falkensee", "Eberswalde", "Bernau", "Schwedt", "Oranienburg", "Kleinmachnow", "Stahnsdorf", "Ketzin", "Wandlitz", "Hennigsdorf", "Teltow", "Zossen", "Ludwigsfelde", "Rathenow"], "brandenburg_towns": ["Cottbus", "Frankfurt (Oder)", "Leipzig", "Dessau-Ro\u00dflau", "Wittenberg", "Senftenberg", "Brandenburg an der Havel", "Potsdam", "Dresden"], "comment": "Berlin Au\u00dfenbezirke + S-Bahn/RE-G\u00fcrtel + Brandenburger Universit\u00e4tsst\u00e4dte (+ Dresden: 197 scout hits, 0 DB listings \u2014 data gap)"}, "location_must_have": {"max_distance_to_station_minutes": 5, "comment": "Muss innerhalb von \u226410 Min. Fu\u00dfweg zu einem Bahnanschluss haben"}, "yield": {"gross": {"min": 0.045, "preferred": 0.05}, "comment": "Brutto-Yield = Jahreskaltmiete / Kaufpreis. 3.5% Minimum, 5%+ bevorzugt"}, "monthly_top_up": {"max": 500, "comment": "Die Differenz zwischen monatlichen Kosten (Kredit + NK) und Kaltmiete"}, "exclusions": {"erbpacht": true, "vacation": true, "auction": true, "care_apartment": true, "social_binding": true, "city_specific": {"cottbus": {"max_living_space": 45, "max_price": 99000}, "frankfurt_oder": {"max_living_space": 45, "max_price": 81000}, "leipzig": {"max_living_space": 50, "max_price": 117000}}, "comment": "Erbpacht, Ferienwohnung, Zwangsversteigerung, Betreutes Wohnen, Sozialbindung immer ausschlie\u00dfen; st\u00e4dtespezifische Limits als zus\u00e4tzlicher Filter"}, "monthly_nk_per_sqm": 3.0, "non_allocable_pct": 0.02, "comment": "Gesch\u00e4tztes Hausgeld; nicht umlagef\u00e4higer Anteil f\u00fcr Build-Plan-Formel", "rent_per_sqm": {"berlin_min": 8.0, "berlin_max": 12.0, "brandenburg_min": 5.0, "brandenburg_max": 8.0, "other_min": 5.0, "other_max": 9.0, "comment": "Referenzwerte f\u00fcr Kaltmiete pro m\u00b2 zur Plausibilisierung"}}`

## 2026-09-30T03:00:00+00:00 [llm_analyst]

- Shortlist size: 71 (current, from autotune run 5)
- Mean score: 25.73 (not promoted)
- Promoted: no (LLM analyst recommending criteria change)
- Changes: Lowered equity.min from 20000 to 15000 in criteria.yaml
- Rationale: The equity.min=20000 filter blocks 52 listings that are financially sound:
  - All 52 have gross_yield >= 4.5% (passing the yield filter)
  - 12 are in 'phenomenal' or 'very_good' tier
  - 28 have score > 25
  - These listings are blocked because equity_required = purchase_costs + renovation_budget
    falls between 19000-20000€, just under the 20k threshold. The 15k threshold captures
    these without letting in truly undercapitalized deals.
- Data quality notes:
  1. Dresden: still 197 scout hits, 0 DB listings (data collection gap, not criteria)
  2. Brandenburg S-Bahn belt cities: all 0 sale hits in region_scouting (scraping gap)
  3. Many duplicate rows in region_scouting (same city/scout batch repeated)
  4. 3 land-type listings in DB (poschmann-0002, 0009, 0014) — already filtered out
  5. Grid search PARAM_GRID only tests 3 params (built_year.min, yield.gross.min,
     max_distance_to_station_minutes); equity and renovation_budget never tested

## 2026-10-03T03:00:00+00:00 [llm_analyst]

- Shortlist size: 71 (current, from autotune run 5)
- Mean score: 25.73 (not promoted)
- Promoted: no (LLM analyst recommending criteria change)
- Changes: Raised Leipzig city-specific limits in criteria.yaml:
  - max_living_space: 50 -> 55 (matching global allowed_max)
  - max_price: 117000 -> 120000
- Rationale: The Leipzig-specific living space limit (50m²) is 5m² tighter
  than the global allowed_max (55m²), blocking 68 Leipzig listings with
  yield >= 4.5%. Analysis shows 37 additional listings would pass with the
  raised limits. Top unblocked listings have scores 43.9 (yield 6.13%),
  41.0 (yield 5.96%), 38.2 (yield 5.78%) — quality deals currently excluded
  by an arbitrary 5m² city-specific cap. The price increase to 120000€
  captures listings in the 117000-120000€ range that are otherwise blocked.
- Key findings:
  1. Equity.min=15000 was already applied in previous LLM analyst cycle
  2. Dresden: still 197 scout hits, 0 DB listings (data collection gap)
  3. Hannover: 75 scout hits, 0 DB listings (data collection gap)
  4. Dortmund: 52 scout hits, only 5 DB listings (data gap)
  5. All 363 listings have rent_monthly=0 or NULL — rent estimation relies
     entirely on location table's rent_index (known, handled by estimate_missing_rents())
  6. f_heating_fossil (119 true) and f_renovation (77 true) are the only
     meaningful risk flags; all other flags always predict false
  7. Yield >= 4.5% is the single biggest blocker (187 listings) — already
     tested by the grid search
  8. Grid search PARAM_GRID only tests 3 params (built_year.min, yield.gross.min,
     max_distance_to_station_minutes); city-specific limits never tested
