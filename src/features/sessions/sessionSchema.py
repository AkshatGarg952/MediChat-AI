from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from src.features.docs.Dschema import DocumentModel
from src.features.chats.chatSchema import ChatMessage

class SessionModel(BaseModel):
    session_id: str                   
    user_id: str
    documents: List[DocumentModel] = []
    messages: List[ChatMessage] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

