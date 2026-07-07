"""
CLI entrypoint: crawl the target website end-to-end and (re)build the
ChromaDB index.

Usage:
    python -m scripts.crawl_and_index --base-url https://vignaniit.edu.in --max-pages 300

Run this once before starting the API, and re-run any time you want to
refresh the knowledge base with the latest site content.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow running as `python -m scripts.crawl_and_index` from the backend/ dir
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.crawler import crawl_site
from app.embeddings import chunk_text, embed_texts
from app.vectorstore import VectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("crawl_and_index")


async def main(base_url: str, max_pages: int, max_depth: int) -> None:
    settings = get_settings()

    logger.info("Starting crawl of %s (max_pages=%d, max_depth=%d)", base_url, max_pages, max_depth)
    pages = await crawl_site(
        base_url=base_url,
        max_pages=max_pages,
        max_depth=max_depth,
        request_timeout_ms=settings.request_timeout_ms,
    )
    logger.info("Crawl finished: %d pages fetched", len(pages))

    if not pages:
        logger.error("No pages were crawled. Check the base URL and network access.")
        return

    store = VectorStore(
        persist_dir=settings.chroma_db_dir,
        collection_name=settings.collection_name,
    )
    logger.info("Resetting existing collection '%s'...", settings.collection_name)
    store.reset()

    total_chunks = 0
    for page in pages:
        chunks = chunk_text(
            page.text,
            chunk_size_words=settings.chunk_size_words,
            overlap_words=settings.chunk_overlap_words,
        )
        if not chunks:
            continue
        vectors = embed_texts(chunks, settings.embedding_model)
        n = store.add_page_chunks(page.url, page.title, chunks, vectors)
        total_chunks += n
        logger.info("  + %s -> %d chunks", page.url, n)

    logger.info(
        "Indexing complete: %d pages, %d chunks stored in '%s'",
        len(pages), total_chunks, settings.chroma_db_dir,
    )


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Crawl a site and build the RAG vector index.")
    parser.add_argument("--base-url", default=settings.base_url)
    parser.add_argument("--max-pages", type=int, default=settings.max_pages)
    parser.add_argument("--max-depth", type=int, default=settings.crawl_depth)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.base_url, args.max_pages, args.max_depth))
