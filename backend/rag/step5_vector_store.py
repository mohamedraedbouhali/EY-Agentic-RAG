import chromadb
import os

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
COLLECTION  = "tdr_documents"

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
            {
                "source":         c["source"],
                "page":           c["page"],
                "chunk_index":    c["chunk_index"],
                "country":        c.get("country",        "Inconnu"),
                "region":         c.get("region",         "Inconnu"),
                "domain":         c.get("domain",         "Inconnu"),
                "donor":          c.get("donor",          "Inconnu"),
                "year":           c.get("year",           "Inconnu"),
                "is_tdr":         bool(c.get("is_tdr",         False)),
                "tdr_confidence": float(c.get("tdr_confidence", 0.0)),
                "tdr_label":      c.get("tdr_label",      "Indéterminé"),
            }
            for c in chunks
        ],
    )


def _build_where(filters: dict) -> dict | None:
    conditions = []
    for key in ("country", "region", "domain", "donor", "year"):
        values = [v for v in filters.get(key, []) if v]
        if values:
            conditions.append({key: {"$in": values}})
    if filters.get("only_tdr"):
        conditions.append({"is_tdr": {"$eq": True}})
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def search(query_embedding: list[float], top_k: int = 8, filters: dict = None) -> list[dict]:
    col   = get_collection()
    total = col.count()
    if total == 0:
        return []

    where  = _build_where(filters) if filters else None
    kwargs = {
        "query_embeddings": [query_embedding],
        "n_results":        min(top_k, total),
        "include":          ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    try:
        results = col.query(**kwargs)
    except Exception:
        # If filters match 0 chunks, fall back to unfiltered search
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, total),
            include=["documents", "metadatas", "distances"],
        )

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({
            "text":           doc,
            "source":         meta.get("source", ""),
            "page":           meta.get("page", 1),
            "score":          round(1 - dist, 4),
            "country":        meta.get("country", ""),
            "domain":         meta.get("domain", ""),
            "donor":          meta.get("donor", ""),
            "year":           meta.get("year", ""),
            "is_tdr":         bool(meta.get("is_tdr", False)),
            "tdr_confidence": float(meta.get("tdr_confidence", 0.0)),
            "tdr_label":      meta.get("tdr_label", "Indéterminé"),
        })
    return hits


def collection_count() -> int:
    try:
        return get_collection().count()
    except Exception:
        return 0


def clear_collection():
    global _client, _collection
    import shutil
    _client     = None
    _collection = None
    chroma_path = os.path.abspath(CHROMA_PATH)
    if os.path.exists(chroma_path):
        shutil.rmtree(chroma_path)
