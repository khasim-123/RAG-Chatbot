"""
ChromaDB wrapper: a thin, focused interface over a single persistent
collection used to store website chunk embeddings and query them at
chat time.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger("vectorstore")


@dataclass
class RetrievedChunk:
    text: str
    url: str
    title: str
    distance: float


class VectorStore:
    def __init__(self, persist_dir: str, collection_name: str):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _chunk_id(url: str, chunk_index: int) -> str:
        digest = hashlib.sha256(f"{url}::{chunk_index}".encode()).hexdigest()[:16]
        return f"{digest}-{chunk_index}"

    def reset(self) -> None:
        """Delete and recreate the collection (used before a fresh crawl)."""
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_page_chunks(
        self,
        url: str,
        title: str,
        chunks: list[str],
        embeddings: list[list[float]],
    ) -> int:
        if not chunks:
            return 0
        ids = [self._chunk_id(url, i) for i in range(len(chunks))]
        metadatas = [{"url": url, "title": title, "chunk_index": i} for i in range(len(chunks))]
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
        return len(chunks)

    def count(self) -> int:
        return self.collection.count()

    def query(self, query_embedding: list[float], top_k: int = 5) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.count()),
        )
        chunks = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            chunks.append(
                RetrievedChunk(
                    text=doc,
                    url=meta.get("url", ""),
                    title=meta.get("title", ""),
                    distance=dist,
                )
            )
        return chunks
