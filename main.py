from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.database.db import connect_to_mongo, close_mongo_connection
from src.features.users.Uroutes import router as user_router
from src.features.docs.Droutes import router as doc_router
from src.features.chats.chatRoutes import router as chat_router
from src.features.sessions.sessionRoutes import router as session_router
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"], 
)


@app.get("/")
async def root():
    return {"message": "Welcome to the server side"}

@app.on_event("startup")
async def startup_db():
    await connect_to_mongo()

@app.on_event("shutdown")
async def shutdown_db():
    await close_mongo_connection()



app.include_router(user_router)
app.include_router(doc_router)
app.include_router(chat_router)
app.include_router(session_router)