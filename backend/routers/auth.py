from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from database import users_col
from schemas import UserCreate, LoginRequest, Token, UserOut, ProfileUpdate
from auth_utils import hash_password, verify_password, create_token, doc_to_out, get_current_user
from pymongo.errors import DuplicateKeyError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(body: UserCreate):
    try:
        users_col.insert_one({
            "email":           body.email.lower().strip(),
            "hashed_password": hash_password(body.password),
            "first_name":      body.first_name,
            "last_name":       body.last_name,
            "role_title":      body.role_title,
            "role":            "user",
            "is_approved":     False,
            "created_at":      datetime.utcnow(),
        })
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Email already registered")
    return {"message": "Account created. Waiting for admin approval."}


@router.post("/login", response_model=Token)
def login(body: LoginRequest):
    doc = users_col.find_one({"email": body.email.lower().strip()})
    if not doc or not verify_password(body.password, doc["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not doc.get("is_approved") and doc.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Your account is pending admin approval")
    token = create_token(str(doc["_id"]))
    return {"access_token": token, "token_type": "bearer", "user": doc_to_out(doc)}


@router.get("/me", response_model=UserOut)
def me(current_user=Depends(get_current_user)):
    return doc_to_out(current_user)


@router.put("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, current_user=Depends(get_current_user)):
    updates = body.model_dump(exclude_none=True)
    if updates:
        users_col.update_one({"_id": current_user["_id"]}, {"$set": updates})
    return doc_to_out(users_col.find_one({"_id": current_user["_id"]}))
