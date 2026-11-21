import pytest

from app.api.routes import _parse_levels, _row_matches, _search_words

ROW = {
    "skill": "herblore",
    "product": {"name": "Attack potion(3)", "qty": 1},
    "materials": [
        {"name": "Vial of water"},
        {"name": "Guam leaf"},
        {"name": "Eye of newt"},
    ],
    "note": None,
}


def test_search_words_strips_and_lowercases():
    assert _search_words(None) == []
    assert _search_words("") == []
    assert _search_words("  ") == []
    assert _search_words("  Attack  potion(3) ") == ["attack", "potion(3)"]


def test_match_product_name():
    assert _row_matches(ROW, _search_words("attack"))
    assert _row_matches(ROW, _search_words("potion"))
    assert not _row_matches(ROW, _search_words("defence"))


def test_match_material_name_ignored():
    # search is product-name only: material names must not match
    assert not _row_matches(ROW, _search_words("guam"))
    assert not _row_matches(ROW, _search_words("vial"))


def test_match_note_ignored():
    row = dict(ROW)
    row["note"] = "needs a tanning leather"
    assert not _row_matches(row, _search_words("tanning"))


def test_match_skill_ignored():
    assert not _row_matches(ROW, _search_words("herblore"))


def test_all_words_must_match():
    assert _row_matches(ROW, _search_words("attack potion"))
    assert not _row_matches(ROW, _search_words("attack guam"))


def test_empty_words_match_everything():
    assert _row_matches(ROW, [])


# ---------- _parse_levels ----------

def test_parse_levels_valid():
    assert _parse_levels("smithing:40,cooking:21") == {"smithing": 40, "cooking": 21}
    assert _parse_levels(" smithing : 40 , ") == {"smithing": 40}


def test_parse_levels_empty():
    assert _parse_levels(None) == {}
    assert _parse_levels("") == {}
    assert _parse_levels(" , ") == {}


def test_parse_levels_rejects_bad_input():
    for bad in ("smithing", "smithing:abc", "smithing:100", "smithing:0", "smithing:"):
        with pytest.raises(Exception):
            _parse_levels(bad)
