from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from typing import List
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from database import users_col
from schemas import UserCreate, UserUpdate, UserOut
from auth_utils import hash_password, doc_to_out, require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


def get_user_or_404(user_id: str):
    try:
        doc = users_col.find_one({"_id": ObjectId(user_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")
    return doc


@router.get("/users", response_model=List[UserOut])
def list_users(_=Depends(require_admin)):
    docs = users_col.find().sort("created_at", -1)
    return [doc_to_out(d) for d in docs]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, _=Depends(require_admin)):
    try:
        result = users_col.insert_one({
            "email":           body.email.lower().strip(),
            "hashed_password": hash_password(body.password),
            "first_name":      body.first_name,
            "last_name":       body.last_name,
            "role_title":      body.role_title,
            "role":            "user",
            "is_approved":     True,
            "created_at":      datetime.utcnow(),
        })
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Email already registered")
    doc = users_col.find_one({"_id": result.inserted_id})
    return doc_to_out(doc)


@router.put("/users/{user_id}/approve", response_model=UserOut)
def approve_user(user_id: str, _=Depends(require_admin)):
    doc = get_user_or_404(user_id)
    users_col.update_one({"_id": doc["_id"]}, {"$set": {"is_approved": True}})
    return doc_to_out(users_col.find_one({"_id": doc["_id"]}))


@router.put("/users/{user_id}/revoke", response_model=UserOut)
def revoke_user(user_id: str, _=Depends(require_admin)):
    doc = get_user_or_404(user_id)
    if doc.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Cannot revoke an admin account")
    users_col.update_one({"_id": doc["_id"]}, {"$set": {"is_approved": False}})
    return doc_to_out(users_col.find_one({"_id": doc["_id"]}))


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UserUpdate, _=Depends(require_admin)):
    doc = get_user_or_404(user_id)
    updates = body.model_dump(exclude_none=True)
    if "password" in updates:
        updates["hashed_password"] = hash_password(updates.pop("password"))
    if "email" in updates:
        updates["email"] = updates["email"].lower().strip()
    if updates:
        try:
            users_col.update_one({"_id": doc["_id"]}, {"$set": updates})
        except DuplicateKeyError:
            raise HTTPException(status_code=400, detail="Email already in use")
    return doc_to_out(users_col.find_one({"_id": doc["_id"]}))


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: str, _=Depends(require_admin)):
    doc = get_user_or_404(user_id)
    if doc.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Cannot delete an admin account")
    users_col.delete_one({"_id": doc["_id"]})
