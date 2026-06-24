from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from database import users_col
from auth_utils import hash_password
from routers import auth, admin, search

app = FastAPI(title="EY Agentic RAG API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(search.router)


@app.on_event("startup")
def warmup():
    try:
        from rag.step4_embedder import embed_query
        embed_query("warmup")
        print("✅  Embedding model warmed up")
    except Exception as e:
        print(f"⚠️  Warmup skipped: {e}")


@app.on_event("startup")
def seed_admin():
    if not users_col.find_one({"email": "admin@gmail.com"}):
        users_col.insert_one({
            "email":           "admin@gmail.com",
            "hashed_password": hash_password("admin"),
            "first_name":      "Admin",
            "last_name":       "EY",
            "role_title":      "Administrator",
            "role":            "admin",
            "is_approved":     True,
            "created_at":      datetime.utcnow(),
        })
        print("✅  Admin seeded → admin@gmail.com / admin")

    if not users_col.find_one({"email": "user@gmail.com"}):
        users_col.insert_one({
            "email":           "user@gmail.com",
            "hashed_password": hash_password("user"),
            "first_name":      "Test",
            "last_name":       "User",
            "role_title":      "Consultant",
            "role":            "user",
            "is_approved":     True,
            "created_at":      datetime.utcnow(),
        })
        print("✅  User seeded → user@gmail.com / user")


@app.get("/")
def root():
    return {"status": "ok", "api": "EY Agentic RAG"}
