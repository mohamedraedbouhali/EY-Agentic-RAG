<div align="center">

# EY Agentic RAG — TdR Intelligence

### Natural-language search over Tender Reference Documents, grounded in real citations.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-Vite-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Database-47A248?style=flat-square&logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20Store-FF6F00?style=flat-square)](https://www.trychroma.com/)
[![Groq](https://img.shields.io/badge/Groq-LLaMA%203.1-F55036?style=flat-square)](https://console.groq.com/)
[![Status](https://img.shields.io/badge/status-internal-lightgrey?style=flat-square)]()
[![Made for](https://img.shields.io/badge/made%20for-EY-FFE600?style=flat-square)]()

54 documents · recursive character chunking (800 chars · 150 overlap) · TDR auto-classifier · IBM Granite multilingual embeddings · sub-second retrieval

</div>

---

## Table of Contents

- [What is this?](#what-is-this)
- [Architecture](#architecture)
- [RAG Pipeline Details](#rag-pipeline-details)
- [Evaluation](#evaluation)
- [Quickstart](#quickstart)
- [Default Accounts](#default-accounts)
- [Features](#features)
- [Project Structure](#project-structure)
- [Suivi des échanges (Changelog)](#suivi-des-échanges-changelog)

---

## What is this?

A **Retrieval-Augmented Generation (RAG)** system built for **EY** to search and analyze **Tender Reference Documents (TdR)** at scale. Instead of manually digging through dozens of PDF tenders, ask a question in plain language — French or English — and get an AI-generated answer **grounded directly in the indexed documents**, with the source page and file cited so every answer can be verified.

> **Why it matters:** TdR documents are dense, repetitive, and scattered across many files. This system turns that pile of PDFs into a searchable knowledge base that answers questions in seconds instead of hours.

---

## Architecture

A bird's-eye view of how a PDF becomes a searchable, cited answer:

```
PDF files
   |
   v
[step1 — Extractor]   pdfplumber + EasyOCR (OCR fallback for scanned pages)
   |
   v
[step2 — Metadata]    country · region · donor · domain · year
                       + TDR classifier (is_tdr · tdr_confidence · tdr_label)
   |
   v
[step3 — Chunker]     Recursive Character Splitter
                       separators: \n\n → \n → ". " → " " → ""
                       chunk_size = 800 chars · overlap = 150 chars
   |
   v
[step4 — Embedder]    IBM Granite (granite-embedding-278m-multilingual)
   |
   v
[step5 — ChromaDB]    cosine / HNSW index  <----+
                                                  |
User Query                                        |
   |                                              |
   v                                              |
[step4 — Embedder]    same Granite model          |
   |                                              |
   v                                              |
[Vector Search]       top 8 chunks · score >= 0.40 · optional only_tdr filter
   |
   v
[step6 — Groq LLM]   llama-3.1-8b-instant
   |
   v
Answer + Citations + TDR badge + Similar Missions
```

### Tech Stack

| Layer | Technology | Role |
|---|---|---|
| Frontend | React + Vite | User & Admin dashboards |
| Backend | FastAPI (Python) | API, auth, orchestration |
| Database | MongoDB | Users, accounts, metadata |
| Embeddings | IBM Granite 278M multilingual | Turns text into searchable vectors |
| Vector Store | ChromaDB (cosine / HNSW) | Fast similarity search |
| LLM | Groq — llama-3.1-8b-instant | Generates grounded answers |
| OCR | EasyOCR (fr + en) + pdf2image | Extracts text from scanned pages |

---

## RAG Pipeline Details

### 1 — Extraction (`rag/step1_extractor.py`)

Uses **pdfplumber** to read each PDF page by page.

- Plain text is extracted per page and tagged with a `[Page N]` marker.
- Tables are detected separately, converted to Markdown pipe format, and appended with a `[Tableau N – Page N]` label.
- **OCR fallback**: if pdfplumber finds no text on a page (scanned/image-only), the page is rasterised at 300 DPI via pdf2image + Poppler and passed to **EasyOCR** (French + English). The recovered text is merged back transparently.
- Documents with fewer than 20 words after extraction are skipped.

### 2 — Metadata & TDR Classification (`rag/step2_metadata.py`)

Every document is analysed (filename + first 15 000 characters) to extract:

| Field | Detection method |
|---|---|
| Country | Keyword match on country names + capitals |
| Region | Derived from detected country |
| Donor | Keyword match on donor acronyms & names |
| Domain | Keyword match on sector vocabulary |
| Year | Regex on filename + first 3 000 characters |
| `is_tdr` | Multi-tier scoring — see below |
| `tdr_confidence` | Normalised score in \[0, 1\] |
| `tdr_label` | Human-readable: *TDR confirmé / Probable TDR / Indéterminé / Non-TDR* |

**TDR classifier scoring:**

| Signal tier | Where checked | Points |
|---|---|---|
| Filename contains TDR keyword (tdr, tor, termes, cahier…) | filename | +15 |
| Strong signal ("termes de référence", "scope of work", "appel à candidatures"…) | first 3 000 chars | +7 each |
| Strong signal found beyond title area | first 8 000 chars | +4 each |
| Structure signal (section headers: "livrables attendus", "profil du consultant"…) | first 15 000 chars | +2 each |
| Non-TDR signal ("rapport final", "annual report", "seminar", "user manual"…) | first 3 000 chars | −8 each |
| Non-TDR signal beyond title area | first 15 000 chars | −3 each |

`is_tdr = True` when score ≥ 10. `tdr_confidence = min(1.0, score / 30)`.

### 3 — Chunking (`rag/step3_chunker.py`)

**Strategy: Recursive Character Splitting**

| Parameter | Value |
|---|---|
| `CHUNK_SIZE` | 800 characters (~130 words) |
| `OVERLAP` | 150 characters (~25 words) |
| Separators (priority order) | `\n\n` → `\n` → `". "` → `"? "` → `"! "` → `"; "` → `" "` → `""` |

The splitter tries paragraph breaks (`\n\n`) first. Any piece still larger than `CHUNK_SIZE` is recursed with the next separator, down to raw characters as a last resort. Small pieces are then greedily merged back up to `CHUNK_SIZE`, carrying the last 200 characters of each chunk into the start of the next (the overlap). This ensures a TDR section and its bullet list stay in the same chunk rather than being split arbitrarily.

### 4 — Embedding (`rag/step4_embedder.py`)

Model: **ibm-granite/granite-embedding-278m-multilingual**

- Multilingual — handles French and English documents seamlessly
- Embeddings are L2-normalized before storage
- Same model used for both indexing and query embedding

### 5 — Vector Store (`rag/step5_vector_store.py`)

**ChromaDB** with persistent storage in `backend/chroma_db/`.

- Similarity metric: cosine (via HNSW index)
- Returns the top 8 most similar chunks per query
- Score: `1 − cosine_distance`
- Minimum relevance threshold of **0.40** — chunks below this are discarded
- Stored metadata per chunk: `source`, `page`, `chunk_index`, `country`, `region`, `domain`, `donor`, `year`, `is_tdr`, `tdr_confidence`, `tdr_label`
- Supports `only_tdr` filter: when enabled, restricts retrieval to chunks from TDR-classified documents only

At search time, selected filters are passed to ChromaDB as a `where` clause (e.g. `{"$and": [{"domain": {"$in": ["Santé"]}}, {"is_tdr": {"$eq": true}}]}`).

### 6 — Generation (`rag/step6_generator.py`)

Retrieved chunks + conversation history (last 8 messages) are sent to **Groq LLaMA 3.1 8B**. The LLM is strictly instructed to answer only from the provided chunks.

### 7 — Similar Missions, TDR Badge & Profile Extraction (`routers/search.py`)

Each search response includes:
- **TDR badge** — `is_tdr`, `tdr_confidence`, `tdr_label` on every source and similar mission
- **Similar Missions** — other documents that scored above threshold
- **Profiles & Competencies** — keyword-extracted consultant requirements from the source chunks

The `Filters` model accepts `only_tdr: bool` — set to `true` to restrict the search to confirmed TDR documents only.

---

## Models & Configuration History

### Embedding Models

| Model | Params | Dimensions | Max Tokens | Languages | Status |
|---|---|---|---|---|---|
| `BAAI/bge-m3` | 570M | 1024 | 8192 | 100+ | Replaced (v1) |
| `ibm-granite/granite-embedding-278m-multilingual` | 278M | 768 | 512 | Multilingual | **Current** |

> **BGE-M3** is recommended for production — better French retrieval, 8192-token context, and hybrid dense+sparse search. Switch by changing `MODEL_NAME` in `step4_embedder.py` then re-indexing.

### LLM (Generation)

| Model | Provider | Params | Speed | Status |
|---|---|---|---|---|
| `llama-3.1-8b-instant` | Groq (LPU) | 8B | ~600 tok/s | **Current** |

### Chunking Configuration History

| Version | CHUNK_SIZE | OVERLAP | ~Words/chunk | Estimated chunks | Notes |
|---|---|---|---|---|---|
| v1 (original) | 1500 chars | 200 chars | ~250 words | ~450 | Rich context, less precise |
| v2 | 500 chars | 100 chars | ~83 words | ~1350 | Too granular, thin context |
| **v3 (current)** | **800 chars** | **150 chars** | **~130 words** | **~850** | **Best balance for TdR docs** |

---

## Evaluation

The `backend/metrics.py` script evaluates the full RAG pipeline and writes results to `backend/metrics_results.json`.

### Metrics computed

| Category | Metric | Requires |
|---|---|---|
| **Retrieval** | `coverage_rate` — % of queries with at least one result above threshold | — |
| | `no_answer_rate` — % of queries returning "not found" | — |
| | `avg_top1_score` — mean cosine similarity of the best chunk | — |
| | `avg_mean_score` — mean cosine similarity across all retrieved chunks | — |
| | `score_distribution` — histogram across 4 score bands | — |
| | `tdr_ratio_in_results` — % of retrieved sources classified as TDR | — |
| | `hit_rate_at_K` — % of queries where a relevant source is in top K | ground-truth sources |
| | `mrr` — Mean Reciprocal Rank of the first relevant source | ground-truth sources |
| | `precision_at_K` — fraction of top-K results that are relevant | ground-truth sources |
| **Generation** | `avg_faithfulness` (1–5) — answer grounded in context, no hallucination | LLM judge |
| | `avg_relevancy` (1–5) — answer addresses the question | LLM judge |
| **Latency** | `avg_retrieval_ms`, `avg_generation_ms`, `avg_total_ms` | — |

### Usage

```bash
cd backend

# Default — built-in 10-query test set, LLM judge enabled
python metrics.py

# Skip LLM judge (faster, no extra Groq calls)
python metrics.py --no-llm-judge

# Custom test set (JSON file)
python metrics.py --test my_test.json

# Experiment with retrieval settings
python metrics.py --top-k 5 --min-score 0.45

# Custom output file
python metrics.py --output eval_june.json
```

### Custom test set format

```json
[
  {"query": "Quels sont les livrables attendus?"},
  {
    "query": "Who is the donor for this project?",
    "relevant_sources": ["TDR_Mali_2023.pdf"]
  }
]
```

Adding `relevant_sources` unlocks `hit_rate`, `mrr`, and `precision_at_K`. Without it, only automatic metrics (no labelling needed) are computed.

### Output — `metrics_results.json`

```json
{
  "evaluation_date": "2026-06-19T16:00:00",
  "config": { "top_k": 8, "min_score_threshold": 0.4, ... },
  "retrieval": {
    "coverage_rate": 0.9,
    "no_answer_rate": 0.1,
    "avg_top1_score": 0.6213,
    "score_distribution": { "0.0-0.3": 1, "0.3-0.5": 2, "0.5-0.7": 5, "0.7-1.0": 2 }
  },
  "generation": {
    "avg_faithfulness": 4.3,
    "avg_relevancy": 3.9
  },
  "latency": { "avg_retrieval_ms": 48, "avg_generation_ms": 1150, "avg_total_ms": 1198 },
  "per_query_results": [ ... ]
}
```

---

## Quickstart

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | Python 3.14 tested and working |
| Node.js 18+ | |
| MongoDB | running on `localhost:27017` |
| Groq API key | [console.groq.com](https://console.groq.com) |
| Poppler | path set in `rag/extractor.py` (for OCR) |

### 1 — Configure environment

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

### 2 — Install dependencies

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 3 — Classify and filter TDR documents

Before indexing, run the TDR classifier to remove non-TDR files:

```bash
python check_tdrs.py --yes
```

Non-TDR files are moved to `data/not_tdrs/`. Scanned PDFs (no text) stay in `data/` and are handled by OCR during indexing.

### 4 — Index documents (one-time)

Place PDF files in `data/`, then:

```bash
cd backend
python index_documents.py
```

Re-run if you add new PDFs or change the embedding model (choose `y` to re-index from scratch).

### 5 — Launch

**Terminal 1 — Backend:**
```bash
cd backend
uvicorn main:app --reload
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`.

### 6 — Evaluate (optional)

```bash
cd backend
python metrics.py --no-llm-judge   # fast, no LLM judge
python metrics.py                  # full evaluation with Groq judge
```

Results are saved to `backend/metrics_results.json`.

---

## Default Accounts

| Role | Email | Password |
|---|---|---|
| Admin | `admin@gmail.com` | `admin` |
| User | `user@gmail.com` | `user` |

New registrations require admin approval before login.

---

## Features

| Feature | Description |
|---|---|
| Conversational search | Natural language Q&A with persistent chat interface |
| Query suggestions | Pre-built suggestion chips |
| Smart filters | Filter by country, region, donor, domain, year — auto-detected at indexing |
| `only_tdr` filter | Restrict search to TDR-classified documents only |
| TDR auto-classifier | Multi-tier scorer (filename + strong signals + structure signals − anti-signals) assigns `is_tdr`, `tdr_confidence`, `tdr_label` to every document at indexing |
| TDR badge in results | Every source and similar mission shows its TDR classification and confidence |
| Conversation memory | Follow-up questions understand prior context (last 4 turns) |
| OCR support | Scanned PDF pages processed automatically with EasyOCR |
| Source citations | Every answer links to the exact file and page |
| Profile & competency extraction | Consultant profiles and required skills surfaced automatically |
| Similar missions | Related TdR documents shown alongside each answer |
| Relevance threshold | 0.40 cosine-similarity floor filters irrelevant chunks |
| Recursive chunking | Structure-aware splitter keeps paragraphs and sections intact |
| Admin Dashboard | Manage users (approve, revoke, create, delete) |
| RAG evaluation script | `metrics.py` computes coverage, MRR, hit rate, faithfulness, relevancy, latency — outputs `metrics_results.json` |

---

## Project Structure

```
ey-agentic-rag/
├── data/                          <- Place PDF files here
│   └── not_tdrs/                  <- Non-TDR files moved here by check_tdrs.py
├── check_tdrs.py                  <- Pre-indexing TDR file sorter (optional)
├── backend/
│   ├── chroma_db/                 <- ChromaDB vector store (auto-generated)
│   ├── rag/
│   │   ├── step1_extractor.py     <- PDF text + table extraction + EasyOCR fallback
│   │   ├── step2_metadata.py      <- Country/region/donor/domain/year + TDR classifier
│   │   ├── step3_chunker.py       <- Recursive Character Splitter (800 chars, 150 overlap)
│   │   ├── step4_embedder.py      <- IBM Granite multilingual embeddings
│   │   ├── step5_vector_store.py  <- ChromaDB storage, search, TDR filter, score threshold
│   │   └── step6_generator.py     <- LLM answer generation with conversation memory
│   ├── routers/
│   │   ├── auth.py                <- Login, register, profile
│   │   ├── admin.py               <- User management
│   │   └── search.py              <- RAG search, filters (incl. only_tdr), TDR badge, similar missions
│   ├── main.py                    <- FastAPI app entry point
│   ├── index_documents.py         <- One-time indexing script (shows TDR badge per document)
│   ├── metrics.py                 <- RAG evaluation script (retrieval + generation + latency)
│   ├── filters_cache.json         <- Available filter values (auto-generated)
│   ├── metrics_results.json       <- Evaluation output (auto-generated by metrics.py)
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

---

## Suivi des échanges (Changelog)

This section tracks all significant changes made during development sessions.

---

### Session — 2026-06-21

**Problèmes résolus**

| # | Problème | Cause | Solution |
|---|---|---|---|
| 1 | "Failed to fetch" sur toutes les recherches | Clé GROQ_API_KEY invalide (401) — l'exception non capturée remontait jusqu'à Uvicorn, qui renvoyait un 500 `text/plain` sans headers CORS, causant un rejet CORS dans le navigateur | Ajout de `try/except` autour de `embed_query` et `search` dans `routers/search.py` ; remplacement de `.dict()` (déprécié Pydantic v2) par `.model_dump()` |
| 2 | Taille des chunks inadaptée | Chunk size à 1500 chars (trop large) puis 500 chars (trop granulaire) | Fixé à **800 chars / 150 overlap** après analyse du compromis précision vs contexte pour les TdR |

**Améliorations apportées**

| Fichier | Changement |
|---|---|
| `routers/search.py` | Wrapping `embed_query` et `search` dans `try/except` → toutes les erreurs retournent désormais des `HTTPException` JSON avec headers CORS corrects |
| `rag/step3_chunker.py` | `CHUNK_SIZE` : 1500 → 500 → **800** ; `OVERLAP` : 200 → 100 → **150** |
| `README.md` | Ajout section **Models & Configuration History** avec tableaux embedding models, LLM, et historique des configs de chunking |

---

### Session — 2026-06-19 (update 3)

**Améliorations apportées**

| Fichier | Changement |
|---|---|
| `metrics.py` (nouveau) | Script d'évaluation complet du pipeline RAG. Calcule automatiquement : `coverage_rate`, `no_answer_rate`, `avg_top1_score`, `score_distribution`, `tdr_ratio_in_results`, `hit_rate@K`, `mrr`, `precision@K` (si sources annotées), `faithfulness` et `relevancy` via LLM judge Groq (1–5), et latences retrieval/génération/total. Résultats exportés dans `metrics_results.json`. |
| `README.md` | Ajout de la section **Evaluation** avec description des métriques, format du test set, exemple de sortie JSON, et étape 6 dans le Quickstart. Mise à jour du nombre de documents (54), correction des noms de fichiers step-prefixés. |

**Métriques disponibles**

- **Sans annotation** : coverage rate, no-answer rate, scores de similarité, distribution des scores, ratio TDR dans les résultats, latences
- **Avec annotation** (`relevant_sources` dans le test set) : Hit Rate@K, MRR, Precision@K
- **Avec LLM judge** : Faithfulness (1–5), Relevancy (1–5)

---

### Session — 2026-06-19 (update 2)

**Améliorations apportées**

| Fichier | Changement |
|---|---|
| `rag/step2_metadata.py` | Ajout du **classificateur TDR** : système de scoring multi-niveaux (filename +15, signaux forts +7/+4, signaux structurels +2, anti-signaux −8/−3). Retourne `is_tdr`, `tdr_confidence`, `tdr_label`, `tdr_score` pour chaque document. |
| `rag/step3_chunker.py` | Remplacement du découpage fixe (500 mots) par un **Recursive Character Splitter** : séparateurs `\n\n → \n → ". " → " " → ""`, `CHUNK_SIZE = 1 500 chars`, `OVERLAP = 200 chars`. Préserve les limites naturelles de paragraphes et de phrases. |
| `rag/step5_vector_store.py` | Stockage de `is_tdr`, `tdr_confidence`, `tdr_label` dans les métadonnées ChromaDB. Support du filtre `only_tdr` (`{"is_tdr": {"$eq": true}}`). Retour de ces champs dans les résultats de recherche. |
| `routers/search.py` | Ajout de `only_tdr: bool` dans le modèle `Filters`. Retour de `is_tdr`, `tdr_confidence`, `tdr_label` dans `sources` et `similar_missions`. |
| `index_documents.py` | Affichage d'un badge `[TDR XX%]` ou `[NON-TDR]` par document lors de l'indexation, avec score TDR et label. Résumé final TDR vs non-TDR avec liste des fichiers non-TDR. |

---

### Session — 2026-06-19 (update 1)

**Problèmes résolus**

| # | Problème | Cause | Solution |
|---|---|---|---|
| 1 | Site bloqué sur "Loading..." au démarrage | `fetch /auth/me` sans timeout — si le backend était lent ou MongoDB down, la page restait bloquée indéfiniment | Ajout d'un `AbortController` avec timeout 10s sur tous les appels API (60s pour les recherches) dans `api.js` |
| 2 | ChromaDB crash (exit code 5) au lancement du script d'indexation | La base `chroma_db/` était corrompue (SQLite de 540 octets, issu d'une initialisation partielle) | Suppression du dossier `chroma_db/` et recréation propre |
| 3 | Script d'indexation crash (UnicodeEncodeError) | Emojis (`→`, `⚠`) incompatibles avec l'encodage cp1252 de la console Windows | Remplacement de tous les emojis par des équivalents ASCII dans `extractor.py` et `index_documents.py` |
| 4 | MongoDB timeout long (30s) quand la base est inaccessible | `MongoClient` par défaut attend 30 secondes avant d'échouer | Ajout de `serverSelectionTimeoutMS=5000` dans `database.py` |

**Améliorations apportées**

| Fichier | Changement |
|---|---|
| `check_tdrs.py` | Script entièrement réécrit (v2) : classification TDR plus stricte avec 3 niveaux de keywords (STRONG / CONTEXT / WEAK), scan sur 5 pages, logique de scoring en 4 règles, flag `--yes` pour automatisation, déplacement automatique des non-TDR vers `data/not_tdrs/` |
| `rag/metadata_extractor.py` | Fenêtre de scan étendue de 3 000 à **6 000 caractères** pour la détection pays/région/bailleur/domaine, et de 800 à **3 000 caractères** pour l'année |
| `rag/chunker.py` | Taille des chunks augmentée de 300 à **500 mots**, overlap de 30 à **100 mots** |
| `rag/embedder.py` | Modèle d'embedding remplacé : `BAAI/bge-m3` → **`ibm-granite/granite-embedding-278m-multilingual`** |
| `frontend/src/services/api.js` | Ajout d'un timeout global (10s) sur tous les appels `fetch`, 60s pour `/search/tdr` |
| `backend/database.py` | Ajout de `serverSelectionTimeoutMS=5000` sur la connexion MongoDB |

**Tri des documents**

- 100 PDFs analysés dans `data/`
- **54 TDR confirmés** conservés dans `data/`
- **36 non-TDR** déplacés dans `data/not_tdrs/` (35 hors-domaine + 1 PDF corrompu)
- **10 PDFs scannés** (sans texte extractible) conservés dans `data/` — traités par OCR lors de l'indexation

---

<div align="center">

Built for EY · RAG pipeline powered by IBM Granite, ChromaDB & Groq

</div>
