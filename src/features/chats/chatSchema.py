### 📁 chatSchema.py
from pydantic import BaseModel
from datetime import datetime

class ChatMessage(BaseModel):
    # user_id: str
    # session_id: str
    question: str
    refined_question: str
    answer: str
    timestamp: datetime 