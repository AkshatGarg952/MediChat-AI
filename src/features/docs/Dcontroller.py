import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name="dnd6asdiw",
    api_key="284753554659585",
    api_secret="661gxpTMdI_51oNw4YGacj6xqBg"
)

import hashlib
from datetime import datetime
from PyPDF2 import PdfReader
from docx import Document as DocxReader
from .Dschema import DocumentModel, DocumentMetadata
from openai import OpenAI
from io import BytesIO
import chromadb
from chromadb import PersistentClient
from bson import ObjectId
from fastapi import HTTPException
from dotenv import load_dotenv
import os

load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=openai_api_key)

chroma_client = PersistentClient(path="./chroma_data")
collection = chroma_client.get_or_create_collection(name="doc_chunks")


async def generate_doc_id(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def get_page_count(file_bytes: bytes, file_type: str) -> int:
    if file_type == "application/pdf":
        reader = PdfReader(BytesIO(file_bytes))
        return len(reader.pages)
    elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = DocxReader(BytesIO(file_bytes))
        return len(doc.paragraphs)
    return None


def extract_text_chunks(file_bytes: bytes, file_type: str, chunk_size=500):
    text = ""
    if file_type == "application/pdf":
        reader = PdfReader(BytesIO(file_bytes))
        for page in reader.pages:
            text += page.extract_text() or ""
    elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = DocxReader(BytesIO(file_bytes))
        for para in doc.paragraphs:
            text += para.text + "\n"

    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    return chunks


async def embed_chunks(chunks):
    response = client.embeddings.create(
        input=chunks,
        model="text-embedding-ada-002"
    )
    embeddings = [item.embedding for item in response.data]
    return embeddings

async def process_document(file, user_id: str, session_id: str, db):
    file_bytes = await file.read()
    doc_id = await generate_doc_id(file_bytes)

    
    try:
        if file.content_type == "application/pdf":
            PdfReader(BytesIO(file_bytes))  
        elif file.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            DocxReader(BytesIO(file_bytes)) 
    except Exception as e:
        return {"error": "Uploaded document is corrupted or unreadable.", "details": str(e)}

    
    resource_type = "raw" if file.content_type in [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ] else "auto"

    upload_result = cloudinary.uploader.upload(
        file=file_bytes,
        folder=f"users/{user_id}/sessions/{session_id}",
        public_id=doc_id,
        resource_type=resource_type,
        format="pdf" if file.content_type == "application/pdf" else None
    )

    cloudinary_url = upload_result.get("secure_url")

    
    metadata = DocumentMetadata(
        file_name=file.filename,
        file_type=file.content_type,
        file_size=len(file_bytes),
        page_count=get_page_count(file_bytes, file.content_type)
    )

    document = DocumentModel(
        doc_id=doc_id,
        metadata=metadata,
        user_id=user_id,
        session_id=session_id,
        cloudinary_url=cloudinary_url,
        uploaded_at=datetime.utcnow()
    )

    
    session = await db["sessions"].find_one({"session_id": session_id, "user_id": user_id})
    if not session:
       
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "documents": [document.dict()],
            "messages": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        await db["sessions"].insert_one(session_data)
        doc_in_session = False
    else:
        
        doc_in_session = any(doc["doc_id"] == doc_id for doc in session.get("documents", []))
        if not doc_in_session:
            await db["sessions"].update_one(
                {"session_id": session_id, "user_id": user_id},
                {
                    "$push": {"documents": document.dict()},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

    if not doc_in_session:
        
        chunks = extract_text_chunks(file_bytes, file.content_type)

        if not chunks or all(chunk.strip() == "" for chunk in chunks):
            return {
                "message": "No readable text found in document",
                "doc_id": doc_id,
                "cloudinary_url": cloudinary_url,
                "chunk_count": 0,
                "chunk_ids": []
            }

        embeddings = await embed_chunks(chunks)
        chunk_ids = [f"{doc_id}_chunk_{i}_session_{session_id}" for i in range(len(chunks))]

        collection.add(
            ids=chunk_ids,
            documents=chunks,
            metadatas=[{
                "doc_id": doc_id,
                "user_id": user_id,
                "session_id": session_id,
                "chunk_index": i
            } for i in range(len(chunks))],
            embeddings=embeddings
        )

        return {
            "message": "Document processed and embedded",
            "doc_id": doc_id,
            "cloudinary_url": cloudinary_url,
            "chunk_count": len(chunks),
            "chunk_ids": chunk_ids
        }
    else:
        
        return {
            "message": "Document already exists in this session. Skipping re-embedding.",
            "doc_id": doc_id,
            "cloudinary_url": cloudinary_url,
            "chunk_count": 0,
            "chunk_ids": []
        }




async def delete_document(doc_id: str, session_id: str, db):
    session = await db["sessions"].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    document = next((doc for doc in session.get("documents", []) if doc["doc_id"] == doc_id), None)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found in session")

    try:
        cloudinary.uploader.destroy(
            public_id=f"users/{session['user_id']}/sessions/{session_id}/{doc_id}",
            resource_type="raw"
        )
    except Exception as e:
        print(f"Error deleting from Cloudinary: {e}")

    await db["sessions"].update_one(
        {"session_id": session_id},
        {
            "$pull": {"documents": {"doc_id": doc_id}},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )

    raw_chunks = collection.get(where={"doc_id": doc_id})
    delete_ids = [
        raw_chunks["ids"][i]
        for i, meta in enumerate(raw_chunks["metadatas"])
        if meta.get("session_id") == session_id
    ]
    if delete_ids:
        collection.delete(ids=delete_ids)

    return {
        "message": f"Deleted document and {len(delete_ids)} chunks",
        "doc_id": doc_id
    }


async def get_documents_by_user(user_id: str, session_id: str, db):
    session = await db["sessions"].find_one({"session_id": session_id, "user_id": user_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session.get("documents", [])
