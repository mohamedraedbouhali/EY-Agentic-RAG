# EY Agentic RAG — TdR Intelligence

A RAG (Retrieval-Augmented Generation) system built for EY to search and analyze **Tender Reference Documents (TdR)**. Users can ask questions in natural language and receive AI-generated answers grounded in the indexed PDF documents.

---

## Architecture

```
PDFs → pdfplumber → Chunker (300 words) → bge-small-en-v1.5 → ChromaDB
                                                                    ↓
User Query → Embed Query → Vector Search → Top 8 Chunks → Groq LLM → Answer
```

| Layer | Technology |
|---|---|
| Frontend | React + Vite |
| Backend | FastAPI (Python) |
| Database | MongoDB |
| Embeddings | BAAI/bge-small-en-v1.5 |
| Vector Store | ChromaDB |
| LLM | Groq — llama-3.1-8b-instant |

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- MongoDB running on `localhost:27017`
- A [Groq API key](https://console.groq.com)

---

## Setup

### 1. Clone and configure environment

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env`:

```env
MONGO_URL=mongodb://localhost:27017
MONGO_DB=ey_rag
GROQ_API_KEY=your_groq_api_key_here
```

### 2. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
```

---

## Index Documents (one-time)

Place your PDF files in `backend/data/`, then run:

```bash
cd backend
python index_documents.py
```

This will extract text from all PDFs, split into chunks, generate embeddings, and store them in ChromaDB. You should see:

```
✅ Done! 2841 chunks indexed from 92 documents.
```

> Only needs to be run once. If you add new PDFs, run it again.

---

## Start the Project

Open **two terminals**:

**Terminal 1 — Backend**
```bash
cd backend
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.  
On first startup, the embedding model loads (~15s) — wait for:
```
✅ Embedding model warmed up
```

**Terminal 2 — Frontend**
```bash
cd frontend
npm run dev
```

The app will be available at `http://localhost:5173`.

---

## Default Accounts

| Role | Email | Password |
|---|---|---|
| Admin | admin@gmail.com | admin |
| User | user@gmail.com | user |

> New user registrations require admin approval before they can log in.

---

## Features

- **User Dashboard** — natural language search over indexed TdR PDFs with AI-generated answers and source citations
- **Admin Dashboard** — manage users (approve, revoke, create, delete), view all accounts
- **Profile editing** — update name and profile photo for both roles
- **Mobile responsive** — works on desktop and mobile

---

## Project Structure

```
ey-agentic-rag/
├── backend/
│   ├── data/               ← Place PDF files here
│   ├── chroma_db/          ← ChromaDB vector store (auto-generated)
│   ├── rag/
│   │   ├── extractor.py    ← PDF text extraction (pdfplumber)
│   │   ├── chunker.py      ← Text chunking (300 words, 30 overlap)
│   │   ├── embedder.py     ← Sentence embeddings (bge-small-en-v1.5)
│   │   ├── vector_store.py ← ChromaDB storage and search
│   │   └── generator.py    ← LLM answer generation (Groq)
│   ├── routers/
│   │   ├── auth.py         ← Login, register, profile
│   │   ├── admin.py        ← User management
│   │   └── search.py       ← RAG search endpoint
│   ├── main.py             ← FastAPI app entry point
│   ├── index_documents.py  ← One-time indexing script
│   ├── requirements.txt
│   └── .env
└── frontend/
    ├── src/
    │   ├── pages/
    │   │   ├── UserDashboard.jsx
    │   │   └── AdminDashboard.jsx
    │   ├── components/
    │   │   └── ProfileModal.jsx
    │   ├── context/
    │   │   └── AuthContext.jsx
    │   └── services/
    │       └── api.js
    └── package.json
```
