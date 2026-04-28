 
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
MONGO_URL = os.getenv("MONGO_URL")
REDIS_URL = os.getenv("REDIS_URL")

COLLECTION_NAME = "doclense_vectors"
DATABASE_NAME = "doclense"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200