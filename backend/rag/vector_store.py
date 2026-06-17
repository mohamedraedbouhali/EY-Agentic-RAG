import chromadb
import os

CHROMA_PATH  = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
COLLECTION   = "tdr_documents"

_client     = None
_collection = None


def get_collection():
    global _client, _collection
    if _collection is None:
        _client     = chromadb.PersistentClient(path=os.path.abspath(CHROMA_PATH))
        _collection = _client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def store_chunks(chunks: list[dict], embeddings: list[list[float]]):
    col = get_collection()
    col.add(
        ids        = [c["id"] for c in chunks],
        documents  = [c["text"] for c in chunks],
        embeddings = embeddings,
        metadatas  = [
            {"source": c["source"], "page": c["page"], "chunk_index": c["chunk_index"]}
            for c in chunks
        ],
    )


def search(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    col = get_collection()
    results = col.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, col.count()) if col.count() > 0 else 1,
        include=["documents", "metadatas", "distances"],
    )
    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({
            "text":     doc,
            "source":   meta.get("source", ""),
            "page":     meta.get("page", 1),
            "score":    round(1 - dist, 4),   # cosine distance → similarity
        })
    return hits


def collection_count() -> int:
    try:
        return get_collection().count()
    except Exception:
        return 0


def clear_collection():
    col = get_collection()
    col.delete(where={"source": {"$ne": ""}})
