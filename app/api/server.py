import os
import re
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.models.schemas import UploadResponse, ChatRequest, ChatResponse, JobStatus
from app.services.redis_service import enqueue_job, get_job_status
from app.services.embedding_service import get_embedding
from app.services.qdrant_service import search_chunks, delete_chunks
from app.services.mongo_service import delete_chat_history
from app.worker.process_pdf import process_pdf_task
from app.graph.workflow import ask_question

app = FastAPI(title="DocLense", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "temp_uploads"))
os.makedirs(TEMP_DIR, exist_ok=True)

CASE_ID_PATTERN = re.compile(r'^[a-zA-Z]{4}-\d+$')


@app.post("/upload", response_model=UploadResponse)
async def upload_pdf(file: UploadFile = File(...), case_id: str = Form(...)):
    try:
        if not file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")

        case_id = case_id.strip()

        if not CASE_ID_PATTERN.match(case_id):
            raise HTTPException(
                status_code=400,
                detail="ID must be 4 letters, a dash, then a number. Example: TESL-42"
            )

        file_path = os.path.join(TEMP_DIR, f"{case_id}_{file.filename}")

        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        job_id = enqueue_job(process_pdf_task, case_id, file_path, job_timeout="10m")
        print("\n" + "="*50)
        print(f"🚨 FILE ACTUALLY SAVED HERE: {os.path.abspath(file_path)}")
        print("="*50 + "\n")
        
        return UploadResponse(
            case_id=case_id,
            filename=file.filename,
            job_id=job_id,
            message="PDF uploaded. Processing in background."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload PDF: {e}")


@app.get("/status/{job_id}", response_model=JobStatus)
async def check_status(job_id: str):
    try:
        status = get_job_status(job_id)
        return JobStatus(job_id=job_id, **status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check job status: {e}")


@app.get("/verify/{case_id}")
async def verify_case(case_id: str):
    try:
        results = search_chunks(case_id, get_embedding("test"), top_k=1)
        if results:
            return {"valid": True, "message": "Documents found"}
        return {"valid": False, "message": "No documents found for this ID"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to verify case: {e}")


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        result = await ask_question(request.case_id, request.question)
        return ChatResponse(
            case_id=request.case_id,
            answer=result["answer"],
            sources=result["sources"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process question: {e}")


@app.delete("/delete/{case_id}")
async def delete_case(case_id: str):
    try:
        delete_chunks(case_id)
        await delete_chat_history(case_id)
        return {"case_id": case_id, "message": "All document and chat data deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete case: {e}")


# Static files MUST be last — after all API routes
_FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")