import asyncio
import httpx
import sys
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse

from config import TOP_K, PER_PAGE_CHARS, TOTAL_CHARS
from search import parse_queries_from_prompt, searx_top_links
from vector_cache import cache_page, vector_search
from mcp_server import create_server, run_server


def extract_page_metadata(html: str, url: str):
    """Extract metadata from HTML"""
    try:
        soup = BeautifulSoup(html, "lxml")

        meta_author = ""
        meta_date = ""
        meta_description = ""

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
            output_format="txt",
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
        print(f"Fetch error for {url}: {e}", file=sys.stderr, flush=True)

    return "", {}


async def bulk_retrieve(prompt: str):
    queries, claim = parse_queries_from_prompt(prompt)
    print(f"DEBUG: Parsed {len(queries)} queries: {queries}", file=sys.stderr, flush=True)

    search_tasks = [searx_top_links(q, TOP_K) for q in queries]
    search_results = await asyncio.gather(*search_tasks)

    flat_links = []
    for q, results in zip(queries, search_results):
        print(f"DEBUG: Query '{q}' returned {len(results)} results", file=sys.stderr, flush=True)
        for item in results:
            item["source_query"] = q
            flat_links.append(item)

    print(f"DEBUG: Total {len(flat_links)} links to fetch", file=sys.stderr, flush=True)

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
                        url_norm = item["url"].split('#')[0].rstrip('/')
                        cache_page(
                            url_norm,
                            text,
                            item.get("title") or fetch_metadata.get("page_title"),
                            urlparse(item["url"]).netloc,
                            fetch_metadata.get("fetch_timestamp"),
                        )
                    except Exception as e:
                        print(f"Vector cache error for {item['url']}: {e}", file=sys.stderr, flush=True)

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

                    chunk = f"[SOURCE {source['id']}] {source['title']}\n{source['url']}\n\n{text}\n\n"

                    if used_chars + len(chunk) > TOTAL_CHARS:
                        chunk = chunk[:max(0, TOTAL_CHARS - used_chars)]

                    merged_text.append(chunk)
                    used_chars += len(chunk)

                    if used_chars >= TOTAL_CHARS:
                        break

    print(f"DEBUG: Successfully fetched {len(sources)} sources, {used_chars} chars", file=sys.stderr, flush=True)

    vec_hits = vector_search(claim or " ".join(queries), k=TOP_K * 2)
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
            "num_queries": len(queries),
            "hybrid_vector_cache": True,
        },
    }


server = create_server(bulk_retrieve)


async def main():
    await run_server(server)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except* (asyncio.CancelledError, BrokenPipeError):
        pass
    except* Exception as eg:
        import traceback
        print("FATAL ExceptionGroup:", file=sys.stderr, flush=True)
        traceback.print_exception(eg, file=sys.stderr)
        sys.exit(1)
