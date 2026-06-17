from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth_utils import get_current_user
from rag.embedder     import embed_query
from rag.vector_store import search, collection_count
from rag.generator    import generate_answer

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = ""


@router.get("/status")
def search_status(_=Depends(get_current_user)):
    count = collection_count()
    return {"indexed_chunks": count, "ready": count > 0}


@router.post("/tdr")
def search_tdr(body: SearchRequest, _=Depends(get_current_user)):
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if collection_count() == 0:
        raise HTTPException(
            status_code=503,
            detail="RAG pipeline not ready. Run index_documents.py first.",
        )

    query_vec = embed_query(body.query)
    hits = search(query_vec, top_k=8)
    answer = generate_answer(body.query, hits)

    seen = set()
    sources = []
    for h in hits:
        if h["source"] not in seen:
            seen.add(h["source"])
            sources.append({
                "filename": h["source"],
                "page":     h["page"],
                "excerpt":  h["text"][:220] + "…" if len(h["text"]) > 220 else h["text"],
                "score":    h["score"],
            })

    return {
        "answer":  answer,
        "sources": sources,
        "query":   body.query,
    }
