import os
import time
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config import CHUNK_SIZE, CHUNK_OVERLAP
from app.services.embedding_service import get_embeddings_batch
from app.services.qdrant_service import store_chunks, create_collection


def process_pdf_task(case_id: str, file_path: str):
    try:
        # Step 1: Read the PDF
        try:
            loader = PyPDFLoader(file_path)
            documents = loader.load()
        except Exception as e:
            raise Exception(f"Failed to read PDF: {e}")

        # Step 2: Chop into pieces
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )
        chunks = splitter.split_documents(documents)
        texts = [chunk.page_content for chunk in chunks]

        if not texts:
            raise ValueError("PDF had no readable text")

        # Step 3: Turn text into numbers (BATCHED)
        try:
            vectors = []
            batch_size = 50

            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                batch_vectors = get_embeddings_batch(batch_texts)
                vectors.extend(batch_vectors)
                time.sleep(0.5)
        except Exception as e:
            raise Exception(f"Failed to generate embeddings: {e}")

        # Step 4: File them in Qdrant
        try:
            create_collection()
            store_chunks(case_id, texts, vectors)
        except Exception as e:
            raise Exception(f"Failed to store in Qdrant: {e}")

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)