from fastapi import APIRouter, HTTPException
from models.user import UserCreate, UserLogin
from db.mongo import users_collection
from utils.security import hash_password, verify_password, create_token

router = APIRouter(prefix="/auth")

@router.post("/register")
def register(user: UserCreate):
    if users_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="User exists")

    users_collection.insert_one({
        "email": user.email,
        "password": hash_password(user.password)
    })

    return {"message": "User created"}

@router.post("/login")
def login(user: UserLogin):
    db_user = users_collection.find_one({"email": user.email})

    if not db_user or not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"sub": user.email})

    return {"access_token": token}