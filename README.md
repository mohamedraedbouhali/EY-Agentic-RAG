<div align="center">

# EY Agentic RAG — TdR Intelligence

### Natural-language search over Tender Reference Documents, grounded in real citations.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-Vite-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Database-47A248?style=flat-square&logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20Store-FF6F00?style=flat-square)](https://www.trychroma.com/)
[![Groq](https://img.shields.io/badge/Groq-LLaMA%203.3%2070B-F55036?style=flat-square)](https://console.groq.com/)
[![Status](https://img.shields.io/badge/status-internal-lightgrey?style=flat-square)]()
[![Made for](https://img.shields.io/badge/made%20for-EY-FFE600?style=flat-square)]()

54 documents · structure-aware chunking (512 tokens, table & bullet safe) · OCR word de-gluing · BGE-M3 multilingual embeddings · TDR auto-classifier · named-document detection · regression test suite

</div>

---

## Table of Contents

- [What is this?](#what-is-this)
- [Architecture](#architecture)
- [RAG Pipeline — Step by Step](#rag-pipeline--step-by-step)
- [Testing](#testing)
- [Evaluation](#evaluation)
- [Quickstart](#quickstart)
- [Default Accounts](#default-accounts)
- [Features](#features)
- [Known Limits](#known-limits)
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
[step1 — Extractor]   pymupdf4llm → structured Markdown (headings, tables, [Page N])
                       RapidOCR integrated OCR for scanned PDFs (EasyOCR legacy fallback)
                       + OCR de-gluer (dictionary word segmentation)
   |
   v
[step2 — Metadata]    country · region · donor · domain · year
                       + TDR classifier (is_tdr · tdr_confidence · tdr_label)
                       all keyword matching accent-folded (OCR-proof)
   |
   v
[step3 — Chunker]     structure-aware fixed-size packing
                       512-token chunks · ~50-token overlap · tables & bullets atomic
   |
   v
[step4 — Embedder]    BAAI/bge-m3 (1024-dim, normalized) on cleaned text
   |
   v
[step5 — ChromaDB]    cosine / HNSW index  <-------------------+
                                                               |
User Query                                                     |
   |                                                           |
   v                                                           |
[named-document detection]  filename stem / tokens / title    |
   |                                                           |
   v                                                           |
[Vector Search]    targeted top-40 in named doc, else top-20   |
   + lexical rerank (accent-folded) + neighbor expansion ------+
   |
   v
[step6 — Groq LLM]   llama-3.3-70b-versatile (temp 0)
                      fallback ladder → llama-3.1-8b-instant
                      + table-row repair + strict reproduce-only prompt
   |
   v
Answer + Citations + TDR badge + Similar Missions
```

### Tech Stack

| Layer | Technology | Role |
|---|---|---|
| Frontend | React + Vite (react-markdown + remark-gfm) | User & Admin dashboards |
| Backend | FastAPI (Python) | API, auth, orchestration |
| Database | MongoDB | Users, accounts, conversations |
| Embeddings | BAAI/bge-m3 (570M, 1024-dim) | Turns text into searchable vectors |
| Vector Store | ChromaDB (cosine / HNSW) | Fast similarity search |
| LLM | Groq — llama-3.3-70b-versatile (fallback: llama-3.1-8b-instant) | Generates grounded answers |
| OCR | pymupdf4llm + RapidOCR (EasyOCR legacy fallback) | Extracts text from scanned pages |
| OCR cleanup | wordfreq (fr + en) dictionary segmentation | Splits OCR-glued words |

---

## RAG Pipeline — Step by Step

Every design decision below traces back to two realities: **the documents are messy** (scanned PDFs, merged-cell tables, mixed French/English) and **users ask for exact content** (sections, criteria, scoring grids), not vague summaries.

The pipeline runs in two phases:

- **Ingestion** (once, `python main.py`): Steps 1 → 5 — PDF → structured text → metadata → chunks → vectors → ChromaDB.
- **Query** (per question): Steps 5 → 7 — query → filtered vector search → LLM answer with citations.

### Who does what — libraries at a glance

| Library / Model | Step | Role |
|---|---|---|
| `pymupdf4llm` | 1 | **Main extractor** — text, headings AND tables, all as Markdown (RapidOCR built in for scans) |
| `pdfplumber` | 1 | Secondary — raw text page by page (page counting/numbering) |
| `pymupdf` (fitz) | 1 | Table rescue — cell-by-cell extraction of tables pymupdf4llm missed |
| `easyocr` + `pdf2image` + Poppler | 1 | Last-resort OCR chain (rarely fires) |
| `wordfreq` | 1 | fr+en frequency dictionary powering the OCR de-gluer |
| `re` + `unicodedata` | 2 | Rule-based metadata — no ML model at all |
| `tiktoken` | 3 | Token counting only (`cl100k_base`) — chunk sizes measured in tokens, not characters |
| `sentence-transformers` + **BAAI/bge-m3** | 4 | Embedding model (a neural transformer, but *not* an LLM — it cannot generate text) |
| `chromadb` | 5 | Embedded vector DB — vectors + text + metadata filters in one local folder |
| `groq` + **Llama 3.3 70B** (8B fallback) | 6 | **The only LLM in the whole pipeline** — writes the final answer |

Everything that *can* be deterministic code *is* deterministic code (parsing, filtering, chunking, retrieval). The expensive, non-deterministic LLM is reserved for the one task nothing else can do: reading excerpts and producing a faithful, human-readable answer.

### Step 1 — Extraction (`rag/step1_extractor.py`)

**Job:** PDF in → clean structured text out. Nothing else — no filters, no chunks yet. Everything downstream depends on this step: if extraction is bad, the best embedding model in the world is embedding garbage.

Turns each PDF into **structured Markdown** — not flat text — so that headings, tables and lists survive all the way to the LLM.

1. **Native pass** — `pymupdf4llm.to_markdown(page_chunks=True)` extracts each page as Markdown: headings become `#`/`######` lines, tables become `|cell|cell|` rows, and each page is prefixed with a `[Page N]` marker (used later for citations).
2. **OCR pass (scanned PDFs)** — if the native pass yields fewer than 200 characters, the PDF is a scan: pymupdf4llm's integrated **RapidOCR** re-extracts every page. A legacy **EasyOCR** path (pdf2image + Poppler) remains as last resort.
3. **Table fallback** — for pages where the Markdown pass produced *no* table, PyMuPDF's `find_tables()` output is serialized as `[Tableau p.N]` key-value blocks. Cell text is read via `tab.rows[r].cells[c]` (the per-row API — the flat `tab.cells` list excludes merged cells and maps positions incorrectly). Pages that already have a Markdown table are **never duplicated** — a second, differently-worded copy of the same table used to compete in retrieval and could win with a garbled version.
4. **OCR de-gluing** (`rag/ocr_degluer.py`) — RapidOCR frequently glues adjacent words (`conditionsgenerales`, `Termesdereferencepour`). A deterministic **dictionary segmenter** fixes this:
   - vocabulary = top-60k French + English words (wordfreq) **+ domain words harvested from the corpus's native PDFs** (so words like *transfrontalière* are known);
   - a token ≥12 letters that is not itself a known word is split **only if it decomposes entirely into known words** (unigram log-probability scoring; 2–3 letter parts restricted to a function-word whitelist);
   - anything that doesn't fully decompose — project codes, names, acronyms — passes through byte-for-byte, so content can never be corrupted;
   - the common OCR misread `I'` → `l'` (`I'elaboration` → `l'elaboration`) is normalized.
5. Documents with fewer than 20 words after all passes are skipped.

> **Why Markdown, not flat text?** Every later step relies on the structure: Step 3 keeps `|` table rows atomic and bullets on their own lines *because* the structure survived extraction; Step 6's answers reproduce tables correctly *because* rows were never flattened. Flat text loses all of that at minute one — unrecoverably.

### Step 2 — Metadata & TDR Classification (`rag/step2_metadata.py`)

**Job:** answer six questions about each document — *what country? region? domain? donor? year? is it actually a TDR?* These fields power the UI filters and are attached to every chunk in ChromaDB. No pages are re-read here: Step 2 receives the text Step 1 extracted and examines only its beginning (character windows: ~3 000 chars for title signals, 6 000 for country/donor/domain, 15 000 ≈ 5 pages for structure signals).

Every document (filename + first 15 000 characters) is analysed to extract filterable metadata. **All keyword matching is accent-folded on both sides** — OCR'd documents lose their accents (`reference` vs `référence`), and without folding, scanned TdRs scored near zero.

| Field | Detection method |
|---|---|
| Country / Region | Keyword match on country names + capitals; region derived from country |
| Donor | Keyword match on donor acronyms & names |
| Domain | Keyword match on sector vocabulary |
| Year | Regex on filename + first 3 000 characters |
| `is_tdr` / `tdr_confidence` / `tdr_label` | Multi-tier scoring (below) |

**TDR classifier scoring:** filename keyword +15 · definitive phrases +30 (max 2) · strong signals +7 (title) / +4 (head) · structure signals +2 · anti-signals −8 (title) / −3 (body). `is_tdr = score ≥ 10`, `tdr_confidence = min(1, score/40)`. The same phrase is worth more in the title area than in the body — titles rarely lie. Region is not detected at all: it is derived from the country via `REGION_MAP`.

> **Why only the first pages?** A document declares its identity at the start — title, country, donor, year are on the cover. Scanning the whole document would *hurt* precision: a 60-page project report mentioning "termes de référence" once in an annex would be misclassified as a TDR.

> **Why rules instead of an LLM?** Deterministic (same document → same filters, every run), free and instant (this runs at every re-index), and auditable (`tdr_matched` shows exactly which signals fired — a fix is one keyword added to a list, not a re-prompted black box). Trade-off accepted: countries absent from the keyword lists become `Inconnu`.

### Step 3 — Chunking (`rag/step3_chunker.py`)

**Job:** cut each document's Markdown into retrieval units. The chunk is **the unit of retrieval**: if an answer is split across a bad boundary or a table is mangled here, no embedding model or LLM can repair it later.

**Mode: structure-aware fixed-size packing** (tiktoken `cl100k_base` token counting).

| Parameter | Value | Role |
|---|---|---|
| `CHUNK_SIZE` | 512 tokens | Hard ceiling per chunk |
| `OVERLAP` | ~50 tokens | Trailing context repeated at the start of the next chunk |

> **Why 512 tokens / 50 overlap?** Too big → the embedding averages several topics and matches everything weakly. Too small → bullets get orphaned from their headings and become meaningless. 512 fits a typical TDR section; the 50-token overlap guarantees a sentence cut at a boundary exists whole in at least one chunk. Sizes are counted in tokens (not characters) because that is the unit embedding models and LLMs actually think in.

How a document becomes chunks:

1. **Sentence split** — text is split on sentence punctuation (`.` `!` `?`) and newlines… *except inside Markdown tables*: consecutive `|…|` lines are kept together as **one atomic block** with internal newlines preserved. A table flattened onto one line stops being a table — this was the root cause of garbled scoring-table answers.
2. **Oversized handling** — a table bigger than 512 tokens is split **between rows**, with the header row repeated at the top of every piece (each piece stays a valid, self-describing table). Oversized prose is hard-split by tokens.
3. **Greedy packing** — sentences are packed into chunks up to the 512-token ceiling. When rebuilding the chunk text, **structural lines keep their own line**: table rows, `#` headings, `-`/`•` bullets and `1.`/`1)` numbered items always start a new line (gluing bullets into one long line made the LLM drop items — the "missing bullets" bug).
4. **Overlap** — ~50 trailing tokens are carried into the next chunk so a sentence cut at a boundary can still be read in full; blocks larger than 100 tokens (tables) are never used as overlap to avoid near-duplicating them.
5. **Page tracking** — each chunk records the page of its *first* sentence by walking the `[Page N]` markers in order (deterministic, instead of "first marker that happens to appear inside the chunk").

> **Why not semantic chunking?** Earlier versions split chunks where BGE-M3 sentence-window similarity dropped (threshold 0.65/0.75). In practice, topic-similarity boundaries cut through tables and lists and destroyed document structure — and for an assistant whose job is to *reproduce* sections faithfully, structure fidelity matters more than topical purity. The structure-aware packer keeps every table row, bullet and heading intact, which measurably fixed wrong-answer cases.

### Step 4 — Embedding (`rag/step4_embedder.py`)

**Job:** turn each chunk into a **vector** that captures its *meaning*, so that "profil du consultant" can find a chunk saying "qualifications requises de l'expert" — zero shared words, same direction in vector space. This is what makes the search semantic instead of keyword-based.

Model: **BAAI/bge-m3** — 570M params, 1024-dim vectors, 8192-token context, 100+ languages (French/English handled natively).

> **Why BGE-M3?** (1) **Truly multilingual** — French queries and English chunks share one vector space; a monolingual model would cut the corpus in half. (2) **8 192-token input** — 512-token chunks never truncate. (3) **Strong multilingual retrieval quality while running locally on CPU** — free, no rate limits, no document text leaving the machine. It replaced IBM Granite after comparison on this corpus (see [history](#models--configuration-history)). Note: changing the embedding model means a **full re-index** — old chunk vectors and new query vectors would live in incompatible spaces.

- Before embedding, chunk text is **cleaned** so the vector represents pure content: `[Page N]`/`[Tableau…]` markers, table pipes, HTML artifacts (`<br>`, `<!-- picture text -->`, `<u>`…), heading hashes and bold markers are stripped.
- Embeddings are **L2-normalized**; the same model embeds queries at search time, so cosine similarity is a valid comparison.
- The stored chunk text keeps its full structure (tables, bullets) — only the *embedded* copy is cleaned.

### Step 5 — Vector Store & Retrieval (`rag/step5_vector_store.py` + `routers/search.py`)

**Job:** the meeting point of the pipeline — Step 3's text, Step 4's vectors and Step 2's filters live side by side, so one query can ask *"closest in meaning, but only within these filters."*

**ChromaDB** (persistent, `backend/chroma_db/`, cosine/HNSW). Stored per chunk: text + `source`, `page`, `chunk_index`, `country`, `region`, `domain`, `donor`, `year`, `is_tdr`, `tdr_confidence`, `tdr_label`.

> **Why ChromaDB (not Pinecone / FAISS / pgvector)?** ~900 chunks on one machine. Chroma is embedded like SQLite — a local folder, zero infrastructure — and natively combines vector search with metadata `where` filtering, which is exactly the feature set the UI filters need. Pinecone is paid server infrastructure this scale doesn't justify; raw FAISS stores only vectors and filtering would have to be built by hand.

**Filter pre-count guard** — before querying, the store counts how many chunks match the `where` clause and caps `n_results` accordingly; zero matches returns an honest empty result. (ChromaDB raises when `top_k` exceeds the match count, and the old error handler silently retried *without* filters — "Tunisie only" quietly returned every country.)

A query goes through this retrieval pipeline:

1. **Named-document detection** — three accent-folded strategies, in order:
   - *stem phrase*: the whole filename stem appears in the query (catches short names like `COM N° 01 DC`, `tdr-3`);
   - *tokens*: ≥2 distinctive query words (or one ≥15-char word) match a stored filename — generic TdR vocabulary (`termes`, `consultant`, …) never counts;
   - *title*: substring containment against a stored 600-char title sample per document (substring, not word-equality, so OCR-glued titles still match).
2. **Search** — if a document is named: top-40 chunks *inside that document* + top-5 general; otherwise top-20 general. User filters (country/region/domain/donor/year/`only_tdr`) become a ChromaDB `where` clause.
3. **Filtering** — score floor (0.20 named / 0.30 general, score = 1 − cosine distance), minimum-content check, and table-of-contents chunks are dropped (they match section-title queries but never contain the answer).
4. **Lexical rerank** — vector similarity is blended with exact-term overlap (accent-folded) + a bonus for exact section numbers ("1.1") so the chunk *containing* the asked section beats look-alike boilerplate.
5. **Neighbor expansion** — for the best hits, chunks `±1` in the same document are pulled in: sections often spill into the next chunk, which rarely matches the query wording on its own.
6. For a named-document question, **only that document's chunks** go to the LLM — other documents appear as "Similar Missions" instead of burning context budget.

### Step 6 — Generation (`rag/step6_generator.py`)

**Job:** the **only step that uses an LLM**. And the LLM is used as a *document extractor, not a writer* — it must reproduce what the documents say (verbatim, complete, in order), never summarize, embellish, or fill gaps from its own knowledge. For TDR consultation, a paraphrase that drops one bullet from "pièces constitutives du dossier" produces a rejected application in the real world.

Model: **Groq `llama-3.3-70b-versatile`**, temperature 0.

> **Why Groq + Llama, temperature 0?** Groq serves open models at extreme speed (answers feel instant) with a free tier — no per-token bill for an internal tool. Rate limits are tracked **per model**, so when the 70B's daily quota is exhausted the 8B fallback still has its own — a slightly weaker answer beats an error page. Temperature 0 because the task is extraction, not creativity: same question → same answer, maximum faithfulness to the excerpts. Privacy note: only the retrieved excerpts (≤ ~20k chars) + the question leave the machine per query; swapping Step 6 to a local LLM (e.g. Ollama) is a one-module change.

**Anti-hallucination layers:** (1) the prompt forbids outside knowledge and paraphrase; (2) temperature 0; (3) a fixed refusal sentence when the answer is not in the excerpts; (4) a post-generation hedge guard (below) so a confused half-answer never ships.

- **Context assembly** — best chunks fill a ~20 000-char budget, are re-sorted into natural document order, and *consecutive chunks are merged* (the ~50-token overlap is deduplicated) so a section reads as one continuous passage. Each excerpt is labeled `[Extrait i — Document — Page(s) n(-m)]`.
- **Strict prompt** — the LLM must *reproduce* the relevant passage: no paraphrase, no outside knowledge, every bullet in order, stop at the next heading, answer `"Cette information ne figure pas dans les documents fournis."` when absent, and cite `**Source :** file — Page n`.
- **Table-row repair** — the model tends to break table cells onto multiple lines despite instructions; a deterministic post-processor rejoins any `|…` row split across lines (remark-gfm only renders single-line rows).
- **Hedge guard** — answers containing hallucination-then-self-correction markers are replaced by the standard not-found sentence.
- **Rate-limit ladder** — Groq free-tier resilience: `70b (20k chars)` → 429/413 → `8b-instant (11.5k chars, 700 tokens)` → still too big → `8b-instant (6k chars, no history)`. History messages are truncated to 800 chars each — they only exist to resolve follow-up references.

### Step 7 — Response enrichment (`routers/search.py`)

Each response also carries: per-source **TDR badge** (`is_tdr`, confidence, label), **Similar Missions** (other high-scoring documents), keyword-extracted **profiles & competencies** (accent-folded matching), cleaned excerpts, and the full chunk list with scores for the "chunks utilisés" panel.

---

## Testing

`backend/test_pipeline.py` — the regression suite that locks in every structural guarantee (21 tests):

```bash
cd backend
python test_pipeline.py          # fast: chunker, tables, bullets, de-gluer, real-PDF checks
python test_pipeline.py --full   # + re-extracts all 54 PDFs, asserts zero flattened tables
```

Run it after **any** change to `rag/step1_extractor.py`, `rag/step3_chunker.py` or `rag/ocr_degluer.py`. It asserts, among others: tables keep one row per line, `/40` stays attached to its criteria row in the real scoring-table PDF, oversized tables split on row boundaries with headers repeated, bullets/headings keep their own lines, the de-gluer splits glued words but never touches names/codes/rare real words.

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
python metrics.py                  # full evaluation (LLM judge via Groq)
python metrics.py --no-llm-judge   # faster, no extra Groq calls
python metrics.py --test my_test.json --top-k 5 --min-score 0.45
```

Custom test set format — adding `relevant_sources` unlocks `hit_rate`, `mrr`, `precision_at_K`:

```json
[
  {"query": "Quels sont les livrables attendus?"},
  {"query": "Who is the donor?", "relevant_sources": ["TDR_Mali_2023.pdf"]}
]
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
| Poppler | path set in `rag/step1_extractor.py` (legacy OCR fallback only) |

### 1 — Configure environment

Create `backend/.env`:

```env
MONGO_URL=mongodb://localhost:27017
MONGO_DB=ey_rag
GROQ_API_KEY=your_groq_api_key_here
```

### 2 — Install dependencies

```bash
cd backend
pip install -r requirements.txt

cd ../frontend
npm install
```

### 3 — (Optional) Classify and sort TDR documents

```bash
python check_tdrs.py --yes    # moves non-TDR files to data/not_tdrs/
```

### 4 — Index documents

Place PDF files in `data/`, then:

```bash
cd backend
python main.py                # answer "y" to re-index from scratch
```

> ⚠️ **The backend server must be stopped during indexing** — it holds the ChromaDB files open. Re-run `main.py` whenever you add/replace PDFs or change extraction/chunking code.

### 5 — Launch

```bash
# Terminal 1 — Backend
cd backend
uvicorn app:app --reload

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Open `http://localhost:5173`.

### 6 — Verify (optional but recommended)

```bash
cd backend
python test_pipeline.py       # 21 regression tests
python metrics.py --no-llm-judge
```

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
| Named-document questions | "dans le tdr X…" targets that document — by filename (even short names like `COM N° 01 DC`), by distinctive tokens, or by the document's own title |
| Smart filters | Country, region, donor, domain, year — auto-detected at indexing |
| `only_tdr` filter | Restrict search to TDR-classified documents only |
| TDR auto-classifier | Multi-tier scorer assigns `is_tdr`, `tdr_confidence`, `tdr_label` to every document |
| Structure-safe chunking | Tables keep one row per line, bullets/headings keep their own lines — the LLM reproduces sections without dropping items |
| OCR support | Scanned PDFs processed with RapidOCR + dictionary de-gluing of joined words |
| Accent-proof retrieval | All matching accent-folded — accented queries find unaccented OCR text |
| Source citations | Every answer cites the exact file and page (page ranges for merged excerpts) |
| Conversation memory | Follow-up questions understand prior context (last 4 turns, truncated) |
| Profile & competency extraction | Consultant requirements surfaced automatically per source |
| Similar missions | Related TdR documents shown alongside each answer |
| Rate-limit resilience | 70B → 8B fallback ladder — an answer instead of an error page when Groq throttles |
| Regression test suite | `test_pipeline.py` — 21 tests locking in every structural guarantee |
| Admin Dashboard | Manage users (approve, revoke, create, delete) |
| RAG evaluation script | `metrics.py` — coverage, MRR, hit rate, faithfulness, relevancy, latency |

---

## Known Limits

Honest boundaries of the system — these are physics, not bugs:

| Limit | Detail | Workaround |
|---|---|---|
| Scanned **table grids** | OCR can scramble row/column structure of complex tables in photographed pages (e.g. ranking tables where a name lands mid-sentence in another column) | Source the native (digital) PDF |
| OCR **misreads** | Wrong letters (`Decentralisecs`) are kept as-is — the de-gluer never guesses | Better scans / native PDFs |
| Groq **free tier** | Daily token quota on the 70B model; heavy days degrade to the 8B fallback | Paid Groq tier for production |
| Login sessions | JWT tokens expire after 24h (`auth_utils.py: EXPIRE_HOURS`) | Log in again, or raise the constant |

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
│   │   ├── step1_extractor.py     <- pymupdf4llm Markdown + RapidOCR + table fallback + de-glue hook
│   │   ├── step2_metadata.py      <- Country/region/donor/domain/year + TDR classifier (accent-folded)
│   │   ├── step3_chunker.py       <- Structure-aware 512-token chunker (tables & bullets atomic)
│   │   ├── step4_embedder.py      <- BAAI/bge-m3 embeddings on cleaned text
│   │   ├── step5_vector_store.py  <- ChromaDB storage, search, filters, per-document search
│   │   ├── step6_generator.py     <- Groq 70B generation, fallback ladder, table-row repair
│   │   └── ocr_degluer.py         <- Dictionary segmentation of OCR-glued words (wordfreq fr+en)
│   ├── routers/
│   │   ├── auth.py                <- Login, register, profile (JWT, 24h expiry)
│   │   ├── admin.py               <- User management
│   │   └── search.py              <- Retrieval pipeline: named-doc detection, rerank, neighbors
│   ├── app.py                     <- FastAPI app entry point
│   ├── main.py                    <- Indexing script (extraction → metadata → chunks → embeddings)
│   ├── test_pipeline.py           <- Regression suite (21 tests; --full re-extracts all PDFs)
│   ├── metrics.py                 <- RAG evaluation script
│   ├── filters_cache.json         <- Available filter values (auto-generated at indexing)
│   ├── titles_cache.json          <- 600-char title samples for named-doc detection (auto-generated)
│   ├── requirements.txt
│   └── .env                       <- MONGO_URL, MONGO_DB, GROQ_API_KEY
└── frontend/
    ├── src/
    │   ├── pages/                 <- UserDashboard.jsx, AdminDashboard.jsx
    │   ├── components/            <- ProfileModal.jsx
    │   ├── context/               <- AuthContext.jsx
    │   └── services/              <- api.js
    └── package.json
```

---

## Models & Configuration History

### Embedding Models

| Model | Params | Dimensions | Max Tokens | Languages | Status |
|---|---|---|---|---|---|
| `ibm-granite/granite-embedding-278m-multilingual` | 278M | 768 | 512 | Multilingual | Replaced |
| `BAAI/bge-m3` | 570M | 1024 | 8192 | 100+ | **Current** |

### LLM (Generation)

| Model | Provider | Role | Status |
|---|---|---|---|
| `llama-3.1-8b-instant` | Groq (LPU) | Was primary; now rate-limit fallback | Fallback |
| `llama-3.3-70b-versatile` | Groq (LPU) | Primary generation model | **Current** |

### Chunking Configuration History

| Version | Strategy | CHUNK_SIZE | OVERLAP | Notes |
|---|---|---|---|---|
| v1–v3 | Recursive character | 500–1500 chars | 100–200 chars | Character-based experiments |
| v4 | Token-based recursive | 512 tokens | 100 tokens | Accurate token counting via tiktoken |
| v5–v6 | Semantic (BGE-M3) | 512 tokens | 50–100 tokens | Topic-aware splits (threshold 0.65–0.75) |
| **v7 (current)** | **Structure-aware fixed-size** | **512 tokens** | **~50 tokens** | **Semantic splitting removed: it cut through tables/lists and flattened structure, producing garbled answers. Tables & bullets are now atomic; oversized tables split by rows with headers repeated; big blocks never duplicated as overlap.** |

---

## Suivi des échanges (Changelog)

This section tracks all significant changes made during development sessions.

---

### Session — 2026-07-03 / 2026-07-04

**Refonte fiabilité : structure des réponses, OCR, détection de documents**

| Fichier | Changement |
|---|---|
| `rag/step3_chunker.py` | **Réécriture complète (v7)** : chunking structure-aware — les tableaux Markdown sont des blocs atomiques (une ligne par rangée), les tableaux > 512 tokens sont découpés **entre les lignes** avec l'en-tête répété, les puces/titres/énumérations gardent leur propre ligne, les gros blocs ne sont jamais dupliqués dans l'overlap, pages suivies déterministiquement. Corrige les tableaux de notation garbled (« /40 » détaché de ses critères) et les puces manquantes (WISEMED). |
| `rag/step1_extractor.py` | Blocs `[Tableau p.N]` en **fallback uniquement** (pages sans tableau Markdown) — supprime la copie dupliquée/garbled qui concurrençait la bonne version en retrieval. Mapping cellules corrigé : `tab.rows[r].cells[c]` (l'ancien indexage plat de `tab.cells` pointait sur les mauvaises cellules — vérifié empiriquement). Hook de de-gluing OCR. |
| `rag/ocr_degluer.py` (nouveau) | Segmentation dictionnaire des mots collés par l'OCR (`conditionsgenerales` → `conditions generales`) : wordfreq fr+en + vocabulaire du corpus natif, scoring log-probabilité, whitelist des mots-fonction 2-3 lettres, règle `I'` → `l'`. Ne touche jamais un token qui ne se décompose pas entièrement en mots connus. |
| `rag/step2_metadata.py` | **Accent-folding** de tous les signaux TDR — les documents scannés (sans accents) scoraient près de zéro. |
| `routers/search.py` | Accent-folding généralisé (rerank lexical, détection de documents, extraction profils). **Détection par stem de fichier** (« COM N° 01 DC », « tdr-3 »). Matching de titres par **containment de sous-chaîne** (résiste aux titres OCR collés). `top_k` 20 → 40 pour les documents nommés. Nettoyage des artefacts HTML dans les extraits. |
| `rag/step6_generator.py` | `_repair_table_rows` : rejoint les lignes de tableau que le LLM casse (remark-gfm exige une ligne par rangée). Étiquettes `Pages n-m` pour les extraits fusionnés. **Échelle anti-rate-limit** : 70B (20k) → 8B (11,5k, 700 tokens) → 8B (6k, sans historique) ; historique tronqué à 800 chars/message ; erreurs 413 gérées. Nettoyage `<u>/<sup>/<mark>`. |
| `rag/step4_embedder.py` | Nettoyage renforcé avant embedding : commentaires HTML, balises, `#`, `**`, backticks. |
| `rag/step5_vector_store.py` | `list_source_filenames` : limite 2 000 → 50 000 (la détection de documents nommés cessait silencieusement de voir des documents au-delà). |
| `main.py` | `_extract_title` : échantillon de 600 chars significatifs, blocs « picture text » (logos/tampons) exclus — les titres OCR étaient du bruit d'en-tête (« REPUBLIQUETUNISIENNE »). |
| `test_pipeline.py` (nouveau) | Suite de régression : 21 tests (chunker, tableaux, puces, de-gluer, PDF réel) + mode `--full` (ré-extraction des 54 PDFs, zéro tableau aplati). |
| `requirements.txt` | Ajout `wordfreq>=3.0`. |

**Problèmes résolus (vérifiés de bout en bout sur l'index final)**

| # | Problème | Cause | Solution |
|---|---|---|---|
| 1 | Tableau de notation garbled — « /40 » séparé de ses 4 critères diplômes | Chunker aplatissait le tableau sur une ligne + copie sérialisée garbled indexée en parallèle | Chunker table-aware + fallback-only + réparation des lignes LLM |
| 2 | Puces manquantes (3/7 conditions WISEMED) | Liste à puces collée en une seule ligne — le LLM perdait les limites d'items | Lignes structurelles préservées |
| 3 | Mauvais document cité (« score de diplôme » → gage-c012020 au lieu de Prototype-Tdr) | Titres OCR collés + matching mot-à-mot | Titres riches 600c sans logos + containment de sous-chaîne |
| 4 | « COM N° 01 DC » non détecté comme document nommé | Tokens trop courts (COM=3, 01=2, DC=2) sous le seuil de 6 chars | Détection par phrase-stem du nom de fichier |
| 5 | Erreurs Groq 413 en rouge dans l'UI | Budget fallback trop optimiste + historique complet envoyé | Échelle 3 niveaux + troncature historique |
| 6 | Réponses incomplètes/ratées sur documents scannés | Requêtes accentuées vs texte OCR sans accents + mots collés | Accent-folding partout + de-gluer |

**Limite documentée (non corrigeable côté logiciel)** : les grilles de tableaux scannés peuvent être mélangées par l'OCR (ex. « GRECO SARL » atterrit au milieu de la colonne Observations du COM N° 01 DC) — seule la version native du PDF corrige cela.

---

### Session — 2026-06-29

**Améliorations apportées**

| Fichier | Changement |
|---|---|
| `rag/step3_chunker.py` | `OVERLAP` réduit de 100 → **50 tokens** pour limiter le chevauchement entre chunks et réduire la redondance dans les résultats. `SIMILARITY_THRESHOLD` abaissé de 0.75 → **0.65** pour des découpages thématiques plus fins. |
| `rag/step1_extractor.py` | Refonte complète de `table_to_natural` : suppression du préfixe hardcodé "Modalité de paiement :" et du format "le montant X est de Y". Nouvelle logique : détection automatique de la ligne d'en-têtes (cellules sans `-` ni valeurs numériques `%/€`), formatage `Header : Valeur` pour chaque ligne de données. Gestion correcte des tableaux complexes multi-colonnes (ex. Article 9 ATDEPA). Ajout de `import re` en tête de fichier. |
| `backend/main.py` | Ajout de `_filter_chunks` : filtre les chunks parasites à l'indexation — ratio mots uniques < 35% et bigrammes répétés plus de 3 fois sont éliminés. Seuil de longueur minimum à **8 mots** (au lieu de 20). |
| `routers/search.py` | Seuil `MIN_SCORE` abaissé de 0.40 → **0.30** pour améliorer la couverture sur les documents courts. Seuil `_is_meaningful` abaissé de 20 → **8 mots** pour ne plus filtrer les tableaux courts (ex. paiement 30%/70%). |
| `frontend/src/pages/UserDashboard.jsx` | Ajout d'un **badge score** sur chaque carte source : affiche la similarité cosinus en % (ex. `87%`) à côté du numéro de page. |
| `frontend/src/pages/UserDashboard.module.css` | Ajout de `.sourceTopRight` (flex row, gap 6px) et `.sourceScore` (badge vert arrondi) pour le badge de score. |
| `backend/app.py` | Ajout de `http://localhost:3000` dans `allow_origins` CORS (port Docker frontend). Warmup de l'embedding model déplacé dans un thread background pour ne pas bloquer le démarrage. |

**Problèmes résolus**

| # | Problème | Cause | Solution |
|---|---|---|---|
| 1 | Table 30%/70% absente des réponses (EBSOMED) | Chunk de ~14 mots filtré par le seuil `_is_meaningful` à 20 mots + format `table_to_natural` peu lisible | Seuil abaissé à 8 mots + nouveau format `Key : Value` sans préfixe hardcodé |
| 2 | Chunks parasites saturant les résultats | Chunks répétant "Modalité de paiement" des dizaines de fois rankés haut sur requêtes de paiement | `_filter_chunks` avec ratio mots uniques + détection bigrammes répétés |
| 3 | Article 9 ATDEPA (tableau multi-colonnes) sans contenu dans la réponse | `table_to_natural` traitait tous les tableaux à 2 colonnes comme des tableaux paiement, produisant du texte incohérent | Détection d'en-têtes + formatage `{Header} : {Valeur}` généralisé |
| 4 | Multiples instances uvicorn sur le port 8000 | Processus Python orphelins d'anciennes sessions | `Stop-Process` sur tous les PIDs Python avant relance |

---

### Session — 2026-06-25

**Améliorations apportées**

| Fichier | Changement |
|---|---|
| `frontend/src/pages/UserDashboard.jsx` | Remplacement de l'icône loupe (`BigSearchIcon`) par le **logo EY** (`ey.jpg`) dans l'état vide. Refonte complète du composant : ajout d'un wrapper `emptyLogoWrap` avec halo radial animé et anneau lumineux, d'un badge overline "EY · Agentic Intelligence", d'un séparateur dégradé jaune, et reformulation du label des suggestions ("Essayez :"). |
| `frontend/src/pages/UserDashboard.module.css` | Nouveaux styles pour l'état vide : `.emptyLogoWrap` (positionnement relatif), `.emptyLogoHalo` (animation `haloPulse` — glow jaune radial), `.emptyLogoRing` (animation `ringFade` — bordure jaune clignotante), `.emptyHeadingGroup` / `.emptyOverline` / `.emptyDivider`. Chips améliorées : hover avec élévation `translateY(-1px)` et ombre portée. |
| `backend/rag/step4_embedder.py` | Ajout du mode **offline** : `SentenceTransformer(MODEL_NAME, local_files_only=True)` avec fallback vers le téléchargement si le modèle n'est pas en cache. Résout l'erreur `[Errno 11001] getaddrinfo failed` lorsque HuggingFace Hub est inaccessible (pas de connexion réseau). |

---

### Session — 2026-06-24

**Améliorations apportées**

| Fichier | Changement |
|---|---|
| `rag/step3_chunker.py` | Remplacement du token-based recursive splitter par un **Semantic Chunker** : embeddings BGE-M3 par fenêtre de 3 phrases, seuil de similarité cosinus fixe à **0.75**, plafond de **512 tokens** avec overlap de 100 tokens. Suppression de la dépendance numpy (cosinus calculé en pur Python). |
| `rag/step4_embedder.py` | Retour au modèle **BAAI/bge-m3** (570M, 1024 dims, 8192 tokens) — utilisé à la fois pendant le chunking (fenêtres de phrases) et pour l'indexation finale et les requêtes. |
| `backend/main.py` | Renommage de `index_documents.py` → `main.py` (script d'indexation). |
| `backend/app.py` | Renommage de `main.py` → `app.py` (entrée FastAPI). |
| `requirements.txt` | Ajout de `tiktoken` (comptage de tokens via cl100k_base). |
| `commands.txt` | Commande de lancement mise à jour : `uvicorn app:app --reload`. |
| `routers/search.py`, `metrics.py`, `test_fixes.py` | Références à `index_documents.py` mises à jour vers `main.py`. |

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

---

### Session — 2026-06-19 (update 2)

**Améliorations apportées**

| Fichier | Changement |
|---|---|
| `rag/step2_metadata.py` | Ajout du **classificateur TDR** : système de scoring multi-niveaux (filename +15, signaux forts +7/+4, signaux structurels +2, anti-signaux −8/−3). Retourne `is_tdr`, `tdr_confidence`, `tdr_label`, `tdr_score` pour chaque document. |
| `rag/step3_chunker.py` | Remplacement du découpage fixe (500 mots) par un **Recursive Character Splitter** : séparateurs `\n\n → \n → ". " → " " → ""`, `CHUNK_SIZE = 1 500 chars`, `OVERLAP = 200 chars`. Préserve les limites naturelles de paragraphes et de phrases. |
| `rag/step5_vector_store.py` | Stockage de `is_tdr`, `tdr_confidence`, `tdr_label` dans les métadonnées ChromaDB. Support du filtre `only_tdr` (`{"is_tdr": {"$eq": true}}`). Retour de ces champs dans les résultats de recherche. |
| `routers/search.py` | Ajout de `only_tdr: bool` dans le modèle `Filters`. Retour de `is_tdr`, `tdr_confidence`, `tdr_label` dans `sources` et `similar_missions`. |
| `main.py` (ex `index_documents.py`) | Affichage d'un badge `[TDR XX%]` ou `[NON-TDR]` par document lors de l'indexation, avec score TDR et label. Résumé final TDR vs non-TDR avec liste des fichiers non-TDR. |

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

Built for EY · RAG pipeline powered by BGE-M3, ChromaDB & Groq

</div>
