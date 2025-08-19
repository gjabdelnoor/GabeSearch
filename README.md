# GabeSearch MCP

GabeSearch is a local MCP server that gives [LM Studio](https://lmstudio.ai) access to real-time web search and retrieval.  Search results are fetched through a local [SearXNG](https://docs.searxng.org/) instance, embedded with [FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) and stored in [Qdrant](https://qdrant.tech/) for fast RAG queries.  Everything runs locally with no API keys or external services.

## Features
- **Real-time web search** through SearXNG
- **Vector cache** in Qdrant using BAAI/bge-small-en-v1.5 embeddings
- **Configurable chunking and deduplication** to reduce prompt bloat
- **Fully local**: runs with Docker on Windows, macOS and Linux

## Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- [LM Studio](https://lmstudio.ai) installed

## Quick Start
1. Clone and start the services:
   ```bash
   git clone https://github.com/gjabdelnoor/GabeSearch.git
   cd GabeSearch
   ./start_servers.sh        # or start_servers.bat on Windows
   ```
2. Configure LM Studio:
   - Open LM Studio → **Settings** → **Developer** → **MCP Settings**
   - Copy the contents of `lm-studio-config/mcp.json` into your MCP configuration
   - Restart LM Studio

## Usage
The server exposes two tools:

- `search_and_retrieve` – generate multiple search queries for a prompt, scrape pages and return deduplicated RAG chunks.
  ```json
  {"prompt": "LLM reasoning capabilities 2024"}
  ```
- `rag_query` – query the existing vector cache directly.
  ```json
  {"query": "vector databases", "k": 10}
  ```

Results include the text snippet, page title, source URL and a confidence score.

## Configuration
Environment variables in `lm-studio-config/mcp.json` allow tuning:

- `SEARX_URL` – SearXNG search endpoint
- `TOP_K` – results fetched per query
- `QUERIES` – number of search queries to generate
- `PER_PAGE_CHARS` / `TOTAL_CHARS` – page and total character limits
- `QDRANT_HOST` / `QDRANT_PORT` – location of the Qdrant service
- `WEB_CACHE_COLLECTION` – Qdrant collection name
- `EMBED_MODEL` – embedding model used for RAG
- `CHUNKS_PER_QUERY` / `CHUNK_CHARS` – size and count of text chunks
- `DEDUP_THRESHOLD` – similarity threshold for deduplication

Adjust these as needed before running the container.

## Docker build
To build the MCP server image separately:
```bash
docker build . -t gabesearch-mcp:latest
```
