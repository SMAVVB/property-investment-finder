import os
import sqlite3
import sys
import tempfile

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
SCHEMA_PATH = os.path.join(REPO_ROOT, "schema.sql")

sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from autotune import get_state, should_stop, rank_scouted_cities, NON_IMPROVING_STOP_AFTER


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(open(SCHEMA_PATH, encoding="utf-8").read())
    conn.commit()
    return conn, path


def test_should_stop_true_at_threshold():
    assert should_stop(NON_IMPROVING_STOP_AFTER) is True
    assert should_stop(NON_IMPROVING_STOP_AFTER - 1) is False


def test_get_state_no_runs_yet():
    conn, path = _fresh_db()
    state = get_state(conn)
    assert state == {"best_score": 0.0, "non_improving_streak": 0}
    conn.close()
    os.unlink(path)


def test_get_state_tracks_best_promoted_score_and_streak():
    conn, path = _fresh_db()
    conn.execute(
        "INSERT INTO tuning_runs (cycle_at, preset_json, shortlist_size, mean_score, promoted, source) "
        "VALUES ('t1', '{}', 30, 40.0, 1, 'autotune')"
    )
    conn.execute(
        "INSERT INTO tuning_runs (cycle_at, preset_json, shortlist_size, mean_score, promoted, source) "
        "VALUES ('t2', '{}', 30, 38.0, 0, 'autotune')"
    )
    conn.execute(
        "INSERT INTO tuning_runs (cycle_at, preset_json, shortlist_size, mean_score, promoted, source) "
        "VALUES ('t3', '{}', 30, 39.0, 0, 'autotune')"
    )
    conn.commit()
    state = get_state(conn)
    assert state["best_score"] == 40.0
    assert state["non_improving_streak"] == 2
    conn.close()
    os.unlink(path)


def test_rank_scouted_cities_orders_by_kaufpreisfaktor_ascending():
    conn, path = _fresh_db()
    conn.execute(
        "INSERT INTO region_scouting (city, kreis_ags, scouted_at, n_sale_hits, "
        "median_price_per_sqm, median_rent_per_sqm, est_kaufpreisfaktor, status) "
        "VALUES ('Cheap City', 'x/y', 't', 10, 2000, 15, 11.1, 'ok')"
    )
    conn.execute(
        "INSERT INTO region_scouting (city, kreis_ags, scouted_at, n_sale_hits, "
        "median_price_per_sqm, median_rent_per_sqm, est_kaufpreisfaktor, status) "
        "VALUES ('Expensive City', 'a/b', 't', 10, 3000, 8, 31.25, 'ok')"
    )
    conn.execute(
        "INSERT INTO region_scouting (city, kreis_ags, scouted_at, n_sale_hits, "
        "median_price_per_sqm, median_rent_per_sqm, est_kaufpreisfaktor, status) "
        "VALUES ('Failed City', 'c/d', 't', 0, NULL, NULL, NULL, 'failed')"
    )
    conn.commit()
    top = rank_scouted_cities(conn, top_k=5)
    assert [r["city"] for r in top] == ["Cheap City", "Expensive City"]
    conn.close()
    os.unlink(path)
