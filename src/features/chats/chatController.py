from fastapi import HTTPException
from datetime import datetime
from .chatSchema import ChatMessage
from .utils import refine_question, retrieve_chunks, rerank_chunks, generate_answer_streaming
from openai import OpenAI
from fpdf import FPDF
import os
from datetime import datetime
from dotenv import load_dotenv
import unicodedata
import logging

load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=openai_api_key)

async def handle_user_query(user_id: str, session_id: str, question: str, db):
    try:
        session = await db["sessions"].find_one({"session_id": session_id, "user_id": user_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Step 2: Prepare inputs
        history = session.get("messages", [])
        refined_question = await refine_question(question, history)
        chunks = await retrieve_chunks(user_id, session_id, refined_question)
        top_chunks = await rerank_chunks(refined_question, chunks)

        # Step 3: Stream LLM answer word-by-word
        answer_accumulator = ""
        async for word in generate_answer_streaming(refined_question, top_chunks, history):
            answer_accumulator += word
            yield word  # Stream to user

        # Step 4: Save complete message to DB (after streaming is done)
        message_obj = ChatMessage(
            question=question,
            refined_question=refined_question,
            answer=answer_accumulator.strip(),
            timestamp=datetime.utcnow()
        )

        await db["sessions"].update_one(
            {"session_id": session_id, "user_id": user_id},
            {
                "$push": {"messages": message_obj.dict()},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )

    except Exception as e:
        yield f"\n[Internal error: {str(e)}]"




async def handle_voice_query(user_id: str, session_id: str, question: str, db):
    try:
        session = await db["sessions"].find_one({"session_id": session_id, "user_id": user_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        history = session.get("messages", [])
        refined_question = await refine_question(question, history)
        chunks = await retrieve_chunks(user_id, session_id, refined_question)
        top_chunks = await rerank_chunks(refined_question, chunks)

        # Collect full answer from stream
        answer_accumulator = ""
        async for word in generate_answer_streaming(refined_question, top_chunks, history):
            answer_accumulator += word

        # Save to DB
        message_obj = ChatMessage(
            question=question,
            refined_question=refined_question,
            answer=answer_accumulator.strip(),
            timestamp=datetime.utcnow()
        )
        await db["sessions"].update_one(
            {"session_id": session_id, "user_id": user_id},
            {
                "$push": {"messages": message_obj.dict()},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )

        return answer_accumulator.strip()

    except Exception as e:
        return f"\n[Internal error: {str(e)}]"




    
async def get_all_chats(user_id: str, session_id: str, db):
    session = await db["sessions"].find_one({"session_id": session_id, "user_id": user_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "messages": session.get("messages", [])
    }



async def generate_chat_summary_text(user_id: str, session_id: str, db):
    session = await db["sessions"].find_one({"session_id": session_id, "user_id": user_id})
    if not session or not session.get("messages"):
        raise ValueError("Session not found or has no messages.")

    messages = session["messages"][-20:]
    chat_history = ""
    for msg in messages:
        question = msg.get("question", "").strip()
        answer = msg.get("answer", "").strip()
        if question:
            chat_history += f"User: {question}\n"
        if answer:
            chat_history += f"AI: {answer}\n\n"

    prompt = f"""
You are an AI assistant summarizing a conversation between a student and an AI tutor.

Based on the following conversation:

{chat_history}

Generate a well-structured, friendly, and engaging summary using the format below:

1. 🧭 **Objective of the Chat** – Briefly explain what the student was trying to learn or achieve.
2. 📚 **Topics Discussed** – Use bullet points to list the main topics or questions covered during the chat.
3. 💡 **Key Insights from the AI** – Summarize the most valuable responses or explanations from the AI, using bullet points for clarity.
4. ✅ **Recommendations & Actionable Tips** – Provide concrete suggestions or next steps the student can follow, in bullet point format.
5. 🌟 **Final Takeaway** – End with a short, motivational or friendly message that encourages the student to keep learning.

Ensure the summary is clear, concise, and enjoyable to read in a PDF. Use bullet points wherever applicable to improve readability and structure.
"""

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a helpful AI assistant that summarizes chat sessions for students."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5,
        max_tokens=600
    )

    return response.choices[0].message.content.strip()




def summarize_with_gpt(raw_text: str) -> str:
    if not raw_text.strip():
        return "No text provided for summarization."

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a helpful assistant who summarizes texts."},
            {"role": "user", "content": f"Summarize the following:\n\n{raw_text}"}
        ],
        temperature=0.5,
        max_tokens=300
    )

    return response.choices[0].message.content.strip()