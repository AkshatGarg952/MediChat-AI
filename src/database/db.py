from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
from pathlib import Path

env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

client = None
db = None

async def connect_to_mongo():
    global client, db
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    print("Connected to MongoDB")

async def close_mongo_connection():
    global client
    client.close()
    print("MongoDB connection closed")


def get_database():
    return db


def get_user_collection():
    if db is None:
        raise Exception("Database not connected. Did you forget to call connect_to_mongo()?")
    return db["users"]

def get_doc_collection():
    if db is None:
        raise Exception("Database not connected. Did you forget to call connect_to_mongo()?")
    return db["docs"]

def get_db():
    if db is None:
        raise Exception("Database not connected. Did you forget to call connect_to_mongo()?")
    return db
