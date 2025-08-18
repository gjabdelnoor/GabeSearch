"""Configuration for GabeSearch orchestrator.

Values are taken from environment variables with safe defaults so that
missing configuration does not crash the application.  Users may copy
`config_example.py` to `config.py` to set static values instead of
environment variables.
"""

import os

TOP_K = int(os.getenv("TOP_K", "3"))
PER_PAGE_CHARS = int(os.getenv("PER_PAGE_CHARS", "5000"))
TOTAL_CHARS = int(os.getenv("TOTAL_CHARS", "25000"))
