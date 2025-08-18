import sys
from datetime import datetime
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from FlagEmbedding import BGEM3FlagModel

from config import (
    QDRANT_HOST,
    QDRANT_PORT,
    WEB_CACHE_COLLECTION,
    WEB_CACHE_TTL_DAYS,
)


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
    import os
    import torch

    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"
        if torch.version.hip is not None and os.name == "nt":
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


def is_fresh(url_norm: str) -> bool:
    qc = get_qdrant()
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
            return (datetime.now() - datetime.fromisoformat(ts)).days < WEB_CACHE_TTL_DAYS
    return False


def cache_page(url_norm: str, text: str, title: str, site: str, fetched_at: str) -> None:
    if is_fresh(url_norm):
        return
    qc = get_qdrant()
    embed = get_embed()
    pts = []
    for idx, (seg, a, b) in enumerate(chunk_text(text)):
        vec = embed.encode([seg], batch_size=1, max_length=2048)['dense_vecs'][0]
        pts.append(
            qm.PointStruct(
                id=f"{url_norm}|{idx}|{a}|{b}",
                vector=vec,
                payload={
                    "url": url_norm,
                    "title": title,
                    "site": site,
                    "chunk": idx,
                    "a": a,
                    "b": b,
                    "text": seg,
                    "fetched_at": fetched_at,
                },
            )
        )
    if pts:
        qc.upsert(WEB_CACHE_COLLECTION, points=pts)


def vector_search(q: str, k: int = 12):
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
        print(f"Vector search error: {e}", file=sys.stderr, flush=True)
        return []
