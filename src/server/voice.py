"""Speech recognition helpers for spell detection.

This isolates the Vosk spell matching rules from the websocket loop so they
can be tested independently from networking and combat logic.
"""

import re

from .config import SPELLS_LIST

SPELL_PATTERN = re.compile(
    rf"(?<!\w)({'|'.join(re.escape(spell) for spell in sorted(SPELLS_LIST, key=len, reverse=True))})(?!\w)",
    re.IGNORECASE,
)


def find_spells(text):
    """Return complete spell words found in recognized speech text."""
    return [match.group(1).lower() for match in SPELL_PATTERN.finditer(text)]


def find_spell_matches(text):
    """Return regex matches, including their positions, for recognized spells."""
    return list(SPELL_PATTERN.finditer(text))
