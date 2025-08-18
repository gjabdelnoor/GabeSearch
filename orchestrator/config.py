import os

SEARX_URL = os.getenv("SEARX_URL", "http://localhost:8888/search")
TOP_K = int(os.getenv("TOP_K", "3"))
N_QUERIES = int(os.getenv("QUERIES", "5"))
PER_PAGE_CHARS = int(os.getenv("PER_PAGE_CHARS", "20000"))
TOTAL_CHARS = int(os.getenv("TOTAL_CHARS", "100000"))
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
WEB_CACHE_COLLECTION = os.getenv("WEB_CACHE_COLLECTION", "web-cache")
WEB_CACHE_TTL_DAYS = int(os.getenv("WEB_CACHE_TTL_DAYS", "999999"))
