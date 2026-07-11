from app.core.text import closest_matches, normalize_tag


def test_normalize_tag():
    assert normalize_tag("  Compliance ") == "compliance"
    assert normalize_tag("HR") == "hr"


def test_closest_matches_finds_typo():
    assert closest_matches("complaince", ["compliance", "hr", "product"]) == ["compliance"]


def test_closest_matches_empty_when_nothing_close():
    assert closest_matches("zzzzzz", ["compliance", "hr"]) == []
