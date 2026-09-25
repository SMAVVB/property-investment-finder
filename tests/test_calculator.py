"""
Property Investment Finder — Tests (Phase 1)

5 Hand-beispiele, die auf den Euro exakt matchen muessen.
Kein LLM-Call, reines Python.
"""

import os
import sys
import pytest
import sqlite3
import tempfile

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from calculator import (
    Listing,
    CalculationResult,
    calculate,
    load_criteria,
    calculate_batch,
    filter_passed,
    sort_by_score,
    init_db,
    store_calculation,
    store_criteria_in_db,
    format_result,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def criteria():
    """Lade Kriterien aus criteria.yaml."""
    criteria_path = os.path.join(os.path.dirname(__file__), "..", "criteria.yaml")
    return load_criteria(criteria_path)


# ---------------------------------------------------------------------------
# Erwartete Werte (Hand berechnet, auf den Euro genau)
# Renovation budget: 15000 (in criteria.yaml gesetzt)
# net_yield = ((annual_rent - purchase_costs) / price) * 100
# ---------------------------------------------------------------------------

EXPECTED = {
    "BER-001": {
        "purchase_costs_eur": 7200.0,
        "total_acquisition": 127200.0,
        "loan_amount": 120000.0,
        "monthly_interest": 480.0,
        "monthly_amortization": 200.0,
        "total_monthly_mortgage": 680.0,
        "monthly_nk": 120.0,
        "total_monthly_cost": 800.0,
        "gross_yield": 8.0,
        "net_yield": 2.0,
        "monthly_surplus": 0.0,
        "monthly_top_up": 0.0,
        "equity_required": 22200.0,
        "total_investment": 142200.0,
        "passed_filter": True,
    },
    "BRB-001": {
        "purchase_costs_eur": 5850.0,
        "total_acquisition": 95850.0,
        "loan_amount": 90000.0,
        "monthly_interest": 360.0,
        "monthly_amortization": 150.0,
        "total_monthly_mortgage": 510.0,
        "monthly_nk": 135.0,
        "total_monthly_cost": 645.0,
        "gross_yield": 7.33,
        "net_yield": 0.83,
        "monthly_surplus": -95.0,
        "monthly_top_up": 95.0,
        "equity_required": 20850.0,
        "total_investment": 110850.0,
        "passed_filter": True,
    },
    "LEP-001": {
        "purchase_costs_eur": 7020.0,
        "total_acquisition": 124020.0,
        "loan_amount": 117000.0,
        "monthly_interest": 468.0,
        "monthly_amortization": 195.0,
        "total_monthly_mortgage": 663.0,
        "monthly_nk": 135.0,
        "total_monthly_cost": 798.0,
        "gross_yield": 7.18,
        "net_yield": 1.18,
        "monthly_surplus": -98.0,
        "monthly_top_up": 98.0,
        "equity_required": 22020.0,
        "total_investment": 139020.0,
        "passed_filter": True,
    },
    "FFO-001": {
        "purchase_costs_eur": 5265.0,
        "total_acquisition": 86265.0,
        "loan_amount": 81000.0,
        "monthly_interest": 324.0,
        "monthly_amortization": 135.0,
        "total_monthly_mortgage": 459.0,
        "monthly_nk": 120.0,
        "total_monthly_cost": 579.0,
        "gross_yield": 6.67,
        "net_yield": 0.17,
        "monthly_surplus": -129.0,
        "monthly_top_up": 129.0,
        "equity_required": 20265.0,
        "total_investment": 101265.0,
        "passed_filter": True,
    },
    "CBU-001": {
        "purchase_costs_eur": 6435.0,
        "total_acquisition": 105435.0,
        "loan_amount": 99000.0,
        "monthly_interest": 396.0,
        "monthly_amortization": 165.0,
        "total_monthly_mortgage": 561.0,
        "monthly_nk": 135.0,
        "total_monthly_cost": 696.0,
        "gross_yield": 6.06,
        "net_yield": -0.44,
        "monthly_surplus": -196.0,
        "monthly_top_up": 196.0,
        "equity_required": 21435.0,
        "total_investment": 120435.0,
        "passed_filter": True,
    },
}


# ---------------------------------------------------------------------------
# Hilfsfunktion: erstelle Listing für Tests
# ---------------------------------------------------------------------------

def _make_listing(name, price, space, rent, city, state, **kwargs):
    return Listing(
        listing_id=name, price=price, living_space=space,
        rent_monthly=rent, city=city, state=state,
        condition="needs_work", property_type="apartment",
        distance_to_station_minutes=kwargs.get("dist", 10.0),
        travel_time_to_berlin_hours=kwargs.get("travel", 1.0),
        region_label=kwargs.get("region", "other"),
        **{k: v for k, v in kwargs.items() if k not in ("dist", "travel", "region")},
    )


# ---------------------------------------------------------------------------
# Tests: 5 Hand-Beispiele
# ---------------------------------------------------------------------------

class TestHandExamples:
    """Jedes der 5 Hand-Beispiele muss auf den Euro exakt matchen."""

    def test_berlin_neukoelln(self, criteria):
        l = _make_listing("BER-001", 120000.0, 40.0, 800.0, "Berlin", "Berlin",
                          dist=8.0, travel=0.5, region="berlin_outer")
        r = calculate(l, criteria)
        e = EXPECTED["BER-001"]
        for field in ["purchase_costs_eur", "total_acquisition", "loan_amount",
                      "monthly_interest", "monthly_amortization", "total_monthly_mortgage",
                      "monthly_nk", "total_monthly_cost", "monthly_surplus",
                      "monthly_top_up", "equity_required", "total_investment"]:
            assert getattr(r, field) == e[field], f"{field}: expected {e[field]}, got {getattr(r, field)}"
        for field in ["gross_yield", "net_yield"]:
            assert getattr(r, field) == pytest.approx(e[field], abs=0.01)
        assert r.passed_filter == e["passed_filter"]

    def test_brandenburg_potsdam(self, criteria):
        l = _make_listing("BRB-001", 90000.0, 45.0, 550.0, "Potsdam", "Brandenburg",
                          dist=10.0, travel=0.75, region="s_bahn_belt")
        r = calculate(l, criteria)
        e = EXPECTED["BRB-001"]
        for field in ["purchase_costs_eur", "total_acquisition", "loan_amount",
                      "monthly_interest", "monthly_amortization", "total_monthly_mortgage",
                      "monthly_nk", "total_monthly_cost", "monthly_surplus",
                      "monthly_top_up", "equity_required", "total_investment"]:
            assert getattr(r, field) == e[field], f"{field}: expected {e[field]}, got {getattr(r, field)}"
        for field in ["gross_yield", "net_yield"]:
            assert getattr(r, field) == pytest.approx(e[field], abs=0.01)
        assert r.passed_filter == e["passed_filter"]

    def test_leipzig(self, criteria):
        l = _make_listing("LEP-001", 117000.0, 45.0, 700.0, "Leipzig", "Sachsen",
                          dist=7.0, travel=1.25, region="brandenburg_town")
        r = calculate(l, criteria)
        e = EXPECTED["LEP-001"]
        for field in ["purchase_costs_eur", "total_acquisition", "loan_amount",
                      "monthly_interest", "monthly_amortization", "total_monthly_mortgage",
                      "monthly_nk", "total_monthly_cost", "monthly_surplus",
                      "monthly_top_up", "equity_required", "total_investment"]:
            assert getattr(r, field) == e[field], f"{field}: expected {e[field]}, got {getattr(r, field)}"
        for field in ["gross_yield", "net_yield"]:
            assert getattr(r, field) == pytest.approx(e[field], abs=0.01)
        assert r.passed_filter == e["passed_filter"]

    def test_frankfurt_oder(self, criteria):
        l = _make_listing("FFO-001", 81000.0, 40.0, 450.0, "Frankfurt (Oder)", "Brandenburg",
                          dist=10.0, travel=1.0, region="brandenburg_town")
        r = calculate(l, criteria)
        e = EXPECTED["FFO-001"]
        for field in ["purchase_costs_eur", "total_acquisition", "loan_amount",
                      "monthly_interest", "monthly_amortization", "total_monthly_mortgage",
                      "monthly_nk", "total_monthly_cost", "monthly_surplus",
                      "monthly_top_up", "equity_required", "total_investment"]:
            assert getattr(r, field) == e[field], f"{field}: expected {e[field]}, got {getattr(r, field)}"
        for field in ["gross_yield", "net_yield"]:
            assert getattr(r, field) == pytest.approx(e[field], abs=0.01)
        assert r.passed_filter == e["passed_filter"]

    def test_cottbus(self, criteria):
        l = _make_listing("CBU-001", 99000.0, 45.0, 500.0, "Cottbus", "Brandenburg",
                          dist=10.0, travel=1.5, region="brandenburg_town")
        r = calculate(l, criteria)
        e = EXPECTED["CBU-001"]
        for field in ["purchase_costs_eur", "total_acquisition", "loan_amount",
                      "monthly_interest", "monthly_amortization", "total_monthly_mortgage",
                      "monthly_nk", "total_monthly_cost", "monthly_surplus",
                      "monthly_top_up", "equity_required", "total_investment"]:
            assert getattr(r, field) == e[field], f"{field}: expected {e[field]}, got {getattr(r, field)}"
        for field in ["gross_yield", "net_yield"]:
            assert getattr(r, field) == pytest.approx(e[field], abs=0.01)
        assert r.passed_filter == e["passed_filter"]


# ---------------------------------------------------------------------------
# Tests: Filter-Funktionen
# ---------------------------------------------------------------------------

def test_filter_erbpacht(criteria):
    """Erbpacht muss ausschließen."""
    l = _make_listing("ERP-001", 100000.0, 40.0, 600.0, "Berlin", "Berlin", is_erbpacht=True)
    r = calculate(l, criteria)
    assert not r.passed_filter
    assert any("Erbpacht" in x for x in r.rejection_reasons)


def test_filter_vacation(criteria):
    """Ferienwohnung muss ausschließen."""
    l = _make_listing("VAC-001", 100000.0, 40.0, 600.0, "Berlin", "Berlin", is_vacation=True)
    r = calculate(l, criteria)
    assert not r.passed_filter
    assert any("Ferienwohnung" in x for x in r.rejection_reasons)


def test_filter_price_too_high(criteria):
    """Kaufpreis über Maximum muss ausschließen."""
    l = _make_listing("HIGH-001", 200000.0, 40.0, 1200.0, "Berlin", "Berlin")
    r = calculate(l, criteria)
    assert not r.passed_filter
    assert any("Kaufpreis" in x and "Maximum" in x for x in r.rejection_reasons)


def test_filter_price_too_low(criteria):
    """Kaufpreis unter Minimum muss ausschließen."""
    l = _make_listing("LOW-001", 50000.0, 30.0, 300.0, "Brandenburg", "Brandenburg")
    r = calculate(l, criteria)
    assert not r.passed_filter
    assert any("Kaufpreis" in x and "Minimum" in x for x in r.rejection_reasons)


def test_filter_yield_too_low(criteria):
    """Brutto-Yield unter Minimum muss ausschließen."""
    l = _make_listing("YLD-001", 150000.0, 50.0, 300.0, "Brandenburg", "Brandenburg")
    r = calculate(l, criteria)
    assert not r.passed_filter
    assert any("Brutto-Yield" in x for x in r.rejection_reasons)


def test_filter_top_up_too_high(criteria):
    """Monatlicher Top-Up über Maximum muss ausschließen."""
    l = _make_listing("TOP-001", 140000.0, 35.0, 350.0, "Berlin", "Berlin")
    r = calculate(l, criteria)
    assert not r.passed_filter
    assert any("Top-Up" in x for x in r.rejection_reasons)


def test_filter_equity_too_low(criteria):
    """Eigenkapital unter Minimum muss ausschließen."""
    l = _make_listing("EQ-001", 60000.0, 30.0, 500.0, "Brandenburg", "Brandenburg")
    r = calculate(l, criteria)
    assert not r.passed_filter
    assert any("Eigenkapital" in x for x in r.rejection_reasons)


def test_city_specific_filter_cottbus(criteria):
    """Cottbus: Wohnfläche > 45m² oder Preis > 99000€ muss ausschließen."""
    l = _make_listing("CBU-LG", 90000.0, 50.0, 500.0, "Cottbus", "Brandenburg")
    r = calculate(l, criteria)
    assert not r.passed_filter
    assert any("Cottbus" in x and "Wohnfläche" in x for x in r.rejection_reasons)

    l = _make_listing("CBU-HT", 120000.0, 40.0, 600.0, "Cottbus", "Brandenburg")
    r = calculate(l, criteria)
    assert not r.passed_filter
    assert any("Cottbus" in x and "Kaufpreis" in x for x in r.rejection_reasons)


# ---------------------------------------------------------------------------
# Tests: Batch-Verarbeitung
# ---------------------------------------------------------------------------

def test_batch_all_pass(criteria):
    """Alle 5 Beispiele sollten durchkommen."""
    listings = [
        _make_listing("BER-001", 120000.0, 40.0, 800.0, "Berlin", "Berlin", dist=8.0, travel=0.5),
        _make_listing("BRB-001", 90000.0, 45.0, 550.0, "Potsdam", "Brandenburg", dist=10.0, travel=0.75),
        _make_listing("LEP-001", 117000.0, 45.0, 700.0, "Leipzig", "Sachsen", dist=7.0, travel=1.25),
        _make_listing("FFO-001", 81000.0, 40.0, 450.0, "Frankfurt (Oder)", "Brandenburg", dist=10.0, travel=1.0),
        _make_listing("CBU-001", 99000.0, 45.0, 500.0, "Cottbus", "Brandenburg", dist=10.0, travel=1.5),
    ]
    results = calculate_batch(listings, criteria)
    passed = filter_passed(results)
    assert len(passed) == 5


def test_batch_sorted_by_score(criteria):
    """Ergebnisse sollten nach Score sortiert sein (höchster zuerst)."""
    listings = [
        _make_listing("BER-001", 120000.0, 40.0, 800.0, "Berlin", "Berlin"),
        _make_listing("BRB-001", 90000.0, 45.0, 550.0, "Potsdam", "Brandenburg"),
        _make_listing("LEP-001", 117000.0, 45.0, 700.0, "Leipzig", "Sachsen"),
        _make_listing("FFO-001", 81000.0, 40.0, 450.0, "Frankfurt (Oder)", "Brandenburg"),
        _make_listing("CBU-001", 99000.0, 45.0, 500.0, "Cottbus", "Brandenburg"),
    ]
    results = calculate_batch(listings, criteria)
    sorted_results = sort_by_score(results)
    for i in range(len(sorted_results) - 1):
        assert sorted_results[i].score >= sorted_results[i + 1].score


# ---------------------------------------------------------------------------
# Tests: Datenbank
# ---------------------------------------------------------------------------

def test_db_init_and_store(criteria):
    """Datenbank erstellen, Berechnung speichern, lesen."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")

        conn = init_db(db_path, schema_path)
        store_criteria_in_db(conn, criteria)

        l = _make_listing("BER-001", 120000.0, 40.0, 800.0, "Berlin", "Berlin")
        r = calculate(l, criteria)
        store_calculation(conn, l, r)
        conn.commit()

        row = conn.execute(
            "SELECT purchase_costs_eur, gross_yield, passed_filter FROM calculations WHERE listing_id = ?",
            ("BER-001",),
        ).fetchone()
        assert row is not None
        assert row[0] == 7200.0
        assert abs(row[1] - 8.0) < 0.01
        assert row[2] == 1

        rows = conn.execute("SELECT key, value FROM criteria").fetchall()
        assert len(rows) > 0
        conn.close()


def test_db_five_tables_exist(criteria):
    """Alle 5 Tabellen sollten existieren."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")

        conn = init_db(db_path, schema_path)

        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t[0] for t in tables]

        assert "listings" in table_names
        assert "criteria" in table_names
        assert "calculations" in table_names
        assert "locations" in table_names
        assert "rankings" in table_names
        conn.close()


# ---------------------------------------------------------------------------
# Tests: Format
# ---------------------------------------------------------------------------

def test_format_result(criteria):
    """format_result sollte lesbaren Text zurueckgeben."""
    l = _make_listing("BER-001", 120000.0, 40.0, 800.0, "Berlin", "Berlin")
    r = calculate(l, criteria)
    text = format_result(r)
    assert "Listing: BER-001" in text
    assert "BESTANDEN" in text
    assert "€" in text


# ---------------------------------------------------------------------------
# Tests: Kriterien-Lader
# ---------------------------------------------------------------------------

def test_load_criteria_has_all_keys():
    """criteria.yaml sollte alle erwarteten Keys haben."""
    criteria_path = os.path.join(os.path.dirname(__file__), "..", "criteria.yaml")
    c = load_criteria(criteria_path)

    assert "purchase_price" in c
    assert "living_space" in c
    assert "equity" in c
    assert "financing" in c
    assert "loan" in c
    assert "purchase_costs" in c
    assert "renovation" in c
    assert "location" in c
    assert "target_regions" in c
    assert "location_must_have" in c
    assert "yield" in c
    assert "monthly_top_up" in c
    assert "exclusions" in c
