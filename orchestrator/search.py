import re
import json
import aiohttp
import sys
from urllib.parse import urlparse

from config import SEARX_URL, N_QUERIES


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


def parse_queries_from_prompt(prompt: str):
    """Extract queries from JSON or structured text"""
    try:
        data = json.loads(prompt)
        if "queries" in data:
            return data["queries"][:N_QUERIES], data.get("claim", prompt)
    except json.JSONDecodeError:
        pass

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

    return simple_queries(prompt, N_QUERIES), prompt


async def searx_top_links(query: str, k: int):
    """Get search results with metadata - bypasses bot detection"""
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
            print(f"DEBUG: Searching for '{query}'...", file=sys.stderr, flush=True)
            async with s.get(SEARX_URL, params=params, timeout=15) as r:
                print(f"DEBUG: Status {r.status}, Content-Type: {r.headers.get('content-type')}", file=sys.stderr, flush=True)

                content_type = r.headers.get('content-type', '')
                if 'text/html' in content_type:
                    print(f"DEBUG: SearxNG returned HTML (bot detection) for query '{query}'", file=sys.stderr, flush=True)
                    html_content = await r.text()
                    print(f"DEBUG: HTML preview: {html_content[:300]}...", file=sys.stderr, flush=True)
                    return []

                data = await r.json()
                results_found = len(data.get("results", []))
                print(f"DEBUG: Found {results_found} results for '{query}'", file=sys.stderr, flush=True)

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
            print(f"Network error for query '{query}': {e}", file=sys.stderr, flush=True)
            return []
        except json.JSONDecodeError as e:
            print(f"JSON decode error for query '{query}': {e}", file=sys.stderr, flush=True)
            return []
        except Exception as e:
            print(f"Unexpected error for query '{query}': {e}", file=sys.stderr, flush=True)
            return []
