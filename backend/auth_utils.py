from datetime import datetime, timedelta
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import users_col
from bson import ObjectId

SECRET_KEY   = "ey-agentic-rag-jwt-secret-2024"
ALGORITHM    = "HS256"
EXPIRE_HOURS = 24

bearer = HTTPBearer()


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(user_id: str) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(hours=EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def doc_to_out(doc: dict) -> dict:
    """Convert a MongoDB document to a UserOut-compatible dict."""
    return {
        "id":          str(doc["_id"]),
        "email":       doc.get("email", ""),
        "first_name":  doc.get("first_name", ""),
        "last_name":   doc.get("last_name", ""),
        "role_title":  doc.get("role_title", ""),
        "role":        doc.get("role", "user"),
        "is_approved": doc.get("is_approved", False),
        "created_at":  doc.get("created_at", datetime.utcnow()),
        "avatar":      doc.get("avatar", None),
    }


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    doc = users_col.find_one({"_id": ObjectId(user_id)})
    if not doc:
        raise HTTPException(status_code=401, detail="User not found")
    return doc


def require_admin(current_user=Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
