from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Header
from motor.motor_asyncio import AsyncIOMotorDatabase
from .Dcontroller import process_document, delete_document, get_documents_by_user, collection
from src.utils.auth_utils import get_user_id_from_token

router = APIRouter(prefix="/doc", tags=["Doc"])


def get_db():
    from src.database.db import get_database
    return get_database()


@router.post("/upload-document/{session_id}")
async def upload_document(
    session_id: str,
    file: UploadFile = File(...),
    authorization: str = Header(None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    user_id = get_user_id_from_token(authorization)

    if file.content_type not in [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    return await process_document(file, user_id, session_id, db)


@router.delete("/delete-document/{doc_id}/{session_id}")
async def delete_doc(
    doc_id: str,
    session_id: str,
    authorization: str = Header(None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    _ = get_user_id_from_token(authorization)
    return await delete_document(doc_id, session_id, db)


@router.get("/list-documents/{session_id}")
async def list_documents(
    session_id: str,
    authorization: str = Header(None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    user_id = get_user_id_from_token(authorization)
    docs = await get_documents_by_user(user_id, session_id, db)
    return {"documents": docs}

@router.get("/debug-chunks/{doc_id}/{session_id}")
async def debug_chunks(
    doc_id: str,
    session_id: str,
    authorization: str = Header(None)
):
    user_id = get_user_id_from_token(authorization)

    try:
        results = collection.get(where={"doc_id": doc_id})

        filtered_chunks = []
        for i, metadata in enumerate(results.get("metadatas", [])):
            if (
                metadata.get("session_id") == session_id
                and metadata.get("user_id") == user_id
            ):
                filtered_chunks.append({
                    "chunk_id": results["ids"][i],
                    "document": results["documents"][i],
                    "metadata": metadata
                })

        if not filtered_chunks:
            raise HTTPException(
                status_code=404,
                detail=f"No chunks found for doc_id: {doc_id}, session_id: {session_id}, and user_id: {user_id}"
            )

        return {
            "chunk_count": len(filtered_chunks),
            "chunks": filtered_chunks
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


