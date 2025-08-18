import os, re, json, asyncio, aiohttp, httpx
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

SEARX_URL = os.getenv("SEARX_URL", "http://localhost:8888/search")
TOP_K = int(os.getenv("TOP_K", "3"))
N_QUERIES = int(os.getenv("QUERIES", "5"))
PER_PAGE_CHARS = int(os.getenv("PER_PAGE_CHARS", "5000"))
TOTAL_CHARS = int(os.getenv("TOTAL_CHARS", "25000"))

server = Server("bulk-rag")

def parse_queries_from_prompt(prompt: str):
    """Extract queries from JSON or structured text"""
    try:
        # Try JSON format first
        data = json.loads(prompt)
        if "queries" in data:
            return data["queries"][:5], data.get("claim", prompt)
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
        
        return queries[:5], claim
    
    # Fallback: generate queries from prompt
    return simple_queries(prompt, 3), prompt

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
    return [" ".join(words)][:n]

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
            print(f"DEBUG: Searching for '{query}'...", flush=True)
            async with s.get(SEARX_URL, params=params, timeout=15) as r:
                print(f"DEBUG: Status {r.status}, Content-Type: {r.headers.get('content-type')}", flush=True)
                
                # Check if we got HTML instead of JSON (bot detection triggered)
                content_type = r.headers.get('content-type', '')
                if 'text/html' in content_type:
                    print(f"DEBUG: SearxNG returned HTML (bot detection) for query '{query}'", flush=True)
                    html_content = await r.text()
                    print(f"DEBUG: HTML preview: {html_content[:300]}...", flush=True)
                    return []
                
                # Parse JSON response
                data = await r.json()
                results_found = len(data.get("results", []))
                print(f"DEBUG: Found {results_found} results for '{query}'", flush=True)
                
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
            print(f"Network error for query '{query}': {e}", flush=True)
            return []
        except json.JSONDecodeError as e:
            print(f"JSON decode error for query '{query}': {e}", flush=True)
            return []
        except Exception as e:
            print(f"Unexpected error for query '{query}': {e}", flush=True)
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

async def bulk_retrieve(prompt: str):
    queries, claim = parse_queries_from_prompt(prompt)
    print(f"DEBUG: Parsed {len(queries)} queries: {queries}", flush=True)
    
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
    merged_text = []
    used_chars = 0
    
    if flat_links:
        async with httpx.AsyncClient(headers={"User-Agent": "bulk-rag/0.1"}) as client:
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

    print(f"DEBUG: Successfully fetched {len(sources)} sources, {used_chars} chars", flush=True)

    return {
        "queries": queries,
        "claim": claim,
        "sources": sources,
        "source_count": len(sources),
        "total_results_found": len(flat_links),
        "merged_text": "".join(merged_text),
        "retrieval_timestamp": datetime.now().isoformat(),
        "character_count": used_chars
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
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())