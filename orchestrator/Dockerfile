FROM python:3.11-slim

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2 libxslt1.1 libxslt1-dev libxml2-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

COPY server.py config.py search.py vector_cache.py mcp_server.py /app/
ENTRYPOINT ["python", "/app/server.py"]
