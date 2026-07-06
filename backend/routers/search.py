import os
import re
import json
import unicodedata
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from bson import ObjectId
from auth_utils             import get_current_user
from database               import conversations_col
from rag.step4_embedder     import embed_query
from rag.step5_vector_store import (
    search, search_in_source, list_source_filenames, collection_count,
    get_chunks_by_index,
)
from rag.step6_generator    import generate_answer

router = APIRouter(prefix="/search", tags=["search"])

FILTERS_CACHE = os.path.join(os.path.dirname(__file__), "..", "filters_cache.json")
TITLES_CACHE  = os.path.join(os.path.dirname(__file__), "..", "titles_cache.json")

MAX_HISTORY = 8  # last 4 turns — prevent context overflow on Groq


def _fold(s: str) -> str:
    """Lowercase and strip accents. OCR'd documents are stored WITHOUT
    accents ("generales") while user queries have them ("générales") —
    every textual comparison must fold both sides or scanned documents
    silently lose keyword matching."""
    return (unicodedata.normalize("NFD", s)
            .encode("ascii", "ignore").decode("ascii").lower())


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
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.DOTALL)
    text = re.sub(r'</?[a-zA-Z][a-zA-Z0-9]*\s*/?>', ' ', text)  # <br>, <u>, <sup>…
    text = re.sub(r'\|[-\s|:]+\|', ' ', text)
    text = re.sub(r'\|', ' ', text)
    text = re.sub(r'#{1,6}\s', ' ', text)
    text = re.sub(r'[*_`]{1,3}', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _is_meaningful(text: str) -> bool:
    return len(_clean_excerpt(text).split()) >= 8


# Table-of-contents lines: leader dots followed by a page number
# ("ACTIVITÉS DES EXPERTS ............... 4").
_TOC_DOTS_RE = re.compile(r'\.{6,}\s*\d+')

def _is_toc_chunk(text: str) -> bool:
    """Detect table-of-contents chunks. They match section-title queries
    strongly (they contain every heading of the document) but never hold the
    actual content — worse, the LLM finds the asked-for heading there, sees
    nothing under it, and gives up instead of reading the real section."""
    return len(_TOC_DOTS_RE.findall(text)) >= 3


# Matches filename-like tokens: hyphenated/underscored words of 5+ chars
_FILENAME_RE = re.compile(r'\b([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9\-_]{4,})\b')

# Generic RFP/TdR boilerplate vocabulary — words that show up in almost every
# call-for-tender document's own text ("avis de manifestation d'intérêt",
# "termes de référence", "pièces constitutives"...). If a filename happens to
# contain one of these as a substring, that's coincidence, not the user
# naming the document, so they must never count as naming evidence on their
# own — only genuinely distinctive words (proper nouns, project codes) can.
_GENERIC_TDR_TERMS = {
    "avis", "appel", "action", "contexte", "consultation", "consultance",
    "sollicitation", "manifestation", "interet", "constitutives", "pieces",
    "termes", "reference", "references", "referentiel", "mission", "missions",
    "assistance", "technique", "appui", "formation", "evaluation", "projet",
    "programme", "rapport", "national", "service", "services", "selection",
    "recrutement", "candidature", "candidat", "expert", "consultant",
}

# Below this length a single matching word is common enough in everyday TdR
# vocabulary that a substring hit is more likely a coincidence than the user
# actually naming a document.
_SINGLE_WORD_MIN_LEN = 15


def _norm_phrase(s: str) -> str:
    """Fold accents/case and collapse punctuation to single spaces, so
    'COM N° 01 DC' and 'com n 01 dc' compare equal."""
    return re.sub(r'[^a-z0-9]+', ' ', _fold(s)).strip()


def _detect_named_document(query: str) -> str | None:
    """Return the stored source filename if the query explicitly names a document.

    A filename is only considered "named" when there is strong evidence:
    the query contains the whole filename stem as a phrase, or several
    distinct non-generic query words match the same stored filename, or one
    very long/specific word matches it (too long to be a coincidental
    overlap with common domain vocabulary).
    """
    # Exact stem-phrase match — the only rule that can catch SHORT document
    # names ("COM N° 01 DC", "TDR-ERP", "tdr-3") whose individual tokens are
    # all below the token-matching length threshold.
    q_norm = _norm_phrase(query)
    best_stem = None
    for src in list_source_filenames():
        stem = _norm_phrase(re.sub(r'\.pdf$', '', src, flags=re.IGNORECASE))
        if len(stem.replace(" ", "")) < 4:
            continue
        if re.search(rf'(?<![a-z0-9]){re.escape(stem)}(?![a-z0-9])', q_norm):
            if best_stem is None or len(stem) > len(best_stem[1]):
                best_stem = (src, stem)
    if best_stem:
        return best_stem[0]

    candidates = {
        _fold(c) for c in _FILENAME_RE.findall(query)
        if len(c) >= 6 and _fold(c) not in _GENERIC_TDR_TERMS
    }
    if not candidates:
        return None

    sources = list_source_filenames()
    matches: dict[str, set[str]] = {}
    for src in sources:
        src_folded = _fold(src).replace(".pdf", "")
        hit_words = {c for c in candidates if c in src_folded}
        if hit_words:
            matches[src] = hit_words

    if not matches:
        return None

    best_doc, best_words = max(matches.items(), key=lambda kv: len(kv[1]))
    if len(best_words) >= 2:
        return best_doc
    if len(next(iter(best_words))) >= _SINGLE_WORD_MIN_LEN:
        return best_doc

    # Fallback: title matching — lets users refer to documents by content title
    # instead of filename (e.g. "Concertations élargies avec les jeunes filles")
    return _detect_by_title(query)


def _detect_by_title(query: str) -> str | None:
    """Match query significant words against stored document titles."""
    if not os.path.exists(TITLES_CACHE):
        return None
    try:
        with open(TITLES_CACHE, encoding="utf-8") as f:
            titles: dict = json.load(f)
    except Exception:
        return None

    query_words = set(re.findall(r'[a-z]{6,}', _fold(query)))
    # Remove generic TDR vocabulary to avoid false positives
    query_words -= _GENERIC_TDR_TERMS
    if not query_words:
        return None

    best_file, best_score = None, 0
    for filename, title in titles.items():
        # substring containment, not word equality: OCR'd titles have glued
        # words ("larealisationdeprototypes") that never equal a query word
        # but still CONTAIN it
        title_folded = _fold(title)
        score = sum(1 for w in query_words if w in title_folded)
        if score > best_score:
            best_score = score
            best_file  = filename

    return best_file if best_score >= 3 else None


# Section/article numbers like "1.1", "2.3.4" — when the user asks about a
# specific numbered activity, chunks containing that exact number are almost
# certainly the right ones, regardless of their raw embedding similarity.
_SECTION_NUM_RE = re.compile(r'\b\d+(?:\.\d+)+\b')


def _lexical_rerank(query: str, hits: list[dict]) -> list[dict]:
    """Blend vector similarity with exact-term overlap.

    Pure embedding similarity ranks boilerplate that merely resembles the
    topic (repeated headers/footers) above the chunk holding the actual
    answer. Boosting chunks that contain the question's own words — and
    especially its section numbers — puts the factual chunk back on top.
    """
    words    = set(re.findall(r'[a-z]{4,}', _fold(query)))
    sections = set(_SECTION_NUM_RE.findall(query))
    if not words and not sections:
        return hits

    for h in hits:
        text = _fold(h["text"])
        overlap = sum(1 for w in words if w in text) / max(len(words), 1)
        section_bonus = 0.15 if any(s in h["text"] for s in sections) else 0.0
        h["score"] = round(h["score"] + 0.10 * overlap + section_bonus, 4)

    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits


def _expand_neighbors(hits: list[dict], max_seeds: int = 4) -> list[dict]:
    """Pull in the chunks adjacent to the best hits (same document, index ±1).

    A document section often spans two consecutive chunks; the continuation
    chunk rarely repeats the query's wording, so vector search misses it and
    the LLM only ever sees the first half of the section. Each neighbour is
    inserted right after its seed with a slightly lower score, so the
    generator's budget fills with complete sections instead of off-topic
    chunks from other documents.
    """
    have = {(h["source"], h.get("chunk_index")) for h in hits}
    expanded: list[dict] = []

    for rank, seed in enumerate(hits):
        expanded.append(seed)
        if rank >= max_seeds:
            continue
        ci = seed.get("chunk_index")
        if ci is None:
            continue
        want = {n for n in (ci - 1, ci + 1)
                if n >= 0 and (seed["source"], n) not in have}
        if not want:
            continue
        for extra in get_chunks_by_index(seed["source"], want):
            extra["score"] = round(max(seed["score"] - 0.01, 0.0), 4)
            expanded.append(extra)
            have.add((extra["source"], extra["chunk_index"]))

    return expanded


def _extract_profiles_competencies(chunks: list[dict]) -> tuple[list, list]:
    """Simple keyword-based extraction of profiles/competencies from TdR chunks."""
    profiles: list[str] = []
    competencies: list[str] = []
    seen: set[str] = set()

    # accent-free (folded) keywords — matched against folded text so both
    # native-text and OCR'd (accent-less) documents hit
    profile_kws     = ['profil', 'qualification', 'diplome', "niveau d'etudes",
                       'consultant senior', 'expert senior', 'chef de mission', 'candidat']
    competency_kws  = ['competence', 'experience en ', 'experience dans',
                       'maitrise de', 'connaissance de', 'expertise en', 'capacite']

    for chunk in chunks:
        for line in chunk['text'].split('\n'):
            s = line.strip()
            if not s or len(s) < 15 or len(s) > 260:
                continue
            lower = _fold(s)
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

        # If the query explicitly names a document, search within it first.
        named_doc = _detect_named_document(body.query)
        if named_doc:
            # top_k=40 covers the whole document so the LLM sees ALL sections
            # (largest current document has 30+ chunks; search_in_source caps
            # n_results at the document's real chunk count)
            targeted = search_in_source(query_vec, named_doc, top_k=40)
            general  = search(query_vec, top_k=5, filters=filters)
            # Merge: targeted hits first, then general hits not from the same doc
            seen = {h["source"] + str(h["page"]) for h in targeted}
            hits = targeted + [h for h in general if h["source"] + str(h["page"]) not in seen]
        else:
            hits = search(query_vec, top_k=20, filters=filters)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur de recherche vectorielle: {exc}")

    # Lower threshold for named-document queries — we already know the document
    # is relevant, so we just need enough chunks to cover multi-page tables.
    MIN_SCORE = 0.20 if named_doc else 0.30
    hits = [h for h in hits
            if h["score"] >= MIN_SCORE and _is_meaningful(h["text"])
            and not _is_toc_chunk(h["text"])]

    if named_doc:
        # The named document must never lose context-budget slots to other
        # documents: the query text often contains the document's own title,
        # which makes OTHER documents' title pages score deceptively high.
        # Rerank each group separately and keep the named document first.
        targeted_hits = [h for h in hits if h["source"] == named_doc]
        other_hits    = [h for h in hits if h["source"] != named_doc]
        hits = (_lexical_rerank(body.query, targeted_hits)
                + _lexical_rerank(body.query, other_hits))
    else:
        hits = _lexical_rerank(body.query, hits)
    hits = _expand_neighbors(hits)

    # For a document-scoped question, only that document's chunks go to the
    # LLM — chunks from other documents can't hold the answer, they only
    # burn the context budget (other documents stay in "similar missions").
    gen_hits = [h for h in hits if h["source"] == named_doc] if named_doc else hits

    # No relevant chunks found — distinguish between filter mismatch and absent content
    if not hits:
        active_filters = {k: v for k, v in body.filters.model_dump().items() if v}
        if active_filters:
            answer = "Aucun document correspondant aux filtres sélectionnés ne contient cette information."
        else:
            answer = "Cette information ne figure pas dans les documents fournis."
        _save_messages(str(current_user["_id"]), body.query, answer, [], [])
        return {"answer": answer, "sources": [], "similar_missions": [], "chunks": [], "query": body.query}

    # Limit history to prevent Groq context overflow
    history = [{"role": m.role, "content": m.content} for m in body.history][-MAX_HISTORY:]

    try:
        answer = generate_answer(body.query, gen_hits, history)
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
        "chunks":           [
            {"text": h["text"], "source": h["source"], "page": h["page"], "score": h["score"]}
            for h in hits
        ],
        "query":            body.query,
    }
