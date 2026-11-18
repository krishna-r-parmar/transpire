from app.domains.profiles.controllers import TOURS_KEY, _tour_progress


def test_tour_progress_defaults_to_nothing_seen() -> None:
    assert _tour_progress(None).seen == {}
    assert _tour_progress({"compact_lists": True}).seen == {}


def test_tour_progress_ignores_malformed_values() -> None:
    progress = _tour_progress({TOURS_KEY: {"platform": 1, "submit_idea": "yes"}})
    assert progress.seen == {"platform": 1}
    assert _tour_progress({TOURS_KEY: ["platform"]}).seen == {}
