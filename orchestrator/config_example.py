"""Example static configuration for GabeSearch orchestrator.

Copy this file to `config.py` and adjust the values if you prefer to
store configuration in the repository instead of using environment
variables.
"""

# How many results to retrieve from each search query
TOP_K = 3

# Maximum characters to keep per fetched page
PER_PAGE_CHARS = 5000

# Maximum characters across all pages
TOTAL_CHARS = 25000
