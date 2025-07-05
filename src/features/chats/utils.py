from fastapi import UploadFile, HTTPException
from datetime import datetime
from typing import List
from openai import AsyncOpenAI
from chromadb import Client
from chromadb.config import Settings
import os
import requests
import tempfile
import base64
import io
import asyncio
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from openai.types.chat import ChatCompletionChunk
import time
import subprocess
import mimetypes
import httpx
import requests

load_dotenv()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SPEAK_API_URL = "https://c96a-13-126-144-181.ngrok-free.app/speak"

RESEMBLE_API_KEY = os.getenv("RESEMBLE_API_KEY", "").strip()
RESEMBLE_VOICE_UUID = os.getenv("RESEMBLE_VOICE_UUID", "").strip()
RESEMBLE_PROJECT_UUID = os.getenv("RESEMBLE_PROJECT_UUID", "").strip()
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "").strip()

chroma_client = Client(Settings())
collection = chroma_client.get_or_create_collection("doc_chunks")


async def get_chat_history(user_id: str, session_id: str, db):
    cursor = db["chats"].find({"user_id": user_id, "session_id": session_id}).sort("timestamp", 1)
    history = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        history.append(doc)
    return history


async def refine_question(original_question: str, history: List[dict]) -> str:
    chat_context = "\n".join([f"User: {msg['question']}\nAI: {msg['answer']}" for msg in history[-5:]])
    prompt = f"Refine the question based on previous conversation:\n{chat_context}\nUser: {original_question}"

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()


async def retrieve_chunks(user_id: str, session_id: str, query: str):
    query_embedding = (await client.embeddings.create(
        input=query,
        model="text-embedding-ada-002"
    )).data[0].embedding

    raw_results = collection.query(
        query_embeddings=[query_embedding],
        n_results=20,
        where={"user_id": user_id}
    )

    filtered_docs = []
    metadatas = raw_results.get("metadatas", [[]])[0]
    documents = raw_results.get("documents", [[]])[0]

    for meta, doc in zip(metadatas, documents):
        if meta.get("session_id") == session_id:
            filtered_docs.append(doc)

    return filtered_docs


async def rerank_chunks(query: str, chunks: List[str]) -> List[str]:
    rerank_prompt = f"Query: {query}\n\nBelow are retrieved text chunks:\n\n" + "\n\n".join([f"[{i+1}] {c}" for i, c in enumerate(chunks)])
    rerank_prompt += "\n\nRank the most relevant chunks by numbers (comma-separated):"

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": rerank_prompt}]
    )
    ranked_indexes = [int(i.strip()) - 1 for i in response.choices[0].message.content.split(",") if i.strip().isdigit()]

    return [chunks[i] for i in ranked_indexes[:3]]


async def generate_answer_streaming(query: str, context_chunks: List[str], history: List[dict]):
    chat_context = "\n".join([
        f"User: {msg['question']}\nAI: {msg['answer']}" for msg in history[-5:]
    ]) if history else "No previous chats."

    document_context = "\n\n".join(context_chunks) if context_chunks else "No documents found."

    prompt = f"""
You are a helpful AI assistant. Answer the user's question by considering both the prior conversation and relevant document context.

---

📂 Previous Conversation:
{chat_context}

📄 Relevant Document Chunks:
{document_context}

❓ User Query:
{query}
""".strip()

    buffer = ""

    try:
        stream = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            if delta and delta.content:
                buffer += delta.content

                while " " in buffer:
                    word, buffer = buffer.split(" ", 1)
                    yield word + " "
                    await asyncio.sleep(0.01)

        if buffer.strip():
            yield buffer.strip()

    except Exception as e:
        yield f"\n[Internal error: {str(e)}]"


async def convert_speech_to_text(audio_file: UploadFile) -> str:
    # Get original MIME type from filename (e.g., 'audio/webm', 'audio/mpeg')
    mime_type, _ = mimetypes.guess_type(audio_file.filename)
    if not mime_type:
        mime_type = "audio/wav"  # fallback

    # Read file bytes
    audio_bytes = await audio_file.read()

    # Send to Deepgram
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": mime_type
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.deepgram.com/v1/listen",
            headers=headers,
            content=audio_bytes
        )

    if response.status_code != 200:
        print("Deepgram Error:", response.text)
        raise Exception("Deepgram transcription failed")

    transcript = response.json()["results"]["channels"][0]["alternatives"][0]["transcript"]
    return transcript.strip()



def convert_text_to_speech(text: str) -> dict:
    try:
        # 🛰️ Send the text to your own FastAPI /speak endpoint (hosted on EC2)
        response = requests.post(SPEAK_API_URL, json={"text": text})

        if response.status_code != 200:
            return {"error": f"API returned {response.status_code}: {response.text}"}

        data = response.json()
        filename = data.get("file")

        if not filename:
            return {"error": "No audio file returned by /speak API"}

        # 🧠 Construct audio URL
        base_url = SPEAK_API_URL.rsplit("/speak", 1)[0]
        download_url = f"{base_url}/static/{filename}"

        return {
            "message": "Speech generated successfully",
            "file": filename,
            "url": download_url
        }

    except Exception as e:
        print(f"Error during TTS forwarding: {e}")
        return {"error": str(e)}



async def convert_any_audio_to_wav(audio_file: UploadFile) -> str:
    try:
        # Get extension (e.g., "webm", "mp3", "m4a")
        original_ext = audio_file.filename.split('.')[-1].lower()

        # Save uploaded file to temp path
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{original_ext}") as tmp_input:
            tmp_input.write(await audio_file.read())
            tmp_input_path = tmp_input.name

        # Output .wav path
        tmp_wav_path = tmp_input_path.rsplit(".", 1)[0] + ".wav"

        # Convert using ffmpeg to 16kHz mono .wav (perfect for Whisper)
        subprocess.run([
            "ffmpeg", "-y",
            "-i", tmp_input_path,
            "-ar", "16000",
            "-ac", "1",
            tmp_wav_path
        ], check=True)

        # Clean input after conversion (optional)
        os.remove(tmp_input_path)

        return tmp_wav_path  # You can now use this for Whisper

    except subprocess.CalledProcessError:
        raise HTTPException(status_code=400, detail="Audio conversion failed. Unsupported format or ffmpeg error.")