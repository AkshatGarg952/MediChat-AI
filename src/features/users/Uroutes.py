from fastapi import APIRouter, Depends
from .Uschema import UserCreate, UserLogin
from .Ucontroller import register_user, login_user
from src.database.db import get_user_collection 

router = APIRouter(prefix="/user", tags=["User"])

@router.post("/register")
async def register(user: UserCreate, user_collection=Depends(get_user_collection)):
    return await register_user(user, user_collection)

@router.post("/login")
async def login(user: UserLogin, user_collection=Depends(get_user_collection)):
    return await login_user(user, user_collection)
