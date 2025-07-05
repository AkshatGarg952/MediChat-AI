from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from src.database.db import get_database
from .chatController import handle_user_query, get_all_chats, generate_chat_summary_text, handle_voice_query, summarize_with_gpt
from src.utils.auth_utils import get_user_id_from_token
from .utils import convert_speech_to_text, convert_text_to_speech, convert_any_audio_to_wav
from .pdf import generate_enhanced_consultation_pdf
from datetime import datetime
import subprocess
import tempfile
import requests
import os

router = APIRouter(prefix="/chat", tags=["Chat"])

# @router.post("/ask/{session_id}/{is_voice}")
# async def unified_ask_handler(
#     session_id: str,
#     is_voice: bool,
#     question: str = Form(...),
#     authorization: str = Header(None),
#     db: AsyncIOMotorDatabase = Depends(get_database)
# ):
#     user_id = get_user_id_from_token(authorization)
#     print(f"🔐 User ID: {user_id}")
#     print(f"📥 Received Question: {question}")
#     print(f"🎙️ Is Voice: {is_voice}")

#     if not question.strip():
#         raise HTTPException(status_code=400, detail="Empty query not allowed")

#     if is_voice:
#         # 🔊 Return voice-based (TTS) response
#         answer_text = await handle_voice_query(user_id, session_id, question.strip(), db)
#         print(f"🤖 Answer: {answer_text}")

#         tts_result = convert_text_to_speech(answer_text)
#         if "error" in tts_result:
#             raise HTTPException(status_code=500, detail=tts_result["error"])

#         return {
#             "query": question,
#             "answer": answer_text,
#             "audio_url": tts_result["url"],
#             "audio_file": tts_result["file"]
#         }

#     else:
#         return StreamingResponse(
#             handle_user_query(user_id, session_id, question.strip(), db),
#             media_type="text/plain"
#         )



@router.post("/ask/{session_id}")
async def unified_ask_handler(
    session_id: str,
    authorization: str = Header(None),
    question: str = Form(None),  # Optional
    audio_file: UploadFile = File(None),  # Optional
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    user_id = get_user_id_from_token(authorization)
    print(f"🔐 User ID: {user_id}")
    
    if audio_file:  # 🎙️ Voice-based query
        print("🎙️ Voice query received")
        print(f"📁 File: {audio_file.filename}, Content type: {audio_file.content_type}")

        text_query = await convert_speech_to_text(audio_file)
        print(f"📄 Transcribed Text: {text_query}")

        if not text_query.strip():
            raise HTTPException(status_code=400, detail="Transcription failed or empty")

        answer_text = await handle_voice_query(user_id, session_id, text_query, db)
        print(f"🤖 Answer: {answer_text}")

        tts_result = convert_text_to_speech(answer_text)
        if "error" in tts_result:
            raise HTTPException(status_code=500, detail=tts_result["error"])

        return {
            "query": text_query,
            "answer": answer_text,
            "audio_url": tts_result["url"],
            "audio_file": tts_result["file"]
        }
    
    elif question:  # 📄 Text-based query
        print(f"💬 Text query: {question}")
        return StreamingResponse(
            handle_user_query(user_id, session_id, question, db),
            media_type="text/plain"
        )
    
    else:  # 🚫 No input
        raise HTTPException(status_code=400, detail="No question or audio file provided")










@router.post("/summarize/{session_id}")
async def summarize_session_chat(
    session_id: str,
    authorization: str = Header(None),
    db=Depends(get_database)
):
    try:
        user_id = get_user_id_from_token(authorization)
        summary_text = await generate_chat_summary_text(user_id, session_id, db)
        pdf_stream = generate_enhanced_consultation_pdf(user_id, session_id, summary_text)

        return StreamingResponse(
            pdf_stream,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=Summary_Of_Chat_{session_id}.pdf"
            }
        )

    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        print(f"Summary generation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate chat summary PDF.")
        

@router.post("/summarize-audio/{session_id}")
async def summarize_audio_file(
    session_id: str,
    audio_file: UploadFile = File(...),
    authorization: str = Header(None),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    try:
        user_id = get_user_id_from_token(authorization)

        transcript = await convert_speech_to_text(audio_file)
        if not transcript.strip():
            raise HTTPException(status_code=400, detail="Transcription failed or empty")

        summary_text = summarize_with_gpt(raw_text=transcript)

        pdf_stream = generate_enhanced_consultation_pdf(user_id, session_id, transcript)

        return StreamingResponse(
            pdf_stream,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=Summary_{session_id}.pdf"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio summary error: {str(e)}")



@router.get("/history/{session_id}")
async def chat_history(
    session_id: str,
    authorization: str = Header(None),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    user_id = get_user_id_from_token(authorization)
    return await get_all_chats(user_id, session_id, db)



