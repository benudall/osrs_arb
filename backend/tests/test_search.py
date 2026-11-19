from app.api.routes import _row_matches, _search_words

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


def test_match_material():
    assert _row_matches(ROW, _search_words("guam"))
    assert not _row_matches(ROW, _search_words("aranim"))


def test_match_note():
    row = dict(ROW)
    row["note"] = "needs a tanning leather"
    assert _row_matches(row, _search_words("tanning"))
    assert not _row_matches(ROW, _search_words("tanning"))


def test_match_skill():
    assert _row_matches(ROW, _search_words("herblore"))
    assert not _row_matches(ROW, _search_words("smithing"))


def test_all_words_must_match():
    assert _row_matches(ROW, _search_words("attack guam"))
    # both words must appear, not split across fields: "guam" ok, "attack" ok
    assert _row_matches(ROW, _search_words("guam attack"))
    assert not _row_matches(ROW, _search_words("attack iron"))


def test_empty_words_match_everything():
    assert _row_matches(ROW, [])
