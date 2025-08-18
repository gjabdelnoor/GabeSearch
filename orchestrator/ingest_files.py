import sys
from pathlib import Path


def main(paths):
    for p in paths:
        try:
            text = Path(p).read_text(encoding='utf-8')
            print(f"Ingested {p} ({len(text)} bytes)")
        except Exception as e:
            print(f"Failed to ingest {p}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
