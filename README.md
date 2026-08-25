# Vouch

A financial document analyst you can chat with. Upload annual reports, trading
updates or contracts into a chat and ask questions about them. Every answer comes
from those documents and shows the page it was read from. When the documents do
not support an answer, it says so.

To *vouch* a figure is to trace it back to the document that supports it. That is
the whole product.

---

## How it works

```
question ──┬─► dense search  → 30 ─┐
           └─► BM25 keyword  → 30 ─┴─► RRF → 30 ─► local rerank → top 5 ─► agent
```

The agent decides for itself whether to search, so "hello" never touches the
vector store. Facts worth remembering are extracted in the background after the
answer has already been sent.

---

## Stack

| | |
|---|---|
| API | FastAPI, LangGraph, LangChain |
| Models | `gpt-4.1-mini` answers, `gpt-4o-mini` extracts memory |
| Vectors | Qdrant — dense + BM25 sparse, RRF fusion |
| Reranker | `Xenova/ms-marco-MiniLM-L-6-v2` via fastembed, local, no API key |
| Database | Postgres — tenants, users, threads, documents, and LangGraph's checkpoints |
| Memory | LangMem over a Postgres store |
| Queue | Valkey + RQ |
| PDF | pdfplumber, tables kept whole |
| Frontend | Vanilla HTML/CSS/JS, no build step, deployed separately |

---

## Running it

Five containers: Postgres, Qdrant, Valkey, the API, the worker.

```bash
docker compose up -d          # all five
docker compose logs -f api    # follow the API
```

Or without Docker, for development:

```bash
docker compose up -d postgres qdrant valkey
uv sync
uv run main.py                # API on :8000
uv run run_worker.py          # required — uploads hang without it
```

The API serves no pages. Open `frontend/index.html` with any static server and
point `ALLOWED_ORIGINS` at it.

### Environment

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/vouch
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=sk-...
JWT_SECRET=...
ALLOWED_ORIGINS=http://localhost:5500
```

`docker compose` overrides the first three with container names — inside a
container `localhost` means that container.

---

## API

| Method | Endpoint | |
|---|---|---|
| `POST` | `/auth/register` | create a company and its first admin |
| `POST` | `/auth/login` | form-encoded, returns a token |
| `GET` | `/auth/me` | the caller and their company |
| `GET` `POST` | `/threads` | list and create chats |
| `GET` `DELETE` | `/threads/{id}` | one chat |
| `GET` `POST` | `/threads/{id}/documents` | list and upload PDFs |
| `GET` `DELETE` | `/threads/{id}/documents/{doc}` | poll status, remove |
| `POST` | `/threads/{id}/chat` | ask a question |
| `GET` | `/threads/{id}/messages` | the conversation so far |
| `GET` `POST` | `/users` | admin only — the team |
| `DELETE` | `/users/{id}` | admin only — remove someone |
| `GET` | `/health` | Postgres and Qdrant reachable |

Upload returns immediately with `pending`. Poll the document until it reads
`ready` or `failed`.

---

## Isolation

Three keys, all from the verified token, never from a request body.

`tenant_id` is whose data it is. `thread_id` is which documents are in scope.
`created_by` is whose chat it is — a colleague's chat is invisible, admins
included. Someone else's id returns 404, never 403.

```bash
uv run pytest          # 17 tests; the isolation ones gate the rest
```

---

## Measured

233 questions over three annual reports: Recall@5 88%, correct-when-retrieved
84%, p50 2.4s, $0.32. Those came from a substring scorer and are an upper bound.

`eval/` has the current tools — `run_retrieval.py` for search alone,
`run_answers.py` to generate, and `judge.py` for four Ragas metrics.
`metrics/METRICS.md` records every result and every rejected experiment.

Memory, measured in containers under load:

```
api        1.67 GB    the local reranker is 85% of it
worker     1.69 GB    peaks while pdfplumber holds a 40MB PDF
qdrant       83 MB
postgres     65 MB
valkey        5 MB
```

8 GB of RAM for one machine running all five.

---

## Documentation

`CLAUDE.md` — the rules that do not bend, and why each exists.
`claude_data/` — the original specs. Older than the code in places.
