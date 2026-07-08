# Vignan IIT RAG Chatbot — Setup Guide

Follow these steps **in order**, on a fresh machine, using **PowerShell** (not Command
Prompt — some commands here are PowerShell-only). To open PowerShell in a folder,
Shift+Right-click the folder in File Explorer → "Open PowerShell window here."

---

## 0. Prerequisites

- **Python 3.11 or 3.12** (avoid 3.13 — some ML packages don't have prebuilt wheels
  for it yet). Check your version:
  ```powershell
  python --version
  ```
- An **OpenAI** or **Gemini** API key (see step 5).

---

## 1. Get the code onto the machine

Extract the project zip into a **new, empty folder** — don't merge into an existing
partial copy. After extracting, verify the folder structure is intact:

```powershell
cd path\to\vignan-rag-chatbot\backend
dir app
```

You must see all of these files inside `app\`:
```
__init__.py
main.py
config.py
schemas.py
crawler.py
embeddings.py
vectorstore.py
rag_pipeline.py
```

If any are missing or sitting in `backend\` instead of `backend\app\`, fix that
**before** continuing — nothing past this point will work otherwise. Do not zip or
copy the `venv` / `venv312` folders between machines; each machine builds its own
(see step 2).

---

## 2. Create a virtual environment

```powershell
python -m venv venv
venv\Scripts\activate
```

Your prompt should now start with `(venv)`.

---

## 3. Install dependencies

Some packages (`chroma-hnswlib`) don't ship a Windows wheel for the exact pinned
version in `requirements.txt`. Install in this order to avoid a C++ compiler error:

```powershell
python -m pip install --upgrade pip setuptools wheel
pip install chroma-hnswlib==0.7.5
pip install -r requirements.txt
playwright install chromium
```

Verify everything actually imports (catches issues pip's resolver can miss):
```powershell
python -c "import chromadb; import sentence_transformers; import fastapi; import playwright; print('ALL IMPORTS OK')"
```

### If you hit a TLS / certificate error during install

```
OSError: Could not find a suitable TLS CA certificate bundle
```

This happens on machines with a leftover `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` /
`CURL_CA_BUNDLE` environment variable (commonly left behind by a PostgreSQL
install) pointing at a cert file that doesn't exist. Clear it for the current
session and retry:

```powershell
Remove-Item Env:SSL_CERT_FILE -ErrorAction SilentlyContinue
Remove-Item Env:REQUESTS_CA_BUNDLE -ErrorAction SilentlyContinue
Remove-Item Env:CURL_CA_BUNDLE -ErrorAction SilentlyContinue
```

If it comes back in every new terminal, it's set permanently at the User or
Machine level and you don't have permission to unset it — see the `reindex.ps1`
wrapper in step 6, which clears it automatically every run.

---

## 4. Set up environment variables

```powershell
copy .env.example .env
notepad .env
```

Fill in:
```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.5-flash
```
(or `LLM_PROVIDER=openai` + `OPENAI_API_KEY=...` if using OpenAI instead)

**Never share this file or paste its contents into chat/screenshots** — API keys
in shared text should be treated as compromised and rotated immediately.

---

## 5. Crawl the site and build the vector index

Use the wrapper script below instead of running the command directly — it clears
the CA-bundle environment variables automatically so you don't hit the TLS error
above on every fresh terminal.

Create `reindex.ps1` in `backend\`:
```powershell
notepad reindex.ps1
```
Paste in:
```powershell
$env:SSL_CERT_FILE = $null
$env:REQUESTS_CA_BUNDLE = $null
$env:CURL_CA_BUNDLE = $null
$env:PIP_CERT = $null

python -m scripts.crawl_and_index --base-url https://vignaniit.edu.in --max-pages 300
```

Run it:
```powershell
.\reindex.ps1
```

If PowerShell blocks script execution the first time:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

This takes several minutes (headless Chromium renders every page). You should see
`Indexed [n/300] <url> (N chars)` lines streaming, ending with something like:
```
Indexing complete: 142 pages, 351 chunks stored in '../data/chroma_db'
```

**Note:** some pages on this site fall back to serving homepage content when
visited directly (a quirk of the site's routing, not our crawler). The crawler
already detects and skips these automatically — you'll see
`Skipping page -- content is identical to an already-captured page` warnings for
them. That's expected and correct, not an error to fix.

---

## 6. Start the API server

```powershell
uvicorn app.main:app --reload --port 8000
```

Leave this running in its own terminal window the whole time the chatbot is in
use. Verify it's healthy by opening in a browser:
```
http://localhost:8000/api/health
```
You should see JSON like:
```json
{"status":"ok","collection_document_count":351,"embedding_model":"all-MiniLM-L6-v2","llm_provider":"gemini"}
```

(The `chromadb.telemetry.product.posthog` errors in the log are harmless —
ChromaDB failing to send anonymous usage stats. Safe to ignore.)

---

## 7. Open the frontend

Open in a browser:
```
frontend\index.html
```
Ask it a question, e.g. "What courses does Vignan IIT offer?" — you should get a
grounded answer with clickable source links.

If the UI shows **"Could not reach the chatbot backend"**, the uvicorn server
from step 6 either isn't running or was closed — check that terminal window
first before troubleshooting anything else.

---

## Troubleshooting quick reference

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'app.main'` | Files misplaced outside `app/`, or missing `__init__.py` | Re-check step 1 file layout |
| TLS/CA-bundle `OSError` on any `pip install` or model download | Leftover cert env var from another tool (often PostgreSQL) | See step 3, or use `reindex.ps1` |
| Crawl finds pages with ~50 char content | Site hadn't finished rendering when crawler grabbed it | Already fixed in `crawler.py`'s settle-poll logic — re-pull latest code if you see this |
| Many pages with identical large character counts | Site falls back to homepage for some routes | Already handled by dedup logic in `crawler.py` |
| Chat answers "I don't have that information" for things clearly on the site | Stale/empty vector index | Re-run step 5 |
| `Move-Item is not recognized` | You're in Command Prompt, not PowerShell | Type `powershell` to switch, or use `move` instead |
| Gemini `PERMISSION_DENIED` | New Google Cloud project needs billing set up, or is still provisioning | Check aistudio.google.com/apikey for a billing/status banner, or switch to OpenAI temporarily |

---

## Security note for the team

Rotate any API key that has ever been pasted into a chat tool, screenshot, or
shared conversation link — treat it as compromised even if the conversation
itself is private.
