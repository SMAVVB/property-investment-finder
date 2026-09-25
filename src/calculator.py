"""
Property Investment Finder — Calculator (Phase 1)

Berechnet alle Investitionskennzahlen für eine Immobilie basierend auf
den Kriterien aus criteria.yaml und wendet Filter an.

Kein LLM-Call, kein Modell — reines Python.
"""

from __future__ import annotations

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
    is_erbpacht: bool = False
    is_vacation: bool = False
    property_type: str = "apartment"
    url: str = ""
    scraped_at: str = ""
    # Optional: direkt berechnete Werte vom Extractor
    rent_per_sqm: Optional[float] = None
    distance_to_station_minutes: Optional[float] = None
    travel_time_to_berlin_hours: Optional[float] = None
    region_label: Optional[str] = None


@dataclass
class CalculationResult:
    """Ergebnis der Berechnung für eine Immobilie."""
    listing_id: str
    purchase_costs_eur: float = 0.0
    total_acquisition: float = 0.0
    loan_amount: float = 0.0
    monthly_interest: float = 0.0
    monthly_amortization: float = 0.0
    total_monthly_mortgage: float = 0.0
    monthly_nk: float = 0.0
    total_monthly_cost: float = 0.0
    gross_yield: float = 0.0
    net_yield: float = 0.0
    monthly_surplus: float = 0.0
    monthly_top_up: float = 0.0
    equity_required: float = 0.0
    total_investment: float = 0.0
    living_space: float = 0.0
    distance_to_station_minutes: float = 999.0
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
    Berechle alle Kennzahlen für eine Immobilie.

    Berechnungen:
    - purchase_costs_eur: Kaufnebenkosten = price × rate(state)
    - total_acquisition: price + purchase_costs_eur
    - loan_amount: price (100% Finanzierung des Kaufpreises)
    - monthly_interest: loan_amount × interest_rate / 12
    - monthly_amortization: loan_amount × amortization_rate / 12
    - monthly_nk: living_space × rent_per_sqm_nk (aus criteria, default 3.0)
    - total_monthly_cost: monthly_interest + monthly_amortization + monthly_nk
    - gross_yield: (rent_monthly × 12) / price × 100
    - net_yield: ((rent_monthly × 12) - purchase_costs_eur) / price × 100
    - monthly_surplus: rent_monthly - total_monthly_cost
    - monthly_top_up: max(0, -monthly_surplus)
    - equity_required: purchase_costs_eur + renovation_budget
    - total_investment: total_acquisition + renovation_budget
    - score: gewichtete Bewertung (0-100)
    """
    result = CalculationResult(listing_id=listing.listing_id)

    # --- Kosten ---
    purchase_costs_rate = _get_purchase_costs_rate(criteria, listing.state)
    result.purchase_costs_eur = round(listing.price * purchase_costs_rate, 2)
    result.total_acquisition = round(listing.price + result.purchase_costs_eur, 2)

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

    # --- Nebenkosten ---
    nk_per_sqm = criteria.get("monthly_nk_per_sqm", 3.0)
    result.monthly_nk = round(listing.living_space * nk_per_sqm, 2)
    result.total_monthly_cost = round(
        result.total_monthly_mortgage + result.monthly_nk, 2
    )

    # --- Erträge ---
    annual_rent = listing.rent_monthly * 12
    result.gross_yield = round((annual_rent / listing.price) * 100, 2) if listing.price > 0 else 0.0
    # Netto-Yield: Brutto-Ertrag abzgl. Kaufnebenkosten (konservativ: 1-jährige Abschreibung)
    result.net_yield = round(((annual_rent - result.purchase_costs_eur) / listing.price) * 100, 2) if listing.price > 0 else 0.0

    # --- Cashflow ---
    result.monthly_surplus = round(listing.rent_monthly - result.total_monthly_cost, 2)
    result.monthly_top_up = round(max(0.0, -result.monthly_surplus), 2)

    # --- Eigenkapital ---
    renovation_budget = criteria.get("renovation", {}).get("budget", 10000)
    result.equity_required = round(result.purchase_costs_eur + renovation_budget, 2)
    result.total_investment = round(result.total_acquisition + renovation_budget, 2)

    # --- Score-Inputs ---
    result.living_space = listing.living_space
    result.distance_to_station_minutes = (
        listing.distance_to_station_minutes if listing.distance_to_station_minutes is not None else 999.0
    )

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


def _compute_score(result: CalculationResult, criteria: dict) -> float:
    """
    Berechne eine Gesamtwertung (0-100).

    Gewichtung:
    - Brutto-Yield:        30% (besser = höher)
    - Monatlicher Überschuss: 25% (weniger Top-up = besser)
    - Preis/m²:           15% (niedriger = besser)
    - Lage (ÖPNV):        15% (näher = besser)
    - Größe:              15% (Zielbereich = besser)
    """
    score = 0.0

    # 1. Brutto-Yield (0-30 Punkte)
    #    3.5% = 0 Punkte, 7%+ = 30 Punkte
    gy = result.gross_yield
    if gy >= 7.0:
        score += 30.0
    elif gy >= 3.5:
        score += (gy - 3.5) / (7.0 - 3.5) * 30.0
    # else: 0 Punkte

    # 2. Monthly Top-Up (0-25 Punkte)
    #    0€ = 25 Punkte, 500€ = 0 Punkte
    tu = result.monthly_top_up
    if tu <= 0:
        score += 25.0
    elif tu <= 500:
        score += (1.0 - tu / 500.0) * 25.0
    # else: 0 Punkte

    # 3. Preis/m² (0-15 Punkte)
    #    < 2000€/m² = 15 Punkte, > 5000€/m² = 0 Punkte
    price_per_sqm = result.total_acquisition / result.living_space if result.living_space > 0 else 9999
    if price_per_sqm <= 2000:
        score += 15.0
    elif price_per_sqm >= 5000:
        score += 0.0
    else:
        score += (1.0 - (price_per_sqm - 2000) / (5000 - 2000)) * 15.0

    # 4. Lage/ÖPNV (0-15 Punkte)
    #    < 5 Min = 15 Punkte, > 15 Min = 0 Punkte
    dist = result.distance_to_station_minutes
    if dist <= 5:
        score += 15.0
    elif dist >= 15:
        score += 0.0
    else:
        score += (1.0 - dist / 15.0) * 15.0

    # 5. Größe (0-15 Punkte)
    #    Zielbereich 35-50m² = 15 Punkte, außerhalb = weniger
    ls = result.living_space
    target_min = 35
    target_max = 50
    if target_min <= ls <= target_max:
        score += 15.0
    elif ls < target_min:
        score += max(0, (ls / target_min) * 15.0)
    else:
        score += max(0, (target_max / ls) * 15.0)

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

    # 3. Erbpacht
    if listing.is_erbpacht:
        reasons.append("Erbpacht ausgeschlossen")

    # 4. Ferienwohnung
    if listing.is_vacation:
        reasons.append("Ferienwohnung > Threshold ausgeschlossen")

    # 5. Städtische Limits
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

    # 6. Brutto-Yield
    y = criteria["yield"]["gross"]
    if result.gross_yield < y["min"] * 100:
        reasons.append(
            f"Brutto-Yield {result.gross_yield:.2f}% < {y['min']*100:.1f}% Minimum"
        )

    # 7. Monatlicher Top-Up
    mt = criteria["monthly_top_up"]
    if result.monthly_top_up > mt["max"]:
        reasons.append(
            f"Monatlicher Top-Up {result.monthly_top_up:.0f}€ > {mt['max']}€ Maximum"
        )

    # 8. Eigenkapital
    eq = criteria["equity"]
    if result.equity_required < eq["min"]:
        reasons.append(
            f"Erforderliches Eigenkapital {result.equity_required:.0f}€ < {eq['min']}€ Minimum"
        )
    if result.equity_required > eq["max"]:
        reasons.append(
            f"Erforderliches Eigenkapital {result.equity_required:.0f}€ > {eq['max']}€ Maximum"
        )

    # 9. Location: ÖPNV
    lmh = criteria.get("location_must_have", {})
    max_dist = lmh.get("max_distance_to_station_minutes", 999)
    if listing.distance_to_station_minutes is not None:
        if listing.distance_to_station_minutes > max_dist:
            reasons.append(
                f"Entfernung zur Bahn {listing.distance_to_station_minutes:.0f}min > "
                f"{max_dist}min Maximum"
            )

    # 10. Location: Reisezeit
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


def store_calculation(conn: sqlite3.Connection, listing: Listing, result: CalculationResult) -> None:
    """Speichere Berechnungsergebnis in der Datenbank."""
    conn.execute("""
        INSERT OR REPLACE INTO calculations (
            listing_id, purchase_costs_eur, total_acquisition, loan_amount,
            monthly_interest, monthly_amortization, total_monthly_mortgage,
            monthly_nk, total_monthly_cost, gross_yield, net_yield,
            monthly_surplus, monthly_top_up, equity_required,
            total_investment, score, passed_filter
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result.listing_id,
        result.purchase_costs_eur,
        result.total_acquisition,
        result.loan_amount,
        result.monthly_interest,
        result.monthly_amortization,
        result.total_monthly_mortgage,
        result.monthly_nk,
        result.total_monthly_cost,
        result.gross_yield,
        result.net_yield,
        result.monthly_surplus,
        result.monthly_top_up,
        result.equity_required,
        result.total_investment,
        result.score,
        1 if result.passed_filter else 0,
    ))

    # Speichere auch die Immobilie selbst
    conn.execute("""
        INSERT OR REPLACE INTO listings (
            listing_id, title, price, living_space, rent_monthly, rooms,
            floor, built_year, condition, location_city, location_state,
            location_address, latitude, longitude, is_erbpacht, is_vacation,
            property_type, url, scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        listing.property_type,
        listing.url,
        listing.scraped_at,
    ))

    # Speichere Location-Daten
    if listing.distance_to_station_minutes is not None:
        conn.execute("""
            INSERT OR REPLACE INTO locations (
                listing_id, city, state, latitude, longitude,
                distance_to_station_minutes, travel_time_to_berlin_hours,
                region_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.listing_id,
            listing.city,
            listing.state,
            listing.latitude,
            listing.longitude,
            listing.distance_to_station_minutes,
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
        f"  Kaufnebenkosten:  {result.purchase_costs_eur:>10.2f} €",
        f"  Gesamtakquisition:{result.total_acquisition:>10.2f} €",
        f"  Kreditbetrag:     {result.loan_amount:>10.2f} €",
        f"  Zins/Monat:       {result.monthly_interest:>10.2f} €",
        f"  Tilgung/Monat:    {result.monthly_amortization:>10.2f} €",
        f"  NK/Monat:         {result.monthly_nk:>10.2f} €",
        f"  Kosten/Monat:     {result.total_monthly_cost:>10.2f} €",
        f"  Brutto-Yield:     {result.gross_yield:>10.2f} %",
        f"  Netto-Yield:      {result.net_yield:>10.2f} %",
        f"  Überschuss/Monat: {result.monthly_surplus:>10.2f} €",
        f"  Top-Up/Monat:     {result.monthly_top_up:>10.2f} €",
        f"  Eigenkapital:     {result.equity_required:>10.2f} €",
        f"  Gesamtinvest:     {result.total_investment:>10.2f} €",
        f"  Score:            {result.score:>10.2f} / 100",
        f"  Filter:           {'BESTANDEN' if result.passed_filter else 'DURCHGEFALLEN'}",
    ]
    if not result.passed_filter:
        for reason in result.rejection_reasons:
            lines.append(f"    ❌ {reason}")
    return "\n".join(lines)
