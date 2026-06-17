from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))
db     = client[os.getenv("MONGO_DB", "ey_rag")]

users_col = db["users"]

# Unique index on email
users_col.create_index("email", unique=True)
