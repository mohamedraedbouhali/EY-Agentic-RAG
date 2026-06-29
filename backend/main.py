"""
Run this script ONCE to index all PDFs into ChromaDB.
Usage:  python main.py
Re-run if you add or replace PDF files in data/.
"""
import sys
import os
import json

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from rag.step1_extractor    import load_all_pdfs
from rag.step3_chunker      import split_into_chunks
from rag.step4_embedder     import embed_documents
from rag.step5_vector_store import store_chunks
from rag.step2_metadata     import extract_metadata

DATA_FOLDER    = os.path.join(os.path.dirname(__file__), "..", "data")


def _filter_chunks(chunks: list[dict]) -> list[dict]:
    """Remove garbage chunks: page markers, empty table rows, section numbers, etc."""
    import re
    def _clean(t):
        t = re.sub(r'\[Page \d+\]', '', t)
        t = re.sub(r'\[Tableau[^\]]*\]', '', t)
        t = re.sub(r'\|[-\s|:]+\|', ' ', t)
        t = re.sub(r'\|', ' ', t)
        t = re.sub(r'\s+', ' ', t).strip()
        return t
    result = []
    for c in chunks:
        cleaned = _clean(c["text"])
        words = cleaned.split()
        if len(words) < 8:
            continue
        # Drop repetitive chunks — low unique word ratio
        unique_ratio = len(set(w.lower() for w in words)) / len(words)
        if unique_ratio < 0.35:
            continue
        # Drop chunks where any 2-word phrase repeats more than 3 times
        from collections import Counter
        bigrams = [f"{words[i].lower()} {words[i+1].lower()}" for i in range(len(words) - 1)]
        if bigrams and max(Counter(bigrams).values()) > 3:
            continue
        result.append(c)
    return result
CHROMA_PATH    = os.path.join(os.path.dirname(__file__), "chroma_db")
FILTERS_CACHE  = os.path.join(os.path.dirname(__file__), "filters_cache.json")


def main():
    print("=" * 60)
    print("EY Agentic RAG — Document Indexing")
    print("=" * 60)

    if not os.path.isdir(DATA_FOLDER):
        print(f"ERROR: data folder not found at {DATA_FOLDER}")
        sys.exit(1)

    # Check for existing index using the folder — avoids initialising ChromaDB
    # with the old collection (which would cache the wrong embedding dimension)
    if os.path.exists(CHROMA_PATH) and os.listdir(CHROMA_PATH):
        answer = input("\nExisting index found. Re-index from scratch? (y/n): ").strip().lower()
        if answer == "y":
            import shutil
            print("Clearing existing index...")
            shutil.rmtree(CHROMA_PATH)
        else:
            print("Aborted. Existing index kept.")
            return

    # Step 1 — Extract
    print("\n[1/3] Extracting text from PDFs...")
    documents = load_all_pdfs(DATA_FOLDER)
    if not documents:
        print("No usable PDFs found.")
        return
    print(f"  -> {len(documents)} documents loaded")

    # Step 2 — Chunk + extract metadata
    print("\n[2/3] Splitting into chunks and extracting metadata...")
    all_chunks  = []
    filter_values = {"country": set(), "region": set(), "domain": set(), "donor": set(), "year": set()}
    tdr_docs:     list[str] = []
    non_tdr_docs: list[str] = []

    for doc in documents:
        meta = extract_metadata(doc["text"], doc["filename"])

        # Collect available filter values (exclude "Inconnu" and boolean/float fields)
        for key in ("country", "region", "domain", "donor", "year"):
            val = meta.get(key, "Inconnu")
            if val != "Inconnu":
                filter_values[key].add(val)

        chunks = split_into_chunks(doc["text"], doc["filename"])
        chunks = _filter_chunks(chunks)
        for chunk in chunks:
            chunk.update(meta)
        all_chunks.extend(chunks)

        # TDR classification badge
        tdr_badge = f"[TDR {meta['tdr_confidence']*100:.0f}%]" if meta["is_tdr"] else "[NON-TDR]"
        if meta["is_tdr"]:
            tdr_docs.append(doc["filename"])
        else:
            non_tdr_docs.append(doc["filename"])

        print(
            f"  {tdr_badge:<12} {doc['filename']}: {len(chunks)} chunks"
            f" | {meta['tdr_label']:<16} (score {meta['tdr_score']:+.0f})"
            f" | {meta['domain']} | {meta['country']} | {meta['year']}"
        )

    print(f"\n  -> {len(all_chunks)} total chunks")
    print(f"  -> TDR documents    : {len(tdr_docs)}")
    print(f"  -> Non-TDR documents: {len(non_tdr_docs)}")
    if non_tdr_docs:
        print("  -> Non-TDR list:")
        for fn in non_tdr_docs:
            print(f"       - {fn}")

    # Save filter values for the API
    cache = {k: sorted(v) for k, v in filter_values.items()}
    with open(FILTERS_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"  -> Filter cache saved ({sum(len(v) for v in cache.values())} values)")

    # Step 3 — Embed + Store
    print("\n[3/3] Embedding and storing chunks...")
    BATCH = 64
    for i in range(0, len(all_chunks), BATCH):
        batch      = all_chunks[i: i + BATCH]
        texts      = [c["text"] for c in batch]
        embeddings = embed_documents(texts)
        store_chunks(batch, embeddings)
        print(f"  Stored {min(i + BATCH, len(all_chunks))}/{len(all_chunks)} chunks")

    print("\n" + "=" * 60)
    print(f"Done! {len(all_chunks)} chunks indexed from {len(documents)} documents "
          f"({len(tdr_docs)} TDR, {len(non_tdr_docs)} non-TDR).")
    print("=" * 60)


if __name__ == "__main__":
    main()
