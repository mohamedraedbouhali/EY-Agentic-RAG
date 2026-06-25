import re

MODEL_NAME = "BAAI/bge-m3"

_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        print(f"Loading embedding model: {MODEL_NAME} ...")
        try:
            _model = SentenceTransformer(MODEL_NAME, local_files_only=True)
        except Exception:
            _model = SentenceTransformer(MODEL_NAME)
        print("Model loaded.")
    return _model


def _clean(text: str) -> str:
    """Strip indexing noise before embedding so the vector represents real content."""
    text = re.sub(r'\[Page \d+\]', '', text)
    text = re.sub(r'\[Tableau[^\]]*\]', '', text)
    text = re.sub(r'\|[-\s|:]+\|', ' ', text)   # table separator rows  |---|---|
    text = re.sub(r'\|', ' ', text)              # remaining pipe chars
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _encode(fn):
    """Run fn(model) and reload the model once if the client was closed."""
    global _model
    try:
        return fn(get_model())
    except Exception as e:
        if "client has been closed" in str(e).lower():
            _model = None
            return fn(get_model())
        raise


def embed_documents(texts: list[str]) -> list[list[float]]:
    cleaned = [_clean(t) for t in texts]
    return _encode(lambda m: m.encode(cleaned, show_progress_bar=True, normalize_embeddings=True).tolist())


def embed_query(query: str) -> list[float]:
    return _encode(lambda m: m.encode(query.strip(), normalize_embeddings=True).tolist())
