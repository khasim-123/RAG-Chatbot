"""
Text chunking + embedding utilities backed by Sentence-Transformers.

A single, lazily-loaded model instance is shared across the app (both the
one-off indexing script and the live API use this module), so the model is
loaded into memory only once per process.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from sentence_transformers import SentenceTransformer

logger = logging.getLogger("embeddings")


@lru_cache
def get_embedding_model(model_name: str) -> SentenceTransformer:
    logger.info("Loading Sentence-Transformers model: %s", model_name)
    return SentenceTransformer(model_name)


def embed_texts(texts: list[str], model_name: str) -> list[list[float]]:
    """Embed a batch of texts, returning plain Python lists (Chroma-friendly)."""
    if not texts:
        return []
    model = get_embedding_model(model_name)
    vectors = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return vectors.tolist()


def embed_query(query: str, model_name: str) -> list[float]:
    return embed_texts([query], model_name)[0]


def chunk_text(
    text: str,
    chunk_size_words: int = 350,
    overlap_words: int = 60,
) -> list[str]:
    """
    Split text into overlapping word-based chunks.

    Word-based (rather than character-based) chunking keeps chunks roughly
    aligned to complete sentences/thoughts, which improves retrieval quality
    for short-to-medium web pages typical of an institutional site.
    """
    words = text.split()
    if len(words) <= chunk_size_words:
        return [text] if text.strip() else []

    chunks = []
    step = max(chunk_size_words - overlap_words, 1)
    for start in range(0, len(words), step):
        chunk_words = words[start : start + chunk_size_words]
        if not chunk_words:
            break
        chunks.append(" ".join(chunk_words))
        if start + chunk_size_words >= len(words):
            break
    return chunks
