"""Pydantic models for API requests and responses."""

from typing import Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's question")
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Prior turns in the conversation, oldest first (optional).",
    )


class Source(BaseModel):
    url: str
    title: str
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    used_context: bool = Field(
        ..., description="Whether relevant website context was found and used."
    )


class HealthResponse(BaseModel):
    status: str
    collection_document_count: int
    embedding_model: str
    llm_provider: str


class CrawlStatus(BaseModel):
    status: str
    pages_indexed: Optional[int] = None
    chunks_indexed: Optional[int] = None
    message: Optional[str] = None
