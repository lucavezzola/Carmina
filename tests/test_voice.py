from src.server.voice import find_spell_matches, find_spells


def test_find_spells_is_case_insensitive_and_normalized():
    assert find_spells("FUOCO, poi scudo e Fulmine") == ["fuoco", "scudo", "fulmine"]


def test_find_spell_matches_preserves_match_positions():
    matches = find_spell_matches("pronuncia fulmine adesso")

    assert [(match.group(1), match.start(), match.end()) for match in matches] == [
        ("fulmine", 10, 17),
    ]


def test_find_spells_requires_word_boundaries():
    assert find_spells("fuocofuoco scudetto fulmine") == ["fulmine"]
