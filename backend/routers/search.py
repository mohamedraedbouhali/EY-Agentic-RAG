import os
import re
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from bson import ObjectId
from auth_utils             import get_current_user
from database               import conversations_col
from rag.step4_embedder     import embed_query
from rag.step5_vector_store import search, collection_count
from rag.step6_generator    import generate_answer

router = APIRouter(prefix="/search", tags=["search"])

FILTERS_CACHE = os.path.join(os.path.dirname(__file__), "..", "filters_cache.json")

MAX_HISTORY = 8  # last 4 turns — prevent context overflow on Groq


class HistoryMessage(BaseModel):
    role: str
    content: str


class Filters(BaseModel):
    country:  list[str] = []
    region:   list[str] = []
    domain:   list[str] = []
    donor:    list[str] = []
    year:     list[str] = []
    only_tdr: bool = False


class SearchRequest(BaseModel):
    query:   str = ""
    history: list[HistoryMessage] = []
    filters: Filters = Filters()


@router.get("/status")
def search_status(_=Depends(get_current_user)):
    count = collection_count()
    return {"indexed_chunks": count, "ready": count > 0}


@router.get("/filters")
def get_filters(_=Depends(get_current_user)):
    if os.path.exists(FILTERS_CACHE):
        with open(FILTERS_CACHE, encoding="utf-8") as f:
            return json.load(f)
    from rag.step2_metadata import COUNTRIES, DONORS, DOMAINS, REGION_MAP
    return {
        "domain":  sorted(DOMAINS.keys()),
        "country": sorted(COUNTRIES.keys()),
        "region":  sorted(REGION_MAP.keys()),
        "donor":   sorted(DONORS.keys()),
        "year":    [],
    }


def _clean_excerpt(text: str) -> str:
    text = re.sub(r'\[Page \d+\]', '', text)
    text = re.sub(r'\[Tableau[^\]]*\]', '', text)
    text = re.sub(r'\|[-\s|:]+\|', ' ', text)
    text = re.sub(r'\|', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _is_meaningful(text: str) -> bool:
    return len(_clean_excerpt(text).split()) >= 15


def _extract_profiles_competencies(chunks: list[dict]) -> tuple[list, list]:
    """Simple keyword-based extraction of profiles/competencies from TdR chunks."""
    profiles: list[str] = []
    competencies: list[str] = []
    seen: set[str] = set()

    profile_kws     = ['profil', 'qualification', 'diplôme', "niveau d'études",
                       'consultant senior', 'expert senior', 'chef de mission', 'candidat']
    competency_kws  = ['compétence', 'expérience en ', 'expérience dans',
                       'maîtrise de', 'connaissance de', 'expertise en', 'capacité']

    for chunk in chunks:
        for line in chunk['text'].split('\n'):
            s = line.strip()
            if not s or len(s) < 15 or len(s) > 260:
                continue
            lower = s.lower()
            clean = re.sub(r'^[\-\*\•\d\.]+\s*', '', s).strip()
            if not clean or clean in seen:
                continue

            if any(kw in lower for kw in profile_kws) and len(clean) > 20:
                seen.add(clean)
                profiles.append(clean[:160])
            elif any(kw in lower for kw in competency_kws) and len(clean) > 20:
                seen.add(clean)
                competencies.append(clean[:160])

    return profiles[:4], competencies[:4]


@router.get("/history")
def get_history(current_user=Depends(get_current_user)):
    uid = str(current_user["_id"])
    docs = list(
        conversations_col.find({"user_id": uid}, {"_id": 0})
        .sort("timestamp", 1)
        .limit(100)
    )
    return docs


@router.delete("/history")
def clear_history(current_user=Depends(get_current_user)):
    uid = str(current_user["_id"])
    conversations_col.delete_many({"user_id": uid})
    return {"deleted": True}


def _save_messages(user_id: str, query: str, answer: str, sources: list, similar_missions: list):
    now = datetime.now(timezone.utc)
    conversations_col.insert_many([
        {"user_id": user_id, "role": "user",      "content": query,  "timestamp": now},
        {"user_id": user_id, "role": "assistant",  "content": answer,
         "sources": sources, "similar_missions": similar_missions, "timestamp": now},
    ])


@router.post("/tdr")
def search_tdr(body: SearchRequest, current_user=Depends(get_current_user)):
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if collection_count() == 0:
        raise HTTPException(
            status_code=503,
            detail="RAG pipeline not ready. Run main.py first.",
        )

    try:
        query_vec = embed_query(body.query)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur d'embedding: {exc}")

    try:
        filters = body.filters.model_dump()
        hits    = search(query_vec, top_k=15, filters=filters)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur de recherche vectorielle: {exc}")

    MIN_SCORE = 0.30
    hits = [h for h in hits if h["score"] >= MIN_SCORE and _is_meaningful(h["text"])]

    # No relevant chunks found — return standard message without calling the LLM
    if not hits:
        answer = "Cette information ne figure pas dans les documents fournis."
        _save_messages(str(current_user["_id"]), body.query, answer, [], [])
        return {"answer": answer, "sources": [], "similar_missions": [], "query": body.query}

    # Limit history to prevent Groq context overflow
    history = [{"role": m.role, "content": m.content} for m in body.history][-MAX_HISTORY:]

    try:
        answer = generate_answer(body.query, hits, history)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erreur du modèle de langage: {exc}")

    # Group chunks by source document
    doc_chunks: dict[str, list] = {}
    for h in hits:
        doc_chunks.setdefault(h["source"], []).append(h)

    seen_docs: set[str] = set()
    sources: list[dict] = []

    for h in hits[:5]:
        if h["source"] in seen_docs:
            continue
        seen_docs.add(h["source"])
        excerpt = _clean_excerpt(h["text"])
        profiles, competencies = _extract_profiles_competencies(doc_chunks[h["source"]])
        sources.append({
            "filename":       h["source"],
            "page":           h["page"],
            "excerpt":        excerpt[:300] + "…" if len(excerpt) > 300 else excerpt,
            "score":          h["score"],
            "country":        h.get("country", ""),
            "domain":         h.get("domain", ""),
            "donor":          h.get("donor", ""),
            "year":           h.get("year", ""),
            "is_tdr":         h.get("is_tdr", False),
            "tdr_confidence": h.get("tdr_confidence", 0.0),
            "tdr_label":      h.get("tdr_label", "Indéterminé"),
            "profiles":       profiles,
            "competencies":   competencies,
        })

    # Similar missions: unique documents beyond the primary hit
    primary = sources[0]["filename"] if sources else None
    similar_missions: list[dict] = []
    for s in sources[1:]:
        similar_missions.append({
            "filename":       s["filename"],
            "score":          s["score"],
            "country":        s["country"],
            "domain":         s["domain"],
            "donor":          s["donor"],
            "year":           s["year"],
            "is_tdr":         s.get("is_tdr", False),
            "tdr_label":      s.get("tdr_label", "Indéterminé"),
        })

    _save_messages(str(current_user["_id"]), body.query, answer, sources, similar_missions)
    return {
        "answer":           answer,
        "sources":          sources,
        "similar_missions": similar_missions,
        "query":            body.query,
    }
