"""
FastAPI entrypoint for the Vignan IIT RAG chatbot.

Routes
------
GET  /api/health        -> service + index status
POST /api/chat           -> ask a question, get a grounded answer + sources
POST /api/admin/reindex   -> re-crawl the site and rebuild the vector index
"""

from __future__ import annotations

import asyncio
import logging
import sys

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .rag_pipeline import RAGPipeline
from .schemas import ChatRequest, ChatResponse, CrawlStatus, HealthResponse
from .vectorstore import VectorStore

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")

settings = get_settings()

app = FastAPI(
    title="Vignan IIT RAG Chatbot API",
    description="Grounded Q&A over the vignaniit.edu.in website content.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single shared vector store + pipeline instance for the app's lifetime.
vector_store = VectorStore(
    persist_dir=settings.chroma_db_dir,
    collection_name=settings.collection_name,
)
pipeline = RAGPipeline(settings=settings, vector_store=vector_store)

# Tracks state of a background re-index job, if triggered via the API.
_reindex_state: dict = {"status": "idle"}


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        collection_document_count=vector_store.count(),
        embedding_model=settings.embedding_model,
        llm_provider=settings.llm_provider,
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    if vector_store.count() == 0:
        raise HTTPException(
            status_code=503,
            detail=(
                "The knowledge base is empty. Run the crawl/index script "
                "(scripts/crawl_and_index.py) or POST /api/admin/reindex first."
            ),
        )

    answer, sources, used_context = pipeline.answer(request.message, request.history)
    return ChatResponse(answer=answer, sources=sources, used_context=used_context)


def _run_reindex_job(base_url: str, max_pages: int, max_depth: int) -> None:
    """Runs the full crawl -> chunk -> embed -> store pipeline in the background."""
    import asyncio
    from .crawler import crawl_site
    from .embeddings import chunk_text, embed_texts

    try:
        _reindex_state.update(status="running", pages_indexed=0, chunks_indexed=0)
        pages = asyncio.run(crawl_site(base_url, max_pages=max_pages, max_depth=max_depth))

        vector_store.reset()
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
            total_chunks += vector_store.add_page_chunks(page.url, page.title, chunks, vectors)

        _reindex_state.update(
            status="completed",
            pages_indexed=len(pages),
            chunks_indexed=total_chunks,
        )
        logger.info("Reindex completed: %d pages, %d chunks", len(pages), total_chunks)
    except Exception as e:
        logger.exception("Reindex failed")
        _reindex_state.update(status="failed", message=str(e))


@app.post("/api/admin/reindex", response_model=CrawlStatus)
def trigger_reindex(background_tasks: BackgroundTasks) -> CrawlStatus:
    """
    Kicks off a fresh crawl + index build in the background.
    Poll GET /api/admin/reindex/status for progress.
    """
    if _reindex_state.get("status") == "running":
        return CrawlStatus(status="already_running")

    background_tasks.add_task(
        _run_reindex_job, settings.base_url, settings.max_pages, settings.crawl_depth
    )
    return CrawlStatus(status="started")


@app.get("/api/admin/reindex/status", response_model=CrawlStatus)
def reindex_status() -> CrawlStatus:
    return CrawlStatus(**_reindex_state) if _reindex_state.get("status") != "idle" else CrawlStatus(status="idle")
