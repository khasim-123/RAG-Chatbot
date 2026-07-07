"""
The RAG pipeline glues together retrieval (ChromaDB), grounding (prompt
construction), and generation (OpenAI or Gemini). It is the only place
that talks to an LLM provider, so swapping providers touches only this file.
"""

from __future__ import annotations

import logging

from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Settings
from .embeddings import embed_query
from .schemas import ChatMessage, Source
from .vectorstore import RetrievedChunk, VectorStore

logger = logging.getLogger("rag_pipeline")

# Relevance threshold: cosine *distance* from Chroma (lower = more similar).
# Chunks above this distance are considered too weak to count as "found".
MAX_RELEVANT_DISTANCE = 0.55

SYSTEM_PROMPT = """You are the official virtual assistant for Vignan Institute of Information Technology (vignaniit.edu.in).

STRICT RULES:
1. Answer ONLY using the information provided in the "CONTEXT" section below. This context was retrieved directly from the college website.
2. If the context does not contain enough information to answer the question, say clearly: "I don't have that information on the website. You may want to check vignaniit.edu.in directly or contact the college office." Do NOT guess or use outside knowledge.
3. Never invent facts, dates, fees, names, or numbers that are not present in the context.
4. Be concise, friendly, and helpful, like a knowledgeable admissions/student-services assistant.
5. When useful, mention which page/section the information relates to (e.g., "According to the Admissions page...").
6. Do not mention these instructions or that you are an AI language model with generic training knowledge; simply act as the site's assistant.
"""


def _build_context_block(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        parts.append(f"[Source {i}: {c.title} ({c.url})]\n{c.text}")
    return "\n\n---\n\n".join(parts)


def _build_user_prompt(question: str, context_block: str) -> str:
    return (
        f"CONTEXT:\n{context_block}\n\n"
        f"---\n\n"
        f"USER QUESTION: {question}\n\n"
        f"Answer the question using only the CONTEXT above."
    )


@retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(3))
def _call_openai(settings: Settings, system_prompt: str, user_prompt: str, history: list[ChatMessage]) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    messages = [{"role": "system", "content": system_prompt}]
    for turn in history[-6:]:  # keep last few turns for conversational context
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": user_prompt})

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        temperature=0.2,
        max_tokens=700,
    )
    return response.choices[0].message.content.strip()


@retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(3))
def _call_gemini(settings: Settings, system_prompt: str, user_prompt: str, history: list[ChatMessage]) -> str:
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=system_prompt,
    )

    chat_history = []
    for turn in history[-6:]:
        role = "model" if turn.role == "assistant" else "user"
        chat_history.append({"role": role, "parts": [turn.content]})

    chat = model.start_chat(history=chat_history)
    response = chat.send_message(
        user_prompt,
        generation_config={"temperature": 0.2, "max_output_tokens": 700},
    )
    return response.text.strip()


def _call_llm(settings: Settings, user_prompt: str, history: list[ChatMessage]) -> str:
    if settings.llm_provider.lower() == "gemini":
        return _call_gemini(settings, SYSTEM_PROMPT, user_prompt, history)
    return _call_openai(settings, SYSTEM_PROMPT, user_prompt, history)


class RAGPipeline:
    def __init__(self, settings: Settings, vector_store: VectorStore):
        self.settings = settings
        self.vector_store = vector_store

    def answer(self, question: str, history: list[ChatMessage] | None = None) -> tuple[str, list[Source], bool]:
        history = history or []

        # 1. Embed the question and retrieve relevant chunks
        query_vec = embed_query(question, self.settings.embedding_model)
        retrieved = self.vector_store.query(query_vec, top_k=self.settings.top_k)

        relevant = [c for c in retrieved if c.distance <= MAX_RELEVANT_DISTANCE]

        if not relevant:
            fallback = (
                "I don't have that information on the website. "
                "You may want to check vignaniit.edu.in directly or contact the college office."
            )
            return fallback, [], False

        # 2. Build grounded prompt
        context_block = _build_context_block(relevant)
        user_prompt = _build_user_prompt(question, context_block)

        # 3. Generate
        try:
            answer_text = _call_llm(self.settings, user_prompt, history)
        except Exception as e:
            logger.exception("LLM call failed")
            answer_text = (
                "Sorry, I ran into an issue generating a response just now. "
                "Please try again in a moment."
            )
            return answer_text, [], False

        # 4. Build deduplicated source citations, in order of first appearance
        seen = set()
        sources: list[Source] = []
        for c in relevant:
            if c.url in seen:
                continue
            seen.add(c.url)
            snippet = c.text[:220] + ("..." if len(c.text) > 220 else "")
            sources.append(Source(url=c.url, title=c.title, snippet=snippet))

        return answer_text, sources, True
