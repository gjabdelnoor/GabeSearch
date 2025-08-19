import os, re, json, random, asyncio, aiohttp, httpx, ast, uuid, time
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from FlagEmbedding import FlagModel
import numpy as np

# Load paging configuration either from a local config module or environment
try:
    from config import TOP_K, PER_PAGE_CHARS, TOTAL_CHARS
except Exception:  # pragma: no cover - fallback for missing config file
    TOP_K = int(os.getenv("TOP_K", "3"))
    PER_PAGE_CHARS = int(os.getenv("PER_PAGE_CHARS", "5000"))
    TOTAL_CHARS = int(os.getenv("TOTAL_CHARS", "25000"))

SEARX_URL = os.getenv("SEARX_URL", "http://localhost:8888/search")
N_QUERIES = int(os.getenv("QUERIES", "5"))

STRICT_ARGS = os.getenv("STRICT_ARGS", "false").lower() == "true"
MAX_QUERIES = int(os.getenv("MAX_QUERIES", "12"))
LOG_ARG_WARNINGS = os.getenv("LOG_ARG_WARNINGS", "true").lower() == "true"

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("WEB_CACHE_COLLECTION", "web-cache")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

_qdrant_client: Optional[QdrantClient] = None
_embed_model: Optional[FlagModel] = None


def _ensure_clients():
    global _qdrant_client, _embed_model
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    if _embed_model is None:
        _embed_model = FlagModel(EMBED_MODEL_NAME, use_fp16=False)


async def _upsert_text(text: str, metadata: Dict[str, Any]):
    _ensure_clients()
    loop = asyncio.get_running_loop()
    vector = await loop.run_in_executor(None, lambda: _embed_model.encode([text])[0])
    point = PointStruct(
        id=metadata.get("url") or metadata.get("id") or str(uuid.uuid4()),
        vector=vector.tolist(),
        payload={"text": text, **metadata},
    )
    await loop.run_in_executor(
        None,
        lambda: _qdrant_client.upsert(collection_name=QDRANT_COLLECTION, points=[point]),
    )


async def _rag_search(query: str, k: int):
    _ensure_clients()
    loop = asyncio.get_running_loop()
    vector = await loop.run_in_executor(None, lambda: _embed_model.encode([query])[0])

    def _search():
        return _qdrant_client.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=vector.tolist(),
            limit=k,
            with_payload=True,
            with_vectors=True,
        )

    results = await loop.run_in_executor(None, _search)
    matches = []
    for r in results:
        payload = r.payload or {}
        matches.append(
            {
                "text": payload.get("text") or payload.get("content") or "",
                "metadata": payload,
                "score": r.score,
                "vector": r.vector,
            }
        )
    return matches


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    a_vec, b_vec = np.array(a), np.array(b)
    return float(np.dot(a_vec, b_vec) / ((np.linalg.norm(a_vec) * np.linalg.norm(b_vec)) + 1e-10))


def _deduplicate_chunks(matches: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    unique_matches: List[Dict[str, Any]] = []
    for match in matches:
        vec = match.get("vector")
        dom = match.get("metadata", {}).get("domain")
        is_duplicate = False
        for existing in unique_matches:
            if vec is not None and existing.get("vector") is not None:
                if _cosine_similarity(vec, existing["vector"]) > 0.8:
                    is_duplicate = True
                    break
            if dom and dom == existing.get("metadata", {}).get("domain"):
                is_duplicate = True
                break
        if not is_duplicate:
            unique_matches.append(match)
    return unique_matches[:k]


async def _smart_rag_search(query: str, k: int = 15) -> List[Dict[str, Any]]:
    raw_matches = await _rag_search(query, k * 2)
    unique_matches = _deduplicate_chunks(raw_matches, k)
    for match in unique_matches:
        match["text"] = match["text"][:350]
    return unique_matches

SEARCH_ENGINES = [e.strip() for e in os.getenv("SEARCH_ENGINES", "bing,brave,qwant,mojeek,wikipedia").split(",") if e.strip()]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:119.0) Gecko/20100101 Firefox/119.0",
]

ACCEPT_LANGS = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.8",
    "en;q=0.7",
]

def _random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": random.choice(ACCEPT_LANGS),
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }

server = Server("GabeSearch-mcp")

CODEFENCE_RE = re.compile(r"^\s*```(?:json|yaml|yml|txt)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
JSON_ARRAY_RE = re.compile(r"\[(?:\s*\".*?\"\s*,?)+\]", re.DOTALL)
BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+\.)\s+(.*\S)\s*$")
KEYVAL_RE = re.compile(r"^\s*([A-Za-z_][\w\- ]{0,32})\s*:\s*(.+?)\s*$")

def _strip_fences(s: str) -> str:
    m = CODEFENCE_RE.search(s)
    return m.group(1) if m else s

def _json_try(s: str) -> Optional[Any]:
    try:
        return json.loads(s)
    except Exception:
        pass
    try:
        obj = ast.literal_eval(s)
        return obj
    except Exception:
        return None

def _extract_claim(text: str) -> Optional[str]:
    for ln in text.splitlines():
        if ln.lower().startswith("claim:"):
            return ln.split(":", 1)[1].strip() or None
    return None

def _extract_queries_from_text(text: str) -> List[str]:
    text = _strip_fences(text).strip()
    qs: List[str] = []
    obj = _json_try(text)
    if isinstance(obj, dict) and "queries" in obj and isinstance(obj["queries"], list):
        qs.extend([str(x) for x in obj["queries"]])
    elif isinstance(obj, list) and all(isinstance(x, str) for x in obj):
        qs.extend(obj)
    else:
        blocks = re.split(r"(?im)^\s*queries?\s*:\s*$", text)
        if len(blocks) > 1:
            payload = blocks[1]
            for ln in payload.splitlines():
                m = BULLET_RE.match(ln)
                if m:
                    qs.append(m.group(1).strip())
            if not qs:
                arr = JSON_ARRAY_RE.search(payload)
                if arr:
                    arr_obj = _json_try(arr.group(0))
                    if isinstance(arr_obj, list):
                        qs.extend([str(x) for x in arr_obj if isinstance(x, str)])
        if not qs:
            for ln in text.splitlines():
                m = BULLET_RE.match(ln)
                if m:
                    qs.append(m.group(1).strip())
        if not qs:
            for ln in text.splitlines():
                m = KEYVAL_RE.match(ln)
                if m:
                    k = m.group(1).strip().lower()
                    if k in {"q", "query", "search", "prompt"}:
                        qs.append(m.group(2).strip())
        if not qs:
            lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) >= 3]
            if 1 <= len(lines) <= 20:
                qs.extend(lines)
    return qs


def generate_search_queries(prompt: str) -> List[str]:
    prompt = prompt.strip()[:200]
    if not prompt:
        return []
    base = prompt
    variations = [
        base,
        f"latest {base}",
        f"{base} research",
        f"news on {base}",
        f"background of {base}",
    ]
    return variations[:5]

def normalize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(args.get("queries"), list) and all(isinstance(x, str) for x in args["queries"]):
        queries = [x.strip() for x in args["queries"] if str(x).strip()]
        claim = str(args.get("claim")).strip() if isinstance(args.get("claim"), str) else None
        if LOG_ARG_WARNINGS:
            print("normalize_args: direct queries provided", flush=True)
    elif any(k in args for k in ("query", "q", "search", "searches", "questions")):
        key = next(k for k in ("query", "q", "search", "searches", "questions") if k in args)
        v = args[key]
        if isinstance(v, list):
            queries = [str(x).strip() for x in v if str(x).strip()]
        else:
            queries = [str(v).strip()]
        claim = str(args.get("claim")).strip() if isinstance(args.get("claim"), str) else None
        if LOG_ARG_WARNINGS:
            print(f"normalize_args: used alias '{key}'", flush=True)
    else:
        text_fields = []
        for k in ("prompt", "input", "body", "data", "text"):
            v = args.get(k)
            if isinstance(v, str) and v.strip():
                text_fields.append(v)
        if isinstance(args, str):
            text_fields.append(args)
        queries, claim = [], None
        for t in text_fields:
            t = _strip_fences(t)
            obj = _json_try(t)
            if isinstance(obj, dict) and "queries" in obj:
                if isinstance(obj["queries"], list):
                    queries.extend([str(x) for x in obj["queries"]])
                if not claim and isinstance(obj.get("claim"), str):
                    claim = obj["claim"].strip() or None
                if LOG_ARG_WARNINGS:
                    print("normalize_args: parsed JSON object", flush=True)
            if not queries:
                extracted = _extract_queries_from_text(t)
                if extracted and LOG_ARG_WARNINGS:
                    print("normalize_args: extracted queries from text", flush=True)
                queries.extend(extracted)
            if not claim:
                claim = _extract_claim(t)
        if not queries and STRICT_ARGS:
            raise ValueError("No queries found. Provide at least one search query.")
    queries = [q.strip() for q in queries if q and isinstance(q, str)]
    seen: set[str] = set()
    uniq: List[str] = []
    for q in queries:
        if q not in seen:
            uniq.append(q)
            seen.add(q)
    if len(uniq) == 0:
        raise ValueError("No queries found. Provide at least one search query.")
    if len(uniq) > MAX_QUERIES:
        if LOG_ARG_WARNINGS:
            print(f"normalize_args: clipping queries to {MAX_QUERIES}", flush=True)
        uniq = uniq[:MAX_QUERIES]
    uniq = [re.sub(r"\s+", " ", q) for q in uniq]
    out: Dict[str, Any] = {"queries": uniq}
    if claim:
        out["claim"] = claim
    return out

async def searx_top_links(query: str, k: int):
    """Get search results with randomized headers and engine rotation."""

    engines = SEARCH_ENGINES.copy()
    random.shuffle(engines)

    async with aiohttp.ClientSession() as s:
        for engine in engines:
            params = {"q": query, "format": "json", "engines": engine}
            headers = _random_headers()
            try:
                print(f"DEBUG: Searching '{query}' via {engine}", flush=True)
                async with s.get(SEARX_URL, params=params, headers=headers, timeout=15) as r:
                    content_type = r.headers.get("content-type", "")
                    if "application/json" not in content_type:
                        print(f"DEBUG: {engine} returned non-JSON for '{query}' (type={content_type})", flush=True)
                        continue

                    data = await r.json()
                    if not data.get("results"):
                        print(f"DEBUG: {engine} yielded no results for '{query}'", flush=True)
                        continue

                    out = []
                    for item in data.get("results", [])[:k]:
                        out.append({
                            "title": item.get("title", "").strip(),
                            "url": item.get("url", "").strip(),
                            "snippet": item.get("content", "").strip(),
                            "engine": item.get("engine", engine),
                            "publishedDate": item.get("publishedDate", ""),
                            "domain": urlparse(item.get("url", "")).netloc,
                            "query": query,
                            "source_query": query,
                        })
                    return out
            except Exception as e:
                print(f"DEBUG: error with engine {engine} for '{query}': {e}", flush=True)
                continue
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
        print(f"Fetch error for {url}: {e}", flush=True)
    
    return "", {}

async def bulk_retrieve(queries: List[str], claim: Optional[str] = None):
    print(f"DEBUG: Using {len(queries)} queries: {queries}", flush=True)
    
    # Search all queries in parallel
    search_tasks = [searx_top_links(q, TOP_K) for q in queries]
    search_results = await asyncio.gather(*search_tasks)
    
    # Flatten results but keep query association
    flat_links = []
    for q, results in zip(queries, search_results):
        print(f"DEBUG: Query '{q}' returned {len(results)} results", flush=True)
        for item in results:
            item["source_query"] = q
            flat_links.append(item)
    
    print(f"DEBUG: Total {len(flat_links)} links to fetch", flush=True)
    
    # Fetch all pages in parallel
    sources = []
    
    if flat_links:
        async with httpx.AsyncClient(headers={"User-Agent": "GabeSearch-mcp/0.1"}) as client:
            tasks = [fetch_page_with_metadata(item["url"], client) for item in flat_links]
            pages = await asyncio.gather(*tasks)
            
            for item, (text, fetch_metadata) in zip(flat_links, pages):
                if text:
                    # Create rich source metadata for citations
                    source = {
                        "id": len(sources) + 1,
                        "title": item.get("title") or fetch_metadata.get("page_title", "Untitled"),
                        "url": item["url"],
                        "domain": item["domain"],
                        "snippet": item["snippet"],
                        "source_query": item.get("source_query", ""),
                        "search_engine": item["engine"],
                        "author": fetch_metadata.get("meta_author", ""),
                        "publish_date": fetch_metadata.get("meta_date", ""),
                        "fetch_timestamp": fetch_metadata.get("fetch_timestamp", ""),
                        "content_type": fetch_metadata.get("content_type", ""),
                        "word_count": len(text.split()),
                        "status": "successfully_fetched"
                    }
                    sources.append(source)

                    # Vectorize and store in Qdrant
                    try:
                        await _upsert_text(text, source)
                    except Exception as e:
                        print(f"Upsert failed for {item['url']}: {e}", flush=True)

    print(f"DEBUG: Successfully fetched {len(sources)} sources", flush=True)

    return {
        "queries": queries,
        "claim": claim,
        "sources": sources,
        "source_count": len(sources),
        "total_results_found": len(flat_links),
        "retrieval_timestamp": datetime.now().isoformat(),
    }


@server.call_tool()
async def search_and_retrieve(name: str, arguments: dict):
    if name != "search_and_retrieve":
        raise ValueError(f"Unknown tool: {name}")

    if not isinstance(arguments, dict) or not isinstance(arguments.get("prompt"), str):
        err = {
            "error": "Expected object with 'prompt' string",
            "example": {"prompt": "LLM reasoning capabilities 2024"},
        }
        return [TextContent(type="text", text=json.dumps(err, indent=2))]

    prompt = arguments["prompt"][:200]
    queries = generate_search_queries(prompt)

    start = time.time()

    try:
        await bulk_retrieve(queries)
    except Exception as e:
        print(f"bulk_retrieve failed: {e}", flush=True)

    all_matches: List[Dict[str, Any]] = []
    for q in queries:
        try:
            all_matches.extend(await _smart_rag_search(q, 15))
        except Exception as e:
            print(f"RAG search failed for {q}: {e}", flush=True)

    final_matches = _deduplicate_chunks(all_matches, 30)

    chunks = [
        {
            "text": m["text"],
            "title": m.get("metadata", {}).get("title", ""),
            "url": m.get("metadata", {}).get("url", ""),
            "domain": m.get("metadata", {}).get("domain", ""),
            "score": m.get("score", 0),
        }
        for m in final_matches
    ]

    result = {
        "query": prompt,
        "chunks": chunks,
        "total_chunks": len(chunks),
        "processing_time_ms": int((time.time() - start) * 1000),
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="search_and_retrieve",
            description="Search, scrape, vectorize into Qdrant, and return deduplicated RAG chunks for a prompt.",
            inputSchema={
                "type": "object",
                "properties": {"prompt": {"type": "string"}},
                "required": ["prompt"],
                "additionalProperties": False,
            },
        ),
    ]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
