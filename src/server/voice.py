"""Speech recognition helpers for spell detection.

This isolates the Vosk spell matching rules from the websocket loop so they
can be tested independently from networking and combat logic.
"""

import re

from .config import SPELLS_LIST


def find_spells(text):
    spell_pattern = "|".join(re.escape(spell) for spell in sorted(SPELLS_LIST, key=len, reverse=True))
    return re.findall(rf"(?<!\w)({spell_pattern})(?!\w)", text.lower())


def find_spell_matches(text):
    spell_pattern = "|".join(re.escape(spell) for spell in sorted(SPELLS_LIST, key=len, reverse=True))
    return list(re.finditer(rf"(?<!\w)({spell_pattern})(?!\w)", text.lower()))
