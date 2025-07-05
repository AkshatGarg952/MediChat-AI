from fastapi import APIRouter, Depends, Header
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List
from src.utils.auth_utils import get_user_id_from_token
from .sessionSchema import SessionModel
from src.database.db import get_db

router = APIRouter()

router = APIRouter(prefix="/session", tags=["Session"])

@router.get("/get-user-sessions", response_model=List[SessionModel])
async def get_user_sessions(
    authorization: str = Header(None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    user_id = get_user_id_from_token(authorization)

    cursor = db.sessions.find({"user_id": user_id})
    sessions = []
    async for session in cursor:
        session["_id"] = str(session["_id"]) 
        sessions.append(SessionModel(**session))

    return sessions


@router.get("/get-next-session-id")
async def get_next_session_id(
    authorization: str = Header(None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    user_id = get_user_id_from_token(authorization)


    session_count = await db.sessions.count_documents({"user_id": user_id})

    # Next session ID will be count + 1
    next_session_id = str(session_count + 1)

    return {"next_session_id": next_session_id}