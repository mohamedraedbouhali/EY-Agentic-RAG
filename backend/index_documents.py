"""
Run this script ONCE to index all PDFs into ChromaDB.
Usage:  python index_documents.py
Re-run if you add or replace PDF files in data/.
"""
import sys
import os

# Allow imports from backend root
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from rag.extractor    import load_all_pdfs
from rag.chunker      import split_into_chunks
from rag.embedder     import embed_documents
from rag.vector_store import store_chunks, collection_count, clear_collection

DATA_FOLDER = os.path.join(os.path.dirname(__file__), "..", "data")


def main():
    print("=" * 60)
    print("EY Agentic RAG — Document Indexing")
    print("=" * 60)

    if not os.path.isdir(DATA_FOLDER):
        print(f"ERROR: data folder not found at {DATA_FOLDER}")
        sys.exit(1)

    existing = collection_count()
    if existing > 0:
        answer = input(f"\n{existing} chunks already indexed. Re-index from scratch? (y/n): ").strip().lower()
        if answer == "y":
            print("Clearing existing index...")
            clear_collection()
        else:
            print("Aborted. Existing index kept.")
            return

    # Step 1 — Extract
    print("\n[1/3] Extracting text from PDFs...")
    documents = load_all_pdfs(DATA_FOLDER)
    if not documents:
        print("No usable PDFs found.")
        return
    print(f"  → {len(documents)} documents loaded")

    # Step 2 — Chunk
    print("\n[2/3] Splitting into chunks (size=300, overlap=30)...")
    all_chunks = []
    for doc in documents:
        chunks = split_into_chunks(doc["text"], doc["filename"])
        all_chunks.extend(chunks)
        print(f"  {doc['filename']}: {len(chunks)} chunks")
    print(f"  → {len(all_chunks)} total chunks")

    # Step 3 — Embed + Store
    print("\n[3/3] Embedding and storing chunks...")
    BATCH = 64
    for i in range(0, len(all_chunks), BATCH):
        batch = all_chunks[i: i + BATCH]
        texts = [c["text"] for c in batch]
        embeddings = embed_documents(texts)
        store_chunks(batch, embeddings)
        print(f"  Stored {min(i + BATCH, len(all_chunks))}/{len(all_chunks)} chunks")

    print("\n" + "=" * 60)
    print(f"Done! {len(all_chunks)} chunks indexed from {len(documents)} documents.")
    print("You can now start the backend and use the search.")
    print("=" * 60)


if __name__ == "__main__":
    main()
