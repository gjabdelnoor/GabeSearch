FROM python:3.11-slim

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2 libxslt1.1 libxslt1-dev libxml2-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY orchestrator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY orchestrator/server.py ./server.py

# Default environment values
ENV SEARX_URL=http://localhost:8888/search \
    TOP_K=3 \
    QUERIES=5 \
    PER_PAGE_CHARS=20000 \
    TOTAL_CHARS=100000

ENTRYPOINT ["python", "/app/server.py"]
