"""Server package scaffold for Carmina.

This package is intentionally small at first: it separates configuration,
world generation, spell matching and future gameplay modules from the
runtime bootstrap in server.py.
"""

from .config import *
