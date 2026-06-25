from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"), serverSelectionTimeoutMS=5000)
db     = client[os.getenv("MONGO_DB", "ey_rag")]

users_col         = db["users"]
conversations_col = db["conversations"]

# Unique index on email
users_col.create_index("email", unique=True)
# Index for fast per-user history queries ordered by time
conversations_col.create_index([("user_id", 1), ("timestamp", 1)])
