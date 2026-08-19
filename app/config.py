import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------
# External services
# ---------------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/doclense"
)
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ---------------------------------------------------------------
# Auth
# ---------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_MINUTES = int(os.getenv("JWT_EXPIRY_MINUTES", "60"))

# ---------------------------------------------------------------
# Observability
# ---------------------------------------------------------------
# LangChain and LangGraph read these from the environment themselves —
# load_dotenv() above is what activates tracing. Nothing else to wire.
# LANGCHAIN_* are still honoured as legacy aliases.
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "doclense")
LANGSMITH_ENDPOINT = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# ---------------------------------------------------------------
# Qdrant
# ---------------------------------------------------------------
COLLECTION_NAME = "documents"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# ---------------------------------------------------------------
# Models
# ---------------------------------------------------------------
# Routing and small talk on the cheap model; answers on the retrieval
# path go to the larger one, where a misread table becomes a
# confidently wrong number. Chosen by path, never by a grade.
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
ANSWER_MODEL = os.getenv("ANSWER_MODEL", "gpt-4o")

# Named vectors. The collection carries both from the start so that
# adding BM25 in phase 5 does not mean rebuilding the collection.
DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"
SPARSE_MODEL = os.getenv("SPARSE_MODEL", "Qdrant/bm25")

# ---------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# ---------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------
FETCH_LIMIT = int(os.getenv("FETCH_LIMIT", "20"))
FINAL_K = int(os.getenv("FINAL_K", "5"))
RERANK_MODEL = os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")

# The cross-encoder emits raw logits, roughly -11..+11 — not a 0-1
# probability. Start at 0 and tune against printed scores. A threshold
# copied from a hosted reranker's documentation will be wrong.
MIN_SCORE = float(os.getenv("MIN_SCORE", "0"))

# ---------------------------------------------------------------
# Graph
# ---------------------------------------------------------------
MAX_TOOL_ITERATIONS = int(os.getenv("MAX_TOOL_ITERATIONS", "3"))

# ---------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------
# One gpt-4o-mini call per chunk writing its context line. Off until
# there is a Recall@5 baseline to compare against — it is the only
# improvement written into the stored vector.
CONTEXT_LINE_ENABLED = os.getenv("CONTEXT_LINE_ENABLED", "false").lower() == "true"
CONTEXT_LINE_CONCURRENCY = int(os.getenv("CONTEXT_LINE_CONCURRENCY", "20"))
