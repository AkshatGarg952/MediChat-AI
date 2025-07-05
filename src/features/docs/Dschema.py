from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class DocumentMetadata(BaseModel):
    file_name: str
    file_type: str
    file_size: int
    page_count: Optional[int] = None

class DocumentModel(BaseModel):
    doc_id: str
    # user_id: str
    # session_id: str
    metadata: DocumentMetadata
    cloudinary_url: str                        
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
