import re

MODEL_NAME = "BAAI/bge-m3"

_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        print(f"Loading embedding model: {MODEL_NAME} ...")
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


def embed_documents(texts: list[str]) -> list[list[float]]:
    model   = get_model()
    cleaned = [_clean(t) for t in texts]
    return model.encode(cleaned, show_progress_bar=True, normalize_embeddings=True).tolist()


def embed_query(query: str) -> list[float]:
    model = get_model()
    return model.encode(query.strip(), normalize_embeddings=True).tolist()
