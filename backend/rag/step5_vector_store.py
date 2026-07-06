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
        # Store as both bool and string to handle ChromaDB serialization differences
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

    where = _build_where(filters) if filters else None

    # Count how many chunks actually match the filter before querying.
    # Without this, ChromaDB raises an error when top_k > matching_count,
    # and the old code silently fell back to unfiltered results.
    if where:
        try:
            matching_ids = col.get(where=where, include=[])["ids"]
            n_results    = min(top_k, len(matching_ids))
        except Exception:
            n_results = 0
        if n_results == 0:
            return []
    else:
        n_results = min(top_k, total)

    kwargs = {
        "query_embeddings": [query_embedding],
        "n_results":        n_results,
        "include":          ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    try:
        results = col.query(**kwargs)
    except Exception as exc:
        print(f"[!] ChromaDB query error: {exc}")
        return []

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
            "chunk_index":    meta.get("chunk_index", 0),
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


def get_chunks_by_index(source_filename: str, chunk_indices: set[int]) -> list[dict]:
    """Fetch specific chunks of a document by their chunk_index (for
    neighbour expansion: a section often spills into the next chunk, which
    rarely matches the query wording on its own)."""
    if not chunk_indices:
        return []
    col   = get_collection()
    where = {"source": {"$eq": source_filename}}
    try:
        result = col.get(where=where, include=["documents", "metadatas"])
    except Exception as exc:
        print(f"[!] get_chunks_by_index error: {exc}")
        return []

    out = []
    for doc, meta in zip(result["documents"], result["metadatas"]):
        if meta.get("chunk_index") in chunk_indices:
            out.append({
                "text":           doc,
                "source":         meta.get("source", ""),
                "page":           meta.get("page", 1),
                "chunk_index":    meta.get("chunk_index", 0),
                "score":          0.0,   # caller assigns a score
                "country":        meta.get("country", ""),
                "domain":         meta.get("domain", ""),
                "donor":          meta.get("donor", ""),
                "year":           meta.get("year", ""),
                "is_tdr":         bool(meta.get("is_tdr", False)),
                "tdr_confidence": float(meta.get("tdr_confidence", 0.0)),
                "tdr_label":      meta.get("tdr_label", "Indéterminé"),
            })
    return out


def search_in_source(query_embedding: list[float], source_filename: str, top_k: int = 8) -> list[dict]:
    """Retrieve the chunks of a named document ranked by relevance to the query.

    Ranking by real similarity (instead of returning the whole document in
    page order with a fake score) matters because the generator can only fit
    a handful of chunks in its context window: if the answer lives on the
    last page, page order would crowd it out with irrelevant early pages.
    The caller re-sorts the selected chunks by page for natural reading order.
    """
    col   = get_collection()
    where = {"source": {"$eq": source_filename}}

    try:
        matching = col.get(where=where, include=[])["ids"]
        if not matching:
            return []
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, len(matching)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        print(f"[!] search_in_source error: {exc}")
        return []

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
            "chunk_index":    meta.get("chunk_index", 0),
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


def list_source_filenames() -> set[str]:
    """Return the set of distinct stored source filenames."""
    col = get_collection()
    try:
        # limit must stay well above the total chunk count (917 today) or
        # named-document detection silently stops seeing some documents.
        sample = col.get(limit=50_000, include=["metadatas"])
        return {m["source"] for m in sample["metadatas"] if m.get("source")}
    except Exception:
        return set()


def resolve_source_filename(name_hint: str) -> str | None:
    """Find the exact stored source filename that best matches a name hint."""
    hint_lower = name_hint.lower().replace(".pdf", "").replace(".PDF", "")
    for src in list_source_filenames():
        if hint_lower in src.lower().replace(".pdf", "").replace(".PDF", ""):
            return src
    return None


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
