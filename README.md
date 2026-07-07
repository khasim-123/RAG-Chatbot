# Vignan IIT — Website RAG Chatbot

A production-ready Retrieval-Augmented-Generation (RAG) chatbot that crawls
**https://vignaniit.edu.in**, indexes the public content into a local
ChromaDB vector store, and answers user questions **only** using that
content — with source citations back to the page(s) the answer came from.

## Architecture

```
vignan-rag-chatbot/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app + routes
│   │   ├── config.py          # Settings (env vars)
│   │   ├── schemas.py         # Pydantic request/response models
│   │   ├── crawler.py         # Playwright site crawler
│   │   ├── embeddings.py      # Sentence-Transformers embedding wrapper
│   │   ├── vectorstore.py     # ChromaDB wrapper (store + query)
│   │   └── rag_pipeline.py    # Retrieval + prompt + LLM call + citations
│   ├── scripts/
│   │   └── crawl_and_index.py # CLI: crawl site -> chunk -> embed -> store
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html              # ChatGPT-style chat UI
│   ├── style.css
│   └── script.js
├── data/
│   └── chroma_db/              # Persisted vector DB (created at runtime)
└── README.md
```

## How it works

1. **Crawl** (`crawler.py`, driven by `scripts/crawl_and_index.py`)
   Playwright (headless Chromium) starts at the site root, discovers and
   follows same-domain links (respecting depth/page limits and skipping
   files like PDFs/images/mailto/tel links), renders each page (so JS-driven
   content is captured), and extracts clean visible text + title + URL.

2. **Chunk + Embed** (`embeddings.py`)
   Each page's text is split into overlapping chunks (~500 tokens/words with
   overlap). Chunks are embedded using a local `sentence-transformers` model
   (`all-MiniLM-L6-v2` by default — fast, no API cost, runs on CPU).

3. **Store** (`vectorstore.py`)
   Embeddings + metadata (source URL, page title, chunk id) are stored in a
   persistent **ChromaDB** collection on disk under `data/chroma_db`.

4. **Chat** (`rag_pipeline.py` + `main.py`)
   On each user question:
   - Embed the question with the same Sentence-Transformers model.
   - Retrieve top-k most similar chunks from ChromaDB.
   - Build a strict prompt that instructs the LLM to answer **only** from
     the retrieved context, and to say it doesn't know if the answer isn't
     present.
   - Call **OpenAI** or **Google Gemini** (configurable via `LLM_PROVIDER`)
     to generate the answer.
   - Return the answer **plus** the list of source URLs/titles used, so the
     frontend can show citations.

5. **Frontend** (`frontend/`)
   A clean, dependency-free ChatGPT-style chat UI (HTML/CSS/vanilla JS) that
   talks to the FastAPI backend, streams messages into a chat log, shows a
   typing indicator, and renders clickable source citations under each
   answer.

## Setup

### 1. Install dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# then edit .env and set:
#   LLM_PROVIDER=openai            (or gemini)
#   OPENAI_API_KEY=sk-...          (if using openai)
#   GEMINI_API_KEY=...             (if using gemini)
```

### 3. Crawl the site and build the index (one-time / re-run to refresh)

```bash
python -m scripts.crawl_and_index --base-url https://vignaniit.edu.in --max-pages 300
```

This populates `data/chroma_db`. Re-run any time to refresh content.

### 4. Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Open the frontend

Just open `frontend/index.html` in a browser (or serve it with any static
server). It's pre-configured to call `http://localhost:8000`.

## Key design choices

- **Grounded answers only**: the system prompt explicitly forbids the model
  from using outside knowledge; if retrieved chunks don't cover the
  question, it says so instead of guessing.
- **Citations**: every response includes the deduplicated list of source
  URLs (and page titles) whose chunks were actually used in context.
- **Swappable LLM**: one interface (`llm.py`-equivalent inside
  `rag_pipeline.py`) supports OpenAI and Gemini behind a single config flag.
- **Local embeddings**: Sentence-Transformers runs locally — no per-query
  embedding API cost, and it keeps retrieval fast and offline-capable.
- **Idempotent re-crawl**: the crawler script clears and rebuilds the
  collection cleanly on each run so content never goes stale/duplicated.
