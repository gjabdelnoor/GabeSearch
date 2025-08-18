import sys, os
from datetime import datetime
from urllib.parse import urlparse
from qdrant_client.http import models as qm

from server import get_qdrant, get_embed, chunk_text, WEB_CACHE_COLLECTION


def ingest_file(path: str):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        txt = f.read()
    qc = get_qdrant()
    embed = get_embed()
    url_norm = f"file://{os.path.abspath(path)}"
    pts = []
    for idx, (seg, a, b) in enumerate(chunk_text(txt)):
        vec = embed.encode([seg], batch_size=1, max_length=2048)['dense_vecs'][0]
        pts.append(
            qm.PointStruct(
                id=f"{url_norm}|{idx}|{a}|{b}",
                vector=vec,
                payload={
                    'url': url_norm,
                    'title': os.path.basename(path),
                    'site': urlparse(url_norm).netloc or 'local',
                    'chunk': idx,
                    'a': a,
                    'b': b,
                    'text': seg,
                    'fetched_at': datetime.now().isoformat(),
                },
            )
        )
    if pts:
        qc.upsert(WEB_CACHE_COLLECTION, points=pts)


if __name__ == '__main__':
    for p in sys.argv[1:]:
        try:
            ingest_file(p)
            print(f'Ingested {p}')
        except Exception as e:
            print(f'Error ingesting {p}: {e}', file=sys.stderr)

