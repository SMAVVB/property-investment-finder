"""
Property Investment Finder — Calculator (Phase 1)

Berechnet alle Investitionskennzahlen für eine Immobilie basierend auf
den Kriterien aus criteria.yaml und wendet Filter an.

Formeln nach Build-Plan:
- gross_yield = R_year / P * 100
- net_yield = (R_year * (1 - v) - 12 * H_non_alloc - M) / K
  wobei: R_year = Jahreskaltmiete, v = Leerstandsquote,
         H_non_alloc = nicht umlagefähiges Hausgeld,
         M = jährliche Kreditkosten, K = All-in-Kosten
- kaufpreisfaktor = P / R_year
- outlier_tier: ≤14 = phenomenal, 15-18 = very_good, 19-22 = acceptable, >22 = market
- stress_test: +2pp Zins, 6 Monate Leerstand

Kein LLM-Call, kein Modell — reines Python.
"""

from __future__ import annotations

import json
import sqlite3
import os
from dataclasses import dataclass, field
from typing import Optional

import yaml


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Listing:
    """Eine Immobilie, wie sie vom Extractor geliefert wird."""
    listing_id: str
    price: float              # Kaufpreis in Euro
    living_space: float       # Wohnfläche in m²
    rent_monthly: float = 0.0 # Monatliche Kaltmiete
    rooms: int = 0
    floor: int = 0
    built_year: int = 0
    condition: str = "unknown"
    city: str = ""
    state: str = ""           # Bundesland (ISO-Code oder Name)
    address: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Ausschlüsse als boolesche Flags (Kategorie, kein Preis-Schwellenwert)
    is_erbpacht: bool = False
    is_vacation: bool = False
    is_auction: bool = False          # Zwangsversteigerung
    is_care_apartment: bool = False   # Betreutes Wohnen
    is_social_binding: bool = False   # Sozialbindung
    property_type: str = "apartment"
    url: str = ""
    scraped_at: str = ""
    # Optional: direkt berechnete Werte vom Extractor
    rent_per_sqm: Optional[float] = None
    distance_to_station_minutes: Optional[float] = None
    travel_time_to_berlin_hours: Optional[float] = None
    region_label: Optional[str] = None
    # Hausgeld-Parameter für Build-Plan-Formel
    monthly_housing_total: float = 0.0       # Gesamtes monatliches Hausgeld
    monthly_housing_non_allocable: float = 0.0  # Nicht umlagefähiger Anteil
    vacancy_rate: float = 0.05               # Leerstandsquote (default 5%)
    # Location
    kreis_ags: Optional[str] = None          # Kreis-AGS für Phase-3-Verknüpfung


@dataclass
class CalculationResult:
    """Ergebnis der Berechnung für eine Immobilie."""
    listing_id: str
    # Kosten
    purchase_costs_eur: float = 0.0
    all_in_costs: float = 0.0               # K = price + purchase_costs + renovation
    renovation_budget: float = 0.0
    # Finanzierung
    loan_amount: float = 0.0
    monthly_interest: float = 0.0
    monthly_amortization: float = 0.0
    total_monthly_mortgage: float = 0.0
    annual_loan_costs: float = 0.0          # M = (interest + amortization) * 12
    # Hausgeld
    monthly_nk: float = 0.0                 # Gesamtes Hausgeld
    monthly_nk_non_alloc: float = 0.0       # Nicht umlagefähiger Anteil
    # Erträge
    annual_rent: float = 0.0                # R_year = rent_monthly * 12
    gross_yield: float = 0.0                # R_year / price * 100
    net_yield: float = 0.0                  # Build-Plan-Formel
    # Kaufpreisfaktor
    kaufpreisfaktor: float = 0.0            # P / R_year
    outlier_tier: str = "unknown"           # phenomenal, very_good, acceptable, market
    # Cashflow
    monthly_surplus: float = 0.0
    monthly_top_up: float = 0.0
    equity_required: float = 0.0
    total_investment: float = 0.0
    # Stress-Test
    stress_test_passed: bool = True
    stress_monthly_surplus: float = 0.0
    stress_6month_loss: float = 0.0
    # Bewertung
    score: float = 0.0
    passed_filter: bool = False
    rejection_reasons: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Criteria loader
# ---------------------------------------------------------------------------

def load_criteria(path: Optional[str] = None) -> dict:
    """Lade Kriterien aus criteria.yaml."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "criteria.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Core calculator
# ---------------------------------------------------------------------------

def calculate(listing: Listing, criteria: dict) -> CalculationResult:
    """
    Berechne alle Kennzahlen für eine Immobilie nach Build-Plan-Formeln.

    Siehe Docstring auf Modulebene für die Formeln.
    """
    result = CalculationResult(listing_id=listing.listing_id)

    # --- Kosten ---
    purchase_costs_rate = _get_purchase_costs_rate(criteria, listing.state)
    result.purchase_costs_eur = round(listing.price * purchase_costs_rate, 2)

    renovation_budget = criteria.get("renovation", {}).get("budget", 15000)
    result.renovation_budget = renovation_budget
    result.all_in_costs = round(listing.price + result.purchase_costs_eur + renovation_budget, 2)

    # --- Finanzierung ---
    ltv = criteria["financing"]["loan_to_value"]
    result.loan_amount = round(listing.price * ltv, 2)

    interest_rate = criteria["loan"]["interest_rate"]
    amortization_rate = criteria["loan"]["amortization_rate"]

    result.monthly_interest = round(result.loan_amount * interest_rate / 12, 2)
    result.monthly_amortization = round(result.loan_amount * amortization_rate / 12, 2)
    result.total_monthly_mortgage = round(
        result.monthly_interest + result.monthly_amortization, 2
    )
    # M = jährliche Kreditkosten
    result.annual_loan_costs = round(
        (result.monthly_interest + result.monthly_amortization) * 12, 2
    )

    # --- Hausgeld ---
    # Wenn nicht vom Extractor gesetzt: Schätzung über Wohnfläche
    if listing.monthly_housing_total > 0:
        result.monthly_nk = listing.monthly_housing_total
    else:
        nk_per_sqm = criteria.get("monthly_nk_per_sqm", 3.0)
        result.monthly_nk = round(listing.living_space * nk_per_sqm, 2)

    if listing.monthly_housing_non_allocable > 0:
        result.monthly_nk_non_alloc = listing.monthly_housing_non_allocable
    else:
        # Default: 2% des Gesamthaushalts sind nicht umlagefähig
        non_alloc_pct = criteria.get("non_allocable_pct", 0.02)
        result.monthly_nk_non_alloc = round(result.monthly_nk * non_alloc_pct, 2)

    # --- Erträge (Build-Plan-Formeln) ---
    result.annual_rent = round(listing.rent_monthly * 12, 2)

    # Brutto-Yield
    result.gross_yield = round((result.annual_rent / listing.price) * 100, 2) if listing.price > 0 else 0.0

    # Netto-Yield nach Build-Plan:
    # y_net = (R_year * (1 - v) - 12 * H_non_alloc - M) / K
    vacancy_rate = listing.vacancy_rate if listing.vacancy_rate > 0 else 0.05
    net_yield_num = (
        result.annual_rent * (1 - vacancy_rate)
        - result.monthly_nk_non_alloc * 12
        - result.annual_loan_costs
    )
    result.net_yield = round((net_yield_num / result.all_in_costs) * 100, 2) if result.all_in_costs > 0 else 0.0

    # --- Kaufpreisfaktor ---
    # k = P / R_year
    result.kaufpreisfaktor = round(listing.price / result.annual_rent, 2) if result.annual_rent > 0 else 0.0

    # --- Outlier-Tier-Klassifikation ---
    result.outlier_tier = _classify_outlier_tier(result.kaufpreisfaktor)

    # --- Cashflow ---
    total_monthly_cost = result.total_monthly_mortgage + result.monthly_nk
    result.monthly_surplus = round(listing.rent_monthly - total_monthly_cost, 2)
    result.monthly_top_up = round(max(0.0, -result.monthly_surplus), 2)

    # --- Eigenkapital ---
    result.equity_required = round(result.purchase_costs_eur + renovation_budget, 2)
    result.total_investment = round(result.all_in_costs + renovation_budget, 2)

    # --- Stress-Test ---
    _run_stress_test(result, listing, criteria)

    # --- Score ---
    result.score = _compute_score(result, criteria)

    # --- Filter ---
    _apply_filters(listing, result, criteria)

    return result


def _get_purchase_costs_rate(criteria: dict, state: str) -> float:
    """Ermittle Kaufnebenkosten-Rate für ein Bundesland."""
    pc = criteria.get("purchase_costs", {})
    state_lower = state.lower().strip()

    if "berlin" in state_lower:
        return pc.get("berlin", 0.06)
    elif "brandenburg" in state_lower:
        return pc.get("brandenburg", 0.065)
    elif "sachsen" in state_lower and "anhalt" in state_lower:
        return pc.get("saxony_anhalt", 0.065)
    elif "sachsen" in state_lower:
        return pc.get("saxony", 0.06)
    else:
        return pc.get("other", 0.06)


def _classify_outlier_tier(kaufpreisfaktor: float) -> str:
    """
    Outlier-Tier-Klassifikation nach Build-Plan.

    Basierend auf Kaufpreisfaktor k = P / R_year:
    - Phenomenal:     k ≤ 14
    - Very good:      15 ≤ k ≤ 18
    - Acceptable:     19 ≤ k ≤ 22
    - Market:         k > 22
    """
    if kaufpreisfaktor <= 14:
        return "phenomenal"
    elif kaufpreisfaktor <= 18:
        return "very_good"
    elif kaufpreisfaktor <= 22:
        return "acceptable"
    else:
        return "market"


def _run_stress_test(result: CalculationResult, listing: Listing, criteria: dict) -> None:
    """
    Stress-Test: +2 Prozentpunkte Zins, 6 Monate Leerstand.

    Prüft, ob der Cashflow auch unter verschärften Bedingungen positiv bleibt.
    """
    stress_interest_rate = criteria["loan"]["interest_rate"] + 0.02  # +2pp
    stress_loan_amount = result.loan_amount

    # Monatliche Belastung mit erhöhtem Zins
    amortization_rate = criteria["loan"]["amortization_rate"]
    stress_monthly_interest = round(stress_loan_amount * stress_interest_rate / 12, 2)
    stress_monthly_amortization = round(stress_loan_amount * amortization_rate / 12, 2)
    stress_monthly_mortgage = round(stress_monthly_interest + stress_monthly_amortization, 2)
    stress_total_monthly_cost = round(stress_monthly_mortgage + result.monthly_nk, 2)

    # 6 Monate Leerstand: nur 6 Monate Mieteinnahmen
    stress_6month_rent = listing.rent_monthly * 6
    stress_6month_costs = stress_total_monthly_cost * 6
    stress_6month_loss = round(stress_6month_costs - stress_6month_rent, 2)

    # Monatlicher Überschuss unter Stress (nach 6 Monaten Leerstand)
    stress_monthly_surplus = round(listing.rent_monthly - stress_total_monthly_cost, 2)

    result.stress_test_passed = stress_6month_loss <= 0
    result.stress_monthly_surplus = stress_monthly_surplus
    result.stress_6month_loss = stress_6month_loss


def _compute_score(result: CalculationResult, criteria: dict) -> float:
    """
    Berechne eine Gesamtwertung (0-100).

    Gewichtung:
    - Brutto-Yield:        25% (besser = höher)
    - Netto-Yield:        20% (besser = höher)
    - Kaufpreisfaktor:    20% (niedriger = besser)
    - Stress-Test:        15% (kein Verlust = besser)
    - Top-Up:             10% (weniger = besser)
    - Lage (ÖPNV):        10% (näher = besser)
    """
    score = 0.0

    # 1. Brutto-Yield (0-25 Punkte)
    gy = result.gross_yield
    if gy >= 7.0:
        score += 25.0
    elif gy >= 3.5:
        score += (gy - 3.5) / (7.0 - 3.5) * 25.0

    # 2. Netto-Yield (0-20 Punkte)
    ny = result.net_yield
    if ny >= 3.0:
        score += 20.0
    elif ny >= 0.0:
        score += ny / 3.0 * 20.0
    else:
        score += max(0, ny / 3.0 * 10.0)  # Strafe für negatives Yield

    # 3. Kaufpreisfaktor (0-20 Punkte)
    #    ≤14 = 20 Punkte, >22 = 0 Punkte
    kpf = result.kaufpreisfaktor
    if kpf <= 14:
        score += 20.0
    elif kpf >= 22:
        score += 0.0
    else:
        score += (1.0 - (kpf - 14) / (22 - 14)) * 20.0

    # 4. Stress-Test (0-15 Punkte)
    #    Kein Verlust = 15 Punkte, >5000€ Verlust = 0 Punkte
    loss = abs(result.stress_6month_loss)
    if result.stress_test_passed:
        score += 15.0
    elif loss <= 1000:
        score += 10.0
    elif loss <= 3000:
        score += 5.0
    # else: 0 Punkte

    # 5. Top-Up (0-10 Punkte)
    tu = result.monthly_top_up
    if tu <= 0:
        score += 10.0
    elif tu <= 500:
        score += (1.0 - tu / 500.0) * 10.0

    # 6. Lage/ÖPNV (0-10 Punkte)
    dist = result.distance_to_station_minutes if hasattr(result, 'distance_to_station_minutes') else 999
    if dist <= 5:
        score += 10.0
    elif dist >= 15:
        score += 0.0
    else:
        score += (1.0 - dist / 15.0) * 10.0

    return round(min(100.0, score), 2)


def _apply_filters(listing: Listing, result: CalculationResult, criteria: dict) -> None:
    """Wende alle Filter an. Setze passed_filter und rejection_reasons."""
    reasons = []

    # 1. Kaufpreis
    pp = criteria["purchase_price"]
    if listing.price < pp["min"]:
        reasons.append(f"Kaufpreis {listing.price:.0f}€ < {pp['min']}€ Minimum")
    if listing.price > pp["max"]:
        reasons.append(f"Kaufpreis {listing.price:.0f}€ > {pp['max']}€ Maximum")

    # 2. Wohnfläche
    ls = criteria["living_space"]
    if listing.living_space < ls["allowed_min"]:
        reasons.append(f"Wohnfläche {listing.living_space:.1f}m² < {ls['allowed_min']}m² Minimum")
    if listing.living_space > ls["allowed_max"]:
        reasons.append(f"Wohnfläche {listing.living_space:.1f}m² > {ls['allowed_max']}m² Maximum")

    # 3. Ausschlüsse (boolesche Flags, keine Preis-Schwellenwerte)
    if listing.is_erbpacht:
        reasons.append("Erbpacht (Erbbaurecht) ausgeschlossen")
    if listing.is_vacation:
        reasons.append("Ferienwohnung ausgeschlossen")
    if listing.is_auction:
        reasons.append("Zwangsversteigerung ausgeschlossen")
    if listing.is_care_apartment:
        reasons.append("Betreutes Wohnen ausgeschlossen")
    if listing.is_social_binding:
        reasons.append("Sozialbindung ausgeschlossen")

    # 4. Städtische Limits
    cs = criteria.get("exclusions", {}).get("city_specific", {})
    city_lower = listing.city.lower().strip()
    for city_key, city_limits in cs.items():
        if city_key in city_lower:
            if listing.living_space > city_limits["max_living_space"]:
                reasons.append(
                    f"{listing.city}: Wohnfläche {listing.living_space:.0f}m² > "
                    f"{city_limits['max_living_space']}m² Limit"
                )
            if listing.price > city_limits["max_price"]:
                reasons.append(
                    f"{listing.city}: Kaufpreis {listing.price:.0f}€ > "
                    f"{city_limits['max_price']}€ Limit"
                )

    # 5. Brutto-Yield
    y = criteria["yield"]["gross"]
    if result.gross_yield < y["min"] * 100:
        reasons.append(
            f"Brutto-Yield {result.gross_yield:.2f}% < {y['min']*100:.1f}% Minimum"
        )

    # 6. Monatlicher Top-Up
    mt = criteria["monthly_top_up"]
    if result.monthly_top_up > mt["max"]:
        reasons.append(
            f"Monatlicher Top-Up {result.monthly_top_up:.0f}€ > {mt['max']}€ Maximum"
        )

    # 7. Eigenkapital
    eq = criteria["equity"]
    if result.equity_required < eq["min"]:
        reasons.append(
            f"Erforderliches Eigenkapital {result.equity_required:.0f}€ < {eq['min']}€ Minimum"
        )
    if result.equity_required > eq["max"]:
        reasons.append(
            f"Erforderliches Eigenkapital {result.equity_required:.0f}€ > {eq['max']}€ Maximum"
        )

    # 8. Location: ÖPNV
    lmh = criteria.get("location_must_have", {})
    max_dist = lmh.get("max_distance_to_station_minutes", 999)
    if listing.distance_to_station_minutes is not None:
        if listing.distance_to_station_minutes > max_dist:
            reasons.append(
                f"Entfernung zur Bahn {listing.distance_to_station_minutes:.0f}min > "
                f"{max_dist}min Maximum"
            )

    # 9. Location: Reisezeit
    max_travel = criteria.get("location", {}).get("max_travel_time_hours", 999)
    if listing.travel_time_to_berlin_hours is not None:
        if listing.travel_time_to_berlin_hours > max_travel:
            reasons.append(
                f"Reisezeit nach Berlin {listing.travel_time_to_berlin_hours:.1f}h > "
                f"{max_travel}h Maximum"
            )

    result.passed_filter = len(reasons) == 0
    result.rejection_reasons = reasons


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def init_db(db_path: str, schema_path: Optional[str] = None) -> sqlite3.Connection:
    """Initialisiere die SQLite-Datenbank mit dem Schema."""
    if schema_path is None:
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    conn = sqlite3.connect(db_path)
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    return conn


def store_result(conn: sqlite3.Connection, listing: Listing, result: CalculationResult) -> None:
    """Speichere Berechnungsergebnis in der Datenbank (Build-Plan-Schema)."""
    # listing
    conn.execute("""
        INSERT OR REPLACE INTO listing (
            listing_id, title, price, living_space, rent_monthly, rooms,
            floor, built_year, condition, location_city, location_state,
            location_address, latitude, longitude,
            is_erbpacht, is_vacation, is_auction, is_care_apartment, is_social_binding,
            property_type, url, scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result.listing_id,
        "",  # title
        listing.price,
        listing.living_space,
        listing.rent_monthly,
        listing.rooms,
        listing.floor,
        listing.built_year,
        listing.condition,
        listing.city,
        listing.state,
        listing.address,
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
    ))

    # financials
    conn.execute("""
        INSERT OR REPLACE INTO financials (
            listing_id, purchase_costs_eur, all_in_costs, annual_rent,
            gross_yield, net_yield, kaufpreisfaktor,
            loan_amount, monthly_interest, monthly_amortization,
            total_monthly_mortgage, monthly_nk, monthly_nk_non_alloc,
            annual_loan_costs, monthly_surplus, monthly_top_up,
            equity_required, renovation_budget
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result.listing_id,
        result.purchase_costs_eur,
        result.all_in_costs,
        result.annual_rent,
        result.gross_yield,
        result.net_yield,
        result.kaufpreisfaktor,
        result.loan_amount,
        result.monthly_interest,
        result.monthly_amortization,
        result.total_monthly_mortgage,
        result.monthly_nk,
        result.monthly_nk_non_alloc,
        result.annual_loan_costs,
        result.monthly_surplus,
        result.monthly_top_up,
        result.equity_required,
        result.renovation_budget,
    ))

    # judgments
    conn.execute("""
        INSERT OR REPLACE INTO judgments (
            listing_id, passed_filter, outlier_tier,
            stress_test_passed, stress_monthly_surplus, stress_6month_loss,
            rejection_reasons, score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result.listing_id,
        1 if result.passed_filter else 0,
        result.outlier_tier,
        1 if result.stress_test_passed else 0,
        result.stress_monthly_surplus,
        result.stress_6month_loss,
        json.dumps(result.rejection_reasons),
        result.score,
    ))

    # location
    if listing.distance_to_station_minutes is not None:
        conn.execute("""
            INSERT OR REPLACE INTO location (
                listing_id, city, state, kreis_ags, latitude, longitude,
                distance_to_station_minutes, station_name, transport_types,
                travel_time_to_berlin_hours, region_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.listing_id,
            listing.city,
            listing.state,
            listing.kreis_ags,
            listing.latitude,
            listing.longitude,
            listing.distance_to_station_minutes,
            None,  # station_name
            None,  # transport_types
            listing.travel_time_to_berlin_hours,
            listing.region_label,
        ))


def store_criteria_in_db(conn: sqlite3.Connection, criteria: dict) -> None:
    """Speichere Kriterien als Key-Value-Paare in der Datenbank."""
    def _store(d: dict, prefix: str = ""):
        for k, v in d.items():
            key = f"{prefix}{k}" if prefix else k
            if isinstance(v, dict):
                _store(v, f"{key}_")
            else:
                conn.execute("""
                    INSERT OR REPLACE INTO criteria (key, value, category)
                    VALUES (?, ?, ?)
                """, (key, str(v), "investment"))

    _store(criteria)


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

def calculate_batch(listings: list[Listing], criteria: dict) -> list[CalculationResult]:
    """Berechne Kennzahlen für eine Liste von Immobilien."""
    results = []
    for listing in listings:
        result = calculate(listing, criteria)
        results.append(result)
    return results


def filter_passed(results: list[CalculationResult]) -> list[CalculationResult]:
    """Filtere nur die Ergebnisse, die alle Bestanden haben."""
    return [r for r in results if r.passed_filter]


def sort_by_score(results: list[CalculationResult]) -> list[CalculationResult]:
    """Sortiere Ergebnisse nach Score (höchster zuerst)."""
    return sorted(results, key=lambda r: r.score, reverse=True)


# ---------------------------------------------------------------------------
# Pretty-print
# ---------------------------------------------------------------------------

def format_result(result: CalculationResult) -> str:
    """Formatiere ein Berechnungsergebnis als lesbaren Text."""
    lines = [
        f"Listing: {result.listing_id}",
        f"  Kaufnebenkosten:    {result.purchase_costs_eur:>10.2f} €",
        f"  All-in-Kosten:      {result.all_in_costs:>10.2f} €",
        f"  Jahreskaltmiete:    {result.annual_rent:>10.2f} €",
        f"  Brutto-Yield:       {result.gross_yield:>10.2f} %",
        f"  Netto-Yield:        {result.net_yield:>10.2f} %",
        f"  Kaufpreisfaktor:    {result.kaufpreisfaktor:>10.2f}",
        f"  Outlier-Tier:       {result.outlier_tier:>10s}",
        f"  Kreditbetrag:       {result.loan_amount:>10.2f} €",
        f"  Zins/Monat:         {result.monthly_interest:>10.2f} €",
        f"  Tilgung/Monat:      {result.monthly_amortization:>10.2f} €",
        f"  NK/Monat:           {result.monthly_nk:>10.2f} €",
        f"  NK/nicht uml.:      {result.monthly_nk_non_alloc:>10.2f} €",
        f"  Kreditkosten/Jahr:  {result.annual_loan_costs:>10.2f} €",
        f"  Überschuss/Monat:   {result.monthly_surplus:>10.2f} €",
        f"  Top-Up/Monat:       {result.monthly_top_up:>10.2f} €",
        f"  Stress-Test:        {'BESTANDEN' if result.stress_test_passed else 'DURCHGEFALLEN'}",
        f"  Stress-Verlust(6m): {result.stress_6month_loss:>10.2f} €",
        f"  Score:              {result.score:>10.2f} / 100",
        f"  Filter:             {'BESTANDEN' if result.passed_filter else 'DURCHGEFALLEN'}",
    ]
    if not result.passed_filter:
        for reason in result.rejection_reasons:
            lines.append(f"    ✗ {reason}")
    return "\n".join(lines)
