"""RAG ingest runner: chunks markdown files and writes to the store."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from totalrecall.testgen.rag.models import RagChunkIngestRequest

_CHUNK_SIZE = 512
_OVERLAP = 64


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _OVERLAP) -> list[str]:
    """Split text into overlapping word-count chunks."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += chunk_size - overlap
    return chunks


class RagIngestRunner:
    def __init__(self, store, tenant_id: str = "") -> None:
        self._store = store
        self._tenant_id = tenant_id

    def ingest_file(self, path: Path) -> int:
        text = path.read_text(encoding="utf-8")
        source_ref = path.name
        raw_chunks = _chunk_text(text)
        requests = [
            RagChunkIngestRequest(
                tenant_id=self._tenant_id,
                source_ref=source_ref,
                chunk_index=i,
                chunk_text=chunk,
            )
            for i, chunk in enumerate(raw_chunks)
        ]
        return self._store.ingest(requests)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest markdown into the RAG store")
    parser.add_argument("--source", required=True, help="Path to .md file")
    parser.add_argument("--tenant", default="", help="Tenant ID")
    args = parser.parse_args()

    from totalrecall.testgen.rag.store import NullRagStore

    # In production this would be wired via factory; for CLI use NullRagStore as placeholder
    store = NullRagStore()
    runner = RagIngestRunner(store, tenant_id=args.tenant)
    count = runner.ingest_file(Path(args.source))
    print(f"Ingested {count} chunks from {args.source}")


if __name__ == "__main__":
    main()
