FROM python:3.11-slim

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1

# Install system dependencies for lxml/trafilatura and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2 libxslt1.1 libxslt1-dev libxml2-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY orchestrator/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy server code and ingestion helper
COPY orchestrator/server.py /app/server.py
COPY orchestrator/ingest_files.py /app/orchestrator/ingest_files.py

# Default environment values (can be overridden)
ENV SEARX_URL=http://localhost:8888/search \
    TOP_K=3 \
    QUERIES=5 \
    PER_PAGE_CHARS=20000 \
    TOTAL_CHARS=100000 \
    QDRANT_HOST=localhost \
    QDRANT_PORT=6333 \
    WEB_CACHE_COLLECTION=web-cache \
    WEB_CACHE_TTL_DAYS=10

ENTRYPOINT ["python", "/app/server.py"]
