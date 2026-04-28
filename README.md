# DocLense — AI Document Intelligence

Chat with your PDF documents using AI. Upload any PDF, assign a Case ID, and ask questions — DocLense retrieves precise, source-grounded answers using RAG (Retrieval-Augmented Generation).

---

## Architecture

```
Browser → FastAPI Server → Redis (Valkey) Queue → RQ Worker
                        ↓                              ↓
                   Qdrant (vectors)           PDF → Chunks → Embeddings → Qdrant
                   MongoDB (chat history)
                   LangGraph (RAG pipeline)
```

**Stack:**
- **Backend:** FastAPI, LangGraph, LangChain, OpenAI (GPT-4o-mini / GPT-4o)
- **Vector DB:** Qdrant
- **Chat History:** MongoDB
- **Queue:** Valkey (Redis-compatible) + RQ
- **Frontend:** Vanilla HTML/CSS/JS (3 pages)
- **Deployment:** Azure Container Apps + Azure Container Registry

---

## Project Structure

```
04_DocLense/
├── app/
│   ├── api/
│   │   └── server.py          # FastAPI routes
│   ├── graph/
│   │   ├── workflow.py        # LangGraph graph definition
│   │   ├── nodes.py           # Graph node functions
│   │   └── prompts.py         # Prompts + LLM models
│   ├── models/
│   │   └── schemas.py         # Pydantic schemas
│   ├── services/
│   │   ├── embedding_service.py
│   │   ├── mongo_service.py
│   │   ├── qdrant_service.py
│   │   └── redis_service.py
│   ├── worker/
│   │   └── process_pdf.py     # PDF processing task
│   └── config.py
├── frontend/
│   ├── index.html             # Landing page
│   ├── upload.html            # Upload / enter case ID
│   └── chat.html              # Chat interface
├── main.py                    # Uvicorn entry point
├── run_worker.py              # RQ worker entry point
├── Dockerfile                 # Server image
├── Dockerfile.worker          # Worker image
├── docker-compose.yml         # Local infra (Valkey, MongoDB, Qdrant)
├── deploy.ps1                 # Azure deployment script
└── requirements.txt
```

---

## RAG Pipeline (LangGraph)

```
classify_intent
    ├── chat     → generate_direct → save_conversation
    └── document → retrieve_history → check_processing → retrieve_chunks
                   → generate_answer_mini → evaluate_answer
                        ├── good → save_conversation
                        └── bad  → generate_answer_heavy → save_conversation
```

- **classify_intent** — LLM classifies message as `chat` or `document`
- **generate_direct** — fast response for greetings/small talk (no retrieval)
- **retrieve_chunks** — semantic search via Qdrant (top 15 chunks)
- **generate_answer_mini** — GPT-4o-mini answers from context
- **evaluate_answer** — GPT-4o-mini evaluates answer quality
- **generate_answer_heavy** — GPT-4o fallback if mini answer is poor

---

## Local Development

### Prerequisites
- Python 3.12+
- Docker Desktop
- `uv` package manager

### Setup

```bash
# Install dependencies
uv sync

# Start local infrastructure (Valkey, MongoDB, Qdrant)
docker compose up -d
```

### Environment Variables

Create a `.env` file:

```env
OPENAI_API_KEY=sk-...
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
MONGO_URL=mongodb://localhost:27017
REDIS_URL=redis://localhost:6379
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=DocLense
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

### Run

```bash
# Terminal 1 — API server
uv run main.py

# Terminal 2 — Background worker
uv run run_worker.py
```

Open `http://localhost:8000`

---

## Case ID Format

Case IDs follow the pattern: **4 letters + dash + number**

Examples: `TESL-42`, `DOCS-1`, `INVC-99`

Multiple PDFs can be uploaded under the same Case ID and will be queried together.

---

## Deployment (Azure)

Images are hosted on Azure Container Registry (`doclesnses.azurecr.io`) and run as Azure Container Apps.

```powershell
.\deploy.ps1
```

**Container Apps:**
- `doclense-server` — FastAPI + frontend
- `doclense-worker` — RQ background worker

Both share an Azure Files volume at `/app/temp_uploads` for PDF handoff between server and worker.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload a PDF with a Case ID |
| `GET` | `/status/{job_id}` | Check PDF processing status |
| `GET` | `/verify/{case_id}` | Check if a Case ID has documents |
| `POST` | `/chat` | Ask a question about a Case ID |
| `DELETE` | `/delete/{case_id}` | Delete all data for a Case ID |