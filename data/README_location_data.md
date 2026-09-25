# Phase 3 — Location Data

Status: **PARTIAL, echte Recherche wo moeglich, Rest als PLACEHOLDER markiert** (nicht erfunden).

## Was echt recherchiert wurde (mit Quelle)

- **GrESt-Saetze** (Stand 2026, korrigiert gegenueber der ersten criteria.yaml-Version,
  die Sachsen/Sachsen-Anhalt falsch hatte):
  Berlin 6.0%, Brandenburg 6.5%, Sachsen 5.5% (seit 1.1.2023, nicht mehr 3.5%),
  Sachsen-Anhalt 5.0% (nicht 6.5%).
  Quelle: finanz-tools.de/grunderwerbsteuer/bundeslaender-tabelle, rechenbar.de (Abfrage 2026-09-25).
- **Kaltmiete pro m²** (Mietspiegel, Q2/Q3 2026): Leipzig 9.09 €/m², Halle (Saale) 9.22 €/m²,
  Magdeburg 7.44 €/m². Quelle: immoportal.com, engelvoelkers.com Mietspiegel-Seiten.
- **Kaufpreise pro m²**: Leipzig ~2985 €/m² (Spanne 2678-3360), Cottbus ~2602 €/m²,
  Frankfurt (Oder) ~2242 €/m² (Spanne 2028-2384), Brandenburg an der Havel ~2902 €/m².
  Quelle: immoportal.com, engelvoelkers.com, immowelt.de Immobilienpreise-Seiten (Abfrage 2026-09-25).

## Was PLACEHOLDER ist (bewusst nicht erfunden)

- Kaufpreise pro m² fuer Halle, Magdeburg, Eberswalde, Wildau, Berlin-Aussenbezirke (Web-Suche
  lieferte hier nur Mietdaten oder gar nichts Verwertbares).
- `pop_trend_10y` (Bevoelkerungstrend) und `vacancy_rate` (Leerstandsquote) fuer ALLE Orte --
  diese Kennzahlen stehen typischerweise in destatis-Regionaldatenbank / Zensus-Tabellen, die
  keine brauchbaren Web-Suchtreffer mit konkreten Zahlen liefern; sollten von Hand aus
  https://www.regionalstatistik.de nachgetragen werden.
- `rent_growth_5y` fuer alle Orte.

## Naechster Schritt

1. `pop_trend_10y` + `vacancy_rate` aus regionalstatistik.de (Kreisebene) nachtragen.
2. Kaufpreise fuer Halle/Magdeburg/Eberswalde/Wildau/Berlin-Aussenbezirke aus einer
   zahlengetriebenen Quelle (z.B. Gutachterausschuss-Berichte, nicht nur Search-Snippets) nachtragen.
3. `rent_growth_5y` ergaenzen (Vorjahresvergleich Mietspiegel).

## Wie geladen wird

```
python3 scripts/load_location_data.py data/location_data.csv <db_path>
```

Schreibt in die `location`-Tabelle exakt nach Build-Plan-Schema (kreis_ags PK). PLACEHOLDER-Zellen
werden als NULL gespeichert, nie als erfundene Zahl.
