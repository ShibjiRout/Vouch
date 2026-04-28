from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UploadResponse(BaseModel):
    case_id: str
    filename: str
    job_id: str
    message: str


class ChatRequest(BaseModel):
    case_id: str
    question: str


class ChatResponse(BaseModel):
    case_id: str
    answer: str
    sources: int


class JobStatus(BaseModel):
    job_id: str
    status: str
    message: Optional[str] = None


class ChatMessage(BaseModel):
    case_id: str
    role: str
    content: str
    timestamp: datetime = None