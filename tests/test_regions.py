import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from regions import load_regions, save_regions, get_active_tracks, load_candidate_batch, mark_scouted

FIXTURE = {
    "active": [
        {"bl_slug": "sachsen", "city_slug": "leipzig", "display_city": "Leipzig", "display_bundesland": "Sachsen"},
    ],
    "candidates": [
        {"bl_slug": "sachsen", "city_slug": "dresden", "display_city": "Dresden", "display_bundesland": "Sachsen"},
        {"bl_slug": "sachsen", "city_slug": "chemnitz", "display_city": "Chemnitz", "display_bundesland": "Sachsen"},
    ],
    "scouted": [],
}


def _write_fixture(tmp_path):
    save_regions(FIXTURE, tmp_path)


def test_get_active_tracks_shape():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        path = f.name
    _write_fixture(path)
    tracks = get_active_tracks(path)
    assert tracks == [("sachsen", "leipzig", "Leipzig", "Sachsen")]
    os.unlink(path)


def test_load_candidate_batch_respects_batch_size():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        path = f.name
    _write_fixture(path)
    batch = load_candidate_batch(batch_size=1, path=path)
    assert batch == [("sachsen", "dresden", "Dresden", "Sachsen")]
    os.unlink(path)


def test_mark_scouted_excludes_from_next_batch():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        path = f.name
    _write_fixture(path)
    mark_scouted([("sachsen", "dresden", "Dresden", "Sachsen")], path=path)
    remaining = load_candidate_batch(batch_size=10, path=path)
    assert remaining == [("sachsen", "chemnitz", "Chemnitz", "Sachsen")]
    os.unlink(path)
