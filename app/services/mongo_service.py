from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
from app.config import MONGO_URL, DATABASE_NAME

client = AsyncIOMotorClient(MONGO_URL)
db = client[DATABASE_NAME]
chat_collection = db["chat_history"]


async def store_message(case_id: str, role: str, content: str):
    try:
        await chat_collection.insert_one({
            "case_id": case_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc)
        })
    except Exception as e:
        raise Exception(f"Failed to store message: {e}")


async def get_chat_history(case_id: str, token_budget: int = 2000) -> list[dict]:
    try:
        cursor = chat_collection.find(
            {"case_id": case_id}
        ).sort("timestamp", -1)

        messages = []
        total_tokens = 0

        async for doc in cursor:
            estimated_tokens = len(doc["content"]) // 4
            if total_tokens + estimated_tokens > token_budget:
                break
            messages.append({
                "role": doc["role"],
                "content": doc["content"]
            })
            total_tokens += estimated_tokens

        messages.reverse()
        return messages
    except Exception as e:
        raise Exception(f"Failed to get chat history: {e}")


async def delete_chat_history(case_id: str):
    try:
        await chat_collection.delete_many({"case_id": case_id})
    except Exception as e:
        raise Exception(f"Failed to delete chat history: {e}")