import os, re, json, asyncio, aiohttp, httpx, sys, logging
from functools import lru_cache
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from FlagEmbedding import BGEM3FlagModel
from mcp.server import Server
from mcp.transport.stdio import stdio_transport
from mcp.types import Tool, TextContent

SEARX_URL = os.getenv("SEARX_URL", "http://localhost:8888/search")
TOP_K = int(os.getenv("TOP_K", "3"))
N_QUERIES = int(os.getenv("QUERIES", "5"))
PER_PAGE_CHARS = int(os.getenv("PER_PAGE_CHARS", "20000"))
TOTAL_CHARS = int(os.getenv("TOTAL_CHARS", "100000"))
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
WEB_CACHE_COLLECTION = os.getenv("WEB_CACHE_COLLECTION", "web-cache")
WEB_CACHE_TTL_DAYS = int(os.getenv("WEB_CACHE_TTL_DAYS", "999999"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

server = Server("gabesearch-mcp")


@lru_cache(maxsize=1)
def get_qdrant():
    qc = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    try:
        qc.get_collection(WEB_CACHE_COLLECTION)
    except Exception:
        qc.recreate_collection(
            collection_name=WEB_CACHE_COLLECTION,
            vectors=qm.VectorParams(size=1024, distance=qm.Distance.COSINE),
            optimizers_config=qm.OptimizersConfigDiff(indexing_threshold=20000),
        )
        qc.create_payload_index(WEB_CACHE_COLLECTION, field_name="url", field_schema="keyword")
    return qc


@lru_cache(maxsize=1)
def get_embed():
    import torch

    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"
        if torch.version.hip is not None and os.name == "nt":
            # Enable Windows ROCm on RX 6800 XT (gfx1030)
            os.environ.setdefault("HSA_OVERRIDE_GFX_VERSION", "10.3.0")
    return BGEM3FlagModel('BAAI/bge-m3', use_fp16=True, device=device)


def chunk_text(txt: str, size=1000, overlap=120):
    out = []
    i = 0
    L = len(txt)
    while i < L:
        j = min(L, i + size)
        seg = txt[i:j].strip()
        if len(seg) >= 200:
            out.append((seg, i, j))
        i += size - overlap
    return out


async def vector_search(q: str, k: int = 12):
    try:
        qc = get_qdrant()
        embed = get_embed()
        qvec = embed.encode([q], max_length=1024)['dense_vecs'][0]
        res = qc.search(WEB_CACHE_COLLECTION, query_vector=qvec, limit=k, with_payload=True)
        hits = []
        for r in res:
            p = r.payload
            hits.append({
                "id": f"V{len(hits)+1}",
                "title": p.get("title") or p.get("site"),
                "url": p.get("url"),
                "domain": p.get("site"),
                "snippet": p.get("text", "")[:280],
                "score": float(r.score),
                "character_count": len(p.get("text", "")),
                "status": "from_vector_cache",
            })
        return hits
    except Exception as e:
        logger.error("Vector search error: %s", e)
        return []

def parse_queries_from_prompt(prompt: str):
    """Extract queries from JSON or structured text"""
    try:
        # Try JSON format first
        data = json.loads(prompt)
        if "queries" in data:
            return data["queries"][:N_QUERIES], data.get("claim", prompt)
    except json.JSONDecodeError:
        pass
    
    # Try structured text format
    if "QUERIES:" in prompt and "CLAIM:" in prompt:
        queries_start = prompt.find("QUERIES:") + len("QUERIES:")
        claim_start = prompt.find("CLAIM:")
        
        queries_section = prompt[queries_start:claim_start].strip()
        claim = prompt[claim_start + len("CLAIM:"):].strip()
        
        queries = []
        for line in queries_section.split('\n'):
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith('-')):
                query = re.sub(r'^[\d\-\.\s]+', '', line).strip()
                if query:
                    queries.append(query)
        
        return queries[:N_QUERIES], claim
    
    # Fallback: generate queries from prompt
    return simple_queries(prompt, N_QUERIES), prompt

def simple_queries(prompt: str, n: int):
    """Fallback query generation"""
    if 'CLAIM TO EVALUATE:' in prompt:
        claim_start = prompt.find('CLAIM TO EVALUATE:') + len('CLAIM TO EVALUATE:')
        claim_section = prompt[claim_start:].strip()
        
        if '"' in claim_section:
            start_quote = claim_section.find('"') + 1
            end_quote = claim_section.find('"', start_quote)
            if end_quote > start_quote:
                actual_claim = claim_section[start_quote:end_quote]
            else:
                actual_claim = claim_section[:200]
        else:
            actual_claim = claim_section[:200]
    else:
        actual_claim = prompt[:200]
    
    words = [w for w in actual_claim.lower().split() if len(w) > 3][:10]
    base = " ".join(words)
    if not base:
        base = actual_claim[:200]
    return [base] * max(1, n)

async def searx_top_links(query: str, k: int):
    """Get search results with metadata - bypasses bot detection"""
    
    # Headers to bypass SearxNG bot detection
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Forwarded-For": "127.0.0.1",
        "X-Real-IP": "127.0.0.1",
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache"
    }
    
    async with aiohttp.ClientSession(headers=headers) as s:
        params = {"q": query, "format": "json", "categories": "general"}
        try:
            logger.debug("Searching for '%s'...", query)
            async with s.get(SEARX_URL, params=params, timeout=15) as r:
                logger.debug("Status %s, Content-Type: %s", r.status, r.headers.get('content-type'))
                
                # Check if we got HTML instead of JSON (bot detection triggered)
                content_type = r.headers.get('content-type', '')
                if 'text/html' in content_type:
                    logger.debug("SearxNG returned HTML (bot detection) for query '%s'", query)
                    html_content = await r.text()
                    logger.debug("HTML preview: %s...", html_content[:300])
                    return []
                
                # Parse JSON response
                data = await r.json()
                results_found = len(data.get("results", []))
                logger.debug("Found %s results for '%s'", results_found, query)
                
                out = []
                for item in data.get("results", [])[:k]:
                    result = {
                        "title": item.get("title", "").strip(),
                        "url": item.get("url", "").strip(),
                        "snippet": item.get("content", "").strip(),
                        "engine": item.get("engine", "unknown"),
                        "publishedDate": item.get("publishedDate", ""),
                        "domain": urlparse(item.get("url", "")).netloc,
                        "query": query,
                    }
                    out.append(result)
                return out
                
        except aiohttp.ClientError as e:
            logger.error("Network error for query '%s': %s", query, e)
            return []
        except json.JSONDecodeError as e:
            logger.error("JSON decode error for query '%s': %s", query, e)
            return []
        except Exception as e:
            logger.error("Unexpected error for query '%s': %s", query, e)
            return []

def extract_page_metadata(html: str, url: str):
    """Extract metadata from HTML"""
    try:
        soup = BeautifulSoup(html, "lxml")
        
        # Extract meta tags
        meta_author = ""
        meta_date = ""
        meta_description = ""
        
        # Try various meta tag formats
        for meta in soup.find_all("meta"):
            name = meta.get("name", "").lower()
            property_attr = meta.get("property", "").lower()
            content = meta.get("content", "")
            
            if name in ["author"] or property_attr in ["article:author"]:
                meta_author = content
            elif name in ["date", "publish-date"] or property_attr in ["article:published_time"]:
                meta_date = content
            elif name in ["description"] or property_attr in ["og:description"]:
                meta_description = content
        
        # Try to extract title
        title_tag = soup.find("title")
        page_title = title_tag.text.strip() if title_tag else ""
        
        return {
            "page_title": page_title,
            "meta_author": meta_author,
            "meta_date": meta_date,
            "meta_description": meta_description,
        }
    except Exception:
        return {}

def clean_html_with_metadata(html: str, url: str):
    """Extract text and metadata"""
    try:
        import trafilatura
        txt = trafilatura.extract(
            html, 
            include_comments=False, 
            include_tables=False,
            output_format="txt"
        )
        if txt and len(txt) > 200:
            clean_text = txt
        else:
            soup = BeautifulSoup(html, "lxml")
            clean_text = soup.get_text(separator=" ", strip=True)
    except Exception:
        soup = BeautifulSoup(html, "lxml")
        clean_text = soup.get_text(separator=" ", strip=True)
    
    metadata = extract_page_metadata(html, url)
    return clean_text, metadata

async def fetch_page_with_metadata(url: str, client: httpx.AsyncClient):
    """Fetch page and extract text + metadata"""
    try:
        r = await client.get(url, timeout=8, follow_redirects=True)
        if 200 <= r.status_code < 300:
            clean_text, page_meta = clean_html_with_metadata(r.text, url)
            
            # Combine response metadata
            metadata = {
                "status_code": r.status_code,
                "content_type": r.headers.get("content-type", ""),
                "last_modified": r.headers.get("last-modified", ""),
                "content_length": len(clean_text),
                "fetch_timestamp": datetime.now().isoformat(),
                **page_meta
            }
            
            return clean_text[:PER_PAGE_CHARS], metadata
    except Exception as e:
        logger.error("Fetch error for %s: %s", url, e)
    
    return "", {}

async def bulk_retrieve(prompt: str):
    queries, claim = parse_queries_from_prompt(prompt)
    logger.debug("Parsed %s queries: %s", len(queries), queries)
    
    # Search all queries in parallel
    search_tasks = [searx_top_links(q, TOP_K) for q in queries]
    search_results = await asyncio.gather(*search_tasks)
    
    # Flatten results but keep query association
    flat_links = []
    for q, results in zip(queries, search_results):
        logger.debug("Query '%s' returned %s results", q, len(results))
        for item in results:
            item["source_query"] = q
            flat_links.append(item)
    
    logger.debug("Total %s links to fetch", len(flat_links))
    
    # Fetch all pages in parallel
    sources = []
    merged_text = []
    used_chars = 0
    
    if flat_links:
        async with httpx.AsyncClient(headers={"User-Agent": "gabesearch-mcp/0.1"}) as client:
            tasks = [fetch_page_with_metadata(item["url"], client) for item in flat_links]
            pages = await asyncio.gather(*tasks)
            
            for item, (text, fetch_metadata) in zip(flat_links, pages):
                if text:
                    try:
                        qc = get_qdrant()
                        embed = get_embed()
                        url_norm = item["url"].split('#')[0].rstrip('/')

                        fresh = False
                        it = qc.scroll(
                            WEB_CACHE_COLLECTION,
                            scroll_filter=qm.Filter(
                                must=[qm.FieldCondition(key="url", match=qm.MatchValue(value=url_norm))]
                            ),
                            limit=1,
                            with_payload=True,
                        )
                        if it and it[0]:
                            meta0 = it[0][0].payload
                            ts = meta0.get("fetched_at")
                            if ts:
                                if (datetime.now() - datetime.fromisoformat(ts)).days < WEB_CACHE_TTL_DAYS:
                                    fresh = True

                        if not fresh:
                            pts = []
                            for idx, (seg, a, b) in enumerate(chunk_text(text)):
                                vec = embed.encode([seg], batch_size=1, max_length=2048)['dense_vecs'][0]
                                pts.append(
                                    qm.PointStruct(
                                        id=f"{url_norm}|{idx}|{a}|{b}",
                                        vector=vec,
                                        payload={
                                            "url": url_norm,
                                            "title": fetch_metadata.get("page_title") or item.get("title"),
                                            "site": urlparse(item["url"]).netloc,
                                            "chunk": idx,
                                            "a": a,
                                            "b": b,
                                            "text": seg,
                                            "fetched_at": fetch_metadata.get("fetch_timestamp"),
                                        },
                                    )
                                )
                            if pts:
                                qc.upsert(WEB_CACHE_COLLECTION, points=pts)
                    except Exception as e:
                        logger.error("Vector cache error for %s: %s", item['url'], e)

                    # Create rich source metadata for citations
                    source = {
                        "id": len(sources) + 1,
                        "title": item.get("title") or fetch_metadata.get("page_title", "Untitled"),
                        "url": item["url"],
                        "domain": item["domain"],
                        "snippet": item["snippet"],
                        "source_query": item["source_query"],
                        "search_engine": item["engine"],
                        "author": fetch_metadata.get("meta_author", ""),
                        "publish_date": fetch_metadata.get("meta_date", ""),
                        "fetch_timestamp": fetch_metadata.get("fetch_timestamp", ""),
                        "content_type": fetch_metadata.get("content_type", ""),
                        "word_count": len(text.split()),
                        "status": "successfully_fetched"
                    }
                    sources.append(source)

                    # Add to merged text with source reference
                    chunk = f"[SOURCE {source['id']}] {source['title']}\n{source['url']}\n\n{text}\n\n"
                    
                    if used_chars + len(chunk) > TOTAL_CHARS:
                        chunk = chunk[:max(0, TOTAL_CHARS - used_chars)]
                    
                    merged_text.append(chunk)
                    used_chars += len(chunk)
                    
                    if used_chars >= TOTAL_CHARS:
                        break

    logger.debug("Successfully fetched %s sources, %s chars", len(sources), used_chars)

    vec_hits = await vector_search(claim or " ".join(queries), k=TOP_K * 2)
    seen = set(u["url"] for u in sources)
    merged = sources + [h for h in vec_hits if h["url"] not in seen]
    merged.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    return {
        "queries": queries,
        "claim": claim,
        "sources": merged[:len(sources)],
        "source_count": len(merged),
        "total_results_found": len(flat_links),
        "merged_text": "".join(merged_text),
        "retrieval_timestamp": datetime.now().isoformat(),
        "character_count": used_chars,
        "settings": {
            "total_chars": TOTAL_CHARS,
            "per_page_chars": PER_PAGE_CHARS,
            "top_k": TOP_K,
            "num_queries": N_QUERIES,
            "hybrid_vector_cache": True,
        },
    }

@server.call_tool()
async def search_and_retrieve(name: str, arguments: dict):
    if name != "search_and_retrieve":
        raise ValueError(f"Unknown tool: {name}")
    
    prompt = arguments.get("prompt", "")
    result = await bulk_retrieve(prompt)
    
    return [TextContent(type="text", text=json.dumps(result, indent=2))]

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="search_and_retrieve",
            description="Bulk search and retrieve content with citation metadata. Accepts JSON with 'queries' array or structured text format.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "JSON object with queries array, or structured text with QUERIES: and CLAIM: sections"
                    }
                },
                "required": ["prompt"],
            },
        )
    ]

async def main():
    async with stdio_transport() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except* (asyncio.CancelledError, BrokenPipeError):
        pass
    except* Exception:
        logger.exception("FATAL ExceptionGroup")
        sys.exit(1)
